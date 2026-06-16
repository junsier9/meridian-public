from __future__ import annotations

import argparse
import csv
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

from enhengclaw.quant_research.onchain_stablecoin import (  # noqa: E402
    DEFAULT_REFRESH_OVERLAP_DAYS,
    resolve_onchain_external_root,
    run_m3_2_stablecoin_sync,
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


ARTIFACT_FAMILY = "quant_stablecoin_ethereum_sync"
CONTRACT_VERSION = "quant_stablecoin_ethereum_sync_cycle.v2"
DEFAULT_BOOTSTRAP_LOOKBACK_DAYS = 8
DEFAULT_CYCLE_TRANSFER_PROVIDER = "eth_rpc_logs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one M3.2 stablecoin on-chain sync + overlay-candidate cycle."
    )
    parser.add_argument("--symbols", default="USDT,USDC,DAI")
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--bootstrap-lookback-days", type=int, default=DEFAULT_BOOTSTRAP_LOOKBACK_DAYS)
    parser.add_argument("--refresh-overlap-days", type=int, default=DEFAULT_REFRESH_OVERLAP_DAYS)
    parser.add_argument("--force-mode", choices=("bootstrap", "refresh"), default=None)
    parser.add_argument("--address-label-root", type=Path, default=None)
    parser.add_argument("--address-label-import-csv", action="append", default=[])
    parser.add_argument("--skip-address-label-sync", action="store_true")
    parser.add_argument(
        "--transfer-provider",
        choices=("alchemy_transfers", "eth_rpc_logs"),
        default=DEFAULT_CYCLE_TRANSFER_PROVIDER,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    external_root = resolve_onchain_external_root(external_root=args.external_root)
    symbols = [item.strip().upper() for item in str(args.symbols).split(",") if item.strip()]
    cycle_date = datetime.now().astimezone().date().isoformat()
    report_dir = ROOT / "artifacts" / "quant_research" / "factor_reports" / cycle_date
    report_dir.mkdir(parents=True, exist_ok=True)
    label_report_path = report_dir / "m3_2_ethereum_address_labels_sync.json"
    sync_report_path = report_dir / "m3_2_stablecoin_daily_task_sync.json"
    overlay_report_path = report_dir / "stablecoin_issuance_velocity_overlay_candidate.json"
    flow_overlay_report_path = report_dir / "stablecoin_flow_overlay_candidates.json"
    cycle_report_path = report_dir / "m3_2_stablecoin_daily_task_cycle.json"
    address_label_root = resolve_onchain_address_label_root(external_root=args.address_label_root)

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
            as_of_date=datetime.now().astimezone().date(),
            external_root=address_label_root,
            import_csv_paths=[Path(item) for item in args.address_label_import_csv],
            report_path=label_report_path,
        )

    effective_mode = args.force_mode or _determine_effective_mode(external_root)
    sync_summary = run_m3_2_stablecoin_sync(
        lookback_days=args.bootstrap_lookback_days,
        mode=effective_mode,
        refresh_overlap_days=args.refresh_overlap_days,
        transfer_provider=args.transfer_provider,
        external_root=external_root,
        token_symbols=symbols,
        address_label_root=address_label_root,
        address_label_snapshot_path=(
            Path(str(label_summary["latest_snapshot_path"]))
            if label_summary.get("latest_snapshot_path")
            else None
        ),
        report_path=sync_report_path,
    )
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
        "success": bool(sync_summary.get("success", False)),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "effective_mode": effective_mode,
        "bootstrap_lookback_days": int(args.bootstrap_lookback_days),
        "refresh_overlap_days": int(args.refresh_overlap_days),
        "external_root": str(external_root),
        "address_label_root": str(address_label_root),
        "requested_symbols": symbols,
        "transfer_provider": args.transfer_provider,
        "address_label_sync_report_path": str(label_report_path),
        "sync_report_path": str(sync_report_path),
        "overlay_report_path": str(overlay_report_path),
        "flow_overlay_report_path": str(flow_overlay_report_path),
        "overlay_id": DEFAULT_STABLECOIN_OVERLAY_ID,
        "sync_status": sync_summary.get("status"),
        "overlay_available": bool(overlay_summary.get("available")),
        "overlay_history_ready": bool(overlay_summary.get("history_ready", False)),
        "flow_overlay_payload": flow_overlay_payload,
        "address_label_summary": label_summary,
        "sync_summary": sync_summary,
        "overlay_summary": overlay_summary,
        "input_watermarks": dict(sync_summary.get("input_watermarks") or {}),
        "upstream_versions": {
            "selected_symbols": symbols,
            "overlay_contract_version": overlay_summary.get("contract_version"),
            "sync_contract_version": sync_summary.get("contract_version"),
        },
    }
    cycle_report_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary["report_path"] = str(cycle_report_path)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _determine_effective_mode(external_root: Path) -> str:
    output_path = external_root / "daily_aggregates.csv"
    if not output_path.exists():
        return "bootstrap"
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return "bootstrap"
        fieldnames = {str(name).strip() for name in reader.fieldnames if name}
        if "is_full_day" not in fieldnames or "fetch_status" not in fieldnames:
            return "bootstrap"
        for row in reader:
            if str(row.get("is_full_day") or "").strip().lower() in {"1", "true", "yes", "y"}:
                return "refresh"
    return "bootstrap"


if __name__ == "__main__":
    raise SystemExit(main())
