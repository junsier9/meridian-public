from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SYNC_SCRIPT = SCRIPT_DIR / "sync_deribit_options_chain.py"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "external_market_data" / "deribit_options_chain"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Deribit options-chain snapshot accumulation cycle."
    )
    parser.add_argument("--currencies", default="BTC,ETH")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = [
        sys.executable,
        str(SYNC_SCRIPT),
        "--currencies",
        str(args.currencies),
        "--output-dir",
        str(args.output_dir),
        "--write-summary",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
    )
    summary_path = args.output_dir / "_snapshot_summary_latest.json"
    output: dict[str, object] = {
        "command": command,
        "output_dir": str(args.output_dir),
        "snapshot_summary_path": str(summary_path),
        "exit_code": int(completed.returncode),
    }
    if summary_path.exists():
        try:
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            output["snapshot"] = summary_payload
        except json.JSONDecodeError:
            output["snapshot_summary_decode_error"] = True
    print(json.dumps(output, indent=2, sort_keys=True))
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
