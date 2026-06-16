from __future__ import annotations

import argparse
from datetime import UTC, datetime
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

from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, QUANT_INPUT_ROOT, WORKBENCH_ROOT, run_quant_research_cycle


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")


def _build_failure_summary(args: argparse.Namespace, exc: Exception, formatted_traceback: str) -> dict[str, object]:
    return {
        "artifact_family": "quant_research_cycle_failure",
        "contract_version": "quant_research_cycle.failure.v1",
        "as_of": args.as_of,
        "compiler_backend": args.compiler_backend,
        "status": "failed",
        "success": False,
        "produced_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "error": {
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": formatted_traceback.splitlines(),
        },
        "runtime_context": {
            "artifacts_root": args.artifacts_root,
            "quant_input_root": args.quant_input_root,
            "workbench_root": args.workbench_root,
            "ohlcv_external_root": args.ohlcv_external_root,
            "spot_ohlcv_external_root": args.spot_ohlcv_external_root,
            "derivatives_external_root": args.derivatives_external_root,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one deterministic Quant Research Lab daily monitoring cycle.")
    parser.add_argument("--as-of", required=True, help="Research as-of date in YYYY-MM-DD format.")
    parser.add_argument(
        "--compiler-backend",
        choices=("deterministic", "live"),
        default="deterministic",
        help="Recorded backend label. Quant Lab remains deterministic in v1.",
    )
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    parser.add_argument(
        "--no-auto-api-gap-backfill",
        action="store_true",
        help="Disable suite-specific CoinAPI spot backfill for blocked cross-sectional datasets.",
    )
    parser.add_argument("--summary-out", type=Path, default=None, help="Optional path to write the successful cycle summary JSON.")
    parser.add_argument(
        "--failure-summary-out",
        type=Path,
        default=None,
        help="Optional path to write a structured failure summary when the cycle errors.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_quant_research_cycle(
            as_of=args.as_of,
            compiler_backend=args.compiler_backend,
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
            workbench_root=args.workbench_root,
            ohlcv_external_root=args.ohlcv_external_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            derivatives_external_root=args.derivatives_external_root,
            auto_api_gap_backfill=not bool(args.no_auto_api_gap_backfill),
        )
    except Exception as exc:
        formatted_traceback = traceback.format_exc()
        failure_summary = _build_failure_summary(args, exc, formatted_traceback)
        _write_json(args.failure_summary_out, failure_summary)
        print(formatted_traceback, file=sys.stderr, end="")
        if args.failure_summary_out is not None:
            print(f"failure_summary_path={args.failure_summary_out.expanduser().resolve()}", file=sys.stderr)
        return 1
    _write_json(args.summary_out, summary)
    print(json.dumps(summary, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
