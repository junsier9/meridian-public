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
from enhengclaw.agents.execution.context_views import ExistingObjectExecutionContext, build_attention_execution_context
from enhengclaw.agents.execution.continue_existing_slice import (
    ContinueExistingSliceExecutionPipeline,
    ContinueExistingSliceExecutionResult,
    ContinueExistingSliceSpec,
    DeterministicContinueExistingSliceCompiler,
    OpenAICompatibleContinueExistingSliceBackend,
    RecordedTranscriptContinueExistingSliceBackend,
    live_backend_kwargs_from_env,
)
from enhengclaw.agents.schemas.attention_allocator import AttentionAllocatorSignalDraft


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "attention_allocator.system.md"
ATTENTION_ALLOCATOR_COMPILER_CONTRACT_VERSION = "attention_allocator_compiler_v1"
ATTENTION_ALLOCATOR_LIVE_BACKEND_NAME = "openai_compatible_chat_completions"
ATTENTION_ALLOCATOR_RECORDED_BACKEND_NAME = "recorded_transcript_replay"
ATTENTION_ALLOCATOR_DETERMINISTIC_BACKEND_NAME = "deterministic_compiler"
PROMPT_TEMPLATE_VERSION = "attention_allocator_prompt_template_v1"
ALLOWED_PREDICATES = frozenset(
    {
        "attention_posture_monitor",
        "attention_posture_advance",
        "attention_posture_archive",
        "attention_posture_hold",
    }
)


@dataclass(frozen=True, slots=True)
class AttentionAllocatorObservationInput:
    input_id: str
    object_id: str
    subject: str
    scope: str
    attention_text: str

    def to_spec_input_payload(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "attention_text": self.attention_text,
        }

    def fingerprint(self) -> str:
        return sha256_fragment(
            {
                "object_id": self.object_id,
                "subject": self.subject,
                "scope": self.scope,
                "attention_text": self.attention_text,
            }
        )

    def text_value(self) -> str:
        return self.attention_text


AttentionAllocatorExecutionResult = ContinueExistingSliceExecutionResult


class AttentionAllocatorLiveBackendConfigError(SliceLiveBackendConfigError):
    pass


class AttentionAllocatorCompilerTransportError(SliceCompilerTransportError):
    pass


class AttentionAllocatorTranscriptReplayError(SliceTranscriptReplayError):
    pass


class AttentionAllocatorObjectContextError(SliceObjectContextError):
    pass


ATTENTION_ALLOCATOR_SPEC = ContinueExistingSliceSpec(
    slice_id="attention_allocator",
    contract_version=ATTENTION_ALLOCATOR_COMPILER_CONTRACT_VERSION,
    prompt_template_version=PROMPT_TEMPLATE_VERSION,
    prompt_path=DEFAULT_PROMPT_PATH,
    input_text_label="attention_text",
    success_prompt_line="Compile one bounded attention-posture observation into exactly one JSON compiler envelope.",
    live_backend_name=ATTENTION_ALLOCATOR_LIVE_BACKEND_NAME,
    recorded_backend_name=ATTENTION_ALLOCATOR_RECORDED_BACKEND_NAME,
    deterministic_backend_name=ATTENTION_ALLOCATOR_DETERMINISTIC_BACKEND_NAME,
    env_prefix="ENHENGCLAW_ATTENTION_ALLOCATOR_MODEL",
    draft_cls=AttentionAllocatorSignalDraft,
    allowed_predicates=ALLOWED_PREDICATES,
    allowed_claim_types=frozenset({"measurement"}),
    allowed_directions=frozenset({"neutral"}),
    allowed_source_families=frozenset({"analytics"}),
    allowed_evidence_levels=frozenset({"E2", "E3", "E4"}),
    allowed_time_horizons=frozenset({"short", "medium"}),
    build_object_context=build_attention_execution_context,
    deterministic_compile=lambda observation, object_context: _deterministic_compile(observation, object_context),
)


class OpenAICompatibleAttentionAllocatorBackend(OpenAICompatibleContinueExistingSliceBackend):
    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(spec=ATTENTION_ALLOCATOR_SPEC, **kwargs)
        except SliceLiveBackendConfigError as exc:
            raise AttentionAllocatorLiveBackendConfigError(str(exc)) from exc

    @classmethod
    def from_env(cls) -> OpenAICompatibleAttentionAllocatorBackend:
        try:
            return cls(**live_backend_kwargs_from_env(ATTENTION_ALLOCATOR_SPEC))
        except SliceLiveBackendConfigError as exc:
            raise AttentionAllocatorLiveBackendConfigError(str(exc)) from exc

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceCompilerTransportError as exc:
            raise AttentionAllocatorCompilerTransportError(str(exc)) from exc


class RecordedTranscriptAttentionAllocatorBackend(RecordedTranscriptContinueExistingSliceBackend):
    def __init__(self, *, transcript_path: str | Path) -> None:
        super().__init__(spec=ATTENTION_ALLOCATOR_SPEC, transcript_path=transcript_path)

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceTranscriptReplayError as exc:
            raise AttentionAllocatorTranscriptReplayError(str(exc)) from exc


class DeterministicAttentionAllocatorCompiler(DeterministicContinueExistingSliceCompiler):
    def __init__(self) -> None:
        super().__init__(spec=ATTENTION_ALLOCATOR_SPEC)


class AttentionAllocatorExecutionPipeline(ContinueExistingSliceExecutionPipeline):
    def __init__(self, *, artifact_store=None, compiler_backend=None, prompt_path: str | Path | None = None) -> None:
        super().__init__(
            spec=ATTENTION_ALLOCATOR_SPEC,
            artifact_store=artifact_store,
            compiler_backend=compiler_backend,
            prompt_path=prompt_path,
        )


def build_attention_allocator_object_context(*, runtime, object_id: str, subject: str, scope: str) -> ExistingObjectExecutionContext:
    try:
        return build_attention_execution_context(runtime=runtime, object_id=object_id, subject=subject, scope=scope)
    except SliceObjectContextError as exc:
        raise AttentionAllocatorObjectContextError(str(exc)) from exc


def _deterministic_compile(
    observation: AttentionAllocatorObservationInput,
    object_context: ExistingObjectExecutionContext,
) -> dict[str, Any]:
    lowered = observation.attention_text.lower()
    assessment = object_context.extra_payload
    if "archive" in lowered or str(assessment.get("recommendation", "")) == "archive":
        predicate = "attention_posture_archive"
        value = "the bounded attention note supports archiving or near-zero attention for the current object"
    elif "advance" in lowered or str(assessment.get("recommendation", "")) == "advance":
        predicate = "attention_posture_advance"
        value = "the bounded attention note supports continued research attention without changing processing state directly"
    elif "hold" in lowered or str(assessment.get("recommendation", "")) == "hold":
        predicate = "attention_posture_hold"
        value = "the bounded attention note supports holding attention steady because the object remains constrained"
    elif "monitor" in lowered or str(assessment.get("recommendation", "")) == "monitor":
        predicate = "attention_posture_monitor"
        value = "the bounded attention note supports monitoring rather than expansion of attention"
    else:
        return {
            "status": "blocked",
            "blocked_reason": "deterministic compiler could not map the attention text to a stable supported predicate",
            "candidate_payloads": [],
            "notes": ["deterministic compiler failed closed"],
        }
    candidate = {
        "input_id": observation.input_id,
        "subject": observation.subject,
        "predicate": predicate,
        "value": normalize_text(value),
        "claim_type": "measurement",
        "direction": "neutral",
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
