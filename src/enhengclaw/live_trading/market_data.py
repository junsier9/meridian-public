from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd

from enhengclaw.live_trading.binance_usdm_client import BinanceUsdmClient
from enhengclaw.quant_research.binance_canonical_h10d import add_binance_ohlcv_core_features


DEFAULT_USDM_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "UNIUSDT",
    "AAVEUSDT",
    "NEARUSDT",
    "FILUSDT",
    "ETCUSDT",
    "APTUSDT",
    "ARBUSDT",
)
FUTURE_LABEL_COLUMNS = ("target_forward_return", "target_up", "target_execution_forward_return", "target_execution_up")


@dataclass(frozen=True, slots=True)
class SymbolExchangeFilter:
    symbol: str
    status: str
    contract_type: str
    quote_asset: str
    step_size: float
    min_qty: float
    tick_size: float
    min_notional: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "contract_type": self.contract_type,
            "quote_asset": self.quote_asset,
            "step_size": self.step_size,
            "min_qty": self.min_qty,
            "tick_size": self.tick_size,
            "min_notional": self.min_notional,
        }

    @property
    def tradable_usdm_perp(self) -> bool:
        return self.status == "TRADING" and self.contract_type == "PERPETUAL" and self.quote_asset == "USDT"


def parse_symbol_exchange_filters(exchange_info: dict[str, Any]) -> dict[str, SymbolExchangeFilter]:
    parsed: dict[str, SymbolExchangeFilter] = {}
    for item in list(exchange_info.get("symbols") or []):
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        filters = {str(entry.get("filterType") or ""): dict(entry) for entry in list(item.get("filters") or [])}
        lot = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE") or {}
        price = filters.get("PRICE_FILTER") or {}
        notional = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        parsed[symbol] = SymbolExchangeFilter(
            symbol=symbol,
            status=str(item.get("status") or ""),
            contract_type=str(item.get("contractType") or ""),
            quote_asset=str(item.get("quoteAsset") or ""),
            step_size=_float(lot.get("stepSize"), default=0.0),
            min_qty=_float(lot.get("minQty"), default=0.0),
            tick_size=_float(price.get("tickSize"), default=0.0),
            min_notional=_float(notional.get("notional") or notional.get("minNotional"), default=0.0),
        )
    return parsed


def resolve_config_symbols(config: dict[str, Any], *, override_symbols: str | Iterable[str] | None = None) -> list[str]:
    if override_symbols:
        raw = override_symbols
    else:
        market_data = dict(config.get("market_data") or {})
        raw = market_data.get("symbols") or ",".join(DEFAULT_USDM_SYMBOLS)
    if isinstance(raw, str):
        symbols = [item.strip().upper() for item in raw.split(",")]
    else:
        symbols = [str(item).strip().upper() for item in raw]
    seen: set[str] = set()
    output: list[str] = []
    for symbol in symbols:
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        output.append(symbol)
    return output


def fetch_public_live_feature_panel(
    *,
    client: BinanceUsdmClient,
    config: dict[str, Any],
    symbols: Iterable[str],
    daily_limit: int = 140,
    four_hour_limit: int = 840,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]:
    server_time_ms = _server_time_ms(client)
    exchange_info = client.exchange_info().payload
    filters = parse_symbol_exchange_filters(exchange_info)
    requested_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    tradable_symbols = [
        symbol for symbol in requested_symbols if symbol in filters and filters[symbol].tradable_usdm_perp
    ]
    skipped_symbols = [
        symbol for symbol in requested_symbols if symbol not in set(tradable_symbols)
    ]
    daily_by_symbol: dict[str, pd.DataFrame] = {}
    four_h_by_symbol: dict[str, pd.DataFrame] = {}
    funding_by_symbol: dict[str, float] = {}
    funding_history_by_symbol: dict[str, pd.DataFrame] = {}
    funding_history_rows = 0
    funding_history_error_symbols: list[str] = []
    raw_daily_rows = 0
    raw_four_hour_rows = 0
    closed_daily_rows = 0
    closed_four_hour_rows = 0
    for symbol in tradable_symbols:
        daily_raw = klines_payload_to_frame(
            symbol=symbol,
            payload=client.klines(symbol=symbol, interval="1d", limit=daily_limit).payload,
        )
        four_h_raw = klines_payload_to_frame(
            symbol=symbol,
            payload=client.klines(symbol=symbol, interval="4h", limit=four_hour_limit).payload,
        )
        raw_daily_rows += int(len(daily_raw))
        raw_four_hour_rows += int(len(four_h_raw))
        daily_closed = _closed_kline_frame(daily_raw, server_time_ms=server_time_ms)
        four_h_closed = _closed_kline_frame(four_h_raw, server_time_ms=server_time_ms)
        closed_daily_rows += int(len(daily_closed))
        closed_four_hour_rows += int(len(four_h_closed))
        daily_by_symbol[symbol] = daily_closed
        four_h_by_symbol[symbol] = four_h_closed
        funding_start_ms = _frame_min_int(daily_closed, "open_time_ms")
        funding_end_ms = _frame_max_int(daily_closed, "close_time_ms")
        if funding_start_ms is not None and funding_end_ms is not None:
            try:
                funding_history = fetch_symbol_funding_rate_history(
                    client=client,
                    symbol=symbol,
                    start_time_ms=funding_start_ms,
                    end_time_ms=funding_end_ms,
                )
                funding_history_by_symbol[symbol] = funding_history
                funding_history_rows += int(len(funding_history))
            except Exception:
                funding_history_error_symbols.append(symbol)
        try:
            funding_by_symbol[symbol] = _float(client.premium_index(symbol=symbol).payload.get("lastFundingRate"), default=float("nan"))
        except Exception:
            funding_by_symbol[symbol] = float("nan")
    panel = build_feature_panel_from_klines(
        daily_by_symbol=daily_by_symbol,
        four_h_by_symbol=four_h_by_symbol,
        config=config,
        funding_by_symbol=funding_by_symbol,
        funding_history_by_symbol=funding_history_by_symbol,
    )
    audit = {
        "requested_symbols": requested_symbols,
        "tradable_symbols": tradable_symbols,
        "skipped_symbols": skipped_symbols,
        "daily_limit": int(daily_limit),
        "four_hour_limit": int(four_hour_limit),
        "server_time_ms": int(server_time_ms),
        "raw_daily_rows": raw_daily_rows,
        "closed_daily_rows": closed_daily_rows,
        "raw_four_hour_rows": raw_four_hour_rows,
        "closed_four_hour_rows": closed_four_hour_rows,
        "funding_history_rows": funding_history_rows,
        "funding_history_error_symbols": funding_history_error_symbols,
        "row_count": int(len(panel)),
        "source": "binance_usdm_public_rest",
    }
    return panel, audit, {symbol: filters[symbol].to_dict() for symbol in tradable_symbols}


def klines_payload_to_frame(*, symbol: str, payload: Any) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in list(payload or []):
        if len(item) < 11:
            continue
        rows.append(
            {
                "symbol": str(symbol).upper(),
                "open_time_ms": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "close_time_ms": int(item[6]),
                "quote_volume": float(item[7]),
                "trade_count": int(item[8]),
                "taker_buy_base_volume": float(item[9]),
                "taker_buy_quote_volume": float(item[10]),
            }
        )
    return pd.DataFrame(rows)


def fetch_live_spot_close_frame(
    *,
    client: BinanceUsdmClient,
    symbols: Iterable[str],
    daily_limit: int = 140,
) -> pd.DataFrame:
    """Fetch Binance SPOT daily closes for the live universe → a tidy
    [subject, date_utc, spot_close] frame to LEFT-merge onto the live (perp) panel.

    The frozen dth60 overlay's shock gauge is research-defined on spot_close
    (features.py: return_1 = spot_close.pct_change()), but the live panel is built from USDM
    futures klines (perp_close only) — this bridges that gap. `client` MUST be constructed with
    base_url=BINANCE_SPOT_MAINNET_BASE_URL. A symbol with no spot pair / failed request is SKIPPED
    (its rows then fail closed downstream via frontier_overlay_gauge_columns_missing) — never
    silently zero-filled. date_utc mirrors build_feature_panel_from_klines so the merge aligns.
    """
    rows: list[pd.DataFrame] = []
    for symbol in symbols:
        try:
            payload = client.spot_klines(symbol=str(symbol), interval="1d", limit=int(daily_limit)).payload
        except Exception:
            continue
        frame = klines_payload_to_frame(symbol=str(symbol), payload=payload)
        if frame.empty:
            continue
        out = pd.DataFrame()
        out["timestamp_ms"] = pd.to_numeric(frame["open_time_ms"], errors="coerce").astype("int64")
        out["subject"] = symbol_to_subject(str(symbol))
        out["date_utc"] = pd.to_datetime(out["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
        out["spot_close"] = pd.to_numeric(frame["close"], errors="coerce")
        rows.append(out[["subject", "date_utc", "spot_close"]])
    if not rows:
        return pd.DataFrame(columns=["subject", "date_utc", "spot_close"])
    merged = pd.concat(rows, ignore_index=True, sort=False)
    return merged.dropna(subset=["spot_close"]).drop_duplicates(subset=["subject", "date_utc"], keep="last")


def fetch_symbol_funding_rate_history(
    *,
    client: BinanceUsdmClient,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int = 1000,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    cursor = int(start_time_ms)
    safe_limit = min(max(int(limit), 1), 1000)
    while cursor <= int(end_time_ms):
        response = client.funding_rate_history(
            symbol=symbol,
            start_time=cursor,
            end_time=int(end_time_ms),
            limit=safe_limit,
        )
        frame = funding_rate_history_payload_to_frame(symbol=symbol, payload=response.payload)
        if frame.empty:
            break
        rows.append(frame)
        max_seen = int(pd.to_numeric(frame["funding_time_ms"], errors="coerce").max())
        if max_seen < cursor:
            break
        cursor = max_seen + 1
        if len(frame) < safe_limit:
            break
    if not rows:
        return pd.DataFrame(columns=["symbol", "funding_time_ms", "funding_rate", "funding_mark_price"])
    return (
        pd.concat(rows, ignore_index=True, sort=False)
        .drop_duplicates(subset=["symbol", "funding_time_ms"], keep="last")
        .sort_values(["symbol", "funding_time_ms"])
        .reset_index(drop=True)
    )


def funding_rate_history_payload_to_frame(*, symbol: str, payload: Any) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    fallback_symbol = str(symbol).strip().upper()
    for item in list(payload or []):
        if not isinstance(item, dict):
            continue
        funding_time = _int_or_none(item.get("fundingTime"))
        if funding_time is None:
            continue
        rows.append(
            {
                "symbol": str(item.get("symbol") or fallback_symbol).strip().upper(),
                "funding_time_ms": int(funding_time),
                "funding_rate": _float(item.get("fundingRate"), default=float("nan")),
                "funding_mark_price": _float(item.get("markPrice"), default=float("nan")),
            }
        )
    return pd.DataFrame(rows)


def build_feature_panel_from_klines(
    *,
    daily_by_symbol: dict[str, pd.DataFrame],
    four_h_by_symbol: dict[str, pd.DataFrame],
    config: dict[str, Any],
    funding_by_symbol: dict[str, float] | None = None,
    funding_history_by_symbol: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    funding = dict(funding_by_symbol or {})
    funding_history = dict(funding_history_by_symbol or {})
    for symbol, daily in sorted(daily_by_symbol.items()):
        if daily.empty:
            continue
        subject = symbol_to_subject(symbol)
        daily_frame = daily.sort_values("open_time_ms").copy()
        daily_frame["timestamp_ms"] = pd.to_numeric(daily_frame["open_time_ms"], errors="coerce").astype("int64")
        daily_frame["date_utc"] = pd.to_datetime(daily_frame["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
        daily_frame["subject"] = subject
        daily_frame["usdm_symbol"] = symbol
        daily_frame["perp_open"] = pd.to_numeric(daily_frame["open"], errors="coerce")
        daily_frame["perp_high"] = pd.to_numeric(daily_frame["high"], errors="coerce")
        daily_frame["perp_low"] = pd.to_numeric(daily_frame["low"], errors="coerce")
        daily_frame["perp_close"] = pd.to_numeric(daily_frame["close"], errors="coerce")
        daily_frame["perp_volume"] = pd.to_numeric(daily_frame["volume"], errors="coerce")
        daily_frame["perp_quote_volume_usd"] = pd.to_numeric(daily_frame["quote_volume"], errors="coerce")
        daily_frame["has_perp"] = True
        daily_frame["perp_execution_eligible"] = True
        daily_frame["perp_executable_start_ms"] = int(daily_frame["timestamp_ms"].min())
        daily_frame["funding_rate"] = np.nan
        daily_frame["funding_sample_count"] = 0.0
        daily_funding = daily_funding_features(funding_history.get(symbol, pd.DataFrame()))
        if not daily_funding.empty:
            daily_frame = daily_frame.drop(columns=["funding_rate", "funding_sample_count"], errors="ignore").merge(
                daily_funding,
                on="date_utc",
                how="left",
            )
            daily_frame["funding_rate"] = pd.to_numeric(daily_frame["funding_rate"], errors="coerce")
            daily_frame["funding_sample_count"] = (
                pd.to_numeric(daily_frame["funding_sample_count"], errors="coerce").fillna(0.0)
            )
        elif math.isfinite(float(funding.get(symbol, float("nan")))):
            latest_idx = daily_frame.index[-1]
            daily_frame.loc[latest_idx, "funding_rate"] = float(funding[symbol])
            daily_frame.loc[latest_idx, "funding_sample_count"] = 1.0
        intraday = _intraday_realized_vol_by_day(four_h_by_symbol.get(symbol, pd.DataFrame()))
        daily_frame = daily_frame.merge(intraday, on="date_utc", how="left")
        frames.append(daily_frame)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True, sort=False)
    panel = add_binance_ohlcv_core_features(panel)
    panel = _apply_live_universe(panel, config=config)
    panel = panel.drop(columns=[column for column in FUTURE_LABEL_COLUMNS if column in panel.columns], errors="ignore")
    with pd.option_context("future.no_silent_downcasting", True):
        panel = panel.replace([np.inf, -np.inf], np.nan)
    return panel.sort_values(["timestamp_ms", "subject"]).reset_index(drop=True)


def daily_funding_features(funding_history: pd.DataFrame) -> pd.DataFrame:
    if funding_history.empty or "funding_time_ms" not in funding_history.columns:
        return pd.DataFrame(columns=["date_utc", "funding_rate", "funding_sample_count"])
    frame = funding_history.copy()
    frame["funding_time_ms"] = pd.to_numeric(frame["funding_time_ms"], errors="coerce")
    if "funding_rate" not in frame.columns:
        frame["funding_rate"] = np.nan
    frame["funding_rate"] = pd.to_numeric(frame["funding_rate"], errors="coerce")
    frame = frame.loc[frame["funding_time_ms"].notna()].copy()
    if frame.empty:
        return pd.DataFrame(columns=["date_utc", "funding_rate", "funding_sample_count"])
    frame["date_utc"] = pd.to_datetime(frame["funding_time_ms"].astype("int64"), unit="ms", utc=True).dt.date.astype(str)
    return (
        frame.groupby("date_utc", sort=True)
        .agg(
            funding_rate=("funding_rate", "mean"),
            funding_sample_count=("funding_time_ms", "count"),
        )
        .reset_index()
    )


def symbol_to_subject(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    if normalized.endswith("USDT"):
        return normalized[:-4]
    return normalized


def _apply_live_universe(panel: pd.DataFrame, *, config: dict[str, Any]) -> pd.DataFrame:
    output = panel.copy()
    policy = dict(config.get("universe_policy") or {})
    top_n = max(int(policy.get("top_n", 20) or 20), 1)
    output["universe_active"] = False
    output["universe_rank"] = np.nan
    output["liquidity_bucket"] = "not_in_universe"
    for _, group in output.groupby("timestamp_ms", sort=True):
        quote = pd.to_numeric(group["perp_quote_volume_usd"], errors="coerce")
        ordered = group.assign(_quote=quote).sort_values(["_quote", "subject"], ascending=[False, True]).head(top_n)
        ranks = pd.Series(np.arange(1, len(ordered) + 1, dtype="int64"), index=ordered.index)
        output.loc[ordered.index, "universe_active"] = True
        output.loc[ordered.index, "universe_rank"] = ranks
        output.loc[ordered.index, "liquidity_bucket"] = np.where(ranks.le(10), "top_liquidity", "mid_liquidity")
    return output


def _intraday_realized_vol_by_day(four_h: pd.DataFrame) -> pd.DataFrame:
    if four_h.empty:
        return pd.DataFrame(columns=["date_utc", "intraday_realized_vol_4h_to_1d"])
    frame = four_h.sort_values("open_time_ms").copy()
    frame["date_utc"] = pd.to_datetime(frame["open_time_ms"].astype("int64"), unit="ms", utc=True).dt.date.astype(str)
    close = pd.to_numeric(frame["close"], errors="coerce").replace(0.0, np.nan)
    frame["log_return_4h"] = np.log(close / close.shift(1))

    def _rv(group: pd.DataFrame) -> float:
        returns = pd.to_numeric(group["log_return_4h"], errors="coerce").dropna()
        if len(group) != 6 or len(returns) < 5:
            return float("nan")
        return float(math.sqrt(float(np.square(returns).sum())))

    return (
        frame.groupby("date_utc", sort=True)
        .apply(_rv, include_groups=False)
        .rename("intraday_realized_vol_4h_to_1d")
        .reset_index()
    )


def _closed_kline_frame(frame: pd.DataFrame, *, server_time_ms: int) -> pd.DataFrame:
    if frame.empty or "close_time_ms" not in frame.columns:
        return frame.iloc[0:0].copy()
    close_time = pd.to_numeric(frame["close_time_ms"], errors="coerce")
    return frame.loc[close_time.lt(int(server_time_ms))].copy()


def _frame_min_int(frame: pd.DataFrame, column: str) -> int | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return int(values.min())


def _frame_max_int(frame: pd.DataFrame, column: str) -> int | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return int(values.max())


def _server_time_ms(client: BinanceUsdmClient) -> int:
    try:
        payload = client.server_time().payload
        return int(payload["serverTime"])
    except Exception:
        return int(datetime.now(UTC).timestamp() * 1000)


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
