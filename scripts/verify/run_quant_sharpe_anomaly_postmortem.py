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

from enhengclaw.quant_research.postmortem import write_sharpe_anomaly_postmortem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a reproducible postmortem for a quant Sharpe anomaly card.")
    parser.add_argument("--alpha-id", required=True, help="Canonical experiment_id / alpha_id to analyze.")
    parser.add_argument("--artifacts-root", type=Path, default=ROOT / "artifacts" / "quant_research")
    parser.add_argument("--now-utc", help="Optional ISO-8601 UTC timestamp for deterministic output paths.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = write_sharpe_anomaly_postmortem(
        alpha_id=args.alpha_id,
        artifacts_root=args.artifacts_root.expanduser().resolve(),
        repo_root=ROOT,
        now_utc=args.now_utc,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
