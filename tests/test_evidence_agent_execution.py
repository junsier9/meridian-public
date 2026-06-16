from __future__ import annotations

import copy
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
    EvidenceAgentExecutionPipeline,
    EvidenceAgentLiveBackendConfigError,
    EvidenceObjectContextSummary,
    EvidenceObservationInput,
    OpenAICompatibleEvidenceAgentBackend,
    RecordedTranscriptEvidenceAgentBackend,
)
from enhengclaw.agents.execution.evidence_agent import (
    EVIDENCE_AGENT_COMPILER_CONTRACT_VERSION,
    DeterministicEvidenceAgentCompiler,
    EvidenceAgentTranscriptReplayError,
)
from enhengclaw.agents.owner_state import OwnerArtifactStore, OwnerArtifactWriter
from enhengclaw.core.enums import ObjectType
from enhengclaw.core.session import InMemoryObjectStore
from enhengclaw.orchestration.runtime import GovernedAgentOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.testing import runtime_worker_harness


FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "evidence_agent"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))


def _load_transcript(name: str) -> Path:
    return FIXTURE_ROOT / name / "model_transcript.json"


class EvidenceAgentExecutionTests(unittest.TestCase):
    def test_recorded_success_fixture_compiles_to_one_valid_draft_and_writes_full_execution_artifacts(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_load_transcript("success")),
            )
            result = pipeline.execute(_observation(fixture), _object_context(tmpdir, str(fixture["object_id"])))

            self.assertEqual(result.status, "success")
            self.assertEqual(result.backend_kind, "recorded")
            self.assertIsNotNone(result.candidate_draft)
            self.assertEqual(result.candidate_draft.predicate, "fresh_supportive_flow")
            self.assertTrue(Path(result.prompt_context_path).exists())
            self.assertTrue(Path(result.model_request_path).exists())
            self.assertTrue(Path(result.raw_model_output_path).exists())
            self.assertTrue(Path(result.transcript_path).exists())
            self.assertTrue(Path(result.parsed_draft_path).exists())
            artifact_store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            prompt_context = artifact_store.load_execution_artifact("evidence_agent__golden_evidence_success_aix", "prompt_context")
            self.assertEqual(prompt_context["backend_kind"], "recorded")
            self.assertEqual(prompt_context["contract_version"], EVIDENCE_AGENT_COMPILER_CONTRACT_VERSION)

    def test_recorded_blocked_fixture_returns_blocked_without_candidate_draft(self) -> None:
        fixture = _load_fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_load_transcript("blocked")),
            )
            result = pipeline.execute(_observation(fixture), _object_context(tmpdir, str(fixture["object_id"])))

            self.assertEqual(result.status, "blocked")
            self.assertIsNone(result.candidate_draft)
            self.assertIsNotNone(result.blocked_reason)
            self.assertTrue(Path(result.compiler_output_path).exists())
            self.assertIsNotNone(result.transcript_fingerprint)

    def test_recorded_quarantine_fixture_preserves_quarantine_without_runtime_write(self) -> None:
        fixture = _load_fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_load_transcript("quarantine")),
            )
            result = pipeline.execute(_observation(fixture), _object_context(tmpdir, str(fixture["object_id"])))

            self.assertEqual(result.status, "quarantine")
            self.assertIsNone(result.candidate_draft)
            self.assertEqual(result.quarantine_reason, "candidate_payload_subject_mismatches_host_context")
            self.assertTrue(Path(result.quarantine_path).exists())

    def test_recorded_transcript_object_context_fingerprint_mismatch_fails_closed(self) -> None:
        fixture = _load_fixture("success")
        transcript = json.loads(_load_transcript("success").read_text(encoding="utf-8"))
        transcript["object_context_fingerprint"] = "bad"
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "bad.json"
            transcript_path.write_text(json.dumps(transcript, indent=2, sort_keys=True), encoding="utf-8")
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=transcript_path),
            )
            with self.assertRaises(EvidenceAgentTranscriptReplayError):
                pipeline.execute(_observation(fixture), _object_context(tmpdir, str(fixture["object_id"])))

    def test_live_backend_parses_success_response_and_sanitizes_request_artifact(self) -> None:
        captured: dict[str, object] = {}
        response_body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "status": "success",
                                "blocked_reason": None,
                                "candidate_payloads": [
                                    {
                                        "input_id": "evidence-live-success-1",
                                        "subject": "AIX",
                                        "predicate": "fresh_supportive_flow",
                                        "value": (
                                            "facts=follow-up desk notes still show supportive flow from buyers; "
                                            "interpretation=the existing object keeps receiving bounded supportive evidence; "
                                            "uncertainty=the evidence remains one follow-up signal and not a publish decision"
                                        ),
                                        "claim_type": "flow",
                                        "direction": "bullish",
                                        "source_family": "analytics",
                                        "evidence_level": "E4",
                                        "confidence_hint": 74,
                                        "scope": "spot+perp",
                                        "time_horizon": "short",
                                    }
                                ],
                                "notes": ["live success fixture"],
                            }
                        )
                    }
                }
            ]
        }
        with _live_server(response_body, captured) as base_url, tempfile.TemporaryDirectory() as tmpdir:
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=OpenAICompatibleEvidenceAgentBackend(
                    base_url=base_url,
                    model_name="gpt-test",
                    api_key="secret",
                    timeout_seconds=2,
                ),
            )
            result = pipeline.execute(
                EvidenceObservationInput(
                    input_id="evidence-live-success-1",
                    object_id="evidence-live-success-aix",
                    subject="AIX",
                    scope="spot+perp",
                    evidence_text="Fresh desk notes still show aggressive buyers supporting AIX after the initial breakout.",
                ),
                _object_context(tmpdir, "evidence-live-success-aix"),
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.backend_kind, "live")
            self.assertEqual(captured["path"], "/chat/completions")
            request_body = json.loads(captured["body"])
            self.assertEqual(request_body["model"], "gpt-test")
            stored_request = OwnerArtifactStore(Path(tmpdir) / "agent_owner").load_execution_artifact(
                "evidence_agent__evidence_live_success_aix", "model_request"
            )
            self.assertEqual(stored_request["payload"]["request_headers"]["Authorization"], "Bearer ***redacted***")

    def test_live_backend_config_error_is_explicit(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ENHENGCLAW_EVIDENCE_AGENT_MODEL_BASE_URL": "",
                "ENHENGCLAW_EVIDENCE_AGENT_MODEL_NAME": "",
                "ENHENGCLAW_EVIDENCE_AGENT_API_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaises(EvidenceAgentLiveBackendConfigError):
                OpenAICompatibleEvidenceAgentBackend.from_env()

    def test_prewrite_blocked_owner_path_uses_spec_input_payload_and_execution_artifacts(self) -> None:
        fixture = _load_fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptEvidenceAgentBackend(transcript_path=_load_transcript("blocked")),
            )
            observation = _observation(fixture)
            execution = pipeline.execute(observation, _object_context(tmpdir, str(fixture["object_id"])))
            orchestrator = GovernedAgentOrchestrator(runtime=RuntimeOrchestrator())

            result = orchestrator.run_governed_write(
                requested_delegate_id="evidence_agent",
                object_id=observation.object_id,
                subject=observation.subject,
                scope=observation.scope,
                signal_draft=None,
                artifacts_root=tmpdir,
                user_intent="Block prewrite evidence_agent admission when the compiler cannot emit a stable draft.",
                admission_blocked_reason=execution.blocked_reason,
                spec_input_payload=observation.to_spec_input_payload(),
                admission_artifacts=execution.compiler_artifact_paths(),
            )

            artifact_store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            final_output = artifact_store.load_json(result.final_output_path)
            self.assertEqual(result.run_state, "BLOCKED")
            self.assertEqual(final_output["run_state"], "BLOCKED")
            self.assertEqual(tuple(final_output["output_paths"]), execution.compiler_artifact_paths())

    def test_deterministic_backend_remains_explicit_fallback_only(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=DeterministicEvidenceAgentCompiler(),
            )
            result = pipeline.execute(_observation(fixture), _object_context(tmpdir, str(fixture["object_id"])))
            self.assertEqual(result.backend_kind, "deterministic")
            self.assertEqual(result.status, "success")

    def test_deterministic_backend_accepts_quant_validation_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=DeterministicEvidenceAgentCompiler(),
            )
            result = pipeline.execute(
                EvidenceObservationInput(
                    input_id="cutover-quant-1",
                    object_id="cutover-quant-eth",
                    subject="ETH",
                    scope="spot+perp",
                    evidence_text=(
                        "facts=ETH single-asset logistic_regression passed the quant validation gates with positive "
                        "out-of-sample performance; interpretation=this is a quantitatively validated candidate worth "
                        "feeding back into the thesis workflow for explanation and monitoring; "
                        "uncertainty=the alpha still depends on future regime stability and daily re-validation."
                    ),
                ),
                _object_context(tmpdir, "cutover-quant-eth", subject="ETH"),
            )

            self.assertEqual(result.backend_kind, "deterministic")
            self.assertEqual(result.status, "success")
            self.assertIsNotNone(result.candidate_draft)
            self.assertEqual(result.candidate_draft.predicate, "fresh_supportive_flow")
            self.assertEqual(result.candidate_draft.subject, "ETH")

    def test_deterministic_backend_accepts_watchlist_support_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = EvidenceAgentExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=DeterministicEvidenceAgentCompiler(),
            )
            result = pipeline.execute(
                EvidenceObservationInput(
                    input_id="cutover-watchlist-1",
                    object_id="cutover-watchlist-hype",
                    subject="HYPE",
                    scope="spot+perp",
                    evidence_text=(
                        "facts=Hyperliquid is ranked #13 by market cap at roughly $9.9B, with about $227M in 24-hour volume "
                        "and modestly positive 7-day performance; interpretation=this keeps HYPE on the large-cap watchlist "
                        "as a higher-beta alternative where exchange narrative and order-flow can still matter; "
                        "uncertainty=I still need a clearer support map and leverage read before treating it as a top-tier thesis."
                    ),
                ),
                _object_context(tmpdir, "cutover-watchlist-hype", subject="HYPE"),
            )

            self.assertEqual(result.backend_kind, "deterministic")
            self.assertEqual(result.status, "success")
            self.assertIsNotNone(result.candidate_draft)
            self.assertEqual(result.candidate_draft.predicate, "fresh_supportive_flow")
            self.assertEqual(result.candidate_draft.subject, "HYPE")


def _observation(fixture: dict[str, object]) -> EvidenceObservationInput:
    return EvidenceObservationInput(
        input_id=f"{fixture['case_id']}:1",
        object_id=str(fixture["object_id"]),
        subject=str(fixture["subject"]),
        scope=str(fixture["scope"]),
        evidence_text=str(fixture["evidence_text"]),
    )


def _object_context(tmpdir: str, object_id: str, *, subject: str = "AIX") -> EvidenceObjectContextSummary:
    del tmpdir
    runtime = RuntimeOrchestrator(store=InMemoryObjectStore())
    with runtime_worker_harness(slug=f"evidence-context-{object_id}", scope="spot+perp"):
        runtime.run_new(
            object_id=object_id,
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=_seed_signals(object_id, subject=subject),
        )
    session = runtime.store.load(object_id)
    return EvidenceObjectContextSummary.from_runtime_session(session, subject=subject, scope="spot+perp")


def _seed_signals(object_id: str, *, subject: str = "AIX"):
    from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, SourceFamily, TimeHorizon
    from enhengclaw.core.signals import Signal

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
            scope="spot+perp",
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
            scope="spot+perp",
            time_horizon=TimeHorizon.INTRADAY,
        ),
    ]


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
            "LiveHandler",
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
