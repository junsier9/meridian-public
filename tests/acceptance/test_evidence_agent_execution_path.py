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
    EvidenceAgentExecutionPipeline,
    EvidenceObjectContextSummary,
    EvidenceObservationInput,
    RecordedTranscriptEvidenceAgentBackend,
)
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


FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "evidence_agent"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))


def _transcript(name: str) -> Path:
    return FIXTURE_ROOT / name / "model_transcript.json"


class EvidenceAgentExecutionAcceptanceTests(unittest.TestCase):
    def test_success_fixture_runs_end_to_end_from_recorded_transcript(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, str(fixture["object_id"]))
            before_claims = len(runtime.store.load(str(fixture["object_id"])).claims)
            observation = _observation_from_fixture(fixture)
            object_context = EvidenceObjectContextSummary.from_runtime_session(
                runtime.store.load(observation.object_id),
                subject=observation.subject,
                scope=observation.scope,
            )
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_transcript("success")),
            )
            execution = pipeline.execute(observation, object_context)

            with runtime_worker_harness(slug="evidence-agent-execution-success", scope=observation.scope):
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Continue one existing governed object from one recorded evidence_agent transcript.",
                    constraints=("single_payload", "single_tool_call", "verify_before_finalize"),
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=execution.compiler_artifact_paths(),
                )

            _restamp_execution(store, observation, execution, result)
            session = runtime.store.load(observation.object_id)
            self.assertEqual(execution.status, "success")
            self.assertEqual(execution.backend_kind, "recorded")
            self.assertEqual(result.run_state, "FINALIZED")
            self.assertEqual(len(session.claims), before_claims + 1)

    def test_blocked_fixture_generates_owner_blocked_without_runtime_mutation(self) -> None:
        fixture = _load_fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, str(fixture["object_id"]))
            before_claims = len(runtime.store.load(str(fixture["object_id"])).claims)
            observation = _observation_from_fixture(fixture)
            object_context = EvidenceObjectContextSummary.from_runtime_session(
                runtime.store.load(observation.object_id),
                subject=observation.subject,
                scope=observation.scope,
            )
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_transcript("blocked")),
            )
            execution = pipeline.execute(observation, object_context)
            result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                requested_delegate_id="evidence_agent",
                object_id=observation.object_id,
                subject=observation.subject,
                scope=observation.scope,
                signal_draft=None,
                artifacts_root=tmpdir,
                object_type=ObjectType.ASSET,
                user_intent="Block evidence_agent before runtime write when the recorded transcript blocks.",
                admission_blocked_reason=execution.blocked_reason,
                spec_input_payload=observation.to_spec_input_payload(),
                admission_artifacts=execution.compiler_artifact_paths(),
            )

            _restamp_execution(store, observation, execution, result)
            self.assertEqual(execution.status, "blocked")
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertEqual(len(runtime.store.load(observation.object_id).claims), before_claims)

    def test_quarantine_fixture_generates_owner_blocked_and_preserves_quarantine_artifact(self) -> None:
        fixture = _load_fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, str(fixture["object_id"]))
            before_claims = len(runtime.store.load(str(fixture["object_id"])).claims)
            observation = _observation_from_fixture(fixture)
            object_context = EvidenceObjectContextSummary.from_runtime_session(
                runtime.store.load(observation.object_id),
                subject=observation.subject,
                scope=observation.scope,
            )
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_transcript("quarantine")),
            )
            execution = pipeline.execute(observation, object_context)
            result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                requested_delegate_id="evidence_agent",
                object_id=observation.object_id,
                subject=observation.subject,
                scope=observation.scope,
                signal_draft=None,
                artifacts_root=tmpdir,
                object_type=ObjectType.ASSET,
                user_intent="Quarantine evidence_agent candidates that conflict with the host context.",
                admission_blocked_reason=execution.quarantine_reason,
                spec_input_payload=observation.to_spec_input_payload(),
                admission_artifacts=execution.compiler_artifact_paths(),
            )

            artifact_paths = _restamp_execution(store, observation, execution, result)
            self.assertEqual(execution.status, "quarantine")
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertTrue(any(path.endswith("quarantine.json") for path in artifact_paths))
            self.assertEqual(len(runtime.store.load(observation.object_id).claims), before_claims)

    def test_retry_reuses_recorded_artifacts_and_does_not_duplicate_runtime_write(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, str(fixture["object_id"]))
            observation = _observation_from_fixture(fixture)
            object_context = EvidenceObjectContextSummary.from_runtime_session(
                runtime.store.load(observation.object_id),
                subject=observation.subject,
                scope=observation.scope,
            )
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_transcript("success")),
            )
            first_execution = pipeline.execute(observation, object_context)

            with runtime_worker_harness(slug="evidence-agent-execution-retry", scope=observation.scope):
                orchestrator = GovernedAgentOrchestrator(runtime=runtime)
                first = orchestrator.run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=first_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Retry-safe recorded evidence_agent execution.",
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=first_execution.compiler_artifact_paths(),
                )
                _restamp_execution(store, observation, first_execution, first)
                claim_count = len(runtime.store.load(observation.object_id).claims)

                second_execution = pipeline.execute(observation, object_context)
                second = orchestrator.run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=second_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Retry-safe recorded evidence_agent execution.",
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=second_execution.compiler_artifact_paths(),
                )

            self.assertTrue(second_execution.reused)
            self.assertTrue(second.replayed)
            self.assertEqual(len(runtime.store.load(observation.object_id).claims), claim_count)

    def test_recorded_compiler_success_can_be_recovered_from_owner_artifacts_before_finalize(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            _seed_object(runtime, str(fixture["object_id"]))
            observation = _observation_from_fixture(fixture)
            object_context = EvidenceObjectContextSummary.from_runtime_session(
                runtime.store.load(observation.object_id),
                subject=observation.subject,
                scope=observation.scope,
            )
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            first_pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_transcript("success")),
            )
            first_execution = first_pipeline.execute(observation, object_context)
            self.assertEqual(first_execution.status, "success")

            second_pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_transcript("success")),
            )
            recovered_execution = second_pipeline.execute(observation, object_context)
            self.assertTrue(recovered_execution.reused)

            with runtime_worker_harness(slug="evidence-agent-compiler-recovery", scope=observation.scope):
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="evidence_agent",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=recovered_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Recover from recorded compiler artifacts after an interrupted evidence run.",
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=recovered_execution.compiler_artifact_paths(),
                )

            _restamp_execution(store, observation, recovered_execution, result)
            self.assertEqual(result.run_state, "FINALIZED")


def _build_runtime(tmpdir: str) -> RuntimeOrchestrator:
    return RuntimeOrchestrator(
        store=FileObjectStore(Path(tmpdir) / "runtime_sessions"),
        agent_ingress_firewall=AgentIngressFirewall(
            quarantine_buffer=QuarantineBuffer(Path(tmpdir) / "quarantine"),
            replayable_input_log=ReplayableInputLog(Path(tmpdir) / "replay_log"),
        ),
    )


def _seed_object(runtime: RuntimeOrchestrator, object_id: str) -> None:
    with runtime_worker_harness(slug=f"seed-{object_id}", scope="spot+perp"):
        runtime.run_new(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=[
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
            ],
        )


def _observation_from_fixture(fixture: dict[str, object]) -> EvidenceObservationInput:
    return EvidenceObservationInput(
        input_id=f"{fixture['case_id']}:1",
        object_id=str(fixture["object_id"]),
        subject=str(fixture["subject"]),
        scope=str(fixture["scope"]),
        evidence_text=str(fixture["evidence_text"]),
    )


def _restamp_execution(
    store: OwnerArtifactWriter,
    observation: EvidenceObservationInput,
    execution,
    result,
) -> tuple[str, ...]:
    payload = observation.to_spec_input_payload()
    if execution.candidate_draft is not None:
        payload = dict(execution.candidate_draft.to_agent_payload())
    idempotency_key = compute_idempotency_key(
        requested_delegate_id="evidence_agent",
        object_id=observation.object_id,
        subject=observation.subject,
        scope=observation.scope,
        signal_payload=payload,
        spec_version=result.spec_version,
    )
    step_id = f"evidence_agent:{result.spec_version}:{idempotency_key[:12]}"
    return EvidenceAgentExecutionPipeline(artifact_store=store).restamp_execution_artifacts(
        run_id=result.owner_run_id,
        step_id=step_id,
        spec_version=result.spec_version,
    )


if __name__ == "__main__":
    unittest.main()
