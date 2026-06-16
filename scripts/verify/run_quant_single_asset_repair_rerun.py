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

from enhengclaw.quant_research.single_asset_repair import run_single_asset_repair_rerun


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair the single-asset quant path and rerun only affected canonical strategies.")
    parser.add_argument("--as-of", action="append", dest="as_ofs", default=[])
    parser.add_argument("--compiler-backend", default="deterministic", choices=("deterministic", "live"))
    parser.add_argument("--artifacts-root", default=str(ROOT / "artifacts" / "quant_research"))
    parser.add_argument("--workbench-root", default=str(ROOT / "artifacts" / "research_workbench"))
    parser.add_argument("--ohlcv-external-root", default=None)
    parser.add_argument("--derivatives-external-root", default=None)
    parser.add_argument("--now-utc", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_single_asset_repair_rerun(
        artifacts_root=Path(args.artifacts_root).expanduser().resolve(),
        workbench_root=Path(args.workbench_root).expanduser().resolve(),
        as_ofs=tuple(args.as_ofs) if args.as_ofs else ("2026-04-20", "2026-04-21"),
        compiler_backend=args.compiler_backend,
        ohlcv_external_root=Path(args.ohlcv_external_root).expanduser().resolve() if args.ohlcv_external_root else None,
        derivatives_external_root=Path(args.derivatives_external_root).expanduser().resolve() if args.derivatives_external_root else None,
        now_utc=args.now_utc,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
