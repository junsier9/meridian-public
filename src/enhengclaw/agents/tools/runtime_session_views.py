from __future__ import annotations

import json
import os

from enhengclaw.agents.execution.context_views import (
    build_attention_allocator_assessment,
    build_research_lead_directive,
    build_research_synthesis_draft,
    build_risk_governance_review,
    build_validation_review,
)
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator

_REVIEW_OVERRIDE_ENV = "ENHENGCLAW_TEST_REVIEW_OVERRIDE"


def inspect_attention_allocation(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
) -> AttentionAllocatorAssessment:
    review = build_attention_allocator_assessment(runtime=runtime, object_id=object_id)
    return _maybe_override_review_payload("attention_allocation", review)


def inspect_research_synthesis(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
) -> ResearchSynthesisDraft:
    review = build_research_synthesis_draft(runtime=runtime, object_id=object_id)
    return _maybe_override_review_payload("research_synthesis", review)


def inspect_validation_review(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    spec_version: int = 0,
) -> ValidationReviewDraft:
    review = build_validation_review(runtime=runtime, object_id=object_id, spec_version=spec_version)
    return _maybe_override_review_payload("validation_review", review)


def inspect_risk_governance_review(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    spec_version: int = 0,
) -> RiskGovernanceReview:
    review = build_risk_governance_review(runtime=runtime, object_id=object_id, spec_version=spec_version)
    return _maybe_override_review_payload("risk_governance_review", review)


def inspect_research_lead_directive(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
) -> ResearchLeadDirective:
    review = build_research_lead_directive(runtime=runtime, object_id=object_id)
    return _maybe_override_review_payload("research_lead_directive", review)


def _maybe_override_review_payload(review_name: str, review):
    raw = os.environ.get(_REVIEW_OVERRIDE_ENV, "").strip()
    if not raw:
        return review
    overrides = json.loads(raw)
    if not isinstance(overrides, dict):
        raise RuntimeError(f"{_REVIEW_OVERRIDE_ENV} must be a JSON object when set")
    override = overrides.get(review_name)
    if override is None:
        return review
    if not isinstance(override, dict):
        raise RuntimeError(f"{_REVIEW_OVERRIDE_ENV}.{review_name} must be a JSON object when set")
    if "error" in override:
        raise RuntimeError(str(override["error"]))
    return override
