from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ObjectType
from enhengclaw.adapters.mock_adapters import (
    MockCEXMarketAdapter,
    MockInfoflowAdapter,
    MockOnchainFlowAdapter,
    MockSafetyRiskAdapter,
)
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator


def _serialize_adapter_result(adapter_result):
    runtime_result = adapter_result.runtime_result
    return {
        "adapter_request": {
            "object_id": adapter_result.adapter_request.object_id,
            "object_type": adapter_result.adapter_request.object_type.value,
            "subject": adapter_result.adapter_request.subject,
            "scope": adapter_result.adapter_request.scope,
            "scenario": adapter_result.adapter_request.scenario,
        },
        "adapter_outputs": [
            {
                "adapter_name": batch.adapter_name,
                "source_family": batch.source_family.value,
                "source_metadata": batch.source_metadata,
                "retrieval_timestamp": batch.retrieval_timestamp.isoformat(),
                "normalized_signals": [
                    {
                        "signal_id": signal.signal_id,
                        "predicate": signal.predicate,
                        "claim_type": signal.claim_type.value,
                        "direction": signal.direction.value,
                        "evidence_level": signal.evidence_level.value,
                        "confidence_hint": signal.confidence_hint,
                    }
                    for signal in batch.signals
                ],
            }
            for batch in adapter_result.adapter_batches
        ],
        "runtime_result": {
            "object_id": runtime_result.research_object.object_id,
            "processing_state": runtime_result.research_object.processing_state.value,
            "risk_state": runtime_result.research_object.risk_state.value,
            "market_state": runtime_result.research_object.market_state.value,
            "attention_score": runtime_result.research_object.attention_score,
            "working_primary_thesis_id": runtime_result.research_object.working_primary_thesis_id,
            "working_opposing_thesis_id": runtime_result.research_object.working_opposing_thesis_id,
            "decision": runtime_result.decision.decision,
            "decision_reasons": runtime_result.decision.reasons,
            "cadence": {
                "mode": runtime_result.cadence.mode,
                "normal_review_after": None
                if runtime_result.cadence.normal_review_after is None
                else str(runtime_result.cadence.normal_review_after),
                "deep_review_after": None
                if runtime_result.cadence.deep_review_after is None
                else str(runtime_result.cadence.deep_review_after),
            },
            "allocation": None
            if runtime_result.resource_allocation is None
            else {
                "tier": runtime_result.resource_allocation.tier.value,
                "slot_type": runtime_result.resource_allocation.slot_type.value,
            },
        },
    }


def main() -> None:
    adapters = [
        MockCEXMarketAdapter(),
        MockOnchainFlowAdapter(),
        MockSafetyRiskAdapter(),
        MockInfoflowAdapter(),
    ]
    orchestrator = RuntimeOrchestrator()

    bullish = orchestrator.run_new_from_adapters(
        object_id="adapter-demo-bullish",
        object_type=ObjectType.ASSET,
        subject="AIX",
        scope="spot+perp",
        scenario="bullish_publish",
        adapters=adapters,
    )
    restricted = orchestrator.run_new_from_adapters(
        object_id="adapter-demo-restricted",
        object_type=ObjectType.ASSET,
        subject="ORBX",
        scope="bridge",
        scenario="restricted_monitoring",
        adapters=adapters,
    )
    seeded = orchestrator.run_new_from_adapters(
        object_id="adapter-demo-blocked",
        object_type=ObjectType.ASSET,
        subject="VRTX",
        scope="spot+perp",
        scenario="bullish_publish",
        adapters=adapters,
    )
    blocked = orchestrator.continue_existing_from_adapters(
        object_id="adapter-demo-blocked",
        subject="VRTX",
        scenario="blocked_risk",
        adapters=adapters,
    )

    payload = {
        "runs": [
            _serialize_adapter_result(bullish),
            _serialize_adapter_result(restricted),
            {
                "phase": "seed_for_blocked",
                **_serialize_adapter_result(seeded),
            },
            {
                "phase": "blocked_resume",
                **_serialize_adapter_result(blocked),
            },
        ]
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    from enhengclaw.testing import runtime_worker_harness

    with runtime_worker_harness(slug="mock-adapter-demo"):
        main()

