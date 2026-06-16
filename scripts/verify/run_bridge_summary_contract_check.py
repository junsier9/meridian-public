from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.bridge_contracts import find_bridge_summary_paths, verify_bridge_summary_contract
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify that checked-in bridge summaries agree with current quant publication contracts.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--as-of", help="Optional YYYY-MM-DD export date filter.")
    parser.add_argument("--summary-path", type=Path, help="Optional explicit bridge_summary.json path.")
    parser.add_argument("--now-utc", help="Optional ISO-8601 UTC timestamp for deterministic checks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary_paths = _resolve_summary_paths(
        artifacts_root=args.artifacts_root,
        as_of=args.as_of,
        summary_path=args.summary_path,
    )
    report = {"checked": [], "failures": [], "success": True}
    for summary_path in summary_paths:
        blockers = verify_bridge_summary_contract(
            summary_path=summary_path,
            artifacts_root=args.artifacts_root,
            now_utc=args.now_utc,
        )
        item = {
            "summary_path": str(summary_path),
            "blockers": blockers,
            "ok": not blockers,
        }
        report["checked"].append(item)
        if blockers:
            report["success"] = False
            report["failures"].append(item)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["success"] else 1


def _resolve_summary_paths(*, artifacts_root: Path, as_of: str | None, summary_path: Path | None) -> list[Path]:
    if summary_path is not None:
        return [summary_path.expanduser().resolve()]
    paths = find_bridge_summary_paths(artifacts_root=artifacts_root.expanduser().resolve())
    if as_of:
        return [path for path in paths if path.parent.name == as_of]
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
