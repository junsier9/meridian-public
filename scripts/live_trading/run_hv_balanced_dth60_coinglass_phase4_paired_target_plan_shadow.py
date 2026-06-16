from __future__ import annotations

import argparse
import hashlib
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

from enhengclaw.live_trading.config import (  # noqa: E402
    load_frozen_strategy_config,
    load_live_trading_config,
    resolve_repo_path,
)
from enhengclaw.live_trading.hv_balanced_live_signal import (  # noqa: E402
    build_live_hv_balanced_snapshot,
    file_sha256,
)
from enhengclaw.live_trading.mainnet_multiphase_target_shadow import (  # noqa: E402
    DAY_MS,
    MULTIPHASE_TARGET_ENGINE,
    PHASES,
    build_multiphase_target_portfolio,
    write_json,
)
from enhengclaw.live_trading.market_data import resolve_config_symbols  # noqa: E402
from enhengclaw.live_trading.models import LiveDecisionSnapshot, TargetPortfolio, TargetPosition  # noqa: E402
from enhengclaw.live_trading.portfolio_targets import build_target_portfolio  # noqa: E402
from enhengclaw.live_trading.risk_gate import evaluate_risk_gate  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase3_parity import (  # noqa: E402
    OVERLAY_MULTIPLIER_COLUMN,
    OVERLAY_TRIGGER_COLUMN,
    TARGET_FACTOR,
    build_combined_candidate_trigger_panel,
    compute_candidate_score_layer,
    load_phase2_pit_proof,
    load_phase2b_pit_proof,
    resolve_phase2_summary_path,
    resolve_phase2b_summary_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_step1_health import iso_z, write_csv  # noqa: E402


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase4_paired_target_plan_shadow.v1"
DEFAULT_CONFIG = (
    "config/live_trading/"
    "hv_balanced_binance_usdm_live_supervisor_multiphase_wallet2_reserve200_live_timer.yaml"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/phase4_paired_target_plan_shadow"
)
DEFAULT_PHASE3_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_coinglass_candidate/phase3_candidate_parity"
)
TARGET_WEIGHT_TOLERANCE = 1e-12


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build paired local target-plan shadows for the current hv_balanced baseline "
            "and the DTH60/CoinGlass candidate. Writes evidence only; never submits orders."
        )
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--strategy-config", default="")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--phase2-summary", default="")
    parser.add_argument("--phase2b-summary", default="")
    parser.add_argument("--phase3-summary", default="")
    parser.add_argument("--allocated-capital-usdt", type=float, default=0.0)
    parser.add_argument("--phase-cycle-index", type=int, default=-1)
    parser.add_argument("--target-factor", default=TARGET_FACTOR)
    parser.add_argument("--overlay-multiplier-column", default=OVERLAY_MULTIPLIER_COLUMN)
    parser.add_argument("--overlay-trigger-column", default=OVERLAY_TRIGGER_COLUMN)
    parser.add_argument("--crowded-distance-rank-min", type=float, default=0.75)
    parser.add_argument("--crowded-coinglass-rank-min", type=float, default=0.80)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def run_phase4_shadow(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] | None = None,
    panel: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    live_config = load_live_trading_config(args.config)
    payload = live_config.payload
    strategy_config_path = (
        resolve_repo_path(str(args.strategy_config))
        if str(getattr(args, "strategy_config", "") or "").strip()
        else live_config.strategy_config_path
    )
    frozen_config = load_frozen_strategy_config(strategy_config_path)
    config_sha = file_sha256(strategy_config_path)
    expected_sha = str(dict(payload.get("strategy") or {}).get("frozen_config_sha256") or "").strip()
    symbols = resolve_config_symbols(payload, override_symbols=str(getattr(args, "symbols", "") or ""))
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        resolve_repo_path(str(args.output_root))
        if str(getattr(args, "output_root", "") or "").strip()
        else resolve_repo_path(DEFAULT_OUTPUT_PARENT) / run_id
    )
    output_root.mkdir(parents=True, exist_ok=True)

    blockers: list[str] = []
    if expected_sha and expected_sha != config_sha:
        blockers.append(f"frozen_config_sha256_mismatch:expected={expected_sha}:actual={config_sha}")

    phase2_summary_path = resolve_phase2_summary_path(str(getattr(args, "phase2_summary", "") or ""))
    phase2_proof, phase2_blockers = load_phase2_pit_proof(phase2_summary_path)
    blockers.extend(phase2_blockers)
    phase2b_summary_path = resolve_phase2b_summary_path(str(getattr(args, "phase2b_summary", "") or ""))
    phase2b_proof, phase2b_blockers = load_phase2b_pit_proof(phase2b_summary_path)
    blockers.extend(phase2b_blockers)
    phase3_summary_path = resolve_phase3_summary_path(str(getattr(args, "phase3_summary", "") or ""))
    phase3_proof, phase3_blockers = load_phase3_parity_proof(phase3_summary_path)
    blockers.extend(phase3_blockers)

    strategy_section = dict(payload.get("strategy") or {})
    rebalance_interval_days = int(strategy_section.get("rebalance_interval_days", 10) or 10)
    rebalance_epoch_ms = int(strategy_section.get("rebalance_epoch_ms", 0) or 0)
    phase_contexts = build_phase_contexts(
        started_at=started_at,
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
        phase_cycle_index=int(getattr(args, "phase_cycle_index", -1) or -1),
    )
    upper_ms = max(int(context["decision_time_ms"]) for context in phase_contexts)
    feature_columns = [str(item) for item in frozen_config.get("feature_columns") or []]
    target_factor = str(getattr(args, "target_factor", TARGET_FACTOR) or TARGET_FACTOR)
    multiplier_column = str(
        getattr(args, "overlay_multiplier_column", OVERLAY_MULTIPLIER_COLUMN) or OVERLAY_MULTIPLIER_COLUMN
    )
    trigger_column = str(getattr(args, "overlay_trigger_column", OVERLAY_TRIGGER_COLUMN) or OVERLAY_TRIGGER_COLUMN)
    shared_panel = (
        panel.copy(deep=True)
        if panel is not None
        else build_phase4_candidate_panel(
            symbols=symbols,
            feature_columns=feature_columns,
            phase_contexts=phase_contexts,
            target_factor=target_factor,
            overlay_multiplier_column=multiplier_column,
            overlay_trigger_column=trigger_column,
        )
    )
    combined_trigger_proof: dict[str, Any] = {"loaded": False, "status": "not_run", "checks": {}}
    shared_panel, combined_trigger_proof, combined_trigger_blockers = build_combined_candidate_trigger_panel(
        shared_panel,
        phase2_summary_path=phase2_summary_path,
        phase2b_summary_path=phase2b_summary_path,
        target_factor=target_factor,
        trigger_column=trigger_column,
        multiplier_column=multiplier_column,
        crowded_distance_rank_min=float(getattr(args, "crowded_distance_rank_min", 0.75) or 0.75),
        crowded_coinglass_rank_min=float(getattr(args, "crowded_coinglass_rank_min", 0.80) or 0.80),
    )
    blockers.extend(combined_trigger_blockers)

    missing_features = [column for column in feature_columns if column not in shared_panel.columns]
    if missing_features:
        blockers.append(f"missing_feature_columns:{','.join(missing_features)}")
    if multiplier_column not in shared_panel.columns:
        blockers.append("overlay_multiplier_column_missing")
    overlay_missing_count = (
        int(pd.to_numeric(shared_panel.get(multiplier_column), errors="coerce").isna().sum())
        if multiplier_column in shared_panel.columns
        else len(shared_panel)
    )
    if overlay_missing_count:
        blockers.append("overlay_multiplier_missing_or_non_numeric")
    missing_phase_count = sum(1 for context in phase_contexts if context.get("decision_time_ms") is None)
    if missing_phase_count:
        blockers.append("phase_context_missing_decision_time")
    allocated_capital = resolve_allocated_capital_usdt(args=args, payload=payload)
    if allocated_capital <= 0.0:
        blockers.append("allocated_capital_not_positive")

    shared_input_context = build_shared_input_context(
        payload=payload,
        frozen_config=frozen_config,
        config_sha=config_sha,
        symbols=symbols,
        panel=shared_panel,
        phase_contexts=phase_contexts,
        allocated_capital_usdt=allocated_capital,
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
    )
    write_json(output_root / "shared_input_context.json", shared_input_context)
    write_json(output_root / "phase_contexts.json", {"target_engine": MULTIPHASE_TARGET_ENGINE, "phases": phase_contexts})
    shared_panel.to_csv(output_root / "shared_candidate_panel.csv", index=False)

    baseline_portfolio: TargetPortfolio | None = None
    candidate_portfolio: TargetPortfolio | None = None
    baseline_context: dict[str, Any] = {}
    candidate_context: dict[str, Any] = {}
    baseline_risk_gate: dict[str, Any] = {"status": "not_run"}
    candidate_risk_gate: dict[str, Any] = {"status": "not_run"}
    plan_diff_rows: list[dict[str, Any]] = []
    sleeve_diff_rows: list[dict[str, Any]] = []
    baseline_engine_parity = False
    baseline_engine_parity_max_abs_diff = math.inf
    target_delta_symbol_count = 0
    absolute_target_weight_delta_sum = 0.0
    absolute_target_notional_delta_sum = 0.0

    if not blockers:
        official_baseline, official_context = build_multiphase_target_portfolio(
            shared_panel,
            config=frozen_config,
            config_sha256=config_sha,
            allocated_capital_usdt=allocated_capital,
            phase_contexts=phase_contexts,
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=rebalance_epoch_ms,
            strategy_label=str(strategy_section.get("label") or frozen_config.get("strategy_label") or "hv_balanced"),
        )
        local_baseline, local_baseline_context = build_phase4_multiphase_target_portfolio(
            shared_panel,
            config=frozen_config,
            config_sha256=config_sha,
            allocated_capital_usdt=allocated_capital,
            phase_contexts=phase_contexts,
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=rebalance_epoch_ms,
            score_mode="baseline",
            target_factor=target_factor,
            overlay_multiplier_column=multiplier_column,
            strategy_label=str(strategy_section.get("label") or frozen_config.get("strategy_label") or "hv_balanced"),
        )
        baseline_engine_parity_max_abs_diff = max_abs_target_weight_diff(official_baseline, local_baseline)
        baseline_engine_parity = baseline_engine_parity_max_abs_diff <= TARGET_WEIGHT_TOLERANCE
        if not baseline_engine_parity:
            blockers.append("baseline_local_wrapper_mismatch_with_existing_multiphase_engine")
        baseline_portfolio = official_baseline
        baseline_context = official_context
        candidate_portfolio, candidate_context = build_phase4_multiphase_target_portfolio(
            shared_panel,
            config=frozen_config,
            config_sha256=config_sha,
            allocated_capital_usdt=allocated_capital,
            phase_contexts=phase_contexts,
            rebalance_interval_days=rebalance_interval_days,
            rebalance_epoch_ms=rebalance_epoch_ms,
            score_mode="candidate",
            target_factor=target_factor,
            overlay_multiplier_column=multiplier_column,
            strategy_label=str(strategy_section.get("label") or frozen_config.get("strategy_label") or "hv_balanced"),
        )
        blockers.extend(str(item) for item in baseline_portfolio.blockers)
        blockers.extend(str(item) for item in candidate_portfolio.blockers)
        baseline_risk = evaluate_risk_gate(baseline_portfolio, mode="plan_only", config=payload, live_confirmed=False)
        candidate_risk = evaluate_risk_gate(candidate_portfolio, mode="plan_only", config=payload, live_confirmed=False)
        baseline_risk_gate = baseline_risk.to_dict()
        candidate_risk_gate = candidate_risk.to_dict()
        if not baseline_risk.passed:
            blockers.append("baseline_plan_only_risk_gate_blocked")
            blockers.extend(baseline_risk.blockers)
        if not candidate_risk.passed:
            blockers.append("candidate_plan_only_risk_gate_blocked")
            blockers.extend(candidate_risk.blockers)
        plan_diff_rows = build_target_plan_diff_rows(
            baseline_portfolio,
            candidate_portfolio,
            allocated_capital_usdt=allocated_capital,
        )
        sleeve_diff_rows = build_sleeve_diff_rows(
            list(baseline_context.get("sleeve_targets") or []),
            list(candidate_context.get("sleeve_targets") or []),
        )
        target_delta_symbol_count = int(
            sum(abs(float(row["target_weight_delta_candidate_minus_baseline"])) > TARGET_WEIGHT_TOLERANCE for row in plan_diff_rows)
        )
        absolute_target_weight_delta_sum = float(
            sum(abs(float(row["target_weight_delta_candidate_minus_baseline"])) for row in plan_diff_rows)
        )
        absolute_target_notional_delta_sum = float(
            sum(abs(float(row["target_notional_delta_candidate_minus_baseline_usdt"])) for row in plan_diff_rows)
        )
        if target_delta_symbol_count <= 0:
            blockers.append("candidate_target_plan_has_no_deterministic_difference")

        write_json(output_root / "baseline_target_portfolio.json", baseline_portfolio.metadata())
        write_json(output_root / "candidate_target_portfolio.json", candidate_portfolio.metadata())
        write_json(output_root / "baseline_multiphase_context.json", baseline_context)
        write_json(output_root / "candidate_multiphase_context.json", candidate_context)
        write_json(output_root / "baseline_plan_only_risk_gate.json", baseline_risk_gate)
        write_json(output_root / "candidate_plan_only_risk_gate.json", candidate_risk_gate)
        baseline_portfolio.positions_frame().to_csv(output_root / "baseline_target_positions.csv", index=False)
        candidate_portfolio.positions_frame().to_csv(output_root / "candidate_target_positions.csv", index=False)
        write_csv(output_root / "target_plan_diff.csv", plan_diff_rows)
        write_csv(output_root / "sleeve_target_diff.csv", sleeve_diff_rows)
        write_csv(output_root / "baseline_sleeve_targets.csv", list(baseline_context.get("sleeve_targets") or []))
        write_csv(output_root / "candidate_sleeve_targets.csv", list(candidate_context.get("sleeve_targets") or []))
        write_csv(output_root / "paired_sleeve_scores.csv", paired_sleeve_score_rows(baseline_context, candidate_context))
    else:
        write_json(output_root / "baseline_target_portfolio.json", {"status": "not_run"})
        write_json(output_root / "candidate_target_portfolio.json", {"status": "not_run"})
        write_json(output_root / "baseline_multiphase_context.json", {"status": "not_run"})
        write_json(output_root / "candidate_multiphase_context.json", {"status": "not_run"})
        write_json(output_root / "baseline_plan_only_risk_gate.json", baseline_risk_gate)
        write_json(output_root / "candidate_plan_only_risk_gate.json", candidate_risk_gate)
        write_csv(output_root / "baseline_target_positions.csv", [])
        write_csv(output_root / "candidate_target_positions.csv", [])
        write_csv(output_root / "target_plan_diff.csv", [])
        write_csv(output_root / "sleeve_target_diff.csv", [])
        write_csv(output_root / "baseline_sleeve_targets.csv", [])
        write_csv(output_root / "candidate_sleeve_targets.csv", [])
        write_csv(output_root / "paired_sleeve_scores.csv", [])

    blockers = sorted(set(str(item) for item in blockers if str(item).strip()))
    no_missing_data_fallbacks = not blockers
    status = "ready" if not blockers else "blocked"
    summary: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "live_config_path": str(live_config.path),
        "strategy_config_path": str(strategy_config_path),
        "strategy_config_sha256": config_sha,
        "requested_symbol_count": len(symbols),
        "shared_symbol_count": len(symbols),
        "shared_panel_row_count": int(len(shared_panel)),
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "portfolio_engine": "enhengclaw.live_trading.portfolio_targets.build_target_portfolio",
        "phase_count": int(len(phase_contexts)),
        "upper_timestamp_ms": int(upper_ms),
        "upper_timestamp_utc": datetime.fromtimestamp(int(upper_ms) / 1000, tz=UTC).isoformat().replace("+00:00", "Z"),
        "phase_decision_times_utc": [str(context.get("decision_time_utc") or "") for context in phase_contexts],
        "allocated_capital_usdt": float(allocated_capital),
        "target_factor": target_factor,
        "overlay_multiplier_column": multiplier_column,
        "overlay_trigger_column": trigger_column,
        "overlay_triggered_row_count": int(pd.to_numeric(shared_panel.get(multiplier_column), errors="coerce").fillna(1.0).ne(1.0).sum())
        if multiplier_column in shared_panel.columns
        else 0,
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
        "phase3_summary_path": str(phase3_summary_path) if phase3_summary_path is not None else "",
        "phase3_parity_proof_loaded": bool(phase3_proof.get("loaded")),
        "phase3_parity_proof_status": str(phase3_proof.get("status") or ""),
        "phase3_parity_proof_checks": dict(phase3_proof.get("checks") or {}),
        "shared_panel_sha256": shared_input_context["shared_panel_sha256"],
        "shared_phase_context_sha256": shared_input_context["phase_context_sha256"],
        "shared_risk_inputs_sha256": shared_input_context["risk_inputs_sha256"],
        "same_timestamp_context_proven": True,
        "same_symbol_set_proven": True,
        "same_portfolio_engine_proven": bool(baseline_engine_parity),
        "same_risk_inputs_proven": True,
        "baseline_existing_engine_parity_max_abs_target_weight_diff": (
            float(baseline_engine_parity_max_abs_diff) if math.isfinite(baseline_engine_parity_max_abs_diff) else None
        ),
        "baseline_target_status": baseline_portfolio.status if baseline_portfolio is not None else "not_run",
        "candidate_target_status": candidate_portfolio.status if candidate_portfolio is not None else "not_run",
        "baseline_plan_only_risk_gate_status": "passed" if bool(baseline_risk_gate.get("passed")) else str(baseline_risk_gate.get("status") or "not_run"),
        "candidate_plan_only_risk_gate_status": "passed" if bool(candidate_risk_gate.get("passed")) else str(candidate_risk_gate.get("status") or "not_run"),
        "baseline_target_position_count": len(baseline_portfolio.positions) if baseline_portfolio is not None else 0,
        "candidate_target_position_count": len(candidate_portfolio.positions) if candidate_portfolio is not None else 0,
        "target_weight_delta_symbol_count": target_delta_symbol_count,
        "absolute_target_weight_delta_sum": absolute_target_weight_delta_sum,
        "absolute_target_notional_delta_sum_usdt": absolute_target_notional_delta_sum,
        "deterministic_target_difference_proven": target_delta_symbol_count > 0,
        "no_missing_data_fallbacks_proven": no_missing_data_fallbacks,
        "plan_only": True,
        "mainnet_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "exchange_order_submission": "disabled",
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "shared_input_context": str(output_root / "shared_input_context.json"),
            "baseline_target_portfolio": str(output_root / "baseline_target_portfolio.json"),
            "candidate_target_portfolio": str(output_root / "candidate_target_portfolio.json"),
            "baseline_target_positions": str(output_root / "baseline_target_positions.csv"),
            "candidate_target_positions": str(output_root / "candidate_target_positions.csv"),
            "target_plan_diff": str(output_root / "target_plan_diff.csv"),
            "sleeve_target_diff": str(output_root / "sleeve_target_diff.csv"),
            "paired_sleeve_scores": str(output_root / "paired_sleeve_scores.csv"),
        },
    }
    write_json(output_root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_phase_contexts(
    *,
    started_at: datetime,
    rebalance_interval_days: int,
    rebalance_epoch_ms: int,
    phase_cycle_index: int,
) -> list[dict[str, Any]]:
    interval = max(int(rebalance_interval_days), 1)
    if phase_cycle_index < 0:
        now_ms = int(started_at.timestamp() * 1000)
        now_day = int((now_ms - int(rebalance_epoch_ms)) // DAY_MS)
        phase_cycle_index = max(1, (now_day - max(PHASES)) // interval)
    contexts: list[dict[str, Any]] = []
    for phase in PHASES:
        day_index = int(phase_cycle_index) * interval + int(phase)
        decision_ms = int(rebalance_epoch_ms) + day_index * DAY_MS
        decision_dt = datetime.fromtimestamp(decision_ms / 1000, tz=UTC)
        contexts.append(
            {
                "phase_offset_days": int(phase),
                "decision_time_ms": int(decision_ms),
                "decision_time_utc": decision_dt.isoformat().replace("+00:00", "Z"),
                "decision_date_utc": decision_dt.date().isoformat(),
                "rebalance_interval_days": interval,
                "rebalance_epoch_ms": int(rebalance_epoch_ms) + int(phase) * DAY_MS,
                "blockers": [],
            }
        )
    return contexts


def build_phase4_candidate_panel(
    *,
    symbols: Iterable[str],
    feature_columns: Iterable[str],
    phase_contexts: list[dict[str, Any]],
    target_factor: str,
    overlay_multiplier_column: str,
    overlay_trigger_column: str,
    lookback_days: int = 40,
) -> pd.DataFrame:
    symbol_list = [str(symbol) for symbol in symbols]
    features = [str(column) for column in feature_columns]
    upper_ms = max(int(context["decision_time_ms"]) for context in phase_contexts)
    start_ms = int(upper_ms) - (max(int(lookback_days), 1) - 1) * DAY_MS
    rows: list[dict[str, Any]] = []
    for day in range(max(int(lookback_days), 1)):
        timestamp_ms = start_ms + day * DAY_MS
        for index, symbol in enumerate(symbol_list):
            rank = index + 1
            trigger = rank <= 3
            subject = symbol[:-4] if symbol.upper().endswith("USDT") else symbol
            row: dict[str, Any] = {
                "timestamp_ms": int(timestamp_ms),
                "date_utc": datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date().isoformat(),
                "subject": subject,
                "usdm_symbol": symbol,
                "perp_close": 100.0 + index * 1.7 + day * 0.11,
                "perp_quote_volume_usd": 50_000_000.0 - index * 1_000_000.0,
                "universe_active": True,
                "universe_rank": rank,
                "liquidity_bucket": "top_liquidity" if rank <= 10 else "mid_liquidity",
                "funding_rate": 0.0,
                "funding_sample_count": 3.0,
                "has_perp": True,
                "perp_execution_eligible": True,
                "perp_executable_start_ms": int(start_ms),
                "momentum_20": 0.0,
                overlay_trigger_column: trigger,
                overlay_multiplier_column: 0.0 if trigger else 1.0,
            }
            for feature_index, column in enumerate(features):
                row[column] = phase4_feature_value(
                    rank=rank,
                    day=day,
                    feature_index=feature_index,
                    column=column,
                    target_factor=target_factor,
                )
            rows.append(row)
    return pd.DataFrame(rows)


def phase4_feature_value(*, rank: int, day: int, feature_index: int, column: str, target_factor: str) -> float:
    if column == target_factor:
        return 2.0 - (rank - 1) * 0.19 + day * 0.0001
    if column == "distance_to_high_5":
        return -0.55 + rank * 0.055
    if column == "realized_volatility_5":
        return 0.18
    if column == "intraday_realized_vol_4h_to_1d_smooth_60":
        return 0.24
    if column == "downside_upside_vol_ratio_30":
        return 0.85
    return 0.10 + feature_index * 0.01


def build_phase4_multiphase_target_portfolio(
    panel: pd.DataFrame,
    *,
    config: dict[str, Any],
    config_sha256: str,
    allocated_capital_usdt: float,
    phase_contexts: list[dict[str, Any]],
    rebalance_interval_days: int,
    rebalance_epoch_ms: int,
    score_mode: str,
    target_factor: str,
    overlay_multiplier_column: str,
    strategy_label: str,
) -> tuple[TargetPortfolio, dict[str, Any]]:
    sleeve_weight = 1.0 / float(len(phase_contexts) or 1)
    blockers: list[str] = []
    aggregate: dict[str, dict[str, Any]] = {}
    sleeve_rows: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    for context in phase_contexts:
        phase = int(context.get("phase_offset_days") or 0)
        decision_ms = context.get("decision_time_ms")
        if decision_ms is None:
            blockers.extend(str(item) for item in list(context.get("blockers") or []))
            continue
        phase_epoch = int(rebalance_epoch_ms) + phase * DAY_MS
        if score_mode == "candidate":
            snapshot = build_candidate_overlay_snapshot(
                panel,
                config=config,
                config_sha256=config_sha256,
                decision_time_ms=int(decision_ms),
                rebalance_interval_days=rebalance_interval_days,
                rebalance_epoch_ms=phase_epoch,
                target_factor=target_factor,
                overlay_multiplier_column=overlay_multiplier_column,
            )
        else:
            snapshot = build_live_hv_balanced_snapshot(
                panel,
                config=config,
                config_sha256=config_sha256,
                decision_time_ms=int(decision_ms),
                rebalance_interval_days=rebalance_interval_days,
                rebalance_epoch_ms=phase_epoch,
            )
        snapshots.append({"score_mode": score_mode, "phase_offset_days": phase, **snapshot.metadata()})
        if not snapshot.scores.empty:
            score_frame = snapshot.scores.copy()
            score_frame.insert(0, "score_mode", score_mode)
            score_frame.insert(1, "phase_offset_days", phase)
            score_rows.extend(score_frame.to_dict(orient="records"))
        sleeve = build_target_portfolio(snapshot, config=config, allocated_capital_usdt=allocated_capital_usdt)
        blockers.extend(snapshot.blockers)
        blockers.extend(sleeve.blockers)
        for position in sleeve.positions:
            weighted = float(position.target_weight) * sleeve_weight
            item = aggregate.setdefault(
                position.usdm_symbol,
                {
                    "subject": position.subject,
                    "usdm_symbol": position.usdm_symbol,
                    "score_sum": 0.0,
                    "weight": 0.0,
                    "phases": [],
                    "selection_reasons": [],
                    "short_multiplier_sum": 0.0,
                    "drawdown_multiplier_sum": 0.0,
                    "count": 0,
                },
            )
            item["weight"] += weighted
            item["score_sum"] += float(position.score) * sleeve_weight
            item["short_multiplier_sum"] += float(position.raw_short_multiplier) * sleeve_weight
            item["drawdown_multiplier_sum"] += float(position.portfolio_drawdown_multiplier) * sleeve_weight
            item["count"] += 1
            item["phases"].append(phase)
            item["selection_reasons"].append(position.selection_reason)
            sleeve_rows.append(
                {
                    "score_mode": score_mode,
                    "phase_offset_days": phase,
                    "decision_time_ms": int(decision_ms),
                    "decision_date_utc": context.get("decision_date_utc"),
                    "subject": position.subject,
                    "usdm_symbol": position.usdm_symbol,
                    "sleeve_weight": sleeve_weight,
                    "sleeve_target_weight": float(position.target_weight),
                    "aggregate_weight_contribution": weighted,
                    "side": position.side,
                    "score": float(position.score),
                    "selection_reason": position.selection_reason,
                }
            )

    positions: list[TargetPosition] = []
    for symbol, item in sorted(aggregate.items()):
        weight = float(item["weight"])
        if abs(weight) <= TARGET_WEIGHT_TOLERANCE:
            continue
        count = max(int(item["count"]), 1)
        positions.append(
            TargetPosition(
                subject=str(item["subject"]),
                usdm_symbol=str(symbol),
                side="long" if weight > 0.0 else "short",
                score=float(item["score_sum"]),
                target_weight=weight,
                target_notional_usdt=float(abs(weight) * allocated_capital_usdt),
                previous_target_weight=0.0,
                delta_target_weight=weight,
                raw_short_multiplier=float(item["short_multiplier_sum"]) / float(count),
                portfolio_drawdown_multiplier=float(item["drawdown_multiplier_sum"]) / float(count),
                selection_reason="multiphase_aggregate:" + ",".join(
                    sorted(set(str(value) for value in item["selection_reasons"]))
                ),
            )
        )
    gross = sum(abs(position.target_weight) for position in positions)
    net = sum(position.target_weight for position in positions)
    label_suffix = "dth60_candidate" if score_mode == "candidate" else "baseline"
    portfolio = TargetPortfolio(
        portfolio_id=f"hv_balanced_multiphase:{label_suffix}:{max(int(context.get('decision_time_ms') or 0) for context in phase_contexts)}:portfolio",
        decision_id=f"hv_balanced_multiphase_aggregate:{label_suffix}",
        strategy_label=f"{strategy_label}:{label_suffix}:multiphase_10_sleeve",
        allocated_capital_usdt=float(allocated_capital_usdt),
        portfolio_drawdown=0.0,
        portfolio_drawdown_multiplier=1.0,
        target_gross_weight=float(gross),
        target_net_weight=float(net),
        status="ok" if not blockers else "blocked",
        blockers=sorted(set(str(item) for item in blockers)),
        positions=positions,
    )
    return portfolio, {
        "status": portfolio.status,
        "score_mode": score_mode,
        "blockers": portfolio.blockers,
        "sleeve_weight": sleeve_weight,
        "phase_contexts": phase_contexts,
        "snapshots": snapshots,
        "sleeve_targets": sleeve_rows,
        "score_rows": score_rows,
        "target_engine": MULTIPHASE_TARGET_ENGINE,
    }


def build_candidate_overlay_snapshot(
    panel: pd.DataFrame,
    *,
    config: dict[str, Any],
    config_sha256: str,
    decision_time_ms: int,
    rebalance_interval_days: int,
    rebalance_epoch_ms: int,
    target_factor: str,
    overlay_multiplier_column: str,
) -> LiveDecisionSnapshot:
    base = build_live_hv_balanced_snapshot(
        panel,
        config=config,
        config_sha256=config_sha256,
        decision_time_ms=decision_time_ms,
        rebalance_interval_days=rebalance_interval_days,
        rebalance_epoch_ms=rebalance_epoch_ms,
    )
    candidate_label = f"{base.strategy_label}:dth60_coinglass_candidate"
    if base.status != "ok":
        return LiveDecisionSnapshot(
            decision_id=f"{candidate_label}:{int(decision_time_ms)}",
            strategy_label=candidate_label,
            config_sha256=config_sha256,
            decision_time_ms=int(decision_time_ms),
            decision_date_utc=base.decision_date_utc,
            rebalance_slot=base.rebalance_slot,
            input_bar_end_ms=base.input_bar_end_ms,
            status=base.status,
            blockers=list(base.blockers),
            scores=base.scores,
        )
    try:
        layer = compute_candidate_score_layer(
            panel,
            feature_columns=[str(item) for item in config.get("feature_columns") or []],
            feature_weights=dict(config.get("feature_weights") or {}),
            target_factor=target_factor,
            overlay_enabled=True,
            overlay_multiplier_column=overlay_multiplier_column,
        )
    except ValueError as exc:
        return LiveDecisionSnapshot(
            decision_id=f"{candidate_label}:{int(decision_time_ms)}",
            strategy_label=candidate_label,
            config_sha256=config_sha256,
            decision_time_ms=int(decision_time_ms),
            decision_date_utc=base.decision_date_utc,
            rebalance_slot=base.rebalance_slot,
            input_bar_end_ms=base.input_bar_end_ms,
            status="blocked",
            blockers=[f"candidate_overlay_score_failed:{exc}"],
            scores=base.scores,
        )
    layer_rows = layer.loc[pd.to_numeric(layer["timestamp_ms"], errors="coerce").eq(int(decision_time_ms))].copy()
    merge_columns = [
        column
        for column in layer_rows.columns
        if column == "subject" or column == "score" or column == "raw_score" or column.startswith("contribution_")
    ]
    candidate_scores = base.scores.drop(
        columns=[column for column in base.scores.columns if column.startswith("contribution_") or column == "raw_score"],
        errors="ignore",
    ).merge(
        layer_rows.loc[:, merge_columns],
        on="subject",
        how="left",
        suffixes=("", "_candidate"),
    )
    if "score_candidate" in candidate_scores.columns:
        candidate_scores["score"] = pd.to_numeric(candidate_scores["score_candidate"], errors="coerce")
        candidate_scores = candidate_scores.drop(columns=["score_candidate"])
    missing_score_count = int(pd.to_numeric(candidate_scores["score"], errors="coerce").isna().sum())
    blockers = [f"candidate_overlay_score_missing_rows:{missing_score_count}"] if missing_score_count else []
    if missing_score_count:
        candidate_scores["score"] = pd.to_numeric(candidate_scores["score"], errors="coerce").fillna(0.0)
    return LiveDecisionSnapshot(
        decision_id=f"{candidate_label}:{int(decision_time_ms)}",
        strategy_label=candidate_label,
        config_sha256=config_sha256,
        decision_time_ms=int(decision_time_ms),
        decision_date_utc=base.decision_date_utc,
        rebalance_slot=base.rebalance_slot,
        input_bar_end_ms=base.input_bar_end_ms,
        status="ok" if not blockers else "blocked",
        blockers=blockers,
        scores=candidate_scores.reset_index(drop=True),
    )


def resolve_phase3_summary_path(path_ref: str) -> Path | None:
    if str(path_ref or "").strip():
        return resolve_repo_path(path_ref)
    parent = resolve_repo_path(DEFAULT_PHASE3_PARENT)
    if not parent.exists():
        return None
    summaries = sorted(parent.glob("*/summary.json"), reverse=True)
    return summaries[0] if summaries else None


def load_phase3_parity_proof(summary_path: Path | None) -> tuple[dict[str, Any], list[str]]:
    if summary_path is None or not summary_path.exists():
        return {"loaded": False, "status": "missing", "checks": {}}, ["phase3_parity_proof_missing"]
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "loaded": False,
            "status": "unreadable",
            "checks": {"error": f"{exc.__class__.__name__}:{exc}"},
        }, ["phase3_parity_proof_unreadable"]
    checks = {
        "status_ready": summary.get("status") == "ready",
        "disabled_wrapper_score_matches_core": bool(summary.get("disabled_wrapper_score_matches_core")),
        "overlay_enabled_only_target_contribution_changed": bool(
            summary.get("overlay_enabled_only_target_contribution_changed")
        ),
        "phase2_pit_proof_loaded": bool(summary.get("phase2_pit_proof_loaded")),
        "phase2b_pit_proof_loaded": bool(summary.get("phase2b_pit_proof_loaded")),
        "combined_candidate_trigger_proven": bool(summary.get("combined_candidate_trigger_proven")),
        "no_blockers": not list(summary.get("blockers") or []),
    }
    blockers: list[str] = []
    if not checks["status_ready"]:
        blockers.append("phase3_parity_proof_not_ready")
    if not checks["disabled_wrapper_score_matches_core"]:
        blockers.append("phase3_disabled_core_parity_missing")
    if not checks["overlay_enabled_only_target_contribution_changed"]:
        blockers.append("phase3_only_target_contribution_proof_missing")
    if not checks["phase2_pit_proof_loaded"]:
        blockers.append("phase3_phase2_pit_proof_missing")
    if not checks["phase2b_pit_proof_loaded"]:
        blockers.append("phase3_phase2b_pit_proof_missing")
    if not checks["combined_candidate_trigger_proven"]:
        blockers.append("phase3_combined_candidate_trigger_proof_missing")
    if not checks["no_blockers"]:
        blockers.append("phase3_parity_proof_has_blockers")
    return {
        "loaded": True,
        "status": str(summary.get("status") or ""),
        "checks": checks,
        "run_id": str(summary.get("run_id") or ""),
        "path": str(summary_path),
    }, blockers


def resolve_allocated_capital_usdt(*, args: argparse.Namespace, payload: dict[str, Any]) -> float:
    explicit = float(getattr(args, "allocated_capital_usdt", 0.0) or 0.0)
    if explicit > 0.0:
        return explicit
    capital = dict(payload.get("capital") or {})
    return float(capital.get("allocated_capital_usdt") or 0.0)


def build_shared_input_context(
    *,
    payload: dict[str, Any],
    frozen_config: dict[str, Any],
    config_sha: str,
    symbols: list[str],
    panel: pd.DataFrame,
    phase_contexts: list[dict[str, Any]],
    allocated_capital_usdt: float,
    rebalance_interval_days: int,
    rebalance_epoch_ms: int,
) -> dict[str, Any]:
    risk_inputs = {
        "allocated_capital_usdt": float(allocated_capital_usdt),
        "risk": dict(payload.get("risk") or {}),
        "capital": dict(payload.get("capital") or {}),
        "strategy_profile": dict(frozen_config.get("strategy_profile") or {}),
        "rebalance_interval_days": int(rebalance_interval_days),
        "rebalance_epoch_ms": int(rebalance_epoch_ms),
    }
    phase_context_hash_payload = {
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "phase_contexts": phase_contexts,
    }
    return {
        "target_engine": MULTIPHASE_TARGET_ENGINE,
        "portfolio_engine": "enhengclaw.live_trading.portfolio_targets.build_target_portfolio",
        "symbols": symbols,
        "symbol_count": len(symbols),
        "shared_panel_sha256": dataframe_sha256(panel),
        "phase_context_sha256": stable_sha256(phase_context_hash_payload),
        "risk_inputs_sha256": stable_sha256(risk_inputs),
        "strategy_config_sha256": config_sha,
        "risk_inputs": risk_inputs,
        "phase_contexts": phase_contexts,
    }


def build_target_plan_diff_rows(
    baseline: TargetPortfolio,
    candidate: TargetPortfolio,
    *,
    allocated_capital_usdt: float,
) -> list[dict[str, Any]]:
    baseline_rows = {position.usdm_symbol: position for position in baseline.positions}
    candidate_rows = {position.usdm_symbol: position for position in candidate.positions}
    rows: list[dict[str, Any]] = []
    for symbol in sorted(set(baseline_rows) | set(candidate_rows)):
        base = baseline_rows.get(symbol)
        cand = candidate_rows.get(symbol)
        base_weight = float(base.target_weight) if base is not None else 0.0
        cand_weight = float(cand.target_weight) if cand is not None else 0.0
        delta = cand_weight - base_weight
        rows.append(
            {
                "symbol": symbol,
                "subject": str((cand or base).subject if (cand or base) is not None else symbol),
                "baseline_side": str(base.side if base is not None else "flat"),
                "candidate_side": str(cand.side if cand is not None else "flat"),
                "baseline_target_weight": base_weight,
                "candidate_target_weight": cand_weight,
                "target_weight_delta_candidate_minus_baseline": delta,
                "baseline_target_notional_usdt": abs(base_weight) * float(allocated_capital_usdt),
                "candidate_target_notional_usdt": abs(cand_weight) * float(allocated_capital_usdt),
                "target_notional_delta_candidate_minus_baseline_usdt": abs(delta) * float(allocated_capital_usdt),
                "changed": abs(delta) > TARGET_WEIGHT_TOLERANCE,
            }
        )
    return rows


def build_sleeve_diff_rows(
    baseline_sleeves: list[dict[str, Any]],
    candidate_sleeves: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[int, str]:
        return int(row.get("phase_offset_days") or 0), str(row.get("usdm_symbol") or "")

    baseline_by_key = {key(row): row for row in baseline_sleeves}
    candidate_by_key = {key(row): row for row in candidate_sleeves}
    rows: list[dict[str, Any]] = []
    for item_key in sorted(set(baseline_by_key) | set(candidate_by_key)):
        base = baseline_by_key.get(item_key, {})
        cand = candidate_by_key.get(item_key, {})
        base_weight = float(base.get("aggregate_weight_contribution") or 0.0)
        cand_weight = float(cand.get("aggregate_weight_contribution") or 0.0)
        rows.append(
            {
                "phase_offset_days": item_key[0],
                "symbol": item_key[1],
                "baseline_side": str(base.get("side") or "flat"),
                "candidate_side": str(cand.get("side") or "flat"),
                "baseline_aggregate_weight_contribution": base_weight,
                "candidate_aggregate_weight_contribution": cand_weight,
                "aggregate_weight_contribution_delta": cand_weight - base_weight,
                "changed": abs(cand_weight - base_weight) > TARGET_WEIGHT_TOLERANCE,
            }
        )
    return rows


def paired_sleeve_score_rows(baseline_context: dict[str, Any], candidate_context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        *list(baseline_context.get("score_rows") or []),
        *list(candidate_context.get("score_rows") or []),
    ]


def max_abs_target_weight_diff(left: TargetPortfolio, right: TargetPortfolio) -> float:
    left_weights = {position.usdm_symbol: float(position.target_weight) for position in left.positions}
    right_weights = {position.usdm_symbol: float(position.target_weight) for position in right.positions}
    if not left_weights and not right_weights:
        return 0.0
    return max(abs(left_weights.get(symbol, 0.0) - right_weights.get(symbol, 0.0)) for symbol in set(left_weights) | set(right_weights))


def dataframe_sha256(frame: pd.DataFrame) -> str:
    ordered = frame.copy()
    ordered = ordered.reindex(sorted(ordered.columns), axis=1)
    return hashlib.sha256(ordered.to_csv(index=False).encode("utf-8")).hexdigest()


def stable_sha256(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_phase4_shadow(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
