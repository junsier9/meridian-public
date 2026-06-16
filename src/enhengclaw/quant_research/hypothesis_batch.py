from __future__ import annotations

from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import required_source_commit_sha, with_evidence_metadata

from .contracts import (
    QuantUniverseCandidate,
    portable_path,
    read_json,
    sha256_canonical_json,
    utc_now,
    write_json,
)
from .data_readiness import (
    CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE,
    load_data_readiness_contract,
    normalize_dataset_profile,
    resolve_default_spot_ohlcv_external_root,
)
from .deterministic_core import feature_group_for_column, select_feature_columns
from .execution_backtest import filter_cross_sectional_execution_frame
from .feature_admission import feature_admission_status
from .features import (
    DEFAULT_LABEL_CONTRACT_ID,
    EXECUTION_ALIGNED_LABEL_CONTRACT_ID,
)
from .lab import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    WORKBENCH_ROOT,
    _apply_spot_gap_backfill_for_cross_sectional_profiles,
    _apply_universe_filter,
    _backtest_cross_sectional,
    _build_factor_evidence_section,
    _chronological_split,
    _execution_cost_model_data_gap_blockers,
    _fit_and_score,
    _initial_data_gap_blockers,
    _resolved_execution_cost_models,
    _run_walk_forward,
    build_quant_datasets,
    build_quant_feature_sets,
    load_quant_universe_snapshot,
    require_derivatives_sync_summary,
    run_quant_experiments_for_strategies,
)
from .validation_contract import (
    build_regime_holdout_section,
    build_walk_forward_assessment,
    execution_capacity_limits,
    load_validation_contract,
    validation_contract_reference_capital_usd,
)


ROOT = Path(__file__).resolve().parents[3]
FAST_REJECT_CONTRACT_VERSION = "quant_fast_reject_contract.v2"
FROZEN_BENCHMARK_MANIFEST_PATH = Path(__file__).with_name("cross_sectional_hypothesis_batch_manifest_v35.json")
FROZEN_BENCHMARK_SOURCE = "hypothesis_batch_manifest_v35"
FROZEN_BENCHMARK_CANDIDATE_IDS = ("xs_pair_spread_book_v8_h5d",)
HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION = "quant_cross_sectional_hypothesis_batch_manifest.v97"
FAST_REJECT_REPORT_CONTRACT_VERSION = "quant_cross_sectional_fast_reject_report.v97"
STRICT_CANDIDATE_LIST_CONTRACT_VERSION = "quant_cross_sectional_strict_candidate_list.v97"
STRICT_RESULT_CONTRACT_VERSION = "quant_cross_sectional_strict_result.v97"
BATCH_SUMMARY_CONTRACT_VERSION = "quant_cross_sectional_hypothesis_batch_cycle.v97"
HYPOTHESIS_BATCH_MANIFEST_PATH = Path(__file__).with_name("cross_sectional_hypothesis_batch_manifest_v97.json")
FAST_REJECT_CONTRACT_PATH = ROOT / "config" / "quant_research" / "fast_reject_contract.json"
HYPOTHESIS_BATCH_SOURCE = "hypothesis_batch_manifest_v97"
HYPOTHESIS_RESEARCH_LANE = "hypothesis_factor"
HYPOTHESIS_SELECTION_LANE = "hypothesis_batch"
HYPOTHESIS_PROMOTION_STATE = "shadow_only"
HYPOTHESIS_BATCH_DATASET_PROFILE = CROSS_SECTIONAL_DAILY_4H_DATASET_PROFILE
HYPOTHESIS_BATCH_FEATURE_SET_VERSION = "v91"
HYPOTHESIS_BATCH_ALLOWED_LABEL_CONTRACT_IDS = (
    DEFAULT_LABEL_CONTRACT_ID,
    EXECUTION_ALIGNED_LABEL_CONTRACT_ID,
)
EXPECTED_BASE_MECHANISM_IDS = (
    "xs_minimal_v12",
)
EXPECTED_HORIZON_SPECS = (
    ("h5d", 5),
)
EXPECTED_HORIZON_MAP = dict(EXPECTED_HORIZON_SPECS)
LITE_BLOCKER_FACTOR = "factor_evidence_lite_failed"
LITE_BLOCKER_WALK_FORWARD = "walk_forward_assessment_lite_failed"
LITE_BLOCKER_REGIME = "regime_holdout_lite_failed"
LITE_ADVISORY_REGIME = "regime_holdout_lite_advisory"


def _expected_candidate_ids() -> tuple[str, ...]:
    return tuple(
        f"{base_mechanism_id}_{horizon_id}"
        for base_mechanism_id in EXPECTED_BASE_MECHANISM_IDS
        for horizon_id, _ in EXPECTED_HORIZON_SPECS
    )


EXPECTED_CANDIDATE_IDS = _expected_candidate_ids()
HYPOTHESIS_BATCH_TARGET_HORIZONS = tuple(int(bars) for _, bars in EXPECTED_HORIZON_SPECS)


def load_fast_reject_contract(*, path: Path | None = None) -> dict[str, Any]:
    contract_path = (path or FAST_REJECT_CONTRACT_PATH).expanduser().resolve()
    payload = dict(read_json(contract_path))
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != FAST_REJECT_CONTRACT_VERSION:
        raise ValueError(
            "fast reject contract contract_version mismatch: "
            f"{contract_version or 'missing'}"
        )
    forbidden_sections = {
        "alpha_card",
        "falsification_audit",
        "publication_assessment",
        "execution_stress",
        "validation_contract",
    }
    if forbidden_sections.intersection(payload):
        raise ValueError("fast reject contract must not define strict-only sections")
    for section_name in ("factor_evidence_lite", "walk_forward_assessment_lite", "regime_holdout_lite"):
        if not isinstance(payload.get(section_name), dict):
            raise ValueError(f"fast reject contract missing section: {section_name}")
    return {
        "path": str(contract_path),
        "contract_version": contract_version,
        "factor_evidence_lite": dict(payload.get("factor_evidence_lite") or {}),
        "walk_forward_assessment_lite": dict(payload.get("walk_forward_assessment_lite") or {}),
        "regime_holdout_lite": dict(payload.get("regime_holdout_lite") or {}),
    }


def load_cross_sectional_hypothesis_batch_manifest(*, path: Path | None = None) -> dict[str, Any]:
    manifest_path = (path or HYPOTHESIS_BATCH_MANIFEST_PATH).expanduser().resolve()
    payload = dict(read_json(manifest_path))
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != HYPOTHESIS_BATCH_MANIFEST_CONTRACT_VERSION:
        raise ValueError(
            "hypothesis batch manifest contract_version mismatch: "
            f"{contract_version or 'missing'}"
        )
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("hypothesis batch manifest entries must be a list")
    normalized_entries = [_normalize_hypothesis_candidate_entry(entry, index=index) for index, entry in enumerate(raw_entries)]
    observed_ids = {str(item["candidate_id"]) for item in normalized_entries}
    if observed_ids != set(_expected_candidate_ids()):
        raise ValueError(
            "hypothesis batch manifest candidate_id set mismatch: "
            f"{sorted(observed_ids)}"
        )
    return {
        "path": str(manifest_path),
        "contract_version": contract_version,
        "entries": normalized_entries,
    }


def _normalize_hypothesis_candidate_entry(entry: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"hypothesis batch entry {index} must be an object")
    candidate_id = str(entry.get("candidate_id") or "").strip()
    shape = str(entry.get("shape") or "").strip()
    base_mechanism_id = str(entry.get("base_mechanism_id") or "").strip()
    horizon_id = str(entry.get("horizon_id") or "").strip()
    target_horizon_bars = int(entry.get("target_horizon_bars") or 0)
    label_contract_id = str(entry.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID).strip() or DEFAULT_LABEL_CONTRACT_ID
    dataset_profile = normalize_dataset_profile(
        shape=shape,
        dataset_profile=str(entry.get("dataset_profile") or "").strip() or None,
    )
    model_family = str(entry.get("model_family") or "").strip()
    strategy_profile = str(entry.get("strategy_profile") or "").strip()
    if not candidate_id or not shape or not model_family or not strategy_profile or not base_mechanism_id or not horizon_id:
        raise ValueError(f"hypothesis batch entry {index} missing required fields")
    if shape != "cross_sectional":
        raise ValueError(f"hypothesis batch entry {candidate_id} must be cross_sectional")
    if dataset_profile != HYPOTHESIS_BATCH_DATASET_PROFILE:
        raise ValueError(
            f"hypothesis batch entry {candidate_id} must use dataset_profile={HYPOTHESIS_BATCH_DATASET_PROFILE}"
        )
    expected_candidate_id = f"{base_mechanism_id}_{horizon_id}"
    if candidate_id != expected_candidate_id:
        raise ValueError(
            f"hypothesis batch entry {candidate_id} candidate_id must equal {expected_candidate_id}"
        )
    if horizon_id not in EXPECTED_HORIZON_MAP:
        raise ValueError(f"hypothesis batch entry {candidate_id} horizon_id is unsupported")
    if target_horizon_bars != int(EXPECTED_HORIZON_MAP[horizon_id]):
        raise ValueError(
            f"hypothesis batch entry {candidate_id} target_horizon_bars must equal {EXPECTED_HORIZON_MAP[horizon_id]}"
        )
    if base_mechanism_id not in EXPECTED_BASE_MECHANISM_IDS:
        raise ValueError(f"hypothesis batch entry {candidate_id} base_mechanism_id is unsupported")
    if label_contract_id not in HYPOTHESIS_BATCH_ALLOWED_LABEL_CONTRACT_IDS:
        raise ValueError(
            f"hypothesis batch entry {candidate_id} must use one of "
            f"{sorted(HYPOTHESIS_BATCH_ALLOWED_LABEL_CONTRACT_IDS)}"
        )
    feature_groups = [
        str(item).strip()
        for item in list(entry.get("feature_groups") or [])
        if str(item).strip()
    ]
    required_feature_columns = [
        str(item).strip()
        for item in list(entry.get("required_feature_columns") or [])
        if str(item).strip()
    ]
    if not feature_groups or not required_feature_columns:
        raise ValueError(f"hypothesis batch entry {candidate_id} must define feature groups and required columns")
    invalid_required_columns = [
        column
        for column in required_feature_columns
        if feature_group_for_column(column) not in set(feature_groups)
    ]
    if invalid_required_columns:
        raise ValueError(
            f"hypothesis batch entry {candidate_id} required_feature_columns are not covered by feature_groups: "
            f"{invalid_required_columns}"
        )
    disallowed_required_columns = [
        column
        for column in required_feature_columns
        if feature_admission_status(column) != "admitted"
    ]
    if disallowed_required_columns:
        raise ValueError(
            f"hypothesis batch entry {candidate_id} required_feature_columns are not admitted: "
            f"{disallowed_required_columns}"
        )
    profile_constraints = _normalize_profile_constraints(
        candidate_id=candidate_id,
        model_family=model_family,
        profile_constraints=dict(entry.get("profile_constraints") or {}),
    )
    thesis_profile = dict(entry.get("thesis_profile") or {})
    thesis_required_columns = [
        str(item).strip()
        for item in list(thesis_profile.get("required_feature_columns") or [])
        if str(item).strip()
    ]
    if thesis_required_columns != required_feature_columns:
        raise ValueError(
            f"hypothesis batch entry {candidate_id} thesis_profile.required_feature_columns mismatch"
        )
    requires_derivatives_features = bool(
        "derivatives" in set(feature_groups)
        or thesis_profile.get("requires_derivatives_features")
    )
    expected_spec_hash = _compute_hypothesis_candidate_spec_hash(
        candidate_id=candidate_id,
        base_mechanism_id=base_mechanism_id,
        horizon_id=horizon_id,
        target_horizon_bars=target_horizon_bars,
        label_contract_id=label_contract_id,
        shape=shape,
        dataset_profile=dataset_profile,
        strategy_profile=strategy_profile,
        universe_filter=dict(entry.get("universe_filter") or {}),
        model_family=model_family,
        feature_groups=feature_groups,
        required_feature_columns=required_feature_columns,
        requires_derivatives_features=requires_derivatives_features,
        profile_constraints=profile_constraints,
        thesis_profile=thesis_profile,
    )
    observed_spec_hash = str(entry.get("spec_hash") or "").strip()
    if observed_spec_hash != expected_spec_hash:
        raise ValueError(
            f"hypothesis batch entry {candidate_id} spec_hash mismatch: "
            f"{observed_spec_hash or 'missing'} != {expected_spec_hash}"
        )
    return {
        "candidate_id": candidate_id,
        "base_mechanism_id": base_mechanism_id,
        "horizon_id": horizon_id,
        "target_horizon_bars": target_horizon_bars,
        "label_contract_id": label_contract_id,
        "enabled": bool(entry.get("enabled", True)),
        "shape": shape,
        "dataset_profile": dataset_profile,
        "model_family": model_family,
        "strategy_profile": strategy_profile,
        "feature_selection_mode": str(entry.get("feature_selection_mode") or "").strip().lower(),
        "include_required_feature_columns_in_selection": bool(
            entry.get("include_required_feature_columns_in_selection")
        ),
        "feature_groups": feature_groups,
        "required_feature_columns": required_feature_columns,
        "requires_derivatives_features": requires_derivatives_features,
        "profile_constraints": profile_constraints,
        "universe_filter": dict(entry.get("universe_filter") or {}),
        "thesis_profile": thesis_profile,
        "spec_hash": expected_spec_hash,
    }


def _normalize_profile_constraints(
    *,
    candidate_id: str,
    model_family: str,
    profile_constraints: dict[str, Any],
) -> dict[str, Any]:
    allowed_buckets = sorted(
        {
            str(item).strip()
            for item in list(profile_constraints.get("allowed_liquidity_buckets") or [])
            if str(item).strip()
        }
    )
    if not allowed_buckets:
        raise ValueError(f"hypothesis batch entry {candidate_id} must define allowed_liquidity_buckets")
    normalized = {
        "allowed_liquidity_buckets": allowed_buckets,
        "spot_only": bool(profile_constraints.get("spot_only", False)),
        "long_only": bool(profile_constraints.get("long_only", False)),
        "short_allowed": bool(profile_constraints.get("short_allowed", False)),
        "execution_venue": str(profile_constraints.get("execution_venue") or "").strip().lower(),
        "max_gross_leverage": float(profile_constraints.get("max_gross_leverage", 1.0) or 1.0),
        "long_leverage": float(profile_constraints.get("long_leverage", 1.0) or 1.0),
        "short_leverage": float(profile_constraints.get("short_leverage", 0.0) or 0.0),
        "max_turnover_per_rebalance": float(profile_constraints.get("max_turnover_per_rebalance", 1.0) or 1.0),
    }
    # v93: preserve optional portfolio-level multiplier overlay id (passed to execution_backtest._cross_sectional_period)
    overlay_id = str(profile_constraints.get("position_multiplier_overlay_id") or "").strip()
    if overlay_id:
        normalized["position_multiplier_overlay_id"] = overlay_id
    short_multiplier_column = str(profile_constraints.get("short_position_weight_multiplier_column") or "").strip()
    if short_multiplier_column:
        normalized["short_position_weight_multiplier_column"] = short_multiplier_column
    # W2-A (alpha ontology, 2026-04-29): preserve top-K / bottom-K count overrides for
    # cross-sectional default portfolio construction. Defaults stay at 3 long / 2 short.
    # Wider K is the §H.2 W2-A path for breaking BTC/ETH/PAXG capacity binding.
    if "top_long_count" in profile_constraints:
        normalized["top_long_count"] = max(int(profile_constraints.get("top_long_count") or 0), 0)
    if "bottom_short_count" in profile_constraints:
        normalized["bottom_short_count"] = max(int(profile_constraints.get("bottom_short_count") or 0), 0)
    # v100 (Phase 2d): preserve drawdown-conditional throttle params for cross-period DD tracking
    if profile_constraints.get("drawdown_throttle_enabled"):
        normalized["drawdown_throttle_enabled"] = bool(profile_constraints.get("drawdown_throttle_enabled"))
        normalized["dd_throttle_window_days"] = int(profile_constraints.get("dd_throttle_window_days", 30) or 30)
        normalized["dd_throttle_5pct_threshold"] = float(profile_constraints.get("dd_throttle_5pct_threshold", 0.05) or 0.05)
        normalized["dd_throttle_10pct_threshold"] = float(profile_constraints.get("dd_throttle_10pct_threshold", 0.10) or 0.10)
        normalized["dd_throttle_5pct_multiplier"] = float(profile_constraints.get("dd_throttle_5pct_multiplier", 0.5) or 0.5)
        normalized["dd_throttle_10pct_multiplier"] = float(profile_constraints.get("dd_throttle_10pct_multiplier", 0.0) or 0.0)
    if str(model_family).strip() in {"xs_pair_spread_book_v1", "xs_pair_spread_book_v2", "xs_pair_spread_book_v3", "xs_pair_spread_book_v4", "xs_pair_spread_book_v5", "xs_pair_spread_book_v6", "xs_pair_spread_book_v7", "xs_pair_spread_book_v8", "xs_pair_spread_book_v9", "xs_pair_spread_book_v10", "xs_pair_spread_book_v11", "xs_pair_spread_book_v12", "xs_pair_spread_book_v16", "xs_pair_spread_book_v17", "xs_pair_spread_book_v18", "xs_pair_spread_book_v19", "xs_pair_spread_book_v20", "xs_pair_spread_book_v21", "xs_pair_spread_book_v22", "xs_pair_spread_book_v23", "xs_pair_spread_book_v24"}:
        normalized["pair_construction"] = str(profile_constraints.get("pair_construction") or "").strip().lower()
        normalized["pair_bucket_count"] = int(profile_constraints.get("pair_bucket_count", 4) or 4)
        normalized["pair_count"] = int(profile_constraints.get("pair_count", 2) or 2)
        normalized["pair_score_spread_min"] = float(profile_constraints.get("pair_score_spread_min", 0.08) or 0.08)
        normalized["pair_quality_floor"] = float(profile_constraints.get("pair_quality_floor", 0.35) or 0.35)
        if "pair_turnover_mode" in profile_constraints:
            normalized["pair_turnover_mode"] = str(profile_constraints.get("pair_turnover_mode") or "").strip().lower()
        if "pair_trend_crowding_max" in profile_constraints:
            normalized["pair_trend_crowding_max"] = float(profile_constraints.get("pair_trend_crowding_max") or 0.0)
        if "pair_strength_soft_cap" in profile_constraints:
            normalized["pair_strength_soft_cap"] = float(profile_constraints.get("pair_strength_soft_cap") or 0.0)
        if "pair_additional_strength_ratio_min" in profile_constraints:
            normalized["pair_additional_strength_ratio_min"] = float(
                profile_constraints.get("pair_additional_strength_ratio_min") or 0.0
            )
        if "pair_switch_strength_ratio_min" in profile_constraints:
            normalized["pair_switch_strength_ratio_min"] = float(
                profile_constraints.get("pair_switch_strength_ratio_min") or 0.0
            )
        if "pair_market_momentum_soft_threshold" in profile_constraints:
            normalized["pair_market_momentum_soft_threshold"] = float(
                profile_constraints.get("pair_market_momentum_soft_threshold") or 0.0
            )
        if "pair_market_ema_soft_threshold" in profile_constraints:
            normalized["pair_market_ema_soft_threshold"] = float(
                profile_constraints.get("pair_market_ema_soft_threshold") or 0.0
            )
        if "pair_market_trend_short_scale" in profile_constraints:
            normalized["pair_market_trend_short_scale"] = float(
                profile_constraints.get("pair_market_trend_short_scale") or 0.0
            )
        if "pair_trend_crowding_soft_threshold" in profile_constraints:
            normalized["pair_trend_crowding_soft_threshold"] = float(
                profile_constraints.get("pair_trend_crowding_soft_threshold") or 0.0
            )
        if "pair_trend_crowding_soft_scale" in profile_constraints:
            normalized["pair_trend_crowding_soft_scale"] = float(
                profile_constraints.get("pair_trend_crowding_soft_scale") or 0.0
            )
        if "pair_short_trend_crowding_soft_threshold" in profile_constraints:
            normalized["pair_short_trend_crowding_soft_threshold"] = float(
                profile_constraints.get("pair_short_trend_crowding_soft_threshold") or 0.0
            )
        if "pair_short_trend_crowding_soft_scale" in profile_constraints:
            normalized["pair_short_trend_crowding_soft_scale"] = float(
                profile_constraints.get("pair_short_trend_crowding_soft_scale") or 0.0
            )
        if "pair_short_quality_max" in profile_constraints:
            normalized["pair_short_quality_max"] = float(
                profile_constraints.get("pair_short_quality_max") or 0.0
            )
        if "pair_short_quality_soft_threshold" in profile_constraints:
            normalized["pair_short_quality_soft_threshold"] = float(
                profile_constraints.get("pair_short_quality_soft_threshold") or 0.0
            )
        if "pair_short_quality_soft_scale" in profile_constraints:
            normalized["pair_short_quality_soft_scale"] = float(
                profile_constraints.get("pair_short_quality_soft_scale") or 0.0
            )
        if "pair_quality_balance_soft_floor" in profile_constraints:
            normalized["pair_quality_balance_soft_floor"] = float(
                profile_constraints.get("pair_quality_balance_soft_floor") or 0.0
            )
        if "pair_quality_balance_soft_scale" in profile_constraints:
            normalized["pair_quality_balance_soft_scale"] = float(
                profile_constraints.get("pair_quality_balance_soft_scale") or 0.0
            )
        expected = {
            "spot_only": False,
            "long_only": False,
            "short_allowed": True,
            "execution_venue": "perp",
            "max_gross_leverage": 1.0,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "pair_construction": "quality_bucket_pairs",
        }
        for field_name, expected_value in expected.items():
            if normalized[field_name] != expected_value:
                raise ValueError(
                    f"hypothesis batch entry {candidate_id} profile_constraints.{field_name} must equal {expected_value!r}"
                )
        if not (0.0 < normalized["max_turnover_per_rebalance"] <= 1.0):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.max_turnover_per_rebalance "
                "must be within (0.0, 1.0]"
            )
        if normalized["pair_bucket_count"] not in {3, 4}:
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_bucket_count "
                "must be 3 or 4"
            )
        if normalized["pair_count"] not in {1, 2}:
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_count must be 1 or 2"
            )
        if normalized["pair_count"] > normalized["pair_bucket_count"]:
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_count "
                "must not exceed pair_bucket_count"
            )
        if not (0.08 <= normalized["pair_score_spread_min"] <= 0.20):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_score_spread_min "
                "must be within [0.08, 0.20]"
            )
        if not (0.35 <= normalized["pair_quality_floor"] <= 0.60):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_quality_floor "
                "must be within [0.35, 0.60]"
            )
        if "pair_turnover_mode" in normalized and normalized["pair_turnover_mode"] not in {"exit_first", "pair_hold", "pair_project"}:
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_turnover_mode "
                "must equal 'exit_first', 'pair_hold', or 'pair_project'"
            )
        if "pair_trend_crowding_max" in normalized and not (0.80 <= normalized["pair_trend_crowding_max"] <= 0.95):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_trend_crowding_max "
                "must be within [0.80, 0.95]"
            )
        if "pair_strength_soft_cap" in normalized:
            if not (0.12 <= normalized["pair_strength_soft_cap"] <= 0.30):
                raise ValueError(
                    f"hypothesis batch entry {candidate_id} profile_constraints.pair_strength_soft_cap "
                    "must be within [0.12, 0.30]"
                )
            if normalized["pair_strength_soft_cap"] < normalized["pair_score_spread_min"]:
                raise ValueError(
                    f"hypothesis batch entry {candidate_id} profile_constraints.pair_strength_soft_cap "
                    "must be >= pair_score_spread_min"
                )
        if "pair_trend_crowding_soft_threshold" in normalized and not (
            0.80 <= normalized["pair_trend_crowding_soft_threshold"] <= 0.95
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_trend_crowding_soft_threshold "
                "must be within [0.80, 0.95]"
            )
        if "pair_trend_crowding_soft_scale" in normalized and not (
            0.50 <= normalized["pair_trend_crowding_soft_scale"] < 1.0
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_trend_crowding_soft_scale "
                "must be within [0.50, 1.00)"
            )
        if "pair_short_trend_crowding_soft_threshold" in normalized and not (
            0.70 <= normalized["pair_short_trend_crowding_soft_threshold"] <= 0.95
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_short_trend_crowding_soft_threshold "
                "must be within [0.70, 0.95]"
            )
        if "pair_short_trend_crowding_soft_scale" in normalized and not (
            0.50 <= normalized["pair_short_trend_crowding_soft_scale"] < 1.0
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_short_trend_crowding_soft_scale "
                "must be within [0.50, 1.00)"
            )
        if "pair_short_quality_max" in normalized and not (
            0.70 <= normalized["pair_short_quality_max"] <= 0.95
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_short_quality_max "
                "must be within [0.70, 0.95]"
            )
        if "pair_short_quality_soft_threshold" in normalized and not (
            0.70 <= normalized["pair_short_quality_soft_threshold"] <= 0.95
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_short_quality_soft_threshold "
                "must be within [0.70, 0.95]"
            )
        if "pair_short_quality_soft_scale" in normalized and not (
            0.50 <= normalized["pair_short_quality_soft_scale"] < 1.0
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_short_quality_soft_scale "
                "must be within [0.50, 1.00)"
            )
        if "pair_additional_strength_ratio_min" in normalized and not (
            0.50 <= normalized["pair_additional_strength_ratio_min"] <= 1.0
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_additional_strength_ratio_min "
                "must be within [0.50, 1.00]"
            )
        if "pair_switch_strength_ratio_min" in normalized and not (
            1.00 <= normalized["pair_switch_strength_ratio_min"] <= 1.50
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_switch_strength_ratio_min "
                "must be within [1.00, 1.50]"
            )
        if "pair_market_momentum_soft_threshold" in normalized and not (
            -0.10 <= normalized["pair_market_momentum_soft_threshold"] <= 0.30
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_market_momentum_soft_threshold "
                "must be within [-0.10, 0.30]"
            )
        if "pair_market_ema_soft_threshold" in normalized and not (
            -0.05 <= normalized["pair_market_ema_soft_threshold"] <= 0.15
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_market_ema_soft_threshold "
                "must be within [-0.05, 0.15]"
            )
        if "pair_market_trend_short_scale" in normalized and not (
            0.50 <= normalized["pair_market_trend_short_scale"] < 1.0
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_market_trend_short_scale "
                "must be within [0.50, 1.00)"
            )
        if "pair_quality_balance_soft_floor" in normalized and not (
            0.60 <= normalized["pair_quality_balance_soft_floor"] <= 0.95
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_quality_balance_soft_floor "
                "must be within [0.60, 0.95]"
            )
        if "pair_quality_balance_soft_scale" in normalized and not (
            0.50 <= normalized["pair_quality_balance_soft_scale"] < 1.0
        ):
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.pair_quality_balance_soft_scale "
                "must be within [0.50, 1.00)"
            )
        return normalized
    if normalized["long_only"]:
        expected = {
            "spot_only": True,
            "long_only": True,
            "short_allowed": False,
            "execution_venue": "",
            "max_gross_leverage": 1.0,
            "long_leverage": 1.0,
            "short_leverage": 0.0,
            "max_turnover_per_rebalance": 1.0,
        }
    else:
        # W2-A long-short variant (alpha-ontology lsk* family). Perp execution
        # required because spot does not natively support shorting. Symmetric
        # leverage 0.5 long + 0.5 short (gross 1.0, net 0.0). Drives
        # beta-neutral construction; addresses cycle blocker #3 (regime sharpe
        # noise) and #4 (capacity binding) per threshold_provenance.md
        # "W2-A iteration 1" entry. See doc §H.2 W2-A.
        expected = {
            "spot_only": False,
            "long_only": False,
            "short_allowed": True,
            "execution_venue": "perp",
            "max_gross_leverage": 1.0,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "max_turnover_per_rebalance": 1.0,
        }
    for field_name, expected_value in expected.items():
        if normalized[field_name] != expected_value:
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.{field_name} must equal {expected_value!r}"
            )
    pair_construction_value = str(profile_constraints.get("pair_construction") or "").strip().lower()
    if pair_construction_value == "inverse_vol_weighted_long_only":
        normalized["pair_construction"] = pair_construction_value
        normalized["top_long_count"] = int(profile_constraints.get("top_long_count", 5) or 5)
        normalized["inverse_vol_column"] = str(
            profile_constraints.get("inverse_vol_column", "realized_volatility_20")
            or "realized_volatility_20"
        ).strip()
        normalized["inverse_vol_floor"] = float(
            profile_constraints.get("inverse_vol_floor", 0.005) or 0.005
        )
        if normalized["top_long_count"] < 1 or normalized["top_long_count"] > 20:
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.top_long_count "
                "must be within [1, 20]"
            )
        if normalized["inverse_vol_floor"] <= 0.0:
            raise ValueError(
                f"hypothesis batch entry {candidate_id} profile_constraints.inverse_vol_floor "
                "must be > 0"
            )
    return normalized


def _compute_hypothesis_candidate_spec_hash(
    *,
    candidate_id: str,
    base_mechanism_id: str,
    horizon_id: str,
    target_horizon_bars: int,
    label_contract_id: str,
    shape: str,
    dataset_profile: str,
    strategy_profile: str,
    universe_filter: dict[str, Any],
    model_family: str,
    feature_groups: list[str],
    required_feature_columns: list[str],
    requires_derivatives_features: bool,
    profile_constraints: dict[str, Any],
    thesis_profile: dict[str, Any],
) -> str:
    return sha256_canonical_json(
        {
            "candidate_id": candidate_id,
            "base_mechanism_id": base_mechanism_id,
            "horizon_id": horizon_id,
            "target_horizon_bars": int(target_horizon_bars),
            "label_contract_id": str(label_contract_id or DEFAULT_LABEL_CONTRACT_ID),
            "shape": shape,
            "dataset_profile": dataset_profile,
            "strategy_profile": strategy_profile,
            "universe_filter": dict(universe_filter),
            "model_family": model_family,
            "feature_groups": list(feature_groups),
            "required_feature_columns": list(required_feature_columns),
            "requires_derivatives_features": bool(requires_derivatives_features),
            "profile_constraints": dict(profile_constraints),
            "thesis_profile": dict(thesis_profile),
        }
    )


def _materialize_strict_strategy_entry(candidate_entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": str(candidate_entry["candidate_id"]),
        "candidate_id": str(candidate_entry["candidate_id"]),
        "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
        "horizon_id": str(candidate_entry["horizon_id"]),
        "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
        "label_contract_id": str(candidate_entry.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID),
        "shape": "cross_sectional",
        "dataset_profile": HYPOTHESIS_BATCH_DATASET_PROFILE,
        "subject": None,
        "universe_filter": dict(candidate_entry.get("universe_filter") or {}),
        "model_family": str(candidate_entry["model_family"]),
        "strategy_profile": str(candidate_entry["strategy_profile"]),
        "feature_selection_mode": str(candidate_entry.get("feature_selection_mode") or "").strip().lower(),
        "include_required_feature_columns_in_selection": bool(
            candidate_entry.get("include_required_feature_columns_in_selection")
        ),
        "feature_groups": list(candidate_entry.get("feature_groups") or []),
        "required_feature_columns": list(candidate_entry.get("required_feature_columns") or []),
        "profile_constraints": dict(candidate_entry.get("profile_constraints") or {}),
        "spec_hash": str(candidate_entry["spec_hash"]),
        "source": HYPOTHESIS_BATCH_SOURCE,
        "research_lane": HYPOTHESIS_RESEARCH_LANE,
        "selection_lane": HYPOTHESIS_SELECTION_LANE,
        "promotion_state": HYPOTHESIS_PROMOTION_STATE,
        "daily_executable": False,
        "family_id": str(candidate_entry["model_family"]),
        "feature_family_ids": [],
        "requires_derivatives_features": bool(candidate_entry.get("requires_derivatives_features")),
        "thesis_family": f"hypothesis_{candidate_entry['candidate_id']}",
        "thesis_profile": dict(candidate_entry.get("thesis_profile") or {}),
        "proposal_origin": HYPOTHESIS_BATCH_SOURCE,
        "search_action": "mechanism_batch",
        "registry_snapshot_id": None,
        "published_via": "not_published",
        "model_overlay_ready": False,
        "lifecycle": "active",
        "monitoring_status": "shadow_only",
    }


def run_quant_hypothesis_batch_cycle(
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
    auto_api_gap_backfill: bool = True,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    resolved_spot_ohlcv_external_root = (
        resolve_default_spot_ohlcv_external_root(
            spot_ohlcv_external_root=spot_ohlcv_external_root,
        )
        if auto_detect_spot_ohlcv_external_root
        else (None if spot_ohlcv_external_root is None else Path(spot_ohlcv_external_root).expanduser().resolve())
    )
    cycle_root = resolved_artifacts_root / "hypothesis_batches" / as_of
    cycle_root.mkdir(parents=True, exist_ok=True)
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)

    universe_snapshot = load_quant_universe_snapshot(as_of=as_of, artifacts_root=resolved_artifacts_root)
    universe_candidates = tuple(
        QuantUniverseCandidate.from_payload(item)
        for item in list(universe_snapshot.get("candidates", []))
        if isinstance(item, dict)
    )
    derivatives_sync, derivatives_sync_summary_path = require_derivatives_sync_summary(
        as_of=as_of,
        derivatives_external_root=derivatives_external_root,
    )
    batch_manifest = load_cross_sectional_hypothesis_batch_manifest()
    enabled_entries = [dict(entry) for entry in batch_manifest["entries"] if bool(entry.get("enabled", True))]
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
        strategy_manifest={"entries": enabled_entries},
        datasets=datasets,
        universe_snapshot=universe_snapshot,
        universe_candidates=universe_candidates,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=resolved_spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
        auto_api_gap_backfill=auto_api_gap_backfill,
        strategy_id_allowlist=None,
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
    cross_sectional_daily_label_contract_ids = tuple(
        sorted(
            {
                str(entry.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID).strip() or DEFAULT_LABEL_CONTRACT_ID
                for entry in enabled_entries
            }
        )
    )
    feature_sets = build_quant_feature_sets(
        artifacts_root=resolved_artifacts_root,
        datasets=datasets,
        derivatives_sync=derivatives_sync,
        source_commit_sha=source_commit_sha,
        cross_sectional_daily_target_horizons=HYPOTHESIS_BATCH_TARGET_HORIZONS,
        cross_sectional_daily_label_contract_ids=cross_sectional_daily_label_contract_ids,
        feature_set_version=HYPOTHESIS_BATCH_FEATURE_SET_VERSION,
    )
    fast_reject_contract = load_fast_reject_contract()
    fast_reject_reports: list[dict[str, Any]] = []
    fast_reject_pass_entries: list[dict[str, Any]] = []
    for entry in enabled_entries:
        report = _run_fast_reject_candidate(
            as_of=as_of,
            batch_root=cycle_root,
            candidate_entry=entry,
            feature_sets=feature_sets,
            fast_reject_contract=fast_reject_contract,
            source_commit_sha=source_commit_sha,
        )
        fast_reject_reports.append(report)
        if bool(report.get("fast_reject_passed")):
            fast_reject_pass_entries.append(dict(entry))

    strict_experiments: list[dict[str, Any]] = []
    if fast_reject_pass_entries:
        strict_strategies = [
            _materialize_strict_strategy_entry(entry)
            for entry in fast_reject_pass_entries
        ]
        strict_experiments = run_quant_experiments_for_strategies(
            as_of=as_of,
            artifacts_root=resolved_artifacts_root,
            strategies=strict_strategies,
            feature_sets=feature_sets,
            compiler_backend=compiler_backend,
            source_commit_sha=source_commit_sha,
        )

    strict_results = _write_strict_results(
        as_of=as_of,
        batch_root=cycle_root,
        reports=fast_reject_reports,
        strict_experiments=strict_experiments,
        source_commit_sha=source_commit_sha,
    )
    strict_candidate_list = _write_strict_candidate_list(
        path=cycle_root / "strict_candidate_list.json",
        as_of=as_of,
        manifest=batch_manifest,
        strict_results=strict_results,
        source_commit_sha=source_commit_sha,
    )
    summary_payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "artifact_family": "quant_cross_sectional_hypothesis_batch_cycle",
        "contract_version": BATCH_SUMMARY_CONTRACT_VERSION,
        "compiler_backend": compiler_backend,
        "artifacts_root": str(resolved_artifacts_root),
        "quant_input_root": str(resolved_quant_input_root),
        "workbench_root": str(resolved_workbench_root),
        "batch_manifest_path": str(batch_manifest["path"]),
        "batch_manifest_contract_version": str(batch_manifest["contract_version"]),
        "fast_reject_contract_path": str(fast_reject_contract["path"]),
        "fast_reject_contract_version": str(fast_reject_contract["contract_version"]),
        "dataset_ids": [str(item["dataset_id"]) for item in datasets],
        "feature_set_ids": [str(item["feature_set_id"]) for item in feature_sets],
        "derivatives_sync_summary_path": str(derivatives_sync_summary_path),
        "spot_gap_backfill_summary_path": str(spot_gap_backfill_summary.get("summary_path") or ""),
        "candidate_count": len(enabled_entries),
        "candidate_ids": [str(item["candidate_id"]) for item in enabled_entries],
        "candidate_count_by_horizon": _count_entries_by_field(
            entries=enabled_entries,
            field_name="horizon_id",
        ),
        "fast_reject_pass_count": sum(1 for item in fast_reject_reports if bool(item.get("fast_reject_passed"))),
        "fast_reject_pass_candidate_ids": [
            str(item["candidate_id"])
            for item in fast_reject_reports
            if bool(item.get("fast_reject_passed"))
        ],
        "fast_reject_pass_count_by_horizon": _count_reports_by_field(
            reports=fast_reject_reports,
            field_name="horizon_id",
            require_fast_reject_passed=True,
        ),
        "fast_reject_pass_count_by_mechanism": _count_reports_by_field(
            reports=fast_reject_reports,
            field_name="base_mechanism_id",
            require_fast_reject_passed=True,
        ),
        "blocked_candidate_ids": [
            str(item["candidate_id"])
            for item in fast_reject_reports
            if str(item.get("status") or "") == "blocked"
        ],
        "strict_candidate_count": len(strict_results["strict_candidates"]),
        "strict_candidate_ids": [str(item["candidate_id"]) for item in strict_results["strict_candidates"]],
        "strict_survivor_count": len(strict_results["strict_survivors"]),
        "strict_survivor_ids": [str(item["candidate_id"]) for item in strict_results["strict_survivors"]],
        "strict_survivor_count_by_horizon": _count_entries_by_field(
            entries=strict_results["strict_survivors"],
            field_name="horizon_id",
        ),
        "strict_candidate_list_path": portable_path(Path(str(strict_candidate_list["path"])), repo_root=ROOT),
        "spot_gap_backfill_summary": {
            "attempted": bool(spot_gap_backfill_summary.get("attempted")),
            "status": str(spot_gap_backfill_summary.get("status") or "skipped"),
            "requested_profiles": list(spot_gap_backfill_summary.get("requested_profiles") or []),
            "requested_intervals": list(spot_gap_backfill_summary.get("requested_intervals") or []),
        },
    }
    summary_payload["summary_hash"] = sha256_canonical_json(
        {
            key: value
            for key, value in summary_payload.items()
            if key != "generated_at_utc"
        }
    )
    summary = _write_evidence(
        path=cycle_root / "batch_summary.json",
        payload=summary_payload,
        evidence_family="quant_cross_sectional_hypothesis_batch_cycle",
        contract_version=BATCH_SUMMARY_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )
    summary["summary_path"] = str(cycle_root / "batch_summary.json")
    return summary


def _run_fast_reject_candidate(
    *,
    as_of: str,
    batch_root: Path,
    candidate_entry: dict[str, Any],
    feature_sets: list[dict[str, Any]],
    fast_reject_contract: dict[str, Any],
    source_commit_sha: str,
) -> dict[str, Any]:
    family_root = batch_root / "families" / str(candidate_entry["candidate_id"])
    family_root.mkdir(parents=True, exist_ok=True)
    feature_set = _feature_set_for_candidate(
        feature_sets=feature_sets,
        candidate_entry=candidate_entry,
    )
    selected_feature_columns: list[str] = []
    dataset_manifest_path = ""
    feature_manifest_path = ""
    feature_set_id = ""
    split_realization_contract: dict[str, Any] = {}
    label_contract_id = str(candidate_entry.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID).strip() or DEFAULT_LABEL_CONTRACT_ID
    target_column = "target_up"
    forward_return_column = "target_forward_return"
    if feature_set is not None:
        selected_feature_columns = _select_candidate_feature_columns(
            candidate_entry=candidate_entry,
            numeric_feature_columns=list(feature_set.get("numeric_feature_columns") or []),
        )
        dataset_manifest_path = str(feature_set.get("dataset_manifest_path") or "").strip()
        feature_manifest_path = str(feature_set.get("manifest_path") or "").strip()
        feature_set_id = str(feature_set.get("feature_set_id") or "").strip()
        split_realization_contract = dict(feature_set.get("split_realization_contract") or {})
        label_contract_id = str(feature_set.get("label_contract_id") or label_contract_id).strip() or DEFAULT_LABEL_CONTRACT_ID
        target_column = str(feature_set.get("target_column") or target_column).strip() or "target_up"
        forward_return_column = str(feature_set.get("forward_return_column") or forward_return_column).strip() or "target_forward_return"
    if feature_set is None:
        return _write_fast_reject_report(
            path=family_root / "fast_reject_report.json",
            payload={
                "status": "blocked",
                "success": False,
                "as_of": as_of,
                "candidate_id": str(candidate_entry["candidate_id"]),
                "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
                "horizon_id": str(candidate_entry["horizon_id"]),
                "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
                "label_contract_id": label_contract_id,
                "dataset_profile": HYPOTHESIS_BATCH_DATASET_PROFILE,
                "feature_set_id": "",
                "split_realization_contract": {},
                "fast_reject_passed": False,
                "blocker_codes": ["missing_feature_set"],
            },
            source_commit_sha=source_commit_sha,
        )
    strategy_entry = _materialize_strict_strategy_entry(candidate_entry)
    constraints = dict(strategy_entry.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(strategy_entry.get("strategy_profile") or "")
    frame = _apply_universe_filter(
        feature_set["dataframe"],
        universe_filter=dict(strategy_entry.get("universe_filter") or {}),
    )
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    data_gap_blockers = _initial_data_gap_blockers(
        shape="cross_sectional",
        strategy_entry=strategy_entry,
        frame=frame,
        dataset_data_readiness=dict(feature_set.get("dataset_data_readiness") or {}),
        contract=load_data_readiness_contract(),
        subject_count_override=int(feature_set["dataframe"]["subject"].nunique()) if not feature_set["dataframe"].empty else 0,
    )
    if data_gap_blockers or frame.empty or len(frame) < 90:
        blocker_codes = list(data_gap_blockers) if data_gap_blockers else ["insufficient_rows"]
        return _write_fast_reject_report(
            path=family_root / "fast_reject_report.json",
            payload={
                "status": "blocked",
                "success": False,
                "as_of": as_of,
                "candidate_id": str(candidate_entry["candidate_id"]),
                "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
                "horizon_id": str(candidate_entry["horizon_id"]),
                "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
                "label_contract_id": label_contract_id,
                "dataset_profile": HYPOTHESIS_BATCH_DATASET_PROFILE,
                "feature_set_id": feature_set_id,
                "split_realization_contract": split_realization_contract,
                "target_column": target_column,
                "forward_return_column": forward_return_column,
                "selected_feature_columns": selected_feature_columns,
                "dataset_manifest_path": portable_path(Path(dataset_manifest_path), repo_root=ROOT) if dataset_manifest_path else "",
                "feature_manifest_path": portable_path(Path(feature_manifest_path), repo_root=ROOT) if feature_manifest_path else "",
                "fast_reject_passed": False,
                "blocker_codes": blocker_codes,
            },
            source_commit_sha=source_commit_sha,
        )
    resolved_split_realization_contract = dict(feature_set["split_realization_contract"])
    split = _chronological_split(
        frame,
        time_col="timestamp_ms",
        split_realization_contract=resolved_split_realization_contract,
    )
    if split is None:
        return _write_fast_reject_report(
            path=family_root / "fast_reject_report.json",
            payload={
                "status": "blocked",
                "success": False,
                "as_of": as_of,
                "candidate_id": str(candidate_entry["candidate_id"]),
                "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
                "horizon_id": str(candidate_entry["horizon_id"]),
                "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
                "label_contract_id": label_contract_id,
                "dataset_profile": HYPOTHESIS_BATCH_DATASET_PROFILE,
                "feature_set_id": feature_set_id,
                "split_realization_contract": split_realization_contract,
                "target_column": target_column,
                "forward_return_column": forward_return_column,
                "selected_feature_columns": selected_feature_columns,
                "dataset_manifest_path": portable_path(Path(dataset_manifest_path), repo_root=ROOT) if dataset_manifest_path else "",
                "feature_manifest_path": portable_path(Path(feature_manifest_path), repo_root=ROOT) if feature_manifest_path else "",
                "fast_reject_passed": False,
                "blocker_codes": ["unable_to_split"],
            },
            source_commit_sha=source_commit_sha,
        )
    train_df, validation_df, test_df = split
    prediction_bundle = _fit_and_score(
        model_family=str(candidate_entry["model_family"]),
        shape="cross_sectional",
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=selected_feature_columns,
        target_column=target_column,
    )
    validation_contract = load_validation_contract()
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(candidate_entry["strategy_profile"]),
        contract=validation_contract,
    )
    capacity_limits = execution_capacity_limits(validation_contract)
    base_execution_cost_model, stress_execution_cost_model = _resolved_execution_cost_models()
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
    walk_forward = _run_walk_forward(
        frame=frame,
        shape="cross_sectional",
        model_family=str(candidate_entry["model_family"]),
        feature_columns=selected_feature_columns,
        constraints=constraints,
        split_realization_contract=resolved_split_realization_contract,
        target_column=target_column,
        execution_cost_model=base_execution_cost_model,
        stress_execution_cost_model=stress_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        validation_contract=validation_contract,
    )
    execution_cost_model_data_gap_blockers = _execution_cost_model_data_gap_blockers(
        validation_metrics,
        test_metrics,
        walk_forward,
    )
    if execution_cost_model_data_gap_blockers:
        return _write_fast_reject_report(
            path=family_root / "fast_reject_report.json",
            payload={
                "status": "blocked",
                "success": False,
                "as_of": as_of,
                "candidate_id": str(candidate_entry["candidate_id"]),
                "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
                "horizon_id": str(candidate_entry["horizon_id"]),
                "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
                "label_contract_id": label_contract_id,
                "dataset_profile": HYPOTHESIS_BATCH_DATASET_PROFILE,
                "feature_set_id": feature_set_id,
                "split_realization_contract": split_realization_contract,
                "target_column": target_column,
                "forward_return_column": forward_return_column,
                "selected_feature_columns": selected_feature_columns,
                "dataset_manifest_path": portable_path(Path(dataset_manifest_path), repo_root=ROOT) if dataset_manifest_path else "",
                "feature_manifest_path": portable_path(Path(feature_manifest_path), repo_root=ROOT) if feature_manifest_path else "",
                "fast_reject_passed": False,
                "blocker_codes": execution_cost_model_data_gap_blockers,
            },
            source_commit_sha=source_commit_sha,
        )
    factor_evidence = _build_factor_evidence_section(
        prediction_frame=prediction_bundle["test"],
        test_metrics=test_metrics,
        thesis_profile=dict(candidate_entry["thesis_profile"]),
        selected_feature_columns=selected_feature_columns,
        strategy_entry=strategy_entry,
        forward_return_column=forward_return_column,
        label_contract_id=label_contract_id,
    )
    factor_evidence_lite = _build_factor_evidence_lite_section(
        factor_evidence=factor_evidence,
        contract=fast_reject_contract,
    )
    walk_forward_assessment_lite = build_walk_forward_assessment(
        walk_forward=walk_forward,
        contract={"walk_forward_assessment": dict(fast_reject_contract["walk_forward_assessment_lite"])},
    )
    regime_holdout_contract_section = dict(fast_reject_contract["regime_holdout_lite"])
    regime_holdout_mode = str(regime_holdout_contract_section.get("mode") or "blocker").strip().lower()
    regime_holdout_lite = build_regime_holdout_section(
        walk_forward=walk_forward,
        contract={"regime_holdout": regime_holdout_contract_section},
    )
    regime_holdout_lite["mode"] = regime_holdout_mode
    regime_is_blocker = regime_holdout_mode != "advisory"
    fast_reject_passed = (
        bool(factor_evidence_lite.get("passed"))
        and bool(walk_forward_assessment_lite.get("passed"))
        and (bool(regime_holdout_lite.get("passed")) or not regime_is_blocker)
    )
    blocker_codes: list[str] = []
    advisory_codes: list[str] = []
    if not bool(factor_evidence_lite.get("passed")):
        blocker_codes.append(LITE_BLOCKER_FACTOR)
    if not bool(walk_forward_assessment_lite.get("passed")):
        blocker_codes.append(LITE_BLOCKER_WALK_FORWARD)
    if not bool(regime_holdout_lite.get("passed")):
        if regime_is_blocker:
            blocker_codes.append(LITE_BLOCKER_REGIME)
        else:
            advisory_codes.append(LITE_ADVISORY_REGIME)
    return _write_fast_reject_report(
        path=family_root / "fast_reject_report.json",
        payload={
            "status": "success",
            "success": True,
            "as_of": as_of,
            "candidate_id": str(candidate_entry["candidate_id"]),
            "base_mechanism_id": str(candidate_entry["base_mechanism_id"]),
            "horizon_id": str(candidate_entry["horizon_id"]),
            "target_horizon_bars": int(candidate_entry["target_horizon_bars"]),
            "label_contract_id": label_contract_id,
            "strategy_id": str(candidate_entry["candidate_id"]),
            "dataset_profile": HYPOTHESIS_BATCH_DATASET_PROFILE,
            "feature_set_id": feature_set_id,
            "split_realization_contract": split_realization_contract,
            "target_column": target_column,
            "forward_return_column": forward_return_column,
            "dataset_manifest_path": portable_path(Path(dataset_manifest_path), repo_root=ROOT) if dataset_manifest_path else "",
            "feature_manifest_path": portable_path(Path(feature_manifest_path), repo_root=ROOT) if feature_manifest_path else "",
            "selected_feature_columns": selected_feature_columns,
            "split_row_counts": {
                "train": int(len(train_df)),
                "validation": int(len(validation_df)),
                "test": int(len(test_df)),
            },
            "validation_metrics_lite": {
                "net_return": float(validation_metrics.get("net_return", 0.0) or 0.0),
                "sharpe": float(validation_metrics.get("sharpe", 0.0) or 0.0),
            },
            "test_metrics_lite": {
                "net_return": float(test_metrics.get("net_return", 0.0) or 0.0),
                "sharpe": float(test_metrics.get("sharpe", 0.0) or 0.0),
            },
            "factor_evidence_lite": factor_evidence_lite,
            "walk_forward_assessment_lite": walk_forward_assessment_lite,
            "regime_holdout_lite": regime_holdout_lite,
            "fast_reject_passed": fast_reject_passed,
            "blocker_codes": blocker_codes,
            "advisory_codes": advisory_codes,
        },
        source_commit_sha=source_commit_sha,
    )


def _select_candidate_feature_columns(
    *,
    candidate_entry: dict[str, Any],
    numeric_feature_columns: list[str],
) -> list[str]:
    selection_mode = str(candidate_entry.get("feature_selection_mode") or "").strip().lower()
    if selection_mode == "required_columns":
        return [
            column
            for column in dict.fromkeys(
                str(item).strip()
                for item in list(candidate_entry.get("required_feature_columns") or [])
                if str(item).strip()
            )
            if column
        ]
    selected = select_feature_columns(
        numeric_feature_columns=numeric_feature_columns,
        feature_groups=list(candidate_entry.get("feature_groups") or []),
    )
    if bool(candidate_entry.get("include_required_feature_columns_in_selection")):
        for column in list(candidate_entry.get("required_feature_columns") or []):
            normalized = str(column).strip()
            if normalized and normalized not in selected:
                selected.append(normalized)
    return selected


def _build_factor_evidence_lite_section(
    *,
    factor_evidence: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    thresholds = dict(contract.get("factor_evidence_lite") or {})
    quarter_results = [
        dict(item)
        for item in list(factor_evidence.get("regime_split_results") or [])
        if isinstance(item, dict)
    ]
    positive_regime_count = sum(1 for item in quarter_results if bool(item.get("positive")))
    positive_edge_contributions = [
        max(float(item.get("top_minus_bottom_return", 0.0) or 0.0), 0.0)
        for item in quarter_results
    ]
    total_positive_edge = sum(positive_edge_contributions)
    max_single_quarter_edge_contribution_ratio = (
        max(positive_edge_contributions) / total_positive_edge
        if total_positive_edge > 0.0
        else 0.0
    )
    missing_required_feature_columns = [
        str(item).strip()
        for item in list(factor_evidence.get("missing_required_feature_columns") or [])
        if str(item).strip()
    ]
    passed = (
        not missing_required_feature_columns
        and abs(float(factor_evidence.get("rank_ic_mean", 0.0) or 0.0))
        >= float(thresholds.get("rank_ic_mean_abs_min", 0.01) or 0.01)
        and float(factor_evidence.get("rank_ic_positive_rate", 0.0) or 0.0)
        >= float(thresholds.get("rank_ic_positive_rate_min", 0.50) or 0.50)
        and float(factor_evidence.get("top_minus_bottom_return", 0.0) or 0.0)
        > float(thresholds.get("top_minus_bottom_return_min_exclusive", 0.0) or 0.0)
        and positive_regime_count
        >= int(thresholds.get("positive_regime_count_min", 1) or 1)
        and max_single_quarter_edge_contribution_ratio
        <= float(thresholds.get("max_single_quarter_edge_contribution_ratio_max", 0.75) or 0.75)
    )
    return {
        "rank_ic_mean": float(factor_evidence.get("rank_ic_mean", 0.0) or 0.0),
        "rank_ic_positive_rate": float(factor_evidence.get("rank_ic_positive_rate", 0.0) or 0.0),
        "top_minus_bottom_return": float(factor_evidence.get("top_minus_bottom_return", 0.0) or 0.0),
        "positive_regime_count": int(positive_regime_count),
        "max_single_quarter_edge_contribution_ratio": float(max_single_quarter_edge_contribution_ratio),
        "monotonicity_passed": bool(factor_evidence.get("monotonicity_passed")),
        "missing_required_feature_columns": missing_required_feature_columns,
        "passed": passed,
    }


def _write_strict_results(
    *,
    as_of: str,
    batch_root: Path,
    reports: list[dict[str, Any]],
    strict_experiments: list[dict[str, Any]],
    source_commit_sha: str,
) -> dict[str, Any]:
    experiments_by_candidate_id = {
        str(item.get("strategy_id") or "").strip(): dict(item)
        for item in strict_experiments
        if str(item.get("strategy_id") or "").strip()
    }
    strict_candidates: list[dict[str, Any]] = []
    strict_survivors: list[dict[str, Any]] = []
    for report in reports:
        candidate_id = str(report.get("candidate_id") or "").strip()
        if not candidate_id or not bool(report.get("fast_reject_passed")):
            continue
        experiment = dict(experiments_by_candidate_id.get(candidate_id) or {})
        family_root = batch_root / "families" / candidate_id
        family_root.mkdir(parents=True, exist_ok=True)
        result_payload = _strict_result_payload(
            as_of=as_of,
            report=report,
            experiment=experiment,
        )
        result_document = _write_evidence(
            path=family_root / "strict_result.json",
            payload=result_payload,
            evidence_family="quant_cross_sectional_strict_result",
            contract_version=STRICT_RESULT_CONTRACT_VERSION,
            source_commit_sha=source_commit_sha,
        )
        strict_candidate = {
            "candidate_id": candidate_id,
            "base_mechanism_id": str(report.get("base_mechanism_id") or ""),
            "horizon_id": str(report.get("horizon_id") or ""),
            "target_horizon_bars": int(report.get("target_horizon_bars") or 0),
            "label_contract_id": str(report.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID),
            "fast_reject_report_path": portable_path(Path(str(report["path"])), repo_root=ROOT),
            "strict_result_path": portable_path(Path(str(result_document["path"])), repo_root=ROOT),
            "strict_validation_passed": bool(result_payload.get("strict_validation_passed")),
            "experiment_id": str(result_payload.get("experiment_id") or ""),
            "alpha_card_path": str(result_payload.get("alpha_card_path") or ""),
            "validation_report_path": str(result_payload.get("validation_report_path") or ""),
            "validation_contract_status": str(result_payload.get("validation_contract_status") or ""),
            "falsification_status": str(result_payload.get("falsification_status") or ""),
            "statistical_falsification_status": str(result_payload.get("statistical_falsification_status") or ""),
            "alpha_experiment_card_status": str(result_payload.get("alpha_experiment_card_status") or ""),
            "alpha_experiment_card_go_no_go": result_payload.get("alpha_experiment_card_go_no_go"),
            "credible_research_evidence": bool(result_payload.get("credible_research_evidence")),
        }
        strict_candidates.append(strict_candidate)
        if strict_candidate["strict_validation_passed"]:
            strict_survivors.append(dict(strict_candidate))
    return {
        "strict_candidates": strict_candidates,
        "strict_survivors": strict_survivors,
    }


def _strict_result_payload(
    *,
    as_of: str,
    report: dict[str, Any],
    experiment: dict[str, Any],
) -> dict[str, Any]:
    alpha_card = dict(experiment.get("alpha_card") or {})
    validation_report = dict(experiment.get("validation_report") or {})
    validation_contract = dict(validation_report.get("validation_contract") or alpha_card.get("validation_contract") or {})
    falsification_status = str(alpha_card.get("falsification_status") or validation_report.get("falsification_status") or "").strip()
    alpha_experiment_card = dict(
        validation_report.get("alpha_experiment_card")
        or alpha_card.get("alpha_experiment_card")
        or {}
    )
    statistical_falsification = dict(
        validation_report.get("statistical_falsification")
        or alpha_card.get("statistical_falsification")
        or {}
    )
    alpha_experiment_card_go_no_go = (
        bool(alpha_experiment_card.get("go_no_go")) if alpha_experiment_card else True
    )
    statistical_falsification_status = str(statistical_falsification.get("status") or "").strip()
    statistical_falsification_passed = (
        statistical_falsification_status in {"", "cleared", "not_required", "passed"}
    )
    credible_research_evidence = bool(
        alpha_card.get("credible_research_evidence", validation_report.get("credible_research_evidence", False))
    )
    strict_validation_passed = (
        str(validation_contract.get("status") or "").strip() == "passed"
        and falsification_status in {"cleared", "not_required"}
        and alpha_experiment_card_go_no_go
        and statistical_falsification_passed
        and credible_research_evidence
    )
    return {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "candidate_id": str(report.get("candidate_id") or ""),
        "base_mechanism_id": str(report.get("base_mechanism_id") or ""),
        "horizon_id": str(report.get("horizon_id") or ""),
        "target_horizon_bars": int(report.get("target_horizon_bars") or 0),
        "label_contract_id": str(report.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID),
        "fast_reject_report_path": portable_path(Path(str(report["path"])), repo_root=ROOT),
        "experiment_id": str(experiment.get("experiment_id") or ""),
        "experiment_status": str(experiment.get("experiment_status") or alpha_card.get("experiment_status") or ""),
        "alpha_card_path": str(experiment.get("alpha_card_path") or ""),
        "validation_report_path": str(experiment.get("validation_report_path") or ""),
        "validation_contract_status": str(validation_contract.get("status") or ""),
        "falsification_status": falsification_status,
        "statistical_falsification_status": statistical_falsification_status,
        "statistical_falsification_blocker_codes": list(statistical_falsification.get("blocker_codes") or []),
        "alpha_experiment_card_status": str(alpha_experiment_card.get("status") or ""),
        "alpha_experiment_card_go_no_go": (
            bool(alpha_experiment_card.get("go_no_go")) if alpha_experiment_card else None
        ),
        "alpha_experiment_card_blocker_codes": list(alpha_experiment_card.get("blocker_codes") or []),
        "credible_research_evidence": credible_research_evidence,
        "strict_validation_passed": strict_validation_passed,
    }


def _write_strict_candidate_list(
    *,
    path: Path,
    as_of: str,
    manifest: dict[str, Any],
    strict_results: dict[str, Any],
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "artifact_family": "quant_cross_sectional_strict_candidate_list",
        "contract_version": STRICT_CANDIDATE_LIST_CONTRACT_VERSION,
        "eligible_candidate_ids": [
            str(item["candidate_id"])
            for item in manifest["entries"]
            if bool(item.get("enabled", True))
        ],
        "strict_candidate_count": len(strict_results["strict_candidates"]),
        "strict_survivor_count": len(strict_results["strict_survivors"]),
        "strict_candidates": strict_results["strict_candidates"],
        "strict_survivors": strict_results["strict_survivors"],
    }
    return _write_evidence(
        path=path,
        payload=payload,
        evidence_family="quant_cross_sectional_strict_candidate_list",
        contract_version=STRICT_CANDIDATE_LIST_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )


def _count_entries_by_field(
    *,
    entries: list[dict[str, Any]],
    field_name: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        value = str(entry.get(field_name) or "").strip()
        if not value:
            continue
        counts[value] = int(counts.get(value, 0)) + 1
    return dict(sorted(counts.items()))


def _count_reports_by_field(
    *,
    reports: list[dict[str, Any]],
    field_name: str,
    require_fast_reject_passed: bool = False,
) -> dict[str, int]:
    filtered_reports = [
        report
        for report in reports
        if not require_fast_reject_passed or bool(report.get("fast_reject_passed"))
    ]
    return _count_entries_by_field(entries=filtered_reports, field_name=field_name)


def _feature_set_for_dataset_profile(
    *,
    feature_sets: list[dict[str, Any]],
    dataset_profile: str,
) -> list[dict[str, Any]]:
    matching_feature_sets: list[dict[str, Any]] = []
    for feature_set in feature_sets:
        if str(feature_set.get("dataset_profile") or "").strip() == dataset_profile:
            matching_feature_sets.append(dict(feature_set))
    return matching_feature_sets


def _feature_set_for_candidate(
    *,
    feature_sets: list[dict[str, Any]],
    candidate_entry: dict[str, Any],
) -> dict[str, Any] | None:
    dataset_profile_feature_sets = _feature_set_for_dataset_profile(
        feature_sets=feature_sets,
        dataset_profile=str(candidate_entry.get("dataset_profile") or HYPOTHESIS_BATCH_DATASET_PROFILE),
    )
    if not dataset_profile_feature_sets:
        return None
    requested_target_horizon_bars = int(candidate_entry.get("target_horizon_bars") or 0)
    requested_label_contract_id = str(
        candidate_entry.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID
    ).strip() or DEFAULT_LABEL_CONTRACT_ID
    if requested_target_horizon_bars <= 0:
        for feature_set in dataset_profile_feature_sets:
            feature_set_label_contract_id = str(
                feature_set.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID
            ).strip() or DEFAULT_LABEL_CONTRACT_ID
            if feature_set_label_contract_id == requested_label_contract_id:
                return dict(feature_set)
        return dict(dataset_profile_feature_sets[0])
    for feature_set in dataset_profile_feature_sets:
        feature_set_target_horizon_bars = int(
            feature_set.get("target_horizon_bars")
            or dict(feature_set.get("split_realization_contract") or {}).get("target_horizon_bars")
            or 0
        )
        feature_set_label_contract_id = str(
            feature_set.get("label_contract_id") or DEFAULT_LABEL_CONTRACT_ID
        ).strip() or DEFAULT_LABEL_CONTRACT_ID
        if (
            feature_set_target_horizon_bars == requested_target_horizon_bars
            and feature_set_label_contract_id == requested_label_contract_id
        ):
            return dict(feature_set)
    return None


def _write_fast_reject_report(
    *,
    path: Path,
    payload: dict[str, Any],
    source_commit_sha: str,
) -> dict[str, Any]:
    normalized_payload = dict(payload)
    normalized_payload.setdefault("artifact_family", "quant_cross_sectional_fast_reject_report")
    normalized_payload.setdefault("contract_version", FAST_REJECT_REPORT_CONTRACT_VERSION)
    normalized_payload["report_hash"] = sha256_canonical_json(
        {
            key: value
            for key, value in normalized_payload.items()
            if key != "generated_at_utc"
        }
    )
    return _write_evidence(
        path=path,
        payload=normalized_payload,
        evidence_family="quant_cross_sectional_fast_reject_report",
        contract_version=FAST_REJECT_REPORT_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )


def _write_evidence(
    *,
    path: Path,
    payload: dict[str, Any],
    evidence_family: str,
    contract_version: str,
    source_commit_sha: str,
) -> dict[str, Any]:
    document = with_evidence_metadata(
        dict(payload),
        evidence_family=evidence_family,
        contract_version=contract_version,
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, document)
    document["path"] = str(path)
    return document
