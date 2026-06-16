from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.onchain_cryptoquant import (  # noqa: E402
    _fetch_cryptoquant_series,
    _resolve_cryptoquant_api_token,
)


DEFAULT_CANDIDATE_TOKENS = (
    "usdt_eth",
    "usdt_trx",
    "usdt_tron",
    "usdt_omni",
    "usdt_sol",
    "usdt_bsc",
    "usdt_avax",
    "usdt_polygon",
    "usdt_arb",
    "usdt_arbitrum",
    "usdt_op",
    "usdt_optimism",
    "usdt_base",
    "usdt_ton",
    "usdc",
    "usdc_eth",
    "usdc_sol",
    "usdc_bsc",
    "usdc_avax",
    "usdc_polygon",
    "usdc_arb",
    "usdc_arbitrum",
    "usdc_op",
    "usdc_optimism",
    "usdc_base",
    "usdc_tron",
    "dai",
    "dai_eth",
    "dai_arb",
    "dai_arbitrum",
    "dai_op",
    "dai_optimism",
    "dai_polygon",
    "dai_base",
    "fdusd",
    "fdusd_eth",
    "busd",
    "busd_eth",
    "tusd",
    "tusd_eth",
    "usde",
    "usde_eth",
    "pyusd",
    "pyusd_eth",
    "frax",
    "frax_eth",
    "usds",
    "usds_eth",
    "susde",
    "susde_eth",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe which CryptoQuant stablecoin token ids are currently valid.")
    parser.add_argument("--tokens", default=",".join(DEFAULT_CANDIDATE_TOKENS))
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--exchange-probe", default="spot_exchange")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    access_token = _resolve_cryptoquant_api_token()
    end_date = datetime.now(UTC).date() - timedelta(days=1)
    start_date = end_date
    tokens = [item.strip().lower() for item in str(args.tokens).split(",") if item.strip()]
    valid: list[dict[str, object]] = []
    invalid: list[dict[str, object]] = []
    for token_id in tokens:
        row: dict[str, object] = {"token_id": token_id}
        try:
            supply_rows = _fetch_cryptoquant_series(
                access_token=access_token,
                path="/stablecoin/network-data/supply",
                params={"token": token_id},
                start_date=start_date,
                end_date=end_date,
            )
            row["supply_ok"] = bool(supply_rows)
            try:
                flow_rows = _fetch_cryptoquant_series(
                    access_token=access_token,
                    path="/stablecoin/exchange-flows/reserve",
                    params={"token": token_id, "exchange": str(args.exchange_probe)},
                    start_date=start_date,
                    end_date=end_date,
                )
                row["exchange_flow_ok"] = bool(flow_rows)
                row["exchange_probe"] = str(args.exchange_probe)
                row["latest_supply_date_utc"] = supply_rows[-1]["date_utc"] if supply_rows else None
                valid.append(row)
            except Exception as exc:  # noqa: BLE001
                row["exchange_flow_ok"] = False
                row["exchange_probe"] = str(args.exchange_probe)
                row["exchange_flow_error"] = str(exc)
                row["latest_supply_date_utc"] = supply_rows[-1]["date_utc"] if supply_rows else None
                valid.append(row)
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
            invalid.append(row)

    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "probe_date_utc": end_date.isoformat(),
        "candidate_count": len(tokens),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "valid_tokens": valid,
        "invalid_tokens": invalid,
    }
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
