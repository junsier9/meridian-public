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

from enhengclaw.quant_research.binance_derivatives import resolve_external_derivatives_root
from enhengclaw.quant_research.runtime_support import QUANT_INPUT_ROOT, run_quant_derivatives_sync_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync derivatives history for the current quant universe candidate set.")
    parser.add_argument("--as-of", required=True, help="Sync date in YYYY-MM-DD format.")
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    parser.add_argument("--mode", choices=("refresh", "bootstrap"), default="refresh")
    parser.add_argument("--provider", choices=("auto", "coinglass", "binance"), default="auto")
    parser.add_argument("--intervals", default="4h,1d", help="Comma-separated derivatives intervals, e.g. 4h or 4h,1d.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    resolved_intervals = tuple(
        item.strip()
        for item in str(args.intervals).split(",")
        if item.strip()
    )
    if not resolved_intervals:
        print("at least one derivatives interval is required", file=sys.stderr)
        return 1
    try:
        summary = run_quant_derivatives_sync_cycle(
            as_of=args.as_of,
            quant_input_root=args.quant_input_root,
            derivatives_external_root=args.derivatives_external_root,
            mode=args.mode,
            intervals=resolved_intervals,
            provider=args.provider,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    output = {
        "derivatives_sync_summary_path": str(
            resolve_external_derivatives_root(external_root=args.derivatives_external_root) / "last_sync_summary.json"
        ),
        "derivatives_sync_by_as_of_summary_path": summary.get("by_as_of_summary_path"),
        "sync": summary,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
