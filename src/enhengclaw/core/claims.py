from __future__ import annotations

from dataclasses import dataclass, field

from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
    ConflictSeverity,
    Direction,
    EvidenceLevel,
    SourceFamily,
    TimeHorizon,
)
from enhengclaw.core.signals import Signal


@dataclass(slots=True)
class EvidenceRef:
    evidence_id: str
    level: EvidenceLevel
    source_family: SourceFamily
    fresh: bool = True


@dataclass(slots=True)
class Claim:
    claim_id: str
    object_id: str
    claim_type: ClaimType
    subject: str
    predicate: str
    value: str
    direction: Direction
    scope: str
    time_horizon: TimeHorizon
    source_family: SourceFamily
    confidence: int
    status: ClaimStatus
    evidence: list[EvidenceRef] = field(default_factory=list)
    conflict_group_id: str | None = None

    def highest_evidence_level(self) -> EvidenceLevel:
        if not self.evidence:
            return EvidenceLevel.E1
        return max((ref.level for ref in self.evidence), key=lambda level: level.rank)

    def is_fresh(self) -> bool:
        return all(ref.fresh for ref in self.evidence) if self.evidence else False

    def source_families(self) -> set[SourceFamily]:
        return {ref.source_family for ref in self.evidence} | {self.source_family}

    def add_evidence(self, evidence: EvidenceRef) -> None:
        self.evidence.append(evidence)
        if self.status == ClaimStatus.PROPOSED and evidence.level.rank >= EvidenceLevel.E3.rank:
            self.status = ClaimStatus.GROUNDED

    def advance_basic_status(self) -> None:
        if self.status in {ClaimStatus.INVALIDATED, ClaimStatus.ARCHIVED}:
            return
        highest_level = self.highest_evidence_level()
        if highest_level.rank < EvidenceLevel.E3.rank:
            self.status = ClaimStatus.PROPOSED
            return
        if not self.is_fresh():
            self.status = ClaimStatus.STALE
            return
        if self.confidence >= 60:
            if self.status in {ClaimStatus.PROPOSED, ClaimStatus.GROUNDED}:
                self.status = ClaimStatus.SUPPORTED
        elif self.status == ClaimStatus.PROPOSED:
            self.status = ClaimStatus.GROUNDED

    def mark_contested(self) -> None:
        if self.status not in {ClaimStatus.INVALIDATED, ClaimStatus.ARCHIVED}:
            self.status = ClaimStatus.CONTESTED

    def mark_invalidated(self) -> None:
        self.status = ClaimStatus.INVALIDATED

    def promote(self) -> None:
        if self.status == ClaimStatus.SUPPORTED:
            self.status = ClaimStatus.PROMOTED

    def can_anchor(self, group_severity: ConflictSeverity | None) -> bool:
        if self.status not in {ClaimStatus.SUPPORTED, ClaimStatus.PROMOTED}:
            return False
        if not self.is_fresh():
            return False
        if group_severity is None:
            return True
        return group_severity.rank <= ConflictSeverity.LOW.rank


def claim_from_signal(signal: Signal, object_id: str, claim_id: str) -> Claim:
    status = ClaimStatus.GROUNDED if signal.evidence_level.rank >= EvidenceLevel.E3.rank else ClaimStatus.PROPOSED
    evidence = [
        EvidenceRef(
            evidence_id=f"{signal.signal_id}:e1",
            level=signal.evidence_level,
            source_family=signal.source_family,
            fresh=signal.fresh,
        )
    ]
    claim = Claim(
        claim_id=claim_id,
        object_id=object_id,
        claim_type=signal.claim_type,
        subject=signal.subject,
        predicate=signal.predicate,
        value=signal.value,
        direction=signal.direction,
        scope=signal.scope,
        time_horizon=signal.time_horizon,
        source_family=signal.source_family,
        confidence=max(0, min(signal.confidence_hint, 100)),
        status=status,
        evidence=evidence,
    )
    claim.advance_basic_status()
    return claim
