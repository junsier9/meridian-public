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

from enhengclaw.quant_research.positive_controls import write_positive_control_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run independent positive-control benchmarks for quant research.")
    parser.add_argument("--as-of", action="append", required=True, dest="as_ofs")
    parser.add_argument("--artifacts-root", default=str(ROOT / "artifacts" / "quant_research"))
    parser.add_argument("--now-utc", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifacts_root = Path(args.artifacts_root).expanduser().resolve()
    results = [
        write_positive_control_summary(
            as_of=as_of,
            artifacts_root=artifacts_root,
            repo_root=ROOT,
            now_utc=args.now_utc,
        )
        for as_of in args.as_ofs
    ]
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
