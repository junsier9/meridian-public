from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlencode

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from enhengclaw.live_trading.binance_usdm_client import (  # noqa: E402
    BINANCE_SPOT_MAINNET_BASE_URL,
    BINANCE_USDM_MAINNET_BASE_URL,
    BinanceUsdmClient,
)
from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path  # noqa: E402
from enhengclaw.live_trading.market_data import (  # noqa: E402
    FUTURE_LABEL_COLUMNS,
    fetch_live_spot_close_frame,
    fetch_public_live_feature_panel,
    klines_payload_to_frame,
    resolve_config_symbols,
)
from enhengclaw.quant_research.coinglass_derivatives import (  # noqa: E402
    DEFAULT_EXCHANGE_NAME as COINGLASS_DEFAULT_EXCHANGE_NAME,
    FUNDING_RATE_HISTORY_URL,
    OPEN_INTEREST_HISTORY_URL,
    PRICE_HISTORY_URL,
    TAKER_BUY_SELL_VOLUME_HISTORY_URL,
    _aggregate_derivatives_rows,
    _fetch_ohlc_history,
    _fetch_taker_buy_sell_volume_history,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9r_research_to_live_parity import (  # noqa: E402
    ACTIVE_H10D_REGISTRY_PATH,
    load_research_scorer_contract,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase2_join import (  # noqa: E402
    VALUE_ALIASES as TOP_TRADER_VALUE_ALIASES,
    float_from_row as top_trader_float_from_row,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_step1_health import (  # noqa: E402
    BASE_URL as COINGLASS_BASE_URL,
    TOP_TRADER_PATH,
    http_get_json,
    iso_z,
    payload_rows,
    provider_ok,
    resolve_api_key,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10a_pit_safe_live_feature_builder.v1"
DEFAULT_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_12factor_candidate/p10a_pit_safe_live_feature_builder"
DEFAULT_FRESHNESS_SECONDS = 36 * 3600
DEFAULT_AVAILABILITY_LAG_SECONDS = 60
DAY_MS = 86_400_000
HOUR_MS = 3_600_000

BINANCE_PUBLIC_FACTOR_IDS = frozenset(
    {
        "intraday_realized_vol_4h_to_1d_smooth_60",
        "realized_volatility_5",
        "distance_to_high_60",
        "distance_to_high_5",
        "liquidity_stress_qv_iv",
        "momentum_decay_5_20",
        "downside_upside_vol_ratio_30",
    }
)
SETTLEMENT_FACTOR_ID = "settlement_cycle_premium_60d"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10A proof-only PIT-safe live feature builder for the 12-factor research contract. "
            "Writes retained evidence only; never touches timer, supervisor, executor, config, or orders."
        )
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--symbols", default="")
    parser.add_argument(
        "--mode",
        choices=["live-binance-public", "input-panel", "deterministic-fixture"],
        default="live-binance-public",
    )
    parser.add_argument("--input-panel", type=Path, default=None)
    parser.add_argument("--output-root", default="")
    parser.add_argument("--decision-time", default="now")
    parser.add_argument("--freshness-seconds", type=int, default=DEFAULT_FRESHNESS_SECONDS)
    parser.add_argument("--availability-lag-seconds", type=int, default=DEFAULT_AVAILABILITY_LAG_SECONDS)
    parser.add_argument("--min-symbol-coverage", type=float, default=1.0)
    parser.add_argument("--daily-limit", type=int, default=140)
    parser.add_argument("--four-hour-limit", type=int, default=840)
    parser.add_argument("--base-url", default=BINANCE_USDM_MAINNET_BASE_URL)
    parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--disable-sidecar-builders", action="store_true")
    parser.add_argument("--sidecar-lookback-days", type=int, default=90)
    parser.add_argument("--sidecar-hour-lookback-days", type=int, default=4)
    parser.add_argument("--settlement-hour-limit", type=int, default=1500)
    parser.add_argument(
        "--settlement-lookback-days",
        type=int,
        default=0,
        help=(
            "When >0, fetch Binance 1h klines in pages over this many days for "
            "settlement_cycle_premium_60d warmup. The default 0 preserves the "
            "single latest-page behavior."
        ),
    )
    parser.add_argument("--settlement-page-limit", type=int, default=1500)
    parser.add_argument("--settlement-request-sleep-seconds", type=float, default=0.0)
    parser.add_argument("--settlement-request-max-attempts", type=int, default=3)
    parser.add_argument("--settlement-request-retry-sleep-seconds", type=float, default=0.25)
    parser.add_argument("--coinglass-request-sleep-seconds", type=float, default=0.03)
    parser.add_argument("--active-h10d-registry", type=Path, default=ACTIVE_H10D_REGISTRY_PATH)
    parser.add_argument("--research-parent-manifest", type=Path, default=None)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_decision_time(value: str, *, now_fn: Callable[[], datetime]) -> datetime | None:
    raw = str(value or "now").strip()
    if raw.lower() == "now":
        return None
    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def run_p10a_live_feature_builder(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
    input_panel: pd.DataFrame | None = None,
    live_panel_fetcher: Callable[..., tuple[pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]] | None = None,
    live_sidecar_builder: Callable[..., tuple[pd.DataFrame, dict[str, Any]]] | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    requested_decision_time = parse_decision_time(str(getattr(args, "decision_time", "now") or "now"), now_fn=now)
    provisional_decision_time = requested_decision_time or started_at

    live_config = load_live_trading_config(str(getattr(args, "config", DEFAULT_CONFIG)))
    symbols = resolve_config_symbols(live_config.payload, override_symbols=str(getattr(args, "symbols", "") or ""))
    required_contract = load_research_scorer_contract(
        active_h10d_registry_path=Path(getattr(args, "active_h10d_registry", ACTIVE_H10D_REGISTRY_PATH)),
        research_parent_manifest_path=getattr(args, "research_parent_manifest", None),
    )
    required_factors = [str(column) for column in list(required_contract.get("required_feature_columns") or [])]
    mode = str(getattr(args, "mode", "live-binance-public"))
    run_id = f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}_{_safe_path_token(mode)}"
    output_root = (
        resolve_repo_path(str(getattr(args, "output_root", "") or ""))
        if str(getattr(args, "output_root", "") or "").strip()
        else resolve_repo_path(DEFAULT_OUTPUT_PARENT) / run_id
    )
    output_root.mkdir(parents=True, exist_ok=True)

    panel, panel_audit, exchange_filters = _load_panel(
        args=args,
        config=live_config.payload,
        symbols=symbols,
        required_factors=required_factors,
        decision_time=provisional_decision_time,
        now_fn=now,
        input_panel=input_panel,
        live_panel_fetcher=live_panel_fetcher,
        live_sidecar_builder=live_sidecar_builder,
    )
    decision_time = requested_decision_time or now()
    decision_ms = int(decision_time.timestamp() * 1000)
    panel = _normalize_panel_symbols(panel)
    future_label_columns_present = [column for column in FUTURE_LABEL_COLUMNS if column in panel.columns]

    joined_rows, candidate_rows, factor_rows = _build_pit_snapshot(
        panel=panel,
        symbols=symbols,
        required_factors=required_factors,
        decision_time=decision_time,
        freshness_seconds=int(getattr(args, "freshness_seconds", DEFAULT_FRESHNESS_SECONDS)),
        availability_lag_seconds=int(getattr(args, "availability_lag_seconds", DEFAULT_AVAILABILITY_LAG_SECONDS)),
        min_symbol_coverage=float(getattr(args, "min_symbol_coverage", 1.0)),
    )

    no_future_fill = all(not _bool(row.get("future_fill_violation")) for row in joined_rows)
    no_stale_fill = all(not _bool(row.get("stale_fill_violation")) for row in joined_rows)
    no_zero_fill = all(not _bool(row.get("zero_fill_violation")) for row in joined_rows)
    complete_joined_rows = [row for row in joined_rows if row.get("join_status") == "joined"]
    blockers: list[str] = []
    if len(required_factors) != 12:
        blockers.append("research_contract_required_feature_count_not_12")
    if future_label_columns_present:
        blockers.append("future_label_columns_present")
    if panel.empty:
        blockers.append("live_feature_panel_empty")
    for row in factor_rows:
        if row.get("missing_column"):
            blockers.append(f"factor:{row['factor_id']}:missing_column")
        if _bool(row.get("coverage_below_min")):
            blockers.append(f"factor:{row['factor_id']}:coverage_below_min")
    if not no_future_fill:
        blockers.append("future_fill_violation")
    if not no_stale_fill:
        blockers.append("stale_fill_violation")
    if not no_zero_fill:
        blockers.append("zero_fill_violation")
    blockers.extend(str(item) for item in panel_audit.get("blockers", []) if str(item).strip())
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    joined_snapshot_path = output_root / "pit_live_feature_joined_snapshot.csv"
    candidate_audit_path = output_root / "pit_live_feature_candidate_rows.csv"
    factor_readiness_path = output_root / "pit_live_feature_factor_readiness.csv"
    panel_snapshot_path = output_root / "source_live_feature_panel_snapshot.csv"
    research_contract_path = output_root / "research_scorer_contract.json"
    summary_path = output_root / "summary.json"

    write_csv(joined_snapshot_path, joined_rows)
    write_csv(candidate_audit_path, candidate_rows)
    write_csv(factor_readiness_path, factor_rows)
    write_csv(panel_snapshot_path, _bounded_panel_snapshot(panel))
    write_json(research_contract_path, required_contract)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "generated_at_utc": iso_z(now()),
        "started_at_utc": iso_z(started_at),
        "decision_time_utc": iso_z(decision_time),
        "decision_time_ms": decision_ms,
        "decision_time_source": "operator_supplied" if requested_decision_time is not None else "post_feature_fetch_now",
        "mode": mode,
        "config_path": str(live_config.path),
        "output_root": str(output_root),
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "supervisor_invoked": False,
        "executor_invoked": False,
        "candidate_executed": False,
        "target_plan_replaced": False,
        "exchange_order_submission": "disabled",
        "orders_submitted": 0,
        "fills_observed": 0,
        "required_feature_count": len(required_factors),
        "required_feature_columns": required_factors,
        "requested_symbol_count": len(symbols),
        "requested_symbols": symbols,
        "panel_row_count": int(len(panel)),
        "panel_columns": [str(column) for column in panel.columns],
        "future_label_columns_present": future_label_columns_present,
        "freshness_seconds": int(getattr(args, "freshness_seconds", DEFAULT_FRESHNESS_SECONDS)),
        "availability_lag_seconds": int(getattr(args, "availability_lag_seconds", DEFAULT_AVAILABILITY_LAG_SECONDS)),
        "min_symbol_coverage": float(getattr(args, "min_symbol_coverage", 1.0)),
        "joined_feature_cell_count": len(complete_joined_rows),
        "required_feature_cell_count": int(len(symbols) * len(required_factors)),
        "future_blocked_count": sum(int(row.get("future_blocked_count") or 0) for row in factor_rows),
        "stale_blocked_count": sum(int(row.get("stale_blocked_count") or 0) for row in factor_rows),
        "missing_value_blocked_count": sum(int(row.get("missing_value_blocked_count") or 0) for row in factor_rows),
        "missing_timestamp_metadata_count": sum(
            int(row.get("missing_timestamp_metadata_count") or 0) for row in factor_rows
        ),
        "no_future_fill_proven": no_future_fill,
        "no_stale_fill_proven": no_stale_fill,
        "no_zero_fill_proven": no_zero_fill,
        "factor_readiness_status": "ready"
        if factor_rows and all(row.get("status") == "ready" for row in factor_rows)
        else "blocked",
        "panel_audit": panel_audit,
        "exchange_filters": exchange_filters,
        "blockers": blockers,
        "artifacts": {
            "summary": str(summary_path),
            "pit_live_feature_joined_snapshot": str(joined_snapshot_path),
            "pit_live_feature_candidate_rows": str(candidate_audit_path),
            "pit_live_feature_factor_readiness": str(factor_readiness_path),
            "source_live_feature_panel_snapshot": str(panel_snapshot_path),
            "research_scorer_contract": str(research_contract_path),
        },
    }
    write_json(summary_path, summary)
    return summary, 0 if status == "ready" else 2


def _load_panel(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    symbols: list[str],
    required_factors: list[str],
    decision_time: datetime,
    now_fn: Callable[[], datetime],
    input_panel: pd.DataFrame | None,
    live_panel_fetcher: Callable[..., tuple[pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]] | None,
    live_sidecar_builder: Callable[..., tuple[pd.DataFrame, dict[str, Any]]] | None,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, dict[str, Any]]]:
    mode = str(getattr(args, "mode", "live-binance-public"))
    if input_panel is not None:
        return input_panel.copy(), {"source": "injected_input_panel", "blockers": []}, {}
    if mode == "input-panel":
        path = Path(getattr(args, "input_panel", None) or "")
        if not path:
            return pd.DataFrame(), {"source": "input_panel", "blockers": ["input_panel_path_missing"]}, {}
        resolved = path if path.is_absolute() else ROOT / path
        return pd.read_csv(resolved), {"source": "input_panel", "input_panel_path": str(resolved), "blockers": []}, {}
    if mode == "deterministic-fixture":
        panel = build_deterministic_fixture_panel(
            required_factors=required_factors,
            symbols=symbols,
            decision_time=decision_time,
            availability_lag_seconds=int(getattr(args, "availability_lag_seconds", DEFAULT_AVAILABILITY_LAG_SECONDS)),
        )
        return panel, {"source": "deterministic_fixture", "blockers": []}, {}

    fetcher = live_panel_fetcher or fetch_public_live_feature_panel
    client = BinanceUsdmClient(
        base_url=str(getattr(args, "base_url", BINANCE_USDM_MAINNET_BASE_URL)),
        timeout_seconds=float(getattr(args, "request_timeout_seconds", 20.0)),
    )
    try:
        panel, audit, filters = fetcher(
            client=client,
            config=config,
            symbols=symbols,
            daily_limit=int(getattr(args, "daily_limit", 140)),
            four_hour_limit=int(getattr(args, "four_hour_limit", 840)),
        )
        panel_audit = dict(audit)
        panel_audit.setdefault("blockers", [])
        if not bool(getattr(args, "disable_sidecar_builders", False)):
            builder = live_sidecar_builder or append_live_12factor_sidecars
            panel, sidecar_audit = builder(
                panel=panel,
                symbols=symbols,
                decision_time=decision_time,
                args=args,
                now_fn=now_fn,
            )
            panel_audit["sidecar_builders"] = sidecar_audit
            panel_audit["blockers"].extend(list(sidecar_audit.get("blockers") or []))
        else:
            panel_audit["sidecar_builders"] = {"enabled": False, "blockers": []}
        return panel, panel_audit, filters
    except Exception as exc:
        return (
            pd.DataFrame(),
            {
                "source": "binance_usdm_public_rest",
                "blockers": ["live_binance_public_panel_fetch_failed"],
                "exception_type": exc.__class__.__name__,
                "exception_message": str(exc),
            },
            {},
        )


def build_deterministic_fixture_panel(
    *,
    required_factors: list[str],
    symbols: list[str],
    decision_time: datetime,
    availability_lag_seconds: int = DEFAULT_AVAILABILITY_LAG_SECONDS,
) -> pd.DataFrame:
    provider_time = decision_time - timedelta(hours=2)
    available_time = provider_time + timedelta(seconds=int(availability_lag_seconds))
    provider_ms = int(provider_time.timestamp() * 1000)
    available_ms = int(available_time.timestamp() * 1000)
    rows: list[dict[str, Any]] = []
    for symbol_index, symbol in enumerate(symbols):
        subject = _symbol_to_subject(symbol)
        row: dict[str, Any] = {
            "timestamp_ms": int((provider_time - timedelta(days=1)).timestamp() * 1000),
            "close_time_ms": provider_ms,
            "symbol": str(symbol).upper(),
            "usdm_symbol": str(symbol).upper(),
            "subject": subject,
            "provider_timestamp_ms": provider_ms,
            "available_at_ms": available_ms,
            "source": "deterministic_fixture",
        }
        for factor_index, factor in enumerate(required_factors):
            row[factor] = float((factor_index + 1) * 0.01 + symbol_index * 0.001)
            row[f"{factor}_provider_timestamp_ms"] = provider_ms
            row[f"{factor}_available_at_ms"] = available_ms
            row[f"{factor}_source"] = "deterministic_fixture"
        rows.append(row)
    return pd.DataFrame(rows)


def append_live_12factor_sidecars(
    *,
    panel: pd.DataFrame,
    symbols: list[str],
    decision_time: datetime,
    args: argparse.Namespace,
    now_fn: Callable[[], datetime],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    output = _normalize_panel_symbols(panel)
    audit: dict[str, Any] = {
        "enabled": True,
        "status": "ready",
        "provider": "coinglass_plus_binance_public",
        "requested_symbol_count": len(symbols),
        "blockers": [],
        "request_count": 0,
        "symbol_status": [],
    }
    if output.empty:
        audit["status"] = "blocked"
        audit["blockers"].append("sidecar_source_panel_empty")
        return output, audit

    key = resolve_api_key()
    audit["coinglass_api_key_present"] = key.present
    audit["coinglass_api_key_source"] = key.source
    if not key.present:
        audit["status"] = "blocked"
        audit["blockers"].append("coinglass_api_key_missing_for_12factor_sidecars")
        return output, audit

    client = BinanceUsdmClient(
        base_url=str(getattr(args, "base_url", BINANCE_USDM_MAINNET_BASE_URL)),
        timeout_seconds=float(getattr(args, "request_timeout_seconds", 20.0)),
    )
    # Research-parity funding_basis (perp_spot) needs Binance spot closes to compute
    # basis=(perp_close-spot_close)/spot_close (== research lab.py:1876), replacing the live
    # premiumIndex basis. Fetched ONCE for all symbols; the per-symbol sidecar fails closed if its
    # spot leg is missing. funding_basis_source=premium_index (legacy) skips this fetch entirely.
    funding_basis_source = str(getattr(args, "funding_basis_source", "premium_index") or "premium_index").strip().lower()
    spot_close_frame: pd.DataFrame | None = None
    if funding_basis_source == "perp_spot":
        try:
            spot_close_frame = fetch_live_spot_close_frame(
                client=BinanceUsdmClient(
                    base_url=BINANCE_SPOT_MAINNET_BASE_URL,
                    timeout_seconds=float(getattr(args, "request_timeout_seconds", 20.0)),
                ),
                symbols=list(symbols),
                daily_limit=int(getattr(args, "sidecar_lookback_days", 70) or 70) + 10,
            )
        except Exception as exc:
            spot_close_frame = pd.DataFrame(columns=["subject", "date_utc", "spot_close"])
            audit["blockers"].append(f"perp_spot_basis_spot_fetch_failed:{exc.__class__.__name__}:{exc}")
    sidecar_frames: list[pd.DataFrame] = []
    request_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        symbol_started = now_fn()
        try:
            frame, symbol_audit = build_symbol_live_sidecar_frame(
                panel=output,
                symbol=symbol,
                decision_time=decision_time,
                args=args,
                now_fn=now_fn,
                api_key=key.value,
                binance_client=client,
                spot_close_frame=spot_close_frame,
            )
            sidecar_frames.append(frame)
            audit["symbol_status"].append(symbol_audit)
            request_rows.extend(list(symbol_audit.get("requests") or []))
        except Exception as exc:
            audit["symbol_status"].append(
                {
                    "symbol": symbol,
                    "status": "blocked",
                    "started_at_utc": iso_z(symbol_started),
                    "exception_type": exc.__class__.__name__,
                    "exception_message": str(exc),
                    "requests": [],
                }
            )
            audit["blockers"].append(f"{symbol}:sidecar_builder_exception:{exc.__class__.__name__}")
        sleep_seconds = float(getattr(args, "coinglass_request_sleep_seconds", 0.03) or 0.0)
        if sleep_seconds > 0.0:
            time.sleep(sleep_seconds)

    audit["request_count"] = len(request_rows)
    audit["requests"] = request_rows[:200]
    blocked_symbols = [row["symbol"] for row in audit["symbol_status"] if row.get("status") != "ready"]
    audit["blocked_symbols"] = blocked_symbols
    if blocked_symbols:
        audit["status"] = "blocked"
        audit["blockers"].append("sidecar_symbol_build_failed")
    if sidecar_frames:
        sidecars = pd.concat([frame for frame in sidecar_frames if not frame.empty], ignore_index=True, sort=False)
        if not sidecars.empty:
            output = output.merge(sidecars, on=["subject", "date_utc"], how="left", suffixes=("", "_sidecar"))
            output = output.drop(columns=[column for column in output.columns if column.endswith("_sidecar")], errors="ignore")
    if audit["blockers"]:
        audit["status"] = "blocked"
    return output, audit


def build_symbol_live_sidecar_frame(
    *,
    panel: pd.DataFrame,
    symbol: str,
    decision_time: datetime,
    args: argparse.Namespace,
    now_fn: Callable[[], datetime],
    api_key: str,
    binance_client: BinanceUsdmClient,
    spot_close_frame: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    subject = _symbol_to_subject(symbol)
    symbol_audit: dict[str, Any] = {
        "symbol": symbol,
        "subject": subject,
        "status": "ready",
        "requests": [],
        "blockers": [],
    }
    frames: list[pd.DataFrame] = []

    top_frame, top_audit = _build_top_trader_sidecar(
        symbol=symbol,
        decision_time=decision_time,
        args=args,
        now_fn=now_fn,
        api_key=api_key,
    )
    frames.append(top_frame)
    symbol_audit["requests"].extend(top_audit["requests"])
    symbol_audit["blockers"].extend(top_audit["blockers"])

    derivatives_frame, derivatives_audit = _build_daily_derivatives_sidecar(
        panel=panel,
        symbol=symbol,
        decision_time=decision_time,
        args=args,
        api_key=api_key,
        binance_client=binance_client,
        spot_close_frame=spot_close_frame,
    )
    frames.append(derivatives_frame)
    symbol_audit["requests"].extend(derivatives_audit["requests"])
    symbol_audit["blockers"].extend(derivatives_audit["blockers"])

    taker_frame, taker_audit = _build_taker_dispersion_sidecar(
        symbol=symbol,
        decision_time=decision_time,
        args=args,
        now_fn=now_fn,
        api_key=api_key,
    )
    frames.append(taker_frame)
    symbol_audit["requests"].extend(taker_audit["requests"])
    symbol_audit["blockers"].extend(taker_audit["blockers"])

    settlement_frame, settlement_audit = _build_settlement_sidecar(
        symbol=symbol,
        decision_time=decision_time,
        args=args,
        binance_client=binance_client,
    )
    frames.append(settlement_frame)
    symbol_audit["requests"].extend(settlement_audit["requests"])
    symbol_audit["blockers"].extend(settlement_audit["blockers"])

    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        symbol_audit["status"] = "blocked"
        symbol_audit["blockers"].append("all_sidecar_frames_empty")
        return pd.DataFrame(), symbol_audit
    merged = non_empty[0]
    for frame in non_empty[1:]:
        merged = merged.merge(frame, on=["subject", "date_utc"], how="outer", suffixes=("", "_dup"))
        merged = merged.drop(columns=[column for column in merged.columns if column.endswith("_dup")], errors="ignore")
    if symbol_audit["blockers"]:
        symbol_audit["status"] = "blocked"
    return merged.sort_values(["subject", "date_utc"]).reset_index(drop=True), symbol_audit


def _build_top_trader_sidecar(
    *,
    symbol: str,
    decision_time: datetime,
    args: argparse.Namespace,
    now_fn: Callable[[], datetime],
    api_key: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    subject = _symbol_to_subject(symbol)
    limit = max(10, min(int(getattr(args, "sidecar_lookback_days", 90) or 90) + 5, 1000))
    params = {
        "exchange": COINGLASS_DEFAULT_EXCHANGE_NAME,
        "symbol": symbol,
        "interval": "1d",
        "limit": limit,
    }
    requested_at = now_fn()
    url = f"{COINGLASS_BASE_URL}{TOP_TRADER_PATH}?{urlencode(params)}"
    audit = {"requests": [_request_audit_row(symbol, "coinglass_top_trader", requested_at, url)], "blockers": []}
    try:
        payload = http_get_json(url, api_key=api_key, timeout_seconds=float(getattr(args, "request_timeout_seconds", 20.0)))
        received_at = now_fn()
        rows = payload_rows(payload)
        audit["requests"][0].update(
            {
                "received_at_utc": iso_z(received_at),
                "status": "success" if provider_ok(payload, rows) else "provider_error",
                "row_count": len(rows),
            }
        )
    except Exception as exc:
        audit["requests"][0].update({"status": "error", "error": f"{exc.__class__.__name__}:{exc}"})
        audit["blockers"].append(f"{symbol}:coinglass_top_trader_request_failed")
        return pd.DataFrame(), audit
    values: list[float] = []
    output_rows: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: int(_int_ms(item.get("time") or item.get("timestamp") or 0) or 0)):
        open_ms = _int_ms(row.get("time") or row.get("timestamp") or row.get("timestamp_ms") or row.get("t"))
        raw_value = top_trader_float_from_row(dict(row), *TOP_TRADER_VALUE_ALIASES)
        if open_ms is None:
            continue
        if raw_value is not None:
            values.append(raw_value)
        window = values[-5:]
        if len(window) < 5:
            continue
        provider_ms = _daily_close_ms(open_ms)
        output_rows.append(
            {
                "subject": subject,
                "date_utc": _date_utc_from_ms(open_ms),
                "coinglass_top_trader_long_pct_smooth_5": float(sum(window) / len(window)),
                "coinglass_top_trader_long_pct_smooth_5_provider_timestamp_ms": provider_ms,
                "coinglass_top_trader_long_pct_smooth_5_available_at_ms": int(received_at.timestamp() * 1000),
                "coinglass_top_trader_long_pct_smooth_5_source": "coinglass_top_trader_sidecar_p10b",
            }
        )
    if not output_rows:
        audit["blockers"].append(f"{symbol}:coinglass_top_trader_no_smooth5_rows")
    return pd.DataFrame(output_rows), audit


def _build_daily_derivatives_sidecar(
    *,
    panel: pd.DataFrame,
    symbol: str,
    decision_time: datetime,
    args: argparse.Namespace,
    api_key: str,
    binance_client: BinanceUsdmClient,
    spot_close_frame: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    subject = _symbol_to_subject(symbol)
    lookback_days = max(40, int(getattr(args, "sidecar_lookback_days", 90) or 90))
    end_ms = int(decision_time.timestamp() * 1000)
    start_ms = end_ms - lookback_days * DAY_MS
    timeout = float(getattr(args, "request_timeout_seconds", 20.0))

    def _cg_get(url: str) -> Any:
        return http_get_json(url, api_key=api_key, timeout_seconds=timeout)

    audit = {"requests": [], "blockers": []}
    request_started = datetime.now(UTC)
    try:
        funding_bars = _fetch_ohlc_history(
            url=FUNDING_RATE_HISTORY_URL,
            exchange=COINGLASS_DEFAULT_EXCHANGE_NAME,
            symbol=symbol,
            interval="1d",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            http_get_json_fn=_cg_get,
        )
        open_interest_coin_bars = _fetch_ohlc_history(
            url=OPEN_INTEREST_HISTORY_URL,
            exchange=COINGLASS_DEFAULT_EXCHANGE_NAME,
            symbol=symbol,
            interval="1d",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            extra_params={"unit": "coin"},
            http_get_json_fn=_cg_get,
        )
        open_interest_usd_bars = _fetch_ohlc_history(
            url=OPEN_INTEREST_HISTORY_URL,
            exchange=COINGLASS_DEFAULT_EXCHANGE_NAME,
            symbol=symbol,
            interval="1d",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            extra_params={"unit": "usd"},
            http_get_json_fn=_cg_get,
        )
        price_bars = _fetch_ohlc_history(
            url=PRICE_HISTORY_URL,
            exchange=COINGLASS_DEFAULT_EXCHANGE_NAME,
            symbol=symbol,
            interval="1d",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            http_get_json_fn=_cg_get,
        )
        request_received = datetime.now(UTC)
        audit["requests"].append(
            {
                "symbol": symbol,
                "endpoint_id": "coinglass_daily_derivatives_bundle",
                "requested_at_utc": iso_z(request_started),
                "received_at_utc": iso_z(request_received),
                "status": "success",
                "row_count": len(funding_bars)
                + len(open_interest_coin_bars)
                + len(open_interest_usd_bars)
                + len(price_bars),
            }
        )
    except Exception as exc:
        audit["requests"].append(
            {
                "symbol": symbol,
                "endpoint_id": "coinglass_daily_derivatives_bundle",
                "requested_at_utc": iso_z(request_started),
                "status": "error",
                "error": f"{exc.__class__.__name__}:{exc}",
            }
        )
        audit["blockers"].append(f"{symbol}:coinglass_daily_derivatives_request_failed")
        return pd.DataFrame(), audit

    rows = _aggregate_derivatives_rows(
        symbol=symbol,
        interval="1d",
        funding_bars=funding_bars,
        open_interest_coin_bars=open_interest_coin_bars,
        open_interest_usd_bars=open_interest_usd_bars,
        price_bars=price_bars,
        volume_bars=[],
    )
    if not rows:
        audit["blockers"].append(f"{symbol}:coinglass_daily_derivatives_empty")
        return pd.DataFrame(), audit
    frame = pd.DataFrame(rows).sort_values("open_time_ms").reset_index(drop=True)
    for column in ("open_time_ms", "close_time_ms"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("int64")
    for column in ("funding_rate", "open_interest", "open_interest_value", "perp_close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["date_utc"] = frame["open_time_ms"].map(_date_utc_from_ms)
    frame["subject"] = subject
    frame["oi_change_5"] = frame["open_interest"].replace(0.0, np.nan).pct_change(5, fill_method=None)
    frame["quality_funding_oi"] = frame["funding_rate"] * frame["oi_change_5"]

    # Basis source for funding_basis_residual_implied_repo_30:
    #   * "perp_spot" (research parity): basis=(perp_close-spot_close)/spot_close == research lab.py:1876.
    #     Removes the dominant live-vs-research gap (~0.0028) of the premiumIndex basis. Fail-closed if
    #     spot is unavailable (NaN basis => factor NaN => snapshot blocks; no silent premiumIndex fallback).
    #   * "premium_index" (legacy default): Binance premiumIndexKlines, the prior live behaviour.
    funding_basis_source = str(getattr(args, "funding_basis_source", "premium_index") or "premium_index").strip().lower()
    if funding_basis_source == "perp_spot":
        basis, basis_blockers = _perp_spot_basis_proxy(
            panel=panel, symbol=symbol, subject=subject, spot_close_frame=spot_close_frame
        )
        audit["blockers"].extend(basis_blockers)
    else:
        premium_frame = _fetch_binance_premium_index_daily(
            client=binance_client,
            symbol=symbol,
            limit=min(max(lookback_days + 5, 40), 1500),
        )
        if premium_frame.empty:
            audit["blockers"].append(f"{symbol}:binance_premium_index_daily_empty")
            basis = pd.DataFrame(columns=["date_utc", "basis_proxy"])
        else:
            basis = premium_frame[["date_utc", "basis_proxy"]].copy()
    panel_atr = _panel_atr_proxy_20(panel=panel, symbol=symbol, subject=subject)
    frame = frame.merge(basis, on="date_utc", how="left").merge(panel_atr, on="date_utc", how="left")
    funding_30 = frame["funding_rate"].rolling(30).mean()
    basis_30 = frame["basis_proxy"].rolling(30).mean()
    frame["funding_basis_residual_implied_repo_30"] = (funding_30 - basis_30) / frame["atr_proxy_20"].replace(0.0, np.nan)

    received_ms = int(request_received.timestamp() * 1000)
    output = frame[
        [
            "subject",
            "date_utc",
            "quality_funding_oi",
            "funding_basis_residual_implied_repo_30",
            "close_time_ms",
        ]
    ].copy()
    for factor in ("quality_funding_oi", "funding_basis_residual_implied_repo_30"):
        output[f"{factor}_provider_timestamp_ms"] = output["close_time_ms"]
        output[f"{factor}_available_at_ms"] = received_ms
        output[f"{factor}_source"] = "coinglass_daily_derivatives_plus_binance_premium_sidecar_p10b"
    output = output.drop(columns=["close_time_ms"])
    return output, audit


def _build_taker_dispersion_sidecar(
    *,
    symbol: str,
    decision_time: datetime,
    args: argparse.Namespace,
    now_fn: Callable[[], datetime],
    api_key: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    subject = _symbol_to_subject(symbol)
    lookback_days = max(2, int(getattr(args, "sidecar_hour_lookback_days", 4) or 4))
    end_ms = int(decision_time.timestamp() * 1000)
    start_ms = end_ms - lookback_days * DAY_MS
    timeout = float(getattr(args, "request_timeout_seconds", 20.0))

    def _cg_get(url: str) -> Any:
        return http_get_json(url, api_key=api_key, timeout_seconds=timeout)

    requested_at = now_fn()
    audit = {"requests": [_request_audit_row(symbol, "coinglass_taker_buy_sell_volume_1h", requested_at, TAKER_BUY_SELL_VOLUME_HISTORY_URL)], "blockers": []}
    try:
        rows = _fetch_taker_buy_sell_volume_history(
            exchange=COINGLASS_DEFAULT_EXCHANGE_NAME,
            symbol=symbol,
            interval="1h",
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            http_get_json_fn=_cg_get,
        )
        received_at = now_fn()
        audit["requests"][0].update({"received_at_utc": iso_z(received_at), "status": "success", "row_count": len(rows)})
    except Exception as exc:
        audit["requests"][0].update({"status": "error", "error": f"{exc.__class__.__name__}:{exc}"})
        audit["blockers"].append(f"{symbol}:coinglass_taker_1h_request_failed")
        return pd.DataFrame(), audit
    parsed_rows: list[dict[str, Any]] = []
    for row in rows:
        open_ms = _int_ms(row.get("time"))
        buy, sell = _taker_buy_sell_values(row)
        if open_ms is None or buy is None or sell is None:
            continue
        total = buy + sell
        if total <= 0.0:
            continue
        parsed_rows.append(
            {
                "open_time_ms": open_ms,
                "day_open_ms": (open_ms // DAY_MS) * DAY_MS,
                "taker_imb": (buy - sell) / total,
            }
        )
    if not parsed_rows:
        audit["blockers"].append(f"{symbol}:coinglass_taker_1h_no_parseable_rows")
        return pd.DataFrame(), audit
    hourly = pd.DataFrame(parsed_rows).sort_values("open_time_ms")
    grouped = hourly.groupby("day_open_ms", sort=True).agg(
        hourly_count=("open_time_ms", "count"),
        coinglass_taker_imb_intraday_dispersion_24h=("taker_imb", lambda s: float(pd.to_numeric(s, errors="coerce").std())),
    )
    grouped = grouped.reset_index()
    grouped = grouped.loc[grouped["hourly_count"].ge(20)].copy()
    if grouped.empty:
        audit["blockers"].append(f"{symbol}:coinglass_taker_1h_no_complete_daily_dispersion")
        return pd.DataFrame(), audit
    grouped["subject"] = subject
    grouped["date_utc"] = grouped["day_open_ms"].map(_date_utc_from_ms)
    grouped["coinglass_taker_imb_intraday_dispersion_24h_provider_timestamp_ms"] = grouped["day_open_ms"].map(_daily_close_ms)
    grouped["coinglass_taker_imb_intraday_dispersion_24h_available_at_ms"] = int(received_at.timestamp() * 1000)
    grouped["coinglass_taker_imb_intraday_dispersion_24h_source"] = "coinglass_taker_1h_sidecar_p10b"
    return grouped[
        [
            "subject",
            "date_utc",
            "coinglass_taker_imb_intraday_dispersion_24h",
            "coinglass_taker_imb_intraday_dispersion_24h_provider_timestamp_ms",
            "coinglass_taker_imb_intraday_dispersion_24h_available_at_ms",
            "coinglass_taker_imb_intraday_dispersion_24h_source",
        ]
    ], audit


def _build_settlement_sidecar(
    *,
    symbol: str,
    decision_time: datetime,
    args: argparse.Namespace,
    binance_client: BinanceUsdmClient,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    subject = _symbol_to_subject(symbol)
    requested_at = datetime.now(UTC)
    audit = {
        "requests": [],
        "blockers": [],
        "pagination_enabled": False,
        "lookback_days": int(getattr(args, "settlement_lookback_days", 0) or 0),
        "retry_count": 0,
    }
    try:
        payload = _fetch_settlement_1h_klines(
            symbol=symbol,
            decision_time=decision_time,
            args=args,
            binance_client=binance_client,
            audit=audit,
            requested_at=requested_at,
        )
        received_at = datetime.now(UTC)
    except Exception as exc:
        if not audit["requests"]:
            audit["requests"].append(_request_audit_row(symbol, "binance_1h_klines_settlement", requested_at, "/fapi/v1/klines"))
        audit["requests"][-1].update({"status": "error", "error": f"{exc.__class__.__name__}:{exc}"})
        audit["blockers"].append(f"{symbol}:binance_1h_settlement_request_failed")
        return pd.DataFrame(), audit
    audit["row_count"] = int(len(payload or []))
    audit["page_count"] = int(len(audit["requests"]))
    hourly = klines_payload_to_frame(symbol=symbol, payload=payload)
    if hourly.empty:
        audit["blockers"].append(f"{symbol}:binance_1h_settlement_empty")
        return pd.DataFrame(), audit
    frame = hourly.sort_values("open_time_ms").copy()
    close = pd.to_numeric(frame["close"], errors="coerce").replace(0.0, np.nan)
    frame["log_return_1h"] = np.log(close / close.shift(1))
    frame["hour_utc"] = pd.to_datetime(frame["open_time_ms"].astype("int64"), unit="ms", utc=True).dt.hour
    frame["date_utc"] = frame["open_time_ms"].map(_date_utc_from_ms)

    daily_rows: list[dict[str, Any]] = []
    for date_utc, group in frame.groupby("date_utc", sort=True):
        returns = pd.to_numeric(group["log_return_1h"], errors="coerce")
        if len(group) != 24 or returns.notna().sum() != 24:
            continue
        pre = returns.loc[group["hour_utc"].isin({7, 15, 23})]
        other = returns.loc[~group["hour_utc"].isin({7, 15, 23})]
        if len(pre) != 3 or len(other) != 21:
            continue
        daily_rows.append(
            {
                "date_utc": date_utc,
                "day_open_ms": int(pd.to_numeric(group["open_time_ms"], errors="coerce").min()),
                "provider_timestamp_ms": int(pd.to_numeric(group["close_time_ms"], errors="coerce").max()),
                "settlement_cycle_premium_raw": float(pre.mean() - other.mean()),
            }
        )
    if not daily_rows:
        audit["blockers"].append(f"{symbol}:binance_1h_settlement_no_complete_days")
        return pd.DataFrame(), audit
    daily = pd.DataFrame(daily_rows).sort_values("day_open_ms").reset_index(drop=True)
    daily["settlement_cycle_premium_60d"] = daily["settlement_cycle_premium_raw"].rolling(60, min_periods=60).mean()
    daily["subject"] = subject
    daily["settlement_cycle_premium_60d_provider_timestamp_ms"] = daily["provider_timestamp_ms"]
    daily["settlement_cycle_premium_60d_available_at_ms"] = daily["provider_timestamp_ms"] + int(
        getattr(args, "availability_lag_seconds", DEFAULT_AVAILABILITY_LAG_SECONDS)
    ) * 1000
    daily["settlement_cycle_premium_60d_source"] = "binance_1h_settlement_sidecar_p10b"
    return daily[
        [
            "subject",
            "date_utc",
            "settlement_cycle_premium_60d",
            "settlement_cycle_premium_60d_provider_timestamp_ms",
            "settlement_cycle_premium_60d_available_at_ms",
            "settlement_cycle_premium_60d_source",
        ]
    ], audit


def _fetch_settlement_1h_klines(
    *,
    symbol: str,
    decision_time: datetime,
    args: argparse.Namespace,
    binance_client: BinanceUsdmClient,
    audit: dict[str, Any],
    requested_at: datetime,
) -> list[Any]:
    max_attempts = min(max(int(getattr(args, "settlement_request_max_attempts", 3) or 3), 1), 5)
    retry_sleep_seconds = max(float(getattr(args, "settlement_request_retry_sleep_seconds", 0.25) or 0.0), 0.0)
    lookback_days = int(getattr(args, "settlement_lookback_days", 0) or 0)
    if lookback_days <= 0:
        limit = min(max(int(getattr(args, "settlement_hour_limit", 1500) or 1500), 100), 1500)
        payload = _fetch_settlement_kline_page_with_retry(
            symbol=symbol,
            binance_client=binance_client,
            audit=audit,
            endpoint_id="binance_1h_klines_settlement",
            requested_at=requested_at,
            pagination_page=1,
            limit=limit,
            start_time=None,
            end_time=None,
            max_attempts=max_attempts,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        return list(payload or [])

    audit["pagination_enabled"] = True
    page_limit = min(max(int(getattr(args, "settlement_page_limit", 1500) or 1500), 100), 1500)
    availability_lag_seconds = int(getattr(args, "availability_lag_seconds", DEFAULT_AVAILABILITY_LAG_SECONDS) or DEFAULT_AVAILABILITY_LAG_SECONDS)
    end_ms = int(decision_time.timestamp() * 1000) - availability_lag_seconds * 1000
    start_ms = end_ms - int(lookback_days) * DAY_MS
    cursor = int(start_ms)
    payload_rows: list[Any] = []
    seen_open_times: set[int] = set()
    page = 0
    sleep_seconds = max(float(getattr(args, "settlement_request_sleep_seconds", 0.0) or 0.0), 0.0)
    while cursor <= end_ms:
        page += 1
        page_payload = _fetch_settlement_kline_page_with_retry(
            symbol=symbol,
            binance_client=binance_client,
            audit=audit,
            endpoint_id="binance_1h_klines_settlement_paginated",
            requested_at=datetime.now(UTC),
            pagination_page=page,
            limit=page_limit,
            start_time=int(cursor),
            end_time=int(end_ms),
            max_attempts=max_attempts,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        request = audit["requests"][-1]
        page_rows = list(page_payload or [])
        if not page_rows:
            break
        max_open_ms = cursor
        new_rows = 0
        for item in page_rows:
            try:
                open_ms = int(item[0])
            except (TypeError, ValueError, IndexError):
                continue
            max_open_ms = max(max_open_ms, open_ms)
            if open_ms in seen_open_times:
                continue
            seen_open_times.add(open_ms)
            payload_rows.append(item)
            new_rows += 1
        request["deduped_new_row_count"] = int(new_rows)
        next_cursor = int(max_open_ms) + HOUR_MS
        if next_cursor <= cursor:
            audit["blockers"].append(f"{symbol}:binance_1h_settlement_pagination_cursor_stalled")
            break
        cursor = next_cursor
        if len(page_rows) < page_limit:
            break
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return sorted(payload_rows, key=lambda item: int(item[0]) if len(item) else 0)


def _fetch_settlement_kline_page_with_retry(
    *,
    symbol: str,
    binance_client: BinanceUsdmClient,
    audit: dict[str, Any],
    endpoint_id: str,
    requested_at: datetime,
    pagination_page: int,
    limit: int,
    start_time: int | None,
    end_time: int | None,
    max_attempts: int,
    retry_sleep_seconds: float,
) -> list[Any]:
    last_exc: Exception | None = None
    for attempt in range(1, int(max_attempts) + 1):
        request = _request_audit_row(symbol, endpoint_id, requested_at if attempt == 1 else datetime.now(UTC), "/fapi/v1/klines")
        request.update(
            {
                "pagination_page": int(pagination_page),
                "retry_attempt": int(attempt),
                "retry_max_attempts": int(max_attempts),
                "limit": int(limit),
            }
        )
        if start_time is not None:
            request["start_time_ms"] = int(start_time)
        if end_time is not None:
            request["end_time_ms"] = int(end_time)
        audit["requests"].append(request)
        try:
            kwargs: dict[str, Any] = {"symbol": symbol, "interval": "1h", "limit": int(limit)}
            if start_time is not None:
                kwargs["start_time"] = int(start_time)
            if end_time is not None:
                kwargs["end_time"] = int(end_time)
            payload = binance_client.klines(**kwargs).payload
            rows = list(payload or [])
            request.update({"received_at_utc": iso_z(datetime.now(UTC)), "status": "success", "row_count": len(rows)})
            return rows
        except Exception as exc:
            last_exc = exc
            request.update(
                {
                    "received_at_utc": iso_z(datetime.now(UTC)),
                    "status": "error",
                    "error": f"{exc.__class__.__name__}:{exc}",
                    "retryable": True,
                }
            )
            if attempt < int(max_attempts):
                audit["retry_count"] = int(audit.get("retry_count") or 0) + 1
                if retry_sleep_seconds > 0:
                    time.sleep(retry_sleep_seconds)
                continue
            request["retryable"] = False
            raise
    if last_exc is not None:
        raise last_exc
    return []


def _build_pit_snapshot(
    *,
    panel: pd.DataFrame,
    symbols: list[str],
    required_factors: list[str],
    decision_time: datetime,
    freshness_seconds: int,
    availability_lag_seconds: int,
    min_symbol_coverage: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    joined_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    factor_rows: list[dict[str, Any]] = []
    decision_ms = int(decision_time.timestamp() * 1000)
    expected_subjects = [_symbol_to_subject(symbol) for symbol in symbols]
    minimum_joined_symbols = int(math.ceil(max(0.0, min(float(min_symbol_coverage), 1.0)) * len(symbols)))
    if len(symbols) == 0:
        minimum_joined_symbols = 0

    for factor in required_factors:
        missing_column = factor not in panel.columns
        factor_joined = 0
        factor_counts = {
            "eligible_count": 0,
            "future_blocked_count": 0,
            "stale_blocked_count": 0,
            "missing_value_blocked_count": 0,
            "missing_timestamp_metadata_count": 0,
        }
        for symbol, subject in zip(symbols, expected_subjects, strict=False):
            symbol_rows = _rows_for_symbol(panel, symbol=symbol, subject=subject)
            factor_candidates: list[dict[str, Any]] = []
            if not missing_column:
                for row_index, row in symbol_rows.iterrows():
                    candidate = _candidate_from_panel_row(
                        row=row,
                        row_index=int(row_index),
                        symbol=symbol,
                        subject=subject,
                        factor=factor,
                        decision_time=decision_time,
                        freshness_seconds=freshness_seconds,
                        availability_lag_seconds=availability_lag_seconds,
                    )
                    candidate_rows.append(candidate)
                    factor_candidates.append(candidate)
            selected = _latest_eligible_candidate(factor_candidates)
            counts = _candidate_counts(factor_candidates)
            for key in factor_counts:
                factor_counts[key] += counts[key]
            if selected is None:
                joined_rows.append(
                    {
                        "symbol": symbol,
                        "subject": subject,
                        "factor_id": factor,
                        "factor_source_category": classify_factor_source(factor),
                        "join_status": "blocked_missing_factor_column"
                        if missing_column
                        else "blocked_no_eligible_live_feature_row",
                        "decision_time_utc": iso_z(decision_time),
                        "decision_time_ms": decision_ms,
                        "provider_timestamp_utc": "",
                        "provider_timestamp_ms": "",
                        "available_at_utc": "",
                        "available_at_ms": "",
                        "provider_age_seconds": "",
                        "value": "",
                        "source": "",
                        "future_fill_violation": False,
                        "stale_fill_violation": False,
                        "zero_fill_violation": False,
                        **counts,
                    }
                )
                continue
            provider_ms = int(selected["provider_timestamp_ms"])
            available_ms = int(selected["available_at_ms"])
            provider_age_seconds = (decision_ms - provider_ms) / 1000.0
            joined_rows.append(
                {
                    "symbol": symbol,
                    "subject": subject,
                    "factor_id": factor,
                    "factor_source_category": classify_factor_source(factor),
                    "join_status": "joined",
                    "decision_time_utc": iso_z(decision_time),
                    "decision_time_ms": decision_ms,
                    "provider_timestamp_utc": selected["provider_timestamp_utc"],
                    "provider_timestamp_ms": provider_ms,
                    "available_at_utc": selected["available_at_utc"],
                    "available_at_ms": available_ms,
                    "provider_age_seconds": round(provider_age_seconds, 3),
                    "value": selected["value"],
                    "source": selected["source"],
                    "future_fill_violation": provider_ms > decision_ms or available_ms > decision_ms,
                    "stale_fill_violation": provider_age_seconds > freshness_seconds,
                    "zero_fill_violation": not _bool(selected.get("value_ready")) or _bool(selected.get("zero_fill_used")),
                    **counts,
                }
            )
            factor_joined += 1

        coverage_ratio = (factor_joined / len(symbols)) if symbols else 0.0
        coverage_below_min = factor_joined < minimum_joined_symbols
        factor_rows.append(
            {
                "factor_id": factor,
                "factor_source_category": classify_factor_source(factor),
                "status": "ready" if not missing_column and not coverage_below_min else "blocked",
                "missing_column": missing_column,
                "requested_symbol_count": len(symbols),
                "joined_symbol_count": factor_joined,
                "minimum_joined_symbol_count": minimum_joined_symbols,
                "coverage_ratio": round(coverage_ratio, 6),
                "coverage_below_min": coverage_below_min,
                **factor_counts,
            }
        )
    return joined_rows, candidate_rows, factor_rows


def _candidate_from_panel_row(
    *,
    row: pd.Series,
    row_index: int,
    symbol: str,
    subject: str,
    factor: str,
    decision_time: datetime,
    freshness_seconds: int,
    availability_lag_seconds: int,
) -> dict[str, Any]:
    decision_ms = int(decision_time.timestamp() * 1000)
    value = _finite_float(row.get(factor))
    provider_ms = _provider_timestamp_ms(row, factor=factor)
    provider_source = _provider_timestamp_source(row, factor=factor)
    available_ms = _available_at_ms(
        row,
        factor=factor,
        provider_ms=provider_ms,
        availability_lag_seconds=availability_lag_seconds,
    )
    available_source = _available_at_source(row, factor=factor, provider_ms=provider_ms)
    provider_age_seconds = ((decision_ms - provider_ms) / 1000.0) if provider_ms is not None else None
    source = str(row.get(f"{factor}_source") or row.get("source") or classify_factor_source(factor))

    if provider_ms is None or available_ms is None:
        status = "blocked_missing_timestamp_metadata"
    elif value is None:
        status = "blocked_missing_value"
    elif provider_ms > decision_ms or available_ms > decision_ms:
        status = "future_blocked"
    elif provider_age_seconds is not None and provider_age_seconds > freshness_seconds:
        status = "stale_blocked"
    else:
        status = "eligible"

    return {
        "row_index": row_index,
        "symbol": symbol,
        "subject": subject,
        "factor_id": factor,
        "factor_source_category": classify_factor_source(factor),
        "source": source,
        "decision_time_utc": iso_z(decision_time),
        "decision_time_ms": decision_ms,
        "provider_timestamp_utc": _ms_iso(provider_ms),
        "provider_timestamp_ms": provider_ms if provider_ms is not None else "",
        "provider_timestamp_source": provider_source,
        "available_at_utc": _ms_iso(available_ms),
        "available_at_ms": available_ms if available_ms is not None else "",
        "available_at_source": available_source,
        "provider_age_seconds": round(provider_age_seconds, 3) if provider_age_seconds is not None else "",
        "freshness_seconds": freshness_seconds,
        "value": value if value is not None else "",
        "value_ready": value is not None,
        "zero_fill_used": False,
        "pit_candidate_status": status,
        "future_blocked": status == "future_blocked",
        "stale_blocked": status == "stale_blocked",
        "missing_value_blocked": status == "blocked_missing_value",
        "missing_timestamp_metadata": status == "blocked_missing_timestamp_metadata",
    }


def _fetch_binance_premium_index_daily(
    *,
    client: BinanceUsdmClient,
    symbol: str,
    limit: int,
) -> pd.DataFrame:
    response = client._request(  # Private client request keeps this proof-only script read-only.
        "GET",
        "/fapi/v1/premiumIndexKlines",
        params={"symbol": symbol, "interval": "1d", "limit": int(limit)},
    )
    rows: list[dict[str, Any]] = []
    for item in list(response.payload or []):
        if len(item) < 7:
            continue
        try:
            open_ms = int(item[0])
            close_ms = int(item[6])
            basis_proxy = float(item[4])
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "open_time_ms": open_ms,
                "close_time_ms": close_ms,
                "date_utc": _date_utc_from_ms(open_ms),
                "basis_proxy": basis_proxy,
            }
        )
    return pd.DataFrame(rows).sort_values("open_time_ms").reset_index(drop=True) if rows else pd.DataFrame()


def _panel_atr_proxy_20(*, panel: pd.DataFrame, symbol: str, subject: str) -> pd.DataFrame:
    rows = _rows_for_symbol(_normalize_panel_symbols(panel), symbol=symbol, subject=subject)
    if rows.empty:
        return pd.DataFrame(columns=["date_utc", "atr_proxy_20"])
    frame = rows.sort_values("timestamp_ms").copy()
    if "date_utc" not in frame.columns:
        frame["date_utc"] = pd.to_numeric(frame["timestamp_ms"], errors="coerce").map(_date_utc_from_ms)
    high = pd.to_numeric(frame.get("perp_high"), errors="coerce")
    low = pd.to_numeric(frame.get("perp_low"), errors="coerce")
    close = pd.to_numeric(frame.get("perp_close"), errors="coerce").replace(0.0, np.nan)
    frame["atr_proxy_20"] = ((high - low) / close.shift(1).replace(0.0, np.nan)).rolling(20).mean()
    return frame[["date_utc", "atr_proxy_20"]].copy()


def _perp_spot_basis_proxy(
    *,
    panel: pd.DataFrame,
    symbol: str,
    subject: str,
    spot_close_frame: pd.DataFrame | None,
) -> tuple[pd.DataFrame, list[str]]:
    """Research-parity basis_proxy = (perp_close - spot_close) / spot_close per date_utc, matching
    research lab.py:1876.

    IMPORTANT (data source): perp_close is read from the BASE ``panel`` — Binance USDM perp close set by
    market_data.fetch_public_live_feature_panel (market_data.py:342, source 'binance_usdm_public_rest'),
    via _rows_for_symbol/_normalize_panel_symbols — the SAME venue as research's perp leg. It is NOT the
    CoinGlass-sourced ``frame["perp_close"]`` that _build_daily_derivatives_sidecar uses for funding/OI.
    spot_close comes from fetch_live_spot_close_frame (Binance spot). So basis == research's
    (Binance perp - Binance spot)/spot exactly.

    Returns ([date_utc, basis_proxy], blockers). Fail-closed: any missing input yields an EMPTY frame +
    a blocker (=> downstream basis_30 NaN => funding_basis_residual NaN => the snapshot blocks; never a
    silent fallback to premiumIndex)."""
    rows = _rows_for_symbol(_normalize_panel_symbols(panel), symbol=symbol, subject=subject)
    if rows.empty:
        return pd.DataFrame(columns=["date_utc", "basis_proxy"]), [f"{symbol}:perp_spot_basis_panel_rows_missing"]
    pframe = rows.sort_values("timestamp_ms").copy()
    if "date_utc" not in pframe.columns:
        pframe["date_utc"] = pd.to_numeric(pframe["timestamp_ms"], errors="coerce").map(_date_utc_from_ms)
    pframe["perp_close"] = pd.to_numeric(pframe.get("perp_close"), errors="coerce")
    if spot_close_frame is None or spot_close_frame.empty or "subject" not in spot_close_frame.columns:
        return pd.DataFrame(columns=["date_utc", "basis_proxy"]), [f"{symbol}:perp_spot_basis_spot_unavailable"]
    sf = spot_close_frame.loc[spot_close_frame["subject"] == subject, ["date_utc", "spot_close"]].copy()
    if sf.empty:
        return pd.DataFrame(columns=["date_utc", "basis_proxy"]), [f"{symbol}:perp_spot_basis_spot_subject_missing"]
    sf["spot_close"] = pd.to_numeric(sf["spot_close"], errors="coerce")
    merged = pframe[["date_utc", "perp_close"]].merge(sf, on="date_utc", how="inner")
    merged = merged.loc[
        merged["perp_close"].notna() & merged["spot_close"].notna() & merged["spot_close"].ne(0.0)
    ]
    if merged.empty:
        return pd.DataFrame(columns=["date_utc", "basis_proxy"]), [f"{symbol}:perp_spot_basis_no_overlap"]
    merged["basis_proxy"] = (merged["perp_close"] - merged["spot_close"]) / merged["spot_close"]
    return merged[["date_utc", "basis_proxy"]].copy(), []


def _taker_buy_sell_values(row: dict[str, Any]) -> tuple[float | None, float | None]:
    candidates = (
        ("taker_buy_volume_usd", "taker_sell_volume_usd"),
        ("buy_volume_usd", "sell_volume_usd"),
        ("buy_usd", "sell_usd"),
        ("buy", "sell"),
    )
    for buy_key, sell_key in candidates:
        if buy_key not in row and sell_key not in row:
            continue
        buy = _finite_float(row.get(buy_key))
        sell = _finite_float(row.get(sell_key))
        if buy is not None and sell is not None:
            return buy, sell
    return None, None


def _request_audit_row(symbol: str, endpoint_id: str, requested_at: datetime, endpoint: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "endpoint_id": endpoint_id,
        "endpoint": endpoint,
        "requested_at_utc": iso_z(requested_at),
        "received_at_utc": "",
        "status": "requested",
        "row_count": 0,
    }


def _provider_timestamp_ms(row: pd.Series, *, factor: str) -> int | None:
    for column in (
        f"{factor}_provider_timestamp_ms",
        f"{factor}_provider_time_ms",
        f"{factor}_timestamp_ms",
        f"{factor}_time_ms",
        "provider_timestamp_ms",
    ):
        parsed = _int_ms(row.get(column))
        if parsed is not None:
            return parsed
    if factor in BINANCE_PUBLIC_FACTOR_IDS:
        for column in ("close_time_ms", "timestamp_ms"):
            parsed = _int_ms(row.get(column))
            if parsed is not None:
                return parsed
    return None


def _provider_timestamp_source(row: pd.Series, *, factor: str) -> str:
    for column in (
        f"{factor}_provider_timestamp_ms",
        f"{factor}_provider_time_ms",
        f"{factor}_timestamp_ms",
        f"{factor}_time_ms",
        "provider_timestamp_ms",
    ):
        if _int_ms(row.get(column)) is not None:
            return column
    if factor in BINANCE_PUBLIC_FACTOR_IDS:
        for column in ("close_time_ms", "timestamp_ms"):
            if _int_ms(row.get(column)) is not None:
                return f"derived_from_{column}"
    return ""


def _available_at_ms(
    row: pd.Series,
    *,
    factor: str,
    provider_ms: int | None,
    availability_lag_seconds: int,
) -> int | None:
    for column in (f"{factor}_available_at_ms", f"{factor}_observed_at_ms", "available_at_ms", "observed_at_ms"):
        parsed = _int_ms(row.get(column))
        if parsed is not None:
            return parsed
    if provider_ms is not None and factor in BINANCE_PUBLIC_FACTOR_IDS:
        return int(provider_ms + int(availability_lag_seconds) * 1000)
    return None


def _available_at_source(row: pd.Series, *, factor: str, provider_ms: int | None) -> str:
    for column in (f"{factor}_available_at_ms", f"{factor}_observed_at_ms", "available_at_ms", "observed_at_ms"):
        if _int_ms(row.get(column)) is not None:
            return column
    if provider_ms is not None and factor in BINANCE_PUBLIC_FACTOR_IDS:
        return "derived_from_provider_timestamp_plus_lag"
    return ""


def classify_factor_source(factor: str) -> str:
    if factor in BINANCE_PUBLIC_FACTOR_IDS:
        return "binance_usdm_public_1d_4h_klines"
    if factor == SETTLEMENT_FACTOR_ID:
        return "binance_usdm_public_1h_settlement_sidecar_required"
    if factor == "coinglass_top_trader_long_pct_smooth_5":
        return "coinglass_top_trader_sidecar_required"
    if factor == "open_interest_value":
        return "coinglass_open_interest_sidecar_required"
    if factor == "coinglass_taker_imb_intraday_dispersion_24h":
        return "coinglass_taker_volume_sidecar_required"
    if factor == "quality_funding_oi":
        return "funding_open_interest_derived_sidecar_required"
    if factor == "funding_basis_residual_implied_repo_30":
        return "funding_basis_price_derived_sidecar_required"
    return "unknown_required_factor_source"


def _normalize_panel_symbols(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    output = panel.copy()
    if "symbol" not in output.columns and "usdm_symbol" in output.columns:
        output["symbol"] = output["usdm_symbol"]
    if "subject" not in output.columns and "symbol" in output.columns:
        output["subject"] = output["symbol"].map(_symbol_to_subject)
    if "symbol" not in output.columns and "subject" in output.columns:
        output["symbol"] = output["subject"].astype(str).str.upper() + "USDT"
    if "symbol" in output.columns:
        output["symbol"] = output["symbol"].astype(str).str.upper()
    if "usdm_symbol" in output.columns:
        output["usdm_symbol"] = output["usdm_symbol"].astype(str).str.upper()
    if "subject" in output.columns:
        output["subject"] = output["subject"].astype(str).str.upper()
    return output


def _rows_for_symbol(panel: pd.DataFrame, *, symbol: str, subject: str) -> pd.DataFrame:
    if panel.empty:
        return panel
    masks: list[pd.Series] = []
    if "symbol" in panel.columns:
        masks.append(panel["symbol"].astype(str).str.upper().eq(str(symbol).upper()))
    if "usdm_symbol" in panel.columns:
        masks.append(panel["usdm_symbol"].astype(str).str.upper().eq(str(symbol).upper()))
    if "subject" in panel.columns:
        masks.append(panel["subject"].astype(str).str.upper().eq(str(subject).upper()))
    if not masks:
        return panel.iloc[0:0]
    mask = masks[0].copy()
    for item in masks[1:]:
        mask = mask | item
    return panel.loc[mask].copy()


def _latest_eligible_candidate(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [row for row in rows if row.get("pit_candidate_status") == "eligible"]
    if not eligible:
        return None
    eligible.sort(key=lambda row: (int(row.get("provider_timestamp_ms") or -1), int(row.get("available_at_ms") or -1)))
    return eligible[-1]


def _candidate_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "eligible_count": sum(1 for row in rows if row.get("pit_candidate_status") == "eligible"),
        "future_blocked_count": sum(1 for row in rows if row.get("pit_candidate_status") == "future_blocked"),
        "stale_blocked_count": sum(1 for row in rows if row.get("pit_candidate_status") == "stale_blocked"),
        "missing_value_blocked_count": sum(
            1 for row in rows if row.get("pit_candidate_status") == "blocked_missing_value"
        ),
        "missing_timestamp_metadata_count": sum(
            1 for row in rows if row.get("pit_candidate_status") == "blocked_missing_timestamp_metadata"
        ),
    }


def _bounded_panel_snapshot(panel: pd.DataFrame, *, max_rows: int = 500) -> pd.DataFrame:
    if panel.empty:
        return panel.copy()
    columns = [str(column) for column in panel.columns]
    ordered_columns = [
        column
        for column in (
            "timestamp_ms",
            "close_time_ms",
            "provider_timestamp_ms",
            "available_at_ms",
            "symbol",
            "usdm_symbol",
            "subject",
        )
        if column in columns
    ]
    factor_columns = [column for column in columns if column not in set(ordered_columns)]
    selected_columns = ordered_columns + factor_columns[:40]
    return panel.loc[:, selected_columns].head(max_rows).copy()


def _symbol_to_subject(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if normalized.endswith("USDT"):
        return normalized[:-4]
    return normalized


def _date_utc_from_ms(value: Any) -> str:
    parsed = _int_ms(value)
    if parsed is None:
        return ""
    return datetime.fromtimestamp(parsed / 1000.0, tz=UTC).date().isoformat()


def _daily_close_ms(open_ms: int) -> int:
    return int((int(open_ms) // DAY_MS) * DAY_MS + DAY_MS - 1)


def _safe_path_token(value: str) -> str:
    normalized = []
    for char in str(value or "").lower():
        normalized.append(char if char.isalnum() else "_")
    token = "".join(normalized).strip("_")
    return token or "run"


def _int_ms(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    if parsed < 10_000_000_000:
        parsed *= 1000
    return parsed


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _ms_iso(value: int | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(int(value) / 1000.0, tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def write_csv(path: Path, rows: Iterable[dict[str, Any]] | pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(rows, pd.DataFrame):
        rows.to_csv(path, index=False)
        return
    materialized = list(rows)
    if not materialized:
        path.write_text("", encoding="utf-8")
        return
    pd.DataFrame(materialized).to_csv(path, index=False)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).tz_convert("UTC").isoformat().replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    return value


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_p10a_live_feature_builder(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
