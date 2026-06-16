from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.config import (  # noqa: E402
    load_frozen_strategy_config,
    load_live_trading_config,
    resolve_repo_path,
)
from enhengclaw.live_trading.market_data import resolve_config_symbols  # noqa: E402
from enhengclaw.quant_research._binance_canonical_normalization import (  # noqa: E402
    _timestamp_percentile_rank,
    _timestamp_zscore,
)
from enhengclaw.quant_research.binance_canonical_h10d import (  # noqa: E402
    BINANCE_OHLCV_CORE_WEIGHTS,
    score_binance_ohlcv_core,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_step1_health import (  # noqa: E402
    iso_z,
    write_csv,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase3_candidate_parity.v1"
DEFAULT_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/phase3_candidate_parity"
)
DEFAULT_PHASE2_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/phase2_pit_sidecar_join"
)
DEFAULT_PHASE2B_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/phase2b_shock_branch_builder"
)
TARGET_FACTOR = "distance_to_high_60"
COINGLASS_FACTOR = "coinglass_top_trader_long_pct_smooth_5"
DISTANCE_RANK_COLUMN = "distance_to_high_60_rank_pct"
COINGLASS_RANK_COLUMN = "coinglass_top_trader_long_pct_smooth_5_rank_pct"
CROWDED_TRIGGER_COLUMN = "dth60_crowded_branch_trigger"
SHOCK_TRIGGER_COLUMN = "dth60_shock_branch_trigger"
OVERLAY_MULTIPLIER_COLUMN = "dth60_candidate_overlay_multiplier"
OVERLAY_TRIGGER_COLUMN = "dth60_candidate_overlay_trigger"
SCORE_TOLERANCE = 1e-12
CONTRIBUTION_TOLERANCE = 1e-12


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a local candidate parity wrapper for the hv_balanced DTH60/CoinGlass "
            "candidate. Writes evidence only; never changes live config or submits orders."
        )
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--strategy-config", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--target-factor", default=TARGET_FACTOR)
    parser.add_argument("--overlay-multiplier-column", default=OVERLAY_MULTIPLIER_COLUMN)
    parser.add_argument("--overlay-trigger-column", default=OVERLAY_TRIGGER_COLUMN)
    parser.add_argument(
        "--phase2-summary",
        default="",
        help=(
            "Path to a retained Phase 2 PIT sidecar summary. Defaults to the latest local "
            "phase2_pit_sidecar_join summary and blocks if no proof is available."
        ),
    )
    parser.add_argument(
        "--phase2b-summary",
        default="",
        help=(
            "Path to a retained Phase 2B PIT shock-branch summary. Defaults to the latest "
            "local phase2b_shock_branch_builder summary and blocks if no proof is available."
        ),
    )
    parser.add_argument("--crowded-distance-rank-min", type=float, default=0.75)
    parser.add_argument("--crowded-coinglass-rank-min", type=float, default=0.80)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def run_phase3_parity(
    args: argparse.Namespace,
    *,
    now_fn=utc_now,
    panel: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    live_config = load_live_trading_config(args.config)
    strategy_config_path = (
        resolve_repo_path(str(args.strategy_config))
        if str(getattr(args, "strategy_config", "") or "").strip()
        else live_config.strategy_config_path
    )
    strategy_config = load_frozen_strategy_config(strategy_config_path)
    symbols = resolve_config_symbols(live_config.payload, override_symbols=str(getattr(args, "symbols", "") or ""))
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        resolve_repo_path(str(args.output_root))
        if str(getattr(args, "output_root", "") or "").strip()
        else resolve_repo_path(DEFAULT_OUTPUT_PARENT) / run_id
    )
    output_root.mkdir(parents=True, exist_ok=True)

    feature_columns = [str(item) for item in strategy_config.get("feature_columns") or []]
    feature_weights = dict(strategy_config.get("feature_weights") or BINANCE_OHLCV_CORE_WEIGHTS)
    target_factor = str(getattr(args, "target_factor", TARGET_FACTOR) or TARGET_FACTOR)
    multiplier_column = str(
        getattr(args, "overlay_multiplier_column", OVERLAY_MULTIPLIER_COLUMN) or OVERLAY_MULTIPLIER_COLUMN
    )
    trigger_column = str(getattr(args, "overlay_trigger_column", OVERLAY_TRIGGER_COLUMN) or OVERLAY_TRIGGER_COLUMN)
    blockers: list[str] = []
    phase2_summary_path = resolve_phase2_summary_path(str(getattr(args, "phase2_summary", "") or ""))
    phase2_proof, phase2_blockers = load_phase2_pit_proof(phase2_summary_path)
    blockers.extend(phase2_blockers)
    phase2b_summary_path = resolve_phase2b_summary_path(str(getattr(args, "phase2b_summary", "") or ""))
    phase2b_proof, phase2b_blockers = load_phase2b_pit_proof(phase2b_summary_path)
    blockers.extend(phase2b_blockers)

    if target_factor not in feature_columns:
        blockers.append("target_factor_not_in_strategy_features")
    if not feature_columns:
        blockers.append("strategy_feature_columns_empty")

    candidate_panel = (
        panel.copy(deep=True)
        if panel is not None
        else build_deterministic_candidate_panel(symbols=symbols, feature_columns=feature_columns)
    )
    combined_trigger_proof: dict[str, Any] = {"loaded": False, "status": "not_run", "checks": {}}
    candidate_panel, combined_trigger_proof, combined_trigger_blockers = build_combined_candidate_trigger_panel(
        candidate_panel,
        phase2_summary_path=phase2_summary_path,
        phase2b_summary_path=phase2b_summary_path,
        target_factor=target_factor,
        trigger_column=trigger_column,
        multiplier_column=multiplier_column,
        crowded_distance_rank_min=float(getattr(args, "crowded_distance_rank_min", 0.75) or 0.75),
        crowded_coinglass_rank_min=float(getattr(args, "crowded_coinglass_rank_min", 0.80) or 0.80),
    )
    blockers.extend(combined_trigger_blockers)
    candidate_panel.to_csv(output_root / "combined_candidate_trigger_panel.csv", index=False)
    missing_features = [column for column in feature_columns if column not in candidate_panel.columns]
    if missing_features:
        blockers.append(f"missing_feature_columns:{','.join(missing_features)}")
    if multiplier_column not in candidate_panel.columns:
        blockers.append("overlay_multiplier_column_missing")

    disabled_frame: pd.DataFrame
    enabled_frame: pd.DataFrame
    parity_rows: list[dict[str, Any]] = []
    contribution_deltas: list[dict[str, Any]] = []
    baseline_score_match_max_abs_diff = math.inf
    non_target_contribution_max_abs_diff = math.inf
    target_contribution_max_abs_diff = math.inf
    raw_score_max_abs_diff = math.inf
    score_max_abs_diff = math.inf
    changed_contribution_columns: list[str] = []
    changed_non_target_contribution_columns: list[str] = []
    target_changed_row_count = 0
    overlay_triggered_row_count = 0

    if not blockers:
        disabled_frame = compute_candidate_score_layer(
            candidate_panel,
            feature_columns=feature_columns,
            feature_weights=feature_weights,
            target_factor=target_factor,
            overlay_enabled=False,
            overlay_multiplier_column=multiplier_column,
        )
        enabled_frame = compute_candidate_score_layer(
            candidate_panel,
            feature_columns=feature_columns,
            feature_weights=feature_weights,
            target_factor=target_factor,
            overlay_enabled=True,
            overlay_multiplier_column=multiplier_column,
        )
        official_score = score_binance_ohlcv_core(
            candidate_panel,
            feature_columns=feature_columns,
            feature_weights=feature_weights,
            require_complete_feature_set=False,
        )
        baseline_score_match_max_abs_diff = _max_abs_diff(disabled_frame["score"], official_score)
        if baseline_score_match_max_abs_diff > SCORE_TOLERANCE:
            blockers.append("disabled_wrapper_score_mismatch")

        contribution_columns = [contribution_column_name(column) for column in feature_columns]
        target_contribution_column = contribution_column_name(target_factor)
        for column in contribution_columns:
            max_abs_diff = _max_abs_diff(disabled_frame[column], enabled_frame[column])
            if max_abs_diff > CONTRIBUTION_TOLERANCE:
                changed_contribution_columns.append(column)
                if column != target_contribution_column:
                    changed_non_target_contribution_columns.append(column)
        if changed_non_target_contribution_columns:
            blockers.append("non_target_contribution_changed")
        if target_contribution_column not in changed_contribution_columns:
            blockers.append("target_contribution_unchanged")

        non_target_contribution_max_abs_diff = max(
            (
                _max_abs_diff(disabled_frame[contribution_column_name(column)], enabled_frame[contribution_column_name(column)])
                for column in feature_columns
                if column != target_factor
            ),
            default=0.0,
        )
        target_contribution_max_abs_diff = _max_abs_diff(
            disabled_frame[target_contribution_column],
            enabled_frame[target_contribution_column],
        )
        raw_score_max_abs_diff = _max_abs_diff(disabled_frame["raw_score"], enabled_frame["raw_score"])
        score_max_abs_diff = _max_abs_diff(disabled_frame["score"], enabled_frame["score"])
        target_changed_row_count = int(
            (disabled_frame[target_contribution_column] - enabled_frame[target_contribution_column])
            .abs()
            .gt(CONTRIBUTION_TOLERANCE)
            .sum()
        )
        overlay_triggered_row_count = int(
            pd.to_numeric(candidate_panel[multiplier_column], errors="coerce").fillna(1.0).ne(1.0).sum()
        )
        if target_changed_row_count <= 0:
            blockers.append("no_overlay_effect_rows")

        parity_rows = build_parity_rows(
            candidate_panel=candidate_panel,
            disabled_frame=disabled_frame,
            enabled_frame=enabled_frame,
            official_score=official_score,
            feature_columns=feature_columns,
            trigger_column=trigger_column,
            multiplier_column=multiplier_column,
        )
        contribution_deltas = build_contribution_delta_rows(
            disabled_frame=disabled_frame,
            enabled_frame=enabled_frame,
            feature_columns=feature_columns,
            target_factor=target_factor,
        )
        write_csv(output_root / "candidate_parity_rows.csv", parity_rows)
        write_csv(output_root / "contribution_deltas.csv", contribution_deltas)
        write_csv(
            output_root / "disabled_feature_contributions.csv",
            build_contribution_export_rows(disabled_frame, feature_columns=feature_columns, mode="disabled"),
        )
        write_csv(
            output_root / "enabled_feature_contributions.csv",
            build_contribution_export_rows(enabled_frame, feature_columns=feature_columns, mode="enabled"),
        )
    else:
        write_csv(output_root / "candidate_parity_rows.csv", [])
        write_csv(output_root / "contribution_deltas.csv", [])
        write_csv(output_root / "disabled_feature_contributions.csv", [])
        write_csv(output_root / "enabled_feature_contributions.csv", [])

    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"
    summary: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "live_config_path": str(live_config.path),
        "strategy_config_path": str(strategy_config_path),
        "requested_symbol_count": len(symbols),
        "panel_row_count": int(len(candidate_panel)),
        "feature_columns": feature_columns,
        "feature_weights": {column: float(feature_weights.get(column, 0.0)) for column in feature_columns},
        "normalized_feature_weights": normalize_feature_weights(feature_columns, feature_weights),
        "target_factor": target_factor,
        "overlay_multiplier_column": multiplier_column,
        "overlay_trigger_column": trigger_column,
        "phase2_summary_path": str(phase2_summary_path) if phase2_summary_path is not None else "",
        "phase2_pit_proof_loaded": bool(phase2_proof.get("loaded")),
        "phase2_pit_proof_status": str(phase2_proof.get("status") or ""),
        "phase2_pit_proof_checks": dict(phase2_proof.get("checks") or {}),
        "phase2b_summary_path": str(phase2b_summary_path) if phase2b_summary_path is not None else "",
        "phase2b_pit_proof_loaded": bool(phase2b_proof.get("loaded")),
        "phase2b_pit_proof_status": str(phase2b_proof.get("status") or ""),
        "phase2b_pit_proof_checks": dict(phase2b_proof.get("checks") or {}),
        "combined_trigger_contract": "dth60_combined_shock_or_crowded.v1",
        "combined_trigger_formula": (
            "dth60_shock_branch_trigger OR "
            "(distance_to_high_60_rank_pct >= crowded_distance_rank_min AND "
            "coinglass_top_trader_long_pct_smooth_5_rank_pct >= crowded_coinglass_rank_min)"
        ),
        "combined_candidate_trigger_proven": bool(combined_trigger_proof.get("proven")),
        "combined_candidate_trigger_proof": combined_trigger_proof,
        "overlay_triggered_row_count": overlay_triggered_row_count,
        "disabled_wrapper_score_matches_core": baseline_score_match_max_abs_diff <= SCORE_TOLERANCE,
        "disabled_wrapper_score_max_abs_diff_vs_core": _finite_or_none(baseline_score_match_max_abs_diff),
        "overlay_enabled_only_target_contribution_changed": (
            changed_contribution_columns == [contribution_column_name(target_factor)]
        ),
        "changed_contribution_columns": changed_contribution_columns,
        "changed_non_target_contribution_columns": changed_non_target_contribution_columns,
        "non_target_contribution_max_abs_diff_enabled_vs_disabled": _finite_or_none(
            non_target_contribution_max_abs_diff
        ),
        "target_contribution_max_abs_diff_enabled_vs_disabled": _finite_or_none(target_contribution_max_abs_diff),
        "target_contribution_changed_row_count": target_changed_row_count,
        "raw_score_max_abs_diff_enabled_vs_disabled": _finite_or_none(raw_score_max_abs_diff),
        "score_max_abs_diff_enabled_vs_disabled": _finite_or_none(score_max_abs_diff),
        "score_change_allowed_reason": (
            "Final hv_balanced score is a timestamp percentile rank/tanh of raw_score; "
            "Phase 3 proves factor-contribution parity, not final-score immutability under enabled overlay."
        ),
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "exchange_order_submission": "disabled",
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "combined_candidate_trigger_panel": str(output_root / "combined_candidate_trigger_panel.csv"),
            "candidate_parity_rows": str(output_root / "candidate_parity_rows.csv"),
            "contribution_deltas": str(output_root / "contribution_deltas.csv"),
            "disabled_feature_contributions": str(output_root / "disabled_feature_contributions.csv"),
            "enabled_feature_contributions": str(output_root / "enabled_feature_contributions.csv"),
        },
    }
    write_json(output_root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_deterministic_candidate_panel(*, symbols: Iterable[str], feature_columns: Iterable[str]) -> pd.DataFrame:
    timestamp_ms = int(datetime(2026, 6, 6, 0, 0, tzinfo=UTC).timestamp() * 1000)
    rows: list[dict[str, Any]] = []
    feature_list = [str(item) for item in feature_columns]
    for index, symbol in enumerate(symbols):
        row: dict[str, Any] = {
            "timestamp_ms": timestamp_ms,
            "subject": str(symbol),
            "perp_close": 100.0 + index,
            "perp_quote_volume_usd": 10_000_000.0 + index * 250_000.0,
            OVERLAY_TRIGGER_COLUMN: index % 4 == 0,
            OVERLAY_MULTIPLIER_COLUMN: 0.0 if index % 4 == 0 else 1.0,
        }
        for feature_index, column in enumerate(feature_list):
            row[column] = deterministic_feature_value(index=index, feature_index=feature_index, column=column)
        rows.append(row)
    return pd.DataFrame(rows)


def deterministic_feature_value(*, index: int, feature_index: int, column: str) -> float:
    if column == TARGET_FACTOR:
        return -0.35 + index * 0.047
    base = (feature_index + 1) * 0.19
    wave = math.sin((index + 1) * (feature_index + 2) * 0.37) * 0.05
    return base + index * (0.021 + feature_index * 0.006) + wave


def resolve_phase2_summary_path(path_ref: str) -> Path | None:
    if str(path_ref or "").strip():
        return resolve_repo_path(path_ref)
    parent = resolve_repo_path(DEFAULT_PHASE2_PARENT)
    if not parent.exists():
        return None
    summaries = sorted(parent.glob("*/summary.json"), reverse=True)
    return summaries[0] if summaries else None


def load_phase2_pit_proof(summary_path: Path | None) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    if summary_path is None:
        return {"loaded": False, "status": "missing", "checks": {}}, ["phase2_pit_proof_missing"]
    if not summary_path.exists():
        return {"loaded": False, "status": "missing", "checks": {}}, ["phase2_pit_proof_missing"]
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "loaded": False,
            "status": "unreadable",
            "checks": {"error": f"{exc.__class__.__name__}:{exc}"},
        }, ["phase2_pit_proof_unreadable"]

    requested_symbol_count = int(summary.get("requested_symbol_count") or 0)
    joined_symbol_count = int(summary.get("joined_symbol_count") or 0)
    checks = {
        "status_ready": summary.get("status") == "ready",
        "no_future_fill_proven": bool(summary.get("no_future_fill_proven")),
        "no_stale_fill_proven": bool(summary.get("no_stale_fill_proven")),
        "no_zero_fill_proven": bool(summary.get("no_zero_fill_proven")),
        "all_requested_symbols_joined": requested_symbol_count > 0 and joined_symbol_count == requested_symbol_count,
    }
    if not checks["status_ready"]:
        blockers.append("phase2_pit_proof_not_ready")
    if not checks["no_future_fill_proven"]:
        blockers.append("phase2_future_fill_proof_missing")
    if not checks["no_stale_fill_proven"]:
        blockers.append("phase2_stale_fill_proof_missing")
    if not checks["no_zero_fill_proven"]:
        blockers.append("phase2_zero_fill_proof_missing")
    if not checks["all_requested_symbols_joined"]:
        blockers.append("phase2_joined_symbol_proof_missing")
    return {
        "loaded": True,
        "status": str(summary.get("status") or ""),
        "checks": checks,
        "run_id": str(summary.get("run_id") or ""),
        "path": str(summary_path),
    }, blockers


def resolve_phase2b_summary_path(path_ref: str) -> Path | None:
    if str(path_ref or "").strip():
        return resolve_repo_path(path_ref)
    parent = resolve_repo_path(DEFAULT_PHASE2B_PARENT)
    if not parent.exists():
        return None
    summaries = sorted(parent.glob("*/summary.json"), reverse=True)
    return summaries[0] if summaries else None


def load_phase2b_pit_proof(summary_path: Path | None) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    if summary_path is None:
        return {"loaded": False, "status": "missing", "checks": {}}, ["phase2b_pit_proof_missing"]
    if not summary_path.exists():
        return {"loaded": False, "status": "missing", "checks": {}}, ["phase2b_pit_proof_missing"]
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "loaded": False,
            "status": "unreadable",
            "checks": {"error": f"{exc.__class__.__name__}:{exc}"},
        }, ["phase2b_pit_proof_unreadable"]

    requested_symbol_count = int(summary.get("requested_symbol_count") or 0)
    joined_symbol_count = int(summary.get("joined_symbol_count") or 0)
    checks = {
        "status_ready": summary.get("status") == "ready",
        "no_future_fill_proven": bool(summary.get("no_future_fill_proven")),
        "no_stale_fill_proven": bool(summary.get("no_stale_fill_proven")),
        "no_zero_fill_proven": bool(summary.get("no_zero_fill_proven")),
        "all_requested_symbols_joined": requested_symbol_count > 0 and joined_symbol_count == requested_symbol_count,
        "current_row_excluded_from_threshold": bool(summary.get("current_row_excluded_from_threshold")),
        "train_excludes_decision_row": not bool(summary.get("train_includes_decision_row")),
        "train_future_row_count_zero": int(summary.get("train_future_row_count") or 0) == 0,
    }
    if not checks["status_ready"]:
        blockers.append("phase2b_pit_proof_not_ready")
    if not checks["no_future_fill_proven"]:
        blockers.append("phase2b_future_fill_proof_missing")
    if not checks["no_stale_fill_proven"]:
        blockers.append("phase2b_stale_fill_proof_missing")
    if not checks["no_zero_fill_proven"]:
        blockers.append("phase2b_zero_fill_proof_missing")
    if not checks["all_requested_symbols_joined"]:
        blockers.append("phase2b_joined_symbol_proof_missing")
    if not checks["current_row_excluded_from_threshold"]:
        blockers.append("phase2b_current_row_exclusion_proof_missing")
    if not checks["train_excludes_decision_row"]:
        blockers.append("phase2b_train_includes_decision_row")
    if not checks["train_future_row_count_zero"]:
        blockers.append("phase2b_train_future_rows_present")
    return {
        "loaded": True,
        "status": str(summary.get("status") or ""),
        "checks": checks,
        "run_id": str(summary.get("run_id") or ""),
        "path": str(summary_path),
    }, blockers


def build_combined_candidate_trigger_panel(
    frame: pd.DataFrame,
    *,
    phase2_summary_path: Path | None,
    phase2b_summary_path: Path | None,
    target_factor: str,
    trigger_column: str,
    multiplier_column: str,
    crowded_distance_rank_min: float,
    crowded_coinglass_rank_min: float,
) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    output = frame.copy(deep=True)
    blockers: list[str] = []
    proof: dict[str, Any] = {
        "loaded": False,
        "status": "blocked",
        "proven": False,
        "checks": {},
        "crowded_distance_rank_min": float(crowded_distance_rank_min),
        "crowded_coinglass_rank_min": float(crowded_coinglass_rank_min),
    }
    if target_factor not in output.columns:
        blockers.append("combined_trigger_target_factor_missing")
        return output, proof, blockers
    if "timestamp_ms" not in output.columns:
        blockers.append("combined_trigger_timestamp_missing")
        return output, proof, blockers

    output["usdm_symbol"] = panel_symbol_series(output)
    phase2_summary, phase2_summary_blockers = read_summary_json(phase2_summary_path, missing_label="phase2_pit_proof_missing")
    phase2b_summary, phase2b_summary_blockers = read_summary_json(
        phase2b_summary_path,
        missing_label="phase2b_pit_proof_missing",
    )
    blockers.extend(phase2_summary_blockers)
    blockers.extend(phase2b_summary_blockers)
    coinglass_snapshot_path = summary_artifact_path(
        phase2_summary,
        ("artifacts", "joined_snapshot_csv"),
        ("output_files", "pit_joined_snapshot"),
        ("output_files", "joined_snapshot"),
    )
    shock_snapshot_path = summary_artifact_path(
        phase2b_summary,
        ("output_files", "shock_joined_snapshot"),
        ("artifacts", "shock_joined_snapshot_csv"),
    )
    coinglass_rows, coinglass_blockers = read_joined_snapshot(
        coinglass_snapshot_path,
        factor_columns=[COINGLASS_FACTOR, "provider_timestamp_ms"],
        blocker_prefix="phase2_coinglass",
    )
    shock_rows, shock_blockers = read_joined_snapshot(
        shock_snapshot_path,
        factor_columns=[SHOCK_TRIGGER_COLUMN, "provider_timestamp_ms"],
        blocker_prefix="phase2b_shock",
    )
    blockers.extend(coinglass_blockers)
    blockers.extend(shock_blockers)

    coinglass_map = rows_by_symbol(coinglass_rows)
    shock_map = rows_by_symbol(shock_rows)
    required_symbols = sorted(set(str(value) for value in output["usdm_symbol"].dropna().astype(str)))
    missing_coinglass = [symbol for symbol in required_symbols if symbol not in coinglass_map]
    missing_shock = [symbol for symbol in required_symbols if symbol not in shock_map]
    if missing_coinglass:
        blockers.append(f"combined_trigger_missing_coinglass_symbols:{','.join(missing_coinglass)}")
    if missing_shock:
        blockers.append(f"combined_trigger_missing_shock_symbols:{','.join(missing_shock)}")

    output[COINGLASS_FACTOR] = output["usdm_symbol"].map(
        {symbol: parse_float(row.get(COINGLASS_FACTOR)) for symbol, row in coinglass_map.items()}
    )
    output["coinglass_provider_timestamp_ms"] = output["usdm_symbol"].map(
        {symbol: parse_int(row.get("provider_timestamp_ms")) for symbol, row in coinglass_map.items()}
    )
    output[SHOCK_TRIGGER_COLUMN] = output["usdm_symbol"].map(
        {symbol: parse_bool(row.get(SHOCK_TRIGGER_COLUMN)) for symbol, row in shock_map.items()}
    ).fillna(False)
    output["shock_provider_timestamp_ms"] = output["usdm_symbol"].map(
        {symbol: parse_int(row.get("provider_timestamp_ms")) for symbol, row in shock_map.items()}
    )
    if "shock_co_occurrence_index" in shock_rows.columns:
        output["shock_co_occurrence_index"] = output["usdm_symbol"].map(
            {symbol: parse_float(row.get("shock_co_occurrence_index")) for symbol, row in shock_map.items()}
        )
    if "co_jump_count_3d" in shock_rows.columns:
        output["co_jump_count_3d"] = output["usdm_symbol"].map(
            {symbol: parse_float(row.get("co_jump_count_3d")) for symbol, row in shock_map.items()}
        )

    output[DISTANCE_RANK_COLUMN] = rank_pct_by_timestamp(output[target_factor], output["timestamp_ms"])
    output[COINGLASS_RANK_COLUMN] = rank_pct_by_timestamp(output[COINGLASS_FACTOR], output["timestamp_ms"])
    coinglass_timestamp_match = pd.to_numeric(output["timestamp_ms"], errors="coerce").eq(
        pd.to_numeric(output["coinglass_provider_timestamp_ms"], errors="coerce")
    )
    shock_timestamp_match = pd.to_numeric(output["timestamp_ms"], errors="coerce").eq(
        pd.to_numeric(output["shock_provider_timestamp_ms"], errors="coerce")
    )
    crowded_trigger = (
        coinglass_timestamp_match
        & pd.to_numeric(output[DISTANCE_RANK_COLUMN], errors="coerce").ge(float(crowded_distance_rank_min))
        & pd.to_numeric(output[COINGLASS_RANK_COLUMN], errors="coerce").ge(float(crowded_coinglass_rank_min))
    )
    shock_trigger = shock_timestamp_match & output[SHOCK_TRIGGER_COLUMN].astype(bool)
    output[CROWDED_TRIGGER_COLUMN] = crowded_trigger.astype(bool)
    output[SHOCK_TRIGGER_COLUMN] = shock_trigger.astype(bool)
    output[trigger_column] = (output[CROWDED_TRIGGER_COLUMN] | output[SHOCK_TRIGGER_COLUMN]).astype(bool)
    output[multiplier_column] = output[trigger_column].map({True: 0.0, False: 1.0}).astype("float64")
    output["dth60_combined_trigger_source"] = [
        combined_trigger_source(shock=bool(shock), crowded=bool(crowded))
        for shock, crowded in zip(output[SHOCK_TRIGGER_COLUMN], output[CROWDED_TRIGGER_COLUMN], strict=False)
    ]

    missing_trigger_values = int(pd.to_numeric(output[multiplier_column], errors="coerce").isna().sum())
    if missing_trigger_values:
        blockers.append("combined_trigger_multiplier_missing")
    combined_count = int(output[trigger_column].sum())
    proof.update(
        {
            "loaded": not blockers,
            "status": "ready" if not blockers else "blocked",
            "proven": not blockers and combined_count > 0,
            "coinglass_joined_snapshot_path": str(coinglass_snapshot_path) if coinglass_snapshot_path is not None else "",
            "shock_joined_snapshot_path": str(shock_snapshot_path) if shock_snapshot_path is not None else "",
            "row_count": int(len(output)),
            "symbol_count": int(len(required_symbols)),
            "missing_coinglass_symbol_count": int(len(missing_coinglass)),
            "missing_shock_symbol_count": int(len(missing_shock)),
            "shock_triggered_row_count": int(output[SHOCK_TRIGGER_COLUMN].sum()),
            "crowded_triggered_row_count": int(output[CROWDED_TRIGGER_COLUMN].sum()),
            "combined_overlay_triggered_row_count": combined_count,
            "combined_overlay_identity_row_count": int(len(output) - combined_count),
            "checks": {
                "all_symbols_have_coinglass_join": not missing_coinglass,
                "all_symbols_have_shock_join": not missing_shock,
                "no_missing_multiplier": missing_trigger_values == 0,
                "combined_trigger_has_effect": combined_count > 0,
            },
        }
    )
    if combined_count <= 0:
        blockers.append("combined_trigger_has_no_effect_rows")
        proof["status"] = "blocked"
        proof["proven"] = False
        proof["checks"]["combined_trigger_has_effect"] = False
    return output, proof, blockers


def read_summary_json(summary_path: Path | None, *, missing_label: str) -> tuple[dict[str, Any], list[str]]:
    if summary_path is None or not summary_path.exists():
        return {}, [missing_label]
    try:
        return json.loads(summary_path.read_text(encoding="utf-8")), []
    except (json.JSONDecodeError, OSError) as exc:
        return {}, [f"{missing_label}_unreadable:{exc.__class__.__name__}"]


def summary_artifact_path(summary: dict[str, Any], *candidates: tuple[str, str]) -> Path | None:
    for section_name, key in candidates:
        section = summary.get(section_name)
        if isinstance(section, dict):
            value = str(section.get(key) or "").strip()
            if value:
                return resolve_repo_path(value)
    return None


def read_joined_snapshot(
    path: Path | None,
    *,
    factor_columns: list[str],
    blocker_prefix: str,
) -> tuple[pd.DataFrame, list[str]]:
    if path is None:
        return pd.DataFrame(), [f"{blocker_prefix}_joined_snapshot_missing"]
    if not path.exists():
        return pd.DataFrame(), [f"{blocker_prefix}_joined_snapshot_missing"]
    try:
        frame = pd.read_csv(path)
    except OSError as exc:
        return pd.DataFrame(), [f"{blocker_prefix}_joined_snapshot_unreadable:{exc.__class__.__name__}"]
    required = ["symbol", "join_status", *factor_columns]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        return frame, [f"{blocker_prefix}_joined_snapshot_missing_columns:{','.join(missing)}"]
    joined = frame.loc[frame["join_status"].astype(str).str.lower().eq("joined")].copy()
    if joined.empty:
        return joined, [f"{blocker_prefix}_joined_snapshot_has_no_joined_rows"]
    duplicate_symbols = joined["symbol"].astype(str).str.upper().duplicated().sum()
    if duplicate_symbols:
        return joined, [f"{blocker_prefix}_joined_snapshot_duplicate_symbols"]
    return joined, []


def rows_by_symbol(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if frame.empty or "symbol" not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict(orient="records"):
        rows[normalize_usdm_symbol(row.get("symbol"))] = row
    return rows


def panel_symbol_series(frame: pd.DataFrame) -> pd.Series:
    if "usdm_symbol" in frame.columns:
        source = frame["usdm_symbol"]
    elif "symbol" in frame.columns:
        source = frame["symbol"]
    elif "subject" in frame.columns:
        source = frame["subject"]
    else:
        return pd.Series("", index=frame.index, dtype="object")
    return source.map(normalize_usdm_symbol).astype("object")


def normalize_usdm_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        return ""
    if symbol.endswith("USDT"):
        return symbol
    return f"{symbol}USDT"


def rank_pct_by_timestamp(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.groupby(timestamps).rank(method="average", pct=True)


def parse_float(value: Any) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else math.nan


def parse_int(value: Any) -> int | float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return int(numeric) if pd.notna(numeric) else math.nan


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def combined_trigger_source(*, shock: bool, crowded: bool) -> str:
    if shock and crowded:
        return "shock+crowded"
    if shock:
        return "shock"
    if crowded:
        return "crowded"
    return ""


def compute_candidate_score_layer(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str],
    feature_weights: dict[str, float] | None,
    target_factor: str = TARGET_FACTOR,
    overlay_enabled: bool,
    overlay_multiplier_column: str = OVERLAY_MULTIPLIER_COLUMN,
) -> pd.DataFrame:
    features = [str(item) for item in feature_columns]
    missing = [column for column in features if column not in frame.columns]
    if missing:
        raise ValueError(f"missing Binance-canonical feature columns: {missing}")
    if target_factor not in features:
        raise ValueError(f"target factor is not in feature columns: {target_factor}")
    if overlay_enabled and overlay_multiplier_column not in frame.columns:
        raise ValueError(f"missing overlay multiplier column: {overlay_multiplier_column}")
    if "timestamp_ms" not in frame.columns:
        raise ValueError("missing timestamp_ms column")

    output = frame.copy(deep=True)
    timestamps = output["timestamp_ms"]
    weights = dict(feature_weights or BINANCE_OHLCV_CORE_WEIGHTS)
    normalized_weights = normalize_feature_weights(features, weights)
    overlay_multiplier = _overlay_multiplier(output, overlay_enabled, overlay_multiplier_column)
    raw_score = pd.Series(0.0, index=output.index, dtype="float64")
    for column in features:
        zscore = _timestamp_zscore(pd.to_numeric(output[column], errors="coerce"), timestamps)
        contribution = zscore * float(normalized_weights[column])
        if overlay_enabled and column == target_factor:
            contribution = contribution * overlay_multiplier
        contribution_name = contribution_column_name(column)
        output[contribution_name] = contribution.astype("float64")
        raw_score = raw_score + output[contribution_name]
    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    output["raw_score"] = raw_score.astype("float64")
    output["score"] = pd.Series(np.tanh(centered_rank * 1.80), index=output.index, dtype="float64")
    return output


def normalize_feature_weights(feature_columns: Iterable[str], feature_weights: dict[str, float] | None) -> dict[str, float]:
    features = [str(item) for item in feature_columns]
    weights = dict(feature_weights or BINANCE_OHLCV_CORE_WEIGHTS)
    abs_sum = sum(abs(float(weights.get(column, 0.0))) for column in features)
    return {
        column: (float(weights.get(column, 0.0)) / abs_sum if abs_sum > 0.0 else 0.0)
        for column in features
    }


def contribution_column_name(feature_column: str) -> str:
    return f"contribution_{feature_column}"


def build_parity_rows(
    *,
    candidate_panel: pd.DataFrame,
    disabled_frame: pd.DataFrame,
    enabled_frame: pd.DataFrame,
    official_score: pd.Series,
    feature_columns: Iterable[str],
    trigger_column: str,
    multiplier_column: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    features = [str(item) for item in feature_columns]
    for index in candidate_panel.index:
        row: dict[str, Any] = {
            "timestamp_ms": int(candidate_panel.at[index, "timestamp_ms"]),
            "subject": str(candidate_panel.at[index, "subject"]),
            "overlay_trigger": bool(candidate_panel.at[index, trigger_column]) if trigger_column in candidate_panel else "",
            "overlay_multiplier": float(candidate_panel.at[index, multiplier_column]),
            "core_score": float(official_score.at[index]),
            "disabled_wrapper_score": float(disabled_frame.at[index, "score"]),
            "enabled_wrapper_score": float(enabled_frame.at[index, "score"]),
            "disabled_core_score_abs_diff": abs(float(disabled_frame.at[index, "score"]) - float(official_score.at[index])),
            "raw_score_disabled": float(disabled_frame.at[index, "raw_score"]),
            "raw_score_enabled": float(enabled_frame.at[index, "raw_score"]),
            "raw_score_delta": float(enabled_frame.at[index, "raw_score"] - disabled_frame.at[index, "raw_score"]),
            "score_delta": float(enabled_frame.at[index, "score"] - disabled_frame.at[index, "score"]),
        }
        for column in features:
            contribution_name = contribution_column_name(column)
            row[f"{contribution_name}_disabled"] = float(disabled_frame.at[index, contribution_name])
            row[f"{contribution_name}_enabled"] = float(enabled_frame.at[index, contribution_name])
            row[f"{contribution_name}_delta"] = float(
                enabled_frame.at[index, contribution_name] - disabled_frame.at[index, contribution_name]
            )
        rows.append(row)
    return rows


def build_contribution_delta_rows(
    *,
    disabled_frame: pd.DataFrame,
    enabled_frame: pd.DataFrame,
    feature_columns: Iterable[str],
    target_factor: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in feature_columns:
        contribution_name = contribution_column_name(str(column))
        max_abs_diff = _max_abs_diff(disabled_frame[contribution_name], enabled_frame[contribution_name])
        rows.append(
            {
                "feature_column": str(column),
                "contribution_column": contribution_name,
                "is_target_factor": str(column) == target_factor,
                "max_abs_delta_enabled_vs_disabled": max_abs_diff,
                "changed_row_count": int(
                    (enabled_frame[contribution_name] - disabled_frame[contribution_name])
                    .abs()
                    .gt(CONTRIBUTION_TOLERANCE)
                    .sum()
                ),
            }
        )
    return rows


def build_contribution_export_rows(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str],
    mode: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in frame.index:
        row: dict[str, Any] = {
            "mode": mode,
            "timestamp_ms": int(frame.at[index, "timestamp_ms"]),
            "subject": str(frame.at[index, "subject"]),
            "raw_score": float(frame.at[index, "raw_score"]),
            "score": float(frame.at[index, "score"]),
        }
        for column in feature_columns:
            contribution_name = contribution_column_name(str(column))
            row[contribution_name] = float(frame.at[index, contribution_name])
        rows.append(row)
    return rows


def _overlay_multiplier(frame: pd.DataFrame, overlay_enabled: bool, column: str) -> pd.Series:
    if not overlay_enabled:
        return pd.Series(1.0, index=frame.index, dtype="float64")
    multiplier = pd.to_numeric(frame[column], errors="coerce")
    if multiplier.isna().any():
        raise ValueError(f"overlay multiplier contains non-numeric values: {column}")
    if ((multiplier < 0.0) | (multiplier > 1.0)).any():
        raise ValueError(f"overlay multiplier must be in [0, 1]: {column}")
    return multiplier.astype("float64")


def _max_abs_diff(left: pd.Series, right: pd.Series) -> float:
    if len(left) != len(right):
        return math.inf
    diff = (pd.to_numeric(left, errors="coerce") - pd.to_numeric(right, errors="coerce")).abs()
    if diff.empty:
        return 0.0
    value = float(diff.max())
    return value if math.isfinite(value) else math.inf


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_phase3_parity(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
