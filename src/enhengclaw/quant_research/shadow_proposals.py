from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from typing import Any

import pandas as pd

from enhengclaw.ops.evidence_contracts import required_source_commit_sha, with_evidence_metadata

from .contracts import portable_path, read_json, resolve_portable_path, sha256_canonical_json, utc_now, write_json
from .deterministic_core import compute_strategy_spec_hash, load_deterministic_strategy_manifest
from .deterministic_survival import (
    SURVIVAL_OUTCOME_BLOCKED,
    SURVIVAL_OUTCOME_FAILED,
    SURVIVAL_OUTCOME_MISSING,
    SURVIVAL_OUTCOME_SURVIVED,
    resolve_experiment_artifact_paths,
    run_quant_deterministic_daily_sample,
)
from .execution_cost_model import execution_venue_for_constraints
from .lab import QUANT_ARTIFACTS_ROOT, QUANT_INPUT_ROOT, WORKBENCH_ROOT, run_quant_experiments_for_strategies


ROOT = Path(__file__).resolve().parents[3]
ETH_SHADOW_GRID_BASE_STRATEGY_ID = "core-eth-conservative-breakout-volatility-expansion-single-asset"
ETH_SHADOW_GRID_VARIANT_SPEC_CONTRACT_VERSION = "quant_eth_shadow_grid_variant_spec.v1"
ETH_SHADOW_GRID_VARIANT_MANIFEST_CONTRACT_VERSION = "quant_eth_shadow_grid_variant_manifest.v1"
ETH_SHADOW_GRID_VARIANT_EVALUATION_CONTRACT_VERSION = "quant_eth_shadow_grid_variant_evaluation.v1"
ETH_SHADOW_GRID_VARIANT_VS_BASELINE_CONTRACT_VERSION = "quant_eth_shadow_grid_variant_vs_baseline.v1"
ETH_SHADOW_GRID_DAILY_SAMPLE_CONTRACT_VERSION = "quant_eth_shadow_grid_daily_sample.v1"
ETH_SHADOW_GRID_SURVIVAL_CONTRACT_VERSION = "quant_eth_shadow_survival.v1"
ETH_SHADOW_GRID_CYCLE_SUMMARY_CONTRACT_VERSION = "quant_eth_shadow_grid_cycle.v1"
SHADOW_CANDIDATE_LIST_CONTRACT_VERSION = "quant_shadow_candidate_list.v1"
ETH_SHADOW_GRID_SOURCE = "quantagent_shadow_grid"
ETH_SHADOW_GRID_SELECTION_LANE = "shadow_grid"
ETH_SHADOW_GRID_PROMOTION_STATE = "shadow_only"
ETH_SHADOW_GRID_SEARCH_MODE = "deterministic_grid"
ETH_SHADOW_GRID_SURVIVAL_WINDOW_DAYS_DEFAULT = 5
ETH_SHADOW_GRID_NEUTRAL_BANDS = (0.0, 0.1, 0.2, 0.3)
ETH_SHADOW_GRID_TURNOVER_CAPS = (0.5, 0.75, 1.0)
ETH_SHADOW_GRID_INCUMBENT_PATCH = {
    "execution_venue": "spot",
    "positioning_mode": "long_only",
    "neutral_band_abs_score": 0.0,
    "max_turnover_per_rebalance": 1.0,
}


def run_quantagent_shadow_proposal_cycle(
    *,
    as_of: str,
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    workbench_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
    base_strategy_ids: list[str] | None = None,
    survival_window_days: int = ETH_SHADOW_GRID_SURVIVAL_WINDOW_DAYS_DEFAULT,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    resolved_perp_root = None if ohlcv_external_root is None else Path(ohlcv_external_root).expanduser().resolve()
    resolved_spot_root = None if spot_ohlcv_external_root is None else Path(spot_ohlcv_external_root).expanduser().resolve()
    resolved_derivatives_root = None if derivatives_external_root is None else Path(derivatives_external_root).expanduser().resolve()
    if survival_window_days <= 0:
        raise ValueError("survival_window_days must be positive")

    strategy_manifest = load_deterministic_strategy_manifest()
    base_strategy_entry = _resolve_eth_base_strategy_entry(
        strategy_manifest=strategy_manifest,
        requested_base_strategy_ids=base_strategy_ids,
    )
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)
    end_date = date.fromisoformat(as_of)
    start_date = end_date - timedelta(days=survival_window_days - 1)
    window_dates = [current.isoformat() for current in _date_range(start_date, end_date)]

    daily_samples: list[dict[str, Any]] = []
    for current_as_of in window_dates:
        daily_samples.append(
            run_eth_shadow_grid_daily_sample(
                as_of=current_as_of,
                artifacts_root=resolved_artifacts_root,
                quant_input_root=resolved_quant_input_root,
                workbench_root=resolved_workbench_root,
                ohlcv_external_root=resolved_perp_root,
                spot_ohlcv_external_root=resolved_spot_root,
                derivatives_external_root=resolved_derivatives_root,
                base_strategy_ids=[str(base_strategy_entry["strategy_id"])],
            )
        )

    survival_report = run_eth_shadow_grid_survival(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        survival_window_days=survival_window_days,
        base_strategy_ids=[str(base_strategy_entry["strategy_id"])],
    )
    accepted_candidates = _build_accepted_candidates(
        as_of=as_of,
        daily_sample=daily_samples[-1],
        survival_report=survival_report,
    )
    candidate_list_path = resolved_artifacts_root / "shadow_candidates" / as_of / "shadow_candidate_list.json"
    candidate_list = _write_shadow_candidate_list(
        path=candidate_list_path,
        as_of=as_of,
        eligible_base_strategy_ids=[str(base_strategy_entry["strategy_id"])],
        accepted_candidates=accepted_candidates,
        source_commit_sha=source_commit_sha,
    )
    summary_path = resolved_artifacts_root / "shadow_grid" / as_of / "grid_cycle_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    return _write_grid_cycle_summary(
        path=summary_path,
        as_of=as_of,
        strategy_manifest=strategy_manifest,
        base_strategy_entry=base_strategy_entry,
        daily_samples=daily_samples,
        survival_report=survival_report,
        candidate_list_path=Path(str(candidate_list["path"])),
        accepted_candidates=accepted_candidates,
        survival_window_days=survival_window_days,
        source_commit_sha=source_commit_sha,
    )


def run_eth_shadow_grid_daily_sample(
    *,
    as_of: str,
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    workbench_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
    base_strategy_ids: list[str] | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    resolved_perp_root = None if ohlcv_external_root is None else Path(ohlcv_external_root).expanduser().resolve()
    resolved_spot_root = None if spot_ohlcv_external_root is None else Path(spot_ohlcv_external_root).expanduser().resolve()
    resolved_derivatives_root = None if derivatives_external_root is None else Path(derivatives_external_root).expanduser().resolve()
    strategy_manifest = load_deterministic_strategy_manifest()
    base_strategy_entry = _resolve_eth_base_strategy_entry(
        strategy_manifest=strategy_manifest,
        requested_base_strategy_ids=base_strategy_ids,
    )
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)

    canonical_daily_sample = run_quant_deterministic_daily_sample(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        quant_input_root=resolved_quant_input_root,
        workbench_root=resolved_workbench_root,
        spot_ohlcv_external_root=resolved_spot_root,
        perp_ohlcv_external_root=resolved_perp_root,
        derivatives_external_root=resolved_derivatives_root,
    )
    cycle_summary_path = str(canonical_daily_sample.get("cycle_summary_path") or "").strip()
    if not cycle_summary_path:
        raise RuntimeError("deterministic daily sample missing cycle_summary_path")
    cycle_summary = dict(read_json(resolve_portable_path(cycle_summary_path, repo_root=ROOT)))
    feature_sets = _load_feature_sets_from_cycle_summary(cycle_summary=cycle_summary)
    sample_by_strategy_id = {
        str(item.get("strategy_id") or "").strip(): dict(item)
        for item in list(canonical_daily_sample.get("strategy_samples") or [])
        if isinstance(item, dict) and str(item.get("strategy_id") or "").strip()
    }
    baseline_sample = dict(sample_by_strategy_id.get(str(base_strategy_entry["strategy_id"])) or {})
    baseline_context = None if _base_strategy_is_blocked(baseline_sample) else _load_baseline_context(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        base_strategy_entry=base_strategy_entry,
        daily_sample_entry=baseline_sample,
    )

    variants = _build_eth_shadow_grid_variants(base_strategy_entry=base_strategy_entry)
    grid_root = resolved_artifacts_root / "shadow_grid" / as_of
    grid_root.mkdir(parents=True, exist_ok=True)
    variant_manifest_path = grid_root / "grid_variant_manifest.json"
    variant_manifest = _write_grid_variant_manifest(
        path=variant_manifest_path,
        as_of=as_of,
        base_strategy_entry=base_strategy_entry,
        variants=variants,
        source_commit_sha=source_commit_sha,
    )

    variant_samples: list[dict[str, Any]] = []
    if baseline_context is None:
        blocker_codes = list(baseline_sample.get("blocker_codes") or []) if baseline_sample else ["baseline_context_missing"]
        reason = "baseline_daily_sample_blocked" if baseline_sample else "baseline_context_missing"
        for variant in variants:
            variant_root = grid_root / "variants" / str(variant["variant_id"])
            variant_root.mkdir(parents=True, exist_ok=True)
            variant_spec = _write_grid_variant_spec(
                path=variant_root / "variant_spec.json",
                as_of=as_of,
                variant=variant,
                base_strategy_entry=base_strategy_entry,
                source_commit_sha=source_commit_sha,
            )
            variant_samples.append(
                _blocked_variant_sample(
                    as_of=as_of,
                    variant=variant,
                    blocker_codes=blocker_codes,
                    reason=reason,
                    variant_spec_path=Path(str(variant_spec["path"])),
                )
            )
    else:
        for variant in variants:
            variant_root = grid_root / "variants" / str(variant["variant_id"])
            variant_root.mkdir(parents=True, exist_ok=True)
            variant_spec = _write_grid_variant_spec(
                path=variant_root / "variant_spec.json",
                as_of=as_of,
                variant=variant,
                base_strategy_entry=base_strategy_entry,
                source_commit_sha=source_commit_sha,
            )
            variant_samples.append(
                _evaluate_grid_variant(
                    as_of=as_of,
                    variant=variant,
                    variant_root=variant_root,
                    base_strategy_entry=base_strategy_entry,
                    baseline_context=baseline_context,
                    feature_sets=feature_sets,
                    source_commit_sha=source_commit_sha,
                    variant_spec_path=Path(str(variant_spec["path"])),
                )
            )

    output_path = resolved_artifacts_root / "cycles" / as_of / "eth_shadow_grid_daily_sample.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "artifact_family": "quant_eth_shadow_grid_daily_sample",
        "contract_version": ETH_SHADOW_GRID_DAILY_SAMPLE_CONTRACT_VERSION,
        "search_mode": ETH_SHADOW_GRID_SEARCH_MODE,
        "base_strategy_id": str(base_strategy_entry["strategy_id"]),
        "base_strategy_spec_hash": str(base_strategy_entry.get("spec_hash") or ""),
        "baseline_daily_sample_path": str(canonical_daily_sample.get("deterministic_daily_sample_path") or ""),
        "baseline_cycle_summary_path": cycle_summary_path,
        "baseline_experiment_id": str(baseline_context.get("baseline_experiment_id") or "") if baseline_context else None,
        "quant_input_path": str(canonical_daily_sample.get("quant_input_path") or ""),
        "universe_snapshot_path": str(canonical_daily_sample.get("universe_snapshot_path") or ""),
        "derivatives_sync_summary_path": str(canonical_daily_sample.get("derivatives_sync_summary_path") or ""),
        "grid_variant_manifest_path": portable_path(variant_manifest_path, repo_root=ROOT),
        "grid_variant_ids": [str(item["variant_id"]) for item in variants],
        "variant_outcome_counts": _count_variant_outcomes(variant_samples),
        "variant_samples": variant_samples,
    }
    payload["sample_hash"] = _stable_payload_hash(payload)
    document = _write_evidence(
        path=output_path,
        payload=payload,
        evidence_family="quant_eth_shadow_grid_daily_sample",
        contract_version=ETH_SHADOW_GRID_DAILY_SAMPLE_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )
    document["eth_shadow_grid_daily_sample_path"] = str(output_path)
    document["grid_variant_manifest"] = variant_manifest
    return document


def run_eth_shadow_grid_survival(
    *,
    as_of: str,
    artifacts_root: Path | None = None,
    survival_window_days: int = ETH_SHADOW_GRID_SURVIVAL_WINDOW_DAYS_DEFAULT,
    base_strategy_ids: list[str] | None = None,
) -> dict[str, Any]:
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    if survival_window_days <= 0:
        raise ValueError("survival_window_days must be positive")
    strategy_manifest = load_deterministic_strategy_manifest()
    base_strategy_entry = _resolve_eth_base_strategy_entry(
        strategy_manifest=strategy_manifest,
        requested_base_strategy_ids=base_strategy_ids,
    )
    variants = _build_eth_shadow_grid_variants(base_strategy_entry=base_strategy_entry)
    source_commit_sha = required_source_commit_sha(repo_root=ROOT)
    end_date = date.fromisoformat(as_of)
    start_date = end_date - timedelta(days=survival_window_days - 1)
    daily_samples_by_date = {
        current.isoformat(): _load_eth_shadow_grid_daily_sample_if_valid(
            as_of=current.isoformat(),
            artifacts_root=resolved_artifacts_root,
        )
        for current in _date_range(start_date, end_date)
    }

    per_variant: dict[str, Any] = {}
    alpha_like_variant_ids: list[str] = []
    for variant in variants:
        variant_id = str(variant["variant_id"])
        daily_outcomes: list[dict[str, Any]] = []
        breaker_dates: list[str] = []
        current_streak = 0
        max_streak = 0
        previous_date: date | None = None
        for current in _date_range(start_date, end_date):
            current_as_of = current.isoformat()
            outcome_payload = _grid_variant_outcome_from_sample(
                variant_id=variant_id,
                as_of=current_as_of,
                sample=daily_samples_by_date.get(current_as_of),
            )
            daily_outcomes.append(outcome_payload)
            outcome = str(outcome_payload["outcome"] or SURVIVAL_OUTCOME_MISSING)
            if outcome == SURVIVAL_OUTCOME_SURVIVED:
                if previous_date is not None and current == previous_date + timedelta(days=1) and current_streak > 0:
                    current_streak += 1
                else:
                    current_streak = 1
                if current_streak > max_streak:
                    max_streak = current_streak
            else:
                current_streak = 0
                breaker_dates.append(current_as_of)
            previous_date = current
        if current_streak >= survival_window_days:
            alpha_like_variant_ids.append(variant_id)
        per_variant[variant_id] = {
            "variant_id": variant_id,
            "base_strategy_id": str(base_strategy_entry["strategy_id"]),
            "parameter_patch": dict(variant["parameter_patch"]),
            "is_incumbent_control": bool(variant["is_incumbent_control"]),
            "current_consecutive_survival_streak": current_streak,
            "max_consecutive_survival_streak": max_streak,
            "daily_outcomes": daily_outcomes,
            "breaker_dates": breaker_dates,
        }

    output_path = resolved_artifacts_root / "cycles" / as_of / "eth_shadow_survival.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "artifact_family": "quant_eth_shadow_survival",
        "contract_version": ETH_SHADOW_GRID_SURVIVAL_CONTRACT_VERSION,
        "search_mode": ETH_SHADOW_GRID_SEARCH_MODE,
        "survival_window_days": int(survival_window_days),
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "base_strategy_id": str(base_strategy_entry["strategy_id"]),
        "eligible_variant_ids": [str(item["variant_id"]) for item in variants],
        "eligible_variant_count": len(variants),
        "alpha_like_variant_ids": alpha_like_variant_ids,
        "started_looking_like_alpha": bool(alpha_like_variant_ids),
        "per_variant": per_variant,
    }
    payload["survival_hash"] = _stable_payload_hash(payload)
    document = _write_evidence(
        path=output_path,
        payload=payload,
        evidence_family="quant_eth_shadow_survival",
        contract_version=ETH_SHADOW_GRID_SURVIVAL_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )
    document["eth_shadow_survival_path"] = str(output_path)
    return document


def run_btc_shadow_grid_daily_sample(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(
        "BTC shadow grid is retired from the active shadow lane; use run_eth_shadow_grid_daily_sample()"
    )


def run_btc_shadow_grid_survival(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError(
        "BTC shadow grid is retired from the active shadow lane; use run_eth_shadow_grid_survival()"
    )


def _resolve_eth_base_strategy_entry(
    *,
    strategy_manifest: dict[str, Any],
    requested_base_strategy_ids: list[str] | None,
) -> dict[str, Any]:
    requested = sorted({str(item).strip() for item in list(requested_base_strategy_ids or []) if str(item).strip()})
    if requested and requested != [ETH_SHADOW_GRID_BASE_STRATEGY_ID]:
        raise ValueError(
            "ETH-only shadow grid accepts only "
            f"{ETH_SHADOW_GRID_BASE_STRATEGY_ID!r} as base_strategy_id"
        )
    for entry in list(strategy_manifest.get("entries") or []):
        if not isinstance(entry, dict):
            continue
        if not bool(entry.get("enabled")):
            continue
        if str(entry.get("strategy_id") or "").strip() != ETH_SHADOW_GRID_BASE_STRATEGY_ID:
            continue
        if str(entry.get("shape") or "").strip() != "single_asset":
            raise ValueError("ETH shadow grid base strategy must be single_asset")
        return dict(entry)
    raise RuntimeError(f"enabled ETH base strategy not found: {ETH_SHADOW_GRID_BASE_STRATEGY_ID}")


def _build_eth_shadow_grid_variants(*, base_strategy_entry: dict[str, Any]) -> list[dict[str, Any]]:
    base_constraints = dict(base_strategy_entry.get("profile_constraints") or {})
    variants: list[dict[str, Any]] = []
    seen_variant_ids: set[str] = set()
    for neutral_band_abs_score in ETH_SHADOW_GRID_NEUTRAL_BANDS:
        for max_turnover_per_rebalance in ETH_SHADOW_GRID_TURNOVER_CAPS:
            parameter_patch = {
                "execution_venue": "spot",
                "positioning_mode": "long_only",
                "max_turnover_per_rebalance": float(max_turnover_per_rebalance),
                "neutral_band_abs_score": float(neutral_band_abs_score),
            }
            effective_constraints = _apply_parameter_patch_to_constraints(
                base_constraints=base_constraints,
                normalized_patch=parameter_patch,
            )
            risk_blocker = _validate_grid_risk_envelope(
                base_constraints=base_constraints,
                candidate_constraints=effective_constraints,
            )
            if risk_blocker:
                raise ValueError(f"invalid ETH shadow grid variant: {risk_blocker}")
            variant_id = _shadow_grid_variant_id(
                base_strategy_id=str(base_strategy_entry["strategy_id"]),
                parameter_patch=parameter_patch,
            )
            if variant_id in seen_variant_ids:
                continue
            seen_variant_ids.add(variant_id)
            variants.append(
                {
                    "variant_id": variant_id,
                    "shadow_strategy_id": variant_id,
                    "base_strategy_id": str(base_strategy_entry["strategy_id"]),
                    "parameter_patch": dict(parameter_patch),
                    "effective_profile_constraints": effective_constraints,
                    "is_incumbent_control": dict(parameter_patch) == ETH_SHADOW_GRID_INCUMBENT_PATCH,
                }
            )
    variants.sort(key=lambda item: str(item["variant_id"]))
    return variants


def _apply_parameter_patch_to_constraints(
    *,
    base_constraints: dict[str, Any],
    normalized_patch: dict[str, Any],
) -> dict[str, Any]:
    candidate = dict(base_constraints)
    execution_venue = str(normalized_patch.get("execution_venue") or execution_venue_for_constraints(candidate)).strip().lower()
    if execution_venue:
        candidate["execution_venue"] = execution_venue
    positioning_mode = str(normalized_patch.get("positioning_mode") or "").strip().lower()
    if positioning_mode == "long_only":
        candidate["long_only"] = True
        candidate["short_allowed"] = False
        candidate["short_leverage"] = 0.0
    elif positioning_mode == "long_short":
        candidate["long_only"] = False
        candidate["short_allowed"] = True
        candidate["short_leverage"] = float(base_constraints.get("short_leverage", 0.0) or 0.0)
    for key in ("max_turnover_per_rebalance", "neutral_band_abs_score"):
        if key in normalized_patch:
            candidate[key] = float(normalized_patch[key])
    if str(candidate.get("execution_venue") or "").strip().lower() == "spot" and bool(candidate.get("long_only")):
        candidate["long_only_full_size_abs_score"] = max(
            float(candidate.get("neutral_band_abs_score", 0.0) or 0.0) + 0.4,
            1.0,
        )
    else:
        candidate.pop("long_only_full_size_abs_score", None)
    return candidate


def _validate_grid_risk_envelope(
    *,
    base_constraints: dict[str, Any],
    candidate_constraints: dict[str, Any],
) -> str | None:
    if bool(base_constraints.get("spot_only")) and str(candidate_constraints.get("execution_venue") or "").strip().lower() == "perp":
        return "spot_only_base_cannot_switch_to_perp"
    if float(candidate_constraints.get("max_turnover_per_rebalance", 0.0) or 0.0) > float(base_constraints.get("max_turnover_per_rebalance", 0.0) or 0.0):
        return "max_turnover_per_rebalance_exceeds_base_profile"
    if float(candidate_constraints.get("long_leverage", 0.0) or 0.0) > float(base_constraints.get("long_leverage", 0.0) or 0.0):
        return "long_leverage_exceeds_base_profile"
    if float(candidate_constraints.get("short_leverage", 0.0) or 0.0) > float(base_constraints.get("short_leverage", 0.0) or 0.0):
        return "short_leverage_exceeds_base_profile"
    if float(candidate_constraints.get("max_gross_leverage", 0.0) or 0.0) > float(base_constraints.get("max_gross_leverage", 0.0) or 0.0):
        return "max_gross_leverage_exceeds_base_profile"
    if bool(base_constraints.get("long_only")) and not bool(candidate_constraints.get("long_only")):
        return "positioning_mode_exceeds_base_profile"
    if bool(candidate_constraints.get("short_allowed")) and not bool(base_constraints.get("short_allowed")):
        return "short_allowed_exceeds_base_profile"
    return None


def _materialize_grid_strategy(
    *,
    base_strategy_entry: dict[str, Any],
    variant: dict[str, Any],
) -> dict[str, Any]:
    effective_constraints = dict(variant.get("effective_profile_constraints") or {})
    strategy_id = str(variant["shadow_strategy_id"])
    thesis_profile = dict(base_strategy_entry.get("thesis_profile") or {})
    thesis_profile["execution_venue"] = str(
        effective_constraints.get("execution_venue") or execution_venue_for_constraints(effective_constraints)
    )
    thesis_profile["shadow_parameter_patch"] = dict(variant.get("parameter_patch") or {})
    thesis_profile["shadow_base_strategy_id"] = str(base_strategy_entry["strategy_id"])
    thesis_profile["shadow_search_mode"] = ETH_SHADOW_GRID_SEARCH_MODE
    spec_hash = compute_strategy_spec_hash(
        shape=str(base_strategy_entry.get("shape") or ""),
        dataset_profile=str(base_strategy_entry.get("dataset_profile") or ""),
        strategy_profile=str(base_strategy_entry.get("strategy_profile") or ""),
        subject=str(base_strategy_entry.get("subject") or "").strip().upper() or None,
        universe_filter=dict(base_strategy_entry.get("universe_filter") or {}),
        model_family=str(base_strategy_entry.get("model_family") or ""),
        feature_groups=list(base_strategy_entry.get("feature_groups") or []),
        profile_constraints=effective_constraints,
    )
    shadow_entry = dict(base_strategy_entry)
    shadow_entry.update(
        {
            "strategy_id": strategy_id,
            "spec_hash": spec_hash,
            "profile_constraints": effective_constraints,
            "thesis_profile": thesis_profile,
            "source": ETH_SHADOW_GRID_SOURCE,
            "selection_lane": ETH_SHADOW_GRID_SELECTION_LANE,
            "promotion_state": ETH_SHADOW_GRID_PROMOTION_STATE,
            "promotion_eligibility": "ineligible",
            "proposal_origin": str(variant["variant_id"]),
            "search_action": "deterministic_grid_variant",
            "published_via": "not_published",
            "daily_executable": False,
            "lifecycle": "shadow",
            "monitoring_status": "shadow_only",
        }
    )
    return shadow_entry


def _evaluate_grid_variant(
    *,
    as_of: str,
    variant: dict[str, Any],
    variant_root: Path,
    base_strategy_entry: dict[str, Any],
    baseline_context: dict[str, Any],
    feature_sets: list[dict[str, Any]],
    source_commit_sha: str,
    variant_spec_path: Path,
) -> dict[str, Any]:
    shadow_strategy = _materialize_grid_strategy(
        base_strategy_entry=base_strategy_entry,
        variant=variant,
    )
    sandbox_root = variant_root / "sandbox"
    compare_path = variant_root / "variant_vs_baseline.json"
    evaluation_path = variant_root / "variant_evaluation.json"
    try:
        experiments = run_quant_experiments_for_strategies(
            as_of=as_of,
            artifacts_root=sandbox_root,
            strategies=[shadow_strategy],
            feature_sets=feature_sets,
            compiler_backend="deterministic",
            source_commit_sha=source_commit_sha,
        )
    except Exception as exc:
        compare = _write_variant_compare_report(
            path=compare_path,
            as_of=as_of,
            variant=variant,
            baseline_context=baseline_context,
            proposal_experiment=None,
            hard_gate_passed=False,
            better_than_baseline=False,
            comparison_blocker_codes=["grid_evaluation_failed"],
            source_commit_sha=source_commit_sha,
        )
        evaluation = _write_variant_evaluation_report(
            path=evaluation_path,
            variant=variant,
            status="blocked",
            hard_gate_passed=False,
            better_than_baseline=False,
            baseline_context=baseline_context,
            proposal_experiment=None,
            blocker_codes=["grid_evaluation_failed", exc.__class__.__name__],
            compare_report_path=Path(str(compare["path"])),
            source_commit_sha=source_commit_sha,
        )
        return {
            "variant_id": str(variant["variant_id"]),
            "shadow_strategy_id": str(variant["shadow_strategy_id"]),
            "base_strategy_id": str(variant["base_strategy_id"]),
            "parameter_patch": dict(variant["parameter_patch"]),
            "is_incumbent_control": bool(variant["is_incumbent_control"]),
            "outcome": SURVIVAL_OUTCOME_BLOCKED,
            "reason": "grid_evaluation_failed",
            "blocker_codes": ["grid_evaluation_failed", exc.__class__.__name__],
            "hard_gate_passed": False,
            "better_than_baseline": False,
            "baseline_experiment_id": str(baseline_context.get("baseline_experiment_id") or ""),
            "experiment_id": None,
            "variant_spec_path": portable_path(variant_spec_path, repo_root=ROOT),
            "variant_evaluation_path": portable_path(Path(str(evaluation["path"])), repo_root=ROOT),
            "variant_vs_baseline_path": portable_path(Path(str(compare["path"])), repo_root=ROOT),
        }

    proposal_experiment = dict(experiments[0]) if experiments else {}
    if not proposal_experiment:
        compare = _write_variant_compare_report(
            path=compare_path,
            as_of=as_of,
            variant=variant,
            baseline_context=baseline_context,
            proposal_experiment=None,
            hard_gate_passed=False,
            better_than_baseline=False,
            comparison_blocker_codes=["grid_variant_missing_experiment"],
            source_commit_sha=source_commit_sha,
        )
        evaluation = _write_variant_evaluation_report(
            path=evaluation_path,
            variant=variant,
            status="blocked",
            hard_gate_passed=False,
            better_than_baseline=False,
            baseline_context=baseline_context,
            proposal_experiment=None,
            blocker_codes=["grid_variant_missing_experiment"],
            compare_report_path=Path(str(compare["path"])),
            source_commit_sha=source_commit_sha,
        )
        return {
            "variant_id": str(variant["variant_id"]),
            "shadow_strategy_id": str(variant["shadow_strategy_id"]),
            "base_strategy_id": str(variant["base_strategy_id"]),
            "parameter_patch": dict(variant["parameter_patch"]),
            "is_incumbent_control": bool(variant["is_incumbent_control"]),
            "outcome": SURVIVAL_OUTCOME_BLOCKED,
            "reason": "grid_variant_missing_experiment",
            "blocker_codes": ["grid_variant_missing_experiment"],
            "hard_gate_passed": False,
            "better_than_baseline": False,
            "baseline_experiment_id": str(baseline_context.get("baseline_experiment_id") or ""),
            "experiment_id": None,
            "variant_spec_path": portable_path(variant_spec_path, repo_root=ROOT),
            "variant_evaluation_path": portable_path(Path(str(evaluation["path"])), repo_root=ROOT),
            "variant_vs_baseline_path": portable_path(Path(str(compare["path"])), repo_root=ROOT),
        }

    hard_gate_passed = _hard_gate_passed(proposal_experiment=proposal_experiment)
    better_than_baseline = _better_than_baseline(
        proposal_experiment=proposal_experiment,
        baseline_context=baseline_context,
    )
    comparison_blocker_codes: list[str] = []
    if not hard_gate_passed:
        comparison_blocker_codes.append("hard_gate_failed")
    if not better_than_baseline:
        comparison_blocker_codes.append("not_better_than_baseline")
    compare = _write_variant_compare_report(
        path=compare_path,
        as_of=as_of,
        variant=variant,
        baseline_context=baseline_context,
        proposal_experiment=proposal_experiment,
        hard_gate_passed=hard_gate_passed,
        better_than_baseline=better_than_baseline,
        comparison_blocker_codes=comparison_blocker_codes,
        source_commit_sha=source_commit_sha,
    )
    outcome = SURVIVAL_OUTCOME_SURVIVED if hard_gate_passed and better_than_baseline else SURVIVAL_OUTCOME_FAILED
    evaluation = _write_variant_evaluation_report(
        path=evaluation_path,
        variant=variant,
        status="survived" if outcome == SURVIVAL_OUTCOME_SURVIVED else "failed",
        hard_gate_passed=hard_gate_passed,
        better_than_baseline=better_than_baseline,
        baseline_context=baseline_context,
        proposal_experiment=proposal_experiment,
        blocker_codes=comparison_blocker_codes,
        compare_report_path=Path(str(compare["path"])),
        source_commit_sha=source_commit_sha,
    )
    return {
        "variant_id": str(variant["variant_id"]),
        "shadow_strategy_id": str(variant["shadow_strategy_id"]),
        "base_strategy_id": str(variant["base_strategy_id"]),
        "parameter_patch": dict(variant["parameter_patch"]),
        "is_incumbent_control": bool(variant["is_incumbent_control"]),
        "outcome": outcome,
        "reason": "hard_gate_passed_and_better_than_baseline" if outcome == SURVIVAL_OUTCOME_SURVIVED else "grid_variant_failed_same_day_gate",
        "blocker_codes": comparison_blocker_codes,
        "hard_gate_passed": hard_gate_passed,
        "better_than_baseline": better_than_baseline,
        "baseline_experiment_id": str(baseline_context.get("baseline_experiment_id") or ""),
        "experiment_id": str(proposal_experiment.get("experiment_id") or ""),
        "variant_spec_path": portable_path(variant_spec_path, repo_root=ROOT),
        "variant_evaluation_path": portable_path(Path(str(evaluation["path"])), repo_root=ROOT),
        "variant_vs_baseline_path": portable_path(Path(str(compare["path"])), repo_root=ROOT),
    }


def _write_grid_variant_spec(
    *,
    path: Path,
    as_of: str,
    variant: dict[str, Any],
    base_strategy_entry: dict[str, Any],
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = {
        "generated_at_utc": utc_now(),
        "artifact_family": "quant_eth_shadow_grid_variant_spec",
        "contract_version": ETH_SHADOW_GRID_VARIANT_SPEC_CONTRACT_VERSION,
        "as_of": as_of,
        "variant_id": str(variant["variant_id"]),
        "shadow_strategy_id": str(variant["shadow_strategy_id"]),
        "base_strategy_id": str(base_strategy_entry["strategy_id"]),
        "base_strategy_spec_hash": str(base_strategy_entry.get("spec_hash") or ""),
        "parameter_patch": dict(variant["parameter_patch"]),
        "effective_profile_constraints": dict(variant["effective_profile_constraints"]),
        "is_incumbent_control": bool(variant["is_incumbent_control"]),
        "search_mode": ETH_SHADOW_GRID_SEARCH_MODE,
    }
    return _write_evidence(
        path=path,
        payload=payload,
        evidence_family="quant_eth_shadow_grid_variant_spec",
        contract_version=ETH_SHADOW_GRID_VARIANT_SPEC_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )


def _write_grid_variant_manifest(
    *,
    path: Path,
    as_of: str,
    base_strategy_entry: dict[str, Any],
    variants: list[dict[str, Any]],
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = {
        "generated_at_utc": utc_now(),
        "artifact_family": "quant_eth_shadow_grid_variant_manifest",
        "contract_version": ETH_SHADOW_GRID_VARIANT_MANIFEST_CONTRACT_VERSION,
        "as_of": as_of,
        "base_strategy_id": str(base_strategy_entry["strategy_id"]),
        "base_strategy_spec_hash": str(base_strategy_entry.get("spec_hash") or ""),
        "variant_count": len(variants),
        "variant_ids": [str(item["variant_id"]) for item in variants],
        "incumbent_control_variant_ids": [
            str(item["variant_id"]) for item in variants if bool(item.get("is_incumbent_control"))
        ],
        "variants": [
            {
                "variant_id": str(item["variant_id"]),
                "parameter_patch": dict(item["parameter_patch"]),
                "effective_profile_constraints": dict(item["effective_profile_constraints"]),
                "is_incumbent_control": bool(item["is_incumbent_control"]),
            }
            for item in variants
        ],
    }
    return _write_evidence(
        path=path,
        payload=payload,
        evidence_family="quant_eth_shadow_grid_variant_manifest",
        contract_version=ETH_SHADOW_GRID_VARIANT_MANIFEST_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )


def _write_variant_compare_report(
    *,
    path: Path,
    as_of: str,
    variant: dict[str, Any],
    baseline_context: dict[str, Any],
    proposal_experiment: dict[str, Any] | None,
    hard_gate_passed: bool,
    better_than_baseline: bool,
    comparison_blocker_codes: list[str],
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = {
        "generated_at_utc": utc_now(),
        "artifact_family": "quant_eth_shadow_grid_variant_vs_baseline",
        "contract_version": ETH_SHADOW_GRID_VARIANT_VS_BASELINE_CONTRACT_VERSION,
        "as_of": as_of,
        "variant_id": str(variant["variant_id"]),
        "shadow_strategy_id": str(variant["shadow_strategy_id"]),
        "base_strategy_id": str(baseline_context.get("base_strategy_id") or ""),
        "parameter_patch": dict(variant["parameter_patch"]),
        "baseline_experiment_id": str(baseline_context.get("baseline_experiment_id") or ""),
        "proposal_experiment_id": str(proposal_experiment.get("experiment_id") or "") if proposal_experiment else None,
        "baseline_metrics": _comparison_metrics_from_context(baseline_context),
        "proposal_metrics": (
            _comparison_metrics_from_context(
                {
                    "alpha_card": dict(proposal_experiment.get("alpha_card") or {}),
                    "validation_report": dict(proposal_experiment.get("validation_report") or {}),
                }
            )
            if proposal_experiment is not None
            else {}
        ),
        "hard_gate_passed": bool(hard_gate_passed),
        "better_than_baseline": bool(better_than_baseline),
        "comparison_blocker_codes": sorted({str(code).strip() for code in comparison_blocker_codes if str(code).strip()}),
    }
    return _write_evidence(
        path=path,
        payload=payload,
        evidence_family="quant_eth_shadow_grid_variant_vs_baseline",
        contract_version=ETH_SHADOW_GRID_VARIANT_VS_BASELINE_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )


def _write_variant_evaluation_report(
    *,
    path: Path,
    variant: dict[str, Any],
    status: str,
    hard_gate_passed: bool,
    better_than_baseline: bool,
    baseline_context: dict[str, Any],
    proposal_experiment: dict[str, Any] | None,
    blocker_codes: list[str],
    compare_report_path: Path,
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = {
        "generated_at_utc": utc_now(),
        "artifact_family": "quant_eth_shadow_grid_variant_evaluation",
        "contract_version": ETH_SHADOW_GRID_VARIANT_EVALUATION_CONTRACT_VERSION,
        "variant_id": str(variant["variant_id"]),
        "shadow_strategy_id": str(variant["shadow_strategy_id"]),
        "base_strategy_id": str(baseline_context.get("base_strategy_id") or ""),
        "status": status,
        "hard_gate_passed": bool(hard_gate_passed),
        "better_than_baseline": bool(better_than_baseline),
        "baseline_experiment_id": str(baseline_context.get("baseline_experiment_id") or ""),
        "proposal_experiment_id": str(proposal_experiment.get("experiment_id") or "") if proposal_experiment else None,
        "blocker_codes": sorted({str(code).strip() for code in blocker_codes if str(code).strip()}),
        "variant_vs_baseline_path": portable_path(compare_report_path, repo_root=ROOT),
    }
    if proposal_experiment is not None and str(proposal_experiment.get("alpha_card_path") or "").strip():
        payload["sandbox_experiment_root"] = portable_path(
            Path(str(proposal_experiment["alpha_card_path"])).resolve().parent,
            repo_root=ROOT,
        )
    return _write_evidence(
        path=path,
        payload=payload,
        evidence_family="quant_eth_shadow_grid_variant_evaluation",
        contract_version=ETH_SHADOW_GRID_VARIANT_EVALUATION_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )


def _build_accepted_candidates(
    *,
    as_of: str,
    daily_sample: dict[str, Any],
    survival_report: dict[str, Any],
) -> list[dict[str, Any]]:
    sample_by_variant_id = {
        str(item.get("variant_id") or "").strip(): dict(item)
        for item in list(daily_sample.get("variant_samples") or [])
        if isinstance(item, dict) and str(item.get("variant_id") or "").strip()
    }
    accepted_candidates: list[dict[str, Any]] = []
    per_variant = dict(survival_report.get("per_variant") or {})
    survival_report_path = (
        portable_path(Path(str(survival_report.get("eth_shadow_survival_path") or "")), repo_root=ROOT)
        if str(survival_report.get("eth_shadow_survival_path") or "").strip()
        else ""
    )
    for variant_id in list(survival_report.get("alpha_like_variant_ids") or []):
        normalized_variant_id = str(variant_id).strip()
        variant_state = dict(per_variant.get(normalized_variant_id) or {})
        sample_entry = sample_by_variant_id.get(normalized_variant_id)
        if sample_entry is None:
            continue
        if str(sample_entry.get("outcome") or "") != SURVIVAL_OUTCOME_SURVIVED:
            continue
        if int(variant_state.get("current_consecutive_survival_streak") or 0) < int(survival_report.get("survival_window_days") or 0):
            continue
        accepted_candidates.append(
            {
                "proposal_id": normalized_variant_id,
                "variant_id": normalized_variant_id,
                "base_strategy_id": str(sample_entry.get("base_strategy_id") or ""),
                "shadow_strategy_id": str(sample_entry.get("shadow_strategy_id") or ""),
                "parameter_patch": dict(sample_entry.get("parameter_patch") or {}),
                "current_consecutive_survival_streak": int(variant_state.get("current_consecutive_survival_streak") or 0),
                "today_experiment_id": sample_entry.get("experiment_id"),
                "today_variant_vs_baseline_path": str(sample_entry.get("variant_vs_baseline_path") or ""),
                "survival_report_path": survival_report_path,
                "accepted_at_utc": utc_now(),
                "as_of": as_of,
            }
        )
    return accepted_candidates


def _write_shadow_candidate_list(
    *,
    path: Path,
    as_of: str,
    eligible_base_strategy_ids: list[str],
    accepted_candidates: list[dict[str, Any]],
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = {
        "generated_at_utc": utc_now(),
        "artifact_family": "quant_shadow_candidate_list",
        "contract_version": SHADOW_CANDIDATE_LIST_CONTRACT_VERSION,
        "as_of": as_of,
        "eligible_base_strategy_ids": list(eligible_base_strategy_ids),
        "accepted_candidate_count": len(accepted_candidates),
        "accepted_candidates": accepted_candidates,
    }
    document = _write_evidence(
        path=path,
        payload=payload,
        evidence_family="quant_shadow_candidate_list",
        contract_version=SHADOW_CANDIDATE_LIST_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )
    document["path"] = str(path)
    return document


def _write_grid_cycle_summary(
    *,
    path: Path,
    as_of: str,
    strategy_manifest: dict[str, Any],
    base_strategy_entry: dict[str, Any],
    daily_samples: list[dict[str, Any]],
    survival_report: dict[str, Any],
    candidate_list_path: Path,
    accepted_candidates: list[dict[str, Any]],
    survival_window_days: int,
    source_commit_sha: str,
) -> dict[str, Any]:
    today_daily_sample = daily_samples[-1]
    grid_variant_ids = [
        str(item.get("variant_id") or "").strip()
        for item in list(today_daily_sample.get("variant_samples") or [])
        if str(item.get("variant_id") or "").strip()
    ]
    payload = {
        "status": "success",
        "success": True,
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "artifact_family": "quant_eth_shadow_grid_cycle",
        "contract_version": ETH_SHADOW_GRID_CYCLE_SUMMARY_CONTRACT_VERSION,
        "strategy_manifest_path": str(strategy_manifest.get("path") or ""),
        "strategy_manifest_contract_version": str(strategy_manifest.get("contract_version") or ""),
        "search_mode": ETH_SHADOW_GRID_SEARCH_MODE,
        "base_strategy_id": str(base_strategy_entry["strategy_id"]),
        "eligible_base_strategy_count": 1,
        "eligible_base_strategy_ids": [str(base_strategy_entry["strategy_id"])],
        "survival_window_days": int(survival_window_days),
        "date_window": [str(item.get("as_of") or "") for item in daily_samples],
        "daily_sample_paths": [
            portable_path(Path(str(item.get("eth_shadow_grid_daily_sample_path") or "")), repo_root=ROOT)
            for item in daily_samples
            if str(item.get("eth_shadow_grid_daily_sample_path") or "").strip()
        ],
        "grid_variant_count": len(grid_variant_ids),
        "grid_variant_ids": grid_variant_ids,
        "survival_report_path": (
            portable_path(Path(str(survival_report.get("eth_shadow_survival_path") or "")), repo_root=ROOT)
            if str(survival_report.get("eth_shadow_survival_path") or "").strip()
            else ""
        ),
        "accepted_candidate_count": len(accepted_candidates),
        "candidate_list_path": portable_path(candidate_list_path, repo_root=ROOT),
        "started_looking_like_alpha": bool(survival_report.get("started_looking_like_alpha")),
    }
    payload["summary_hash"] = sha256_canonical_json(payload)
    document = _write_evidence(
        path=path,
        payload=payload,
        evidence_family="quant_eth_shadow_grid_cycle",
        contract_version=ETH_SHADOW_GRID_CYCLE_SUMMARY_CONTRACT_VERSION,
        source_commit_sha=source_commit_sha,
    )
    document["summary_path"] = str(path)
    return document


def _blocked_variant_sample(
    *,
    as_of: str,
    variant: dict[str, Any],
    blocker_codes: list[str],
    reason: str,
    variant_spec_path: Path,
) -> dict[str, Any]:
    return {
        "as_of": as_of,
        "variant_id": str(variant["variant_id"]),
        "shadow_strategy_id": str(variant["shadow_strategy_id"]),
        "base_strategy_id": str(variant["base_strategy_id"]),
        "parameter_patch": dict(variant["parameter_patch"]),
        "is_incumbent_control": bool(variant["is_incumbent_control"]),
        "outcome": SURVIVAL_OUTCOME_BLOCKED,
        "reason": reason,
        "blocker_codes": _ordered_unique_strings(blocker_codes),
        "hard_gate_passed": False,
        "better_than_baseline": False,
        "baseline_experiment_id": None,
        "experiment_id": None,
        "variant_spec_path": portable_path(variant_spec_path, repo_root=ROOT),
        "variant_evaluation_path": None,
        "variant_vs_baseline_path": None,
    }


def _load_feature_sets_from_cycle_summary(*, cycle_summary: dict[str, Any]) -> list[dict[str, Any]]:
    feature_manifests = [
        resolve_portable_path(item, repo_root=ROOT)
        for item in list(cycle_summary.get("feature_manifests") or [])
        if str(item).strip()
    ]
    if not feature_manifests:
        raise RuntimeError("canonical cycle summary missing feature_manifests")
    feature_sets = [_load_feature_set_from_manifest(manifest_path=path) for path in feature_manifests]
    shapes = {str(item.get("shape") or "") for item in feature_sets}
    if "single_asset" not in shapes or "cross_sectional" not in shapes:
        raise RuntimeError("canonical cycle summary must provide both single_asset and cross_sectional feature sets")
    return feature_sets


def _load_feature_set_from_manifest(*, manifest_path: Path) -> dict[str, Any]:
    manifest = dict(read_json(manifest_path))
    features_path = manifest_path.parent / "features.csv.gz"
    if not features_path.exists():
        raise FileNotFoundError(f"feature matrix missing for canonical feature set: {features_path}")
    feature_frame = pd.read_csv(features_path)
    dataset_manifest_path_ref = str(manifest.get("dataset_manifest_path") or "").strip()
    dataset_manifest = {}
    if dataset_manifest_path_ref:
        dataset_manifest = dict(read_json(resolve_portable_path(dataset_manifest_path_ref, repo_root=ROOT)))
    return {
        "feature_set_id": str(manifest.get("feature_set_id") or ""),
        "dataset_id": str(manifest.get("dataset_id") or ""),
        "shape": str(manifest.get("shape") or ""),
        "features_path": str(features_path),
        "manifest_path": str(manifest_path),
        "dataframe": feature_frame,
        "available_numeric_columns": list(manifest.get("available_numeric_columns") or []),
        "numeric_feature_columns": list(manifest.get("numeric_feature_columns") or []),
        "excluded_numeric_columns": list(manifest.get("excluded_numeric_columns") or []),
        "feature_admission_policy": dict(manifest.get("feature_admission_policy") or {}),
        "feature_quality_frame": pd.DataFrame({"subject": pd.Series(dtype="object")}),
        "feature_quality": dict(manifest.get("feature_quality") or {}),
        "derivatives_quality_frame": pd.DataFrame({"subject": pd.Series(dtype="object")}),
        "derivatives_feature_quality": dict(manifest.get("derivatives_feature_quality") or {}),
        "split_realization_contract": dict(manifest.get("split_realization_contract") or {}),
        "dataset_data_readiness": dict(dataset_manifest.get("data_readiness") or {}),
        "dataset_fingerprint": str(manifest.get("dataset_fingerprint") or ""),
        "dataset_manifest_path": str(resolve_portable_path(dataset_manifest_path_ref, repo_root=ROOT)) if dataset_manifest_path_ref else "",
        "feature_hash": str(manifest.get("feature_hash") or ""),
        "universe_definition_id": str(manifest.get("universe_definition_id") or ""),
        "universe_contract_version": str(manifest.get("universe_contract_version") or ""),
        "universe_snapshot_path": (
            str(resolve_portable_path(str(manifest.get("universe_snapshot_path") or ""), repo_root=ROOT))
            if str(manifest.get("universe_snapshot_path") or "").strip()
            else ""
        ),
        "universe_selection_policy_hash": str(manifest.get("universe_selection_policy_hash") or ""),
    }


def _load_baseline_context(
    *,
    as_of: str,
    artifacts_root: Path,
    base_strategy_entry: dict[str, Any],
    daily_sample_entry: dict[str, Any],
) -> dict[str, Any] | None:
    experiment_id = str(daily_sample_entry.get("experiment_id") or "").strip()
    if not experiment_id:
        return None
    resolved_paths = resolve_experiment_artifact_paths(
        experiment_id=experiment_id,
        artifacts_root=artifacts_root,
    )
    if resolved_paths is None:
        return None
    experiment_root, alpha_card_path, validation_report_path = resolved_paths
    alpha_card = dict(read_json(alpha_card_path))
    validation_report = dict(read_json(validation_report_path))
    return {
        "as_of": as_of,
        "base_strategy_id": str(base_strategy_entry["strategy_id"]),
        "base_strategy_entry": dict(base_strategy_entry),
        "daily_sample_entry": dict(daily_sample_entry),
        "baseline_experiment_id": experiment_id,
        "alpha_card": alpha_card,
        "validation_report": validation_report,
        "experiment_root": str(experiment_root),
        "alpha_card_path": str(alpha_card_path),
        "validation_report_path": str(validation_report_path),
    }


def _base_strategy_is_blocked(sample_entry: dict[str, Any]) -> bool:
    if not sample_entry:
        return True
    return str(sample_entry.get("outcome") or "").strip() in {SURVIVAL_OUTCOME_BLOCKED, SURVIVAL_OUTCOME_MISSING}


def _hard_gate_passed(*, proposal_experiment: dict[str, Any]) -> bool:
    alpha_card = dict(proposal_experiment.get("alpha_card") or {})
    validation_report = dict(proposal_experiment.get("validation_report") or {})
    validation_contract = dict(validation_report.get("validation_contract") or alpha_card.get("validation_contract") or {})
    falsification_status = str(alpha_card.get("falsification_status") or validation_report.get("falsification_status") or "").strip()
    credible_research_evidence = bool(alpha_card.get("credible_research_evidence", validation_report.get("credible_research_evidence", False)))
    execution_stress = dict(validation_report.get("execution_stress") or alpha_card.get("execution_stress") or {})
    regime_holdout = dict(validation_report.get("regime_holdout") or alpha_card.get("regime_holdout") or {})
    return (
        str(validation_contract.get("status") or "").strip() == "passed"
        and credible_research_evidence
        and falsification_status in {"cleared", "not_required"}
        and bool(execution_stress.get("passed"))
        and bool(regime_holdout.get("passed"))
    )


def _better_than_baseline(
    *,
    proposal_experiment: dict[str, Any],
    baseline_context: dict[str, Any],
) -> bool:
    proposal_alpha_card = dict(proposal_experiment.get("alpha_card") or {})
    proposal_validation = dict(proposal_experiment.get("validation_report") or {})
    baseline_alpha_card = dict(baseline_context.get("alpha_card") or {})
    baseline_validation = dict(baseline_context.get("validation_report") or {})
    proposal_test = dict(proposal_validation.get("test_metrics") or proposal_alpha_card.get("test_metrics") or {})
    baseline_test = dict(baseline_validation.get("test_metrics") or baseline_alpha_card.get("test_metrics") or {})
    proposal_walk_forward = dict(proposal_validation.get("walk_forward_assessment") or proposal_alpha_card.get("walk_forward_assessment") or {})
    baseline_walk_forward = dict(baseline_validation.get("walk_forward_assessment") or baseline_alpha_card.get("walk_forward_assessment") or {})
    proposal_regime = dict(proposal_validation.get("regime_holdout") or proposal_alpha_card.get("regime_holdout") or {})
    baseline_regime = dict(baseline_validation.get("regime_holdout") or baseline_alpha_card.get("regime_holdout") or {})
    proposal_stress = dict(proposal_validation.get("execution_stress") or proposal_alpha_card.get("execution_stress") or {})
    baseline_stress = dict(baseline_validation.get("execution_stress") or baseline_alpha_card.get("execution_stress") or {})
    return (
        float(proposal_test.get("net_return", float("-inf")) or float("-inf")) > float(baseline_test.get("net_return", float("-inf")) or float("-inf"))
        and float(proposal_walk_forward.get("median_oos_sharpe", float("-inf")) or float("-inf")) > float(baseline_walk_forward.get("median_oos_sharpe", float("-inf")) or float("-inf"))
        and float(proposal_regime.get("positive_regime_fraction", float("-inf")) or float("-inf")) >= float(baseline_regime.get("positive_regime_fraction", float("-inf")) or float("-inf"))
        and float(proposal_stress.get("max_participation_rate", float("inf")) or float("inf")) <= float(baseline_stress.get("max_participation_rate", float("inf")) or float("inf"))
    )


def _comparison_metrics_from_context(context: dict[str, Any]) -> dict[str, Any]:
    alpha_card = dict(context.get("alpha_card") or {})
    validation_report = dict(context.get("validation_report") or {})
    validation_contract = dict(validation_report.get("validation_contract") or alpha_card.get("validation_contract") or {})
    return {
        "validation_contract_status": str(validation_contract.get("status") or "").strip(),
        "validation_metrics": dict(validation_report.get("validation_metrics") or alpha_card.get("validation_metrics") or {}),
        "test_metrics": dict(validation_report.get("test_metrics") or alpha_card.get("test_metrics") or {}),
        "walk_forward_assessment": dict(validation_report.get("walk_forward_assessment") or alpha_card.get("walk_forward_assessment") or {}),
        "execution_stress": dict(validation_report.get("execution_stress") or alpha_card.get("execution_stress") or {}),
        "regime_holdout": dict(validation_report.get("regime_holdout") or alpha_card.get("regime_holdout") or {}),
        "falsification_status": str(alpha_card.get("falsification_status") or validation_report.get("falsification_status") or "").strip(),
        "falsification_blocker_codes": list(alpha_card.get("falsification_blocker_codes") or validation_report.get("falsification_blocker_codes") or []),
        "credible_research_evidence": bool(alpha_card.get("credible_research_evidence", validation_report.get("credible_research_evidence", False))),
    }


def _load_eth_shadow_grid_daily_sample_if_valid(*, as_of: str, artifacts_root: Path) -> dict[str, Any] | None:
    path = artifacts_root / "cycles" / as_of / "eth_shadow_grid_daily_sample.json"
    if not path.exists():
        return None
    try:
        payload = dict(read_json(path))
    except Exception:
        return None
    if str(payload.get("contract_version") or "").strip() != ETH_SHADOW_GRID_DAILY_SAMPLE_CONTRACT_VERSION:
        return None
    payload["path"] = str(path)
    return payload


def _grid_variant_outcome_from_sample(
    *,
    variant_id: str,
    as_of: str,
    sample: dict[str, Any] | None,
) -> dict[str, Any]:
    if sample is None:
        return {
            "as_of": as_of,
            "outcome": SURVIVAL_OUTCOME_MISSING,
            "reason": "missing_grid_daily_sample_artifact",
            "blocker_codes": [],
            "experiment_id": None,
        }
    sample_by_variant_id = {
        str(item.get("variant_id") or "").strip(): dict(item)
        for item in list(sample.get("variant_samples") or [])
        if isinstance(item, dict) and str(item.get("variant_id") or "").strip()
    }
    variant_sample = sample_by_variant_id.get(variant_id)
    if variant_sample is None:
        return {
            "as_of": as_of,
            "outcome": SURVIVAL_OUTCOME_MISSING,
            "reason": "variant_missing_from_grid_daily_sample",
            "blocker_codes": [],
            "experiment_id": None,
        }
    return {
        "as_of": as_of,
        "outcome": str(variant_sample.get("outcome") or SURVIVAL_OUTCOME_MISSING),
        "reason": str(variant_sample.get("reason") or "").strip(),
        "blocker_codes": _ordered_unique_strings(list(variant_sample.get("blocker_codes") or [])),
        "experiment_id": variant_sample.get("experiment_id"),
        "hard_gate_passed": bool(variant_sample.get("hard_gate_passed")),
        "better_than_baseline": bool(variant_sample.get("better_than_baseline")),
    }


def _shadow_grid_variant_id(*, base_strategy_id: str, parameter_patch: dict[str, Any]) -> str:
    digest = sha256_canonical_json(
        {
            "base_strategy_id": base_strategy_id,
            "parameter_patch": parameter_patch,
        }
    )[:12]
    return f"eth-shadow-variant-{digest}"


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at_utc", "produced_at_utc"}
    }
    return sha256_canonical_json(canonical)


def _count_variant_outcomes(variant_samples: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        SURVIVAL_OUTCOME_SURVIVED: 0,
        SURVIVAL_OUTCOME_FAILED: 0,
        SURVIVAL_OUTCOME_BLOCKED: 0,
        SURVIVAL_OUTCOME_MISSING: 0,
    }
    for sample in variant_samples:
        outcome = str(sample.get("outcome") or "").strip()
        if outcome not in counts:
            counts[outcome] = 0
        counts[outcome] += 1
    return counts


def _ordered_unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


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
    path.write_text(json.dumps(document, indent=2, sort_keys=True, default=str), encoding="utf-8")
    document["path"] = str(path)
    return document
