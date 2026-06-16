from __future__ import annotations

import hashlib
from typing import Any, Protocol

from enhengclaw.agents.owner_state import CapabilityStatus, DelegateCallContext, OwnerArtifactStore
from enhengclaw.agents.schemas.attention_allocator import AttentionAllocatorSignalDraft
from enhengclaw.agents.schemas.evidence_agent import EvidenceSignalDraft
from enhengclaw.agents.schemas.market_observer import MarketObserverSignalDraft
from enhengclaw.agents.schemas.research_lead import ResearchLeadSignalDraft
from enhengclaw.agents.schemas.research_synthesizer import ResearchSynthesisSignalDraft
from enhengclaw.agents.schemas.risk_governance_agent import RiskGovernanceSignalDraft
from enhengclaw.agents.schemas.risk_signal_agent import RiskSignalDraft
from enhengclaw.agents.schemas.validation_agent import ValidationBlockerSignalDraft
from enhengclaw.core.enums import ObjectType
from enhengclaw.orchestration.runtime_runner import AgentIngressRuntimeResult, RuntimeOrchestrator


class UnsupportedGovernedDelegateDirectCallError(PermissionError):
    pass


class _SignalDraft(Protocol):
    subject: str
    scope: str

    def to_agent_payload(self) -> dict[str, object]:
        ...


def _reject_legacy_context(call_context: DelegateCallContext | None) -> None:
    if call_context is not None:
        raise UnsupportedGovernedDelegateDirectCallError(
            "governed delegate submitters no longer accept DelegateCallContext; use an owner-issued delegate capability"
        )


def _require_delegate_capability(
    *,
    expected_delegate_id: str,
    object_id: str,
    signal: _SignalDraft,
    delegate_capability: str | None,
    artifact_store: OwnerArtifactStore | None,
    call_context: DelegateCallContext | None,
) -> dict[str, Any]:
    _reject_legacy_context(call_context)
    if not delegate_capability:
        raise UnsupportedGovernedDelegateDirectCallError(
            "governed delegate submitters are owner-first internal adapters; direct calls must provide an owner-issued delegate capability"
        )
    if artifact_store is None:
        raise UnsupportedGovernedDelegateDirectCallError(
            "delegate capability validation requires an OwnerArtifactStore rooted at the owner artifact directory"
        )
    capability = artifact_store.find_capability(delegate_capability)
    if capability is None:
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability is unknown or was not issued by the owner")
    if str(capability.get("requested_delegate_id", "")).strip() != expected_delegate_id:
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability does not belong to this delegate")
    if str(capability.get("object_id", "")).strip() != object_id:
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability object_id does not match the requested object")
    if str(capability.get("subject", "")).strip() != signal.subject:
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability subject does not match the requested signal")
    if CapabilityStatus.normalize(str(capability.get("status", CapabilityStatus.ACTIVE.value))) != CapabilityStatus.ACTIVE:
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability is no longer active")
    owner_run_id = str(capability.get("owner_run_id", "")).strip()
    run_state_path = artifact_store.paths_for(owner_run_id).run_state_path
    if run_state_path.exists():
        run_record = artifact_store.load_json(run_state_path)
    else:
        run_record = artifact_store.load_run_record(owner_run_id)
    if run_record is None:
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability references an unknown owner run")
    if str(run_record.get("requested_delegate_id", "")).strip() != expected_delegate_id:
        raise UnsupportedGovernedDelegateDirectCallError("owner run delegate does not match the requested delegate")
    if str(run_record.get("object_id", "")).strip() != object_id:
        raise UnsupportedGovernedDelegateDirectCallError("owner run object_id does not match the requested object")
    if str(run_record.get("current_step_id", "")).strip() != str(capability.get("step_id", "")).strip():
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability does not match the active owner step")
    if str(run_record.get("current_idempotency_key", "")).strip() != str(capability.get("idempotency_key", "")).strip():
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability does not match the active owner idempotency key")
    if int(run_record.get("spec_version", 0)) != int(capability.get("spec_version", 0)):
        raise UnsupportedGovernedDelegateDirectCallError("delegate capability spec_version is stale")
    if str(run_record.get("state", "")).strip().upper() != "DELEGATED":
        raise UnsupportedGovernedDelegateDirectCallError("owner run is not currently delegated for this capability")
    return capability


def _owner_scenario(base_scenario: str, capability: dict[str, Any]) -> str:
    fingerprint = hashlib.sha1(
        "|".join(
            [
                str(capability.get("owner_run_id", "")),
                str(capability.get("capability_id", "")),
                str(capability.get("spec_version", "")),
                str(capability.get("step_id", "")),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"{base_scenario}__owner_first__{fingerprint}"


def _submit_new_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: _SignalDraft,
    object_type: ObjectType,
    scenario: str,
    expected_delegate_id: str,
    delegate_capability: str | None,
    artifact_store: OwnerArtifactStore | None,
    call_context: DelegateCallContext | None,
    execution_permit: Any | None,
) -> AgentIngressRuntimeResult:
    capability = _require_delegate_capability(
        expected_delegate_id=expected_delegate_id,
        object_id=object_id,
        signal=signal,
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
    )
    return runtime.run_new_from_agent_payloads(
        object_id=object_id,
        object_type=object_type,
        subject=signal.subject,
        scope=signal.scope,
        scenario=_owner_scenario(scenario, capability),
        payloads=[signal.to_agent_payload()],
        execution_permit=execution_permit,
    )


def _submit_existing_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: _SignalDraft,
    scenario: str,
    expected_delegate_id: str,
    delegate_capability: str | None,
    artifact_store: OwnerArtifactStore | None,
    call_context: DelegateCallContext | None,
    execution_permit: Any | None,
) -> AgentIngressRuntimeResult:
    capability = _require_delegate_capability(
        expected_delegate_id=expected_delegate_id,
        object_id=object_id,
        signal=signal,
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
    )
    return runtime.continue_existing_from_agent_payloads(
        object_id=object_id,
        subject=signal.subject,
        scenario=_owner_scenario(scenario, capability),
        payloads=[signal.to_agent_payload()],
        execution_permit=execution_permit,
    )


def submit_market_observer_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: MarketObserverSignalDraft,
    object_type: ObjectType = ObjectType.ASSET,
    scenario: str = "single_agent_market_observer",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
) -> AgentIngressRuntimeResult:
    return _submit_new_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        object_type=object_type,
        scenario=scenario,
        expected_delegate_id="market_observer",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )


def submit_evidence_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: EvidenceSignalDraft,
    scenario: str = "rulebook_evidence_agent",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
    object_type: ObjectType = ObjectType.ASSET,
) -> AgentIngressRuntimeResult:
    del object_type
    return _submit_existing_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        scenario=scenario,
        expected_delegate_id="evidence_agent",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )


def submit_risk_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: RiskSignalDraft,
    scenario: str = "rulebook_risk_signal_agent",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
    object_type: ObjectType = ObjectType.ASSET,
) -> AgentIngressRuntimeResult:
    del object_type
    return _submit_existing_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        scenario=scenario,
        expected_delegate_id="risk_signal_agent",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )


def submit_risk_governance_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: RiskGovernanceSignalDraft,
    scenario: str = "rulebook_risk_governance_agent",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
    object_type: ObjectType = ObjectType.ASSET,
) -> AgentIngressRuntimeResult:
    del object_type
    return _submit_existing_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        scenario=scenario,
        expected_delegate_id="risk_governance_agent",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )


def submit_validation_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: ValidationBlockerSignalDraft,
    scenario: str = "rulebook_validation_agent",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
    object_type: ObjectType = ObjectType.ASSET,
) -> AgentIngressRuntimeResult:
    del object_type
    return _submit_existing_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        scenario=scenario,
        expected_delegate_id="validation_agent",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )


def submit_attention_allocator_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: AttentionAllocatorSignalDraft,
    scenario: str = "rulebook_attention_allocator",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
    object_type: ObjectType = ObjectType.ASSET,
) -> AgentIngressRuntimeResult:
    del object_type
    return _submit_existing_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        scenario=scenario,
        expected_delegate_id="attention_allocator",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )


def submit_research_synthesis_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: ResearchSynthesisSignalDraft,
    scenario: str = "rulebook_research_synthesizer",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
    object_type: ObjectType = ObjectType.ASSET,
) -> AgentIngressRuntimeResult:
    del object_type
    return _submit_existing_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        scenario=scenario,
        expected_delegate_id="research_synthesizer",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )


def submit_research_lead_signal(
    *,
    runtime: RuntimeOrchestrator,
    object_id: str,
    signal: ResearchLeadSignalDraft,
    scenario: str = "rulebook_research_lead",
    delegate_capability: str | None = None,
    artifact_store: OwnerArtifactStore | None = None,
    call_context: DelegateCallContext | None = None,
    execution_permit: Any | None = None,
    object_type: ObjectType = ObjectType.ASSET,
) -> AgentIngressRuntimeResult:
    del object_type
    return _submit_existing_signal(
        runtime=runtime,
        object_id=object_id,
        signal=signal,
        scenario=scenario,
        expected_delegate_id="research_lead",
        delegate_capability=delegate_capability,
        artifact_store=artifact_store,
        call_context=call_context,
        execution_permit=execution_permit,
    )
