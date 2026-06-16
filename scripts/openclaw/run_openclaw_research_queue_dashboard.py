from __future__ import annotations

import argparse
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.utils.research_workbench_queue_dashboard import generate_research_workbench_queue_dashboard


WORKBENCH_ROOT = ROOT / "artifacts" / "research_workbench"
QUANT_ARTIFACTS_ROOT = ROOT / "artifacts" / "quant_research"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a research workbench queue operations dashboard.")
    parser.add_argument(
        "--workbench-root",
        type=Path,
        default=WORKBENCH_ROOT,
        help="Research workbench root. Defaults to artifacts\\research_workbench.",
    )
    parser.add_argument(
        "--quant-artifacts-root",
        type=Path,
        default=QUANT_ARTIFACTS_ROOT,
        help="Quant research artifacts root. Defaults to artifacts\\quant_research.",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=24,
        help="Recent intake window in hours. Defaults to 24.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = generate_research_workbench_queue_dashboard(
            workbench_root=args.workbench_root,
            quant_artifacts_root=args.quant_artifacts_root,
            window_hours=args.window_hours,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"[research-queue-dashboard] json={summary['queue_dashboard_json_path']}")
    print(f"[research-queue-dashboard] markdown={summary['queue_dashboard_markdown_path']}")
    print(f"[research-queue-dashboard] alert_count={len(summary['alerts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
