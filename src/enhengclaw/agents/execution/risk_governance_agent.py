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
from enhengclaw.agents.execution.context_views import ExistingObjectExecutionContext, build_risk_governance_execution_context
from enhengclaw.agents.execution.continue_existing_slice import (
    ContinueExistingSliceExecutionPipeline,
    ContinueExistingSliceExecutionResult,
    ContinueExistingSliceSpec,
    DeterministicContinueExistingSliceCompiler,
    OpenAICompatibleContinueExistingSliceBackend,
    RecordedTranscriptContinueExistingSliceBackend,
    live_backend_kwargs_from_env,
)
from enhengclaw.agents.schemas.risk_governance_agent import RiskGovernanceSignalDraft


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "risk_governance_agent.system.md"
RISK_GOVERNANCE_AGENT_COMPILER_CONTRACT_VERSION = "risk_governance_agent_compiler_v1"
RISK_GOVERNANCE_AGENT_LIVE_BACKEND_NAME = "openai_compatible_chat_completions"
RISK_GOVERNANCE_AGENT_RECORDED_BACKEND_NAME = "recorded_transcript_replay"
RISK_GOVERNANCE_AGENT_DETERMINISTIC_BACKEND_NAME = "deterministic_compiler"
PROMPT_TEMPLATE_VERSION = "risk_governance_agent_prompt_template_v1"
ALLOWED_PREDICATES = frozenset(
    {
        "governance_suppression_required",
        "risk_escalation_required",
        "restricted_monitoring_required",
        "governance_blocker_present",
    }
)


@dataclass(frozen=True, slots=True)
class RiskGovernanceObservationInput:
    input_id: str
    object_id: str
    subject: str
    scope: str
    governance_text: str

    def to_spec_input_payload(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "governance_text": self.governance_text,
        }

    def fingerprint(self) -> str:
        return sha256_fragment(
            {
                "object_id": self.object_id,
                "subject": self.subject,
                "scope": self.scope,
                "governance_text": self.governance_text,
            }
        )

    def text_value(self) -> str:
        return self.governance_text


RiskGovernanceExecutionResult = ContinueExistingSliceExecutionResult


class RiskGovernanceAgentLiveBackendConfigError(SliceLiveBackendConfigError):
    pass


class RiskGovernanceAgentCompilerTransportError(SliceCompilerTransportError):
    pass


class RiskGovernanceAgentTranscriptReplayError(SliceTranscriptReplayError):
    pass


class RiskGovernanceAgentObjectContextError(SliceObjectContextError):
    pass


RISK_GOVERNANCE_SPEC = ContinueExistingSliceSpec(
    slice_id="risk_governance_agent",
    contract_version=RISK_GOVERNANCE_AGENT_COMPILER_CONTRACT_VERSION,
    prompt_template_version=PROMPT_TEMPLATE_VERSION,
    prompt_path=DEFAULT_PROMPT_PATH,
    input_text_label="governance_text",
    success_prompt_line="Compile one bounded governance-pressure observation into exactly one JSON compiler envelope.",
    live_backend_name=RISK_GOVERNANCE_AGENT_LIVE_BACKEND_NAME,
    recorded_backend_name=RISK_GOVERNANCE_AGENT_RECORDED_BACKEND_NAME,
    deterministic_backend_name=RISK_GOVERNANCE_AGENT_DETERMINISTIC_BACKEND_NAME,
    env_prefix="ENHENGCLAW_RISK_GOVERNANCE_AGENT_MODEL",
    draft_cls=RiskGovernanceSignalDraft,
    allowed_predicates=ALLOWED_PREDICATES,
    allowed_claim_types=frozenset({"risk_flag", "invalidation"}),
    allowed_directions=frozenset({"risk", "invalidating"}),
    allowed_source_families=frozenset({"safety", "analytics", "official"}),
    allowed_evidence_levels=frozenset({"E2", "E3", "E4", "E5"}),
    allowed_time_horizons=frozenset({"short", "medium", "structural"}),
    build_object_context=build_risk_governance_execution_context,
    deterministic_compile=lambda observation, object_context: _deterministic_compile(observation, object_context),
)


class OpenAICompatibleRiskGovernanceAgentBackend(OpenAICompatibleContinueExistingSliceBackend):
    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(spec=RISK_GOVERNANCE_SPEC, **kwargs)
        except SliceLiveBackendConfigError as exc:
            raise RiskGovernanceAgentLiveBackendConfigError(str(exc)) from exc

    @classmethod
    def from_env(cls) -> OpenAICompatibleRiskGovernanceAgentBackend:
        try:
            return cls(**live_backend_kwargs_from_env(RISK_GOVERNANCE_SPEC))
        except SliceLiveBackendConfigError as exc:
            raise RiskGovernanceAgentLiveBackendConfigError(str(exc)) from exc

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceCompilerTransportError as exc:
            raise RiskGovernanceAgentCompilerTransportError(str(exc)) from exc


class RecordedTranscriptRiskGovernanceAgentBackend(RecordedTranscriptContinueExistingSliceBackend):
    def __init__(self, *, transcript_path: str | Path) -> None:
        super().__init__(spec=RISK_GOVERNANCE_SPEC, transcript_path=transcript_path)

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceTranscriptReplayError as exc:
            raise RiskGovernanceAgentTranscriptReplayError(str(exc)) from exc


class DeterministicRiskGovernanceAgentCompiler(DeterministicContinueExistingSliceCompiler):
    def __init__(self) -> None:
        super().__init__(spec=RISK_GOVERNANCE_SPEC)


class RiskGovernanceExecutionPipeline(ContinueExistingSliceExecutionPipeline):
    def __init__(self, *, artifact_store=None, compiler_backend=None, prompt_path: str | Path | None = None) -> None:
        super().__init__(
            spec=RISK_GOVERNANCE_SPEC,
            artifact_store=artifact_store,
            compiler_backend=compiler_backend,
            prompt_path=prompt_path,
        )


def build_risk_governance_object_context(*, runtime, object_id: str, subject: str, scope: str) -> ExistingObjectExecutionContext:
    try:
        return build_risk_governance_execution_context(runtime=runtime, object_id=object_id, subject=subject, scope=scope)
    except SliceObjectContextError as exc:
        raise RiskGovernanceAgentObjectContextError(str(exc)) from exc


def _deterministic_compile(
    observation: RiskGovernanceObservationInput,
    object_context: ExistingObjectExecutionContext,
) -> dict[str, Any]:
    lowered = observation.governance_text.lower()
    if "restricted monitoring" in lowered or str(object_context.extra_payload.get("governance_posture", "")) == "restricted_monitoring":
        predicate = "restricted_monitoring_required"
        value = (
            "the bounded governance note indicates restricted monitoring should remain active until targeted review clears the object"
        )
        source_family = "analytics"
    elif "suppression" in lowered or "publish suppressed" in lowered or "do not publish" in lowered:
        predicate = "governance_suppression_required"
        value = (
            "the bounded governance note requires publish suppression and a conservative posture for the current object"
        )
        source_family = "safety"
    elif "escalat" in lowered or "tighten" in lowered:
        predicate = "risk_escalation_required"
        value = "the bounded governance note recommends escalating the object's risk posture without broadening authority"
        source_family = "official"
    elif "blocker" in lowered or "governance hold" in lowered:
        predicate = "governance_blocker_present"
        value = "the bounded governance note identifies one governance blocker that should remain attached to the object"
        source_family = "official"
    else:
        return {
            "status": "blocked",
            "blocked_reason": "deterministic compiler could not map the governance text to a stable supported predicate",
            "candidate_payloads": [],
            "notes": ["deterministic compiler failed closed"],
        }
    candidate = {
        "input_id": observation.input_id,
        "subject": observation.subject,
        "predicate": predicate,
        "value": normalize_text(value),
        "claim_type": "risk_flag",
        "direction": "risk",
        "source_family": source_family,
        "evidence_level": "E4",
        "confidence_hint": 72,
        "scope": observation.scope,
        "time_horizon": "short",
    }
    return {
        "status": "success",
        "blocked_reason": None,
        "candidate_payloads": [candidate],
        "notes": ["deterministic compiler emitted one candidate payload"],
    }
