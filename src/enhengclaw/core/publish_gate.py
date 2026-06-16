from __future__ import annotations

from dataclasses import dataclass, field

from enhengclaw.core.claims import Claim
from enhengclaw.core.enums import ClaimType, ConflictSeverity, ProcessingState, RiskState, ThesisStatus, ThesisType
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.thesis import Thesis


class PublishDecisionType(str):
    PUBLISH = "publish"
    MONITORING = "monitoring"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


@dataclass(slots=True)
class PublishDecision:
    decision: str
    reasons: list[str] = field(default_factory=list)


class PublishGate:
    def __init__(self, *, attention_threshold: int = 70) -> None:
        self.attention_threshold = attention_threshold

    def evaluate(
        self,
        research_object: ResearchObject,
        working_primary: Thesis | None,
        working_opposing: Thesis | None,
        claim_index: dict[str, Claim],
    ) -> PublishDecision:
        reasons: list[str] = []

        if research_object.processing_state == ProcessingState.BLOCKED or research_object.risk_state == RiskState.BLOCKED:
            return PublishDecision(PublishDecisionType.BLOCKED, ["object is blocked"])

        if working_primary is None:
            return PublishDecision(PublishDecisionType.MONITORING, ["no working primary thesis"])

        if working_primary.thesis_type == ThesisType.RISK:
            return PublishDecision(PublishDecisionType.MONITORING, ["risk thesis is the current working priority"])

        if research_object.risk_state == RiskState.RESTRICTED:
            return PublishDecision(PublishDecisionType.MONITORING, ["risk_state is restricted"])

        if working_primary.status == ThesisStatus.CHALLENGED:
            reasons.append("working primary thesis is challenged")

        if working_primary.conflict_severity.rank >= ConflictSeverity.MEDIUM.rank:
            reasons.append("thesis conflict is medium or higher")

        if working_opposing is not None and working_opposing.conflict_severity.rank >= ConflictSeverity.MEDIUM.rank:
            reasons.append("opposing thesis remains unresolved at medium or higher")

        if working_primary.thesis_type == ThesisType.PREDICTIVE:
            if working_primary.working_primary_streak < 2:
                reasons.append("predictive thesis has not stayed primary for two consecutive evaluations")
            if len(working_primary.anchor_claim_ids) < 2:
                reasons.append("predictive thesis has fewer than two anchor claims")
            if working_primary.promoted_claim_count(claim_index) < 3:
                reasons.append("predictive thesis has fewer than three promoted claims")
            if len(working_primary.source_families(claim_index)) < 2:
                reasons.append("anchor claims do not span at least two source families")
            if working_primary.best_evidence_rank(claim_index) < 4:
                reasons.append("predictive thesis lacks E4+ core evidence")
            if not any(
                claim_index[claim_id].claim_type
                in {ClaimType.FACT, ClaimType.MEASUREMENT, ClaimType.FLOW, ClaimType.MARKET_STRUCTURE}
                for claim_id in working_primary.anchor_claim_ids
            ):
                reasons.append("predictive thesis has no valid anchor claim type")
            if not working_primary.all_anchor_fresh(claim_index):
                reasons.append("predictive thesis anchor evidence is not fully fresh")
            if research_object.attention_score < self.attention_threshold:
                reasons.append("attention score is below predictive publish threshold")

        if reasons:
            return PublishDecision(PublishDecisionType.MONITORING, reasons)

        return PublishDecision(PublishDecisionType.PUBLISH, ["publish gate passed"])
