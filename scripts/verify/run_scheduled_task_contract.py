from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.evidence_contracts import utc_now_iso
from enhengclaw.ops.scheduled_task_contracts import evaluate_task_readiness, load_scheduled_task_manifest


DEFAULT_MANIFEST_PATH = ROOT / "config" / "scheduled_tasks" / "manifest.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate one scheduled task summary bundle against the scheduled-task manifest.")
    parser.add_argument("--task-key", required=True)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--summary-map-path", type=Path, required=True, help="JSON map keyed by task_key -> summary payload.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_scheduled_task_manifest(args.manifest_path)
    summaries_by_task_key = json.loads(args.summary_map_path.read_text(encoding="utf-8"))
    result = evaluate_task_readiness(
        task_key=args.task_key,
        manifest=manifest,
        summaries_by_task_key=summaries_by_task_key,
        now_utc=utc_now_iso(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
