from __future__ import annotations

from pathlib import Path
from typing import Any

from .alpha_manifest import load_daily_alpha_manifest, manifest_entries_by_experiment_id
from .contracts import read_json, resolve_portable_path
from .governance import load_strategy_library
from . import promotion as promotion_contracts
from .promotion import (
    _stable_metrics_snapshot,
    alpha_experiment_status,
    evaluate_promotion_decision_for_export,
    evaluate_quant_publication_assessment,
    load_publication_contract,
    sha256_json,
)


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_FRESHNESS_CONTRACT_PATH = ROOT / "config" / "agent_layer_governance" / "evidence_freshness_contract.json"
REQUIRED_SUMMARY_FIELDS = (
    "produced_at_utc",
    "source_commit_sha",
    "artifacts_root",
    "as_of",
    "blocked_experiment_count",
    "daily_alpha_manifest_path",
    "eligible_experiment_count",
    "export_root",
    "exported_snapshot_count",
    "exports",
    "published_snapshot_count",
    "queue",
    "queue_root",
    "staged_only_snapshot_count",
    "suppressed_exports",
)
REQUIRED_SNAPSHOT_FIELDS = (
    "backend_mode",
    "cycle_date",
    "cycle_id",
    "evidence",
    "executable_signal",
    "family_id",
    "next_step",
    "observation",
    "proposal_origin",
    "publication_status",
    "published_via",
    "published_to_intake",
    "quality_summary",
    "queue",
    "registry_snapshot_id",
    "risk",
    "search_action",
    "source",
    "subject",
    "validation",
)
BANNED_TRUTHFULNESS_PHRASES = (
    "positive out-of-sample performance",
    "quantitatively validated candidate",
    "worth feeding back into the thesis workflow",
)


def find_bridge_summary_paths(*, artifacts_root: Path) -> list[Path]:
    bridge_root = artifacts_root / "bridge_exports"
    if not bridge_root.exists():
        return []
    return sorted(path.resolve() for path in bridge_root.glob("*/bridge_summary.json"))


def verify_bridge_summary_contract(
    *,
    summary_path: Path,
    artifacts_root: Path | None = None,
    now_utc: str | None = None,
) -> list[str]:
    path = summary_path.expanduser().resolve()
    summary = read_json(path)
    blockers: list[str] = []
    for field_name in REQUIRED_SUMMARY_FIELDS:
        if field_name not in summary:
            blockers.append(f"bridge summary is missing required field {field_name}")
    if blockers:
        return blockers
    if not str(summary.get("source_commit_sha") or "").strip():
        blockers.append("bridge summary source_commit_sha must be non-empty")
    if blockers:
        return blockers

    resolved_artifacts_root = (
        artifacts_root.expanduser().resolve()
        if artifacts_root is not None
        else resolve_portable_path(str(summary.get("artifacts_root") or path.parents[2]), repo_root=ROOT)
    )
    export_root = resolve_portable_path(str(summary.get("export_root") or path.parent), repo_root=ROOT)
    queue_root = resolve_portable_path(str(summary.get("queue_root") or ""), repo_root=ROOT)
    queue_name = str(summary.get("queue") or "").strip()
    as_of = str(summary.get("as_of") or "").strip()
    if export_root != path.parent:
        blockers.append(f"bridge summary export_root mismatch: expected {path.parent} got {export_root}")

    exports = _dict_list(summary.get("exports"))
    suppressed_exports = _dict_list(summary.get("suppressed_exports"))
    blocked_exports = _dict_list(summary.get("blocked_exports"))
    all_entries = exports + suppressed_exports

    if _as_int(summary.get("published_snapshot_count")) != len(exports):
        blockers.append(
            f"bridge summary published_snapshot_count={summary.get('published_snapshot_count')} does not match exports={len(exports)}"
        )
    if _as_int(summary.get("staged_only_snapshot_count")) != len(suppressed_exports):
        blockers.append(
            "bridge summary staged_only_snapshot_count="
            f"{summary.get('staged_only_snapshot_count')} does not match suppressed_exports={len(suppressed_exports)}"
        )
    if _as_int(summary.get("exported_snapshot_count")) != len(all_entries):
        blockers.append(
            f"bridge summary exported_snapshot_count={summary.get('exported_snapshot_count')} does not match referenced snapshots={len(all_entries)}"
        )
    if _as_int(summary.get("blocked_experiment_count")) != len(blocked_exports):
        blockers.append(
            "bridge summary blocked_experiment_count="
            f"{summary.get('blocked_experiment_count')} does not match blocked_exports={len(blocked_exports)}"
        )
    if _as_int(summary.get("eligible_experiment_count")) != len(all_entries):
        blockers.append(
            f"bridge summary eligible_experiment_count={summary.get('eligible_experiment_count')} does not match eligible entries={len(all_entries)}"
        )

    publication_contract = load_publication_contract()
    archive_only_stages = {str(item) for item in publication_contract.get("archive_only_stages", [])}
    current_stage = promotion_contracts.current_project_stage()
    if current_stage in archive_only_stages and exports and any(
        str(entry.get("publication_status") or "") != "publishable_to_incoming_auto"
        for entry in exports
    ):
        blockers.append(
            f"current_stage={current_stage} is archive-only but bridge summary declares published exports"
        )
    manifest = load_daily_alpha_manifest(artifacts_root=resolved_artifacts_root, as_of=as_of)
    manifest_path = resolve_portable_path(str(summary.get("daily_alpha_manifest_path") or ""), repo_root=ROOT)
    if manifest_path != Path(str(manifest["path"])).resolve():
        blockers.append(
            f"bridge summary daily_alpha_manifest_path mismatch: expected {manifest['path']} got {summary.get('daily_alpha_manifest_path')}"
        )
    manifest_entry_by_id = manifest_entries_by_experiment_id(manifest)

    strategy_library = load_strategy_library(artifacts_root=resolved_artifacts_root)
    strategy_entries = {
        str(entry.get("strategy_id")): {
            **entry,
            "strategy_library_path": str(strategy_library["path"]),
        }
        for entry in strategy_library.get("entries", [])
        if isinstance(entry, dict) and str(entry.get("strategy_id", "")).strip()
    }

    expected_archive_paths: set[Path] = set()
    expected_queue_paths: set[Path] = set()
    for entry in all_entries:
        blockers.extend(
            _verify_bridge_entry(
                entry=entry,
                resolved_artifacts_root=resolved_artifacts_root,
                manifest_entry_by_id=manifest_entry_by_id,
                strategy_entries=strategy_entries,
                expected_archive_paths=expected_archive_paths,
                expected_queue_paths=expected_queue_paths,
                now_utc=now_utc,
            )
        )
    for entry in blocked_exports:
        experiment_id = str(entry.get("experiment_id") or "").strip()
        if not experiment_id:
            blockers.append("blocked bridge entry is missing experiment_id")
            continue
        manifest_entry = manifest_entry_by_id.get(experiment_id)
        if manifest_entry is None:
            blockers.append(f"blocked bridge entry {experiment_id} is not present in daily alpha manifest")
            continue
        alpha_card_path_raw = str(entry.get("alpha_card_path") or "").strip()
        if alpha_card_path_raw:
            alpha_card_path = resolve_portable_path(alpha_card_path_raw, repo_root=ROOT)
            manifest_alpha_card_path = resolve_portable_path(str(manifest_entry.get("alpha_card_path") or ""), repo_root=ROOT)
            if alpha_card_path != manifest_alpha_card_path:
                blockers.append(f"blocked bridge entry {experiment_id} alpha_card_path does not match daily alpha manifest")

    actual_archive_paths = {item.resolve() for item in export_root.glob("*.snapshot.json")}
    unexpected_archive_paths = sorted(str(item) for item in actual_archive_paths - expected_archive_paths)
    if unexpected_archive_paths:
        blockers.append(
            "bridge export root contains snapshot files not referenced by bridge_summary: "
            + ", ".join(unexpected_archive_paths)
        )

    if queue_root.exists():
        actual_queue_paths: set[Path] = set()
        for candidate in queue_root.glob("*.snapshot.json"):
            try:
                payload = read_json(candidate)
            except Exception:
                continue
            if str(payload.get("source") or "").strip() == queue_name and str(payload.get("cycle_date") or "").strip() == as_of:
                actual_queue_paths.add(candidate.resolve())
        unexpected_queue_paths = sorted(str(item) for item in actual_queue_paths - expected_queue_paths)
        if unexpected_queue_paths:
            blockers.append(
                "queue root contains snapshot files for this as_of not referenced by bridge_summary: "
                + ", ".join(unexpected_queue_paths)
            )

    return blockers


def _verify_bridge_entry(
    *,
    entry: dict[str, Any],
    resolved_artifacts_root: Path,
    manifest_entry_by_id: dict[str, dict[str, Any]],
    strategy_entries: dict[str, dict[str, Any]],
    expected_archive_paths: set[Path],
    expected_queue_paths: set[Path],
    now_utc: str | None,
) -> list[str]:
    blockers: list[str] = []
    experiment_id = str(entry.get("experiment_id") or "").strip()
    if not experiment_id:
        return ["bridge summary entry is missing experiment_id"]
    archive_path_raw = str(entry.get("archive_path") or "").strip()
    if not archive_path_raw:
        return [f"bridge summary entry for {experiment_id} is missing archive_path"]
    archive_path = resolve_portable_path(archive_path_raw, repo_root=ROOT)
    expected_archive_paths.add(archive_path)
    if not archive_path.exists():
        return [f"bridge summary entry for {experiment_id} references missing archive_path {archive_path}"]

    snapshot = read_json(archive_path)
    missing_snapshot_fields = [field_name for field_name in REQUIRED_SNAPSHOT_FIELDS if field_name not in snapshot]
    if missing_snapshot_fields:
        blockers.append(
            f"snapshot {archive_path.name} is missing required fields: {', '.join(missing_snapshot_fields)}"
        )
    for banned_phrase in BANNED_TRUTHFULNESS_PHRASES:
        if banned_phrase in str(snapshot.get("evidence") or "") or banned_phrase in str(snapshot.get("observation") or ""):
            blockers.append(f"snapshot {archive_path.name} still contains banned phrase '{banned_phrase}'")

    if str(snapshot.get("cycle_id") or "").strip() != str(entry.get("cycle_id") or "").strip():
        blockers.append(f"snapshot {archive_path.name} cycle_id does not match bridge_summary")
    if str(snapshot.get("subject") or "").strip() != str(entry.get("subject") or "").strip():
        blockers.append(f"snapshot {archive_path.name} subject does not match bridge_summary")
    if str(snapshot.get("queue") or "").strip() != str(entry.get("queue") or "").strip():
        blockers.append(f"snapshot {archive_path.name} queue does not match bridge_summary")
    if str(snapshot.get("source") or "").strip() != str(entry.get("source") or "").strip():
        blockers.append(f"snapshot {archive_path.name} source does not match bridge_summary")
    if str(snapshot.get("publication_status") or "").strip() != str(entry.get("publication_status") or "").strip():
        blockers.append(f"snapshot {archive_path.name} publication_status does not match bridge_summary")
    if str(snapshot.get("validation") or "").strip() != str(entry.get("validation") or "").strip():
        blockers.append(f"snapshot {archive_path.name} validation does not match bridge_summary")

    published_to_intake = bool(entry.get("published_to_intake"))
    if bool(snapshot.get("published_to_intake")) != published_to_intake:
        blockers.append(f"snapshot {archive_path.name} published_to_intake does not match bridge_summary")
    queue_path_raw = entry.get("queue_path")
    if published_to_intake:
        if not queue_path_raw:
            blockers.append(f"published bridge entry {experiment_id} is missing queue_path")
        else:
            queue_path = resolve_portable_path(str(queue_path_raw), repo_root=ROOT)
            expected_queue_paths.add(queue_path)
            if not queue_path.exists():
                blockers.append(f"published bridge entry {experiment_id} references missing queue_path {queue_path}")
            else:
                queued_snapshot = read_json(queue_path)
                if sha256_json(queued_snapshot) != sha256_json(snapshot):
                    blockers.append(f"published bridge entry {experiment_id} queue snapshot differs from archived snapshot")
    elif queue_path_raw not in (None, ""):
        blockers.append(f"suppressed bridge entry {experiment_id} must not carry queue_path")

    manifest_entry = manifest_entry_by_id.get(experiment_id)
    if manifest_entry is None:
        blockers.append(f"bridge entry {experiment_id} is not present in daily alpha manifest")
        return blockers
    alpha_card_path = resolve_portable_path(str(manifest_entry.get("alpha_card_path") or ""), repo_root=ROOT)
    if not alpha_card_path.exists():
        blockers.append(f"bridge entry {experiment_id} is missing alpha_card at {alpha_card_path}")
        return blockers
    alpha_card = read_json(alpha_card_path)
    strategy_id = str(alpha_card.get("strategy_id") or "").strip()
    if strategy_id != str(manifest_entry.get("strategy_id") or "").strip():
        blockers.append(f"bridge entry {experiment_id} strategy_id does not match daily alpha manifest")
    strategy_entry = strategy_entries.get(strategy_id)
    assessment = evaluate_quant_publication_assessment(
        alpha_card=alpha_card,
        strategy_entry=strategy_entry,
        artifacts_root=resolved_artifacts_root,
    )
    if alpha_experiment_status(alpha_card) != "pass":
        blockers.append(f"bridge entry {experiment_id} points at alpha_card with experiment_status={alpha_experiment_status(alpha_card)}")
    if str(snapshot.get("backend_mode") or "").strip() != str(assessment.get("backend_mode") or "").strip():
        blockers.append(f"snapshot {archive_path.name} backend_mode is stale relative to current promotion assessment")
    if str(snapshot.get("publication_status") or "").strip() != str(assessment.get("publication_status") or "").strip():
        blockers.append(f"snapshot {archive_path.name} publication_status is stale relative to current promotion assessment")
    if str(snapshot.get("validation") or "").strip() != str(assessment.get("validation") or "").strip():
        blockers.append(f"snapshot {archive_path.name} validation is stale relative to current promotion assessment")
    snapshot_quality_summary = dict(snapshot.get("quality_summary") or {})
    snapshot_quality_summary["metrics_snapshot"] = _stable_metrics_snapshot(
        snapshot_quality_summary.get("metrics_snapshot")
    )
    if sha256_json(snapshot_quality_summary) != sha256_json(
        {
            "quality_gate_passed": assessment["quality_gate_passed"],
            "quality_blockers": assessment["quality_blockers"],
            "metrics_snapshot": _stable_metrics_snapshot(assessment["metrics_snapshot"]),
        }
    ):
        blockers.append(f"snapshot {archive_path.name} quality_summary is stale relative to current promotion assessment")

    if published_to_intake:
        ok, _, decision_blockers = evaluate_promotion_decision_for_export(
            artifacts_root=resolved_artifacts_root,
            as_of=str(alpha_card.get("as_of") or snapshot.get("cycle_date") or ""),
            alpha_card_path=alpha_card_path,
            alpha_card=alpha_card,
            strategy_entry=strategy_entry,
            evidence_freshness_contract_path=EVIDENCE_FRESHNESS_CONTRACT_PATH,
            now_utc=now_utc,
        )
        if not ok:
            blockers.extend(
                f"published bridge entry {experiment_id} violates promotion decision contract: {blocker}"
                for blocker in decision_blockers
            )
    return blockers


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
