from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import with_evidence_metadata
from enhengclaw.utils.research_workbench_queues import (
    LEGACY_QUEUE,
    QUANT_QUEUE,
    STRUCTURAL_QUEUE,
    consumed_archive_root,
    incoming_queue_root,
)
from enhengclaw.utils.research_workbench_queue_dashboard import generate_research_workbench_queue_dashboard
from scripts.openclaw.run_openclaw_research_cycle import run_openclaw_research_cycle


WORKBENCH_ROOT = ROOT / "artifacts" / "research_workbench"


@dataclass(frozen=True, slots=True)
class PendingSnapshot:
    source: str
    snapshot_path: Path
    cycle_id: str
    object_id: str
    cycle_summary_path: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consume up to one structural and one quant snapshot from the research workbench intake queues."
    )
    parser.add_argument(
        "--workbench-root",
        type=Path,
        default=WORKBENCH_ROOT,
        help="Research workbench root. Defaults to artifacts\\research_workbench.",
    )
    parser.add_argument(
        "--compiler-backend",
        choices=("live", "deterministic"),
        default="live",
        help="Compiler backend label forwarded into the single-snapshot worker.",
    )
    parser.add_argument("--max-structural", type=int, default=1, help="Maximum structural snapshots to process.")
    parser.add_argument("--max-quant", type=int, default=1, help="Maximum quant snapshots to process.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_openclaw_research_intake_cycle(
            workbench_root=args.workbench_root,
            compiler_backend=args.compiler_backend,
            max_structural=args.max_structural,
            max_quant=args.max_quant,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"[openclaw-research-intake] intake_summary={summary['intake_summary_path']}")
    print(f"[openclaw-research-intake] processed_snapshot_count={summary['processed_snapshot_count']}")
    return 0 if summary["status"] == "success" else 1


def run_openclaw_research_intake_cycle(
    *,
    workbench_root: Path,
    compiler_backend: str = "live",
    max_structural: int = 1,
    max_quant: int = 1,
) -> dict[str, Any]:
    if max_structural < 0 or max_quant < 0:
        raise ValueError("max_structural and max_quant must be non-negative")
    resolved_workbench_root = workbench_root.expanduser().resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    intake_root = resolved_workbench_root / "_intake_runs" / run_id
    intake_root.mkdir(parents=True, exist_ok=False)
    summary: dict[str, Any] = with_evidence_metadata(
        {
        "status": "success",
        "success": True,
        "generated_at_utc": _utc_now(),
        "run_id": run_id,
        "workbench_root": str(resolved_workbench_root),
        "compiler_backend": compiler_backend,
        "queue_budgets": {
            STRUCTURAL_QUEUE: int(max_structural),
            QUANT_QUEUE: int(max_quant),
            LEGACY_QUEUE: int(max_structural + max_quant),
        },
        "processed": [],
        "archived_already_consumed": [],
        "errors": [],
        "input_watermarks": {},
        "upstream_versions": {
            "queue_sources": [STRUCTURAL_QUEUE, QUANT_QUEUE, LEGACY_QUEUE],
        },
        },
        evidence_family="openclaw_research_intake_cycle",
        contract_version="openclaw_research_intake_cycle.v1",
        repo_root=ROOT,
    )

    try:
        for source, budget in ((STRUCTURAL_QUEUE, max_structural), (QUANT_QUEUE, max_quant)):
            if budget <= 0:
                continue
            processed_for_source = 0
            while processed_for_source < budget:
                pending = _next_pending_snapshot(workbench_root=resolved_workbench_root, source=source, summary=summary)
                if pending is None:
                    break
                result = run_openclaw_research_cycle(
                    snapshot_path=pending.snapshot_path,
                    workbench_root=resolved_workbench_root,
                    compiler_backend=compiler_backend,
                )
                processed_entry = {
                    "source": source,
                    "cycle_id": pending.cycle_id,
                    "object_id": pending.object_id,
                    "snapshot_path": str(pending.snapshot_path),
                    "cycle_summary_path": result.get("cycle_summary_path"),
                    "status": result.get("status"),
                }
                if result.get("status") == "success":
                    archive_path = _archive_snapshot(
                        snapshot_path=pending.snapshot_path,
                        workbench_root=resolved_workbench_root,
                        source=source,
                        reason="cycle_completed",
                    )
                    processed_entry["archive_path"] = str(archive_path)
                else:
                    summary["status"] = "partial"
                    processed_entry["error"] = result.get("error")
                    summary["errors"].append(
                        {
                            "source": source,
                            "cycle_id": pending.cycle_id,
                            "snapshot_path": str(pending.snapshot_path),
                            "error": result.get("error"),
                        }
                    )
                summary["processed"].append(processed_entry)
                processed_for_source += 1
        remaining_legacy_budget = max(0, (max_structural + max_quant) - len(summary["processed"]))
        processed_legacy = 0
        while processed_legacy < remaining_legacy_budget:
            pending = _next_pending_snapshot(workbench_root=resolved_workbench_root, source=LEGACY_QUEUE, summary=summary)
            if pending is None:
                break
            result = run_openclaw_research_cycle(
                snapshot_path=pending.snapshot_path,
                workbench_root=resolved_workbench_root,
                compiler_backend=compiler_backend,
            )
            processed_entry = {
                "source": LEGACY_QUEUE,
                "cycle_id": pending.cycle_id,
                "object_id": pending.object_id,
                "snapshot_path": str(pending.snapshot_path),
                "cycle_summary_path": result.get("cycle_summary_path"),
                "status": result.get("status"),
            }
            if result.get("status") == "success":
                archive_path = _archive_snapshot(
                    snapshot_path=pending.snapshot_path,
                    workbench_root=resolved_workbench_root,
                    source=LEGACY_QUEUE,
                    reason="cycle_completed",
                )
                processed_entry["archive_path"] = str(archive_path)
            else:
                summary["status"] = "partial"
                processed_entry["error"] = result.get("error")
                summary["errors"].append(
                    {
                        "source": LEGACY_QUEUE,
                        "cycle_id": pending.cycle_id,
                        "snapshot_path": str(pending.snapshot_path),
                        "error": result.get("error"),
                    }
                )
            summary["processed"].append(processed_entry)
            processed_legacy += 1
        summary["processed_snapshot_count"] = len(summary["processed"])
        summary["archived_already_consumed_count"] = len(summary["archived_already_consumed"])
        summary["input_watermarks"] = {
            "structural_queue_latest_mtime": _latest_queue_mtime(resolved_workbench_root, STRUCTURAL_QUEUE),
            "quant_queue_latest_mtime": _latest_queue_mtime(resolved_workbench_root, QUANT_QUEUE),
            "legacy_queue_latest_mtime": _latest_queue_mtime(resolved_workbench_root, LEGACY_QUEUE),
        }
    finally:
        summary_path = intake_root / "intake_summary.json"
        summary["intake_summary_path"] = str(summary_path)
        _write_json(summary_path, summary)
        try:
            dashboard = generate_research_workbench_queue_dashboard(workbench_root=resolved_workbench_root)
        except Exception as exc:
            summary["queue_dashboard_refresh_error"] = str(exc)
        else:
            summary["queue_dashboard_json_path"] = dashboard["queue_dashboard_json_path"]
            summary["queue_dashboard_markdown_path"] = dashboard["queue_dashboard_markdown_path"]
    return summary


def _next_pending_snapshot(*, workbench_root: Path, source: str, summary: dict[str, Any]) -> PendingSnapshot | None:
    queue_root = incoming_queue_root(workbench_root=workbench_root, source=source)
    if not queue_root.exists():
        return None
    for snapshot_path in sorted(queue_root.glob("*.snapshot.json"), key=lambda path: (path.stat().st_mtime, path.name)):
        pending = _load_pending_snapshot(snapshot_path=snapshot_path, workbench_root=workbench_root, source=source)
        if pending is None:
            archive_path = _archive_snapshot(
                snapshot_path=snapshot_path,
                workbench_root=workbench_root,
                source=source,
                reason="already_consumed",
            )
            summary["archived_already_consumed"].append(
                {
                    "source": source,
                    "snapshot_path": str(snapshot_path),
                    "archive_path": str(archive_path),
                }
            )
            continue
        return pending
    return None


def _load_pending_snapshot(*, snapshot_path: Path, workbench_root: Path, source: str) -> PendingSnapshot | None:
    payload = _read_json(snapshot_path)
    cycle_id = str(payload.get("cycle_id", "")).strip()
    object_id = str(payload.get("object_id", "")).strip()
    if not cycle_id or not object_id:
        raise ValueError(f"snapshot is missing cycle_id/object_id: {snapshot_path}")
    cycle_summary_path = workbench_root / object_id / "cycles" / cycle_id / "cycle_summary.json"
    if cycle_summary_path.exists():
        return None
    return PendingSnapshot(
        source=source,
        snapshot_path=snapshot_path.resolve(),
        cycle_id=cycle_id,
        object_id=object_id,
        cycle_summary_path=cycle_summary_path,
    )


def _archive_snapshot(*, snapshot_path: Path, workbench_root: Path, source: str, reason: str) -> Path:
    archive_root = consumed_archive_root(workbench_root=workbench_root, source=source)
    archive_root.mkdir(parents=True, exist_ok=True)
    target_path = archive_root / snapshot_path.name
    if target_path.exists():
        stem = snapshot_path.stem
        suffix = snapshot_path.suffix
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target_path = archive_root / f"{stem}-{reason}-{stamp}{suffix}"
    snapshot_path.replace(target_path)
    return target_path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _latest_queue_mtime(workbench_root: Path, source: str) -> str | None:
    queue_root = incoming_queue_root(workbench_root=workbench_root, source=source)
    if not queue_root.exists():
        return None
    newest = max((path.stat().st_mtime for path in queue_root.glob("*.snapshot.json")), default=None)
    if newest is None:
        return None
    return datetime.fromtimestamp(newest, tz=UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
