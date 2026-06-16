from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
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

from enhengclaw.quant_research.onchain_stablecoin import (  # noqa: E402
    resolve_onchain_external_root,
)
from enhengclaw.quant_research.onchain_address_labels import (  # noqa: E402
    resolve_onchain_address_label_root,
    sync_ethereum_address_labels,
)
from enhengclaw.quant_research.stablecoin_regime import (  # noqa: E402
    DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
    DEFAULT_STABLECOIN_OVERLAY_ID,
    DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
    stablecoin_overlay_summary,
    stablecoin_issuance_velocity_overlay_summary,
)

from backfill_stablecoin_history import main as backfill_main  # noqa: E402


ARTIFACT_FAMILY = "quant_stablecoin_ethereum_backfill"
CONTRACT_VERSION = "quant_stablecoin_ethereum_backfill.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a production M3.2 historical backfill window and refresh the overlay candidate."
    )
    parser.add_argument("--symbols", default="USDT,USDC,DAI")
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--batch-days", type=int, default=1)
    parser.add_argument("--providers", default="eth_rpc_logs,alchemy_transfers")
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--address-label-root", type=Path, default=None)
    parser.add_argument("--address-label-import-csv", action="append", default=[])
    parser.add_argument("--skip-address-label-sync", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    end_date = (
        datetime.fromisoformat(str(args.end_date)).date()
        if args.end_date
        else (datetime.now(UTC).date() - timedelta(days=1))
    )
    window_days = max(int(args.window_days), 1)
    start_date = end_date - timedelta(days=window_days - 1)
    external_root = resolve_onchain_external_root(external_root=args.external_root)
    address_label_root = resolve_onchain_address_label_root(external_root=args.address_label_root)
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / datetime.now().astimezone().date().isoformat()
    report_dir.mkdir(parents=True, exist_ok=True)
    label_report_path = report_dir / "m3_2_ethereum_address_labels_sync.json"
    backfill_report_path = report_dir / f"m3_2_stablecoin_backfill_{window_days}d.json"
    overlay_report_path = report_dir / "stablecoin_issuance_velocity_overlay_candidate.json"
    flow_overlay_report_path = report_dir / "stablecoin_flow_overlay_candidates.json"

    label_summary: dict[str, object]
    if args.skip_address_label_sync:
        label_summary = {
            "status": "skipped",
            "success": True,
            "external_root": str(address_label_root),
            "latest_snapshot_path": None,
        }
    else:
        label_summary = sync_ethereum_address_labels(
            as_of_date=end_date,
            external_root=address_label_root,
            import_csv_paths=[Path(item) for item in args.address_label_import_csv],
            report_path=label_report_path,
        )

    backfill_exit = backfill_main(
        [
            "--symbols",
            str(args.symbols),
            "--start-date",
            start_date.isoformat(),
            "--end-date",
            end_date.isoformat(),
            "--batch-days",
            str(max(int(args.batch_days), 1)),
            "--providers",
            str(args.providers),
            "--external-root",
            str(external_root),
            "--address-label-root",
            str(address_label_root),
            "--address-label-as-of-date",
            end_date.isoformat(),
            "--report-path",
            str(backfill_report_path),
        ]
        + (
            [
                "--address-label-snapshot-path",
                str(label_summary["latest_snapshot_path"]),
            ]
            if label_summary.get("latest_snapshot_path")
            else []
        )
    )
    if int(backfill_exit) != 0:
        return int(backfill_exit)

    overlay_summary = stablecoin_issuance_velocity_overlay_summary(external_root=external_root)
    overlay_report_path.write_text(
        json.dumps(overlay_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    flow_overlay_payload = {
        "overlay_ids": [
            DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
            DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
        ],
        "summaries": {
            overlay_id: stablecoin_overlay_summary(external_root=external_root, overlay_id=overlay_id)
            for overlay_id in (
                DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
                DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
            )
        },
    }
    flow_overlay_report_path.write_text(
        json.dumps(flow_overlay_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = {
        "artifact_family": ARTIFACT_FAMILY,
        "contract_version": CONTRACT_VERSION,
        "success": True,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "external_root": str(external_root),
        "address_label_root": str(address_label_root),
        "window_days": window_days,
        "start_date_utc": start_date.isoformat(),
        "end_date_utc": end_date.isoformat(),
        "providers": [item.strip().lower() for item in str(args.providers).split(",") if item.strip()],
        "requested_symbols": [item.strip().upper() for item in str(args.symbols).split(",") if item.strip()],
        "address_label_sync_report_path": str(label_report_path),
        "address_label_summary": label_summary,
        "backfill_report_path": str(backfill_report_path),
        "overlay_report_path": str(overlay_report_path),
        "flow_overlay_report_path": str(flow_overlay_report_path),
        "overlay_id": DEFAULT_STABLECOIN_OVERLAY_ID,
        "overlay_available": bool(overlay_summary.get("available")),
        "overlay_history_ready": bool(overlay_summary.get("history_ready", False)),
        "overlay_table_size": int(overlay_summary.get("overlay_table_size", 0) or 0),
        "latest_ready_signal": overlay_summary.get("latest_ready_signal"),
        "flow_overlay_payload": flow_overlay_payload,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
