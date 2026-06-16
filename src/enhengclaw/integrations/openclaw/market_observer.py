from __future__ import annotations

import argparse
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from enhengclaw.agents.execution.market_observer import (
    DeterministicMarketObserverCompiler,
    MarketObservationInput,
    MarketObserverExecutionPipeline,
    OpenAICompatibleMarketObserverBackend,
    RecordedTranscriptMarketObserverBackend,
)
from enhengclaw.agents.owner_state import OwnerArtifactWriter, compute_idempotency_key
from enhengclaw.core.enums import ObjectType
from enhengclaw.core.execution_control import (
    LEASE_REGISTRY_PATH_ENV,
    MissingExecutionPermitError,
    ExecutionPermit,
    load_execution_permit,
)
from enhengclaw.core.session import FileObjectStore, RUNTIME_SESSION_ROOT_ENV
from enhengclaw.ingress.agent_ingress_firewall import AgentIngressFirewall
from enhengclaw.ingress.quarantine_buffer import QuarantineBuffer
from enhengclaw.ingress.replayable_input_log import ReplayableInputLog
from enhengclaw.orchestration.governed_agent_orchestrator import GovernedAgentOrchestrator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator
from enhengclaw.orchestration.worker_operations import OPERATIONAL_AUDIT_ROOT_ENV


OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION = "openclaw-market-observer.v1"
MARKET_OBSERVER_AGENT_ID = "market_observer"


@dataclass(frozen=True, slots=True)
class OpenClawMarketObserverRequest:
    contract_version: str
    subject: str
    scope: str
    object_id: str
    observation_text: str
    execution_permit_path: str
    input_id: str | None = None
    artifacts_root: str | None = None
    compiler_backend: str = "live"
    recorded_transcript_path: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OpenClawMarketObserverRequest":
        if not isinstance(payload, dict):
            raise ValueError("OpenClaw request payload must be a JSON object")
        contract_version = str(payload.get("contract_version", "")).strip()
        if contract_version != OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION:
            raise ValueError(
                "OpenClaw market_observer request contract_version must be "
                f"'{OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION}'"
            )
        subject = _require_non_empty_string(payload.get("subject"), "subject")
        scope = _require_non_empty_string(payload.get("scope"), "scope")
        object_id = _require_non_empty_string(payload.get("object_id"), "object_id")
        observation_text = _require_non_empty_string(payload.get("observation_text"), "observation_text")
        execution_permit_path = _require_non_empty_string(
            payload.get("execution_permit_path"),
            "execution_permit_path",
        )
        input_id = payload.get("input_id")
        compiler_backend = str(payload.get("compiler_backend", "live")).strip().lower() or "live"
        if compiler_backend not in {"live", "recorded", "deterministic"}:
            raise ValueError("compiler_backend must be one of: live, recorded, deterministic")
        recorded_transcript_path = payload.get("recorded_transcript_path")
        if compiler_backend == "recorded" and not str(input_id or "").strip():
            raise ValueError("input_id is required when compiler_backend=recorded")
        if compiler_backend == "recorded" and not str(recorded_transcript_path or "").strip():
            raise ValueError("recorded_transcript_path is required when compiler_backend=recorded")
        if compiler_backend != "recorded" and recorded_transcript_path not in {None, ""}:
            raise ValueError("recorded_transcript_path is only legal when compiler_backend=recorded")
        artifacts_root = payload.get("artifacts_root")
        return cls(
            contract_version=contract_version,
            subject=subject,
            scope=scope,
            object_id=object_id,
            observation_text=observation_text,
            execution_permit_path=execution_permit_path,
            input_id=None if input_id in {None, ""} else str(input_id),
            artifacts_root=None if artifacts_root in {None, ""} else str(artifacts_root),
            compiler_backend=compiler_backend,
            recorded_transcript_path=None
            if recorded_transcript_path in {None, ""}
            else str(recorded_transcript_path),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "subject": self.subject,
            "scope": self.scope,
            "object_id": self.object_id,
            "observation_text": self.observation_text,
            "execution_permit_path": self.execution_permit_path,
            "input_id": self.input_id,
            "artifacts_root": self.artifacts_root,
            "compiler_backend": self.compiler_backend,
            "recorded_transcript_path": self.recorded_transcript_path,
        }


@dataclass(frozen=True, slots=True)
class OpenClawMarketObserverResponse:
    contract_version: str
    status: str
    execution_status: str | None
    run_state: str
    owner_run_id: str | None
    spec_version: int | None
    final_output_path: str | None
    runtime_session_path: str | None
    compiler_artifact_paths: tuple[str, ...]
    accepted_signal_ids: tuple[str, ...]
    blocked_reason: str | None = None
    quarantine_reason: str | None = None
    error: str | None = None
    artifacts_root: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "execution_status": self.execution_status,
            "run_state": self.run_state,
            "owner_run_id": self.owner_run_id,
            "spec_version": self.spec_version,
            "final_output_path": self.final_output_path,
            "runtime_session_path": self.runtime_session_path,
            "compiler_artifact_paths": list(self.compiler_artifact_paths),
            "accepted_signal_ids": list(self.accepted_signal_ids),
            "blocked_reason": self.blocked_reason,
            "quarantine_reason": self.quarantine_reason,
            "error": self.error,
            "artifacts_root": self.artifacts_root,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the OpenClaw deployment adapter for the shipped market_observer lane."
    )
    parser.add_argument("--request", type=Path, required=True, help="Path to an openclaw-market-observer.v1 JSON request.")
    parser.add_argument("--response", type=Path, required=True, help="Path to write the JSON response.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request_payload: dict[str, Any] | None = None
    exit_code = 0
    try:
        request_payload = json.loads(args.request.read_text(encoding="utf-8"))
        request = OpenClawMarketObserverRequest.from_payload(request_payload)
        response = run_openclaw_market_observer(request)
        exit_code = 0 if response.status != "failed" else 1
    except Exception as exc:
        response = OpenClawMarketObserverResponse(
            contract_version=OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
            status="failed",
            execution_status=None,
            run_state="FAILED",
            owner_run_id=None,
            spec_version=None,
            final_output_path=None,
            runtime_session_path=None,
            compiler_artifact_paths=(),
            accepted_signal_ids=(),
            error=str(exc),
            artifacts_root=_payload_artifacts_root(request_payload),
        )
        exit_code = 1
    args.response.parent.mkdir(parents=True, exist_ok=True)
    args.response.write_text(json.dumps(response.to_payload(), indent=2, sort_keys=True), encoding="utf-8")
    if exit_code != 0:
        print(response.error or "openclaw market_observer adapter failed", file=os.sys.stderr)
    return exit_code


def run_openclaw_market_observer(request: OpenClawMarketObserverRequest) -> OpenClawMarketObserverResponse:
    artifacts_root = resolve_openclaw_artifacts_root(request.artifacts_root)
    runtime_paths = openclaw_runtime_paths(artifacts_root)
    for directory in (
        runtime_paths["runtime_sessions"],
        runtime_paths["replay_log"],
        runtime_paths["quarantine"],
        runtime_paths["operational_audit"],
    ):
        directory.mkdir(parents=True, exist_ok=True)
    permit = load_execution_permit(Path(request.execution_permit_path).resolve())
    owner_store = OwnerArtifactWriter(artifacts_root / "agent_owner")
    observation = MarketObservationInput(
        input_id=request.input_id or f"{MARKET_OBSERVER_AGENT_ID}:{request.object_id}:1",
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        observation_text=request.observation_text.strip(),
    )
    execution = MarketObserverExecutionPipeline(
        artifact_store=owner_store,
        compiler_backend=_market_observer_backend(request),
    )
    with _override_runtime_environment(runtime_paths):
        execution_result = execution.execute(observation)
        runtime = RuntimeOrchestrator(
            store=FileObjectStore(runtime_paths["runtime_sessions"]),
            agent_ingress_firewall=AgentIngressFirewall(
                quarantine_buffer=QuarantineBuffer(runtime_paths["quarantine"]),
                replayable_input_log=ReplayableInputLog(runtime_paths["replay_log"]),
            ),
            execution_permit=permit,
        )
        result = GovernedAgentOrchestrator(runtime=runtime).run_governed_write(
            requested_delegate_id=MARKET_OBSERVER_AGENT_ID,
            object_id=request.object_id,
            subject=request.subject,
            scope=request.scope,
            signal_draft=execution_result.candidate_draft,
            artifacts_root=artifacts_root,
            execution_permit=permit,
            object_type=ObjectType.ASSET,
            user_intent="Execute one OpenClaw market_observer deployment request.",
            constraints=("single_payload", "single_tool_call", "verify_before_finalize"),
            admission_blocked_reason=_admission_blocked_reason(execution_result),
            spec_input_payload=observation.to_spec_input_payload(),
            admission_artifacts=execution_result.compiler_artifact_paths(),
        )
        step_id = _market_observer_step_id(
            request=request,
            observation=observation,
            execution_status=execution_result.status,
            signal_payload={}
            if execution_result.candidate_draft is None
            else execution_result.candidate_draft.to_agent_payload(),
            spec_version=result.spec_version,
        )
        compiler_artifact_paths = execution.restamp_execution_artifacts(
            run_id=result.owner_run_id,
            step_id=step_id,
            spec_version=result.spec_version,
        )
        runtime_session_path = governed_runtime_session_path(artifacts_root=artifacts_root, object_id=request.object_id)

    status = _response_status(result.run_state, execution_result.status)
    return OpenClawMarketObserverResponse(
        contract_version=OPENCLAW_MARKET_OBSERVER_CONTRACT_VERSION,
        status=status,
        execution_status=execution_result.status,
        run_state=result.run_state,
        owner_run_id=result.owner_run_id,
        spec_version=result.spec_version,
        final_output_path=result.final_output_path,
        runtime_session_path=str(runtime_session_path) if runtime_session_path.exists() else None,
        compiler_artifact_paths=tuple(compiler_artifact_paths or execution_result.compiler_artifact_paths()),
        accepted_signal_ids=tuple(result.accepted_signal_ids),
        blocked_reason=result.blocked_reason or execution_result.blocked_reason,
        quarantine_reason=execution_result.quarantine_reason,
        artifacts_root=str(artifacts_root),
    )


def resolve_openclaw_artifacts_root(artifacts_root: str | None) -> Path:
    if artifacts_root is not None and artifacts_root.strip():
        resolved = Path(artifacts_root).resolve()
    else:
        resolved = Path(tempfile.mkdtemp(prefix="ecoc_mo_", dir=_resolve_openclaw_temp_root())).resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def openclaw_runtime_paths(artifacts_root: str | Path) -> dict[str, Path]:
    root = Path(artifacts_root).resolve()
    return {
        "artifacts_root": root,
        "runtime_sessions": root / "runtime_sessions",
        "replay_log": root / "replay_log",
        "quarantine": root / "quarantine",
        "operational_audit": root / "operational_audit",
        "lease_registry_path": root / "execution_leases.sqlite3",
    }


def governed_runtime_session_path(*, artifacts_root: str | Path, object_id: str) -> Path:
    root = Path(artifacts_root).resolve()
    return root / "runtime_sessions" / f"{quote(object_id, safe='._-')}.json"


def _market_observer_backend(request: OpenClawMarketObserverRequest):
    if request.compiler_backend == "live":
        return OpenAICompatibleMarketObserverBackend.from_env()
    if request.compiler_backend == "recorded":
        transcript_path = request.recorded_transcript_path
        if transcript_path is None:
            raise ValueError("recorded_transcript_path is required when compiler_backend=recorded")
        return RecordedTranscriptMarketObserverBackend(transcript_path=transcript_path)
    return DeterministicMarketObserverCompiler()


def _response_status(run_state: str, execution_status: str) -> str:
    if run_state == "FINALIZED":
        return "success"
    if run_state == "FAILED":
        return "failed"
    if execution_status == "quarantine":
        return "quarantine"
    return "blocked"


def _admission_blocked_reason(execution_result) -> str | None:
    if execution_result.status == "blocked":
        return execution_result.blocked_reason
    if execution_result.status == "quarantine":
        return execution_result.quarantine_reason
    return None


def _market_observer_step_id(
    *,
    request: OpenClawMarketObserverRequest,
    observation: MarketObservationInput,
    execution_status: str,
    signal_payload: dict[str, Any],
    spec_version: int,
) -> str:
    idempotency_signal_payload = signal_payload or observation.to_spec_input_payload()
    idempotency_key = compute_idempotency_key(
        requested_delegate_id=MARKET_OBSERVER_AGENT_ID,
        object_id=request.object_id,
        subject=request.subject,
        scope=request.scope,
        signal_payload=idempotency_signal_payload,
        spec_version=spec_version,
    )
    return f"{MARKET_OBSERVER_AGENT_ID}:{execution_status}:{idempotency_key[:12]}"


def _resolve_openclaw_temp_root() -> str | None:
    candidates: list[Path] = []
    if os.name == "nt":
        temp_drive = Path(tempfile.gettempdir()).drive or Path.cwd().drive
        if temp_drive:
            candidates.append(Path(f"{temp_drive}\\ecoc"))
    candidates.append(Path(tempfile.gettempdir()) / "ecoc")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return str(candidate)
    return None


@contextmanager
def _override_runtime_environment(paths: dict[str, Path]):
    overrides = {
        RUNTIME_SESSION_ROOT_ENV: str(paths["runtime_sessions"]),
        OPERATIONAL_AUDIT_ROOT_ENV: str(paths["operational_audit"]),
        LEASE_REGISTRY_PATH_ENV: str(paths["lease_registry_path"]),
    }
    saved = {name: os.getenv(name) for name in overrides}
    for name, value in overrides.items():
        os.environ[name] = value
    try:
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def _payload_artifacts_root(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    artifacts_root = payload.get("artifacts_root")
    return None if artifacts_root in {None, ""} else str(artifacts_root)


def _require_non_empty_string(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise MissingExecutionPermitError(f"OpenClaw market_observer request requires non-empty {field_name}")
    return text


if __name__ == "__main__":
    raise SystemExit(main())
