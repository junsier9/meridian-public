from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

from _canonical_demo_support import (
    build_governed_demo_runtime,
    governed_demo_session_path,
    resolve_governed_demo_artifacts_root,
    resolve_governed_demo_execution_permit,
)
from enhengclaw.agents.execution import (
    AttentionAllocatorExecutionPipeline,
    AttentionAllocatorObservationInput,
    DeterministicEvidenceAgentCompiler,
    DeterministicAttentionAllocatorCompiler,
    DeterministicMarketObserverCompiler,
    DeterministicResearchLeadCompiler,
    DeterministicResearchSynthesizerCompiler,
    DeterministicRiskGovernanceAgentCompiler,
    DeterministicRiskSignalAgentCompiler,
    DeterministicValidationAgentCompiler,
    EvidenceAgentExecutionPipeline,
    EvidenceObjectContextError,
    EvidenceObjectContextSummary,
    EvidenceObservationInput,
    MarketObservationInput,
    MarketObserverExecutionPipeline,
    OpenAICompatibleAttentionAllocatorBackend,
    OpenAICompatibleEvidenceAgentBackend,
    OpenAICompatibleMarketObserverBackend,
    OpenAICompatibleResearchLeadBackend,
    OpenAICompatibleResearchSynthesizerBackend,
    OpenAICompatibleRiskGovernanceAgentBackend,
    OpenAICompatibleRiskSignalAgentBackend,
    OpenAICompatibleValidationAgentBackend,
    RecordedTranscriptAttentionAllocatorBackend,
    RecordedTranscriptEvidenceAgentBackend,
    RecordedTranscriptMarketObserverBackend,
    RecordedTranscriptResearchLeadBackend,
    RecordedTranscriptResearchSynthesizerBackend,
    RecordedTranscriptRiskGovernanceAgentBackend,
    RecordedTranscriptRiskSignalAgentBackend,
    RecordedTranscriptValidationAgentBackend,
    ResearchLeadExecutionPipeline,
    ResearchLeadObservationInput,
    ResearchSynthesisExecutionPipeline,
    ResearchSynthesisObservationInput,
    RiskGovernanceExecutionPipeline,
    RiskGovernanceObservationInput,
    RiskSignalExecutionPipeline,
    RiskSignalObservationInput,
    ValidationExecutionPipeline,
    ValidationObservationInput,
)
from enhengclaw.agents.execution.attention_allocator import build_attention_allocator_object_context
from enhengclaw.agents.definitions.attention_allocator import ATTENTION_ALLOCATOR_AGENT
from enhengclaw.agents.definitions.evidence_agent import EVIDENCE_AGENT
from enhengclaw.agents.definitions.market_observer import MARKET_OBSERVER_AGENT
from enhengclaw.agents.definitions.research_lead import RESEARCH_LEAD_AGENT
from enhengclaw.agents.definitions.research_synthesizer import RESEARCH_SYNTHESIZER_AGENT
from enhengclaw.agents.definitions.risk_governance_agent import RISK_GOVERNANCE_AGENT
from enhengclaw.agents.definitions.risk_signal_agent import RISK_SIGNAL_AGENT
from enhengclaw.agents.definitions.validation_agent import VALIDATION_AGENT
from enhengclaw.agents.execution.research_lead import build_research_lead_object_context
from enhengclaw.agents.execution.research_synthesizer import build_research_synthesizer_object_context
from enhengclaw.agents.execution.risk_governance_agent import build_risk_governance_object_context
from enhengclaw.agents.execution.risk_signal_agent import build_risk_signal_object_context
from enhengclaw.agents.execution.validation_agent import build_validation_object_context
from enhengclaw.agents.owner_state import OwnerArtifactWriter, compute_idempotency_key
from enhengclaw.core.execution_control import MissingExecutionPermitError
from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.core.signals import Signal
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressValidationError
from enhengclaw.orchestration.agent_layer_governance import evaluate_agent_layer_governance
from enhengclaw.orchestration.runtime import GovernedAgentOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the canonical governed-agent ingress demos through the worker-backed runtime lane."
    )
    subparsers = parser.add_subparsers(dest="command")

    market_parser = subparsers.add_parser(
        "market_observer",
        help="Compile one raw observation into one governed draft, then run the owner-first create_new_object path.",
    )
    _add_market_observer_arguments(
        market_parser,
        object_id_default="market-observer-aix",
        subject_default="AIX",
        scope_default="spot+perp",
    )
    market_parser.set_defaults(func=_run_market_observer)

    evidence_parser = subparsers.add_parser(
        "evidence_agent",
        help="Compile one raw follow-up evidence observation, then run the owner-first continue_existing_object path.",
    )
    _add_evidence_agent_arguments(
        evidence_parser,
        object_id_default="evidence-agent-aix",
        subject_default="AIX",
        scope_default="spot+perp",
    )
    evidence_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seed create step and continue an already-persisted object under the chosen artifacts root.",
    )
    evidence_parser.set_defaults(func=_run_evidence_agent)

    risk_parser = subparsers.add_parser(
        "risk_signal_agent",
        help="Run the first promoted governed follow-up risk slice through the public owner-first path.",
    )
    _add_pending_raw_text_arguments(
        risk_parser,
        object_id_default="risk-signal-aix",
        subject_default="AIX",
        scope_default="spot+perp",
        text_argument="risk-text",
        file_argument="risk-file",
        help_prefix="risk_signal_agent",
    )
    risk_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seed create step and continue an already-persisted object under the chosen artifacts root.",
    )
    risk_parser.set_defaults(func=_run_risk_signal_agent)

    governance_parser = subparsers.add_parser(
        "risk_governance_agent",
        help="Run the promoted governance-pressure slice sample through the public owner-first path with required review gating.",
    )
    _add_pending_raw_text_arguments(
        governance_parser,
        object_id_default="risk-governance-aix",
        subject_default="AIX",
        scope_default="spot+perp",
        text_argument="governance-text",
        file_argument="governance-file",
        help_prefix="risk_governance_agent",
    )
    governance_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seed create step and continue an already-persisted object under the chosen artifacts root.",
    )
    governance_parser.set_defaults(func=_run_risk_governance_agent)

    validation_parser = subparsers.add_parser(
        "validation_agent",
        help="Run the promoted validation-blocker slice sample through the public owner-first path with required review gating.",
    )
    _add_pending_raw_text_arguments(
        validation_parser,
        object_id_default="validation-agent-aix",
        subject_default="AIX",
        scope_default="spot+perp",
        text_argument="validation-text",
        file_argument="validation-file",
        help_prefix="validation_agent",
    )
    validation_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seed create step and continue an already-persisted object under the chosen artifacts root.",
    )
    validation_parser.set_defaults(func=_run_validation_agent)

    attention_parser = subparsers.add_parser(
        "attention_allocator",
        help="Run the promoted attention-posture slice sample through the public owner-first path.",
    )
    _add_pending_raw_text_arguments(
        attention_parser,
        object_id_default="attention-allocator-aix",
        subject_default="AIX",
        scope_default="spot+perp",
        text_argument="attention-text",
        file_argument="attention-file",
        help_prefix="attention_allocator",
    )
    attention_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seed create step and continue an already-persisted object under the chosen artifacts root.",
    )
    attention_parser.set_defaults(func=_run_attention_allocator)

    synthesis_parser = subparsers.add_parser(
        "research_synthesizer",
        help="Run the promoted synthesis-preview slice sample through the public owner-first path.",
    )
    _add_pending_raw_text_arguments(
        synthesis_parser,
        object_id_default="research-synthesizer-aix",
        subject_default="AIX",
        scope_default="spot+perp",
        text_argument="synthesis-text",
        file_argument="synthesis-file",
        help_prefix="research_synthesizer",
    )
    synthesis_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seed create step and continue an already-persisted object under the chosen artifacts root.",
    )
    synthesis_parser.set_defaults(func=_run_research_synthesizer)

    lead_parser = subparsers.add_parser(
        "research_lead",
        help="Run the promoted next-stage directive slice sample through the public owner-first path.",
    )
    _add_pending_raw_text_arguments(
        lead_parser,
        object_id_default="research-lead-aix",
        subject_default="AIX",
        scope_default="spot+perp",
        text_argument="directive-text",
        file_argument="directive-file",
        help_prefix="research_lead",
    )
    lead_parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip the seed create step and continue an already-persisted object under the chosen artifacts root.",
    )
    lead_parser.set_defaults(func=_run_research_lead)
    return parser


def _add_shared_arguments(
    parser: argparse.ArgumentParser,
    *,
    object_id_default: str,
    subject_default: str,
    scope_default: str,
    predicate_default: str,
    value_default: str,
    confidence_default: int,
) -> None:
    parser.add_argument("--artifacts-root", default=None)
    parser.add_argument("--execution-permit", default=None)
    parser.add_argument("--require-external-permit", action="store_true")
    parser.add_argument("--object-id", default=object_id_default)
    parser.add_argument("--input-id", default=None)
    parser.add_argument("--subject", default=subject_default)
    parser.add_argument("--scope", default=scope_default)
    parser.add_argument("--predicate", default=predicate_default)
    parser.add_argument("--value", default=value_default)
    parser.add_argument("--confidence-hint", type=int, default=confidence_default)
    parser.add_argument("--claim-type", default=None)
    parser.add_argument("--direction", default=None)
    parser.add_argument("--source-family", default=None)
    parser.add_argument("--evidence-level", default=None)
    parser.add_argument("--time-horizon", default=None)


def _add_market_observer_arguments(
    parser: argparse.ArgumentParser,
    *,
    object_id_default: str,
    subject_default: str,
    scope_default: str,
) -> None:
    parser.add_argument("--artifacts-root", default=None)
    parser.add_argument("--execution-permit", default=None)
    parser.add_argument("--require-external-permit", action="store_true")
    parser.add_argument("--object-id", default=object_id_default)
    parser.add_argument("--input-id", default=None)
    parser.add_argument("--subject", default=subject_default)
    parser.add_argument("--scope", default=scope_default)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--observation-text", default=None)
    group.add_argument("--observation-file", default=None)
    parser.add_argument(
        "--compiler-backend",
        choices=("live", "recorded", "deterministic"),
        default="live",
        help="Choose the market_observer compiler backend. Public default is live and fails closed when model config is missing.",
    )
    parser.add_argument(
        "--recorded-transcript",
        default=None,
        help="Recorded transcript fixture path. Required when --compiler-backend=recorded.",
    )


def _add_evidence_agent_arguments(
    parser: argparse.ArgumentParser,
    *,
    object_id_default: str,
    subject_default: str,
    scope_default: str,
) -> None:
    parser.add_argument("--artifacts-root", default=None)
    parser.add_argument("--execution-permit", default=None)
    parser.add_argument("--require-external-permit", action="store_true")
    parser.add_argument("--object-id", default=object_id_default)
    parser.add_argument("--input-id", default=None)
    parser.add_argument("--subject", default=subject_default)
    parser.add_argument("--scope", default=scope_default)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--evidence-text", default=None)
    group.add_argument("--evidence-file", default=None)
    parser.add_argument(
        "--compiler-backend",
        choices=("live", "recorded", "deterministic"),
        default="live",
        help="Choose the evidence_agent compiler backend. Public default is live and fails closed when model config is missing.",
    )
    parser.add_argument(
        "--recorded-transcript",
        default=None,
        help="Recorded transcript fixture path. Required when --compiler-backend=recorded.",
    )


def _add_pending_raw_text_arguments(
    parser: argparse.ArgumentParser,
    *,
    object_id_default: str,
    subject_default: str,
    scope_default: str,
    text_argument: str,
    file_argument: str,
    help_prefix: str,
) -> None:
    parser.add_argument("--artifacts-root", default=None)
    parser.add_argument("--execution-permit", default=None)
    parser.add_argument("--require-external-permit", action="store_true")
    parser.add_argument("--object-id", default=object_id_default)
    parser.add_argument("--input-id", default=None)
    parser.add_argument("--subject", default=subject_default)
    parser.add_argument("--scope", default=scope_default)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(f"--{text_argument}", default=None)
    group.add_argument(f"--{file_argument}", default=None)
    parser.add_argument(
        "--compiler-backend",
        choices=("live", "recorded", "deterministic"),
        default="live",
        help=f"Choose the {help_prefix} compiler backend. Public default is live and fails closed when model config is missing.",
    )
    parser.add_argument(
        "--recorded-transcript",
        default=None,
        help="Recorded transcript fixture path. Required when --compiler-backend=recorded.",
    )


def _signal_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if args.claim_type is not None:
        overrides["claim_type"] = args.claim_type
    if args.direction is not None:
        overrides["direction"] = args.direction
    if args.source_family is not None:
        overrides["source_family"] = args.source_family
    if args.evidence_level is not None:
        overrides["evidence_level"] = args.evidence_level
    if args.time_horizon is not None:
        overrides["time_horizon"] = args.time_horizon
    return overrides


def _build_seed_signals(*, object_id: str, subject: str, scope: str) -> list[Signal]:
    return [
        Signal(
            signal_id=f"{object_id}:seed:1",
            object_type=ObjectType.ASSET,
            subject=subject,
            predicate="spot_breakout",
            value=f"{subject} spot structure remains constructive",
            claim_type=ClaimType.MEASUREMENT,
            direction=Direction.BULLISH,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=82,
            scope=scope,
            time_horizon=TimeHorizon.INTRADAY,
        ),
        Signal(
            signal_id=f"{object_id}:seed:2",
            object_type=ObjectType.ASSET,
            subject=subject,
            predicate="wallet_buy",
            value=f"{subject} still shows supportive flow from large buyers",
            claim_type=ClaimType.FLOW,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=78,
            scope=scope,
            time_horizon=TimeHorizon.INTRADAY,
        ),
    ]


def _run_market_observer(args: argparse.Namespace) -> dict[str, object]:
    agent_id = str(MARKET_OBSERVER_AGENT["agent_id"])
    artifacts_root = resolve_governed_demo_artifacts_root(artifacts_root=args.artifacts_root, agent_id=agent_id)
    owner_store = OwnerArtifactWriter(artifacts_root / "agent_owner")
    if args.require_external_permit and args.execution_permit is None:
        raise MissingExecutionPermitError(
            "governed-agent ingress demo requires --execution-permit when --require-external-permit is set"
        )
    observation = MarketObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{agent_id}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        observation_text=_market_observation_text(args),
    )
    with resolve_governed_demo_execution_permit(
        scope=args.scope,
        slug="governed-market-observer-demo",
        artifacts_root=artifacts_root,
        execution_permit_path=args.execution_permit,
        require_external_permit=args.require_external_permit,
    ) as (permit, _paths):
        execution = MarketObserverExecutionPipeline(
            artifact_store=owner_store,
            compiler_backend=_market_observer_backend(args),
        )
        execution_result = execution.execute(observation)
        runtime = build_governed_demo_runtime(artifacts_root=artifacts_root, execution_permit=permit)
        orchestrator = GovernedAgentOrchestrator(runtime=runtime)
        result = orchestrator.run_governed_write(
            requested_delegate_id=agent_id,
            object_id=args.object_id,
            subject=args.subject,
            scope=args.scope,
            signal_draft=execution_result.candidate_draft,
            artifacts_root=artifacts_root,
            execution_permit=permit,
            object_type=ObjectType.ASSET,
            user_intent="Create one governed runtime object from one bounded market observation.",
            constraints=("single_payload", "single_tool_call", "verify_before_finalize"),
            admission_blocked_reason=_market_observer_admission_blocked_reason(execution_result),
            spec_input_payload=observation.to_spec_input_payload(),
            admission_artifacts=execution_result.compiler_artifact_paths(),
        )
        step_id = _market_observer_step_id(
            agent_id=agent_id,
            object_id=args.object_id,
            subject=args.subject,
            scope=args.scope,
            spec_version=result.spec_version,
            execution_result=execution_result,
            observation=observation,
        )
        compiler_artifact_paths = execution.restamp_execution_artifacts(
            run_id=result.owner_run_id,
            step_id=step_id,
            spec_version=result.spec_version,
        )
        session = None if result.run_state != "FINALIZED" else runtime.store.load(args.object_id)
    return {
        "accepted_signal_ids": list(result.accepted_signal_ids),
        "agent_id": agent_id,
        "artifacts_root": str(artifacts_root),
        "blocked_reason": result.blocked_reason or execution_result.blocked_reason,
        "compiler_backend": execution_result.backend_kind,
        "quarantine_reason": execution_result.quarantine_reason,
        "decision": _market_observer_decision(result),
        "execution_status": execution_result.status,
        "compiler_artifact_paths": list(compiler_artifact_paths or execution_result.compiler_artifact_paths()),
        "object_id": args.object_id,
        "owner_run_id": result.owner_run_id,
        "spec_version": result.spec_version,
        "run_state": result.run_state,
        "final_output_path": result.final_output_path,
        "verification_path": result.verification_path,
        "processing_state": None if session is None else session.research_object.processing_state.value,
        "quarantine_paths": list(result.quarantine_paths),
        "replay_log_paths": list(result.replay_log_paths),
        "slice_mode": str(MARKET_OBSERVER_AGENT["slice_mode"]),
    }


def _market_observer_backend(args: argparse.Namespace):
    backend = str(args.compiler_backend).strip().lower()
    if backend == "live":
        if args.recorded_transcript is not None:
            raise ValueError("--recorded-transcript is only legal when --compiler-backend=recorded")
        return OpenAICompatibleMarketObserverBackend.from_env()
    if backend == "recorded":
        if args.recorded_transcript is None:
            raise ValueError("--recorded-transcript is required when --compiler-backend=recorded")
        return RecordedTranscriptMarketObserverBackend(transcript_path=args.recorded_transcript)
    if args.recorded_transcript is not None:
        raise ValueError("--recorded-transcript is only legal when --compiler-backend=recorded")
    return DeterministicMarketObserverCompiler()


def _market_observation_text(args: argparse.Namespace) -> str:
    if args.observation_text is not None:
        return str(args.observation_text)
    if args.observation_file is None:
        raise ValueError("market_observer requires --observation-text or --observation-file")
    return Path(args.observation_file).read_text(encoding="utf-8").strip()


def _evidence_agent_backend(args: argparse.Namespace):
    backend = str(args.compiler_backend).strip().lower()
    if backend == "live":
        if args.recorded_transcript is not None:
            raise ValueError("--recorded-transcript is only legal when --compiler-backend=recorded")
        return OpenAICompatibleEvidenceAgentBackend.from_env()
    if backend == "recorded":
        if args.recorded_transcript is None:
            raise ValueError("--recorded-transcript is required when --compiler-backend=recorded")
        return RecordedTranscriptEvidenceAgentBackend(transcript_path=args.recorded_transcript)
    if args.recorded_transcript is not None:
        raise ValueError("--recorded-transcript is only legal when --compiler-backend=recorded")
    return DeterministicEvidenceAgentCompiler()


def _evidence_text(args: argparse.Namespace) -> str:
    if args.evidence_text is not None:
        return str(args.evidence_text)
    if args.evidence_file is None:
        raise ValueError("evidence_agent requires --evidence-text or --evidence-file")
    return Path(args.evidence_file).read_text(encoding="utf-8").strip()


def _pending_slice_backend(
    args: argparse.Namespace,
    *,
    live_backend_cls,
    recorded_backend_cls,
    deterministic_backend_cls,
):
    backend = str(args.compiler_backend).strip().lower()
    if backend == "live":
        if args.recorded_transcript is not None:
            raise ValueError("--recorded-transcript is only legal when --compiler-backend=recorded")
        return live_backend_cls.from_env()
    if backend == "recorded":
        if args.recorded_transcript is None:
            raise ValueError("--recorded-transcript is required when --compiler-backend=recorded")
        return recorded_backend_cls(transcript_path=args.recorded_transcript)
    if args.recorded_transcript is not None:
        raise ValueError("--recorded-transcript is only legal when --compiler-backend=recorded")
    return deterministic_backend_cls()


def _pending_text(args: argparse.Namespace, *, text_attr: str, file_attr: str, label: str) -> str:
    text_value = getattr(args, text_attr)
    if text_value is not None:
        return str(text_value)
    file_value = getattr(args, file_attr)
    if file_value is None:
        raise ValueError(f"{label} requires --{text_attr.replace('_', '-')} or --{file_attr.replace('_', '-')}")
    return Path(file_value).read_text(encoding="utf-8").strip()


def _market_observer_admission_blocked_reason(execution_result) -> str | None:
    if execution_result.status == "blocked":
        return execution_result.blocked_reason
    if execution_result.status == "quarantine":
        return execution_result.quarantine_reason or "market_observer_candidate_quarantined"
    return None


def _evidence_admission_blocked_reason(execution_result, blocked_reason: str | None) -> str | None:
    if blocked_reason is not None:
        return blocked_reason
    if execution_result is None:
        return "missing existing object context for evidence_agent"
    if execution_result.status == "blocked":
        return execution_result.blocked_reason
    if execution_result.status == "quarantine":
        return execution_result.quarantine_reason or "evidence_agent_candidate_quarantined"
    return None


def _market_observer_step_id(
    *,
    agent_id: str,
    object_id: str,
    subject: str,
    scope: str,
    spec_version: int,
    execution_result,
    observation: MarketObservationInput,
) -> str:
    payload = observation.to_spec_input_payload()
    if execution_result.candidate_draft is not None:
        payload = dict(execution_result.candidate_draft.to_agent_payload())
    idempotency_key = compute_idempotency_key(
        requested_delegate_id=agent_id,
        object_id=object_id,
        subject=subject,
        scope=scope,
        signal_payload=payload,
        spec_version=spec_version,
    )
    return f"{agent_id}:{spec_version}:{idempotency_key[:12]}"


def _evidence_agent_step_id(
    *,
    agent_id: str,
    object_id: str,
    subject: str,
    scope: str,
    spec_version: int,
    execution_result,
    observation: EvidenceObservationInput,
) -> str:
    payload = observation.to_spec_input_payload()
    if execution_result.candidate_draft is not None:
        payload = dict(execution_result.candidate_draft.to_agent_payload())
    idempotency_key = compute_idempotency_key(
        requested_delegate_id=agent_id,
        object_id=object_id,
        subject=subject,
        scope=scope,
        signal_payload=payload,
        spec_version=spec_version,
    )
    return f"{agent_id}:{spec_version}:{idempotency_key[:12]}"


def _pending_execution_step_id(
    *,
    agent_id: str,
    object_id: str,
    subject: str,
    scope: str,
    spec_version: int,
    execution_result,
    observation,
) -> str:
    payload = observation.to_spec_input_payload()
    if execution_result.candidate_draft is not None:
        payload = dict(execution_result.candidate_draft.to_agent_payload())
    idempotency_key = compute_idempotency_key(
        requested_delegate_id=agent_id,
        object_id=object_id,
        subject=subject,
        scope=scope,
        signal_payload=payload,
        spec_version=spec_version,
    )
    return f"{agent_id}:{spec_version}:{idempotency_key[:12]}"


def _market_observer_decision(result) -> str:
    if result.runtime_result is not None:
        return result.runtime_result.runtime_result.decision.decision
    if result.run_state == "BLOCKED":
        return "blocked"
    if result.replayed:
        return "replayed"
    return "blocked"


def _evidence_agent_decision(result) -> str:
    if result.runtime_result is not None:
        return result.runtime_result.runtime_result.decision.decision
    if result.run_state == "BLOCKED":
        return "blocked"
    if result.replayed:
        return "replayed"
    return "blocked"


def _build_ephemeral_context_runtime(
    *,
    object_id: str,
    subject: str,
    scope: str,
) -> RuntimeOrchestrator:
    runtime = RuntimeOrchestrator(
        store=InMemoryObjectStore(),
    )
    with runtime_worker_harness(slug=f"pending-ephemeral-{object_id}", scope=scope):
        runtime.run_new(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            scope=scope,
            signals=_build_seed_signals(
                object_id=object_id,
                subject=subject,
                scope=scope,
            ),
        )
    return runtime


def _run_evidence_agent(args: argparse.Namespace) -> dict[str, object]:
    agent_id = str(EVIDENCE_AGENT["agent_id"])
    artifacts_root = resolve_governed_demo_artifacts_root(artifacts_root=args.artifacts_root, agent_id=agent_id)
    owner_store = OwnerArtifactWriter(artifacts_root / "agent_owner")
    if args.require_external_permit and args.execution_permit is None:
        raise MissingExecutionPermitError(
            "governed-agent ingress demo requires --execution-permit when --require-external-permit is set"
        )
    if args.execution_permit is not None and not args.skip_seed:
        raise ValueError(
            "external execution permits are single-use; rerun evidence_agent with --skip-seed or omit --execution-permit"
        )
    if not args.skip_seed:
        with resolve_governed_demo_execution_permit(
            scope=args.scope,
            slug="governed-evidence-agent-seed-demo",
            artifacts_root=artifacts_root,
            execution_permit_path=None,
            require_external_permit=False,
        ) as (seed_permit, _seed_paths):
            seed_runtime = build_governed_demo_runtime(artifacts_root=artifacts_root, execution_permit=seed_permit)
            seed_runtime.run_new(
                object_id=args.object_id,
                object_type=ObjectType.ASSET,
                scope=args.scope,
                signals=_build_seed_signals(
                    object_id=args.object_id,
                    subject=args.subject,
                    scope=args.scope,
                ),
            )
    observation = EvidenceObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{agent_id}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        evidence_text=_evidence_text(args),
    )
    with resolve_governed_demo_execution_permit(
        scope=args.scope,
        slug="governed-evidence-agent-demo",
        artifacts_root=artifacts_root,
        execution_permit_path=args.execution_permit,
        require_external_permit=args.require_external_permit,
    ) as (permit, _paths):
        runtime = build_governed_demo_runtime(artifacts_root=artifacts_root, execution_permit=permit)
        orchestrator = GovernedAgentOrchestrator(runtime=runtime)
        seeded_session = None
        execution_result = None
        blocked_reason = None
        try:
            seeded_session = runtime.store.load(args.object_id)
            object_context = EvidenceObjectContextSummary.from_runtime_session(
                seeded_session,
                subject=args.subject,
                scope=args.scope,
            )
            execution = EvidenceAgentExecutionPipeline(
                artifact_store=owner_store,
                compiler_backend=_evidence_agent_backend(args),
            )
            execution_result = execution.execute(observation, object_context)
        except KeyError:
            blocked_reason = "missing existing object context for evidence_agent"
        except EvidenceObjectContextError as exc:
            blocked_reason = str(exc)
        result = orchestrator.run_governed_write(
            requested_delegate_id=agent_id,
            object_id=args.object_id,
            subject=args.subject,
            scope=args.scope,
            signal_draft=None if execution_result is None else execution_result.candidate_draft,
            artifacts_root=artifacts_root,
            execution_permit=permit,
            object_type=ObjectType.ASSET,
            user_intent="Continue one existing governed object with one bounded evidence signal.",
            constraints=("single_payload", "single_tool_call", "verify_before_finalize"),
            admission_blocked_reason=_evidence_admission_blocked_reason(execution_result, blocked_reason),
            spec_input_payload=observation.to_spec_input_payload(),
            admission_artifacts=()
            if execution_result is None
            else execution_result.compiler_artifact_paths(),
        )
        compiler_artifact_paths: tuple[str, ...] = ()
        if execution_result is not None:
            step_id = _evidence_agent_step_id(
                agent_id=agent_id,
                object_id=args.object_id,
                subject=args.subject,
                scope=args.scope,
                spec_version=result.spec_version,
                execution_result=execution_result,
                observation=observation,
            )
            compiler_artifact_paths = EvidenceAgentExecutionPipeline(artifact_store=owner_store).restamp_execution_artifacts(
                run_id=result.owner_run_id,
                step_id=step_id,
                spec_version=result.spec_version,
            )
        updated_session = None
        if runtime.store.exists(args.object_id):
            updated_session = runtime.store.load(args.object_id)
    return {
        "accepted_signal_ids": list(result.accepted_signal_ids),
        "agent_id": agent_id,
        "artifacts_root": str(artifacts_root),
        "blocked_reason": result.blocked_reason or (None if execution_result is None else execution_result.blocked_reason) or blocked_reason,
        "compiler_backend": None if execution_result is None else execution_result.backend_kind,
        "decision": _evidence_agent_decision(result),
        "execution_status": "blocked" if execution_result is None else execution_result.status,
        "compiler_artifact_paths": list(compiler_artifact_paths or (() if execution_result is None else execution_result.compiler_artifact_paths())),
        "final_claim_count": 0 if updated_session is None else len(updated_session.claims),
        "object_id": args.object_id,
        "owner_run_id": result.owner_run_id,
        "spec_version": result.spec_version,
        "run_state": result.run_state,
        "final_output_path": result.final_output_path,
        "verification_path": result.verification_path,
        "processing_state": None if updated_session is None else updated_session.research_object.processing_state.value,
        "quarantine_reason": None if execution_result is None else execution_result.quarantine_reason,
        "quarantine_paths": list(result.quarantine_paths),
        "replay_log_paths": list(result.replay_log_paths),
        "seeded_claim_count": 0 if seeded_session is None else len(seeded_session.claims),
        "session_path": None if updated_session is None else str(governed_demo_session_path(artifacts_root=artifacts_root, object_id=args.object_id)),
        "slice_mode": str(EVIDENCE_AGENT["slice_mode"]),
    }


def _run_risk_signal_agent(args: argparse.Namespace) -> dict[str, object]:
    observation = RiskSignalObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{RISK_SIGNAL_AGENT['agent_id']}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        risk_text=_pending_text(args, text_attr="risk_text", file_attr="risk_file", label="risk_signal_agent"),
    )
    return _run_pending_execution_agent(
        args=args,
        agent_definition=RISK_SIGNAL_AGENT,
        slug="governed-risk-signal-agent-demo",
        seed_slug="governed-risk-signal-agent-seed-demo",
        observation=observation,
        execution_pipeline_cls=RiskSignalExecutionPipeline,
        backend=_pending_slice_backend(
            args,
            live_backend_cls=OpenAICompatibleRiskSignalAgentBackend,
            recorded_backend_cls=RecordedTranscriptRiskSignalAgentBackend,
            deterministic_backend_cls=DeterministicRiskSignalAgentCompiler,
        ),
        context_builder=build_risk_signal_object_context,
        missing_context_reason="missing existing object context for risk_signal_agent",
    )


def _run_risk_governance_agent(args: argparse.Namespace) -> dict[str, object]:
    observation = RiskGovernanceObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{RISK_GOVERNANCE_AGENT['agent_id']}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        governance_text=_pending_text(
            args,
            text_attr="governance_text",
            file_attr="governance_file",
            label="risk_governance_agent",
        ),
    )
    return _run_pending_execution_agent(
        args=args,
        agent_definition=RISK_GOVERNANCE_AGENT,
        slug="governed-risk-governance-agent-demo",
        seed_slug="governed-risk-governance-agent-seed-demo",
        observation=observation,
        execution_pipeline_cls=RiskGovernanceExecutionPipeline,
        backend=_pending_slice_backend(
            args,
            live_backend_cls=OpenAICompatibleRiskGovernanceAgentBackend,
            recorded_backend_cls=RecordedTranscriptRiskGovernanceAgentBackend,
            deterministic_backend_cls=DeterministicRiskGovernanceAgentCompiler,
        ),
        context_builder=build_risk_governance_object_context,
        missing_context_reason="missing existing object context for risk_governance_agent",
    )


def _run_validation_agent(args: argparse.Namespace) -> dict[str, object]:
    observation = ValidationObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{VALIDATION_AGENT['agent_id']}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        validation_text=_pending_text(
            args,
            text_attr="validation_text",
            file_attr="validation_file",
            label="validation_agent",
        ),
    )
    return _run_pending_execution_agent(
        args=args,
        agent_definition=VALIDATION_AGENT,
        slug="governed-validation-agent-demo",
        seed_slug="governed-validation-agent-seed-demo",
        observation=observation,
        execution_pipeline_cls=ValidationExecutionPipeline,
        backend=_pending_slice_backend(
            args,
            live_backend_cls=OpenAICompatibleValidationAgentBackend,
            recorded_backend_cls=RecordedTranscriptValidationAgentBackend,
            deterministic_backend_cls=DeterministicValidationAgentCompiler,
        ),
        context_builder=build_validation_object_context,
        missing_context_reason="missing existing object context for validation_agent",
    )


def _run_attention_allocator(args: argparse.Namespace) -> dict[str, object]:
    observation = AttentionAllocatorObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{ATTENTION_ALLOCATOR_AGENT['agent_id']}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        attention_text=_pending_text(
            args,
            text_attr="attention_text",
            file_attr="attention_file",
            label="attention_allocator",
        ),
    )
    return _run_pending_execution_agent(
        args=args,
        agent_definition=ATTENTION_ALLOCATOR_AGENT,
        slug="governed-attention-allocator-demo",
        seed_slug="governed-attention-allocator-seed-demo",
        observation=observation,
        execution_pipeline_cls=AttentionAllocatorExecutionPipeline,
        backend=_pending_slice_backend(
            args,
            live_backend_cls=OpenAICompatibleAttentionAllocatorBackend,
            recorded_backend_cls=RecordedTranscriptAttentionAllocatorBackend,
            deterministic_backend_cls=DeterministicAttentionAllocatorCompiler,
        ),
        context_builder=build_attention_allocator_object_context,
        missing_context_reason="missing existing object context for attention_allocator",
    )


def _run_research_synthesizer(args: argparse.Namespace) -> dict[str, object]:
    observation = ResearchSynthesisObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{RESEARCH_SYNTHESIZER_AGENT['agent_id']}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        synthesis_text=_pending_text(
            args,
            text_attr="synthesis_text",
            file_attr="synthesis_file",
            label="research_synthesizer",
        ),
    )
    return _run_pending_execution_agent(
        args=args,
        agent_definition=RESEARCH_SYNTHESIZER_AGENT,
        slug="governed-research-synthesizer-demo",
        seed_slug="governed-research-synthesizer-seed-demo",
        observation=observation,
        execution_pipeline_cls=ResearchSynthesisExecutionPipeline,
        backend=_pending_slice_backend(
            args,
            live_backend_cls=OpenAICompatibleResearchSynthesizerBackend,
            recorded_backend_cls=RecordedTranscriptResearchSynthesizerBackend,
            deterministic_backend_cls=DeterministicResearchSynthesizerCompiler,
        ),
        context_builder=build_research_synthesizer_object_context,
        missing_context_reason="missing existing object context for research_synthesizer",
    )


def _run_research_lead(args: argparse.Namespace) -> dict[str, object]:
    observation = ResearchLeadObservationInput(
        input_id=str(args.input_id).strip() if args.input_id is not None else f"{RESEARCH_LEAD_AGENT['agent_id']}:{args.object_id}:1",
        object_id=args.object_id,
        subject=args.subject,
        scope=args.scope,
        directive_text=_pending_text(
            args,
            text_attr="directive_text",
            file_attr="directive_file",
            label="research_lead",
        ),
    )
    return _run_pending_execution_agent(
        args=args,
        agent_definition=RESEARCH_LEAD_AGENT,
        slug="governed-research-lead-demo",
        seed_slug="governed-research-lead-seed-demo",
        observation=observation,
        execution_pipeline_cls=ResearchLeadExecutionPipeline,
        backend=_pending_slice_backend(
            args,
            live_backend_cls=OpenAICompatibleResearchLeadBackend,
            recorded_backend_cls=RecordedTranscriptResearchLeadBackend,
            deterministic_backend_cls=DeterministicResearchLeadCompiler,
        ),
        context_builder=build_research_lead_object_context,
        missing_context_reason="missing existing object context for research_lead",
    )


def _run_pending_execution_agent(
    *,
    args: argparse.Namespace,
    agent_definition: dict[str, object],
    slug: str,
    seed_slug: str,
    observation,
    execution_pipeline_cls,
    backend,
    context_builder: Callable[..., Any],
    missing_context_reason: str,
) -> dict[str, object]:
    agent_id = str(agent_definition["agent_id"])
    artifacts_root = resolve_governed_demo_artifacts_root(artifacts_root=args.artifacts_root, agent_id=agent_id)
    owner_store = OwnerArtifactWriter(artifacts_root / "agent_owner")
    governance = evaluate_agent_layer_governance()
    governance_blocked_reason = _pending_governance_block_reason(agent_definition=agent_definition, governance=governance)
    if governance_blocked_reason is None and args.require_external_permit and args.execution_permit is None:
        raise MissingExecutionPermitError(
            "governed-agent ingress demo requires --execution-permit when --require-external-permit is set"
        )
    if governance_blocked_reason is None and args.execution_permit is not None and not args.skip_seed:
        raise ValueError(
            f"external execution permits are single-use; rerun {agent_id} with --skip-seed or omit --execution-permit"
        )
    if governance_blocked_reason is None and not args.skip_seed:
        with resolve_governed_demo_execution_permit(
            scope=args.scope,
            slug=seed_slug,
            artifacts_root=artifacts_root,
            execution_permit_path=None,
            require_external_permit=False,
        ) as (seed_permit, _seed_paths):
            seed_runtime = build_governed_demo_runtime(artifacts_root=artifacts_root, execution_permit=seed_permit)
            seed_runtime.run_new(
                object_id=args.object_id,
                object_type=ObjectType.ASSET,
                scope=args.scope,
                signals=_build_seed_signals(
                    object_id=args.object_id,
                    subject=args.subject,
                    scope=args.scope,
                ),
            )
    with resolve_governed_demo_execution_permit(
        scope=args.scope,
        slug=slug,
        artifacts_root=artifacts_root,
        execution_permit_path=args.execution_permit,
        require_external_permit=args.require_external_permit and governance_blocked_reason is None,
    ) as (permit, _paths):
        runtime = build_governed_demo_runtime(artifacts_root=artifacts_root, execution_permit=permit)
        orchestrator = GovernedAgentOrchestrator(runtime=runtime)
        seeded_session = None
        if runtime.store.exists(args.object_id):
            seeded_session = runtime.store.load(args.object_id)
        execution_result = None
        compile_blocked_reason: str | None = None
        compile_runtime: RuntimeOrchestrator | None = None
        if governance_blocked_reason is None:
            compile_runtime = runtime
        elif not args.skip_seed:
            compile_runtime = _build_ephemeral_context_runtime(
                object_id=args.object_id,
                subject=args.subject,
                scope=args.scope,
            )
            seeded_session = compile_runtime.store.load(args.object_id)
        elif runtime.store.exists(args.object_id):
            compile_runtime = runtime
            seeded_session = runtime.store.load(args.object_id)
        else:
            compile_blocked_reason = missing_context_reason

        if compile_runtime is not None:
            try:
                object_context = context_builder(
                    runtime=compile_runtime,
                    object_id=args.object_id,
                    subject=args.subject,
                    scope=args.scope,
                )
            except KeyError:
                compile_blocked_reason = missing_context_reason
            except RuntimeError as exc:
                compile_blocked_reason = str(exc)
            else:
                execution = execution_pipeline_cls(
                    artifact_store=owner_store,
                    compiler_backend=backend,
                )
                execution_result = execution.execute(observation, object_context)

        if execution_result is None:
            admission_blocked_reason = compile_blocked_reason or governance_blocked_reason or missing_context_reason
        elif execution_result.status == "success":
            admission_blocked_reason = governance_blocked_reason
        elif execution_result.status == "blocked":
            admission_blocked_reason = execution_result.blocked_reason
        else:
            admission_blocked_reason = execution_result.quarantine_reason

        delegate_draft = None
        if execution_result is not None and execution_result.status == "success" and governance_blocked_reason is None:
            delegate_draft = execution_result.candidate_draft

        result = orchestrator.run_governed_write(
            requested_delegate_id=agent_id,
            object_id=args.object_id,
            subject=args.subject,
            scope=args.scope,
            signal_draft=delegate_draft,
            artifacts_root=artifacts_root,
            execution_permit=permit,
            object_type=ObjectType.ASSET,
            user_intent=f"Continue one existing governed object with one bounded raw-input slice '{agent_id}'.",
            constraints=("single_payload", "single_tool_call", "verify_before_finalize"),
            admission_blocked_reason=admission_blocked_reason,
            spec_input_payload=observation.to_spec_input_payload(),
            admission_artifacts=()
            if execution_result is None
            else execution_result.compiler_artifact_paths(),
        )
        compiler_artifact_paths: tuple[str, ...] = ()
        if execution_result is not None:
            step_id = _pending_execution_step_id(
                agent_id=agent_id,
                object_id=args.object_id,
                subject=args.subject,
                scope=args.scope,
                spec_version=result.spec_version,
                execution_result=execution_result,
                observation=observation,
            )
            compiler_artifact_paths = execution_pipeline_cls(artifact_store=owner_store).restamp_execution_artifacts(
                run_id=result.owner_run_id,
                step_id=step_id,
                spec_version=result.spec_version,
            )
        updated_session = None
        if runtime.store.exists(args.object_id):
            updated_session = runtime.store.load(args.object_id)
    return {
        "accepted_signal_ids": list(result.accepted_signal_ids),
        "agent_id": agent_id,
        "artifacts_root": str(artifacts_root),
        "blocked_reason": result.blocked_reason or (None if execution_result is None else execution_result.blocked_reason) or compile_blocked_reason,
        "compiler_backend": None if execution_result is None else execution_result.backend_kind,
        "decision": _evidence_agent_decision(result),
        "execution_status": "blocked" if execution_result is None else execution_result.status,
        "compiler_artifact_paths": list(compiler_artifact_paths or (() if execution_result is None else execution_result.compiler_artifact_paths())),
        "final_claim_count": 0 if updated_session is None else len(updated_session.claims),
        "object_id": args.object_id,
        "owner_run_id": result.owner_run_id,
        "spec_version": result.spec_version,
        "run_state": result.run_state,
        "final_output_path": result.final_output_path,
        "verification_path": result.verification_path,
        "processing_state": None if updated_session is None else updated_session.research_object.processing_state.value,
        "quarantine_reason": None if execution_result is None else execution_result.quarantine_reason,
        "quarantine_paths": list(result.quarantine_paths),
        "replay_log_paths": list(result.replay_log_paths),
        "seeded_claim_count": 0 if seeded_session is None else len(seeded_session.claims),
        "session_path": None if updated_session is None else str(governed_demo_session_path(artifacts_root=artifacts_root, object_id=args.object_id)),
        "slice_mode": str(agent_definition["slice_mode"]),
    }


def _pending_governance_block_reason(
    *,
    agent_definition: dict[str, object],
    governance: dict[str, object],
) -> str | None:
    if bool(agent_definition.get("enabled_under_current_governance")):
        return None
    agent_id = str(agent_definition["agent_id"])
    pending_ids = list(governance.get("registered_pending_promotion_controlled_slice_ids") or [])
    if agent_id in pending_ids:
        return (
            f"agent '{agent_id}' is admission-ready but still pending promotion; it remains outside "
            "current_controlled_slice_ids and is not operator-enabled"
        )
    return f"agent '{agent_id}' is not enabled under current governance"


def _error_payload(exc: Exception) -> dict[str, object]:
    payload: dict[str, object] = {
        "error": str(exc),
        "error_type": type(exc).__name__,
    }
    if isinstance(exc, AgentIngressValidationError):
        payload["quarantine_paths"] = [record.path for record in exc.quarantine_records]
        payload["replay_log_paths"] = [record.path for record in exc.replay_records]
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 2
    try:
        payload = args.func(args)
    except Exception as exc:  # noqa: BLE001 - public demo should emit the exact failure class
        print(json.dumps(_error_payload(exc), indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
