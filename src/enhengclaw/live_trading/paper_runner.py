from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path
from typing import Any

from enhengclaw.live_trading.cli import run_from_args
from enhengclaw.quant_research.contracts import write_json


PAPER_ONLY_MODE = "paper"
PAPER_ORDER_SUBMISSION_POLICY = "paper_fills_only_no_exchange_order_endpoint"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Controlled paper-only hv_balanced strategy automation runner."
    )
    parser.add_argument("--config", default="config/live_trading/hv_balanced_binance_usdm.yaml")
    parser.add_argument("--as-of", default="now")
    parser.add_argument("--fixture-panel", default="")
    parser.add_argument("--symbols", default="", help="Comma-separated Binance USD-M symbols for public data.")
    parser.add_argument(
        "--public-market-data",
        action="store_true",
        help="Use Binance USD-M public REST data when no fixture panel is supplied.",
    )
    args = parser.parse_args(argv)
    summary, exit_code = run_paper_controlled_from_args(args)
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return exit_code


def run_paper_controlled_from_args(args: Namespace) -> tuple[dict[str, Any], int]:
    """Run the strategy automation stack with exchange order submission locked out.

    This wrapper intentionally does not expose mode selection, live confirmation,
    manual lifecycle operations, or operator flatten execution. It delegates to
    the shared pipeline only after pinning the run mode to paper.
    """
    pinned_args = Namespace(
        config=str(getattr(args, "config", "config/live_trading/hv_balanced_binance_usdm.yaml") or ""),
        mode=PAPER_ONLY_MODE,
        as_of=str(getattr(args, "as_of", "now") or "now"),
        fixture_panel=str(getattr(args, "fixture_panel", "") or ""),
        symbols=str(getattr(args, "symbols", "") or ""),
        public_market_data=bool(getattr(args, "public_market_data", False)),
        operator_action="none",
        operator_reason="",
        confirm_plan_id="",
        i_understand_this_is_live=False,
    )
    summary, exit_code = run_from_args(pinned_args)
    summary = dict(summary)
    summary["runner"] = "hv_balanced_paper_controlled"
    summary["paper_only"] = True
    summary["exchange_order_submission"] = "disabled"
    summary["order_submission_policy"] = PAPER_ORDER_SUBMISSION_POLICY
    artifact_root_raw = str(summary.get("artifact_root") or "").strip()
    if artifact_root_raw:
        artifact_root = Path(artifact_root_raw)
        artifact_root.mkdir(parents=True, exist_ok=True)
        write_json(artifact_root / "run_summary.json", summary)
        write_json(
            artifact_root / "paper_controlled_runner.json",
            {
                "runner": summary["runner"],
                "paper_only": summary["paper_only"],
                "exchange_order_submission": summary["exchange_order_submission"],
                "order_submission_policy": summary["order_submission_policy"],
            },
        )
    return summary, exit_code


if __name__ == "__main__":
    raise SystemExit(main())
