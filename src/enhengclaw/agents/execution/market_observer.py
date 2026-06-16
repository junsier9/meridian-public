from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

from enhengclaw.compat.naming import env_aliases_text, getenv_compat
from enhengclaw.agents.owner_state import OwnerArtifactWriter, build_owner_run_id
from enhengclaw.agents.schemas.market_observer import MarketObserverSignalDraft


DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "market_observer.system.md"
MARKET_OBSERVER_COMPILER_CONTRACT_VERSION = "market_observer_compiler_v3"
MARKET_OBSERVER_LIVE_BACKEND_NAME = "openai_compatible_chat_completions"
MARKET_OBSERVER_RECORDED_BACKEND_NAME = "recorded_transcript_replay"
MARKET_OBSERVER_DETERMINISTIC_BACKEND_NAME = "deterministic_compiler"
PROMPT_TEMPLATE_VERSION = "market_observer_prompt_template_v1"
EXECUTION_ARTIFACT_ORDER = (
    "input",
    "prompt_context",
    "model_request",
    "raw_model_output",
    "model_transcript",
    "compiler_output",
    "parsed_draft",
    "quarantine",
)
REQUIRED_DRAFT_KEYS = {
    "input_id",
    "subject",
    "predicate",
    "value",
    "claim_type",
    "direction",
    "source_family",
    "evidence_level",
    "confidence_hint",
    "scope",
    "time_horizon",
}
ALLOWED_PREDICATES = {
    "agent_market_structure_support",
    "fresh_supportive_flow",
    "fresh_invalidation_risk",
    "headline_risk",
    "neutral_range_observation",
}
ALLOWED_CLAIM_TYPES = {
    "fact",
    "measurement",
    "flow",
    "market_structure",
    "causal",
    "predictive",
    "risk_flag",
    "invalidation",
}
ALLOWED_DIRECTIONS = {"bullish", "bearish", "neutral", "risk", "invalidating"}
ALLOWED_SOURCE_FAMILIES = {"infoflow", "cex", "onchain", "analytics", "safety", "official"}
ALLOWED_EVIDENCE_LEVELS = {"E1", "E2", "E3", "E4", "E5"}
ALLOWED_TIME_HORIZONS = {"intraday", "short", "medium", "structural"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _sha256_fragment(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    return " ".join(str(value).strip().split())


@dataclass(frozen=True, slots=True)
class MarketObservationInput:
    input_id: str
    object_id: str
    subject: str
    scope: str
    observation_text: str

    def to_spec_input_payload(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "object_id": self.object_id,
            "subject": self.subject,
            "scope": self.scope,
            "observation_text": self.observation_text,
        }

    def fingerprint(self) -> str:
        return _sha256_fragment(
            {
                "object_id": self.object_id,
                "subject": self.subject,
                "scope": self.scope,
                "observation_text": self.observation_text,
            }
        )


@dataclass(frozen=True, slots=True)
class MarketObserverExecutionResult:
    status: str
    candidate_draft: MarketObserverSignalDraft | None
    backend_kind: str
    backend_name: str
    input_path: str
    prompt_context_path: str
    model_request_path: str
    raw_model_output_path: str
    compiler_output_path: str
    transcript_path: str
    prompt_fingerprint: str
    transcript_fingerprint: str | None = None
    blocked_reason: str | None = None
    quarantine_reason: str | None = None
    parsed_draft_path: str | None = None
    quarantine_path: str | None = None
    reused: bool = False

    def compiler_artifact_paths(self) -> tuple[str, ...]:
        ordered = (
            self.input_path,
            self.prompt_context_path,
            self.model_request_path,
            self.raw_model_output_path,
            self.transcript_path,
            self.compiler_output_path,
            self.parsed_draft_path,
            self.quarantine_path,
        )
        return tuple(path for path in ordered if path)


@dataclass(frozen=True, slots=True)
class MarketObserverCompilerArtifacts:
    backend_kind: str
    backend_name: str
    prompt_context: dict[str, Any]
    model_request: dict[str, Any]
    raw_model_output: dict[str, Any]
    compiler_output: dict[str, Any]
    transcript_payload: dict[str, Any]

    @property
    def prompt_fingerprint(self) -> str:
        return str(self.prompt_context["prompt_fingerprint"])

    @property
    def transcript_fingerprint(self) -> str | None:
        value = self.transcript_payload.get("transcript_fingerprint")
        return None if value is None else str(value)


class MarketObserverCompilerBackend(Protocol):
    backend_kind: str
    backend_name: str

    def compile(
        self,
        *,
        observation: MarketObservationInput,
        prompt_context: dict[str, Any],
    ) -> MarketObserverCompilerArtifacts: ...


class MarketObserverLiveBackendConfigError(RuntimeError):
    pass


class MarketObserverCompilerTransportError(RuntimeError):
    pass


class MarketObserverTranscriptReplayError(RuntimeError):
    pass


class OpenAICompatibleMarketObserverBackend:
    backend_kind = "live"
    backend_name = MARKET_OBSERVER_LIVE_BACKEND_NAME

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        api_key: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.strip()
        self.model_name = model_name.strip()
        self.api_key = api_key.strip()
        self.timeout_seconds = float(timeout_seconds)
        if not self.base_url:
            raise MarketObserverLiveBackendConfigError("ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL must be set")
        if not self.model_name:
            raise MarketObserverLiveBackendConfigError("ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME must be set")
        if not self.api_key:
            raise MarketObserverLiveBackendConfigError("ENHENGCLAW_MARKET_OBSERVER_API_KEY must be set")

    @classmethod
    def from_env(cls) -> OpenAICompatibleMarketObserverBackend:
        base_url_name = "ENHENGCLAW_MARKET_OBSERVER_MODEL_BASE_URL"
        model_name_name = "ENHENGCLAW_MARKET_OBSERVER_MODEL_NAME"
        api_key_name = "ENHENGCLAW_MARKET_OBSERVER_API_KEY"
        timeout_name = "ENHENGCLAW_MARKET_OBSERVER_MODEL_TIMEOUT_SECONDS"
        base_url = str(getenv_compat(base_url_name, "") or "").strip()
        model_name = str(getenv_compat(model_name_name, "") or "").strip()
        api_key = str(getenv_compat(api_key_name, "") or "").strip()
        timeout_raw = str(getenv_compat(timeout_name, "30") or "").strip()
        missing = [
            name
            for name, value in (
                (base_url_name, base_url),
                (model_name_name, model_name),
                (api_key_name, api_key),
            )
            if not value
        ]
        if missing:
            raise MarketObserverLiveBackendConfigError(
                "market_observer live backend requires "
                + ", ".join(env_aliases_text(name) for name in missing)
                + " to be set; no deterministic fallback is applied on the public path"
            )
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise MarketObserverLiveBackendConfigError(
                f"{env_aliases_text(timeout_name)} must be numeric"
            ) from exc
        return cls(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    def compile(
        self,
        *,
        observation: MarketObservationInput,
        prompt_context: dict[str, Any],
    ) -> MarketObserverCompilerArtifacts:
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        request_body = {
            "model": self.model_name,
            "messages": prompt_context["messages"],
            "temperature": 0.0,
        }
        serialized = json.dumps(request_body).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=serialized,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        sanitized_request = {
            "endpoint": endpoint,
            "request_body": request_body,
            "request_headers": {
                "Authorization": "Bearer ***redacted***",
                "Content-Type": "application/json",
            },
            "timeout_seconds": self.timeout_seconds,
        }
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
                status_code = int(response.status)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise MarketObserverCompilerTransportError(
                f"market_observer live backend returned HTTP {exc.code}: {body[:400]}"
            ) from exc
        except error.URLError as exc:
            raise MarketObserverCompilerTransportError(
                f"market_observer live backend request failed: {exc.reason}"
            ) from exc
        response_json, parse_error = _try_parse_json(raw_body)
        assistant_text = _assistant_text_from_chat_completion(response_json) if response_json is not None else ""
        compiler_output = _normalize_compiler_envelope(
            assistant_text=assistant_text,
            raw_body=raw_body,
            parse_error=parse_error,
        )
        raw_model_output = {
            "status_code": status_code,
            "response_json": response_json,
            "response_text": raw_body,
            "assistant_text": assistant_text,
        }
        transcript = _build_transcript_payload(
            backend_kind=self.backend_kind,
            backend_name=self.backend_name,
            observation=observation,
            prompt_context=prompt_context,
            model_request=sanitized_request,
            raw_model_output=raw_model_output,
            compiler_output=compiler_output,
        )
        return MarketObserverCompilerArtifacts(
            backend_kind=self.backend_kind,
            backend_name=self.backend_name,
            prompt_context=prompt_context,
            model_request=sanitized_request,
            raw_model_output=raw_model_output,
            compiler_output=compiler_output,
            transcript_payload=transcript,
        )


class RecordedTranscriptMarketObserverBackend:
    backend_kind = "recorded"
    backend_name = MARKET_OBSERVER_RECORDED_BACKEND_NAME

    def __init__(self, *, transcript_path: str | Path) -> None:
        self.transcript_path = Path(transcript_path).resolve()

    def compile(
        self,
        *,
        observation: MarketObservationInput,
        prompt_context: dict[str, Any],
    ) -> MarketObserverCompilerArtifacts:
        payload = json.loads(self.transcript_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise MarketObserverTranscriptReplayError("recorded transcript must be a JSON object")
        if str(payload.get("contract_version", "")).strip() != MARKET_OBSERVER_COMPILER_CONTRACT_VERSION:
            raise MarketObserverTranscriptReplayError("recorded transcript contract_version mismatch")
        if str(payload.get("input_fingerprint", "")).strip() != observation.fingerprint():
            raise MarketObserverTranscriptReplayError("recorded transcript input_fingerprint mismatch")
        if str(payload.get("prompt_fingerprint", "")).strip() != str(prompt_context["prompt_fingerprint"]):
            raise MarketObserverTranscriptReplayError("recorded transcript prompt_fingerprint mismatch")
        stored_fingerprint = str(payload.get("transcript_fingerprint", "")).strip()
        if stored_fingerprint != _fingerprint_transcript_payload(payload):
            raise MarketObserverTranscriptReplayError("recorded transcript fingerprint mismatch")
        transcript = {**payload, "replayed_from": str(self.transcript_path)}
        return MarketObserverCompilerArtifacts(
            backend_kind=self.backend_kind,
            backend_name=self.backend_name,
            prompt_context=prompt_context,
            model_request=_require_dict(payload.get("model_request"), "model_request"),
            raw_model_output=_require_dict(payload.get("raw_model_output"), "raw_model_output"),
            compiler_output=_require_dict(payload.get("compiler_output"), "compiler_output"),
            transcript_payload=transcript,
        )


class DeterministicMarketObserverCompiler:
    backend_kind = "deterministic"
    backend_name = MARKET_OBSERVER_DETERMINISTIC_BACKEND_NAME

    _SUPPORTIVE_STRUCTURE_TOKENS = (
        "higher low",
        "support",
        "one of the stronger",
        "relative strength",
        "remains constructive",
        "still constructive",
    )

    def compile(
        self,
        *,
        observation: MarketObservationInput,
        prompt_context: dict[str, Any],
    ) -> MarketObserverCompilerArtifacts:
        lowered = observation.observation_text.lower()
        if "subject=btc" in lowered:
            compiler_output = {
                "status": "success",
                "blocked_reason": None,
                "candidate_payloads": [
                    {
                        "input_id": observation.input_id,
                        "subject": "BTC",
                        "predicate": "agent_market_structure_support",
                        "value": (
                            "facts=subject=BTC supportive structure with higher low above support; "
                            "interpretation=structure still leans constructive; "
                            "uncertainty=host subject alignment must be rechecked"
                        ),
                        "claim_type": "market_structure",
                        "direction": "bullish",
                        "source_family": "analytics",
                        "evidence_level": "E4",
                        "confidence_hint": 72,
                        "scope": observation.scope,
                        "time_horizon": "intraday",
                    }
                ],
                "notes": ["deterministic compiler emitted one candidate payload"],
            }
        elif "higher low" in lowered and "support" in lowered:
            compiler_output = {
                "status": "success",
                "blocked_reason": None,
                "candidate_payloads": [
                    {
                        "input_id": observation.input_id,
                        "subject": observation.subject,
                        "predicate": "agent_market_structure_support",
                        "value": (
                            "facts=higher low remains above support and no immediate breakdown is visible; "
                            "interpretation=market structure still looks locally supportive; "
                            "uncertainty=confirmation still depends on follow-through and no fresh invalidation"
                        ),
                        "claim_type": "market_structure",
                        "direction": "bullish",
                        "source_family": "analytics",
                        "evidence_level": "E4",
                        "confidence_hint": 74,
                        "scope": observation.scope,
                        "time_horizon": "intraday",
                    }
                ],
                "notes": ["deterministic compiler matched supportive structure pattern"],
            }
        elif any(token in lowered for token in self._SUPPORTIVE_STRUCTURE_TOKENS):
            uncertainty = (
                "confirmation still depends on follow-through and whether catalyst-sensitive volatility stays contained"
                if any(token in lowered for token in ("volatile", "volatility", "catalyst-sensitive"))
                else "confirmation still depends on follow-through and no fresh invalidation"
            )
            compiler_output = {
                "status": "success",
                "blocked_reason": None,
                "candidate_payloads": [
                    {
                        "input_id": observation.input_id,
                        "subject": observation.subject,
                        "predicate": "agent_market_structure_support",
                        "value": (
                            "facts=the observation still describes a relatively stronger and constructive structure; "
                            "interpretation=market structure remains supportive enough for bounded follow-up; "
                            f"uncertainty={uncertainty}"
                        ),
                        "claim_type": "market_structure",
                        "direction": "bullish",
                        "source_family": "analytics",
                        "evidence_level": "E4",
                        "confidence_hint": 70,
                        "scope": observation.scope,
                        "time_horizon": "short",
                    }
                ],
                "notes": ["deterministic compiler matched bounded constructive structure phrasing"],
            }
        else:
            compiler_output = {
                "status": "blocked",
                "blocked_reason": "deterministic compiler could not map the observation to a stable supported predicate",
                "candidate_payloads": [],
                "notes": ["deterministic compiler failed closed"],
            }
        assistant_text = json.dumps(compiler_output, sort_keys=True)
        raw_model_output = {
            "status_code": 200,
            "response_json": {"kind": "deterministic", "compiler_output": compiler_output},
            "response_text": assistant_text,
            "assistant_text": assistant_text,
        }
        model_request = {
            "endpoint": "deterministic://market_observer",
            "request_body": {
                "observation_text": observation.observation_text,
                "subject": observation.subject,
                "scope": observation.scope,
            },
            "request_headers": {},
            "timeout_seconds": 0.0,
        }
        transcript = _build_transcript_payload(
            backend_kind=self.backend_kind,
            backend_name=self.backend_name,
            observation=observation,
            prompt_context=prompt_context,
            model_request=model_request,
            raw_model_output=raw_model_output,
            compiler_output=compiler_output,
        )
        return MarketObserverCompilerArtifacts(
            backend_kind=self.backend_kind,
            backend_name=self.backend_name,
            prompt_context=prompt_context,
            model_request=model_request,
            raw_model_output=raw_model_output,
            compiler_output=compiler_output,
            transcript_payload=transcript,
        )


class MarketObserverExecutionPipeline:
    def __init__(
        self,
        *,
        artifact_store: OwnerArtifactWriter | None = None,
        compiler_backend: MarketObserverCompilerBackend | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        self.artifact_store = artifact_store or OwnerArtifactWriter()
        self.compiler_backend = compiler_backend or DeterministicMarketObserverCompiler()
        self.prompt_path = Path(prompt_path) if prompt_path is not None else DEFAULT_PROMPT_PATH

    def execute(self, observation: MarketObservationInput) -> MarketObserverExecutionResult:
        run_id = build_owner_run_id(requested_delegate_id="market_observer", object_id=observation.object_id)
        prompt_context = self._build_prompt_context(observation)
        reused = self._reuse_existing_result(run_id=run_id, observation=observation, prompt_context=prompt_context)
        if reused is not None:
            return reused

        compilation = self.compiler_backend.compile(observation=observation, prompt_context=prompt_context)
        input_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="input",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload={"input_fingerprint": observation.fingerprint(), "payload": observation.to_spec_input_payload()},
        )
        prompt_context_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="prompt_context",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.prompt_context,
        )
        model_request_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="model_request",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.model_request,
        )
        raw_model_output_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="raw_model_output",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.raw_model_output,
        )
        transcript_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="model_transcript",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.transcript_payload,
        )
        compiler_output_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="compiler_output",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.compiler_output,
        )

        compiler_output = compilation.compiler_output
        if str(compiler_output.get("status", "")).strip().lower() == "blocked":
            return MarketObserverExecutionResult(
                status="blocked",
                candidate_draft=None,
                backend_kind=compilation.backend_kind,
                backend_name=compilation.backend_name,
                input_path=str(input_path),
                prompt_context_path=str(prompt_context_path),
                model_request_path=str(model_request_path),
                raw_model_output_path=str(raw_model_output_path),
                compiler_output_path=str(compiler_output_path),
                transcript_path=str(transcript_path),
                prompt_fingerprint=compilation.prompt_fingerprint,
                transcript_fingerprint=compilation.transcript_fingerprint,
                blocked_reason=str(compiler_output.get("blocked_reason", "")).strip() or "compiler_blocked",
            )

        candidate_payloads = compiler_output.get("candidate_payloads", [])
        if not isinstance(candidate_payloads, list) or len(candidate_payloads) != 1:
            blocked_output = {
                "status": "blocked",
                "blocked_reason": "compiler must emit exactly one candidate payload when status=success",
                "candidate_payloads": [],
                "notes": list(compiler_output.get("notes", [])) + ["local validator rejected malformed success envelope"],
            }
            compiler_output_path = self._write_execution_artifact(
                run_id=run_id,
                artifact_name="compiler_output",
                backend_kind=compilation.backend_kind,
                backend_name=compilation.backend_name,
                prompt_fingerprint=compilation.prompt_fingerprint,
                transcript_fingerprint=compilation.transcript_fingerprint,
                payload=blocked_output,
            )
            return MarketObserverExecutionResult(
                status="blocked",
                candidate_draft=None,
                backend_kind=compilation.backend_kind,
                backend_name=compilation.backend_name,
                input_path=str(input_path),
                prompt_context_path=str(prompt_context_path),
                model_request_path=str(model_request_path),
                raw_model_output_path=str(raw_model_output_path),
                compiler_output_path=str(compiler_output_path),
                transcript_path=str(transcript_path),
                prompt_fingerprint=compilation.prompt_fingerprint,
                transcript_fingerprint=compilation.transcript_fingerprint,
                blocked_reason="compiler must emit exactly one candidate payload when status=success",
            )

        candidate_payload = candidate_payloads[0]
        quarantine_reason = self._candidate_quarantine_reason(observation=observation, candidate_payload=candidate_payload)
        if quarantine_reason is not None:
            quarantine_path = self._write_execution_artifact(
                run_id=run_id,
                artifact_name="quarantine",
                backend_kind=compilation.backend_kind,
                backend_name=compilation.backend_name,
                prompt_fingerprint=compilation.prompt_fingerprint,
                transcript_fingerprint=compilation.transcript_fingerprint,
                payload={"reason": quarantine_reason, "candidate_payload": candidate_payload},
            )
            return MarketObserverExecutionResult(
                status="quarantine",
                candidate_draft=None,
                backend_kind=compilation.backend_kind,
                backend_name=compilation.backend_name,
                input_path=str(input_path),
                prompt_context_path=str(prompt_context_path),
                model_request_path=str(model_request_path),
                raw_model_output_path=str(raw_model_output_path),
                compiler_output_path=str(compiler_output_path),
                transcript_path=str(transcript_path),
                prompt_fingerprint=compilation.prompt_fingerprint,
                transcript_fingerprint=compilation.transcript_fingerprint,
                quarantine_reason=quarantine_reason,
                quarantine_path=str(quarantine_path),
            )

        draft = MarketObserverSignalDraft(**candidate_payload)
        parsed_draft_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="parsed_draft",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload={"candidate_payload": draft.to_agent_payload()},
        )
        return MarketObserverExecutionResult(
            status="success",
            candidate_draft=draft,
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            input_path=str(input_path),
            prompt_context_path=str(prompt_context_path),
            model_request_path=str(model_request_path),
            raw_model_output_path=str(raw_model_output_path),
            compiler_output_path=str(compiler_output_path),
            transcript_path=str(transcript_path),
            prompt_fingerprint=compilation.prompt_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            parsed_draft_path=str(parsed_draft_path),
        )

    def restamp_execution_artifacts(self, *, run_id: str, step_id: str, spec_version: int) -> tuple[str, ...]:
        ordered_paths: list[str] = []
        for artifact_name in EXECUTION_ARTIFACT_ORDER:
            payload = self.artifact_store.load_execution_artifact(run_id, artifact_name)
            if payload is None:
                continue
            payload["run_id"] = run_id
            payload["step_id"] = step_id
            payload["spec_version"] = spec_version
            payload["timestamp"] = _utc_now()
            artifact_path = self.artifact_store.write_execution_artifact(run_id, artifact_name, payload)
            ordered_paths.append(str(artifact_path))
        return tuple(ordered_paths)

    def _build_prompt_context(self, observation: MarketObservationInput) -> dict[str, Any]:
        system_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        user_prompt = (
            "Compile one bounded market observation into exactly one JSON compiler envelope.\n"
            f"host_subject={observation.subject}\n"
            f"host_scope={observation.scope}\n"
            f"input_id={observation.input_id}\n"
            f"object_id={observation.object_id}\n"
            "observation_text:\n"
            f"{observation.observation_text.strip()}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prompt_fingerprint = _sha256_fragment(
            {
                "contract_version": MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "messages": messages,
            }
        )
        return {
            "contract_version": MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
            "prompt_template_version": PROMPT_TEMPLATE_VERSION,
            "system_prompt_path": str(self.prompt_path.resolve()),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "messages": messages,
            "prompt_fingerprint": prompt_fingerprint,
        }

    def _reuse_existing_result(
        self,
        *,
        run_id: str,
        observation: MarketObservationInput,
        prompt_context: dict[str, Any],
    ) -> MarketObserverExecutionResult | None:
        input_payload = self.artifact_store.load_execution_artifact(run_id, "input")
        prompt_payload = self.artifact_store.load_execution_artifact(run_id, "prompt_context")
        compiler_payload = self.artifact_store.load_execution_artifact(run_id, "compiler_output")
        model_request_payload = self.artifact_store.load_execution_artifact(run_id, "model_request")
        raw_output_payload = self.artifact_store.load_execution_artifact(run_id, "raw_model_output")
        transcript_payload = self.artifact_store.load_execution_artifact(run_id, "model_transcript")
        if None in (input_payload, prompt_payload, compiler_payload, model_request_payload, raw_output_payload, transcript_payload):
            return None
        if str(input_payload.get("backend_kind", "")) != str(getattr(self.compiler_backend, "backend_kind", "")):
            return None
        if str(input_payload.get("backend_name", "")) != str(getattr(self.compiler_backend, "backend_name", "")):
            return None
        if str(input_payload.get("prompt_fingerprint", "")) != str(prompt_context["prompt_fingerprint"]):
            return None
        input_body = _require_dict(input_payload.get("payload"), "input.payload")
        if str(input_body.get("input_fingerprint", "")) != observation.fingerprint():
            return None

        parsed_draft_payload = self.artifact_store.load_execution_artifact(run_id, "parsed_draft")
        quarantine_payload = self.artifact_store.load_execution_artifact(run_id, "quarantine")
        compiler_body = _require_dict(compiler_payload.get("payload"), "compiler_output.payload")
        base_kwargs = {
            "backend_kind": str(input_payload["backend_kind"]),
            "backend_name": str(input_payload["backend_name"]),
            "input_path": str(input_payload["artifact_path"]),
            "prompt_context_path": str(prompt_payload["artifact_path"]),
            "model_request_path": str(model_request_payload["artifact_path"]),
            "raw_model_output_path": str(raw_output_payload["artifact_path"]),
            "compiler_output_path": str(compiler_payload["artifact_path"]),
            "transcript_path": str(transcript_payload["artifact_path"]),
            "prompt_fingerprint": str(input_payload.get("prompt_fingerprint", "")),
            "transcript_fingerprint": str(input_payload.get("transcript_fingerprint", "")) or None,
            "reused": True,
        }
        if parsed_draft_payload is not None:
            draft_payload = _require_dict(parsed_draft_payload.get("payload"), "parsed_draft.payload").get("candidate_payload")
            if not isinstance(draft_payload, dict):
                return None
            return MarketObserverExecutionResult(
                status="success",
                candidate_draft=MarketObserverSignalDraft(**draft_payload),
                parsed_draft_path=str(parsed_draft_payload["artifact_path"]),
                **base_kwargs,
            )
        if quarantine_payload is not None:
            quarantine_body = _require_dict(quarantine_payload.get("payload"), "quarantine.payload")
            return MarketObserverExecutionResult(
                status="quarantine",
                candidate_draft=None,
                quarantine_reason=str(quarantine_body.get("reason", "")).strip() or "candidate_payload_quarantined",
                quarantine_path=str(quarantine_payload["artifact_path"]),
                **base_kwargs,
            )
        return MarketObserverExecutionResult(
            status="blocked",
            candidate_draft=None,
            blocked_reason=str(compiler_body.get("blocked_reason", "")).strip() or "compiler_blocked",
            **base_kwargs,
        )

    def _candidate_quarantine_reason(
        self,
        *,
        observation: MarketObservationInput,
        candidate_payload: Any,
    ) -> str | None:
        if not isinstance(candidate_payload, dict):
            return "candidate_payload_is_not_a_json_object"
        if set(candidate_payload) != REQUIRED_DRAFT_KEYS:
            return "candidate_payload_keys_do_not_match_schema"
        if str(candidate_payload.get("subject", "")).strip() != observation.subject:
            return "candidate_payload_subject_mismatches_host_context"
        if str(candidate_payload.get("scope", "")).strip() != observation.scope:
            return "candidate_payload_scope_mismatches_host_context"
        if str(candidate_payload.get("predicate", "")).strip() not in ALLOWED_PREDICATES:
            return "candidate_payload_predicate_outside_supported_closed_set"
        if str(candidate_payload.get("claim_type", "")).strip() not in ALLOWED_CLAIM_TYPES:
            return "candidate_payload_claim_type_invalid"
        if str(candidate_payload.get("direction", "")).strip() not in ALLOWED_DIRECTIONS:
            return "candidate_payload_direction_invalid"
        if str(candidate_payload.get("source_family", "")).strip() not in ALLOWED_SOURCE_FAMILIES:
            return "candidate_payload_source_family_invalid"
        if str(candidate_payload.get("evidence_level", "")).strip() not in ALLOWED_EVIDENCE_LEVELS:
            return "candidate_payload_evidence_level_invalid"
        if str(candidate_payload.get("time_horizon", "")).strip() not in ALLOWED_TIME_HORIZONS:
            return "candidate_payload_time_horizon_invalid"
        try:
            confidence_hint = int(candidate_payload.get("confidence_hint"))
        except (TypeError, ValueError):
            return "candidate_payload_confidence_not_integer"
        if not 60 <= confidence_hint <= 100:
            return "candidate_payload_confidence_outside_allowed_range"
        value = _normalize_text(str(candidate_payload.get("value", "")))
        if not value:
            return "candidate_payload_value_missing"
        lowered_value = value.lower()
        if "facts=" not in lowered_value or "interpretation=" not in lowered_value or "uncertainty=" not in lowered_value:
            return "candidate_payload_value_missing_required_sections"
        return None

    def _write_execution_artifact(
        self,
        *,
        run_id: str,
        artifact_name: str,
        backend_kind: str,
        backend_name: str,
        prompt_fingerprint: str,
        transcript_fingerprint: str | None,
        payload: dict[str, Any],
    ) -> Path:
        return self.artifact_store.write_execution_artifact(
            run_id,
            artifact_name,
            {
                "run_id": run_id,
                "step_id": "",
                "spec_version": 0,
                "timestamp": _utc_now(),
                "provenance": "market_observer_execution",
                "artifact_name": artifact_name,
                "backend_kind": backend_kind,
                "backend_name": backend_name,
                "contract_version": MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
                "prompt_fingerprint": prompt_fingerprint,
                "transcript_fingerprint": transcript_fingerprint,
                "payload": payload,
            },
        )


def _try_parse_json(raw_text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "top-level response must be a JSON object"
    return payload, None


def _assistant_text_from_chat_completion(response_json: dict[str, Any] | None) -> str:
    if not isinstance(response_json, dict):
        return ""
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _normalize_compiler_envelope(
    *,
    assistant_text: str,
    raw_body: str,
    parse_error: str | None,
) -> dict[str, Any]:
    if parse_error is not None and not assistant_text:
        return {
            "status": "blocked",
            "blocked_reason": "model_response_json_invalid",
            "candidate_payloads": [],
            "notes": [parse_error],
        }
    if not assistant_text:
        return {
            "status": "blocked",
            "blocked_reason": "model_response_missing_assistant_content",
            "candidate_payloads": [],
            "notes": ["assistant content missing from chat completion response"],
        }
    assistant_payload, assistant_parse_error = _try_parse_json(assistant_text)
    if assistant_parse_error is not None:
        return {
            "status": "blocked",
            "blocked_reason": "model_output_not_valid_json_envelope",
            "candidate_payloads": [],
            "notes": [assistant_parse_error, raw_body[:400]],
        }
    status = str(assistant_payload.get("status", "")).strip().lower()
    blocked_reason = assistant_payload.get("blocked_reason")
    candidate_payloads = assistant_payload.get("candidate_payloads", [])
    notes = assistant_payload.get("notes", [])
    if not isinstance(candidate_payloads, list):
        candidate_payloads = []
    if not isinstance(notes, list):
        notes = [str(notes)]
    normalized_notes = [str(item) for item in notes if str(item).strip()]
    if status not in {"success", "blocked"}:
        return {
            "status": "blocked",
            "blocked_reason": "model_output_status_invalid",
            "candidate_payloads": [],
            "notes": normalized_notes or ["status must be 'success' or 'blocked'"],
        }
    if status == "blocked":
        reason_text = str(blocked_reason).strip() if blocked_reason is not None else ""
        return {
            "status": "blocked",
            "blocked_reason": reason_text or "model_blocked_without_reason",
            "candidate_payloads": [],
            "notes": normalized_notes,
        }
    if len(candidate_payloads) != 1:
        return {
            "status": "blocked",
            "blocked_reason": "model_must_emit_exactly_one_candidate_payload",
            "candidate_payloads": [],
            "notes": normalized_notes,
        }
    if not isinstance(candidate_payloads[0], dict):
        return {
            "status": "blocked",
            "blocked_reason": "model_candidate_payload_must_be_json_object",
            "candidate_payloads": [],
            "notes": normalized_notes,
        }
    return {
        "status": "success",
        "blocked_reason": None,
        "candidate_payloads": [candidate_payloads[0]],
        "notes": normalized_notes,
    }


def _build_transcript_payload(
    *,
    backend_kind: str,
    backend_name: str,
    observation: MarketObservationInput,
    prompt_context: dict[str, Any],
    model_request: dict[str, Any],
    raw_model_output: dict[str, Any],
    compiler_output: dict[str, Any],
) -> dict[str, Any]:
    transcript = {
        "contract_version": MARKET_OBSERVER_COMPILER_CONTRACT_VERSION,
        "backend_kind": backend_kind,
        "backend_name": backend_name,
        "input_fingerprint": observation.fingerprint(),
        "prompt_fingerprint": str(prompt_context["prompt_fingerprint"]),
        "prompt_context": {
            "prompt_template_version": str(prompt_context["prompt_template_version"]),
            "system_prompt_path": str(prompt_context["system_prompt_path"]),
            "system_prompt": str(prompt_context["system_prompt"]),
            "user_prompt": str(prompt_context["user_prompt"]),
            "messages": prompt_context["messages"],
        },
        "model_request": model_request,
        "raw_model_output": raw_model_output,
        "compiler_output": compiler_output,
    }
    transcript["transcript_fingerprint"] = _fingerprint_transcript_payload(transcript)
    return transcript


def _fingerprint_transcript_payload(payload: dict[str, Any]) -> str:
    serializable = {key: value for key, value in payload.items() if key != "transcript_fingerprint"}
    return _sha256_fragment(serializable)


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MarketObserverTranscriptReplayError(f"{label} must be a JSON object")
    return value
