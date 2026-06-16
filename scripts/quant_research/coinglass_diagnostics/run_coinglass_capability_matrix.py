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

from enhengclaw.quant_research.coinglass_capability_matrix import build_coinglass_capability_matrix


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke CoinGlass endpoint families and write no-secret capability artifacts.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "provider_smoke",
        help="Directory for coinglass_capability_matrix.json and sanitized samples.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_coinglass_capability_matrix(output_root=args.output_root)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["success_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
