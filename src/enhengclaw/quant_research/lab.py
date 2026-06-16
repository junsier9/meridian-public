from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import traceback
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from enhengclaw.ops.evidence_contracts import required_source_commit_sha, with_evidence_metadata

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from .binance_derivatives import as_of_sync_summary_path, latest_sync_summary_path, resolve_external_derivatives_root
from .coinapi_spot_sync import run_quant_coinapi_spot_sync
from .coinglass_extended import load_extended_rows, resolve_extended_external_root
from .contracts import (
    PIT_SELECTION_METRIC,
    QuantUniverseCandidate,
    pit_universe_artifact_is_valid,
    pit_universe_artifact_metadata,
    portable_path,
    read_json,
    slugify,
    utc_now,
    write_json,
)
from .data_readiness import (
    CROSS_SECTIONAL_SPOT_BLOCKER,
    CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    CROSS_SECTIONAL_DAILY_4H_SPOT_BLOCKER,
    CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE,
    CROSS_SECTIONAL_INTRADAY_1H_SPOT_BLOCKER,
    DISCOVERY_DERIVATIVES_BLOCKER,
    DISCOVERY_EVENT_BLOCKER,
    SINGLE_ASSET_SPOT_BLOCKER,
    build_dataset_data_readiness,
    cross_sectional_subject_min,
    dataset_required_spot_intervals,
    derivatives_ready_row_fraction_thresholds,
    evaluate_derivatives_history_gap,
    load_data_readiness_contract,
    normalize_dataset_profile,
    required_derivatives_families,
    required_walk_forward_window_count,
    resolve_default_spot_ohlcv_external_root,
    SINGLE_ASSET_DATASET_PROFILE,
    spot_provider_lane,
    strategy_requires_derivatives,
    strategy_requires_temporal_event_tape,
)
from .features import (
    ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS,
    DEFAULT_LABEL_CONTRACT_ID,
    EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
    EXECUTION_ALIGNED_LABEL_CONTRACT_ID,
    PARTICIPATION_DRIFT_LABEL_CONTRACT_ID,
    _xs_alpha_ontology_v5_h10d_strict_event_state_short_boundary_score,
    _xs_alpha_ontology_v6_h10d_spk_short_replacement_score,
    basis_divergence_score,
    breakout_volatility_expansion_score,
    breakout_continuation_score,
    build_cross_sectional_feature_bundle,
    build_cross_sectional_intraday_feature_bundle,
    build_single_asset_feature_bundle,
    carry_funding_score,
    event_drift_score,
    evaluate_no_future_leakage,
    mean_reversion_score,
    ranking_score,
    relative_strength_score,
    trend_following_score,
    volatility_expansion_score,
    xs_breakout_confirmation_score,
    xs_breakout_failure_reversal_score,
    xs_base_breakout_score,
    xs_exhaustion_reversal_score,
    xs_low_vol_strength_score,
    xs_momentum_acceleration_score,
    xs_participation_drift_score,
    xs_participation_drift_v3_score,
    xs_participation_drift_v4_score,
    xs_participation_drift_v5_score,
    xs_strength_on_reset_v1_score,
    xs_strength_on_reset_v2_score,
    xs_strength_on_reset_v3_score,
    xs_strength_on_reset_v4_score,
    xs_strength_on_reset_v5_score,
    xs_pullback_resume_score,
    xs_quality_strength_v3_score,
    xs_quality_pullback_v1_score,
    xs_quality_pullback_v2_score,
    xs_contraction_release_v1_score,
    xs_contraction_release_v2_score,
    xs_contraction_release_v3_score,
    xs_contraction_release_v4_score,
    xs_contraction_release_v5_score,
    xs_absorption_recovery_v1_score,
    xs_failed_breakdown_reclaim_v1_score,
    xs_regime_switch_ranking_v1_score,
    xs_basis_funding_dislocation_v1_score,
    xs_relative_value_spread_v1_score,
    xs_relative_value_spread_v2_score,
    xs_relative_value_spread_v3_score,
    xs_relative_value_spread_v4_score,
    xs_relative_value_spread_v5_score,
    xs_relative_value_spread_v6_score,
    xs_relative_value_spread_v7_score,
    xs_relative_value_spread_v8_score,
    xs_relative_value_spread_v9_score,
    xs_reversal_quality_v1_score,
    xs_carry_dislocation_v1_score,
    xs_vol_regime_blend_v1_score,
    xs_dispersion_regime_blend_v1_score,
    xs_dual_regime_filter_v1_score,
    xs_dual_regime_filter_v6_score,
    xs_quad_regime_filter_v1_score,
    xs_dual_regime_filter_v2_score,
    xs_dual_regime_filter_v3_score,
    xs_dual_regime_filter_v4_score,
    xs_dual_regime_filter_v5_score,
    xs_dual_regime_filter_v6_score,
    xs_dual_regime_filter_v7_score,
    xs_dual_regime_filter_v8_score,
    xs_dual_regime_filter_v9_score,
    xs_dual_regime_filter_v11_score,
    xs_minimal_v1_score,
    xs_minimal_v2_score,
    xs_minimal_v3_score,
    xs_minimal_v4_score,
    xs_minimal_v5_score,
    xs_minimal_v6_score,
    xs_minimal_v9_score,
    xs_minimal_v10_score,
    xs_minimal_v11_score,
    xs_minimal_v12_score,
    xs_minimal_v13_score,
    xs_alpha_ontology_v1_score,
    xs_alpha_ontology_v2_score,
    xs_alpha_ontology_v3_score,
    xs_alpha_ontology_v4_score,
    xs_alpha_ontology_v5_score,
    xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d_score,
    xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v6_score,
    xs_alpha_ontology_v6_h10d_score,
    xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005_score,
    xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010_score,
    xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini_score,
    xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score,
    xs_alpha_ontology_v6_h10d_spk_ss_veto_mini_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v2_score,
    xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v3_score,
    xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1_score,
    xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1_score,
    xs_alpha_ontology_spk_lsk3_mid_tail_h5d_score,
    xs_alpha_ontology_spk_post_pump_stall_v1_h5d_score,
    xs_alpha_ontology_spk_post_pump_stall_v2_h5d_score,
    xs_alpha_ontology_v7_score,
    xs_alpha_ontology_v8_score,
    xs_alpha_ontology_v9_h10d_score,
    xs_alpha_ontology_v10_regime_conditional_h10d_score,
    xs_alpha_ontology_v11_absorb_qshare_h10d_score,
    xs_alpha_ontology_v11_drain_rs_h10d_score,
    xs_alpha_ontology_v11_flow_blend_h10d_score,
    xs_alpha_ontology_v12_mf14_sell_beta_h10d_score,
    xs_alpha_ontology_v12_mf14_sell_mid_short_h10d_score,
    xs_alpha_ontology_v12_mf14_rebound_idio_h10d_score,
    xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d_score,
    xs_ensemble_v74_v80_score,
    xs_residualized_pair_book_v1_score,
    xs_residualized_pair_book_v2_score,
    xs_pair_spread_book_v1_score,
    xs_pair_spread_book_v2_score,
    xs_pair_spread_book_v3_score,
    xs_pair_spread_book_v4_score,
    xs_pair_spread_book_v5_score,
    xs_pair_spread_book_v6_score,
    xs_pair_spread_book_v7_score,
    xs_pair_spread_book_v8_score,
    xs_pair_spread_book_v9_score,
    xs_pair_spread_book_v10_score,
    xs_pair_spread_book_v11_score,
    xs_pair_spread_book_v12_score,
     xs_pair_spread_book_v16_score,
     xs_pair_spread_book_v17_score,
     xs_pair_spread_book_v18_score,
     xs_pair_spread_book_v19_score,
     xs_pair_spread_book_v20_score,
     xs_pair_spread_book_v21_score,
     xs_pair_spread_book_v22_score,
     xs_pair_spread_book_v23_score,
     xs_pair_spread_book_v24_score,
     xs_quality_strength_score,
     xs_range_reversion_score,
    xs_squeeze_release_score,
    xs_relative_strength_score,
    xs_squeeze_breakout_score,
    xs_volatility_expansion_follow_through_score,
)
from .derivatives_quality import (
    DERIVATIVES_FAMILY_COLUMNS,
    aggregate_strategy_derivatives_quality,
    build_derivatives_provider_index,
    feature_derivatives_quality_highlights,
    summarize_dataset_derivatives_quality,
    summarize_strategy_derivatives_quality,
)
from .execution_backtest import (
    backtest_cross_sectional,
    backtest_single_asset,
    filter_cross_sectional_execution_frame,
)
from .execution_cost_model import (
    EXECUTION_COST_MODEL_VERSION,
    load_execution_cost_model,
    resolve_execution_cost_model,
)
from .experiment_status import (
    EXPERIMENT_STATUS_INVALIDATED,
    EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
    EXPERIMENT_STATUS_PIPELINE_UNRELIABLE_PENDING_SINGLE_ASSET_FIX,
    EXPERIMENT_STATUS_QUARANTINED,
    is_pass_experiment_status,
    is_pipeline_unreliable_pending_single_asset_fix,
    is_quarantined_experiment_status,
    is_rerun_required_experiment_status,
)
from .feature_admission import (
    build_feature_admission_policy,
    build_feature_admission_section,
    classify_feature_manifest_columns,
    is_model_admissible_numeric_column,
)
from .feature_quality import (
    build_feature_quality_frame,
    select_feature_quality,
    summarize_feature_quality,
)
from .feature_registry import build_feature_registry_section
from .gap_remediation import (
    build_gap_remediation_plan,
    execute_gap_remediation_backfill,
    write_gap_remediation_summary,
)
from .fixed_set_comparison import (
    build_promotion_gate_assessment,
    extract_period_frame,
    fixed_set_comparison_applicability,
    fixed_set_reference_entries,
    fixed_set_reference_labels,
    load_fixed_set_comparison_contract,
    pairwise_comparison,
    performance_summary as fixed_set_performance_summary,
    periods_per_year as fixed_set_periods_per_year,
    resolve_fixed_set_candidate_label,
)
from .falsification_audit import (
    INVALIDATED_UNVERIFIED_RESEARCH_EVIDENCE,
    falsification_is_required,
    falsification_outcome_for_skipped_audit,
    NOT_REQUIRED_FALSIFICATION_STATUS,
    run_falsification_audit,
)
from .falsification_runner import run_statistical_falsification
from .alpha_experiment_reporter import build_alpha_experiment_card
from .deterministic_core import (
    CONTROL_BASELINE_LANE,
    DERIVATIVES_THESIS_FEATURE_COLUMNS,
    HYPOTHESIS_MODEL_FAMILIES,
    HYPOTHESIS_MODEL_LANE,
    LIQUID_PERP_CORE_20_PRESET,
    LIQUID_PERP_TIER2_20_PRESET,
    LIQUID_PERP_CORE_30_PRESET,
    HYPOTHESIS_RESEARCH_LANES,
    load_deterministic_strategy_manifest,
    select_feature_columns,
    strategy_lifecycle,
)
from .legacy_surface import raise_legacy_surface_frozen
from .market_data import (
    aggregate_4h_to_1d_context,
    aggregate_1h_to_1d_context,
    as_of_end_ms as resolve_as_of_end_ms,
    load_derivatives_frame,
    load_ohlcv_frame,
)
from .runtime_support import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    WORKBENCH_ROOT,
    build_universe_snapshot,
    resolve_quant_input_path,
    run_quant_universe_freeze,
    load_quant_universe_snapshot,
)
from .overlap_integrity import (
    chronological_split_with_purge,
    evaluate_overlap_integrity,
    infer_interval_ms,
    infer_label_horizon_bars,
    walk_forward_split_with_purge,
)
from .label_builder import build_label_artifact
from .m3_3_event_state import add_m3_3_event_state_features
from .research_dataset_builder import (
    build_research_dataset_manifest_fields,
    scope_research_dataset_to_frame,
    validate_research_dataset_requirements,
)
from .reproducibility import (
    QUANT_DATASET_MANIFEST_ARTIFACT_FAMILY,
    QUANT_DATASET_MANIFEST_CONTRACT_VERSION,
    QUANT_FEATURE_MANIFEST_ARTIFACT_FAMILY,
    QUANT_FEATURE_MANIFEST_CONTRACT_VERSION,
    apply_reproducibility_fields,
    build_dataset_fingerprint,
    build_feature_hash,
    build_reproducibility_section,
    sha256_dataframe_csv,
)
from .split_realization_contract import (
    build_split_realization_contract,
    expected_rebalance_count,
    partition_gap_bars as split_contract_partition_gap_bars,
    realization_step_bars as split_contract_realization_step_bars,
    resolve_split_realization_contract,
    split_boundary_contamination_total,
)
from .validation_contract import (
    VALIDATION_CONTRACT_VERSION,
    build_execution_stress_section,
    build_regime_holdout_section,
    build_split_integrity_section,
    build_walk_forward_assessment,
    execution_capacity_limits,
    evaluate_validation_contract,
    load_validation_contract,
    validation_contract_reference_capital_usd,
    validation_contract_blocker_codes,
)


def _safe_spearman_rank_corr(left: pd.Series, right: pd.Series) -> float | None:
    """Spearman rank correlation without SciPy, returning None for constant slices."""
    df = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(df) < 3:
        return None
    left_rank = df["left"].rank(method="average")
    right_rank = df["right"].rank(method="average")
    if left_rank.nunique(dropna=True) < 2 or right_rank.nunique(dropna=True) < 2:
        return None
    rho = left_rank.corr(right_rank)
    if pd.isna(rho):
        return None
    return float(rho)


NUMERIC_EXCLUDE = {
    "subject",
    "liquidity_bucket",
    "strategy_profile",
    "timestamp_utc",
    "date_utc",
    "shape",
    "target_up",
}
DATASET_PROVENANCE = "live_ohlcv_dataset"
DERIVATIVES_FIRST_CROSS_SECTION_MODELS = {"carry_funding", "basis_divergence"}


def _build_logistic_pipeline(*, max_iter: int = 3000) -> Pipeline:
    return Pipeline(
        steps=(
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=max_iter, random_state=42)),
        )
    )


def run_quant_research_cycle(
    *,
    as_of: str,
    compiler_backend: str = "deterministic",
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    workbench_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
    auto_detect_spot_ohlcv_external_root: bool = True,
    auto_api_gap_backfill: bool = False,
    strategy_id_allowlist: list[str] | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)
    resolved_spot_ohlcv_external_root = (
        resolve_default_spot_ohlcv_external_root(
            spot_ohlcv_external_root=spot_ohlcv_external_root,
        )
        if auto_detect_spot_ohlcv_external_root
        else (None if spot_ohlcv_external_root is None else Path(spot_ohlcv_external_root).expanduser().resolve())
    )
    cycle_root = resolved_artifacts_root / "cycles" / as_of
    cycle_root.mkdir(parents=True, exist_ok=True)

    universe_snapshot = load_quant_universe_snapshot(as_of=as_of, artifacts_root=resolved_artifacts_root)
    universe_candidates = tuple(
        QuantUniverseCandidate.from_payload(item)
        for item in universe_snapshot.get("candidates", [])
        if isinstance(item, dict)
    )
    derivatives_sync, derivatives_sync_summary_path = require_derivatives_sync_summary(
        as_of=as_of,
        derivatives_external_root=derivatives_external_root,
    )
    derivatives_sync_summary = _summarize_derivatives_sync(sync_summary=derivatives_sync)
    strategy_manifest = load_deterministic_strategy_manifest()
    datasets = build_quant_datasets(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        universe_snapshot=universe_snapshot,
        universe_candidates=universe_candidates,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=resolved_spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
    )
    spot_gap_backfill_summary = _apply_spot_gap_backfill_for_cross_sectional_profiles(
        as_of=as_of,
        cycle_root=cycle_root,
        quant_input_root=resolved_quant_input_root,
        artifacts_root=resolved_artifacts_root,
        strategy_manifest=strategy_manifest,
        datasets=datasets,
        universe_snapshot=universe_snapshot,
        universe_candidates=universe_candidates,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=resolved_spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
        auto_api_gap_backfill=auto_api_gap_backfill,
        strategy_id_allowlist=strategy_id_allowlist,
    )
    if spot_gap_backfill_summary.get("rebuild_required"):
        datasets = build_quant_datasets(
            as_of=as_of,
            artifacts_root=resolved_artifacts_root,
            universe_snapshot=universe_snapshot,
            universe_candidates=universe_candidates,
            ohlcv_external_root=ohlcv_external_root,
            spot_ohlcv_external_root=resolved_spot_ohlcv_external_root,
            derivatives_external_root=derivatives_external_root,
            derivatives_sync=derivatives_sync,
            source_commit_sha=source_commit_sha,
        )
    feature_sets = build_quant_feature_sets(
        artifacts_root=resolved_artifacts_root,
        datasets=datasets,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
    )
    daily_cycle_selection = _daily_cycle_strategies(
        as_of=as_of,
        datasets=datasets,
        strategy_manifest=strategy_manifest,
        strategy_id_allowlist=strategy_id_allowlist,
    )
    daily_strategies = list(daily_cycle_selection["strategies"])
    if not daily_strategies:
        blockers = ", ".join(daily_cycle_selection["data_gap_blockers"]) or "unknown"
        raise RuntimeError(f"deterministic quant core blocked before experiments: {blockers}")
    experiments = run_quant_experiments_for_strategies(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        strategies=daily_strategies,
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
        source_commit_sha=source_commit_sha,
    )
    lane_summary = _quant_lane_summary(
        datasets=datasets,
        feature_sets=feature_sets,
        experiments=experiments,
        spot_ohlcv_external_root=resolved_spot_ohlcv_external_root,
        selection_blocked_strategy_ids=daily_cycle_selection["blocked_strategy_ids"],
        selection_data_gap_blockers=daily_cycle_selection["data_gap_blockers"],
    )
    aggregate_metrics = {
        "experiment_status_counts": _count_values(experiments, field_name="experiment_status"),
        "pass_rate": (
            sum(1 for item in experiments if is_pass_experiment_status(item.get("experiment_status"))) / len(experiments)
            if experiments
            else 0.0
        ),
        "median_test_sharpe": _median_metric(
            experiments=experiments,
            section="validation_report",
            subfield="test_metrics",
            metric="sharpe",
        ),
        "median_validation_net_return": _median_metric(
            experiments=experiments,
            section="validation_report",
            subfield="validation_metrics",
            metric="net_return",
        ),
    }
    summary_payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "cycle_mode": "deterministic_core",
        "compiler_backend": compiler_backend,
        "artifacts_root": str(resolved_artifacts_root),
        "quant_input_root": str(resolved_quant_input_root),
        "spot_provider_lane": lane_summary["spot_provider_lane"],
        "universe_input_path": str(universe_snapshot.get("source_input_path")),
        "universe_snapshot_path": str(universe_snapshot["path"]),
        "universe_count": len(universe_candidates),
        "strategy_manifest_path": str(strategy_manifest["path"]),
        "strategy_manifest_contract_version": str(strategy_manifest["contract_version"]),
        "strategy_manifest_selection_policy": str(strategy_manifest["selection_policy"]),
        "strategy_manifest_strategy_count": len(strategy_manifest["entries"]),
        "strategy_manifest_enabled_count": sum(1 for entry in strategy_manifest["entries"] if bool(entry.get("enabled"))),
        "strategy_id_allowlist": [
            str(item).strip()
            for item in list(strategy_id_allowlist or [])
            if str(item).strip()
        ],
        "readiness_verdict": str(daily_cycle_selection["readiness_verdict"]),
        "daily_strategy_count": len(daily_strategies),
        "daily_strategy_ids": [str(entry.get("strategy_id")) for entry in daily_strategies],
        "blocked_strategy_ids": lane_summary["blocked_strategy_ids"],
        "data_gap_blockers": lane_summary["data_gap_blockers"],
        "dataset_ids": [str(entry["dataset_id"]) for entry in datasets],
        "dataset_manifests": [entry["manifest_path"] for entry in datasets],
        "dataset_subject_counts": lane_summary["dataset_subject_counts"],
        "dataset_row_counts": lane_summary["dataset_row_counts"],
        "spot_subject_coverage": lane_summary["spot_subject_coverage"],
        "cross_sectional_executable_subject_count": lane_summary["cross_sectional_executable_subject_count"],
        "cross_sectional_dataset_subject_counts": lane_summary["cross_sectional_dataset_subject_counts"],
        "feature_set_ids": [str(entry["feature_set_id"]) for entry in feature_sets],
        "feature_manifests": [entry["manifest_path"] for entry in feature_sets],
        "feature_row_counts": lane_summary["feature_row_counts"],
        "dataset_derivatives_quality": lane_summary["dataset_derivatives_quality"],
        "feature_derivatives_quality_highlights": lane_summary["feature_derivatives_quality_highlights"],
        "experiment_ids": [str(item.get("experiment_id")) for item in experiments],
        "experiment_count": len(experiments),
        "passed_experiment_count": sum(1 for item in experiments if is_pass_experiment_status(item.get("experiment_status"))),
        "trainable_strategy_count": lane_summary["trainable_strategy_count"],
        "train_split_row_count_total": lane_summary["train_split_row_count_total"],
        "strategy_derivatives_quality_highlights": lane_summary["strategy_derivatives_quality_highlights"],
        "derivatives_sync_summary_path": str(derivatives_sync_summary_path),
        "derivatives_coverage_validation": derivatives_sync_summary["coverage_validation"],
        "derivatives_provider_cap_summary": derivatives_sync_summary["provider_cap_summary"],
        "derivatives_sync_warning_symbols": derivatives_sync_summary["warning_symbols"],
        "spot_gap_backfill_summary_path": str(spot_gap_backfill_summary.get("summary_path") or ""),
        "spot_gap_backfill_summary": {
            "attempted": bool(spot_gap_backfill_summary.get("attempted")),
            "rebuild_required": bool(spot_gap_backfill_summary.get("rebuild_required")),
            "status": str(spot_gap_backfill_summary.get("status") or "skipped"),
            "requested_profiles": list(spot_gap_backfill_summary.get("requested_profiles") or []),
            "requested_intervals": list(spot_gap_backfill_summary.get("requested_intervals") or []),
        },
        "aggregate_metrics": aggregate_metrics,
        "input_watermarks": {
            "quant_universe_generated_at_utc": universe_snapshot.get("generated_at_utc"),
            "quant_universe_freeze_produced_at_utc": universe_snapshot.get("produced_at_utc") or universe_snapshot.get("generated_at_utc"),
            "derivatives_sync_generated_at_utc": derivatives_sync.get("produced_at_utc") or derivatives_sync.get("generated_at_utc"),
            "ohlcv_latest_manifest_generated_at_utc": _latest_generated_at([entry["manifest_path"] for entry in datasets]),
        },
    }
    summary_payload["summary_hash"] = _stable_summary_hash(summary_payload)
    summary = with_evidence_metadata(
        summary_payload,
        evidence_family="quant_research_cycle",
        contract_version="quant_research_cycle.v2",
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )
    summary_path = cycle_root / "quant_cycle_summary.json"
    markdown_path = cycle_root / "quant_cycle_summary.md"
    write_json(summary_path, summary)
    markdown_path.write_text(_quant_cycle_markdown(summary) + "\n", encoding="utf-8")
    summary["quant_cycle_summary_path"] = str(summary_path)
    summary["summary_path"] = str(summary_path)
    summary["quant_cycle_markdown_path"] = str(markdown_path)
    summary["markdown_path"] = str(markdown_path)
    return summary


def _resolve_quant_local_timezone():
    return datetime.now().astimezone().tzinfo or UTC


def _quant_cycle_markdown(summary: dict[str, Any]) -> str:
    blockers = [str(item).strip() for item in list(summary.get("data_gap_blockers") or []) if str(item).strip()]
    blocked_strategies = [
        str(item).strip()
        for item in list(summary.get("blocked_strategy_ids") or [])
        if str(item).strip()
    ]
    return "\n".join(
        [
            "# Quant Cycle Summary",
            "",
            f"- As of: `{summary.get('as_of')}`",
            f"- Backend: `{summary.get('compiler_backend')}`",
            f"- Cycle mode: `{summary.get('cycle_mode')}`",
            f"- Readiness verdict: `{summary.get('readiness_verdict')}`",
            f"- Spot lane: `{summary.get('spot_provider_lane') or summary.get('spot_lane')}`",
            f"- Daily strategy count: `{summary.get('daily_strategy_count')}`",
            f"- Experiment count: `{summary.get('experiment_count')}`",
            f"- Passed experiment count: `{summary.get('passed_experiment_count')}`",
            f"- Cross-sectional executable subjects: `{summary.get('cross_sectional_executable_subject_count')}`",
            f"- Data gap blockers: `{', '.join(blockers) if blockers else 'none'}`",
            f"- Blocked strategy ids: `{', '.join(blocked_strategies) if blocked_strategies else 'none'}`",
            f"- Strategy manifest path: `{summary.get('strategy_manifest_path')}`",
            f"- Summary hash: `{summary.get('summary_hash')}`",
        ]
    )


def _count_values(items: list[dict[str, Any]], *, field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(field_name) or "").strip() or "missing"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _median_metric(
    *,
    experiments: list[dict[str, Any]],
    section: str,
    subfield: str,
    metric: str,
) -> float | None:
    values: list[float] = []
    for experiment in experiments:
        payload = dict(experiment.get(section) or {})
        metrics = dict(payload.get(subfield) or {})
        try:
            values.append(float(metrics.get(metric)))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return float(statistics.median(values))


def _stable_summary_hash(payload: dict[str, Any]) -> str:
    stable_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at_utc", "summary_hash", "input_watermarks"}
    }
    encoded = json.dumps(stable_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _local_date_for_timestamp(timestamp_utc: str) -> str | None:
    normalized = str(timestamp_utc or "").strip()
    if not normalized:
        return None
    try:
        local_dt = datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(_resolve_quant_local_timezone())
    except ValueError:
        return None
    return local_dt.date().isoformat()


def require_derivatives_sync_summary(*, as_of: str, derivatives_external_root: Path | None) -> tuple[dict[str, Any], Path]:
    resolved_root = resolve_external_derivatives_root(external_root=derivatives_external_root)
    archived_summary_path = as_of_sync_summary_path(external_root=resolved_root, as_of=as_of)
    if archived_summary_path.exists():
        summary = read_json(archived_summary_path)
        _validate_historical_derivatives_sync_summary(
            summary=summary,
            as_of=as_of,
            summary_path=archived_summary_path,
        )
        return summary, archived_summary_path
    summary_path = latest_sync_summary_path(external_root=resolved_root)
    if not summary_path.exists():
        raise FileNotFoundError(f"derivatives sync summary not found: {summary_path}")
    summary = read_json(summary_path)
    if str(summary.get("status")) != "success":
        raise RuntimeError(f"derivatives sync did not finish successfully: {summary.get('status')}")
    summary_as_of = str(summary.get("as_of") or "").strip()
    if summary_as_of:
        _validate_historical_derivatives_sync_summary(
            summary=summary,
            as_of=as_of,
            summary_path=summary_path,
        )
        return summary, summary_path
    generated_at = str(summary.get("produced_at_utc") or summary.get("generated_at_utc") or "").strip()
    generated_local_date = _local_date_for_timestamp(generated_at)
    current_local_date = datetime.now(_resolve_quant_local_timezone()).date().isoformat()
    allowed_local_dates = {as_of}
    if as_of < current_local_date:
        allowed_local_dates.add((datetime.strptime(as_of, "%Y-%m-%d").date() + timedelta(days=1)).isoformat())
    if generated_local_date not in allowed_local_dates:
        raise RuntimeError(
            "derivatives sync summary is stale for "
            f"{as_of}: {generated_at or 'missing generated_at_utc'} "
            f"(local_date={generated_local_date or 'unparseable'})"
        )
    return summary, summary_path


def _validate_historical_derivatives_sync_summary(
    *,
    summary: dict[str, Any],
    as_of: str,
    summary_path: Path,
) -> None:
    if str(summary.get("status")) != "success":
        raise RuntimeError(f"derivatives sync did not finish successfully: {summary.get('status')}")
    summary_as_of = str(summary.get("as_of") or "").strip()
    if summary_as_of != as_of:
        raise RuntimeError(
            f"derivatives sync summary as_of mismatch for {as_of}: "
            f"{summary_as_of or 'missing as_of'} ({summary_path})"
        )
    try:
        window_end_ms = int(summary.get("window_end_ms"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"derivatives sync summary missing valid window_end_ms: {summary_path}") from exc
    if window_end_ms <= 0 or window_end_ms > resolve_as_of_end_ms(as_of):
        raise RuntimeError(
            f"derivatives sync summary window_end_ms exceeds as_of={as_of}: "
            f"{window_end_ms} ({summary_path})"
        )
    symbols = [str(item).strip() for item in list(summary.get("symbols") or []) if str(item).strip()]
    intervals = [str(item).strip() for item in list(summary.get("intervals") or []) if str(item).strip()]
    if not symbols:
        raise RuntimeError(f"derivatives sync summary missing symbols: {summary_path}")
    if not intervals:
        raise RuntimeError(f"derivatives sync summary missing intervals: {summary_path}")
    if not isinstance(summary.get("coverage_validation"), dict):
        raise RuntimeError(f"derivatives sync summary missing coverage_validation: {summary_path}")
    if not isinstance(summary.get("provider_cap_summary"), dict):
        raise RuntimeError(f"derivatives sync summary missing provider_cap_summary: {summary_path}")


def _latest_generated_at(manifest_paths: list[str]) -> str | None:
    generated_values: list[str] = []
    for path_str in manifest_paths:
        payload = read_json(Path(path_str))
        candidate = str(payload.get("produced_at_utc") or payload.get("generated_at_utc") or "").strip()
        if candidate:
            generated_values.append(candidate)
    return max(generated_values) if generated_values else None


def _summarize_derivatives_sync(*, sync_summary: dict[str, Any]) -> dict[str, Any]:
    sync_results = [
        item
        for item in list(sync_summary.get("sync_results") or [])
        if isinstance(item, dict)
    ]
    warning_entries = [
        item
        for item in sync_results
        if str((item.get("coverage_validation") or {}).get("status", "")).strip() == "warning"
    ]
    warning_codes = sorted(
        {
            str(code)
            for item in warning_entries
            for code in list((item.get("coverage_validation") or {}).get("warning_codes") or [])
            if str(code).strip()
        }
    )
    top_level_validation = dict(sync_summary.get("coverage_validation") or {})
    warning_count = int(sync_summary.get("warning_count", len(warning_entries)) or 0)
    coverage_validation = {
        "status": str(top_level_validation.get("status") or ("warning" if warning_count > 0 else "ok")),
        "warning_count": warning_count,
        "warning_codes": list(top_level_validation.get("warning_codes") or warning_codes),
    }
    provider_cap_summary = sync_summary.get("provider_cap_summary")
    if not isinstance(provider_cap_summary, dict):
        provider_cap_summary = _build_derivatives_provider_cap_summary(sync_results=sync_results)
    warning_symbols = [
        {
            "symbol": str(item.get("symbol", "")),
            "interval": str(item.get("interval", "")),
            "warning_codes": list((item.get("coverage_validation") or {}).get("warning_codes") or []),
        }
        for item in warning_entries[:20]
    ]
    return {
        "coverage_validation": coverage_validation,
        "provider_cap_summary": provider_cap_summary,
        "warning_symbols": warning_symbols,
    }


def _build_derivatives_provider_cap_summary(*, sync_results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in sync_results:
        if str(item.get("status")) != "success":
            continue
        interval = str(item.get("interval", "")).strip()
        if not interval:
            continue
        grouped.setdefault(interval, []).append(item)
    summary: dict[str, Any] = {}
    for interval, items in grouped.items():
        funding_coverages = [
            float(((item.get("field_coverage") or {}).get("funding_rate") or {}).get("coverage_days", 0.0) or 0.0)
            for item in items
        ]
        open_interest_coverages = [
            float(((item.get("field_coverage") or {}).get("open_interest") or {}).get("coverage_days", 0.0) or 0.0)
            for item in items
        ]
        summary[interval] = {
            "requested_lookback_days": max(
                float((item.get("requested_window") or {}).get("lookback_days", 0.0) or 0.0)
                for item in items
            ),
            "funding_median_coverage_days": round(statistics.median(funding_coverages), 3) if funding_coverages else 0.0,
            "open_interest_median_coverage_days": (
                round(statistics.median(open_interest_coverages), 3) if open_interest_coverages else 0.0
            ),
            "open_interest_provider_capped_symbol_count": sum(
                1
                for item in items
                if bool(((item.get("field_coverage") or {}).get("open_interest") or {}).get("provider_capped"))
            ),
        }
    return summary


def _resolved_execution_cost_models() -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_execution_cost_model()
    return (
        resolve_execution_cost_model(contract=contract, scenario="base"),
        resolve_execution_cost_model(contract=contract, scenario="stress"),
    )


def _frictionless_summary(
    *,
    validation_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    walk_forward: dict[str, Any],
) -> dict[str, Any]:
    windows = [item for item in list(walk_forward.get("windows") or []) if isinstance(item, dict)]
    frictionless_sharpes = [
        float(dict(item.get("frictionless_metrics") or {}).get("sharpe", 0.0) or 0.0)
        for item in windows
    ]
    return {
        "validation_metrics": dict(validation_metrics.get("frictionless_metrics") or {}),
        "test_metrics": dict(test_metrics.get("frictionless_metrics") or {}),
        "walk_forward": {
            "window_count": int(walk_forward.get("window_count", 0) or 0),
            "median_oos_sharpe": statistics.median(frictionless_sharpes) if frictionless_sharpes else 0.0,
            "windows": [dict(item.get("frictionless_metrics") or {}) for item in windows],
        },
    }


def _execution_cost_model_data_gap_blockers(*metrics_payloads: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for payload in metrics_payloads:
        blockers.extend(str(item) for item in list(payload.get("data_gap_blockers") or []) if str(item).strip())
        for window in list(payload.get("windows") or []):
            if isinstance(window, dict):
                blockers.extend(str(item) for item in list(window.get("data_gap_blockers") or []) if str(item).strip())
    seen: set[str] = set()
    ordered: list[str] = []
    for blocker in blockers:
        if blocker not in seen:
            ordered.append(blocker)
            seen.add(blocker)
    return ordered


def build_quant_datasets(
    *,
    as_of: str,
    artifacts_root: Path,
    universe_snapshot: dict[str, Any],
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
    derivatives_sync: dict[str, Any] | None = None,
    source_commit_sha: str | None = None,
) -> list[dict[str, Any]]:
    resolved_source_commit_sha = str(source_commit_sha or "").strip() or required_source_commit_sha(repo_root=ROOT)
    data_readiness_contract = load_data_readiness_contract()
    provider_index = build_derivatives_provider_index(derivatives_sync)
    single_panel_raw = _build_single_asset_panel(
        universe_candidates=universe_candidates,
        as_of=as_of,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
    )
    cross_daily_panel_raw, cross_daily_missing_symbols_by_interval = _build_cross_sectional_daily_4h_panel(
        universe_candidates=universe_candidates,
        as_of=as_of,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
    )
    cross_intraday_panel_raw, cross_intraday_missing_symbols_by_interval = _build_cross_sectional_intraday_1h_panel(
        universe_candidates=universe_candidates,
        as_of=as_of,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
    )
    outputs: list[dict[str, Any]] = []
    for dataset_id, raw_panel, shape, dataset_profile, primary_interval, missing_spot_symbols_by_interval in (
        (
            f"{as_of}-single-asset-4h",
            single_panel_raw,
            "single_asset",
            SINGLE_ASSET_DATASET_PROFILE,
            "4h",
            {},
        ),
        (
            f"{as_of}-cross-sectional-daily-1d",
            cross_daily_panel_raw,
            "cross_sectional",
            CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
            "1d",
            cross_daily_missing_symbols_by_interval,
        ),
        (
            f"{as_of}-cross-sectional-intraday-1h",
            cross_intraday_panel_raw,
            "cross_sectional",
            CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE,
            "1h",
            cross_intraday_missing_symbols_by_interval,
        ),
    ):
        panel = raw_panel.copy()
        with pd.option_context("future.no_silent_downcasting", True):
            panel = panel.fillna(0.0)
        panel = panel.infer_objects(copy=False)
        derivatives_data_quality = summarize_dataset_derivatives_quality(
            panel=raw_panel,
            interval=primary_interval,
            provider_index=provider_index,
        )
        subject_count = int(raw_panel["subject"].nunique()) if not raw_panel.empty else 0
        data_readiness = build_dataset_data_readiness(
            dataset_id=dataset_id,
            shape=shape,
            subject_count=subject_count,
            requested_universe_count=len(universe_candidates),
            spot_ohlcv_external_root=spot_ohlcv_external_root,
            dataset_profile=dataset_profile,
            missing_spot_symbols_by_interval=missing_spot_symbols_by_interval,
            contract=data_readiness_contract,
        )
        research_dataset_fields = build_research_dataset_manifest_fields(
            as_of=as_of,
            dataset_id=dataset_id,
            dataset_profile=dataset_profile,
            primary_interval=primary_interval,
            raw_panel=raw_panel,
        )
        dataset_root = artifacts_root / "datasets" / dataset_id
        dataset_root.mkdir(parents=True, exist_ok=True)
        panel_path = dataset_root / "panel.csv.gz"
        panel.to_csv(panel_path, index=False, compression="gzip")
        dataset_panel_sha256 = sha256_dataframe_csv(panel)
        dataset_fingerprint = build_dataset_fingerprint(
            dataset_id=dataset_id,
            shape=shape,
            primary_interval=primary_interval,
            row_count=int(len(panel)),
            subjects=sorted({str(item) for item in panel["subject"].dropna().unique()}) if not panel.empty else [],
            min_timestamp_utc=str(panel["timestamp_utc"].min()) if not panel.empty else None,
            max_timestamp_utc=str(panel["timestamp_utc"].max()) if not panel.empty else None,
            columns=list(panel.columns),
            dataset_panel_sha256=dataset_panel_sha256,
        )
        manifest = with_evidence_metadata(
            {
            "generated_at_utc": utc_now(),
            "dataset_id": dataset_id,
            "shape": shape,
            "dataset_profile": dataset_profile,
            "primary_interval": primary_interval,
            "row_count": int(len(panel)),
            "subjects": sorted({str(item) for item in panel["subject"].dropna().unique()}) if not panel.empty else [],
            "min_timestamp_utc": str(panel["timestamp_utc"].min()) if not panel.empty else None,
            "max_timestamp_utc": str(panel["timestamp_utc"].max()) if not panel.empty else None,
            "columns": list(panel.columns),
            "dataset_panel_sha256": dataset_panel_sha256,
            "dataset_fingerprint": dataset_fingerprint,
            "universe_definition_id": str(universe_snapshot.get("universe_definition_id") or ""),
            "universe_contract_version": str(universe_snapshot.get("universe_contract_version") or ""),
            "universe_snapshot_path": portable_path(Path(str(universe_snapshot["path"])), repo_root=ROOT),
            "universe_selection_policy_hash": str(universe_snapshot.get("universe_selection_policy_hash") or ""),
            "data_readiness": data_readiness,
            "derivatives_data_quality": derivatives_data_quality,
            **research_dataset_fields,
            },
            evidence_family=QUANT_DATASET_MANIFEST_ARTIFACT_FAMILY,
            contract_version=QUANT_DATASET_MANIFEST_CONTRACT_VERSION,
            repo_root=ROOT,
            source_commit_sha=resolved_source_commit_sha,
            require_source_commit_sha=True,
        )
        manifest_path = dataset_root / "dataset_manifest.json"
        write_json(manifest_path, manifest)
        outputs.append(
            {
                "dataset_id": dataset_id,
                "shape": shape,
                "dataset_profile": dataset_profile,
                "primary_interval": primary_interval,
                "panel_path": str(panel_path),
                "manifest_path": str(manifest_path),
                "dataframe": panel,
                "raw_dataframe": raw_panel,
                "data_readiness": data_readiness,
                "derivatives_data_quality": derivatives_data_quality,
                "source_commit_sha": resolved_source_commit_sha,
                "dataset_panel_sha256": dataset_panel_sha256,
                "dataset_fingerprint": dataset_fingerprint,
                "universe_definition_id": str(universe_snapshot.get("universe_definition_id") or ""),
                "universe_contract_version": str(universe_snapshot.get("universe_contract_version") or ""),
                "universe_snapshot_path": str(universe_snapshot["path"]),
                "universe_selection_policy_hash": str(universe_snapshot.get("universe_selection_policy_hash") or ""),
                "subject_count": int(research_dataset_fields.get("subject_count", subject_count) or subject_count),
                "research_dataset": dict(research_dataset_fields.get("research_dataset") or {}),
            }
        )
    return outputs


def _normalize_news_subjects(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, np.ndarray):
        items = value.tolist()
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = [str(value)]
    out: list[str] = []
    for item in items:
        token = str(item or "").strip().upper()
        if token and token not in {"NAN", "NONE", "NULL"}:
            out.append(token)
    return sorted(set(out))


def _parse_news_effective_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _bounded_news_decay_days(value: Any) -> int:
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return 1
    return max(1, min(int(number), 30))


def _build_news_veto_daily_flags_from_scores(
    *,
    scored: pd.DataFrame,
    veto_column: str,
    horizon_column: str,
    effective_time_column: str,
    start_date: date,
    end_date: date,
    output_column: str,
) -> pd.DataFrame:
    required = {"currencies", effective_time_column, veto_column, horizon_column}
    missing = [column for column in required if column not in scored.columns]
    if missing:
        return pd.DataFrame(columns=["subject", "date_utc", output_column])
    flagged = scored.loc[scored[veto_column].fillna(False).astype(bool)].copy()
    if flagged.empty:
        return pd.DataFrame(columns=["subject", "date_utc", output_column])

    rows: list[dict[str, Any]] = []
    for row in flagged.itertuples(index=False):
        subjects = _normalize_news_subjects(getattr(row, "currencies"))
        effective_date = _parse_news_effective_date(getattr(row, effective_time_column))
        if not subjects or effective_date is None:
            continue
        active_start = max(start_date, effective_date)
        active_end = min(
            end_date,
            effective_date + timedelta(days=_bounded_news_decay_days(getattr(row, horizon_column)) - 1),
        )
        if active_end < active_start:
            continue
        dates = pd.date_range(active_start.isoformat(), active_end.isoformat(), freq="D")
        for subject in subjects:
            for active_date in dates:
                rows.append(
                    {
                        "subject": subject,
                        "date_utc": active_date.date().isoformat(),
                        output_column: 1,
                    }
                )
    if not rows:
        return pd.DataFrame(columns=["subject", "date_utc", output_column])
    daily = pd.DataFrame(rows)
    return (
        daily.groupby(["subject", "date_utc"], as_index=False)[output_column]
        .max()
        .sort_values(["date_utc", "subject"])
        .reset_index(drop=True)
    )


def _augment_cross_sectional_daily_features_with_news_veto(*, features: pd.DataFrame, as_of: str) -> pd.DataFrame:
    augmented = features.copy()
    for column in (
        "news_short_veto_mini_flag",
        "news_short_veto_adjudicated_flag",
        "news_short_veto_adjudicated_do_not_fill_multiplier",
        "news_short_veto_adjudicated_reduced_exposure_multiplier",
    ):
        if column not in augmented.columns:
            augmented[column] = 0
    if augmented.empty or "date_utc" not in augmented.columns or "subject" not in augmented.columns:
        return augmented
    date_series = pd.to_datetime(augmented["date_utc"], utc=True, errors="coerce").dropna()
    if date_series.empty:
        return augmented
    start_date = date_series.min().date()
    end_date = date_series.max().date()
    dataset_dir = ROOT / "artifacts" / "quant_research" / "datasets" / f"{as_of}-crypto-news-dataset"
    mini_path = dataset_dir / "llm_structured_scores.parquet"
    adjudicated_path = dataset_dir / "llm_structured_scores_adjudicated_priority_ge_8.parquet"
    if not mini_path.exists() or not adjudicated_path.exists():
        augmented["news_short_veto_mini_flag"] = pd.to_numeric(
            augmented["news_short_veto_mini_flag"], errors="coerce"
        ).fillna(0).astype("int8")
        augmented["news_short_veto_adjudicated_flag"] = pd.to_numeric(
            augmented["news_short_veto_adjudicated_flag"], errors="coerce"
        ).fillna(0).astype("int8")
        adjudicated_flag = pd.to_numeric(
            augmented["news_short_veto_adjudicated_flag"], errors="coerce"
        ).fillna(0).astype("int8")
        augmented["news_short_veto_adjudicated_do_not_fill_multiplier"] = (
            1.0 - adjudicated_flag.astype("float64")
        ).clip(lower=0.0, upper=1.0)
        augmented["news_short_veto_adjudicated_reduced_exposure_multiplier"] = np.where(
            adjudicated_flag.to_numpy(dtype="int8") > 0,
            0.5,
            1.0,
        ).astype("float64")
        return augmented

    mini = pd.read_parquet(mini_path)
    adjudicated = pd.read_parquet(adjudicated_path)
    mini_daily = _build_news_veto_daily_flags_from_scores(
        scored=mini,
        veto_column="short_veto_flag",
        horizon_column="decay_horizon_days",
        effective_time_column="research_effective_at_utc",
        start_date=start_date,
        end_date=end_date,
        output_column="news_short_veto_mini_flag",
    )
    adjudicated_daily = _build_news_veto_daily_flags_from_scores(
        scored=adjudicated,
        veto_column="final_short_veto_flag",
        horizon_column="final_decay_horizon_days",
        effective_time_column="research_effective_at_utc",
        start_date=start_date,
        end_date=end_date,
        output_column="news_short_veto_adjudicated_flag",
    )
    augmented = augmented.drop(columns=["news_short_veto_mini_flag", "news_short_veto_adjudicated_flag"], errors="ignore")
    augmented = augmented.merge(mini_daily, on=["subject", "date_utc"], how="left")
    augmented = augmented.merge(adjudicated_daily, on=["subject", "date_utc"], how="left")
    augmented["news_short_veto_mini_flag"] = pd.to_numeric(
        augmented["news_short_veto_mini_flag"], errors="coerce"
    ).fillna(0).astype("int8")
    augmented["news_short_veto_adjudicated_flag"] = pd.to_numeric(
        augmented["news_short_veto_adjudicated_flag"], errors="coerce"
    ).fillna(0).astype("int8")
    adjudicated_flag = pd.to_numeric(
        augmented["news_short_veto_adjudicated_flag"], errors="coerce"
    ).fillna(0).astype("int8")
    augmented["news_short_veto_adjudicated_do_not_fill_multiplier"] = (
        1.0 - adjudicated_flag.astype("float64")
    ).clip(lower=0.0, upper=1.0)
    augmented["news_short_veto_adjudicated_reduced_exposure_multiplier"] = np.where(
        adjudicated_flag.to_numpy(dtype="int8") > 0,
        0.5,
        1.0,
    ).astype("float64")
    return augmented


def build_quant_feature_sets(
    *,
    artifacts_root: Path,
    datasets: list[dict[str, Any]],
    derivatives_sync: dict[str, Any] | None = None,
    source_commit_sha: str | None = None,
    cross_sectional_daily_target_horizons: tuple[int, ...] | None = None,
    cross_sectional_daily_label_contract_ids: tuple[str, ...] | None = None,
    feature_set_version: str = "v1",
) -> list[dict[str, Any]]:
    resolved_source_commit_sha = str(source_commit_sha or "").strip() or required_source_commit_sha(repo_root=ROOT)
    provider_index = build_derivatives_provider_index(derivatives_sync)
    outputs: list[dict[str, Any]] = []
    resolved_cross_sectional_daily_label_contract_ids = tuple(
        str(item).strip()
        for item in (
            cross_sectional_daily_label_contract_ids
            or (DEFAULT_LABEL_CONTRACT_ID,)
        )
        if str(item).strip()
    ) or (DEFAULT_LABEL_CONTRACT_ID,)
    for dataset in datasets:
        panel = dataset["raw_dataframe"].copy()
        bundle_specs: list[tuple[dict[str, Any], str, str | None]] = []
        if dataset["shape"] == "single_asset":
            bundle_specs.append(
                (
                    build_single_asset_feature_bundle(panel, provider_index=provider_index),
                    f"{dataset['dataset_id']}-features-{feature_set_version}",
                    None,
                )
            )
        elif str(dataset.get("dataset_profile") or "") == CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE:
            bundle_specs.append(
                (
                    build_cross_sectional_intraday_feature_bundle(panel, provider_index=provider_index),
                    f"{dataset['dataset_id']}-features-{feature_set_version}",
                    None,
                )
            )
        elif (
            str(dataset.get("dataset_profile") or "") == CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE
            and cross_sectional_daily_target_horizons
        ):
            for target_horizon_bars in cross_sectional_daily_target_horizons:
                resolved_target_horizon_bars = int(target_horizon_bars)
                horizon_id = f"h{resolved_target_horizon_bars}d"
                for label_contract_id in resolved_cross_sectional_daily_label_contract_ids:
                    feature_set_id = f"{dataset['dataset_id']}-{horizon_id}"
                    if label_contract_id != DEFAULT_LABEL_CONTRACT_ID:
                        feature_set_id = (
                            f"{feature_set_id}-{_label_contract_feature_set_suffix(label_contract_id)}"
                        )
                    feature_set_id = f"{feature_set_id}-features-{feature_set_version}"
                    bundle_specs.append(
                        (
                            build_cross_sectional_feature_bundle(
                                panel,
                                interval=str(dataset.get("primary_interval") or "1d"),
                                target_shift_bars=resolved_target_horizon_bars,
                                label_contract_id=label_contract_id,
                                provider_index=provider_index,
                            ),
                            feature_set_id,
                            horizon_id,
                        )
                    )
        else:
            bundle_specs.append(
                (
                    build_cross_sectional_feature_bundle(
                        panel,
                        interval=str(dataset.get("primary_interval") or "1d"),
                        provider_index=provider_index,
                    ),
                    f"{dataset['dataset_id']}-features-{feature_set_version}",
                    None,
                )
            )
        for bundle, feature_set_id, horizon_id in bundle_specs:
            features = bundle["dataframe"]
            if str(dataset.get("dataset_profile") or "") == CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE:
                dataset_id = str(dataset.get("dataset_id") or "")
                as_of = dataset_id.split("-cross-sectional-daily-1d", 1)[0] or dataset_id
                features = _augment_cross_sectional_daily_features_with_news_veto(features=features, as_of=as_of)
                m3_3_news_artifact = str(os.environ.get("ENHENGCLAW_M3_3_EVENT_STATE_NEWS_ARTIFACT") or "").strip()
                if m3_3_news_artifact:
                    features = add_m3_3_event_state_features(
                        features,
                        news_artifact=Path(m3_3_news_artifact),
                        lookback_days=int(os.environ.get("ENHENGCLAW_M3_3_EVENT_LOOKBACK_DAYS") or 10),
                    )
            feature_root = artifacts_root / "features" / feature_set_id
            feature_root.mkdir(parents=True, exist_ok=True)
            label_artifact = build_label_artifact(
                features=features,
                feature_root=feature_root,
                feature_set_id=feature_set_id,
                dataset_id=str(dataset["dataset_id"]),
                shape=str(dataset["shape"]),
                dataset_profile=str(dataset.get("dataset_profile") or ""),
                label_contract_id=str(bundle.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID),
                source_commit_sha=resolved_source_commit_sha,
            )
            features_path = feature_root / "features.csv.gz"
            features.to_csv(features_path, index=False, compression="gzip")
            split_realization_contract = resolve_split_realization_contract(
                contract=dict(bundle.get("split_realization_contract") or {}),
                shape=str(dataset["shape"]),
                bar_interval_ms=infer_interval_ms(features["timestamp_ms"]) if not features.empty else None,
            )
            label_columns = {
                str(column).strip()
                for column in [
                    *list(bundle.get("label_columns") or []),
                    *list(label_artifact.get("label_columns") or []),
                ]
                if str(column).strip()
            }
            available_numeric_columns = sorted(
                column
                for column in features.columns
                if column not in NUMERIC_EXCLUDE
                and features[column].dtype.kind in {"i", "u", "f", "b"}
                and column not in label_columns
            )
            feature_admission = classify_feature_manifest_columns(available_numeric_columns)
            feature_quality_frame = build_feature_quality_frame(
                feature_frame=features,
                tracked_feature_columns=feature_admission["numeric_feature_columns"],
                derivatives_quality_frame=bundle["quality_frame"],
            )
            feature_quality = summarize_feature_quality(
                feature_quality_frame=feature_quality_frame,
                tracked_feature_columns=feature_admission["numeric_feature_columns"],
            )
            feature_matrix_sha256 = sha256_dataframe_csv(features)
            dataset_manifest_path = portable_path(Path(str(dataset["manifest_path"])), repo_root=ROOT)
            feature_hash = build_feature_hash(
                feature_set_id=feature_set_id,
                dataset_id=str(dataset["dataset_id"]),
                shape=str(dataset["shape"]),
                row_count=int(len(features)),
                numeric_feature_columns=feature_admission["numeric_feature_columns"],
                excluded_numeric_columns=feature_admission["excluded_numeric_columns"],
                feature_admission_policy_contract_version=str(
                    dict(feature_admission["feature_admission_policy"]).get("contract_version") or ""
                ),
                split_realization_contract=split_realization_contract,
                feature_matrix_sha256=feature_matrix_sha256,
            )
            manifest = with_evidence_metadata(
                {
                "generated_at_utc": utc_now(),
                "feature_set_id": feature_set_id,
                "dataset_id": dataset["dataset_id"],
                "shape": dataset["shape"],
                "dataset_profile": str(dataset.get("dataset_profile") or ""),
                "row_count": int(len(features)),
                "dataset_manifest_path": dataset_manifest_path,
                "dataset_fingerprint": str(dataset.get("dataset_fingerprint") or ""),
                "universe_definition_id": str(dataset.get("universe_definition_id") or ""),
                "universe_contract_version": str(dataset.get("universe_contract_version") or ""),
                "universe_snapshot_path": portable_path(Path(str(dataset.get("universe_snapshot_path") or "")), repo_root=ROOT)
                if str(dataset.get("universe_snapshot_path") or "").strip()
                else "",
                "universe_selection_policy_hash": str(dataset.get("universe_selection_policy_hash") or ""),
                "available_numeric_columns": feature_admission["available_numeric_columns"],
                "numeric_feature_columns": feature_admission["numeric_feature_columns"],
                "excluded_numeric_columns": feature_admission["excluded_numeric_columns"],
                "feature_admission_policy": feature_admission["feature_admission_policy"],
                "feature_matrix_sha256": feature_matrix_sha256,
                "feature_hash": feature_hash,
                "features_path": portable_path(features_path, repo_root=ROOT),
                "label_contract_id": str(bundle.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID),
                "target_column": str(label_artifact.get("target_column") or bundle.get("target_column") or "target_up"),
                "forward_return_column": str(
                    label_artifact.get("forward_return_column")
                    or bundle.get("forward_return_column")
                    or "target_forward_return"
                ),
                "raw_forward_return_column": str(label_artifact.get("raw_forward_return_column") or ""),
                "labels_path": portable_path(Path(str(label_artifact["labels_path"])), repo_root=ROOT),
                "label_manifest_path": portable_path(Path(str(label_artifact["label_manifest_path"])), repo_root=ROOT),
                "label_hash": str(label_artifact.get("label_hash") or ""),
                "neutral_zone": dict(label_artifact.get("neutral_zone") or {}),
                "cost_adjustment": dict(label_artifact.get("cost_adjustment") or {}),
                "label_horizon_bars": int(split_realization_contract["target_horizon_bars"]),
                "realization_step_bars": int(split_realization_contract["realization_step_bars"]),
                "partition_gap_bars": int(split_realization_contract["partition_gap_bars"]),
                "bar_interval_ms": int(split_realization_contract["bar_interval_ms"]),
                "split_realization_contract": split_realization_contract,
                "feature_quality": feature_quality,
                "derivatives_feature_quality": bundle["derivatives_feature_quality"],
                "horizon_id": str(horizon_id or ""),
                },
                evidence_family=QUANT_FEATURE_MANIFEST_ARTIFACT_FAMILY,
                contract_version=QUANT_FEATURE_MANIFEST_CONTRACT_VERSION,
                repo_root=ROOT,
                source_commit_sha=resolved_source_commit_sha,
                require_source_commit_sha=True,
            )
            manifest_path = feature_root / "feature_manifest.json"
            write_json(manifest_path, manifest)
            outputs.append(
                {
                    "feature_set_id": feature_set_id,
                    "dataset_id": dataset["dataset_id"],
                    "shape": dataset["shape"],
                    "dataset_profile": str(dataset.get("dataset_profile") or ""),
                    "features_path": str(features_path),
                    "manifest_path": str(manifest_path),
                    "dataframe": features,
                    "available_numeric_columns": feature_admission["available_numeric_columns"],
                    "numeric_feature_columns": feature_admission["numeric_feature_columns"],
                    "excluded_numeric_columns": feature_admission["excluded_numeric_columns"],
                    "feature_admission_policy": feature_admission["feature_admission_policy"],
                    "feature_quality_frame": feature_quality_frame,
                    "feature_quality": feature_quality,
                    "derivatives_quality_frame": bundle["quality_frame"],
                    "derivatives_feature_quality": bundle["derivatives_feature_quality"],
                    "split_realization_contract": split_realization_contract,
                    "dataset_data_readiness": dict(dataset.get("data_readiness") or {}),
                    "source_commit_sha": resolved_source_commit_sha,
                    "dataset_fingerprint": str(dataset.get("dataset_fingerprint") or ""),
                    "dataset_manifest_path": str(dataset["manifest_path"]),
                    "feature_matrix_sha256": feature_matrix_sha256,
                    "feature_hash": feature_hash,
                    "universe_definition_id": str(dataset.get("universe_definition_id") or ""),
                    "universe_contract_version": str(dataset.get("universe_contract_version") or ""),
                    "universe_snapshot_path": str(dataset.get("universe_snapshot_path") or ""),
                    "universe_selection_policy_hash": str(dataset.get("universe_selection_policy_hash") or ""),
                    "label_contract_id": str(bundle.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID),
                    "target_column": str(label_artifact.get("target_column") or bundle.get("target_column") or "target_up"),
                    "forward_return_column": str(
                        label_artifact.get("forward_return_column")
                        or bundle.get("forward_return_column")
                        or "target_forward_return"
                    ),
                    "raw_forward_return_column": str(label_artifact.get("raw_forward_return_column") or ""),
                    "labels_path": str(label_artifact["labels_path"]),
                    "label_manifest_path": str(label_artifact["label_manifest_path"]),
                    "label_hash": str(label_artifact.get("label_hash") or ""),
                    "neutral_zone": dict(label_artifact.get("neutral_zone") or {}),
                    "cost_adjustment": dict(label_artifact.get("cost_adjustment") or {}),
                    "target_horizon_bars": int(split_realization_contract["target_horizon_bars"]),
                    "horizon_id": str(horizon_id or ""),
                    "dataset_research_dataset": dict(dataset.get("research_dataset") or {}),
                }
            )
    return outputs


def _label_contract_feature_set_suffix(label_contract_id: str) -> str:
    if label_contract_id == EXECUTION_ALIGNED_LABEL_CONTRACT_ID:
        return "exec-aligned-label-v1"
    if label_contract_id == PARTICIPATION_DRIFT_LABEL_CONTRACT_ID:
        return "pdrift-label-v1"
    return "label-contract"


def _apply_spot_gap_backfill_for_cross_sectional_profiles(
    *,
    as_of: str,
    cycle_root: Path,
    quant_input_root: Path,
    artifacts_root: Path,
    strategy_manifest: dict[str, Any],
    datasets: list[dict[str, Any]],
    universe_snapshot: dict[str, Any],
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
    derivatives_sync: dict[str, Any] | None,
    source_commit_sha: str,
    auto_api_gap_backfill: bool,
    strategy_id_allowlist: list[str] | None,
) -> dict[str, Any]:
    summary_path = cycle_root / "spot_gap_backfill_summary.json"
    allowlist = {
        str(item).strip()
        for item in list(strategy_id_allowlist or [])
        if str(item).strip()
    }
    requested_profiles = sorted(
        {
            normalize_dataset_profile(
                shape=str(entry.get("shape") or "").strip(),
                dataset_profile=str(entry.get("dataset_profile") or "").strip() or None,
            )
            for entry in list(strategy_manifest.get("entries") or [])
            if isinstance(entry, dict)
            and bool(entry.get("enabled"))
            and str(entry.get("shape") or "").strip() == "cross_sectional"
            and (
                not allowlist
                or str(entry.get("strategy_id") or "").strip() in allowlist
            )
        }
    )
    summary: dict[str, Any] = {
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "attempted": False,
        "status": "skipped",
        "requested_profiles": requested_profiles,
        "requested_intervals": [],
        "rebuild_required": False,
        "lanes": [],
        "summary_path": str(summary_path),
    }
    if not auto_api_gap_backfill:
        summary["status"] = "disabled"
        write_json(summary_path, summary)
        return summary
    if spot_ohlcv_external_root is None or not requested_profiles:
        summary["status"] = "skipped"
        write_json(summary_path, summary)
        return summary

    backfill_requests: dict[str, set[str]] = {}
    for dataset in datasets:
        dataset_profile = str(dataset.get("dataset_profile") or "").strip()
        if dataset_profile not in requested_profiles:
            continue
        readiness = dict(dataset.get("data_readiness") or {})
        blockers = {
            str(item).strip()
            for item in list(readiness.get("data_gap_blockers") or [])
            if str(item).strip()
        }
        missing_by_interval = dict(
            dict(readiness.get("spot_subject_coverage") or {}).get("missing_spot_symbols_by_interval") or {}
        )
        lane_summary = {
            "dataset_id": str(dataset.get("dataset_id") or ""),
            "dataset_profile": dataset_profile,
            "blocked": bool(blockers),
            "blockers": sorted(blockers),
            "missing_spot_symbols_by_interval": missing_by_interval,
        }
        summary["lanes"].append(lane_summary)
        if not blockers:
            continue
        for interval, symbols in missing_by_interval.items():
            normalized_interval = str(interval).strip()
            if not normalized_interval:
                continue
            bucket = backfill_requests.setdefault(normalized_interval, set())
            bucket.update(
                str(symbol).strip().upper()
                for symbol in list(symbols or [])
                if str(symbol).strip()
            )

    if not backfill_requests:
        write_json(summary_path, summary)
        return summary

    summary["attempted"] = True
    summary["status"] = "success"
    summary["requested_intervals"] = sorted(backfill_requests)
    attempts: list[dict[str, Any]] = []
    for interval in sorted(backfill_requests):
        symbols = sorted(backfill_requests[interval])
        attempt_summary: dict[str, Any] = {
            "interval": interval,
            "spot_symbol_count": len(symbols),
            "spot_symbols": symbols,
        }
        try:
            sync_summary = run_quant_coinapi_spot_sync(
                as_of=as_of,
                mode="bootstrap",
                quant_input_root=quant_input_root,
                external_root=spot_ohlcv_external_root,
                spot_symbols=symbols,
                required_intervals=(interval,),
            )
            attempt_summary["status"] = str(sync_summary.get("status") or "success")
            attempt_summary["summary"] = sync_summary
            summary["rebuild_required"] = True
        except Exception as exc:
            attempt_summary["status"] = "error"
            attempt_summary["error"] = str(exc)
            summary["status"] = "partial_error"
        attempts.append(attempt_summary)
    summary["attempts"] = attempts
    if summary["rebuild_required"]:
        rerun_datasets = build_quant_datasets(
            as_of=as_of,
            artifacts_root=artifacts_root,
            universe_snapshot=universe_snapshot,
            universe_candidates=universe_candidates,
            ohlcv_external_root=ohlcv_external_root,
            spot_ohlcv_external_root=spot_ohlcv_external_root,
            derivatives_external_root=derivatives_external_root,
            derivatives_sync=derivatives_sync,
            source_commit_sha=source_commit_sha,
        )
        summary["post_backfill_dataset_subject_counts"] = {
            str(dataset["dataset_id"]): int(dataset["dataframe"]["subject"].nunique()) if not dataset["dataframe"].empty else 0
            for dataset in rerun_datasets
        }
        summary["post_backfill_data_gap_blockers"] = {
            str(dataset["dataset_id"]): list(dict(dataset.get("data_readiness") or {}).get("data_gap_blockers") or [])
            for dataset in rerun_datasets
        }
    write_json(summary_path, summary)
    return summary


def _quant_lane_summary(
    *,
    datasets: list[dict[str, Any]],
    feature_sets: list[dict[str, Any]],
    experiments: list[dict[str, Any]],
    spot_ohlcv_external_root: Path | None,
    selection_blocked_strategy_ids: list[str] | None = None,
    selection_data_gap_blockers: list[str] | None = None,
) -> dict[str, Any]:
    dataset_subject_counts = {
        str(dataset["dataset_id"]): int(dataset["dataframe"]["subject"].nunique()) if not dataset["dataframe"].empty else 0
        for dataset in datasets
    }
    dataset_row_counts = {
        str(dataset["dataset_id"]): int(len(dataset["dataframe"]))
        for dataset in datasets
    }
    dataset_data_readiness = {
        str(dataset["dataset_id"]): dict(dataset.get("data_readiness") or {})
        for dataset in datasets
    }
    feature_row_counts = {
        str(feature_set["feature_set_id"]): int(len(feature_set["dataframe"]))
        for feature_set in feature_sets
    }
    trainable_experiments = [
        experiment for experiment in experiments
        if bool(experiment.get("is_trainable"))
    ]
    blocked_strategy_ids = sorted(
        {
            str(experiment.get("strategy_id") or "")
            for experiment in experiments
            if str(experiment.get("strategy_id") or "").strip()
            and list(experiment.get("data_gap_blockers") or [])
        }
        | {
            str(strategy_id)
            for strategy_id in list(selection_blocked_strategy_ids or [])
            if str(strategy_id).strip()
        }
        | {
            str(strategy_id)
            for readiness in dataset_data_readiness.values()
            for strategy_id in list(dict(readiness).get("blocked_strategy_ids") or [])
            if str(strategy_id).strip()
        }
    )
    data_gap_blockers = sorted(
        {
            str(blocker)
            for experiment in experiments
            for blocker in list(experiment.get("data_gap_blockers") or [])
            if str(blocker).strip()
        }
        | {
            str(blocker)
            for readiness in dataset_data_readiness.values()
            for blocker in list(dict(readiness).get("data_gap_blockers") or [])
            if str(blocker).strip()
        }
        | {
            str(blocker)
            for blocker in list(selection_data_gap_blockers or [])
            if str(blocker).strip()
        }
    )
    spot_subject_coverage = {
        dataset_id: dict(readiness.get("spot_subject_coverage") or {})
        for dataset_id, readiness in dataset_data_readiness.items()
    }
    cross_sectional_executable_subject_count = 0
    cross_sectional_dataset_subject_counts: dict[str, int] = {}
    for dataset_id, readiness in dataset_data_readiness.items():
        if str(dict(readiness).get("dataset_profile") or "") in {
            CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
            CROSS_SECTIONAL_INTRADAY_1H_DATASET_PROFILE,
        }:
            cross_sectional_dataset_subject_counts[dataset_id] = int(
                readiness.get("cross_sectional_executable_subject_count") or 0
            )
        if str(dict(readiness).get("dataset_profile") or "") == CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE:
            cross_sectional_executable_subject_count = int(readiness.get("cross_sectional_executable_subject_count") or 0)
    return {
        "spot_provider_lane": spot_provider_lane(spot_ohlcv_external_root=spot_ohlcv_external_root),
        "dataset_subject_counts": dataset_subject_counts,
        "dataset_row_counts": dataset_row_counts,
        "spot_subject_coverage": spot_subject_coverage,
        "cross_sectional_executable_subject_count": cross_sectional_executable_subject_count,
        "cross_sectional_dataset_subject_counts": cross_sectional_dataset_subject_counts,
        "blocked_strategy_ids": blocked_strategy_ids,
        "data_gap_blockers": data_gap_blockers,
        "dataset_derivatives_quality": {
            str(dataset["dataset_id"]): dict(dataset.get("derivatives_data_quality") or {})
            for dataset in datasets
        },
        "feature_row_counts": feature_row_counts,
        "feature_derivatives_quality_highlights": feature_derivatives_quality_highlights(feature_sets),
        "trainable_strategy_count": len(trainable_experiments),
        "train_split_row_count_total": sum(
            int((experiment.get("split_row_counts") or {}).get("train", 0) or 0)
            for experiment in trainable_experiments
        ),
        "strategy_derivatives_quality_highlights": aggregate_strategy_derivatives_quality(experiments),
    }


def _build_single_asset_panel(
    *,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    as_of: str,
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
) -> pd.DataFrame:
    as_of_end = resolve_as_of_end_ms(as_of)
    frames: list[pd.DataFrame] = []
    for candidate in universe_candidates:
        spot4h = load_ohlcv_frame(
            symbol=candidate.spot_symbol,
            market_type="spot",
            interval="4h",
            external_root=ohlcv_external_root,
            spot_external_root=spot_ohlcv_external_root,
            end_time_ms=as_of_end,
        )
        spot1d = load_ohlcv_frame(
            symbol=candidate.spot_symbol,
            market_type="spot",
            interval="1d",
            external_root=ohlcv_external_root,
            spot_external_root=spot_ohlcv_external_root,
            end_time_ms=as_of_end,
        )
        if spot4h.empty or spot1d.empty:
            continue
        perp4h = (
        load_ohlcv_frame(
                symbol=str(candidate.usdm_symbol),
                market_type="usdm_perp",
                interval="4h",
                external_root=ohlcv_external_root,
                end_time_ms=as_of_end,
            )
            if candidate.usdm_symbol
            else pd.DataFrame()
        )
        deriv4h = (
        load_derivatives_frame(
                symbol=str(candidate.usdm_symbol),
                interval="4h",
                external_root=derivatives_external_root,
                end_time_ms=as_of_end,
            )
            if candidate.usdm_symbol
            else pd.DataFrame()
        )
        daily_context = spot1d[["open_time_ms", "close", "quote_volume"]].rename(
            columns={"open_time_ms": "daily_open_time_ms", "close": "daily_close", "quote_volume": "daily_quote_volume"}
        )
        base = spot4h.rename(
            columns={
                "open": "spot_open",
                "high": "spot_high",
                "low": "spot_low",
                "close": "spot_close",
                "volume": "spot_volume",
                "quote_volume": "spot_quote_volume",
            }
        )[["open_time_ms", "close_time_ms", "spot_open", "spot_high", "spot_low", "spot_close", "spot_volume", "spot_quote_volume"]]
        if not daily_context.empty:
            base = pd.merge_asof(
                base.sort_values("open_time_ms"),
                daily_context.sort_values("daily_open_time_ms"),
                left_on="open_time_ms",
                right_on="daily_open_time_ms",
                direction="backward",
            )
        if not perp4h.empty:
            base = base.merge(
                perp4h.rename(
                    columns={"close": "perp_close", "volume": "perp_volume", "quote_volume": "perp_quote_volume_usd"}
                )[["open_time_ms", "perp_close", "perp_volume", "perp_quote_volume_usd"]],
                on="open_time_ms",
                how="left",
            )
        else:
            base["perp_close"] = np.nan
            base["perp_volume"] = np.nan
            base["perp_quote_volume_usd"] = np.nan
        if not deriv4h.empty:
            base = base.merge(
                deriv4h[_derivatives_panel_columns(deriv4h)].rename(
                    columns={
                        "perp_close": "derivatives_perp_close",
                        "perp_quote_volume_usd": "derivatives_perp_quote_volume_usd",
                    }
                ),
                on="open_time_ms",
                how="left",
            )
        else:
            base["funding_rate"] = np.nan
            base["funding_sample_count"] = np.nan
            base["open_interest"] = np.nan
            base["open_interest_value"] = np.nan
            base["derivatives_perp_close"] = np.nan
            base["derivatives_perp_quote_volume_usd"] = np.nan
        if "derivatives_perp_close" in base.columns:
            base["perp_close"] = base["perp_close"].combine_first(base["derivatives_perp_close"])
            base.drop(columns=["derivatives_perp_close"], inplace=True)
        if "derivatives_perp_quote_volume_usd" in base.columns:
            base["perp_quote_volume_usd"] = base["perp_quote_volume_usd"].combine_first(
                base["derivatives_perp_quote_volume_usd"]
            )
            base.drop(columns=["derivatives_perp_quote_volume_usd"], inplace=True)
        base["basis_proxy"] = np.where(base["perp_close"].notna() & base["spot_close"].ne(0), (base["perp_close"] - base["spot_close"]) / base["spot_close"], np.nan)
        base["timestamp_ms"] = base["open_time_ms"].astype("int64")
        base["timestamp_utc"] = pd.to_datetime(base["timestamp_ms"], unit="ms", utc=True).astype(str)
        base["subject"] = candidate.subject
        base["liquidity_bucket"] = candidate.liquidity_bucket
        base["selection_rank"] = candidate.selection_rank
        base["rolling_median_quote_volume_usd_30d"] = candidate.rolling_median_quote_volume_usd_30d
        base["listing_age_days_as_of"] = candidate.listing_age_days_as_of
        base["spot_symbol"] = candidate.spot_symbol
        base["usdm_symbol"] = candidate.usdm_symbol
        base["has_perp_as_of"] = candidate.has_perp_as_of
        base["shape"] = "single_asset"
        frames.append(base)
    if not frames:
        return pd.DataFrame(columns=["timestamp_ms", "timestamp_utc", "subject", "liquidity_bucket", "shape"])
    panel = pd.concat(frames, ignore_index=True, sort=False)
    panel.sort_values(["subject", "timestamp_ms"], inplace=True)
    return panel


COINGLASS_EXTENDED_DERIVED_COLUMNS = (
    "coinglass_liquidation_imbalance_24h",
    "coinglass_taker_imbalance_5d_sum",
    "coinglass_global_account_long_pct",
    "coinglass_top_trader_long_pct",
    "coinglass_liq_intraday_concentration_24h",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "coinglass_top_trader_intraday_volatility_24h",
    "coinglass_orderbook_imb_persistence_24h",
    "coinglass_hourly_bar_count_24h",
    "coinglass_orderbook_bids_mean_24h",
    "coinglass_orderbook_asks_mean_24h",
    "coinglass_orderbook_total_depth_mean_24h",
    "coinglass_orderbook_total_depth_min_24h",
    "coinglass_orderbook_imb_mean_24h",
    "coinglass_orderbook_imb_last_24h",
    "coinglass_orderbook_bid_heavy_share_24h",
    "coinglass_orderbook_ask_heavy_share_24h",
    "coinglass_taker_buy_volume_24h",
    "coinglass_taker_sell_volume_24h",
    "coinglass_taker_net_volume_24h",
    "coinglass_taker_net_to_depth_mean_24h",
)

DERIVATIVES_PANEL_BASE_COLUMNS = (
    "open_time_ms",
    "funding_rate",
    "funding_sample_count",
    "open_interest",
    "open_interest_value",
    "perp_close",
    "perp_quote_volume_usd",
)

OI_PROVENANCE_PANEL_COLUMNS = (
    "open_interest_value_native_usd",
    "open_interest_coin",
    "binance_perp_close",
    "open_interest_value_derived_usd",
    "derived_native_rel_diff",
    "derived_native_formula_status",
    "oi_value_provenance",
    "price_source_for_derived_value",
    "open_interest_value_provider",
    "open_interest_value_source",
    "open_interest_value_source_interval",
    "open_interest_value_canonical_policy",
    "open_interest_value_sample_count",
)


def _derivatives_panel_columns(frame: pd.DataFrame) -> list[str]:
    return [
        column
        for column in (*DERIVATIVES_PANEL_BASE_COLUMNS, *OI_PROVENANCE_PANEL_COLUMNS)
        if column in frame.columns
    ]


def _load_coinglass_extended_features_daily(*, symbol: str | None, end_time_ms: int) -> pd.DataFrame:
    if not symbol:
        return pd.DataFrame()
    rows = load_extended_rows(
        external_root=resolve_extended_external_root(),
        symbol=str(symbol),
        interval="1d",
    )
    if not rows:
        return pd.DataFrame()
    records: list[dict[str, float | int]] = []
    for raw in rows:
        try:
            ts = int(raw["open_time_ms"])
        except (TypeError, ValueError, KeyError):
            continue
        if ts > end_time_ms:
            continue
        def _f(value: Any) -> float:
            text = str(value or "").strip()
            if not text:
                return float("nan")
            try:
                return float(text)
            except ValueError:
                return float("nan")
        records.append({
            "open_time_ms": ts,
            "long_liquidation_usd": _f(raw.get("long_liquidation_usd")),
            "short_liquidation_usd": _f(raw.get("short_liquidation_usd")),
            "global_account_long_pct": _f(raw.get("global_account_long_pct")),
            "top_trader_long_pct": _f(raw.get("top_trader_long_pct")),
            "taker_buy_volume_usd": _f(raw.get("taker_buy_volume_usd")),
            "taker_sell_volume_usd": _f(raw.get("taker_sell_volume_usd")),
        })
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame.from_records(records).drop_duplicates("open_time_ms").sort_values("open_time_ms").reset_index(drop=True)
    eps = 1e-9
    long_liq = df["long_liquidation_usd"].astype("float64")
    short_liq = df["short_liquidation_usd"].astype("float64")
    df["coinglass_liquidation_imbalance_24h"] = (long_liq - short_liq) / (long_liq + short_liq + eps)
    buy = df["taker_buy_volume_usd"].astype("float64")
    sell = df["taker_sell_volume_usd"].astype("float64")
    taker_imb = (buy - sell) / (buy + sell + eps)
    df["coinglass_taker_imbalance_5d_sum"] = taker_imb.rolling(5, min_periods=2).sum()
    df["coinglass_global_account_long_pct"] = df["global_account_long_pct"].astype("float64")
    df["coinglass_top_trader_long_pct"] = df["top_trader_long_pct"].astype("float64")

    # v75: 1h-derived intraday-aggregated daily features
    intraday_df = _load_coinglass_intraday_daily_aggregates(symbol=str(symbol), end_time_ms=end_time_ms)
    if not intraday_df.empty:
        df = df.merge(intraday_df, on="open_time_ms", how="left")
    for col in (
        "coinglass_liq_intraday_concentration_24h",
        "coinglass_taker_imb_intraday_dispersion_24h",
        "coinglass_top_trader_intraday_volatility_24h",
        "coinglass_orderbook_imb_persistence_24h",
    ):
        if col not in df.columns:
            df[col] = float("nan")

    return df[["open_time_ms", *COINGLASS_EXTENDED_DERIVED_COLUMNS]]


def _load_coinglass_intraday_daily_aggregates(*, symbol: str | None, end_time_ms: int) -> pd.DataFrame:
    """Read 1h CoinGlass extended data and aggregate to daily intraday-derived features.

    Aggregations (per UTC-day, computed from 24 hourly bars within each day):
      - liq_intraday_concentration:        max(liq_total_1h) / sum(liq_total_24h)  in [0.04, 1.0]
      - taker_imb_intraday_dispersion:     std((buy-sell)/(buy+sell), 24)
      - top_trader_intraday_volatility:    std(top_trader_long_pct_1h, 24)
      - orderbook_imb_persistence:         autocorr_lag1(orderbook_imbalance_1h, 24)
      - raw orderbook / taker daily state: mean bid depth, mean ask depth,
        total depth mean/min, imbalance mean/last, bid/ask-heavy share, and
        taker-to-depth intensity for downstream MF-01 inventory-transfer work.
    """
    if not symbol:
        return pd.DataFrame()
    rows = load_extended_rows(
        external_root=resolve_extended_external_root(),
        symbol=str(symbol),
        interval="1h",
    )
    if not rows:
        return pd.DataFrame()
    eps = 1e-9
    records: list[dict[str, float | int]] = []
    for raw in rows:
        try:
            ts = int(raw["open_time_ms"])
        except (TypeError, ValueError, KeyError):
            continue
        if ts > end_time_ms:
            continue
        def _f(value: Any) -> float:
            text = str(value or "").strip()
            if not text:
                return float("nan")
            try:
                return float(text)
            except ValueError:
                return float("nan")
        records.append({
            "open_time_ms": ts,
            "long_liq": _f(raw.get("long_liquidation_usd")),
            "short_liq": _f(raw.get("short_liquidation_usd")),
            "taker_buy": _f(raw.get("taker_buy_volume_usd")),
            "taker_sell": _f(raw.get("taker_sell_volume_usd")),
            "top_trader": _f(raw.get("top_trader_long_pct")),
            "ob_bids": _f(raw.get("orderbook_bids_usd")),
            "ob_asks": _f(raw.get("orderbook_asks_usd")),
        })
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame.from_records(records).sort_values("open_time_ms").reset_index(drop=True)
    df["liq_total"] = df["long_liq"].fillna(0.0) + df["short_liq"].fillna(0.0)
    df["ob_total_depth"] = df["ob_bids"].fillna(0.0) + df["ob_asks"].fillna(0.0)
    df["taker_net"] = df["taker_buy"].fillna(0.0) - df["taker_sell"].fillna(0.0)
    df["taker_imb"] = (df["taker_buy"] - df["taker_sell"]) / (df["taker_buy"] + df["taker_sell"] + eps)
    df["ob_imb"] = (df["ob_bids"] - df["ob_asks"]) / (df["ob_bids"] + df["ob_asks"] + eps)
    df["taker_net_to_depth"] = df["taker_net"] / (df["ob_total_depth"] + eps)
    df["day_open_ms"] = (df["open_time_ms"] // (86_400_000)) * 86_400_000

    def _autocorr_lag1(s: pd.Series) -> float:
        s = s.dropna()
        if len(s) < 3:
            return float("nan")
        s_lag = s.shift(1).iloc[1:]
        s_now = s.iloc[1:]
        if s_lag.std() == 0 or s_now.std() == 0:
            return 0.0
        return float(s_now.corr(s_lag))

    by_day = df.groupby("day_open_ms").agg(
        hourly_bar_count=("open_time_ms", "size"),
        liq_max_1h=("liq_total", "max"),
        liq_sum_24h=("liq_total", "sum"),
        taker_imb_std=("taker_imb", lambda s: float(s.std()) if len(s.dropna()) > 1 else float("nan")),
        top_trader_std=("top_trader", lambda s: float(s.std()) if len(s.dropna()) > 1 else float("nan")),
        ob_imb_autocorr=("ob_imb", _autocorr_lag1),
        ob_bids_mean_24h=("ob_bids", "mean"),
        ob_asks_mean_24h=("ob_asks", "mean"),
        ob_total_depth_mean_24h=("ob_total_depth", "mean"),
        ob_total_depth_min_24h=("ob_total_depth", "min"),
        ob_imb_mean_24h=("ob_imb", "mean"),
        ob_imb_last_24h=("ob_imb", "last"),
        ob_bid_heavy_share_24h=("ob_imb", lambda s: float((pd.to_numeric(s, errors="coerce") > 0).mean())),
        ob_ask_heavy_share_24h=("ob_imb", lambda s: float((pd.to_numeric(s, errors="coerce") < 0).mean())),
        taker_buy_sum_24h=("taker_buy", "sum"),
        taker_sell_sum_24h=("taker_sell", "sum"),
        taker_net_sum_24h=("taker_net", "sum"),
        taker_net_to_depth_mean_24h=("taker_net_to_depth", "mean"),
    ).reset_index()
    by_day["coinglass_liq_intraday_concentration_24h"] = (
        by_day["liq_max_1h"] / (by_day["liq_sum_24h"] + eps)
    ).clip(lower=0.0, upper=1.0)
    by_day["coinglass_taker_imb_intraday_dispersion_24h"] = by_day["taker_imb_std"]
    by_day["coinglass_top_trader_intraday_volatility_24h"] = by_day["top_trader_std"]
    by_day["coinglass_orderbook_imb_persistence_24h"] = by_day["ob_imb_autocorr"]
    by_day["coinglass_hourly_bar_count_24h"] = by_day["hourly_bar_count"]
    by_day["coinglass_orderbook_bids_mean_24h"] = by_day["ob_bids_mean_24h"]
    by_day["coinglass_orderbook_asks_mean_24h"] = by_day["ob_asks_mean_24h"]
    by_day["coinglass_orderbook_total_depth_mean_24h"] = by_day["ob_total_depth_mean_24h"]
    by_day["coinglass_orderbook_total_depth_min_24h"] = by_day["ob_total_depth_min_24h"]
    by_day["coinglass_orderbook_imb_mean_24h"] = by_day["ob_imb_mean_24h"]
    by_day["coinglass_orderbook_imb_last_24h"] = by_day["ob_imb_last_24h"]
    by_day["coinglass_orderbook_bid_heavy_share_24h"] = by_day["ob_bid_heavy_share_24h"]
    by_day["coinglass_orderbook_ask_heavy_share_24h"] = by_day["ob_ask_heavy_share_24h"]
    by_day["coinglass_taker_buy_volume_24h"] = by_day["taker_buy_sum_24h"]
    by_day["coinglass_taker_sell_volume_24h"] = by_day["taker_sell_sum_24h"]
    by_day["coinglass_taker_net_volume_24h"] = by_day["taker_net_sum_24h"]
    by_day["coinglass_taker_net_to_depth_mean_24h"] = by_day["taker_net_to_depth_mean_24h"]
    by_day = by_day.rename(columns={"day_open_ms": "open_time_ms"})
    return by_day[[
        "open_time_ms",
        "coinglass_liq_intraday_concentration_24h",
        "coinglass_taker_imb_intraday_dispersion_24h",
        "coinglass_top_trader_intraday_volatility_24h",
        "coinglass_orderbook_imb_persistence_24h",
        "coinglass_hourly_bar_count_24h",
        "coinglass_orderbook_bids_mean_24h",
        "coinglass_orderbook_asks_mean_24h",
        "coinglass_orderbook_total_depth_mean_24h",
        "coinglass_orderbook_total_depth_min_24h",
        "coinglass_orderbook_imb_mean_24h",
        "coinglass_orderbook_imb_last_24h",
        "coinglass_orderbook_bid_heavy_share_24h",
        "coinglass_orderbook_ask_heavy_share_24h",
        "coinglass_taker_buy_volume_24h",
        "coinglass_taker_sell_volume_24h",
        "coinglass_taker_net_volume_24h",
        "coinglass_taker_net_to_depth_mean_24h",
    ]]


def _build_cross_sectional_daily_4h_panel(
    *,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    as_of: str,
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    as_of_end = resolve_as_of_end_ms(as_of)
    frames: list[pd.DataFrame] = []
    missing_spot_symbols_by_interval: dict[str, list[str]] = {"1d": [], "4h": []}
    for candidate in universe_candidates:
        spot1d = load_ohlcv_frame(
            symbol=candidate.spot_symbol,
            market_type="spot",
            interval="1d",
            external_root=ohlcv_external_root,
            spot_external_root=spot_ohlcv_external_root,
            end_time_ms=as_of_end,
        )
        if spot1d.empty:
            missing_spot_symbols_by_interval["1d"].append(candidate.spot_symbol)
            continue
        spot4h = load_ohlcv_frame(
            symbol=candidate.spot_symbol,
            market_type="spot",
            interval="4h",
            external_root=ohlcv_external_root,
            spot_external_root=spot_ohlcv_external_root,
            end_time_ms=as_of_end,
        )
        if spot4h.empty:
            missing_spot_symbols_by_interval["4h"].append(candidate.spot_symbol)
            continue
        intraday_daily = aggregate_4h_to_1d_context(spot4h)
        perp1d = (
        load_ohlcv_frame(
                symbol=str(candidate.usdm_symbol),
                market_type="usdm_perp",
                interval="1d",
                external_root=ohlcv_external_root,
                end_time_ms=as_of_end,
            )
            if candidate.usdm_symbol
            else pd.DataFrame()
        )
        deriv1d = (
        load_derivatives_frame(
                symbol=str(candidate.usdm_symbol),
                interval="1d",
                external_root=derivatives_external_root,
                end_time_ms=as_of_end,
            )
            if candidate.usdm_symbol
            else pd.DataFrame()
        )
        base = spot1d.rename(
            columns={
                "open": "spot_open",
                "high": "spot_high",
                "low": "spot_low",
                "close": "spot_close",
                "volume": "spot_volume",
                "quote_volume": "spot_quote_volume",
            }
        )[["open_time_ms", "close_time_ms", "spot_open", "spot_high", "spot_low", "spot_close", "spot_volume", "spot_quote_volume"]]
        if not intraday_daily.empty:
            base = base.merge(intraday_daily, on="open_time_ms", how="left")
        if not perp1d.empty:
            base = base.merge(
                perp1d.rename(
                    columns={"close": "perp_close", "volume": "perp_volume", "quote_volume": "perp_quote_volume_usd"}
                )[["open_time_ms", "perp_close", "perp_volume", "perp_quote_volume_usd"]],
                on="open_time_ms",
                how="left",
            )
        else:
            base["perp_close"] = np.nan
            base["perp_volume"] = np.nan
            base["perp_quote_volume_usd"] = np.nan
        if not deriv1d.empty:
            base = base.merge(
                deriv1d[_derivatives_panel_columns(deriv1d)].rename(
                    columns={
                        "perp_close": "derivatives_perp_close",
                        "perp_quote_volume_usd": "derivatives_perp_quote_volume_usd",
                    }
                ),
                on="open_time_ms",
                how="left",
            )
        else:
            base["funding_rate"] = np.nan
            base["funding_sample_count"] = np.nan
            base["open_interest"] = np.nan
            base["open_interest_value"] = np.nan
            base["derivatives_perp_close"] = np.nan
            base["derivatives_perp_quote_volume_usd"] = np.nan
        if "derivatives_perp_close" in base.columns:
            base["perp_close"] = base["perp_close"].combine_first(base["derivatives_perp_close"])
            base.drop(columns=["derivatives_perp_close"], inplace=True)
        if "derivatives_perp_quote_volume_usd" in base.columns:
            base["perp_quote_volume_usd"] = base["perp_quote_volume_usd"].combine_first(
                base["derivatives_perp_quote_volume_usd"]
            )
            base.drop(columns=["derivatives_perp_quote_volume_usd"], inplace=True)
        base["basis_proxy"] = np.where(base["perp_close"].notna() & base["spot_close"].ne(0), (base["perp_close"] - base["spot_close"]) / base["spot_close"], np.nan)
        coinglass_features = _load_coinglass_extended_features_daily(
            symbol=str(candidate.usdm_symbol) if candidate.usdm_symbol else None,
            end_time_ms=as_of_end,
        )
        if not coinglass_features.empty:
            base = base.merge(coinglass_features, on="open_time_ms", how="left")
        else:
            for column in COINGLASS_EXTENDED_DERIVED_COLUMNS:
                base[column] = np.nan
        base["timestamp_ms"] = base["open_time_ms"].astype("int64")
        base["timestamp_utc"] = pd.to_datetime(base["timestamp_ms"], unit="ms", utc=True).astype(str)
        base["date_utc"] = pd.to_datetime(base["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
        base["subject"] = candidate.subject
        base["liquidity_bucket"] = candidate.liquidity_bucket
        base["selection_rank"] = candidate.selection_rank
        base["rolling_median_quote_volume_usd_30d"] = candidate.rolling_median_quote_volume_usd_30d
        base["listing_age_days_as_of"] = candidate.listing_age_days_as_of
        base["spot_symbol"] = candidate.spot_symbol
        base["usdm_symbol"] = candidate.usdm_symbol
        _attach_cross_sectional_perp_execution_metadata(base=base, candidate=candidate)
        base["shape"] = "cross_sectional"
        frames.append(base)
    if not frames:
        return (
            pd.DataFrame(columns=["timestamp_ms", "timestamp_utc", "subject", "liquidity_bucket", "shape"]),
            _normalize_missing_spot_symbols_by_interval(missing_spot_symbols_by_interval),
        )
    panel = pd.concat(frames, ignore_index=True, sort=False)
    panel.sort_values(["timestamp_ms", "subject"], inplace=True)
    return panel, _normalize_missing_spot_symbols_by_interval(missing_spot_symbols_by_interval)


def _build_cross_sectional_intraday_1h_panel(
    *,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    as_of: str,
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    as_of_end = resolve_as_of_end_ms(as_of)
    frames: list[pd.DataFrame] = []
    missing_spot_symbols_by_interval: dict[str, list[str]] = {"1h": []}
    for candidate in universe_candidates:
        spot1h = load_ohlcv_frame(
            symbol=candidate.spot_symbol,
            market_type="spot",
            interval="1h",
            external_root=ohlcv_external_root,
            spot_external_root=spot_ohlcv_external_root,
            end_time_ms=as_of_end,
        )
        if spot1h.empty:
            missing_spot_symbols_by_interval["1h"].append(candidate.spot_symbol)
            continue
        perp1d = (
            load_ohlcv_frame(
                symbol=str(candidate.usdm_symbol),
                market_type="usdm_perp",
                interval="1d",
                external_root=ohlcv_external_root,
                end_time_ms=as_of_end,
            )
            if candidate.usdm_symbol
            else pd.DataFrame()
        )
        deriv1d = (
            load_derivatives_frame(
                symbol=str(candidate.usdm_symbol),
                interval="1d",
                external_root=derivatives_external_root,
                end_time_ms=as_of_end,
            )
            if candidate.usdm_symbol
            else pd.DataFrame()
        )
        base = spot1h.rename(
            columns={
                "open": "spot_open",
                "high": "spot_high",
                "low": "spot_low",
                "close": "spot_close",
                "volume": "spot_volume",
                "quote_volume": "spot_quote_volume",
            }
        )[["open_time_ms", "close_time_ms", "spot_open", "spot_high", "spot_low", "spot_close", "spot_volume", "spot_quote_volume"]]
        if not perp1d.empty:
            daily_perp = perp1d.rename(
                columns={"open_time_ms": "daily_open_time_ms", "close": "perp_close", "volume": "perp_volume", "quote_volume": "perp_quote_volume_usd"}
            )[["daily_open_time_ms", "perp_close", "perp_volume", "perp_quote_volume_usd"]]
            base = pd.merge_asof(
                base.sort_values("open_time_ms"),
                daily_perp.sort_values("daily_open_time_ms"),
                left_on="open_time_ms",
                right_on="daily_open_time_ms",
                direction="backward",
            )
            base.drop(columns=["daily_open_time_ms"], inplace=True, errors="ignore")
        else:
            base["perp_close"] = np.nan
            base["perp_volume"] = np.nan
            base["perp_quote_volume_usd"] = np.nan
        if not deriv1d.empty:
            daily_derivatives = deriv1d[_derivatives_panel_columns(deriv1d)].rename(
                columns={
                    "open_time_ms": "daily_open_time_ms",
                    "perp_close": "derivatives_perp_close",
                    "perp_quote_volume_usd": "derivatives_perp_quote_volume_usd",
                }
            )
            base = pd.merge_asof(
                base.sort_values("open_time_ms"),
                daily_derivatives.sort_values("daily_open_time_ms"),
                left_on="open_time_ms",
                right_on="daily_open_time_ms",
                direction="backward",
            )
            base.drop(columns=["daily_open_time_ms"], inplace=True, errors="ignore")
        else:
            base["funding_rate"] = np.nan
            base["funding_sample_count"] = np.nan
            base["open_interest"] = np.nan
            base["open_interest_value"] = np.nan
            base["derivatives_perp_close"] = np.nan
            base["derivatives_perp_quote_volume_usd"] = np.nan
        if "derivatives_perp_close" in base.columns:
            base["perp_close"] = base["perp_close"].combine_first(base["derivatives_perp_close"])
            base.drop(columns=["derivatives_perp_close"], inplace=True)
        if "derivatives_perp_quote_volume_usd" in base.columns:
            base["perp_quote_volume_usd"] = base["perp_quote_volume_usd"].combine_first(
                base["derivatives_perp_quote_volume_usd"]
            )
            base.drop(columns=["derivatives_perp_quote_volume_usd"], inplace=True)
        base["basis_proxy"] = np.where(
            base["perp_close"].notna() & base["spot_close"].ne(0),
            (base["perp_close"] - base["spot_close"]) / base["spot_close"],
            np.nan,
        )
        base["timestamp_ms"] = base["open_time_ms"].astype("int64")
        base["timestamp_utc"] = pd.to_datetime(base["timestamp_ms"], unit="ms", utc=True).astype(str)
        base["date_utc"] = pd.to_datetime(base["timestamp_ms"], unit="ms", utc=True).dt.date.astype(str)
        base["subject"] = candidate.subject
        base["liquidity_bucket"] = candidate.liquidity_bucket
        base["selection_rank"] = candidate.selection_rank
        base["rolling_median_quote_volume_usd_30d"] = candidate.rolling_median_quote_volume_usd_30d
        base["listing_age_days_as_of"] = candidate.listing_age_days_as_of
        base["spot_symbol"] = candidate.spot_symbol
        base["usdm_symbol"] = candidate.usdm_symbol
        _attach_cross_sectional_perp_execution_metadata(base=base, candidate=candidate)
        base["shape"] = "cross_sectional"
        frames.append(base)
    if not frames:
        return (
            pd.DataFrame(columns=["timestamp_ms", "timestamp_utc", "subject", "liquidity_bucket", "shape"]),
            _normalize_missing_spot_symbols_by_interval(missing_spot_symbols_by_interval),
        )
    panel = pd.concat(frames, ignore_index=True, sort=False)
    panel.sort_values(["timestamp_ms", "subject"], inplace=True)
    return panel, _normalize_missing_spot_symbols_by_interval(missing_spot_symbols_by_interval)


def _normalize_missing_spot_symbols_by_interval(
    missing_spot_symbols_by_interval: dict[str, list[str]],
) -> dict[str, list[str]]:
    return {
        str(interval).strip(): sorted(
            {
                str(symbol).strip().upper()
                for symbol in list(symbols or [])
                if str(symbol).strip()
            }
        )
        for interval, symbols in missing_spot_symbols_by_interval.items()
        if str(interval).strip()
    }


def _attach_cross_sectional_perp_execution_metadata(
    *,
    base: pd.DataFrame,
    candidate: QuantUniverseCandidate,
) -> None:
    has_perp = candidate.has_perp_as_of
    base["has_perp_as_of"] = has_perp
    if base.empty or not has_perp:
        base["perp_execution_eligible"] = False
        base["perp_executable_start_ms"] = np.nan
        return
    perp_close = _numeric_series_or_zero(base, "perp_close")
    perp_quote_volume_usd = _numeric_series_or_zero(base, "perp_quote_volume_usd")
    perp_volume = _numeric_series_or_zero(base, "perp_volume")
    open_interest_value = _numeric_series_or_zero(base, "open_interest_value")
    liquidity_ready = perp_quote_volume_usd.gt(0.0) | (perp_volume.gt(0.0) & perp_close.gt(0.0))
    row_eligible = perp_close.gt(0.0) & open_interest_value.gt(0.0) & liquidity_ready
    base["perp_execution_eligible"] = row_eligible.astype(bool)
    if bool(row_eligible.any()):
        timestamp_ms = pd.to_numeric(base["timestamp_ms"], errors="coerce")
        base["perp_executable_start_ms"] = float(timestamp_ms.loc[row_eligible].min())
    else:
        base["perp_executable_start_ms"] = np.nan


def _numeric_series_or_zero(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def run_quant_experiments(
    *,
    as_of: str,
    artifacts_root: Path,
    strategy_library: dict[str, Any],
    feature_sets: list[dict[str, Any]],
    compiler_backend: str,
) -> list[dict[str, Any]]:
    return run_quant_experiments_for_strategies(
        as_of=as_of,
        artifacts_root=artifacts_root,
        strategies=_daily_cycle_strategies(strategy_library=strategy_library, as_of=as_of),
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
    )


def run_quant_experiments_for_strategies(
    *,
    as_of: str,
    artifacts_root: Path,
    strategies: list[dict[str, Any]],
    feature_sets: list[dict[str, Any]],
    compiler_backend: str,
    source_commit_sha: str | None = None,
) -> list[dict[str, Any]]:
    resolved_source_commit_sha = str(source_commit_sha or "").strip() or required_source_commit_sha(repo_root=ROOT)
    resolved_artifacts_root = artifacts_root.expanduser().resolve()
    registry_artifacts_root = _canonical_quant_artifacts_root(resolved_artifacts_root)
    feature_sets_by_profile: dict[str, list[dict[str, Any]]] = {}
    for item in feature_sets:
        dataset_profile = normalize_dataset_profile(
            shape=str(item.get("shape") or "").strip(),
            dataset_profile=str(item.get("dataset_profile") or "").strip() or None,
        )
        feature_sets_by_profile.setdefault(dataset_profile, []).append(item)
    experiments: list[dict[str, Any]] = []
    for strategy in strategies:
        dataset_profile = normalize_dataset_profile(
            shape=str(strategy.get("shape") or "").strip(),
            dataset_profile=str(strategy.get("dataset_profile") or "").strip() or None,
        )
        feature_set = dict(
            _select_feature_set_for_strategy(
                feature_sets=feature_sets_by_profile[dataset_profile],
                strategy_entry=strategy,
            )
        )
        model_definition = _resolve_strategy_model_definition(
            artifacts_root=registry_artifacts_root,
            strategy_entry=strategy,
        )
        feature_family_entries = _resolve_feature_family_entries(
            artifacts_root=registry_artifacts_root,
            strategy_entry=strategy,
        )
        if strategy["shape"] == "single_asset":
            frame = feature_set["dataframe"].loc[
                feature_set["dataframe"]["subject"] == str(strategy.get("subject"))
            ].copy()
            feature_quality_frame = feature_set.get("feature_quality_frame")
            if not isinstance(feature_quality_frame, pd.DataFrame):
                feature_quality_frame = build_feature_quality_frame(
                    feature_frame=feature_set["dataframe"],
                    tracked_feature_columns=feature_set["numeric_feature_columns"],
                    derivatives_quality_frame=feature_set["derivatives_quality_frame"],
                )
            feature_quality_frame = feature_quality_frame.loc[
                feature_quality_frame["subject"] == str(strategy.get("subject"))
            ].copy()
            derivatives_quality_frame = feature_set["derivatives_quality_frame"].loc[
                feature_set["derivatives_quality_frame"]["subject"] == str(strategy.get("subject"))
            ].copy()
            candidate = _candidate_from_frame(frame)
            numeric_columns = _select_strategy_feature_columns(
                strategy_entry=strategy,
                numeric_feature_columns=list(feature_set["numeric_feature_columns"]),
            )
            feature_admission_bundle = {
                "feature_admission_policy": dict(feature_set.get("feature_admission_policy") or {}),
                "available_numeric_columns": list(feature_set.get("available_numeric_columns") or []),
                "numeric_feature_columns": list(feature_set.get("numeric_feature_columns") or []),
                "excluded_numeric_columns": list(feature_set.get("excluded_numeric_columns") or []),
            }
            dataset_manifest_path = str(feature_set.get("dataset_manifest_path") or "").strip()
            reproducibility_bundle = {
                "source_commit_sha": resolved_source_commit_sha,
                "dataset_fingerprint": str(feature_set.get("dataset_fingerprint") or ""),
                "feature_hash": str(feature_set.get("feature_hash") or ""),
                "dataset_manifest_path": portable_path(Path(dataset_manifest_path), repo_root=ROOT) if dataset_manifest_path else "",
                "feature_manifest_path": portable_path(Path(str(feature_set["manifest_path"])), repo_root=ROOT),
                "features_path": portable_path(Path(str(feature_set.get("features_path") or "")), repo_root=ROOT)
                if str(feature_set.get("features_path") or "").strip()
                else "",
            }
            universe_metadata = {
                "universe_definition_id": str(feature_set.get("universe_definition_id") or ""),
                "universe_contract_version": str(feature_set.get("universe_contract_version") or ""),
                "universe_snapshot_path": portable_path(Path(str(feature_set.get("universe_snapshot_path") or "")), repo_root=ROOT)
                if str(feature_set.get("universe_snapshot_path") or "").strip()
                else "",
                "universe_selection_policy_hash": str(feature_set.get("universe_selection_policy_hash") or ""),
            }
            feature_quality = feature_set.get("feature_quality")
            derivatives_feature_quality = feature_set.get("derivatives_feature_quality")
            dataset_data_readiness = dict(feature_set.get("dataset_data_readiness") or {})
        else:
            frame = _apply_universe_filter(feature_set["dataframe"], universe_filter=strategy.get("universe_filter"))
            feature_quality_frame = feature_set.get("feature_quality_frame")
            if not isinstance(feature_quality_frame, pd.DataFrame):
                feature_quality_frame = build_feature_quality_frame(
                    feature_frame=feature_set["dataframe"],
                    tracked_feature_columns=feature_set["numeric_feature_columns"],
                    derivatives_quality_frame=feature_set["derivatives_quality_frame"],
                )
            feature_quality_frame = feature_quality_frame.copy()
            if frame.empty:
                feature_quality_frame = feature_quality_frame.iloc[0:0].copy()
            elif "subject" in feature_quality_frame.columns:
                allowed_subjects = sorted(
                    {
                        str(subject).strip()
                        for subject in list(frame["subject"].dropna().astype(str))
                        if str(subject).strip()
                    }
                )
                feature_quality_frame = feature_quality_frame.loc[
                    feature_quality_frame["subject"].astype(str).isin(allowed_subjects)
                ].copy()
            derivatives_quality_frame = feature_set["derivatives_quality_frame"].copy()
            if frame.empty:
                derivatives_quality_frame = derivatives_quality_frame.iloc[0:0].copy()
            elif "subject" in derivatives_quality_frame.columns:
                allowed_subjects = sorted(
                    {
                        str(subject).strip()
                        for subject in list(frame["subject"].dropna().astype(str))
                        if str(subject).strip()
                    }
                )
                derivatives_quality_frame = derivatives_quality_frame.loc[
                    derivatives_quality_frame["subject"].astype(str).isin(allowed_subjects)
                ].copy()
            candidate = None
            numeric_columns = _select_strategy_feature_columns(
                strategy_entry=strategy,
                numeric_feature_columns=list(feature_set["numeric_feature_columns"]),
            )
            feature_admission_bundle = {
                "feature_admission_policy": dict(feature_set.get("feature_admission_policy") or {}),
                "available_numeric_columns": list(feature_set.get("available_numeric_columns") or []),
                "numeric_feature_columns": list(feature_set.get("numeric_feature_columns") or []),
                "excluded_numeric_columns": list(feature_set.get("excluded_numeric_columns") or []),
            }
            dataset_manifest_path = str(feature_set.get("dataset_manifest_path") or "").strip()
            reproducibility_bundle = {
                "source_commit_sha": resolved_source_commit_sha,
                "dataset_fingerprint": str(feature_set.get("dataset_fingerprint") or ""),
                "feature_hash": str(feature_set.get("feature_hash") or ""),
                "dataset_manifest_path": portable_path(Path(dataset_manifest_path), repo_root=ROOT) if dataset_manifest_path else "",
                "feature_manifest_path": portable_path(Path(str(feature_set["manifest_path"])), repo_root=ROOT),
                "features_path": portable_path(Path(str(feature_set.get("features_path") or "")), repo_root=ROOT)
                if str(feature_set.get("features_path") or "").strip()
                else "",
            }
            universe_metadata = {
                "universe_definition_id": str(feature_set.get("universe_definition_id") or ""),
                "universe_contract_version": str(feature_set.get("universe_contract_version") or ""),
                "universe_snapshot_path": portable_path(Path(str(feature_set.get("universe_snapshot_path") or "")), repo_root=ROOT)
                if str(feature_set.get("universe_snapshot_path") or "").strip()
                else "",
                "universe_selection_policy_hash": str(feature_set.get("universe_selection_policy_hash") or ""),
            }
            feature_quality = feature_set.get("feature_quality")
            derivatives_feature_quality = feature_set.get("derivatives_feature_quality")
            dataset_data_readiness = dict(feature_set.get("dataset_data_readiness") or {})
        frame, generated_feature_columns = _apply_feature_family_registry(
            frame=frame,
            feature_family_entries=feature_family_entries,
            shape=str(strategy.get("shape") or ""),
        )
        experiments.append(
            _run_experiment(
                as_of=as_of,
                artifacts_root=artifacts_root,
                frame=frame,
                feature_quality_frame=feature_quality_frame,
                feature_quality=feature_quality,
                derivatives_quality_frame=derivatives_quality_frame,
                derivatives_feature_quality=derivatives_feature_quality,
                shape=strategy["shape"],
                model_family=strategy["model_family"],
                strategy_profile=strategy["strategy_profile"],
                feature_columns=numeric_columns,
                compiler_backend=compiler_backend,
                subject=strategy.get("subject"),
                candidate=candidate,
                strategy_entry=strategy,
                model_definition=model_definition,
                split_realization_contract=dict(feature_set["split_realization_contract"]),
                label_contract_id=str(feature_set.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID),
                target_column=str(feature_set.get("target_column") or "target_up"),
                forward_return_column=str(feature_set.get("forward_return_column") or "target_forward_return"),
                dataset_data_readiness=dataset_data_readiness,
                dataset_research_dataset=dict(feature_set.get("dataset_research_dataset") or {}),
                feature_admission_bundle=feature_admission_bundle,
                reproducibility_bundle=reproducibility_bundle,
                universe_metadata=universe_metadata,
                generated_feature_columns=generated_feature_columns,
            )
        )
    return experiments


def _select_feature_set_for_strategy(
    *,
    feature_sets: list[dict[str, Any]],
    strategy_entry: dict[str, Any],
) -> dict[str, Any]:
    if not feature_sets:
        raise KeyError("no feature sets available for strategy")
    requested_target_horizon_bars = int(strategy_entry.get("target_horizon_bars") or 0)
    requested_label_contract_id = str(
        strategy_entry.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID
    ).strip() or DEFAULT_LABEL_CONTRACT_ID
    if requested_target_horizon_bars > 0:
        horizon_matches: list[dict[str, Any]] = []
        for feature_set in feature_sets:
            feature_set_target_horizon_bars = int(
                feature_set.get("target_horizon_bars")
                or dict(feature_set.get("split_realization_contract") or {}).get("target_horizon_bars")
                or 0
            )
            if feature_set_target_horizon_bars == requested_target_horizon_bars:
                horizon_matches.append(dict(feature_set))
        if requested_label_contract_id:
            for feature_set in horizon_matches:
                feature_set_label_contract_id = str(
                    feature_set.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID
                ).strip() or DEFAULT_LABEL_CONTRACT_ID
                if feature_set_label_contract_id == requested_label_contract_id:
                    return dict(feature_set)
        if requested_label_contract_id == DEFAULT_LABEL_CONTRACT_ID and horizon_matches:
            return dict(horizon_matches[0])
        available_horizons = sorted(
            {
                int(
                    feature_set.get("target_horizon_bars")
                    or dict(feature_set.get("split_realization_contract") or {}).get("target_horizon_bars")
                    or 0
                )
                for feature_set in feature_sets
            }
        )
        raise KeyError(
            "no matching feature set for strategy horizon/label contract: "
            f"horizon={requested_target_horizon_bars}, label_contract_id={requested_label_contract_id} "
            f"not in horizons={available_horizons}"
        )
    if len(feature_sets) == 1:
        return dict(feature_sets[0])
    for feature_set in feature_sets:
        feature_set_target_horizon_bars = int(
            feature_set.get("target_horizon_bars")
            or dict(feature_set.get("split_realization_contract") or {}).get("target_horizon_bars")
            or 0
        )
        feature_set_label_contract_id = str(
            feature_set.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID
        ).strip() or DEFAULT_LABEL_CONTRACT_ID
        if (
            feature_set_target_horizon_bars == 1
            and feature_set_label_contract_id == requested_label_contract_id
        ):
            return dict(feature_set)
    if requested_label_contract_id == DEFAULT_LABEL_CONTRACT_ID:
        for feature_set in feature_sets:
            feature_set_target_horizon_bars = int(
                feature_set.get("target_horizon_bars")
                or dict(feature_set.get("split_realization_contract") or {}).get("target_horizon_bars")
                or 0
            )
            if feature_set_target_horizon_bars == 1:
                return dict(feature_set)
    return dict(feature_sets[0])


def _select_strategy_feature_columns(
    *,
    strategy_entry: dict[str, Any],
    numeric_feature_columns: list[str],
) -> list[str]:
    selection_mode = str(strategy_entry.get("feature_selection_mode") or "").strip().lower()
    if selection_mode == "required_columns":
        required_columns = (
            list(strategy_entry.get("required_feature_columns") or [])
            or list(dict(strategy_entry.get("thesis_profile") or {}).get("required_feature_columns") or [])
        )
        return [
            column
            for column in dict.fromkeys(str(item).strip() for item in required_columns if str(item).strip())
            if column
        ]
    if str(strategy_entry.get("model_family") or "") in DERIVATIVES_FIRST_CROSS_SECTION_MODELS:
        selected = _derivatives_first_cross_section_feature_columns(numeric_feature_columns)
    else:
        selected = select_feature_columns(
            numeric_feature_columns=numeric_feature_columns,
            feature_groups=strategy_entry.get("feature_groups", []),
        )
    if bool(strategy_entry.get("include_required_feature_columns_in_selection")):
        for column in list(strategy_entry.get("required_feature_columns") or []):
            normalized = str(column).strip()
            if normalized and normalized not in selected:
                selected.append(normalized)
    return selected


def _apply_gap_driven_backfill_and_targeted_rerun(
    *,
    as_of: str,
    cycle_root: Path,
    artifacts_root: Path,
    quant_input_root: Path,
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    derivatives_external_root: Path | None,
    compiler_backend: str,
    source_commit_sha: str,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    daily_strategies: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
    feature_sets: list[dict[str, Any]],
    experiments: list[dict[str, Any]],
    derivatives_sync: dict[str, Any],
    derivatives_sync_summary_path: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    Path,
    dict[str, Any],
]:
    original_datasets = datasets
    original_feature_sets = feature_sets
    original_experiments = experiments
    original_derivatives_sync = derivatives_sync
    original_derivatives_sync_summary_path = derivatives_sync_summary_path
    summary_path = cycle_root / "gap_remediation_summary.json"
    plan = build_gap_remediation_plan(
        as_of=as_of,
        experiments=experiments,
        strategies=daily_strategies,
        universe_candidates=universe_candidates,
    )
    execution = execute_gap_remediation_backfill(
        as_of=as_of,
        plan=plan,
        quant_input_root=quant_input_root,
        spot_ohlcv_external_root=spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
    )
    rerun: dict[str, Any] = {
        "attempted": False,
        "rerun_strategy_ids": list(plan.get("affected_strategy_ids") or []),
        "rerun_experiment_count": 0,
        "resolved_strategy_ids": [],
        "remaining_data_gap_strategy_ids": [],
    }
    if plan.get("should_attempt") and _gap_backfill_succeeded(execution):
        try:
            derivatives_lane = dict(execution.get("derivatives_backfill") or {})
            if (
                derivatives_lane.get("attempted")
                and str(derivatives_lane.get("status") or "").strip().lower() != "error"
            ):
                derivatives_sync, derivatives_sync_summary_path = require_derivatives_sync_summary(
                    as_of=as_of,
                    derivatives_external_root=derivatives_external_root,
                )
            datasets = build_quant_datasets(
                as_of=as_of,
                artifacts_root=artifacts_root,
                universe_candidates=universe_candidates,
                ohlcv_external_root=ohlcv_external_root,
                spot_ohlcv_external_root=spot_ohlcv_external_root,
                derivatives_external_root=derivatives_external_root,
                derivatives_sync=derivatives_sync,
                source_commit_sha=source_commit_sha,
            )
            feature_sets = build_quant_feature_sets(
                artifacts_root=artifacts_root,
                datasets=datasets,
                derivatives_sync=derivatives_sync,
                source_commit_sha=source_commit_sha,
            )
            rerun_strategy_ids = {
                str(item).strip()
                for item in list(plan.get("affected_strategy_ids") or [])
                if str(item).strip()
            }
            rerun_strategies = [
                dict(entry)
                for entry in daily_strategies
                if str(entry.get("strategy_id") or "").strip() in rerun_strategy_ids
            ]
            rerun_experiments = run_quant_experiments_for_strategies(
                as_of=as_of,
                artifacts_root=artifacts_root,
                strategies=rerun_strategies,
                feature_sets=feature_sets,
                compiler_backend=compiler_backend,
                source_commit_sha=source_commit_sha,
            )
            experiments = _merge_rerun_experiments(
                experiments=experiments,
                rerun_experiments=rerun_experiments,
            )
            resolved_strategy_ids, remaining_data_gap_strategy_ids = _gap_rerun_resolution(
                before=original_experiments,
                rerun_experiments=rerun_experiments,
            )
            rerun = {
                "attempted": True,
                "rerun_strategy_ids": sorted(rerun_strategy_ids),
                "rerun_experiment_count": len(rerun_experiments),
                "resolved_strategy_ids": resolved_strategy_ids,
                "remaining_data_gap_strategy_ids": remaining_data_gap_strategy_ids,
            }
        except Exception as exc:
            datasets = original_datasets
            feature_sets = original_feature_sets
            experiments = original_experiments
            derivatives_sync = original_derivatives_sync
            derivatives_sync_summary_path = original_derivatives_sync_summary_path
            rerun = {
                "attempted": False,
                "rerun_strategy_ids": list(plan.get("affected_strategy_ids") or []),
                "rerun_experiment_count": 0,
                "resolved_strategy_ids": [],
                "remaining_data_gap_strategy_ids": [],
                "error": str(exc),
            }
    elif plan.get("should_attempt"):
        rerun["skip_reason"] = "no_successful_backfill"
    else:
        rerun["skip_reason"] = "no_resolvable_data_gaps"
    summary = write_gap_remediation_summary(
        path=summary_path,
        as_of=as_of,
        plan=plan,
        execution=execution,
        rerun=rerun,
        source_commit_sha=source_commit_sha,
    )
    return datasets, feature_sets, experiments, derivatives_sync, derivatives_sync_summary_path, summary


def _gap_backfill_succeeded(execution: dict[str, Any]) -> bool:
    for lane_name in ("spot_backfill", "derivatives_backfill"):
        lane = dict(execution.get(lane_name) or {})
        if not lane.get("attempted"):
            continue
        if str(lane.get("status") or "").strip().lower() != "error":
            return True
    return False


def _merge_rerun_experiments(
    *,
    experiments: list[dict[str, Any]],
    rerun_experiments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged_by_strategy_id = {
        str(experiment.get("strategy_id") or ""): experiment
        for experiment in experiments
        if str(experiment.get("strategy_id") or "").strip()
    }
    order = [
        str(experiment.get("strategy_id") or "")
        for experiment in experiments
        if str(experiment.get("strategy_id") or "").strip()
    ]
    for experiment in rerun_experiments:
        strategy_id = str(experiment.get("strategy_id") or "").strip()
        if not strategy_id:
            continue
        merged_by_strategy_id[strategy_id] = experiment
        if strategy_id not in order:
            order.append(strategy_id)
    return [merged_by_strategy_id[strategy_id] for strategy_id in order if strategy_id in merged_by_strategy_id]


def _gap_rerun_resolution(
    *,
    before: list[dict[str, Any]],
    rerun_experiments: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    before_by_strategy_id = {
        str(experiment.get("strategy_id") or "").strip(): experiment
        for experiment in before
        if str(experiment.get("strategy_id") or "").strip()
    }
    resolved: list[str] = []
    remaining: list[str] = []
    for experiment in rerun_experiments:
        strategy_id = str(experiment.get("strategy_id") or "").strip()
        if not strategy_id:
            continue
        before_had_gap = _experiment_has_remediable_gap(before_by_strategy_id.get(strategy_id, {}))
        after_has_gap = _experiment_has_remediable_gap(experiment)
        if before_had_gap and not after_has_gap:
            resolved.append(strategy_id)
        if after_has_gap:
            remaining.append(strategy_id)
    return sorted(set(resolved)), sorted(set(remaining))


def _experiment_has_remediable_gap(experiment: dict[str, Any]) -> bool:
    blockers = {
        str(item).strip()
        for item in list(experiment.get("data_gap_blockers") or [])
        if str(item).strip()
    }
    validation_blocker_codes = {
        str(item).strip()
        for item in list(experiment.get("validation_blocker_codes") or [])
        if str(item).strip()
    }
    if blockers:
        return True
    return bool(
        validation_blocker_codes
        & {
            CROSS_SECTIONAL_SPOT_BLOCKER,
            SINGLE_ASSET_SPOT_BLOCKER,
            "execution_cost_model_data_gap",
            DISCOVERY_DERIVATIVES_BLOCKER,
        }
    )


def _cross_sectional_daily_lane_gate(*, datasets: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    for dataset in datasets:
        dataset_id = str(dataset.get("dataset_id") or "").strip()
        if not (
            dataset_id.endswith("-cross-sectional-daily-1d")
            or dataset_id.endswith("-cross-sectional-1d")
        ):
            continue
        readiness = dict(dataset.get("data_readiness") or {})
        eligible = readiness.get("cross_sectional_daily_lane_eligible")
        blockers = [
            str(item).strip()
            for item in list(readiness.get("data_gap_blockers") or [])
            if str(item).strip()
        ]
        if eligible is False:
            return False, blockers or [CROSS_SECTIONAL_SPOT_BLOCKER]
        return True, blockers
    return False, [CROSS_SECTIONAL_SPOT_BLOCKER]


def _daily_cycle_strategies(
    *,
    as_of: str,
    datasets: list[dict[str, Any]],
    strategy_manifest: dict[str, Any],
    strategy_id_allowlist: list[str] | None = None,
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    blocked_strategy_ids: set[str] = set()
    blockers: set[str] = set()
    allowlist = {
        str(item).strip()
        for item in list(strategy_id_allowlist or [])
        if str(item).strip()
    }
    dataset_readiness_by_profile = _dataset_readiness_by_profile(datasets=datasets)
    for entry in strategy_manifest.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if not bool(entry.get("enabled")):
            continue
        strategy_id = str(entry.get("strategy_id") or "").strip()
        if allowlist and strategy_id not in allowlist:
            continue
        shape = str(entry.get("shape") or "").strip()
        dataset_profile = normalize_dataset_profile(
            shape=shape,
            dataset_profile=str(entry.get("dataset_profile") or "").strip() or None,
        )
        readiness = dict(dataset_readiness_by_profile.get(dataset_profile) or {})
        shape_blockers = [
            str(item).strip()
            for item in list(readiness.get("data_gap_blockers") or [])
            if str(item).strip()
        ]
        if shape_blockers:
            blocked_strategy_ids.add(strategy_id)
            blockers.update(shape_blockers)
            continue
        selected.append(dict(entry))
    return {
        "strategies": selected,
        "blocked_strategy_ids": sorted(blocked_strategy_ids),
        "data_gap_blockers": sorted(blockers),
        "readiness_verdict": "ready" if not blockers else "blocked",
        "selection_as_of": as_of,
    }


def _dataset_readiness_by_shape(*, datasets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _dataset_readiness_by_profile(datasets=datasets)


def _dataset_readiness_by_profile(*, datasets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        normalize_dataset_profile(
            shape=str(dataset.get("shape") or "").strip(),
            dataset_profile=str(dataset.get("dataset_profile") or "").strip() or None,
        ): dict(dataset.get("data_readiness") or {})
        for dataset in datasets
        if str(dataset.get("shape") or "").strip()
    }


def _apply_universe_filter(frame: pd.DataFrame, *, universe_filter: dict[str, Any] | None) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    filtered = frame.copy()
    normalized_filter = dict(universe_filter or {})
    liquidity_buckets = normalized_filter.get("liquidity_buckets")
    if isinstance(liquidity_buckets, list) and liquidity_buckets:
        filtered = filtered.loc[filtered["liquidity_bucket"].isin([str(item) for item in liquidity_buckets])].copy()
    subjects = normalized_filter.get("subjects")
    if isinstance(subjects, list) and subjects:
        allowed_subjects = [str(item).upper() for item in subjects]
        filtered = filtered.loc[filtered["subject"].isin(allowed_subjects)].copy()
    preset = str(
        normalized_filter.get("preset")
        or normalized_filter.get("universe_preset")
        or normalized_filter.get("universe_rule")
        or ""
    ).strip()
    if preset == LIQUID_PERP_CORE_20_PRESET:
        filtered = _apply_liquid_perp_core_20(filtered)
    elif preset == LIQUID_PERP_TIER2_20_PRESET:
        filtered = _apply_liquid_perp_tier2_20(filtered)
    elif preset == LIQUID_PERP_CORE_30_PRESET:
        filtered = _apply_liquid_perp_core_30(filtered)
    return filtered


def _apply_liquid_perp_core_30(frame: pd.DataFrame) -> pd.DataFrame:
    """Top 30 by perp volume with relaxed coverage threshold (0.70 instead of 0.85)."""
    if frame.empty or "subject" not in frame.columns:
        return frame.copy()
    filtered = frame.copy()
    if "has_perp_as_of" in filtered.columns:
        filtered = filtered.loc[filtered["has_perp_as_of"].fillna(False)].copy()
    if "usdm_symbol" in filtered.columns:
        filtered = filtered.loc[filtered["usdm_symbol"].fillna("").astype(str).str.strip() != ""].copy()
    if "perp_execution_eligible" in filtered.columns:
        filtered = filtered.loc[filtered["perp_execution_eligible"].fillna(False)].copy()
    if filtered.empty:
        return filtered
    earliest_timestamp = int(filtered["timestamp_ms"].min()) if "timestamp_ms" in filtered.columns else None
    summaries: list[dict[str, Any]] = []
    for subject, subject_frame in filtered.groupby("subject", sort=True):
        coverage_ratio = float(subject_frame["perp_execution_eligible"].fillna(False).mean()) if "perp_execution_eligible" in subject_frame.columns else 1.0
        executable_start_ms = None
        if "perp_executable_start_ms" in subject_frame.columns:
            executable_values = subject_frame["perp_executable_start_ms"].dropna()
            if not executable_values.empty:
                executable_start_ms = int(executable_values.min())
        # core_30 relaxes the executable_start window AND coverage threshold
        if coverage_ratio < 0.70:  # relaxed from 0.85
            continue
        median_perp_quote_volume = (
            float(subject_frame["perp_quote_volume_usd"].dropna().median())
            if "perp_quote_volume_usd" in subject_frame.columns and subject_frame["perp_quote_volume_usd"].notna().any()
            else 0.0
        )
        median_open_interest_value = (
            float(subject_frame["open_interest_value"].dropna().median())
            if "open_interest_value" in subject_frame.columns and subject_frame["open_interest_value"].notna().any()
            else 0.0
        )
        if median_perp_quote_volume <= 0.0 or median_open_interest_value <= 0.0:
            continue
        summaries.append({
            "subject": str(subject),
            "coverage_ratio": coverage_ratio,
            "median_perp_quote_volume_usd": median_perp_quote_volume,
            "median_open_interest_value": median_open_interest_value,
        })
    if not summaries:
        return filtered.iloc[0:0].copy()
    summaries.sort(
        key=lambda item: (
            -float(item["median_perp_quote_volume_usd"]),
            -float(item["median_open_interest_value"]),
            str(item["subject"]),
        )
    )
    allowed_subjects = {str(item["subject"]) for item in summaries[:30]}
    return filtered.loc[filtered["subject"].isin(allowed_subjects)].copy()


def _liquid_perp_summaries(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if frame.empty or "subject" not in frame.columns:
        return frame.copy(), []
    filtered = frame.copy()
    if "has_perp_as_of" in filtered.columns:
        filtered = filtered.loc[filtered["has_perp_as_of"].fillna(False)].copy()
    if "usdm_symbol" in filtered.columns:
        filtered = filtered.loc[filtered["usdm_symbol"].fillna("").astype(str).str.strip() != ""].copy()
    if "perp_execution_eligible" in filtered.columns:
        filtered = filtered.loc[filtered["perp_execution_eligible"].fillna(False)].copy()
    if filtered.empty:
        return filtered, []
    earliest_timestamp = int(filtered["timestamp_ms"].min()) if "timestamp_ms" in filtered.columns else None
    summaries: list[dict[str, Any]] = []
    for subject, subject_frame in filtered.groupby("subject", sort=True):
        coverage_ratio = float(subject_frame["perp_execution_eligible"].fillna(False).mean()) if "perp_execution_eligible" in subject_frame.columns else 1.0
        executable_start_ms = None
        if "perp_executable_start_ms" in subject_frame.columns:
            executable_values = subject_frame["perp_executable_start_ms"].dropna()
            if not executable_values.empty:
                executable_start_ms = int(executable_values.min())
        if earliest_timestamp is not None and executable_start_ms is not None and executable_start_ms > earliest_timestamp:
            continue
        if coverage_ratio < 0.85:
            continue
        median_perp_quote_volume = (
            float(subject_frame["perp_quote_volume_usd"].dropna().median())
            if "perp_quote_volume_usd" in subject_frame.columns and subject_frame["perp_quote_volume_usd"].notna().any()
            else 0.0
        )
        median_open_interest_value = (
            float(subject_frame["open_interest_value"].dropna().median())
            if "open_interest_value" in subject_frame.columns and subject_frame["open_interest_value"].notna().any()
            else 0.0
        )
        if median_perp_quote_volume <= 0.0 or median_open_interest_value <= 0.0:
            continue
        summaries.append(
            {
                "subject": str(subject),
                "coverage_ratio": coverage_ratio,
                "median_perp_quote_volume_usd": median_perp_quote_volume,
                "median_open_interest_value": median_open_interest_value,
            }
        )
    summaries.sort(
        key=lambda item: (
            -float(item["median_perp_quote_volume_usd"]),
            -float(item["median_open_interest_value"]),
            str(item["subject"]),
        )
    )
    return filtered, summaries


def _apply_liquid_perp_tier2_20(frame: pd.DataFrame) -> pd.DataFrame:
    filtered, summaries = _liquid_perp_summaries(frame)
    if not summaries:
        return filtered.iloc[0:0].copy() if not filtered.empty else filtered
    # Tier 2: ranks 20..40 (the next 20 after the top 20 core).
    tier2 = summaries[20:40]
    if not tier2:
        return filtered.iloc[0:0].copy()
    allowed_subjects = {str(item["subject"]) for item in tier2}
    return filtered.loc[filtered["subject"].isin(allowed_subjects)].copy()


def _apply_liquid_perp_core_20(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "subject" not in frame.columns:
        return frame.copy()
    filtered = frame.copy()
    if "has_perp_as_of" in filtered.columns:
        filtered = filtered.loc[filtered["has_perp_as_of"].fillna(False)].copy()
    if "usdm_symbol" in filtered.columns:
        filtered = filtered.loc[filtered["usdm_symbol"].fillna("").astype(str).str.strip() != ""].copy()
    if "perp_execution_eligible" in filtered.columns:
        filtered = filtered.loc[filtered["perp_execution_eligible"].fillna(False)].copy()
    if filtered.empty:
        return filtered
    earliest_timestamp = int(filtered["timestamp_ms"].min()) if "timestamp_ms" in filtered.columns else None
    summaries: list[dict[str, Any]] = []
    for subject, subject_frame in filtered.groupby("subject", sort=True):
        coverage_ratio = float(subject_frame["perp_execution_eligible"].fillna(False).mean()) if "perp_execution_eligible" in subject_frame.columns else 1.0
        executable_start_ms = None
        if "perp_executable_start_ms" in subject_frame.columns:
            executable_values = subject_frame["perp_executable_start_ms"].dropna()
            if not executable_values.empty:
                executable_start_ms = int(executable_values.min())
        if earliest_timestamp is not None and executable_start_ms is not None and executable_start_ms > earliest_timestamp:
            continue
        if coverage_ratio < 0.85:
            continue
        median_perp_quote_volume = (
            float(subject_frame["perp_quote_volume_usd"].dropna().median())
            if "perp_quote_volume_usd" in subject_frame.columns and subject_frame["perp_quote_volume_usd"].notna().any()
            else 0.0
        )
        median_open_interest_value = (
            float(subject_frame["open_interest_value"].dropna().median())
            if "open_interest_value" in subject_frame.columns and subject_frame["open_interest_value"].notna().any()
            else 0.0
        )
        if median_perp_quote_volume <= 0.0 or median_open_interest_value <= 0.0:
            continue
        summaries.append(
            {
                "subject": str(subject),
                "coverage_ratio": coverage_ratio,
                "median_perp_quote_volume_usd": median_perp_quote_volume,
                "median_open_interest_value": median_open_interest_value,
            }
        )
    if not summaries:
        return filtered.iloc[0:0].copy()
    summaries.sort(
        key=lambda item: (
            -float(item["median_perp_quote_volume_usd"]),
            -float(item["median_open_interest_value"]),
            str(item["subject"]),
        )
    )
    allowed_subjects = {str(item["subject"]) for item in summaries[:20]}
    return filtered.loc[filtered["subject"].isin(allowed_subjects)].copy()


def _strategy_uses_liquid_perp_core_20(strategy_entry: dict[str, Any]) -> bool:
    universe_filter = dict(strategy_entry.get("universe_filter") or {})
    preset = str(
        universe_filter.get("preset")
        or universe_filter.get("universe_preset")
        or universe_filter.get("universe_rule")
        or ""
    ).strip()
    return preset in {LIQUID_PERP_CORE_20_PRESET, LIQUID_PERP_TIER2_20_PRESET, LIQUID_PERP_CORE_30_PRESET}


def _strategy_thesis_profile(strategy_entry: dict[str, Any]) -> dict[str, Any]:
    return dict(strategy_entry.get("thesis_profile") or {})


def _factor_evidence_spread_diagnostics(
    *,
    scored: pd.DataFrame,
    evaluation_mode: str,
    forward_return_column: str = "target_forward_return",
) -> tuple[float, bool, list[dict[str, Any]]]:
    def _cross_sectional_bucket_size(count: int, *, target_bucket_count: int) -> int | None:
        if count < 3:
            return None
        if count >= target_bucket_count:
            return max(1, count // target_bucket_count)
        return 1

    top_minus_bottom_return = 0.0
    monotonicity_passed = False
    quarter_results: list[dict[str, Any]] = []
    if scored.empty:
        return top_minus_bottom_return, monotonicity_passed, quarter_results
    resolved_forward_return_column = str(forward_return_column or "target_forward_return").strip() or "target_forward_return"
    if evaluation_mode == "single_asset_time_series":
        ordered = scored.sort_values("score")
        if len(ordered) >= 5:
            bucket_size = max(1, len(ordered) // 5)
            bottom = ordered.head(bucket_size)
            top = ordered.tail(bucket_size)
            top_minus_bottom_return = float(
                top[resolved_forward_return_column].mean() - bottom[resolved_forward_return_column].mean()
            )
        try:
            quintiles = pd.qcut(
                scored["score"].rank(method="first"),
                5,
                labels=False,
                duplicates="drop",
            )
            bucket_means = (
                scored.assign(_bucket=quintiles)
                .groupby("_bucket")[resolved_forward_return_column]
                .mean()
                .tolist()
            )
            monotonicity_passed = len(bucket_means) >= 3 and bucket_means[0] < bucket_means[-1]
        except ValueError:
            monotonicity_passed = False
        if "timestamp_utc" not in scored.columns:
            return top_minus_bottom_return, monotonicity_passed, quarter_results
        quarter_frame = scored.assign(
            _quarter=scored["timestamp_utc"].astype(str).str.slice(0, 7)
        )
        for quarter, group in quarter_frame.groupby("_quarter", sort=True):
            ordered = group.sort_values("score")
            if len(ordered) < 4:
                continue
            bucket_size = max(1, len(ordered) // 4)
            spread = float(
                ordered.tail(bucket_size)[resolved_forward_return_column].mean()
                - ordered.head(bucket_size)[resolved_forward_return_column].mean()
            )
            quarter_results.append(
                {
                    "quarter": str(quarter),
                    "top_minus_bottom_return": spread,
                    "positive": spread > 0.0,
                }
            )
        return top_minus_bottom_return, monotonicity_passed, quarter_results[-4:]
    if "timestamp_ms" in scored.columns:
        top_bottom_spreads: list[float] = []
        for _, group in scored.groupby("timestamp_ms", sort=True):
            ordered = group.sort_values("score")
            bucket_size = _cross_sectional_bucket_size(len(ordered), target_bucket_count=5)
            if bucket_size is None:
                continue
            bottom = ordered.head(bucket_size)
            top = ordered.tail(bucket_size)
            top_bottom_spreads.append(
                float(top[resolved_forward_return_column].mean() - bottom[resolved_forward_return_column].mean())
            )
        if top_bottom_spreads:
            top_minus_bottom_return = float(sum(top_bottom_spreads) / len(top_bottom_spreads))
        try:
            quintiles = pd.qcut(
                scored["score"].rank(method="first"),
                5,
                labels=False,
                duplicates="drop",
            )
            bucket_means = (
                scored.assign(_bucket=quintiles)
                .groupby("_bucket")[resolved_forward_return_column]
                .mean()
                .tolist()
            )
            monotonicity_passed = len(bucket_means) >= 3 and bucket_means[0] < bucket_means[-1]
        except ValueError:
            monotonicity_passed = False
    if "timestamp_utc" not in scored.columns:
        return top_minus_bottom_return, monotonicity_passed, quarter_results
    quarter_frame = scored.assign(_quarter=scored["timestamp_utc"].astype(str).str.slice(0, 7))
    for quarter, group in quarter_frame.groupby("_quarter", sort=True):
        ordered = group.sort_values("score")
        bucket_size = _cross_sectional_bucket_size(len(ordered), target_bucket_count=4)
        if bucket_size is None:
            continue
        spread = float(
            ordered.tail(bucket_size)[resolved_forward_return_column].mean()
            - ordered.head(bucket_size)[resolved_forward_return_column].mean()
        )
        quarter_results.append(
            {
                "quarter": str(quarter),
                "top_minus_bottom_return": spread,
                "positive": spread > 0.0,
            }
        )
    return top_minus_bottom_return, monotonicity_passed, quarter_results[-4:]


def _filter_cross_sectional_subject_panel_for_derivatives_readiness(
    *,
    frame: pd.DataFrame,
    derivatives_quality_frame: pd.DataFrame,
    feature_columns: list[str],
    derivatives_feature_quality: dict[str, Any] | None,
    strategy_entry: dict[str, Any],
    split: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    split_realization_contract: dict[str, Any],
    data_readiness_contract: dict[str, Any],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None,
    dict[str, Any],
]:
    train_df, validation_df, test_df = split
    required_families = required_derivatives_families(strategy_entry=strategy_entry)
    split_thresholds = derivatives_ready_row_fraction_thresholds(contract=data_readiness_contract)
    derivatives_strategy_quality = summarize_strategy_derivatives_quality(
        feature_frame=frame,
        quality_frame=derivatives_quality_frame,
        feature_columns=feature_columns,
        derivatives_feature_quality=derivatives_feature_quality,
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        required_families=required_families,
        split_ready_row_fraction_thresholds=split_thresholds,
    )
    if str(strategy_entry.get("shape") or "").strip() != "cross_sectional":
        return frame, derivatives_quality_frame, split, derivatives_strategy_quality
    if not strategy_requires_derivatives(strategy_entry=strategy_entry):
        return frame, derivatives_quality_frame, split, derivatives_strategy_quality
    panel_readiness = dict(derivatives_strategy_quality.get("subject_panel_readiness") or {})
    eligible_subjects = [
        str(subject).strip()
        for subject in list(panel_readiness.get("eligible_subjects") or [])
        if str(subject).strip()
    ]
    if not eligible_subjects:
        return frame, derivatives_quality_frame, split, derivatives_strategy_quality
    current_subjects = sorted(
        {
            str(subject).strip()
            for subject in list(frame.get("subject", []))
            if str(subject).strip()
        }
    )
    if len(eligible_subjects) >= len(current_subjects):
        return frame, derivatives_quality_frame, split, derivatives_strategy_quality
    filtered_frame = frame.loc[frame["subject"].isin(eligible_subjects)].copy()
    filtered_quality_frame = derivatives_quality_frame.loc[
        derivatives_quality_frame["subject"].isin(eligible_subjects)
    ].copy()
    filtered_split = _chronological_split(
        filtered_frame,
        time_col="timestamp_ms",
        split_realization_contract=split_realization_contract,
    )
    if filtered_split is None:
        return filtered_frame, filtered_quality_frame, None, derivatives_strategy_quality
    filtered_train_df, filtered_validation_df, filtered_test_df = filtered_split
    filtered_derivatives_strategy_quality = summarize_strategy_derivatives_quality(
        feature_frame=filtered_frame,
        quality_frame=filtered_quality_frame,
        feature_columns=feature_columns,
        derivatives_feature_quality=derivatives_feature_quality,
        train_df=filtered_train_df,
        validation_df=filtered_validation_df,
        test_df=filtered_test_df,
        required_families=required_families,
        split_ready_row_fraction_thresholds=split_thresholds,
    )
    filtered_derivatives_strategy_quality["subject_panel_filter"] = {
        "dropped_subjects_before_training": [
            str(subject).strip()
            for subject in list(panel_readiness.get("excluded_subjects") or [])
            if str(subject).strip()
        ],
        "late_start_subjects": [
            str(subject).strip()
            for subject in list(panel_readiness.get("late_start_subjects") or [])
            if str(subject).strip()
        ],
        "filter_reason": "split_window_derivatives_readiness",
    }
    return filtered_frame, filtered_quality_frame, filtered_split, filtered_derivatives_strategy_quality


def _build_factor_evidence_section(
    *,
    prediction_frame: pd.DataFrame,
    test_metrics: dict[str, Any],
    thesis_profile: dict[str, Any],
    selected_feature_columns: list[str],
    strategy_entry: dict[str, Any],
    forward_return_column: str = "target_forward_return",
    label_contract_id: str = DEFAULT_LABEL_CONTRACT_ID,
) -> dict[str, Any]:
    shape = str(strategy_entry.get("shape") or "").strip()
    evaluation_mode = "single_asset_time_series" if shape == "single_asset" else "cross_sectional_snapshot"
    resolved_forward_return_column = str(forward_return_column or "target_forward_return").strip() or "target_forward_return"
    required_feature_columns = [
        str(item).strip()
        for item in list(thesis_profile.get("required_feature_columns") or [])
        if str(item).strip()
    ]
    missing_required_feature_columns = [
        column for column in required_feature_columns if column not in selected_feature_columns
    ]
    derivatives_feature_columns_present = [
        column for column in selected_feature_columns if column in DERIVATIVES_THESIS_FEATURE_COLUMNS
    ]
    requires_derivatives_features = bool(strategy_entry.get("requires_derivatives_features") or thesis_profile.get("requires_derivatives_features"))
    scored = prediction_frame.copy()
    if not scored.empty:
        scored = scored.loc[
            scored["score"].notna()
            & pd.to_numeric(scored[resolved_forward_return_column], errors="coerce").notna()
        ].copy()
    ic_series: list[float] = []
    if not scored.empty and "timestamp_ms" in scored.columns:
        for _, group in scored.groupby("timestamp_ms", sort=True):
            if len(group) < 2 or group["score"].nunique() < 2:
                continue
            correlation = _safe_spearman_rank_corr(group["score"], group[resolved_forward_return_column])
            if correlation is not None:
                ic_series.append(float(correlation))
    if not ic_series and len(scored) >= 3 and scored["score"].nunique() >= 2:
        fallback_correlation = _safe_spearman_rank_corr(scored["score"], scored[resolved_forward_return_column])
        if fallback_correlation is not None:
            ic_series.append(float(fallback_correlation))
    rank_ic_mean = float(sum(ic_series) / len(ic_series)) if ic_series else 0.0
    rank_ic_positive_rate = float(sum(1 for value in ic_series if value > 0.0) / len(ic_series)) if ic_series else 0.0
    top_minus_bottom_return, monotonicity_passed, quarter_results = _factor_evidence_spread_diagnostics(
        scored=scored,
        evaluation_mode=evaluation_mode,
        forward_return_column=resolved_forward_return_column,
    )
    positive_quarters = sum(1 for item in quarter_results if bool(item.get("positive")))
    # W2-B (validation_contract v8 -> v9): denominator is sum-of-POSITIVE-quarters
    # only. Previously sum(all), which is mathematically ill-defined when the
    # test segment contains a negative quarter — it can drive the ratio above 1.0
    # and makes the cap a function of negative-quarter magnitude rather than of
    # actual positive-edge concentration. The new formula is bounded [0, 1] and
    # answers "of the positive quarters, how concentrated is the edge in one
    # quarter?" which matches the over-fit concern that the gate is meant to
    # detect. See threshold_provenance.md "validation_contract v9 calibration".
    positive_edge_contributions = [
        float(item.get("top_minus_bottom_return", 0.0) or 0.0)
        for item in quarter_results
        if float(item.get("top_minus_bottom_return", 0.0) or 0.0) > 0.0
    ]
    cumulative_positive_edge = sum(positive_edge_contributions)
    max_positive_quarter = max(positive_edge_contributions, default=0.0)
    concentration_ratio = (
        max_positive_quarter / cumulative_positive_edge
        if cumulative_positive_edge > 0.0
        else (1.0 if max_positive_quarter > 0.0 else 0.0)
    )
    intended_horizon_return = top_minus_bottom_return
    passed = (
        bool(thesis_profile)
        and not missing_required_feature_columns
        and (not requires_derivatives_features or bool(derivatives_feature_columns_present))
        and abs(rank_ic_mean) >= 0.01
        and rank_ic_positive_rate >= 0.52
        and top_minus_bottom_return > 0.0
        and monotonicity_passed
        and intended_horizon_return > 0.0
        and float(test_metrics.get("max_trade_participation_rate", 0.0) or 0.0) <= 0.005
        and float(test_metrics.get("max_inventory_participation_rate", 0.0) or 0.0) <= 0.02
        and positive_quarters >= 2
        # W2-B (validation_contract v8 -> v9): concentration cap raised from 0.50
        # to 0.65 to admit small-sample (n<=4 quarters) variance. Mirrors
        # config/quant_research/validation_contract.json factor_evidence.
        # max_single_quarter_edge_contribution_ratio_max. Both sites must be
        # bumped together (acknowledged dual-source; see threshold_provenance.md
        # "validation_contract v9 calibration" entry).
        and concentration_ratio <= 0.65
    )
    return {
        "thesis_id": str(thesis_profile.get("thesis_id") or strategy_entry.get("strategy_id") or "").strip(),
        "evaluation_mode": evaluation_mode,
        "label_contract_id": str(label_contract_id or DEFAULT_LABEL_CONTRACT_ID),
        "forward_return_column": resolved_forward_return_column,
        "rank_ic_mean": rank_ic_mean,
        "rank_ic_positive_rate": rank_ic_positive_rate,
        "top_minus_bottom_return": top_minus_bottom_return,
        "monotonicity_passed": monotonicity_passed,
        "decay_curve": {
            "intended_horizon_bars": int(thesis_profile.get("intended_holding_horizon_bars") or 0),
            "intended_horizon_return": intended_horizon_return,
        },
        "turnover": float(test_metrics.get("turnover", 0.0) or 0.0),
        "max_trade_participation_rate": float(test_metrics.get("max_trade_participation_rate", 0.0) or 0.0),
        "max_inventory_participation_rate": float(test_metrics.get("max_inventory_participation_rate", 0.0) or 0.0),
        "regime_split_results": quarter_results,
        "required_feature_columns": required_feature_columns,
        "selected_feature_columns": list(selected_feature_columns),
        "missing_required_feature_columns": missing_required_feature_columns,
        "requires_derivatives_features": requires_derivatives_features,
        "derivatives_feature_columns_present": derivatives_feature_columns_present,
        "passed": passed,
    }

def _initial_data_gap_blockers(
    *,
    shape: str,
    strategy_entry: dict[str, Any],
    frame: pd.DataFrame,
    dataset_data_readiness: dict[str, Any] | None,
    contract: dict[str, Any],
    subject_count_override: int | None = None,
) -> list[str]:
    blockers: list[str] = []
    if strategy_requires_temporal_event_tape(strategy_entry=strategy_entry):
        blockers.append(DISCOVERY_EVENT_BLOCKER)
    if str(shape) == "cross_sectional":
        subject_count = (
            int(subject_count_override)
            if subject_count_override is not None
            else (int(frame["subject"].nunique()) if not frame.empty else 0)
        )
        if (
            not dataset_data_readiness
            and not _strategy_uses_liquid_perp_core_20(strategy_entry)
            and subject_count < cross_sectional_subject_min(contract=contract)
        ):
            blockers.append(CROSS_SECTIONAL_SPOT_BLOCKER)
    elif str(shape) == "single_asset":
        has_4h = not frame.empty
        has_1d = "daily_close" in frame.columns and frame["daily_close"].notna().any()
        if not (has_4h and has_1d):
            blockers.append(SINGLE_ASSET_SPOT_BLOCKER)
    if dataset_data_readiness:
        blockers.extend(
            str(item).strip()
            for item in list(dict(dataset_data_readiness).get("data_gap_blockers") or [])
            if str(item).strip()
        )
    return sorted(set(blockers))


def _insufficient_history_blocker(*, shape: str) -> str:
    return CROSS_SECTIONAL_SPOT_BLOCKER if str(shape) == "cross_sectional" else SINGLE_ASSET_SPOT_BLOCKER


def _resolve_feature_family_entries(*, artifacts_root: Path, strategy_entry: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def _resolve_strategy_model_definition(*, artifacts_root: Path, strategy_entry: dict[str, Any]) -> dict[str, Any] | None:
    return None


def _apply_feature_family_registry(
    *,
    frame: pd.DataFrame,
    feature_family_entries: list[dict[str, Any]],
    shape: str,
) -> tuple[pd.DataFrame, list[str]]:
    if frame.empty or not feature_family_entries:
        return frame.copy(), []
    enriched = frame.copy()
    generated_columns: list[str] = []
    time_group = "subject" if "subject" in enriched.columns else None
    for family in feature_family_entries:
        transforms = [dict(item) for item in family.get("transforms", []) if isinstance(item, dict)]
        for transform in transforms:
            feature_name = str(transform.get("feature_name") or "").strip()
            transform_name = str(transform.get("transform") or "").strip()
            source_column = str(transform.get("source_column") or "").strip()
            if not feature_name or not transform_name:
                continue
            if transform_name in {"lag", "difference", "ema", "rolling_mean", "rolling_std", "zscore", "clip"} and source_column not in enriched.columns:
                continue
            series: pd.Series | None = None
            if transform_name == "lag":
                periods = int(transform.get("lag_bars", transform.get("periods", 1)) or 1)
                series = _series_by_subject(enriched, source_column, periods=periods, op="lag", group_column=time_group)
            elif transform_name == "difference":
                periods = int(transform.get("lag_bars", transform.get("periods", 1)) or 1)
                lagged = _series_by_subject(enriched, source_column, periods=periods, op="lag", group_column=time_group)
                series = enriched[source_column] - lagged
            elif transform_name == "ratio":
                numerator = str(transform.get("numerator_column") or source_column or "").strip()
                denominator = str(transform.get("denominator_column") or "").strip()
                if numerator in enriched.columns and denominator in enriched.columns:
                    denom = enriched[denominator].replace(0.0, np.nan)
                    series = (enriched[numerator] / denom).replace([np.inf, -np.inf], np.nan)
            elif transform_name == "ema":
                span = int(transform.get("window", transform.get("span", 5)) or 5)
                series = _series_by_subject(enriched, source_column, periods=span, op="ema", group_column=time_group)
            elif transform_name == "rolling_mean":
                window = int(transform.get("window", 5) or 5)
                series = _series_by_subject(enriched, source_column, periods=window, op="rolling_mean", group_column=time_group)
            elif transform_name == "rolling_std":
                window = int(transform.get("window", 5) or 5)
                series = _series_by_subject(enriched, source_column, periods=window, op="rolling_std", group_column=time_group)
            elif transform_name == "zscore":
                window = int(transform.get("window", 20) or 20)
                rolling_mean = _series_by_subject(enriched, source_column, periods=window, op="rolling_mean", group_column=time_group)
                rolling_std = _series_by_subject(enriched, source_column, periods=window, op="rolling_std", group_column=time_group).replace(0.0, np.nan)
                series = (enriched[source_column] - rolling_mean) / rolling_std
            elif transform_name == "rank":
                rank_source = str(transform.get("source_column") or "").strip()
                if rank_source in enriched.columns and "timestamp_ms" in enriched.columns:
                    series = enriched.groupby("timestamp_ms")[rank_source].rank(pct=True)
            elif transform_name == "interaction":
                left = str(transform.get("left_column") or "").strip()
                right = str(transform.get("right_column") or "").strip()
                if left in enriched.columns and right in enriched.columns:
                    series = enriched[left] * enriched[right]
            elif transform_name == "clip":
                lower = float(transform.get("clip_min", transform.get("lower", -5.0)) or -5.0)
                upper = float(transform.get("clip_max", transform.get("upper", 5.0)) or 5.0)
                series = enriched[source_column].clip(lower=lower, upper=upper)
            if series is None:
                continue
            enriched[feature_name] = pd.Series(series, index=enriched.index, dtype="float64").fillna(0.0)
            if feature_name not in generated_columns:
                generated_columns.append(feature_name)
    return enriched, generated_columns


def _series_by_subject(
    frame: pd.DataFrame,
    column: str,
    *,
    periods: int,
    op: str,
    group_column: str | None,
) -> pd.Series:
    if group_column and group_column in frame.columns:
        grouped = frame.groupby(group_column)[column]
        if op == "lag":
            return grouped.shift(periods)
        if op == "ema":
            return grouped.transform(lambda item: item.ewm(span=max(periods, 1), adjust=False).mean())
        if op == "rolling_mean":
            return grouped.transform(lambda item: item.rolling(window=max(periods, 1), min_periods=1).mean())
        if op == "rolling_std":
            return grouped.transform(lambda item: item.rolling(window=max(periods, 1), min_periods=1).std())
    if op == "lag":
        return frame[column].shift(periods)
    if op == "ema":
        return frame[column].ewm(span=max(periods, 1), adjust=False).mean()
    if op == "rolling_mean":
        return frame[column].rolling(window=max(periods, 1), min_periods=1).mean()
    if op == "rolling_std":
        return frame[column].rolling(window=max(periods, 1), min_periods=1).std()
    return frame[column]


def _candidate_from_frame(frame: pd.DataFrame) -> QuantUniverseCandidate | None:
    if frame.empty:
        return None
    row = frame.sort_values("timestamp_ms").iloc[-1]
    return QuantUniverseCandidate(
        subject=str(row["subject"]),
        spot_symbol=str(row["spot_symbol"]),
        usdm_symbol=str(row["usdm_symbol"]) if str(row.get("usdm_symbol", "")).strip() not in {"", "0", "nan", "None"} else None,
        selection_rank=int(row["selection_rank"]),
        selection_score=float(row.get("rolling_median_quote_volume_usd_30d", 0.0) or 0.0),
        selection_metric=PIT_SELECTION_METRIC,
        selection_window_start_utc=str(frame.sort_values("timestamp_ms").iloc[0]["timestamp_utc"]),
        selection_window_end_utc=str(row["timestamp_utc"]),
        rolling_median_quote_volume_usd_30d=float(row.get("rolling_median_quote_volume_usd_30d", 0.0) or 0.0),
        rolling_mean_quote_volume_usd_30d=float(row.get("rolling_median_quote_volume_usd_30d", 0.0) or 0.0),
        listing_age_days_as_of=int(row["listing_age_days_as_of"]),
        first_spot_bar_utc=str(frame.sort_values("timestamp_ms").iloc[0]["timestamp_utc"]),
        first_perp_bar_utc=None,
        liquidity_bucket=str(row["liquidity_bucket"]),
        is_stablecoin=False,
        is_pegged_asset=False,
        field_provenance={"source": "feature_frame_reconstruction"},
    )


def _split_row_counts(
    *,
    train_df: pd.DataFrame | None = None,
    validation_df: pd.DataFrame | None = None,
    test_df: pd.DataFrame | None = None,
) -> dict[str, int]:
    return {
        "train": int(len(train_df)) if train_df is not None else 0,
        "validation": int(len(validation_df)) if validation_df is not None else 0,
        "test": int(len(test_df)) if test_df is not None else 0,
    }


def _resolve_repo_relative_path(path_text: str | Path) -> Path:
    candidate = Path(str(path_text))
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def _fixed_set_pairwise_seed(*, base_seed: int, candidate_label: str, reference_label: str) -> int:
    digest = hashlib.sha1(f"{candidate_label}|{reference_label}".encode("utf-8")).hexdigest()[:8]
    return int(base_seed) + int(digest, 16)


def _fixed_set_derivatives_fields(*, feature_columns: list[str]) -> list[str]:
    families: list[str] = []
    for family_name in ("funding", "open_interest", "basis"):
        family_columns = set(DERIVATIVES_FAMILY_COLUMNS.get(family_name) or ())
        if any(column in family_columns for column in feature_columns):
            families.append(family_name)
    field_map = {
        "funding": "funding_rate",
        "open_interest": "open_interest",
        "basis": "perp_close",
    }
    return [field_map[family_name] for family_name in families if family_name in field_map]


def _fixed_set_strategy_entry_for_comparison(experiment_spec: dict[str, Any]) -> dict[str, Any]:
    feature_columns = [
        str(item).strip()
        for item in list(experiment_spec.get("feature_columns") or [])
        if str(item).strip()
    ]
    return {
        "shape": str(experiment_spec.get("shape") or "").strip(),
        "model_family": str(experiment_spec.get("model_family") or "").strip(),
        "research_lane": str(experiment_spec.get("research_lane") or "").strip(),
        "requires_derivatives_features": bool(experiment_spec.get("requires_derivatives_features")),
        "thesis_profile": dict(experiment_spec.get("thesis_profile") or {}),
        "data_dependencies": {
            "derivatives_fields": _fixed_set_derivatives_fields(feature_columns=feature_columns),
        },
    }


def _load_fixed_set_reference_artifact(*, artifacts_root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    experiment_id = str(entry.get("experiment_id") or "").strip()
    experiment_root = artifacts_root / "experiments" / _experiment_directory_name(experiment_id)
    if not experiment_root.exists():
        canonical_root = QUANT_ARTIFACTS_ROOT.expanduser().resolve()
        canonical_experiment_root = canonical_root / "experiments" / _experiment_directory_name(experiment_id)
        if canonical_experiment_root.exists():
            experiment_root = canonical_experiment_root
        else:
            raise FileNotFoundError(f"fixed-set reference experiment missing: {experiment_root}")
    return {
        "label": str(entry.get("label") or "").strip(),
        "role": str(entry.get("role") or "").strip(),
        "experiment_id": experiment_id,
        "experiment_root": experiment_root,
        "experiment_spec": dict(read_json(experiment_root / "experiment_spec.json")),
        "validation_report": dict(read_json(experiment_root / "validation_report.json")),
        "profile_constraints_override": dict(entry.get("profile_constraints_override") or {}),
    }


def _fixed_set_constraints(
    *,
    experiment_spec: dict[str, Any],
    overlay_context: dict[str, Any],
    profile_constraints_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = dict(experiment_spec.get("profile_constraints") or {})
    for key, value in dict(profile_constraints_override or {}).items():
        if value is None:
            constraints.pop(str(key), None)
        else:
            constraints[str(key)] = value
    constraints["strategy_profile"] = str(experiment_spec.get("strategy_profile") or "")
    resolved_overlay_context = {
        key: str(value).strip()
        for key, value in dict(overlay_context or {}).items()
        if str(value).strip()
    }
    if resolved_overlay_context:
        constraints["position_multiplier_overlay_context"] = resolved_overlay_context
    return constraints


def _reported_worst_regime_from_report(report: dict[str, Any]) -> float | None:
    if report.get("worst_regime_median_oos_sharpe") is not None:
        return float(report["worst_regime_median_oos_sharpe"])
    regime_holdout = dict(report.get("regime_holdout") or {})
    value = regime_holdout.get("worst_regime_median_oos_sharpe")
    if value is None:
        return None
    return float(value)


def _reported_execution_stress_max_trade_participation_rate(report: dict[str, Any]) -> float | None:
    if report.get("execution_stress_max_trade_participation_rate") is not None:
        return float(report["execution_stress_max_trade_participation_rate"])
    execution_stress = dict(report.get("execution_stress") or {})
    value = execution_stress.get("max_trade_participation_rate")
    if value is None:
        return None
    return float(value)


def _recompute_fixed_set_candidate(
    *,
    comparison_base_frame: pd.DataFrame,
    comparison_derivatives_quality_frame: pd.DataFrame,
    derivatives_feature_quality: dict[str, Any] | None,
    candidate_artifact: dict[str, Any],
    validation_contract: dict[str, Any],
    overlay_context: dict[str, Any],
    data_readiness_contract: dict[str, Any],
    base_execution_cost_model: dict[str, Any],
    stress_execution_cost_model: dict[str, Any],
) -> dict[str, Any]:
    spec = dict(candidate_artifact["experiment_spec"])
    frame = _apply_universe_filter(
        comparison_base_frame,
        universe_filter=dict(spec.get("universe_filter") or {}),
    )
    constraints = _fixed_set_constraints(
        experiment_spec=spec,
        overlay_context=overlay_context,
        profile_constraints_override=dict(candidate_artifact.get("profile_constraints_override") or {}),
    )
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    resolved_split_realization_contract = resolve_split_realization_contract(
        contract=dict(spec.get("split_realization_contract") or {}),
        shape=str(spec.get("shape") or "cross_sectional"),
        bar_interval_ms=infer_interval_ms(frame["timestamp_ms"]) if not frame.empty else None,
    )
    split = _chronological_split(
        frame,
        time_col="timestamp_ms",
        split_realization_contract=resolved_split_realization_contract,
    )
    if split is None:
        raise ValueError(f"fixed-set comparison could not split {candidate_artifact['label']}")
    strategy_entry = _fixed_set_strategy_entry_for_comparison(spec)
    (
        frame,
        _filtered_derivatives_quality_frame,
        filtered_split,
        derivatives_strategy_quality,
    ) = _filter_cross_sectional_subject_panel_for_derivatives_readiness(
        frame=frame,
        derivatives_quality_frame=comparison_derivatives_quality_frame,
        feature_columns=list(spec.get("feature_columns") or []),
        derivatives_feature_quality=derivatives_feature_quality,
        strategy_entry=strategy_entry,
        split=split,
        split_realization_contract=resolved_split_realization_contract,
        data_readiness_contract=data_readiness_contract,
    )
    if filtered_split is None:
        raise ValueError(f"fixed-set comparison lost split after readiness filter for {candidate_artifact['label']}")
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    walk_forward = _run_walk_forward(
        frame=frame,
        shape=str(spec.get("shape") or "cross_sectional"),
        model_family=str(spec["model_family"]),
        feature_columns=list(spec.get("feature_columns") or []),
        constraints=constraints,
        split_realization_contract=resolved_split_realization_contract,
        target_column=str(spec.get("target_column") or "target_up"),
        execution_cost_model=base_execution_cost_model,
        stress_execution_cost_model=stress_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=execution_capacity_limits(validation_contract),
        validation_contract=validation_contract,
        model_definition=None,
        include_periods=True,
    )
    periods = extract_period_frame(
        candidate_label=str(candidate_artifact["label"]),
        walk_forward=walk_forward,
    )
    periods_per_year = fixed_set_periods_per_year(
        bar_interval_ms=int(resolved_split_realization_contract["bar_interval_ms"]),
        evaluation_step_bars=int(resolved_split_realization_contract["realization_step_bars"]),
    )
    performance = fixed_set_performance_summary(
        periods["net_period_return"],
        periods_per_year=periods_per_year,
    )
    validation_report = dict(candidate_artifact.get("validation_report") or {})
    summary = {
        "candidate_label": str(candidate_artifact["label"]),
        "role": str(candidate_artifact.get("role") or ""),
        "experiment_id": str(candidate_artifact["experiment_id"]),
        "reported_walk_forward_median_oos_sharpe": float(
            validation_report.get("walk_forward_median_oos_sharpe")
            or dict(validation_report.get("walk_forward") or {}).get("median_oos_sharpe")
            or 0.0
        ),
        "recomputed_walk_forward_median_oos_sharpe": float(walk_forward.get("median_oos_sharpe") or 0.0),
        "reported_worst_regime_median_oos_sharpe": _reported_worst_regime_from_report(validation_report),
        "reported_execution_stress_max_trade_participation_rate": _reported_execution_stress_max_trade_participation_rate(validation_report),
        "full_oos_period_count": int(len(periods)),
        "full_oos_start_utc": str(periods["timestamp_utc"].iloc[0]) if not periods.empty else None,
        "full_oos_end_utc": str(periods["timestamp_utc"].iloc[-1]) if not periods.empty else None,
        "full_oos_cumulative_net_return": float(performance["net_return"]),
        "full_oos_period_sharpe": float(performance["sharpe"]),
        "full_oos_max_drawdown": float(performance["max_drawdown"]),
        "full_oos_loss_period_fraction": float((periods["net_period_return"] < 0.0).mean()) if not periods.empty else 0.0,
        "full_oos_mean_period_return": float(periods["net_period_return"].mean()) if not periods.empty else 0.0,
        "full_oos_turnover_total": float(periods["turnover"].sum()) if not periods.empty else 0.0,
        "full_oos_max_trade_participation_rate": float(periods["trade_participation_rate"].max()) if not periods.empty else 0.0,
        "eligible_subject_count": int(
            dict(derivatives_strategy_quality.get("subject_panel_readiness") or {}).get("eligible_subject_count", 0) or 0
        ),
    }
    return {
        "walk_forward": walk_forward,
        "periods": periods,
        "summary": summary,
        "periods_per_year": int(periods_per_year),
    }


def _write_fixed_set_comparison_markdown(
    *,
    output_path: Path,
    section: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append("# Fixed-Set Paired Comparison")
    lines.append("")
    lines.append(f"- Status: `{section.get('status')}`")
    lines.append(f"- Candidate: `{section.get('candidate_label')}`")
    lines.append(f"- Applicable: `{section.get('applicable')}`")
    lines.append(f"- Research gate passed: `{dict(section.get('research_gate') or {}).get('passed')}`")
    lines.append(f"- Promotion gate passed: `{dict(section.get('promotion_gate') or {}).get('passed')}`")
    if list(section.get("candidate_summaries") or []):
        lines.append("")
        lines.append("## Candidate Summary")
        lines.append("")
        lines.append("| Candidate | Reported WF Median | Recomputed WF Median | Full OOS CumRet | Full OOS Sharpe | Worst Regime |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for item in list(section.get("candidate_summaries") or []):
            worst_regime = item.get("reported_worst_regime_median_oos_sharpe")
            lines.append(
                "| {label} | {reported:.3f} | {recomputed:.3f} | {cumret:.3f} | {sharpe:.3f} | {worst} |".format(
                    label=item["candidate_label"],
                    reported=float(item.get("reported_walk_forward_median_oos_sharpe", 0.0) or 0.0),
                    recomputed=float(item.get("recomputed_walk_forward_median_oos_sharpe", 0.0) or 0.0),
                    cumret=float(item.get("full_oos_cumulative_net_return", 0.0) or 0.0),
                    sharpe=float(item.get("full_oos_period_sharpe", 0.0) or 0.0),
                    worst=("n/a" if worst_regime is None else f"{float(worst_regime):.3f}"),
                )
            )
    if list(section.get("pairwise_results") or []):
        lines.append("")
        lines.append("## Candidate vs Fixed Set")
        lines.append("")
        lines.append("| Candidate | Reference | N | CumRet Diff | Sharpe Diff | Win Rate | Sign p | P(Candidate > Reference CumRet) |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for item in list(section.get("pairwise_results") or []):
            bootstrap = dict(item.get("bootstrap") or {})
            lines.append(
                "| {a} | {b} | {n} | {cumdiff:.3f} | {shdiff:.3f} | {winrate} | {pvalue} | {prob:.3f} |".format(
                    a=item["candidate_a"],
                    b=item["candidate_b"],
                    n=int(item.get("aligned_period_count", 0) or 0),
                    cumdiff=float(item.get("observed_cumulative_return_diff", 0.0) or 0.0),
                    shdiff=float(item.get("observed_sharpe_diff", 0.0) or 0.0),
                    winrate=("n/a" if item.get("period_win_rate_a_gt_b") is None else f"{float(item['period_win_rate_a_gt_b']):.3f}"),
                    pvalue=("n/a" if item.get("sign_test_pvalue") is None else f"{float(item['sign_test_pvalue']):.4f}"),
                    prob=float(bootstrap.get("probability_a_beats_b_on_cumulative_return", 0.0) or 0.0),
                )
            )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_fixed_set_comparison(
    *,
    as_of: str,
    artifacts_root: Path,
    experiment_root: Path,
    current_experiment_id: str,
    current_experiment_spec: dict[str, Any],
    current_validation_report: dict[str, Any],
    comparison_base_frame: pd.DataFrame,
    comparison_derivatives_quality_frame: pd.DataFrame,
    derivatives_feature_quality: dict[str, Any] | None,
    validation_contract: dict[str, Any],
    overlay_context: dict[str, Any],
) -> dict[str, Any]:
    contract = load_fixed_set_comparison_contract()
    applicability = fixed_set_comparison_applicability(
        shape=str(current_experiment_spec.get("shape") or ""),
        bar_interval_ms=int(current_experiment_spec.get("bar_interval_ms") or 0),
        target_horizon_bars=int(current_experiment_spec.get("label_horizon_bars") or 0),
        label_contract_id=str(current_experiment_spec.get("label_contract_id") or ""),
        research_lane=str(current_experiment_spec.get("research_lane") or ""),
        contract=contract,
    )
    candidate_label = resolve_fixed_set_candidate_label(
        strategy_id=str(current_experiment_spec.get("strategy_id") or ""),
        contract=contract,
    )
    base_section = {
        "contract_version": str(contract.get("contract_version") or ""),
        "as_of": as_of,
        "candidate_label": candidate_label,
        "applicable": bool(applicability.get("applicable")),
        "applicability": applicability,
        "reference_candidate_labels": fixed_set_reference_labels(contract),
        "research_gate": {"passed": True, "blocker_codes": []},
        "promotion_gate": {"passed": True, "blocker_codes": []},
        "artifact_paths": {},
    }
    if not applicability.get("applicable"):
        base_section["status"] = "not_applicable"
        return base_section
    try:
        bootstrap_contract = dict(contract.get("bootstrap") or {})
        bootstrap_iterations = int(bootstrap_contract.get("iterations", 4000) or 4000)
        bootstrap_seed = int(bootstrap_contract.get("seed", 20260502) or 20260502)
        data_readiness_contract = load_data_readiness_contract()
        base_execution_cost_model, stress_execution_cost_model = _resolved_execution_cost_models()
        current_artifact = {
            "label": candidate_label,
            "role": "candidate_under_review",
            "experiment_id": current_experiment_id,
            "experiment_spec": dict(current_experiment_spec),
            "validation_report": dict(current_validation_report),
        }
        reference_artifacts = [
            _load_fixed_set_reference_artifact(artifacts_root=artifacts_root, entry=entry)
            for entry in fixed_set_reference_entries(contract)
            if str(entry.get("label") or "").strip() != candidate_label
        ]
        candidate_artifacts = [current_artifact, *reference_artifacts]
        results_by_label: dict[str, dict[str, Any]] = {}
        for artifact in candidate_artifacts:
            results_by_label[str(artifact["label"])] = _recompute_fixed_set_candidate(
                comparison_base_frame=comparison_base_frame,
                comparison_derivatives_quality_frame=comparison_derivatives_quality_frame,
                derivatives_feature_quality=derivatives_feature_quality,
                candidate_artifact=artifact,
                validation_contract=validation_contract,
                overlay_context=overlay_context,
                data_readiness_contract=data_readiness_contract,
                base_execution_cost_model=base_execution_cost_model,
                stress_execution_cost_model=stress_execution_cost_model,
            )
        ordered_labels = list(fixed_set_reference_labels(contract))
        if candidate_label not in ordered_labels:
            ordered_labels.append(candidate_label)
        ordered_labels = [label for label in ordered_labels if label in results_by_label]
        aligned_period_returns: pd.DataFrame | None = None
        for label in ordered_labels:
            period_frame = results_by_label[label]["periods"].copy()
            period_frame.rename(columns={"net_period_return": label}, inplace=True)
            current_panel = period_frame[["timestamp_ms", "timestamp_utc", label]]
            aligned_period_returns = current_panel if aligned_period_returns is None else aligned_period_returns.merge(
                current_panel,
                on=["timestamp_ms", "timestamp_utc"],
                how="outer",
            )
        if aligned_period_returns is None:
            aligned_period_returns = pd.DataFrame(columns=["timestamp_ms", "timestamp_utc"])
        aligned_period_returns = aligned_period_returns.sort_values("timestamp_ms").reset_index(drop=True)
        pairwise_results: list[dict[str, Any]] = []
        for entry in fixed_set_reference_entries(contract):
            reference_label = str(entry.get("label") or "").strip()
            if reference_label == candidate_label or reference_label not in results_by_label:
                continue
            pairwise_results.append(
                pairwise_comparison(
                    label_a=candidate_label,
                    label_b=reference_label,
                    periods_a=results_by_label[candidate_label]["periods"],
                    periods_b=results_by_label[reference_label]["periods"],
                    periods_per_year=int(results_by_label[candidate_label]["periods_per_year"]),
                    iterations=bootstrap_iterations,
                    seed=_fixed_set_pairwise_seed(
                        base_seed=bootstrap_seed,
                        candidate_label=candidate_label,
                        reference_label=reference_label,
                    ),
                )
            )
        candidate_summaries = [
            dict(results_by_label[label]["summary"])
            for label in ordered_labels
        ]
        candidate_summaries = sorted(
            candidate_summaries,
            key=lambda item: float(item.get("full_oos_cumulative_net_return", 0.0) or 0.0),
            reverse=True,
        )
        promotion_gate = build_promotion_gate_assessment(
            candidate_label=candidate_label,
            candidate_summaries=candidate_summaries,
            pairwise_results=pairwise_results,
            contract=contract,
        )
        section = {
            **base_section,
            "status": "computed",
            "candidate_order": ordered_labels,
            "candidate_summaries": candidate_summaries,
            "pairwise_results": pairwise_results,
            "research_gate": {"passed": True, "blocker_codes": []},
            "promotion_gate": promotion_gate,
        }
        json_path = experiment_root / "fixed_set_comparison.json"
        markdown_path = experiment_root / "fixed_set_comparison.md"
        aligned_returns_path = experiment_root / "fixed_set_aligned_period_returns.csv"
        pairwise_csv_path = experiment_root / "fixed_set_pairwise_comparisons.csv"
        aligned_period_returns.to_csv(aligned_returns_path, index=False)
        pd.DataFrame.from_records(pairwise_results).to_csv(pairwise_csv_path, index=False)
        _write_fixed_set_comparison_markdown(output_path=markdown_path, section=section)
        section["artifact_paths"] = {
            "comparison_json_path": portable_path(json_path, repo_root=ROOT),
            "comparison_markdown_path": portable_path(markdown_path, repo_root=ROOT),
            "aligned_period_returns_path": portable_path(aligned_returns_path, repo_root=ROOT),
            "pairwise_comparisons_path": portable_path(pairwise_csv_path, repo_root=ROOT),
        }
        write_json(json_path, section)
        return section
    except Exception as exc:
        return {
            **base_section,
            "status": "error",
            "error": str(exc),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
            "research_gate": {
                "passed": False,
                "blocker_codes": ["fixed_set_comparison_error"],
            },
            "promotion_gate": {
                "passed": False,
                "blocker_codes": ["fixed_set_comparison_error"],
            },
        }


def _apply_universe_metadata_fields(
    payload: dict[str, Any],
    *,
    universe_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    decorated = dict(payload)
    decorated.update(pit_universe_artifact_metadata(universe_metadata))
    return decorated


def update_alpha_registry(*, artifacts_root: Path, as_of: str, experiments: list[dict[str, Any]]) -> dict[str, Any]:
    raise_legacy_surface_frozen(
        operation="alpha_registry_update",
        as_of=as_of,
        artifacts_root=artifacts_root,
    )


def _run_experiment(
    *,
    as_of: str,
    artifacts_root: Path,
    frame: pd.DataFrame,
    feature_quality_frame: pd.DataFrame,
    feature_quality: dict[str, Any] | None,
    derivatives_quality_frame: pd.DataFrame,
    derivatives_feature_quality: dict[str, Any] | None,
    shape: str,
    model_family: str,
    strategy_profile: str,
    feature_columns: list[str],
    compiler_backend: str,
    subject: str | None,
    candidate: QuantUniverseCandidate | None,
    strategy_entry: dict[str, Any],
    model_definition: dict[str, Any] | None,
    split_realization_contract: dict[str, Any],
    label_contract_id: str,
    target_column: str,
    forward_return_column: str,
    dataset_data_readiness: dict[str, Any] | None,
    dataset_research_dataset: dict[str, Any] | None,
    feature_admission_bundle: dict[str, Any] | None,
    reproducibility_bundle: dict[str, Any] | None,
    universe_metadata: dict[str, Any] | None,
    generated_feature_columns: list[str] | None,
) -> dict[str, Any]:
    experiment_id = f"{as_of}-{strategy_entry['strategy_id']}"
    experiment_root = artifacts_root / "experiments" / _experiment_directory_name(experiment_id)
    experiment_root.mkdir(parents=True, exist_ok=True)
    comparison_base_frame = frame.copy()
    comparison_derivatives_quality_frame = derivatives_quality_frame.copy()
    resolved_split_realization_contract = resolve_split_realization_contract(
        contract=split_realization_contract,
        shape=shape,
        bar_interval_ms=infer_interval_ms(frame["timestamp_ms"]) if not frame.empty else None,
    )
    resolved_feature_admission_bundle = dict(feature_admission_bundle or {})
    feature_admission_policy = dict(resolved_feature_admission_bundle.get("feature_admission_policy") or {})
    available_numeric_columns = list(resolved_feature_admission_bundle.get("available_numeric_columns") or [])
    numeric_feature_columns = list(resolved_feature_admission_bundle.get("numeric_feature_columns") or [])
    excluded_numeric_columns = list(resolved_feature_admission_bundle.get("excluded_numeric_columns") or [])
    reproducibility = build_reproducibility_section(
        source_commit_sha=str((reproducibility_bundle or {}).get("source_commit_sha") or ""),
        dataset_fingerprint=str((reproducibility_bundle or {}).get("dataset_fingerprint") or ""),
        feature_hash=str((reproducibility_bundle or {}).get("feature_hash") or ""),
        dataset_manifest_path=str((reproducibility_bundle or {}).get("dataset_manifest_path") or ""),
        feature_manifest_path=str((reproducibility_bundle or {}).get("feature_manifest_path") or ""),
    )
    resolved_universe_metadata = pit_universe_artifact_metadata(universe_metadata)
    cross_sectional_subject_count_before_execution_filter = (
        int(frame["subject"].nunique()) if str(shape) == "cross_sectional" and not frame.empty else None
    )
    constraints = dict(strategy_entry.get("profile_constraints") or {})
    constraints["strategy_profile"] = strategy_profile
    overlay_context = {
        "features_path": str((reproducibility_bundle or {}).get("features_path") or ""),
        "feature_manifest_path": str((reproducibility_bundle or {}).get("feature_manifest_path") or ""),
        "universe_snapshot_path": str(resolved_universe_metadata.get("universe_snapshot_path") or ""),
    }
    if any(str(value).strip() for value in overlay_context.values()):
        constraints["position_multiplier_overlay_context"] = overlay_context
    if str(shape) == "cross_sectional":
        frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
        if not feature_quality_frame.empty and "subject" in feature_quality_frame.columns and not frame.empty:
            executable_subjects = {
                str(subject).strip()
                for subject in list(frame["subject"].dropna().astype(str))
                if str(subject).strip()
            }
            feature_quality_frame = feature_quality_frame.loc[
                feature_quality_frame["subject"].astype(str).isin(executable_subjects)
            ].copy()
    else:
        frame = frame.copy()
    scoped_dataset_research_dataset = scope_research_dataset_to_frame(
        research_dataset=dataset_research_dataset,
        scoped_frame=frame,
    )
    dataset_research_dataset = scoped_dataset_research_dataset
    selected_feature_quality = summarize_feature_quality(
        feature_quality_frame=feature_quality_frame,
        tracked_feature_columns=feature_columns,
    )
    if not dict(selected_feature_quality.get("features") or {}) and feature_quality:
        selected_feature_quality = select_feature_quality(
            feature_quality_summary=feature_quality,
            selected_feature_columns=feature_columns,
        )
    feature_admission = build_feature_admission_section(
        feature_admission_policy=feature_admission_policy,
        available_numeric_columns=available_numeric_columns,
        numeric_feature_columns=numeric_feature_columns,
        excluded_numeric_columns=excluded_numeric_columns,
        selected_feature_columns=feature_columns,
        generated_feature_columns=generated_feature_columns or [],
        selected_feature_quality=selected_feature_quality,
    )
    data_readiness_contract = load_data_readiness_contract()
    default_derivatives_strategy_quality = summarize_strategy_derivatives_quality(
        feature_frame=frame,
        quality_frame=derivatives_quality_frame,
        feature_columns=feature_columns,
        derivatives_feature_quality=derivatives_feature_quality,
    )
    if not pit_universe_artifact_is_valid(resolved_universe_metadata):
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="invalidated_non_point_in_time_universe",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=["non_point_in_time_universe"],
            quality_blockers=["non_point_in_time_universe"],
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
            experiment_status=EXPERIMENT_STATUS_QUARANTINED,
            validation_state="invalidated_non_point_in_time_universe",
        )
    if not reproducibility["passed"]:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="reproducibility_contract_failed",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=["reproducibility_contract_failed"],
            quality_blockers=["reproducibility_contract_failed"],
            data_gap_blockers=[],
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    if not feature_admission["passed"]:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="feature_admission_failed",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=["feature_admission_failed"],
            quality_blockers=["feature_admission_failed"],
            data_gap_blockers=[],
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    feature_columns = list(feature_admission["selected_feature_columns"])
    thesis_profile = _strategy_thesis_profile(strategy_entry)
    feature_registry = build_feature_registry_section(
        strategy_entry=strategy_entry,
        selected_feature_columns=feature_columns,
    )
    if not feature_registry["passed"]:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="required_feature_columns_missing",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=["required_feature_columns_missing"],
            quality_blockers=["required_feature_columns_missing"],
            data_gap_blockers=[],
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            factor_evidence={
                "thesis_id": str(thesis_profile.get("thesis_id") or strategy_entry.get("strategy_id") or ""),
                "missing_required_feature_columns": list(feature_registry["missing_required_feature_columns"]),
                "required_feature_columns": list(feature_registry["required_feature_columns"]),
                "selected_feature_columns": list(feature_registry["selected_feature_columns"]),
                "passed": False,
            },
            universe_metadata=resolved_universe_metadata,
        )
    dataset_research_blockers = validate_research_dataset_requirements(
        research_dataset=scoped_dataset_research_dataset,
    )
    if dataset_research_blockers:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason=dataset_research_blockers[0],
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=dataset_research_blockers,
            quality_blockers=dataset_research_blockers,
            data_gap_blockers=dataset_research_blockers,
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            dataset_research_dataset=scoped_dataset_research_dataset,
            universe_metadata=resolved_universe_metadata,
        )
    research_lane = str(strategy_entry.get("research_lane") or "").strip()
    if str(strategy_entry.get("research_lane") or "").strip() != CONTROL_BASELINE_LANE and not thesis_profile:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="factor_evidence_failed",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=["factor_evidence_failed"],
            quality_blockers=["factor_evidence_failed"],
            data_gap_blockers=[],
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            factor_evidence={
                "thesis_id": str(strategy_entry.get("strategy_id") or ""),
                "rank_ic_mean": 0.0,
                "rank_ic_positive_rate": 0.0,
                "top_minus_bottom_return": 0.0,
                "monotonicity_passed": False,
                "decay_curve": {},
                "turnover": 0.0,
                "max_trade_participation_rate": 0.0,
                "max_inventory_participation_rate": 0.0,
                "regime_split_results": [],
                "missing_required_feature_columns": [],
                "requires_derivatives_features": bool(strategy_entry.get("requires_derivatives_features")),
                "derivatives_feature_columns_present": [],
                "passed": False,
            },
            universe_metadata=resolved_universe_metadata,
        )
    if research_lane in HYPOTHESIS_RESEARCH_LANES:
        if research_lane != HYPOTHESIS_MODEL_LANE and model_family in HYPOTHESIS_MODEL_FAMILIES:
            return _write_quarantined_experiment(
                experiment_root=experiment_root,
                experiment_id=experiment_id,
                as_of=as_of,
                shape=shape,
                model_family=model_family,
                strategy_profile=strategy_profile,
                subject=subject,
                reason="hypothesis_stage_contract_failed",
                compiler_backend=compiler_backend,
                strategy_entry=strategy_entry,
                derivatives_strategy_quality=default_derivatives_strategy_quality,
                validation_blocker_codes=["hypothesis_stage_contract_failed"],
                quality_blockers=["hypothesis_stage_contract_failed"],
                data_gap_blockers=[],
                split_realization_contract=resolved_split_realization_contract,
                feature_columns=feature_columns,
                feature_admission_policy=feature_admission_policy,
                available_numeric_columns=available_numeric_columns,
                numeric_feature_columns=numeric_feature_columns,
                excluded_numeric_columns=excluded_numeric_columns,
                feature_admission=feature_admission,
                reproducibility=reproducibility,
                universe_metadata=resolved_universe_metadata,
            )
        if research_lane == HYPOTHESIS_MODEL_LANE and (
            model_family not in HYPOTHESIS_MODEL_FAMILIES
            or not bool(strategy_entry.get("model_overlay_ready"))
        ):
            return _write_quarantined_experiment(
                experiment_root=experiment_root,
                experiment_id=experiment_id,
                as_of=as_of,
                shape=shape,
                model_family=model_family,
                strategy_profile=strategy_profile,
                subject=subject,
                reason="hypothesis_stage_contract_failed",
                compiler_backend=compiler_backend,
                strategy_entry=strategy_entry,
                derivatives_strategy_quality=default_derivatives_strategy_quality,
                validation_blocker_codes=["hypothesis_stage_contract_failed"],
                quality_blockers=["hypothesis_stage_contract_failed"],
                data_gap_blockers=[],
                split_realization_contract=resolved_split_realization_contract,
                feature_columns=feature_columns,
                feature_admission_policy=feature_admission_policy,
                available_numeric_columns=available_numeric_columns,
                numeric_feature_columns=numeric_feature_columns,
                excluded_numeric_columns=excluded_numeric_columns,
                feature_admission=feature_admission,
                reproducibility=reproducibility,
                universe_metadata=resolved_universe_metadata,
            )
    if bool(strategy_entry.get("requires_derivatives_features")) and not any(
        column in DERIVATIVES_THESIS_FEATURE_COLUMNS for column in feature_columns
    ):
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="factor_evidence_failed",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=["factor_evidence_failed"],
            quality_blockers=["factor_evidence_failed"],
            data_gap_blockers=[],
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            factor_evidence={
                "thesis_id": str(thesis_profile.get("thesis_id") or strategy_entry.get("strategy_id") or ""),
                "rank_ic_mean": 0.0,
                "rank_ic_positive_rate": 0.0,
                "top_minus_bottom_return": 0.0,
                "monotonicity_passed": False,
                "decay_curve": {},
                "turnover": 0.0,
                "max_trade_participation_rate": 0.0,
                "max_inventory_participation_rate": 0.0,
                "regime_split_results": [],
                "missing_required_feature_columns": [],
                "requires_derivatives_features": True,
                "derivatives_feature_columns_present": [
                    column for column in feature_columns if column in DERIVATIVES_THESIS_FEATURE_COLUMNS
                ],
                "passed": False,
            },
            universe_metadata=resolved_universe_metadata,
        )
    initial_data_gap_blockers = _initial_data_gap_blockers(
        shape=shape,
        strategy_entry=strategy_entry,
        frame=frame,
        dataset_data_readiness=dataset_data_readiness,
        contract=data_readiness_contract,
        subject_count_override=cross_sectional_subject_count_before_execution_filter,
    )
    if initial_data_gap_blockers:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason=initial_data_gap_blockers[0],
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=initial_data_gap_blockers,
            quality_blockers=initial_data_gap_blockers,
            data_gap_blockers=initial_data_gap_blockers,
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    if frame.empty or len(frame) < 90:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="insufficient_rows",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=[_insufficient_history_blocker(shape=shape)],
            quality_blockers=[_insufficient_history_blocker(shape=shape)],
            data_gap_blockers=[_insufficient_history_blocker(shape=shape)],
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )

    label_horizon_bars = int(resolved_split_realization_contract["target_horizon_bars"])
    realization_step_bars = int(resolved_split_realization_contract["realization_step_bars"])
    bar_interval_ms = int(resolved_split_realization_contract["bar_interval_ms"])
    label_contract_id = str(label_contract_id or DEFAULT_LABEL_CONTRACT_ID).strip() or DEFAULT_LABEL_CONTRACT_ID
    target_column = str(target_column or "target_up").strip() or "target_up"
    forward_return_column = str(forward_return_column or "target_forward_return").strip() or "target_forward_return"
    split = _chronological_split(
        frame,
        time_col="timestamp_ms",
        split_realization_contract=resolved_split_realization_contract,
    )
    if split is None:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="unable_to_split",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=default_derivatives_strategy_quality,
            validation_blocker_codes=[_insufficient_history_blocker(shape=shape)],
            quality_blockers=[_insufficient_history_blocker(shape=shape)],
            data_gap_blockers=[_insufficient_history_blocker(shape=shape)],
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    train_df, validation_df, test_df = split
    split_row_counts = _split_row_counts(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
    )
    (
        frame,
        derivatives_quality_frame,
        split,
        derivatives_strategy_quality,
    ) = _filter_cross_sectional_subject_panel_for_derivatives_readiness(
        frame=frame,
        derivatives_quality_frame=derivatives_quality_frame,
        feature_columns=feature_columns,
        derivatives_feature_quality=derivatives_feature_quality,
        strategy_entry=strategy_entry,
        split=(train_df, validation_df, test_df),
        split_realization_contract=resolved_split_realization_contract,
        data_readiness_contract=data_readiness_contract,
    )
    if not feature_quality_frame.empty and "subject" in feature_quality_frame.columns and not frame.empty:
        ready_subjects = {
            str(subject).strip()
            for subject in list(frame["subject"].dropna().astype(str))
            if str(subject).strip()
        }
        feature_quality_frame = feature_quality_frame.loc[
            feature_quality_frame["subject"].astype(str).isin(ready_subjects)
        ].copy()
        selected_feature_quality = summarize_feature_quality(
            feature_quality_frame=feature_quality_frame,
            tracked_feature_columns=feature_columns,
        )
        if not dict(selected_feature_quality.get("features") or {}) and feature_quality:
            selected_feature_quality = select_feature_quality(
                feature_quality_summary=feature_quality,
                selected_feature_columns=feature_columns,
            )
        feature_admission = build_feature_admission_section(
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            selected_feature_columns=feature_columns,
            generated_feature_columns=generated_feature_columns or [],
            selected_feature_quality=selected_feature_quality,
        )
    if split is None:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="derivatives_history_gap",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=derivatives_strategy_quality,
            validation_blocker_codes=[DISCOVERY_DERIVATIVES_BLOCKER],
            quality_blockers=[DISCOVERY_DERIVATIVES_BLOCKER],
            data_gap_blockers=[DISCOVERY_DERIVATIVES_BLOCKER],
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    train_df, validation_df, test_df = split
    split_row_counts = _split_row_counts(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
    )
    derivatives_data_gap_blockers = evaluate_derivatives_history_gap(
        strategy_entry=strategy_entry,
        derivatives_strategy_quality=derivatives_strategy_quality,
        contract=data_readiness_contract,
    )
    if derivatives_data_gap_blockers:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason=derivatives_data_gap_blockers[0],
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=derivatives_strategy_quality,
            validation_blocker_codes=derivatives_data_gap_blockers,
            quality_blockers=derivatives_data_gap_blockers,
            data_gap_blockers=derivatives_data_gap_blockers,
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    pre_train_overlap_integrity = evaluate_overlap_integrity(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        evaluation_step_bars=realization_step_bars,
        prediction_count=int(len(test_df)),
        rebalance_count=expected_rebalance_count(
            frame=test_df,
            contract=resolved_split_realization_contract,
        ),
        split_realization_contract=resolved_split_realization_contract,
    )
    pre_train_leakage_checks = evaluate_no_future_leakage(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        label_horizon_bars=label_horizon_bars,
        bar_interval_ms=bar_interval_ms,
        overlap_integrity=pre_train_overlap_integrity,
    )
    pre_train_split_integrity = build_split_integrity_section(
        split_realization_contract=resolved_split_realization_contract,
        overlap_integrity=pre_train_overlap_integrity,
        leakage_checks=pre_train_leakage_checks,
        walk_forward_boundary_contamination_total=0,
    )
    if not pre_train_split_integrity["passed"]:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="split_realization_contract_failed",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=derivatives_strategy_quality,
            validation_blocker_codes=["split_realization_contract_failed"],
            quality_blockers=["split_realization_contract_failed"],
            data_gap_blockers=[],
            split_realization_contract=resolved_split_realization_contract,
            overlap_integrity=pre_train_overlap_integrity,
            leakage_checks=pre_train_leakage_checks,
            split_integrity=pre_train_split_integrity,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    prediction_bundle = _fit_and_score(
        model_family=model_family,
        shape=shape,
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=feature_columns,
        target_column=target_column,
        model_definition=model_definition,
    )
    model_fit_summary = dict(prediction_bundle.get("fit_metadata") or {})
    validation_contract_config = load_validation_contract()
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=strategy_profile,
        contract=validation_contract_config,
    )
    capacity_limits = execution_capacity_limits(validation_contract_config)
    base_execution_cost_model, stress_execution_cost_model = _resolved_execution_cost_models()
    if shape == "single_asset":
        validation_metrics = _backtest_single_asset(
            prediction_bundle["validation"],
            constraints=constraints,
            split_realization_contract=resolved_split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
        test_metrics = _backtest_single_asset(
            prediction_bundle["test"],
            constraints=constraints,
            split_realization_contract=resolved_split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
    else:
        validation_metrics = _backtest_cross_sectional(
            prediction_bundle["validation"],
            constraints=constraints,
            split_realization_contract=resolved_split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
        test_metrics = _backtest_cross_sectional(
            prediction_bundle["test"],
            constraints=constraints,
            split_realization_contract=resolved_split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
    top_long_candidates = _top_long_candidates(prediction_bundle["test"]) if shape == "cross_sectional" else []
    walk_forward = _run_walk_forward(
        frame=frame,
        shape=shape,
        model_family=model_family,
        feature_columns=feature_columns,
        constraints=constraints,
        split_realization_contract=resolved_split_realization_contract,
        target_column=target_column,
        execution_cost_model=base_execution_cost_model,
        stress_execution_cost_model=stress_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        validation_contract=validation_contract_config,
        model_definition=model_definition,
    )
    execution_cost_model_data_gap_blockers = _execution_cost_model_data_gap_blockers(
        validation_metrics,
        test_metrics,
        walk_forward,
    )
    if execution_cost_model_data_gap_blockers:
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason="execution_cost_model_data_gap",
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=derivatives_strategy_quality,
            validation_blocker_codes=["execution_cost_model_data_gap"],
            quality_blockers=["execution_cost_model_data_gap"],
            data_gap_blockers=execution_cost_model_data_gap_blockers,
            split_realization_contract=resolved_split_realization_contract,
            feature_columns=feature_columns,
            feature_admission_policy=feature_admission_policy,
            available_numeric_columns=available_numeric_columns,
            numeric_feature_columns=numeric_feature_columns,
            excluded_numeric_columns=excluded_numeric_columns,
            feature_admission=feature_admission,
            reproducibility=reproducibility,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
            walk_forward=walk_forward,
            execution_cost_model=base_execution_cost_model,
            frictionless_metrics=_frictionless_summary(
                validation_metrics=validation_metrics,
                test_metrics=test_metrics,
                walk_forward=walk_forward,
            ),
            universe_metadata=resolved_universe_metadata,
        )
    if (
        shape == "single_asset"
        and not strategy_requires_derivatives(strategy_entry=strategy_entry)
        and int(walk_forward.get("window_count", 0) or 0) < required_walk_forward_window_count()
    ):
        return _write_quarantined_experiment(
            experiment_root=experiment_root,
            experiment_id=experiment_id,
            as_of=as_of,
            shape=shape,
            model_family=model_family,
            strategy_profile=strategy_profile,
            subject=subject,
            reason=SINGLE_ASSET_SPOT_BLOCKER,
            compiler_backend=compiler_backend,
            strategy_entry=strategy_entry,
            derivatives_strategy_quality=derivatives_strategy_quality,
            validation_blocker_codes=[SINGLE_ASSET_SPOT_BLOCKER],
            quality_blockers=[SINGLE_ASSET_SPOT_BLOCKER],
            data_gap_blockers=[SINGLE_ASSET_SPOT_BLOCKER],
            reproducibility=reproducibility,
            universe_metadata=resolved_universe_metadata,
        )
    overlap_integrity = evaluate_overlap_integrity(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        evaluation_step_bars=int(test_metrics.get("evaluation_step_bars", 1) or 1),
        prediction_count=int(len(prediction_bundle["test"])),
        rebalance_count=int(test_metrics.get("rebalance_count", 0) or 0),
        split_realization_contract=resolved_split_realization_contract,
    )
    leakage_checks = evaluate_no_future_leakage(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        label_horizon_bars=label_horizon_bars,
        bar_interval_ms=bar_interval_ms,
        overlap_integrity=overlap_integrity,
    )
    if shape == "single_asset":
        stress_test_metrics = _backtest_single_asset(
            prediction_bundle["test"],
            constraints=constraints,
            split_realization_contract=resolved_split_realization_contract,
            execution_cost_model=stress_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
    else:
        stress_test_metrics = _backtest_cross_sectional(
            prediction_bundle["test"],
            constraints=constraints,
            split_realization_contract=resolved_split_realization_contract,
            execution_cost_model=stress_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
    walk_forward_boundary_contamination_total = int(walk_forward.get("boundary_contamination_total", 0) or 0)
    split_integrity = build_split_integrity_section(
        split_realization_contract=resolved_split_realization_contract,
        overlap_integrity=overlap_integrity,
        leakage_checks=leakage_checks,
        walk_forward_boundary_contamination_total=walk_forward_boundary_contamination_total,
    )
    walk_forward_assessment = build_walk_forward_assessment(
        walk_forward=walk_forward,
        contract=validation_contract_config,
    )
    execution_stress = build_execution_stress_section(
        strategy_profile=strategy_profile,
        stress_test_metrics=stress_test_metrics,
        walk_forward=walk_forward,
        execution_cost_model=stress_execution_cost_model,
        contract=validation_contract_config,
    )
    frictionless_metrics = _frictionless_summary(
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        walk_forward=walk_forward,
    )
    factor_evidence = _build_factor_evidence_section(
        prediction_frame=prediction_bundle["test"],
        test_metrics=test_metrics,
        thesis_profile=thesis_profile,
        selected_feature_columns=feature_columns,
        strategy_entry=strategy_entry,
        forward_return_column=forward_return_column,
        label_contract_id=label_contract_id,
    )
    regime_holdout = build_regime_holdout_section(
        walk_forward=walk_forward,
        contract=validation_contract_config,
    )
    validation_contract = evaluate_validation_contract(
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        walk_forward=walk_forward,
        split_integrity=split_integrity,
        feature_admission=feature_admission,
        reproducibility=reproducibility,
        factor_evidence=factor_evidence,
        walk_forward_assessment=walk_forward_assessment,
        execution_stress=execution_stress,
        regime_holdout=regime_holdout,
        contract=validation_contract_config,
    )
    status = _experiment_status_from_validation_contract(validation_contract)
    experiment_spec = _apply_universe_metadata_fields(apply_reproducibility_fields({
        "experiment_id": experiment_id,
        "strategy_id": strategy_entry["strategy_id"],
        "spec_hash": strategy_entry["spec_hash"],
        "source": strategy_entry["source"],
        "as_of": as_of,
        "shape": shape,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "subject": subject,
        "universe_filter": strategy_entry.get("universe_filter", {}),
        "feature_groups": strategy_entry.get("feature_groups", []),
        "profile_constraints": strategy_entry.get("profile_constraints", {}),
        "dataset_provenance": DATASET_PROVENANCE,
        "compiler_backend": compiler_backend,
        "feature_admission_policy": feature_admission_policy,
        "available_numeric_columns": available_numeric_columns,
        "numeric_feature_columns": numeric_feature_columns,
        "excluded_numeric_columns": excluded_numeric_columns,
        "feature_columns": feature_columns,
        "label_contract_id": label_contract_id,
        "target_column": target_column,
        "forward_return_column": forward_return_column,
        "execution_cost_model": base_execution_cost_model,
        "model_fit_summary": model_fit_summary,
        "proposal_origin": strategy_entry.get("proposal_origin", "heuristic"),
        "search_action": strategy_entry.get("search_action", "parameter_tune"),
        "registry_snapshot_id": strategy_entry.get("registry_snapshot_id"),
        "family_id": strategy_entry.get("family_id", model_family),
        "feature_family_ids": strategy_entry.get("feature_family_ids", []),
        "published_via": strategy_entry.get("published_via", "not_published"),
        "executable_signal": False,
        "research_lane": strategy_entry.get("research_lane"),
        "promotion_eligibility": strategy_entry.get("promotion_eligibility"),
        "thesis_family": strategy_entry.get("thesis_family"),
        "requires_derivatives_features": strategy_entry.get("requires_derivatives_features"),
        "daily_executable": strategy_entry.get("daily_executable"),
        "thesis_profile": thesis_profile,
        "label_horizon_bars": label_horizon_bars,
        "realization_step_bars": realization_step_bars,
        "partition_gap_bars": int(resolved_split_realization_contract["partition_gap_bars"]),
        "bar_interval_ms": bar_interval_ms,
        "split_realization_contract": resolved_split_realization_contract,
        "split_row_counts": split_row_counts,
        "feature_admission": feature_admission,
        "feature_registry": feature_registry,
        "dataset_research": dict(dataset_research_dataset or {}),
        "split_boundary_contamination_counts": overlap_integrity["split_boundary_contamination_counts"],
        "label_split_overlap": overlap_integrity["label_split_overlap"],
        "backtest_horizon_mismatch": overlap_integrity["backtest_horizon_mismatch"],
    }, reproducibility), universe_metadata=resolved_universe_metadata)
    backtest_report = _apply_universe_metadata_fields(apply_reproducibility_fields({
        "generated_at_utc": utc_now(),
        "experiment_id": experiment_id,
        "execution_cost_model": base_execution_cost_model,
        "model_fit_summary": model_fit_summary,
        "label_contract_id": label_contract_id,
        "target_column": target_column,
        "forward_return_column": forward_return_column,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "split_row_counts": split_row_counts,
        "prediction_counts": {"validation": int(len(prediction_bundle["validation"])), "test": int(len(prediction_bundle["test"]))},
        "top_long_candidates": top_long_candidates,
        "frictionless_metrics": frictionless_metrics,
        "factor_evidence": factor_evidence,
        "feature_registry": feature_registry,
    }, reproducibility), universe_metadata=resolved_universe_metadata)
    validation_report = _apply_universe_metadata_fields(apply_reproducibility_fields({
        "generated_at_utc": utc_now(),
        "experiment_id": experiment_id,
        "execution_cost_model": base_execution_cost_model,
        "model_fit_summary": model_fit_summary,
        "label_contract_id": label_contract_id,
        "target_column": target_column,
        "forward_return_column": forward_return_column,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "split_row_counts": split_row_counts,
        "walk_forward": walk_forward,
        "frictionless_metrics": frictionless_metrics,
        "leakage_checks": leakage_checks,
        "overlap_integrity": overlap_integrity,
        **_overlap_contract_fields(
            split_realization_contract=resolved_split_realization_contract,
            overlap_integrity=overlap_integrity,
        ),
        "validation_contract": validation_contract,
        "split_integrity": split_integrity,
        "feature_admission_policy": feature_admission_policy,
        "feature_admission": feature_admission,
        "feature_registry": feature_registry,
        "dataset_research": dict(dataset_research_dataset or {}),
        "reproducibility": reproducibility,
        "factor_evidence": factor_evidence,
        "walk_forward_assessment": walk_forward_assessment,
        "execution_stress": execution_stress,
        "regime_holdout": regime_holdout,
        "experiment_status": status,
        "dataset_provenance": DATASET_PROVENANCE,
        "derivatives_strategy_quality": derivatives_strategy_quality,
        "data_gap_blockers": [],
        "research_lane": strategy_entry.get("research_lane"),
        "promotion_eligibility": strategy_entry.get("promotion_eligibility"),
        "thesis_family": strategy_entry.get("thesis_family"),
        "requires_derivatives_features": strategy_entry.get("requires_derivatives_features"),
        "daily_executable": strategy_entry.get("daily_executable"),
        "thesis_profile": thesis_profile,
    }, reproducibility), universe_metadata=resolved_universe_metadata)
    alpha_card = _apply_universe_metadata_fields(apply_reproducibility_fields({
        "generated_at_utc": utc_now(),
        "experiment_id": experiment_id,
        "strategy_id": strategy_entry["strategy_id"],
        "spec_hash": strategy_entry["spec_hash"],
        "source": strategy_entry["source"],
        "as_of": as_of,
        "shape": shape,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "subject": subject,
        "liquidity_bucket": candidate.liquidity_bucket if candidate is not None else None,
        "market_symbols": {"spot_symbol": candidate.spot_symbol, "usdm_symbol": candidate.usdm_symbol} if candidate is not None else None,
        "compiler_backend": compiler_backend,
        "label_contract_id": label_contract_id,
        "target_column": target_column,
        "forward_return_column": forward_return_column,
        "backend_mode": _backend_mode_for_compiler_backend(compiler_backend),
        "experiment_status": status,
        "execution_cost_model": base_execution_cost_model,
        "model_fit_summary": model_fit_summary,
        "proposal_origin": strategy_entry.get("proposal_origin", "heuristic"),
        "search_action": strategy_entry.get("search_action", "parameter_tune"),
        "registry_snapshot_id": strategy_entry.get("registry_snapshot_id"),
        "family_id": strategy_entry.get("family_id", model_family),
        "feature_family_ids": strategy_entry.get("feature_family_ids", []),
        "published_via": strategy_entry.get("published_via", "not_published"),
        "executable_signal": False,
        "dataset_provenance": DATASET_PROVENANCE,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "split_row_counts": split_row_counts,
        "walk_forward": walk_forward,
        "frictionless_metrics": frictionless_metrics,
        "leakage_checks": leakage_checks,
        "overlap_integrity": overlap_integrity,
        "split_integrity": split_integrity,
        "feature_admission_policy": feature_admission_policy,
        "feature_admission": feature_admission,
        "feature_registry": feature_registry,
        "dataset_research": dict(dataset_research_dataset or {}),
        "reproducibility": reproducibility,
        "factor_evidence": factor_evidence,
        "walk_forward_assessment": walk_forward_assessment,
        "execution_stress": execution_stress,
        "regime_holdout": regime_holdout,
        **_overlap_contract_fields(
            split_realization_contract=resolved_split_realization_contract,
            overlap_integrity=overlap_integrity,
        ),
        "top_long_candidates": top_long_candidates,
        "lifecycle": strategy_lifecycle(strategy_entry),
        "monitoring_status": strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry)),
        "selection_lane": strategy_entry.get("selection_lane", strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry))),
        "promotion_state": strategy_entry.get("promotion_state", "staged"),
        "research_lane": strategy_entry.get("research_lane"),
        "promotion_eligibility": strategy_entry.get("promotion_eligibility"),
        "thesis_family": strategy_entry.get("thesis_family"),
        "requires_derivatives_features": strategy_entry.get("requires_derivatives_features"),
        "daily_executable": strategy_entry.get("daily_executable"),
        "thesis_profile": thesis_profile,
        "validation_contract": _alpha_card_validation_contract_summary(validation_contract),
        "validation": _initial_validation_state(status=status, compiler_backend=compiler_backend),
        "publication_status": "archived_only",
        "derivatives_strategy_quality": derivatives_strategy_quality,
        "data_gap_blockers": [],
    }, reproducibility), universe_metadata=resolved_universe_metadata)
    fixed_set_comparison = _build_fixed_set_comparison(
        as_of=as_of,
        artifacts_root=artifacts_root,
        experiment_root=experiment_root,
        current_experiment_id=experiment_id,
        current_experiment_spec=experiment_spec,
        current_validation_report=validation_report,
        comparison_base_frame=comparison_base_frame,
        comparison_derivatives_quality_frame=comparison_derivatives_quality_frame,
        derivatives_feature_quality=derivatives_feature_quality,
        validation_contract=validation_contract_config,
        overlay_context=overlay_context,
    )
    validation_report["fixed_set_comparison"] = fixed_set_comparison
    alpha_card["fixed_set_comparison"] = fixed_set_comparison
    statistical_falsification = run_statistical_falsification(
        experiment_spec=experiment_spec,
        strategy_entry=strategy_entry,
        prediction_bundle=prediction_bundle,
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=feature_columns,
        target_column=target_column,
        constraints=constraints,
        split_realization_contract=resolved_split_realization_contract,
        execution_cost_model=base_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        fit_and_score_fn=_fit_and_score,
        backtest_cross_sectional_fn=_backtest_cross_sectional,
    )
    validation_report["statistical_falsification"] = statistical_falsification
    alpha_card["statistical_falsification"] = statistical_falsification
    alpha_experiment_card = build_alpha_experiment_card(
        experiment_id=experiment_id,
        strategy_id=str(strategy_entry.get("strategy_id") or ""),
        fixed_set_comparison=fixed_set_comparison,
        statistical_falsification=statistical_falsification,
        overlay_ablation=alpha_card.get("overlay_ablation"),
    )
    validation_report["alpha_experiment_card"] = alpha_experiment_card
    alpha_card["alpha_experiment_card"] = alpha_experiment_card
    evidence_paths = _finalize_experiment_evidence(
        experiment_root=experiment_root,
        experiment_spec=experiment_spec,
        backtest_report=backtest_report,
        validation_report=validation_report,
        alpha_card=alpha_card,
        compiler_backend=compiler_backend,
    )
    return {
        "experiment_id": experiment_id,
        "shape": shape,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "subject": subject,
        "strategy_id": strategy_entry["strategy_id"],
        "spec_hash": strategy_entry["spec_hash"],
        "source": strategy_entry["source"],
        "monitoring_status": strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry)),
        "selection_lane": strategy_entry.get("selection_lane", strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry))),
        "promotion_state": strategy_entry.get("promotion_state", "staged"),
        "compiler_backend": compiler_backend,
        "backend_mode": _backend_mode_for_compiler_backend(compiler_backend),
        "experiment_status": status,
        "lifecycle": strategy_lifecycle(strategy_entry),
        "validation": alpha_card["validation"],
        "publication_status": alpha_card["publication_status"],
        "proposal_origin": strategy_entry.get("proposal_origin", "heuristic"),
        "search_action": strategy_entry.get("search_action", "parameter_tune"),
        "registry_snapshot_id": strategy_entry.get("registry_snapshot_id"),
        "family_id": strategy_entry.get("family_id", model_family),
        "feature_family_ids": strategy_entry.get("feature_family_ids", []),
        "published_via": alpha_card.get("published_via", "not_published"),
        "executable_signal": False,
        "split_row_counts": split_row_counts,
        "is_trainable": True,
        "experiment_root": str(experiment_root),
        "experiment_spec_path": evidence_paths["experiment_spec_path"],
        "backtest_report": backtest_report,
        "backtest_report_path": evidence_paths["backtest_report_path"],
        "validation_report": validation_report,
        "validation_report_path": evidence_paths["validation_report_path"],
        "alpha_card": alpha_card,
        "alpha_card_path": evidence_paths["alpha_card_path"],
        "alpha_card_md_path": evidence_paths["alpha_card_md_path"],
        "statistical_falsification_report_path": evidence_paths.get("statistical_falsification_report_path", ""),
        "alpha_experiment_card_path": evidence_paths.get("alpha_experiment_card_path", ""),
        "overlap_integrity": overlap_integrity,
        "derivatives_strategy_quality": derivatives_strategy_quality,
        "data_gap_blockers": [],
    }


def _experiment_directory_name(experiment_id: str) -> str:
    normalized = str(experiment_id).strip()
    if len(normalized) <= 64:
        return normalized
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    prefix = normalized[:40].rstrip("-")
    return f"{prefix}-{digest}"


def _write_quarantined_experiment(
    *,
    experiment_root: Path,
    experiment_id: str,
    as_of: str,
    shape: str,
    model_family: str,
    strategy_profile: str,
    subject: str | None,
    reason: str,
    compiler_backend: str,
    strategy_entry: dict[str, Any],
    derivatives_strategy_quality: dict[str, Any],
    validation_blocker_codes: list[str] | None = None,
    quality_blockers: list[str] | None = None,
    data_gap_blockers: list[str] | None = None,
    split_realization_contract: dict[str, Any] | None = None,
    overlap_integrity: dict[str, Any] | None = None,
    leakage_checks: dict[str, Any] | None = None,
    split_integrity: dict[str, Any] | None = None,
    feature_columns: list[str] | None = None,
    feature_admission_policy: dict[str, Any] | None = None,
    available_numeric_columns: list[str] | None = None,
    numeric_feature_columns: list[str] | None = None,
    excluded_numeric_columns: list[str] | None = None,
    feature_admission: dict[str, Any] | None = None,
    reproducibility: dict[str, Any] | None = None,
    factor_evidence: dict[str, Any] | None = None,
    validation_metrics: dict[str, Any] | None = None,
    test_metrics: dict[str, Any] | None = None,
    walk_forward: dict[str, Any] | None = None,
    execution_cost_model: dict[str, Any] | None = None,
    frictionless_metrics: dict[str, Any] | None = None,
    dataset_research_dataset: dict[str, Any] | None = None,
    universe_metadata: dict[str, Any] | None = None,
    experiment_status: str = EXPERIMENT_STATUS_INVALIDATED,
    validation_state: str = "failed",
) -> dict[str, Any]:
    split_row_counts = _split_row_counts()
    blocker_codes = list(validation_blocker_codes or ["validation_contract_incomplete"])
    normalized_quality_blockers = list(quality_blockers or blocker_codes)
    normalized_data_gap_blockers = [
        str(item).strip()
        for item in list(data_gap_blockers or [])
        if str(item).strip()
    ]
    resolved_split_realization_contract = resolve_split_realization_contract(
        contract=split_realization_contract,
        shape=shape,
        interval="4h" if str(shape) == "single_asset" else "1d",
    )
    resolved_overlap_integrity = dict(overlap_integrity or {})
    if not resolved_overlap_integrity:
        resolved_overlap_integrity = {
            "label_horizon_bars": int(resolved_split_realization_contract["target_horizon_bars"]),
            "bar_interval_ms": int(resolved_split_realization_contract["bar_interval_ms"]),
            "purge_gap_bars": int(resolved_split_realization_contract["partition_gap_bars"]),
            "split_boundary_contamination_counts": {
                "train_to_validation": {"contaminated_row_count": 0, "next_partition_start_ms": None, "samples": []},
                "validation_to_test": {"contaminated_row_count": 0, "next_partition_start_ms": None, "samples": []},
            },
            "label_split_overlap": 0,
            "backtest_horizon_mismatch": {
                "detected": False,
                "label_horizon_bars": int(resolved_split_realization_contract["target_horizon_bars"]),
                "realization_step_bars": int(resolved_split_realization_contract["realization_step_bars"]),
                "evaluation_step_bars": int(resolved_split_realization_contract["realization_step_bars"]),
                "prediction_count": 0,
                "rebalance_count": 0,
            },
            "passed": True,
        }
    resolved_leakage_checks = dict(leakage_checks or {"passed": True, "details": [], "blockers": []})
    resolved_split_integrity = dict(split_integrity or {})
    if not resolved_split_integrity:
        resolved_split_integrity = build_split_integrity_section(
            split_realization_contract=resolved_split_realization_contract,
            overlap_integrity=resolved_overlap_integrity,
            leakage_checks=resolved_leakage_checks,
            walk_forward_boundary_contamination_total=0,
        )
    resolved_feature_admission_policy = dict(feature_admission_policy or build_feature_admission_policy())
    resolved_feature_admission = dict(feature_admission or {})
    if not resolved_feature_admission:
        resolved_feature_admission = build_feature_admission_section(
            feature_admission_policy=resolved_feature_admission_policy,
            available_numeric_columns=available_numeric_columns or [],
            numeric_feature_columns=numeric_feature_columns or [],
            excluded_numeric_columns=excluded_numeric_columns or [],
            selected_feature_columns=feature_columns or [],
        )
    resolved_execution_cost_model = dict(execution_cost_model or _resolved_execution_cost_models()[0])
    resolved_reproducibility = dict(reproducibility or {})
    resolved_factor_evidence = dict(factor_evidence or {})
    required_sections_present = []
    if resolved_split_integrity:
        required_sections_present.append("split_integrity")
    if resolved_feature_admission:
        required_sections_present.append("feature_admission")
    if resolved_reproducibility:
        required_sections_present.append("reproducibility")
    if resolved_factor_evidence:
        required_sections_present.append("factor_evidence")
    validation_contract = _placeholder_validation_contract(
        status="incomplete",
        blocker_codes=blocker_codes,
        required_sections_present=required_sections_present,
    )
    payload = _apply_universe_metadata_fields(apply_reproducibility_fields({
        "generated_at_utc": utc_now(),
        "experiment_id": experiment_id,
        "strategy_id": strategy_entry["strategy_id"],
        "spec_hash": strategy_entry["spec_hash"],
        "source": strategy_entry["source"],
        "as_of": as_of,
        "shape": shape,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "subject": subject,
        "experiment_status": experiment_status,
        "dataset_provenance": DATASET_PROVENANCE,
        "lifecycle": strategy_lifecycle(strategy_entry),
        "monitoring_status": strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry)),
        "selection_lane": strategy_entry.get("selection_lane", strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry))),
        "promotion_state": strategy_entry.get("promotion_state", "staged"),
        "feature_admission_policy": resolved_feature_admission_policy,
        "available_numeric_columns": list(available_numeric_columns or []),
        "numeric_feature_columns": list(numeric_feature_columns or []),
        "excluded_numeric_columns": list(excluded_numeric_columns or []),
        "feature_columns": list(feature_columns or []),
        "execution_cost_model": resolved_execution_cost_model,
        "reason": reason,
        "compiler_backend": compiler_backend,
        "backend_mode": _backend_mode_for_compiler_backend(compiler_backend),
        "validation_metrics": dict(validation_metrics or {}),
        "test_metrics": dict(test_metrics or {}),
        "split_row_counts": split_row_counts,
        "walk_forward": dict(walk_forward or {"window_count": 0, "windows": [], "median_oos_sharpe": 0.0}),
        "frictionless_metrics": dict(frictionless_metrics or {}),
        "overlap_integrity": resolved_overlap_integrity,
        **_overlap_contract_fields(
            split_realization_contract=resolved_split_realization_contract,
            overlap_integrity=resolved_overlap_integrity,
        ),
        "validation": validation_state,
        "publication_status": "archived_only",
        "validation_contract": validation_contract,
        "split_integrity": resolved_split_integrity,
        "feature_admission": resolved_feature_admission,
        "dataset_research": dict(dataset_research_dataset or {}),
        "reproducibility": resolved_reproducibility,
        "factor_evidence": resolved_factor_evidence,
        "leakage_checks": resolved_leakage_checks,
        "walk_forward_assessment": {},
        "execution_stress": {},
        "regime_holdout": {},
        "data_gap_blockers": normalized_data_gap_blockers,
        "quality_summary": {
            "quality_gate_passed": False,
            "quality_blockers": normalized_quality_blockers,
            "metrics_snapshot": {
                "reason": reason,
                "validation_contract": validation_contract,
            },
        },
        "derivatives_strategy_quality": derivatives_strategy_quality,
        "research_lane": strategy_entry.get("research_lane"),
        "promotion_eligibility": strategy_entry.get("promotion_eligibility"),
        "thesis_family": strategy_entry.get("thesis_family"),
        "requires_derivatives_features": strategy_entry.get("requires_derivatives_features"),
        "daily_executable": strategy_entry.get("daily_executable"),
        "thesis_profile": strategy_entry.get("thesis_profile"),
    }, resolved_reproducibility), universe_metadata=universe_metadata)
    evidence_paths = _finalize_experiment_evidence(
        experiment_root=experiment_root,
        experiment_spec=payload,
        backtest_report=payload,
        validation_report=payload,
        alpha_card=payload,
        compiler_backend=compiler_backend,
    )
    return {
        "experiment_id": experiment_id,
        "shape": shape,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "subject": subject,
        "strategy_id": strategy_entry["strategy_id"],
        "spec_hash": strategy_entry["spec_hash"],
        "source": strategy_entry["source"],
        "monitoring_status": strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry)),
        "selection_lane": strategy_entry.get("selection_lane", strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry))),
        "promotion_state": strategy_entry.get("promotion_state", "staged"),
        "compiler_backend": compiler_backend,
        "backend_mode": _backend_mode_for_compiler_backend(compiler_backend),
        "experiment_status": experiment_status,
        "lifecycle": strategy_lifecycle(strategy_entry),
        "validation": validation_state,
        "publication_status": "archived_only",
        "split_row_counts": split_row_counts,
        "is_trainable": False,
        "experiment_root": str(experiment_root),
        "experiment_spec_path": evidence_paths["experiment_spec_path"],
        "backtest_report": payload,
        "backtest_report_path": evidence_paths["backtest_report_path"],
        "validation_report": payload,
        "validation_report_path": evidence_paths["validation_report_path"],
        "alpha_card": payload,
        "alpha_card_path": evidence_paths["alpha_card_path"],
        "alpha_card_md_path": evidence_paths["alpha_card_md_path"],
        "statistical_falsification_report_path": evidence_paths.get("statistical_falsification_report_path", ""),
        "alpha_experiment_card_path": evidence_paths.get("alpha_experiment_card_path", ""),
        "overlap_integrity": payload["overlap_integrity"],
        "derivatives_strategy_quality": derivatives_strategy_quality,
        "data_gap_blockers": normalized_data_gap_blockers,
    }


def _write_rerun_required_experiment(
    *,
    experiment_root: Path,
    experiment_id: str,
    as_of: str,
    shape: str,
    model_family: str,
    strategy_profile: str,
    subject: str | None,
    compiler_backend: str,
    strategy_entry: dict[str, Any],
    validation_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    walk_forward: dict[str, Any],
    leakage_checks: dict[str, Any],
    overlap_integrity: dict[str, Any],
    candidate: QuantUniverseCandidate | None,
    top_long_candidates: list[dict[str, Any]],
    split_row_counts: dict[str, int],
    derivatives_strategy_quality: dict[str, Any],
    universe_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_state = "insufficient_track_record"
    validation_contract = _placeholder_validation_contract(
        status="incomplete",
        blocker_codes=["overlap_fix_pending_rerun"],
        required_sections_present=["split_integrity"],
    )
    payload = _apply_universe_metadata_fields({
        "generated_at_utc": utc_now(),
        "experiment_id": experiment_id,
        "strategy_id": strategy_entry["strategy_id"],
        "spec_hash": strategy_entry["spec_hash"],
        "source": strategy_entry["source"],
        "as_of": as_of,
        "shape": shape,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "subject": subject,
        "liquidity_bucket": candidate.liquidity_bucket if candidate is not None else None,
        "market_symbols": {"spot_symbol": candidate.spot_symbol, "usdm_symbol": candidate.usdm_symbol} if candidate is not None else None,
        "experiment_status": EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
        "dataset_provenance": DATASET_PROVENANCE,
        "lifecycle": strategy_lifecycle(strategy_entry),
        "monitoring_status": strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry)),
        "selection_lane": strategy_entry.get("selection_lane", strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry))),
        "promotion_state": strategy_entry.get("promotion_state", "staged"),
        "compiler_backend": compiler_backend,
        "backend_mode": _backend_mode_for_compiler_backend(compiler_backend),
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "split_row_counts": split_row_counts,
        "walk_forward": walk_forward,
        "leakage_checks": leakage_checks,
        "overlap_integrity": overlap_integrity,
        **_overlap_contract_fields(
            label_horizon_bars=overlap_integrity.get("label_horizon_bars"),
            bar_interval_ms=overlap_integrity.get("bar_interval_ms"),
            overlap_integrity=overlap_integrity,
        ),
        "validation_contract": validation_contract,
        "split_integrity": build_split_integrity_section(
            label_horizon_bars=overlap_integrity.get("label_horizon_bars"),
            bar_interval_ms=overlap_integrity.get("bar_interval_ms"),
            overlap_integrity=overlap_integrity,
            leakage_checks=leakage_checks,
        ),
        "walk_forward_assessment": {},
        "execution_stress": {},
        "regime_holdout": {},
        "top_long_candidates": top_long_candidates,
        "validation": validation_state,
        "publication_status": "archived_only",
        "reason": "overlap_integrity_failed",
        "data_gap_blockers": [],
        "quality_summary": {
            "quality_gate_passed": False,
            "quality_blockers": ["overlap_fix_pending_rerun"],
            "metrics_snapshot": {
                "validation_contract": validation_contract,
            },
        },
        "derivatives_strategy_quality": derivatives_strategy_quality,
    }, universe_metadata=universe_metadata)
    evidence_paths = _finalize_experiment_evidence(
        experiment_root=experiment_root,
        experiment_spec=payload,
        backtest_report=payload,
        validation_report=payload,
        alpha_card=payload,
        compiler_backend=compiler_backend,
    )
    return {
        "experiment_id": experiment_id,
        "shape": shape,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "subject": subject,
        "strategy_id": strategy_entry["strategy_id"],
        "spec_hash": strategy_entry["spec_hash"],
        "source": strategy_entry["source"],
        "monitoring_status": strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry)),
        "selection_lane": strategy_entry.get("selection_lane", strategy_entry.get("monitoring_status", strategy_lifecycle(strategy_entry))),
        "promotion_state": strategy_entry.get("promotion_state", "staged"),
        "compiler_backend": compiler_backend,
        "backend_mode": _backend_mode_for_compiler_backend(compiler_backend),
        "experiment_status": EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
        "lifecycle": strategy_lifecycle(strategy_entry),
        "validation": validation_state,
        "publication_status": "archived_only",
        "split_row_counts": split_row_counts,
        "is_trainable": True,
        "experiment_root": str(experiment_root),
        "experiment_spec_path": evidence_paths["experiment_spec_path"],
        "backtest_report": payload,
        "backtest_report_path": evidence_paths["backtest_report_path"],
        "validation_report": payload,
        "validation_report_path": evidence_paths["validation_report_path"],
        "alpha_card": payload,
        "alpha_card_path": evidence_paths["alpha_card_path"],
        "alpha_card_md_path": evidence_paths["alpha_card_md_path"],
        "overlap_integrity": overlap_integrity,
        "derivatives_strategy_quality": derivatives_strategy_quality,
        "data_gap_blockers": [],
    }


def _timestamp_cross_section_zscore(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    grouped = pd.DataFrame({"value": values.values, "timestamp_ms": timestamps.values}, index=values.index)
    group_mean = grouped.groupby("timestamp_ms")["value"].transform("mean")
    group_std = grouped.groupby("timestamp_ms")["value"].transform("std").replace(0.0, np.nan)
    return ((grouped["value"] - group_mean) / group_std).fillna(0.0).astype("float64")


def _timestamp_cross_section_percentile_rank(values: pd.Series, timestamps: pd.Series) -> pd.Series:
    grouped = pd.DataFrame({"value": values.values, "timestamp_ms": timestamps.values}, index=values.index)
    return grouped.groupby("timestamp_ms")["value"].rank(pct=True).fillna(0.5).astype("float64")


def _normalized_factor_weight_map(
    factor_weights: Iterable[tuple[str, float]],
) -> dict[str, float]:
    normalized = [(str(column), float(weight)) for column, weight in factor_weights]
    abs_sum = sum(abs(weight) for _, weight in normalized)
    if abs_sum <= 1e-12:
        equal_weight = 1.0 / max(len(normalized), 1)
        return {column: equal_weight for column, _ in normalized}
    return {column: float(weight / abs_sum) for column, weight in normalized}


def _alpha_ontology_linear_score_from_weights(
    frame: pd.DataFrame,
    *,
    factor_weights: dict[str, float],
) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    timestamps = frame["timestamp_ms"]
    raw_score = pd.Series(0.0, index=frame.index, dtype="float64")
    for column, weight in factor_weights.items():
        if column not in frame.columns:
            continue
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            continue
        raw_score = raw_score + float(weight) * _timestamp_cross_section_zscore(series, timestamps)
    centered_rank = _timestamp_cross_section_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def _fit_alpha_ontology_v5_h10d_rw_bridge_weights(
    train: pd.DataFrame,
) -> tuple[dict[str, float], dict[str, Any]]:
    static_weights = _normalized_factor_weight_map(ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS)
    factor_diagnostics: dict[str, Any] = {
        column: {
            "daily_ic_obs": 0,
            "mean_ic": 0.0,
            "ic_std": 0.0,
            "ir": 0.0,
        }
        for column in static_weights
    }
    summary: dict[str, Any] = {
        "mode": "fallback_static_v5",
        "forward_return_column": EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
        "train_row_count": int(len(train)),
        "train_timestamp_count": (
            int(pd.Series(train["timestamp_ms"]).nunique())
            if "timestamp_ms" in train.columns
            else 0
        ),
        "minimum_daily_ic_obs": 30,
        "weights": dict(static_weights),
        "factor_diagnostics": factor_diagnostics,
    }
    if (
        train.empty
        or "timestamp_ms" not in train.columns
        or EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN not in train.columns
    ):
        for column, weight in static_weights.items():
            factor_diagnostics[column]["weight"] = float(weight)
        return static_weights, summary

    forward_returns = pd.to_numeric(
        train[EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN],
        errors="coerce",
    ).astype("float64")
    resolved_weights: dict[str, float] = {}
    abs_ir_sum = 0.0

    for column, static_weight in static_weights.items():
        if column not in train.columns:
            factor_diagnostics[column]["weight"] = float(static_weight)
            continue
        series = pd.to_numeric(train[column], errors="coerce").astype("float64")
        if not series.notna().any():
            factor_diagnostics[column]["weight"] = float(static_weight)
            continue
        zscore = _timestamp_cross_section_zscore(series, train["timestamp_ms"])
        ic_values: list[float] = []
        for _, group in train.groupby("timestamp_ms", sort=True):
            scores = zscore.loc[group.index]
            returns = forward_returns.loc[group.index]
            valid = scores.notna() & returns.notna()
            if int(valid.sum()) < 3:
                continue
            rho = _safe_spearman_rank_corr(scores.loc[valid], returns.loc[valid])
            if rho is not None:
                ic_values.append(float(rho))
        ic_series = pd.Series(ic_values, dtype="float64")
        mean_ic = float(ic_series.mean()) if not ic_series.empty else 0.0
        ic_std = float(ic_series.std(ddof=0)) if len(ic_series) > 1 else 0.0
        ir = 0.0
        if len(ic_series) >= int(summary["minimum_daily_ic_obs"]) and ic_std > 1e-12:
            ir = float(mean_ic / ic_std)
        factor_diagnostics[column] = {
            "daily_ic_obs": int(len(ic_series)),
            "mean_ic": mean_ic,
            "ic_std": ic_std,
            "ir": ir,
        }
        abs_ir_sum += abs(ir)

    if abs_ir_sum <= 1e-12:
        for column, weight in static_weights.items():
            factor_diagnostics[column]["weight"] = float(weight)
        return static_weights, summary

    for column, static_weight in static_weights.items():
        mean_ic = float(factor_diagnostics[column]["mean_ic"])
        ir = float(factor_diagnostics[column]["ir"])
        if mean_ic > 0.0:
            sign = 1.0
        elif mean_ic < 0.0:
            sign = -1.0
        else:
            sign = 1.0 if static_weight >= 0.0 else -1.0
        resolved_weights[column] = float(sign * abs(ir) / abs_ir_sum)
        factor_diagnostics[column]["weight"] = float(resolved_weights[column])

    summary["mode"] = "train_ir_absnorm_bridge"
    summary["weights"] = dict(resolved_weights)
    return resolved_weights, summary


def _score_alpha_ontology_v5_h10d_rw_bridge_bundle(
    *,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> dict[str, Any]:
    weights, fit_metadata = _fit_alpha_ontology_v5_h10d_rw_bridge_weights(train)
    train["score"] = _alpha_ontology_linear_score_from_weights(train, factor_weights=weights)
    validation["score"] = _alpha_ontology_linear_score_from_weights(validation, factor_weights=weights)
    test["score"] = _alpha_ontology_linear_score_from_weights(test, factor_weights=weights)
    return {
        "train": train,
        "validation": validation,
        "test": test,
        "fit_metadata": fit_metadata,
    }


def _score_alpha_ontology_v5_h10d_rw_bridge_spk_replace_mid_v1_bundle(
    *,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> dict[str, Any]:
    weights, fit_metadata = _fit_alpha_ontology_v5_h10d_rw_bridge_weights(train)

    def _score_with_spk_replacement(frame: pd.DataFrame) -> pd.Series:
        base_score = _alpha_ontology_linear_score_from_weights(frame, factor_weights=weights)
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            frame,
            base_raw_score_fn=lambda _: base_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
        )

    train["score"] = _score_with_spk_replacement(train)
    validation["score"] = _score_with_spk_replacement(validation)
    test["score"] = _score_with_spk_replacement(test)
    fit_metadata = dict(fit_metadata)
    fit_metadata["spk_boundary_rule"] = {
        "parent_model_family": "xs_alpha_ontology_v5_h10d_rw_bridge",
        "signal_column": "post_pump_stall_core_score_3d",
        "replacement_pool_size": 6,
        "signal_threshold": 0.0,
        "max_replacements_per_timestamp": 1,
        "eligible_liquidity_buckets": ["mid_liquidity"],
    }
    return {
        "train": train,
        "validation": validation,
        "test": test,
        "fit_metadata": fit_metadata,
    }


def _score_alpha_ontology_v5_h10d_rw_bridge_mf01_combo_replace_v1_bundle(
    *,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> dict[str, Any]:
    weights, fit_metadata = _fit_alpha_ontology_v5_h10d_rw_bridge_weights(train)

    def _score_with_mf01_replacement(frame: pd.DataFrame) -> pd.Series:
        base_score = _alpha_ontology_linear_score_from_weights(frame, factor_weights=weights)
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            frame,
            base_raw_score_fn=lambda _: base_score,
            signal_column="mf01_short_boundary_combo_score",
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            eligible_liquidity_buckets=None,
            protect_selected_when_signal_leq=False,
        )

    train["score"] = _score_with_mf01_replacement(train)
    validation["score"] = _score_with_mf01_replacement(validation)
    test["score"] = _score_with_mf01_replacement(test)
    fit_metadata = dict(fit_metadata)
    fit_metadata["parent_model_family"] = "xs_alpha_ontology_v5_h10d_rw_bridge"
    fit_metadata["mf01_boundary_rule"] = {
        "parent_model_family": "xs_alpha_ontology_v5_h10d_rw_bridge",
        "signal_column": "mf01_short_boundary_combo_score",
        "replacement_pool_size": 6,
        "signal_threshold": 0.0,
        "max_replacements_per_timestamp": 1,
        "eligible_liquidity_buckets": "all",
        "landing_mode": "short_boundary_replacement",
        "long_leg_unchanged": True,
    }
    return {
        "train": train,
        "validation": validation,
        "test": test,
        "fit_metadata": fit_metadata,
    }


def _score_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0_bundle(
    *,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> dict[str, Any]:
    weights, fit_metadata = _fit_alpha_ontology_v5_h10d_rw_bridge_weights(train)

    def _score_with_event_state_replacement(frame: pd.DataFrame) -> pd.Series:
        base_score = _alpha_ontology_linear_score_from_weights(frame, factor_weights=weights)
        return _xs_alpha_ontology_v5_h10d_strict_event_state_short_boundary_score(
            frame,
            base_raw_score_fn=lambda _: base_score,
        )

    train["score"] = _score_with_event_state_replacement(train)
    validation["score"] = _score_with_event_state_replacement(validation)
    test["score"] = _score_with_event_state_replacement(test)
    fit_metadata = dict(fit_metadata)
    fit_metadata["parent_model_family"] = "xs_alpha_ontology_v5_h10d_rw_bridge"
    fit_metadata["m3_3_event_state_rule"] = {
        "parent_model_family": "xs_alpha_ontology_v5_h10d_rw_bridge",
        "signal_column": "m3_3_event_state_short_quality_v1",
        "min_quality": 1.0,
        "max_noise_ratio": 0.0,
        "require_no_hype": True,
        "replacement_pool_size": 8,
        "landing_mode": "short_boundary_replacement",
        "long_leg_unchanged": True,
    }
    return {
        "train": train,
        "validation": validation,
        "test": test,
        "fit_metadata": fit_metadata,
    }


def _fit_and_score(
    *,
    model_family: str,
    shape: str,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str = "target_up",
    model_definition: dict[str, Any] | None = None,
) -> dict[str, pd.DataFrame]:
    train = train_df.copy()
    validation = validation_df.copy()
    test = test_df.copy()
    resolved_target_column = str(target_column or "target_up").strip() or "target_up"
    if model_definition:
        engine_template = str(model_definition.get("engine_template") or "").strip()
        hyperparameters = dict(model_definition.get("hyperparameters") or {})
        if engine_template == "deterministic_rule_stack":
            base_rule_family = str(hyperparameters.get("base_rule_family") or model_family or "trend_following")
            return _score_deterministic_family(
                base_rule_family=base_rule_family,
                shape=shape,
                train=train,
                validation=validation,
                test=test,
                feature_columns=feature_columns,
            )
        if engine_template == "meta_label_wrapper":
            base_rule_family = str(hyperparameters.get("base_rule_family") or ("breakout_continuation" if shape == "single_asset" else "ranking_scorer"))
            return _score_meta_label_wrapper(
                base_rule_family=base_rule_family,
                shape=shape,
                train=train,
                validation=validation,
                test=test,
                feature_columns=feature_columns,
                target_column=resolved_target_column,
            )
    if model_family == "xs_alpha_ontology_v5_h10d_rw_bridge":
        return _score_alpha_ontology_v5_h10d_rw_bridge_bundle(
            train=train,
            validation=validation,
            test=test,
        )
    if model_family == "xs_alpha_ontology_v5_h10d_rw_bridge_spk_short_replace_mid_v1":
        return _score_alpha_ontology_v5_h10d_rw_bridge_spk_replace_mid_v1_bundle(
            train=train,
            validation=validation,
            test=test,
        )
    if model_family == "xs_alpha_ontology_v5_h10d_rw_bridge_mf01_combo_replace_v1":
        return _score_alpha_ontology_v5_h10d_rw_bridge_mf01_combo_replace_v1_bundle(
            train=train,
            validation=validation,
            test=test,
        )
    if model_family == "xs_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0":
        return _score_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0_bundle(
            train=train,
            validation=validation,
            test=test,
        )
    def _score_bundle(scorer: Callable[..., pd.Series]) -> None:
        train["score"] = scorer(train, feature_columns=feature_columns)
        validation["score"] = scorer(validation, feature_columns=feature_columns)
        test["score"] = scorer(test, feature_columns=feature_columns)
    if model_family == "trend_following":
        _score_bundle(trend_following_score)
    elif model_family == "mean_reversion":
        _score_bundle(mean_reversion_score)
    elif model_family == "breakout_continuation":
        _score_bundle(breakout_continuation_score)
    elif model_family == "breakout_volatility_expansion":
        _score_bundle(breakout_volatility_expansion_score)
    elif model_family == "relative_strength_cross_section":
        _score_bundle(relative_strength_score)
    elif model_family == "ranking_scorer":
        _score_bundle(ranking_score)
    elif model_family == "xs_relative_strength":
        _score_bundle(xs_relative_strength_score)
    elif model_family == "xs_quality_strength":
        _score_bundle(xs_quality_strength_score)
    elif model_family == "xs_quality_strength_v3":
        _score_bundle(xs_quality_strength_v3_score)
    elif model_family == "xs_momentum_acceleration":
        _score_bundle(xs_momentum_acceleration_score)
    elif model_family == "xs_pullback_resume":
        _score_bundle(xs_pullback_resume_score)
    elif model_family == "xs_breakout_confirmation":
        _score_bundle(xs_breakout_confirmation_score)
    elif model_family == "xs_squeeze_release":
        _score_bundle(xs_squeeze_release_score)
    elif model_family == "xs_breakout_failure_reversal":
        _score_bundle(xs_breakout_failure_reversal_score)
    elif model_family == "xs_participation_drift":
        _score_bundle(xs_participation_drift_score)
    elif model_family == "xs_participation_drift_v3":
        _score_bundle(xs_participation_drift_v3_score)
    elif model_family == "xs_participation_drift_v4":
        _score_bundle(xs_participation_drift_v4_score)
    elif model_family == "xs_participation_drift_v5":
        _score_bundle(xs_participation_drift_v5_score)
    elif model_family == "xs_strength_on_reset_v1":
        _score_bundle(xs_strength_on_reset_v1_score)
    elif model_family == "xs_strength_on_reset_v2":
        _score_bundle(xs_strength_on_reset_v2_score)
    elif model_family == "xs_strength_on_reset_v3":
        _score_bundle(xs_strength_on_reset_v3_score)
    elif model_family == "xs_strength_on_reset_v4":
        _score_bundle(xs_strength_on_reset_v4_score)
    elif model_family == "xs_strength_on_reset_v5":
        _score_bundle(xs_strength_on_reset_v5_score)
    elif model_family == "xs_quality_pullback_v1":
        _score_bundle(xs_quality_pullback_v1_score)
    elif model_family == "xs_quality_pullback_v2":
        _score_bundle(xs_quality_pullback_v2_score)
    elif model_family == "xs_contraction_release_v1":
        _score_bundle(xs_contraction_release_v1_score)
    elif model_family == "xs_contraction_release_v2":
        _score_bundle(xs_contraction_release_v2_score)
    elif model_family == "xs_contraction_release_v3":
        _score_bundle(xs_contraction_release_v3_score)
    elif model_family == "xs_contraction_release_v4":
        _score_bundle(xs_contraction_release_v4_score)
    elif model_family == "xs_contraction_release_v5":
        _score_bundle(xs_contraction_release_v5_score)
    elif model_family == "xs_absorption_recovery_v1":
        _score_bundle(xs_absorption_recovery_v1_score)
    elif model_family == "xs_failed_breakdown_reclaim_v1":
        _score_bundle(xs_failed_breakdown_reclaim_v1_score)
    elif model_family == "xs_regime_switch_ranking_v1":
        _score_bundle(xs_regime_switch_ranking_v1_score)
    elif model_family == "xs_basis_funding_dislocation_v1":
        _score_bundle(xs_basis_funding_dislocation_v1_score)
    elif model_family == "xs_relative_value_spread_v1":
        _score_bundle(xs_relative_value_spread_v1_score)
    elif model_family == "xs_relative_value_spread_v2":
        _score_bundle(xs_relative_value_spread_v2_score)
    elif model_family == "xs_relative_value_spread_v3":
        _score_bundle(xs_relative_value_spread_v3_score)
    elif model_family == "xs_relative_value_spread_v4":
        _score_bundle(xs_relative_value_spread_v4_score)
    elif model_family == "xs_relative_value_spread_v5":
        _score_bundle(xs_relative_value_spread_v5_score)
    elif model_family == "xs_relative_value_spread_v6":
        _score_bundle(xs_relative_value_spread_v6_score)
    elif model_family == "xs_relative_value_spread_v7":
        _score_bundle(xs_relative_value_spread_v7_score)
    elif model_family == "xs_relative_value_spread_v8":
        _score_bundle(xs_relative_value_spread_v8_score)
    elif model_family == "xs_relative_value_spread_v9":
        _score_bundle(xs_relative_value_spread_v9_score)
    elif model_family == "xs_reversal_quality_v1":
        _score_bundle(xs_reversal_quality_v1_score)
    elif model_family == "xs_carry_dislocation_v1":
        _score_bundle(xs_carry_dislocation_v1_score)
    elif model_family == "xs_vol_regime_blend_v1":
        _score_bundle(xs_vol_regime_blend_v1_score)
    elif model_family == "xs_dispersion_regime_blend_v1":
        _score_bundle(xs_dispersion_regime_blend_v1_score)
    elif model_family == "xs_dual_regime_filter_v1":
        _score_bundle(xs_dual_regime_filter_v1_score)
    elif model_family == "xs_quad_regime_filter_v1":
        _score_bundle(xs_quad_regime_filter_v1_score)
    elif model_family == "xs_dual_regime_filter_v2":
        _score_bundle(xs_dual_regime_filter_v2_score)
    elif model_family == "xs_dual_regime_filter_v3":
        _score_bundle(xs_dual_regime_filter_v3_score)
    elif model_family == "xs_dual_regime_filter_v4":
        _score_bundle(xs_dual_regime_filter_v4_score)
    elif model_family == "xs_tier2_dual_regime_v1":
        _score_bundle(xs_dual_regime_filter_v3_score)
    elif model_family == "xs_dual_regime_filter_v5":
        _score_bundle(xs_dual_regime_filter_v5_score)
    elif model_family == "xs_dual_regime_filter_v6":
        _score_bundle(xs_dual_regime_filter_v6_score)
    elif model_family == "xs_dual_regime_filter_v7":
        _score_bundle(xs_dual_regime_filter_v7_score)
    elif model_family == "xs_dual_regime_filter_v8":
        _score_bundle(xs_dual_regime_filter_v8_score)
    elif model_family == "xs_dual_regime_filter_v9":
        _score_bundle(xs_dual_regime_filter_v9_score)
    elif model_family == "xs_dual_regime_filter_v11":
        _score_bundle(xs_dual_regime_filter_v11_score)
    elif model_family == "xs_minimal_v1":
        _score_bundle(xs_minimal_v1_score)
    elif model_family == "xs_minimal_v2":
        _score_bundle(xs_minimal_v2_score)
    elif model_family == "xs_minimal_v3":
        _score_bundle(xs_minimal_v3_score)
    elif model_family == "xs_minimal_v4":
        _score_bundle(xs_minimal_v4_score)
    elif model_family == "xs_minimal_v5":
        _score_bundle(xs_minimal_v5_score)
    elif model_family == "xs_minimal_v6":
        _score_bundle(xs_minimal_v6_score)
    elif model_family == "xs_minimal_v8":
        # v93: identical to v6 score; portfolio-level multiplier overlay applied in
        # execution_backtest._cross_sectional_period via constraints.position_multiplier_overlay_id
        _score_bundle(xs_minimal_v6_score)
    elif model_family == "xs_minimal_v9":
        # v94: recovers iv_smooth_20 + dh_20 dropped by v91 VIF threshold; multiplier overlay still active
        _score_bundle(xs_minimal_v9_score)
    elif model_family == "xs_minimal_v10":
        # v95: Phase 1d-informed lean rebuild (7 WF-stable factors + rescued stress_liq_conc_iv); multiplier overlay still active
        _score_bundle(xs_minimal_v10_score)
    elif model_family == "xs_minimal_v11":
        # v96-A: only-drop isolation experiment (v94 minus 4 weak, keep v94 weights, no rescue)
        _score_bundle(xs_minimal_v11_score)
    elif model_family == "xs_minimal_v12":
        # v96-B: only-add isolation experiment (v94 + stress_liq_conc_iv at -0.11, keep all v94 weights)
        _score_bundle(xs_minimal_v12_score)
    elif model_family == "xs_minimal_v13":
        # v99 (Phase 1d): dynamic weights via rolling-IR softmax schedule (offline-generated)
        _score_bundle(xs_minimal_v13_score)
    elif model_family == "xs_alpha_ontology_v1":
        # Alpha Ontology W1.4: v91 9-factor IC-pruned baseline plus 2 strict-G6+G3 W1.1
        # winners (F33 downside_upside_vol_ratio_30 + F12 funding_basis_residual_implied_repo_30).
        # Selection lineage: artifacts/quant_research/factor_reports/2026-04-29/.
        _score_bundle(xs_alpha_ontology_v1_score)
    elif model_family == "xs_alpha_ontology_v2":
        # Alpha Ontology v_alpha_v2: v_alpha_v1 11 + F29 contagion_in_degree
        # (MF-09 co-jump network, W3.2 strict-admissible). 12 score factors.
        _score_bundle(xs_alpha_ontology_v2_score)
    elif model_family == "xs_alpha_ontology_v3":
        # Alpha Ontology W3.6 v3: identical 11 lsk3 factors but weights are
        # Bayesian-IR-shrunk on the first 60% of the panel (config/quant_research/
        # alpha_ontology_v3_weights.json) instead of hand-tuned.
        _score_bundle(xs_alpha_ontology_v3_score)
    elif model_family == "xs_alpha_ontology_v4":
        # Alpha Ontology M2.2 v4: lsk3 11 hand-tuned + F08 funding_term_skew_60
        # (rolling 60d skew of daily funding_rate per subject). G6 PASS vs lsk3
        # baseline (residual IC +0.030, t=+5.61 on 2026-04-29 panel).
        _score_bundle(xs_alpha_ontology_v4_score)
    elif model_family == "xs_alpha_ontology_v5":
        # Alpha Ontology M2.3 v5: lsk3 11 + F62 settlement_cycle_premium_60d
        # (per-subject pre-settlement-hour drift in 1h perp returns, 60d rolling).
        # G6 PASS vs lsk3 (residual IC -0.044, t=-7.21 on 2026-04-29 panel).
        _score_bundle(xs_alpha_ontology_v5_score)
    elif model_family == "xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1":
        _score_bundle(xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score)
    elif model_family == "xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d":
        _score_bundle(xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d_score)
    elif model_family == "xs_alpha_ontology_v6":
        # Alpha Ontology SP-A v6: lsk3 11 + liq_cascade_recency_score_5d
        # (per-subject 1h liquidation cascade, 5d exponential-decay recency).
        # Doc §E.12 falsification PASS (t=+10.75); G6 PASS vs lsk3 (residual
        # IC +0.062, t=+10.77 on 2026-04-29 panel).
        _score_bundle(xs_alpha_ontology_v6_score)
    elif model_family == "xs_alpha_ontology_v6_h10d":
        # SP-C Phase 2: v6 re-tuned for h10d horizon (F-cascade weight halved
        # from 0.05 to 0.025 to compensate for the stronger h10d signal magnitude).
        _score_bundle(xs_alpha_ontology_v6_h10d_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_ss_veto_mini":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_ss_veto_mini_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v2":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v2_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v3":
        _score_bundle(xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v3_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1":
        _score_bundle(xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1":
        _score_bundle(xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1":
        _score_bundle(xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1":
        _score_bundle(xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1":
        _score_bundle(xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1_score)
    elif model_family == "xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1":
        _score_bundle(xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1_score)
    elif model_family == "xs_alpha_ontology_spk_lsk3_mid_tail_h5d":
        # SP-K baseline control: lsk3 score on the mid/tail perp universe only.
        _score_bundle(xs_alpha_ontology_spk_lsk3_mid_tail_h5d_score)
    elif model_family == "xs_alpha_ontology_spk_post_pump_stall_v1_h5d":
        # SP-K v1: lsk3 + full post_pump_stall factor contribution.
        _score_bundle(xs_alpha_ontology_spk_post_pump_stall_v1_h5d_score)
    elif model_family == "xs_alpha_ontology_spk_post_pump_stall_v2_h5d":
        # SP-K v2: risk-managed short-side-only post_pump_stall contribution.
        _score_bundle(xs_alpha_ontology_spk_post_pump_stall_v2_h5d_score)
    elif model_family == "xs_alpha_ontology_v9_h10d":
        # SP-F: v9 = v6_h10d + F1 funding_intraday_dispersion_30d at w=-0.020.
        # Per-subject 4h-grain rolling-30d mean of within-day funding_rate std.
        # G6 vs lsk3+F08 = +0.040 t=+7.24 at h10d (STRICT PASS).
        _score_bundle(xs_alpha_ontology_v9_h10d_score)
    elif model_family == "xs_alpha_ontology_v10_regime_conditional_h10d":
        # SP-J: v10 = v6_h10d base + regime-conditional F1 (rotation +0.025,
        # drawdown_rebound +0.030, trend_up 0). Regime label from
        # regime_label_v10 column (production-realistic, no lookahead).
        _score_bundle(xs_alpha_ontology_v10_regime_conditional_h10d_score)
    elif model_family == "xs_alpha_ontology_v11_absorb_qshare_h10d":
        _score_bundle(xs_alpha_ontology_v11_absorb_qshare_h10d_score)
    elif model_family == "xs_alpha_ontology_v11_drain_rs_h10d":
        _score_bundle(xs_alpha_ontology_v11_drain_rs_h10d_score)
    elif model_family == "xs_alpha_ontology_v11_flow_blend_h10d":
        _score_bundle(xs_alpha_ontology_v11_flow_blend_h10d_score)
    elif model_family == "xs_alpha_ontology_v12_mf14_sell_beta_h10d":
        _score_bundle(xs_alpha_ontology_v12_mf14_sell_beta_h10d_score)
    elif model_family == "xs_alpha_ontology_v12_mf14_sell_mid_short_h10d":
        _score_bundle(xs_alpha_ontology_v12_mf14_sell_mid_short_h10d_score)
    elif model_family == "xs_alpha_ontology_v12_mf14_rebound_idio_h10d":
        _score_bundle(xs_alpha_ontology_v12_mf14_rebound_idio_h10d_score)
    elif model_family == "xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d":
        _score_bundle(xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d_score)
    elif model_family == "xs_alpha_ontology_v7":
        # Alpha Ontology v7: lsk3 11 + F62 (M2.3) + F-cascade (SP-A). Both
        # factors mutually orthogonal vs each other (residual G6 still PASS).
        _score_bundle(xs_alpha_ontology_v7_score)
    elif model_family == "xs_alpha_ontology_v8":
        # Alpha Ontology SP-C v8: lsk3 11 + F47 funding_flip_decay_phase
        # (W3.1 idle factor unlocked at h5d via SP-C horizon scan; G6 borderline
        # PASS at h5d, stronger at h10d).
        _score_bundle(xs_alpha_ontology_v8_score)
    elif model_family == "xs_ensemble_v74_v80":
        _score_bundle(xs_ensemble_v74_v80_score)
    elif model_family == "xs_residualized_pair_book_v1":
        _score_bundle(xs_residualized_pair_book_v1_score)
    elif model_family == "xs_residualized_pair_book_v2":
        _score_bundle(xs_residualized_pair_book_v2_score)
    elif model_family == "xs_pair_spread_book_v1":
        _score_bundle(xs_pair_spread_book_v1_score)
    elif model_family == "xs_pair_spread_book_v2":
        _score_bundle(xs_pair_spread_book_v2_score)
    elif model_family == "xs_pair_spread_book_v3":
        _score_bundle(xs_pair_spread_book_v3_score)
    elif model_family == "xs_pair_spread_book_v4":
        _score_bundle(xs_pair_spread_book_v4_score)
    elif model_family == "xs_pair_spread_book_v5":
        _score_bundle(xs_pair_spread_book_v5_score)
    elif model_family == "xs_pair_spread_book_v6":
        _score_bundle(xs_pair_spread_book_v6_score)
    elif model_family == "xs_pair_spread_book_v7":
        _score_bundle(xs_pair_spread_book_v7_score)
    elif model_family == "xs_pair_spread_book_v8":
        _score_bundle(xs_pair_spread_book_v8_score)
    elif model_family == "xs_pair_spread_book_v9":
        _score_bundle(xs_pair_spread_book_v9_score)
    elif model_family == "xs_pair_spread_book_v10":
        _score_bundle(xs_pair_spread_book_v10_score)
    elif model_family == "xs_pair_spread_book_v11":
        _score_bundle(xs_pair_spread_book_v11_score)
    elif model_family == "xs_pair_spread_book_v12":
        _score_bundle(xs_pair_spread_book_v12_score)
    elif model_family == "xs_pair_spread_book_v16":
        _score_bundle(xs_pair_spread_book_v16_score)
    elif model_family == "xs_pair_spread_book_v17":
        _score_bundle(xs_pair_spread_book_v17_score)
    elif model_family == "xs_pair_spread_book_v18":
        _score_bundle(xs_pair_spread_book_v18_score)
    elif model_family == "xs_pair_spread_book_v19":
        _score_bundle(xs_pair_spread_book_v19_score)
    elif model_family == "xs_pair_spread_book_v20":
        _score_bundle(xs_pair_spread_book_v20_score)
    elif model_family == "xs_pair_spread_book_v21":
        _score_bundle(xs_pair_spread_book_v21_score)
    elif model_family == "xs_pair_spread_book_v22":
        _score_bundle(xs_pair_spread_book_v22_score)
    elif model_family == "xs_pair_spread_book_v23":
        _score_bundle(xs_pair_spread_book_v23_score)
    elif model_family == "xs_pair_spread_book_v24":
        _score_bundle(xs_pair_spread_book_v24_score)
    elif model_family == "xs_range_reversion":
        _score_bundle(xs_range_reversion_score)
    elif model_family == "xs_exhaustion_reversal":
        _score_bundle(xs_exhaustion_reversal_score)
    elif model_family == "xs_volatility_expansion_follow_through":
        _score_bundle(xs_volatility_expansion_follow_through_score)
    elif model_family == "xs_low_vol_strength":
        _score_bundle(xs_low_vol_strength_score)
    elif model_family == "xs_squeeze_breakout":
        _score_bundle(xs_squeeze_breakout_score)
    elif model_family == "xs_base_breakout":
        _score_bundle(xs_base_breakout_score)
    elif model_family == "carry_funding":
        _score_bundle(carry_funding_score)
    elif model_family == "basis_divergence":
        _score_bundle(basis_divergence_score)
    elif model_family == "volatility_expansion":
        _score_bundle(volatility_expansion_score)
    elif model_family == "event_drift":
        _score_bundle(event_drift_score)
    elif model_family == "meta_labeling":
        baseline_train = (
            breakout_continuation_score(train, feature_columns=feature_columns)
            if shape == "single_asset"
            else ranking_score(train, feature_columns=feature_columns)
        )
        baseline_validation = (
            breakout_continuation_score(validation, feature_columns=feature_columns)
            if shape == "single_asset"
            else ranking_score(validation, feature_columns=feature_columns)
        )
        baseline_test = (
            breakout_continuation_score(test, feature_columns=feature_columns)
            if shape == "single_asset"
            else ranking_score(test, feature_columns=feature_columns)
        )
        train["baseline_active"] = (baseline_train > 0).astype(int)
        validation["baseline_active"] = (baseline_validation > 0).astype(int)
        test["baseline_active"] = (baseline_test > 0).astype(int)
        meta_feature_columns = list(feature_columns) + ["baseline_active"]
        model = _build_logistic_pipeline()
        active_train = train.loc[train["baseline_active"] == 1].copy()
        if active_train.empty or active_train[resolved_target_column].nunique() < 2:
            train["score"] = baseline_train
            validation["score"] = baseline_validation
            test["score"] = baseline_test
        else:
            model.fit(active_train[meta_feature_columns], active_train[resolved_target_column])
            train["score"] = np.where(train["baseline_active"] == 1, model.predict_proba(train[meta_feature_columns])[:, 1] - 0.5, 0.0)
            validation["score"] = np.where(validation["baseline_active"] == 1, model.predict_proba(validation[meta_feature_columns])[:, 1] - 0.5, 0.0)
            test["score"] = np.where(test["baseline_active"] == 1, model.predict_proba(test[meta_feature_columns])[:, 1] - 0.5, 0.0)
    else:
        model = _build_ml_model(model_family, model_definition=model_definition)
        if train[resolved_target_column].nunique() < 2:
            train["score"] = 0.0
            validation["score"] = 0.0
            test["score"] = 0.0
        else:
            model.fit(train[feature_columns], train[resolved_target_column])
            train["score"] = model.predict_proba(train[feature_columns])[:, 1] - 0.5
            validation["score"] = model.predict_proba(validation[feature_columns])[:, 1] - 0.5
            test["score"] = model.predict_proba(test[feature_columns])[:, 1] - 0.5
    return {"train": train, "validation": validation, "test": test}


def _score_deterministic_family(
    *,
    base_rule_family: str,
    shape: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, pd.DataFrame]:
    scoring_family = str(base_rule_family or "trend_following")
    if scoring_family == "trend_following":
        scorer = trend_following_score
    elif scoring_family == "mean_reversion":
        scorer = mean_reversion_score
    elif scoring_family == "breakout_continuation":
        scorer = breakout_continuation_score
    elif scoring_family == "breakout_volatility_expansion":
        scorer = breakout_volatility_expansion_score
    elif scoring_family == "relative_strength_cross_section":
        scorer = relative_strength_score
    elif scoring_family == "ranking_scorer":
        scorer = ranking_score
    elif scoring_family == "xs_relative_strength":
        scorer = xs_relative_strength_score
    elif scoring_family == "xs_quality_strength":
        scorer = xs_quality_strength_score
    elif scoring_family == "xs_quality_strength_v3":
        scorer = xs_quality_strength_v3_score
    elif scoring_family == "xs_momentum_acceleration":
        scorer = xs_momentum_acceleration_score
    elif scoring_family == "xs_pullback_resume":
        scorer = xs_pullback_resume_score
    elif scoring_family == "xs_breakout_confirmation":
        scorer = xs_breakout_confirmation_score
    elif scoring_family == "xs_squeeze_release":
        scorer = xs_squeeze_release_score
    elif scoring_family == "xs_breakout_failure_reversal":
        scorer = xs_breakout_failure_reversal_score
    elif scoring_family == "xs_participation_drift":
        scorer = xs_participation_drift_score
    elif scoring_family == "xs_participation_drift_v3":
        scorer = xs_participation_drift_v3_score
    elif scoring_family == "xs_participation_drift_v4":
        scorer = xs_participation_drift_v4_score
    elif scoring_family == "xs_participation_drift_v5":
        scorer = xs_participation_drift_v5_score
    elif scoring_family == "xs_strength_on_reset_v1":
        scorer = xs_strength_on_reset_v1_score
    elif scoring_family == "xs_strength_on_reset_v2":
        scorer = xs_strength_on_reset_v2_score
    elif scoring_family == "xs_strength_on_reset_v3":
        scorer = xs_strength_on_reset_v3_score
    elif scoring_family == "xs_strength_on_reset_v4":
        scorer = xs_strength_on_reset_v4_score
    elif scoring_family == "xs_strength_on_reset_v5":
        scorer = xs_strength_on_reset_v5_score
    elif scoring_family == "xs_quality_pullback_v1":
        scorer = xs_quality_pullback_v1_score
    elif scoring_family == "xs_quality_pullback_v2":
        scorer = xs_quality_pullback_v2_score
    elif scoring_family == "xs_contraction_release_v1":
        scorer = xs_contraction_release_v1_score
    elif scoring_family == "xs_contraction_release_v2":
        scorer = xs_contraction_release_v2_score
    elif scoring_family == "xs_contraction_release_v3":
        scorer = xs_contraction_release_v3_score
    elif scoring_family == "xs_contraction_release_v4":
        scorer = xs_contraction_release_v4_score
    elif scoring_family == "xs_contraction_release_v5":
        scorer = xs_contraction_release_v5_score
    elif scoring_family == "xs_absorption_recovery_v1":
        scorer = xs_absorption_recovery_v1_score
    elif scoring_family == "xs_failed_breakdown_reclaim_v1":
        scorer = xs_failed_breakdown_reclaim_v1_score
    elif scoring_family == "xs_regime_switch_ranking_v1":
        scorer = xs_regime_switch_ranking_v1_score
    elif scoring_family == "xs_basis_funding_dislocation_v1":
        scorer = xs_basis_funding_dislocation_v1_score
    elif scoring_family == "xs_relative_value_spread_v1":
        scorer = xs_relative_value_spread_v1_score
    elif scoring_family == "xs_relative_value_spread_v2":
        scorer = xs_relative_value_spread_v2_score
    elif scoring_family == "xs_relative_value_spread_v3":
        scorer = xs_relative_value_spread_v3_score
    elif scoring_family == "xs_relative_value_spread_v4":
        scorer = xs_relative_value_spread_v4_score
    elif scoring_family == "xs_relative_value_spread_v5":
        scorer = xs_relative_value_spread_v5_score
    elif scoring_family == "xs_relative_value_spread_v6":
        scorer = xs_relative_value_spread_v6_score
    elif scoring_family == "xs_relative_value_spread_v7":
        scorer = xs_relative_value_spread_v7_score
    elif scoring_family == "xs_relative_value_spread_v8":
        scorer = xs_relative_value_spread_v8_score
    elif scoring_family == "xs_relative_value_spread_v9":
        scorer = xs_relative_value_spread_v9_score
    elif scoring_family == "xs_reversal_quality_v1":
        scorer = xs_reversal_quality_v1_score
    elif scoring_family == "xs_carry_dislocation_v1":
        scorer = xs_carry_dislocation_v1_score
    elif scoring_family == "xs_vol_regime_blend_v1":
        scorer = xs_vol_regime_blend_v1_score
    elif scoring_family == "xs_dispersion_regime_blend_v1":
        scorer = xs_dispersion_regime_blend_v1_score
    elif scoring_family == "xs_dual_regime_filter_v1":
        scorer = xs_dual_regime_filter_v1_score
    elif scoring_family == "xs_quad_regime_filter_v1":
        scorer = xs_quad_regime_filter_v1_score
    elif scoring_family == "xs_dual_regime_filter_v2":
        scorer = xs_dual_regime_filter_v2_score
    elif scoring_family == "xs_dual_regime_filter_v3":
        scorer = xs_dual_regime_filter_v3_score
    elif scoring_family == "xs_dual_regime_filter_v4":
        scorer = xs_dual_regime_filter_v4_score
    elif scoring_family == "xs_tier2_dual_regime_v1":
        scorer = xs_dual_regime_filter_v3_score
    elif scoring_family == "xs_dual_regime_filter_v5":
        scorer = xs_dual_regime_filter_v5_score
    elif scoring_family == "xs_dual_regime_filter_v6":
        scorer = xs_dual_regime_filter_v6_score
    elif scoring_family == "xs_dual_regime_filter_v7":
        scorer = xs_dual_regime_filter_v7_score
    elif scoring_family == "xs_dual_regime_filter_v8":
        scorer = xs_dual_regime_filter_v8_score
    elif scoring_family == "xs_dual_regime_filter_v9":
        scorer = xs_dual_regime_filter_v9_score
    elif scoring_family == "xs_dual_regime_filter_v11":
        scorer = xs_dual_regime_filter_v11_score
    elif scoring_family == "xs_minimal_v1":
        scorer = xs_minimal_v1_score
    elif scoring_family == "xs_minimal_v2":
        scorer = xs_minimal_v2_score
    elif scoring_family == "xs_minimal_v3":
        scorer = xs_minimal_v3_score
    elif scoring_family == "xs_minimal_v4":
        scorer = xs_minimal_v4_score
    elif scoring_family == "xs_minimal_v5":
        scorer = xs_minimal_v5_score
    elif scoring_family == "xs_minimal_v6":
        scorer = xs_minimal_v6_score
    elif scoring_family == "xs_minimal_v8":
        # v93: alias to v6 score (overlay applied at backtest portfolio layer)
        scorer = xs_minimal_v6_score
    elif scoring_family == "xs_minimal_v9":
        # v94: recovers iv_smooth_20 + dh_20 from v91 VIF over-pruning
        scorer = xs_minimal_v9_score
    elif scoring_family == "xs_minimal_v10":
        # v95: lean 7-factor rebuild informed by Phase 1d stability diagnostic
        scorer = xs_minimal_v10_score
    elif scoring_family == "xs_minimal_v11":
        # v96-A: only-drop isolation experiment (6 factors, v94 weights kept)
        scorer = xs_minimal_v11_score
    elif scoring_family == "xs_minimal_v12":
        # v96-B: only-add isolation experiment (v94 10 + stress_liq_conc_iv)
        scorer = xs_minimal_v12_score
    elif scoring_family == "xs_minimal_v13":
        # v99 (Phase 1d): dynamic weights via rolling-IR softmax schedule
        scorer = xs_minimal_v13_score
    elif scoring_family == "xs_alpha_ontology_v1":
        # Alpha Ontology W1.4: v91 9-factor baseline + F33 + F12 (G6+G3 strict pass).
        scorer = xs_alpha_ontology_v1_score
    elif scoring_family == "xs_alpha_ontology_v2":
        # Alpha Ontology v_alpha_v2: v_alpha_v1 11 + F29 contagion_in_degree (W3.2).
        scorer = xs_alpha_ontology_v2_score
    elif scoring_family == "xs_alpha_ontology_v3":
        # Alpha Ontology W3.6: same 11 lsk3 factors with Bayesian-IR-shrunk weights.
        scorer = xs_alpha_ontology_v3_score
    elif scoring_family == "xs_alpha_ontology_v4":
        # Alpha Ontology M2.2: lsk3 11 + F08 funding_term_skew_60.
        scorer = xs_alpha_ontology_v4_score
    elif scoring_family == "xs_alpha_ontology_v5":
        # Alpha Ontology M2.3: lsk3 11 + F62 settlement_cycle_premium_60d.
        scorer = xs_alpha_ontology_v5_score
    elif scoring_family == "xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d":
        scorer = xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d_score
    elif scoring_family == "xs_alpha_ontology_v6":
        # Alpha Ontology SP-A: lsk3 11 + liq_cascade_recency_score_5d.
        scorer = xs_alpha_ontology_v6_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d":
        # SP-C Phase 2: v6 with halved F-cascade weight tuned for h10d.
        scorer = xs_alpha_ontology_v6_h10d_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_ss_veto_mini":
        scorer = xs_alpha_ontology_v6_h10d_spk_ss_veto_mini_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated":
        scorer = xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v2":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v2_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v3":
        scorer = xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v3_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1":
        scorer = xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1":
        scorer = xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1":
        scorer = xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1":
        scorer = xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1":
        scorer = xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1_score
    elif scoring_family == "xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1":
        scorer = xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1_score
    elif scoring_family == "xs_alpha_ontology_spk_lsk3_mid_tail_h5d":
        scorer = xs_alpha_ontology_spk_lsk3_mid_tail_h5d_score
    elif scoring_family == "xs_alpha_ontology_spk_post_pump_stall_v1_h5d":
        scorer = xs_alpha_ontology_spk_post_pump_stall_v1_h5d_score
    elif scoring_family == "xs_alpha_ontology_spk_post_pump_stall_v2_h5d":
        scorer = xs_alpha_ontology_spk_post_pump_stall_v2_h5d_score
    elif scoring_family == "xs_alpha_ontology_v9_h10d":
        # SP-F: v9 = v6_h10d + F1 funding_intraday_dispersion_30d (w=-0.02).
        scorer = xs_alpha_ontology_v9_h10d_score
    elif scoring_family == "xs_alpha_ontology_v10_regime_conditional_h10d":
        # SP-J: v10 = v6_h10d + regime-conditional F1 (rotation/drawdown only).
        scorer = xs_alpha_ontology_v10_regime_conditional_h10d_score
    elif scoring_family == "xs_alpha_ontology_v11_absorb_qshare_h10d":
        scorer = xs_alpha_ontology_v11_absorb_qshare_h10d_score
    elif scoring_family == "xs_alpha_ontology_v11_drain_rs_h10d":
        scorer = xs_alpha_ontology_v11_drain_rs_h10d_score
    elif scoring_family == "xs_alpha_ontology_v11_flow_blend_h10d":
        scorer = xs_alpha_ontology_v11_flow_blend_h10d_score
    elif scoring_family == "xs_alpha_ontology_v12_mf14_sell_beta_h10d":
        scorer = xs_alpha_ontology_v12_mf14_sell_beta_h10d_score
    elif scoring_family == "xs_alpha_ontology_v12_mf14_sell_mid_short_h10d":
        scorer = xs_alpha_ontology_v12_mf14_sell_mid_short_h10d_score
    elif scoring_family == "xs_alpha_ontology_v12_mf14_rebound_idio_h10d":
        scorer = xs_alpha_ontology_v12_mf14_rebound_idio_h10d_score
    elif scoring_family == "xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d":
        scorer = xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d_score
    elif scoring_family == "xs_alpha_ontology_v7":
        # Alpha Ontology v7: lsk3 11 + F62 + F-cascade.
        scorer = xs_alpha_ontology_v7_score
    elif scoring_family == "xs_alpha_ontology_v8":
        # Alpha Ontology SP-C v8: lsk3 11 + F47 funding_flip_decay_phase.
        scorer = xs_alpha_ontology_v8_score
    elif scoring_family == "xs_ensemble_v74_v80":
        scorer = xs_ensemble_v74_v80_score
    elif scoring_family == "xs_residualized_pair_book_v1":
        scorer = xs_residualized_pair_book_v1_score
    elif scoring_family == "xs_residualized_pair_book_v2":
        scorer = xs_residualized_pair_book_v2_score
    elif scoring_family == "xs_pair_spread_book_v1":
        scorer = xs_pair_spread_book_v1_score
    elif scoring_family == "xs_pair_spread_book_v2":
        scorer = xs_pair_spread_book_v2_score
    elif scoring_family == "xs_pair_spread_book_v3":
        scorer = xs_pair_spread_book_v3_score
    elif scoring_family == "xs_pair_spread_book_v4":
        scorer = xs_pair_spread_book_v4_score
    elif scoring_family == "xs_pair_spread_book_v5":
        scorer = xs_pair_spread_book_v5_score
    elif scoring_family == "xs_pair_spread_book_v6":
        scorer = xs_pair_spread_book_v6_score
    elif scoring_family == "xs_pair_spread_book_v7":
        scorer = xs_pair_spread_book_v7_score
    elif scoring_family == "xs_pair_spread_book_v8":
        scorer = xs_pair_spread_book_v8_score
    elif scoring_family == "xs_pair_spread_book_v9":
        scorer = xs_pair_spread_book_v9_score
    elif scoring_family == "xs_pair_spread_book_v10":
        scorer = xs_pair_spread_book_v10_score
    elif scoring_family == "xs_pair_spread_book_v11":
        scorer = xs_pair_spread_book_v11_score
    elif scoring_family == "xs_pair_spread_book_v12":
        scorer = xs_pair_spread_book_v12_score
    elif scoring_family == "xs_pair_spread_book_v16":
        scorer = xs_pair_spread_book_v16_score
    elif scoring_family == "xs_pair_spread_book_v17":
        scorer = xs_pair_spread_book_v17_score
    elif scoring_family == "xs_pair_spread_book_v18":
        scorer = xs_pair_spread_book_v18_score
    elif scoring_family == "xs_pair_spread_book_v19":
        scorer = xs_pair_spread_book_v19_score
    elif scoring_family == "xs_pair_spread_book_v20":
        scorer = xs_pair_spread_book_v20_score
    elif scoring_family == "xs_pair_spread_book_v21":
        scorer = xs_pair_spread_book_v21_score
    elif scoring_family == "xs_pair_spread_book_v22":
        scorer = xs_pair_spread_book_v22_score
    elif scoring_family == "xs_pair_spread_book_v23":
        scorer = xs_pair_spread_book_v23_score
    elif scoring_family == "xs_pair_spread_book_v24":
        scorer = xs_pair_spread_book_v24_score
    elif scoring_family == "xs_range_reversion":
        scorer = xs_range_reversion_score
    elif scoring_family == "xs_exhaustion_reversal":
        scorer = xs_exhaustion_reversal_score
    elif scoring_family == "xs_volatility_expansion_follow_through":
        scorer = xs_volatility_expansion_follow_through_score
    elif scoring_family == "xs_low_vol_strength":
        scorer = xs_low_vol_strength_score
    elif scoring_family == "xs_squeeze_breakout":
        scorer = xs_squeeze_breakout_score
    elif scoring_family == "xs_base_breakout":
        scorer = xs_base_breakout_score
    elif scoring_family == "carry_funding":
        scorer = carry_funding_score
    elif scoring_family == "basis_divergence":
        scorer = basis_divergence_score
    elif scoring_family == "volatility_expansion":
        scorer = volatility_expansion_score
    elif scoring_family == "event_drift":
        scorer = event_drift_score
    else:
        scorer = breakout_continuation_score if shape == "single_asset" else ranking_score
    train["score"] = scorer(train, feature_columns=feature_columns)
    validation["score"] = scorer(validation, feature_columns=feature_columns)
    test["score"] = scorer(test, feature_columns=feature_columns)
    return {"train": train, "validation": validation, "test": test}


def _score_meta_label_wrapper(
    *,
    base_rule_family: str,
    shape: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
    target_column: str = "target_up",
) -> dict[str, pd.DataFrame]:
    baseline_bundle = _score_deterministic_family(
        base_rule_family=base_rule_family,
        shape=shape,
        train=train,
        validation=validation,
        test=test,
        feature_columns=feature_columns,
    )
    train = baseline_bundle["train"]
    validation = baseline_bundle["validation"]
    test = baseline_bundle["test"]
    train["baseline_active"] = (train["score"] > 0).astype(int)
    validation["baseline_active"] = (validation["score"] > 0).astype(int)
    test["baseline_active"] = (test["score"] > 0).astype(int)
    meta_feature_columns = list(feature_columns) + ["baseline_active"]
    model = _build_logistic_pipeline()
    active_train = train.loc[train["baseline_active"] == 1].copy()
    resolved_target_column = str(target_column or "target_up").strip() or "target_up"
    if active_train.empty or active_train[resolved_target_column].nunique() < 2:
        return {"train": train, "validation": validation, "test": test}
    model.fit(active_train[meta_feature_columns], active_train[resolved_target_column])
    train["score"] = np.where(train["baseline_active"] == 1, model.predict_proba(train[meta_feature_columns])[:, 1] - 0.5, 0.0)
    validation["score"] = np.where(validation["baseline_active"] == 1, model.predict_proba(validation[meta_feature_columns])[:, 1] - 0.5, 0.0)
    test["score"] = np.where(test["baseline_active"] == 1, model.predict_proba(test[meta_feature_columns])[:, 1] - 0.5, 0.0)
    return {"train": train, "validation": validation, "test": test}


def _build_ml_model(model_family: str, *, model_definition: dict[str, Any] | None = None):
    if model_definition:
        engine_template = str(model_definition.get("engine_template") or "").strip()
        hyperparameters = dict(model_definition.get("hyperparameters") or {})
        if engine_template == "linear_classifier":
            penalty = str(hyperparameters.get("penalty") or "l2")
            if penalty == "elasticnet":
                return Pipeline(
                    steps=(
                        ("scaler", StandardScaler()),
                        (
                            "model",
                            LogisticRegression(
                                max_iter=int(hyperparameters.get("max_iter", 4000) or 4000),
                                penalty="elasticnet",
                                solver=str(hyperparameters.get("solver") or "saga"),
                                l1_ratio=float(hyperparameters.get("l1_ratio", 0.5) or 0.5),
                                random_state=42,
                            ),
                        ),
                    )
                )
            return Pipeline(
                steps=(
                    ("scaler", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            max_iter=int(hyperparameters.get("max_iter", 2000) or 2000),
                            penalty=penalty,
                            solver=str(hyperparameters.get("solver") or "lbfgs"),
                            random_state=42,
                        ),
                    ),
                )
            )
        if engine_template == "tree_ensemble":
            implementation = str(hyperparameters.get("implementation") or "random_forest")
            if implementation == "extra_trees":
                return ExtraTreesClassifier(
                    n_estimators=int(hyperparameters.get("n_estimators", 300) or 300),
                    max_depth=None if hyperparameters.get("max_depth") in {None, ""} else int(hyperparameters.get("max_depth")),
                    min_samples_leaf=int(hyperparameters.get("min_samples_leaf", 4) or 4),
                    random_state=42,
                )
            return RandomForestClassifier(
                n_estimators=int(hyperparameters.get("n_estimators", 200) or 200),
                max_depth=None if hyperparameters.get("max_depth") in {None, ""} else int(hyperparameters.get("max_depth")),
                min_samples_leaf=int(hyperparameters.get("min_samples_leaf", 5) or 5),
                random_state=42,
            )
        if engine_template == "boosted_tree":
            implementation = str(hyperparameters.get("implementation") or "hist_gradient_boosting")
            if implementation == "gradient_boosting":
                return GradientBoostingClassifier(
                    learning_rate=float(hyperparameters.get("learning_rate", 0.1) or 0.1),
                    random_state=42,
                )
            return HistGradientBoostingClassifier(
                max_depth=None if hyperparameters.get("max_depth") in {None, ""} else int(hyperparameters.get("max_depth")),
                max_iter=int(hyperparameters.get("max_iter", 200) or 200),
                learning_rate=float(hyperparameters.get("learning_rate", 0.05) or 0.05),
                random_state=42,
            )
    if model_family == "logistic_regression":
        return _build_logistic_pipeline()
    if model_family == "elasticnet_logistic":
        return Pipeline(
            steps=(
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        max_iter=4000,
                        penalty="elasticnet",
                        solver="saga",
                        l1_ratio=0.5,
                        random_state=42,
                    ),
                ),
            )
        )
    if model_family == "random_forest":
        return RandomForestClassifier(n_estimators=200, max_depth=6, min_samples_leaf=5, random_state=42)
    if model_family == "extra_trees_classifier":
        return ExtraTreesClassifier(n_estimators=300, max_depth=8, min_samples_leaf=4, random_state=42)
    if model_family == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(max_depth=6, max_iter=200, learning_rate=0.05, random_state=42)
    if model_family == "gradient_boosting_classifier":
        return GradientBoostingClassifier(random_state=42)
    raise ValueError(f"unsupported model family: {model_family}")


def _chronological_split(
    frame: pd.DataFrame,
    *,
    time_col: str,
    label_horizon_bars: int | None = None,
    split_realization_contract: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    return chronological_split_with_purge(
        frame=frame,
        time_col=time_col,
        label_horizon_bars=label_horizon_bars,
        split_realization_contract=split_realization_contract,
    )


def _run_walk_forward(
    *,
    frame: pd.DataFrame,
    shape: str,
    model_family: str,
    feature_columns: list[str],
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    target_column: str = "target_up",
    execution_cost_model: dict[str, Any] | None = None,
    stress_execution_cost_model: dict[str, Any] | None = None,
    reference_capital_usd: float | None = None,
    capacity_limits: dict[str, float] | None = None,
    validation_contract: dict[str, Any] | None = None,
    model_definition: dict[str, Any] | None = None,
    include_periods: bool = False,
) -> dict[str, Any]:
    resolved_validation_contract = validation_contract or load_validation_contract()
    resolved_split_realization_contract = resolve_split_realization_contract(
        contract=split_realization_contract,
        shape=shape,
    )
    resolved_execution_cost_model = (
        dict(execution_cost_model)
        if execution_cost_model
        else resolve_execution_cost_model(contract=load_execution_cost_model(), scenario="base")
    )
    resolved_stress_execution_cost_model = (
        dict(stress_execution_cost_model)
        if stress_execution_cost_model
        else resolve_execution_cost_model(contract=load_execution_cost_model(), scenario="stress")
    )
    resolved_reference_capital_usd = (
        float(reference_capital_usd)
        if reference_capital_usd is not None
        else validation_contract_reference_capital_usd(
            strategy_profile=str(constraints.get("strategy_profile") or ""),
            contract=resolved_validation_contract,
        )
    )
    resolved_capacity_limits = dict(capacity_limits or execution_capacity_limits(resolved_validation_contract))
    time_index = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    start_anchor = time_index.min() + timedelta(days=120)
    final_anchor = time_index.max() - timedelta(days=30)
    windows: list[dict[str, Any]] = []
    boundary_contamination_total = 0
    all_windows_contract_passed = True
    data_gap_blockers: set[str] = set()
    current_anchor = start_anchor
    while current_anchor <= final_anchor:
        train_end = current_anchor - timedelta(days=30)
        validation_end = current_anchor
        test_end = current_anchor + timedelta(days=30)
        train_df, validation_df, test_df = walk_forward_split_with_purge(
            frame=frame,
            time_col="timestamp_ms",
            train_end=train_end,
            validation_end=validation_end,
            test_end=test_end,
            split_realization_contract=resolved_split_realization_contract,
        )
        if not train_df.empty and not validation_df.empty and not test_df.empty:
            expected_window_rebalance_count = expected_rebalance_count(
                frame=test_df,
                contract=resolved_split_realization_contract,
            )
            window_overlap_integrity = evaluate_overlap_integrity(
                train_df=train_df,
                validation_df=validation_df,
                test_df=test_df,
                evaluation_step_bars=split_contract_realization_step_bars(resolved_split_realization_contract),
                prediction_count=int(len(test_df)),
                rebalance_count=expected_window_rebalance_count,
                split_realization_contract=resolved_split_realization_contract,
            )
            window_boundary_contamination_total = split_boundary_contamination_total(
                counts=window_overlap_integrity.get("split_boundary_contamination_counts")
            )
            boundary_contamination_total += window_boundary_contamination_total
            all_windows_contract_passed = all_windows_contract_passed and bool(window_overlap_integrity.get("passed"))
            if not window_overlap_integrity.get("passed"):
                windows.append(
                    {
                        "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                        "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                        "test_start_utc": _frame_timestamp_utc(test_df, reducer="min"),
                        "test_end_utc": _frame_timestamp_utc(test_df, reducer="max") or test_end.isoformat().replace("+00:00", "Z"),
                        "contract_passed": False,
                        "split_boundary_contamination_total": window_boundary_contamination_total,
                        "split_boundary_contamination_counts": dict(window_overlap_integrity.get("split_boundary_contamination_counts") or {}),
                        "backtest_realization_mismatch": dict(window_overlap_integrity.get("backtest_horizon_mismatch") or {}),
                        "sharpe": 0.0,
                        "net_return": 0.0,
                        "max_drawdown": 0.0,
                        "gross_return_before_costs": 0.0,
                        "fee_cost_return": 0.0,
                        "slippage_cost_return": 0.0,
                        "funding_cost_return": 0.0,
                        "borrow_cost_return": 0.0,
                        "turnover": 0.0,
                        "trade_count": 0,
                        "rebalance_count": 0,
                        "latency_bars": int(resolved_execution_cost_model["latency_bars"]),
                        "execution_venue": None,
                        "trade_notional_usd_total": 0.0,
                        "max_trade_participation_rate": 0.0,
                        "max_inventory_participation_rate": 0.0,
                        "stress_net_return": 0.0,
                        "stress_sharpe": 0.0,
                        "stress_max_drawdown": 0.0,
                        "stress_gross_return_before_costs": 0.0,
                        "stress_fee_cost_return": 0.0,
                        "stress_slippage_cost_return": 0.0,
                        "stress_funding_cost_return": 0.0,
                        "stress_borrow_cost_return": 0.0,
                        "stress_latency_bars": int(resolved_stress_execution_cost_model["latency_bars"]),
                        "stress_execution_venue": None,
                        "stress_trade_notional_usd_total": 0.0,
                        "stress_max_trade_participation_rate": 0.0,
                        "stress_max_inventory_participation_rate": 0.0,
                        "max_participation_rate": 0.0,
                        "stress_max_participation_rate": 0.0,
                        "capacity_breach_count": 0,
                        "stress_capacity_breach_count": 0,
                        "data_gap_blockers": [],
                        "stress_data_gap_blockers": [],
                        "frictionless_metrics": {"net_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0},
                    }
                )
                current_anchor = current_anchor + timedelta(days=30)
                continue
            scored = _fit_and_score(
                model_family=model_family,
                shape=shape,
                train_df=train_df,
                validation_df=validation_df,
                test_df=test_df,
                feature_columns=feature_columns,
                target_column=target_column,
                model_definition=model_definition,
            )
            window_model_fit_summary = dict(scored.get("fit_metadata") or {})
            if shape == "single_asset":
                metrics = _backtest_single_asset(
                    scored["test"],
                    constraints=constraints,
                    split_realization_contract=resolved_split_realization_contract,
                    execution_cost_model=resolved_execution_cost_model,
                    reference_capital_usd=resolved_reference_capital_usd,
                    capacity_limits=resolved_capacity_limits,
                    include_periods=include_periods,
                )
                stress_metrics = _backtest_single_asset(
                    scored["test"],
                    constraints=constraints,
                    split_realization_contract=resolved_split_realization_contract,
                    execution_cost_model=resolved_stress_execution_cost_model,
                    reference_capital_usd=resolved_reference_capital_usd,
                    capacity_limits=resolved_capacity_limits,
                    include_periods=include_periods,
                )
            else:
                metrics = _backtest_cross_sectional(
                    scored["test"],
                    constraints=constraints,
                    split_realization_contract=resolved_split_realization_contract,
                    execution_cost_model=resolved_execution_cost_model,
                    reference_capital_usd=resolved_reference_capital_usd,
                    capacity_limits=resolved_capacity_limits,
                    include_periods=include_periods,
                )
                stress_metrics = _backtest_cross_sectional(
                    scored["test"],
                    constraints=constraints,
                    split_realization_contract=resolved_split_realization_contract,
                    execution_cost_model=resolved_stress_execution_cost_model,
                    reference_capital_usd=resolved_reference_capital_usd,
                    capacity_limits=resolved_capacity_limits,
                    include_periods=include_periods,
                )
            test_start_utc = _frame_timestamp_utc(scored["test"], reducer="min")
            test_end_utc = _frame_timestamp_utc(scored["test"], reducer="max")
            window_payload = {
                "train_end_utc": train_end.isoformat().replace("+00:00", "Z"),
                "validation_end_utc": validation_end.isoformat().replace("+00:00", "Z"),
                "test_start_utc": test_start_utc,
                "test_end_utc": test_end_utc or test_end.isoformat().replace("+00:00", "Z"),
                "contract_passed": True,
                "split_boundary_contamination_total": window_boundary_contamination_total,
                "split_boundary_contamination_counts": dict(window_overlap_integrity.get("split_boundary_contamination_counts") or {}),
                "backtest_realization_mismatch": dict(window_overlap_integrity.get("backtest_horizon_mismatch") or {}),
                "sharpe": metrics["sharpe"],
                "net_return": metrics["net_return"],
                "max_drawdown": metrics["max_drawdown"],
                "gross_return_before_costs": metrics["gross_return_before_costs"],
                "fee_cost_return": metrics["fee_cost_return"],
                "slippage_cost_return": metrics["slippage_cost_return"],
                "funding_cost_return": metrics["funding_cost_return"],
                "borrow_cost_return": metrics["borrow_cost_return"],
                "turnover": metrics["turnover"],
                "trade_count": metrics["trade_count"],
                "rebalance_count": metrics["rebalance_count"],
                "latency_bars": metrics["latency_bars"],
                "execution_venue": metrics["execution_venue"],
                "trade_notional_usd_total": metrics["trade_notional_usd_total"],
                "max_trade_participation_rate": metrics["max_trade_participation_rate"],
                "max_inventory_participation_rate": metrics["max_inventory_participation_rate"],
                "stress_net_return": stress_metrics["net_return"],
                "stress_sharpe": stress_metrics["sharpe"],
                "stress_max_drawdown": stress_metrics["max_drawdown"],
                "stress_gross_return_before_costs": stress_metrics["gross_return_before_costs"],
                "stress_fee_cost_return": stress_metrics["fee_cost_return"],
                "stress_slippage_cost_return": stress_metrics["slippage_cost_return"],
                "stress_funding_cost_return": stress_metrics["funding_cost_return"],
                "stress_borrow_cost_return": stress_metrics["borrow_cost_return"],
                "stress_latency_bars": stress_metrics["latency_bars"],
                "stress_execution_venue": stress_metrics["execution_venue"],
                "stress_trade_notional_usd_total": stress_metrics["trade_notional_usd_total"],
                "stress_max_trade_participation_rate": stress_metrics["max_trade_participation_rate"],
                "stress_max_inventory_participation_rate": stress_metrics["max_inventory_participation_rate"],
                "max_participation_rate": stress_metrics["max_participation_rate"],
                "stress_max_participation_rate": stress_metrics["max_participation_rate"],
                "capacity_breach_count": metrics["capacity_breach_count"],
                "stress_capacity_breach_count": stress_metrics["capacity_breach_count"],
                "data_gap_blockers": list(metrics.get("data_gap_blockers") or []),
                "stress_data_gap_blockers": list(stress_metrics.get("data_gap_blockers") or []),
                "frictionless_metrics": dict(metrics.get("frictionless_metrics") or {}),
            }
            if window_model_fit_summary:
                window_payload["model_fit_summary"] = window_model_fit_summary
            if include_periods and list(metrics.get("periods") or []):
                window_payload["periods"] = [dict(item) for item in list(metrics.get("periods") or [])]
            if include_periods and list(stress_metrics.get("periods") or []):
                window_payload["stress_periods"] = [dict(item) for item in list(stress_metrics.get("periods") or [])]
            windows.append(window_payload)
            data_gap_blockers.update(str(item) for item in list(metrics.get("data_gap_blockers") or []) if str(item).strip())
            data_gap_blockers.update(str(item) for item in list(stress_metrics.get("data_gap_blockers") or []) if str(item).strip())
        current_anchor = current_anchor + timedelta(days=30)
    sharpes = [float(item["sharpe"]) for item in windows]
    return {
        "window_count": len(windows),
        "windows": windows,
        "median_oos_sharpe": statistics.median(sharpes) if sharpes else 0.0,
        "boundary_contamination_total": int(boundary_contamination_total),
        "all_windows_contract_passed": bool(all_windows_contract_passed),
        "data_gap_blockers": sorted(data_gap_blockers),
    }


def _backtest_single_asset(
    frame: pd.DataFrame,
    *,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any] | None = None,
    execution_cost_model: dict[str, Any] | None = None,
    scenario: str = "base",
    reference_capital_usd: float | None = None,
    capacity_limits: dict[str, float] | None = None,
    include_periods: bool = False,
) -> dict[str, Any]:
    ordered = frame.sort_values("timestamp_ms").copy()
    resolved_split_realization_contract = (
        resolve_split_realization_contract(contract=split_realization_contract, shape="single_asset")
        if split_realization_contract
        else build_split_realization_contract(
            shape="single_asset",
            bar_interval_ms=infer_interval_ms(ordered["timestamp_ms"]),
        )
    )
    resolved_execution_cost_model = (
        dict(execution_cost_model)
        if execution_cost_model
        else resolve_execution_cost_model(contract=load_execution_cost_model(), scenario=scenario)
    )
    resolved_capacity_limits = dict(capacity_limits or execution_capacity_limits(load_validation_contract()))
    resolved_reference_capital_usd = reference_capital_usd
    if resolved_reference_capital_usd is None:
        strategy_profile = str(constraints.get("strategy_profile") or "").strip()
        if strategy_profile:
            resolved_reference_capital_usd = validation_contract_reference_capital_usd(
                strategy_profile=strategy_profile,
                contract=load_validation_contract(),
            )
    return backtest_single_asset(
        frame=ordered,
        constraints=constraints,
        split_realization_contract=resolved_split_realization_contract,
        execution_cost_model=resolved_execution_cost_model,
        reference_capital_usd=resolved_reference_capital_usd,
        capacity_limits=resolved_capacity_limits,
        include_periods=include_periods,
    )


def _backtest_cross_sectional(
    frame: pd.DataFrame,
    *,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any] | None = None,
    execution_cost_model: dict[str, Any] | None = None,
    scenario: str = "base",
    reference_capital_usd: float | None = None,
    capacity_limits: dict[str, float] | None = None,
    include_periods: bool = False,
) -> dict[str, Any]:
    resolved_split_realization_contract = (
        resolve_split_realization_contract(contract=split_realization_contract, shape="cross_sectional")
        if split_realization_contract
        else build_split_realization_contract(
            shape="cross_sectional",
            bar_interval_ms=infer_interval_ms(frame["timestamp_ms"]) if not frame.empty else 86_400_000,
        )
    )
    resolved_execution_cost_model = (
        dict(execution_cost_model)
        if execution_cost_model
        else resolve_execution_cost_model(contract=load_execution_cost_model(), scenario=scenario)
    )
    resolved_capacity_limits = dict(capacity_limits or execution_capacity_limits(load_validation_contract()))
    resolved_reference_capital_usd = reference_capital_usd
    if resolved_reference_capital_usd is None:
        strategy_profile = str(constraints.get("strategy_profile") or "").strip()
        if strategy_profile:
            resolved_reference_capital_usd = validation_contract_reference_capital_usd(
                strategy_profile=strategy_profile,
                contract=load_validation_contract(),
            )
    return backtest_cross_sectional(
        frame=frame.copy(),
        constraints=constraints,
        split_realization_contract=resolved_split_realization_contract,
        execution_cost_model=resolved_execution_cost_model,
        reference_capital_usd=resolved_reference_capital_usd,
        capacity_limits=resolved_capacity_limits,
        include_periods=include_periods,
    )


def _single_asset_position_from_score(scores: pd.Series, *, constraints: dict[str, Any]) -> pd.Series:
    if constraints["long_only"]:
        execution_venue = str(constraints.get("execution_venue") or ("spot" if bool(constraints.get("spot_only")) else "perp")).strip().lower()
        if execution_venue == "spot":
            neutral_band_abs_score = float(constraints.get("neutral_band_abs_score", 0.0) or 0.0)
            if neutral_band_abs_score < 0.0:
                neutral_band_abs_score = 0.0
            full_size_abs_score = float(constraints.get("long_only_full_size_abs_score", 0.5) or 0.5)
            if full_size_abs_score <= neutral_band_abs_score:
                full_size_abs_score = neutral_band_abs_score + 0.1
            positive_scores = scores.where(scores > neutral_band_abs_score, other=0.0).clip(lower=0.0)
            scaled_exposure = (
                (positive_scores - neutral_band_abs_score)
                / max(full_size_abs_score - neutral_band_abs_score, 1e-9)
            ).clip(lower=0.0, upper=1.0)
            return pd.Series(
                scaled_exposure * float(constraints["long_leverage"]),
                index=scores.index,
                dtype="float64",
            )
        return pd.Series(
            np.where(scores > 0, constraints["long_leverage"], 0.0),
            index=scores.index,
            dtype="float64",
        )
    positions = np.where(scores > 0, constraints["long_leverage"], 0.0)
    positions = np.where(scores < 0, -constraints["short_leverage"], positions)
    return pd.Series(positions, index=scores.index, dtype="float64")


def _performance_metrics(
    *,
    period_returns: pd.Series,
    turnover: pd.Series,
    periods_per_year: int,
    trade_count: int,
    rebalance_count: int,
    evaluation_step_bars: int,
    participation_rates: pd.Series | None = None,
    available_quote_volume_usd: pd.Series | None = None,
) -> dict[str, Any]:
    cleaned_returns = period_returns.fillna(0.0).astype("float64")
    equity_curve = (1.0 + cleaned_returns).cumprod()
    running_max = equity_curve.cummax()
    drawdown = ((running_max - equity_curve) / running_max.replace(0.0, np.nan)).fillna(0.0)
    std = float(cleaned_returns.std(ddof=0))
    sharpe = 0.0 if std == 0.0 else float(cleaned_returns.mean() / std * math.sqrt(periods_per_year))
    participation = participation_rates.fillna(0.0).astype("float64") if participation_rates is not None else pd.Series(dtype="float64")
    available_volume = available_quote_volume_usd.fillna(0.0).astype("float64") if available_quote_volume_usd is not None else pd.Series(dtype="float64")
    return {
        "net_return": float(equity_curve.iloc[-1] - 1.0) if not equity_curve.empty else 0.0,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.max()) if not drawdown.empty else 0.0,
        "turnover": float(turnover.fillna(0.0).sum()),
        "trade_count": int(trade_count),
        "rebalance_count": int(rebalance_count),
        "evaluation_step_bars": int(evaluation_step_bars),
        "max_participation_rate": float(participation.max()) if not participation.empty else 0.0,
        "available_quote_volume_usd_total": float(available_volume.sum()) if not available_volume.empty else 0.0,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "net_return": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "turnover": 0.0,
        "trade_count": 0,
        "rebalance_count": 0,
        "evaluation_step_bars": 1,
        "max_participation_rate": 0.0,
        "available_quote_volume_usd_total": 0.0,
    }


def _available_quote_volume_usd_for_row(row: pd.Series) -> float:
    for field_name in (
        "spot_quote_volume",
        "intraday_quote_volume_4h",
        "daily_quote_volume",
        "rolling_median_quote_volume_usd_30d",
    ):
        try:
            value = float(row.get(field_name, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0.0:
            return value
    return 0.0


def _frame_timestamp_utc(frame: pd.DataFrame, *, reducer: str) -> str | None:
    if frame.empty:
        return None
    series = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)
    timestamp = series.min() if reducer == "min" else series.max()
    return timestamp.isoformat().replace("+00:00", "Z")


def _experiment_status_from_validation_contract(validation_contract: dict[str, Any]) -> str:
    status = str(validation_contract.get("status") or "").strip()
    blocker_codes = set(validation_contract_blocker_codes(validation_contract))
    if blocker_codes.intersection(
        {"split_realization_contract_failed", "feature_admission_failed", "reproducibility_contract_failed"}
    ):
        return EXPERIMENT_STATUS_INVALIDATED
    if status == "passed":
        return "pass"
    if status == "falsification_required":
        return EXPERIMENT_STATUS_QUARANTINED
    if status == "incomplete":
        return EXPERIMENT_STATUS_INVALIDATED
    return "fail"


def _alpha_card_validation_contract_summary(validation_contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": str(validation_contract.get("contract_version") or ""),
        "status": str(validation_contract.get("status") or ""),
        "required_sections_present": list(validation_contract.get("required_sections_present") or []),
        "blocker_codes": validation_contract_blocker_codes(validation_contract),
    }


def _falsification_outcome(
    *,
    experiment_root: Path,
    alpha_card: dict[str, Any],
    validation_report: dict[str, Any],
) -> dict[str, Any]:
    validation_contract = dict(alpha_card.get("validation_contract") or validation_report.get("validation_contract") or {})
    blocker_codes = validation_contract_blocker_codes(validation_contract)
    if not falsification_is_required(
        experiment_status=str(alpha_card.get("experiment_status") or ""),
        validation_contract=validation_contract,
        blocker_codes=blocker_codes,
    ):
        return falsification_outcome_for_skipped_audit(
            validation_contract=validation_contract,
            universe_metadata=alpha_card,
        )
    audit = run_falsification_audit(
        experiment_root=experiment_root,
        alpha_card=alpha_card,
        validation_report=validation_report,
    )
    return {
        "falsification_status": str(audit.get("status") or "failed"),
        "falsification_audit_path": str(audit.get("falsification_audit_path") or ""),
        "falsification_blocker_codes": [
            str(item).strip()
            for item in list(audit.get("blocker_codes") or [])
            if str(item).strip()
        ],
        "credible_research_evidence": bool(audit.get("credible_research_evidence")),
    }


def _apply_falsification_outcome_to_payload(payload: dict[str, Any], outcome: dict[str, Any]) -> None:
    payload["falsification_status"] = str(outcome.get("falsification_status") or NOT_REQUIRED_FALSIFICATION_STATUS)
    audit_path = str(outcome.get("falsification_audit_path") or "").strip()
    payload["falsification_audit_path"] = audit_path or None
    payload["falsification_blocker_codes"] = [
        str(item).strip()
        for item in list(outcome.get("falsification_blocker_codes") or [])
        if str(item).strip()
    ]
    payload["credible_research_evidence"] = bool(outcome.get("credible_research_evidence"))


def _placeholder_validation_contract(
    *,
    status: str,
    blocker_codes: list[str],
    required_sections_present: list[str],
) -> dict[str, Any]:
    return {
        "contract_version": VALIDATION_CONTRACT_VERSION,
        "status": status,
        "required_sections_present": list(required_sections_present),
        "blockers": [
            {
                "code": code,
                "message": code,
                "scope": "validation_contract",
            }
            for code in blocker_codes
        ],
        "summary": {},
    }


def _top_long_candidates(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    latest_timestamp = int(frame["timestamp_ms"].max())
    latest = frame.loc[frame["timestamp_ms"] == latest_timestamp].sort_values("score", ascending=False).head(3)
    return [
        {
            "subject": str(row["subject"]),
            "score": float(row["score"]),
            "liquidity_bucket": str(row["liquidity_bucket"]),
        }
        for _, row in latest.iterrows()
    ]


def _derivatives_first_cross_section_feature_columns(numeric_feature_columns: list[str]) -> list[str]:
    preferred = [
        "funding_rate",
        "funding_zscore_20",
        "oi_change_5",
        "basis_proxy",
        "basis_zscore_20",
        "perp_quote_volume_usd",
    ]
    return [
        column
        for column in preferred
        if column in numeric_feature_columns and is_model_admissible_numeric_column(column)
    ]


def _alpha_card_markdown(alpha_card: dict[str, Any]) -> str:
    validation_contract = dict(alpha_card.get("validation_contract") or {})
    lines = [
        "# Alpha Card",
        "",
        f"- Experiment: `{alpha_card.get('experiment_id')}`",
        f"- Experiment status: `{alpha_card.get('experiment_status')}`",
        f"- Lifecycle: `{alpha_card.get('lifecycle')}`",
        f"- Validation: `{alpha_card.get('validation')}`",
        f"- Validation contract: `{validation_contract.get('status')}`",
        f"- Falsification: `{alpha_card.get('falsification_status')}`",
        f"- Credible research evidence: `{alpha_card.get('credible_research_evidence')}`",
        f"- Publication status: `{alpha_card.get('publication_status')}`",
        f"- Shape: `{alpha_card.get('shape')}`",
        f"- Model: `{alpha_card.get('model_family')}`",
        f"- Strategy profile: `{alpha_card.get('strategy_profile')}`",
    ]
    if alpha_card.get("subject"):
        lines.append(f"- Subject: `{alpha_card.get('subject')}`")
    if isinstance(alpha_card.get("validation_metrics"), dict):
        lines.extend(
            [
                "",
                "## Validation",
                "",
                f"- Net return: `{alpha_card['validation_metrics'].get('net_return')}`",
                f"- Sharpe: `{alpha_card['validation_metrics'].get('sharpe')}`",
                f"- Max drawdown: `{alpha_card['validation_metrics'].get('max_drawdown')}`",
                "",
                "## Test",
                "",
                f"- Net return: `{alpha_card['test_metrics'].get('net_return')}`",
                f"- Sharpe: `{alpha_card['test_metrics'].get('sharpe')}`",
                f"- Max drawdown: `{alpha_card['test_metrics'].get('max_drawdown')}`",
                f"- Trade count: `{alpha_card['test_metrics'].get('trade_count')}`",
            ]
        )
    if alpha_card.get("top_long_candidates"):
        lines.extend(["", "## Top Long Candidates", ""])
        for row in alpha_card["top_long_candidates"]:
            lines.append(f"- `{row['subject']}` score=`{row['score']}` bucket=`{row['liquidity_bucket']}`")
    derivatives_quality = dict(alpha_card.get("derivatives_strategy_quality") or {})
    if derivatives_quality:
        funding_family = dict(derivatives_quality.get("funding_family") or {})
        open_interest_family = dict(derivatives_quality.get("open_interest_family") or {})
        gap_days = dict(derivatives_quality.get("funding_minus_open_interest_gap_days") or {})
        lines.extend(
            [
                "",
                "## Derivatives Data Quality",
                "",
                f"- Status: `{derivatives_quality.get('status')}`",
                f"- Used derivatives features: `{', '.join(derivatives_quality.get('used_derivatives_feature_columns') or []) or 'none'}`",
                f"- Funding train-ready row fraction: `{funding_family.get('train_ready_row_fraction')}`",
                f"- OI train-ready row fraction: `{open_interest_family.get('train_ready_row_fraction')}`",
                f"- Funding vs OI median coverage gap days: `{gap_days.get('median')}`",
                f"- Warning codes: `{', '.join(derivatives_quality.get('warning_codes') or []) or 'none'}`",
            ]
        )
    fixed_set_comparison = dict(alpha_card.get("fixed_set_comparison") or {})
    if fixed_set_comparison:
        promotion_gate = dict(fixed_set_comparison.get("promotion_gate") or {})
        research_gate = dict(fixed_set_comparison.get("research_gate") or {})
        lines.extend(
            [
                "",
                "## Fixed-Set Comparison",
                "",
                f"- Status: `{fixed_set_comparison.get('status')}`",
                f"- Candidate label: `{fixed_set_comparison.get('candidate_label')}`",
                f"- Research gate passed: `{research_gate.get('passed')}`",
                f"- Promotion gate passed: `{promotion_gate.get('passed')}`",
                f"- Promotion blockers: `{', '.join(promotion_gate.get('blocker_codes') or []) or 'none'}`",
            ]
        )
    return "\n".join(lines)


def _backend_mode_for_compiler_backend(compiler_backend: str | None) -> str:
    return "live" if str(compiler_backend or "").strip().lower() == "live" else "deterministic"


def _initial_validation_state(*, status: str, compiler_backend: str | None) -> str:
    normalized = str(status or "").strip()
    if normalized == EXPERIMENT_STATUS_INVALIDATED:
        return "failed"
    if is_quarantined_experiment_status(status):
        return "failed"
    if is_rerun_required_experiment_status(status) or is_pipeline_unreliable_pending_single_asset_fix(status):
        return "insufficient_track_record"
    if normalized != "pass":
        return "failed"
    if _backend_mode_for_compiler_backend(compiler_backend) != "live":
        return "deterministic_only"
    return "passed"


def _core_publication_assessment(
    *,
    experiment_status: str,
    validation_contract: dict[str, Any],
    compiler_backend: str | None,
    falsification_status: str | None = None,
    falsification_blocker_codes: list[str] | None = None,
    pit_universe_valid: bool = True,
    credible_research_evidence: bool = False,
) -> dict[str, Any]:
    raw_blocker_codes = [
        str(item).strip()
        for item in list(validation_contract.get("blocker_codes") or [])
        if str(item).strip()
    ]
    falsification_blockers = [
        str(item).strip()
        for item in list(falsification_blocker_codes or [])
        if str(item).strip()
    ]
    requires_falsification = falsification_is_required(
        experiment_status=experiment_status,
        validation_contract=validation_contract,
        blocker_codes=raw_blocker_codes,
    )
    blocker_codes = list(raw_blocker_codes)
    if requires_falsification and str(falsification_status or "").strip() == "cleared":
        blocker_codes = [code for code in blocker_codes if code != "sharpe_anomaly_detected"]
    quality_blockers = list(blocker_codes)
    if not pit_universe_valid:
        quality_blockers.append("non_point_in_time_universe")
        validation = "invalidated_non_point_in_time_universe"
    elif requires_falsification and str(falsification_status or "").strip() != "cleared":
        quality_blockers.extend(falsification_blockers or ["falsification_not_cleared"])
        validation = INVALIDATED_UNVERIFIED_RESEARCH_EVIDENCE
    else:
        effective_status = (
            "pass"
            if requires_falsification
            and str(falsification_status or "").strip() == "cleared"
            and is_quarantined_experiment_status(experiment_status)
            else experiment_status
        )
        validation = _initial_validation_state(status=effective_status, compiler_backend=compiler_backend)
    if not credible_research_evidence:
        quality_blockers.append("credible_research_evidence=false")
    quality_blockers = sorted({item for item in quality_blockers if item})
    quality_gate_passed = validation == "passed" and not quality_blockers
    return {
        "validation": validation,
        "quality_gate_passed": quality_gate_passed,
        "quality_blockers": quality_blockers,
        "metrics_snapshot": {
            "experiment_status": str(experiment_status or "").strip(),
            "validation_contract_status": str(validation_contract.get("status") or "").strip(),
            "validation_contract_version": str(validation_contract.get("contract_version") or "").strip(),
            "blocker_codes": blocker_codes,
            "backend_mode": _backend_mode_for_compiler_backend(compiler_backend),
            "falsification_status": str(falsification_status or NOT_REQUIRED_FALSIFICATION_STATUS),
            "falsification_blocker_codes": falsification_blockers,
            "credible_research_evidence": bool(credible_research_evidence),
            "pit_universe_valid": bool(pit_universe_valid),
        },
    }


def _finalize_experiment_evidence(
    *,
    experiment_root: Path,
    experiment_spec: dict[str, Any],
    backtest_report: dict[str, Any],
    validation_report: dict[str, Any],
    alpha_card: dict[str, Any],
    compiler_backend: str | None,
) -> dict[str, str]:
    experiment_spec_path = experiment_root / "experiment_spec.json"
    backtest_report_path = experiment_root / "backtest_report.json"
    validation_report_path = experiment_root / "validation_report.json"
    alpha_card_path = experiment_root / "alpha_card.json"
    alpha_card_md_path = experiment_root / "alpha_card.md"
    statistical_falsification_path = experiment_root / "statistical_falsification_report.json"
    alpha_experiment_card_path = experiment_root / "alpha_experiment_card.json"
    write_json(experiment_spec_path, experiment_spec)
    write_json(backtest_report_path, backtest_report)
    write_json(validation_report_path, validation_report)
    write_json(alpha_card_path, alpha_card)
    falsification_outcome = _falsification_outcome(
        experiment_root=experiment_root,
        alpha_card=alpha_card,
        validation_report=validation_report,
    )
    _apply_falsification_outcome_to_payload(validation_report, falsification_outcome)
    _apply_falsification_outcome_to_payload(alpha_card, falsification_outcome)
    publication_assessment = _core_publication_assessment(
        experiment_status=str(alpha_card.get("experiment_status") or ""),
        validation_contract=dict(alpha_card.get("validation_contract") or {}),
        compiler_backend=compiler_backend,
        falsification_status=str(alpha_card.get("falsification_status") or ""),
        falsification_blocker_codes=list(alpha_card.get("falsification_blocker_codes") or []),
        pit_universe_valid=pit_universe_artifact_is_valid(alpha_card),
        credible_research_evidence=bool(alpha_card.get("credible_research_evidence")),
    )
    alpha_card["backend_mode"] = _backend_mode_for_compiler_backend(compiler_backend)
    alpha_card["validation"] = publication_assessment["validation"]
    alpha_card["publication_status"] = "archived_only"
    alpha_card["quality_summary"] = {
        "quality_gate_passed": publication_assessment["quality_gate_passed"],
        "quality_blockers": publication_assessment["quality_blockers"],
        "metrics_snapshot": publication_assessment["metrics_snapshot"],
        "credible_research_evidence": bool(alpha_card.get("credible_research_evidence")),
    }
    quality_summary = dict(validation_report.get("quality_summary") or {})
    quality_summary["quality_gate_passed"] = False
    quality_blockers = [
        str(item).strip()
        for item in list(quality_summary.get("quality_blockers") or [])
        if str(item).strip()
    ]
    quality_summary["quality_blockers"] = sorted(
        set(quality_blockers) | set(alpha_card["quality_summary"]["quality_blockers"])
    )
    metrics_snapshot = dict(quality_summary.get("metrics_snapshot") or {})
    fixed_set_comparison = dict(alpha_card.get("fixed_set_comparison") or {})
    metrics_snapshot.update(
        {
            "falsification_status": alpha_card.get("falsification_status"),
            "falsification_blocker_codes": alpha_card.get("falsification_blocker_codes"),
            "credible_research_evidence": alpha_card.get("credible_research_evidence"),
            "fixed_set_comparison_status": fixed_set_comparison.get("status"),
            "fixed_set_comparison_promotion_gate_passed": dict(
                fixed_set_comparison.get("promotion_gate") or {}
            ).get("passed"),
        }
    )
    quality_summary["metrics_snapshot"] = metrics_snapshot
    quality_summary["credible_research_evidence"] = bool(alpha_card.get("credible_research_evidence"))
    if fixed_set_comparison:
        quality_summary["research_gate"] = {
            "fixed_set_comparison": dict(fixed_set_comparison.get("research_gate") or {}),
        }
    validation_report["quality_summary"] = quality_summary
    write_json(validation_report_path, validation_report)
    write_json(alpha_card_path, alpha_card)
    if validation_report.get("statistical_falsification") or alpha_card.get("statistical_falsification"):
        write_json(
            statistical_falsification_path,
            dict(
                validation_report.get("statistical_falsification")
                or alpha_card.get("statistical_falsification")
                or {}
            ),
        )
    if validation_report.get("alpha_experiment_card") or alpha_card.get("alpha_experiment_card"):
        write_json(
            alpha_experiment_card_path,
            dict(
                validation_report.get("alpha_experiment_card")
                or alpha_card.get("alpha_experiment_card")
                or {}
            ),
        )
    alpha_card_md_path.write_text(_alpha_card_markdown(alpha_card) + "\n", encoding="utf-8")
    return {
        "experiment_spec_path": str(experiment_spec_path),
        "backtest_report_path": str(backtest_report_path),
        "validation_report_path": str(validation_report_path),
        "alpha_card_path": str(alpha_card_path),
        "alpha_card_md_path": str(alpha_card_md_path),
        "statistical_falsification_report_path": str(statistical_falsification_path) if statistical_falsification_path.exists() else "",
        "alpha_experiment_card_path": str(alpha_experiment_card_path) if alpha_experiment_card_path.exists() else "",
    }


def _overlap_contract_fields(
    *,
    split_realization_contract: dict[str, Any] | None = None,
    label_horizon_bars: int | None = None,
    bar_interval_ms: int | None = None,
    overlap_integrity: dict[str, Any],
) -> dict[str, Any]:
    resolved_split_realization_contract: dict[str, Any] | None = None
    if split_realization_contract is not None:
        resolved_split_realization_contract = resolve_split_realization_contract(contract=split_realization_contract)
    elif label_horizon_bars is not None or bar_interval_ms is not None:
        shape = "single_asset" if int(label_horizon_bars or 0) > 1 else "cross_sectional"
        resolved_split_realization_contract = build_split_realization_contract(
            shape=shape,
            bar_interval_ms=int(bar_interval_ms or 0),
        )
        if label_horizon_bars is not None:
            resolved_split_realization_contract["target_horizon_bars"] = int(label_horizon_bars)
            resolved_split_realization_contract["realization_step_bars"] = int(
                dict(overlap_integrity.get("backtest_horizon_mismatch") or {}).get("evaluation_step_bars")
                or label_horizon_bars
            )
            resolved_split_realization_contract["partition_gap_bars"] = int(
                overlap_integrity.get("purge_gap_bars") or label_horizon_bars
            )
            resolved_split_realization_contract["skipped_between_partitions_bars"] = max(
                int(resolved_split_realization_contract["partition_gap_bars"]) - 1,
                0,
            )
    effective_label_horizon_bars = (
        int(resolved_split_realization_contract["target_horizon_bars"])
        if resolved_split_realization_contract is not None
        else label_horizon_bars
    )
    effective_bar_interval_ms = (
        int(resolved_split_realization_contract["bar_interval_ms"])
        if resolved_split_realization_contract is not None
        else bar_interval_ms
    )
    fields = {
        "label_horizon_bars": effective_label_horizon_bars,
        "realization_step_bars": (
            int(resolved_split_realization_contract["realization_step_bars"])
            if resolved_split_realization_contract is not None
            else dict(overlap_integrity.get("backtest_horizon_mismatch") or {}).get("evaluation_step_bars")
        ),
        "partition_gap_bars": (
            int(resolved_split_realization_contract["partition_gap_bars"])
            if resolved_split_realization_contract is not None
            else overlap_integrity.get("purge_gap_bars")
        ),
        "bar_interval_ms": effective_bar_interval_ms,
        "split_boundary_contamination_counts": dict(overlap_integrity.get("split_boundary_contamination_counts") or {}),
        "label_split_overlap": overlap_integrity.get("label_split_overlap"),
        "backtest_horizon_mismatch": dict(overlap_integrity.get("backtest_horizon_mismatch") or {}),
        "backtest_realization_mismatch": dict(
            overlap_integrity.get("backtest_realization_mismatch")
            or overlap_integrity.get("backtest_horizon_mismatch")
            or {}
        ),
    }
    if resolved_split_realization_contract is not None and split_realization_contract is not None:
        fields["split_realization_contract"] = resolved_split_realization_contract
    return fields


def _canonical_quant_artifacts_root(experiment_root: Path) -> Path:
    for candidate in (experiment_root, *experiment_root.parents):
        if candidate.name == "quant_research":
            return candidate
    return experiment_root.parents[1]
