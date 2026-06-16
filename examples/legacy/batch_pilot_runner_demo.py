from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.orchestration.batch_pilot_runner import BatchPilotRunner
from enhengclaw.governance.provider_selection import MODE_DEFAULT, MODE_INCLUDE_SHADOW


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a manual batch pilot using the default runtime providers.")
    parser.add_argument("symbols", nargs="*", default=["AIX", "BTC", "ETH"])
    parser.add_argument("--scope", default="spot+perp")
    parser.add_argument("--archive-root", default=None)
    parser.add_argument("--include-shadow", action="store_true")
    parser.add_argument("--use-live", action="store_true")
    args = parser.parse_args()

    selection_mode = MODE_INCLUDE_SHADOW if args.include_shadow else MODE_DEFAULT
    use_live = args.use_live or os.getenv("ENABLE_REAL_CEX_PROVIDER") == "1"

    runner = BatchPilotRunner(archive_root=args.archive_root)
    result = runner.run_batch(
        symbols=args.symbols,
        scope=args.scope,
        selection_mode=selection_mode,
        use_live=use_live,
    )
    print(
        json.dumps(
            {
                "selection_mode": selection_mode,
                "use_live": use_live,
                "batch_result": asdict(result),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="batch-pilot-runner-demo"):
        main()

