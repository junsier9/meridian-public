from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import ROOT, SRC

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.execution import (
    AttentionAllocatorExecutionPipeline,
    AttentionAllocatorLiveBackendConfigError,
    AttentionAllocatorObservationInput,
    OpenAICompatibleAttentionAllocatorBackend,
    OpenAICompatibleResearchLeadBackend,
    OpenAICompatibleResearchSynthesizerBackend,
    OpenAICompatibleRiskGovernanceAgentBackend,
    OpenAICompatibleRiskSignalAgentBackend,
    OpenAICompatibleValidationAgentBackend,
    RecordedTranscriptAttentionAllocatorBackend,
    RecordedTranscriptResearchLeadBackend,
    RecordedTranscriptResearchSynthesizerBackend,
    RecordedTranscriptRiskGovernanceAgentBackend,
    RecordedTranscriptRiskSignalAgentBackend,
    RecordedTranscriptValidationAgentBackend,
    ResearchLeadExecutionPipeline,
    ResearchLeadLiveBackendConfigError,
    ResearchLeadObservationInput,
    ResearchSynthesisExecutionPipeline,
    ResearchSynthesisObservationInput,
    ResearchSynthesizerLiveBackendConfigError,
    RiskGovernanceAgentLiveBackendConfigError,
    RiskGovernanceExecutionPipeline,
    RiskGovernanceObservationInput,
    RiskSignalAgentLiveBackendConfigError,
    RiskSignalExecutionPipeline,
    RiskSignalObservationInput,
    ValidationAgentLiveBackendConfigError,
    ValidationExecutionPipeline,
    ValidationObservationInput,
)
from enhengclaw.agents.execution.attention_allocator import (
    ATTENTION_ALLOCATOR_COMPILER_CONTRACT_VERSION,
    AttentionAllocatorTranscriptReplayError,
    build_attention_allocator_object_context,
)
from enhengclaw.agents.execution.research_lead import (
    RESEARCH_LEAD_COMPILER_CONTRACT_VERSION,
    ResearchLeadTranscriptReplayError,
    build_research_lead_object_context,
)
from enhengclaw.agents.execution.research_synthesizer import (
    RESEARCH_SYNTHESIZER_COMPILER_CONTRACT_VERSION,
    ResearchSynthesizerTranscriptReplayError,
    build_research_synthesizer_object_context,
)
from enhengclaw.agents.execution.risk_governance_agent import (
    RISK_GOVERNANCE_AGENT_COMPILER_CONTRACT_VERSION,
    RiskGovernanceAgentTranscriptReplayError,
    build_risk_governance_object_context,
)
from enhengclaw.agents.execution.risk_signal_agent import (
    DeterministicRiskSignalAgentCompiler,
    RISK_SIGNAL_AGENT_COMPILER_CONTRACT_VERSION,
    RiskSignalAgentTranscriptReplayError,
    build_risk_signal_object_context,
)
from enhengclaw.agents.execution.validation_agent import (
    VALIDATION_AGENT_COMPILER_CONTRACT_VERSION,
    ValidationAgentTranscriptReplayError,
    build_validation_object_context,
)
from enhengclaw.agents.owner_state import OwnerArtifactStore, OwnerArtifactWriter
from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.core.signals import Signal
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


def _write_transcript(path: Path, payload: dict[str, object]) -> None:
    normalized = copy.deepcopy(payload)
    normalized["transcript_fingerprint"] = _transcript_fingerprint(normalized)
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")


def _transcript_fingerprint(payload: dict[str, object]) -> str:
    serializable = {key: value for key, value in payload.items() if key != "transcript_fingerprint"}
    canonical = json.dumps(serializable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PendingSliceExecutionTestMixin:
    fixture_root: Path
    transcript_error: type[Exception]
    live_backend_cls: type
    live_backend_error: type[Exception]
    recorded_backend_cls: type
    pipeline_cls: type
    observation_cls: type
    context_builder: staticmethod
    contract_version: str
    env_names: tuple[str, str, str]
    text_key: str
    expected_success_predicate: str
    invalid_value_reason: str | None = None

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

    def _object_context(self, object_id: str):
        runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
        with runtime_worker_harness(slug=f"{self.__class__.__name__}-{object_id}", scope="spot+perp"):
            runtime.run_new(
                object_id=object_id,
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=_seed_signals(object_id),
            )
        return self.context_builder(runtime=runtime, object_id=object_id, subject="AIX", scope="spot+perp")

    def _success_envelope(self) -> dict[str, object]:
        transcript = json.loads(self._transcript("success").read_text(encoding="utf-8"))
        return copy.deepcopy(transcript["compiler_output"])

    def test_recorded_success_fixture_compiles_and_writes_execution_artifacts(self) -> None:
        fixture = self._fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = self.pipeline_cls(
                artifact_store=store,
                compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("success")),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))

            self.assertEqual(result.status, "success")
            self.assertEqual(result.backend_kind, "recorded")
            self.assertIsNotNone(result.candidate_draft)
            self.assertEqual(result.candidate_draft.predicate, self.expected_success_predicate)
            self.assertTrue(Path(result.prompt_context_path).exists())
            self.assertTrue(Path(result.model_request_path).exists())
            self.assertTrue(Path(result.raw_model_output_path).exists())
            self.assertTrue(Path(result.transcript_path).exists())
            self.assertTrue(Path(result.parsed_draft_path).exists())
            artifact_store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            prompt_context = artifact_store.load_execution_artifact(
                f"{self.pipeline_cls().spec.slice_id}__{fixture['object_id'].replace('-', '_')}",
                "prompt_context",
            )
            self.assertEqual(prompt_context["backend_kind"], "recorded")
            self.assertEqual(prompt_context["contract_version"], self.contract_version)

    def test_recorded_blocked_fixture_returns_blocked_without_candidate(self) -> None:
        fixture = self._fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("blocked")),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))

            self.assertEqual(result.status, "blocked")
            self.assertIsNone(result.candidate_draft)
            self.assertIsNotNone(result.blocked_reason)
            self.assertTrue(Path(result.compiler_output_path).exists())
            self.assertIsNotNone(result.transcript_fingerprint)

    def test_recorded_quarantine_fixture_preserves_quarantine(self) -> None:
        fixture = self._fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.recorded_backend_cls(transcript_path=self._transcript("quarantine")),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))

            self.assertEqual(result.status, "quarantine")
            self.assertIsNone(result.candidate_draft)
            self.assertEqual(result.quarantine_reason, "candidate_payload_subject_mismatches_host_context")
            self.assertTrue(Path(result.quarantine_path).exists())

    def test_recorded_transcript_object_context_fingerprint_mismatch_fails_closed(self) -> None:
        fixture = self._fixture("success")
        transcript = json.loads(self._transcript("success").read_text(encoding="utf-8"))
        transcript["object_context_fingerprint"] = "bad"
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "bad.json"
            _write_transcript(transcript_path, transcript)
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.recorded_backend_cls(transcript_path=transcript_path),
            )
            with self.assertRaises(self.transcript_error):
                pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))

    def test_live_backend_parses_success_response_and_sanitizes_request_artifact(self) -> None:
        captured: dict[str, object] = {}
        response_body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(self._success_envelope())
                    }
                }
            ]
        }
        fixture = self._fixture("success")
        with _live_server(response_body, captured) as base_url, tempfile.TemporaryDirectory() as tmpdir:
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.live_backend_cls(
                    base_url=base_url,
                    model_name="gpt-test",
                    api_key="secret",
                    timeout_seconds=2,
                ),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))

            self.assertEqual(result.status, "success")
            self.assertEqual(result.backend_kind, "live")
            self.assertEqual(captured["path"], "/chat/completions")
            request_body = json.loads(captured["body"])
            self.assertEqual(request_body["model"], "gpt-test")
            stored_request = OwnerArtifactStore(Path(tmpdir) / "agent_owner").load_execution_artifact(
                f"{self.pipeline_cls().spec.slice_id}__{fixture['object_id'].replace('-', '_')}",
                "model_request",
            )
            self.assertEqual(stored_request["payload"]["request_headers"]["Authorization"], "Bearer ***redacted***")

    def test_live_backend_config_error_is_explicit(self) -> None:
        env = {name: "" for name in self.env_names}
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(self.live_backend_error):
                self.live_backend_cls.from_env()

    def test_local_validator_rejects_illegal_predicate(self) -> None:
        fixture = self._fixture("success")
        transcript = json.loads(self._transcript("success").read_text(encoding="utf-8"))
        transcript["compiler_output"]["candidate_payloads"][0]["predicate"] = "not_allowed"
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "illegal-predicate.json"
            _write_transcript(transcript_path, transcript)
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.recorded_backend_cls(transcript_path=transcript_path),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))
            self.assertEqual(result.status, "quarantine")
            self.assertEqual(result.quarantine_reason, "candidate_payload_predicate_outside_bounded_set")

    def test_local_validator_rejects_confidence_outside_bounded_range(self) -> None:
        fixture = self._fixture("success")
        transcript = json.loads(self._transcript("success").read_text(encoding="utf-8"))
        transcript["compiler_output"]["candidate_payloads"][0]["confidence_hint"] = 10
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "bad-confidence.json"
            _write_transcript(transcript_path, transcript)
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.recorded_backend_cls(transcript_path=transcript_path),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))
            self.assertEqual(result.status, "quarantine")
            self.assertEqual(result.quarantine_reason, "candidate_payload_confidence_hint_outside_bounded_range")

    def test_local_validator_rejects_scope_mismatch(self) -> None:
        fixture = self._fixture("success")
        transcript = json.loads(self._transcript("success").read_text(encoding="utf-8"))
        transcript["compiler_output"]["candidate_payloads"][0]["scope"] = "spot"
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "bad-scope.json"
            _write_transcript(transcript_path, transcript)
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.recorded_backend_cls(transcript_path=transcript_path),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))
            self.assertEqual(result.status, "quarantine")
            self.assertEqual(result.quarantine_reason, "candidate_payload_scope_mismatches_host_context")

    def test_local_validator_rejects_missing_required_value_segments_when_applicable(self) -> None:
        if self.invalid_value_reason is None:
            self.skipTest("slice does not require segmented value validation")
        fixture = self._fixture("success")
        transcript = json.loads(self._transcript("success").read_text(encoding="utf-8"))
        transcript["compiler_output"]["candidate_payloads"][0]["value"] = "facts=only one segment"
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "bad-value.json"
            _write_transcript(transcript_path, transcript)
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=self.recorded_backend_cls(transcript_path=transcript_path),
            )
            result = pipeline.execute(self._observation(fixture), self._object_context(str(fixture["object_id"])))
            self.assertEqual(result.status, "quarantine")
            self.assertEqual(result.quarantine_reason, self.invalid_value_reason)


class RiskSignalExecutionTests(PendingSliceExecutionTestMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "risk_signal_agent"
    transcript_error = RiskSignalAgentTranscriptReplayError
    live_backend_cls = OpenAICompatibleRiskSignalAgentBackend
    live_backend_error = RiskSignalAgentLiveBackendConfigError
    recorded_backend_cls = RecordedTranscriptRiskSignalAgentBackend
    pipeline_cls = RiskSignalExecutionPipeline
    observation_cls = RiskSignalObservationInput
    context_builder = staticmethod(build_risk_signal_object_context)
    contract_version = RISK_SIGNAL_AGENT_COMPILER_CONTRACT_VERSION
    env_names = (
        "ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL_BASE_URL",
        "ENHENGCLAW_RISK_SIGNAL_AGENT_MODEL_NAME",
        "ENHENGCLAW_RISK_SIGNAL_AGENT_API_KEY",
    )
    text_key = "risk_text"
    expected_success_predicate = "fresh_invalidation_risk"
    invalid_value_reason = "candidate_payload_value_missing_required_segments"

    def test_deterministic_backend_accepts_quant_invalidation_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = self.pipeline_cls(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=DeterministicRiskSignalAgentCompiler(),
            )
            result = pipeline.execute(
                self.observation_cls(
                    input_id="risk-quant-1",
                    object_id="risk-quant-aix",
                    subject="AIX",
                    scope="spot+perp",
                    risk_text=(
                        "Invalidate the quant thesis if the next daily quant cycle loses OOS stability "
                        "or the subject exits the allowed liquidity/risk envelope."
                    ),
                ),
                self._object_context("risk-quant-aix"),
            )

            self.assertEqual(result.backend_kind, "deterministic")
            self.assertEqual(result.status, "success")
            self.assertIsNotNone(result.candidate_draft)
            self.assertEqual(result.candidate_draft.predicate, "fresh_invalidation_risk")


class RiskGovernanceExecutionTests(PendingSliceExecutionTestMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "risk_governance_agent"
    transcript_error = RiskGovernanceAgentTranscriptReplayError
    live_backend_cls = OpenAICompatibleRiskGovernanceAgentBackend
    live_backend_error = RiskGovernanceAgentLiveBackendConfigError
    recorded_backend_cls = RecordedTranscriptRiskGovernanceAgentBackend
    pipeline_cls = RiskGovernanceExecutionPipeline
    observation_cls = RiskGovernanceObservationInput
    context_builder = staticmethod(build_risk_governance_object_context)
    contract_version = RISK_GOVERNANCE_AGENT_COMPILER_CONTRACT_VERSION
    env_names = (
        "ENHENGCLAW_RISK_GOVERNANCE_AGENT_MODEL_BASE_URL",
        "ENHENGCLAW_RISK_GOVERNANCE_AGENT_MODEL_NAME",
        "ENHENGCLAW_RISK_GOVERNANCE_AGENT_API_KEY",
    )
    text_key = "governance_text"
    expected_success_predicate = "restricted_monitoring_required"


class ValidationExecutionTests(PendingSliceExecutionTestMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "validation_agent"
    transcript_error = ValidationAgentTranscriptReplayError
    live_backend_cls = OpenAICompatibleValidationAgentBackend
    live_backend_error = ValidationAgentLiveBackendConfigError
    recorded_backend_cls = RecordedTranscriptValidationAgentBackend
    pipeline_cls = ValidationExecutionPipeline
    observation_cls = ValidationObservationInput
    context_builder = staticmethod(build_validation_object_context)
    contract_version = VALIDATION_AGENT_COMPILER_CONTRACT_VERSION
    env_names = (
        "ENHENGCLAW_VALIDATION_AGENT_MODEL_BASE_URL",
        "ENHENGCLAW_VALIDATION_AGENT_MODEL_NAME",
        "ENHENGCLAW_VALIDATION_AGENT_API_KEY",
    )
    text_key = "validation_text"
    expected_success_predicate = "publish_gate_hold"


class AttentionAllocatorExecutionTests(PendingSliceExecutionTestMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "attention_allocator"
    transcript_error = AttentionAllocatorTranscriptReplayError
    live_backend_cls = OpenAICompatibleAttentionAllocatorBackend
    live_backend_error = AttentionAllocatorLiveBackendConfigError
    recorded_backend_cls = RecordedTranscriptAttentionAllocatorBackend
    pipeline_cls = AttentionAllocatorExecutionPipeline
    observation_cls = AttentionAllocatorObservationInput
    context_builder = staticmethod(build_attention_allocator_object_context)
    contract_version = ATTENTION_ALLOCATOR_COMPILER_CONTRACT_VERSION
    env_names = (
        "ENHENGCLAW_ATTENTION_ALLOCATOR_MODEL_BASE_URL",
        "ENHENGCLAW_ATTENTION_ALLOCATOR_MODEL_NAME",
        "ENHENGCLAW_ATTENTION_ALLOCATOR_API_KEY",
    )
    text_key = "attention_text"
    expected_success_predicate = "attention_posture_advance"


class ResearchSynthesizerExecutionTests(PendingSliceExecutionTestMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "research_synthesizer"
    transcript_error = ResearchSynthesizerTranscriptReplayError
    live_backend_cls = OpenAICompatibleResearchSynthesizerBackend
    live_backend_error = ResearchSynthesizerLiveBackendConfigError
    recorded_backend_cls = RecordedTranscriptResearchSynthesizerBackend
    pipeline_cls = ResearchSynthesisExecutionPipeline
    observation_cls = ResearchSynthesisObservationInput
    context_builder = staticmethod(build_research_synthesizer_object_context)
    contract_version = RESEARCH_SYNTHESIZER_COMPILER_CONTRACT_VERSION
    env_names = (
        "ENHENGCLAW_RESEARCH_SYNTHESIZER_MODEL_BASE_URL",
        "ENHENGCLAW_RESEARCH_SYNTHESIZER_MODEL_NAME",
        "ENHENGCLAW_RESEARCH_SYNTHESIZER_API_KEY",
    )
    text_key = "synthesis_text"
    expected_success_predicate = "synthesis_preview_bullish"


class ResearchLeadExecutionTests(PendingSliceExecutionTestMixin, unittest.TestCase):
    fixture_root = ROOT / "fixtures" / "agent_golden" / "research_lead"
    transcript_error = ResearchLeadTranscriptReplayError
    live_backend_cls = OpenAICompatibleResearchLeadBackend
    live_backend_error = ResearchLeadLiveBackendConfigError
    recorded_backend_cls = RecordedTranscriptResearchLeadBackend
    pipeline_cls = ResearchLeadExecutionPipeline
    observation_cls = ResearchLeadObservationInput
    context_builder = staticmethod(build_research_lead_object_context)
    contract_version = RESEARCH_LEAD_COMPILER_CONTRACT_VERSION
    env_names = (
        "ENHENGCLAW_RESEARCH_LEAD_MODEL_BASE_URL",
        "ENHENGCLAW_RESEARCH_LEAD_MODEL_NAME",
        "ENHENGCLAW_RESEARCH_LEAD_API_KEY",
    )
    text_key = "directive_text"
    expected_success_predicate = "next_stage_targeted_refresh"


class _Handler(BaseHTTPRequestHandler):
    response_body: dict[str, object] = {}
    status_code: int = 200
    captured: dict[str, object] | None = None

    def do_POST(self) -> None:  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
        if self.captured is not None:
            self.captured["path"] = self.path
            self.captured["body"] = body
        payload = json.dumps(self.response_body).encode("utf-8")
        self.send_response(self.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class _live_server:
    def __init__(self, response_body: dict[str, object], captured: dict[str, object] | None = None, status_code: int = 200):
        self.response_body = response_body
        self.status_code = status_code
        self.captured = captured
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> str:
        handler = type(
            "PendingSliceLiveHandler",
            (_Handler,),
            {
                "response_body": copy.deepcopy(self.response_body),
                "status_code": self.status_code,
                "captured": self.captured,
            },
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
