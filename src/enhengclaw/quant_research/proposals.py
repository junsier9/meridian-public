from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .contracts import QuantUniverseInput, read_json, slugify, utc_now, write_json
from .discovery import run_quant_discovery_weekly_cycle
from .experiment_status import is_pass_experiment_status, is_rerun_required_experiment_status
from .governance import (
    FEATURE_GROUPS,
    PROPOSAL_BUCKET_LIMITS,
    WEEKLY_SANDBOX_BUDGET,
    apply_weekly_proposal_result,
    build_strategy_entry,
    ensure_strategy_catalog,
    ensure_strategy_library,
    iso_week_label,
    load_strategy_library,
    strategy_catalog_path,
    strategy_library_path,
    strategy_spec_hash,
    validate_proposal_spec,
    weekly_review_root,
)
from .lab import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    WORKBENCH_ROOT,
    build_quant_datasets,
    build_quant_feature_sets,
    build_universe_snapshot,
    resolve_quant_input_path,
    run_quant_experiments_for_strategies,
)
from .legacy_surface import raise_legacy_surface_frozen
from .market_data import load_workbench_thesis_profiles


ROOT = Path(__file__).resolve().parents[3]


PROPOSAL_ROOT_NAME = "proposals"
ALLOWED_PROPOSAL_BUCKETS = ("config", "feature", "universe")


def proposal_week_root(*, artifacts_root: Path, week_of: str) -> Path:
    return artifacts_root / PROPOSAL_ROOT_NAME / iso_week_label(week_of)


def proposal_root(*, artifacts_root: Path, week_of: str, proposal_id: str) -> Path:
    return proposal_week_root(artifacts_root=artifacts_root, week_of=week_of) / proposal_id


def load_existing_weekly_proposals(*, artifacts_root: Path, week_of: str) -> list[dict[str, Any]]:
    week_root = proposal_week_root(artifacts_root=artifacts_root, week_of=week_of)
    if not week_root.exists():
        return []
    proposals: list[dict[str, Any]] = []
    for spec_path in sorted(week_root.glob("*/proposal_spec.json")):
        proposals.append(read_json(spec_path))
    return proposals[:WEEKLY_SANDBOX_BUDGET]


def _parse_date(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _load_alpha_registry(*, artifacts_root: Path) -> dict[str, Any]:
    registry_path = artifacts_root / "registry" / "alpha_registry.json"
    if not registry_path.exists():
        return {"generated_at_utc": utc_now(), "entries": [], "path": str(registry_path)}
    payload = read_json(registry_path)
    payload["path"] = str(registry_path)
    return payload


def _recent_registry_entries(*, registry: dict[str, Any], week_of: str) -> list[dict[str, Any]]:
    week_end = _parse_date(week_of)
    week_start = week_end - timedelta(days=6)
    recent: list[dict[str, Any]] = []
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict):
            continue
        as_of = str(entry.get("as_of", "")).strip()
        if not as_of:
            continue
        try:
            as_of_date = _parse_date(as_of)
        except ValueError:
            continue
        if week_start <= as_of_date <= week_end:
            recent.append(dict(entry))
    return recent


def _proposal_score(entry: dict[str, Any]) -> float:
    test_metrics = entry.get("test_metrics", {})
    validation_metrics = entry.get("validation_metrics", {})
    walk_forward = entry.get("walk_forward", {})
    return (
        float(test_metrics.get("sharpe", 0.0))
        + float(validation_metrics.get("net_return", 0.0))
        + float(test_metrics.get("net_return", 0.0))
        + float(walk_forward.get("median_oos_sharpe", 0.0))
    )


def _tightened_profile_override(base_entry: dict[str, Any]) -> dict[str, Any]:
    current = dict(base_entry.get("profile_constraints") or {})
    override = dict(base_entry.get("profile_constraints_override") or {})
    max_leverage = float(current.get("max_gross_leverage", 1.0))
    max_turnover = float(current.get("max_turnover_per_rebalance", 1.0))
    tightened = dict(override)
    tightened["max_gross_leverage"] = round(max(0.5, max_leverage * 0.8), 4)
    tightened["max_turnover_per_rebalance"] = round(max(0.5, max_turnover * 0.85), 4)
    return tightened


def _feature_variant(feature_groups: list[str], *, variant_index: int) -> list[str]:
    current = list(dict.fromkeys(feature_groups or list(FEATURE_GROUPS)))
    if variant_index % 2 == 0:
        candidate = [group for group in current if group != "events"]
        return candidate or current
    prioritized = ["core_context", "structure", "trend", "derivatives", "volume"]
    candidate = [group for group in prioritized if group in current]
    if "events" in current and "events" not in candidate:
        candidate.append("events")
    return candidate or current


def _subjects_from_recent_cross_entries(recent_entries: list[dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    for entry in sorted(recent_entries, key=_proposal_score, reverse=True):
        for candidate in entry.get("top_long_candidates", []):
            subject = str(candidate.get("subject", "")).strip().upper()
            if subject and subject not in ordered:
                ordered.append(subject)
            if len(ordered) >= 3:
                return ordered
    return ordered


def _build_proposal_spec(
    *,
    week_of: str,
    proposal_bucket: str,
    base_entry: dict[str, Any],
    strategy_profile: str,
    shape: str,
    model_family: str,
    subject: str | None,
    universe_filter: dict[str, Any] | None,
    feature_groups: list[str],
    profile_constraints_override: dict[str, Any] | None,
    rationale: str,
    expected_edge: str,
    invalidates_if: str,
) -> dict[str, Any]:
    spec_hash = strategy_spec_hash(
        shape=shape,
        strategy_profile=strategy_profile,
        subject=subject,
        universe_filter=universe_filter,
        model_family=model_family,
        feature_groups=feature_groups,
        profile_constraints_override=profile_constraints_override,
    )
    subject_slug = slugify(subject or "universe")
    proposal_id = f"{iso_week_label(week_of)}-{proposal_bucket}-{subject_slug}-{slugify(model_family)}-{spec_hash[:8]}"
    strategy_id = f"proposal-{proposal_bucket}-{subject_slug}-{slugify(model_family)}-{spec_hash[:12]}"
    return {
        "proposal_id": proposal_id,
        "proposal_bucket": proposal_bucket,
        "week_of": week_of,
        "base_strategy_id": base_entry.get("strategy_id"),
        "strategy_id": strategy_id,
        "shape": shape,
        "strategy_profile": strategy_profile,
        "subject": str(subject).upper() if subject else None,
        "universe_filter": universe_filter or {},
        "model_family": model_family,
        "feature_groups": feature_groups,
        "profile_constraints_override": profile_constraints_override or {},
        "rationale": rationale,
        "expected_edge": expected_edge,
        "invalidates_if": invalidates_if,
        "spec_hash": spec_hash,
        "source": "proposal",
    }


def generate_weekly_proposals(
    *,
    week_of: str,
    strategy_library: dict[str, Any],
    recent_registry_entries: list[dict[str, Any]],
    workbench_profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_nonproposal_hashes = {
        str(entry.get("spec_hash"))
        for entry in strategy_library.get("entries", [])
        if str(entry.get("source")) != "proposal"
    }
    current_week = iso_week_label(week_of)
    current_week_pairs = {
        _proposal_pair(entry)
        for entry in strategy_library.get("entries", [])
        if str(entry.get("source")) == "proposal"
        and entry.get("base_strategy_id")
        and str(entry.get("governance_week")) == current_week
    }
    candidate_entries_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in strategy_library.get("entries", []):
        pair = _proposal_pair(entry)
        if pair is None or str(entry.get("source")) != "proposal" or str(entry.get("lifecycle")) != "candidate":
            continue
        previous = candidate_entries_by_pair.get(pair)
        if previous is None or str(entry.get("updated_at_utc", "")) > str(previous.get("updated_at_utc", "")):
            candidate_entries_by_pair[pair] = entry
    proposals: list[dict[str, Any]] = []
    used_hashes: set[str] = set()
    budget_counter = {bucket: 0 for bucket in ALLOWED_PROPOSAL_BUCKETS}

    ranked_recent = sorted(recent_registry_entries, key=_proposal_score, reverse=True)
    by_strategy_id = {
        str(entry["strategy_id"]): entry
        for entry in strategy_library.get("entries", [])
        if isinstance(entry, dict) and entry.get("strategy_id")
    }
    strong_active = [
        entry
        for entry in ranked_recent
        if str(entry.get("lifecycle")) in {"active", "watch"}
        and is_pass_experiment_status(str(entry.get("experiment_status")))
        and str(entry.get("strategy_id")) in by_strategy_id
    ]

    def maybe_add(spec: dict[str, Any]) -> None:
        if len(proposals) >= WEEKLY_SANDBOX_BUDGET:
            return
        bucket = str(spec["proposal_bucket"])
        if budget_counter[bucket] >= PROPOSAL_BUCKET_LIMITS[bucket]:
            return
        if spec["spec_hash"] in used_hashes or spec["spec_hash"] in existing_nonproposal_hashes:
            return
        proposals.append(spec)
        used_hashes.add(spec["spec_hash"])
        budget_counter[bucket] += 1

    for entry in strong_active:
        if budget_counter["config"] >= PROPOSAL_BUCKET_LIMITS["config"]:
            break
        base_entry = by_strategy_id[str(entry["strategy_id"])]
        pair = (str(base_entry["strategy_id"]), "config")
        if pair in current_week_pairs:
            continue
        if pair in candidate_entries_by_pair:
            maybe_add(_proposal_spec_from_entry(candidate_entries_by_pair[pair], week_of=week_of, proposal_bucket="config"))
            continue
        maybe_add(
            _build_proposal_spec(
                week_of=week_of,
                proposal_bucket="config",
                base_entry=base_entry,
                strategy_profile=str(base_entry["strategy_profile"]),
                shape=str(base_entry["shape"]),
                model_family=str(base_entry["model_family"]),
                subject=base_entry.get("subject"),
                universe_filter=base_entry.get("universe_filter"),
                feature_groups=list(base_entry.get("feature_groups", [])),
                profile_constraints_override=_tightened_profile_override(base_entry),
                rationale="Tighten execution constraints around a recent passing strategy so daily governance can test whether the edge survives with lower leverage and turnover.",
                expected_edge="If the signal is robust, a slightly stricter profile should preserve OOS performance while reducing implementation risk.",
                invalidates_if="The tightened variant loses positive validation/test net returns or its walk-forward OOS Sharpe turns non-positive.",
            )
        )

    for variant_index, entry in enumerate(strong_active):
        if budget_counter["feature"] >= PROPOSAL_BUCKET_LIMITS["feature"]:
            break
        base_entry = by_strategy_id[str(entry["strategy_id"])]
        pair = (str(base_entry["strategy_id"]), "feature")
        if pair in current_week_pairs:
            continue
        if pair in candidate_entries_by_pair:
            maybe_add(_proposal_spec_from_entry(candidate_entries_by_pair[pair], week_of=week_of, proposal_bucket="feature"))
            continue
        maybe_add(
            _build_proposal_spec(
                week_of=week_of,
                proposal_bucket="feature",
                base_entry=base_entry,
                strategy_profile=str(base_entry["strategy_profile"]),
                shape=str(base_entry["shape"]),
                model_family=str(base_entry["model_family"]),
                subject=base_entry.get("subject"),
                universe_filter=base_entry.get("universe_filter"),
                feature_groups=_feature_variant(list(base_entry.get("feature_groups", [])), variant_index=variant_index),
                profile_constraints_override=base_entry.get("profile_constraints_override"),
                rationale="Re-test a recent passing strategy with a narrower feature surface so we can see whether the edge depends on the full default stack or survives a cleaner subset.",
                expected_edge="A cleaner feature mix can improve stability, interpretability, and reduce noisy dependence on one-off factors.",
                invalidates_if="The reduced feature mix no longer clears the validation/test gates or fails walk-forward OOS stability.",
            )
        )

    recent_cross = [entry for entry in strong_active if str(entry.get("shape")) == "cross_sectional"]
    if budget_counter["universe"] < PROPOSAL_BUCKET_LIMITS["universe"] and recent_cross:
        base_entry = by_strategy_id[str(recent_cross[0]["strategy_id"])]
        pair = (str(base_entry["strategy_id"]), "universe")
        if pair in current_week_pairs:
            return proposals[:WEEKLY_SANDBOX_BUDGET]
        if pair in candidate_entries_by_pair:
            maybe_add(_proposal_spec_from_entry(candidate_entries_by_pair[pair], week_of=week_of, proposal_bucket="universe"))
            return proposals[:WEEKLY_SANDBOX_BUDGET]
        suggested_subjects = _subjects_from_recent_cross_entries(recent_cross)
        if not suggested_subjects:
            suggested_subjects = [
                str(profile.get("subject", "")).upper()
                for profile in workbench_profiles
                if str(profile.get("subject", "")).strip()
            ][:3]
        universe_filter = dict(base_entry.get("universe_filter", {}))
        if suggested_subjects:
            universe_filter["subjects"] = suggested_subjects[:3]
        maybe_add(
            _build_proposal_spec(
                week_of=week_of,
                proposal_bucket="universe",
                base_entry=base_entry,
                strategy_profile=str(base_entry["strategy_profile"]),
                shape="cross_sectional",
                model_family=str(base_entry["model_family"]),
                subject=None,
                universe_filter=universe_filter,
                feature_groups=list(base_entry.get("feature_groups", [])),
                profile_constraints_override=base_entry.get("profile_constraints_override"),
                rationale="Focus the cross-sectional strategy on the strongest recent subjects so sandbox evaluation can test whether a concentrated universe retains the edge.",
                expected_edge="A tighter universe can raise signal density if recent winners continue to dominate the ranking.",
                invalidates_if="The focused universe loses diversification benefits and fails to maintain positive OOS performance.",
            )
        )

    return proposals[:WEEKLY_SANDBOX_BUDGET]


def _proposal_bucket_from_strategy_id(strategy_id: str) -> str | None:
    normalized = str(strategy_id).strip()
    for bucket in ALLOWED_PROPOSAL_BUCKETS:
        if normalized.startswith(f"proposal-{bucket}-"):
            return bucket
    return None


def _proposal_pair(entry: dict[str, Any]) -> tuple[str, str] | None:
    base_strategy_id = str(entry.get("base_strategy_id", "")).strip()
    bucket = _proposal_bucket_from_strategy_id(str(entry.get("strategy_id", "")))
    if not base_strategy_id or bucket is None:
        return None
    return (base_strategy_id, bucket)


def _proposal_spec_from_entry(entry: dict[str, Any], *, week_of: str, proposal_bucket: str) -> dict[str, Any]:
    return {
        "proposal_id": f"{iso_week_label(week_of)}-{proposal_bucket}-{slugify(str(entry.get('subject') or 'universe'))}-{slugify(str(entry.get('model_family')))}-{str(entry.get('spec_hash'))[:8]}",
        "proposal_bucket": proposal_bucket,
        "week_of": week_of,
        "base_strategy_id": entry.get("base_strategy_id"),
        "strategy_id": entry.get("strategy_id"),
        "shape": entry.get("shape"),
        "strategy_profile": entry.get("strategy_profile"),
        "subject": entry.get("subject"),
        "universe_filter": dict(entry.get("universe_filter", {})),
        "model_family": entry.get("model_family"),
        "feature_groups": list(entry.get("feature_groups", [])),
        "profile_constraints_override": dict(entry.get("profile_constraints_override", {})),
        "rationale": "Re-evaluate the existing weekly candidate without changing its allowed-surface configuration.",
        "expected_edge": "A second weekly pass with the same spec_hash should confirm the candidate is stable enough to promote.",
        "invalidates_if": "The candidate loses positive validation/test returns or its walk-forward OOS Sharpe turns non-positive.",
        "spec_hash": entry.get("spec_hash"),
        "source": "proposal",
    }


def _proposal_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Weekly Governance Summary",
        "",
        f"- Week of: `{summary.get('week_of')}`",
        f"- Compiler backend: `{summary.get('compiler_backend')}`",
        f"- Proposal count: `{summary.get('proposal_count')}`",
        f"- Sandbox accepted: `{summary.get('sandbox_accepted_count')}`",
        f"- Promoted to candidate: `{summary.get('promoted_to_candidate_count')}`",
        f"- Promoted to active: `{summary.get('promoted_to_active_count')}`",
        f"- Quarantined proposals: `{summary.get('quarantined_proposal_count')}`",
        "",
        "## Active Library",
    ]
    for strategy_id in summary.get("active_strategy_ids", []):
        lines.append(f"- `{strategy_id}`")
    return "\n".join(lines)


def _evaluate_single_proposal(
    *,
    proposal_spec: dict[str, Any],
    artifacts_root: Path,
    strategy_library: dict[str, Any],
    feature_sets: list[dict[str, Any]],
    compiler_backend: str,
    week_of: str,
) -> dict[str, Any]:
    proposal_dir = proposal_root(artifacts_root=artifacts_root, week_of=week_of, proposal_id=str(proposal_spec["proposal_id"]))
    proposal_dir.mkdir(parents=True, exist_ok=True)
    proposal_spec_path = proposal_dir / "proposal_spec.json"
    write_json(proposal_spec_path, proposal_spec)

    valid, validation_reason = validate_proposal_spec(proposal_spec=proposal_spec, artifacts_root=artifacts_root)
    if not valid:
        evaluation = {
            "generated_at_utc": utc_now(),
            "proposal_id": proposal_spec["proposal_id"],
            "proposal_spec_path": str(proposal_spec_path),
            "evaluation_status": "quarantined",
            "allowed_surface_passed": False,
            "reason": validation_reason,
            "governance_action": "quarantined",
            "strategy_id": proposal_spec["strategy_id"],
            "spec_hash": proposal_spec["spec_hash"],
            "compiler_backend": compiler_backend,
        }
        evaluation_path = proposal_dir / "proposal_evaluation.json"
        write_json(evaluation_path, evaluation)
        evaluation["proposal_evaluation_path"] = str(evaluation_path)
        return evaluation

    sandbox_root = proposal_dir / "sandbox"
    sandbox_entry = build_strategy_entry(
        strategy_id=str(proposal_spec["strategy_id"]),
        shape=str(proposal_spec["shape"]),
        strategy_profile=str(proposal_spec["strategy_profile"]),
        subject=proposal_spec.get("subject"),
        universe_filter=proposal_spec.get("universe_filter"),
        model_family=str(proposal_spec["model_family"]),
        feature_groups=proposal_spec.get("feature_groups"),
        profile_constraints_override=proposal_spec.get("profile_constraints_override"),
        source="proposal",
        status="candidate",
        governance_week=iso_week_label(week_of),
        base_strategy_id=proposal_spec.get("base_strategy_id"),
    )
    experiments = run_quant_experiments_for_strategies(
        as_of=week_of,
        artifacts_root=sandbox_root,
        strategies=[sandbox_entry],
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
    )
    experiment = experiments[0]
    evaluation_status = str(experiment.get("experiment_status") or "fail")
    if not (
        is_pass_experiment_status(evaluation_status)
        or is_rerun_required_experiment_status(evaluation_status)
        or evaluation_status in {"fail", "quarantined"}
    ):
        evaluation_status = "fail"
    governance_result = apply_weekly_proposal_result(
        artifacts_root=artifacts_root,
        strategy_library=strategy_library,
        proposal_spec=proposal_spec,
        evaluation_status=evaluation_status,
        week_of=week_of,
    )
    evaluation = {
        "generated_at_utc": utc_now(),
        "proposal_id": proposal_spec["proposal_id"],
        "proposal_spec_path": str(proposal_spec_path),
        "proposal_bucket": proposal_spec["proposal_bucket"],
        "evaluation_status": evaluation_status,
        "allowed_surface_passed": True,
        "governance_action": governance_result["action"],
        "strategy_id": governance_result.get("strategy_id") or proposal_spec["strategy_id"],
        "spec_hash": proposal_spec["spec_hash"],
        "compiler_backend": compiler_backend,
        "sandbox_experiment": {
            "experiment_id": experiment.get("experiment_id"),
            "experiment_root": experiment.get("experiment_root"),
            "experiment_status": experiment.get("experiment_status"),
            "alpha_card_path": experiment.get("alpha_card_path"),
            "validation_report_path": experiment.get("validation_report_path"),
        },
    }
    evaluation_path = proposal_dir / "proposal_evaluation.json"
    write_json(evaluation_path, evaluation)
    evaluation["proposal_evaluation_path"] = str(evaluation_path)
    return evaluation


def run_quant_strategy_proposal_cycle(
    *,
    as_of: str | None = None,
    week_of: str | None = None,
    compiler_backend: str = "live",
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    workbench_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
) -> dict[str, Any]:
    raise_legacy_surface_frozen(
        operation="strategy_proposal_cycle",
        as_of=as_of or week_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
    )
