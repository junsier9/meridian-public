from __future__ import annotations

import argparse
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

from scripts.market_data.binance_1m_archive import (
    DEFAULT_MARKETS,
    DEFAULT_MONTHS,
    DEFAULT_WORKERS,
    SUPPORTED_OUTPUT_FORMATS,
    backfill_1m_archive_rest_gaps,
    discover_five_year_coverage,
    discovery_summary_path,
    download_eligible_1m_archive,
    load_discovery_summary,
    resolve_external_root,
    write_duckdb_view_sql,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and build a Binance public-archive 1m kline store for symbols "
            "with a complete rolling five-year monthly history window."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Find symbols with complete 1m monthly archive coverage.")
    _add_discovery_args(discover)

    download = subparsers.add_parser("download", help="Download eligible 1m archive partitions into the local store.")
    _add_common_store_args(download)
    download.add_argument(
        "--discovery-json",
        type=Path,
        default=None,
        help="Discovery JSON from the discover command. Defaults to the latest summary under --external-root.",
    )
    download.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Optional eligible symbols to download. Defaults to all eligible symbols in the discovery summary.",
    )
    download.add_argument(
        "--markets",
        default=",".join(DEFAULT_MARKETS),
        help="Comma-separated markets to download from the discovery summary. Defaults to spot,usdm_perp.",
    )
    download.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Optional cap for smoke runs before launching the full store build.",
    )
    download.add_argument(
        "--format",
        choices=SUPPORTED_OUTPUT_FORMATS,
        default="parquet",
        help="Partition format. Parquet is recommended for research scans.",
    )
    download.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing monthly partitions.",
    )

    backfill = subparsers.add_parser(
        "backfill-rest-gaps",
        help="Patch existing 1m archive partitions by fetching missing minutes from Binance REST klines.",
    )
    _add_common_store_args(backfill)
    backfill.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Symbols to patch, e.g. SOLUSDT XRPUSDT.",
    )
    backfill.add_argument(
        "--months",
        nargs="+",
        required=True,
        help="Monthly partitions to patch in YYYY-MM form.",
    )
    backfill.add_argument(
        "--markets",
        default="usdm_perp",
        help="Comma-separated markets to patch. Defaults to usdm_perp.",
    )
    backfill.add_argument(
        "--format",
        choices=SUPPORTED_OUTPUT_FORMATS,
        default="parquet",
        help="Partition format. Must match the existing archive store.",
    )
    backfill.add_argument(
        "--force-full-month",
        action="store_true",
        help="Fetch the full requested month instead of only missing minute ranges.",
    )
    backfill.add_argument(
        "--request-sleep-seconds",
        type=float,
        default=0.05,
        help="Sleep between paginated REST requests. Defaults to 0.05 seconds.",
    )

    duckdb = subparsers.add_parser("write-duckdb-view", help="Write DuckDB SQL for querying parquet partitions.")
    _add_common_store_args(duckdb)

    return parser


def _add_discovery_args(parser: argparse.ArgumentParser) -> None:
    _add_common_store_args(parser)
    parser.add_argument(
        "--markets",
        default=",".join(DEFAULT_MARKETS),
        help="Comma-separated markets to inspect. Defaults to spot,usdm_perp.",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=DEFAULT_MONTHS,
        help="Required complete monthly archive count. Defaults to 60.",
    )
    parser.add_argument(
        "--end-month",
        default=None,
        help="Last required complete month in YYYY-MM. Defaults to the previous UTC calendar month.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Parallel S3 listing workers for per-symbol archive coverage checks.",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help="Include archive symbols that are not currently trading in Binance exchangeInfo.",
    )
    parser.add_argument(
        "--quote-asset",
        default="USDT",
        help="Quote asset filter for active symbol discovery. Defaults to USDT.",
    )


def _add_common_store_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help=(
            "Store root. Defaults to %%LOCALAPPDATA%%\\EnhengClaw\\market_history\\binance_1m_five_year "
            "or ~/.local/share/EnhengClaw/market_history/binance_1m_five_year."
        ),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "discover":
            summary = discover_five_year_coverage(
                external_root=args.external_root,
                markets=_split_csv(args.markets, DEFAULT_MARKETS),
                months=args.months,
                end_month=args.end_month,
                active_only=not args.include_inactive,
                quote_asset=args.quote_asset,
                workers=args.workers,
            )
        elif args.command == "download":
            external_root = resolve_external_root(external_root=args.external_root)
            discovery_json = args.discovery_json or discovery_summary_path(external_root=external_root)
            discovery_summary = json.loads(discovery_json.read_text(encoding="utf-8-sig"))
            summary = download_eligible_1m_archive(
                discovery_summary=discovery_summary,
                external_root=external_root,
                symbols=args.symbols,
                markets=_split_csv(args.markets, DEFAULT_MARKETS),
                max_symbols=args.max_symbols,
                output_format=args.format,
                force=args.force,
            )
        elif args.command == "backfill-rest-gaps":
            summary = backfill_1m_archive_rest_gaps(
                external_root=resolve_external_root(external_root=args.external_root),
                symbols=args.symbols,
                months=args.months,
                markets=_split_csv(args.markets, ("usdm_perp",)),
                output_format=args.format,
                force_full_month=args.force_full_month,
                request_sleep_seconds=args.request_sleep_seconds,
            )
        elif args.command == "write-duckdb-view":
            path = write_duckdb_view_sql(external_root=resolve_external_root(external_root=args.external_root))
            summary = {"status": "success", "duckdb_view_sql_path": str(path)}
        else:
            raise ValueError(f"unsupported command: {args.command}")
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _split_csv(raw_value: str, default: tuple[str, ...]) -> tuple[str, ...]:
    values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
    return tuple(values) if values else default


if __name__ == "__main__":
    raise SystemExit(main())
