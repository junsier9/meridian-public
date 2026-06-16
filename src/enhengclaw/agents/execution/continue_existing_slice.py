from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from enhengclaw.compat.naming import env_aliases_text, getenv_compat
from enhengclaw.agents.execution._shared import (
    SliceCompilerArtifacts,
    SliceCompilerTransportError,
    SliceLiveBackendConfigError,
    SliceObjectContextError,
    SliceTranscriptReplayError,
    build_deterministic_compiler_artifacts,
    normalize_text,
    openai_compatible_compile,
    load_recorded_transcript,
    sha256_fragment,
    utc_now,
)
from enhengclaw.agents.execution.context_views import ExistingObjectExecutionContext
from enhengclaw.agents.owner_state import OwnerArtifactWriter, build_owner_run_id


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


class ContinueExistingObservation(Protocol):
    input_id: str
    object_id: str
    subject: str
    scope: str

    def to_spec_input_payload(self) -> dict[str, Any]: ...

    def fingerprint(self) -> str: ...

    def text_value(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ContinueExistingSliceExecutionResult:
    status: str
    candidate_draft: Any | None
    backend_kind: str
    backend_name: str
    input_path: str
    prompt_context_path: str
    model_request_path: str
    raw_model_output_path: str
    compiler_output_path: str
    transcript_path: str
    prompt_fingerprint: str
    object_context_fingerprint: str
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


class ContinueExistingCompilerBackend(Protocol):
    backend_kind: str
    backend_name: str

    def compile(
        self,
        *,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
        prompt_context: dict[str, Any],
    ) -> SliceCompilerArtifacts: ...


@dataclass(frozen=True, slots=True)
class ContinueExistingSliceSpec:
    slice_id: str
    contract_version: str
    prompt_template_version: str
    prompt_path: Path
    input_text_label: str
    success_prompt_line: str
    live_backend_name: str
    recorded_backend_name: str
    deterministic_backend_name: str
    env_prefix: str
    draft_cls: type[Any]
    allowed_predicates: frozenset[str]
    allowed_claim_types: frozenset[str]
    allowed_directions: frozenset[str]
    allowed_source_families: frozenset[str]
    allowed_evidence_levels: frozenset[str]
    allowed_time_horizons: frozenset[str]
    build_object_context: Callable[..., ExistingObjectExecutionContext]
    deterministic_compile: Callable[[ContinueExistingObservation, ExistingObjectExecutionContext], dict[str, Any]]
    required_value_segments: tuple[str, ...] = ()


class OpenAICompatibleContinueExistingSliceBackend:
    backend_kind = "live"

    def __init__(
        self,
        *,
        spec: ContinueExistingSliceSpec,
        base_url: str,
        model_name: str,
        api_key: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.spec = spec
        self.backend_name = spec.live_backend_name
        self.base_url = base_url.strip()
        self.model_name = model_name.strip()
        self.api_key = api_key.strip()
        self.timeout_seconds = float(timeout_seconds)
        missing = []
        if not self.base_url:
            missing.append(f"{spec.env_prefix}_BASE_URL")
        if not self.model_name:
            missing.append(f"{spec.env_prefix}_NAME")
        if not self.api_key:
            missing.append(f"{spec.env_prefix}_API_KEY")
        if missing:
            raise SliceLiveBackendConfigError(
                f"{spec.slice_id} live backend requires " + ", ".join(missing) + " to be set"
            )

    @classmethod
    def from_env(cls, *, spec: ContinueExistingSliceSpec) -> OpenAICompatibleContinueExistingSliceBackend:
        return cls(spec=spec, **live_backend_kwargs_from_env(spec))

    def compile(
        self,
        *,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
        prompt_context: dict[str, Any],
    ) -> SliceCompilerArtifacts:
        del object_context
        return openai_compatible_compile(
            base_url=self.base_url,
            model_name=self.model_name,
            api_key=self.api_key,
            timeout_seconds=self.timeout_seconds,
            backend_kind=self.backend_kind,
            backend_name=self.backend_name,
            contract_version=self.spec.contract_version,
            failure_label=f"{self.spec.slice_id} live backend",
            observation_fingerprint=observation.fingerprint(),
            prompt_context=prompt_context,
        )


class RecordedTranscriptContinueExistingSliceBackend:
    backend_kind = "recorded"

    def __init__(self, *, spec: ContinueExistingSliceSpec, transcript_path: str | Path) -> None:
        self.spec = spec
        self.backend_name = spec.recorded_backend_name
        self.transcript_path = Path(transcript_path).resolve()

    def compile(
        self,
        *,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
        prompt_context: dict[str, Any],
    ) -> SliceCompilerArtifacts:
        del object_context
        return load_recorded_transcript(
            transcript_path=self.transcript_path,
            contract_version=self.spec.contract_version,
            input_fingerprint=observation.fingerprint(),
            prompt_context=prompt_context,
            failure_label=self.spec.slice_id,
        )


class DeterministicContinueExistingSliceCompiler:
    backend_kind = "deterministic"

    def __init__(self, *, spec: ContinueExistingSliceSpec) -> None:
        self.spec = spec
        self.backend_name = spec.deterministic_backend_name

    def compile(
        self,
        *,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
        prompt_context: dict[str, Any],
    ) -> SliceCompilerArtifacts:
        compiler_output = self.spec.deterministic_compile(observation, object_context)
        return build_deterministic_compiler_artifacts(
            backend_name=self.backend_name,
            contract_version=self.spec.contract_version,
            input_fingerprint=observation.fingerprint(),
            prompt_context=prompt_context,
            compiler_output=compiler_output,
        )


class ContinueExistingSliceExecutionPipeline:
    def __init__(
        self,
        *,
        spec: ContinueExistingSliceSpec,
        artifact_store: OwnerArtifactWriter | None = None,
        compiler_backend: ContinueExistingCompilerBackend | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        self.spec = spec
        self.artifact_store = artifact_store or OwnerArtifactWriter()
        self.compiler_backend = compiler_backend or DeterministicContinueExistingSliceCompiler(spec=spec)
        self.prompt_path = Path(prompt_path) if prompt_path is not None else spec.prompt_path

    def execute(
        self,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
    ) -> ContinueExistingSliceExecutionResult:
        run_id = build_owner_run_id(requested_delegate_id=self.spec.slice_id, object_id=observation.object_id)
        prompt_context = self._build_prompt_context(observation, object_context)
        reused = self._reuse_existing_result(
            run_id=run_id,
            observation=observation,
            object_context=object_context,
            prompt_context=prompt_context,
        )
        if reused is not None:
            return reused

        compilation = self.compiler_backend.compile(
            observation=observation,
            object_context=object_context,
            prompt_context=prompt_context,
        )
        input_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="input",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            object_context_fingerprint=compilation.object_context_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload={
                "input_fingerprint": observation.fingerprint(),
                "payload": observation.to_spec_input_payload(),
            },
        )
        prompt_context_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="prompt_context",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            object_context_fingerprint=compilation.object_context_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.prompt_context,
        )
        model_request_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="model_request",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            object_context_fingerprint=compilation.object_context_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.model_request,
        )
        raw_model_output_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="raw_model_output",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            object_context_fingerprint=compilation.object_context_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.raw_model_output,
        )
        transcript_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="model_transcript",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            object_context_fingerprint=compilation.object_context_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compilation.transcript_payload,
        )
        compiler_output = dict(compilation.compiler_output)
        compiler_output_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="compiler_output",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            object_context_fingerprint=compilation.object_context_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=compiler_output,
        )

        if str(compiler_output.get("status", "")).strip() != "success":
            return ContinueExistingSliceExecutionResult(
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
                object_context_fingerprint=compilation.object_context_fingerprint or "",
                transcript_fingerprint=compilation.transcript_fingerprint,
                blocked_reason=str(compiler_output.get("blocked_reason", "")).strip() or "compiler_blocked",
            )

        candidate_payloads = compiler_output.get("candidate_payloads", [])
        if not isinstance(candidate_payloads, list) or len(candidate_payloads) != 1:
            blocked_output = {
                "status": "blocked",
                "blocked_reason": "compiler must emit exactly one candidate payload when status=success",
                "candidate_payloads": [],
                "notes": list(compiler_output.get("notes", ())) + ["local validator rejected malformed success envelope"],
            }
            compiler_output_path = self._write_execution_artifact(
                run_id=run_id,
                artifact_name="compiler_output",
                backend_kind=compilation.backend_kind,
                backend_name=compilation.backend_name,
                prompt_fingerprint=compilation.prompt_fingerprint,
                object_context_fingerprint=compilation.object_context_fingerprint,
                transcript_fingerprint=compilation.transcript_fingerprint,
                payload=blocked_output,
            )
            return ContinueExistingSliceExecutionResult(
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
                object_context_fingerprint=compilation.object_context_fingerprint or "",
                transcript_fingerprint=compilation.transcript_fingerprint,
                blocked_reason="compiler must emit exactly one candidate payload when status=success",
            )

        candidate_payload = candidate_payloads[0]
        quarantine_reason = self._candidate_quarantine_reason(
            observation=observation,
            object_context=object_context,
            candidate_payload=candidate_payload,
        )
        if quarantine_reason is not None:
            quarantine_path = self._write_execution_artifact(
                run_id=run_id,
                artifact_name="quarantine",
                backend_kind=compilation.backend_kind,
                backend_name=compilation.backend_name,
                prompt_fingerprint=compilation.prompt_fingerprint,
                object_context_fingerprint=compilation.object_context_fingerprint,
                transcript_fingerprint=compilation.transcript_fingerprint,
                payload={"reason": quarantine_reason, "candidate_payload": candidate_payload},
            )
            return ContinueExistingSliceExecutionResult(
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
                object_context_fingerprint=compilation.object_context_fingerprint or "",
                transcript_fingerprint=compilation.transcript_fingerprint,
                quarantine_reason=quarantine_reason,
                quarantine_path=str(quarantine_path),
            )

        draft = self.spec.draft_cls(**candidate_payload)
        parsed_draft_path = self._write_execution_artifact(
            run_id=run_id,
            artifact_name="parsed_draft",
            backend_kind=compilation.backend_kind,
            backend_name=compilation.backend_name,
            prompt_fingerprint=compilation.prompt_fingerprint,
            object_context_fingerprint=compilation.object_context_fingerprint,
            transcript_fingerprint=compilation.transcript_fingerprint,
            payload=draft.to_agent_payload(),
        )
        return ContinueExistingSliceExecutionResult(
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
            object_context_fingerprint=compilation.object_context_fingerprint or "",
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
            payload["timestamp"] = utc_now()
            artifact_path = self.artifact_store.write_execution_artifact(run_id, artifact_name, payload)
            ordered_paths.append(str(artifact_path))
        return tuple(ordered_paths)

    def _build_prompt_context(
        self,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
    ) -> dict[str, Any]:
        system_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        object_context_payload = object_context.to_prompt_payload()
        object_context_fingerprint = object_context.fingerprint()
        user_prompt = (
            f"{self.spec.success_prompt_line}\n"
            f"host_subject={observation.subject}\n"
            f"host_scope={observation.scope}\n"
            f"input_id={observation.input_id}\n"
            f"object_id={observation.object_id}\n"
            f"object_context_fingerprint={object_context_fingerprint}\n"
            "existing_object_context_json:\n"
            f"{json.dumps(object_context_payload, sort_keys=True)}\n"
            f"{self.spec.input_text_label}:\n"
            f"{observation.text_value().strip()}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prompt_fingerprint = sha256_fragment(
            {
                "contract_version": self.spec.contract_version,
                "prompt_template_version": self.spec.prompt_template_version,
                "messages": messages,
                "object_context_fingerprint": object_context_fingerprint,
            }
        )
        return {
            "contract_version": self.spec.contract_version,
            "prompt_template_version": self.spec.prompt_template_version,
            "messages": messages,
            "prompt_fingerprint": prompt_fingerprint,
            "object_context_fingerprint": object_context_fingerprint,
            "object_context": object_context_payload,
            "prompt_path": str(self.prompt_path),
        }

    def _reuse_existing_result(
        self,
        *,
        run_id: str,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
        prompt_context: dict[str, Any],
    ) -> ContinueExistingSliceExecutionResult | None:
        input_payload = self.artifact_store.load_execution_artifact(run_id, "input")
        prompt_payload = self.artifact_store.load_execution_artifact(run_id, "prompt_context")
        compiler_payload = self.artifact_store.load_execution_artifact(run_id, "compiler_output")
        if input_payload is None or prompt_payload is None or compiler_payload is None:
            return None
        input_body = input_payload.get("payload", {})
        if not isinstance(input_body, dict):
            return None
        if str(input_body.get("input_fingerprint", "")).strip() != observation.fingerprint():
            return None
        if str(prompt_payload.get("prompt_fingerprint", "")).strip() != str(prompt_context["prompt_fingerprint"]):
            return None
        if str(prompt_payload.get("object_context_fingerprint", "")).strip() != object_context.fingerprint():
            return None
        base_kwargs = {
            "backend_kind": str(compiler_payload.get("backend_kind", "")),
            "backend_name": str(compiler_payload.get("backend_name", "")),
            "input_path": str(input_payload["artifact_path"]),
            "prompt_context_path": str(prompt_payload["artifact_path"]),
            "model_request_path": str(self.artifact_store.execution_artifact_path(run_id, "model_request")),
            "raw_model_output_path": str(self.artifact_store.execution_artifact_path(run_id, "raw_model_output")),
            "compiler_output_path": str(compiler_payload["artifact_path"]),
            "transcript_path": str(self.artifact_store.execution_artifact_path(run_id, "model_transcript")),
            "prompt_fingerprint": str(prompt_payload.get("prompt_fingerprint", "")),
            "object_context_fingerprint": str(prompt_payload.get("object_context_fingerprint", "")),
            "transcript_fingerprint": prompt_payload.get("transcript_fingerprint"),
            "reused": True,
        }
        parsed_payload = self.artifact_store.load_execution_artifact(run_id, "parsed_draft")
        if parsed_payload is not None:
            draft = self.spec.draft_cls(**parsed_payload["payload"])
            return ContinueExistingSliceExecutionResult(
                status="success",
                candidate_draft=draft,
                parsed_draft_path=str(parsed_payload["artifact_path"]),
                **base_kwargs,
            )
        quarantine_payload = self.artifact_store.load_execution_artifact(run_id, "quarantine")
        if quarantine_payload is not None:
            quarantine_body = quarantine_payload.get("payload", {})
            return ContinueExistingSliceExecutionResult(
                status="quarantine",
                candidate_draft=None,
                quarantine_reason=str(quarantine_body.get("reason", "")).strip() or "candidate_payload_quarantined",
                quarantine_path=str(quarantine_payload["artifact_path"]),
                **base_kwargs,
            )
        return ContinueExistingSliceExecutionResult(
            status="blocked",
            candidate_draft=None,
            blocked_reason=str(compiler_payload.get("payload", {}).get("blocked_reason", "")).strip() or "compiler_blocked",
            **base_kwargs,
        )

    def _candidate_quarantine_reason(
        self,
        *,
        observation: ContinueExistingObservation,
        object_context: ExistingObjectExecutionContext,
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
        predicate = str(candidate_payload.get("predicate", "")).strip()
        if predicate not in self.spec.allowed_predicates:
            return "candidate_payload_predicate_outside_bounded_set"
        claim_type = str(candidate_payload.get("claim_type", "")).strip()
        if claim_type not in self.spec.allowed_claim_types:
            return "candidate_payload_claim_type_outside_bounded_set"
        direction = str(candidate_payload.get("direction", "")).strip()
        if direction not in self.spec.allowed_directions:
            return "candidate_payload_direction_outside_bounded_set"
        source_family = str(candidate_payload.get("source_family", "")).strip()
        if source_family not in self.spec.allowed_source_families:
            return "candidate_payload_source_family_outside_bounded_set"
        evidence_level = str(candidate_payload.get("evidence_level", "")).strip()
        if evidence_level not in self.spec.allowed_evidence_levels:
            return "candidate_payload_evidence_level_outside_bounded_set"
        time_horizon = str(candidate_payload.get("time_horizon", "")).strip()
        if time_horizon not in self.spec.allowed_time_horizons:
            return "candidate_payload_time_horizon_outside_bounded_set"
        confidence_hint = candidate_payload.get("confidence_hint")
        if not isinstance(confidence_hint, int):
            return "candidate_payload_confidence_hint_must_be_int"
        if confidence_hint < 60 or confidence_hint > 100:
            return "candidate_payload_confidence_hint_outside_bounded_range"
        value = normalize_text(str(candidate_payload.get("value", "")))
        if not value:
            return "candidate_payload_value_missing"
        for segment in self.spec.required_value_segments:
            if segment not in value:
                return "candidate_payload_value_missing_required_segments"
        if str(candidate_payload.get("input_id", "")).strip() != observation.input_id:
            return "candidate_payload_input_id_mismatches_host_input"
        if str(object_context.common.subject).strip() != observation.subject:
            return "existing_object_subject_mismatches_requested_subject"
        if str(object_context.common.scope).strip() != observation.scope:
            return "existing_object_scope_mismatches_requested_scope"
        try:
            self.spec.draft_cls(**candidate_payload)
        except Exception:
            return "candidate_payload_failed_schema_construction"
        return None

    def _write_execution_artifact(
        self,
        *,
        run_id: str,
        artifact_name: str,
        backend_kind: str,
        backend_name: str,
        prompt_fingerprint: str,
        object_context_fingerprint: str | None,
        transcript_fingerprint: str | None,
        payload: dict[str, Any],
    ) -> Path:
        artifact_payload = {
            "run_id": run_id,
            "step_id": "",
            "spec_version": 0,
            "artifact_name": artifact_name,
            "backend_kind": backend_kind,
            "backend_name": backend_name,
            "contract_version": self.spec.contract_version,
            "prompt_fingerprint": prompt_fingerprint,
            "object_context_fingerprint": object_context_fingerprint,
            "transcript_fingerprint": transcript_fingerprint,
            "provenance": "agent_execution",
            "timestamp": utc_now(),
            "payload": payload,
        }
        return self.artifact_store.write_execution_artifact(run_id, artifact_name, artifact_payload)


def _env_name(spec: ContinueExistingSliceSpec, suffix: str) -> str:
    return f"{spec.env_prefix}_{suffix}"


def _env_value(spec: ContinueExistingSliceSpec, suffix: str, *, default: str = "") -> str:
    return str(getenv_compat(_env_name(spec, suffix), default) or "").strip()


def live_backend_kwargs_from_env(spec: ContinueExistingSliceSpec) -> dict[str, Any]:
    base_url = _env_value(spec, "BASE_URL")
    model_name = _env_value(spec, "NAME")
    api_key = _env_value(spec, "API_KEY")
    missing = [
        _env_name(spec, suffix)
        for suffix, value in (
            ("BASE_URL", base_url),
            ("NAME", model_name),
            ("API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        raise SliceLiveBackendConfigError(
            f"{spec.slice_id} live backend requires "
            + ", ".join(env_aliases_text(name) for name in missing)
            + " to be set; no fallback is applied on the public path"
        )
    timeout_raw = _env_value(spec, "TIMEOUT_SECONDS", default="30")
    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise SliceLiveBackendConfigError(f"{env_aliases_text(_env_name(spec, 'TIMEOUT_SECONDS'))} must be numeric") from exc
    return {
        "base_url": base_url,
        "model_name": model_name,
        "api_key": api_key,
        "timeout_seconds": timeout_seconds,
    }
