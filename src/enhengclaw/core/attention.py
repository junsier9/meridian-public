from __future__ import annotations

from enhengclaw.core.claims import Claim
from enhengclaw.core.conflicts import ConflictGroup
from enhengclaw.core.enums import ConflictSeverity, ObjectType, RiskState


def _object_relevance(object_type: ObjectType) -> int:
    return {
        ObjectType.ASSET: 7,
        ObjectType.NARRATIVE: 8,
        ObjectType.EVENT: 9,
        ObjectType.WALLET_CLUSTER: 7,
        ObjectType.PROJECT: 6,
        ObjectType.VENUE: 6,
    }[object_type]


def _max_conflict(groups: list[ConflictGroup]) -> ConflictSeverity:
    if not groups:
        return ConflictSeverity.CLEAN
    return max((group.severity for group in groups), key=lambda severity: severity.rank)


def calculate_attention_score(
    object_type: ObjectType,
    claims: list[Claim],
    conflict_groups: list[ConflictGroup],
    risk_state: RiskState,
) -> int:
    supported_claims = [claim for claim in claims if claim.status.value in {"supported", "promoted"}]
    relevant = supported_claims or claims
    source_families = {claim.source_family for claim in relevant}
    claim_types = {claim.claim_type for claim in relevant}
    avg_evidence_rank = round(sum(claim.highest_evidence_level().rank for claim in relevant) / len(relevant)) if relevant else 1

    novelty = min(20, 8 + len(claim_types) * 2)
    evidence_quality = min(20, avg_evidence_rank * 4)
    cross_channel_confirmation = min(20, len(source_families) * 5)
    market_impact = min(
        15,
        sum(4 for claim in supported_claims if claim.claim_type.value in {"measurement", "flow", "market_structure"}) or 3,
    )
    strategic_relevance = _object_relevance(object_type)
    timeliness = 10 if all(claim.is_fresh() for claim in relevant) else 6

    conflict_penalty = {
        ConflictSeverity.CLEAN: 0,
        ConflictSeverity.LOW: 5,
        ConflictSeverity.MEDIUM: 7,
        ConflictSeverity.HIGH: 10,
        ConflictSeverity.CRITICAL: 15,
    }[_max_conflict(conflict_groups)]

    risk_penalty = {
        RiskState.NORMAL: 0,
        RiskState.CAUTION: 6,
        RiskState.RESTRICTED: 12,
        RiskState.BLOCKED: 20,
    }[risk_state]

    score = novelty + evidence_quality + cross_channel_confirmation + market_impact + strategic_relevance + timeliness - conflict_penalty - risk_penalty
    return max(0, min(score, 100))
