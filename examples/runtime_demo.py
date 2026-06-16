from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.core.signals import Signal
from enhengclaw.testing import runtime_worker_harness


def build_demo_signals() -> list[Signal]:
    return [
        Signal(
            signal_id="s1",
            object_type=ObjectType.ASSET,
            subject="AIX",
            predicate="spot_breakout",
            value="spot volume expansion with price strength",
            claim_type=ClaimType.MEASUREMENT,
            direction=Direction.BULLISH,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=82,
            time_horizon=TimeHorizon.INTRADAY,
        ),
        Signal(
            signal_id="s2",
            object_type=ObjectType.ASSET,
            subject="AIX",
            predicate="smart_money_accumulation",
            value="smart money wallets are net buying",
            claim_type=ClaimType.FLOW,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=78,
            time_horizon=TimeHorizon.INTRADAY,
        ),
        Signal(
            signal_id="s3",
            object_type=ObjectType.ASSET,
            subject="AIX",
            predicate="market_structure_support",
            value="spot is leading perps, structure remains constructive",
            claim_type=ClaimType.MARKET_STRUCTURE,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ANALYTICS,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=75,
            time_horizon=TimeHorizon.INTRADAY,
        ),
        Signal(
            signal_id="s4",
            object_type=ObjectType.ASSET,
            subject="AIX",
            predicate="overheating_risk",
            value="funding is elevated and leverage is building",
            claim_type=ClaimType.RISK_FLAG,
            direction=Direction.RISK,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E3,
            confidence_hint=66,
            time_horizon=TimeHorizon.SHORT,
        ),
    ]


def main() -> None:
    with runtime_worker_harness(slug="runtime-demo"):
        orchestrator = RuntimeOrchestrator()
        result = orchestrator.run(
            object_id="ro-runtime-demo",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=build_demo_signals(),
        )

        payload = {
            "execution_trace": [step.as_dict() for step in result.steps],
            "final_object": {
                "object_id": result.research_object.object_id,
                "processing_state": result.research_object.processing_state.value,
                "risk_state": result.research_object.risk_state.value,
                "market_state": result.research_object.market_state.value,
                "attention_score": result.research_object.attention_score,
                "working_primary_thesis_id": result.research_object.working_primary_thesis_id,
                "working_opposing_thesis_id": result.research_object.working_opposing_thesis_id,
            },
            "theses": [
                {
                    "thesis_id": thesis.thesis_id,
                    "type": thesis.thesis_type.value,
                    "status": thesis.status.value,
                    "confidence": thesis.confidence,
                    "conflict_severity": thesis.conflict_severity.value,
                    "primary_streak": thesis.working_primary_streak,
                    "anchors": thesis.anchor_claim_ids,
                    "supporting": thesis.supporting_claim_ids,
                }
                for thesis in result.theses
            ],
            "decision": {
                "decision": result.decision.decision,
                "reasons": result.decision.reasons,
            },
            "cadence": {
                "mode": result.cadence.mode,
                "normal_review_after": None if result.cadence.normal_review_after is None else str(result.cadence.normal_review_after),
                "deep_review_after": None if result.cadence.deep_review_after is None else str(result.cadence.deep_review_after),
            },
            "allocation": None
            if result.resource_allocation is None
            else {
                "tier": result.resource_allocation.tier.value,
                "slot_type": result.resource_allocation.slot_type.value,
            },
        }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

