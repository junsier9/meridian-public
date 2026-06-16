from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.daily_review import DailyReviewPackBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a UTC daily review pack from pilot run artifacts.")
    parser.add_argument("--date", default=None, help="UTC date in YYYY-MM-DD format; defaults to latest available day")
    parser.add_argument("--pilot-runs-root", default=str(ROOT / "artifacts" / "pilot_runs"))
    parser.add_argument("--pilot-batches-root", default=str(ROOT / "artifacts" / "pilot_batches"))
    parser.add_argument("--output-root", default=str(ROOT / "artifacts" / "daily_review_packs"))
    parser.add_argument("--markdown", action="store_true", help="Also emit a markdown summary")
    args = parser.parse_args()

    builder = DailyReviewPackBuilder(
        pilot_runs_root=args.pilot_runs_root,
        pilot_batches_root=args.pilot_batches_root,
        output_root=args.output_root,
    )
    target_date = args.date or (
        builder.latest_available_date().isoformat() if builder.latest_available_date() is not None else "1970-01-01"
    )
    result = builder.build_and_write(date_utc=target_date, write_markdown=args.markdown)

    print(
        json.dumps(
            {
                "date_utc": target_date,
                "artifacts": asdict(result.artifacts),
                "pack": asdict(result.pack),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

