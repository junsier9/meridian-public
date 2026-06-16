from __future__ import annotations

from enhengclaw.core.claims import Claim
from enhengclaw.core.conflicts import ConflictGroup
from enhengclaw.core.enums import ClaimStatus, ClaimType, ConflictSeverity, MarketState, ProcessingState, RiskState, ThesisStatus, ThesisType
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.signals import Signal
from enhengclaw.core.thesis import Thesis


class RuntimeRuleService:
    def derive_risk_state(self, claims: list[Claim]) -> RiskState:
        risk_claims = [
            claim
            for claim in claims
            if claim.claim_type in {ClaimType.RISK_FLAG, ClaimType.INVALIDATION}
            and claim.status in {ClaimStatus.SUPPORTED, ClaimStatus.PROMOTED}
        ]
        if any(claim.highest_evidence_level().rank >= 5 and claim.confidence >= 85 for claim in risk_claims):
            return RiskState.BLOCKED
        if any(claim.highest_evidence_level().rank >= 4 and claim.confidence >= 65 for claim in risk_claims):
            return RiskState.RESTRICTED
        if risk_claims:
            return RiskState.CAUTION
        return RiskState.NORMAL

    def derive_market_state(self, research_object: ResearchObject, claims: list[Claim]) -> MarketState:
        directional = [
            claim
            for claim in claims
            if claim.claim_type in {ClaimType.MEASUREMENT, ClaimType.FLOW, ClaimType.MARKET_STRUCTURE}
            and claim.status in {ClaimStatus.SUPPORTED, ClaimStatus.PROMOTED}
        ]
        if not directional:
            return MarketState.PRE_EMERGENCE
        if research_object.risk_state == RiskState.BLOCKED:
            return MarketState.INVALIDATED
        if research_object.attention_score >= 75 and research_object.risk_state in {RiskState.NORMAL, RiskState.CAUTION}:
            return MarketState.ACCELERATING
        return MarketState.EMERGING

    def candidate_exit_target(self, claims: list[Claim]) -> ProcessingState:
        admissible = [claim for claim in claims if claim.status != ClaimStatus.INVALIDATED]
        if not admissible or all(claim.highest_evidence_level().rank < 3 for claim in admissible):
            return ProcessingState.ARCHIVED
        return ProcessingState.SCREENED

    def screened_exit_target(
        self,
        research_object: ResearchObject,
        claims: list[Claim],
        conflict_groups: list[ConflictGroup],
    ) -> ProcessingState:
        max_conflict = self.max_conflict(conflict_groups)
        source_families = {claim.source_family for claim in claims}
        has_e4 = any(claim.highest_evidence_level().rank >= 4 for claim in claims)
        if research_object.attention_score < 30:
            return ProcessingState.ARCHIVED
        if 30 <= research_object.attention_score < 55:
            return ProcessingState.MONITORING
        if max_conflict.rank >= ConflictSeverity.HIGH.rank:
            return ProcessingState.MONITORING
        if research_object.attention_score >= 55 and (len(source_families) >= 2 or has_e4) and research_object.risk_state != RiskState.BLOCKED:
            return ProcessingState.ACTIVE_RESEARCH
        return ProcessingState.MONITORING

    def active_research_exit_target(
        self,
        research_object: ResearchObject,
        claims: list[Claim],
    ) -> ProcessingState:
        supported = [claim for claim in claims if claim.status in {ClaimStatus.SUPPORTED, ClaimStatus.PROMOTED}]
        clean_anchor_candidates = [
            claim
            for claim in supported
            if claim.claim_type in {ClaimType.FACT, ClaimType.MEASUREMENT, ClaimType.FLOW, ClaimType.MARKET_STRUCTURE}
            and claim.is_fresh()
        ]
        if research_object.risk_state == RiskState.BLOCKED:
            return ProcessingState.BLOCKED
        if len(supported) >= 2 and clean_anchor_candidates:
            return ProcessingState.EVIDENCE_COMPLETE
        return ProcessingState.MONITORING

    def evidence_complete_exit_target(
        self,
        research_object: ResearchObject,
        working_primary: Thesis | None,
    ) -> ProcessingState:
        if research_object.risk_state in {RiskState.RESTRICTED, RiskState.BLOCKED}:
            return ProcessingState.MONITORING
        if working_primary is None:
            return ProcessingState.MONITORING
        if (
            working_primary.thesis_type == ThesisType.PREDICTIVE
            and working_primary.working_primary_streak >= 2
            and working_primary.conflict_severity.rank <= ConflictSeverity.LOW.rank
        ):
            working_primary.status = ThesisStatus.PUBLISHABLE
            return ProcessingState.PUBLISH_READY
        return ProcessingState.MONITORING

    def monitoring_resume_target(
        self,
        research_object: ResearchObject,
        claims: list[Claim],
        conflict_groups: list[ConflictGroup],
    ) -> ProcessingState:
        source_families = {claim.source_family for claim in claims}
        has_e4 = any(claim.highest_evidence_level().rank >= 4 and claim.is_fresh() for claim in claims)
        if research_object.risk_state == RiskState.BLOCKED:
            return ProcessingState.BLOCKED
        if research_object.attention_score < 30:
            return ProcessingState.ARCHIVED
        if research_object.attention_score >= 55 and (len(source_families) >= 2 or has_e4):
            return ProcessingState.ACTIVE_RESEARCH
        return ProcessingState.MONITORING

    def archived_can_reactivate(self, new_claims: list[Claim]) -> bool:
        e5_count = sum(1 for claim in new_claims if claim.highest_evidence_level().rank >= 5 and claim.is_fresh())
        e4_count = sum(1 for claim in new_claims if claim.highest_evidence_level().rank >= 4 and claim.is_fresh())
        return e5_count >= 1 or e4_count >= 2

    def max_conflict(self, groups: list[ConflictGroup]) -> ConflictSeverity:
        if not groups:
            return ConflictSeverity.CLEAN
        return max((group.severity for group in groups), key=lambda severity: severity.rank)
