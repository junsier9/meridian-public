from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.refactor_freeze.common import (
    REPO_ROOT,
    freeze_phase_root,
    parse_snapshot_identity,
    read_json,
    to_jsonable,
    utc_now_iso,
    write_json,
)
from scripts.refactor_freeze.models import DiffEntry, DiffReport, DiffSummary, SnapshotDiffResult
from scripts.refactor_freeze.normalize_snapshot import normalize_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff baseline and candidate freeze snapshots.")
    parser.add_argument("--phase", required=True, help="Phase identifier, for example: phase_01")
    parser.add_argument(
        "--freeze-root",
        type=Path,
        default=None,
        help="Optional override for the refactor freeze root directory.",
    )
    parser.add_argument(
        "--approval-file",
        type=Path,
        default=None,
        help="Optional JSON file listing explicitly approved diffs.",
    )
    args = parser.parse_args()

    report = build_diff_report(
        phase=args.phase,
        freeze_root=args.freeze_root,
        approval_file=args.approval_file,
    )
    diff_root = freeze_phase_root(kind="diffs", phase=args.phase, freeze_root=args.freeze_root)
    write_json(diff_root / "diff_report.json", report)
    print(json.dumps(read_json(diff_root / "diff_report.json"), indent=2, sort_keys=True, ensure_ascii=True))
    return 0


def build_diff_report(
    *,
    phase: str,
    freeze_root: Path | None = None,
    approval_file: Path | None = None,
) -> dict[str, Any]:
    baseline_root = freeze_phase_root(kind="baselines", phase=phase, freeze_root=freeze_root)
    candidate_root = freeze_phase_root(kind="candidates", phase=phase, freeze_root=freeze_root)
    approvals = _load_approvals(approval_file)

    baseline_files = {path.name: path for path in baseline_root.glob("*.snapshot.json")}
    candidate_files = {path.name: path for path in candidate_root.glob("*.snapshot.json")}

    snapshot_results: list[SnapshotDiffResult] = []
    total_diff_count = 0
    snapshot_with_diff_count = 0
    unapproved_diff_count = 0
    missing_snapshot_count = 0

    for file_name in sorted(set(baseline_files) | set(candidate_files)):
        baseline_path = baseline_files.get(file_name)
        candidate_path = candidate_files.get(file_name)
        snapshot_type, case_id = parse_snapshot_identity(Path(file_name))

        if baseline_path is None or candidate_path is None:
            missing_snapshot_count += 1
            diff = DiffEntry(
                field="$.__presence__",
                before="present" if baseline_path is not None else "missing",
                after="present" if candidate_path is not None else "missing",
                normalization_applied=[],
                is_approved_change=False,
                approval_ref=None,
                stopline_triggered=True,
                notes="missing snapshot blocks the phase",
            )
            snapshot_results.append(
                SnapshotDiffResult(
                    snapshot_type=snapshot_type,
                    case_id=case_id,
                    baseline_file=file_name,
                    candidate_file=file_name,
                    diff_count=1,
                    stopline_triggered=True,
                    diffs=[diff],
                )
            )
            total_diff_count += 1
            snapshot_with_diff_count += 1
            unapproved_diff_count += 1
            continue

        baseline_payload = _load_snapshot_body(baseline_path)
        candidate_payload = _load_snapshot_body(candidate_path)
        baseline_normalized, baseline_ops = normalize_snapshot(baseline_payload, repo_root=REPO_ROOT)
        candidate_normalized, candidate_ops = normalize_snapshot(candidate_payload, repo_root=REPO_ROOT)
        normalization_ops = sorted(set(baseline_ops + candidate_ops))

        diffs = _collect_diffs(
            before=baseline_normalized,
            after=candidate_normalized,
            path="$",
            snapshot_type=snapshot_type,
            case_id=case_id,
            normalization_applied=normalization_ops,
            approvals=approvals,
        )
        snapshot_stopline = any(diff.stopline_triggered for diff in diffs)
        snapshot_results.append(
            SnapshotDiffResult(
                snapshot_type=snapshot_type,
                case_id=case_id,
                baseline_file=file_name,
                candidate_file=file_name,
                diff_count=len(diffs),
                stopline_triggered=snapshot_stopline,
                diffs=diffs,
            )
        )
        if diffs:
            snapshot_with_diff_count += 1
            total_diff_count += len(diffs)
            unapproved_diff_count += sum(1 for diff in diffs if not diff.is_approved_change)

    stopline_triggered = unapproved_diff_count > 0 or missing_snapshot_count > 0
    report = DiffReport(
        phase=phase,
        generated_at_utc=utc_now_iso(),
        baseline_root=str(baseline_root),
        candidate_root=str(candidate_root),
        summary=DiffSummary(
            snapshot_count=len(snapshot_results),
            snapshot_with_diff_count=snapshot_with_diff_count,
            total_diff_count=total_diff_count,
            unapproved_diff_count=unapproved_diff_count,
            stopline_triggered=stopline_triggered,
            can_continue=not stopline_triggered,
            missing_snapshot_count=missing_snapshot_count,
            invalid_normalization_count=0,
        ),
        snapshots=snapshot_results,
    )
    return {
        "phase": report.phase,
        "generated_at_utc": report.generated_at_utc,
        "baseline_root": report.baseline_root,
        "candidate_root": report.candidate_root,
        "summary": to_jsonable(report.summary),
        "snapshots": to_jsonable(report.snapshots),
    }


def _load_snapshot_body(path: Path) -> Any:
    payload = read_json(path)
    if isinstance(payload, dict) and "snapshot" in payload:
        return payload["snapshot"]
    return payload


def _load_approvals(path: Path | None) -> dict[tuple[str, str, str], str]:
    if path is None:
        return {}
    payload = read_json(path)
    items = payload.get("approvals", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise ValueError("approval file must contain an 'approvals' list")

    approvals: dict[tuple[str, str, str], str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("approval entries must be objects")
        snapshot_type = item.get("snapshot_type")
        case_id = item.get("case_id")
        field = item.get("field")
        approval_ref = item.get("approval_ref")
        values = [snapshot_type, case_id, field, approval_ref]
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ValueError("each approval entry must include non-empty snapshot_type, case_id, field, approval_ref")
        approvals[(snapshot_type, case_id, field)] = approval_ref
    return approvals


def _collect_diffs(
    *,
    before: Any,
    after: Any,
    path: str,
    snapshot_type: str,
    case_id: str,
    normalization_applied: list[str],
    approvals: dict[tuple[str, str, str], str],
) -> list[DiffEntry]:
    if type(before) is not type(after):
        return [_make_diff(path, before, after, snapshot_type, case_id, normalization_applied, approvals)]

    if isinstance(before, dict):
        diffs: list[DiffEntry] = []
        for key in sorted(set(before.keys()) | set(after.keys())):
            child_path = f"{path}.{key}"
            if key not in before or key not in after:
                diffs.append(_make_diff(child_path, before.get(key), after.get(key), snapshot_type, case_id, normalization_applied, approvals))
                continue
            diffs.extend(
                _collect_diffs(
                    before=before[key],
                    after=after[key],
                    path=child_path,
                    snapshot_type=snapshot_type,
                    case_id=case_id,
                    normalization_applied=normalization_applied,
                    approvals=approvals,
                )
            )
        return diffs

    if isinstance(before, list):
        diffs: list[DiffEntry] = []
        if len(before) != len(after):
            diffs.append(_make_diff(path, before, after, snapshot_type, case_id, normalization_applied, approvals))
            return diffs
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            diffs.extend(
                _collect_diffs(
                    before=left,
                    after=right,
                    path=f"{path}[{index}]",
                    snapshot_type=snapshot_type,
                    case_id=case_id,
                    normalization_applied=normalization_applied,
                    approvals=approvals,
                )
            )
        return diffs

    if before != after:
        return [_make_diff(path, before, after, snapshot_type, case_id, normalization_applied, approvals)]
    return []


def _make_diff(
    path: str,
    before: Any,
    after: Any,
    snapshot_type: str,
    case_id: str,
    normalization_applied: list[str],
    approvals: dict[tuple[str, str, str], str],
) -> DiffEntry:
    approval_ref = approvals.get((snapshot_type, case_id, path))
    approved = approval_ref is not None
    return DiffEntry(
        field=path,
        before=before,
        after=after,
        normalization_applied=normalization_applied,
        is_approved_change=approved,
        approval_ref=approval_ref,
        stopline_triggered=not approved,
    )


if __name__ == "__main__":
    raise SystemExit(main())
