from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import CAP_PROVIDER_FETCH, CAP_RUNTIME_EXECUTE
from enhengclaw.core.enums import ObjectType
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator
from enhengclaw.testing.execution_testbed import execution_testbed, sample_signals


def main() -> int:
    with execution_testbed() as bed:
        _, permit = bed.issue_permit(
            slug="phase1",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE, CAP_PROVIDER_FETCH],
            allowed_operations=["runtime.*", "provider.*"],
        )
        orchestrator = RuntimeOrchestrator(execution_permit=permit)
        result = orchestrator.run_new(
            object_id="phase1-worker",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=sample_signals("phase1"),
        )
        if result.decision.decision not in {"publish", "monitoring"}:
            raise AssertionError(f"unexpected runtime decision: {result.decision.decision}")
        try:
            orchestrator._run_new_impl(
                object_id="phase1-direct-kernel",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=sample_signals("phase1-direct"),
            )
        except RuntimeBoundaryError:
            return 0
        raise AssertionError("controller was able to call _run_new_impl directly")


if __name__ == "__main__":
    raise SystemExit(main())
