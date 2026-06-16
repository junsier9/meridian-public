from __future__ import annotations

import argparse
from datetime import date, datetime
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

from enhengclaw.quant_research.onchain_address_labels import (  # noqa: E402
    resolve_onchain_address_label_root,
    sync_ethereum_address_labels,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a PIT-safe Ethereum address-label snapshot for M3.2 Phase 2."
    )
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=None)
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--import-csv", action="append", default=[])
    parser.add_argument("--no-seed", action="store_true")
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = args.as_of_date or datetime.now().astimezone().date()
    external_root = resolve_onchain_address_label_root(external_root=args.external_root)
    try:
        summary = sync_ethereum_address_labels(
            as_of_date=target_date,
            external_root=external_root,
            import_csv_paths=[Path(item) for item in args.import_csv],
            include_seed=not bool(args.no_seed),
            report_path=args.report_path,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
