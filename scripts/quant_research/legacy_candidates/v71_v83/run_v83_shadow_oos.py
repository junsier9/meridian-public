from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.shadow_oos import ShadowOOSConfig, run_shadow_oos_retrospective


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay v83 (xs_minimal_v3) score over a feature panel and emit shadow OOS daily metrics."
    )
    parser.add_argument("--as-of", required=True)
    parser.add_argument(
        "--feature-panel-path",
        type=Path,
        default=ROOT
        / "artifacts"
        / "quant_research"
        / "features"
        / "2026-04-26-cross-sectional-daily-1d-h5d-features-v83"
        / "features.csv.gz",
    )
    parser.add_argument("--feature-set-id", default="2026-04-26-cross-sectional-daily-1d-h5d-features-v83")
    parser.add_argument("--target-horizon-bars", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--universe-max-selection-rank", type=int, default=20)
    parser.add_argument(
        "--universe-allowed-liquidity-bucket",
        action="append",
        default=None,
        help="Repeatable. Defaults to top_liquidity + mid_liquidity (matches liquid_perp_core_20).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    allowed_buckets = tuple(args.universe_allowed_liquidity_bucket) if args.universe_allowed_liquidity_bucket else (
        "top_liquidity",
        "mid_liquidity",
    )
    config = ShadowOOSConfig(
        candidate_id="xs_minimal_v3_h5d",
        score_fn_name="xs_minimal_v3",
        as_of=args.as_of,
        feature_set_id=args.feature_set_id,
        feature_panel_path=args.feature_panel_path.resolve(),
        target_horizon_bars=args.target_horizon_bars,
        top_k=args.top_k,
        universe_max_selection_rank=args.universe_max_selection_rank,
        universe_allowed_liquidity_buckets=allowed_buckets,
    )
    summary = run_shadow_oos_retrospective(config)
    print(json.dumps(summary, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
