from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .contracts import QuantUniverseCandidate, STRATEGY_PROFILES, profile_constraints, slugify, utc_now, write_json, read_json
from .data_readiness import blocked_discovery_reason, is_daily_executable_strategy, strategy_requires_temporal_event_tape
from .experiment_status import (
    EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
    counts_as_daily_failure,
    is_pass_experiment_status,
    is_pipeline_unreliable_pending_single_asset_fix,
    is_quarantined_experiment_status,
    is_rerun_required_experiment_status,
)
from .feature_admission import is_model_admissible_numeric_column
from .leakage_audit import load_leakage_audit, write_pending_leakage_audit
from .promotion import evaluate_quant_publication_assessment, strategy_lifecycle
from .validation_contract import validation_contract_blocker_codes


BASELINE_SINGLE_ASSET_MODELS = (
    "trend_following",
    "mean_reversion",
    "breakout_continuation",
    "logistic_regression",
    "random_forest",
    "hist_gradient_boosting",
    "meta_labeling",
)
BASELINE_CROSS_SECTION_MODELS = (
    "relative_strength_cross_section",
    "ranking_scorer",
    "logistic_regression",
    "random_forest",
    "hist_gradient_boosting",
    "meta_labeling",
)
DISCOVERY_SINGLE_ASSET_MODELS = (
    "carry_funding",
    "basis_divergence",
    "volatility_expansion",
    "event_drift",
    "extra_trees_classifier",
    "elasticnet_logistic",
    "gradient_boosting_classifier",
)
DISCOVERY_CROSS_SECTION_MODELS = (
    "carry_funding",
    "basis_divergence",
    "extra_trees_classifier",
    "elasticnet_logistic",
    "gradient_boosting_classifier",
)
SINGLE_ASSET_MODELS = BASELINE_SINGLE_ASSET_MODELS
CROSS_SECTION_MODELS = BASELINE_CROSS_SECTION_MODELS
ALLOWED_SINGLE_ASSET_MODELS = tuple(dict.fromkeys(BASELINE_SINGLE_ASSET_MODELS + DISCOVERY_SINGLE_ASSET_MODELS))
ALLOWED_CROSS_SECTION_MODELS = tuple(dict.fromkeys(BASELINE_CROSS_SECTION_MODELS + DISCOVERY_CROSS_SECTION_MODELS))
FEATURE_GROUPS = (
    "core_context",
    "structure",
    "volatility",
    "volume",
    "trend",
    "derivatives",
    "events",
)
LIBRARY_STATUSES = ("active", "watch", "candidate", "discovery", "retired", "quarantined")
PROPOSAL_BUDGET_LIMIT = 12
PROPOSAL_BUCKET_LIMITS = {
    "config": 4,
    "feature": 4,
    "universe": 4,
}
ACTIVE_STRATEGY_IDS = {
    "baseline-eth-balanced-logistic-regression-single-asset",
    "baseline-eth-conservative-logistic-regression-single-asset",
    "baseline-eth-aggressive-meta-labeling-single-asset",
    "baseline-eth-balanced-meta-labeling-single-asset",
    "baseline-eth-conservative-meta-labeling-single-asset",
    "baseline-sui-aggressive-meta-labeling-single-asset",
    "baseline-sui-balanced-meta-labeling-single-asset",
}
WATCH_STRATEGY_IDS = {
    "baseline-eth-aggressive-logistic-regression-single-asset",
    "baseline-sui-conservative-logistic-regression-single-asset",
}
CANDIDATE_STRATEGY_IDS = {
    "baseline-balanced-logistic-regression-cross-sectional",
    "baseline-balanced-ranking-scorer-cross-sectional",
    "baseline-conservative-relative-strength-cross-sectional",
}
DAILY_ACTIVE_EXPERIMENT_BUDGET = 8
DAILY_WATCH_EXPERIMENT_BUDGET = 4
DAILY_CANDIDATE_CANARY_BUDGET = 4
WEEKLY_SANDBOX_BUDGET = 8
WEEKLY_DISCOVERY_SCREEN_BUDGET = 24
WEEKLY_DISCOVERY_FULL_VALIDATION_BUDGET = 12
WEEKLY_CANDIDATE_PROMOTION_CAP = 4
WEEKLY_PROMOTION_TO_ACTIVE_CAP = 2
CATALOG_VERSION = 5
STRATEGY_LIBRARY_VERSION = 6
REGISTRY_VERSION = 1
THESIS_TASK_LIBRARY_MODE = "thesis_task"
THESIS_TASK_LIBRARY_SOFT_MAX = 16
THESIS_TASK_LIBRARY_HARD_MAX = 20
WEEKLY_MAX_NEW_TASKS = 2
WEEKLY_MAX_TASK_REVISIONS = 4
THESIS_TASK_SEED_FILENAME = "strategy_library_thesis_seed.json"
MODEL_ENGINE_TEMPLATES = (
    "linear_classifier",
    "tree_ensemble",
    "boosted_tree",
    "meta_label_wrapper",
    "deterministic_rule_stack",
)
FEATURE_FAMILY_TRANSFORMS = (
    "lag",
    "difference",
    "ratio",
    "ema",
    "rolling_mean",
    "rolling_std",
    "zscore",
    "rank",
    "interaction",
    "clip",
)
PROPOSAL_ORIGINS = ("heuristic", "agent", "proposal")
SEARCH_ACTIONS = (
    "parameter_tune",
    "feature_variant",
    "universe_variant",
    "new_feature_family",
    "model_overlay",
)
CONTROL_BASELINE_LANE = "control_baseline"
HYPOTHESIS_FACTOR_LANE = "hypothesis_factor"
HYPOTHESIS_PORTFOLIO_LANE = "hypothesis_portfolio"
HYPOTHESIS_MODEL_LANE = "hypothesis_model"
RESEARCH_LANES = (
    CONTROL_BASELINE_LANE,
    HYPOTHESIS_FACTOR_LANE,
    HYPOTHESIS_PORTFOLIO_LANE,
    HYPOTHESIS_MODEL_LANE,
)
HYPOTHESIS_RESEARCH_LANES = (
    HYPOTHESIS_FACTOR_LANE,
    HYPOTHESIS_PORTFOLIO_LANE,
    HYPOTHESIS_MODEL_LANE,
)
PROMOTION_ELIGIBILITY_VALUES = ("eligible", "ineligible")
THESIS_PROFILE_CONTRACT_VERSION = "quant_hypothesis_track.v1"
HYPOTHESIS_PROMOTION_PATH = [
    HYPOTHESIS_FACTOR_LANE,
    HYPOTHESIS_PORTFOLIO_LANE,
    HYPOTHESIS_MODEL_LANE,
]
HYPOTHESIS_MODEL_FAMILIES = {"ranking_scorer", "logistic_regression"}
MODEL_OVERLAY_MODEL_FAMILIES = ("logistic_regression", "ranking_scorer")
FROZEN_MODEL_FAMILIES = {"random_forest", "meta_labeling"}
DERIVATIVES_THESIS_FEATURE_COLUMNS = (
    "funding_rate",
    "funding_zscore_20",
    "basis_proxy",
    "basis_zscore_20",
    "oi_change_5",
    "perp_quote_volume_usd",
)
LIQUID_PERP_CORE_20_PRESET = "liquid_perp_core_20"
DAILY_HYPOTHESIS_TRACK_LIMIT = 3
FACTOR_EVIDENCE_ARCHIVE_FAIL_STREAK = 2
PORTFOLIO_MODEL_READY_PASS_STREAK = 2
LEAKAGE_AUDIT_TIMEOUT_HOURS = 24.0
TERMINAL_THESIS_BLOCKER_CODES = {
    "execution_capacity_failed",
    "reproducibility_contract_failed",
    "feature_admission_failed",
    "split_realization_contract_failed",
}
COMPLEXITY_TIERS = {
    "low": 0.2,
    "medium": 0.5,
    "high": 0.8,
}
MAX_PROPOSAL_SELECTED_FEATURES = 32
MAX_MODEL_HYPERPARAMETERS = 12
MAX_INTERACTION_FEATURES = 3
RUNTIME_EVOLUTION_FLAGS = {
    "agent_may_register_new_family": True,
    "agent_may_register_new_feature_family": True,
    "same_day_auto_bridge": True,
    "same_week_auto_bridge": True,
}
UNSAFE_PATCH_PATTERN = re.compile(r"(__import__|eval\(|exec\(|lambda\b|subprocess|pickle|os\.)", re.IGNORECASE)
BUILTIN_MODEL_FAMILY_DEFINITIONS = {
    "trend_following": {
        "family_id": "trend_following",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["single_asset"],
        "hyperparameters": {"base_rule_family": "trend_following"},
    },
    "mean_reversion": {
        "family_id": "mean_reversion",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["single_asset"],
        "hyperparameters": {"base_rule_family": "mean_reversion"},
    },
    "breakout_continuation": {
        "family_id": "breakout_continuation",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["single_asset"],
        "hyperparameters": {"base_rule_family": "breakout_continuation"},
    },
    "carry_funding": {
        "family_id": "carry_funding",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"base_rule_family": "carry_funding"},
    },
    "basis_divergence": {
        "family_id": "basis_divergence",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"base_rule_family": "basis_divergence"},
    },
    "volatility_expansion": {
        "family_id": "volatility_expansion",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["single_asset"],
        "hyperparameters": {"base_rule_family": "trend_following"},
    },
    "event_drift": {
        "family_id": "event_drift",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["single_asset"],
        "hyperparameters": {"base_rule_family": "trend_following"},
    },
    "relative_strength_cross_section": {
        "family_id": "relative_strength_cross_section",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["cross_sectional"],
        "hyperparameters": {"base_rule_family": "relative_strength_cross_section"},
    },
    "ranking_scorer": {
        "family_id": "ranking_scorer",
        "engine_template": "deterministic_rule_stack",
        "allowed_shapes": ["cross_sectional"],
        "hyperparameters": {"base_rule_family": "ranking_scorer"},
    },
    "logistic_regression": {
        "family_id": "logistic_regression",
        "engine_template": "linear_classifier",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"penalty": "l2", "max_iter": 2000},
    },
    "elasticnet_logistic": {
        "family_id": "elasticnet_logistic",
        "engine_template": "linear_classifier",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"penalty": "elasticnet", "solver": "saga", "l1_ratio": 0.5, "max_iter": 4000},
    },
    "random_forest": {
        "family_id": "random_forest",
        "engine_template": "tree_ensemble",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"n_estimators": 200, "max_depth": 6, "min_samples_leaf": 5},
    },
    "extra_trees_classifier": {
        "family_id": "extra_trees_classifier",
        "engine_template": "tree_ensemble",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"implementation": "extra_trees", "n_estimators": 300, "max_depth": 8, "min_samples_leaf": 4},
    },
    "hist_gradient_boosting": {
        "family_id": "hist_gradient_boosting",
        "engine_template": "boosted_tree",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"implementation": "hist_gradient_boosting", "max_depth": 6, "max_iter": 200, "learning_rate": 0.05},
    },
    "gradient_boosting_classifier": {
        "family_id": "gradient_boosting_classifier",
        "engine_template": "boosted_tree",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"implementation": "gradient_boosting"},
    },
    "meta_labeling": {
        "family_id": "meta_labeling",
        "engine_template": "meta_label_wrapper",
        "allowed_shapes": ["single_asset", "cross_sectional"],
        "hyperparameters": {"base_rule_family": "trend_following"},
    },
}
BUILTIN_FEATURE_FAMILY_DEFINITIONS = {
    family_id: {
        "family_id": family_id,
        "kind": "built_in_group",
        "transform_count": 0,
        "generated_features": [],
    }
    for family_id in FEATURE_GROUPS
}


def governance_root(*, artifacts_root: Path) -> Path:
    return artifacts_root / "governance"


def strategy_catalog_path(*, artifacts_root: Path) -> Path:
    return governance_root(artifacts_root=artifacts_root) / "strategy_catalog.json"


def strategy_library_path(*, artifacts_root: Path) -> Path:
    return governance_root(artifacts_root=artifacts_root) / "strategy_library.json"


def strategy_library_archive_root(*, artifacts_root: Path) -> Path:
    return governance_root(artifacts_root=artifacts_root) / "archives" / "strategy_library_thesis_cutover"


def strategy_library_cutover_archive_path(*, artifacts_root: Path, as_of: str) -> Path:
    return strategy_library_archive_root(artifacts_root=artifacts_root) / normalize_governance_as_of(as_of)


def strategy_library_thesis_seed_manifest_path() -> Path:
    return Path(__file__).resolve().with_name(THESIS_TASK_SEED_FILENAME)


def _raw_thesis_task_seed_manifest() -> dict[str, Any]:
    path = strategy_library_thesis_seed_manifest_path()
    payload = read_json(path)
    payload["path"] = str(path)
    return payload


def _default_strategy_data_dependencies(
    *,
    shape: str,
    feature_groups: Iterable[str] | None,
) -> dict[str, Any]:
    normalized_groups = {str(item) for item in (feature_groups or ()) if str(item).strip()}
    derivatives_required = "derivatives" in normalized_groups
    return {
        "spot_ohlcv_intervals": ["4h", "1d"],
        "usdm_ohlcv_intervals": ["4h", "1d"],
        "derivatives_fields": ["funding_rate", "open_interest"] if derivatives_required else [],
        "universe_snapshot_required": str(shape) == "cross_sectional",
    }


def _default_review_priority(*, lifecycle: str) -> float:
    mapping = {
        "active": 100.0,
        "watch": 80.0,
        "candidate": 60.0,
        "discovery": 40.0,
        "retired": 10.0,
        "quarantined": 5.0,
    }
    return float(mapping.get(str(lifecycle or "").strip(), 0.0))


def _default_task_thesis(*, shape: str, subject: str | None, strategy_profile: str, model_family: str) -> tuple[str, str, str]:
    normalized_shape = str(shape)
    normalized_subject = str(subject or "universe").upper()
    normalized_profile = str(strategy_profile)
    normalized_model = str(model_family)
    if normalized_shape == "cross_sectional":
        rationale = (
            f"Validate whether {normalized_profile} cross-sectional rotation built on {normalized_model} "
            "still extracts a persistent ranking edge from the liquid universe."
        )
        expected_edge = (
            "If the thesis is real, top-ranked names should keep outperforming the rebalance basket out of sample."
        )
        invalidates_if = (
            "Median walk-forward OOS Sharpe turns non-positive or the cross-sectional test basket loses net profitability."
        )
        return rationale, expected_edge, invalidates_if
    rationale = (
        f"Validate whether {normalized_subject} retains a durable {normalized_profile} single-asset edge under {normalized_model}."
    )
    expected_edge = "If the thesis is real, validation and test windows should remain profitable after governance constraints."
    invalidates_if = "Out-of-sample returns or Sharpe turn non-positive after the feature and risk envelope are applied."
    return rationale, expected_edge, invalidates_if


def _normalize_data_dependencies(
    *,
    shape: str,
    feature_groups: Iterable[str] | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = _default_strategy_data_dependencies(shape=shape, feature_groups=feature_groups)
    if isinstance(payload, dict):
        merged.update(_json_ready(payload))
    return _json_ready(merged)


def _thesis_seed_entries() -> list[dict[str, Any]]:
    payload = _raw_thesis_task_seed_manifest()
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("thesis seed manifest entries must be a list")
    return [dict(entry) for entry in entries if isinstance(entry, dict)]


def strategy_library_metrics(*, strategy_library: dict[str, Any]) -> dict[str, Any]:
    entries = [entry for entry in strategy_library.get("entries", []) if isinstance(entry, dict)]
    shape_mix = Counter(str(entry.get("shape") or "unknown") for entry in entries)
    lifecycle_mix = Counter(strategy_lifecycle(entry) for entry in entries)
    executable_entries = [entry for entry in entries if is_daily_executable_strategy(strategy_entry=entry)]
    executable_lifecycle_mix = Counter(strategy_lifecycle(entry) for entry in executable_entries)
    target_selected = (
        min(executable_lifecycle_mix.get("active", 0), DAILY_ACTIVE_EXPERIMENT_BUDGET)
        + min(executable_lifecycle_mix.get("watch", 0), DAILY_WATCH_EXPERIMENT_BUDGET)
        + min(executable_lifecycle_mix.get("candidate", 0), DAILY_CANDIDATE_CANARY_BUDGET)
    )
    entry_count = len(entries)
    return {
        "entry_count": entry_count,
        "shape_mix": {key: shape_mix[key] for key in sorted(shape_mix)},
        "lifecycle_mix": {key: lifecycle_mix[key] for key in sorted(lifecycle_mix)},
        "daily_inventory_utilization_target": (target_selected / entry_count) if entry_count else 0.0,
    }


def _validate_strategy_library_payload(*, payload: dict[str, Any]) -> None:
    if str(payload.get("library_mode") or THESIS_TASK_LIBRARY_MODE) != THESIS_TASK_LIBRARY_MODE:
        return
    entries = [entry for entry in payload.get("entries", []) if isinstance(entry, dict)]
    if len(entries) > THESIS_TASK_LIBRARY_HARD_MAX:
        raise ValueError(
            f"thesis task strategy library exceeds hard max={THESIS_TASK_LIBRARY_HARD_MAX}: {len(entries)}"
        )


def normalize_governance_as_of(value: str) -> str:
    normalized = str(value).strip()
    if len(normalized) >= 10:
        return normalized[:10]
    return normalized


def discovery_runs_root(*, artifacts_root: Path) -> Path:
    return governance_root(artifacts_root=artifacts_root) / "discovery_runs"


def discovery_as_of_root(*, artifacts_root: Path, as_of: str) -> Path:
    return discovery_runs_root(artifacts_root=artifacts_root) / normalize_governance_as_of(as_of)


def discovery_run_id(*, generated_at_utc: str | None = None) -> str:
    timestamp = str(generated_at_utc or utc_now()).strip()
    if not timestamp:
        timestamp = utc_now()
    timestamp = re.sub(r"\.\d+", "", timestamp)
    return (
        timestamp.replace("-", "")
        .replace(":", "")
        .replace("+00:00", "Z")
    )


def discovery_run_root(*, artifacts_root: Path, as_of: str, run_id: str) -> Path:
    return discovery_as_of_root(artifacts_root=artifacts_root, as_of=as_of) / str(run_id)


def weekly_review_root(*, artifacts_root: Path, week_of: str) -> Path:
    return governance_root(artifacts_root=artifacts_root) / "weekly_reviews" / week_of


def registry_root(*, artifacts_root: Path) -> Path:
    return governance_root(artifacts_root=artifacts_root) / "registries"


def model_family_registry_path(*, artifacts_root: Path) -> Path:
    return registry_root(artifacts_root=artifacts_root) / "model_family_registry.json"


def feature_family_registry_path(*, artifacts_root: Path) -> Path:
    return registry_root(artifacts_root=artifacts_root) / "feature_family_registry.json"


def registry_snapshot_path(*, artifacts_root: Path, week_of: str) -> Path:
    return weekly_review_root(artifacts_root=artifacts_root, week_of=iso_week_label(week_of)) / "registry_snapshot.json"


def discovery_registry_snapshot_path(*, artifacts_root: Path, as_of: str, run_id: str) -> Path:
    return discovery_run_root(artifacts_root=artifacts_root, as_of=as_of, run_id=run_id) / "registry_snapshot.json"


def selection_lane_for_lifecycle(lifecycle: str) -> str:
    normalized = str(lifecycle or "").strip() or "active"
    if normalized in {"active", "watch", "candidate", "discovery"}:
        return normalized
    return normalized


def promotion_state_for_lifecycle(lifecycle: str) -> str:
    normalized = str(lifecycle or "").strip() or "active"
    if normalized == "active":
        return "promoted"
    if normalized in {"watch", "candidate", "discovery"}:
        return "staged"
    return "blocked"


def target_lifecycle_for_strategy_id(strategy_id: str) -> str:
    normalized = str(strategy_id).strip()
    if normalized in ACTIVE_STRATEGY_IDS:
        return "active"
    if normalized in WATCH_STRATEGY_IDS:
        return "watch"
    if normalized in CANDIDATE_STRATEGY_IDS:
        return "candidate"
    return "discovery"


def iso_week_label(value: str) -> str:
    normalized = str(value).strip()
    if len(normalized) >= 10:
        year, month, day = normalized[:10].split("-")
        import datetime as _dt

        week = _dt.date(int(year), int(month), int(day)).isocalendar()
        return f"{week.year}-W{week.week:02d}"
    return normalized


def build_strategy_catalog_payload() -> dict[str, Any]:
    return {
        "generated_at_utc": utc_now(),
        "catalog_version": CATALOG_VERSION,
        "allowed_shapes": {
            "single_asset": list(ALLOWED_SINGLE_ASSET_MODELS),
            "cross_sectional": list(ALLOWED_CROSS_SECTION_MODELS),
        },
        "allowed_feature_groups": list(FEATURE_GROUPS),
        "strategy_profiles": list(STRATEGY_PROFILES),
        "daily_active_experiment_budget": DAILY_ACTIVE_EXPERIMENT_BUDGET,
        "daily_watch_experiment_budget": DAILY_WATCH_EXPERIMENT_BUDGET,
        "daily_candidate_canary_budget": DAILY_CANDIDATE_CANARY_BUDGET,
        "proposal_budget_limit": PROPOSAL_BUDGET_LIMIT,
        "weekly_sandbox_budget": WEEKLY_SANDBOX_BUDGET,
        "weekly_discovery_screen_budget": WEEKLY_DISCOVERY_SCREEN_BUDGET,
        "weekly_discovery_full_validation_budget": WEEKLY_DISCOVERY_FULL_VALIDATION_BUDGET,
        "weekly_candidate_promotion_cap": WEEKLY_CANDIDATE_PROMOTION_CAP,
        "weekly_promotion_to_active_cap": WEEKLY_PROMOTION_TO_ACTIVE_CAP,
        "proposal_bucket_limits": dict(PROPOSAL_BUCKET_LIMITS),
        "runtime_flags": dict(RUNTIME_EVOLUTION_FLAGS),
        "proposal_origin_allowlist": list(PROPOSAL_ORIGINS),
        "search_action_allowlist": list(SEARCH_ACTIONS),
        "research_lane_allowlist": list(RESEARCH_LANES),
        "promotion_eligibility_allowlist": list(PROMOTION_ELIGIBILITY_VALUES),
        "thesis_profile_contract_version": THESIS_PROFILE_CONTRACT_VERSION,
        "complexity_tiers": dict(COMPLEXITY_TIERS),
        "registry_version": REGISTRY_VERSION,
        "rules": {
            "agent_can_only_propose_config_level_variants": True,
            "agent_cannot_add_new_model_family": True,
            "active_only_bridge": False,
            "baseline_daily_execution_frozen": True,
            "non_control_strategy_requires_thesis_profile": True,
            "hypothesis_model_requires_prior_portfolio_stage": True,
        },
    }


def ensure_strategy_catalog(*, artifacts_root: Path) -> dict[str, Any]:
    payload = build_strategy_catalog_payload()
    path = strategy_catalog_path(artifacts_root=artifacts_root)
    write_json(path, payload)
    payload["path"] = str(path)
    return payload


def _family_usage_counts(*, artifacts_root: Path) -> dict[str, int]:
    path = strategy_library_path(artifacts_root=artifacts_root)
    if not path.exists():
        return {}
    payload = read_json(path)
    counts: dict[str, int] = {}
    for entry in payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        family_id = str(entry.get("family_id") or entry.get("model_family") or "").strip()
        if not family_id:
            continue
        counts[family_id] = counts.get(family_id, 0) + 1
    return counts


def _catalog_model_family_entry(*, family_id: str, definition: dict[str, Any], usage_count: int) -> dict[str, Any]:
    hyperparameters = _json_ready(dict(definition.get("hyperparameters") or {}))
    return {
        "family_id": family_id,
        "engine_template": str(definition.get("engine_template") or "linear_classifier"),
        "allowed_shapes": list(definition.get("allowed_shapes") or []),
        "hyperparameters": hyperparameters,
        "family_usage_count": int(usage_count),
        "failure_rate_rolling_8w": 0.0,
        "novelty_score": 1.0 if usage_count == 0 else round(1.0 / (1.0 + usage_count), 4),
        "regime_fit_tag": str(definition.get("regime_fit_tag") or "generalist"),
        "source": str(definition.get("source") or "builtin"),
    }


def _catalog_feature_family_entry(*, family_id: str, definition: dict[str, Any], usage_count: int) -> dict[str, Any]:
    generated_features = [str(item) for item in definition.get("generated_features", []) if str(item).strip()]
    return {
        "family_id": family_id,
        "kind": str(definition.get("kind") or "custom"),
        "generated_features": generated_features,
        "transform_count": int(definition.get("transform_count") or len(generated_features)),
        "family_usage_count": int(usage_count),
        "failure_rate_rolling_8w": 0.0,
        "novelty_score": 1.0 if usage_count == 0 else round(1.0 / (1.0 + usage_count), 4),
        "regime_fit_tag": str(definition.get("regime_fit_tag") or "generalist"),
        "source": str(definition.get("source") or "builtin"),
    }


def build_model_family_registry_payload(*, artifacts_root: Path) -> dict[str, Any]:
    usage_counts = _family_usage_counts(artifacts_root=artifacts_root)
    entries = [
        _catalog_model_family_entry(family_id=family_id, definition=definition, usage_count=usage_counts.get(family_id, 0))
        for family_id, definition in sorted(BUILTIN_MODEL_FAMILY_DEFINITIONS.items())
    ]
    return {
        "generated_at_utc": utc_now(),
        "registry_version": REGISTRY_VERSION,
        "entries": entries,
    }


def build_feature_family_registry_payload(*, artifacts_root: Path) -> dict[str, Any]:
    usage_counts = _family_usage_counts(artifacts_root=artifacts_root)
    entries = [
        _catalog_feature_family_entry(family_id=family_id, definition=definition, usage_count=usage_counts.get(family_id, 0))
        for family_id, definition in sorted(BUILTIN_FEATURE_FAMILY_DEFINITIONS.items())
    ]
    return {
        "generated_at_utc": utc_now(),
        "registry_version": REGISTRY_VERSION,
        "entries": entries,
    }


def ensure_model_family_registry(*, artifacts_root: Path) -> dict[str, Any]:
    payload = build_model_family_registry_payload(artifacts_root=artifacts_root)
    path = model_family_registry_path(artifacts_root=artifacts_root)
    if path.exists():
        existing = read_json(path)
        existing_entries = {
            str(entry.get("family_id") or ""): dict(entry)
            for entry in existing.get("entries", [])
            if isinstance(entry, dict) and str(entry.get("family_id") or "").strip()
        }
        for entry in payload["entries"]:
            existing_entries[str(entry["family_id"])] = {**existing_entries.get(str(entry["family_id"]), {}), **entry}
        payload["entries"] = [existing_entries[key] for key in sorted(existing_entries)]
    write_json(path, payload)
    payload["path"] = str(path)
    return payload


def ensure_feature_family_registry(*, artifacts_root: Path) -> dict[str, Any]:
    payload = build_feature_family_registry_payload(artifacts_root=artifacts_root)
    path = feature_family_registry_path(artifacts_root=artifacts_root)
    if path.exists():
        existing = read_json(path)
        existing_entries = {
            str(entry.get("family_id") or ""): dict(entry)
            for entry in existing.get("entries", [])
            if isinstance(entry, dict) and str(entry.get("family_id") or "").strip()
        }
        for entry in payload["entries"]:
            existing_entries[str(entry["family_id"])] = {**existing_entries.get(str(entry["family_id"]), {}), **entry}
        payload["entries"] = [existing_entries[key] for key in sorted(existing_entries)]
    write_json(path, payload)
    payload["path"] = str(path)
    return payload


def load_model_family_registry(*, artifacts_root: Path) -> dict[str, Any]:
    path = model_family_registry_path(artifacts_root=artifacts_root)
    if not path.exists():
        return ensure_model_family_registry(artifacts_root=artifacts_root)
    payload = read_json(path)
    payload["path"] = str(path)
    payload["entries"] = [dict(entry) for entry in payload.get("entries", []) if isinstance(entry, dict)]
    return payload


def load_feature_family_registry(*, artifacts_root: Path) -> dict[str, Any]:
    path = feature_family_registry_path(artifacts_root=artifacts_root)
    if not path.exists():
        return ensure_feature_family_registry(artifacts_root=artifacts_root)
    payload = read_json(path)
    payload["path"] = str(path)
    payload["entries"] = [dict(entry) for entry in payload.get("entries", []) if isinstance(entry, dict)]
    return payload


def _registry_entries_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(entry.get("family_id") or ""): dict(entry)
        for entry in registry.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("family_id") or "").strip()
    }


def _normalize_model_registry_patch(patch: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(patch, dict):
        return []
    families = patch.get("families", [])
    if not isinstance(families, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw_family in families:
        if not isinstance(raw_family, dict):
            continue
        family_id = str(raw_family.get("family_id") or "").strip()
        if not family_id:
            continue
        normalized.append(
            {
                "family_id": family_id,
                "engine_template": str(raw_family.get("engine_template") or "").strip(),
                "allowed_shapes": [str(item) for item in raw_family.get("allowed_shapes", []) if str(item).strip()],
                "hyperparameters": _json_ready(dict(raw_family.get("hyperparameters") or {})),
                "regime_fit_tag": str(raw_family.get("regime_fit_tag") or "generalist"),
                "source": str(raw_family.get("source") or "agent"),
            }
        )
    return normalized


def _normalize_feature_registry_patch(patch: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(patch, dict):
        return []
    families = patch.get("families", [])
    if not isinstance(families, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw_family in families:
        if not isinstance(raw_family, dict):
            continue
        family_id = str(raw_family.get("family_id") or "").strip()
        if not family_id:
            continue
        transforms = [dict(item) for item in raw_family.get("transforms", []) if isinstance(item, dict)]
        generated_features = [str(item.get("feature_name") or "") for item in transforms if str(item.get("feature_name") or "").strip()]
        normalized.append(
            {
                "family_id": family_id,
                "kind": str(raw_family.get("kind") or "custom"),
                "transforms": transforms,
                "generated_features": generated_features,
                "transform_count": len(transforms),
                "regime_fit_tag": str(raw_family.get("regime_fit_tag") or "generalist"),
                "source": str(raw_family.get("source") or "agent"),
            }
        )
    return normalized


def resolve_registry_snapshot(
    *,
    artifacts_root: Path,
    model_registry_patch: dict[str, Any] | None = None,
    feature_registry_patch: dict[str, Any] | None = None,
    registry_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_snapshot = registry_snapshot
    if base_snapshot is None:
        base_snapshot = {
            "generated_at_utc": utc_now(),
            "registry_version": REGISTRY_VERSION,
            "model_families": load_model_family_registry(artifacts_root=artifacts_root),
            "feature_families": load_feature_family_registry(artifacts_root=artifacts_root),
        }
    model_entries = _registry_entries_by_id(base_snapshot.get("model_families", {}))
    feature_entries = _registry_entries_by_id(base_snapshot.get("feature_families", {}))
    for family in _normalize_model_registry_patch(model_registry_patch):
        model_entries[str(family["family_id"])] = {
            **model_entries.get(str(family["family_id"]), {}),
            **family,
        }
    for family in _normalize_feature_registry_patch(feature_registry_patch):
        feature_entries[str(family["family_id"])] = {
            **feature_entries.get(str(family["family_id"]), {}),
            **family,
        }
    return {
        "generated_at_utc": base_snapshot.get("generated_at_utc", utc_now()),
        "registry_version": int(base_snapshot.get("registry_version") or REGISTRY_VERSION),
        "model_families": {"entries": [model_entries[key] for key in sorted(model_entries)]},
        "feature_families": {"entries": [feature_entries[key] for key in sorted(feature_entries)]},
    }


def materialize_registry_snapshot(*, artifacts_root: Path, week_of: str, run_id: str | None = None) -> dict[str, Any]:
    snapshot = resolve_registry_snapshot(artifacts_root=artifacts_root)
    as_of = normalize_governance_as_of(week_of)
    snapshot["snapshot_id"] = f"{as_of}-{hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode('utf-8')).hexdigest()[:12]}"
    path = (
        discovery_registry_snapshot_path(artifacts_root=artifacts_root, as_of=as_of, run_id=run_id)
        if run_id
        else registry_snapshot_path(artifacts_root=artifacts_root, week_of=week_of)
    )
    write_json(path, snapshot)
    snapshot["path"] = str(path)
    return snapshot


def persist_registry_patches(
    *,
    artifacts_root: Path,
    model_registry_patch: dict[str, Any] | None = None,
    feature_registry_patch: dict[str, Any] | None = None,
) -> None:
    model_registry = ensure_model_family_registry(artifacts_root=artifacts_root)
    model_entries = _registry_entries_by_id(model_registry)
    for family in _normalize_model_registry_patch(model_registry_patch):
        family_id = str(family["family_id"])
        existing = dict(model_entries.get(family_id, {}))
        existing.update(family)
        existing.setdefault("family_usage_count", 0)
        existing.setdefault("failure_rate_rolling_8w", 0.0)
        existing.setdefault("novelty_score", 1.0)
        existing.setdefault("regime_fit_tag", "generalist")
        model_entries[family_id] = existing
    write_json(model_family_registry_path(artifacts_root=artifacts_root), {"generated_at_utc": utc_now(), "registry_version": REGISTRY_VERSION, "entries": [model_entries[key] for key in sorted(model_entries)]})

    feature_registry = ensure_feature_family_registry(artifacts_root=artifacts_root)
    feature_entries = _registry_entries_by_id(feature_registry)
    for family in _normalize_feature_registry_patch(feature_registry_patch):
        family_id = str(family["family_id"])
        existing = dict(feature_entries.get(family_id, {}))
        existing.update(family)
        existing.setdefault("family_usage_count", 0)
        existing.setdefault("failure_rate_rolling_8w", 0.0)
        existing.setdefault("novelty_score", 1.0)
        existing.setdefault("regime_fit_tag", "generalist")
        feature_entries[family_id] = existing
    write_json(feature_family_registry_path(artifacts_root=artifacts_root), {"generated_at_utc": utc_now(), "registry_version": REGISTRY_VERSION, "entries": [feature_entries[key] for key in sorted(feature_entries)]})


def resolve_model_family_definition(
    *,
    artifacts_root: Path,
    model_family: str,
    strategy_entry: dict[str, Any] | None = None,
    registry_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    resolved = resolve_registry_snapshot(
        artifacts_root=artifacts_root,
        model_registry_patch=None if strategy_entry is None else strategy_entry.get("family_registry_patch"),
        feature_registry_patch=None,
        registry_snapshot=registry_snapshot,
    )
    families = _registry_entries_by_id(resolved.get("model_families", {}))
    family = families.get(str(model_family))
    return None if family is None else dict(family)


def resolve_feature_family_entries(
    *,
    artifacts_root: Path,
    strategy_entry: dict[str, Any] | None = None,
    registry_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    resolved = resolve_registry_snapshot(
        artifacts_root=artifacts_root,
        model_registry_patch=None,
        feature_registry_patch=None if strategy_entry is None else strategy_entry.get("feature_registry_patch"),
        registry_snapshot=registry_snapshot,
    )
    requested_ids = [
        str(item)
        for item in (strategy_entry or {}).get("feature_family_ids", [])
        if str(item).strip()
    ]
    if not requested_ids and strategy_entry is not None:
        requested_ids = [str(item.get("family_id")) for item in _normalize_feature_registry_patch(strategy_entry.get("feature_registry_patch"))]
    feature_entries = _registry_entries_by_id(resolved.get("feature_families", {}))
    return [dict(feature_entries[family_id]) for family_id in requested_ids if family_id in feature_entries]


def _stable_strategy_spec_payload(
    *,
    shape: str,
    strategy_profile: str,
    subject: str | None,
    universe_filter: dict[str, Any] | None,
    model_family: str,
    feature_groups: Iterable[str],
    profile_constraints_override: dict[str, Any] | None,
    family_registry_patch: dict[str, Any] | None = None,
    feature_registry_patch: dict[str, Any] | None = None,
    search_action: str | None = None,
) -> dict[str, Any]:
    return {
        "shape": shape,
        "strategy_profile": strategy_profile,
        "subject": str(subject).upper() if subject else None,
        "universe_filter": _json_ready(universe_filter or {}),
        "model_family": model_family,
        "feature_groups": sorted(set(feature_groups)),
        "profile_constraints_override": _json_ready(profile_constraints_override or {}),
        "family_registry_patch": _json_ready(family_registry_patch or {}),
        "feature_registry_patch": _json_ready(feature_registry_patch or {}),
        "search_action": str(search_action or "").strip() or None,
    }


def strategy_spec_hash(
    *,
    shape: str,
    strategy_profile: str,
    subject: str | None,
    universe_filter: dict[str, Any] | None,
    model_family: str,
    feature_groups: Iterable[str],
    profile_constraints_override: dict[str, Any] | None,
    family_registry_patch: dict[str, Any] | None = None,
    feature_registry_patch: dict[str, Any] | None = None,
    search_action: str | None = None,
) -> str:
    stable_payload = _stable_strategy_spec_payload(
        shape=shape,
        strategy_profile=strategy_profile,
        subject=subject,
        universe_filter=universe_filter,
        model_family=model_family,
        feature_groups=feature_groups,
        profile_constraints_override=profile_constraints_override,
        family_registry_patch=family_registry_patch,
        feature_registry_patch=feature_registry_patch,
        search_action=search_action,
    )
    encoded = json.dumps(stable_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _default_feature_groups(*, shape: str, model_family: str) -> list[str]:
    if str(shape) == "cross_sectional" and str(model_family) in {"carry_funding", "basis_divergence"}:
        return ["core_context", "derivatives"]
    return list(FEATURE_GROUPS)


def _normalize_promotion_path(value: Any) -> list[str]:
    provided = [str(item).strip() for item in list(value or []) if str(item).strip()]
    if not provided:
        return list(HYPOTHESIS_PROMOTION_PATH)
    return [item for item in provided if item in HYPOTHESIS_RESEARCH_LANES] or list(HYPOTHESIS_PROMOTION_PATH)


def _normalize_thesis_profile(
    thesis_profile: dict[str, Any] | None,
    *,
    strategy_id: str,
    shape: str,
    strategy_profile: str,
    model_family: str,
    subject: str | None,
    universe_filter: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(thesis_profile or {})
    if not payload:
        return {}
    thesis_id = str(payload.get("thesis_id") or strategy_id).strip() or strategy_id
    thesis_family = str(payload.get("thesis_family") or "").strip()
    universe_rule = payload.get("universe_rule")
    if universe_rule is None or universe_rule == "":
        if shape == "cross_sectional":
            universe_rule = dict(universe_filter or {})
        else:
            universe_rule = {"subject": str(subject).upper() if subject else None}
    execution_venue = str(payload.get("execution_venue") or ("perp" if shape == "cross_sectional" else "spot")).strip() or "spot"
    required_feature_columns = [
        str(item).strip()
        for item in list(payload.get("required_feature_columns") or [])
        if str(item).strip()
    ]
    requires_derivatives_features = bool(
        payload.get("requires_derivatives_features")
        if payload.get("requires_derivatives_features") is not None
        else (execution_venue == "perp" or any(column in DERIVATIVES_THESIS_FEATURE_COLUMNS for column in required_feature_columns))
    )
    return {
        "contract_version": THESIS_PROFILE_CONTRACT_VERSION,
        "thesis_id": thesis_id,
        "thesis_family": thesis_family,
        "market_mechanism": str(payload.get("market_mechanism") or "").strip(),
        "directional_claim": str(payload.get("directional_claim") or "").strip(),
        "universe_rule": _json_ready(universe_rule),
        "execution_venue": execution_venue,
        "requires_derivatives_features": requires_derivatives_features,
        "minimum_executable_history_days": int(payload.get("minimum_executable_history_days") or 0),
        "minimum_executable_coverage_ratio": float(payload.get("minimum_executable_coverage_ratio") or 0.0),
        "required_feature_columns": required_feature_columns,
        "factor_formula": str(payload.get("factor_formula") or model_family).strip() or model_family,
        "intended_holding_horizon_bars": int(payload.get("intended_holding_horizon_bars") or 0),
        "falsification_conditions": [
            str(item).strip()
            for item in list(payload.get("falsification_conditions") or [])
            if str(item).strip()
        ],
        "promotion_path": _normalize_promotion_path(payload.get("promotion_path")),
    }


def build_strategy_entry(
    *,
    strategy_id: str,
    shape: str,
    strategy_profile: str,
    subject: str | None,
    universe_filter: dict[str, Any] | None,
    model_family: str,
    feature_groups: Iterable[str] | None = None,
    profile_constraints_override: dict[str, Any] | None = None,
    source: str,
    status: str,
    created_at_utc: str | None = None,
    updated_at_utc: str | None = None,
    governance_week: str | None = None,
    governance_as_of: str | None = None,
    run_id: str | None = None,
    base_strategy_id: str | None = None,
    proposal_origin: str | None = None,
    search_action: str | None = None,
    parent_spec_hash: str | None = None,
    family_registry_patch: dict[str, Any] | None = None,
    feature_registry_patch: dict[str, Any] | None = None,
    priority_score: float | None = None,
    complexity_tier: str | None = None,
    risk_tags: Iterable[str] | None = None,
    auto_bridge_requested: bool | None = None,
    registry_snapshot_id: str | None = None,
    family_id: str | None = None,
    novelty_score: float | None = None,
    family_usage_count: int | None = None,
    failure_rate_rolling_8w: float | None = None,
    regime_fit_tag: str | None = None,
    discovery_pass_streak: int | None = None,
    last_discovery_pass_as_of: str | None = None,
    last_discovery_run_id: str | None = None,
    discovery_cadence: str | None = None,
    rationale: str | None = None,
    expected_edge: str | None = None,
    invalidates_if: str | None = None,
    data_dependencies: dict[str, Any] | None = None,
    review_priority: float | None = None,
    research_lane: str | None = None,
    promotion_eligibility: str | None = None,
    thesis_family: str | None = None,
    requires_derivatives_features: bool | None = None,
    daily_executable: bool | None = None,
    thesis_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in LIBRARY_STATUSES:
        raise ValueError(f"unsupported strategy status: {status}")
    selection_lane = selection_lane_for_lifecycle(status)
    normalized_feature_groups = list(feature_groups or _default_feature_groups(shape=shape, model_family=model_family))
    normalized_search_action = str(search_action or "parameter_tune")
    normalized_family_patch = _json_ready(family_registry_patch or {})
    normalized_feature_patch = _json_ready(feature_registry_patch or {})
    resolved_universe_filter = (
        {"liquidity_buckets": sorted(profile_constraints(strategy_profile)["allowed_liquidity_buckets"])}
        if shape == "cross_sectional" and (universe_filter is None or universe_filter == {})
        else universe_filter
    )
    spec_hash = strategy_spec_hash(
        shape=shape,
        strategy_profile=strategy_profile,
        subject=subject,
        universe_filter=resolved_universe_filter,
        model_family=model_family,
        feature_groups=normalized_feature_groups,
        profile_constraints_override=profile_constraints_override,
        family_registry_patch=normalized_family_patch,
        feature_registry_patch=normalized_feature_patch,
        search_action=normalized_search_action,
    )
    normalized_proposal_origin = str(
        proposal_origin
        or ("baseline" if source == "baseline" else "heuristic" if source in {"discovery", "proposal"} else source)
    ).strip() or "heuristic"
    normalized_complexity = str(complexity_tier or "medium").strip().lower() or "medium"
    resolved_family_id = str(family_id or model_family).strip() or str(model_family)
    resolved_governance_as_of = (
        normalize_governance_as_of(governance_as_of)
        if governance_as_of not in {None, ""}
        else None
    )
    resolved_run_id = None if run_id in {None, ""} else str(run_id)
    resolved_discovery_pass_streak = int(discovery_pass_streak if discovery_pass_streak is not None else 0)
    normalized_thesis_profile = _normalize_thesis_profile(
        thesis_profile,
        strategy_id=strategy_id,
        shape=shape,
        strategy_profile=strategy_profile,
        model_family=model_family,
        subject=str(subject).upper() if subject else None,
        universe_filter=resolved_universe_filter,
    )
    resolved_thesis_family = str(thesis_family or normalized_thesis_profile.get("thesis_family") or "").strip() or None
    resolved_requires_derivatives_features = bool(
        requires_derivatives_features
        if requires_derivatives_features is not None
        else normalized_thesis_profile.get("requires_derivatives_features", False)
    )
    resolved_research_lane = str(research_lane or "").strip()
    if not resolved_research_lane:
        resolved_research_lane = (
            CONTROL_BASELINE_LANE
            if source == "baseline"
            else str((normalized_thesis_profile.get("promotion_path") or [HYPOTHESIS_FACTOR_LANE])[0])
        )
    if resolved_research_lane not in RESEARCH_LANES:
        resolved_research_lane = CONTROL_BASELINE_LANE if source == "baseline" else HYPOTHESIS_FACTOR_LANE
    resolved_promotion_eligibility = str(promotion_eligibility or "").strip() or (
        "ineligible" if resolved_research_lane == CONTROL_BASELINE_LANE else "eligible"
    )
    if resolved_promotion_eligibility not in PROMOTION_ELIGIBILITY_VALUES:
        resolved_promotion_eligibility = "ineligible" if resolved_research_lane == CONTROL_BASELINE_LANE else "eligible"
    resolved_daily_executable = bool(
        daily_executable
        if daily_executable is not None
        else (
            resolved_research_lane in HYPOTHESIS_RESEARCH_LANES
            and not strategy_requires_temporal_event_tape(strategy_entry={"model_family": model_family})
        )
    )
    return {
        "strategy_id": strategy_id,
        "lifecycle": status,
        "shape": shape,
        "strategy_profile": strategy_profile,
        "subject": str(subject).upper() if subject else None,
        "universe_filter": _json_ready(resolved_universe_filter or {}),
        "model_family": model_family,
        "feature_groups": normalized_feature_groups,
        "profile_constraints": merged_profile_constraints(
            strategy_profile=strategy_profile,
            profile_constraints_override=profile_constraints_override,
        ),
        "profile_constraints_override": _json_ready(profile_constraints_override or {}),
        "spec_hash": spec_hash,
        "source": source,
        "base_strategy_id": base_strategy_id,
        "proposal_origin": normalized_proposal_origin,
        "search_action": normalized_search_action,
        "parent_spec_hash": None if parent_spec_hash in {None, ""} else str(parent_spec_hash),
        "family_registry_patch": normalized_family_patch,
        "feature_registry_patch": normalized_feature_patch,
        "priority_score": float(priority_score if priority_score is not None else 0.0),
        "complexity_tier": normalized_complexity,
        "risk_tags": [str(item) for item in (risk_tags or ()) if str(item).strip()],
        "auto_bridge_requested": bool(auto_bridge_requested),
        "registry_snapshot_id": None if registry_snapshot_id in {None, ""} else str(registry_snapshot_id),
        "family_id": resolved_family_id,
        "feature_family_ids": [
            str(item.get("family_id"))
            for item in _normalize_feature_registry_patch(feature_registry_patch)
            if str(item.get("family_id") or "").strip()
        ],
        "published_via": "not_published",
        "executable_signal": False,
        "novelty_score": float(novelty_score if novelty_score is not None else 0.0),
        "family_usage_count": int(family_usage_count if family_usage_count is not None else 0),
        "failure_rate_rolling_8w": float(failure_rate_rolling_8w if failure_rate_rolling_8w is not None else 0.0),
        "regime_fit_tag": str(regime_fit_tag or "generalist"),
        "rationale": str(rationale or "").strip(),
        "expected_edge": str(expected_edge or "").strip(),
        "invalidates_if": str(invalidates_if or "").strip(),
        "data_dependencies": _json_ready(data_dependencies or {}),
        "review_priority": float(review_priority if review_priority is not None else 0.0),
        "research_lane": resolved_research_lane,
        "promotion_eligibility": resolved_promotion_eligibility,
        "thesis_family": resolved_thesis_family,
        "requires_derivatives_features": resolved_requires_derivatives_features,
        "daily_executable": resolved_daily_executable,
        "thesis_profile": normalized_thesis_profile,
        "created_at_utc": created_at_utc or utc_now(),
        "updated_at_utc": updated_at_utc or utc_now(),
        "governance_week": governance_week,
        "governance_as_of": resolved_governance_as_of,
        "run_id": resolved_run_id,
        "daily_pass_streak": 0,
        "daily_fail_streak": 0,
        "daily_result_window": [],
        "watch_pass_streak": 0,
        "watch_result_window": [],
        "weekly_pass_streak": resolved_discovery_pass_streak,
        "last_weekly_pass_week": governance_week if resolved_discovery_pass_streak > 0 else None,
        "discovery_pass_streak": resolved_discovery_pass_streak,
        "last_discovery_pass_as_of": (
            normalize_governance_as_of(last_discovery_pass_as_of)
            if last_discovery_pass_as_of not in {None, ""}
            else None
        ),
        "last_discovery_run_id": None if last_discovery_run_id in {None, ""} else str(last_discovery_run_id),
        "discovery_cadence": str(discovery_cadence or "daily_full"),
        "last_daily_as_of": None,
        "last_daily_experiment_status": None,
        "last_transition_reason": "bootstrap" if source == "baseline" else "proposal_created",
        "monitoring_status": status,
        "selection_lane": selection_lane,
        "promotion_state": promotion_state_for_lifecycle(status),
    }


def _json_ready(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def merged_profile_constraints(*, strategy_profile: str, profile_constraints_override: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(profile_constraints(strategy_profile))
    override = dict(profile_constraints_override or {})
    if not override:
        return _json_ready(base)
    merged = dict(base)
    merged.update(override)
    return _json_ready(merged)


def validate_profile_constraints_override(
    *,
    strategy_profile: str,
    override: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    if not override:
        return True, None
    base = dict(profile_constraints(strategy_profile))
    candidate = merged_profile_constraints(strategy_profile=strategy_profile, profile_constraints_override=override)
    allowed_buckets = set(base["allowed_liquidity_buckets"])
    proposed_buckets = set(candidate.get("allowed_liquidity_buckets", []))
    if not proposed_buckets.issubset(allowed_buckets):
        return False, "allowed_liquidity_buckets override cannot widen the base profile envelope"
    if float(candidate["max_gross_leverage"]) > float(base["max_gross_leverage"]):
        return False, "max_gross_leverage override cannot exceed the base profile"
    if bool(candidate["short_allowed"]) and not bool(base["short_allowed"]):
        return False, "short_allowed override cannot enable shorting beyond the base profile"
    if bool(candidate["long_only"]) != bool(base["long_only"]) and bool(base["long_only"]):
        return False, "long_only override cannot loosen the base profile"
    if float(candidate["short_leverage"]) > float(base["short_leverage"]):
        return False, "short_leverage override cannot exceed the base profile"
    if float(candidate["long_leverage"]) > float(base["long_leverage"]):
        return False, "long_leverage override cannot exceed the base profile"
    return True, None


def normalize_proposal_spec(proposal_spec: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(proposal_spec)
    normalized.setdefault("proposal_origin", "heuristic")
    normalized.setdefault("search_action", "parameter_tune")
    normalized.setdefault("parent_spec_hash", None)
    normalized.setdefault("family_registry_patch", {})
    normalized.setdefault("feature_registry_patch", {})
    normalized.setdefault("priority_score", 0.0)
    normalized.setdefault("complexity_tier", "medium")
    normalized.setdefault("risk_tags", [])
    normalized.setdefault("auto_bridge_requested", False)
    normalized.setdefault("registry_snapshot_id", None)
    normalized.setdefault("family_id", str(normalized.get("model_family") or ""))
    normalized.setdefault("source", "proposal")
    normalized.setdefault(
        "data_dependencies",
        _normalize_data_dependencies(
            shape=str(normalized.get("shape") or ""),
            feature_groups=normalized.get("feature_groups"),
            payload=normalized.get("data_dependencies"),
        ),
    )
    normalized.setdefault(
        "review_priority",
        _default_review_priority(
            lifecycle="candidate" if str(normalized.get("base_strategy_id") or "").strip() else "discovery"
        ),
    )
    if "spec_hash" not in normalized or not str(normalized.get("spec_hash") or "").strip():
        normalized["spec_hash"] = strategy_spec_hash(
            shape=str(normalized.get("shape") or ""),
            strategy_profile=str(normalized.get("strategy_profile") or ""),
            subject=normalized.get("subject"),
            universe_filter=normalized.get("universe_filter"),
            model_family=str(normalized.get("model_family") or ""),
            feature_groups=list(normalized.get("feature_groups") or []),
            profile_constraints_override=normalized.get("profile_constraints_override"),
            family_registry_patch=normalized.get("family_registry_patch"),
            feature_registry_patch=normalized.get("feature_registry_patch"),
            search_action=str(normalized.get("search_action") or "parameter_tune"),
        )
    return normalized


def proposal_complexity_penalty(proposal_spec: dict[str, Any]) -> float:
    normalized = normalize_proposal_spec(proposal_spec)
    return float(COMPLEXITY_TIERS.get(str(normalized.get("complexity_tier") or "medium"), 0.5))


def proposal_duplicate_penalty(
    proposal_spec: dict[str, Any],
    *,
    seen_specs: list[dict[str, Any]],
) -> float:
    normalized = normalize_proposal_spec(proposal_spec)
    spec_hash = str(normalized.get("spec_hash") or "")
    base_strategy_id = str(normalized.get("base_strategy_id") or "")
    family_id = str(normalized.get("family_id") or normalized.get("model_family") or "")
    feature_key = tuple(sorted(str(item) for item in normalized.get("feature_groups", [])))
    for seen in seen_specs:
        current = normalize_proposal_spec(seen)
        if str(current.get("spec_hash") or "") == spec_hash:
            return 1.0
        if (
            str(current.get("base_strategy_id") or "") == base_strategy_id
            and str(current.get("family_id") or current.get("model_family") or "") == family_id
            and tuple(sorted(str(item) for item in current.get("feature_groups", []))) == feature_key
        ):
            return 0.5
    return 0.0


def proposal_ranking_score(
    proposal_spec: dict[str, Any],
    *,
    seen_specs: list[dict[str, Any]],
) -> float:
    normalized = normalize_proposal_spec(proposal_spec)
    priority_score = float(normalized.get("priority_score", 0.0) or 0.0)
    return priority_score - proposal_duplicate_penalty(normalized, seen_specs=seen_specs) - proposal_complexity_penalty(normalized)


def _contains_unsafe_patch_text(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_unsafe_patch_text(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unsafe_patch_text(item) for item in value)
    return bool(UNSAFE_PATCH_PATTERN.search(str(value)))


def _validate_model_registry_patch(*, patch: dict[str, Any] | None, shape: str) -> tuple[bool, str | None]:
    for family in _normalize_model_registry_patch(patch):
        if _contains_unsafe_patch_text(family):
            return False, f"model registry patch for {family['family_id']} contains unsafe code-like text"
        if str(family.get("engine_template") or "") not in MODEL_ENGINE_TEMPLATES:
            return False, f"model registry patch engine_template is unsupported for {family['family_id']}"
        allowed_shapes = [str(item) for item in family.get("allowed_shapes", []) if str(item).strip()]
        if shape not in allowed_shapes:
            return False, f"model registry patch for {family['family_id']} does not allow shape={shape}"
        hyperparameters = dict(family.get("hyperparameters") or {})
        if len(hyperparameters) > MAX_MODEL_HYPERPARAMETERS:
            return False, f"model registry patch for {family['family_id']} exceeds max hyperparameters={MAX_MODEL_HYPERPARAMETERS}"
    return True, None


def _validate_feature_registry_patch(*, patch: dict[str, Any] | None) -> tuple[bool, str | None]:
    interaction_count = 0
    generated_feature_count = 0
    for family in _normalize_feature_registry_patch(patch):
        if _contains_unsafe_patch_text(family):
            return False, f"feature registry patch for {family['family_id']} contains unsafe code-like text"
        transforms = [dict(item) for item in family.get("transforms", []) if isinstance(item, dict)]
        generated_feature_count += len(transforms)
        if generated_feature_count > MAX_PROPOSAL_SELECTED_FEATURES:
            return False, f"feature registry patch exceeds max selected features={MAX_PROPOSAL_SELECTED_FEATURES}"
        for transform in transforms:
            transform_name = str(transform.get("transform") or "").strip()
            if transform_name not in FEATURE_FAMILY_TRANSFORMS:
                return False, f"feature transform {transform_name} is unsupported"
            if transform_name == "interaction":
                interaction_count += 1
                if interaction_count > MAX_INTERACTION_FEATURES:
                    return False, f"feature registry patch exceeds max interaction features={MAX_INTERACTION_FEATURES}"
            if "source_column" in transform and "target_" in str(transform.get("source_column") or ""):
                return False, "feature registry patch cannot reference future or target columns"
            if int(transform.get("lag_bars", transform.get("periods", 1)) or 1) < 0:
                return False, "feature registry patch cannot use future-looking negative lags"
    return True, None


def bootstrap_strategy_library(
    *,
    artifacts_root: Path,
    as_of: str,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> dict[str, Any]:
    del universe_candidates
    payload = _build_thesis_task_library_payload(
        bootstrapped_as_of=normalize_governance_as_of(as_of),
        existing_entries=[],
    )
    save_strategy_library(artifacts_root=artifacts_root, payload=payload)
    payload["path"] = str(strategy_library_path(artifacts_root=artifacts_root))
    return payload


def _expected_baseline_entries(
    *,
    as_of: str,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> list[dict[str, Any]]:
    created_at = utc_now()
    entries: list[dict[str, Any]] = []
    for candidate in universe_candidates:
        for strategy_profile in STRATEGY_PROFILES:
            if candidate.liquidity_bucket not in profile_constraints(strategy_profile)["allowed_liquidity_buckets"]:
                continue
            for model_family in SINGLE_ASSET_MODELS:
                strategy_id = f"baseline-{slugify(candidate.subject)}-{strategy_profile}-{slugify(model_family)}-single-asset"
                entries.append(
                    build_strategy_entry(
                        strategy_id=strategy_id,
                        shape="single_asset",
                        strategy_profile=strategy_profile,
                        subject=candidate.subject,
                        universe_filter=None,
                        model_family=model_family,
                        source="baseline",
                        status=target_lifecycle_for_strategy_id(strategy_id),
                        created_at_utc=created_at,
                        updated_at_utc=created_at,
                        governance_week=iso_week_label(as_of),
                    )
                )
    for strategy_profile in STRATEGY_PROFILES:
        strategy_universe = {"liquidity_buckets": sorted(profile_constraints(strategy_profile)["allowed_liquidity_buckets"])}
        for model_family in ALLOWED_CROSS_SECTION_MODELS:
            strategy_id = f"baseline-{strategy_profile}-{slugify(model_family)}-cross-sectional"
            entries.append(
                build_strategy_entry(
                    strategy_id=strategy_id,
                    shape="cross_sectional",
                    strategy_profile=strategy_profile,
                    subject=None,
                    universe_filter=strategy_universe,
                    model_family=model_family,
                    source="baseline",
                    status=target_lifecycle_for_strategy_id(strategy_id),
                    created_at_utc=created_at,
                    updated_at_utc=created_at,
                    governance_week=iso_week_label(as_of),
                )
            )
    return entries


def _sync_baseline_strategy_entries(
    *,
    payload: dict[str, Any],
    as_of: str,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> dict[str, Any]:
    entries_by_id = {
        str(entry["strategy_id"]): normalize_strategy_library_entry(entry)
        for entry in payload.get("entries", [])
        if isinstance(entry, dict) and entry.get("strategy_id")
    }
    for expected in _expected_baseline_entries(as_of=as_of, universe_candidates=universe_candidates):
        strategy_id = str(expected["strategy_id"])
        if strategy_id in entries_by_id:
            current = dict(entries_by_id[strategy_id])
            current["feature_groups"] = list(expected["feature_groups"])
            current["profile_constraints"] = dict(expected["profile_constraints"])
            current["universe_filter"] = dict(expected["universe_filter"])
            current["updated_at_utc"] = utc_now()
            entries_by_id[strategy_id] = normalize_strategy_library_entry(current)
            continue
        entries_by_id[strategy_id] = normalize_strategy_library_entry(expected)
    payload["entries"] = [entries_by_id[key] for key in sorted(entries_by_id)]
    payload["library_version"] = STRATEGY_LIBRARY_VERSION
    payload["generated_at_utc"] = utc_now()
    return payload


def normalize_strategy_library_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    legacy_status = normalized.pop("status", None)
    lifecycle = str(normalized.get("lifecycle") or legacy_status or "").strip()
    if not lifecycle:
        lifecycle = "active"
    normalized["lifecycle"] = lifecycle
    normalized.setdefault(
        "feature_groups",
        _default_feature_groups(
            shape=str(normalized.get("shape") or ""),
            model_family=str(normalized.get("model_family") or ""),
        ),
    )
    normalized.setdefault("universe_filter", {})
    normalized.setdefault("profile_constraints_override", {})
    normalized["universe_filter"] = _json_ready(normalized.get("universe_filter", {}))
    normalized["profile_constraints_override"] = _json_ready(normalized.get("profile_constraints_override", {}))
    normalized["profile_constraints"] = merged_profile_constraints(
        strategy_profile=str(normalized["strategy_profile"]),
        profile_constraints_override=normalized.get("profile_constraints_override"),
    )
    normalized["spec_hash"] = strategy_spec_hash(
        shape=str(normalized["shape"]),
        strategy_profile=str(normalized["strategy_profile"]),
        subject=normalized.get("subject"),
        universe_filter=normalized.get("universe_filter"),
        model_family=str(normalized["model_family"]),
        feature_groups=normalized.get("feature_groups", []),
        profile_constraints_override=normalized.get("profile_constraints_override"),
        family_registry_patch=normalized.get("family_registry_patch"),
        feature_registry_patch=normalized.get("feature_registry_patch"),
        search_action=str(normalized.get("search_action") or "parameter_tune"),
    )
    normalized.setdefault("source", "baseline")
    normalized.setdefault("proposal_origin", "baseline" if str(normalized.get("source") or "") == "baseline" else "heuristic")
    normalized.setdefault("search_action", "parameter_tune")
    normalized.setdefault("parent_spec_hash", None)
    normalized.setdefault("family_registry_patch", {})
    normalized.setdefault("feature_registry_patch", {})
    normalized.setdefault("priority_score", 0.0)
    normalized.setdefault("complexity_tier", "medium")
    normalized.setdefault("risk_tags", [])
    normalized.setdefault("auto_bridge_requested", False)
    normalized.setdefault("registry_snapshot_id", None)
    normalized.setdefault("family_id", str(normalized.get("model_family") or ""))
    normalized.setdefault(
        "feature_family_ids",
        [
            str(item.get("family_id"))
            for item in _normalize_feature_registry_patch(normalized.get("feature_registry_patch"))
            if str(item.get("family_id") or "").strip()
        ],
    )
    normalized.setdefault("published_via", "not_published")
    normalized.setdefault("executable_signal", False)
    normalized.setdefault("novelty_score", 0.0)
    normalized.setdefault("family_usage_count", 0)
    normalized.setdefault("failure_rate_rolling_8w", 0.0)
    normalized.setdefault("regime_fit_tag", "generalist")
    normalized["thesis_profile"] = _normalize_thesis_profile(
        normalized.get("thesis_profile"),
        strategy_id=str(normalized.get("strategy_id") or ""),
        shape=str(normalized.get("shape") or ""),
        strategy_profile=str(normalized.get("strategy_profile") or ""),
        model_family=str(normalized.get("model_family") or ""),
        subject=normalized.get("subject"),
        universe_filter=normalized.get("universe_filter"),
    )
    normalized.setdefault(
        "research_lane",
        CONTROL_BASELINE_LANE if str(normalized.get("source") or "") == "baseline" else HYPOTHESIS_FACTOR_LANE,
    )
    normalized.setdefault(
        "promotion_eligibility",
        "ineligible" if str(normalized.get("research_lane") or "") == CONTROL_BASELINE_LANE else "eligible",
    )
    normalized["thesis_family"] = (
        str(normalized.get("thesis_family") or normalized["thesis_profile"].get("thesis_family") or "").strip() or None
    )
    normalized["requires_derivatives_features"] = bool(
        normalized.get("requires_derivatives_features")
        if normalized.get("requires_derivatives_features") is not None
        else normalized["thesis_profile"].get("requires_derivatives_features", False)
    )
    default_rationale, default_expected_edge, default_invalidates_if = _default_task_thesis(
        shape=str(normalized.get("shape") or ""),
        subject=normalized.get("subject"),
        strategy_profile=str(normalized.get("strategy_profile") or ""),
        model_family=str(normalized.get("model_family") or ""),
    )
    normalized.setdefault("rationale", default_rationale)
    normalized.setdefault("expected_edge", default_expected_edge)
    normalized.setdefault("invalidates_if", default_invalidates_if)
    normalized["rationale"] = str(normalized.get("rationale") or default_rationale).strip() or default_rationale
    normalized["expected_edge"] = (
        str(normalized.get("expected_edge") or default_expected_edge).strip() or default_expected_edge
    )
    normalized["invalidates_if"] = (
        str(normalized.get("invalidates_if") or default_invalidates_if).strip() or default_invalidates_if
    )
    normalized["data_dependencies"] = _normalize_data_dependencies(
        shape=str(normalized.get("shape") or ""),
        feature_groups=normalized.get("feature_groups"),
        payload=normalized.get("data_dependencies"),
    )
    normalized["review_priority"] = float(
        normalized.get("review_priority")
        if normalized.get("review_priority") not in {None, ""}
        else _default_review_priority(lifecycle=str(normalized.get("lifecycle") or ""))
    )
    normalized.setdefault("created_at_utc", utc_now())
    normalized.setdefault("updated_at_utc", normalized["created_at_utc"])
    normalized.setdefault("governance_week", None)
    normalized.setdefault("governance_as_of", None)
    if normalized.get("governance_as_of") in {None, ""}:
        last_daily_as_of = str(normalized.get("last_daily_as_of") or "").strip()
        normalized["governance_as_of"] = normalize_governance_as_of(last_daily_as_of) if last_daily_as_of else None
    normalized.setdefault("run_id", None)
    normalized.setdefault("base_strategy_id", None)
    normalized.setdefault("daily_pass_streak", 0)
    normalized.setdefault("daily_fail_streak", 0)
    normalized.setdefault("daily_result_window", [])
    normalized.setdefault("watch_pass_streak", 0)
    normalized.setdefault("watch_result_window", [])
    normalized.setdefault("weekly_pass_streak", 0)
    normalized.setdefault("last_weekly_pass_week", None)
    normalized.setdefault("discovery_pass_streak", int(normalized.get("weekly_pass_streak", 0) or 0))
    normalized.setdefault("last_discovery_pass_as_of", normalized.get("governance_as_of"))
    normalized.setdefault("last_discovery_run_id", normalized.get("run_id"))
    normalized.setdefault("discovery_cadence", "daily_full")
    normalized.setdefault("last_daily_as_of", None)
    normalized.setdefault("last_daily_experiment_status", None)
    normalized.setdefault("last_factor_evidence_evaluated", None)
    normalized.setdefault("last_factor_evidence_passed", None)
    normalized.setdefault("last_transition_reason", "loaded")
    if str(normalized.get("published_via") or "") == "same_week_auto_bridge":
        normalized["published_via"] = "same_day_auto_bridge"
    lifecycle = str(normalized.get("lifecycle", "active"))
    normalized.setdefault("monitoring_status", lifecycle)
    normalized.setdefault("selection_lane", selection_lane_for_lifecycle(lifecycle))
    normalized.setdefault("promotion_state", promotion_state_for_lifecycle(lifecycle))
    requested_daily_executable = bool(
        normalized.get("daily_executable")
        if normalized.get("daily_executable") is not None
        else str(normalized.get("research_lane") or "") in HYPOTHESIS_RESEARCH_LANES
    )
    normalized["daily_executable"] = is_daily_executable_strategy(
        strategy_entry={**normalized, "daily_executable": requested_daily_executable}
    )
    normalized.setdefault("factor_gate_fail_streak", 0)
    normalized.setdefault("factor_gate_pass_streak", 0)
    normalized.setdefault("portfolio_validation_pass_streak", 0)
    normalized.setdefault("portfolio_validation_fail_streak", 0)
    normalized.setdefault("model_overlay_ready", False)
    normalized.setdefault("model_overlay_ready_as_of", None)
    normalized.setdefault("leakage_audit_required_at_utc", None)
    normalized.setdefault("thesis_archived_reason", None)
    return normalized


def _normalized_bootstrapped_as_of(value: Any) -> str:
    normalized = str(value or "").strip()
    if len(normalized) >= 10:
        return normalize_governance_as_of(normalized[:10])
    return normalize_governance_as_of(utc_now()[:10])


def _thesis_task_serializable_entry(entry: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "strategy_id",
        "lifecycle",
        "shape",
        "strategy_profile",
        "subject",
        "universe_filter",
        "model_family",
        "feature_groups",
        "profile_constraints_override",
        "spec_hash",
        "source",
        "base_strategy_id",
        "family_id",
        "rationale",
        "expected_edge",
        "invalidates_if",
        "data_dependencies",
        "review_priority",
        "research_lane",
        "promotion_eligibility",
        "thesis_family",
        "requires_derivatives_features",
        "daily_executable",
        "thesis_profile",
        "created_at_utc",
        "updated_at_utc",
        "governance_week",
        "governance_as_of",
        "run_id",
        "daily_pass_streak",
        "daily_fail_streak",
        "daily_result_window",
        "watch_pass_streak",
        "watch_result_window",
        "weekly_pass_streak",
        "last_weekly_pass_week",
        "discovery_pass_streak",
        "last_discovery_pass_as_of",
        "last_discovery_run_id",
        "discovery_cadence",
        "last_daily_as_of",
        "last_daily_experiment_status",
        "last_factor_evidence_evaluated",
        "last_factor_evidence_passed",
        "last_transition_reason",
        "monitoring_status",
        "selection_lane",
        "promotion_state",
        "published_via",
        "executable_signal",
        "factor_gate_fail_streak",
        "factor_gate_pass_streak",
        "portfolio_validation_pass_streak",
        "portfolio_validation_fail_streak",
        "model_overlay_ready",
        "model_overlay_ready_as_of",
        "leakage_audit_required_at_utc",
        "thesis_archived_reason",
    }
    return {
        key: _json_ready(entry[key])
        for key in allowed_keys
        if key in entry
    }


def _preserved_thesis_task_state(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    preserved_keys = {
        "lifecycle",
        "research_lane",
        "promotion_eligibility",
        "daily_executable",
        "governance_week",
        "governance_as_of",
        "run_id",
        "daily_pass_streak",
        "daily_fail_streak",
        "daily_result_window",
        "watch_pass_streak",
        "watch_result_window",
        "weekly_pass_streak",
        "last_weekly_pass_week",
        "discovery_pass_streak",
        "last_discovery_pass_as_of",
        "last_discovery_run_id",
        "discovery_cadence",
        "last_daily_as_of",
        "last_daily_experiment_status",
        "last_factor_evidence_evaluated",
        "last_factor_evidence_passed",
        "last_transition_reason",
        "monitoring_status",
        "selection_lane",
        "promotion_state",
        "published_via",
        "executable_signal",
        "factor_gate_fail_streak",
        "factor_gate_pass_streak",
        "portfolio_validation_pass_streak",
        "portfolio_validation_fail_streak",
        "model_overlay_ready",
        "model_overlay_ready_as_of",
        "leakage_audit_required_at_utc",
        "thesis_archived_reason",
    }
    return {
        key: _json_ready(entry[key])
        for key in preserved_keys
        if key in entry
    }


def _seed_entry_from_manifest_item(
    *,
    seed: dict[str, Any],
    bootstrapped_as_of: str,
    preserved_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    strategy_id = str(seed["strategy_id"])
    preserved_entry = _repair_legacy_seed_archive_after_readiness_gate_rewrite(
        seed=seed,
        bootstrapped_as_of=bootstrapped_as_of,
        preserved_entry=preserved_entry,
    )
    target_lifecycle = str(seed.get("lifecycle") or target_lifecycle_for_strategy_id(strategy_id))
    default_rationale, default_expected_edge, default_invalidates_if = _default_task_thesis(
        shape=str(seed.get("shape") or ""),
        subject=seed.get("subject"),
        strategy_profile=str(seed.get("strategy_profile") or ""),
        model_family=str(seed.get("model_family") or ""),
    )
    created_at = str((preserved_entry or {}).get("created_at_utc") or utc_now())
    entry = build_strategy_entry(
        strategy_id=strategy_id,
        shape=str(seed["shape"]),
        strategy_profile=str(seed["strategy_profile"]),
        subject=seed.get("subject"),
        universe_filter=seed.get("universe_filter"),
        model_family=str(seed["model_family"]),
        feature_groups=seed.get("feature_groups"),
        profile_constraints_override=seed.get("profile_constraints_override"),
        source=str(seed.get("source") or "baseline"),
        status=target_lifecycle,
        created_at_utc=created_at,
        updated_at_utc=utc_now(),
        governance_week=iso_week_label(bootstrapped_as_of),
        governance_as_of=bootstrapped_as_of,
        family_id=seed.get("family_id"),
        rationale=str(seed.get("rationale") or default_rationale),
        expected_edge=str(seed.get("expected_edge") or default_expected_edge),
        invalidates_if=str(seed.get("invalidates_if") or default_invalidates_if),
        data_dependencies=_normalize_data_dependencies(
            shape=str(seed.get("shape") or ""),
            feature_groups=seed.get("feature_groups"),
            payload=seed.get("data_dependencies"),
        ),
        review_priority=float(
            seed.get("review_priority")
            if seed.get("review_priority") not in {None, ""}
            else _default_review_priority(lifecycle=target_lifecycle)
        ),
        research_lane=seed.get("research_lane"),
        promotion_eligibility=seed.get("promotion_eligibility"),
        thesis_family=seed.get("thesis_family"),
        requires_derivatives_features=seed.get("requires_derivatives_features"),
        daily_executable=seed.get("daily_executable"),
        thesis_profile=seed.get("thesis_profile"),
    )
    for key, value in _preserved_thesis_task_state(preserved_entry).items():
        entry[key] = value
    entry["lifecycle"] = str(entry.get("lifecycle") or target_lifecycle)
    entry["monitoring_status"] = str(entry.get("monitoring_status") or entry["lifecycle"])
    entry["selection_lane"] = selection_lane_for_lifecycle(entry["lifecycle"])
    entry["promotion_state"] = str(entry.get("promotion_state") or promotion_state_for_lifecycle(entry["lifecycle"]))
    entry["updated_at_utc"] = utc_now()
    return normalize_strategy_library_entry(entry)


def _repair_legacy_seed_archive_after_readiness_gate_rewrite(
    *,
    seed: dict[str, Any],
    bootstrapped_as_of: str,
    preserved_entry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(preserved_entry, dict):
        return preserved_entry
    if str(seed.get("research_lane") or "").strip() != HYPOTHESIS_FACTOR_LANE:
        return preserved_entry
    if str(preserved_entry.get("thesis_archived_reason") or "").strip() != "factor_evidence_failed_twice":
        return preserved_entry
    if str(preserved_entry.get("last_daily_experiment_status") or "").strip() != "invalidated":
        return preserved_entry
    if preserved_entry.get("last_factor_evidence_evaluated") is not None:
        return preserved_entry

    strategy_id = str(seed.get("strategy_id") or "").strip()
    target_lifecycle = str(seed.get("lifecycle") or target_lifecycle_for_strategy_id(strategy_id))
    repaired = dict(preserved_entry)
    repaired.update(
        {
            "lifecycle": target_lifecycle,
            "monitoring_status": target_lifecycle,
            "selection_lane": selection_lane_for_lifecycle(target_lifecycle),
            "promotion_state": promotion_state_for_lifecycle(target_lifecycle),
            "promotion_eligibility": str(seed.get("promotion_eligibility") or "eligible"),
            "daily_executable": bool(seed.get("daily_executable", True)),
            "factor_gate_fail_streak": 0,
            "factor_gate_pass_streak": 0,
            "portfolio_validation_pass_streak": 0,
            "portfolio_validation_fail_streak": 0,
            "model_overlay_ready": False,
            "model_overlay_ready_as_of": None,
            "thesis_archived_reason": None,
            "leakage_audit_required_at_utc": None,
            "last_daily_as_of": None,
            "last_daily_experiment_status": None,
            "last_factor_evidence_evaluated": None,
            "last_factor_evidence_passed": None,
            "last_transition_reason": "restored_after_readiness_gate_rewrite",
            "updated_at_utc": utc_now(),
            "governance_as_of": normalize_governance_as_of(bootstrapped_as_of),
            "governance_week": iso_week_label(bootstrapped_as_of),
        }
    )
    return repaired


def _build_thesis_task_library_payload(
    *,
    bootstrapped_as_of: str,
    existing_entries: list[dict[str, Any]] | None = None,
    preserve_extra_entries: bool = False,
) -> dict[str, Any]:
    existing_by_id = {
        str(entry.get("strategy_id")): normalize_strategy_library_entry(entry)
        for entry in (existing_entries or [])
        if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
    }
    seed_entries = [
        _seed_entry_from_manifest_item(
            seed=seed,
            bootstrapped_as_of=bootstrapped_as_of,
            preserved_entry=existing_by_id.get(str(seed.get("strategy_id") or "")),
        )
        for seed in _thesis_seed_entries()
    ]
    seed_ids = {
        str(entry.get("strategy_id") or "").strip()
        for entry in seed_entries
        if str(entry.get("strategy_id") or "").strip()
    }
    extra_entries = (
        [
            normalize_strategy_library_entry(entry)
            for entry in (existing_entries or [])
            if isinstance(entry, dict)
            and str(entry.get("strategy_id") or "").strip()
            and str(entry.get("strategy_id") or "").strip() not in seed_ids
        ]
        if preserve_extra_entries
        else []
    )
    entries = seed_entries + extra_entries
    payload = {
        "library_version": STRATEGY_LIBRARY_VERSION,
        "library_mode": THESIS_TASK_LIBRARY_MODE,
        "generated_at_utc": utc_now(),
        "bootstrapped_as_of": bootstrapped_as_of,
        "entries": entries,
    }
    _validate_strategy_library_payload(payload=payload)
    return payload


def migrate_strategy_library_payload(payload: dict[str, Any]) -> dict[str, Any]:
    current_mode = str(payload.get("library_mode") or "").strip()
    bootstrapped_as_of = _normalized_bootstrapped_as_of(
        payload.get("bootstrapped_as_of") or payload.get("generated_at_utc") or utc_now()
    )
    raw_entries = [dict(entry) for entry in payload.get("entries", []) if isinstance(entry, dict)]
    if current_mode == THESIS_TASK_LIBRARY_MODE:
        migrated = _build_thesis_task_library_payload(
            bootstrapped_as_of=bootstrapped_as_of,
            existing_entries=[normalize_strategy_library_entry(entry) for entry in raw_entries],
            preserve_extra_entries=True,
        )
        _validate_strategy_library_payload(payload=migrated)
        return migrated
    return _build_thesis_task_library_payload(
        bootstrapped_as_of=bootstrapped_as_of,
        existing_entries=[normalize_strategy_library_entry(entry) for entry in raw_entries],
    )


def load_strategy_library(*, artifacts_root: Path) -> dict[str, Any]:
    path = strategy_library_path(artifacts_root=artifacts_root)
    if not path.exists():
        raise FileNotFoundError(f"strategy library not found: {path}")
    payload = read_json(path)
    payload["library_version"] = int(payload.get("library_version") or 1)
    payload["library_mode"] = (
        str(payload.get("library_mode") or "").strip()
        or (THESIS_TASK_LIBRARY_MODE if payload["library_version"] >= STRATEGY_LIBRARY_VERSION else "legacy_inventory")
    )
    if payload["library_mode"] != THESIS_TASK_LIBRARY_MODE or payload["library_version"] < STRATEGY_LIBRARY_VERSION:
        payload = migrate_strategy_library_payload(payload)
    else:
        payload["entries"] = [
            normalize_strategy_library_entry(entry)
            for entry in payload.get("entries", [])
            if isinstance(entry, dict)
        ]
    _validate_strategy_library_payload(payload=payload)
    payload["path"] = str(path)
    return payload


def save_strategy_library(*, artifacts_root: Path, payload: dict[str, Any]) -> None:
    path = strategy_library_path(artifacts_root=artifacts_root)
    library_version = int(payload.get("library_version") or STRATEGY_LIBRARY_VERSION)
    library_mode = (
        str(payload.get("library_mode") or "").strip()
        or (THESIS_TASK_LIBRARY_MODE if library_version >= STRATEGY_LIBRARY_VERSION else "legacy_inventory")
    )
    normalized_entries = [
        normalize_strategy_library_entry(dict(entry))
        for entry in payload.get("entries", [])
        if isinstance(entry, dict)
    ]
    serializable = {
        "library_version": library_version,
        "library_mode": library_mode,
        "generated_at_utc": payload.get("generated_at_utc", utc_now()),
        "bootstrapped_as_of": _normalized_bootstrapped_as_of(
            payload.get("bootstrapped_as_of") or payload.get("generated_at_utc") or utc_now()
        ),
        "entries": (
            [_thesis_task_serializable_entry(entry) for entry in normalized_entries]
            if library_mode == THESIS_TASK_LIBRARY_MODE
            else [_json_ready(entry) for entry in normalized_entries]
        ),
    }
    _validate_strategy_library_payload(payload=serializable)
    write_json(path, serializable)


def ensure_strategy_library(
    *,
    artifacts_root: Path,
    as_of: str,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> dict[str, Any]:
    del universe_candidates
    path = strategy_library_path(artifacts_root=artifacts_root)
    if not path.exists():
        return bootstrap_strategy_library(artifacts_root=artifacts_root, as_of=as_of, universe_candidates=())
    payload = load_strategy_library(artifacts_root=artifacts_root)
    if int(payload.get("library_version") or 1) < STRATEGY_LIBRARY_VERSION or str(payload.get("library_mode") or "") != THESIS_TASK_LIBRARY_MODE:
        payload = migrate_strategy_library_payload(payload)
    else:
        payload = _build_thesis_task_library_payload(
            bootstrapped_as_of=_normalized_bootstrapped_as_of(payload.get("bootstrapped_as_of") or as_of),
            existing_entries=[
                normalize_strategy_library_entry(entry)
                for entry in payload.get("entries", [])
                if isinstance(entry, dict)
            ],
            preserve_extra_entries=True,
        )
    payload["generated_at_utc"] = utc_now()
    payload["bootstrapped_as_of"] = _normalized_bootstrapped_as_of(payload.get("bootstrapped_as_of") or as_of)
    save_strategy_library(artifacts_root=artifacts_root, payload=payload)
    payload["path"] = str(path)
    return payload


def cutover_strategy_library_to_thesis_tasks(
    *,
    artifacts_root: Path,
    as_of: str,
) -> dict[str, Any]:
    resolved_as_of = normalize_governance_as_of(as_of)
    path = strategy_library_path(artifacts_root=artifacts_root)
    archive_root = strategy_library_cutover_archive_path(artifacts_root=artifacts_root, as_of=resolved_as_of)
    archive_root.mkdir(parents=True, exist_ok=True)
    archived_library_path = archive_root / "strategy_library.pre_cutover.json"
    existing_payload = read_json(path) if path.exists() else None
    if existing_payload is not None:
        write_json(archived_library_path, existing_payload)
    migrated = _build_thesis_task_library_payload(
        bootstrapped_as_of=resolved_as_of,
        existing_entries=[
            normalize_strategy_library_entry(entry)
            for entry in (existing_payload or {}).get("entries", [])
            if isinstance(entry, dict)
        ],
        preserve_extra_entries=False,
    )
    save_strategy_library(artifacts_root=artifacts_root, payload=migrated)
    refreshed = load_strategy_library(artifacts_root=artifacts_root)
    metrics = strategy_library_metrics(strategy_library=refreshed)
    summary = {
        "generated_at_utc": utc_now(),
        "as_of": resolved_as_of,
        "archive_root": str(archive_root),
        "archived_strategy_library_path": str(archived_library_path) if archived_library_path.exists() else None,
        "previous_entry_count": len((existing_payload or {}).get("entries", [])) if isinstance(existing_payload, dict) else 0,
        "strategy_library_path": str(path),
        "library_mode": refreshed.get("library_mode"),
        "entry_count": metrics["entry_count"],
        "shape_mix": metrics["shape_mix"],
        "lifecycle_mix": metrics["lifecycle_mix"],
        "daily_inventory_utilization_target": metrics["daily_inventory_utilization_target"],
        "seed_manifest_path": str(strategy_library_thesis_seed_manifest_path()),
    }
    summary_path = archive_root / "cutover_summary.json"
    write_json(summary_path, summary)
    summary["path"] = str(summary_path)
    return summary


def eligible_daily_strategies(*, strategy_library: dict[str, Any]) -> list[dict[str, Any]]:
    active_pool = _sorted_daily_pool(
        [
            entry
            for entry in strategy_library.get("entries", [])
            if strategy_lifecycle(entry) == "active"
            and is_daily_executable_strategy(strategy_entry=entry)
        ]
    )
    watch_pool = _sorted_daily_pool(
        [
            entry
            for entry in strategy_library.get("entries", [])
            if strategy_lifecycle(entry) == "watch"
            and is_daily_executable_strategy(strategy_entry=entry)
        ]
    )
    candidate_pool = _sorted_daily_pool(
        [
            entry
            for entry in strategy_library.get("entries", [])
            if strategy_lifecycle(entry) == "candidate"
            and is_daily_executable_strategy(strategy_entry=entry)
        ]
    )
    selected = (
        active_pool[:DAILY_ACTIVE_EXPERIMENT_BUDGET]
        + watch_pool[:DAILY_WATCH_EXPERIMENT_BUDGET]
        + candidate_pool[:DAILY_CANDIDATE_CANARY_BUDGET]
    )
    limited: list[dict[str, Any]] = []
    seen_thesis_ids: set[str] = set()
    for entry in selected:
        thesis_profile = dict(entry.get("thesis_profile") or {})
        thesis_id = str(thesis_profile.get("thesis_id") or entry.get("strategy_id") or "").strip()
        if not thesis_id or thesis_id in seen_thesis_ids:
            continue
        seen_thesis_ids.add(thesis_id)
        limited.append(entry)
        if len(limited) >= DAILY_HYPOTHESIS_TRACK_LIMIT:
            break
    return limited


def strategy_entry_by_id(*, strategy_library: dict[str, Any], strategy_id: str) -> dict[str, Any] | None:
    for entry in strategy_library.get("entries", []):
        if str(entry.get("strategy_id")) == strategy_id:
            return entry
    return None


def model_overlay_child_strategy_id(*, base_strategy_id: str, model_family: str) -> str:
    return f"hypothesis-model-{slugify(str(base_strategy_id))}-{slugify(str(model_family))}"


def model_overlay_child_entry_for_base(
    *,
    strategy_library: dict[str, Any],
    base_strategy_id: str,
    model_family: str,
) -> dict[str, Any] | None:
    target_strategy_id = model_overlay_child_strategy_id(
        base_strategy_id=base_strategy_id,
        model_family=model_family,
    )
    for entry in strategy_library.get("entries", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("strategy_id") or "") == target_strategy_id:
            return entry
        if (
            str(entry.get("base_strategy_id") or "") == str(base_strategy_id)
            and str(entry.get("research_lane") or "") == HYPOTHESIS_MODEL_LANE
            and str(entry.get("model_family") or "") == str(model_family)
        ):
            return entry
    return None


def model_overlay_text(
    *,
    base_strategy_id: str,
    thesis_family: str | None,
    model_family: str,
) -> tuple[str, str, str]:
    readable_family = str(thesis_family or "validated_portfolio_thesis").strip() or "validated_portfolio_thesis"
    readable_model = str(model_family).strip()
    rationale = (
        f"Apply a {readable_model} model overlay to validated portfolio thesis {base_strategy_id} "
        f"without changing the underlying {readable_family} market mechanism."
    )
    expected_edge = (
        "If the portfolio thesis is real, the overlay should improve ranking calibration or trade selection "
        "without degrading capacity-adjusted out-of-sample performance."
    )
    invalidates_if = (
        "The overlay fails to preserve or improve the validated portfolio thesis after walk-forward, "
        "capacity, and anomaly checks."
    )
    return rationale, expected_edge, invalidates_if


def _sorted_daily_pool(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_priority = {"active": 0, "watch": 1, "candidate": 2}
    return sorted(
        entries,
        key=lambda entry: (
            status_priority.get(strategy_lifecycle(entry), 9),
            -float(entry.get("review_priority", 0.0) or 0.0),
            str(entry.get("last_daily_as_of") or ""),
            str(entry.get("updated_at_utc") or ""),
            str(entry.get("strategy_id") or ""),
        ),
    )


def _count_recent_failures(window: list[str]) -> int:
    return sum(1 for item in window if counts_as_daily_failure(item))


def _experiment_metric(experiment: dict[str, Any], *keys: str) -> float:
    payload: Any = experiment
    for key in keys:
        if not isinstance(payload, dict):
            return 0.0
        payload = payload.get(key)
    try:
        return float(payload or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _set_lifecycle(entry: dict[str, Any], *, lifecycle: str, reason: str, promotion_state: str | None = None) -> None:
    entry["lifecycle"] = lifecycle
    entry["monitoring_status"] = lifecycle
    entry["selection_lane"] = selection_lane_for_lifecycle(lifecycle)
    entry["promotion_state"] = promotion_state or promotion_state_for_lifecycle(lifecycle)
    entry["last_transition_reason"] = reason


def _parse_utc_or_none(value: Any) -> datetime | None:
    candidate = str(value or "").strip()
    if not candidate:
        return None
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _experiment_validation_contract(experiment: dict[str, Any]) -> dict[str, Any]:
    for payload_key in ("validation_report", "alpha_card"):
        payload = experiment.get(payload_key)
        if isinstance(payload, dict):
            contract = payload.get("validation_contract")
            if isinstance(contract, dict):
                return dict(contract)
    contract = experiment.get("validation_contract")
    return dict(contract) if isinstance(contract, dict) else {}


def _experiment_validation_blocker_codes(experiment: dict[str, Any]) -> list[str]:
    return validation_contract_blocker_codes(_experiment_validation_contract(experiment))


def _experiment_factor_evidence(experiment: dict[str, Any]) -> dict[str, Any]:
    for payload_key in ("validation_report", "alpha_card"):
        payload = experiment.get(payload_key)
        if isinstance(payload, dict):
            evidence = payload.get("factor_evidence")
            if isinstance(evidence, dict):
                return dict(evidence)
    evidence = experiment.get("factor_evidence")
    return dict(evidence) if isinstance(evidence, dict) else {}


def _archive_thesis_entry(entry: dict[str, Any], *, reason: str) -> None:
    _set_lifecycle(entry, lifecycle="retired", reason=reason, promotion_state="blocked")
    entry["promotion_eligibility"] = "ineligible"
    entry["daily_executable"] = False
    entry["thesis_archived_reason"] = reason


def _set_research_lane(entry: dict[str, Any], *, research_lane: str, reason: str) -> None:
    if research_lane not in RESEARCH_LANES:
        return
    entry["research_lane"] = research_lane
    entry["last_transition_reason"] = reason
    if research_lane == CONTROL_BASELINE_LANE:
        entry["promotion_eligibility"] = "ineligible"
        entry["daily_executable"] = False
        return
    entry["promotion_eligibility"] = str(entry.get("promotion_eligibility") or "eligible")
    entry["daily_executable"] = is_daily_executable_strategy(strategy_entry=entry)


def _pending_leakage_audit_timed_out(
    *,
    artifacts_root: Path,
    as_of: str,
    alpha_id: str,
) -> bool:
    leakage_audit = load_leakage_audit(artifacts_root=artifacts_root, as_of=as_of, alpha_id=alpha_id)
    if not isinstance(leakage_audit, dict):
        return False
    if str(leakage_audit.get("status") or "").strip() != "pending":
        return False
    generated_at = _parse_utc_or_none(leakage_audit.get("generated_at_utc"))
    if generated_at is None:
        return False
    age_hours = (datetime.now(UTC) - generated_at).total_seconds() / 3600.0
    return age_hours >= LEAKAGE_AUDIT_TIMEOUT_HOURS


def _apply_hypothesis_lane_governance(
    *,
    artifacts_root: Path,
    entry: dict[str, Any],
    experiment: dict[str, Any],
    as_of: str,
    experiment_status: str,
) -> None:
    research_lane = str(entry.get("research_lane") or "").strip()
    if research_lane not in HYPOTHESIS_RESEARCH_LANES:
        return
    blocker_codes = set(_experiment_validation_blocker_codes(experiment))
    factor_evidence = _experiment_factor_evidence(experiment)
    factor_evidence_evaluated = bool(factor_evidence)
    factor_evidence_passed = factor_evidence_evaluated and bool(factor_evidence.get("passed"))
    entry["last_factor_evidence_evaluated"] = factor_evidence_evaluated
    entry["last_factor_evidence_passed"] = factor_evidence_passed if factor_evidence_evaluated else None
    alpha_id = str(experiment.get("experiment_id") or "").strip()
    validation_state = str(
        experiment.get("validation_report", {}).get("validation")
        or experiment.get("alpha_card", {}).get("validation")
        or experiment.get("validation")
        or ""
    ).strip()
    leakage_audit_required = (
        experiment_status == "quarantined"
        or validation_state == "leakage_audit_required"
        or "sharpe_anomaly_detected" in blocker_codes
    )
    if leakage_audit_required:
        entry["leakage_audit_required_at_utc"] = str(entry.get("leakage_audit_required_at_utc") or utc_now())
        if alpha_id and _pending_leakage_audit_timed_out(
            artifacts_root=artifacts_root,
            as_of=normalize_governance_as_of(as_of),
            alpha_id=alpha_id,
        ):
            _archive_thesis_entry(entry, reason="leakage_audit_timeout")
            return
    else:
        entry["leakage_audit_required_at_utc"] = None

    terminal_failure = sorted(blocker_codes.intersection(TERMINAL_THESIS_BLOCKER_CODES))
    if terminal_failure:
        _archive_thesis_entry(entry, reason=f"thesis_terminal_failure:{terminal_failure[0]}")
        return

    if research_lane == HYPOTHESIS_FACTOR_LANE:
        explicit_factor_failure = "factor_evidence_failed" in blocker_codes or (
            factor_evidence_evaluated and not factor_evidence_passed
        )
        if explicit_factor_failure:
            entry["factor_gate_fail_streak"] = int(entry.get("factor_gate_fail_streak", 0) or 0) + 1
            entry["factor_gate_pass_streak"] = 0
            if int(entry.get("factor_gate_fail_streak", 0) or 0) >= FACTOR_EVIDENCE_ARCHIVE_FAIL_STREAK:
                _archive_thesis_entry(entry, reason="factor_evidence_failed_twice")
            else:
                entry["last_transition_reason"] = "factor_gate_failed"
            return
        if not factor_evidence_evaluated:
            entry["last_transition_reason"] = "factor_gate_not_evaluated"
            return
        entry["factor_gate_fail_streak"] = 0
        if is_pass_experiment_status(experiment_status):
            entry["factor_gate_pass_streak"] = int(entry.get("factor_gate_pass_streak", 0) or 0) + 1
            _set_research_lane(entry, research_lane=HYPOTHESIS_PORTFOLIO_LANE, reason="factor_gate_passed_to_portfolio")
            entry["portfolio_validation_pass_streak"] = 0
            entry["portfolio_validation_fail_streak"] = 0
        else:
            entry["factor_gate_pass_streak"] = 0
        return

    if research_lane == HYPOTHESIS_PORTFOLIO_LANE:
        if is_pass_experiment_status(experiment_status):
            entry["portfolio_validation_pass_streak"] = int(entry.get("portfolio_validation_pass_streak", 0) or 0) + 1
            entry["portfolio_validation_fail_streak"] = 0
            if int(entry.get("portfolio_validation_pass_streak", 0) or 0) >= PORTFOLIO_MODEL_READY_PASS_STREAK:
                entry["model_overlay_ready"] = True
                entry["model_overlay_ready_as_of"] = normalize_governance_as_of(as_of)
                entry["last_transition_reason"] = "portfolio_validation_passed_model_overlay_ready"
        elif counts_as_daily_failure(experiment_status):
            entry["portfolio_validation_pass_streak"] = 0
            entry["portfolio_validation_fail_streak"] = int(entry.get("portfolio_validation_fail_streak", 0) or 0) + 1
        return

    if research_lane == HYPOTHESIS_MODEL_LANE and str(entry.get("model_family") or "") not in HYPOTHESIS_MODEL_FAMILIES:
        _archive_thesis_entry(entry, reason="hypothesis_model_invalid_family")


def apply_daily_governance(
    *,
    artifacts_root: Path,
    strategy_library: dict[str, Any],
    experiments: list[dict[str, Any]],
    as_of: str,
) -> dict[str, Any]:
    thesis_task_mode = str(strategy_library.get("library_mode") or THESIS_TASK_LIBRARY_MODE) == THESIS_TASK_LIBRARY_MODE
    experiment_by_strategy = {str(item["strategy_id"]): item for item in experiments if item.get("strategy_id")}
    transitioned = {"to_watch": [], "to_discovery": [], "to_quarantined": []}
    for entry in strategy_library.get("entries", []):
        strategy_id = str(entry.get("strategy_id"))
        experiment = experiment_by_strategy.get(strategy_id)
        if experiment is None:
            continue
        experiment_status = str(experiment.get("experiment_status") or "fail")
        entry["last_daily_as_of"] = as_of
        entry["last_daily_experiment_status"] = experiment_status
        entry["updated_at_utc"] = utc_now()
        entry_lifecycle = strategy_lifecycle(entry)
        if is_quarantined_experiment_status(experiment_status):
            entry["daily_pass_streak"] = 0
            entry["daily_fail_streak"] = 0
            entry["watch_pass_streak"] = 0
            entry["last_transition_reason"] = "daily_quarantined_result_recorded"
            if not thesis_task_mode:
                _set_lifecycle(entry, lifecycle="quarantined", reason="daily_quarantined")
                transitioned["to_quarantined"].append(strategy_id)
        elif is_rerun_required_experiment_status(experiment_status) or is_pipeline_unreliable_pending_single_asset_fix(experiment_status):
            entry["daily_pass_streak"] = 0
            entry["daily_fail_streak"] = 0
            entry["watch_pass_streak"] = 0
            entry["watch_result_window"] = []
            entry["last_transition_reason"] = (
                "awaiting_single_asset_pipeline_fix"
                if is_pipeline_unreliable_pending_single_asset_fix(experiment_status)
                else "awaiting_overlap_rerun"
            )
        elif entry_lifecycle == "active":
            daily_window = list(entry.get("daily_result_window", []))[-9:]
            daily_window.append(experiment_status)
            entry["daily_result_window"] = daily_window
            if is_pass_experiment_status(experiment_status):
                entry["daily_pass_streak"] = int(entry.get("daily_pass_streak", 0)) + 1
                entry["daily_fail_streak"] = 0
            elif counts_as_daily_failure(experiment_status):
                entry["daily_pass_streak"] = 0
                entry["daily_fail_streak"] = int(entry.get("daily_fail_streak", 0)) + 1
            if counts_as_daily_failure(experiment_status):
                validation_net_return = _experiment_metric(experiment, "validation_report", "validation_metrics", "net_return")
                walk_forward_sharpe = _experiment_metric(experiment, "validation_report", "walk_forward", "median_oos_sharpe")
                entry["watch_pass_streak"] = 0
                entry["watch_result_window"] = []
                if thesis_task_mode:
                    entry["last_transition_reason"] = "daily_active_failure_recorded"
                else:
                    if validation_net_return > 0.0 and walk_forward_sharpe > 0.0:
                        _set_lifecycle(entry, lifecycle="watch", reason="daily_active_failed_watchworthy")
                        transitioned["to_watch"].append(strategy_id)
                    else:
                        _set_lifecycle(entry, lifecycle="discovery", reason="daily_active_failed_to_discovery")
                        transitioned["to_discovery"].append(strategy_id)
        elif entry_lifecycle == "watch":
            watch_window = list(entry.get("watch_result_window", []))[-9:]
            watch_window.append(experiment_status)
            entry["watch_result_window"] = watch_window
            if is_pass_experiment_status(experiment_status):
                entry["watch_pass_streak"] = int(entry.get("watch_pass_streak", 0)) + 1
                entry["daily_fail_streak"] = 0
            elif counts_as_daily_failure(experiment_status):
                entry["watch_pass_streak"] = 0
                entry["daily_fail_streak"] = int(entry.get("daily_fail_streak", 0)) + 1
            if int(entry.get("daily_fail_streak", 0)) >= 2:
                entry["daily_pass_streak"] = 0
                if thesis_task_mode:
                    entry["last_transition_reason"] = "watch_failure_recorded"
                else:
                    _set_lifecycle(entry, lifecycle="discovery", reason="watch_failed_to_discovery")
                    transitioned["to_discovery"].append(strategy_id)
        if thesis_task_mode:
            _apply_hypothesis_lane_governance(
                artifacts_root=artifacts_root,
                entry=entry,
                experiment=experiment,
                as_of=as_of,
                experiment_status=experiment_status,
            )
        entry["lifecycle"] = strategy_lifecycle(entry)
        entry["monitoring_status"] = entry["lifecycle"]
        entry["selection_lane"] = selection_lane_for_lifecycle(entry["lifecycle"])
        entry["promotion_state"] = str(entry.get("promotion_state") or promotion_state_for_lifecycle(entry["lifecycle"]))
        experiment["lifecycle"] = entry["lifecycle"]
        experiment["monitoring_status"] = entry["monitoring_status"]
        experiment["selection_lane"] = entry["selection_lane"]
        experiment["promotion_state"] = entry.get("promotion_state", "staged")
        experiment["source"] = entry["source"]
        experiment["spec_hash"] = entry["spec_hash"]
        experiment["strategy_id"] = strategy_id
        experiment["governance_week"] = iso_week_label(as_of)
        experiment["governance_as_of"] = normalize_governance_as_of(as_of)
        experiment["experiment_status"] = experiment_status
        _rewrite_experiment_artifacts_with_governance(
            artifacts_root=artifacts_root,
            experiment=experiment,
            strategy_entry=entry,
        )
    strategy_library["generated_at_utc"] = utc_now()
    save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
    status_counter = Counter(strategy_lifecycle(entry) for entry in strategy_library.get("entries", []))
    metrics = strategy_library_metrics(strategy_library=strategy_library)
    return {
        "strategy_library_path": str(strategy_library_path(artifacts_root=artifacts_root)),
        "status_counts": dict(status_counter),
        "library_mode": str(strategy_library.get("library_mode") or THESIS_TASK_LIBRARY_MODE),
        "entry_count": metrics["entry_count"],
        "shape_mix": metrics["shape_mix"],
        "lifecycle_mix": metrics["lifecycle_mix"],
        "daily_inventory_utilization_target": metrics["daily_inventory_utilization_target"],
        "transitions": transitioned,
        "promotion_decisions": [],
    }


def _rewrite_experiment_artifacts_with_governance(
    *,
    artifacts_root: Path,
    experiment: dict[str, Any],
    strategy_entry: dict[str, Any],
) -> None:
    alpha_card_path = Path(str(experiment["alpha_card_path"]))
    alpha_card = dict(experiment["alpha_card"])
    experiment_status = str(experiment.get("experiment_status") or alpha_card.get("experiment_status") or "fail")
    lifecycle = strategy_lifecycle(strategy_entry)
    alpha_card["experiment_status"] = experiment_status
    alpha_card["lifecycle"] = lifecycle
    alpha_card.pop("governance_status", None)
    alpha_card["monitoring_status"] = experiment.get("monitoring_status", lifecycle)
    alpha_card["selection_lane"] = experiment.get("selection_lane", experiment.get("monitoring_status", lifecycle))
    alpha_card["promotion_state"] = experiment.get("promotion_state", "staged")
    alpha_card["strategy_id"] = experiment["strategy_id"]
    alpha_card["spec_hash"] = experiment["spec_hash"]
    alpha_card["source"] = experiment["source"]
    alpha_card["governance_week"] = experiment["governance_week"]
    alpha_card["governance_as_of"] = experiment.get("governance_as_of")
    publication_assessment = evaluate_quant_publication_assessment(
        alpha_card=alpha_card,
        strategy_entry=strategy_entry,
        artifacts_root=artifacts_root,
    )
    if publication_assessment["validation"] == "leakage_audit_required":
        write_pending_leakage_audit(
            artifacts_root=artifacts_root,
            as_of=str(alpha_card.get("as_of") or ""),
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            quality_blockers=publication_assessment["quality_blockers"],
        )
        publication_assessment = evaluate_quant_publication_assessment(
            alpha_card=alpha_card,
            strategy_entry=strategy_entry,
            artifacts_root=artifacts_root,
        )
    leakage_audit_status = str(publication_assessment["metrics_snapshot"].get("leakage_audit_status") or "")
    if leakage_audit_status == "confirmed_leakage":
        experiment_status = "invalidated"
        alpha_card["experiment_status"] = experiment_status
        experiment["experiment_status"] = experiment_status
        publication_assessment = evaluate_quant_publication_assessment(
            alpha_card=alpha_card,
            strategy_entry=strategy_entry,
            artifacts_root=artifacts_root,
        )
    alpha_card["backend_mode"] = publication_assessment["backend_mode"]
    alpha_card["validation"] = publication_assessment["validation"]
    alpha_card["publication_status"] = publication_assessment["publication_status"]
    alpha_card["quality_summary"] = {
        "quality_gate_passed": publication_assessment["quality_gate_passed"],
        "quality_blockers": publication_assessment["quality_blockers"],
        "metrics_snapshot": publication_assessment["metrics_snapshot"],
    }
    write_json(alpha_card_path, alpha_card)
    experiment_root = alpha_card_path.parent
    for file_name in ("validation_report.json", "backtest_report.json", "experiment_spec.json"):
        report_path = experiment_root / file_name
        if not report_path.exists():
            continue
        payload = read_json(report_path)
        if not isinstance(payload, dict):
            continue
        payload["experiment_status"] = experiment_status
        payload["validation"] = alpha_card["validation"]
        payload["publication_status"] = alpha_card["publication_status"]
        payload["validation_contract"] = dict(alpha_card.get("validation_contract") or payload.get("validation_contract") or {})
        if file_name != "experiment_spec.json":
            payload["quality_summary"] = alpha_card["quality_summary"]
        write_json(report_path, payload)
    experiment["alpha_card"] = alpha_card
    experiment["experiment_status"] = experiment_status
    experiment["lifecycle"] = lifecycle
    experiment["backend_mode"] = publication_assessment["backend_mode"]
    experiment["validation"] = publication_assessment["validation"]
    experiment["publication_status"] = publication_assessment["publication_status"]
    experiment["selection_lane"] = selection_lane_for_lifecycle(lifecycle)
    experiment["quality_summary"] = alpha_card["quality_summary"]
    alpha_card_md_path = Path(str(experiment["alpha_card_md_path"]))
    alpha_card_md_path.write_text(_alpha_card_markdown(alpha_card) + "\n", encoding="utf-8")


def _alpha_card_markdown(alpha_card: dict[str, Any]) -> str:
    lines = [
        "# Alpha Card",
        "",
        f"- Experiment: `{alpha_card.get('experiment_id')}`",
        f"- Experiment status: `{alpha_card.get('experiment_status')}`",
        f"- Lifecycle: `{alpha_card.get('lifecycle')}`",
        f"- Validation: `{alpha_card.get('validation')}`",
        f"- Publication status: `{alpha_card.get('publication_status')}`",
        f"- Strategy ID: `{alpha_card.get('strategy_id')}`",
        f"- Shape: `{alpha_card.get('shape')}`",
        f"- Model: `{alpha_card.get('model_family')}`",
        f"- Strategy profile: `{alpha_card.get('strategy_profile')}`",
    ]
    if alpha_card.get("subject"):
        lines.append(f"- Subject: `{alpha_card.get('subject')}`")
    return "\n".join(lines)


def feature_group_for_column(column: str) -> str | None:
    if column in {"news_short_veto_mini_flag", "news_short_veto_adjudicated_flag"}:
        return "events"
    if column.startswith("event__") or column.startswith("narrative__") or column in {"event_flag_count", "narrative_tag_count"}:
        return "events"
    if column.startswith("distance_to_") or column == "range_position_20":
        return "structure"
    # Alpha Ontology W1.1 — abnormal_range_z_* is a 60-bar z-score of
    # (high - low) / close; semantically a structure / range factor.
    if column.startswith("abnormal_range_z_"):
        return "structure"
    if (
        column == "atr_proxy_20"
        or column.startswith("realized_volatility_")
        or column.startswith("intraday_realized_vol_")
    ):
        return "volatility"
    # Alpha Ontology W1.1 — MF-10 higher-moment fragility factors are
    # volatility-family by construction.
    if (
        column.startswith("realized_skew_")
        or column.startswith("realized_kurt_")
        or column.startswith("vol_of_vol_")
        or column.startswith("downside_upside_vol_ratio_")
    ):
        return "volatility"
    # Alpha Ontology W3.1 — MF-08 state-machine factors derived from vol /
    # funding / OI shocks; no event__ tape involved.
    if column in {"vol_shock_impulse_phase", "shock_co_occurrence_index"}:
        return "volatility"
    if column in {"funding_flip_decay_phase", "oi_shock_decay_phase"}:
        return "derivatives"
    # Alpha Ontology W3.2 — MF-09 co-jump & contagion network factors.
    if column in {
        "co_jump_count_3d",
        "lead_lag_beta_btc",
        "lead_lag_residual_strength",
        "contagion_in_degree",
    }:
        return "volatility"
    # Alpha Ontology W3.3 — MF-11 liquidity migration / universe rotation.
    if column in {"quote_share_change_30d", "universe_rank_velocity_10"}:
        return "volume"
    if column in {"dispersion_of_returns", "idiosyncratic_share"}:
        return "volatility"
    if column in {"quote_volume_expansion", "liquidity_stress_qv_iv", "stress_abs_basis_qv"}:
        return "volume"
    # Alpha Ontology W1.1 — MF-06 reflexive-flow factors operate on quote
    # volume / flow imbalance.
    if (
        column.startswith("qv_acceleration_")
        or column.startswith("absorption_")
        or column.startswith("flow_persistence_")
        or column.startswith("capitulation_amplification_")
    ):
        return "volume"
    if (
        column.startswith("momentum_")
        or column.startswith("ema_slope_")
        or column.startswith("sma_slope_")
        or column in {"return_1"}
        or column.startswith("relative_strength")
    ):
        return "trend"
    if column in {"funding_rate", "funding_zscore_20", "oi_change_5", "basis_proxy", "basis_zscore_20", "perp_quote_volume_usd", "quality_funding_oi", "funding_crowding_basis", "stress_liq_conc_iv", "crowd_obi_abs_funding", "crowd_tt_signal", "disp_taker_imb_xs", "unwind_liq_dh", "crowd_basis_oi_signed", "crowd_abs_basis_oi", "crowd_funding_obi_signed", "disagree_tt_retail", "unwind_liq_imb_xs"}:
        return "derivatives"
    # Alpha Ontology W1.1 — MF-04 carry-residual factors and basis derivatives.
    if (
        column.startswith("funding_basis_residual_")
        or column.startswith("basis_velocity_")
        or column.startswith("basis_carry_")
    ):
        return "derivatives"
    # M2.2 F08 — funding microstructure (skew/kurt of funding_rate per subject)
    if column.startswith("funding_term_"):
        return "derivatives"
    # M2.3 F62 — settlement-cycle premium (pre-settlement-hour drift)
    if column.startswith("settlement_cycle_"):
        return "derivatives"
    # M2.4 F-triangle — Funding-OI-Basis 3-equation residual
    if column.startswith("triangle_residual_") or column.startswith("triangle_r2_"):
        return "derivatives"
    # SP-A liq cascade — per-subject 1h liq-to-OI z-score, daily aggregated
    if column.startswith("liq_cascade_"):
        return "derivatives"
    # SP-B partial — 1h Coinglass microstructure (top trader / taker / disagreement)
    if (
        column.startswith("top_global_disagreement_")
        or column.startswith("top_trader_velocity_")
        or column.startswith("taker_skew_")
    ):
        return "derivatives"
    # SP-F sub-day funding microstructure — per-subject 4h-grain funding sequence
    # aggregated to daily F1/F2/F3 features. funding_intraday_dispersion_30d is
    # the score-admissible winner (G6 vs lsk3+F08 = +0.040 at h10d).
    if (
        column.startswith("funding_intraday_dispersion_")
        or column.startswith("funding_sign_flip_count_")
        or column == "funding_term_skew_30d_4h"
    ):
        return "derivatives"
    return None


def select_feature_columns(*, numeric_feature_columns: list[str], feature_groups: Iterable[str]) -> list[str]:
    allowed = set(feature_groups)
    return [
        column
        for column in numeric_feature_columns
        if is_model_admissible_numeric_column(column) and feature_group_for_column(column) in allowed
    ]


def validate_proposal_spec(
    *,
    proposal_spec: dict[str, Any],
    artifacts_root: Path,
    registry_snapshot: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    normalized = normalize_proposal_spec(proposal_spec)
    required_fields = (
        "proposal_id",
        "proposal_bucket",
        "week_of",
        "strategy_id",
        "shape",
        "strategy_profile",
        "model_family",
        "feature_groups",
        "rationale",
        "expected_edge",
        "invalidates_if",
        "proposal_origin",
        "search_action",
        "family_registry_patch",
        "feature_registry_patch",
        "priority_score",
        "complexity_tier",
        "risk_tags",
        "auto_bridge_requested",
        "thesis_profile",
    )
    missing = [field_name for field_name in required_fields if field_name not in normalized]
    if missing:
        return False, f"proposal missing required fields: {', '.join(missing)}"
    catalog = ensure_strategy_catalog(artifacts_root=artifacts_root)
    proposal_bucket = str(normalized.get("proposal_bucket"))
    if proposal_bucket not in PROPOSAL_BUCKET_LIMITS:
        return False, "proposal_bucket is not supported"
    shape = str(normalized.get("shape"))
    model_family = str(normalized.get("model_family"))
    if shape not in catalog["allowed_shapes"]:
        return False, "shape is not in the frozen strategy catalog"
    if str(normalized.get("strategy_profile")) not in STRATEGY_PROFILES:
        return False, "strategy_profile is not supported"
    proposal_origin = str(normalized.get("proposal_origin") or "").strip()
    if proposal_origin not in PROPOSAL_ORIGINS:
        return False, "proposal_origin is not supported"
    search_action = str(normalized.get("search_action") or "").strip()
    if search_action not in SEARCH_ACTIONS:
        return False, "search_action is not supported"
    if search_action == "model_overlay":
        if proposal_origin != "heuristic":
            return False, "model_overlay proposals are reserved for heuristic/internal discovery recipes"
        if proposal_bucket != "config":
            return False, "model_overlay proposals must use proposal_bucket=config"
    if model_family in FROZEN_MODEL_FAMILIES:
        return False, f"model_family {model_family} is frozen until hypothesis_model stage"
    if search_action == "parameter_tune":
        return False, "parameter_tune proposals are frozen until hypothesis_model stage"
    complexity_tier = str(normalized.get("complexity_tier") or "").strip()
    if complexity_tier not in COMPLEXITY_TIERS:
        return False, "complexity_tier is not supported"
    if not isinstance(normalized.get("risk_tags"), list):
        return False, "risk_tags must be a list of strings"
    try:
        float(normalized.get("priority_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False, "priority_score must be numeric"
    if not isinstance(normalized.get("auto_bridge_requested"), bool):
        return False, "auto_bridge_requested must be a boolean"
    feature_groups = list(normalized.get("feature_groups", []))
    if not feature_groups:
        return False, "feature_groups must be non-empty"
    unknown_groups = sorted(set(feature_groups) - set(catalog["allowed_feature_groups"]))
    if unknown_groups:
        return False, f"unsupported feature_groups: {', '.join(unknown_groups)}"
    thesis_profile = _normalize_thesis_profile(
        normalized.get("thesis_profile"),
        strategy_id=str(normalized.get("strategy_id") or ""),
        shape=shape,
        strategy_profile=str(normalized.get("strategy_profile") or ""),
        model_family=model_family,
        subject=normalized.get("subject"),
        universe_filter=normalized.get("universe_filter"),
    )
    if not thesis_profile:
        return False, "thesis_profile is required for non-control proposals"
    if str((thesis_profile.get("promotion_path") or [None])[0] or "") not in HYPOTHESIS_RESEARCH_LANES:
        return False, "thesis_profile.promotion_path must start with a hypothesis lane"
    if search_action == "model_overlay":
        if str(normalized.get("research_lane") or "").strip() != HYPOTHESIS_MODEL_LANE:
            return False, "model_overlay proposals must set research_lane=hypothesis_model"
        if model_family not in HYPOTHESIS_MODEL_FAMILIES:
            return False, "model_overlay proposals must use an allowed hypothesis model family"
        if not str(normalized.get("base_strategy_id") or "").strip():
            return False, "model_overlay proposals must include base_strategy_id"
        if not str(normalized.get("parent_spec_hash") or "").strip():
            return False, "model_overlay proposals must include parent_spec_hash"
        if _normalize_model_registry_patch(normalized.get("family_registry_patch")):
            return False, "model_overlay proposals cannot include family_registry_patch"
        if _normalize_feature_registry_patch(normalized.get("feature_registry_patch")):
            return False, "model_overlay proposals cannot include feature_registry_patch"
        if HYPOTHESIS_MODEL_LANE not in thesis_profile.get("promotion_path", []):
            return False, "model_overlay proposals require thesis_profile.promotion_path to include hypothesis_model"
        try:
            strategy_library = load_strategy_library(artifacts_root=artifacts_root)
        except FileNotFoundError:
            strategy_library = None
        if strategy_library is not None:
            parent_entry = strategy_entry_by_id(
                strategy_library=strategy_library,
                strategy_id=str(normalized.get("base_strategy_id") or ""),
            )
            if parent_entry is None:
                return False, "model_overlay base_strategy_id was not found in strategy library"
            if str(parent_entry.get("research_lane") or "") != HYPOTHESIS_PORTFOLIO_LANE:
                return False, "model_overlay base strategy must be a hypothesis_portfolio thesis"
            if not bool(parent_entry.get("model_overlay_ready")):
                return False, "model_overlay base strategy must be model_overlay_ready"
    valid_model_patch, model_patch_reason = _validate_model_registry_patch(
        patch=normalized.get("family_registry_patch"),
        shape=shape,
    )
    if not valid_model_patch:
        return False, model_patch_reason
    valid_feature_patch, feature_patch_reason = _validate_feature_registry_patch(
        patch=normalized.get("feature_registry_patch"),
    )
    if not valid_feature_patch:
        return False, feature_patch_reason
    resolved_registry = resolve_registry_snapshot(
        artifacts_root=artifacts_root,
        model_registry_patch=normalized.get("family_registry_patch"),
        feature_registry_patch=normalized.get("feature_registry_patch"),
        registry_snapshot=registry_snapshot,
    )
    allowed_registry_families = _registry_entries_by_id(resolved_registry.get("model_families", {}))
    if model_family not in catalog["allowed_shapes"][shape]:
        family = allowed_registry_families.get(model_family)
        if family is None:
            return False, "model_family is not in the frozen strategy catalog"
        allowed_shapes = [str(item) for item in family.get("allowed_shapes", []) if str(item).strip()]
        if shape not in allowed_shapes:
            return False, f"model_family {model_family} does not allow shape={shape}"
    if search_action == "new_model_family" and not _normalize_model_registry_patch(normalized.get("family_registry_patch")):
        return False, "new_model_family proposals must include family_registry_patch"
    if search_action == "new_feature_family" and not _normalize_feature_registry_patch(normalized.get("feature_registry_patch")):
        return False, "new_feature_family proposals must include feature_registry_patch"
    valid_constraints, reason = validate_profile_constraints_override(
        strategy_profile=str(normalized.get("strategy_profile")),
        override=normalized.get("profile_constraints_override"),
    )
    if not valid_constraints:
        return False, reason
    return True, None


def library_entry_for_spec_hash(*, strategy_library: dict[str, Any], spec_hash: str) -> dict[str, Any] | None:
    for entry in strategy_library.get("entries", []):
        if str(entry.get("spec_hash")) == spec_hash:
            return entry
    return None


def _dates_are_consecutive(previous_as_of: str, current_as_of: str) -> bool:
    try:
        import datetime as _dt

        previous_date = _dt.date.fromisoformat(normalize_governance_as_of(previous_as_of))
        current_date = _dt.date.fromisoformat(normalize_governance_as_of(current_as_of))
    except (TypeError, ValueError):
        return False
    return (current_date - previous_date).days == 1


def _next_discovery_pass_streak(*, existing_entry: dict[str, Any], current_as_of: str) -> int:
    last_as_of = str(existing_entry.get("last_discovery_pass_as_of") or "").strip()
    current_streak = int(existing_entry.get("discovery_pass_streak", existing_entry.get("weekly_pass_streak", 0)) or 0)
    if last_as_of:
        if normalize_governance_as_of(last_as_of) == current_as_of:
            return current_streak
        if _dates_are_consecutive(last_as_of, current_as_of):
            return current_streak + 1
        return 1
    legacy_last_week = str(existing_entry.get("last_weekly_pass_week") or "").strip()
    legacy_streak = int(existing_entry.get("weekly_pass_streak", 0) or 0)
    current_week = iso_week_label(current_as_of)
    if legacy_last_week:
        if legacy_last_week == current_week:
            return max(current_streak, legacy_streak, 1)
        if _iso_weeks_are_consecutive(legacy_last_week, current_week):
            return max(current_streak, legacy_streak) + 1
    return 1


def _discovery_active_promotion_count(*, strategy_library: dict[str, Any], as_of: str) -> int:
    normalized_as_of = normalize_governance_as_of(as_of)
    return sum(
        1
        for entry in strategy_library.get("entries", [])
        if str(entry.get("last_transition_reason")) in {"discovery_promoted_to_active", "weekly_promoted_to_active"}
        and normalize_governance_as_of(str(entry.get("governance_as_of") or entry.get("last_daily_as_of") or "")) == normalized_as_of
    )


def _weekly_new_task_count(*, strategy_library: dict[str, Any], week_of: str) -> int:
    normalized_as_of = normalize_governance_as_of(week_of)
    return sum(
        1
        for entry in strategy_library.get("entries", [])
        if str(entry.get("last_transition_reason") or "") == "weekly_created_new_task"
        and normalize_governance_as_of(str(entry.get("governance_as_of") or "")) == normalized_as_of
    )


def _weekly_task_revision_count(*, strategy_library: dict[str, Any], week_of: str) -> int:
    normalized_as_of = normalize_governance_as_of(week_of)
    return sum(
        1
        for entry in strategy_library.get("entries", [])
        if str(entry.get("last_transition_reason") or "") == "weekly_updated_existing_task"
        and normalize_governance_as_of(str(entry.get("governance_as_of") or "")) == normalized_as_of
    )


def _reset_task_validation_history(entry: dict[str, Any]) -> None:
    entry["daily_pass_streak"] = 0
    entry["daily_fail_streak"] = 0
    entry["daily_result_window"] = []
    entry["watch_pass_streak"] = 0
    entry["watch_result_window"] = []
    entry["weekly_pass_streak"] = 1
    entry["last_weekly_pass_week"] = entry.get("governance_week")
    entry["discovery_pass_streak"] = 1
    entry["last_discovery_pass_as_of"] = entry.get("governance_as_of")
    entry["last_discovery_run_id"] = entry.get("run_id")
    entry["last_daily_as_of"] = None
    entry["last_daily_experiment_status"] = None


def apply_weekly_proposal_result(
    *,
    artifacts_root: Path,
    strategy_library: dict[str, Any],
    proposal_spec: dict[str, Any],
    evaluation_status: str,
    week_of: str,
) -> dict[str, Any]:
    normalized_proposal = normalize_proposal_spec(proposal_spec)
    blocked_reason = blocked_discovery_reason(model_family=str(normalized_proposal.get("model_family") or ""))
    if blocked_reason is not None:
        return {"action": "artifact_only_data_gap", "strategy_id": None, "reason": blocked_reason}
    persist_registry_patches(
        artifacts_root=artifacts_root,
        model_registry_patch=normalized_proposal.get("family_registry_patch"),
        feature_registry_patch=normalized_proposal.get("feature_registry_patch"),
    )
    spec_hash = str(normalized_proposal["spec_hash"])
    existing_entry = library_entry_for_spec_hash(strategy_library=strategy_library, spec_hash=spec_hash)
    base_strategy_id = str(normalized_proposal.get("base_strategy_id") or "").strip()
    base_entry = (
        strategy_entry_by_id(strategy_library=strategy_library, strategy_id=base_strategy_id)
        if base_strategy_id
        else None
    )
    search_action = str(normalized_proposal.get("search_action") or "").strip()
    action = "no_change"
    current_as_of = normalize_governance_as_of(week_of)
    current_week = iso_week_label(current_as_of)
    current_run_id = None if normalized_proposal.get("run_id") in {None, ""} else str(normalized_proposal.get("run_id"))
    if not is_pass_experiment_status(evaluation_status):
        if is_rerun_required_experiment_status(evaluation_status):
            if existing_entry is not None:
                existing_entry["updated_at_utc"] = utc_now()
                existing_entry["governance_week"] = current_week
                existing_entry["governance_as_of"] = current_as_of
                existing_entry["run_id"] = current_run_id
                existing_entry["last_discovery_run_id"] = current_run_id
                existing_entry["last_transition_reason"] = "discovery_rerun_required"
                save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
                return {"action": "rerun_required", "strategy_id": existing_entry.get("strategy_id")}
            return {"action": "rerun_required", "strategy_id": None}
        if existing_entry is not None and strategy_lifecycle(existing_entry) == "candidate":
            existing_entry["weekly_pass_streak"] = 0
            existing_entry["discovery_pass_streak"] = 0
            existing_entry["updated_at_utc"] = utc_now()
            existing_entry["governance_week"] = current_week
            existing_entry["governance_as_of"] = current_as_of
            existing_entry["run_id"] = current_run_id
            existing_entry["last_discovery_run_id"] = current_run_id
            existing_entry["last_transition_reason"] = "discovery_candidate_failed"
            existing_entry["lifecycle"] = strategy_lifecycle(existing_entry)
            existing_entry["monitoring_status"] = existing_entry["lifecycle"]
            existing_entry["selection_lane"] = selection_lane_for_lifecycle(existing_entry["lifecycle"])
            action = "candidate_retained"
            save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
        return {"action": action, "strategy_id": existing_entry.get("strategy_id") if existing_entry else None}

    if existing_entry is not None:
        existing_entry["updated_at_utc"] = utc_now()
        existing_entry["governance_week"] = current_week
        existing_entry["governance_as_of"] = current_as_of
        existing_entry["run_id"] = current_run_id
        existing_entry["rationale"] = str(normalized_proposal.get("rationale") or existing_entry.get("rationale") or "").strip()
        existing_entry["expected_edge"] = str(
            normalized_proposal.get("expected_edge") or existing_entry.get("expected_edge") or ""
        ).strip()
        existing_entry["invalidates_if"] = str(
            normalized_proposal.get("invalidates_if") or existing_entry.get("invalidates_if") or ""
        ).strip()
        existing_entry["data_dependencies"] = _normalize_data_dependencies(
            shape=str(existing_entry.get("shape") or ""),
            feature_groups=existing_entry.get("feature_groups"),
            payload=normalized_proposal.get("data_dependencies") or existing_entry.get("data_dependencies"),
        )
        existing_entry["review_priority"] = float(
            normalized_proposal.get("review_priority")
            if normalized_proposal.get("review_priority") not in {None, ""}
            else existing_entry.get("review_priority", 0.0)
        )
        current_streak = _next_discovery_pass_streak(existing_entry=existing_entry, current_as_of=current_as_of)
        existing_entry["weekly_pass_streak"] = current_streak
        existing_entry["last_weekly_pass_week"] = current_week
        existing_entry["discovery_pass_streak"] = current_streak
        existing_entry["last_discovery_pass_as_of"] = current_as_of
        existing_entry["last_discovery_run_id"] = current_run_id
        existing_entry["discovery_cadence"] = "daily_full"
        promoted_today = _discovery_active_promotion_count(strategy_library=strategy_library, as_of=current_as_of)
        if strategy_lifecycle(existing_entry) == "candidate" and current_streak >= 2 and promoted_today < WEEKLY_PROMOTION_TO_ACTIVE_CAP:
            _set_lifecycle(existing_entry, lifecycle="active", reason="weekly_promoted_to_active")
            existing_entry["promotion_state"] = "promoted"
            action = "promoted_to_active"
        elif strategy_lifecycle(existing_entry) == "candidate" and current_streak >= 2:
            _set_lifecycle(existing_entry, lifecycle="candidate", reason="weekly_promotion_deferred_cap")
            existing_entry["promotion_state"] = "deferred"
            action = "promotion_deferred"
        else:
            _set_lifecycle(existing_entry, lifecycle=strategy_lifecycle(existing_entry), reason="weekly_candidate_passed")
            existing_entry["promotion_state"] = str(
                existing_entry.get("promotion_state") or promotion_state_for_lifecycle(strategy_lifecycle(existing_entry))
            )
            action = "candidate_retained"
        existing_entry["selection_lane"] = selection_lane_for_lifecycle(existing_entry["lifecycle"])
        strategy_library["generated_at_utc"] = utc_now()
        save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
        return {"action": action, "strategy_id": existing_entry["strategy_id"]}

    if search_action == "model_overlay":
        if (
            base_entry is None
            or str(base_entry.get("research_lane") or "") != HYPOTHESIS_PORTFOLIO_LANE
            or not bool(base_entry.get("model_overlay_ready"))
        ):
            return {"action": "promotion_deferred_invalid_model_overlay_parent", "strategy_id": None}
        overlay_child = model_overlay_child_entry_for_base(
            strategy_library=strategy_library,
            base_strategy_id=base_strategy_id,
            model_family=str(normalized_proposal.get("model_family") or ""),
        )
        if overlay_child is not None:
            if _weekly_task_revision_count(strategy_library=strategy_library, week_of=current_as_of) >= WEEKLY_MAX_TASK_REVISIONS:
                return {"action": "promotion_deferred_revision_cap", "strategy_id": overlay_child.get("strategy_id")}
        else:
            if len([entry for entry in strategy_library.get("entries", []) if isinstance(entry, dict)]) >= THESIS_TASK_LIBRARY_SOFT_MAX:
                return {"action": "promotion_deferred_library_full", "strategy_id": None}
            if _weekly_new_task_count(strategy_library=strategy_library, week_of=current_as_of) >= WEEKLY_MAX_NEW_TASKS:
                return {"action": "promotion_deferred_new_task_cap", "strategy_id": None}

        rationale, expected_edge, invalidates_if = model_overlay_text(
            base_strategy_id=base_strategy_id,
            thesis_family=str(
                normalized_proposal.get("thesis_family")
                or base_entry.get("thesis_family")
                or ""
            ),
            model_family=str(normalized_proposal.get("model_family") or ""),
        )
        if overlay_child is not None:
            revised_entry = build_strategy_entry(
                strategy_id=str(overlay_child["strategy_id"]),
                shape=str(normalized_proposal["shape"]),
                strategy_profile=str(normalized_proposal["strategy_profile"]),
                subject=normalized_proposal.get("subject"),
                universe_filter=normalized_proposal.get("universe_filter"),
                model_family=str(normalized_proposal["model_family"]),
                feature_groups=normalized_proposal.get("feature_groups"),
                profile_constraints_override=normalized_proposal.get("profile_constraints_override"),
                source=str(overlay_child.get("source") or "discovery"),
                status=str(strategy_lifecycle(overlay_child) or "candidate"),
                created_at_utc=str(overlay_child.get("created_at_utc") or utc_now()),
                updated_at_utc=utc_now(),
                governance_week=current_week,
                governance_as_of=current_as_of,
                run_id=current_run_id,
                base_strategy_id=base_strategy_id,
                proposal_origin=str(normalized_proposal.get("proposal_origin") or overlay_child.get("proposal_origin") or "heuristic"),
                search_action=search_action,
                parent_spec_hash=str(base_entry.get("spec_hash") or normalized_proposal.get("parent_spec_hash") or ""),
                family_registry_patch={},
                feature_registry_patch={},
                priority_score=normalized_proposal.get("priority_score"),
                complexity_tier=normalized_proposal.get("complexity_tier"),
                risk_tags=normalized_proposal.get("risk_tags"),
                auto_bridge_requested=normalized_proposal.get("auto_bridge_requested"),
                registry_snapshot_id=normalized_proposal.get("registry_snapshot_id"),
                family_id=normalized_proposal.get("family_id"),
                rationale=rationale,
                expected_edge=expected_edge,
                invalidates_if=invalidates_if,
                data_dependencies=normalized_proposal.get("data_dependencies") or overlay_child.get("data_dependencies"),
                review_priority=normalized_proposal.get("review_priority") or overlay_child.get("review_priority"),
                research_lane=HYPOTHESIS_MODEL_LANE,
                promotion_eligibility="eligible",
                thesis_family=normalized_proposal.get("thesis_family") or base_entry.get("thesis_family"),
                requires_derivatives_features=(
                    normalized_proposal.get("requires_derivatives_features")
                    if normalized_proposal.get("requires_derivatives_features") is not None
                    else base_entry.get("requires_derivatives_features")
                ),
                daily_executable=(
                    normalized_proposal.get("daily_executable")
                    if normalized_proposal.get("daily_executable") is not None
                    else base_entry.get("daily_executable")
                ),
                thesis_profile=normalized_proposal.get("thesis_profile") or base_entry.get("thesis_profile"),
            )
            for key, value in _preserved_thesis_task_state(overlay_child).items():
                if key == "created_at_utc":
                    continue
                revised_entry[key] = value
            revised_entry["governance_week"] = current_week
            revised_entry["governance_as_of"] = current_as_of
            revised_entry["run_id"] = current_run_id
            revised_entry["updated_at_utc"] = utc_now()
            revised_entry["model_overlay_ready"] = True
            revised_entry["model_overlay_ready_as_of"] = current_as_of
            _reset_task_validation_history(revised_entry)
            revised_entry["last_transition_reason"] = "weekly_updated_existing_task"
            revised_entry["selection_lane"] = selection_lane_for_lifecycle(revised_entry["lifecycle"])
            revised_entry["promotion_state"] = promotion_state_for_lifecycle(revised_entry["lifecycle"])
            entries = strategy_library.setdefault("entries", [])
            for index, entry in enumerate(entries):
                if str(entry.get("strategy_id") or "") == str(overlay_child.get("strategy_id") or ""):
                    entries[index] = normalize_strategy_library_entry(revised_entry)
                    break
            strategy_library["generated_at_utc"] = utc_now()
            save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
            return {"action": "update_existing_task", "strategy_id": revised_entry["strategy_id"]}

        created_at = utc_now()
        new_entry = build_strategy_entry(
            strategy_id=str(normalized_proposal["strategy_id"]),
            shape=str(normalized_proposal["shape"]),
            strategy_profile=str(normalized_proposal["strategy_profile"]),
            subject=normalized_proposal.get("subject"),
            universe_filter=normalized_proposal.get("universe_filter"),
            model_family=str(normalized_proposal["model_family"]),
            feature_groups=normalized_proposal.get("feature_groups"),
            profile_constraints_override=normalized_proposal.get("profile_constraints_override"),
            source="discovery",
            status="candidate",
            created_at_utc=created_at,
            updated_at_utc=created_at,
            governance_week=current_week,
            governance_as_of=current_as_of,
            run_id=current_run_id,
            base_strategy_id=base_strategy_id,
            proposal_origin=str(normalized_proposal.get("proposal_origin") or "heuristic"),
            search_action=search_action,
            parent_spec_hash=str(base_entry.get("spec_hash") or normalized_proposal.get("parent_spec_hash") or ""),
            family_registry_patch={},
            feature_registry_patch={},
            priority_score=normalized_proposal.get("priority_score"),
            complexity_tier=normalized_proposal.get("complexity_tier"),
            risk_tags=normalized_proposal.get("risk_tags"),
            auto_bridge_requested=normalized_proposal.get("auto_bridge_requested"),
            registry_snapshot_id=normalized_proposal.get("registry_snapshot_id"),
            family_id=normalized_proposal.get("family_id"),
            rationale=rationale,
            expected_edge=expected_edge,
            invalidates_if=invalidates_if,
            data_dependencies=normalized_proposal.get("data_dependencies") or base_entry.get("data_dependencies"),
            review_priority=normalized_proposal.get("review_priority") or base_entry.get("review_priority"),
            research_lane=HYPOTHESIS_MODEL_LANE,
            promotion_eligibility="eligible",
            thesis_family=normalized_proposal.get("thesis_family") or base_entry.get("thesis_family"),
            requires_derivatives_features=normalized_proposal.get("requires_derivatives_features"),
            daily_executable=normalized_proposal.get("daily_executable"),
            thesis_profile=normalized_proposal.get("thesis_profile") or base_entry.get("thesis_profile"),
        )
        _reset_task_validation_history(new_entry)
        new_entry["model_overlay_ready"] = True
        new_entry["model_overlay_ready_as_of"] = current_as_of
        new_entry["last_transition_reason"] = "weekly_created_new_task"
        new_entry["promotion_state"] = "staged"
        new_entry["lifecycle"] = strategy_lifecycle(new_entry)
        new_entry["monitoring_status"] = new_entry["lifecycle"]
        new_entry["selection_lane"] = selection_lane_for_lifecycle(new_entry["lifecycle"])
        strategy_library.setdefault("entries", []).append(new_entry)
        strategy_library["generated_at_utc"] = utc_now()
        save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
        return {"action": "create_new_task", "strategy_id": new_entry["strategy_id"]}

    if base_entry is not None:
        if _weekly_task_revision_count(strategy_library=strategy_library, week_of=current_as_of) >= WEEKLY_MAX_TASK_REVISIONS:
            return {"action": "promotion_deferred_revision_cap", "strategy_id": base_entry.get("strategy_id")}
        revised_entry = build_strategy_entry(
            strategy_id=str(base_entry["strategy_id"]),
            shape=str(normalized_proposal["shape"]),
            strategy_profile=str(normalized_proposal["strategy_profile"]),
            subject=normalized_proposal.get("subject"),
            universe_filter=normalized_proposal.get("universe_filter"),
            model_family=str(normalized_proposal["model_family"]),
            feature_groups=normalized_proposal.get("feature_groups"),
            profile_constraints_override=normalized_proposal.get("profile_constraints_override"),
            source=str(base_entry.get("source") or "baseline"),
            status=str(strategy_lifecycle(base_entry) or "candidate"),
            created_at_utc=str(base_entry.get("created_at_utc") or utc_now()),
            updated_at_utc=utc_now(),
            governance_week=current_week,
            governance_as_of=current_as_of,
            run_id=current_run_id,
            base_strategy_id=base_entry.get("base_strategy_id"),
            family_id=normalized_proposal.get("family_id"),
            rationale=str(normalized_proposal.get("rationale") or base_entry.get("rationale") or ""),
            expected_edge=str(normalized_proposal.get("expected_edge") or base_entry.get("expected_edge") or ""),
            invalidates_if=str(normalized_proposal.get("invalidates_if") or base_entry.get("invalidates_if") or ""),
            data_dependencies=normalized_proposal.get("data_dependencies") or base_entry.get("data_dependencies"),
            review_priority=normalized_proposal.get("review_priority") or base_entry.get("review_priority"),
            research_lane=normalized_proposal.get("research_lane") or base_entry.get("research_lane"),
            promotion_eligibility=normalized_proposal.get("promotion_eligibility") or base_entry.get("promotion_eligibility"),
            thesis_family=normalized_proposal.get("thesis_family") or base_entry.get("thesis_family"),
            requires_derivatives_features=(
                normalized_proposal.get("requires_derivatives_features")
                if normalized_proposal.get("requires_derivatives_features") is not None
                else base_entry.get("requires_derivatives_features")
            ),
            daily_executable=(
                normalized_proposal.get("daily_executable")
                if normalized_proposal.get("daily_executable") is not None
                else base_entry.get("daily_executable")
            ),
            thesis_profile=normalized_proposal.get("thesis_profile") or base_entry.get("thesis_profile"),
        )
        for key, value in _preserved_thesis_task_state(base_entry).items():
            if key == "created_at_utc":
                continue
            revised_entry[key] = value
        revised_entry["governance_week"] = current_week
        revised_entry["governance_as_of"] = current_as_of
        revised_entry["run_id"] = current_run_id
        revised_entry["updated_at_utc"] = utc_now()
        _reset_task_validation_history(revised_entry)
        revised_entry["last_transition_reason"] = "weekly_updated_existing_task"
        revised_entry["selection_lane"] = selection_lane_for_lifecycle(revised_entry["lifecycle"])
        revised_entry["promotion_state"] = promotion_state_for_lifecycle(revised_entry["lifecycle"])
        entries = strategy_library.setdefault("entries", [])
        for index, entry in enumerate(entries):
            if str(entry.get("strategy_id") or "") == str(base_entry.get("strategy_id") or ""):
                entries[index] = normalize_strategy_library_entry(revised_entry)
                break
        strategy_library["generated_at_utc"] = utc_now()
        save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
        return {"action": "update_existing_task", "strategy_id": base_entry["strategy_id"]}

    if len([entry for entry in strategy_library.get("entries", []) if isinstance(entry, dict)]) >= THESIS_TASK_LIBRARY_SOFT_MAX:
        return {"action": "promotion_deferred_library_full", "strategy_id": None}
    if _weekly_new_task_count(strategy_library=strategy_library, week_of=current_as_of) >= WEEKLY_MAX_NEW_TASKS:
        return {"action": "promotion_deferred_new_task_cap", "strategy_id": None}

    if existing_entry is None:
        created_at = utc_now()
        new_entry = build_strategy_entry(
            strategy_id=str(normalized_proposal["strategy_id"]),
            shape=str(normalized_proposal["shape"]),
            strategy_profile=str(normalized_proposal["strategy_profile"]),
            subject=normalized_proposal.get("subject"),
            universe_filter=normalized_proposal.get("universe_filter"),
            model_family=str(normalized_proposal["model_family"]),
            feature_groups=normalized_proposal.get("feature_groups"),
            profile_constraints_override=normalized_proposal.get("profile_constraints_override"),
            source="discovery",
            status="candidate",
            created_at_utc=created_at,
            updated_at_utc=created_at,
            governance_week=current_week,
            governance_as_of=current_as_of,
            run_id=current_run_id,
            family_id=normalized_proposal.get("family_id"),
            rationale=str(normalized_proposal.get("rationale") or ""),
            expected_edge=str(normalized_proposal.get("expected_edge") or ""),
            invalidates_if=str(normalized_proposal.get("invalidates_if") or ""),
            data_dependencies=normalized_proposal.get("data_dependencies"),
            review_priority=normalized_proposal.get("review_priority"),
            research_lane=normalized_proposal.get("research_lane"),
            promotion_eligibility=normalized_proposal.get("promotion_eligibility"),
            thesis_family=normalized_proposal.get("thesis_family"),
            requires_derivatives_features=normalized_proposal.get("requires_derivatives_features"),
            daily_executable=normalized_proposal.get("daily_executable"),
            thesis_profile=normalized_proposal.get("thesis_profile"),
        )
        _reset_task_validation_history(new_entry)
        new_entry["last_transition_reason"] = "weekly_created_new_task"
        new_entry["promotion_state"] = "staged"
        new_entry["lifecycle"] = strategy_lifecycle(new_entry)
        new_entry["monitoring_status"] = new_entry["lifecycle"]
        new_entry["selection_lane"] = selection_lane_for_lifecycle(new_entry["lifecycle"])
        strategy_library.setdefault("entries", []).append(new_entry)
        strategy_library["generated_at_utc"] = utc_now()
        save_strategy_library(artifacts_root=artifacts_root, payload=strategy_library)
        return {"action": "create_new_task", "strategy_id": new_entry["strategy_id"]}

    return {"action": action, "strategy_id": None}


def _weekly_active_promotion_count(*, strategy_library: dict[str, Any], week_of: str) -> int:
    return _discovery_active_promotion_count(strategy_library=strategy_library, as_of=week_of)


def _iso_weeks_are_consecutive(previous_week: str, current_week: str) -> bool:
    try:
        prev_year_str, prev_week_str = str(previous_week).split("-W", maxsplit=1)
        curr_year_str, curr_week_str = str(current_week).split("-W", maxsplit=1)
        import datetime as _dt

        previous_date = _dt.date.fromisocalendar(int(prev_year_str), int(prev_week_str), 1)
        current_date = _dt.date.fromisocalendar(int(curr_year_str), int(curr_week_str), 1)
    except (TypeError, ValueError):
        return False
    return (current_date - previous_date).days == 7
