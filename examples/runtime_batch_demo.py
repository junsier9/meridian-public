from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.resources import ResourceAllocator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator, RuntimeRunRequest
from enhengclaw.core.signals import Signal
from enhengclaw.testing import runtime_worker_harness


def bullish(prefix: str, subject: str) -> list[Signal]:
    return [
        Signal(f"{prefix}-1", ObjectType.ASSET, subject, "spot_breakout", "spot volume expansion", ClaimType.MEASUREMENT, Direction.BULLISH, SourceFamily.CEX, EvidenceLevel.E4, 82),
        Signal(f"{prefix}-2", ObjectType.ASSET, subject, "wallet_buy", "smart money buying", ClaimType.FLOW, Direction.BULLISH, SourceFamily.ONCHAIN, EvidenceLevel.E4, 78),
        Signal(f"{prefix}-3", ObjectType.ASSET, subject, "structure_support", "spot leads perps", ClaimType.MARKET_STRUCTURE, Direction.BULLISH, SourceFamily.ANALYTICS, EvidenceLevel.E4, 75),
    ]


def risk(prefix: str, subject: str) -> Signal:
    return Signal(
        f"{prefix}-risk",
        ObjectType.ASSET,
        subject,
        "bridge_risk",
        "unusual bridge activity",
        ClaimType.RISK_FLAG,
        Direction.RISK,
        SourceFamily.SAFETY,
        EvidenceLevel.E4,
        68,
        time_horizon=TimeHorizon.SHORT,
    )


def main() -> None:
    with runtime_worker_harness(slug="runtime-batch-demo"):
        orchestrator = RuntimeOrchestrator(
            resource_allocator=ResourceAllocator(
                hot_objects_limit=2,
                deep_limit=1,
                conflict_limit=1,
                publish_limit=1,
                monitoring_limit=1,
            )
        )
        results = orchestrator.run_batch(
            [
                RuntimeRunRequest(
                    mode="create",
                    object_id="batch-aix",
                    object_type=ObjectType.ASSET,
                    scope="spot+perp",
                    signals=bullish("aix", "AIX"),
                ),
                RuntimeRunRequest(
                    mode="create",
                    object_id="batch-orbx",
                    object_type=ObjectType.ASSET,
                    scope="bridge",
                    signals=[*bullish("orbx", "ORBX"), risk("orbx", "ORBX")],
                ),
                RuntimeRunRequest(
                    mode="create",
                    object_id="batch-weak",
                    object_type=ObjectType.PROJECT,
                    scope="global",
                    signals=[
                        Signal(
                            "weak-1",
                            ObjectType.PROJECT,
                            "WEAK",
                            "rumor",
                            "weak rumor",
                            ClaimType.CAUSAL,
                            Direction.NEUTRAL,
                            SourceFamily.INFOFLOW,
                            EvidenceLevel.E2,
                            30,
                        )
                    ],
                ),
            ]
        )

        payload = []
        for result in results:
            payload.append(
                {
                    "object_id": result.research_object.object_id,
                    "processing_state": result.research_object.processing_state.value,
                    "risk_state": result.research_object.risk_state.value,
                    "attention_score": result.research_object.attention_score,
                    "decision": result.decision.decision,
                    "allocation": None
                    if result.resource_allocation is None
                    else {
                        "tier": result.resource_allocation.tier.value,
                        "slot_type": result.resource_allocation.slot_type.value,
                    },
                    "last_step": result.steps[-1].step,
                }
            )

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

