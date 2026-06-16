from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.config import load_live_trading_config, resolve_repo_path  # noqa: E402
from enhengclaw.live_trading.market_data import resolve_config_symbols  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase2_join import parse_decision_time  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_step1_health import iso_z, write_csv, write_json  # noqa: E402


CONTRACT_VERSION = "hv_balanced_dth60_shock_phase2b_pit_builder.v1"
DEFAULT_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/phase2b_shock_branch_builder"
)
DAY_MS = 86_400_000
SHOCK_FACTOR_ID = "shock_co_occurrence_index"
COJUMP_FACTOR_ID = "co_jump_count_3d"
OVERLAY_TRIGGER_COLUMN = "dth60_shock_branch_trigger"
OVERLAY_MULTIPLIER_COLUMN = "dth60_candidate_overlay_multiplier"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a PIT-safe Binance-derived shock branch for the hv_balanced DTH60 "
            "candidate. Writes evidence only; never changes live config or submits orders."
        )
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--input-panel", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--decision-time", default="now")
    parser.add_argument("--availability-lag-seconds", type=int, default=60)
    parser.add_argument("--freshness-seconds", type=int, default=36 * 3600)
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--min-train-timestamps", type=int, default=20)
    parser.add_argument("--min-universe-coverage", type=float, default=0.95)
    parser.add_argument("--shock-quantile", type=float, default=0.90)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def run_phase2b_shock_builder(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
    input_panel: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
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

    panel = resolve_input_panel(
        args=args,
        symbols=symbols,
        now=started_at,
        input_panel=input_panel,
    )
    raw_rows, time_series = build_shock_time_series(
        panel,
        availability_lag_seconds=int(args.availability_lag_seconds),
        min_universe_coverage=float(args.min_universe_coverage),
    )
    if requested_decision_time is None:
        decision_time = now()
        decision_time_source = "post_build_now"
    else:
        decision_time = requested_decision_time
        decision_time_source = "operator_supplied"

    marked_rows = mark_shock_rows(
        time_series,
        decision_time=decision_time,
        freshness_seconds=int(args.freshness_seconds),
    )
    selected = select_latest_eligible_row(marked_rows)
    from_input_panel = bool(
        input_panel is not None or str(getattr(args, "input_panel", "") or "").strip()
    )
    thresholds = build_train_thresholds(
        marked_rows,
        selected=selected,
        decision_time=decision_time,
        train_window_days=int(args.train_window_days),
        min_train_timestamps=int(args.min_train_timestamps),
        shock_quantile=float(args.shock_quantile),
        from_input_panel=from_input_panel,
    )
    joined_rows, audit_rows = build_joined_snapshot(
        symbols=symbols,
        selected=selected,
        thresholds=thresholds,
        decision_time=decision_time,
        freshness_seconds=int(args.freshness_seconds),
        min_train_timestamps=int(args.min_train_timestamps),
    )
    blockers: list[str] = []
    if panel.empty:
        blockers.append("shock_input_panel_empty")
    if selected is None:
        blockers.append("phase2b_shock_missing_eligible_timestamp")
    blockers.extend(str(item) for item in list(thresholds.get("blockers") or []))
    if not all(row.get("join_status") == "joined" for row in joined_rows):
        blockers.append("phase2b_shock_join_missing_symbol")

    future_blocked_count = sum(1 for row in marked_rows if row.get("pit_candidate_status") == "future_blocked")
    stale_blocked_count = sum(1 for row in marked_rows if row.get("pit_candidate_status") == "stale_blocked")
    insufficient_window_count = sum(
        1 for row in marked_rows if row.get("pit_candidate_status") == "insufficient_source_window"
    )
    no_future_fill = all(str(row.get("future_fill_violation")).lower() != "true" for row in joined_rows)
    no_stale_fill = all(str(row.get("stale_fill_violation")).lower() != "true" for row in joined_rows)
    no_zero_fill = all(str(row.get("zero_fill_violation")).lower() != "true" for row in joined_rows)
    train_future_row_count = int(thresholds.get("train_future_row_count") or 0)
    train_includes_decision_row = bool(thresholds.get("train_includes_decision_row"))
    current_row_excluded = bool(thresholds.get("current_row_excluded_from_threshold"))
    if not no_future_fill or train_future_row_count:
        blockers.append("shock_future_fill_violation")
    if not no_stale_fill:
        blockers.append("shock_stale_fill_violation")
    if not no_zero_fill:
        blockers.append("shock_zero_fill_violation")
    if train_includes_decision_row or not current_row_excluded:
        blockers.append("shock_threshold_train_window_not_pit_safe")
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"

    write_csv(output_root / "shock_subject_rows.csv", raw_rows)
    write_csv(output_root / "shock_time_series.csv", marked_rows)
    write_json(output_root / "shock_thresholds.json", thresholds)
    write_csv(output_root / "shock_joined_snapshot.csv", joined_rows)
    write_csv(output_root / "shock_join_audit.csv", audit_rows)

    summary: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "decision_time_utc": iso_z(decision_time),
        "decision_time_source": decision_time_source,
        "status": status,
        "blockers": blockers,
        "live_config_path": str(live_config.path),
        "requested_symbol_count": len(symbols),
        "input_panel_row_count": int(len(panel)),
        "shock_time_series_row_count": int(len(marked_rows)),
        "joined_symbol_count": int(sum(row.get("join_status") == "joined" for row in joined_rows)),
        "required_factor_ids": [SHOCK_FACTOR_ID, COJUMP_FACTOR_ID],
        "selected_provider_timestamp_utc": str(selected.get("provider_timestamp_utc") or "") if selected else "",
        "selected_available_at_utc": str(selected.get("available_at_utc") or "") if selected else "",
        "selected_provider_age_seconds": selected.get("provider_age_seconds") if selected else "",
        "selected_shock_co_occurrence_index": selected.get(SHOCK_FACTOR_ID) if selected else "",
        "selected_co_jump_count_3d": selected.get(COJUMP_FACTOR_ID) if selected else "",
        "shock_quantile": float(args.shock_quantile),
        "shock_co_occurrence_q90": thresholds.get("shock_co_occurrence_q90", ""),
        "shock_co_occurrence_index_q90": thresholds.get("shock_co_occurrence_index_q90", ""),
        "co_jump_count_3d_q90": thresholds.get("co_jump_count_3d_q90", ""),
        "from_input_panel": bool(from_input_panel),
        "train_window_days": int(args.train_window_days),
        "train_timestamp_count": int(thresholds.get("train_timestamp_count") or 0),
        "min_train_timestamps": int(args.min_train_timestamps),
        "shock_branch_triggered": bool(thresholds.get("shock_branch_triggered", False)),
        "future_blocked_count": int(future_blocked_count),
        "stale_blocked_count": int(stale_blocked_count),
        "insufficient_window_count": int(insufficient_window_count),
        "no_future_fill_proven": bool(no_future_fill and train_future_row_count == 0),
        "no_stale_fill_proven": bool(no_stale_fill),
        "no_zero_fill_proven": bool(no_zero_fill),
        "current_row_excluded_from_threshold": current_row_excluded,
        "train_includes_decision_row": train_includes_decision_row,
        "train_future_row_count": train_future_row_count,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "exchange_order_submission": "disabled",
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "shock_subject_rows": str(output_root / "shock_subject_rows.csv"),
            "shock_time_series": str(output_root / "shock_time_series.csv"),
            "shock_thresholds": str(output_root / "shock_thresholds.json"),
            "shock_joined_snapshot": str(output_root / "shock_joined_snapshot.csv"),
            "shock_join_audit": str(output_root / "shock_join_audit.csv"),
        },
    }
    write_json(output_root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def resolve_input_panel(
    *,
    args: argparse.Namespace,
    symbols: list[str],
    now: datetime,
    input_panel: pd.DataFrame | None,
) -> pd.DataFrame:
    if input_panel is not None:
        return input_panel.copy(deep=True)
    input_path = str(getattr(args, "input_panel", "") or "").strip()
    if input_path:
        return pd.read_csv(resolve_repo_path(input_path))
    return build_deterministic_shock_panel(symbols=symbols, now=now)


def build_deterministic_shock_panel(*, symbols: Iterable[str], now: datetime, lookback_days: int = 90) -> pd.DataFrame:
    end = datetime(now.year, now.month, now.day, tzinfo=UTC)
    start_ms = int(end.timestamp() * 1000) - (int(lookback_days) - 1) * DAY_MS
    rows: list[dict[str, Any]] = []
    symbol_list = list(symbols)
    for day in range(int(lookback_days)):
        timestamp_ms = start_ms + day * DAY_MS
        prior_training_shock = day in {34, 44, 54, 64, 74}
        current_candidate_shock = day == int(lookback_days) - 1
        for index, symbol in enumerate(symbol_list):
            base = 0.0015 * math.sin((day + 1) * (index + 2) * 0.17)
            ret = base + 0.0004 * math.cos((day + 3) * 0.11)
            if prior_training_shock and index < 2:
                ret = 0.045 + index * 0.002
            if current_candidate_shock and index < 6:
                ret = 0.070 + index * 0.001
            subject = symbol[:-4] if symbol.upper().endswith("USDT") else symbol
            rows.append(
                {
                    "timestamp_ms": int(timestamp_ms),
                    "date_utc": datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date().isoformat(),
                    "subject": subject,
                    "symbol": symbol,
                    "usdm_symbol": symbol,
                    "return_1": ret,
                }
            )
    return pd.DataFrame(rows)


def build_shock_time_series(
    panel: pd.DataFrame,
    *,
    availability_lag_seconds: int,
    min_universe_coverage: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frame = normalize_panel(panel)
    if frame.empty:
        return [], []
    frame["return_std_20_lag"] = frame.groupby("subject", sort=True)["return_1"].transform(
        lambda item: item.rolling(20).std().shift(1)
    )
    frame["vol_shock_ready"] = frame["return_1"].notna() & frame["return_std_20_lag"].notna() & frame[
        "return_std_20_lag"
    ].gt(0.0)
    frame["vol_shock_event_today"] = (
        frame["vol_shock_ready"] & frame["return_1"].abs().gt(3.0 * frame["return_std_20_lag"])
    ).astype("float64")
    frame["available_at_ms"] = resolve_row_available_at_ms(
        frame,
        availability_lag_seconds=availability_lag_seconds,
    )
    raw_rows = build_subject_rows(frame)
    grouped = (
        frame.groupby("timestamp_ms", sort=True)
        .agg(
            universe_size=("subject", "nunique"),
            valid_return_count=("return_1", lambda item: int(pd.to_numeric(item, errors="coerce").notna().sum())),
            vol_ready_count=("vol_shock_ready", "sum"),
            universe_shock_count=("vol_shock_event_today", "sum"),
            available_at_ms=("available_at_ms", "max"),
        )
        .reset_index()
        .sort_values("timestamp_ms")
    )
    grouped["coverage_ratio"] = grouped["vol_ready_count"] / grouped["universe_size"].replace(0, pd.NA)
    grouped["sidecar_value_ready"] = grouped["coverage_ratio"].ge(float(min_universe_coverage)).fillna(False)
    grouped[SHOCK_FACTOR_ID] = grouped["universe_shock_count"] / grouped["universe_size"].replace(0, pd.NA)
    grouped[SHOCK_FACTOR_ID] = pd.to_numeric(grouped[SHOCK_FACTOR_ID], errors="coerce")
    grouped[COJUMP_FACTOR_ID] = pd.to_numeric(grouped["universe_shock_count"], errors="coerce").rolling(
        3,
        min_periods=1,
    ).sum()
    rows: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        timestamp_ms = int(row["timestamp_ms"])
        available_at_ms = int(row["available_at_ms"])
        rows.append(
            {
                "provider": "binance_public_ohlcv",
                "factor_id": "shock_branch_timestamp_metrics",
                "provider_timestamp_ms": timestamp_ms,
                "provider_timestamp_utc": iso_from_ms(timestamp_ms),
                "available_at_ms": available_at_ms,
                "available_at_utc": iso_from_ms(available_at_ms),
                "universe_size": int(row["universe_size"]),
                "valid_return_count": int(row["valid_return_count"]),
                "vol_ready_count": int(row["vol_ready_count"]),
                "coverage_ratio": float(row["coverage_ratio"]) if pd.notna(row["coverage_ratio"]) else "",
                "universe_shock_count": float(row["universe_shock_count"]),
                SHOCK_FACTOR_ID: float(row[SHOCK_FACTOR_ID]) if pd.notna(row[SHOCK_FACTOR_ID]) else "",
                COJUMP_FACTOR_ID: float(row[COJUMP_FACTOR_ID]) if pd.notna(row[COJUMP_FACTOR_ID]) else "",
                "sidecar_value_ready": bool(row["sidecar_value_ready"]),
                "zero_fill_used": False,
            }
        )
    return raw_rows, rows


def normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy(deep=True)
    if frame.empty:
        return frame
    if "timestamp_ms" not in frame.columns:
        raise ValueError("shock input panel missing timestamp_ms")
    if "subject" not in frame.columns:
        if "symbol" in frame.columns:
            frame["subject"] = frame["symbol"].astype(str).str.replace("USDT", "", regex=False)
        elif "usdm_symbol" in frame.columns:
            frame["subject"] = frame["usdm_symbol"].astype(str).str.replace("USDT", "", regex=False)
        else:
            raise ValueError("shock input panel missing subject/symbol")
    if "symbol" not in frame.columns:
        frame["symbol"] = frame["subject"].astype(str).map(lambda item: item if item.upper().endswith("USDT") else f"{item}USDT")
    frame["timestamp_ms"] = pd.to_numeric(frame["timestamp_ms"], errors="coerce")
    frame = frame.dropna(subset=["timestamp_ms", "subject"]).copy()
    frame["timestamp_ms"] = frame["timestamp_ms"].astype("int64")
    frame["subject"] = frame["subject"].astype(str)
    frame["symbol"] = frame["symbol"].astype(str)
    if "return_1" not in frame.columns:
        close_column = "perp_close" if "perp_close" in frame.columns else "spot_close" if "spot_close" in frame.columns else ""
        if not close_column:
            raise ValueError("shock input panel requires return_1 or close column")
        frame[close_column] = pd.to_numeric(frame[close_column], errors="coerce")
        frame = frame.sort_values(["subject", "timestamp_ms"]).copy()
        frame["return_1"] = frame.groupby("subject", sort=True)[close_column].pct_change(fill_method=None)
    frame["return_1"] = pd.to_numeric(frame["return_1"], errors="coerce")
    return frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)


def resolve_row_available_at_ms(frame: pd.DataFrame, *, availability_lag_seconds: int) -> pd.Series:
    for column in ("available_at_ms", "observed_available_at_ms"):
        if column in frame.columns:
            parsed = pd.to_numeric(frame[column], errors="coerce")
            return parsed.fillna(frame["timestamp_ms"] + int(availability_lag_seconds) * 1000).astype("int64")
    return (frame["timestamp_ms"] + int(availability_lag_seconds) * 1000).astype("int64")


def build_subject_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        rows.append(
            {
                "symbol": str(row["symbol"]),
                "subject": str(row["subject"]),
                "provider_timestamp_ms": int(row["timestamp_ms"]),
                "provider_timestamp_utc": iso_from_ms(int(row["timestamp_ms"])),
                "available_at_ms": int(row["available_at_ms"]),
                "available_at_utc": iso_from_ms(int(row["available_at_ms"])),
                "return_1": float(row["return_1"]) if pd.notna(row["return_1"]) else "",
                "return_std_20_lag": float(row["return_std_20_lag"]) if pd.notna(row["return_std_20_lag"]) else "",
                "vol_shock_ready": bool(row["vol_shock_ready"]),
                "vol_shock_event_today": bool(row["vol_shock_event_today"]),
                "zero_fill_used": False,
            }
        )
    return rows


def mark_shock_rows(
    rows: list[dict[str, Any]],
    *,
    decision_time: datetime,
    freshness_seconds: int,
) -> list[dict[str, Any]]:
    decision_ms = int(decision_time.timestamp() * 1000)
    marked: list[dict[str, Any]] = []
    for row in rows:
        provider_ms = int(row["provider_timestamp_ms"])
        available_ms = int(row["available_at_ms"])
        provider_age = (decision_ms - provider_ms) / 1000.0
        future_blocked = provider_ms > decision_ms or available_ms > decision_ms
        stale_blocked = provider_age > int(freshness_seconds)
        value_ready = bool(row.get("sidecar_value_ready"))
        if not value_ready:
            status = "insufficient_source_window"
        elif future_blocked:
            status = "future_blocked"
        elif stale_blocked:
            status = "stale_blocked"
        else:
            status = "eligible"
        out = dict(row)
        out.update(
            {
                "decision_time_ms": decision_ms,
                "decision_time_utc": iso_z(decision_time),
                "provider_age_seconds": round(provider_age, 3),
                "future_blocked": future_blocked,
                "stale_blocked": stale_blocked,
                "pit_candidate_status": status,
            }
        )
        marked.append(out)
    return marked


def select_latest_eligible_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [row for row in rows if row.get("pit_candidate_status") == "eligible"]
    eligible.sort(key=lambda row: int(row["provider_timestamp_ms"]))
    return dict(eligible[-1]) if eligible else None


def build_train_thresholds(
    rows: list[dict[str, Any]],
    *,
    selected: dict[str, Any] | None,
    decision_time: datetime,
    train_window_days: int,
    min_train_timestamps: int,
    shock_quantile: float,
    from_input_panel: bool = False,
) -> dict[str, Any]:
    if selected is None:
        return {
            "status": "blocked",
            "blockers": ["shock_threshold_selected_row_missing"],
            "train_timestamp_count": 0,
            "from_input_panel": bool(from_input_panel),
        }
    selected_ms = int(selected["provider_timestamp_ms"])
    decision_ms = int(decision_time.timestamp() * 1000)
    lower_ms = selected_ms - int(train_window_days) * DAY_MS
    raw_train = [
        row
        for row in rows
        if bool(row.get("sidecar_value_ready"))
        and int(row["provider_timestamp_ms"]) >= lower_ms
        and int(row["provider_timestamp_ms"]) < selected_ms
        and int(row["available_at_ms"]) <= decision_ms
    ]
    train_future_row_count = sum(1 for row in raw_train if int(row["provider_timestamp_ms"]) > decision_ms)
    train = [row for row in raw_train if int(row["provider_timestamp_ms"]) <= decision_ms]
    blockers: list[str] = []
    if len(train) < int(min_train_timestamps):
        blockers.append("shock_threshold_insufficient_train_timestamps")
    q = min(max(float(shock_quantile), 0.0), 1.0)
    shock_q = quantile([row.get(SHOCK_FACTOR_ID) for row in train], q)
    cojump_q = quantile([row.get(COJUMP_FACTOR_ID) for row in train], q)
    if shock_q is None or cojump_q is None:
        blockers.append("shock_threshold_quantile_unavailable")
    shock_value = as_float(selected.get(SHOCK_FACTOR_ID))
    cojump_value = as_float(selected.get(COJUMP_FACTOR_ID))
    trigger = False
    if shock_q is not None and cojump_q is not None and shock_value is not None and cojump_value is not None:
        trigger = bool(shock_value >= shock_q or cojump_value >= cojump_q)
    max_train_ms = max((int(row["provider_timestamp_ms"]) for row in train), default=0)
    train_includes_decision_row = any(int(row["provider_timestamp_ms"]) >= selected_ms for row in train)
    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "shock_quantile": q,
        "train_window_days": int(train_window_days),
        "train_timestamp_count": int(len(train)),
        "train_start_timestamp_utc": iso_from_ms(min(int(row["provider_timestamp_ms"]) for row in train)) if train else "",
        "train_end_timestamp_utc": iso_from_ms(max_train_ms) if max_train_ms else "",
        "selected_provider_timestamp_utc": selected.get("provider_timestamp_utc"),
        "shock_co_occurrence_q90": shock_q if shock_q is not None else "",
        "co_jump_count_3d_q90": cojump_q if cojump_q is not None else "",
        "selected_shock_co_occurrence_index": shock_value if shock_value is not None else "",
        "selected_co_jump_count_3d": cojump_value if cojump_value is not None else "",
        "shock_branch_triggered": trigger,
        "current_row_excluded_from_threshold": bool(max_train_ms < selected_ms),
        "train_includes_decision_row": bool(train_includes_decision_row),
        "train_future_row_count": int(train_future_row_count),
        # Validator-facing aliases consumed by
        # frozen_frontier_overlay.validate_thresholds_pit (live overlay thresholds block).
        # Additive: the legacy keys above are still read by build_joined_snapshot/summary.
        "shock_co_occurrence_index_q90": shock_q if shock_q is not None else "",
        "current_row_excluded": bool(max_train_ms < selected_ms),
        "from_input_panel": bool(from_input_panel),
    }


def build_joined_snapshot(
    *,
    symbols: list[str],
    selected: dict[str, Any] | None,
    thresholds: dict[str, Any],
    decision_time: datetime,
    freshness_seconds: int,
    min_train_timestamps: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    joined_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    threshold_ready = str(thresholds.get("status") or "") == "ready"
    trigger = bool(thresholds.get("shock_branch_triggered", False))
    for symbol in symbols:
        if selected is None or not threshold_ready:
            row = {
                "symbol": symbol,
                "join_status": "blocked_no_eligible_shock_row" if selected is None else "blocked_no_ready_threshold",
                "decision_time_utc": iso_z(decision_time),
                "provider_timestamp_utc": "",
                "available_at_utc": "",
                SHOCK_FACTOR_ID: "",
                COJUMP_FACTOR_ID: "",
                "shock_co_occurrence_q90": "",
                "co_jump_count_3d_q90": "",
                OVERLAY_TRIGGER_COLUMN: "",
                OVERLAY_MULTIPLIER_COLUMN: "",
                "future_fill_violation": False,
                "stale_fill_violation": False,
                "zero_fill_violation": False,
                "zero_fill_used": False,
            }
        else:
            decision_ms = int(decision_time.timestamp() * 1000)
            provider_ms = int(selected["provider_timestamp_ms"])
            available_ms = int(selected["available_at_ms"])
            provider_age = (decision_ms - provider_ms) / 1000.0
            row = {
                "symbol": symbol,
                "join_status": "joined",
                "decision_time_utc": iso_z(decision_time),
                "decision_time_ms": decision_ms,
                "provider_timestamp_utc": selected["provider_timestamp_utc"],
                "provider_timestamp_ms": provider_ms,
                "available_at_utc": selected["available_at_utc"],
                "available_at_ms": available_ms,
                "provider_age_seconds": round(provider_age, 3),
                SHOCK_FACTOR_ID: selected[SHOCK_FACTOR_ID],
                COJUMP_FACTOR_ID: selected[COJUMP_FACTOR_ID],
                "shock_co_occurrence_q90": thresholds["shock_co_occurrence_q90"],
                "co_jump_count_3d_q90": thresholds["co_jump_count_3d_q90"],
                "train_timestamp_count": thresholds["train_timestamp_count"],
                "min_train_timestamps": int(min_train_timestamps),
                OVERLAY_TRIGGER_COLUMN: trigger,
                OVERLAY_MULTIPLIER_COLUMN: 0.0 if trigger else 1.0,
                "future_fill_violation": provider_ms > decision_ms or available_ms > decision_ms,
                "stale_fill_violation": provider_age > int(freshness_seconds),
                "zero_fill_violation": bool(selected.get("zero_fill_used")) or not bool(selected.get("sidecar_value_ready")),
                "zero_fill_used": bool(selected.get("zero_fill_used")),
            }
        joined_rows.append(row)
        audit_rows.append(
            {
                "symbol": symbol,
                "decision_time_utc": iso_z(decision_time),
                "join_status": row["join_status"],
                "selected_provider_timestamp_utc": row["provider_timestamp_utc"],
                "threshold_status": str(thresholds.get("status") or ""),
                "future_fill_violation": row["future_fill_violation"],
                "stale_fill_violation": row["stale_fill_violation"],
                "zero_fill_violation": row["zero_fill_violation"],
            }
        )
    return joined_rows, audit_rows


def quantile(values: Iterable[Any], q: float) -> float | None:
    numeric = [as_float(value) for value in values]
    clean = [float(value) for value in numeric if value is not None and math.isfinite(float(value))]
    if not clean:
        return None
    return float(pd.Series(clean, dtype="float64").quantile(float(q)))


def as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(int(value) / 1000.0, tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_phase2b_shock_builder(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
