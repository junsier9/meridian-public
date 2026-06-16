from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.test_helpers import ROOT, SRC

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.execution import MarketObservationInput, MarketObserverExecutionPipeline, RecordedTranscriptMarketObserverBackend
from enhengclaw.agents.owner_state import OwnerArtifactWriter, compute_idempotency_key
from enhengclaw.core.enums import ObjectType
from enhengclaw.core.session import FileObjectStore
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.runtime import GovernedAgentOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness


FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "market_observer"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))


def _transcript(name: str) -> Path:
    return FIXTURE_ROOT / name / "model_transcript.json"


class MarketObserverExecutionAcceptanceTests(unittest.TestCase):
    def test_success_fixture_runs_end_to_end_from_recorded_transcript(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = _observation_from_fixture(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_transcript("success")),
            )
            execution = pipeline.execute(observation)

            with runtime_worker_harness(slug="market-observer-execution-success", scope=observation.scope):
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="market_observer",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Create one governed runtime object from one recorded market_observer transcript.",
                    constraints=("single_payload", "single_tool_call", "verify_before_finalize"),
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=execution.compiler_artifact_paths(),
                )

            _restamp_execution(store, observation, execution, result)
            session = runtime.store.load(observation.object_id)
            self.assertEqual(execution.status, "success")
            self.assertEqual(execution.backend_kind, "recorded")
            self.assertEqual(result.run_state, "FINALIZED")
            self.assertGreaterEqual(len(session.claims), 1)

    def test_blocked_fixture_generates_owner_blocked_without_runtime_mutation(self) -> None:
        fixture = _load_fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = _observation_from_fixture(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_transcript("blocked")),
            )
            execution = pipeline.execute(observation)
            result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                requested_delegate_id="market_observer",
                object_id=observation.object_id,
                subject=observation.subject,
                scope=observation.scope,
                signal_draft=None,
                artifacts_root=tmpdir,
                object_type=ObjectType.ASSET,
                user_intent="Block market_observer before runtime write when the recorded transcript blocks.",
                admission_blocked_reason=execution.blocked_reason,
                spec_input_payload=observation.to_spec_input_payload(),
                admission_artifacts=execution.compiler_artifact_paths(),
            )

            _restamp_execution(store, observation, execution, result)
            self.assertEqual(execution.status, "blocked")
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertFalse((Path(tmpdir) / "runtime_sessions" / f"{observation.object_id}.json").exists())

    def test_quarantine_fixture_generates_owner_blocked_and_preserves_quarantine_artifact(self) -> None:
        fixture = _load_fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = _observation_from_fixture(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_transcript("quarantine")),
            )
            execution = pipeline.execute(observation)
            result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                requested_delegate_id="market_observer",
                object_id=observation.object_id,
                subject=observation.subject,
                scope=observation.scope,
                signal_draft=None,
                artifacts_root=tmpdir,
                object_type=ObjectType.ASSET,
                user_intent="Quarantine market_observer candidates that conflict with the host context.",
                admission_blocked_reason=execution.quarantine_reason,
                spec_input_payload=observation.to_spec_input_payload(),
                admission_artifacts=execution.compiler_artifact_paths(),
            )

            artifact_paths = _restamp_execution(store, observation, execution, result)
            self.assertEqual(execution.status, "quarantine")
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertTrue(any(path.endswith("quarantine.json") for path in artifact_paths))
            self.assertFalse((Path(tmpdir) / "runtime_sessions" / f"{observation.object_id}.json").exists())

    def test_retry_reuses_recorded_artifacts_and_does_not_duplicate_runtime_write(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = _build_runtime(tmpdir)
            observation = _observation_from_fixture(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_transcript("success")),
            )
            first_execution = pipeline.execute(observation)

            with runtime_worker_harness(slug="market-observer-execution-retry", scope=observation.scope):
                orchestrator = GovernedAgentOrchestrator(runtime=runtime)
                first = orchestrator.run_governed_write(
                    requested_delegate_id="market_observer",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=first_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Retry-safe recorded market_observer execution.",
                    spec_input_payload=observation.to_spec_input_payload(),
                    admission_artifacts=first_execution.compiler_artifact_paths(),
                )
                _restamp_execution(store, observation, first_execution, first)
                claim_count = len(runtime.store.load(observation.object_id).claims)

                second_execution = pipeline.execute(observation)
                second = orchestrator.run_governed_write(
                    requested_delegate_id="market_observer",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=second_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Retry-safe recorded market_observer execution.",
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
            observation = _observation_from_fixture(fixture)
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            first_pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_transcript("success")),
            )
            first_execution = first_pipeline.execute(observation)
            self.assertEqual(first_execution.status, "success")

            second_pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_transcript("success")),
            )
            recovered_execution = second_pipeline.execute(observation)
            self.assertTrue(recovered_execution.reused)

            with runtime_worker_harness(slug="market-observer-compiler-recovery", scope=observation.scope):
                result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
                    requested_delegate_id="market_observer",
                    object_id=observation.object_id,
                    subject=observation.subject,
                    scope=observation.scope,
                    signal_draft=recovered_execution.candidate_draft,
                    artifacts_root=tmpdir,
                    object_type=ObjectType.ASSET,
                    user_intent="Recover from recorded compiler artifacts after an interrupted run.",
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


def _observation_from_fixture(fixture: dict[str, object]) -> MarketObservationInput:
    return MarketObservationInput(
        input_id=f"{fixture['case_id']}:1",
        object_id=str(fixture["object_id"]),
        subject=str(fixture["subject"]),
        scope=str(fixture["scope"]),
        observation_text=str(fixture["observation_text"]),
    )


def _restamp_execution(
    store: OwnerArtifactWriter,
    observation: MarketObservationInput,
    execution,
    result,
) -> tuple[str, ...]:
    payload = observation.to_spec_input_payload()
    if execution.candidate_draft is not None:
        payload = dict(execution.candidate_draft.to_agent_payload())
    idempotency_key = compute_idempotency_key(
        requested_delegate_id="market_observer",
        object_id=observation.object_id,
        subject=observation.subject,
        scope=observation.scope,
        signal_payload=payload,
        spec_version=result.spec_version,
    )
    step_id = f"market_observer:{result.spec_version}:{idempotency_key[:12]}"
    return MarketObserverExecutionPipeline(artifact_store=store).restamp_execution_artifacts(
        run_id=result.owner_run_id,
        step_id=step_id,
        spec_version=result.spec_version,
    )


if __name__ == "__main__":
    unittest.main()
