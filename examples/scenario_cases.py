from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.claims import Claim
from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
    ConflictSeverity,
    Direction,
    EvidenceLevel,
    ObjectType,
    ProcessingState,
    RiskState,
    SourceFamily,
    ThesisStatus,
    ThesisType,
    TimeHorizon,
)
from enhengclaw.core.publish_gate import PublishGate
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.signals import Signal
from enhengclaw.core.state_machine import StateMachine
from enhengclaw.core.thesis import Thesis, select_working_theses
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness


def _claim(
    claim_id: str,
    *,
    object_id: str = "ro-demo",
    claim_type: ClaimType = ClaimType.MEASUREMENT,
    subject: str = "DEMO",
    predicate: str = "predicate",
    value: str = "value",
    direction: Direction = Direction.BULLISH,
    source_family: SourceFamily = SourceFamily.CEX,
    evidence_level: EvidenceLevel = EvidenceLevel.E4,
    confidence: int = 80,
    status: ClaimStatus = ClaimStatus.PROMOTED,
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY,
) -> Claim:
    from enhengclaw.core.claims import EvidenceRef

    return Claim(
        claim_id=claim_id,
        object_id=object_id,
        claim_type=claim_type,
        subject=subject,
        predicate=predicate,
        value=value,
        direction=direction,
        scope="global",
        time_horizon=time_horizon,
        source_family=source_family,
        confidence=confidence,
        status=status,
        evidence=[EvidenceRef(f"{claim_id}:e1", evidence_level, source_family, True)],
    )


def _serialize_engine_result(name: str, result) -> dict:
    return {
        "scenario": name,
        "processing_state": result.research_object.processing_state.value,
        "risk_state": result.research_object.risk_state.value,
        "market_state": result.research_object.market_state.value,
        "attention_score": result.research_object.attention_score,
        "decision": result.decision.decision,
        "decision_reasons": result.decision.reasons,
        "working_primary_thesis_id": result.research_object.working_primary_thesis_id,
        "working_opposing_thesis_id": result.research_object.working_opposing_thesis_id,
        "cadence_mode": result.cadence.mode,
    }


def success_publish() -> dict:
    engine = RuntimeOrchestrator()
    signals = [
        Signal("s1", ObjectType.ASSET, "AIX", "spot_breakout", "spot volume expansion", ClaimType.MEASUREMENT, Direction.BULLISH, SourceFamily.CEX, EvidenceLevel.E4, 82),
        Signal("s2", ObjectType.ASSET, "AIX", "smart_money_accumulation", "smart money buying", ClaimType.FLOW, Direction.BULLISH, SourceFamily.ONCHAIN, EvidenceLevel.E4, 78),
        Signal("s3", ObjectType.ASSET, "AIX", "market_structure_support", "spot leads perps", ClaimType.MARKET_STRUCTURE, Direction.BULLISH, SourceFamily.ANALYTICS, EvidenceLevel.E4, 75),
        Signal("s4", ObjectType.ASSET, "AIX", "overheating_risk", "funding is elevated", ClaimType.RISK_FLAG, Direction.RISK, SourceFamily.CEX, EvidenceLevel.E3, 66, time_horizon=TimeHorizon.SHORT),
    ]
    result = engine.run("ro-aix-success", ObjectType.ASSET, "spot+perp", signals)
    return _serialize_engine_result("success_publish", result)


def risk_thesis_blocked() -> dict:
    research_object = ResearchObject(
        object_id="ro-vrtx-blocked",
        object_type=ObjectType.ASSET,
        scope="bridge",
        time_horizon=TimeHorizon.SHORT,
        processing_state=ProcessingState.BLOCKED,
        risk_state=RiskState.BLOCKED,
        attention_score=22,
    )
    claim_index = {
        "b1": _claim("b1", object_id=research_object.object_id, predicate="spot_breakout", source_family=SourceFamily.CEX),
        "b2": _claim("b2", object_id=research_object.object_id, predicate="smart_money", claim_type=ClaimType.FLOW, source_family=SourceFamily.ONCHAIN),
        "r1": _claim(
            "r1",
            object_id=research_object.object_id,
            claim_type=ClaimType.RISK_FLAG,
            predicate="bridge_compromise",
            direction=Direction.RISK,
            source_family=SourceFamily.SAFETY,
            evidence_level=EvidenceLevel.E5,
            confidence=90,
        ),
    }
    predictive = Thesis(
        thesis_id="t-bull",
        object_id=research_object.object_id,
        thesis_type=ThesisType.PREDICTIVE,
        title="directional thesis",
        direction=Direction.BULLISH,
        scope="bridge",
        time_horizon=TimeHorizon.SHORT,
        anchor_claim_ids=["b1", "b2"],
        status=ThesisStatus.INVALIDATED,
        confidence=78,
        invalidation_rules=["bridge_compromise"],
    )
    risk = Thesis(
        thesis_id="t-risk",
        object_id=research_object.object_id,
        thesis_type=ThesisType.RISK,
        title="risk thesis",
        direction=Direction.RISK,
        scope="bridge",
        time_horizon=TimeHorizon.SHORT,
        anchor_claim_ids=["r1"],
        status=ThesisStatus.ACTIVE,
        confidence=90,
        invalidation_rules=["risk_evidence_invalidated"],
    )
    working_primary, _ = select_working_theses(research_object, [predictive, risk], claim_index)
    decision = PublishGate().evaluate(research_object, working_primary, None, claim_index)
    return {
        "scenario": "risk_thesis_blocked",
        "processing_state": research_object.processing_state.value,
        "risk_state": research_object.risk_state.value,
        "working_primary_thesis_id": None if working_primary is None else working_primary.thesis_id,
        "decision": decision.decision,
        "decision_reasons": decision.reasons,
    }


def restricted_monitoring() -> dict:
    engine = RuntimeOrchestrator()
    signals = [
        Signal("s1", ObjectType.ASSET, "ORBX", "spot_breakout", "spot leads move", ClaimType.MEASUREMENT, Direction.BULLISH, SourceFamily.CEX, EvidenceLevel.E4, 80),
        Signal("s2", ObjectType.ASSET, "ORBX", "smart_money_buy", "smart money accumulates", ClaimType.FLOW, Direction.BULLISH, SourceFamily.ONCHAIN, EvidenceLevel.E4, 72),
        Signal("s3", ObjectType.ASSET, "ORBX", "bridge_risk", "unusual upgrade observed", ClaimType.RISK_FLAG, Direction.RISK, SourceFamily.SAFETY, EvidenceLevel.E4, 67, time_horizon=TimeHorizon.SHORT),
    ]
    result = engine.run("ro-orbx-restricted", ObjectType.ASSET, "bridge", signals)
    return _serialize_engine_result("restricted_monitoring", result)


def screened_to_archived() -> dict:
    machine = StateMachine()
    research_object = ResearchObject(
        object_id="ro-screened-archive",
        object_type=ObjectType.PROJECT,
        scope="global",
        time_horizon=TimeHorizon.SHORT,
        processing_state=ProcessingState.SCREENED,
        risk_state=RiskState.NORMAL,
        attention_score=25,
    )
    machine.begin_cycle(research_object)
    machine.transition_processing(research_object, ProcessingState.ARCHIVED)
    return {
        "scenario": "screened_to_archived",
        "processing_state": research_object.processing_state.value,
        "risk_state": research_object.risk_state.value,
        "attention_score": research_object.attention_score,
        "decision": "archived",
        "decision_reasons": ["screened attention below threshold"],
    }


def predictive_streak_insufficient() -> dict:
    research_object = ResearchObject(
        object_id="ro-streak",
        object_type=ObjectType.ASSET,
        scope="spot+perp",
        time_horizon=TimeHorizon.INTRADAY,
        processing_state=ProcessingState.PUBLISH_READY,
        risk_state=RiskState.CAUTION,
        attention_score=74,
    )
    claim_index = {
        "a1": _claim("a1", object_id=research_object.object_id, predicate="spot_breakout", source_family=SourceFamily.CEX),
        "a2": _claim("a2", object_id=research_object.object_id, predicate="wallet_buy", claim_type=ClaimType.FLOW, source_family=SourceFamily.ONCHAIN),
        "a3": _claim("a3", object_id=research_object.object_id, predicate="structure", claim_type=ClaimType.MARKET_STRUCTURE, source_family=SourceFamily.ANALYTICS),
    }
    thesis = Thesis(
        thesis_id="t-streak",
        object_id=research_object.object_id,
        thesis_type=ThesisType.PREDICTIVE,
        title="predictive thesis",
        direction=Direction.BULLISH,
        scope="spot+perp",
        time_horizon=TimeHorizon.INTRADAY,
        anchor_claim_ids=["a1", "a2"],
        supporting_claim_ids=["a3"],
        status=ThesisStatus.PUBLISHABLE,
        confidence=79,
        working_primary_streak=1,
        invalidation_rules=["risk_state_restricted"],
    )
    decision = PublishGate().evaluate(research_object, thesis, None, claim_index)
    return {
        "scenario": "predictive_streak_insufficient",
        "processing_state": research_object.processing_state.value,
        "risk_state": research_object.risk_state.value,
        "decision": decision.decision,
        "decision_reasons": decision.reasons,
    }


def all_scenarios() -> list[dict]:
    return [
        success_publish(),
        risk_thesis_blocked(),
        restricted_monitoring(),
        screened_to_archived(),
        predictive_streak_insufficient(),
    ]


def main() -> None:
    with runtime_worker_harness(slug="scenario-cases"):
        print(json.dumps(all_scenarios(), indent=2))


if __name__ == "__main__":
    main()

