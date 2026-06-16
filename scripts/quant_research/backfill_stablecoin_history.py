from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.onchain_stablecoin import (  # noqa: E402
    DEFAULT_TRANSFER_PROVIDER,
    resolve_onchain_external_root,
    run_m3_2_stablecoin_sync,
)


ARTIFACT_FAMILY = "m3_2_stablecoin_history_backfill"
CONTRACT_VERSION = "m3_2_stablecoin_history_backfill.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill M3.2 Ethereum stablecoin history in small explicit date batches."
    )
    parser.add_argument("--symbols", default="USDT,USDC,DAI")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--batch-days", type=int, default=2)
    parser.add_argument(
        "--providers",
        default=f"eth_rpc_logs,{DEFAULT_TRANSFER_PROVIDER}",
        help="Comma-separated provider preference order. Supported: eth_rpc_logs, alchemy_transfers",
    )
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--address-label-root", type=Path, default=None)
    parser.add_argument("--address-label-snapshot-path", type=Path, default=None)
    parser.add_argument("--address-label-as-of-date", type=date.fromisoformat, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.start_date > args.end_date:
        raise SystemExit("start-date must be <= end-date")
    providers = [item.strip().lower() for item in str(args.providers).split(",") if item.strip()]
    if not providers:
        raise SystemExit("at least one provider is required")
    symbols = [item.strip().upper() for item in str(args.symbols).split(",") if item.strip()]
    external_root = resolve_onchain_external_root(external_root=args.external_root)

    batch_days = max(int(args.batch_days), 1)
    started_at = time.perf_counter()
    batches: list[dict[str, object]] = []
    current = args.start_date
    while current <= args.end_date:
        batch_end = min(args.end_date, current + timedelta(days=batch_days - 1))
        batch_summary = _run_batch(
            start_date=current,
            end_date=batch_end,
            providers=providers,
            external_root=external_root,
            symbols=symbols,
            address_label_root=args.address_label_root,
            address_label_snapshot_path=args.address_label_snapshot_path,
            address_label_as_of_date=args.address_label_as_of_date,
        )
        batches.append(batch_summary)
        current = batch_end + timedelta(days=1)

    success = all(bool(batch.get("success")) for batch in batches)
    summary = {
        "artifact_family": ARTIFACT_FAMILY,
        "contract_version": CONTRACT_VERSION,
        "success": success,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "external_root": str(external_root),
        "requested_symbols": symbols,
        "requested_providers": providers,
        "start_date_utc": args.start_date.isoformat(),
        "end_date_utc": args.end_date.isoformat(),
        "batch_days": batch_days,
        "batch_count": len(batches),
        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        "batches": batches,
    }
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        summary["report_path"] = str(args.report_path)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if success else 1


def _run_batch(
    *,
    start_date: date,
    end_date: date,
    providers: list[str],
    external_root: Path,
    symbols: list[str],
    address_label_root: Path | None,
    address_label_snapshot_path: Path | None,
    address_label_as_of_date: date | None,
) -> dict[str, object]:
    attempts: list[dict[str, object]] = []
    started_at = time.perf_counter()
    for provider in providers:
        attempt_started = time.perf_counter()
        try:
            summary = run_m3_2_stablecoin_sync(
                mode="bootstrap",
                lookback_days=1,
                transfer_provider=provider,
                external_root=external_root,
                token_symbols=symbols,
                start_date_override=start_date,
                end_date_override=end_date,
                address_label_root=address_label_root,
                address_label_snapshot_path=address_label_snapshot_path,
                address_label_as_of_date=address_label_as_of_date,
            )
        except Exception as exc:
            attempts.append(
                {
                    "provider": provider,
                    "success": False,
                    "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                    "error": str(exc),
                }
            )
            continue
        attempts.append(
            {
                "provider": provider,
                "success": True,
                "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                "status": summary.get("status"),
                "stored_row_count": summary.get("stored_row_count"),
                "written_row_count": summary.get("written_row_count"),
                "summary_path": summary.get("report_path") or summary.get("latest_summary_path"),
            }
        )
        return {
            "success": True,
            "selected_provider": provider,
            "start_date_utc": start_date.isoformat(),
            "end_date_utc": end_date.isoformat(),
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            "attempts": attempts,
        }
    return {
        "success": False,
        "selected_provider": None,
        "start_date_utc": start_date.isoformat(),
        "end_date_utc": end_date.isoformat(),
        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        "attempts": attempts,
    }


if __name__ == "__main__":
    raise SystemExit(main())
