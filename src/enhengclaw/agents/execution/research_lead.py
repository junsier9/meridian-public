from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enhengclaw.agents.execution._shared import (
    SliceCompilerTransportError,
    SliceLiveBackendConfigError,
    SliceObjectContextError,
    SliceTranscriptReplayError,
    normalize_text,
    sha256_fragment,
)
from enhengclaw.agents.execution.context_views import ExistingObjectExecutionContext, build_research_lead_execution_context
from enhengclaw.agents.execution.continue_existing_slice import (
    ContinueExistingSliceExecutionPipeline,
    ContinueExistingSliceExecutionResult,
    ContinueExistingSliceSpec,
    DeterministicContinueExistingSliceCompiler,
    OpenAICompatibleContinueExistingSliceBackend,
    RecordedTranscriptContinueExistingSliceBackend,
    live_backend_kwargs_from_env,
)
from enhengclaw.agents.schemas.research_lead import ResearchLeadSignalDraft


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "research_lead.system.md"
RESEARCH_LEAD_COMPILER_CONTRACT_VERSION = "research_lead_compiler_v1"
RESEARCH_LEAD_LIVE_BACKEND_NAME = "openai_compatible_chat_completions"
RESEARCH_LEAD_RECORDED_BACKEND_NAME = "recorded_transcript_replay"
RESEARCH_LEAD_DETERMINISTIC_BACKEND_NAME = "deterministic_compiler"
PROMPT_TEMPLATE_VERSION = "research_lead_prompt_template_v1"
ALLOWED_PREDICATES = frozenset(
    {
        "next_stage_targeted_refresh",
        "next_stage_hold",
        "next_stage_conflict_work",
        "next_stage_risk_refresh",
    }
)


@dataclass(frozen=True, slots=True)
class ResearchLeadObservationInput:
    input_id: str
    object_id: str
    subject: str
    scope: str
    directive_text: str

    def to_spec_input_payload(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "directive_text": self.directive_text,
        }

    def fingerprint(self) -> str:
        return sha256_fragment(
            {
                "object_id": self.object_id,
                "subject": self.subject,
                "scope": self.scope,
                "directive_text": self.directive_text,
            }
        )

    def text_value(self) -> str:
        return self.directive_text


ResearchLeadExecutionResult = ContinueExistingSliceExecutionResult


class ResearchLeadLiveBackendConfigError(SliceLiveBackendConfigError):
    pass


class ResearchLeadCompilerTransportError(SliceCompilerTransportError):
    pass


class ResearchLeadTranscriptReplayError(SliceTranscriptReplayError):
    pass


class ResearchLeadObjectContextError(SliceObjectContextError):
    pass


RESEARCH_LEAD_SPEC = ContinueExistingSliceSpec(
    slice_id="research_lead",
    contract_version=RESEARCH_LEAD_COMPILER_CONTRACT_VERSION,
    prompt_template_version=PROMPT_TEMPLATE_VERSION,
    prompt_path=DEFAULT_PROMPT_PATH,
    input_text_label="directive_text",
    success_prompt_line="Compile one bounded next-stage directive observation into exactly one JSON compiler envelope.",
    live_backend_name=RESEARCH_LEAD_LIVE_BACKEND_NAME,
    recorded_backend_name=RESEARCH_LEAD_RECORDED_BACKEND_NAME,
    deterministic_backend_name=RESEARCH_LEAD_DETERMINISTIC_BACKEND_NAME,
    env_prefix="ENHENGCLAW_RESEARCH_LEAD_MODEL",
    draft_cls=ResearchLeadSignalDraft,
    allowed_predicates=ALLOWED_PREDICATES,
    allowed_claim_types=frozenset({"causal", "predictive"}),
    allowed_directions=frozenset({"neutral", "risk"}),
    allowed_source_families=frozenset({"analytics", "official"}),
    allowed_evidence_levels=frozenset({"E2", "E3", "E4"}),
    allowed_time_horizons=frozenset({"short", "medium"}),
    build_object_context=build_research_lead_execution_context,
    deterministic_compile=lambda observation, object_context: _deterministic_compile(observation, object_context),
)


class OpenAICompatibleResearchLeadBackend(OpenAICompatibleContinueExistingSliceBackend):
    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(spec=RESEARCH_LEAD_SPEC, **kwargs)
        except SliceLiveBackendConfigError as exc:
            raise ResearchLeadLiveBackendConfigError(str(exc)) from exc

    @classmethod
    def from_env(cls) -> OpenAICompatibleResearchLeadBackend:
        try:
            return cls(**live_backend_kwargs_from_env(RESEARCH_LEAD_SPEC))
        except SliceLiveBackendConfigError as exc:
            raise ResearchLeadLiveBackendConfigError(str(exc)) from exc

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceCompilerTransportError as exc:
            raise ResearchLeadCompilerTransportError(str(exc)) from exc


class RecordedTranscriptResearchLeadBackend(RecordedTranscriptContinueExistingSliceBackend):
    def __init__(self, *, transcript_path: str | Path) -> None:
        super().__init__(spec=RESEARCH_LEAD_SPEC, transcript_path=transcript_path)

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceTranscriptReplayError as exc:
            raise ResearchLeadTranscriptReplayError(str(exc)) from exc


class DeterministicResearchLeadCompiler(DeterministicContinueExistingSliceCompiler):
    def __init__(self) -> None:
        super().__init__(spec=RESEARCH_LEAD_SPEC)


class ResearchLeadExecutionPipeline(ContinueExistingSliceExecutionPipeline):
    def __init__(self, *, artifact_store=None, compiler_backend=None, prompt_path: str | Path | None = None) -> None:
        super().__init__(
            spec=RESEARCH_LEAD_SPEC,
            artifact_store=artifact_store,
            compiler_backend=compiler_backend,
            prompt_path=prompt_path,
        )


def build_research_lead_object_context(*, runtime, object_id: str, subject: str, scope: str) -> ExistingObjectExecutionContext:
    try:
        return build_research_lead_execution_context(runtime=runtime, object_id=object_id, subject=subject, scope=scope)
    except SliceObjectContextError as exc:
        raise ResearchLeadObjectContextError(str(exc)) from exc


def _deterministic_compile(
    observation: ResearchLeadObservationInput,
    object_context: ExistingObjectExecutionContext,
) -> dict[str, Any]:
    lowered = observation.directive_text.lower()
    extra = object_context.extra_payload
    if "conflict" in lowered:
        predicate = "next_stage_conflict_work"
        direction = "risk"
        claim_type = "causal"
        value = "the bounded directive note recommends conflict work as the next legal step for the object"
    elif "risk refresh" in lowered or "restricted" in lowered:
        predicate = "next_stage_risk_refresh"
        direction = "risk"
        claim_type = "causal"
        value = "the bounded directive note recommends a risk refresh without bypassing the state machine"
    elif "hold" in lowered or str(extra.get("next_legal_stage", "")) == "forced_review":
        predicate = "next_stage_hold"
        direction = "neutral"
        claim_type = "predictive"
        value = "the bounded directive note recommends a hold rather than orchestration or direct publish"
    else:
        predicate = "next_stage_targeted_refresh"
        direction = "neutral"
        claim_type = "predictive"
        value = "the bounded directive note recommends a targeted refresh as the next legal stage"
    candidate = {
        "input_id": observation.input_id,
        "subject": observation.subject,
        "predicate": predicate,
        "value": normalize_text(value),
        "claim_type": claim_type,
        "direction": direction,
        "source_family": "analytics",
        "evidence_level": "E3",
        "confidence_hint": 67,
        "scope": observation.scope,
        "time_horizon": "short",
    }
    return {
        "status": "success",
        "blocked_reason": None,
        "candidate_payloads": [candidate],
        "notes": ["deterministic compiler emitted one candidate payload"],
    }
