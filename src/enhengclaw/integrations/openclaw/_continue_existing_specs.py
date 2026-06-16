from __future__ import annotations

from enhengclaw.agents.execution.attention_allocator import (
    AttentionAllocatorExecutionPipeline,
    AttentionAllocatorObjectContextError,
    AttentionAllocatorObservationInput,
    DeterministicAttentionAllocatorCompiler,
    OpenAICompatibleAttentionAllocatorBackend,
    RecordedTranscriptAttentionAllocatorBackend,
    build_attention_allocator_object_context,
)
from enhengclaw.agents.execution.evidence_agent import (
    DeterministicEvidenceAgentCompiler,
    EvidenceAgentExecutionPipeline,
    EvidenceObjectContextError,
    EvidenceObjectContextSummary,
    EvidenceObservationInput,
    OpenAICompatibleEvidenceAgentBackend,
    RecordedTranscriptEvidenceAgentBackend,
)
from enhengclaw.agents.execution.research_lead import (
    DeterministicResearchLeadCompiler,
    OpenAICompatibleResearchLeadBackend,
    RecordedTranscriptResearchLeadBackend,
    ResearchLeadExecutionPipeline,
    ResearchLeadObjectContextError,
    ResearchLeadObservationInput,
    build_research_lead_object_context,
)
from enhengclaw.agents.execution.research_synthesizer import (
    DeterministicResearchSynthesizerCompiler,
    OpenAICompatibleResearchSynthesizerBackend,
    RecordedTranscriptResearchSynthesizerBackend,
    ResearchSynthesisExecutionPipeline,
    ResearchSynthesisObservationInput,
    ResearchSynthesizerObjectContextError,
    build_research_synthesizer_object_context,
)
from enhengclaw.agents.execution.risk_governance_agent import (
    DeterministicRiskGovernanceAgentCompiler,
    OpenAICompatibleRiskGovernanceAgentBackend,
    RecordedTranscriptRiskGovernanceAgentBackend,
    RiskGovernanceAgentObjectContextError,
    RiskGovernanceExecutionPipeline,
    RiskGovernanceObservationInput,
    build_risk_governance_object_context,
)
from enhengclaw.agents.execution.risk_signal_agent import (
    DeterministicRiskSignalAgentCompiler,
    OpenAICompatibleRiskSignalAgentBackend,
    RecordedTranscriptRiskSignalAgentBackend,
    RiskSignalAgentObjectContextError,
    RiskSignalExecutionPipeline,
    RiskSignalObservationInput,
    build_risk_signal_object_context,
)
from enhengclaw.agents.execution.validation_agent import (
    DeterministicValidationAgentCompiler,
    OpenAICompatibleValidationAgentBackend,
    RecordedTranscriptValidationAgentBackend,
    ValidationAgentObjectContextError,
    ValidationExecutionPipeline,
    ValidationObservationInput,
    build_validation_object_context,
)
from enhengclaw.integrations.openclaw._continue_existing import (
    OpenClawContinueExistingLaneSpec,
    OpenClawContinueExistingRequest,
)


def _backend_from_request(
    request: OpenClawContinueExistingRequest,
    *,
    live_backend_cls,
    recorded_backend_cls,
    deterministic_backend_cls,
):
    if request.compiler_backend == "live":
        return live_backend_cls.from_env()
    if request.compiler_backend == "recorded":
        transcript_path = request.recorded_transcript_path
        if transcript_path is None:
            raise ValueError("recorded_transcript_path is required when compiler_backend=recorded")
        return recorded_backend_cls(transcript_path=transcript_path)
    return deterministic_backend_cls()


def _observation_input_id(request: OpenClawContinueExistingRequest, agent_id: str) -> str:
    return request.input_id or f"{agent_id}:{request.object_id}:1"


EVIDENCE_AGENT_LANE = OpenClawContinueExistingLaneSpec(
    agent_id="evidence_agent",
    contract_version="openclaw-evidence-agent.v1",
    text_field_name="evidence_text",
    entrypoint_module="enhengclaw.integrations.openclaw.evidence_agent",
    description="Run the OpenClaw deployment adapter for the shipped evidence_agent lane.",
    missing_object_context_reason="missing existing object context for evidence_agent",
    build_observation=lambda request: EvidenceObservationInput(
        input_id=_observation_input_id(request, "evidence_agent"),
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        evidence_text=request.text_value.strip(),
    ),
    build_compiler_backend=lambda request: _backend_from_request(
        request,
        live_backend_cls=OpenAICompatibleEvidenceAgentBackend,
        recorded_backend_cls=RecordedTranscriptEvidenceAgentBackend,
        deterministic_backend_cls=DeterministicEvidenceAgentCompiler,
    ),
    pipeline_cls=EvidenceAgentExecutionPipeline,
    build_object_context=lambda *, runtime, object_id, subject, scope: EvidenceObjectContextSummary.from_runtime_session(
        runtime.store.load(object_id),
        subject=subject,
        scope=scope,
    ),
    object_context_error_types=(EvidenceObjectContextError,),
)


RISK_SIGNAL_AGENT_LANE = OpenClawContinueExistingLaneSpec(
    agent_id="risk_signal_agent",
    contract_version="openclaw-risk-signal-agent.v1",
    text_field_name="risk_text",
    entrypoint_module="enhengclaw.integrations.openclaw.risk_signal_agent",
    description="Run the OpenClaw deployment adapter for the shipped risk_signal_agent lane.",
    missing_object_context_reason="missing existing object context for risk_signal_agent",
    build_observation=lambda request: RiskSignalObservationInput(
        input_id=_observation_input_id(request, "risk_signal_agent"),
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        risk_text=request.text_value.strip(),
    ),
    build_compiler_backend=lambda request: _backend_from_request(
        request,
        live_backend_cls=OpenAICompatibleRiskSignalAgentBackend,
        recorded_backend_cls=RecordedTranscriptRiskSignalAgentBackend,
        deterministic_backend_cls=DeterministicRiskSignalAgentCompiler,
    ),
    pipeline_cls=RiskSignalExecutionPipeline,
    build_object_context=build_risk_signal_object_context,
    object_context_error_types=(RiskSignalAgentObjectContextError,),
)


ATTENTION_ALLOCATOR_LANE = OpenClawContinueExistingLaneSpec(
    agent_id="attention_allocator",
    contract_version="openclaw-attention-allocator.v1",
    text_field_name="attention_text",
    entrypoint_module="enhengclaw.integrations.openclaw.attention_allocator",
    description="Run the OpenClaw deployment adapter for the shipped attention_allocator lane.",
    missing_object_context_reason="missing existing object context for attention_allocator",
    build_observation=lambda request: AttentionAllocatorObservationInput(
        input_id=_observation_input_id(request, "attention_allocator"),
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        attention_text=request.text_value.strip(),
    ),
    build_compiler_backend=lambda request: _backend_from_request(
        request,
        live_backend_cls=OpenAICompatibleAttentionAllocatorBackend,
        recorded_backend_cls=RecordedTranscriptAttentionAllocatorBackend,
        deterministic_backend_cls=DeterministicAttentionAllocatorCompiler,
    ),
    pipeline_cls=AttentionAllocatorExecutionPipeline,
    build_object_context=build_attention_allocator_object_context,
    object_context_error_types=(AttentionAllocatorObjectContextError,),
)


RESEARCH_SYNTHESIZER_LANE = OpenClawContinueExistingLaneSpec(
    agent_id="research_synthesizer",
    contract_version="openclaw-research-synthesizer.v1",
    text_field_name="synthesis_text",
    entrypoint_module="enhengclaw.integrations.openclaw.research_synthesizer",
    description="Run the OpenClaw deployment adapter for the shipped research_synthesizer lane.",
    missing_object_context_reason="missing existing object context for research_synthesizer",
    build_observation=lambda request: ResearchSynthesisObservationInput(
        input_id=_observation_input_id(request, "research_synthesizer"),
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        synthesis_text=request.text_value.strip(),
    ),
    build_compiler_backend=lambda request: _backend_from_request(
        request,
        live_backend_cls=OpenAICompatibleResearchSynthesizerBackend,
        recorded_backend_cls=RecordedTranscriptResearchSynthesizerBackend,
        deterministic_backend_cls=DeterministicResearchSynthesizerCompiler,
    ),
    pipeline_cls=ResearchSynthesisExecutionPipeline,
    build_object_context=build_research_synthesizer_object_context,
    object_context_error_types=(ResearchSynthesizerObjectContextError,),
)


RESEARCH_LEAD_LANE = OpenClawContinueExistingLaneSpec(
    agent_id="research_lead",
    contract_version="openclaw-research-lead.v1",
    text_field_name="directive_text",
    entrypoint_module="enhengclaw.integrations.openclaw.research_lead",
    description="Run the OpenClaw deployment adapter for the shipped research_lead lane.",
    missing_object_context_reason="missing existing object context for research_lead",
    build_observation=lambda request: ResearchLeadObservationInput(
        input_id=_observation_input_id(request, "research_lead"),
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        directive_text=request.text_value.strip(),
    ),
    build_compiler_backend=lambda request: _backend_from_request(
        request,
        live_backend_cls=OpenAICompatibleResearchLeadBackend,
        recorded_backend_cls=RecordedTranscriptResearchLeadBackend,
        deterministic_backend_cls=DeterministicResearchLeadCompiler,
    ),
    pipeline_cls=ResearchLeadExecutionPipeline,
    build_object_context=build_research_lead_object_context,
    object_context_error_types=(ResearchLeadObjectContextError,),
)


RISK_GOVERNANCE_AGENT_LANE = OpenClawContinueExistingLaneSpec(
    agent_id="risk_governance_agent",
    contract_version="openclaw-risk-governance-agent.v1",
    text_field_name="governance_text",
    entrypoint_module="enhengclaw.integrations.openclaw.risk_governance_agent",
    description="Run the OpenClaw deployment adapter for the shipped risk_governance_agent lane.",
    missing_object_context_reason="missing existing object context for risk_governance_agent",
    build_observation=lambda request: RiskGovernanceObservationInput(
        input_id=_observation_input_id(request, "risk_governance_agent"),
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        governance_text=request.text_value.strip(),
    ),
    build_compiler_backend=lambda request: _backend_from_request(
        request,
        live_backend_cls=OpenAICompatibleRiskGovernanceAgentBackend,
        recorded_backend_cls=RecordedTranscriptRiskGovernanceAgentBackend,
        deterministic_backend_cls=DeterministicRiskGovernanceAgentCompiler,
    ),
    pipeline_cls=RiskGovernanceExecutionPipeline,
    build_object_context=build_risk_governance_object_context,
    object_context_error_types=(RiskGovernanceAgentObjectContextError,),
)


VALIDATION_AGENT_LANE = OpenClawContinueExistingLaneSpec(
    agent_id="validation_agent",
    contract_version="openclaw-validation-agent.v1",
    text_field_name="validation_text",
    entrypoint_module="enhengclaw.integrations.openclaw.validation_agent",
    description="Run the OpenClaw deployment adapter for the shipped validation_agent lane.",
    missing_object_context_reason="missing existing object context for validation_agent",
    build_observation=lambda request: ValidationObservationInput(
        input_id=_observation_input_id(request, "validation_agent"),
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        validation_text=request.text_value.strip(),
    ),
    build_compiler_backend=lambda request: _backend_from_request(
        request,
        live_backend_cls=OpenAICompatibleValidationAgentBackend,
        recorded_backend_cls=RecordedTranscriptValidationAgentBackend,
        deterministic_backend_cls=DeterministicValidationAgentCompiler,
    ),
    pipeline_cls=ValidationExecutionPipeline,
    build_object_context=build_validation_object_context,
    object_context_error_types=(ValidationAgentObjectContextError,),
)


OPENCLAW_CONTINUE_EXISTING_LANE_SPECS = {
    spec.agent_id: spec
    for spec in (
        EVIDENCE_AGENT_LANE,
        RISK_SIGNAL_AGENT_LANE,
        ATTENTION_ALLOCATOR_LANE,
        RESEARCH_SYNTHESIZER_LANE,
        RESEARCH_LEAD_LANE,
        RISK_GOVERNANCE_AGENT_LANE,
        VALIDATION_AGENT_LANE,
    )
}
