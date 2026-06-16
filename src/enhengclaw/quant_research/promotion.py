from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import current_source_commit_sha, with_evidence_metadata

from .alpha_manifest import load_daily_alpha_manifest
from .contracts import (
    pit_universe_artifact_is_valid,
    pit_universe_artifact_metadata,
    portable_path,
    read_json,
    resolve_portable_path,
    utc_now,
    write_json,
)
from .experiment_status import is_rerun_required_experiment_status
from .fixed_set_comparison import (
    fixed_set_comparison_applicability,
    load_fixed_set_comparison_contract,
)
from .legacy_surface import raise_legacy_surface_frozen
from .falsification_audit import (
    INVALIDATED_UNVERIFIED_RESEARCH_EVIDENCE,
    NOT_REQUIRED_FALSIFICATION_STATUS,
    falsification_is_required,
)
from .validation_contract import (
    VALIDATION_CONTRACT_VERSION,
    sharpe_anomaly_details,
    validation_contract_blocker_codes,
)


ROOT = Path(__file__).resolve().parents[3]
PROJECT_PROFILE_PATH = ROOT / "config" / "project_governance" / "project_profile.json"
STAGE_CONTRACT_PATH = ROOT / "config" / "project_governance" / "stage_contract.json"
PUBLICATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "publication_contract.json"
H10D_PROMOTION_GATE_CONTRACT_PATH = ROOT / "config" / "quant_research" / "promotion_gate_h10d.json"
H10D_PROMOTION_GATE_CONTRACT_VERSION = "quant_h10d_promotion_gate.v1"
PROMOTION_DECISION_CONTRACT_VERSION = "quant_promotion_decision.v2"
PROMOTION_DECISION_EVIDENCE_FAMILY = "quant_promotion_decision"
VOLATILE_METRICS_SNAPSHOT_FIELDS: set[str] = set()


def promotion_decision_root(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "governance" / "promotion_decisions" / as_of


def promotion_decision_path(*, artifacts_root: Path, as_of: str, alpha_id: str) -> Path:
    return promotion_decision_root(artifacts_root=artifacts_root, as_of=as_of) / f"{alpha_id}.promotion_decision.json"


def load_publication_contract() -> dict[str, Any]:
    return read_json(PUBLICATION_CONTRACT_PATH)


def load_h10d_promotion_gate_contract() -> dict[str, Any]:
    payload = dict(read_json(H10D_PROMOTION_GATE_CONTRACT_PATH))
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != H10D_PROMOTION_GATE_CONTRACT_VERSION:
        raise ValueError(
            "h10d promotion gate contract_version mismatch: "
            f"{contract_version or 'missing'}"
        )
    return payload


def publication_threshold(publication_contract: dict[str, Any], field_name: str, default: Any) -> Any:
    thresholds = dict(publication_contract.get("thresholds") or {})
    value = thresholds.get(field_name, default)
    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


def h10d_promotion_evidence_blockers(
    *,
    alpha_card: dict[str, Any],
    strategy_entry: dict[str, Any] | None = None,
    require_applicable: bool = False,
) -> list[str]:
    """Return hard blockers for the h10d promotion-evidence guard."""
    strategy_payload = strategy_entry or {}
    h10d_promotion_contract = load_h10d_promotion_gate_contract()
    applicability = fixed_set_comparison_applicability(
        shape=str(alpha_card.get("shape") or ""),
        bar_interval_ms=int(alpha_card.get("bar_interval_ms") or 0),
        target_horizon_bars=int(alpha_card.get("label_horizon_bars") or 0),
        label_contract_id=str(alpha_card.get("label_contract_id") or ""),
        research_lane=str(strategy_payload.get("research_lane", alpha_card.get("research_lane")) or ""),
        contract=h10d_promotion_contract,
    )
    if not bool(applicability.get("applicable")):
        if not require_applicable:
            return []
        reason_codes = [
            str(item).strip()
            for item in list(applicability.get("reason_codes") or [])
            if str(item).strip()
        ]
        return [
            "h10d_promotion.not_applicable"
            + (f":{','.join(reason_codes)}" if reason_codes else "")
        ]

    fixed_set_comparison = dict(alpha_card.get("fixed_set_comparison") or {})
    fixed_set_promotion_gate = dict(fixed_set_comparison.get("promotion_gate") or {})
    overlay_ablation = dict(alpha_card.get("overlay_ablation") or {})
    overlay_ablation_promotion_gate = dict(overlay_ablation.get("promotion_gate") or {})
    required_evidence = dict(h10d_promotion_contract.get("required_evidence") or {})
    fixed_set_rules = dict(required_evidence.get("fixed_set_comparison") or {})
    capacity_rules = dict(required_evidence.get("capacity") or {})
    overlay_rules = dict(required_evidence.get("overlay_ablation") or {})
    blocker_attribution_rules = dict(required_evidence.get("blocker_attribution") or {})

    blockers: list[str] = []
    fixed_set_status = str(fixed_set_comparison.get("status") or "missing").strip() or "missing"
    if fixed_set_status != str(fixed_set_rules.get("status") or "computed"):
        blockers.append(f"h10d_promotion.fixed_set_comparison.status={fixed_set_status} is not computed")
    if bool(fixed_set_rules.get("promotion_gate_passed", True)) and not bool(fixed_set_promotion_gate.get("passed")):
        blockers.append("h10d_promotion.fixed_set_comparison.promotion_gate_not_passed")
    for blocker_code in [
        str(item).strip()
        for item in list(fixed_set_promotion_gate.get("blocker_codes") or [])
        if str(item).strip()
    ]:
        blockers.append(f"fixed_set_comparison.blocker_code={blocker_code}")

    fixed_set_candidate_summary = dict(fixed_set_promotion_gate.get("candidate_summary") or {})
    full_oos_period_count = int(fixed_set_candidate_summary.get("full_oos_period_count", 0) or 0)
    full_oos_period_count_min = int(fixed_set_rules.get("full_oos_period_count_min", 0) or 0)
    if full_oos_period_count < full_oos_period_count_min:
        blockers.append(
            "h10d_promotion.full_oos_period_count="
            f"{full_oos_period_count} is below minimum {full_oos_period_count_min}"
        )
    max_trade_participation_rate = float(
        fixed_set_candidate_summary.get("full_oos_max_trade_participation_rate", 0.0) or 0.0
    )
    max_trade_participation_rate_max = float(
        capacity_rules.get("max_trade_participation_rate_max", 0.005) or 0.005
    )
    if max_trade_participation_rate > max_trade_participation_rate_max:
        blockers.append(
            "h10d_promotion.full_oos_max_trade_participation_rate="
            f"{max_trade_participation_rate} exceeds {max_trade_participation_rate_max}"
        )

    overlay_status = str(overlay_ablation.get("status") or "missing").strip() or "missing"
    if overlay_status != str(overlay_rules.get("status") or "computed"):
        blockers.append(f"h10d_promotion.overlay_ablation.status={overlay_status} is not computed")
    if bool(overlay_rules.get("promotion_gate_passed", True)) and not bool(
        overlay_ablation_promotion_gate.get("passed")
    ):
        blockers.append("h10d_promotion.overlay_ablation.promotion_gate_not_passed")
    for blocker_code in [
        str(item).strip()
        for item in list(overlay_ablation_promotion_gate.get("blocker_codes") or [])
        if str(item).strip()
    ]:
        blockers.append(f"overlay_ablation.blocker_code={blocker_code}")
    blockers.extend(
        _h10d_blocker_attribution_gate_blockers(
            alpha_card=alpha_card,
            rules=blocker_attribution_rules,
        )
    )
    return blockers


def _h10d_blocker_attribution_gate_blockers(
    *,
    alpha_card: dict[str, Any],
    rules: dict[str, Any],
) -> list[str]:
    if not rules:
        return []
    gate = dict(alpha_card.get("blocker_attribution_gate") or {})
    status = str(gate.get("status") or "missing").strip() or "missing"
    required_status = str(rules.get("status") or "").strip()
    blockers: list[str] = []
    if required_status and status != required_status:
        blockers.append(
            "h10d_promotion.blocker_attribution.status="
            f"{status} is not {required_status}"
        )
    if bool(rules.get("strict_gate_passed", True)) and not bool(gate.get("passed")):
        blockers.append("h10d_promotion.blocker_attribution.strict_gate_not_passed")
    for blocker_code in [
        str(item).strip()
        for item in list(gate.get("blocker_codes") or [])
        if str(item).strip()
    ]:
        blockers.append(f"blocker_attribution.blocker_code={blocker_code}")
    required_policy = str(rules.get("missing_statistical_falsification_policy") or "").strip()
    observed_policy = str(gate.get("missing_statistical_falsification_policy") or "").strip()
    if required_policy and observed_policy and observed_policy != required_policy:
        blockers.append(
            "h10d_promotion.blocker_attribution.missing_statistical_falsification_policy="
            f"{observed_policy} is not {required_policy}"
        )
    return blockers


def current_project_stage() -> str:
    profile = read_json(PROJECT_PROFILE_PATH)
    return str(profile.get("current_stage", "")).strip()


def evaluate_quant_publication_assessment(
    *,
    alpha_card: dict[str, Any],
    strategy_entry: dict[str, Any] | None,
    artifacts_root: Path | None = None,
) -> dict[str, Any]:
    publication_contract = load_publication_contract()
    stage_contract = read_json(STAGE_CONTRACT_PATH)
    current_stage = current_project_stage()
    minimum_stage = str(publication_contract.get("minimum_stage_for_incoming", "")).strip()
    archive_only_stages = {str(item) for item in publication_contract.get("archive_only_stages", [])}

    lifecycle = strategy_lifecycle(strategy_entry or alpha_card)
    experiment_status = alpha_experiment_status(alpha_card)
    backend_mode = alpha_backend_mode(alpha_card)
    daily_pass_streak = int((strategy_entry or {}).get("daily_pass_streak", alpha_card.get("daily_pass_streak", 0)) or 0)
    last_transition_reason = str((strategy_entry or {}).get("last_transition_reason", alpha_card.get("last_transition_reason", "")) or "")
    proposal_origin = str((strategy_entry or {}).get("proposal_origin", alpha_card.get("proposal_origin", "heuristic")) or "heuristic")
    auto_bridge_requested = bool((strategy_entry or {}).get("auto_bridge_requested", alpha_card.get("auto_bridge_requested", False)))

    validation_metrics = dict(alpha_card.get("validation_metrics") or {})
    test_metrics = dict(alpha_card.get("test_metrics") or {})
    walk_forward = dict(alpha_card.get("walk_forward") or {})
    validation_contract = dict(alpha_card.get("validation_contract") or {})
    overlap_integrity = dict(alpha_card.get("overlap_integrity") or {})
    derivatives_strategy_quality = dict(alpha_card.get("derivatives_strategy_quality") or {})
    fixed_set_comparison = dict(alpha_card.get("fixed_set_comparison") or {})
    fixed_set_contract = load_fixed_set_comparison_contract()
    fixed_set_applicability = fixed_set_comparison_applicability(
        shape=str(alpha_card.get("shape") or ""),
        bar_interval_ms=int(alpha_card.get("bar_interval_ms") or 0),
        target_horizon_bars=int(alpha_card.get("label_horizon_bars") or 0),
        label_contract_id=str(alpha_card.get("label_contract_id") or ""),
        research_lane=str((strategy_entry or {}).get("research_lane", alpha_card.get("research_lane")) or ""),
        contract=fixed_set_contract,
    )
    fixed_set_promotion_gate = dict(fixed_set_comparison.get("promotion_gate") or {})
    h10d_promotion_contract = load_h10d_promotion_gate_contract()
    h10d_promotion_applicability = fixed_set_comparison_applicability(
        shape=str(alpha_card.get("shape") or ""),
        bar_interval_ms=int(alpha_card.get("bar_interval_ms") or 0),
        target_horizon_bars=int(alpha_card.get("label_horizon_bars") or 0),
        label_contract_id=str(alpha_card.get("label_contract_id") or ""),
        research_lane=str((strategy_entry or {}).get("research_lane", alpha_card.get("research_lane")) or ""),
        contract=h10d_promotion_contract,
    )
    overlay_ablation = dict(alpha_card.get("overlay_ablation") or {})
    overlay_ablation_promotion_gate = dict(overlay_ablation.get("promotion_gate") or {})
    blocker_attribution_gate = dict(alpha_card.get("blocker_attribution_gate") or {})
    h10d_evidence_blockers = h10d_promotion_evidence_blockers(
        alpha_card=alpha_card,
        strategy_entry=strategy_entry or {},
    )
    window_count = int(walk_forward.get("window_count", 0) or 0)
    median_oos_sharpe = float(walk_forward.get("median_oos_sharpe", 0.0) or 0.0)
    validation_contract_status = str(validation_contract.get("status") or "").strip()
    validation_contract_version = str(validation_contract.get("contract_version") or "").strip()
    validation_contract_blockers = validation_contract_blocker_codes(validation_contract)
    universe_metadata = pit_universe_artifact_metadata(alpha_card)
    pit_universe_valid = pit_universe_artifact_is_valid(universe_metadata)
    alpha_id = str(alpha_card.get("experiment_id") or "").strip()
    as_of = str(alpha_card.get("as_of") or "").strip()
    falsification_status = str(alpha_card.get("falsification_status") or NOT_REQUIRED_FALSIFICATION_STATUS).strip()
    falsification_audit_path = str(alpha_card.get("falsification_audit_path") or "").strip() or None
    falsification_blocker_codes = [
        str(item).strip()
        for item in list(alpha_card.get("falsification_blocker_codes") or [])
        if str(item).strip()
    ]
    credible_research_evidence = bool(alpha_card.get("credible_research_evidence"))
    requires_falsification = falsification_is_required(
        experiment_status=experiment_status,
        validation_contract=validation_contract,
        blocker_codes=validation_contract_blockers,
    )
    metrics_snapshot = {
        "current_stage": current_stage,
        "lifecycle": lifecycle,
        "experiment_status": experiment_status,
        "backend_mode": backend_mode,
        "daily_pass_streak": daily_pass_streak,
        "last_transition_reason": last_transition_reason,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "walk_forward": walk_forward,
        "validation_contract": validation_contract,
        "proposal_origin": proposal_origin,
        "auto_bridge_requested": auto_bridge_requested,
        **universe_metadata,
        "pit_universe_valid": pit_universe_valid,
        "falsification_status": falsification_status,
        "falsification_audit_path": falsification_audit_path,
        "falsification_blocker_codes": falsification_blocker_codes,
        "credible_research_evidence": credible_research_evidence,
        "fixed_set_comparison": {
            "applicable": bool(fixed_set_applicability.get("applicable")),
            "status": str(fixed_set_comparison.get("status") or "missing"),
            "candidate_label": str(fixed_set_comparison.get("candidate_label") or ""),
            "promotion_gate_passed": bool(fixed_set_promotion_gate.get("passed"))
            if fixed_set_comparison
            else None,
            "promotion_gate_blocker_codes": [
                str(item).strip()
                for item in list(fixed_set_promotion_gate.get("blocker_codes") or [])
                if str(item).strip()
            ],
        },
        "overlay_ablation": {
            "status": str(overlay_ablation.get("status") or "missing"),
            "candidate_label": str(overlay_ablation.get("candidate_label") or ""),
            "promotion_gate_passed": bool(overlay_ablation_promotion_gate.get("passed"))
            if overlay_ablation
            else None,
            "promotion_gate_blocker_codes": [
                str(item).strip()
                for item in list(overlay_ablation_promotion_gate.get("blocker_codes") or [])
                if str(item).strip()
            ],
        },
        "h10d_promotion_gate": {
            "applicable": bool(h10d_promotion_applicability.get("applicable")),
            "reason_codes": list(h10d_promotion_applicability.get("reason_codes") or []),
            "contract_version": str(h10d_promotion_contract.get("contract_version") or ""),
            "validation_contract_role": str(h10d_promotion_contract.get("validation_contract_role") or ""),
            "blocker_attribution_gate_status": str(blocker_attribution_gate.get("status") or "missing"),
            "blocker_attribution_gate_passed": bool(blocker_attribution_gate.get("passed"))
            if blocker_attribution_gate
            else None,
            "blocker_attribution_blocker_codes": [
                str(item).strip()
                for item in list(blocker_attribution_gate.get("blocker_codes") or [])
                if str(item).strip()
            ],
            "evidence_guard_passed": (not h10d_evidence_blockers)
            if bool(h10d_promotion_applicability.get("applicable"))
            else None,
            "evidence_guard_blockers": list(h10d_evidence_blockers),
        },
    }
    structural_quality_blocker = bool(
        int(derivatives_strategy_quality.get("blocking_count", derivatives_strategy_quality.get("blocker_count", 0)) or 0) > 0
    )
    auto_bridge_eligible = bool(
        proposal_origin == "agent"
        and auto_bridge_requested
        and backend_mode == "live"
        and experiment_status == "pass"
        and validation_contract_status == "passed"
        and (not requires_falsification or falsification_status == "cleared")
        and credible_research_evidence
        and not structural_quality_blocker
    )
    metrics_snapshot["auto_bridge_eligible"] = auto_bridge_eligible
    metrics_snapshot["structural_quality_blocker"] = structural_quality_blocker
    if not pit_universe_valid:
        return {
            "backend_mode": backend_mode,
            "current_stage": current_stage,
            "publication_status": "archived_only",
            "validation": "invalidated_non_point_in_time_universe",
            "falsification_status": falsification_status,
            "quality_gate_passed": False,
            "quality_blockers": ["non_point_in_time_universe"],
            "metrics_snapshot": metrics_snapshot,
        }
    if auto_bridge_eligible:
        return {
            "backend_mode": backend_mode,
            "current_stage": current_stage,
            "publication_status": "publishable_to_incoming_auto",
            "validation": "passed",
            "falsification_status": falsification_status,
            "quality_gate_passed": True,
            "quality_blockers": [],
            "metrics_snapshot": metrics_snapshot,
        }

    blockers: list[str] = []
    if validation_contract_version != VALIDATION_CONTRACT_VERSION:
        blockers.append(
            "validation_contract.contract_version="
            f"{validation_contract_version or 'missing'} is not {VALIDATION_CONTRACT_VERSION}"
        )
    if validation_contract_status != "passed":
        blockers.append(
            "validation_contract.status="
            f"{validation_contract_status or 'missing'} is not passed"
        )
    for blocker_code in validation_contract_blockers:
        blockers.append(f"validation_contract.blocker_code={blocker_code}")
    if str(strategy_entry.get("promotion_eligibility") or "eligible") != "eligible":
        blockers.append("promotion_eligibility=ineligible")
    if str(strategy_entry.get("research_lane") or "").strip() == "control_baseline":
        blockers.append("research_lane=control_baseline is archive-only")
    if str(strategy_entry.get("research_lane") or "").strip() not in {"hypothesis_model"}:
        blockers.append("research_lane is not hypothesis_model")
    if lifecycle != "active":
        blockers.append(f"lifecycle={lifecycle} is not active")
    if experiment_status != "pass":
        blockers.append(f"experiment_status={experiment_status} is not pass")
    if backend_mode != "live":
        blockers.append(f"backend_mode={backend_mode} is archive-only")
    if current_stage in archive_only_stages:
        blockers.append(f"current_stage={current_stage} is archive-only")
    if not _stage_at_or_above(
        current_stage=current_stage,
        minimum_stage=minimum_stage,
        stage_contract=stage_contract,
    ):
        blockers.append(f"current_stage={current_stage} is below minimum publish stage {minimum_stage}")
    if daily_pass_streak < int(publication_threshold(publication_contract, "daily_pass_streak_min", 5)):
        blockers.append(
            "daily_pass_streak="
            f"{daily_pass_streak} is below minimum {int(publication_threshold(publication_contract, 'daily_pass_streak_min', 5))}"
        )
    if (
        last_transition_reason == "bootstrap"
        and daily_pass_streak < int(
            publication_threshold(
                publication_contract,
                "bootstrap_daily_pass_streak_min",
                publication_contract.get("bootstrap_requires_daily_pass_streak_min", 20),
            )
        )
    ):
        blockers.append(
            "bootstrap strategy requires additional daily pass streak before publish eligibility"
        )
    if (
        last_transition_reason == "bootstrap"
        and window_count < int(publication_threshold(publication_contract, "bootstrap_walk_forward_window_count_min", 2))
    ):
        blockers.append(
            "bootstrap walk_forward.window_count="
            f"{window_count} is below minimum {int(publication_threshold(publication_contract, 'bootstrap_walk_forward_window_count_min', 2))}"
        )
    if requires_falsification and falsification_status != "cleared":
        blockers.extend(f"falsification.blocker_code={code}" for code in falsification_blocker_codes)
        blockers.append(f"falsification.status={falsification_status or 'missing'}")
    if not credible_research_evidence:
        blockers.append("credible_research_evidence=false")
    if structural_quality_blocker:
        blockers.append("derivatives_strategy_quality.blocking_count>0")
    if bool(fixed_set_applicability.get("applicable")):
        fixed_set_status = str(fixed_set_comparison.get("status") or "missing").strip() or "missing"
        if fixed_set_status != "computed":
            blockers.append(f"fixed_set_comparison.status={fixed_set_status} is not computed")
        for blocker_code in [
            str(item).strip()
            for item in list(fixed_set_promotion_gate.get("blocker_codes") or [])
            if str(item).strip()
        ]:
            blockers.append(f"fixed_set_comparison.blocker_code={blocker_code}")
    blockers.extend(h10d_evidence_blockers)

    validation = _validation_state(
        backend_mode=backend_mode,
        experiment_status=experiment_status,
        lifecycle=lifecycle,
        current_stage=current_stage,
        minimum_stage=minimum_stage,
        validation_contract_status=validation_contract_status,
        blockers=blockers,
    )
    quality_gate_passed = not blockers
    publication_status = "publishable_to_incoming" if quality_gate_passed else "archived_only"
    return {
        "backend_mode": backend_mode,
        "current_stage": current_stage,
        "publication_status": publication_status,
        "validation": validation,
        "falsification_status": falsification_status,
        "quality_gate_passed": quality_gate_passed,
        "quality_blockers": blockers,
        "metrics_snapshot": metrics_snapshot,
    }


def write_promotion_decision(
    *,
    artifacts_root: Path,
    as_of: str,
    alpha_card_path: Path,
    alpha_card: dict[str, Any],
    strategy_entry: dict[str, Any],
    strategy_library_path: Path,
    decision_run_id: str,
) -> dict[str, Any]:
    raise_legacy_surface_frozen(
        operation="promotion_decision_write",
        as_of=as_of,
        artifacts_root=artifacts_root,
    )
    alpha_id = str(alpha_card.get("experiment_id", "")).strip()
    strategy_id = str(strategy_entry.get("strategy_id", "")).strip()
    lifecycle = strategy_lifecycle(strategy_entry)
    experiment_status = alpha_experiment_status(alpha_card)
    publication_assessment = evaluate_quant_publication_assessment(
        alpha_card=alpha_card,
        strategy_entry=strategy_entry,
        artifacts_root=artifacts_root,
    )
    approved = (
        experiment_status == "pass"
        and str(alpha_card.get("strategy_id", "")).strip() == strategy_id
        and (
            lifecycle == "active"
            or str(publication_assessment.get("publication_status") or "") == "publishable_to_incoming_auto"
        )
    )
    publication_status = publication_assessment["publication_status"] if approved else "blocked"
    universe_metadata = pit_universe_artifact_metadata(alpha_card)
    payload = with_evidence_metadata(
        {
            "alpha_id": alpha_id,
            "strategy_id": strategy_id,
            "decision": "approved" if approved else "blocked",
            "decision_run_id": decision_run_id,
            "backend_mode": publication_assessment["backend_mode"],
            "publication_status": publication_status,
            "validation": publication_assessment["validation"],
            "proposal_origin": str(strategy_entry.get("proposal_origin", alpha_card.get("proposal_origin", "heuristic")) or "heuristic"),
            "published_via": "same_day_auto_bridge" if publication_status == "publishable_to_incoming_auto" else "standard_promotion_decision",
            "executable_signal": False,
            **universe_metadata,
            "quality_gate_passed": bool(publication_assessment["quality_gate_passed"] and approved),
            "quality_blockers": list(publication_assessment["quality_blockers"]),
            "metrics_snapshot": publication_assessment["metrics_snapshot"],
            "falsification_status": publication_assessment["metrics_snapshot"].get("falsification_status"),
            "falsification_audit_path": publication_assessment["metrics_snapshot"].get("falsification_audit_path")
            or alpha_card.get("falsification_audit_path"),
            "input_hashes": {
                "alpha_card_sha256": sha256_path(alpha_card_path),
                "strategy_entry_sha256": sha256_json(_strategy_hash_payload(strategy_entry)),
                "strategy_library_sha256": sha256_path(strategy_library_path),
            },
        },
        evidence_family=PROMOTION_DECISION_EVIDENCE_FAMILY,
        contract_version=PROMOTION_DECISION_CONTRACT_VERSION,
        repo_root=ROOT,
        produced_at_utc=str(alpha_card.get("generated_at_utc") or utc_now()),
        require_source_commit_sha=True,
    )
    path = promotion_decision_path(artifacts_root=artifacts_root, as_of=as_of, alpha_id=alpha_id)
    write_json(path, payload)
    payload["promotion_decision_path"] = portable_path(path, repo_root=ROOT)
    return payload


def write_promotion_decisions_for_manifest(
    *,
    artifacts_root: Path,
    as_of: str,
    strategy_library: dict[str, Any],
) -> list[dict[str, Any]]:
    raise_legacy_surface_frozen(
        operation="promotion_manifest_write",
        as_of=as_of,
        artifacts_root=artifacts_root,
    )
    manifest = load_daily_alpha_manifest(artifacts_root=artifacts_root, as_of=as_of)
    strategy_library_path = Path(str(strategy_library["path"])).resolve()
    strategy_entries_by_id = {
        str(entry.get("strategy_id")): dict(entry)
        for entry in strategy_library.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("strategy_id") or "").strip()
    }
    decisions: list[dict[str, Any]] = []
    for entry in manifest.get("entries", []):
        experiment_id = str(entry.get("experiment_id") or "").strip()
        strategy_id = str(entry.get("strategy_id") or "").strip()
        if not experiment_id or not strategy_id:
            continue
        alpha_card_path = resolve_portable_path(str(entry.get("alpha_card_path") or ""), repo_root=ROOT)
        alpha_card = read_json(alpha_card_path)
        strategy_entry = strategy_entries_by_id.get(strategy_id)
        if strategy_entry is None:
            raise KeyError(f"strategy library entry not found for manifest strategy_id={strategy_id}")
        decision = write_promotion_decision(
            artifacts_root=artifacts_root,
            as_of=as_of,
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=strategy_entry,
            strategy_library_path=strategy_library_path,
            decision_run_id=f"{as_of}:{strategy_id}",
        )
        decisions.append(
            {
                "alpha_id": decision["alpha_id"],
                "strategy_id": decision["strategy_id"],
                "decision": decision["decision"],
                "publication_status": decision.get("publication_status"),
                "validation": decision.get("validation"),
                "promotion_decision_path": decision["promotion_decision_path"],
            }
        )
    return decisions


def evaluate_promotion_decision_for_export(
    *,
    artifacts_root: Path,
    as_of: str,
    alpha_card_path: Path,
    alpha_card: dict[str, Any],
    strategy_entry: dict[str, Any] | None,
    evidence_freshness_contract_path: Path,
    now_utc: str | None = None,
) -> tuple[bool, dict[str, Any] | None, list[str]]:
    alpha_id = str(alpha_card.get("experiment_id", "")).strip()
    path = promotion_decision_path(artifacts_root=artifacts_root, as_of=as_of, alpha_id=alpha_id)
    blockers: list[str] = []
    if not path.exists():
        blockers.append(f"promotion decision artifact is missing for alpha_id={alpha_id}")
        return False, None, blockers
    decision = read_json(path)
    if str(decision.get("contract_version")) not in {
        PROMOTION_DECISION_CONTRACT_VERSION,
        "quant_promotion_decision.v1",
    }:
        blockers.append(f"promotion decision contract version mismatch for alpha_id={alpha_id}")
    if str(decision.get("decision")) != "approved":
        blockers.append(f"promotion decision is not approved for alpha_id={alpha_id}")
    if str(decision.get("alpha_id")) != alpha_id:
        blockers.append(f"promotion decision alpha_id mismatch for alpha_id={alpha_id}")
    strategy_id = str(alpha_card.get("strategy_id", "")).strip()
    if str(decision.get("strategy_id")) != strategy_id:
        blockers.append(f"promotion decision strategy_id mismatch for alpha_id={alpha_id}")
    publication_assessment = evaluate_quant_publication_assessment(
        alpha_card=alpha_card,
        strategy_entry=strategy_entry,
        artifacts_root=artifacts_root,
    )
    if strategy_entry is None:
        blockers.append(f"strategy library entry is missing for strategy_id={strategy_id}")
    else:
        current_hashes = {
            "alpha_card_sha256": sha256_path(alpha_card_path),
            "strategy_entry_sha256": sha256_json(_strategy_hash_payload(strategy_entry)),
            "strategy_library_sha256": sha256_path(Path(strategy_entry["strategy_library_path"])),
        }
        input_hashes = dict(decision.get("input_hashes") or {})
        for field_name, current_hash in current_hashes.items():
            if str(input_hashes.get(field_name, "")) != current_hash:
                blockers.append(f"promotion decision hash mismatch for {field_name} on alpha_id={alpha_id}")
    blockers.extend(
        evaluate_promotion_decision_freshness(
            decision=decision,
            evidence_freshness_contract_path=evidence_freshness_contract_path,
            now_utc=now_utc,
        )
    )
    resolved_decision = dict(decision)
    for field_name in (
        "backend_mode",
        "publication_status",
        "validation",
        "falsification_status",
        "quality_gate_passed",
        "quality_blockers",
        "metrics_snapshot",
    ):
        current_value = publication_assessment[field_name]
        if field_name not in resolved_decision:
            resolved_decision[field_name] = current_value
            continue
        if field_name == "quality_blockers":
            if sorted(str(item) for item in resolved_decision.get(field_name, [])) != sorted(
                str(item) for item in current_value
            ):
                blockers.append(f"promotion decision {field_name} mismatch for alpha_id={alpha_id}")
        elif field_name == "metrics_snapshot":
            if sha256_json(_stable_metrics_snapshot(resolved_decision.get(field_name))) != sha256_json(
                _stable_metrics_snapshot(current_value)
            ):
                blockers.append(f"promotion decision {field_name} mismatch for alpha_id={alpha_id}")
        elif resolved_decision.get(field_name) != current_value:
            blockers.append(f"promotion decision {field_name} mismatch for alpha_id={alpha_id}")
    resolved_decision["promotion_decision_path"] = portable_path(path, repo_root=ROOT)
    return not blockers, resolved_decision, blockers


def evaluate_promotion_decision_freshness(
    *,
    decision: dict[str, Any],
    evidence_freshness_contract_path: Path,
    now_utc: str | None = None,
) -> list[str]:
    blockers: list[str] = []
    contract = read_json(evidence_freshness_contract_path)
    family_contract = dict(contract.get("families", {}).get(PROMOTION_DECISION_EVIDENCE_FAMILY, {}))
    if not family_contract:
        return [f"freshness contract missing family={PROMOTION_DECISION_EVIDENCE_FAMILY}"]
    produced_at_raw = str(decision.get("produced_at_utc", "")).strip()
    if not produced_at_raw:
        blockers.append("promotion decision is missing produced_at_utc")
    else:
        produced_at = _parse_utc(produced_at_raw)
        current_time = _parse_utc(now_utc) if now_utc else datetime.now(UTC)
        max_age_hours = float(family_contract.get("max_age_hours", 0))
        age_hours = (current_time - produced_at).total_seconds() / 3600.0
        if age_hours > max_age_hours:
            blockers.append(
                f"promotion decision is stale for alpha_id={decision.get('alpha_id')} (age_hours={age_hours:.3f}, max={max_age_hours:.3f})"
            )
    current_commit = current_source_commit_sha()
    decision_commit = str(decision.get("source_commit_sha", "")).strip() or None
    require_commit_match = bool(family_contract.get("require_current_commit_match"))
    if require_commit_match and current_commit and decision_commit and current_commit != decision_commit:
        blockers.append(
            "promotion decision source_commit_sha mismatch: "
            f"current={current_commit} decision={decision_commit}"
        )
    return blockers


def strategy_lifecycle(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "active"
    lifecycle = str(payload.get("lifecycle") or "").strip()
    return lifecycle or "active"


def alpha_experiment_status(alpha_card: dict[str, Any]) -> str:
    experiment_status = str(alpha_card.get("experiment_status") or "").strip()
    return experiment_status or "fail"


def alpha_backend_mode(alpha_card: dict[str, Any]) -> str:
    explicit = str(alpha_card.get("backend_mode", "")).strip().lower()
    if explicit:
        return explicit
    compiler_backend = str(alpha_card.get("compiler_backend", "")).strip().lower()
    return "live" if compiler_backend == "live" else "deterministic"


def sha256_json(payload: Any) -> str:
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_metrics_snapshot(payload: Any) -> dict[str, Any]:
    snapshot = dict(payload or {})
    for field_name in VOLATILE_METRICS_SNAPSHOT_FIELDS:
        snapshot.pop(field_name, None)
    return snapshot


def _strategy_hash_payload(strategy_entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(strategy_entry)
    payload.pop("strategy_library_path", None)
    return payload


def _validation_state(
    *,
    backend_mode: str,
    experiment_status: str,
    lifecycle: str,
    current_stage: str,
    minimum_stage: str,
    validation_contract_status: str,
    blockers: list[str],
) -> str:
    if validation_contract_status == "falsification_required" or experiment_status == "quarantined" or any(
        blocker.startswith("falsification.") for blocker in blockers
    ):
        return INVALIDATED_UNVERIFIED_RESEARCH_EVIDENCE
    if validation_contract_status != "passed":
        return "failed"
    if is_rerun_required_experiment_status(experiment_status):
        return "insufficient_track_record"
    if backend_mode != "live":
        return "deterministic_only"
    if experiment_status != "pass" or lifecycle != "active":
        return "failed"
    insufficient_prefixes = (
        "current_stage=",
        "daily_pass_streak=",
        "walk_forward.window_count=",
        "bootstrap strategy",
    )
    if current_stage == "stage_1_research_readiness_only":
        return "insufficient_track_record"
    if current_stage != minimum_stage and any(
        blocker.startswith("current_stage=") and "below minimum publish stage" in blocker
        for blocker in blockers
    ):
        return "insufficient_track_record"
    if any(blocker.startswith(prefix) for prefix in insufficient_prefixes for blocker in blockers):
        return "insufficient_track_record"
    if blockers:
        return "failed"
    return "passed"


def walk_forward_loss_window_fraction(walk_forward: dict[str, Any]) -> float:
    windows = [
        item
        for item in list(walk_forward.get("windows") or [])
        if isinstance(item, dict)
    ]
    if not windows:
        return 0.0
    loss_count = sum(1 for item in windows if float(item.get("sharpe", 0.0) or 0.0) < 0.0)
    return loss_count / len(windows)


def sharpe_anomaly_details(
    *,
    validation_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    walk_forward: dict[str, Any],
    threshold: float,
) -> dict[str, float | str] | None:
    candidates: list[tuple[str, float]] = [
        ("validation_metrics.sharpe", float(validation_metrics.get("sharpe", 0.0) or 0.0)),
        ("test_metrics.sharpe", float(test_metrics.get("sharpe", 0.0) or 0.0)),
        ("walk_forward.median_oos_sharpe", float(walk_forward.get("median_oos_sharpe", 0.0) or 0.0)),
    ]
    for index, item in enumerate(list(walk_forward.get("windows") or [])):
        if not isinstance(item, dict):
            continue
        candidates.append((f"walk_forward.windows[{index}].sharpe", float(item.get("sharpe", 0.0) or 0.0)))
    triggered = [(metric_name, metric_value) for metric_name, metric_value in candidates if metric_value > threshold]
    if not triggered:
        return None
    metric_name, metric_value = max(triggered, key=lambda item: item[1])
    return {"metric": metric_name, "value": metric_value}


def _stage_at_or_above(*, current_stage: str, minimum_stage: str, stage_contract: dict[str, Any]) -> bool:
    order = [str(item.get("stage_id", "")).strip() for item in stage_contract.get("stages", [])]
    try:
        return order.index(current_stage) >= order.index(minimum_stage)
    except ValueError:
        return False


def _parse_utc(value: str | None) -> datetime:
    candidate = str(value or "").strip()
    if not candidate:
        return datetime.now(UTC)
    return datetime.fromisoformat(candidate.replace("Z", "+00:00")).astimezone(UTC)
