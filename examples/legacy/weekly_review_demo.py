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

from enhengclaw.ops.weekly_review import WeeklyReviewBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a weekly review pack from daily review packs.")
    parser.add_argument("--start-date", required=True, help="UTC start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", required=True, help="UTC end date in YYYY-MM-DD format")
    parser.add_argument(
        "--daily-review-root",
        default=str(ROOT / "artifacts" / "daily_review_packs"),
    )
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "artifacts" / "weekly_review_packs"),
    )
    parser.add_argument("--markdown", action="store_true", help="Also emit a markdown summary")
    args = parser.parse_args()

    builder = WeeklyReviewBuilder(
        daily_review_packs_root=args.daily_review_root,
        output_root=args.output_root,
    )
    result = builder.build_and_write(
        start_date_utc=args.start_date,
        end_date_utc=args.end_date,
        write_markdown=args.markdown,
    )
    print(
        json.dumps(
            {
                "artifacts": asdict(result.artifacts),
                "pack": asdict(result.pack),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

