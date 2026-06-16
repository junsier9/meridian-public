from __future__ import annotations

from dataclasses import dataclass, field

from enhengclaw.core.claims import Claim
from enhengclaw.core.conflicts import ConflictGroup
from enhengclaw.core.enums import (
    ClaimType,
    ConflictSeverity,
    Direction,
    EvidenceLevel,
    RiskState,
    ThesisStatus,
    ThesisType,
    TimeHorizon,
)
from enhengclaw.core.research_object import ResearchObject


@dataclass(slots=True)
class Thesis:
    thesis_id: str
    object_id: str
    thesis_type: ThesisType
    title: str
    direction: Direction
    scope: str
    time_horizon: TimeHorizon
    anchor_claim_ids: list[str]
    supporting_claim_ids: list[str] = field(default_factory=list)
    status: ThesisStatus = ThesisStatus.DRAFT
    confidence: int = 0
    conflict_severity: ConflictSeverity = ConflictSeverity.CLEAN
    invalidation_rules: list[str] = field(default_factory=list)
    working_primary_streak: int = 0

    def best_evidence_rank(self, claim_index: dict[str, Claim]) -> int:
        if not self.anchor_claim_ids:
            return 0
        return max(claim_index[claim_id].highest_evidence_level().rank for claim_id in self.anchor_claim_ids)

    def all_anchor_fresh(self, claim_index: dict[str, Claim]) -> bool:
        return all(claim_index[claim_id].is_fresh() for claim_id in self.anchor_claim_ids)

    def source_families(self, claim_index: dict[str, Claim]) -> set[str]:
        families: set[str] = set()
        for claim_id in self.anchor_claim_ids:
            families.update(source.value for source in claim_index[claim_id].source_families())
        return families

    def promoted_claim_count(self, claim_index: dict[str, Claim]) -> int:
        claim_ids = [*self.anchor_claim_ids, *self.supporting_claim_ids]
        return sum(1 for claim_id in claim_ids if claim_index[claim_id].status.value == "promoted")


def _group_severity_by_claim(groups: list[ConflictGroup]) -> dict[str, ConflictSeverity]:
    result: dict[str, ConflictSeverity] = {}
    for group in groups:
        for claim_id in group.claim_ids:
            current = result.get(claim_id, ConflictSeverity.CLEAN)
            if group.severity.rank > current.rank:
                result[claim_id] = group.severity
    return result


def _directional_claims(claims: list[Claim], groups: list[ConflictGroup]) -> list[Claim]:
    severities = _group_severity_by_claim(groups)
    allowed_types = {
        ClaimType.FACT,
        ClaimType.MEASUREMENT,
        ClaimType.FLOW,
        ClaimType.MARKET_STRUCTURE,
    }
    return [
        claim
        for claim in claims
        if claim.claim_type in allowed_types
        and claim.direction in {Direction.BULLISH, Direction.BEARISH}
        and claim.can_anchor(severities.get(claim.claim_id))
    ]


def _risk_claims(claims: list[Claim], groups: list[ConflictGroup]) -> list[Claim]:
    severities = _group_severity_by_claim(groups)
    return [
        claim
        for claim in claims
        if claim.claim_type in {ClaimType.RISK_FLAG, ClaimType.INVALIDATION}
        and claim.can_anchor(severities.get(claim.claim_id))
    ]


def _confidence_for_claims(claims: list[Claim]) -> int:
    if not claims:
        return 0
    return round(sum(claim.confidence for claim in claims) / len(claims))


def build_theses_for_object(
    research_object: ResearchObject,
    claims: list[Claim],
    groups: list[ConflictGroup],
) -> list[Thesis]:
    theses: list[Thesis] = []
    directional = sorted(_directional_claims(claims, groups), key=lambda claim: claim.confidence, reverse=True)
    risk_claims = sorted(_risk_claims(claims, groups), key=lambda claim: claim.confidence, reverse=True)

    bullish = [claim for claim in directional if claim.direction == Direction.BULLISH]
    bearish = [claim for claim in directional if claim.direction == Direction.BEARISH]
    dominant = bullish if len(bullish) >= len(bearish) else bearish

    if len(dominant) >= 2:
        anchors = dominant[:2]
        supporting = dominant[2:]
        direction = dominant[0].direction
        thesis = Thesis(
            thesis_id=f"{research_object.object_id}:primary",
            object_id=research_object.object_id,
            thesis_type=ThesisType.PREDICTIVE,
            title=f"{dominant[0].subject} directional thesis",
            direction=direction,
            scope=research_object.scope,
            time_horizon=research_object.time_horizon,
            anchor_claim_ids=[claim.claim_id for claim in anchors],
            supporting_claim_ids=[claim.claim_id for claim in supporting],
            status=ThesisStatus.ACTIVE,
            confidence=_confidence_for_claims(anchors + supporting),
            invalidation_rules=["anchor_evidence_stale", "risk_state_restricted", "conflict_medium_plus"],
        )
        theses.append(thesis)

    if risk_claims:
        anchors = risk_claims[:2]
        supporting = risk_claims[2:]
        thesis = Thesis(
            thesis_id=f"{research_object.object_id}:risk",
            object_id=research_object.object_id,
            thesis_type=ThesisType.RISK,
            title=f"{risk_claims[0].subject} risk thesis",
            direction=Direction.RISK,
            scope=research_object.scope,
            time_horizon=TimeHorizon.SHORT,
            anchor_claim_ids=[claim.claim_id for claim in anchors],
            supporting_claim_ids=[claim.claim_id for claim in supporting],
            status=ThesisStatus.ACTIVE,
            confidence=_confidence_for_claims(anchors + supporting),
            invalidation_rules=["risk_evidence_invalidated"],
        )
        theses.append(thesis)

    return theses


def _conflict_penalty(severity: ConflictSeverity) -> int:
    return {
        ConflictSeverity.CLEAN: 0,
        ConflictSeverity.LOW: 5,
        ConflictSeverity.MEDIUM: 15,
        ConflictSeverity.HIGH: 30,
        ConflictSeverity.CRITICAL: 1000,
    }[severity]


def _risk_penalty(risk_state: RiskState) -> int:
    return {
        RiskState.NORMAL: 0,
        RiskState.CAUTION: 10,
        RiskState.RESTRICTED: 25,
        RiskState.BLOCKED: 1000,
    }[risk_state]


def thesis_priority_score(thesis: Thesis, claim_index: dict[str, Claim], risk_state: RiskState) -> int:
    if thesis.best_evidence_rank(claim_index) == 0 or not thesis.all_anchor_fresh(claim_index):
        return -10_000
    freshness_bonus = 10
    evidence_bonus = 15 if thesis.best_evidence_rank(claim_index) >= EvidenceLevel.E5.rank else 10 if thesis.best_evidence_rank(claim_index) >= EvidenceLevel.E4.rank else 0
    return thesis.confidence + freshness_bonus + evidence_bonus - _conflict_penalty(thesis.conflict_severity) - _risk_penalty(risk_state)


def _time_overlap(left: TimeHorizon, right: TimeHorizon) -> float:
    if left == right:
        return 1.0
    adjacent_pairs = {
        (TimeHorizon.INTRADAY, TimeHorizon.SHORT),
        (TimeHorizon.SHORT, TimeHorizon.MEDIUM),
        (TimeHorizon.MEDIUM, TimeHorizon.STRUCTURAL),
    }
    if (left, right) in adjacent_pairs or (right, left) in adjacent_pairs:
        return 0.4
    return 0.0


def evaluate_thesis_conflict(primary: Thesis, opposing: Thesis | None, claim_index: dict[str, Claim], risk_state: RiskState) -> ConflictSeverity:
    if opposing is None:
        return ConflictSeverity.CLEAN
    overlap = _time_overlap(primary.time_horizon, opposing.time_horizon)
    evidence_gap = abs(primary.best_evidence_rank(claim_index) - opposing.best_evidence_rank(claim_index))

    if overlap < 0.25:
        return ConflictSeverity.MEDIUM if risk_state == RiskState.RESTRICTED else ConflictSeverity.LOW
    if opposing.thesis_type == ThesisType.RISK and risk_state == RiskState.RESTRICTED:
        if primary.best_evidence_rank(claim_index) >= EvidenceLevel.E4.rank and opposing.best_evidence_rank(claim_index) >= EvidenceLevel.E4.rank:
            return ConflictSeverity.HIGH if evidence_gap <= 1 else ConflictSeverity.MEDIUM
        return ConflictSeverity.MEDIUM
    if primary.direction != opposing.direction and overlap >= 0.5:
        return ConflictSeverity.HIGH if evidence_gap <= 1 else ConflictSeverity.MEDIUM
    return ConflictSeverity.LOW


def select_working_theses(
    research_object: ResearchObject,
    theses: list[Thesis],
    claim_index: dict[str, Claim],
) -> tuple[Thesis | None, Thesis | None]:
    research_object.working_primary_thesis_id = None
    research_object.working_opposing_thesis_id = None
    eligible = [
        thesis
        for thesis in theses
        if thesis.status in {
            ThesisStatus.ACTIVE,
            ThesisStatus.CHALLENGED,
            ThesisStatus.PUBLISHABLE,
            ThesisStatus.PUBLISHED,
            ThesisStatus.MONITORING,
        }
        and thesis.best_evidence_rank(claim_index) > 0
        and thesis.conflict_severity != ConflictSeverity.CRITICAL
    ]
    if not eligible:
        return None, None

    risk_thesis = next((thesis for thesis in eligible if thesis.thesis_type == ThesisType.RISK), None)
    directional = [thesis for thesis in eligible if thesis.thesis_type != ThesisType.RISK]
    directional.sort(key=lambda thesis: thesis_priority_score(thesis, claim_index, research_object.risk_state), reverse=True)

    working_primary = directional[0] if directional else risk_thesis
    working_opposing: Thesis | None = None

    if risk_thesis is not None and working_primary is not None and risk_thesis.thesis_id != working_primary.thesis_id:
        risk_conflict = evaluate_thesis_conflict(working_primary, risk_thesis, claim_index, research_object.risk_state)
        risk_thesis.conflict_severity = risk_conflict
        if research_object.risk_state == RiskState.RESTRICTED and risk_thesis.best_evidence_rank(claim_index) >= EvidenceLevel.E4.rank:
            working_opposing = working_primary
            working_primary = risk_thesis
        elif risk_conflict.rank >= ConflictSeverity.MEDIUM.rank:
            working_opposing = risk_thesis

    if working_primary is not None:
        research_object.working_primary_thesis_id = working_primary.thesis_id
        working_primary.working_primary_streak += 1

    if working_opposing is not None:
        research_object.working_opposing_thesis_id = working_opposing.thesis_id

    return working_primary, working_opposing
