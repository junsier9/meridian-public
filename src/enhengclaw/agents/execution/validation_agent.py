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
from enhengclaw.agents.execution.context_views import ExistingObjectExecutionContext, build_validation_execution_context
from enhengclaw.agents.execution.continue_existing_slice import (
    ContinueExistingSliceExecutionPipeline,
    ContinueExistingSliceExecutionResult,
    ContinueExistingSliceSpec,
    DeterministicContinueExistingSliceCompiler,
    OpenAICompatibleContinueExistingSliceBackend,
    RecordedTranscriptContinueExistingSliceBackend,
    live_backend_kwargs_from_env,
)
from enhengclaw.agents.schemas.validation_agent import ValidationBlockerSignalDraft


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "validation_agent.system.md"
VALIDATION_AGENT_COMPILER_CONTRACT_VERSION = "validation_agent_compiler_v1"
VALIDATION_AGENT_LIVE_BACKEND_NAME = "openai_compatible_chat_completions"
VALIDATION_AGENT_RECORDED_BACKEND_NAME = "recorded_transcript_replay"
VALIDATION_AGENT_DETERMINISTIC_BACKEND_NAME = "deterministic_compiler"
PROMPT_TEMPLATE_VERSION = "validation_agent_prompt_template_v1"
ALLOWED_PREDICATES = frozenset(
    {
        "publish_gate_hold",
        "unresolved_thesis_conflict",
        "validation_blocker_present",
        "evidence_gap_hold",
    }
)


@dataclass(frozen=True, slots=True)
class ValidationObservationInput:
    input_id: str
    object_id: str
    subject: str
    scope: str
    validation_text: str

    def to_spec_input_payload(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "validation_text": self.validation_text,
        }

    def fingerprint(self) -> str:
        return sha256_fragment(
            {
                "object_id": self.object_id,
                "subject": self.subject,
                "scope": self.scope,
                "validation_text": self.validation_text,
            }
        )

    def text_value(self) -> str:
        return self.validation_text


ValidationExecutionResult = ContinueExistingSliceExecutionResult


class ValidationAgentLiveBackendConfigError(SliceLiveBackendConfigError):
    pass


class ValidationAgentCompilerTransportError(SliceCompilerTransportError):
    pass


class ValidationAgentTranscriptReplayError(SliceTranscriptReplayError):
    pass


class ValidationAgentObjectContextError(SliceObjectContextError):
    pass


VALIDATION_SPEC = ContinueExistingSliceSpec(
    slice_id="validation_agent",
    contract_version=VALIDATION_AGENT_COMPILER_CONTRACT_VERSION,
    prompt_template_version=PROMPT_TEMPLATE_VERSION,
    prompt_path=DEFAULT_PROMPT_PATH,
    input_text_label="validation_text",
    success_prompt_line="Compile one bounded validation-blocker observation into exactly one JSON compiler envelope.",
    live_backend_name=VALIDATION_AGENT_LIVE_BACKEND_NAME,
    recorded_backend_name=VALIDATION_AGENT_RECORDED_BACKEND_NAME,
    deterministic_backend_name=VALIDATION_AGENT_DETERMINISTIC_BACKEND_NAME,
    env_prefix="ENHENGCLAW_VALIDATION_AGENT_MODEL",
    draft_cls=ValidationBlockerSignalDraft,
    allowed_predicates=ALLOWED_PREDICATES,
    allowed_claim_types=frozenset({"risk_flag", "invalidation"}),
    allowed_directions=frozenset({"risk", "invalidating"}),
    allowed_source_families=frozenset({"analytics", "official", "safety"}),
    allowed_evidence_levels=frozenset({"E2", "E3", "E4", "E5"}),
    allowed_time_horizons=frozenset({"short", "medium", "structural"}),
    build_object_context=build_validation_execution_context,
    deterministic_compile=lambda observation, object_context: _deterministic_compile(observation, object_context),
)


class OpenAICompatibleValidationAgentBackend(OpenAICompatibleContinueExistingSliceBackend):
    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(spec=VALIDATION_SPEC, **kwargs)
        except SliceLiveBackendConfigError as exc:
            raise ValidationAgentLiveBackendConfigError(str(exc)) from exc

    @classmethod
    def from_env(cls) -> OpenAICompatibleValidationAgentBackend:
        try:
            return cls(**live_backend_kwargs_from_env(VALIDATION_SPEC))
        except SliceLiveBackendConfigError as exc:
            raise ValidationAgentLiveBackendConfigError(str(exc)) from exc

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceCompilerTransportError as exc:
            raise ValidationAgentCompilerTransportError(str(exc)) from exc


class RecordedTranscriptValidationAgentBackend(RecordedTranscriptContinueExistingSliceBackend):
    def __init__(self, *, transcript_path: str | Path) -> None:
        super().__init__(spec=VALIDATION_SPEC, transcript_path=transcript_path)

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceTranscriptReplayError as exc:
            raise ValidationAgentTranscriptReplayError(str(exc)) from exc


class DeterministicValidationAgentCompiler(DeterministicContinueExistingSliceCompiler):
    def __init__(self) -> None:
        super().__init__(spec=VALIDATION_SPEC)


class ValidationExecutionPipeline(ContinueExistingSliceExecutionPipeline):
    def __init__(self, *, artifact_store=None, compiler_backend=None, prompt_path: str | Path | None = None) -> None:
        super().__init__(
            spec=VALIDATION_SPEC,
            artifact_store=artifact_store,
            compiler_backend=compiler_backend,
            prompt_path=prompt_path,
        )


def build_validation_object_context(*, runtime, object_id: str, subject: str, scope: str) -> ExistingObjectExecutionContext:
    try:
        return build_validation_execution_context(runtime=runtime, object_id=object_id, subject=subject, scope=scope)
    except SliceObjectContextError as exc:
        raise ValidationAgentObjectContextError(str(exc)) from exc


def _deterministic_compile(
    observation: ValidationObservationInput,
    object_context: ExistingObjectExecutionContext,
) -> dict[str, Any]:
    lowered = observation.validation_text.lower()
    extra = object_context.extra_payload
    if "publish" in lowered or extra.get("publish_gate_checked"):
        predicate = "publish_gate_hold"
        value = "the bounded validation note requires a publish-gate hold until outstanding checks are cleared"
    elif "thesis conflict" in lowered or extra.get("working_opposing_thesis_id"):
        predicate = "unresolved_thesis_conflict"
        value = "the bounded validation note identifies unresolved thesis conflict that should keep the object blocked"
    elif "evidence gap" in lowered or "missing evidence" in lowered:
        predicate = "evidence_gap_hold"
        value = "the bounded validation note highlights an evidence gap that prevents clean advancement"
    elif "blocker" in lowered or "hold" in lowered:
        predicate = "validation_blocker_present"
        value = "the bounded validation note identifies one blocker that should remain attached to the object"
    else:
        return {
            "status": "blocked",
            "blocked_reason": "deterministic compiler could not map the validation text to a stable supported predicate",
            "candidate_payloads": [],
            "notes": ["deterministic compiler failed closed"],
        }
    candidate = {
        "input_id": observation.input_id,
        "subject": observation.subject,
        "predicate": predicate,
        "value": normalize_text(value),
        "claim_type": "invalidation",
        "direction": "invalidating",
        "source_family": "analytics",
        "evidence_level": "E4",
        "confidence_hint": 71,
        "scope": observation.scope,
        "time_horizon": "short",
    }
    return {
        "status": "success",
        "blocked_reason": None,
        "candidate_payloads": [candidate],
        "notes": ["deterministic compiler emitted one candidate payload"],
    }
