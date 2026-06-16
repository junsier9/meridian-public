from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .alpha_manifest import daily_alpha_manifest_root, load_daily_alpha_manifest, manifest_entries_by_experiment_id
from .contracts import ROOT, portable_path, read_json, resolve_portable_path, utc_now, write_json
from .experiment_status import (
    EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX,
    EXPERIMENT_STATUS_SUPERSEDED_BY_OVERLAP_RERUN,
)


def overlap_legacy_archive_root(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "experiments" / "legacy" / "overlap_rerun_superseded" / as_of


def overlap_legacy_archive_summary_path(*, artifacts_root: Path, as_of: str) -> Path:
    return artifacts_root / "assessments" / "legacy_experiment_archives" / "overlap_rerun_superseded" / as_of / "cleanup_summary.json"


def archive_superseded_overlap_rerun_experiments(
    *,
    artifacts_root: Path,
    as_of: str,
) -> dict[str, Any]:
    manifest = load_daily_alpha_manifest(artifacts_root=artifacts_root, as_of=as_of)
    manifest_entries = manifest_entries_by_experiment_id(manifest)
    experiments_root = artifacts_root / "experiments"
    legacy_root = overlap_legacy_archive_root(artifacts_root=artifacts_root, as_of=as_of)
    legacy_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for alpha_card_path in sorted(experiments_root.glob("*/alpha_card.json")):
        alpha_card = read_json(alpha_card_path)
        if str(alpha_card.get("as_of") or "").strip() != as_of:
            continue
        if str(alpha_card.get("experiment_status") or "").strip() != EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX:
            continue
        experiment_id = str(alpha_card.get("experiment_id") or "").strip()
        if not experiment_id:
            continue
        manifest_entry = manifest_entries.get(experiment_id)
        if not manifest_entry:
            continue
        canonical_alpha_card_path = resolve_portable_path(str(manifest_entry.get("alpha_card_path") or ""), repo_root=ROOT)
        if not canonical_alpha_card_path.exists():
            continue
        if canonical_alpha_card_path.resolve() == alpha_card_path.resolve():
            continue
        canonical_alpha_card = read_json(canonical_alpha_card_path)
        canonical_status = str(canonical_alpha_card.get("experiment_status") or "").strip()
        if canonical_status == EXPERIMENT_STATUS_NEEDS_RERUN_AFTER_OVERLAP_FIX:
            continue
        experiment_root = alpha_card_path.parent
        legacy_target = legacy_root / experiment_root.name
        if legacy_target.exists():
            shutil.rmtree(legacy_target)
        shutil.move(str(experiment_root), str(legacy_target))
        _rewrite_archived_overlap_experiment(
            legacy_target=legacy_target,
            original_experiment_root=experiment_root,
            canonical_alpha_card_path=canonical_alpha_card_path,
            canonical_experiment_status=canonical_status,
        )
        records.append(
            {
                "experiment_id": experiment_id,
                "original_experiment_root": portable_path(experiment_root, repo_root=ROOT),
                "legacy_experiment_root": portable_path(legacy_target, repo_root=ROOT),
                "canonical_alpha_card_path": portable_path(canonical_alpha_card_path, repo_root=ROOT),
                "canonical_experiment_status": canonical_status,
            }
        )
    summary = {
        "status": "success",
        "generated_at_utc": utc_now(),
        "as_of": as_of,
        "archived_experiment_count": len(records),
        "archived_experiments": records,
        "daily_alpha_manifest_path": portable_path(
            daily_alpha_manifest_root(artifacts_root=artifacts_root) / f"{as_of}.json",
            repo_root=ROOT,
        ),
        "legacy_archive_root": portable_path(legacy_root, repo_root=ROOT),
    }
    summary_path = overlap_legacy_archive_summary_path(artifacts_root=artifacts_root, as_of=as_of)
    write_json(summary_path, summary)
    summary["path"] = portable_path(summary_path, repo_root=ROOT)
    return summary


def _rewrite_archived_overlap_experiment(
    *,
    legacy_target: Path,
    original_experiment_root: Path,
    canonical_alpha_card_path: Path,
    canonical_experiment_status: str,
) -> None:
    alpha_card_path = legacy_target / "alpha_card.json"
    if not alpha_card_path.exists():
        return
    alpha_card = read_json(alpha_card_path)
    blockers = [str(item) for item in dict(alpha_card.get("quality_summary") or {}).get("quality_blockers", [])]
    archive_blocker = "superseded_by_overlap_rerun"
    if archive_blocker not in blockers:
        blockers.append(archive_blocker)
    archive_metadata = {
        "archive_kind": "overlap_rerun_superseded",
        "archived_at_utc": utc_now(),
        "canonical_alpha_card_path": portable_path(canonical_alpha_card_path, repo_root=ROOT),
        "canonical_experiment_status": canonical_experiment_status,
        "original_experiment_root": portable_path(original_experiment_root, repo_root=ROOT),
        "legacy_experiment_root": portable_path(legacy_target, repo_root=ROOT),
    }
    alpha_card["experiment_status"] = EXPERIMENT_STATUS_SUPERSEDED_BY_OVERLAP_RERUN
    alpha_card["publication_status"] = "archived_only"
    alpha_card["reason"] = "superseded_by_overlap_rerun"
    alpha_card["legacy_archive"] = archive_metadata
    alpha_card["quality_summary"] = {
        "quality_gate_passed": False,
        "quality_blockers": blockers,
        "metrics_snapshot": dict(dict(alpha_card.get("quality_summary") or {}).get("metrics_snapshot") or {}),
    }
    write_json(alpha_card_path, alpha_card)

    for file_name in ("validation_report.json", "backtest_report.json", "experiment_spec.json"):
        report_path = legacy_target / file_name
        if not report_path.exists():
            continue
        payload = read_json(report_path)
        if not isinstance(payload, dict):
            continue
        payload["experiment_status"] = EXPERIMENT_STATUS_SUPERSEDED_BY_OVERLAP_RERUN
        payload["publication_status"] = "archived_only"
        payload["reason"] = "superseded_by_overlap_rerun"
        payload["legacy_archive"] = archive_metadata
        if file_name != "experiment_spec.json":
            payload["quality_summary"] = alpha_card["quality_summary"]
        write_json(report_path, payload)
