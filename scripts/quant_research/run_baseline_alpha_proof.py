from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.baseline_alpha_proof import (
    BASELINE_ALPHA_PROOF_FIXTURE_PATH,
    run_baseline_alpha_proof,
)
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, QUANT_INPUT_ROOT, WORKBENCH_ROOT


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic baseline alpha proof.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    parser.add_argument("--fixture-path", type=Path, default=BASELINE_ALPHA_PROOF_FIXTURE_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        proof = run_baseline_alpha_proof(
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
            workbench_root=args.workbench_root,
            ohlcv_external_root=args.ohlcv_external_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            derivatives_external_root=args.derivatives_external_root,
            auto_detect_spot_ohlcv_external_root=args.spot_ohlcv_external_root is None,
            fixture_path=args.fixture_path,
        )
    except Exception:
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1
    print(json.dumps(proof, indent=2, sort_keys=True, default=_json_default))
    return 0 if bool(proof.get("proof_passed")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
