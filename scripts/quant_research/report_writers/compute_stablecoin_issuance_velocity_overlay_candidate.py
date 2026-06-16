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

from enhengclaw.quant_research.stablecoin_regime import (  # noqa: E402
    DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
    DEFAULT_STABLECOIN_OVERLAY_V2_ID,
    DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
    stablecoin_overlay_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute a stablecoin overlay candidate summary."
    )
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument(
        "--overlay-id",
        choices=(
            "stablecoin_issuance_velocity_overlay_v1",
            "stablecoin_issuance_velocity_overlay_v2",
            DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
            DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
        ),
        default=DEFAULT_STABLECOIN_OVERLAY_V2_ID,
    )
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = stablecoin_overlay_summary(
            external_root=args.external_root,
            overlay_id=args.overlay_id,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        summary["report_path"] = str(args.report_path)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
