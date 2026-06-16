from __future__ import annotations

from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import with_evidence_metadata

from .agent_proposals import generate_agent_weekly_proposals
from .alpha_manifest import write_daily_alpha_manifest_from_experiments
from .bridge import export_passed_alphas_to_workbench
from .contracts import (
    QuantUniverseCandidate,
    QuantUniverseInput,
    STRATEGY_PROFILES,
    profile_constraints,
    read_json,
    slugify,
    utc_now,
    write_json,
)
from .data_readiness import blocked_discovery_reason, resolve_default_spot_ohlcv_external_root
from .experiment_status import (
    counts_as_sandbox_accepted,
    is_pass_experiment_status,
    is_rerun_required_experiment_status,
)
from .governance import (
    ACTIVE_STRATEGY_IDS,
    DISCOVERY_SINGLE_ASSET_MODELS,
    FEATURE_GROUPS,
    COMPLEXITY_TIERS,
    HYPOTHESIS_MODEL_LANE,
    HYPOTHESIS_PORTFOLIO_LANE,
    MODEL_OVERLAY_MODEL_FAMILIES,
    RUNTIME_EVOLUTION_FLAGS,
    WEEKLY_CANDIDATE_PROMOTION_CAP,
    WEEKLY_DISCOVERY_FULL_VALIDATION_BUDGET,
    WEEKLY_DISCOVERY_SCREEN_BUDGET,
    WEEKLY_PROMOTION_TO_ACTIVE_CAP,
    apply_weekly_proposal_result,
    ensure_strategy_catalog,
    ensure_strategy_library,
    discovery_run_id,
    discovery_run_root,
    iso_week_label,
    library_entry_for_spec_hash,
    load_strategy_library,
    materialize_registry_snapshot,
    model_overlay_child_strategy_id,
    model_overlay_text,
    normalize_governance_as_of,
    proposal_ranking_score,
    strategy_catalog_path,
    strategy_library_path,
    strategy_lifecycle,
    strategy_spec_hash,
    validate_proposal_spec,
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
from .promotion import write_promotion_decisions_for_manifest


ROOT = Path(__file__).resolve().parents[3]
DISCOVERY_BUCKETS = (
    "model_overlay",
    "cross_sectional_relaunch",
    "new_deterministic_families",
    "new_ml_families",
    "active_adjacency",
)
DISCOVERY_BUCKET_SIZE = 12
DISCOVERY_MIN_UNIVERSE_SIZE = 20
MODEL_OVERLAY_BUCKET = "model_overlay"
MODEL_OVERLAY_READY_THESIS_LIMIT = 3
CROSS_SECTIONAL_RELAUNCH_MODELS = (
    "relative_strength_cross_section",
    "ranking_scorer",
    "logistic_regression",
    "meta_labeling",
)
NEW_DETERMINISTIC_FAMILIES = tuple(DISCOVERY_SINGLE_ASSET_MODELS[:4])
NEW_ML_FAMILIES = ("extra_trees_classifier", "elasticnet_logistic", "gradient_boosting_classifier")


def run_quant_discovery_weekly_cycle(
    *,
    week_of: str,
    compiler_backend: str = "live",
    artifacts_root: Path | None = None,
    quant_input_root: Path | None = None,
    workbench_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    derivatives_external_root: Path | None = None,
) -> dict[str, Any]:
    raise_legacy_surface_frozen(
        operation="discovery_weekly_cycle",
        as_of=week_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
    )
    resolved_artifacts_root = (artifacts_root or QUANT_ARTIFACTS_ROOT).expanduser().resolve()
    resolved_quant_input_root = (quant_input_root or QUANT_INPUT_ROOT).expanduser().resolve()
    resolved_workbench_root = (workbench_root or WORKBENCH_ROOT).expanduser().resolve()
    resolved_spot_ohlcv_external_root = resolve_default_spot_ohlcv_external_root(
        spot_ohlcv_external_root=spot_ohlcv_external_root,
    )
    as_of = normalize_governance_as_of(week_of)
    generated_at_utc = utc_now()
    run_id = discovery_run_id(generated_at_utc=generated_at_utc)

    universe_input_path = resolve_quant_input_path(as_of=as_of, quant_input_root=resolved_quant_input_root)
    universe_input = QuantUniverseInput.from_payload(read_json(universe_input_path))
    filtered_candidates = universe_input.selected_candidates()
    if len(filtered_candidates) < DISCOVERY_MIN_UNIVERSE_SIZE:
        raise RuntimeError(
            "weekly discovery requires a broad Top 100 universe input; "
            f"found {len(filtered_candidates)} filtered candidates, which looks like a smoke universe"
        )

    universe_snapshot = build_universe_snapshot(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        input_path=universe_input_path,
        universe_input=universe_input,
        universe_candidates=filtered_candidates,
    )
    ensure_strategy_catalog(artifacts_root=resolved_artifacts_root)
    strategy_library = ensure_strategy_library(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        universe_candidates=filtered_candidates,
    )
    review_root = discovery_run_root(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
        run_id=run_id,
    )
    review_root.mkdir(parents=True, exist_ok=True)
    registry_snapshot = materialize_registry_snapshot(
        artifacts_root=resolved_artifacts_root,
        week_of=as_of,
        run_id=run_id,
    )

    heuristic_recipes = build_discovery_recipes(
        week_of=as_of,
        strategy_library=strategy_library,
        universe_candidates=filtered_candidates,
    )
    heuristic_recipes = [
        _prepare_heuristic_recipe(recipe=recipe, registry_snapshot=registry_snapshot)
        for recipe in heuristic_recipes
    ]
    agent_summary = generate_agent_weekly_proposals(
        week_of=as_of,
        artifacts_root=resolved_artifacts_root,
        review_root=review_root,
        strategy_library=strategy_library,
        universe_candidates=filtered_candidates,
        registry_snapshot=registry_snapshot,
    )
    agent_recipes = [
        _prepare_agent_recipe(
            recipe=recipe,
            registry_snapshot=registry_snapshot,
        )
        for recipe in agent_summary.get("validated_proposals", [])
        if isinstance(recipe, dict)
    ]
    recent_duplicate_spec_hashes = _recent_duplicate_spec_hashes(
        artifacts_root=resolved_artifacts_root,
        as_of=as_of,
    )
    heuristic_recipes = _filter_recent_duplicate_recipes(
        recipes=heuristic_recipes,
        strategy_library=strategy_library,
        recent_duplicate_spec_hashes=recent_duplicate_spec_hashes,
        run_id=run_id,
        as_of=as_of,
    )
    agent_recipes = _filter_recent_duplicate_recipes(
        recipes=agent_recipes,
        strategy_library=strategy_library,
        recent_duplicate_spec_hashes=recent_duplicate_spec_hashes,
        run_id=run_id,
        as_of=as_of,
    )
    recipes, merge_summary = _merge_proposal_lanes(
        heuristic_recipes=heuristic_recipes,
        agent_recipes=agent_recipes,
        allow_heuristic_only_fallback=not bool(agent_recipes),
    )
    executable_recipes, blocked_data_gap_recipes = _apply_recipe_data_readiness_gate(recipes=recipes)
    recipe_catalog_path = review_root / "discovery_recipe_catalog.json"
    write_json(
        recipe_catalog_path,
        {
            "generated_at_utc": generated_at_utc,
            "as_of": as_of,
            "run_id": run_id,
            "week_of": as_of,
            "iso_week": iso_week_label(as_of),
            "discovery_cadence": "daily_full",
            "universe_count": len(filtered_candidates),
            "registry_snapshot_path": registry_snapshot.get("path"),
            "registry_snapshot_id": registry_snapshot.get("snapshot_id"),
            "agent_proposal_summary_path": agent_summary.get("summary_path"),
            "agent_proposal_count": len(agent_recipes),
            "heuristic_recipe_count": len(heuristic_recipes),
            "merged_recipe_count": len(recipes),
            "screenable_recipe_count": len(executable_recipes),
            "blocked_data_gap_recipe_count": len(blocked_data_gap_recipes),
            "proposal_lane_mix": merge_summary["proposal_lane_mix"],
            "bucket_counts": _bucket_counts(executable_recipes),
            "recipes": executable_recipes,
            "blocked_data_gap_recipes": blocked_data_gap_recipes,
        },
    )

    datasets = build_quant_datasets(
        as_of=as_of,
        artifacts_root=resolved_artifacts_root,
        universe_snapshot=universe_snapshot,
        universe_candidates=filtered_candidates,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=resolved_spot_ohlcv_external_root,
        derivatives_external_root=derivatives_external_root,
    )
    feature_sets = build_quant_feature_sets(
        artifacts_root=resolved_artifacts_root,
        datasets=datasets,
    )
    screen_records, screen_summary_path = _run_discovery_screen(
        week_of=as_of,
        review_root=review_root,
        recipes=executable_recipes,
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
    )
    selected_records = screen_records[:WEEKLY_DISCOVERY_FULL_VALIDATION_BUDGET]
    full_validation_records = _run_full_validation(
        week_of=as_of,
        review_root=review_root,
        selected_records=selected_records,
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
    )
    full_validation_records.sort(key=_full_rank, reverse=True)
    shortlist_records = full_validation_records[:WEEKLY_CANDIDATE_PROMOTION_CAP]
    promotion_results = _apply_shortlist_promotions(
        week_of=week_of,
        artifacts_root=resolved_artifacts_root,
        shortlist_records=shortlist_records,
    )
    shortlist_path = review_root / "discovery_shortlist.json"
    write_json(
        shortlist_path,
        {
            "generated_at_utc": utc_now(),
            "as_of": as_of,
            "run_id": run_id,
            "week_of": as_of,
            "shortlist_count": len(shortlist_records),
            "records": promotion_results,
        },
    )
    auto_bridge_summary = _run_same_week_auto_bridge(
        week_of=as_of,
        artifacts_root=resolved_artifacts_root,
        workbench_root=resolved_workbench_root,
        full_validation_records=full_validation_records,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=resolved_spot_ohlcv_external_root,
        run_id=run_id,
    )
    summary = _write_weekly_summary(
        week_of=as_of,
        compiler_backend=compiler_backend,
        artifacts_root=resolved_artifacts_root,
        review_root=review_root,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        universe_input=universe_input,
        registry_snapshot=registry_snapshot,
        recipe_catalog_path=recipe_catalog_path,
        screen_summary_path=screen_summary_path,
        shortlist_path=shortlist_path,
        recipes=recipes,
        heuristic_recipes=heuristic_recipes,
        agent_summary=agent_summary,
        merge_summary=merge_summary,
        screen_records=screen_records,
        full_validation_records=full_validation_records,
        promotion_results=promotion_results,
        auto_bridge_summary=auto_bridge_summary,
    )
    summary["workbench_root"] = str(resolved_workbench_root)
    return summary


def build_discovery_recipes(
    *,
    week_of: str,
    strategy_library: dict[str, Any],
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    recipes.extend(_portfolio_model_overlay_recipes(week_of=week_of, strategy_library=strategy_library))
    recipes.extend(_cross_sectional_relaunch_recipes(week_of=week_of, strategy_library=strategy_library))
    recipes.extend(_new_deterministic_recipes(week_of=week_of, universe_candidates=universe_candidates))
    recipes.extend(_new_ml_recipes(week_of=week_of, universe_candidates=universe_candidates))
    recipes.extend(_active_adjacency_recipes(week_of=week_of, strategy_library=strategy_library))
    deduped: list[dict[str, Any]] = []
    seen_recipe_ids: set[str] = set()
    for recipe in recipes:
        recipe_id = str(recipe["proposal_id"])
        if recipe_id in seen_recipe_ids:
            continue
        seen_recipe_ids.add(recipe_id)
        deduped.append(recipe)
    return deduped[:WEEKLY_DISCOVERY_SCREEN_BUDGET]


def _prepare_heuristic_recipe(*, recipe: dict[str, Any], registry_snapshot: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(recipe)
    normalized["proposal_origin"] = "heuristic"
    normalized.setdefault("search_action", "feature_variant")
    normalized.setdefault("family_registry_patch", {})
    normalized.setdefault("feature_registry_patch", {})
    normalized.setdefault("priority_score", _heuristic_priority(normalized))
    normalized.setdefault("complexity_tier", "medium")
    normalized.setdefault("risk_tags", ["heuristic_generated"])
    normalized.setdefault("auto_bridge_requested", False)
    normalized["registry_snapshot_id"] = registry_snapshot.get("snapshot_id")
    normalized.setdefault("family_id", normalized.get("model_family"))
    normalized.setdefault("novelty_score", 0.35)
    normalized.setdefault("family_usage_count", 0)
    normalized.setdefault("failure_rate_rolling_8w", 0.0)
    normalized.setdefault("regime_fit_tag", "generalist")
    normalized.setdefault("feature_family_ids", [])
    normalized.setdefault("published_via", "not_published")
    normalized["executable_signal"] = False
    normalized["ranking_score"] = proposal_ranking_score(normalized, seen_specs=[])
    return normalized


def _prepare_agent_recipe(*, recipe: dict[str, Any], registry_snapshot: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(recipe)
    normalized["proposal_origin"] = "agent"
    normalized["bucket"] = str(normalized.get("bucket") or normalized.get("proposal_bucket") or "config")
    normalized["source"] = str(normalized.get("source") or "proposal")
    normalized["registry_snapshot_id"] = str(
        normalized.get("registry_snapshot_id")
        or registry_snapshot.get("snapshot_id")
        or ""
    ) or None
    normalized.setdefault("family_id", normalized.get("model_family"))
    normalized.setdefault("risk_tags", ["agent_generated"])
    normalized.setdefault("published_via", "not_published")
    normalized["executable_signal"] = False
    normalized["ranking_score"] = proposal_ranking_score(normalized, seen_specs=[])
    return normalized


def _merge_proposal_lanes(
    *,
    heuristic_recipes: list[dict[str, Any]],
    agent_recipes: list[dict[str, Any]],
    allow_heuristic_only_fallback: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    agent_cap = 12
    heuristic_cap = 24 if allow_heuristic_only_fallback else 8
    ranked_agent = _rank_recipe_lane(agent_recipes, cap=agent_cap)
    ranked_heuristic = _rank_recipe_lane(heuristic_recipes, cap=heuristic_cap, seed_seen=ranked_agent)
    merged = _rank_recipe_lane(ranked_agent + ranked_heuristic, cap=24)
    return merged, {
        "proposal_lane_mix": {
            "agent": len([item for item in merged if str(item.get("proposal_origin") or "") == "agent"]),
            "heuristic": len([item for item in merged if str(item.get("proposal_origin") or "") == "heuristic"]),
        },
        "agent_cap": agent_cap,
        "heuristic_cap": heuristic_cap,
        "total_cap": 24,
        "heuristic_only_fallback": allow_heuristic_only_fallback,
    }


def _apply_recipe_data_readiness_gate(*, recipes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    executable: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for recipe in recipes:
        blocker_reason = blocked_discovery_reason(model_family=str(recipe.get("model_family") or ""))
        if blocker_reason is None:
            executable.append(recipe)
            continue
        blocked.append(
            {
                "recipe_id": recipe.get("proposal_id"),
                "strategy_id": recipe.get("strategy_id"),
                "model_family": recipe.get("model_family"),
                "bucket": recipe.get("bucket"),
                "proposal_origin": recipe.get("proposal_origin"),
                "data_gap_blocker": blocker_reason,
                "recipe": recipe,
            }
        )
    return executable, blocked


def _latest_discovery_summary_paths(*, artifacts_root: Path) -> list[Path]:
    new_paths = sorted((artifacts_root / "governance" / "discovery_runs").glob("*/*/discovery_governance_summary.json"))
    if new_paths:
        return new_paths
    return sorted((artifacts_root / "governance" / "weekly_reviews").glob("*/weekly_governance_summary.json"))


def _recent_duplicate_spec_hashes(*, artifacts_root: Path, as_of: str) -> set[str]:
    normalized_as_of = normalize_governance_as_of(as_of)
    summary_paths = _latest_discovery_summary_paths(artifacts_root=artifacts_root)
    latest_by_as_of: dict[str, Path] = {}
    for path in summary_paths:
        try:
            payload = read_json(path)
        except Exception:
            continue
        payload_as_of = normalize_governance_as_of(
            str(payload.get("as_of") or payload.get("week_of") or "")
        )
        if not payload_as_of or payload_as_of == normalized_as_of:
            continue
        latest_by_as_of[payload_as_of] = path
    selected_dates = sorted(latest_by_as_of.keys())[-3:]
    suppressed: set[str] = set()
    rerun_allowed: set[str] = set()
    for payload_as_of in selected_dates:
        payload = read_json(latest_by_as_of[payload_as_of])
        recipe_catalog_value = str(payload.get("discovery_recipe_catalog_path") or "").strip()
        recipe_catalog_path = Path(recipe_catalog_value) if recipe_catalog_value else None
        if recipe_catalog_path is not None and recipe_catalog_path.exists():
            catalog = read_json(recipe_catalog_path)
            for recipe in catalog.get("recipes", []):
                if isinstance(recipe, dict) and str(recipe.get("spec_hash") or "").strip():
                    suppressed.add(str(recipe["spec_hash"]))
        for evaluation in payload.get("evaluations", []):
            if not isinstance(evaluation, dict):
                continue
            recipe = evaluation.get("recipe") or {}
            spec_hash = str(recipe.get("spec_hash") or evaluation.get("spec_hash") or "").strip()
            if not spec_hash:
                continue
            if (
                str(evaluation.get("governance_action") or "") == "rerun_required"
                or is_rerun_required_experiment_status(str(evaluation.get("experiment_status") or ""))
            ):
                rerun_allowed.add(spec_hash)
    return suppressed - rerun_allowed


def _filter_recent_duplicate_recipes(
    *,
    recipes: list[dict[str, Any]],
    strategy_library: dict[str, Any],
    recent_duplicate_spec_hashes: set[str],
    run_id: str,
    as_of: str,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for recipe in recipes:
        normalized = dict(recipe)
        normalized["as_of"] = as_of
        normalized["run_id"] = run_id
        normalized["governance_as_of"] = as_of
        normalized["discovery_cadence"] = "daily_full"
        spec_hash = str(normalized.get("spec_hash") or "").strip()
        existing_entry = None if not spec_hash else library_entry_for_spec_hash(strategy_library=strategy_library, spec_hash=spec_hash)
        if spec_hash in recent_duplicate_spec_hashes:
            if existing_entry is None:
                continue
            lifecycle = str(existing_entry.get("lifecycle") or "")
            last_reason = str(existing_entry.get("last_transition_reason") or "")
            if lifecycle != "candidate" and last_reason not in {"discovery_rerun_required", "weekly_rerun_required"}:
                continue
        filtered.append(normalized)
    return filtered


def _rank_recipe_lane(
    recipes: list[dict[str, Any]],
    *,
    cap: int,
    seed_seen: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = list(seed_seen or [])
    remaining = [dict(recipe) for recipe in recipes]
    ranked: list[dict[str, Any]] = []
    while remaining and len(ranked) < cap:
        scored = []
        for recipe in remaining:
            score = proposal_ranking_score(recipe, seen_specs=accepted)
            candidate = dict(recipe)
            candidate["ranking_score"] = score
            scored.append(candidate)
        scored.sort(
            key=lambda item: (
                float(item.get("ranking_score", 0.0)),
                float(item.get("priority_score", 0.0)),
                -float(COMPLEXITY_TIERS.get(str(item.get("complexity_tier") or "medium"), 0.5)),
                str(item.get("proposal_id") or ""),
            ),
            reverse=True,
        )
        selected = scored[0]
        ranked.append(selected)
        accepted.append(selected)
        remaining = [
            recipe
            for recipe in remaining
            if str(recipe.get("proposal_id") or "") != str(selected.get("proposal_id") or "")
        ]
    return ranked


def _heuristic_priority(recipe: dict[str, Any]) -> float:
    bucket = str(recipe.get("bucket") or recipe.get("proposal_bucket") or "")
    if bucket == MODEL_OVERLAY_BUCKET:
        return 0.92
    if bucket == "active_adjacency":
        return 0.78
    if bucket == "new_ml_families":
        return 0.72
    if bucket == "new_deterministic_families":
        return 0.69
    if bucket == "cross_sectional_relaunch":
        return 0.64
    return 0.6


def _portfolio_model_overlay_recipes(*, week_of: str, strategy_library: dict[str, Any]) -> list[dict[str, Any]]:
    ready_entries = [
        entry
        for entry in strategy_library.get("entries", [])
        if _is_model_overlay_ready_portfolio_thesis(entry)
    ]
    ready_entries.sort(key=lambda entry: str(entry.get("strategy_id") or ""))
    ready_entries.sort(key=lambda entry: str(entry.get("updated_at_utc") or ""), reverse=True)
    ready_entries.sort(key=lambda entry: float(entry.get("review_priority", 0.0) or 0.0), reverse=True)
    ready_entries = ready_entries[:MODEL_OVERLAY_READY_THESIS_LIMIT]
    recipes: list[dict[str, Any]] = []
    seen_generation_keys: set[tuple[str, str, str]] = set()
    for entry in ready_entries:
        base_strategy_id = str(entry.get("strategy_id") or "").strip()
        parent_spec_hash = str(entry.get("spec_hash") or "").strip() or None
        thesis_profile = dict(entry.get("thesis_profile") or {})
        for model_family in MODEL_OVERLAY_MODEL_FAMILIES:
            generation_key = (base_strategy_id, model_family, HYPOTHESIS_MODEL_LANE)
            if generation_key in seen_generation_keys:
                continue
            seen_generation_keys.add(generation_key)
            rationale, expected_edge, invalidates_if = model_overlay_text(
                base_strategy_id=base_strategy_id,
                thesis_family=str(entry.get("thesis_family") or ""),
                model_family=model_family,
            )
            recipe = _build_discovery_recipe(
                week_of=week_of,
                bucket=MODEL_OVERLAY_BUCKET,
                proposal_bucket="config",
                strategy_id=model_overlay_child_strategy_id(
                    base_strategy_id=base_strategy_id,
                    model_family=model_family,
                ),
                shape=str(entry.get("shape") or ""),
                strategy_profile=str(entry.get("strategy_profile") or ""),
                subject=entry.get("subject"),
                universe_filter=dict(entry.get("universe_filter") or {}),
                model_family=model_family,
                feature_groups=list(entry.get("feature_groups") or FEATURE_GROUPS),
                profile_constraints_override=dict(entry.get("profile_constraints_override") or {}),
                base_strategy_id=base_strategy_id,
                rationale=rationale,
                expected_edge=expected_edge,
                invalidates_if=invalidates_if,
                search_action="model_overlay",
                parent_spec_hash=parent_spec_hash,
                priority_score=0.92,
                complexity_tier="medium",
                risk_tags=["model_overlay", "portfolio_validated"],
                family_id=model_family,
                research_lane=HYPOTHESIS_MODEL_LANE,
                promotion_eligibility="eligible",
                thesis_family=str(entry.get("thesis_family") or "").strip() or None,
                requires_derivatives_features=bool(entry.get("requires_derivatives_features")),
                daily_executable=bool(entry.get("daily_executable")),
                thesis_profile=thesis_profile,
                model_overlay_ready=True,
            )
            recipes.append(recipe)
    return recipes


def _is_model_overlay_ready_portfolio_thesis(entry: dict[str, Any]) -> bool:
    if not isinstance(entry, dict):
        return False
    if str(entry.get("research_lane") or "") != HYPOTHESIS_PORTFOLIO_LANE:
        return False
    if not bool(entry.get("model_overlay_ready")):
        return False
    if str(entry.get("promotion_eligibility") or "") != "eligible":
        return False
    if not bool(entry.get("daily_executable")):
        return False
    if str(strategy_lifecycle(entry) or "") not in {"active", "watch", "candidate"}:
        return False
    thesis_profile = dict(entry.get("thesis_profile") or {})
    promotion_path = [str(item) for item in thesis_profile.get("promotion_path", []) if str(item).strip()]
    return HYPOTHESIS_MODEL_LANE in promotion_path


def _cross_sectional_relaunch_recipes(*, week_of: str, strategy_library: dict[str, Any]) -> list[dict[str, Any]]:
    entries_by_key = {
        (str(entry.get("strategy_profile")), str(entry.get("model_family")), str(entry.get("shape"))): entry
        for entry in strategy_library.get("entries", [])
        if str(entry.get("shape")) == "cross_sectional"
    }
    recipes: list[dict[str, Any]] = []
    for strategy_profile in STRATEGY_PROFILES:
        for model_family in CROSS_SECTIONAL_RELAUNCH_MODELS:
            existing = entries_by_key.get((strategy_profile, model_family, "cross_sectional"))
            universe_filter = (
                dict(existing.get("universe_filter", {}))
                if existing is not None
                else {"liquidity_buckets": sorted(profile_constraints(strategy_profile)["allowed_liquidity_buckets"])}
            )
            feature_groups = list(existing.get("feature_groups", FEATURE_GROUPS)) if existing is not None else list(FEATURE_GROUPS)
            strategy_id = (
                str(existing.get("strategy_id"))
                if existing is not None
                else f"baseline-{strategy_profile}-{slugify(model_family)}-cross-sectional"
            )
            recipes.append(
                _build_discovery_recipe(
                    week_of=week_of,
                    bucket="cross_sectional_relaunch",
                    strategy_id=strategy_id,
                    shape="cross_sectional",
                    strategy_profile=strategy_profile,
                    subject=None,
                    universe_filter=universe_filter,
                    model_family=model_family,
                    feature_groups=feature_groups,
                    profile_constraints_override=existing.get("profile_constraints_override") if existing is not None else {},
                    base_strategy_id=strategy_id,
                    rationale="Re-run cross-sectional baselines on the full Top 100 cohort so discovery can re-test models that should not consume daily monitoring budget.",
                    expected_edge="Cross-sectional ranking should only return to daily monitoring if the broader universe restores OOS stability.",
                    invalidates_if="Validation/test returns remain negative or walk-forward median OOS Sharpe stays non-positive.",
                )
            )
    return recipes


def _new_deterministic_recipes(
    *,
    week_of: str,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> list[dict[str, Any]]:
    top_subjects = _top_subject_candidates(universe_candidates=universe_candidates, limit=3)
    recipes: list[dict[str, Any]] = []
    for model_family in NEW_DETERMINISTIC_FAMILIES:
        for candidate in top_subjects:
            recipes.append(
                _build_discovery_recipe(
                    week_of=week_of,
                    bucket="new_deterministic_families",
                    strategy_id=f"discovery-{slugify(candidate.subject)}-balanced-{slugify(model_family)}-single-asset",
                    shape="single_asset",
                    strategy_profile="balanced",
                    subject=candidate.subject,
                    universe_filter=None,
                    model_family=model_family,
                    feature_groups=list(FEATURE_GROUPS),
                    profile_constraints_override={},
                    base_strategy_id=None,
                    rationale="Probe a new deterministic family on a liquid Top 100 subject before any candidate promotion.",
                    expected_edge="Funding, basis, volatility, or sparse events may expose edges not covered by the original baseline stack.",
                    invalidates_if="The family cannot sustain positive validation/test returns or walk-forward stability on a liquid subject.",
                )
            )
    return recipes


def _new_ml_recipes(
    *,
    week_of: str,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
) -> list[dict[str, Any]]:
    top_subjects = _top_subject_candidates(universe_candidates=universe_candidates, limit=2)
    subject_a = top_subjects[0].subject
    subject_b = top_subjects[1].subject if len(top_subjects) > 1 else top_subjects[0].subject
    recipes: list[dict[str, Any]] = []
    for model_family in NEW_ML_FAMILIES:
        recipes.extend(
            [
                _build_discovery_recipe(
                    week_of=week_of,
                    bucket="new_ml_families",
                    strategy_id=f"discovery-{slugify(subject_a)}-balanced-{slugify(model_family)}-single-asset",
                    shape="single_asset",
                    strategy_profile="balanced",
                    subject=subject_a,
                    universe_filter=None,
                    model_family=model_family,
                    feature_groups=list(FEATURE_GROUPS),
                    profile_constraints_override={},
                    base_strategy_id=None,
                    rationale="Test a new sklearn family on a liquid single-asset swing setup.",
                    expected_edge="A different classifier family may extract a cleaner decision boundary than the original baseline models.",
                    invalidates_if="Validation/test performance remains weak once costs and walk-forward checks are applied.",
                ),
                _build_discovery_recipe(
                    week_of=week_of,
                    bucket="new_ml_families",
                    strategy_id=f"discovery-{slugify(subject_b)}-aggressive-{slugify(model_family)}-single-asset",
                    shape="single_asset",
                    strategy_profile="aggressive",
                    subject=subject_b,
                    universe_filter=None,
                    model_family=model_family,
                    feature_groups=list(FEATURE_GROUPS),
                    profile_constraints_override={},
                    base_strategy_id=None,
                    rationale="Re-test the new sklearn family under a wider single-asset profile to see whether the edge survives looser constraints.",
                    expected_edge="If the classifier is robust it should still clear OOS gates under a more aggressive envelope.",
                    invalidates_if="The model only appears attractive under overly narrow constraints or fails walk-forward OOS checks.",
                ),
                _build_discovery_recipe(
                    week_of=week_of,
                    bucket="new_ml_families",
                    strategy_id=f"discovery-balanced-{slugify(model_family)}-cross-sectional",
                    shape="cross_sectional",
                    strategy_profile="balanced",
                    subject=None,
                    universe_filter={"liquidity_buckets": sorted(profile_constraints("balanced")["allowed_liquidity_buckets"])},
                    model_family=model_family,
                    feature_groups=list(FEATURE_GROUPS),
                    profile_constraints_override={},
                    base_strategy_id=None,
                    rationale="Relaunch a new sklearn family as a Top 100 cross-sectional ranker.",
                    expected_edge="A new classifier family may improve ranking quality once the universe is broad enough.",
                    invalidates_if="Cross-sectional OOS returns or walk-forward stability remain weak.",
                ),
                _build_discovery_recipe(
                    week_of=week_of,
                    bucket="new_ml_families",
                    strategy_id=f"discovery-aggressive-{slugify(model_family)}-cross-sectional",
                    shape="cross_sectional",
                    strategy_profile="aggressive",
                    subject=None,
                    universe_filter={"liquidity_buckets": sorted(profile_constraints("aggressive")["allowed_liquidity_buckets"])},
                    model_family=model_family,
                    feature_groups=list(FEATURE_GROUPS),
                    profile_constraints_override={},
                    base_strategy_id=None,
                    rationale="Test the new sklearn family on the widest cross-sectional envelope available in weekly discovery.",
                    expected_edge="If a broad Top 100 cohort creates enough dispersion, the model may finally clear the cross-sectional gate.",
                    invalidates_if="The aggressive cross-sectional run still cannot sustain positive OOS performance.",
                ),
            ]
        )
    return recipes


def _active_adjacency_recipes(*, week_of: str, strategy_library: dict[str, Any]) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    candidate_entries = [
        entry
        for entry in strategy_library.get("entries", [])
        if strategy_lifecycle(entry) == "candidate"
    ]
    candidate_entries.sort(key=lambda entry: str(entry.get("updated_at_utc") or ""), reverse=True)
    for entry in candidate_entries[:6]:
        recipe = _build_discovery_recipe(
            week_of=week_of,
            bucket="active_adjacency",
            strategy_id=str(entry["strategy_id"]),
            shape=str(entry["shape"]),
            strategy_profile=str(entry["strategy_profile"]),
            subject=entry.get("subject"),
            universe_filter=entry.get("universe_filter"),
            model_family=str(entry["model_family"]),
            feature_groups=list(entry.get("feature_groups", FEATURE_GROUPS)),
            profile_constraints_override=entry.get("profile_constraints_override"),
            base_strategy_id=entry.get("base_strategy_id") or entry.get("strategy_id"),
            rationale="Re-confirm an existing candidate under the same spec_hash so weekly discovery can decide whether it deserves promotion.",
            expected_edge="A second weekly pass should confirm that the candidate is stable enough to stay on the promotion path.",
            invalidates_if="The candidate fails validation/test or loses walk-forward stability on the confirmation week.",
        )
        if recipe["spec_hash"] in seen_hashes:
            continue
        seen_hashes.add(recipe["spec_hash"])
        recipes.append(recipe)
    active_entries = [
        entry
        for entry in strategy_library.get("entries", [])
        if str(entry.get("strategy_id")) in ACTIVE_STRATEGY_IDS
        or strategy_lifecycle(entry) in {"active", "watch"}
    ]
    active_entries.sort(
        key=lambda entry: (
            0 if str(entry.get("strategy_id")) in ACTIVE_STRATEGY_IDS else 1,
            str(entry.get("strategy_id") or ""),
        )
    )
    for index, entry in enumerate(active_entries):
        recipe = _build_discovery_recipe(
            week_of=week_of,
            bucket="active_adjacency",
            strategy_id=f"discovery-adj-{slugify(str(entry['strategy_id']))}-{index}",
            shape=str(entry["shape"]),
            strategy_profile=str(entry["strategy_profile"]),
            subject=entry.get("subject"),
            universe_filter=entry.get("universe_filter"),
            model_family=str(entry["model_family"]),
            feature_groups=_active_feature_subset(list(entry.get("feature_groups", FEATURE_GROUPS)), variant_index=index),
            profile_constraints_override=entry.get("profile_constraints_override"),
            base_strategy_id=entry.get("strategy_id"),
            rationale="Test whether a slimmer feature surface preserves the edge around a currently active strategy.",
            expected_edge="If the active alpha is robust, it should survive with a smaller and cleaner feature subset.",
            invalidates_if="The narrower feature surface causes validation/test deterioration or walk-forward weakness.",
        )
        if recipe["spec_hash"] in seen_hashes:
            continue
        seen_hashes.add(recipe["spec_hash"])
        recipes.append(recipe)
        if len(recipes) >= DISCOVERY_BUCKET_SIZE:
            return recipes[:DISCOVERY_BUCKET_SIZE]
    for index, entry in enumerate(active_entries):
        if len(recipes) >= DISCOVERY_BUCKET_SIZE:
            break
        recipe = _build_discovery_recipe(
            week_of=week_of,
            bucket="active_adjacency",
            strategy_id=f"discovery-tightened-{slugify(str(entry['strategy_id']))}-{index}",
            shape=str(entry["shape"]),
            strategy_profile=str(entry["strategy_profile"]),
            subject=entry.get("subject"),
            universe_filter=entry.get("universe_filter"),
            model_family=str(entry["model_family"]),
            feature_groups=list(entry.get("feature_groups", FEATURE_GROUPS)),
            profile_constraints_override=_tightened_profile_override(entry, index=index),
            base_strategy_id=entry.get("strategy_id"),
            rationale="Tighten the implementation envelope around an active alpha without changing its model family.",
            expected_edge="A truly robust alpha should remain attractive after leverage/turnover constraints are tightened.",
            invalidates_if="The tighter envelope removes the edge or makes OOS performance unstable.",
        )
        if recipe["spec_hash"] in seen_hashes:
            continue
        seen_hashes.add(recipe["spec_hash"])
        recipes.append(recipe)
    return recipes[:DISCOVERY_BUCKET_SIZE]


def _build_discovery_recipe(
    *,
    week_of: str,
    bucket: str,
    proposal_bucket: str | None = None,
    strategy_id: str,
    shape: str,
    strategy_profile: str,
    subject: str | None,
    universe_filter: dict[str, Any] | None,
    model_family: str,
    feature_groups: list[str],
    profile_constraints_override: dict[str, Any] | None,
    base_strategy_id: str | None,
    rationale: str,
    expected_edge: str,
    invalidates_if: str,
    proposal_origin: str = "heuristic",
    search_action: str = "feature_variant",
    parent_spec_hash: str | None = None,
    family_registry_patch: dict[str, Any] | None = None,
    feature_registry_patch: dict[str, Any] | None = None,
    priority_score: float = 0.0,
    complexity_tier: str = "medium",
    risk_tags: list[str] | None = None,
    auto_bridge_requested: bool = False,
    registry_snapshot_id: str | None = None,
    family_id: str | None = None,
    novelty_score: float | None = None,
    family_usage_count: int | None = None,
    failure_rate_rolling_8w: float | None = None,
    regime_fit_tag: str | None = None,
    research_lane: str | None = None,
    promotion_eligibility: str | None = None,
    thesis_family: str | None = None,
    requires_derivatives_features: bool | None = None,
    daily_executable: bool | None = None,
    thesis_profile: dict[str, Any] | None = None,
    model_overlay_ready: bool | None = None,
) -> dict[str, Any]:
    normalized_subject = str(subject).upper() if subject else None
    normalized_filter = dict(universe_filter or {})
    normalized_groups = list(dict.fromkeys(feature_groups or list(FEATURE_GROUPS)))
    normalized_override = dict(profile_constraints_override or {})
    spec_hash = strategy_spec_hash(
        shape=shape,
        strategy_profile=strategy_profile,
        subject=normalized_subject,
        universe_filter=normalized_filter,
        model_family=model_family,
        feature_groups=normalized_groups,
        profile_constraints_override=normalized_override,
        family_registry_patch=family_registry_patch,
        feature_registry_patch=feature_registry_patch,
        search_action=search_action,
    )
    recipe_id = f"{iso_week_label(week_of)}-{bucket}-{slugify(strategy_id)}-{spec_hash[:8]}"
    return {
        "proposal_id": recipe_id,
        "proposal_bucket": proposal_bucket or bucket,
        "bucket": bucket,
        "week_of": week_of,
        "base_strategy_id": base_strategy_id,
        "strategy_id": strategy_id,
        "shape": shape,
        "strategy_profile": strategy_profile,
        "subject": normalized_subject,
        "universe_filter": normalized_filter,
        "model_family": model_family,
        "feature_groups": normalized_groups,
        "profile_constraints_override": normalized_override,
        "rationale": rationale,
        "expected_edge": expected_edge,
        "invalidates_if": invalidates_if,
        "spec_hash": spec_hash,
        "source": "discovery",
        "proposal_origin": proposal_origin,
        "search_action": search_action,
        "parent_spec_hash": None if parent_spec_hash in {None, ""} else str(parent_spec_hash),
        "family_registry_patch": dict(family_registry_patch or {}),
        "feature_registry_patch": dict(feature_registry_patch or {}),
        "priority_score": float(priority_score),
        "complexity_tier": complexity_tier,
        "risk_tags": list(risk_tags or []),
        "auto_bridge_requested": bool(auto_bridge_requested),
        "registry_snapshot_id": registry_snapshot_id,
        "family_id": family_id or model_family,
        "feature_family_ids": [
            str(item.get("family_id"))
            for item in (feature_registry_patch or {}).get("families", [])
            if isinstance(item, dict) and str(item.get("family_id") or "").strip()
        ],
        "published_via": "not_published",
        "executable_signal": False,
        "novelty_score": float(novelty_score or 0.0),
        "family_usage_count": int(family_usage_count or 0),
        "failure_rate_rolling_8w": float(failure_rate_rolling_8w or 0.0),
        "regime_fit_tag": str(regime_fit_tag or "generalist"),
        "research_lane": None if research_lane in {None, ""} else str(research_lane),
        "promotion_eligibility": None if promotion_eligibility in {None, ""} else str(promotion_eligibility),
        "thesis_family": None if thesis_family in {None, ""} else str(thesis_family),
        "requires_derivatives_features": (
            None if requires_derivatives_features is None else bool(requires_derivatives_features)
        ),
        "daily_executable": None if daily_executable is None else bool(daily_executable),
        "thesis_profile": dict(thesis_profile or {}),
        "model_overlay_ready": None if model_overlay_ready is None else bool(model_overlay_ready),
    }


def _strategy_entry_from_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    base_constraints = dict(profile_constraints(recipe["strategy_profile"]))
    if isinstance(base_constraints.get("allowed_liquidity_buckets"), set):
        base_constraints["allowed_liquidity_buckets"] = sorted(base_constraints["allowed_liquidity_buckets"])
    override = dict(recipe.get("profile_constraints_override", {}))
    constraints = dict(base_constraints)
    constraints.update(override)
    return {
        "strategy_id": recipe["strategy_id"],
        "shape": recipe["shape"],
        "strategy_profile": recipe["strategy_profile"],
        "subject": recipe.get("subject"),
        "universe_filter": dict(recipe.get("universe_filter", {})),
        "model_family": recipe["model_family"],
        "feature_groups": list(recipe.get("feature_groups", [])),
        "profile_constraints": constraints,
        "profile_constraints_override": override,
        "source": recipe.get("source", "discovery"),
        "lifecycle": "discovery",
        "monitoring_status": "discovery",
        "selection_lane": "discovery",
        "promotion_state": "staged",
        "spec_hash": recipe["spec_hash"],
        "base_strategy_id": recipe.get("base_strategy_id"),
        "proposal_origin": recipe.get("proposal_origin", "heuristic"),
        "search_action": recipe.get("search_action", "feature_variant"),
        "parent_spec_hash": recipe.get("parent_spec_hash"),
        "family_registry_patch": dict(recipe.get("family_registry_patch", {})),
        "feature_registry_patch": dict(recipe.get("feature_registry_patch", {})),
        "priority_score": float(recipe.get("priority_score", 0.0) or 0.0),
        "complexity_tier": str(recipe.get("complexity_tier", "medium")),
        "risk_tags": [str(item) for item in recipe.get("risk_tags", []) if str(item).strip()],
        "auto_bridge_requested": bool(recipe.get("auto_bridge_requested")),
        "registry_snapshot_id": recipe.get("registry_snapshot_id"),
        "family_id": recipe.get("family_id", recipe.get("model_family")),
        "feature_family_ids": list(recipe.get("feature_family_ids", [])),
        "published_via": recipe.get("published_via", "not_published"),
        "executable_signal": False,
        "novelty_score": float(recipe.get("novelty_score", 0.0) or 0.0),
        "family_usage_count": int(recipe.get("family_usage_count", 0) or 0),
        "failure_rate_rolling_8w": float(recipe.get("failure_rate_rolling_8w", 0.0) or 0.0),
        "regime_fit_tag": str(recipe.get("regime_fit_tag", "generalist")),
        "governance_as_of": recipe.get("governance_as_of", recipe.get("as_of")),
        "run_id": recipe.get("run_id"),
        "discovery_pass_streak": 0,
        "last_discovery_pass_as_of": None,
        "last_discovery_run_id": None,
        "discovery_cadence": recipe.get("discovery_cadence", "daily_full"),
        "research_lane": recipe.get("research_lane"),
        "promotion_eligibility": recipe.get("promotion_eligibility"),
        "thesis_family": recipe.get("thesis_family"),
        "requires_derivatives_features": recipe.get("requires_derivatives_features"),
        "daily_executable": recipe.get("daily_executable"),
        "thesis_profile": dict(recipe.get("thesis_profile", {})),
        "model_overlay_ready": bool(recipe.get("model_overlay_ready")),
    }


def _top_subject_candidates(
    *,
    universe_candidates: tuple[QuantUniverseCandidate, ...],
    limit: int,
) -> list[QuantUniverseCandidate]:
    ranked = sorted(
        universe_candidates,
        key=lambda candidate: (
            candidate.selection_rank,
            -float(candidate.rolling_mean_quote_volume_usd_30d),
            candidate.subject,
        ),
    )
    return ranked[:limit]


def _tightened_profile_override(entry: dict[str, Any], *, index: int) -> dict[str, Any]:
    current = dict(entry.get("profile_constraints") or profile_constraints(str(entry["strategy_profile"])))
    max_leverage = float(current.get("max_gross_leverage", 1.0))
    max_turnover = float(current.get("max_turnover_per_rebalance", 1.0))
    multiplier = 0.85 - (min(index, 3) * 0.05)
    return {
        "max_gross_leverage": round(max(0.5, max_leverage * multiplier), 4),
        "max_turnover_per_rebalance": round(max(0.5, max_turnover * multiplier), 4),
    }


def _active_feature_subset(feature_groups: list[str], *, variant_index: int) -> list[str]:
    normalized = list(dict.fromkeys(feature_groups or list(FEATURE_GROUPS)))
    if variant_index % 2 == 0:
        subset = [group for group in normalized if group != "events"]
        return subset or normalized
    prioritized = ["core_context", "structure", "trend", "derivatives", "volume"]
    subset = [group for group in prioritized if group in normalized]
    return subset or normalized


def _run_discovery_screen(
    *,
    week_of: str,
    review_root: Path,
    recipes: list[dict[str, Any]],
    feature_sets: list[dict[str, Any]],
    compiler_backend: str,
) -> tuple[list[dict[str, Any]], Path]:
    screen_root = review_root / "s"
    screen_root.mkdir(parents=True, exist_ok=True)
    screen_experiments = run_quant_experiments_for_strategies(
        as_of=week_of,
        artifacts_root=screen_root,
        strategies=[_strategy_entry_from_recipe(recipe) for recipe in recipes],
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
    )
    screen_records = [
        _discovery_experiment_record(recipe=recipe, experiment=experiment)
        for recipe, experiment in zip(recipes, screen_experiments, strict=True)
    ]
    screen_records.sort(key=_screen_rank, reverse=True)
    screen_summary_path = review_root / "discovery_screen_summary.json"
    write_json(
        screen_summary_path,
        {
            "generated_at_utc": utc_now(),
            "as_of": week_of,
            "run_id": str(recipes[0].get("run_id")) if recipes else None,
            "week_of": week_of,
            "screen_recipe_count": len(screen_records),
            "proposal_lane_mix": {
                "agent": len([record for record in screen_records if str(record.get("proposal_origin") or "") == "agent"]),
                "heuristic": len([record for record in screen_records if str(record.get("proposal_origin") or "") == "heuristic"]),
            },
            "bucket_counts": _bucket_counts(recipes),
            "selected_full_validation_count": min(len(screen_records), WEEKLY_DISCOVERY_FULL_VALIDATION_BUDGET),
            "selected_full_validation_recipe_ids": [record["recipe_id"] for record in screen_records[:WEEKLY_DISCOVERY_FULL_VALIDATION_BUDGET]],
            "top_screen_recipe_ids": [record["recipe_id"] for record in screen_records[:10]],
            "records": screen_records,
        },
    )
    return screen_records, screen_summary_path


def _run_full_validation(
    *,
    week_of: str,
    review_root: Path,
    selected_records: list[dict[str, Any]],
    feature_sets: list[dict[str, Any]],
    compiler_backend: str,
) -> list[dict[str, Any]]:
    full_validation_root = review_root / "f"
    full_validation_root.mkdir(parents=True, exist_ok=True)
    experiments = run_quant_experiments_for_strategies(
        as_of=week_of,
        artifacts_root=full_validation_root,
        strategies=[_strategy_entry_from_recipe(record["recipe"]) for record in selected_records],
        feature_sets=feature_sets,
        compiler_backend=compiler_backend,
    )
    return [
        _discovery_experiment_record(recipe=record["recipe"], experiment=experiment)
        for record, experiment in zip(selected_records, experiments, strict=True)
    ]


def _discovery_experiment_record(*, recipe: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    validation_report = dict(experiment.get("validation_report") or {})
    return {
        "recipe_id": recipe["proposal_id"],
        "bucket": recipe["bucket"],
        "proposal_origin": recipe.get("proposal_origin", "heuristic"),
            "search_action": recipe.get("search_action", "feature_variant"),
        "registry_snapshot_id": recipe.get("registry_snapshot_id"),
        "family_id": recipe.get("family_id", recipe.get("model_family")),
        "as_of": recipe.get("as_of", recipe.get("week_of")),
        "run_id": recipe.get("run_id"),
        "strategy_id": experiment.get("strategy_id"),
        "experiment_id": experiment.get("experiment_id"),
        "experiment_status": str(experiment.get("experiment_status") or "fail"),
        "validation_metrics": dict(validation_report.get("validation_metrics") or {}),
        "test_metrics": dict(validation_report.get("test_metrics") or {}),
        "walk_forward": dict(validation_report.get("walk_forward") or {}),
        "alpha_card_path": experiment.get("alpha_card_path"),
        "validation_report_path": experiment.get("validation_report_path"),
        "recipe": recipe,
        "experiment": experiment,
    }


def _screen_rank(record: dict[str, Any]) -> tuple[float, float, float]:
    validation_metrics = dict(record.get("validation_metrics") or {})
    status_boost = 1_000.0 if is_pass_experiment_status(str(record.get("experiment_status"))) else 0.0
    return (
        status_boost + float(validation_metrics.get("net_return", 0.0)) * 100.0 + float(validation_metrics.get("sharpe", 0.0)) * 10.0,
        -float(validation_metrics.get("max_drawdown", 1.0) or 1.0),
        float((record.get("walk_forward") or {}).get("median_oos_sharpe", 0.0)),
    )


def _full_rank(record: dict[str, Any]) -> tuple[float, float, float]:
    test_metrics = dict(record.get("test_metrics") or {})
    walk_forward = dict(record.get("walk_forward") or {})
    status_boost = 1_000.0 if is_pass_experiment_status(str(record.get("experiment_status"))) else 0.0
    return (
        status_boost
        + float(test_metrics.get("net_return", 0.0)) * 100.0
        + float(test_metrics.get("sharpe", 0.0)) * 10.0
        + float(walk_forward.get("median_oos_sharpe", 0.0)) * 10.0,
        -float(test_metrics.get("max_drawdown", 1.0) or 1.0),
        float((record.get("validation_metrics") or {}).get("net_return", 0.0)),
    )


def _apply_shortlist_promotions(
    *,
    week_of: str,
    artifacts_root: Path,
    shortlist_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    strategy_library = load_strategy_library(artifacts_root=artifacts_root)
    promotion_results: list[dict[str, Any]] = []
    for record in shortlist_records:
        governance_action = "not_selected"
        if is_pass_experiment_status(str(record["experiment_status"])):
            governance_result = apply_weekly_proposal_result(
                artifacts_root=artifacts_root,
                strategy_library=strategy_library,
                proposal_spec=record["recipe"],
                evaluation_status=str(record["experiment_status"]),
                week_of=week_of,
            )
            strategy_library = load_strategy_library(artifacts_root=artifacts_root)
            governance_action = str(governance_result["action"])
        promotion_results.append(
            {
                "recipe_id": record["recipe_id"],
                "strategy_id": record["strategy_id"],
                "experiment_id": record["experiment_id"],
                "experiment_status": record["experiment_status"],
                "bucket": record["bucket"],
                "proposal_origin": record.get("proposal_origin", "heuristic"),
            "search_action": record.get("search_action", "feature_variant"),
                "registry_snapshot_id": record.get("registry_snapshot_id"),
                "family_id": record.get("family_id"),
                "governance_action": governance_action,
                "validation_metrics": record["validation_metrics"],
                "test_metrics": record["test_metrics"],
                "walk_forward": record["walk_forward"],
                "alpha_card_path": record["alpha_card_path"],
                "validation_report_path": record["validation_report_path"],
            }
        )
    return promotion_results


def _run_same_day_auto_bridge(
    *,
    week_of: str,
    artifacts_root: Path,
    workbench_root: Path,
    full_validation_records: list[dict[str, Any]],
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    run_id: str | None = None,
) -> dict[str, Any]:
    agent_experiments = [
        dict(record.get("experiment") or {})
        for record in full_validation_records
        if str(record.get("proposal_origin") or "") == "agent"
        and isinstance(record.get("experiment"), dict)
    ]
    if not agent_experiments:
        return {
            "status": "no_agent_candidates",
            "success": True,
            "auto_bridged_snapshot_count": 0,
            "auto_bridged_agent_snapshot_count": 0,
            "published_snapshot_count": 0,
            "bridge_summary_path": None,
        }
    daily_manifest = write_daily_alpha_manifest_from_experiments(
        artifacts_root=artifacts_root,
        as_of=week_of,
        experiments=agent_experiments,
    )
    strategy_library = load_strategy_library(artifacts_root=artifacts_root)
    decisions = write_promotion_decisions_for_manifest(
        artifacts_root=artifacts_root,
        as_of=week_of,
        strategy_library=strategy_library,
    )
    bridge_summary = export_passed_alphas_to_workbench(
        as_of=week_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=spot_ohlcv_external_root,
        daily_export_cap=8,
        single_asset_export_cap=5,
        cross_sectional_group_cap=3,
        agent_export_cap=6,
    )
    bridge_summary["daily_alpha_manifest_path"] = str(daily_manifest["path"])
    bridge_summary["promotion_decision_count"] = len(decisions)
    bridge_summary["run_id"] = run_id
    bridge_summary["auto_bridged_snapshot_count"] = int(bridge_summary.get("published_snapshot_count", 0) or 0)
    bridge_summary["auto_bridged_agent_snapshot_count"] = sum(
        1
        for entry in bridge_summary.get("exports", [])
        if str(entry.get("proposal_origin") or "") == "agent"
    )
    return bridge_summary


def _run_same_week_auto_bridge(
    *,
    week_of: str,
    artifacts_root: Path,
    workbench_root: Path,
    full_validation_records: list[dict[str, Any]],
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    run_id: str | None = None,
) -> dict[str, Any]:
    return _run_same_day_auto_bridge(
        week_of=week_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
        full_validation_records=full_validation_records,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=spot_ohlcv_external_root,
        run_id=run_id,
    )


def _write_weekly_summary(
    *,
    week_of: str,
    compiler_backend: str,
    artifacts_root: Path,
    review_root: Path,
    run_id: str,
    generated_at_utc: str,
    universe_input: QuantUniverseInput,
    registry_snapshot: dict[str, Any],
    recipe_catalog_path: Path,
    screen_summary_path: Path,
    shortlist_path: Path,
    recipes: list[dict[str, Any]],
    heuristic_recipes: list[dict[str, Any]],
    agent_summary: dict[str, Any],
    merge_summary: dict[str, Any],
    screen_records: list[dict[str, Any]],
    full_validation_records: list[dict[str, Any]],
    promotion_results: list[dict[str, Any]],
    auto_bridge_summary: dict[str, Any],
) -> dict[str, Any]:
    final_library = load_strategy_library(artifacts_root=artifacts_root)
    current_lifecycle_counts: dict[str, int] = {}
    for entry in final_library.get("entries", []):
        lifecycle = str(entry.get("lifecycle") or "active")
        current_lifecycle_counts[lifecycle] = current_lifecycle_counts.get(lifecycle, 0) + 1
    as_of = normalize_governance_as_of(week_of)
    def _lane_pass_rate(records: list[dict[str, Any]], lane: str) -> float:
        lane_records = [
            item for item in records
            if str(item.get("research_lane") or item.get("recipe", {}).get("research_lane") or "").strip() == lane
        ]
        if not lane_records:
            return 0.0
        passed = sum(1 for item in lane_records if is_pass_experiment_status(str(item.get("experiment_status") or "")))
        return passed / len(lane_records)

    summary = with_evidence_metadata(
        {
            "generated_at_utc": generated_at_utc,
            "status": "success",
            "success": True,
            "as_of": as_of,
            "run_id": run_id,
            "week_of": as_of,
            "governance_as_of": as_of,
            "iso_week": iso_week_label(as_of),
            "cycle_mode": "discovery_full_daily",
            "discovery_cadence": "daily_full",
            "compiler_backend": compiler_backend,
            "runtime_flags": dict(RUNTIME_EVOLUTION_FLAGS),
            "strategy_catalog_path": str(strategy_catalog_path(artifacts_root=artifacts_root)),
            "strategy_library_path": str(strategy_library_path(artifacts_root=artifacts_root)),
            "registry_snapshot_id": registry_snapshot.get("snapshot_id"),
            "registry_snapshot_path": registry_snapshot.get("path"),
            "proposal_count": len(recipes),
            "discovery_recipe_count": len(heuristic_recipes),
            "heuristic_proposal_count": len(heuristic_recipes),
            "agent_proposal_count": len(agent_summary.get("validated_proposals", [])),
            "agent_raw_proposal_count": int(agent_summary.get("raw_proposal_count", 0) or 0),
            "agent_compiler_extracted_proposal_count": int(agent_summary.get("compiler_extracted_proposal_count", 0) or 0),
            "agent_parse_success_rate": float(agent_summary.get("parse_success_rate", 0.0) or 0.0),
            "agent_quarantine_rate": float(agent_summary.get("quarantine_rate", 0.0) or 0.0),
            "agent_quarantined_proposal_count": int(agent_summary.get("quarantined_proposal_count", 0) or 0),
            "agent_compiler_hygiene_quarantine_count": int(agent_summary.get("compiler_hygiene_quarantine_count", 0) or 0),
            "agent_quarantine_reason_counts": dict(agent_summary.get("quarantine_reason_counts") or {}),
            "agent_api_failure_rate": float(agent_summary.get("api_failure_rate", 0.0) or 0.0),
            "agent_proposal_summary_path": agent_summary.get("summary_path"),
            "selector_usage": dict(agent_summary.get("selector_usage") or {}),
            "compiler_usage": dict(agent_summary.get("compiler_usage") or {}),
            "prompt_budget_status": dict(agent_summary.get("prompt_budget_status") or {}),
            "response_format_fallback_count": int(agent_summary.get("response_format_fallback_count", 0) or 0),
            "proposal_lane_mix": dict(merge_summary.get("proposal_lane_mix") or {}),
            "screen_recipe_count": len(screen_records),
            "full_validation_count": len(full_validation_records),
            "shortlist_count": len(promotion_results),
            "sandbox_accepted_count": sum(
                1 for item in full_validation_records if counts_as_sandbox_accepted(item["experiment_status"])
            ),
            "promoted_to_candidate_count": sum(1 for item in promotion_results if item["governance_action"] == "promoted_to_candidate"),
            "promoted_to_active_count": sum(1 for item in promotion_results if item["governance_action"] == "promoted_to_active"),
            "candidate_promotion_count": sum(1 for item in promotion_results if item["governance_action"] == "promoted_to_candidate"),
            "deferred_active_promotion_count": sum(1 for item in promotion_results if item["governance_action"] == "promotion_deferred"),
            "candidate_retained_count": sum(1 for item in promotion_results if item["governance_action"] == "candidate_retained"),
            "new_thesis_count": sum(
                1 for item in promotion_results
                if item.get("governance_action") in {"promoted_to_candidate", "update_existing_task"}
            ),
            "factor_gate_pass_rate": _lane_pass_rate(full_validation_records, "hypothesis_factor"),
            "portfolio_survival_rate": _lane_pass_rate(full_validation_records, "hypothesis_portfolio"),
            "model_overlay_survival_rate": _lane_pass_rate(full_validation_records, "hypothesis_model"),
            "quarantined_proposal_count": sum(1 for item in full_validation_records if item["experiment_status"] == "quarantined"),
            "registry_growth": {
                "model_family_count": len((registry_snapshot.get("model_families") or {}).get("entries", [])),
                "feature_family_count": len((registry_snapshot.get("feature_families") or {}).get("entries", [])),
            },
            "family_win_loss_table": _family_win_loss_table(full_validation_records),
            "auto_bridged_snapshot_count": int(auto_bridge_summary.get("auto_bridged_snapshot_count", 0) or 0),
            "auto_bridged_agent_snapshot_count": int(auto_bridge_summary.get("auto_bridged_agent_snapshot_count", 0) or 0),
            "downstream_acceptance_count": int(auto_bridge_summary.get("published_snapshot_count", 0) or 0),
            "auto_bridge_summary_path": auto_bridge_summary.get("bridge_summary_path"),
            "auto_bridge_status": auto_bridge_summary.get("status"),
            "openai_usage": dict(agent_summary.get("usage") or {}),
            "evaluations": promotion_results,
            "lifecycle_counts": current_lifecycle_counts,
            "active_strategy_ids": sorted(str(entry["strategy_id"]) for entry in final_library.get("entries", []) if str(entry.get("lifecycle")) == "active"),
            "watch_strategy_ids": sorted(str(entry["strategy_id"]) for entry in final_library.get("entries", []) if str(entry.get("lifecycle")) == "watch"),
            "candidate_strategy_ids": sorted(str(entry["strategy_id"]) for entry in final_library.get("entries", []) if str(entry.get("lifecycle")) == "candidate"),
            "discovery_strategy_ids": sorted(str(entry["strategy_id"]) for entry in final_library.get("entries", []) if str(entry.get("lifecycle")) == "discovery"),
            "discovery_recipe_catalog_path": str(recipe_catalog_path),
            "discovery_screen_summary_path": str(screen_summary_path),
            "discovery_shortlist_path": str(shortlist_path),
            "input_watermarks": {
                "quant_universe_generated_at_utc": universe_input.generated_at_utc,
            },
            "upstream_versions": {
                "weekly_discovery_screen_budget": WEEKLY_DISCOVERY_SCREEN_BUDGET,
                "weekly_discovery_full_validation_budget": WEEKLY_DISCOVERY_FULL_VALIDATION_BUDGET,
                "weekly_candidate_promotion_cap": WEEKLY_CANDIDATE_PROMOTION_CAP,
                "weekly_promotion_to_active_cap": WEEKLY_PROMOTION_TO_ACTIVE_CAP,
            },
        },
        evidence_family="quant_discovery_weekly_cycle",
        contract_version="quant_discovery_weekly_cycle.v1",
        repo_root=ROOT,
        require_source_commit_sha=True,
    )
    summary_path = review_root / "discovery_governance_summary.json"
    summary_md_path = review_root / "discovery_governance_summary.md"
    discovery_md_path = review_root / "discovery_summary.md"
    legacy_summary_path = review_root / "weekly_governance_summary.json"
    legacy_summary_md_path = review_root / "weekly_governance_summary.md"
    write_json(summary_path, summary)
    markdown = _discovery_markdown(summary, promotion_results)
    summary_md_path.write_text(markdown + "\n", encoding="utf-8")
    discovery_md_path.write_text(markdown + "\n", encoding="utf-8")
    write_json(legacy_summary_path, summary)
    legacy_summary_md_path.write_text(markdown + "\n", encoding="utf-8")
    summary["discovery_governance_summary_path"] = str(summary_path)
    summary["discovery_governance_summary_md_path"] = str(summary_md_path)
    summary["weekly_governance_summary_path"] = str(legacy_summary_path)
    summary["weekly_governance_summary_md_path"] = str(legacy_summary_md_path)
    summary["discovery_summary_md_path"] = str(discovery_md_path)
    return summary


def _bucket_counts(recipes: list[dict[str, Any]]) -> dict[str, int]:
    counts = {bucket: 0 for bucket in DISCOVERY_BUCKETS}
    for recipe in recipes:
        bucket = str(recipe.get("bucket") or recipe.get("proposal_bucket"))
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _family_win_loss_table(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_family: dict[str, dict[str, Any]] = {}
    for record in records:
        family_id = str(record.get("family_id") or record.get("recipe", {}).get("family_id") or record.get("recipe", {}).get("model_family") or "unknown")
        payload = by_family.setdefault(
            family_id,
            {
                "family_id": family_id,
                "pass_count": 0,
                "fail_count": 0,
                "quarantine_count": 0,
                "proposal_origin_mix": {"agent": 0, "heuristic": 0},
            },
        )
        origin = str(record.get("proposal_origin") or record.get("recipe", {}).get("proposal_origin") or "heuristic")
        payload["proposal_origin_mix"][origin] = payload["proposal_origin_mix"].get(origin, 0) + 1
        status = str(record.get("experiment_status") or "")
        if status == "quarantined":
            payload["quarantine_count"] += 1
        elif is_pass_experiment_status(status):
            payload["pass_count"] += 1
        else:
            payload["fail_count"] += 1
    return [by_family[key] for key in sorted(by_family)]


def _discovery_markdown(summary: dict[str, Any], promotion_results: list[dict[str, Any]]) -> str:
    lines = [
        "# Weekly Discovery Summary",
        "",
        f"- Week of: `{summary.get('week_of')}`",
        f"- Compiler backend: `{summary.get('compiler_backend')}`",
        f"- Discovery recipes: `{summary.get('discovery_recipe_count')}`",
        f"- Full validation count: `{summary.get('full_validation_count')}`",
        f"- Shortlist count: `{summary.get('shortlist_count')}`",
        f"- New thesis count: `{summary.get('new_thesis_count')}`",
        f"- Factor gate pass rate: `{summary.get('factor_gate_pass_rate')}`",
        f"- Portfolio survival rate: `{summary.get('portfolio_survival_rate')}`",
        f"- Model overlay survival rate: `{summary.get('model_overlay_survival_rate')}`",
        f"- Candidate promotions: `{summary.get('candidate_promotion_count')}`",
        f"- Promoted to active: `{summary.get('promoted_to_active_count')}`",
        f"- Deferred active promotions: `{summary.get('deferred_active_promotion_count')}`",
        "",
        "## Buckets",
    ]
    for bucket, count in sorted(_bucket_counts(summary.get("evaluations", [])).items(), key=lambda item: item[0]):
        lines.append(f"- `{bucket}`: `{count}`")
    lines.extend(["", "## Shortlist"])
    if not promotion_results:
        lines.append("- No shortlist entries cleared the weekly selection stage.")
    for item in promotion_results:
        lines.append(
            "- "
            f"`{item.get('strategy_id')}` "
            f"bucket=`{item.get('bucket')}` "
            f"status=`{item.get('experiment_status')}` "
            f"action=`{item.get('governance_action')}`"
        )
    return "\n".join(lines)
