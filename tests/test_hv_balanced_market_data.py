from __future__ import annotations

from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.market_data import (
    build_feature_panel_from_klines,
    daily_funding_features,
    fetch_public_live_feature_panel,
    funding_rate_history_payload_to_frame,
    klines_payload_to_frame,
    parse_symbol_exchange_filters,
    resolve_config_symbols,
)


class HvBalancedMarketDataTests(unittest.TestCase):
    def test_parse_symbol_exchange_filters_accepts_tradable_usdm_perp(self) -> None:
        filters = parse_symbol_exchange_filters(_exchange_info(["BTCUSDT"]))

        self.assertIn("BTCUSDT", filters)
        self.assertTrue(filters["BTCUSDT"].tradable_usdm_perp)
        self.assertEqual(filters["BTCUSDT"].step_size, 0.001)
        self.assertEqual(filters["BTCUSDT"].min_notional, 5.0)

    def test_klines_payload_to_frame_parses_binance_rows(self) -> None:
        frame = klines_payload_to_frame(symbol="BTCUSDT", payload=[_kline_row(0, close=101.0)])

        self.assertEqual(list(frame["symbol"]), ["BTCUSDT"])
        self.assertEqual(float(frame.loc[0, "close"]), 101.0)
        self.assertEqual(float(frame.loc[0, "quote_volume"]), 10_100_000.0)

    def test_funding_rate_history_payload_to_frame_parses_binance_rows(self) -> None:
        frame = funding_rate_history_payload_to_frame(
            symbol="BTCUSDT",
            payload=[
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.00010000",
                    "fundingTime": 86_400_000,
                    "markPrice": "100.5",
                },
                {"symbol": "BTCUSDT", "fundingRate": "bad", "fundingTime": "not-int"},
            ],
        )

        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.loc[0, "symbol"], "BTCUSDT")
        self.assertEqual(int(frame.loc[0, "funding_time_ms"]), 86_400_000)
        self.assertAlmostEqual(float(frame.loc[0, "funding_rate"]), 0.0001)
        self.assertAlmostEqual(float(frame.loc[0, "funding_mark_price"]), 100.5)

    def test_daily_funding_features_aggregates_intraday_funding_samples(self) -> None:
        history = funding_rate_history_payload_to_frame(
            symbol="BTCUSDT",
            payload=[
                {"fundingRate": "0.0001", "fundingTime": 86_400_000, "markPrice": "100"},
                {"fundingRate": "0.0002", "fundingTime": 86_400_000 + 28_800_000, "markPrice": "100"},
                {"fundingRate": "-0.0001", "fundingTime": 2 * 86_400_000, "markPrice": "101"},
            ],
        )

        daily = daily_funding_features(history)

        self.assertEqual(list(daily["date_utc"]), ["1970-01-02", "1970-01-03"])
        self.assertEqual(list(daily["funding_sample_count"]), [2, 1])
        self.assertAlmostEqual(float(daily.loc[0, "funding_rate"]), 0.00015)

    def test_build_feature_panel_from_klines_drops_future_labels_and_sets_universe(self) -> None:
        symbols = [f"A{i:02d}USDT" for i in range(12)]
        panel = build_feature_panel_from_klines(
            daily_by_symbol={symbol: _daily_frame(symbol, index) for index, symbol in enumerate(symbols)},
            four_h_by_symbol={symbol: _four_hour_frame(symbol, index) for index, symbol in enumerate(symbols)},
            config={"universe_policy": {"top_n": 12}},
            funding_by_symbol={symbol: 0.0001 for symbol in symbols},
        )

        self.assertFalse(panel.empty)
        self.assertNotIn("target_forward_return", panel.columns)
        self.assertNotIn("target_execution_forward_return", panel.columns)
        latest = panel.loc[panel["timestamp_ms"].eq(panel["timestamp_ms"].max())].copy()
        self.assertEqual(int(latest["universe_active"].sum()), 12)
        self.assertEqual(int(latest["liquidity_bucket"].eq("top_liquidity").sum()), 10)
        self.assertEqual(int(latest["liquidity_bucket"].eq("mid_liquidity").sum()), 2)
        self.assertTrue(pd.to_numeric(latest["intraday_realized_vol_4h_to_1d_smooth_60"]).notna().all())
        self.assertTrue(pd.to_numeric(latest["funding_sample_count"]).eq(1.0).all())

    def test_build_feature_panel_from_klines_adds_historical_funding_samples(self) -> None:
        symbol = "BTCUSDT"
        funding_history = funding_rate_history_payload_to_frame(
            symbol=symbol,
            payload=[
                {"fundingRate": "0.0001", "fundingTime": 0, "markPrice": "100"},
                {"fundingRate": "0.0002", "fundingTime": 28_800_000, "markPrice": "100"},
                {"fundingRate": "0.0003", "fundingTime": 86_400_000, "markPrice": "101"},
            ],
        )
        panel = build_feature_panel_from_klines(
            daily_by_symbol={symbol: _daily_frame(symbol, 0, days=3)},
            four_h_by_symbol={symbol: _four_hour_frame(symbol, 0, days=3)},
            config={"universe_policy": {"top_n": 1}},
            funding_history_by_symbol={symbol: funding_history},
        )

        by_day = panel.set_index("date_utc")
        self.assertEqual(float(by_day.loc["1970-01-01", "funding_sample_count"]), 2.0)
        self.assertAlmostEqual(float(by_day.loc["1970-01-01", "funding_rate"]), 0.00015)
        self.assertEqual(float(by_day.loc["1970-01-02", "funding_sample_count"]), 1.0)

    def test_fetch_public_live_feature_panel_records_audit_and_skips_untradable_symbols(self) -> None:
        client = _FakePublicClient(["BTCUSDT", "ETHUSDT"], server_time_ms=65 * 86_400_000 + 1)

        panel, audit, filters = fetch_public_live_feature_panel(
            client=client,
            config={"universe_policy": {"top_n": 2}},
            symbols=resolve_config_symbols({}, override_symbols="BTCUSDT,ETHUSDT,BADUSDT"),
            daily_limit=65,
            four_hour_limit=390,
        )

        self.assertFalse(panel.empty)
        self.assertEqual(audit["source"], "binance_usdm_public_rest")
        self.assertEqual(audit["tradable_symbols"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(audit["skipped_symbols"], ["BADUSDT"])
        self.assertEqual(audit["closed_daily_rows"], audit["raw_daily_rows"])
        self.assertGreater(audit["funding_history_rows"], 0)
        self.assertEqual(audit["funding_history_error_symbols"], [])
        self.assertEqual(sorted(filters), ["BTCUSDT", "ETHUSDT"])

    def test_fetch_public_live_feature_panel_drops_unclosed_current_bar(self) -> None:
        client = _FakePublicClient(["BTCUSDT"], server_time_ms=64 * 86_400_000)

        panel, audit, _ = fetch_public_live_feature_panel(
            client=client,
            config={"universe_policy": {"top_n": 1}},
            symbols=["BTCUSDT"],
            daily_limit=65,
            four_hour_limit=390,
        )

        self.assertEqual(audit["raw_daily_rows"], 65)
        self.assertEqual(audit["closed_daily_rows"], 64)
        self.assertEqual(int(panel["timestamp_ms"].max()), 63 * 86_400_000)


class _FakePublicClient:
    def __init__(self, symbols: list[str], *, server_time_ms: int) -> None:
        self.symbols = symbols
        self.server_time_ms = server_time_ms

    def server_time(self) -> SimpleNamespace:
        return SimpleNamespace(payload={"serverTime": self.server_time_ms})

    def exchange_info(self) -> SimpleNamespace:
        return SimpleNamespace(payload=_exchange_info(self.symbols))

    def klines(self, *, symbol: str, interval: str, limit: int) -> SimpleNamespace:
        index = self.symbols.index(symbol)
        if interval == "1d":
            frame = _daily_frame(symbol, index).tail(limit)
        elif interval == "4h":
            frame = _four_hour_frame(symbol, index).tail(limit)
        else:
            raise AssertionError(f"unexpected interval: {interval}")
        payload = [
            [
                int(row.open_time_ms),
                str(float(row.open)),
                str(float(row.high)),
                str(float(row.low)),
                str(float(row.close)),
                str(float(row.volume)),
                int(row.close_time_ms),
                str(float(row.quote_volume)),
                int(row.trade_count),
                str(float(row.taker_buy_base_volume)),
                str(float(row.taker_buy_quote_volume)),
                "0",
            ]
            for row in frame.itertuples(index=False)
        ]
        return SimpleNamespace(payload=payload)

    def premium_index(self, *, symbol: str) -> SimpleNamespace:
        return SimpleNamespace(payload={"symbol": symbol, "lastFundingRate": "0.0001"})

    def funding_rate_history(
        self,
        *,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> SimpleNamespace:
        start = 0 if start_time is None else int(start_time)
        end = (65 * 86_400_000) if end_time is None else int(end_time)
        rows = []
        for funding_time in range(start - (start % 28_800_000), end + 1, 28_800_000):
            if funding_time < start:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "fundingRate": "0.0001",
                    "fundingTime": funding_time,
                    "markPrice": "100.0",
                }
            )
            if len(rows) >= int(limit):
                break
        return SimpleNamespace(payload=rows)


def _exchange_info(symbols: list[str]) -> dict:
    return {
        "symbols": [
            {
                "symbol": symbol,
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5.0"},
                ],
            }
            for symbol in symbols
        ]
    }


def _daily_frame(symbol: str, symbol_index: int, days: int = 65) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _bar(
                symbol=symbol,
                open_time_ms=day * 86_400_000,
                close_time_ms=(day + 1) * 86_400_000 - 1,
                close=100.0 + symbol_index * 2.0 + day * 0.25,
                quote_volume=1_000_000.0 + symbol_index * 100_000.0 + day * 1_000.0,
            )
            for day in range(days)
        ]
    )


def _four_hour_frame(symbol: str, symbol_index: int, days: int = 65) -> pd.DataFrame:
    rows = []
    for day in range(days):
        for slot in range(6):
            open_time_ms = day * 86_400_000 + slot * 14_400_000
            close = 100.0 + symbol_index * 2.0 + day * 0.25 + slot * 0.03
            rows.append(
                _bar(
                    symbol=symbol,
                    open_time_ms=open_time_ms,
                    close_time_ms=open_time_ms + 14_400_000 - 1,
                    close=close,
                    quote_volume=160_000.0 + symbol_index * 10_000.0 + day * 100.0,
                )
            )
    return pd.DataFrame(rows)


def _kline_row(open_time_ms: int, *, close: float) -> list:
    return [
        open_time_ms,
        str(close * 0.99),
        str(close * 1.01),
        str(close * 0.98),
        str(close),
        "100",
        open_time_ms + 86_400_000 - 1,
        str(close * 100_000.0),
        1000,
        "50",
        str(close * 50_000.0),
        "0",
    ]


def _bar(*, symbol: str, open_time_ms: int, close_time_ms: int, close: float, quote_volume: float) -> dict:
    return {
        "symbol": symbol,
        "open_time_ms": int(open_time_ms),
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": quote_volume / close,
        "close_time_ms": int(close_time_ms),
        "quote_volume": quote_volume,
        "trade_count": 1000,
        "taker_buy_base_volume": quote_volume / close / 2.0,
        "taker_buy_quote_volume": quote_volume / 2.0,
    }
