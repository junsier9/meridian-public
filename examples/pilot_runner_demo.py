from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from _canonical_demo_support import build_demo_batch_setup, resolve_demo_execution_permit
from enhengclaw.core.enums import ObjectType
from enhengclaw.governance.provider_selection import MODE_DEFAULT, MODE_INCLUDE_SHADOW
from enhengclaw.orchestration.pilot_runner import PilotRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the canonical provider/snapshot single-symbol replay path through the worker-backed runtime lane."
    )
    parser.add_argument("--symbol", default=os.getenv("REAL_CEX_SYMBOL", "AIX"))
    parser.add_argument("--scope", default="spot+perp")
    parser.add_argument("--archive-root", default=None)
    parser.add_argument("--include-shadow", action="store_true")
    parser.add_argument("--use-live", action="store_true")
    parser.add_argument("--execution-permit", default=None)
    args = parser.parse_args()

    selection_mode = MODE_INCLUDE_SHADOW if args.include_shadow else MODE_DEFAULT
    use_live = args.use_live or os.getenv("ENABLE_REAL_CEX_PROVIDER") == "1"

    with resolve_demo_execution_permit(
        scope=args.scope,
        slug="pilot-runner-demo",
        execution_permit_path=args.execution_permit,
    ) as permit:
        setup = build_demo_batch_setup(
            symbol=args.symbol,
            scope=args.scope,
            use_live=use_live,
            include_shadow=args.include_shadow,
        )

        runner = PilotRunner(
            archive_root=args.archive_root,
            execution_permit=permit,
        )
        result = runner.run_once(
            subject=args.symbol,
            scope=args.scope,
            scenario=setup.scenario,
            provider_inputs=setup.provider_inputs,
            portfolio_report=setup.portfolio_report,
            provider_sources=setup.provider_sources,
            selection_mode=selection_mode,
            object_type=ObjectType.ASSET,
            execution_permit=permit,
        )

    print(
        json.dumps(
            {
                "selection_mode": selection_mode,
                "use_live": use_live,
                "provider_mode": setup.provider_mode,
                "pilot_result": asdict(result),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
