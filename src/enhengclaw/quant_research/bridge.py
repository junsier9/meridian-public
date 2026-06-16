from __future__ import annotations

from pathlib import Path
from typing import Any

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.utils.research_workbench_queues import (
    LEGACY_QUEUE,
    QUANT_QUEUE,
    all_pending_snapshot_roots,
    incoming_queue_root,
)

from .alpha_manifest import ignored_legacy_alpha_cards, load_daily_alpha_manifest
from .contracts import (
    pit_universe_artifact_metadata,
    portable_path,
    read_json,
    resolve_portable_path,
    slugify,
    utc_now,
    write_json,
)
from .legacy_surface import raise_legacy_surface_frozen
from .governance import load_strategy_library
from .lab import QUANT_ARTIFACTS_ROOT, WORKBENCH_ROOT
from .market_data import build_history_bundle_for_subject, load_workbench_thesis_profiles
from .promotion import alpha_experiment_status, evaluate_promotion_decision_for_export


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_FRESHNESS_CONTRACT_PATH = ROOT / "config" / "agent_layer_governance" / "evidence_freshness_contract.json"


SUPPORTED_EXPORT_QUEUES = (QUANT_QUEUE, LEGACY_QUEUE)
DEFAULT_EXPORT_QUEUE = QUANT_QUEUE
DEFAULT_SINGLE_ASSET_EXPORT_CAP = 2
DEFAULT_CROSS_SECTIONAL_GROUP_CAP = 1
DEFAULT_AGENT_EXPORT_CAP = 3
PUBLISHABLE_STATUSES = {"publishable_to_incoming", "publishable_to_incoming_auto"}


def export_passed_alphas_to_workbench(
    *,
    as_of: str,
    artifacts_root: Path | None = None,
    workbench_root: Path | None = None,
    ohlcv_external_root: Path | None = None,
    spot_ohlcv_external_root: Path | None = None,
    queue: str = DEFAULT_EXPORT_QUEUE,
    daily_export_cap: int | None = None,
    single_asset_export_cap: int = DEFAULT_SINGLE_ASSET_EXPORT_CAP,
    cross_sectional_group_cap: int = DEFAULT_CROSS_SECTIONAL_GROUP_CAP,
    agent_export_cap: int = DEFAULT_AGENT_EXPORT_CAP,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    raise_legacy_surface_frozen(
        operation="bridge_export",
        as_of=as_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
    )

    eligible_cards = []
    blocked_cards: list[dict[str, Any]] = []
    for manifest_entry in daily_manifest.get("entries", []):
        alpha_card_path = resolve_portable_path(str(manifest_entry["alpha_card_path"]), repo_root=ROOT)
        alpha_card = read_json(alpha_card_path)
        if str(alpha_card.get("as_of")) != as_of or alpha_experiment_status(alpha_card) != "pass":
            continue
        strategy_entry = strategy_entries.get(str(alpha_card.get("strategy_id", "")))
        promotion_ok, promotion_decision, promotion_blockers = evaluate_promotion_decision_for_export(
            artifacts_root=resolved_artifacts_root,
            as_of=as_of,
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=strategy_entry,
            evidence_freshness_contract_path=EVIDENCE_FRESHNESS_CONTRACT_PATH,
        )
        if not promotion_ok:
            blocked_cards.append(
                {
                    "experiment_id": alpha_card.get("experiment_id"),
                    "strategy_id": alpha_card.get("strategy_id"),
                    "alpha_card_path": portable_path(alpha_card_path, repo_root=ROOT),
                    "promotion_decision_path": (
                        None
                        if promotion_decision is None or not str(promotion_decision.get("promotion_decision_path") or "").strip()
                        else portable_path(Path(str(promotion_decision["promotion_decision_path"])), repo_root=ROOT)
                    ),
                    "blockers": promotion_blockers,
                }
            )
            continue
        eligible_cards.append((float(_export_score(alpha_card)), alpha_card, promotion_decision))
    eligible_cards.sort(key=lambda item: (item[0], str(item[1].get("experiment_id", ""))), reverse=True)

    published_snapshot_count = 0
    published_single_asset_count = 0
    published_cross_sectional_group_count = 0
    published_agent_count = 0
    exports: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []

    for score, alpha_card, promotion_decision in eligible_cards:
        export_priority = float(score)
        publication_status = str(promotion_decision.get("publication_status") or "")
        publishable_to_incoming = publication_status in PUBLISHABLE_STATUSES
        proposal_origin = str(
            promotion_decision.get("proposal_origin")
            or alpha_card.get("proposal_origin")
            or "heuristic"
        )
        agent_cap_ok = proposal_origin != "agent" or published_agent_count < agent_export_cap
        published_for_card = publishable_to_incoming and agent_cap_ok and (daily_export_cap is None or published_snapshot_count < daily_export_cap)
        if str(alpha_card.get("shape")) == "single_asset":
            snapshot = _build_single_asset_snapshot(
                alpha_card=alpha_card,
                promotion_decision=promotion_decision,
                thesis_profiles=thesis_profiles,
                ohlcv_external_root=ohlcv_external_root,
                spot_ohlcv_external_root=spot_ohlcv_external_root,
                workbench_root=resolved_workbench_root,
                queue_root=queue_root,
                queue=queue,
                export_priority=export_priority,
            )
            if snapshot is None:
                continue
            should_publish = published_for_card and published_single_asset_count < single_asset_export_cap
            archive_path, queue_path = _write_bridge_snapshot(
                snapshot=snapshot,
                queue_root=queue_root,
                export_root=export_root,
                published_to_intake=should_publish,
            )
            entry = _export_entry(
                alpha_card=alpha_card,
                snapshot=snapshot,
                archive_path=archive_path,
                queue_path=queue_path,
                published_to_intake=should_publish,
            )
            if should_publish:
                published_snapshot_count += 1
                published_single_asset_count += 1
                if proposal_origin == "agent":
                    published_agent_count += 1
                exports.append(entry)
            else:
                suppressed.append(entry)
        elif str(alpha_card.get("shape")) == "cross_sectional":
            snapshots = _build_cross_sectional_snapshots(
                alpha_card=alpha_card,
                promotion_decision=promotion_decision,
                thesis_profiles=thesis_profiles,
                ohlcv_external_root=ohlcv_external_root,
                spot_ohlcv_external_root=spot_ohlcv_external_root,
                workbench_root=resolved_workbench_root,
                queue_root=queue_root,
                queue=queue,
                export_priority=export_priority,
            )
            if not snapshots:
                continue
            should_publish_group = published_for_card and published_cross_sectional_group_count < cross_sectional_group_cap
            group_entries: list[dict[str, Any]] = []
            for snapshot in snapshots:
                archive_path, queue_path = _write_bridge_snapshot(
                    snapshot=snapshot,
                    queue_root=queue_root,
                    export_root=export_root,
                    published_to_intake=should_publish_group,
                )
                group_entries.append(
                    _export_entry(
                        alpha_card=alpha_card,
                        snapshot=snapshot,
                        archive_path=archive_path,
                        queue_path=queue_path,
                        published_to_intake=should_publish_group,
                    )
                )
            if should_publish_group:
                published_snapshot_count += len(group_entries)
                published_cross_sectional_group_count += 1
                if proposal_origin == "agent":
                    published_agent_count += len(group_entries)
                exports.extend(group_entries)
            else:
                suppressed.extend(group_entries)

    summary = with_evidence_metadata(
        {
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "artifacts_root": portable_path(resolved_artifacts_root, repo_root=ROOT),
        "workbench_root": portable_path(resolved_workbench_root, repo_root=ROOT),
        "queue": queue,
        "queue_root": portable_path(queue_root, repo_root=ROOT),
        "export_root": portable_path(export_root, repo_root=ROOT),
        "daily_alpha_manifest_path": portable_path(Path(str(daily_manifest["path"])), repo_root=ROOT),
        "single_asset_export_cap": single_asset_export_cap,
        "cross_sectional_group_cap": cross_sectional_group_cap,
        "agent_export_cap": agent_export_cap,
        "daily_export_cap": daily_export_cap,
        "eligible_experiment_count": len(exports) + len(suppressed),
        "blocked_experiment_count": len(blocked_cards),
        "published_snapshot_count": len(exports),
        "staged_only_snapshot_count": len(suppressed),
        "exported_snapshot_count": len(exports) + len(suppressed),
        "suppressed_snapshot_count": len(suppressed),
        "blocked_exports": blocked_cards,
        "exports": exports,
        "suppressed_exports": suppressed,
        "ignored_legacy_alpha_cards": ignored_legacy_alpha_cards(
            artifacts_root=resolved_artifacts_root,
            manifest=daily_manifest,
        ),
        "status": "success",
        "success": True,
        "input_watermarks": {
            "strategy_library_generated_at_utc": strategy_library.get("generated_at_utc"),
        },
        "upstream_versions": {
            "single_asset_export_cap": single_asset_export_cap,
            "cross_sectional_group_cap": cross_sectional_group_cap,
            "agent_export_cap": agent_export_cap,
        },
        },
        evidence_family="quant_bridge_export",
        contract_version="quant_bridge_export.v1",
        repo_root=ROOT,
        source_commit_sha=source_commit_sha,
        require_source_commit_sha=True,
    )
    summary_path = export_root / "bridge_summary.json"
    write_json(summary_path, summary)
    from .bridge_contracts import verify_bridge_summary_contract

    blockers = verify_bridge_summary_contract(
        summary_path=summary_path,
        artifacts_root=resolved_artifacts_root,
    )
    if blockers:
        raise RuntimeError("bridge summary contract violations: " + " | ".join(blockers))
    summary["bridge_summary_path"] = str(summary_path)
    return summary


def _build_single_asset_snapshot(
    *,
    alpha_card: dict[str, Any],
    promotion_decision: dict[str, Any],
    thesis_profiles: list[dict[str, Any]],
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    workbench_root: Path,
    queue_root: Path,
    queue: str,
    export_priority: float,
) -> dict[str, Any] | None:
    subject = str(alpha_card.get("subject", "")).strip().upper()
    if not subject:
        return None
    strategy_profile = str(alpha_card.get("strategy_profile", "balanced")).strip()
    asset_bucket = _liquidity_bucket_value(alpha_card, default="mid_liquidity")
    object_id = _resolve_object_id(
        subject=subject,
        strategy_profile=strategy_profile,
        liquidity_bucket=asset_bucket,
        thesis_profiles=thesis_profiles,
        default_suffix="quant",
        as_of=str(alpha_card.get("as_of")),
    )
    cycle_id = _unique_cycle_id(
        workbench_root=workbench_root,
        object_id=object_id,
        queue_root=queue_root,
        base_cycle_id=f"{object_id}-quant-{slugify(str(alpha_card.get('experiment_id')))}",
    )
    market_symbols = alpha_card.get("market_symbols") or {"spot_symbol": f"{subject}USDT", "usdm_symbol": None}
    history_bundle = build_history_bundle_for_subject(
        subject=subject,
        scope="spot+perp" if market_symbols.get("usdm_symbol") else "spot",
        market_symbols=market_symbols,
        ohlcv_external_root=ohlcv_external_root,
        spot_ohlcv_external_root=spot_ohlcv_external_root,
    )
    truth = _truthfulness_fields(alpha_card=alpha_card, promotion_decision=promotion_decision)
    return {
        "cycle_id": cycle_id,
        "cycle_date": str(alpha_card.get("as_of")),
        "object_id": object_id,
        "subject": subject,
        "scope": "spot+perp" if market_symbols.get("usdm_symbol") else "spot",
        "strategy_profile": strategy_profile,
        "liquidity_bucket": asset_bucket,
        "market_symbols": market_symbols,
        "history_coverage": history_bundle["history_coverage"],
        "strategy_id": alpha_card.get("strategy_id"),
        "spec_hash": alpha_card.get("spec_hash"),
        "proposal_origin": alpha_card.get("proposal_origin", promotion_decision.get("proposal_origin", "heuristic")),
        "registry_snapshot_id": alpha_card.get("registry_snapshot_id"),
        "search_action": alpha_card.get("search_action", "parameter_tune"),
        "family_id": alpha_card.get("family_id", alpha_card.get("model_family")),
        **pit_universe_artifact_metadata(alpha_card),
        "published_via": truth["published_via"],
        "executable_signal": False,
        "source": QUANT_QUEUE,
        "export_priority": export_priority,
        "published_to_intake": False,
        "queue": queue,
        "backend_mode": truth["backend_mode"],
        "publication_status": truth["publication_status"],
        "validation": truth["validation"],
        "quality_summary": truth["quality_summary"],
        "observation": truth["observation"],
        "evidence": truth["evidence"],
        "risk": "Do not treat this artifact as executable signal without a fresh, stage-appropriate promotion decision and renewed quant validation.",
        "next_step": truth["next_step"],
    }


def _build_cross_sectional_snapshots(
    *,
    alpha_card: dict[str, Any],
    promotion_decision: dict[str, Any],
    thesis_profiles: list[dict[str, Any]],
    ohlcv_external_root: Path | None,
    spot_ohlcv_external_root: Path | None,
    workbench_root: Path,
    queue_root: Path,
    queue: str,
    export_priority: float,
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    truth = _truthfulness_fields(alpha_card=alpha_card, promotion_decision=promotion_decision)
    for candidate in list(alpha_card.get("top_long_candidates", []))[:3]:
        subject = str(candidate.get("subject", "")).strip().upper()
        if not subject:
            continue
        strategy_profile = str(alpha_card.get("strategy_profile", "balanced")).strip()
        asset_bucket = _liquidity_bucket_value(candidate, default="mid_liquidity")
        object_id = _resolve_object_id(
            subject=subject,
            strategy_profile=strategy_profile,
            liquidity_bucket=asset_bucket,
            thesis_profiles=thesis_profiles,
            default_suffix="quant",
            as_of=str(alpha_card.get("as_of")),
        )
        cycle_id = _unique_cycle_id(
            workbench_root=workbench_root,
            object_id=object_id,
            queue_root=queue_root,
            base_cycle_id=f"{object_id}-quant-{slugify(str(alpha_card.get('experiment_id')))}",
        )
        market_symbols = {"spot_symbol": f"{subject}USDT", "usdm_symbol": f"{subject}USDT"}
        history_bundle = build_history_bundle_for_subject(
            subject=subject,
            scope="spot+perp",
            market_symbols=market_symbols,
            ohlcv_external_root=ohlcv_external_root,
            spot_ohlcv_external_root=spot_ohlcv_external_root,
        )
        snapshots.append(
            {
                "cycle_id": cycle_id,
                "cycle_date": str(alpha_card.get("as_of")),
                "object_id": object_id,
                "subject": subject,
                "scope": "spot+perp",
                "strategy_profile": strategy_profile,
                "liquidity_bucket": asset_bucket,
                "market_symbols": market_symbols,
                "history_coverage": history_bundle["history_coverage"],
                "strategy_id": alpha_card.get("strategy_id"),
                "spec_hash": alpha_card.get("spec_hash"),
                "proposal_origin": alpha_card.get("proposal_origin", promotion_decision.get("proposal_origin", "heuristic")),
                "registry_snapshot_id": alpha_card.get("registry_snapshot_id"),
                "search_action": alpha_card.get("search_action", "parameter_tune"),
                "family_id": alpha_card.get("family_id", alpha_card.get("model_family")),
                **pit_universe_artifact_metadata(alpha_card),
                "published_via": truth["published_via"],
                "executable_signal": False,
                "source": QUANT_QUEUE,
                "export_priority": export_priority,
                "published_to_intake": False,
                "queue": queue,
                "backend_mode": truth["backend_mode"],
                "publication_status": truth["publication_status"],
                "validation": truth["validation"],
                "quality_summary": truth["quality_summary"],
                "observation": (
                    f"{truth['observation']} ranked_subject={subject}; ranked_score={float(candidate.get('score', 0.0)):.3f}; "
                    f"ranked_liquidity_bucket={asset_bucket}."
                ),
                "evidence": truth["evidence"],
                "risk": "Do not treat this artifact as executable signal without a fresh, stage-appropriate promotion decision and renewed cross-sectional validation.",
                "next_step": truth["next_step"],
            }
        )
    return snapshots


def _resolve_object_id(
    *,
    subject: str,
    strategy_profile: str,
    liquidity_bucket: str,
    thesis_profiles: list[dict[str, Any]],
    default_suffix: str,
    as_of: str,
) -> str:
    for thesis in thesis_profiles:
        if (
            str(thesis.get("subject", "")).upper() == subject
            and str(thesis.get("strategy_profile", "")) == strategy_profile
            and _liquidity_bucket_value(thesis) == liquidity_bucket
        ):
            return str(thesis.get("object_id"))
    return f"{slugify(subject)}-{strategy_profile}-{default_suffix}-{as_of.replace('-', '')}"


def _liquidity_bucket_value(payload: dict[str, Any], *, default: str | None = None) -> str:
    return str(
        payload.get("liquidity_bucket")
        or payload.get("asset_bucket")
        or default
        or ""
    ).strip()


def _unique_cycle_id(*, workbench_root: Path, object_id: str, queue_root: Path, base_cycle_id: str) -> str:
    known_queue_roots = {queue_root.resolve()}
    known_queue_roots.update(path.resolve() for path in all_pending_snapshot_roots(workbench_root=workbench_root))
    candidate = base_cycle_id
    suffix = 2
    while (workbench_root / object_id / "cycles" / candidate / "cycle_summary.json").exists() or any(
        (root / f"{candidate}.snapshot.json").exists() for root in known_queue_roots
    ):
        candidate = f"{base_cycle_id}-{suffix}"
        suffix += 1
    return candidate


def _write_bridge_snapshot(
    *,
    snapshot: dict[str, Any],
    queue_root: Path,
    export_root: Path,
    published_to_intake: bool,
) -> tuple[Path, Path | None]:
    archive_path = export_root / f"{snapshot['cycle_id']}.snapshot.json"
    serializable_snapshot = dict(snapshot)
    serializable_snapshot["published_to_intake"] = bool(published_to_intake)
    queue_path: Path | None = None
    if published_to_intake:
        queue_path = queue_root / f"{snapshot['cycle_id']}.snapshot.json"
        write_json(queue_path, serializable_snapshot)
    write_json(archive_path, serializable_snapshot)
    return archive_path, queue_path


def _export_entry(
    *,
    alpha_card: dict[str, Any],
    snapshot: dict[str, Any],
    archive_path: Path,
    queue_path: Path | None,
    published_to_intake: bool,
) -> dict[str, Any]:
    return {
        "experiment_id": alpha_card["experiment_id"],
        "shape": alpha_card.get("shape"),
        "queue": snapshot.get("queue"),
        "subject": snapshot["subject"],
        "object_id": snapshot.get("object_id"),
        "cycle_id": snapshot.get("cycle_id"),
        "source": snapshot.get("source"),
        "export_priority": snapshot.get("export_priority"),
        "proposal_origin": snapshot.get("proposal_origin"),
        "registry_snapshot_id": snapshot.get("registry_snapshot_id"),
        "search_action": snapshot.get("search_action"),
        "family_id": snapshot.get("family_id"),
        "published_via": snapshot.get("published_via"),
        "executable_signal": bool(snapshot.get("executable_signal", False)),
        "publication_status": snapshot.get("publication_status"),
        "validation": snapshot.get("validation"),
        "published_to_intake": bool(published_to_intake),
        "archive_path": portable_path(archive_path, repo_root=ROOT),
        "queue_path": None if queue_path is None else portable_path(queue_path, repo_root=ROOT),
    }


def _export_score(alpha_card: dict[str, Any]) -> float:
    validation_metrics = alpha_card.get("validation_metrics", {})
    test_metrics = alpha_card.get("test_metrics", {})
    walk_forward = alpha_card.get("walk_forward", {})
    return (
        float(validation_metrics.get("net_return", 0.0))
        + float(test_metrics.get("net_return", 0.0))
        + float(test_metrics.get("sharpe", 0.0))
        + float(walk_forward.get("median_oos_sharpe", 0.0))
    )


def _truthfulness_fields(*, alpha_card: dict[str, Any], promotion_decision: dict[str, Any]) -> dict[str, Any]:
    metrics_snapshot = dict(promotion_decision.get("metrics_snapshot") or {})
    validation_metrics = dict(metrics_snapshot.get("validation_metrics") or alpha_card.get("validation_metrics") or {})
    test_metrics = dict(metrics_snapshot.get("test_metrics") or alpha_card.get("test_metrics") or {})
    walk_forward = dict(metrics_snapshot.get("walk_forward") or alpha_card.get("walk_forward") or {})
    backend_mode = str(promotion_decision.get("backend_mode") or alpha_card.get("backend_mode") or "deterministic")
    publication_status = str(promotion_decision.get("publication_status") or alpha_card.get("publication_status") or "archived_only")
    validation = str(promotion_decision.get("validation") or alpha_card.get("validation") or "insufficient_track_record")
    proposal_origin = str(promotion_decision.get("proposal_origin") or alpha_card.get("proposal_origin") or "heuristic")
    published_via = str(promotion_decision.get("published_via") or alpha_card.get("published_via") or "not_published")
    daily_pass_streak = int(metrics_snapshot.get("daily_pass_streak", alpha_card.get("daily_pass_streak", 0)) or 0)
    quality_blockers = [str(item) for item in promotion_decision.get("quality_blockers", [])]
    window_count = int(walk_forward.get("window_count", 0) or 0)
    median_oos_sharpe = float(walk_forward.get("median_oos_sharpe", 0.0) or 0.0)
    test_sharpe = float(test_metrics.get("sharpe", 0.0) or 0.0)
    max_drawdown = float(test_metrics.get("max_drawdown", 0.0) or 0.0)
    current_stage = str(metrics_snapshot.get("current_stage", "unknown"))
    lifecycle = str(metrics_snapshot.get("lifecycle") or alpha_card.get("lifecycle") or "active")
    experiment_status = str(metrics_snapshot.get("experiment_status") or alpha_card.get("experiment_status") or "fail")
    quality_summary = {
        "quality_gate_passed": bool(promotion_decision.get("quality_gate_passed")),
        "quality_blockers": quality_blockers,
        "metrics_snapshot": metrics_snapshot,
    }
    observation = (
        f"stage={current_stage}; backend={backend_mode}; lifecycle={lifecycle}; experiment_status={experiment_status}; "
        f"walk_forward_median_oos_sharpe={median_oos_sharpe:.3f}; window_count={window_count}; "
        f"daily_pass_streak={daily_pass_streak}; test_sharpe={test_sharpe:.3f}; max_drawdown={max_drawdown:.3f}."
    )
    if publication_status not in PUBLISHABLE_STATUSES:
        observation = (
            f"{observation} disposition=research_only_archive; executable_signal=false; "
            "this snapshot remains a research candidate and not a publish-ready thesis."
        )
    elif publication_status == "publishable_to_incoming_auto":
        observation = (
            f"{observation} disposition=research_candidate_auto_bridge; executable_signal=false; "
            "this snapshot entered the research queue through same-day auto-bridge and is still not a trading signal."
        )
    else:
        observation = (
            f"{observation} disposition=human_review_candidate; executable_signal=false until a fresh promotion decision is accepted."
        )
    blocker_text = "none" if not quality_blockers else ", ".join(quality_blockers)
    evidence = (
        f"backend={backend_mode}; publication_status={publication_status}; validation={validation}; "
        f"proposal_origin={proposal_origin}; published_via={published_via}; "
        f"walk_forward_median_oos_sharpe={median_oos_sharpe:.3f}; window_count={window_count}; "
        f"daily_pass_streak={daily_pass_streak}; test_sharpe={test_sharpe:.3f}; max_drawdown={max_drawdown:.3f}; "
        f"quality_blockers={blocker_text}"
    )
    next_step = (
        "Archive this quant snapshot for audit only; treat it as research-only evidence, not an executable thesis or trading signal. "
        "Stage 1 and deterministic outputs must not enter _incoming_quant."
        if publication_status not in PUBLISHABLE_STATUSES
        else (
            "Send this candidate into _incoming_quant for research review with the promotion decision attached; it remains a research thesis candidate only, not an executable trading signal."
            if publication_status == "publishable_to_incoming_auto"
            else "Send this candidate into _incoming_quant for Stage 2+ human review with the promotion decision attached; it is still not executable until that review explicitly promotes it."
        )
    )
    return {
        "backend_mode": backend_mode,
        "publication_status": publication_status,
        "validation": validation,
        "published_via": published_via,
        "quality_summary": quality_summary,
        "observation": observation,
        "evidence": evidence,
        "next_step": next_step,
    }


def _clear_existing_bridge_outputs(*, export_root: Path) -> None:
    for path in export_root.glob("*.snapshot.json"):
        path.unlink()
    summary_path = export_root / "bridge_summary.json"
    if summary_path.exists():
        summary_path.unlink()


def _clear_existing_queue_outputs(*, queue_root: Path, queue: str, as_of: str) -> None:
    for path in queue_root.glob("*.snapshot.json"):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if str(payload.get("source") or "").strip() == queue and str(payload.get("cycle_date") or "").strip() == as_of:
            path.unlink()
