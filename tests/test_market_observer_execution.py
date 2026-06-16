from __future__ import annotations

import copy
import io
import json
import os
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib import error

from tests.test_helpers import ROOT, SRC

import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.agents.execution import (
    MarketObservationInput,
    MarketObserverExecutionPipeline,
    MarketObserverLiveBackendConfigError,
    OpenAICompatibleMarketObserverBackend,
    RecordedTranscriptMarketObserverBackend,
)
from enhengclaw.agents.execution._shared import normalize_compiler_envelope
from enhengclaw.agents.execution._shared import SliceCompilerTransportError, openai_compatible_compile
from enhengclaw.agents.execution.market_observer import (
    MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
    DeterministicMarketObserverCompiler,
    MarketObserverTranscriptReplayError,
)
from enhengclaw.agents.owner_state import OwnerArtifactStore, OwnerArtifactWriter
from enhengclaw.orchestration.runtime import GovernedAgentOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator


FIXTURE_ROOT = ROOT / "fixtures" / "agent_golden" / "market_observer"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name / "input.json").read_text(encoding="utf-8"))


def _load_transcript(name: str) -> Path:
    return FIXTURE_ROOT / name / "model_transcript.json"


class MarketObserverExecutionTests(unittest.TestCase):
    def test_recorded_success_fixture_compiles_to_one_valid_draft_and_writes_full_execution_artifacts(self) -> None:
        fixture = _load_fixture("success")
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_load_transcript("success")),
            )
            result = pipeline.execute(_observation(fixture))

            self.assertEqual(result.status, "success")
            self.assertEqual(result.backend_kind, "recorded")
            self.assertIsNotNone(result.candidate_draft)
            self.assertEqual(result.candidate_draft.predicate, "agent_market_structure_support")
            self.assertTrue(Path(result.prompt_context_path).exists())
            self.assertTrue(Path(result.model_request_path).exists())
            self.assertTrue(Path(result.raw_model_output_path).exists())
            self.assertTrue(Path(result.transcript_path).exists())
            self.assertTrue(Path(result.parsed_draft_path).exists())
            artifact_store = OwnerArtifactStore(Path(tmpdir) / "agent_owner")
            prompt_context = artifact_store.load_execution_artifact("market_observer__golden_success_aix", "prompt_context")
            self.assertEqual(prompt_context["backend_kind"], "recorded")
            self.assertEqual(prompt_context["contract_version"], MARKET_OBSERVER_COMPILER_CONTRACT_VERSION)

    def test_recorded_blocked_fixture_returns_blocked_without_candidate_draft(self) -> None:
        fixture = _load_fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_load_transcript("blocked")),
            )
            result = pipeline.execute(_observation(fixture))

            self.assertEqual(result.status, "blocked")
            self.assertIsNone(result.candidate_draft)
            self.assertIsNotNone(result.blocked_reason)
            self.assertTrue(Path(result.compiler_output_path).exists())
            self.assertIsNotNone(result.transcript_fingerprint)

    def test_recorded_quarantine_fixture_preserves_quarantine_without_runtime_write(self) -> None:
        fixture = _load_fixture("quarantine")
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_load_transcript("quarantine")),
            )
            result = pipeline.execute(_observation(fixture))

            self.assertEqual(result.status, "quarantine")
            self.assertIsNone(result.candidate_draft)
            self.assertEqual(result.quarantine_reason, "candidate_payload_subject_mismatches_host_context")
            self.assertTrue(Path(result.quarantine_path).exists())

    def test_recorded_transcript_fingerprint_mismatch_fails_closed(self) -> None:
        fixture = _load_fixture("success")
        transcript = json.loads(_load_transcript("success").read_text(encoding="utf-8"))
        transcript["transcript_fingerprint"] = "bad"
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = Path(tmpdir) / "bad.json"
            transcript_path.write_text(json.dumps(transcript, indent=2, sort_keys=True), encoding="utf-8")
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=transcript_path),
            )
            with self.assertRaises(MarketObserverTranscriptReplayError):
                pipeline.execute(_observation(fixture))

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
                                        "input_id": "live-success-1",
                                        "subject": "AIX",
                                        "predicate": "agent_market_structure_support",
                                        "value": (
                                            "facts=higher low remains above support; "
                                            "interpretation=structure still looks constructive; "
                                            "uncertainty=follow-through still needs confirmation"
                                        ),
                                        "claim_type": "market_structure",
                                        "direction": "bullish",
                                        "source_family": "analytics",
                                        "evidence_level": "E4",
                                        "confidence_hint": 73,
                                        "scope": "spot+perp",
                                        "time_horizon": "intraday",
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
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=OpenAICompatibleMarketObserverBackend(
                    base_url=base_url,
                    model_name="gpt-test",
                    api_key="secret",
                    timeout_seconds=2,
                ),
            )
            result = pipeline.execute(
                MarketObservationInput(
                    input_id="live-success-1",
                    object_id="live-success-aix",
                    subject="AIX",
                    scope="spot+perp",
                    observation_text="AIX keeps a higher low above support with no fresh breakdown.",
                )
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.backend_kind, "live")
            self.assertEqual(captured["path"], "/chat/completions")
            request_body = json.loads(captured["body"])
            self.assertEqual(request_body["model"], "gpt-test")
            stored_request = OwnerArtifactStore(Path(tmpdir) / "agent_owner").load_execution_artifact(
                "market_observer__live_success_aix", "model_request"
            )
            self.assertEqual(stored_request["payload"]["request_headers"]["Authorization"], "Bearer ***redacted***")

    def test_live_backend_raises_on_http_error(self) -> None:
        with _live_server({"error": "bad"}, status_code=503) as base_url:
            backend = OpenAICompatibleMarketObserverBackend(
                base_url=base_url,
                model_name="gpt-test",
                api_key="secret",
                timeout_seconds=2,
            )
            pipeline = MarketObserverExecutionPipeline(compiler_backend=backend)
            with self.assertRaisesRegex(Exception, "HTTP 503"):
                pipeline.execute(
                    MarketObservationInput(
                        input_id="http-error-1",
                        object_id="http-error-aix",
                        subject="AIX",
                        scope="spot+perp",
                        observation_text="AIX stays constructive.",
                    )
                )

    def test_live_backend_blocks_when_assistant_content_is_missing(self) -> None:
        response_body = {"choices": [{"message": {}}]}
        with _live_server(response_body) as base_url, tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=OpenAICompatibleMarketObserverBackend(
                    base_url=base_url,
                    model_name="gpt-test",
                    api_key="secret",
                    timeout_seconds=2,
                ),
            )
            result = pipeline.execute(
                MarketObservationInput(
                    input_id="missing-assistant-1",
                    object_id="missing-assistant-aix",
                    subject="AIX",
                    scope="spot+perp",
                    observation_text="AIX stays constructive.",
                )
            )

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.blocked_reason, "model_response_missing_assistant_content")

    def test_live_backend_blocks_when_assistant_content_is_not_json(self) -> None:
        response_body = {"choices": [{"message": {"content": "not json"}}]}
        with _live_server(response_body) as base_url, tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=OpenAICompatibleMarketObserverBackend(
                    base_url=base_url,
                    model_name="gpt-test",
                    api_key="secret",
                    timeout_seconds=2,
                ),
            )
            result = pipeline.execute(
                MarketObservationInput(
                    input_id="not-json-1",
                    object_id="not-json-aix",
                    subject="AIX",
                    scope="spot+perp",
                    observation_text="AIX stays constructive.",
                )
            )

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.blocked_reason, "model_output_not_valid_json_envelope")

    def test_normalize_compiler_envelope_recovers_markdown_fenced_json(self) -> None:
        assistant_text = """```json
{"status":"success","blocked_reason":null,"candidate_payloads":[{"input_id":"fenced-1","subject":"AIX","predicate":"agent_market_structure_support","value":"facts=ok; interpretation=ok; uncertainty=ok","claim_type":"market_structure","direction":"bullish","source_family":"analytics","evidence_level":"E4","confidence_hint":70,"scope":"spot+perp","time_horizon":"intraday"}],"notes":["fenced"]}
```"""
        compiler_output = normalize_compiler_envelope(
            assistant_text=assistant_text,
            raw_body=json.dumps({"choices": [{"message": {"content": assistant_text}}]}),
            parse_error=None,
        )
        self.assertEqual(compiler_output["status"], "success")
        self.assertIn("assistant_content_markdown_fence_stripped", compiler_output["notes"])

    def test_openai_compatible_compile_wraps_timeout_as_transport_error(self) -> None:
        prompt_context = {
            "messages": [{"role": "system", "content": "Return JSON only."}],
            "prompt_fingerprint": "prompt-fingerprint",
            "object_context_fingerprint": "object-fingerprint",
        }
        with patch(
            "enhengclaw.agents.execution._shared.request.urlopen",
            side_effect=socket.timeout("The read operation timed out"),
        ):
            with self.assertRaisesRegex(SliceCompilerTransportError, "timed out"):
                openai_compatible_compile(
                    base_url="https://api.openai.com/v1",
                    model_name="gpt-test",
                    api_key="secret",
                    timeout_seconds=1.0,
                    backend_kind="openai_compatible",
                    backend_name="gpt-test",
                    contract_version=MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
                    failure_label="market observer test",
                    observation_fingerprint="observation-fingerprint",
                    prompt_context=prompt_context,
                )

    def test_openai_compatible_compile_sends_response_format_and_completion_cap(self) -> None:
        prompt_context = {
            "messages": [{"role": "system", "content": "Return JSON only."}],
            "prompt_fingerprint": "prompt-fingerprint",
            "object_context_fingerprint": "object-fingerprint",
        }
        response_body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "status": "success",
                                "blocked_reason": None,
                                "candidate_payloads": [{"payload": "ok"}],
                                "notes": [],
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        }
        captured: dict[str, object] = {}
        with _live_server(response_body, captured) as base_url:
            artifacts = openai_compatible_compile(
                base_url=base_url,
                model_name="gpt-test",
                api_key="secret",
                timeout_seconds=1.0,
                backend_kind="openai_compatible",
                backend_name="gpt-test",
                contract_version=MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
                failure_label="shared compile success test",
                observation_fingerprint="observation-fingerprint",
                prompt_context=prompt_context,
                response_format={"type": "json_object"},
                max_completion_tokens=321,
                request_metadata={"stage": "unit-test"},
                allow_retry_without_response_format=True,
            )

        request_body = json.loads(str(captured["body"]))
        self.assertEqual(request_body["response_format"], {"type": "json_object"})
        self.assertEqual(request_body["max_completion_tokens"], 321)
        self.assertEqual(artifacts.model_request["request_metadata"]["stage"], "unit-test")
        self.assertEqual(artifacts.model_request["retry_count"], 0)
        self.assertFalse(artifacts.model_request["fallback_without_response_format"])

    def test_openai_compatible_compile_retries_once_without_response_format(self) -> None:
        prompt_context = {
            "messages": [{"role": "system", "content": "Return JSON only."}],
            "prompt_fingerprint": "prompt-fingerprint",
            "object_context_fingerprint": "object-fingerprint",
        }
        attempts: list[dict[str, object]] = []

        class _FakeResponse:
            def __init__(self, body: str, *, status: int = 200) -> None:
                self._body = body
                self.status = status

            def read(self) -> bytes:
                return self._body.encode("utf-8")

            def __enter__(self) -> "_FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

        def _fake_urlopen(http_request, timeout):  # type: ignore[no-untyped-def]
            del timeout
            request_body = json.loads(http_request.data.decode("utf-8"))
            attempts.append(request_body)
            if len(attempts) == 1:
                raise error.HTTPError(
                    http_request.full_url,
                    400,
                    "Bad Request",
                    hdrs=None,
                    fp=io.BytesIO(b'{"error":{"message":"response_format is not supported"}}'),
                )
            response_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "success",
                                    "blocked_reason": None,
                                    "candidate_payloads": [{"payload": "ok"}],
                                    "notes": [],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 9, "completion_tokens": 2, "total_tokens": 11},
            }
            return _FakeResponse(json.dumps(response_payload))

        with patch("enhengclaw.agents.execution._shared.request.urlopen", side_effect=_fake_urlopen):
            artifacts = openai_compatible_compile(
                base_url="https://api.openai.com/v1",
                model_name="gpt-test",
                api_key="secret",
                timeout_seconds=1.0,
                backend_kind="openai_compatible",
                backend_name="gpt-test",
                contract_version=MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
                failure_label="shared compile fallback test",
                observation_fingerprint="observation-fingerprint",
                prompt_context=prompt_context,
                response_format={"type": "json_object"},
                max_completion_tokens=123,
                request_metadata={"stage": "fallback-test"},
                allow_retry_without_response_format=True,
            )

        self.assertEqual(len(attempts), 2)
        self.assertIn("response_format", attempts[0])
        self.assertNotIn("response_format", attempts[1])
        self.assertEqual(attempts[1]["max_completion_tokens"], 123)
        self.assertEqual(artifacts.model_request["retry_count"], 1)
        self.assertTrue(artifacts.model_request["fallback_without_response_format"])

    def test_live_backend_config_error_is_explicit(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL": "",
                "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME": "",
                "ENHENGCLAW_MARKET_OBSERVER_API_KEY": "",
            },
            clear=False,
        ):
            with self.assertRaises(MarketObserverLiveBackendConfigError):
                OpenAICompatibleMarketObserverBackend.from_env()

    def test_prewrite_blocked_owner_path_uses_spec_input_payload_and_execution_artifacts(self) -> None:
        fixture = _load_fixture("blocked")
        with tempfile.TemporaryDirectory() as tmpdir:
            store = OwnerArtifactWriter(Path(tmpdir) / "agent_owner")
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=store,
                compiler_backend=RecordedTranscriptMarketObserverBackend(transcript_path=_load_transcript("blocked")),
            )
            observation = _observation(fixture)
            execution = pipeline.execute(observation)
            orchestrator = GovernedAgentOrchestrator(runtime=RuntimeOrchestrator())

            result = orchestrator.run_governed_write(
                requested_delegate_id="market_observer",
                object_id=observation.object_id,
                subject=observation.subject,
                scope=observation.scope,
                signal_draft=None,
                artifacts_root=tmpdir,
                user_intent="Block prewrite market_observer admission when the compiler cannot emit a stable draft.",
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
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=DeterministicMarketObserverCompiler(),
            )
            result = pipeline.execute(_observation(fixture))
            self.assertEqual(result.backend_kind, "deterministic")
            self.assertEqual(result.status, "success")

    def test_deterministic_backend_accepts_constructive_relative_strength_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = MarketObserverExecutionPipeline(
                artifact_store=OwnerArtifactWriter(Path(tmpdir) / "agent_owner"),
                compiler_backend=DeterministicMarketObserverCompiler(),
            )
            result = pipeline.execute(
                MarketObservationInput(
                    input_id="cutover-structural-1",
                    object_id="cutover-structural-hype",
                    subject="HYPE",
                    scope="spot+perp",
                    observation_text=(
                        "HYPE remains one of the stronger exchange-linked large-cap names, "
                        "but the setup is more catalyst-sensitive and volatile than ETH."
                    ),
                )
            )

            self.assertEqual(result.backend_kind, "deterministic")
            self.assertEqual(result.status, "success")
            self.assertIsNotNone(result.candidate_draft)
            self.assertEqual(result.candidate_draft.predicate, "agent_market_structure_support")
            self.assertEqual(result.candidate_draft.subject, "HYPE")


def _observation(fixture: dict[str, object]) -> MarketObservationInput:
    return MarketObservationInput(
        input_id=f"{fixture['case_id']}:1",
        object_id=str(fixture["object_id"]),
        subject=str(fixture["subject"]),
        scope=str(fixture["scope"]),
        observation_text=str(fixture["observation_text"]),
    )


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
