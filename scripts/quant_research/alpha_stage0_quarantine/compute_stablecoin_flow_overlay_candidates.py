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
    DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
    stablecoin_overlay_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute the first batch of M3.2 Phase 2 stablecoin flow overlay candidates."
    )
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    overlay_ids = [
        DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
        DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
    ]
    try:
        payload = {
            "overlay_ids": overlay_ids,
            "summaries": {
                overlay_id: stablecoin_overlay_summary(
                    external_root=args.external_root,
                    overlay_id=overlay_id,
                )
                for overlay_id in overlay_ids
            },
        }
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        payload["report_path"] = str(args.report_path)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
