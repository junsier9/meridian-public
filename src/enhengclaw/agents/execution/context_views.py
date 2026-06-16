from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from enhengclaw.agents.execution._shared import normalize_text, sha256_fragment, SliceObjectContextError
from enhengclaw.agents.schemas.attention_allocator import AttentionAllocatorAssessment
from enhengclaw.agents.schemas.research_lead import ResearchLeadDirective
from enhengclaw.agents.schemas.research_synthesizer import ResearchSynthesisDraft
from enhengclaw.agents.schemas.risk_governance_agent import RiskGovernanceReview
from enhengclaw.agents.schemas.validation_agent import ValidationReviewDraft
from enhengclaw.core.claims import Claim
from enhengclaw.core.enums import ProcessingState, RiskState
from enhengclaw.core.session import RuntimeSession
from enhengclaw.core.thesis import Thesis
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator


@dataclass(frozen=True, slots=True)
class ClaimPromptSummary:
    predicate: str
    value: str
    direction: str
    source_family: str
    confidence: int
    scope: str
    time_horizon: str

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate,
            "value": self.value,
            "direction": self.direction,
            "source_family": self.source_family,
            "confidence": self.confidence,
            "scope": self.scope,
            "time_horizon": self.time_horizon,
        }


@dataclass(frozen=True, slots=True)
class ExistingObjectCommonContextSummary:
    object_id: str
    subject: str
    scope: str
    processing_state: str
    risk_state: str
    claim_count: int
    recent_claims: tuple[ClaimPromptSummary, ...]

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "processing_state": self.processing_state,
            "risk_state": self.risk_state,
            "claim_count": self.claim_count,
            "recent_claims": [claim.to_prompt_payload() for claim in self.recent_claims],
        }


@dataclass(frozen=True, slots=True)
class ExistingObjectExecutionContext:
    common: ExistingObjectCommonContextSummary
    context_name: str
    extra_payload: dict[str, Any]

    def to_prompt_payload(self) -> dict[str, Any]:
        payload = self.common.to_prompt_payload()
        payload[self.context_name] = self.extra_payload
        return payload

    def fingerprint(self) -> str:
        return sha256_fragment(self.to_prompt_payload())


def build_common_existing_object_context(
    session: RuntimeSession,
    *,
    subject: str,
    scope: str,
) -> ExistingObjectCommonContextSummary:
    if session.research_object.scope != scope:
        raise SliceObjectContextError("existing_object_scope_mismatches_requested_scope")
    subjects = {str(claim.subject).strip() for claim in session.claims if str(claim.subject).strip()}
    if subjects and subjects != {subject}:
        raise SliceObjectContextError("existing_object_subject_mismatches_requested_subject")
    recent_claims = tuple(_claim_prompt_summary(claim) for claim in session.claims[-3:])
    return ExistingObjectCommonContextSummary(
        object_id=str(session.object_id),
        subject=subject,
        scope=scope,
        processing_state=session.research_object.processing_state.value,
        risk_state=session.research_object.risk_state.value,
        claim_count=len(session.claims),
        recent_claims=recent_claims,
    )


def build_risk_signal_execution_context(
    session: RuntimeSession,
    *,
    subject: str,
    scope: str,
) -> ExistingObjectExecutionContext:
    common = build_common_existing_object_context(session, subject=subject, scope=scope)
    risk_claims = [
        claim for claim in session.claims if claim.claim_type.value in {"risk_flag", "invalidation"}
    ]
    extra_payload = {
        "current_risk_posture": common.risk_state,
        "recent_risk_claims": [_claim_prompt_summary(claim).to_prompt_payload() for claim in risk_claims[-3:]],
    }
    return ExistingObjectExecutionContext(
        common=common,
        context_name="risk_signal_context",
        extra_payload=extra_payload,
    )


def build_risk_governance_review(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    spec_version: int = 0,
) -> RiskGovernanceReview:
    session = runtime.store.load(object_id)
    research_object = deepcopy(session.research_object)
    claims = deepcopy(session.claims)
    derived_risk_state = runtime.rule_service.derive_risk_state(claims)
    reasons: list[str] = []

    if derived_risk_state != research_object.risk_state:
        reasons.append("stored risk_state differs from the current claim-derived risk_state")
    if derived_risk_state in {RiskState.RESTRICTED, RiskState.BLOCKED}:
        reasons.append("publish must remain suppressed under the derived risk posture")
    if research_object.is_restricted_monitoring:
        posture = "restricted_monitoring"
        reasons.append("object is already running in restricted monitoring")
    else:
        posture = derived_risk_state.value

    gate_status = (
        "pass"
        if derived_risk_state in {RiskState.RESTRICTED, RiskState.BLOCKED} or research_object.is_restricted_monitoring
        else "block"
    )
    return RiskGovernanceReview(
        object_id=research_object.object_id,
        processing_state=research_object.processing_state.value,
        current_risk_state=research_object.risk_state.value,
        derived_risk_state=derived_risk_state.value,
        governance_posture=posture,
        publish_suppressed=derived_risk_state in {RiskState.RESTRICTED, RiskState.BLOCKED},
        gate_status=gate_status,
        spec_version=spec_version,
        reasons=tuple(reasons),
    )


def build_risk_governance_execution_context(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    subject: str,
    scope: str,
) -> ExistingObjectExecutionContext:
    session = runtime.store.load(object_id)
    common = build_common_existing_object_context(session, subject=subject, scope=scope)
    review = build_risk_governance_review(runtime=runtime, object_id=object_id, spec_version=0)
    return ExistingObjectExecutionContext(
        common=common,
        context_name="risk_governance_context",
        extra_payload=asdict(review),
    )


def build_validation_review(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    spec_version: int = 0,
) -> ValidationReviewDraft:
    session = runtime.store.load(object_id)
    research_object = deepcopy(session.research_object)
    claims = deepcopy(session.claims)
    conflict_groups = deepcopy(session.conflict_groups)
    theses = deepcopy(session.theses)
    reasons: list[str] = []
    claim_index = {claim.claim_id: claim for claim in claims}
    working_primary = _find_thesis(theses, research_object.working_primary_thesis_id)
    working_opposing = _find_thesis(theses, research_object.working_opposing_thesis_id)

    if not theses and research_object.processing_state in {
        ProcessingState.ACTIVE_RESEARCH,
        ProcessingState.EVIDENCE_COMPLETE,
    }:
        theses = runtime.build_theses(research_object, claims, conflict_groups)
        claim_index = {claim.claim_id: claim for claim in claims}
        working_primary, working_opposing = runtime.select_working_theses(research_object, theses, claim_index)
        runtime.evaluate_thesis_conflicts(research_object, working_primary, working_opposing, claim_index)

    publish_gate_checked = research_object.processing_state == ProcessingState.PUBLISH_READY
    if publish_gate_checked:
        decision = runtime.evaluate_publish_gate(research_object, working_primary, working_opposing, claim_index)
        reasons.extend(decision.reasons)
    elif research_object.processing_state == ProcessingState.BLOCKED or research_object.risk_state == RiskState.BLOCKED:
        decision = runtime.publish_gate.evaluate(research_object, working_primary, working_opposing, claim_index)
        reasons.extend(decision.reasons)
    elif research_object.processing_state == ProcessingState.ARCHIVED:
        return ValidationReviewDraft(
            object_id=research_object.object_id,
            processing_state=research_object.processing_state.value,
            publish_gate_checked=False,
            working_primary_thesis_id=None if working_primary is None else working_primary.thesis_id,
            working_opposing_thesis_id=None if working_opposing is None else working_opposing.thesis_id,
            decision="archived",
            gate_status="pass",
            spec_version=spec_version,
            reasons=("object is archived before publish gate",),
        )
    else:
        return ValidationReviewDraft(
            object_id=research_object.object_id,
            processing_state=research_object.processing_state.value,
            publish_gate_checked=False,
            working_primary_thesis_id=None if working_primary is None else working_primary.thesis_id,
            working_opposing_thesis_id=None if working_opposing is None else working_opposing.thesis_id,
            decision="monitoring",
            gate_status="pass",
            spec_version=spec_version,
            reasons=(f"publish_gate is not legal in {research_object.processing_state.value}",),
        )

    gate_status = "pass" if decision.decision != "publish" else "block"
    return ValidationReviewDraft(
        object_id=research_object.object_id,
        processing_state=research_object.processing_state.value,
        publish_gate_checked=publish_gate_checked,
        working_primary_thesis_id=None if working_primary is None else working_primary.thesis_id,
        working_opposing_thesis_id=None if working_opposing is None else working_opposing.thesis_id,
        decision=decision.decision,
        gate_status=gate_status,
        spec_version=spec_version,
        reasons=tuple(reasons or ["publish gate passed"]),
    )


def build_validation_execution_context(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    subject: str,
    scope: str,
) -> ExistingObjectExecutionContext:
    session = runtime.store.load(object_id)
    common = build_common_existing_object_context(session, subject=subject, scope=scope)
    review = build_validation_review(runtime=runtime, object_id=object_id, spec_version=0)
    extra_payload = {
        "thesis_count": len(session.theses),
        "working_primary_thesis_id": review.working_primary_thesis_id,
        "working_opposing_thesis_id": review.working_opposing_thesis_id,
        "publish_gate_checked": review.publish_gate_checked,
        "decision": review.decision,
        "gate_status": review.gate_status,
        "reasons": list(review.reasons),
    }
    return ExistingObjectExecutionContext(
        common=common,
        context_name="validation_context",
        extra_payload=extra_payload,
    )


def build_attention_allocator_assessment(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
) -> AttentionAllocatorAssessment:
    session = runtime.store.load(object_id)
    research_object = deepcopy(session.research_object)
    claims = deepcopy(session.claims)
    conflict_groups = deepcopy(session.conflict_groups)
    reasons: list[str] = []

    allowed_states = {
        ProcessingState.CANDIDATE,
        ProcessingState.MONITORING,
        ProcessingState.ARCHIVED,
        ProcessingState.ACTIVE_RESEARCH,
    }
    stage_permitted = research_object.processing_state in allowed_states
    if stage_permitted:
        recalculated_attention = runtime.calculate_attention(research_object, claims, conflict_groups)
    else:
        recalculated_attention = research_object.attention_score
        reasons.append(f"attention_calculation is not legal in {research_object.processing_state.value}")

    if research_object.risk_state == RiskState.BLOCKED:
        recommendation = "hold"
        reasons.append("risk_state is blocked")
    elif recalculated_attention < 30:
        recommendation = "archive"
        reasons.append("attention remains below the archive threshold")
    elif recalculated_attention < 55:
        recommendation = "monitor"
        reasons.append("attention supports monitoring, not active research expansion")
    elif stage_permitted:
        recommendation = "advance"
        reasons.append("attention is high enough for continued research budget")
    else:
        recommendation = "hold"

    return AttentionAllocatorAssessment(
        object_id=research_object.object_id,
        processing_state=research_object.processing_state.value,
        risk_state=research_object.risk_state.value,
        current_attention=research_object.attention_score,
        recalculated_attention=recalculated_attention,
        stage_permitted=stage_permitted,
        recommendation=recommendation,
        reasons=tuple(reasons),
    )


def build_attention_execution_context(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    subject: str,
    scope: str,
) -> ExistingObjectExecutionContext:
    session = runtime.store.load(object_id)
    common = build_common_existing_object_context(session, subject=subject, scope=scope)
    assessment = build_attention_allocator_assessment(runtime=runtime, object_id=object_id)
    return ExistingObjectExecutionContext(
        common=common,
        context_name="attention_context",
        extra_payload=asdict(assessment),
    )


def build_research_synthesis_draft(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
) -> ResearchSynthesisDraft:
    session = runtime.store.load(object_id)
    research_object = deepcopy(session.research_object)
    claims = deepcopy(session.claims)
    conflict_groups = deepcopy(session.conflict_groups)
    theses = deepcopy(session.theses)
    reasons: list[str] = []

    stage_permitted = research_object.processing_state in {
        ProcessingState.ACTIVE_RESEARCH,
        ProcessingState.EVIDENCE_COMPLETE,
    }
    if stage_permitted:
        theses = runtime.build_theses(research_object, claims, conflict_groups)
        claim_index = {claim.claim_id: claim for claim in claims}
        working_primary, working_opposing = runtime.select_working_theses(research_object, theses, claim_index)
        runtime.evaluate_thesis_conflicts(research_object, working_primary, working_opposing, claim_index)
        reasons.append("thesis building and selection are legal in the current processing state")
    else:
        working_primary = _find_thesis(theses, research_object.working_primary_thesis_id)
        working_opposing = _find_thesis(theses, research_object.working_opposing_thesis_id)
        reasons.append(f"thesis_building is not legal in {research_object.processing_state.value}")

    return ResearchSynthesisDraft(
        object_id=research_object.object_id,
        processing_state=research_object.processing_state.value,
        stage_permitted=stage_permitted,
        thesis_count=len(theses),
        thesis_ids=tuple(thesis.thesis_id for thesis in theses),
        working_primary_thesis_id=None if working_primary is None else working_primary.thesis_id,
        working_opposing_thesis_id=None if working_opposing is None else working_opposing.thesis_id,
        working_primary_type="none" if working_primary is None else working_primary.thesis_type.value,
        working_primary_conflict="none" if working_primary is None else working_primary.conflict_severity.value,
        reasons=tuple(reasons),
    )


def build_research_synthesis_execution_context(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    subject: str,
    scope: str,
) -> ExistingObjectExecutionContext:
    session = runtime.store.load(object_id)
    common = build_common_existing_object_context(session, subject=subject, scope=scope)
    draft = build_research_synthesis_draft(runtime=runtime, object_id=object_id)
    extra_payload = asdict(draft)
    extra_payload["risk_state"] = common.risk_state
    return ExistingObjectExecutionContext(
        common=common,
        context_name="research_synthesis_context",
        extra_payload=extra_payload,
    )


def build_research_lead_directive(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
) -> ResearchLeadDirective:
    session = runtime.store.load(object_id)
    research_object = deepcopy(session.research_object)

    if research_object.is_restricted_monitoring:
        next_legal_stage = "restricted_monitoring"
        allowed_actions = ("targeted_refresh", "conflict_work", "risk_refresh")
        blocked_actions = ("publish_gate", "new_deep_investigation")
    else:
        next_legal_stage, allowed_actions, blocked_actions = _lead_plan(research_object.processing_state)

    return ResearchLeadDirective(
        object_id=research_object.object_id,
        processing_state=research_object.processing_state.value,
        risk_state=research_object.risk_state.value,
        next_legal_stage=next_legal_stage,
        allowed_actions=allowed_actions,
        blocked_actions=blocked_actions,
        cadence_mode="none" if session.cadence is None else session.cadence.mode,
        resource_slot="none" if session.resource_allocation is None else session.resource_allocation.slot_type.value,
    )


def build_research_lead_execution_context(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    subject: str,
    scope: str,
) -> ExistingObjectExecutionContext:
    session = runtime.store.load(object_id)
    common = build_common_existing_object_context(session, subject=subject, scope=scope)
    directive = build_research_lead_directive(runtime=runtime, object_id=object_id)
    return ExistingObjectExecutionContext(
        common=common,
        context_name="research_lead_context",
        extra_payload=asdict(directive),
    )


def _claim_prompt_summary(claim: Claim) -> ClaimPromptSummary:
    return ClaimPromptSummary(
        predicate=str(claim.predicate),
        value=normalize_text(str(claim.value)),
        direction=claim.direction.value,
        source_family=claim.source_family.value,
        confidence=int(claim.confidence),
        scope=str(claim.scope),
        time_horizon=claim.time_horizon.value,
    )


def _find_thesis(theses: list[Thesis], thesis_id: str | None) -> Thesis | None:
    if thesis_id is None:
        return None
    return next((thesis for thesis in theses if thesis.thesis_id == thesis_id), None)


def _lead_plan(processing_state: ProcessingState) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    plans = {
        ProcessingState.CANDIDATE: (
            "screening",
            ("signal_intake", "claim_conflict_grouping", "attention_reassessment"),
            ("thesis_building", "publish_gate"),
        ),
        ProcessingState.SCREENED: (
            "screening_decision",
            ("attention_reassessment", "screening_decision"),
            ("thesis_selection", "publish_gate"),
        ),
        ProcessingState.ACTIVE_RESEARCH: (
            "thesis_building",
            ("claim_status_refresh", "conflict_regrouping", "thesis_building", "working_thesis_selection"),
            ("publish_gate", "direct_publish"),
        ),
        ProcessingState.EVIDENCE_COMPLETE: (
            "publishability_review",
            ("claim_promotion", "working_thesis_selection", "publishability_review"),
            ("direct_publish", "provider_override"),
        ),
        ProcessingState.PUBLISH_READY: (
            "publish_gate",
            ("publish_gate",),
            ("direct_publish", "state_bypass"),
        ),
        ProcessingState.PUBLISHED: (
            "monitoring_resume",
            ("monitoring_resume", "targeted_refresh"),
            ("direct_republish", "new_publish_gate_without_resume"),
        ),
        ProcessingState.MONITORING: (
            "targeted_refresh",
            ("targeted_refresh", "attention_reassessment"),
            ("direct_publish", "claim_promotion"),
        ),
        ProcessingState.ARCHIVED: (
            "reactivation_review",
            ("reactivation_review",),
            ("publish_gate", "thesis_building"),
        ),
        ProcessingState.BLOCKED: (
            "forced_review",
            ("forced_review",),
            ("normal_resume", "publish_gate"),
        ),
    }
    return plans[processing_state]
