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
from enhengclaw.agents.execution.context_views import ExistingObjectExecutionContext, build_research_synthesis_execution_context
from enhengclaw.agents.execution.continue_existing_slice import (
    ContinueExistingSliceExecutionPipeline,
    ContinueExistingSliceExecutionResult,
    ContinueExistingSliceSpec,
    DeterministicContinueExistingSliceCompiler,
    OpenAICompatibleContinueExistingSliceBackend,
    RecordedTranscriptContinueExistingSliceBackend,
    live_backend_kwargs_from_env,
)
from enhengclaw.agents.schemas.research_synthesizer import ResearchSynthesisSignalDraft


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "research_synthesizer.system.md"
RESEARCH_SYNTHESIZER_COMPILER_CONTRACT_VERSION = "research_synthesizer_compiler_v1"
RESEARCH_SYNTHESIZER_LIVE_BACKEND_NAME = "openai_compatible_chat_completions"
RESEARCH_SYNTHESIZER_RECORDED_BACKEND_NAME = "recorded_transcript_replay"
RESEARCH_SYNTHESIZER_DETERMINISTIC_BACKEND_NAME = "deterministic_compiler"
PROMPT_TEMPLATE_VERSION = "research_synthesizer_prompt_template_v1"
ALLOWED_PREDICATES = frozenset(
    {
        "synthesis_preview_monitor",
        "synthesis_preview_bullish",
        "synthesis_preview_bearish",
        "synthesis_risk_preview",
    }
)


@dataclass(frozen=True, slots=True)
class ResearchSynthesisObservationInput:
    input_id: str
    object_id: str
    subject: str
    scope: str
    synthesis_text: str

    def to_spec_input_payload(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "synthesis_text": self.synthesis_text,
        }

    def fingerprint(self) -> str:
        return sha256_fragment(
            {
                "object_id": self.object_id,
                "subject": self.subject,
                "scope": self.scope,
                "synthesis_text": self.synthesis_text,
            }
        )

    def text_value(self) -> str:
        return self.synthesis_text


ResearchSynthesisExecutionResult = ContinueExistingSliceExecutionResult


class ResearchSynthesizerLiveBackendConfigError(SliceLiveBackendConfigError):
    pass


class ResearchSynthesizerCompilerTransportError(SliceCompilerTransportError):
    pass


class ResearchSynthesizerTranscriptReplayError(SliceTranscriptReplayError):
    pass


class ResearchSynthesizerObjectContextError(SliceObjectContextError):
    pass


RESEARCH_SYNTHESIZER_SPEC = ContinueExistingSliceSpec(
    slice_id="research_synthesizer",
    contract_version=RESEARCH_SYNTHESIZER_COMPILER_CONTRACT_VERSION,
    prompt_template_version=PROMPT_TEMPLATE_VERSION,
    prompt_path=DEFAULT_PROMPT_PATH,
    input_text_label="synthesis_text",
    success_prompt_line="Compile one bounded synthesis-preview observation into exactly one JSON compiler envelope.",
    live_backend_name=RESEARCH_SYNTHESIZER_LIVE_BACKEND_NAME,
    recorded_backend_name=RESEARCH_SYNTHESIZER_RECORDED_BACKEND_NAME,
    deterministic_backend_name=RESEARCH_SYNTHESIZER_DETERMINISTIC_BACKEND_NAME,
    env_prefix="ENHENGCLAW_RESEARCH_SYNTHESIZER_MODEL",
    draft_cls=ResearchSynthesisSignalDraft,
    allowed_predicates=ALLOWED_PREDICATES,
    allowed_claim_types=frozenset({"predictive", "risk_flag"}),
    allowed_directions=frozenset({"bullish", "bearish", "neutral", "risk"}),
    allowed_source_families=frozenset({"analytics", "official"}),
    allowed_evidence_levels=frozenset({"E2", "E3", "E4"}),
    allowed_time_horizons=frozenset({"short", "medium", "structural"}),
    build_object_context=build_research_synthesis_execution_context,
    deterministic_compile=lambda observation, object_context: _deterministic_compile(observation, object_context),
)


class OpenAICompatibleResearchSynthesizerBackend(OpenAICompatibleContinueExistingSliceBackend):
    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(spec=RESEARCH_SYNTHESIZER_SPEC, **kwargs)
        except SliceLiveBackendConfigError as exc:
            raise ResearchSynthesizerLiveBackendConfigError(str(exc)) from exc

    @classmethod
    def from_env(cls) -> OpenAICompatibleResearchSynthesizerBackend:
        try:
            return cls(**live_backend_kwargs_from_env(RESEARCH_SYNTHESIZER_SPEC))
        except SliceLiveBackendConfigError as exc:
            raise ResearchSynthesizerLiveBackendConfigError(str(exc)) from exc

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceCompilerTransportError as exc:
            raise ResearchSynthesizerCompilerTransportError(str(exc)) from exc


class RecordedTranscriptResearchSynthesizerBackend(RecordedTranscriptContinueExistingSliceBackend):
    def __init__(self, *, transcript_path: str | Path) -> None:
        super().__init__(spec=RESEARCH_SYNTHESIZER_SPEC, transcript_path=transcript_path)

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceTranscriptReplayError as exc:
            raise ResearchSynthesizerTranscriptReplayError(str(exc)) from exc


class DeterministicResearchSynthesizerCompiler(DeterministicContinueExistingSliceCompiler):
    def __init__(self) -> None:
        super().__init__(spec=RESEARCH_SYNTHESIZER_SPEC)


class ResearchSynthesisExecutionPipeline(ContinueExistingSliceExecutionPipeline):
    def __init__(self, *, artifact_store=None, compiler_backend=None, prompt_path: str | Path | None = None) -> None:
        super().__init__(
            spec=RESEARCH_SYNTHESIZER_SPEC,
            artifact_store=artifact_store,
            compiler_backend=compiler_backend,
            prompt_path=prompt_path,
        )


def build_research_synthesizer_object_context(*, runtime, object_id: str, subject: str, scope: str) -> ExistingObjectExecutionContext:
    try:
        return build_research_synthesis_execution_context(runtime=runtime, object_id=object_id, subject=subject, scope=scope)
    except SliceObjectContextError as exc:
        raise ResearchSynthesizerObjectContextError(str(exc)) from exc


def _deterministic_compile(
    observation: ResearchSynthesisObservationInput,
    object_context: ExistingObjectExecutionContext,
) -> dict[str, Any]:
    lowered = observation.synthesis_text.lower()
    extra = object_context.extra_payload
    if "bearish" in lowered:
        predicate = "synthesis_preview_bearish"
        direction = "bearish"
        claim_type = "predictive"
        value = "the bounded synthesis note previews a bearish synthesis without selecting a final working thesis"
    elif "bullish" in lowered:
        predicate = "synthesis_preview_bullish"
        direction = "bullish"
        claim_type = "predictive"
        value = "the bounded synthesis note previews a bullish synthesis without mutating the thesis graph"
    elif "risk" in lowered or str(extra.get("working_primary_conflict", "")) in {"high", "critical"}:
        predicate = "synthesis_risk_preview"
        direction = "risk"
        claim_type = "risk_flag"
        value = "the bounded synthesis note highlights synthesis risk and conflict posture rather than a publish-ready thesis"
    else:
        predicate = "synthesis_preview_monitor"
        direction = "neutral"
        claim_type = "predictive"
        value = "the bounded synthesis note remains monitoring-oriented and keeps thesis selection outside this slice"
    candidate = {
        "input_id": observation.input_id,
        "subject": observation.subject,
        "predicate": predicate,
        "value": normalize_text(value),
        "claim_type": claim_type,
        "direction": direction,
        "source_family": "analytics",
        "evidence_level": "E3",
        "confidence_hint": 68,
        "scope": observation.scope,
        "time_horizon": "medium",
    }
    return {
        "status": "success",
        "blocked_reason": None,
        "candidate_payloads": [candidate],
        "notes": ["deterministic compiler emitted one candidate payload"],
    }
