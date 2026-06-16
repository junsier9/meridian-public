from __future__ import annotations

import argparse
from datetime import UTC, datetime
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

from enhengclaw.quant_research.onchain_cryptoquant import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_REFRESH_OVERLAP_DAYS,
    DEFAULT_SYNC_MODE,
    resolve_onchain_cryptoquant_external_root,
    run_cryptoquant_reflexivity_sync,
    run_cryptoquant_stablecoin_sync,
)


ARTIFACT_FAMILY = "quant_cryptoquant_m3_2_sync_cycle"
CONTRACT_VERSION = "quant_cryptoquant_m3_2_sync_cycle.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one CryptoQuant-backed M3.2 sync cycle for stablecoin plumbing and on-chain reflexivity."
    )
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--mode", default=DEFAULT_SYNC_MODE, choices=("auto", "bootstrap", "refresh"))
    parser.add_argument("--refresh-overlap-days", type=int, default=DEFAULT_REFRESH_OVERLAP_DAYS)
    parser.add_argument("--stablecoin-tokens", default="usdt_eth,usdc,dai,tusd,usdt_trx,usdt_omni")
    parser.add_argument("--reflexivity-assets", default="btc,eth")
    parser.add_argument("--exchanges", default="all_exchange,spot_exchange,derivative_exchange")
    parser.add_argument("--external-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    external_root = resolve_onchain_cryptoquant_external_root(external_root=args.external_root)
    stablecoin_tokens = [item.strip().lower() for item in str(args.stablecoin_tokens).split(",") if item.strip()]
    reflexivity_assets = [item.strip().lower() for item in str(args.reflexivity_assets).split(",") if item.strip()]
    exchanges = [item.strip().lower() for item in str(args.exchanges).split(",") if item.strip()]
    cycle_date = datetime.now().astimezone().date().isoformat()
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / cycle_date
    report_dir.mkdir(parents=True, exist_ok=True)
    stablecoin_report_path = report_dir / "m3_2_cryptoquant_stablecoin_sync.json"
    reflexivity_report_path = report_dir / "m3_2_cryptoquant_reflexivity_sync.json"
    cycle_report_path = report_dir / "m3_2_cryptoquant_sync_cycle.json"
    stablecoin_summary = run_cryptoquant_stablecoin_sync(
        lookback_days=args.lookback_days,
        mode=args.mode,
        refresh_overlap_days=args.refresh_overlap_days,
        external_root=external_root,
        token_ids=stablecoin_tokens,
        exchanges=exchanges,
        report_path=stablecoin_report_path,
    )
    reflexivity_summary = run_cryptoquant_reflexivity_sync(
        lookback_days=args.lookback_days,
        mode=args.mode,
        refresh_overlap_days=args.refresh_overlap_days,
        external_root=external_root,
        asset_ids=reflexivity_assets,
        exchanges=exchanges,
        report_path=reflexivity_report_path,
    )
    summary = {
        "artifact_family": ARTIFACT_FAMILY,
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "success": bool(stablecoin_summary.get("success")) and bool(reflexivity_summary.get("success")),
        "external_root": str(external_root),
        "stablecoin_report_path": str(stablecoin_report_path),
        "reflexivity_report_path": str(reflexivity_report_path),
        "requested_mode": args.mode,
        "lookback_days": int(args.lookback_days),
        "refresh_overlap_days": int(args.refresh_overlap_days),
        "requested_stablecoin_tokens": stablecoin_tokens,
        "requested_reflexivity_assets": reflexivity_assets,
        "requested_exchanges": exchanges,
        "stablecoin_summary": stablecoin_summary,
        "reflexivity_summary": reflexivity_summary,
    }
    cycle_report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(str(cycle_report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
