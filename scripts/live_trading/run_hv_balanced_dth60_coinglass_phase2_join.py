from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path  # noqa: E402
from enhengclaw.live_trading.market_data import resolve_config_symbols  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_step1_health import (  # noqa: E402
    BASE_URL,
    EXCHANGE,
    TOP_TRADER_ENDPOINT_ID,
    TOP_TRADER_PATH,
    http_get_json,
    iso_z,
    parse_time_ms,
    payload_rows,
    provider_ok,
    resolve_api_key,
    write_csv,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase2_pit_join.v1"
DEFAULT_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/phase2_pit_sidecar_join"
)
FACTOR_ID = "coinglass_top_trader_long_pct_smooth_5"
VALUE_ALIASES = (
    "top_position_long_percent",
    "top_trader_long_pct",
    "long_percent",
    "longShortRatio",
    "long_short_ratio",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a PIT-safe CoinGlass top-trader sidecar join for the hv_balanced "
            "DTH60 candidate. Writes evidence only; never changes live config."
        )
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--decision-time", default="now")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--freshness-seconds", type=int, default=36 * 3600)
    parser.add_argument("--min-window", type=int, default=5)
    parser.add_argument("--request-sleep-seconds", type=float, default=0.12)
    parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
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


def parse_row_time(row: dict[str, Any]) -> datetime | None:
    for key in ("time", "timestamp", "timestamp_ms", "t"):
        parsed = parse_time_ms(row.get(key))
        if parsed is not None:
            return datetime.fromtimestamp(parsed / 1000.0, tz=UTC)
    return None


def float_from_row(row: dict[str, Any], *aliases: str) -> float | None:
    for key in aliases:
        if key not in row:
            continue
        value = row.get(key)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            return numeric
    return None


def run_phase2_join(
    args: argparse.Namespace,
    *,
    http_get_json_fn: Callable[[str, str, float], Any] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    requested_decision_time = parse_decision_time(str(getattr(args, "decision_time", "now") or "now"), now_fn=now)
    live_config = load_live_trading_config(args.config)
    symbols = resolve_config_symbols(live_config.payload, override_symbols=str(getattr(args, "symbols", "") or ""))
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        resolve_repo_path(str(args.output_root))
        if str(getattr(args, "output_root", "") or "").strip()
        else resolve_repo_path(DEFAULT_OUTPUT_PARENT) / run_id
    )
    output_root.mkdir(parents=True, exist_ok=True)

    key = resolve_api_key(base_env=base_env)
    http_get = http_get_json_fn or (
        lambda url, api_key, timeout: http_get_json(url, api_key=api_key, timeout_seconds=timeout)
    )
    raw_rows: list[dict[str, Any]] = []
    sidecar_rows: list[dict[str, Any]] = []
    blockers: list[str] = []

    if not key.present:
        blockers.append("coinglass_api_key_missing")

    for symbol in symbols:
        requested_at = now()
        url = f"{BASE_URL}{TOP_TRADER_PATH}?{urlencode(_params(args, symbol))}"
        payload: Any | None = None
        request_status = "skipped"
        request_error = ""
        received_at = requested_at
        if key.present:
            try:
                payload = http_get(str(url), key.value, float(args.request_timeout_seconds))
                received_at = now()
                rows_for_ok = payload_rows(payload)
                request_status = "success" if provider_ok(payload, rows_for_ok) else "provider_error"
                request_error = "" if request_status == "success" else f"provider_code={dict(payload or {}).get('code')}"
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                received_at = now()
                request_status = "error"
                request_error = f"{exc.__class__.__name__}:{exc}"
        rows = _dedupe_rows(payload_rows(payload))
        if request_status != "success":
            blockers.append(f"{symbol}:top_trader_request_failed")
        elif not rows:
            blockers.append(f"{symbol}:top_trader_empty")
        symbol_raw, symbol_sidecar = _build_symbol_rows(
            symbol=symbol,
            rows=rows,
            requested_at=requested_at,
            received_at=received_at,
            request_status=request_status,
            request_error=request_error,
            min_window=int(args.min_window),
        )
        raw_rows.extend(symbol_raw)
        sidecar_rows.extend(symbol_sidecar)
        if float(args.request_sleep_seconds) > 0:
            time.sleep(float(args.request_sleep_seconds))

    if requested_decision_time is None:
        decision_time = now()
        decision_time_source = "post_fetch_now"
    else:
        decision_time = requested_decision_time
        decision_time_source = "operator_supplied"

    joined_rows, audit_rows = _join_snapshot(
        symbols=symbols,
        sidecar_rows=sidecar_rows,
        decision_time=decision_time,
        freshness_seconds=int(args.freshness_seconds),
        min_window=int(args.min_window),
    )
    sidecar_rows = _mark_sidecar_rows(
        sidecar_rows,
        decision_time=decision_time,
        freshness_seconds=int(args.freshness_seconds),
    )
    no_future_fill = all(str(row.get("future_fill_violation")).lower() != "true" for row in joined_rows)
    no_stale_fill = all(str(row.get("stale_fill_violation")).lower() != "true" for row in joined_rows)
    no_zero_fill = all(str(row.get("zero_fill_violation")).lower() != "true" for row in joined_rows)
    joined_symbol_count = len([row for row in joined_rows if row.get("join_status") == "joined"])
    missing_symbols = sorted(str(row["symbol"]) for row in joined_rows if row.get("join_status") != "joined")
    future_blocked_count = sum(1 for row in sidecar_rows if row.get("pit_candidate_status") == "future_blocked")
    stale_blocked_count = sum(1 for row in sidecar_rows if row.get("pit_candidate_status") == "stale_blocked")
    insufficient_window_count = sum(1 for row in sidecar_rows if row.get("pit_candidate_status") == "insufficient_window")

    if joined_symbol_count != len(symbols):
        blockers.append("phase2_join_missing_symbol")
    if not no_future_fill:
        blockers.append("future_fill_violation")
    if not no_stale_fill:
        blockers.append("stale_fill_violation")
    if not no_zero_fill:
        blockers.append("zero_fill_violation")
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "generated_at_utc": iso_z(now()),
        "started_at_utc": iso_z(started_at),
        "decision_time_utc": iso_z(decision_time),
        "decision_time_source": decision_time_source,
        "config_path": str(live_config.path),
        "output_root": str(output_root),
        "applied_to_live": False,
        "live_config_changed": False,
        "exchange_order_submission": "disabled",
        "operator_state_changed": False,
        "timer_state_changed": False,
        "provider": "coinglass",
        "exchange": EXCHANGE,
        "required_factor_id": FACTOR_ID,
        "required_endpoint_id": TOP_TRADER_ENDPOINT_ID,
        "required_endpoint_path": TOP_TRADER_PATH,
        "interval": str(args.interval),
        "limit": int(args.limit),
        "min_window": int(args.min_window),
        "freshness_seconds": int(args.freshness_seconds),
        "api_key_present": key.present,
        "api_key_source": key.source,
        "requested_symbol_count": len(symbols),
        "joined_symbol_count": joined_symbol_count,
        "missing_symbols": missing_symbols,
        "raw_row_count": len(raw_rows),
        "sidecar_row_count": len(sidecar_rows),
        "future_blocked_count": future_blocked_count,
        "stale_blocked_count": stale_blocked_count,
        "insufficient_window_count": insufficient_window_count,
        "no_future_fill_proven": no_future_fill,
        "no_stale_fill_proven": no_stale_fill,
        "no_zero_fill_proven": no_zero_fill,
        "blockers": blockers,
        "artifacts": {
            "summary_json": str(output_root / "summary.json"),
            "raw_rows_csv": str(output_root / "top_trader_raw_rows.csv"),
            "sidecar_rows_csv": str(output_root / "pit_sidecar_rows.csv"),
            "joined_snapshot_csv": str(output_root / "pit_joined_snapshot.csv"),
            "join_audit_csv": str(output_root / "pit_join_audit.csv"),
        },
    }
    write_csv(output_root / "top_trader_raw_rows.csv", raw_rows)
    write_csv(output_root / "pit_sidecar_rows.csv", sidecar_rows)
    write_csv(output_root / "pit_joined_snapshot.csv", joined_rows)
    write_csv(output_root / "pit_join_audit.csv", audit_rows)
    write_json(output_root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def _params(args: argparse.Namespace, symbol: str) -> dict[str, Any]:
    return {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "interval": str(args.interval),
        "limit": int(args.limit),
    }


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_time: dict[int, dict[str, Any]] = {}
    no_time: list[dict[str, Any]] = []
    for row in rows:
        timestamp = parse_row_time(row)
        if timestamp is None:
            no_time.append(row)
            continue
        by_time[int(timestamp.timestamp() * 1000)] = row
    ordered = [by_time[key] for key in sorted(by_time)]
    ordered.extend(no_time)
    return ordered


def _build_symbol_rows(
    *,
    symbol: str,
    rows: list[dict[str, Any]],
    requested_at: datetime,
    received_at: datetime,
    request_status: str,
    request_error: str,
    min_window: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw_rows: list[dict[str, Any]] = []
    sidecar_rows: list[dict[str, Any]] = []
    values_so_far: list[float] = []
    for index, row in enumerate(rows):
        provider_time = parse_row_time(row)
        raw_value = float_from_row(row, *VALUE_ALIASES)
        if raw_value is not None:
            values_so_far.append(raw_value)
        window_values = values_so_far[-min_window:]
        smooth_value = sum(window_values) / len(window_values) if len(window_values) >= min_window else None
        provider_timestamp_ms = int(provider_time.timestamp() * 1000) if provider_time else ""
        raw_rows.append(
            {
                "symbol": symbol,
                "provider": "coinglass",
                "exchange": EXCHANGE,
                "endpoint_id": TOP_TRADER_ENDPOINT_ID,
                "request_status": request_status,
                "request_error": request_error,
                "requested_at_utc": iso_z(requested_at),
                "observed_available_at_utc": iso_z(received_at),
                "provider_timestamp_utc": iso_z(provider_time) if provider_time else "",
                "provider_timestamp_ms": provider_timestamp_ms,
                "row_index": index,
                "top_trader_long_pct": raw_value if raw_value is not None else "",
                "raw_keys": ",".join(sorted(str(key) for key in row.keys())),
            }
        )
        sidecar_rows.append(
            {
                "symbol": symbol,
                "provider": "coinglass",
                "exchange": EXCHANGE,
                "factor_id": FACTOR_ID,
                "endpoint_id": TOP_TRADER_ENDPOINT_ID,
                "request_status": request_status,
                "provider_timestamp_utc": iso_z(provider_time) if provider_time else "",
                "provider_timestamp_ms": provider_timestamp_ms,
                "observed_available_at_utc": iso_z(received_at),
                "observed_available_at_ms": int(received_at.timestamp() * 1000),
                "top_trader_long_pct": raw_value if raw_value is not None else "",
                "rolling_window_count": len(window_values),
                "coinglass_top_trader_long_pct_smooth_5": smooth_value if smooth_value is not None else "",
                "sidecar_value_ready": smooth_value is not None,
                "candidate_rank_input": smooth_value if smooth_value is not None else "",
                "zero_fill_used": False,
            }
        )
    return raw_rows, sidecar_rows


def _mark_sidecar_rows(
    sidecar_rows: list[dict[str, Any]],
    *,
    decision_time: datetime,
    freshness_seconds: int,
) -> list[dict[str, Any]]:
    decision_ms = int(decision_time.timestamp() * 1000)
    marked: list[dict[str, Any]] = []
    for row in sidecar_rows:
        provider_ms = _int_or_none(row.get("provider_timestamp_ms"))
        available_ms = _int_or_none(row.get("observed_available_at_ms"))
        value_ready = _bool(row.get("sidecar_value_ready"))
        provider_age = (decision_ms - provider_ms) / 1000.0 if provider_ms is not None else None
        future_blocked = (
            provider_ms is None
            or available_ms is None
            or provider_ms > decision_ms
            or available_ms > decision_ms
        )
        stale_blocked = provider_age is None or provider_age > freshness_seconds
        if not value_ready:
            status = "insufficient_window"
        elif future_blocked:
            status = "future_blocked"
        elif stale_blocked:
            status = "stale_blocked"
        else:
            status = "eligible"
        out = dict(row)
        out.update(
            {
                "decision_time_utc": iso_z(decision_time),
                "decision_time_ms": decision_ms,
                "provider_age_seconds": round(provider_age, 3) if provider_age is not None else "",
                "future_blocked": future_blocked,
                "stale_blocked": stale_blocked,
                "pit_candidate_status": status,
            }
        )
        marked.append(out)
    return marked


def _join_snapshot(
    *,
    symbols: list[str],
    sidecar_rows: list[dict[str, Any]],
    decision_time: datetime,
    freshness_seconds: int,
    min_window: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    marked = _mark_sidecar_rows(sidecar_rows, decision_time=decision_time, freshness_seconds=freshness_seconds)
    joined_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        symbol_rows = [row for row in marked if row["symbol"] == symbol]
        eligible = [row for row in symbol_rows if row.get("pit_candidate_status") == "eligible"]
        eligible.sort(key=lambda row: int(row.get("provider_timestamp_ms") or -1))
        selected = eligible[-1] if eligible else None
        counts = {
            "eligible_count": len(eligible),
            "future_blocked_count": sum(1 for row in symbol_rows if row.get("pit_candidate_status") == "future_blocked"),
            "stale_blocked_count": sum(1 for row in symbol_rows if row.get("pit_candidate_status") == "stale_blocked"),
            "insufficient_window_count": sum(
                1 for row in symbol_rows if row.get("pit_candidate_status") == "insufficient_window"
            ),
        }
        if selected is None:
            joined = {
                "symbol": symbol,
                "join_status": "blocked_no_eligible_sidecar_row",
                "factor_id": FACTOR_ID,
                "decision_time_utc": iso_z(decision_time),
                "provider_timestamp_utc": "",
                "observed_available_at_utc": "",
                "provider_age_seconds": "",
                "coinglass_top_trader_long_pct_smooth_5": "",
                "rolling_window_count": "",
                "future_fill_violation": False,
                "stale_fill_violation": False,
                "zero_fill_violation": False,
            }
        else:
            provider_ms = int(selected["provider_timestamp_ms"])
            available_ms = int(selected["observed_available_at_ms"])
            decision_ms = int(decision_time.timestamp() * 1000)
            provider_age = (decision_ms - provider_ms) / 1000.0
            joined = {
                "symbol": symbol,
                "join_status": "joined",
                "factor_id": FACTOR_ID,
                "decision_time_utc": iso_z(decision_time),
                "provider_timestamp_utc": selected["provider_timestamp_utc"],
                "provider_timestamp_ms": provider_ms,
                "observed_available_at_utc": selected["observed_available_at_utc"],
                "observed_available_at_ms": available_ms,
                "provider_age_seconds": round(provider_age, 3),
                "coinglass_top_trader_long_pct_smooth_5": selected[
                    "coinglass_top_trader_long_pct_smooth_5"
                ],
                "rolling_window_count": selected["rolling_window_count"],
                "future_fill_violation": provider_ms > decision_ms or available_ms > decision_ms,
                "stale_fill_violation": provider_age > freshness_seconds,
                "zero_fill_violation": not _bool(selected.get("sidecar_value_ready")) or _bool(
                    selected.get("zero_fill_used")
                ),
            }
        joined_rows.append({**joined, **counts, "min_window": min_window, "freshness_seconds": freshness_seconds})
        audit_rows.append(
            {
                "symbol": symbol,
                "decision_time_utc": iso_z(decision_time),
                "selected_provider_timestamp_utc": joined["provider_timestamp_utc"],
                "join_status": joined["join_status"],
                **counts,
                "future_fill_violation": joined["future_fill_violation"],
                "stale_fill_violation": joined["stale_fill_violation"],
                "zero_fill_violation": joined["zero_fill_violation"],
            }
        )
    return joined_rows, audit_rows


def _int_or_none(value: Any) -> int | None:
    try:
        if value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_phase2_join(parse_args(argv))
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
