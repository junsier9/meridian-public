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
from enhengclaw.agents.execution.context_views import ExistingObjectExecutionContext, build_risk_signal_execution_context
from enhengclaw.agents.execution.continue_existing_slice import (
    ContinueExistingSliceExecutionPipeline,
    ContinueExistingSliceExecutionResult,
    ContinueExistingSliceSpec,
    DeterministicContinueExistingSliceCompiler,
    OpenAICompatibleContinueExistingSliceBackend,
    RecordedTranscriptContinueExistingSliceBackend,
    live_backend_kwargs_from_env,
)
from enhengclaw.agents.schemas.risk_signal_agent import RiskSignalDraft


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "risk_signal_agent.system.md"
RISK_SIGNAL_AGENT_COMPILER_CONTRACT_VERSION = "risk_signal_agent_compiler_v1"
RISK_SIGNAL_AGENT_LIVE_BACKEND_NAME = "openai_compatible_chat_completions"
RISK_SIGNAL_AGENT_RECORDED_BACKEND_NAME = "recorded_transcript_replay"
RISK_SIGNAL_AGENT_DETERMINISTIC_BACKEND_NAME = "deterministic_compiler"
PROMPT_TEMPLATE_VERSION = "risk_signal_agent_prompt_template_v1"
ALLOWED_PREDICATES = frozenset(
    {
        "fresh_invalidation_risk",
        "headline_risk",
        "suppression_risk",
        "risk_state_caution",
    }
)


@dataclass(frozen=True, slots=True)
class RiskSignalObservationInput:
    input_id: str
    object_id: str
    subject: str
    scope: str
    risk_text: str

    def to_spec_input_payload(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "risk_text": self.risk_text,
        }

    def fingerprint(self) -> str:
        return sha256_fragment(
            {
                "object_id": self.object_id,
                "subject": self.subject,
                "scope": self.scope,
                "risk_text": self.risk_text,
            }
        )

    def text_value(self) -> str:
        return self.risk_text


RiskSignalExecutionResult = ContinueExistingSliceExecutionResult


class RiskSignalAgentLiveBackendConfigError(SliceLiveBackendConfigError):
    pass


class RiskSignalAgentCompilerTransportError(SliceCompilerTransportError):
    pass


class RiskSignalAgentTranscriptReplayError(SliceTranscriptReplayError):
    pass


class RiskSignalAgentObjectContextError(SliceObjectContextError):
    pass


RISK_SIGNAL_SPEC = ContinueExistingSliceSpec(
    slice_id="risk_signal_agent",
    contract_version=RISK_SIGNAL_AGENT_COMPILER_CONTRACT_VERSION,
    prompt_template_version=PROMPT_TEMPLATE_VERSION,
    prompt_path=DEFAULT_PROMPT_PATH,
    input_text_label="risk_text",
    success_prompt_line="Compile one bounded risk observation into exactly one JSON compiler envelope.",
    live_backend_name=RISK_SIGNAL_AGENT_LIVE_BACKEND_NAME,
    recorded_backend_name=RISK_SIGNAL_AGENT_RECORDED_BACKEND_NAME,
    deterministic_backend_name=RISK_SIGNAL_AGENT_DETERMINISTIC_BACKEND_NAME,
    env_prefix="ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL",
    draft_cls=RiskSignalDraft,
    allowed_predicates=ALLOWED_PREDICATES,
    allowed_claim_types=frozenset({"risk_flag", "invalidation"}),
    allowed_directions=frozenset({"risk", "invalidating"}),
    allowed_source_families=frozenset({"safety", "analytics", "official"}),
    allowed_evidence_levels=frozenset({"E2", "E3", "E4", "E5"}),
    allowed_time_horizons=frozenset({"short", "medium", "structural"}),
    build_object_context=build_risk_signal_execution_context,
    deterministic_compile=lambda observation, object_context: _deterministic_compile(observation, object_context),
    required_value_segments=("facts=", "interpretation=", "uncertainty="),
)


class OpenAICompatibleRiskSignalAgentBackend(OpenAICompatibleContinueExistingSliceBackend):
    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(spec=RISK_SIGNAL_SPEC, **kwargs)
        except SliceLiveBackendConfigError as exc:
            raise RiskSignalAgentLiveBackendConfigError(str(exc)) from exc

    @classmethod
    def from_env(cls) -> OpenAICompatibleRiskSignalAgentBackend:
        try:
            return cls(**live_backend_kwargs_from_env(RISK_SIGNAL_SPEC))
        except SliceLiveBackendConfigError as exc:
            raise RiskSignalAgentLiveBackendConfigError(str(exc)) from exc

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceCompilerTransportError as exc:
            raise RiskSignalAgentCompilerTransportError(str(exc)) from exc


class RecordedTranscriptRiskSignalAgentBackend(RecordedTranscriptContinueExistingSliceBackend):
    def __init__(self, *, transcript_path: str | Path) -> None:
        super().__init__(spec=RISK_SIGNAL_SPEC, transcript_path=transcript_path)

    def compile(self, **kwargs: Any):
        try:
            return super().compile(**kwargs)
        except SliceTranscriptReplayError as exc:
            raise RiskSignalAgentTranscriptReplayError(str(exc)) from exc


class DeterministicRiskSignalAgentCompiler(DeterministicContinueExistingSliceCompiler):
    def __init__(self) -> None:
        super().__init__(spec=RISK_SIGNAL_SPEC)


class RiskSignalExecutionPipeline(ContinueExistingSliceExecutionPipeline):
    def __init__(
        self,
        *,
        artifact_store=None,
        compiler_backend=None,
        prompt_path: str | Path | None = None,
    ) -> None:
        super().__init__(
            spec=RISK_SIGNAL_SPEC,
            artifact_store=artifact_store,
            compiler_backend=compiler_backend,
            prompt_path=prompt_path,
        )


def build_risk_signal_object_context(*, runtime, object_id: str, subject: str, scope: str) -> ExistingObjectExecutionContext:
    try:
        return build_risk_signal_execution_context(runtime.store.load(object_id), subject=subject, scope=scope)
    except SliceObjectContextError as exc:
        raise RiskSignalAgentObjectContextError(str(exc)) from exc


def _deterministic_compile(
    observation: RiskSignalObservationInput,
    object_context: ExistingObjectExecutionContext,
) -> dict[str, Any]:
    lowered = observation.risk_text.lower()
    if any(
        token in lowered
        for token in (
            "oos stability",
            "out-of-sample stability",
            "liquidity envelope",
            "liquidity/risk envelope",
            "risk envelope",
            "exits the allowed liquidity",
        )
    ):
        candidate = {
            "input_id": observation.input_id,
            "subject": observation.subject,
            "predicate": "fresh_invalidation_risk",
            "value": (
                "facts=the bounded risk text names loss of OOS stability or a liquidity-envelope breach as an invalidation trigger; "
                "interpretation=the current object now carries one explicit quant invalidation risk signal; "
                "uncertainty=the trigger still depends on the next cycle outcome and host review"
            ),
            "claim_type": "invalidation",
            "direction": "invalidating",
            "source_family": "analytics",
            "evidence_level": "E4",
            "confidence_hint": 74,
            "scope": observation.scope,
            "time_horizon": "short",
        }
    elif "breakdown" in lowered or "invalidation" in lowered or "reversal" in lowered:
        candidate = {
            "input_id": observation.input_id,
            "subject": observation.subject,
            "predicate": "fresh_invalidation_risk",
            "value": (
                "facts=fresh invalidation cues are visible in the bounded risk observation; "
                "interpretation=the current object now carries one clear invalidation-oriented risk signal; "
                "uncertainty=full invalidation still depends on follow-through and host review"
            ),
            "claim_type": "invalidation",
            "direction": "invalidating",
            "source_family": "safety",
            "evidence_level": "E4",
            "confidence_hint": 72,
            "scope": observation.scope,
            "time_horizon": "short",
        }
    elif "headline" in lowered or "news" in lowered or "downgrade" in lowered:
        candidate = {
            "input_id": observation.input_id,
            "subject": observation.subject,
            "predicate": "headline_risk",
            "value": (
                "facts=the bounded risk text describes a fresh headline-driven downside concern; "
                "interpretation=the object should record one headline risk signal rather than broaden scope; "
                "uncertainty=headline durability and magnitude still need confirmation"
            ),
            "claim_type": "risk_flag",
            "direction": "risk",
            "source_family": "official",
            "evidence_level": "E3",
            "confidence_hint": 68,
            "scope": observation.scope,
            "time_horizon": "short",
        }
    elif "suppression" in lowered or "halt" in lowered or "pause" in lowered:
        candidate = {
            "input_id": observation.input_id,
            "subject": observation.subject,
            "predicate": "suppression_risk",
            "value": (
                "facts=the bounded risk text points to a suppression or pause requirement; "
                "interpretation=the object should attach one suppression-oriented risk note without changing governance directly; "
                "uncertainty=the suppression window and trigger still need host verification"
            ),
            "claim_type": "risk_flag",
            "direction": "risk",
            "source_family": "analytics",
            "evidence_level": "E4",
            "confidence_hint": 70,
            "scope": observation.scope,
            "time_horizon": "medium",
        }
    elif "caution" in lowered or object_context.common.risk_state in {"caution", "restricted"}:
        candidate = {
            "input_id": observation.input_id,
            "subject": observation.subject,
            "predicate": "risk_state_caution",
            "value": (
                "facts=the bounded risk note supports a cautious risk posture for the existing object; "
                "interpretation=one cautionary risk signal is justified without expanding into governance or publish logic; "
                "uncertainty=whether the caution should escalate still depends on stronger evidence"
            ),
            "claim_type": "risk_flag",
            "direction": "risk",
            "source_family": "analytics",
            "evidence_level": "E3",
            "confidence_hint": 66,
            "scope": observation.scope,
            "time_horizon": "short",
        }
    else:
        return {
            "status": "blocked",
            "blocked_reason": "deterministic compiler could not map the risk text to a stable supported predicate",
            "candidate_payloads": [],
            "notes": ["deterministic compiler failed closed"],
        }
    candidate["value"] = normalize_text(str(candidate["value"]))
    return {
        "status": "success",
        "blocked_reason": None,
        "candidate_payloads": [candidate],
        "notes": ["deterministic compiler emitted one candidate payload"],
    }
