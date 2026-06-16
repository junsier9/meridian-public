from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.onchain_m3_2_features import (  # noqa: E402
    DEFAULT_OUT_PATH,
    M3_2_FEATURE_PANEL_CONTRACT_VERSION,
    build_m3_2_feature_panel,
    summarize_m3_2_feature_panel,
    write_m3_2_feature_panel,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build fused Alchemy + CryptoQuant M3.2 daily feature panel.")
    parser.add_argument("--stablecoin-external-root", type=Path, default=None)
    parser.add_argument("--cryptoquant-external-root", type=Path, default=None)
    parser.add_argument("--tron-external-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    panel = build_m3_2_feature_panel(
        stablecoin_external_root=args.stablecoin_external_root,
        cryptoquant_external_root=args.cryptoquant_external_root,
        tron_external_root=args.tron_external_root,
    )
    output_path = write_m3_2_feature_panel(panel, output_path=args.output)
    summary = summarize_m3_2_feature_panel(
        panel,
        stablecoin_external_root=args.stablecoin_external_root,
        cryptoquant_external_root=args.cryptoquant_external_root,
        tron_external_root=args.tron_external_root,
        output_path=output_path,
    )
    summary.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "contract_version": M3_2_FEATURE_PANEL_CONTRACT_VERSION,
        }
    )
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
