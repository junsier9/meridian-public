from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.alpha_manifest import daily_alpha_manifest_root
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT
from enhengclaw.quant_research.legacy_experiments import archive_superseded_overlap_rerun_experiments


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive superseded overlap-rerun experiment directories that are no longer canonical."
    )
    parser.add_argument("--as-of", help="Optional YYYY-MM-DD date to clean instead of scanning all daily manifests.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifacts_root = args.artifacts_root.expanduser().resolve()
    target_dates = [args.as_of] if args.as_of else _available_as_of_dates(artifacts_root=artifacts_root)
    try:
        summaries = [
            archive_superseded_overlap_rerun_experiments(
                artifacts_root=artifacts_root,
                as_of=as_of,
            )
            for as_of in target_dates
        ]
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    output = {
        "status": "success",
        "requested_as_of": args.as_of,
        "processed_dates": target_dates,
        "archived_experiment_count": sum(int(item.get("archived_experiment_count", 0) or 0) for item in summaries),
        "per_as_of": summaries,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _available_as_of_dates(*, artifacts_root: Path) -> list[str]:
    manifest_root = daily_alpha_manifest_root(artifacts_root=artifacts_root)
    if not manifest_root.exists():
        return []
    return sorted(path.stem for path in manifest_root.glob("*.json"))


if __name__ == "__main__":
    raise SystemExit(main())
