from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.claims import Claim, EvidenceRef
from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
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
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.signals import Signal
from enhengclaw.testing import RuntimeWorkerHarness, runtime_worker_harness
from enhengclaw.core.thesis import Thesis


def enter_runtime_worker(testcase: Any, *, slug: str = "test-runtime-worker", scope: str = "*") -> RuntimeWorkerHarness:
    context = runtime_worker_harness(slug=slug, scope=scope)
    harness = context.__enter__()
    testcase.addCleanup(context.__exit__, None, None, None)
    return harness


def enter_runtime_worker_class(
    testcase_cls: Any,
    *,
    slug: str = "test-runtime-worker-class",
    scope: str = "*",
) -> RuntimeWorkerHarness:
    context = runtime_worker_harness(slug=slug, scope=scope)
    harness = context.__enter__()
    testcase_cls.addClassCleanup(context.__exit__, None, None, None)
    return harness


def make_signal(
    signal_id: str,
    subject: str,
    predicate: str,
    value: str,
    claim_type: ClaimType,
    direction: Direction,
    source_family: SourceFamily,
    evidence_level: EvidenceLevel,
    confidence_hint: int,
    *,
    object_type: ObjectType = ObjectType.ASSET,
    scope: str = "global",
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY,
    fresh: bool = True,
) -> Signal:
    return Signal(
        signal_id=signal_id,
        object_type=object_type,
        subject=subject,
        predicate=predicate,
        value=value,
        claim_type=claim_type,
        direction=direction,
        source_family=source_family,
        evidence_level=evidence_level,
        confidence_hint=confidence_hint,
        scope=scope,
        time_horizon=time_horizon,
        fresh=fresh,
    )


def make_claim(
    claim_id: str,
    *,
    object_id: str = "ro-test",
    claim_type: ClaimType = ClaimType.MEASUREMENT,
    subject: str = "TEST",
    predicate: str = "predicate",
    value: str = "value",
    direction: Direction = Direction.BULLISH,
    scope: str = "global",
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY,
    source_family: SourceFamily = SourceFamily.CEX,
    confidence: int = 80,
    status: ClaimStatus = ClaimStatus.SUPPORTED,
    evidence_level: EvidenceLevel = EvidenceLevel.E4,
    fresh: bool = True,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        object_id=object_id,
        claim_type=claim_type,
        subject=subject,
        predicate=predicate,
        value=value,
        direction=direction,
        scope=scope,
        time_horizon=time_horizon,
        source_family=source_family,
        confidence=confidence,
        status=status,
        evidence=[
            EvidenceRef(
                evidence_id=f"{claim_id}:e1",
                level=evidence_level,
                source_family=source_family,
                fresh=fresh,
            )
        ],
    )


def make_research_object(
    *,
    object_id: str = "ro-test",
    object_type: ObjectType = ObjectType.ASSET,
    scope: str = "global",
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY,
    processing_state: ProcessingState = ProcessingState.CANDIDATE,
    risk_state: RiskState = RiskState.NORMAL,
    attention_score: int = 70,
) -> ResearchObject:
    return ResearchObject(
        object_id=object_id,
        object_type=object_type,
        scope=scope,
        time_horizon=time_horizon,
        processing_state=processing_state,
        risk_state=risk_state,
        attention_score=attention_score,
    )


def make_thesis(
    thesis_id: str,
    *,
    object_id: str = "ro-test",
    thesis_type: ThesisType = ThesisType.PREDICTIVE,
    direction: Direction = Direction.BULLISH,
    scope: str = "global",
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY,
    anchor_claim_ids: list[str] | None = None,
    supporting_claim_ids: list[str] | None = None,
    status: ThesisStatus = ThesisStatus.ACTIVE,
    confidence: int = 80,
    working_primary_streak: int = 0,
) -> Thesis:
    return Thesis(
        thesis_id=thesis_id,
        object_id=object_id,
        thesis_type=thesis_type,
        title=thesis_id,
        direction=direction,
        scope=scope,
        time_horizon=time_horizon,
        anchor_claim_ids=anchor_claim_ids or [],
        supporting_claim_ids=supporting_claim_ids or [],
        status=status,
        confidence=confidence,
        working_primary_streak=working_primary_streak,
        invalidation_rules=["test_rule"],
    )
