from __future__ import annotations

import hashlib
import json
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib import error, request

from enhengclaw.compat.naming import env_aliases_text, getenv_compat


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sha256_fragment(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().split())


@dataclass(frozen=True, slots=True)
class SliceCompilerArtifacts:
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
    def object_context_fingerprint(self) -> str | None:
        value = self.prompt_context.get("object_context_fingerprint")
        return None if value is None else str(value)

    @property
    def transcript_fingerprint(self) -> str | None:
        value = self.transcript_payload.get("transcript_fingerprint")
        return None if value is None else str(value)


class SliceLiveBackendConfigError(RuntimeError):
    pass


class SliceCompilerTransportError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class SliceTranscriptReplayError(RuntimeError):
    pass


class SliceObjectContextError(RuntimeError):
    pass


def parse_timeout_from_env(env_name: str, *, default: str = "30") -> float:
    timeout_raw = str(getenv_compat(env_name, default) or "").strip()
    try:
        return float(timeout_raw)
    except ValueError as exc:
        raise SliceLiveBackendConfigError(f"{env_aliases_text(env_name)} must be numeric") from exc


def require_env_values(*names: str, failure_label: str) -> dict[str, str]:
    values = {name: str(getenv_compat(name, "") or "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SliceLiveBackendConfigError(
            f"{failure_label} requires "
            + ", ".join(env_aliases_text(name) for name in missing)
            + " to be set; no fallback is applied on the public path"
        )
    return values


def _build_openai_request_body(
    *,
    model_name: str,
    messages: list[dict[str, str]],
    response_format: dict[str, Any] | None,
    max_completion_tokens: int | None,
) -> dict[str, Any]:
    request_body: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.0,
    }
    if response_format:
        request_body["response_format"] = dict(response_format)
    if max_completion_tokens is not None:
        request_body["max_completion_tokens"] = int(max_completion_tokens)
    return request_body


def _sanitize_openai_request(
    *,
    endpoint: str,
    request_body: dict[str, Any],
    timeout_seconds: float,
    retry_count: int,
    fallback_without_response_format: bool,
    request_metadata: dict[str, Any] | None,
    latency_ms: int,
) -> dict[str, Any]:
    payload = {
        "endpoint": endpoint,
        "request_body": request_body,
        "request_headers": {
            "Authorization": "Bearer ***redacted***",
            "Content-Type": "application/json",
        },
        "timeout_seconds": timeout_seconds,
        "request_body_chars": len(json.dumps(request_body)),
        "retry_count": int(retry_count),
        "fallback_without_response_format": bool(fallback_without_response_format),
        "latency_ms": int(latency_ms),
    }
    if request_metadata:
        payload["request_metadata"] = dict(request_metadata)
    return payload


def _response_format_unsupported(*, status_code: int, body: str) -> bool:
    if int(status_code) != 400:
        return False
    lowered = str(body or "").lower()
    return "response_format" in lowered and any(
        marker in lowered
        for marker in (
            "unsupported",
            "not supported",
            "is not supported",
            "unknown parameter",
            "invalid",
            "unrecognized",
        )
    )


def openai_compatible_compile(
    *,
    base_url: str,
    model_name: str,
    api_key: str,
    timeout_seconds: float,
    backend_kind: str,
    backend_name: str,
    contract_version: str,
    failure_label: str,
    observation_fingerprint: str,
    prompt_context: dict[str, Any],
    response_format: dict[str, Any] | None = None,
    max_completion_tokens: int | None = None,
    request_metadata: dict[str, Any] | None = None,
    allow_retry_without_response_format: bool = False,
) -> SliceCompilerArtifacts:
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    retry_count = 0
    fallback_without_response_format = False
    current_response_format = dict(response_format or {}) or None
    request_body = _build_openai_request_body(
        model_name=model_name,
        messages=prompt_context["messages"],
        response_format=current_response_format,
        max_completion_tokens=max_completion_tokens,
    )
    start_time = perf_counter()
    while True:
        serialized = json.dumps(request_body).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=serialized,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
                status_code = int(response.status)
                break
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if (
                current_response_format
                and allow_retry_without_response_format
                and not fallback_without_response_format
                and _response_format_unsupported(status_code=int(exc.code), body=body)
            ):
                retry_count += 1
                fallback_without_response_format = True
                current_response_format = None
                request_body = _build_openai_request_body(
                    model_name=model_name,
                    messages=prompt_context["messages"],
                    response_format=None,
                    max_completion_tokens=max_completion_tokens,
                )
                continue
            latency_ms = round((perf_counter() - start_time) * 1000)
            raise SliceCompilerTransportError(
                f"{failure_label} returned HTTP {exc.code}: {body[:400]}",
                details=_sanitize_openai_request(
                    endpoint=endpoint,
                    request_body=request_body,
                    timeout_seconds=timeout_seconds,
                    retry_count=retry_count,
                    fallback_without_response_format=fallback_without_response_format,
                    request_metadata=request_metadata,
                    latency_ms=latency_ms,
                ),
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            latency_ms = round((perf_counter() - start_time) * 1000)
            raise SliceCompilerTransportError(
                f"{failure_label} request timed out: {exc}",
                details=_sanitize_openai_request(
                    endpoint=endpoint,
                    request_body=request_body,
                    timeout_seconds=timeout_seconds,
                    retry_count=retry_count,
                    fallback_without_response_format=fallback_without_response_format,
                    request_metadata=request_metadata,
                    latency_ms=latency_ms,
                ),
            ) from exc
        except error.URLError as exc:
            latency_ms = round((perf_counter() - start_time) * 1000)
            raise SliceCompilerTransportError(
                f"{failure_label} request failed: {exc.reason}",
                details=_sanitize_openai_request(
                    endpoint=endpoint,
                    request_body=request_body,
                    timeout_seconds=timeout_seconds,
                    retry_count=retry_count,
                    fallback_without_response_format=fallback_without_response_format,
                    request_metadata=request_metadata,
                    latency_ms=latency_ms,
                ),
            ) from exc

    latency_ms = round((perf_counter() - start_time) * 1000)
    sanitized_request = _sanitize_openai_request(
        endpoint=endpoint,
        request_body=request_body,
        timeout_seconds=timeout_seconds,
        retry_count=retry_count,
        fallback_without_response_format=fallback_without_response_format,
        request_metadata=request_metadata,
        latency_ms=latency_ms,
    )

    response_json, parse_error = try_parse_json(raw_body)
    assistant_text = assistant_text_from_chat_completion(response_json) if response_json is not None else ""
    compiler_output = normalize_compiler_envelope(
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
    transcript = build_transcript_payload(
        backend_kind=backend_kind,
        backend_name=backend_name,
        contract_version=contract_version,
        input_fingerprint=observation_fingerprint,
        prompt_context=prompt_context,
        model_request=sanitized_request,
        raw_model_output=raw_model_output,
        compiler_output=compiler_output,
    )
    return SliceCompilerArtifacts(
        backend_kind=backend_kind,
        backend_name=backend_name,
        prompt_context=prompt_context,
        model_request=sanitized_request,
        raw_model_output=raw_model_output,
        compiler_output=compiler_output,
        transcript_payload=transcript,
    )


def load_recorded_transcript(
    *,
    transcript_path: str | Path,
    contract_version: str,
    input_fingerprint: str,
    prompt_context: dict[str, Any],
    failure_label: str,
) -> SliceCompilerArtifacts:
    resolved = Path(transcript_path).resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SliceTranscriptReplayError("recorded transcript must be a JSON object")
    if str(payload.get("contract_version", "")).strip() != contract_version:
        raise SliceTranscriptReplayError("recorded transcript contract_version mismatch")
    if str(payload.get("input_fingerprint", "")).strip() != input_fingerprint:
        raise SliceTranscriptReplayError("recorded transcript input_fingerprint mismatch")
    if str(payload.get("prompt_fingerprint", "")).strip() != str(prompt_context["prompt_fingerprint"]):
        raise SliceTranscriptReplayError("recorded transcript prompt_fingerprint mismatch")
    expected_object_fingerprint = prompt_context.get("object_context_fingerprint")
    recorded_object_fingerprint = payload.get("object_context_fingerprint")
    if expected_object_fingerprint is not None and str(recorded_object_fingerprint or "").strip() != str(
        expected_object_fingerprint
    ):
        raise SliceTranscriptReplayError("recorded transcript object_context_fingerprint mismatch")
    contract_payload = dict(payload)
    if str(contract_payload.get("transcript_fingerprint", "")).strip() != fingerprint_transcript_payload(contract_payload):
        raise SliceTranscriptReplayError("recorded transcript fingerprint mismatch")
    contract_payload["replayed_from"] = str(resolved)
    return SliceCompilerArtifacts(
        backend_kind="recorded",
        backend_name=str(payload.get("backend_name", failure_label)),
        prompt_context=prompt_context,
        model_request=require_dict(payload.get("model_request"), "model_request"),
        raw_model_output=require_dict(payload.get("raw_model_output"), "raw_model_output"),
        compiler_output=require_dict(payload.get("compiler_output"), "compiler_output"),
        transcript_payload=contract_payload,
    )


def build_deterministic_compiler_artifacts(
    *,
    backend_name: str,
    contract_version: str,
    input_fingerprint: str,
    prompt_context: dict[str, Any],
    compiler_output: dict[str, Any],
) -> SliceCompilerArtifacts:
    assistant_text = json.dumps(compiler_output, sort_keys=True)
    raw_model_output = {
        "status_code": 200,
        "response_json": {"kind": "deterministic", "compiler_output": compiler_output},
        "response_text": assistant_text,
        "assistant_text": assistant_text,
    }
    model_request = {
        "endpoint": "deterministic://local-compiler",
        "request_body": {"messages": prompt_context["messages"]},
        "request_headers": {},
        "timeout_seconds": 0.0,
    }
    transcript = build_transcript_payload(
        backend_kind="deterministic",
        backend_name=backend_name,
        contract_version=contract_version,
        input_fingerprint=input_fingerprint,
        prompt_context=prompt_context,
        model_request=model_request,
        raw_model_output=raw_model_output,
        compiler_output=compiler_output,
    )
    return SliceCompilerArtifacts(
        backend_kind="deterministic",
        backend_name=backend_name,
        prompt_context=prompt_context,
        model_request=model_request,
        raw_model_output=raw_model_output,
        compiler_output=compiler_output,
        transcript_payload=transcript,
    )


def try_parse_json(raw_text: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}@{exc.lineno}:{exc.colno}"
    if not isinstance(payload, dict):
        return None, "json_root_must_be_object"
    return payload, None


def _markdown_fence_json_candidates(raw_text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"```(?:[A-Za-z0-9_-]+)?\s*([\s\S]*?)```", raw_text, flags=re.IGNORECASE):
        candidate = str(match.group(1) or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    return candidates


def try_parse_assistant_json(raw_text: str) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    payload, parse_error = try_parse_json(raw_text)
    if parse_error is None:
        return payload, None, []
    for candidate in _markdown_fence_json_candidates(raw_text):
        payload, candidate_error = try_parse_json(candidate)
        if candidate_error is None:
            return payload, None, ["assistant_content_markdown_fence_stripped"]
    return None, parse_error, []


def assistant_text_from_chat_completion(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message", {})
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    return "" if content is None else str(content).strip()


def normalize_compiler_envelope(
    *,
    assistant_text: str,
    raw_body: str,
    parse_error: str | None,
) -> dict[str, Any]:
    if parse_error is not None:
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
    assistant_payload, assistant_parse_error, parse_recovery_notes = try_parse_assistant_json(assistant_text)
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
    normalized_notes = parse_recovery_notes + [str(item) for item in notes if str(item).strip()]
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


def build_transcript_payload(
    *,
    backend_kind: str,
    backend_name: str,
    contract_version: str,
    input_fingerprint: str,
    prompt_context: dict[str, Any],
    model_request: dict[str, Any],
    raw_model_output: dict[str, Any],
    compiler_output: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "contract_version": contract_version,
        "backend_kind": backend_kind,
        "backend_name": backend_name,
        "input_fingerprint": input_fingerprint,
        "prompt_fingerprint": prompt_context["prompt_fingerprint"],
        "object_context_fingerprint": prompt_context.get("object_context_fingerprint"),
        "prompt_context": prompt_context,
        "model_request": model_request,
        "raw_model_output": raw_model_output,
        "compiler_output": compiler_output,
    }
    payload["transcript_fingerprint"] = fingerprint_transcript_payload(payload)
    return payload


def fingerprint_transcript_payload(payload: dict[str, Any]) -> str:
    material = {
        key: value
        for key, value in payload.items()
        if key not in {"transcript_fingerprint", "replayed_from"}
    }
    return sha256_fragment(material)


def require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SliceTranscriptReplayError(f"{name} must be a JSON object")
    return dict(value)
