from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from enhengclaw.core.claims import Claim
from enhengclaw.core.enums import ClaimType, ConflictResolution, ConflictSeverity, EvidenceLevel


@dataclass(slots=True)
class ConflictGroup:
    group_id: str
    object_id: str
    claim_ids: list[str]
    severity: ConflictSeverity
    resolution: ConflictResolution
    winning_claim_id: str | None = None


def _semantic_key(claim: Claim) -> tuple[str, str, str, str]:
    return (
        claim.subject.strip().lower(),
        claim.predicate.strip().lower(),
        claim.scope.strip().lower(),
        claim.time_horizon.value,
    )


def _claims_conflict(left: Claim, right: Claim) -> bool:
    if _semantic_key(left) != _semantic_key(right):
        return False
    if left.direction != right.direction:
        return True
    return left.value.strip().lower() != right.value.strip().lower()


def _severity_for_pair(left: Claim, right: Claim) -> ConflictSeverity:
    left_level = left.highest_evidence_level().rank
    right_level = right.highest_evidence_level().rank
    min_level = min(left_level, right_level)
    if (
        min_level >= EvidenceLevel.E4.rank
        and left.confidence >= 75
        and right.confidence >= 75
        and (
            left.claim_type in {ClaimType.RISK_FLAG, ClaimType.INVALIDATION}
            or right.claim_type in {ClaimType.RISK_FLAG, ClaimType.INVALIDATION}
        )
    ):
        return ConflictSeverity.CRITICAL
    if min_level >= EvidenceLevel.E4.rank and left.confidence >= 65 and right.confidence >= 65:
        return ConflictSeverity.HIGH
    if min_level >= EvidenceLevel.E3.rank:
        return ConflictSeverity.MEDIUM
    return ConflictSeverity.LOW


def _choose_winner(left: Claim, right: Claim) -> Claim | None:
    left_level = left.highest_evidence_level().rank
    right_level = right.highest_evidence_level().rank
    if abs(left_level - right_level) >= 2:
        return left if left_level > right_level else right
    if abs(left.confidence - right.confidence) >= 15:
        return left if left.confidence > right.confidence else right
    return None


def group_claim_conflicts(claims: list[Claim]) -> list[ConflictGroup]:
    groups: list[ConflictGroup] = []
    seen: set[tuple[str, str]] = set()
    group_index = 1

    for left, right in combinations(claims, 2):
        pair_key = tuple(sorted((left.claim_id, right.claim_id)))
        if pair_key in seen or not _claims_conflict(left, right):
            continue

        seen.add(pair_key)
        severity = _severity_for_pair(left, right)
        winner = _choose_winner(left, right)
        resolution = ConflictResolution.UNRESOLVED
        winning_claim_id: str | None = None

        if winner is not None:
            resolution = ConflictResolution.RESOLVED
            winning_claim_id = winner.claim_id
            loser = right if winner.claim_id == left.claim_id else left
            if severity.rank >= ConflictSeverity.HIGH.rank:
                loser.mark_invalidated()
            else:
                loser.mark_contested()
        else:
            left.mark_contested()
            right.mark_contested()

        group = ConflictGroup(
            group_id=f"cg-{group_index}",
            object_id=left.object_id,
            claim_ids=[left.claim_id, right.claim_id],
            severity=severity,
            resolution=resolution,
            winning_claim_id=winning_claim_id,
        )
        left.conflict_group_id = group.group_id
        right.conflict_group_id = group.group_id
        groups.append(group)
        group_index += 1

    return groups
