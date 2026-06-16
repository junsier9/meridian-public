from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT, SRC

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.execution import (
    AttentionAllocatorExecutionPipeline,
    RecordedTranscriptAttentionAllocatorBackend,
    RecordedTranscriptResearchLeadBackend,
    RecordedTranscriptResearchSynthesizerBackend,
    RecordedTranscriptRiskGovernanceAgentBackend,
    RecordedTranscriptRiskSignalAgentBackend,
    RecordedTranscriptValidationAgentBackend,
    ResearchLeadExecutionPipeline,
    ResearchSynthesisExecutionPipeline,
    RiskGovernanceExecutionPipeline,
    RiskSignalExecutionPipeline,
    ValidationExecutionPipeline,
)
from enhengclaw.agents.execution.attention_allocator import (
    AttentionAllocatorObservationInput,
    build_attention_allocator_object_context,
)
from enhengclaw.agents.execution.research_lead import ResearchLeadObservationInput, build_research_lead_object_context
from enhengclaw.agents.execution.research_synthesizer import (
    ResearchSynthesisObservationInput,
    build_research_synthesizer_object_context,
)
from enhengclaw.agents.execution.risk_governance_agent import (
    RiskGovernanceObservationInput,
    build_risk_governance_object_context,
)
from enhengclaw.agents.execution.risk_signal_agent import RiskSignalObservationInput, build_risk_signal_object_context
from enhengclaw.agents.execution.validation_agent import ValidationObservationInput, build_validation_object_context
from enhengclaw.agents.owner_state import OwnerArtifactWriter, compute_idempotency_key
from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.session import FileObjectStore
from enhengclaw.core.signals import Signal
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.runtime import GovernedAgentOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness


def _seed_signals(object_id: str):
    return [
        Signal(
            signal_id=f"{object_id}:seed:1",
            object_type=ObjectType.ASSET,
            subject="AIX",
            predicate="spot_breakout",
            value="AIX spot structure remains constructive",
            claim_type=ClaimType.MEASUREMENT,
            direction=Direction.BULLISH,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=82,
            scope="spot+perp",
            time_horizon=TimeHorizon.INTRADAY,
        ),
        Signal(
            signal_id=f"{object_id}:seed:2",
            object_type=ObjectType.ASSET,
            subject="AIX",
            predicate="wallet_buy",
            value="AIX still shows supportive flow from large buyers",
            claim_type=ClaimType.FLOW,
            direction=Direction.BULLISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E4,
            confidence_hint=78,
            scope="spot+perp",
            time_horizon=TimeHorizon.INTRADAY,
        ),
    ]


class PendingSliceExecutionAcceptanceMixin:
    fixture_root: Path
    agent_id: str
    pipeline_cls: type
    recorded_backend_cls: type
    observation_cls: type
    context_builder: staticmethod
    text_key: str

    def _fixture(self, name: str) -> dict[str, object]:
        return json.loads((self.fixture_root / name / "input.json").read_text(encoding="utf-8"))

    def _transcript(self, name: str) -> Path:
        return self.fixture_root / name / "model_transcript.json"

    def _observation(self, fixture: dict[str, object]):
        return self.observation_cls(
            input_id=f"{fixture['case_id']}:1",
            object_id=str(fixture["object_id"]),
            subject=str(fixture["subject"]),
            scope=str(fixture["scope"]),
            **{self.text_key: str(fixture[self.text_key])},
        )

    def test_success_fixture_runs_end_to_end_from_recorded_transcript(self) -> None:
        fixture = self._fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = self._observation(fixture)
            with runtime_worker_harness(slug=f"{self.agent_id}-execution-success", scope=observation.scope):
                runtime.run_new(
                    object_id=observation.object_id,
                    object_type=ObjectType.ASSET,
                    scope=observation.scope,
                    signals=_seed_signals(observation.object_id),
                )
                seeded_claim_count = len(runtime.store.load(observation.object_id).claims)
                store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
                pipeline = self.pipeline_cls(
                    artifact_store=store,
                    compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("success")),
                )
                object_context = self.context_builder(
                    runtime=runtime,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                )
                execution = pipeline.execute(observation, object_context)
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id=self.agent_id,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent=f"Execute one recorded {self.agent_id} transcript against one existing object.",
                    constraints=("single_payload", "single_tool_call", "verify_before_finalize"),
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=execution.compiler_artifact_paths(),
                )

            _restamp_execution(self.agent_id, self.pipeline_cls, store, observation, execution, result)
            session = runtime.store.load(observation.object_id)
            self.assertEqual(execution.status, "success")
            self.assertEqual(execution.backend_kind, "recorded")
            self.assertEqual(result.run_state, "FINALIZED")
            self.assertEqual(len(result.accepted_signal_ids), 1)
            self.assertEqual(len(session.claims), seeded_claim_count + 1)

    def test_blocked_fixture_generates_owner_blocked_without_runtime_mutation(self) -> None:
        fixture = self._fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = self._observation(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = self.pipeline_cls(
                artifact_store=store,
                compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("blocked")),
            )
            with runtime_worker_harness(slug=f"{self.agent_id}-execution-blocked", scope=observation.scope):
                runtime.run_new(
                    object_id=observation.object_id,
                    object_type=ObjectType.ASSET,
                    scope=observation.scope,
                    signals=_seed_signals(observation.object_id),
                )
                object_context = self.context_builder(
                    runtime=runtime,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                )
                execution = pipeline.execute(observation, object_context)
                claim_count = len(runtime.store.load(observation.object_id).claims)
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id=self.agent_id,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=None,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent=f"Block {self.agent_id} before runtime write when the recorded transcript blocks.",
                    admission_blocked_reason=execution.blocked_reason,
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=execution.compiler_artifact_paths(),
                )

            _restamp_execution(self.agent_id, self.pipeline_cls, store, observation, execution, result)
            self.assertEqual(execution.status, "blocked")
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertEqual(len(runtime.store.load(observation.object_id).claims), claim_count)

    def test_quarantine_fixture_generates_owner_blocked_and_preserves_quarantine_artifact(self) -> None:
        fixture = self._fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = self._observation(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = self.pipeline_cls(
                artifact_store=store,
                compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("quarantine")),
            )
            with runtime_worker_harness(slug=f"{self.agent_id}-execution-quarantine", scope=observation.scope):
                runtime.run_new(
                    object_id=observation.object_id,
                    object_type=ObjectType.ASSET,
                    scope=observation.scope,
                    signals=_seed_signals(observation.object_id),
                )
                object_context = self.context_builder(
                    runtime=runtime,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                )
                execution = pipeline.execute(observation, object_context)
                claim_count = len(runtime.store.load(observation.object_id).claims)
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id=self.agent_id,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=None,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent=f"Quarantine {self.agent_id} candidates that conflict with host context.",
                    admission_blocked_reason=execution.quarantine_reason,
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=execution.compiler_artifact_paths(),
                )

            artifact_paths = _restamp_execution(self.agent_id, self.pipeline_cls, store, observation, execution, result)
            self.assertEqual(execution.status, "quarantine")
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertTrue(any(path.endswith("quarantine.json") for path in artifact_paths))
            self.assertEqual(len(runtime.store.load(observation.object_id).claims), claim_count)

    def test_retry_reuses_recorded_artifacts_and_does_not_duplicate_runtime_write(self) -> None:
        fixture = self._fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = self._observation(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            with runtime_worker_harness(slug=f"{self.agent_id}-execution-retry", scope=observation.scope):
                runtime.run_new(
                    object_id=observation.object_id,
                    object_type=ObjectType.ASSET,
                    scope=observation.scope,
                    signals=_seed_signals(observation.object_id),
                )
                pipeline = self.pipeline_cls(
                    artifact_store=store,
                    compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("success")),
                )
                object_context = self.context_builder(
                    runtime=runtime,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                )
                first_execution = pipeline.execute(observation, object_context)
                orchestrator = GovernedAgentOrchestrator(runtime=runtime)
                first = orchestrator.run_governed_write(
                    requested_delegate_id=self.agent_id,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=first_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent=f"Retry-safe recorded {self.agent_id} execution.",
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=first_execution.compiler_artifact_paths(),
                )
                _restamp_execution(self.agent_id, self.pipeline_cls, store, observation, first_execution, first)
                claim_count = len(runtime.store.load(observation.object_id).claims)

                second_execution = pipeline.execute(observation, object_context)
                second = orchestrator.run_governed_write(
                    requested_delegate_id=self.agent_id,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=second_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent=f"Retry-safe recorded {self.agent_id} execution.",
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=second_execution.compiler_artifact_paths(),
                )

            self.assertTrue(second_execution.reused)
            self.assertTrue(second.replayed)
            self.assertEqual(len(runtime.store.load(observation.object_id).claims), claim_count)

    def test_recorded_compiler_success_can_be_recovered_from_owner_artifacts_before_finalize(self) -> None:
        fixture = self._fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = self._observation(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            with runtime_worker_harness(slug=f"{self.agent_id}-execution-recovery", scope=observation.scope):
                runtime.run_new(
                    object_id=observation.object_id,
                    object_type=ObjectType.ASSET,
                    scope=observation.scope,
                    signals=_seed_signals(observation.object_id),
                )
                object_context = self.context_builder(
                    runtime=runtime,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                )
                first_pipeline = self.pipeline_cls(
                    artifact_store=store,
                    compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("success")),
                )
                first_execution = first_pipeline.execute(observation, object_context)
                self.assertEqual(first_execution.status, "success")

                second_pipeline = self.pipeline_cls(
                    artifact_store=store,
                    compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("success")),
                )
                recovered_execution = second_pipeline.execute(observation, object_context)
                self.assertTrue(recovered_execution.reused)
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id=self.agent_id,
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=recovered_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent=f"Recover recorded {self.agent_id} compiler artifacts after interruption.",
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=recovered_execution.compiler_artifact_paths(),
                )

            _restamp_execution(self.agent_id, self.pipeline_cls, store, observation, recovered_execution, result)
            self.assertEqual(result.run_state, "FINALIZED")


class RiskSignalExecutionPathTests(PendingSliceExecutionAcceptanceMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "risk_signal_agent"
    agent_id = "risk_signal_agent"
    pipeline_cls = RiskSignalExecutionPipeline
    recorded_backend_cls = RecordedTranscriptRiskSignalAgentBackend
    observation_cls = RiskSignalObservationInput
    context_builder = staticmethod(build_risk_signal_object_context)
    text_key = "risk_text"


class RiskGovernanceExecutionPathTests(PendingSliceExecutionAcceptanceMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "risk_governance_agent"
    agent_id = "risk_governance_agent"
    pipeline_cls = RiskGovernanceExecutionPipeline
    recorded_backend_cls = RecordedTranscriptRiskGovernanceAgentBackend
    observation_cls = RiskGovernanceObservationInput
    context_builder = staticmethod(build_risk_governance_object_context)
    text_key = "governance_text"


class ValidationExecutionPathTests(PendingSliceExecutionAcceptanceMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "validation_agent"
    agent_id = "validation_agent"
    pipeline_cls = ValidationExecutionPipeline
    recorded_backend_cls = RecordedTranscriptValidationAgentBackend
    observation_cls = ValidationObservationInput
    context_builder = staticmethod(build_validation_object_context)
    text_key = "validation_text"


class AttentionAllocatorExecutionPathTests(PendingSliceExecutionAcceptanceMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "attention_allocator"
    agent_id = "attention_allocator"
    pipeline_cls = AttentionAllocatorExecutionPipeline
    recorded_backend_cls = RecordedTranscriptAttentionAllocatorBackend
    observation_cls = AttentionAllocatorObservationInput
    context_builder = staticmethod(build_attention_allocator_object_context)
    text_key = "attention_text"


class ResearchSynthesizerExecutionPathTests(PendingSliceExecutionAcceptanceMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "research_synthesizer"
    agent_id = "research_synthesizer"
    pipeline_cls = ResearchSynthesisExecutionPipeline
    recorded_backend_cls = RecordedTranscriptResearchSynthesizerBackend
    observation_cls = ResearchSynthesisObservationInput
    context_builder = staticmethod(build_research_synthesizer_object_context)
    text_key = "synthesis_text"


class ResearchLeadExecutionPathTests(PendingSliceExecutionAcceptanceMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "research_lead"
    agent_id = "research_lead"
    pipeline_cls = ResearchLeadExecutionPipeline
    recorded_backend_cls = RecordedTranscriptResearchLeadBackend
    observation_cls = ResearchLeadObservationInput
    context_builder = staticmethod(build_research_lead_object_context)
    text_key = "directive_text"


def _build_runtime(tmpdir: str) -> RuntimeOrchestrator:
    return RuntimeOrchestrator(
        store=FileObjectStore(Path(tmpdir) / "runtime_sessions"),
        agent_ingress_firewall=AgentIngressFirewall(
            quarantine_buffer=QuarantineBuffer(Path(tmpdir) / "quarantine"),
            replayable_input_log=ReplayableInputLog(Path(tmpdir) / "replay_log"),
        ),
    )


def _restamp_execution(agent_id: str, pipeline_cls, store: OwnerArtifactWriter, observation, execution, result) -> tuple[str, ...]:
    payload = observation.to_spec_input_payload()
    if execution.candidate_draft is not None:
        payload = dict(execution.candidate_draft.to_agent_payload())
    idempotency_key = compute_idempotency_key(
        requested_delegate_id=agent_id,
        object_id=observation.object_id,
        subject=observation.subject,
        scope=observation.scope,
        signal_payload=payload,
        spec_version=result.spec_version,
    )
    step_id = f"{agent_id}:{result.spec_version}:{idempotency_key[:12]}"
    return pipeline_cls(artifact_store=store).restamp_execution_artifacts(
        run_id=result.owner_run_id,
        step_id=step_id,
        spec_version=result.spec_version,
    )


if __name__ == "__main__":
    unittest.main()
