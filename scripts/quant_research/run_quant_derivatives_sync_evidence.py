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
from enhengclaw.quant_research.contracts import QuantUniverseCandidate, QuantUniverseInput, read_json
from enhengclaw.quant_research.runtime_support import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    load_quant_universe_snapshot,
    resolve_quant_input_path,
    write_quant_derivatives_sync_summary_for_as_of,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a by_as_of derivatives evidence summary from the existing Binance derivatives store."
    )
    parser.add_argument("--as-of", required=True, help="Evidence date in YYYY-MM-DD format.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    parser.add_argument("--provider", choices=("auto", "coinglass", "binance"), default="auto")
    parser.add_argument("--intervals", default="4h,1d", help="Comma-separated interval list. Defaults to 4h,1d.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    intervals = tuple(item.strip() for item in str(args.intervals).split(",") if item.strip())
    if not intervals:
        print("at least one derivatives interval is required", file=sys.stderr)
        return 1
    try:
        symbols, symbol_source = _resolve_required_symbols(
            as_of=args.as_of,
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
        )
        summary, summary_path = write_quant_derivatives_sync_summary_for_as_of(
            as_of=args.as_of,
            symbols=symbols,
            intervals=intervals,
            derivatives_external_root=args.derivatives_external_root,
            provider=args.provider,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    output = {
        "as_of": args.as_of,
        "required_symbol_count": len(symbols),
        "required_symbols": symbols,
        "required_symbol_source": symbol_source,
        "derivatives_sync_summary_path": str(summary_path),
        "derivatives_external_root": str(
            resolve_external_derivatives_root(external_root=args.derivatives_external_root)
        ),
        "sync": summary,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _resolve_required_symbols(*, as_of: str, artifacts_root: Path, quant_input_root: Path) -> tuple[list[str], str]:
    resolved_artifacts_root = artifacts_root.expanduser().resolve()
    try:
        snapshot = load_quant_universe_snapshot(as_of=as_of, artifacts_root=resolved_artifacts_root)
    except FileNotFoundError:
        universe_input_path = resolve_quant_input_path(as_of=as_of, quant_input_root=quant_input_root.expanduser().resolve())
        universe_input = QuantUniverseInput.from_payload(read_json(universe_input_path))
        candidates = universe_input.selected_candidates()
        source_label = f"quant_input:{universe_input_path}"
    else:
        candidates = tuple(
            QuantUniverseCandidate.from_payload(item)
            for item in list(snapshot.get("candidates") or [])
            if isinstance(item, dict)
        )
        source_label = f"frozen_snapshot:{snapshot['path']}"
    symbols = sorted({str(candidate.usdm_symbol) for candidate in candidates if candidate.usdm_symbol})
    if not symbols:
        raise RuntimeError(f"no usdm symbols found for as_of={as_of} in {source_label}")
    return symbols, source_label


if __name__ == "__main__":
    raise SystemExit(main())
