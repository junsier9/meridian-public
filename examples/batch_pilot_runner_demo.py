from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from _canonical_demo_support import ROOT, build_demo_batch_setup, resolve_demo_execution_permit
from enhengclaw.governance.provider_selection import MODE_DEFAULT, MODE_INCLUDE_SHADOW
from enhengclaw.orchestration.batch_pilot_runner import BatchPilotRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the canonical provider/snapshot replay batch through the worker-backed runtime lane."
    )
    parser.add_argument("symbols", nargs="*", default=["AIX", "BTC", "ETH"])
    parser.add_argument("--scope", default="spot+perp")
    parser.add_argument("--archive-root", default=None)
    parser.add_argument("--include-shadow", action="store_true")
    parser.add_argument("--use-live", action="store_true")
    parser.add_argument("--execution-permit", default=None)
    args = parser.parse_args()

    selection_mode = MODE_INCLUDE_SHADOW if args.include_shadow else MODE_DEFAULT
    use_live = args.use_live or os.getenv("ENABLE_REAL_CEX_PROVIDER") == "1"
    if args.archive_root is not None:
        archive_root = args.archive_root
    elif os.name == "nt":
        archive_root = "C:\\ecpb"
    else:
        archive_root = str(ROOT / "artifacts" / "pb")
    if args.execution_permit is not None and len(args.symbols) > 1:
        raise SystemExit("external execution permits are single-use; pass one symbol or omit --execution-permit")

    results = []
    for index, symbol in enumerate(args.symbols):
        slug = f"batch-pilot-runner-demo-{index + 1}"
        with resolve_demo_execution_permit(
            scope=args.scope,
            slug=slug,
            execution_permit_path=args.execution_permit,
        ) as permit:
            runner = BatchPilotRunner(
                archive_root=archive_root,
                execution_permit=permit,
                setup_factory=lambda *, symbol, scope, use_live: build_demo_batch_setup(
                    symbol=symbol,
                    scope=scope,
                    use_live=use_live,
                    include_shadow=args.include_shadow,
                ),
            )
            result = runner.run_batch(
                symbols=[symbol],
                scope=args.scope,
                selection_mode=selection_mode,
                use_live=use_live,
                execution_permit=permit,
            )
            results.append(asdict(result))

    print(
        json.dumps(
            {
                "selection_mode": selection_mode,
                "use_live": use_live,
                "batch_results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
