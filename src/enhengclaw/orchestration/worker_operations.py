from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any
from uuid import uuid4

from enhengclaw.compat.naming import getenv_compat
from enhengclaw.core.execution_control import probe_process_state
from enhengclaw.core.session import RUNTIME_SESSION_ROOT_ENV


OPERATIONAL_AUDIT_ROOT_ENV = "ENHENGCLAW_OPERATIONAL_AUDIT_ROOT"
WORKER_REQUEST_SCHEMA_VERSION = "worker-request.v1"
TASK_LOCK_STALE_SECONDS = 12.0
_WINDOWS_REPLACE_RETRYABLE_WINERRORS = {5, 32}


class WorkerRequestSchemaError(ValueError):
    pass


class WorkerTaskActiveError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerRequestEnvelope:
    schema_version: str
    request_kind: str
    run_id: str
    task_key: str
    controller_pid: int
    audit_root: str
    task_lock_path: str
    created_at_utc: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StreamCaptureMetrics:
    stream_name: str
    byte_count: int
    line_count: int
    contains_nul: bool
    replacement_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "stream_name": self.stream_name,
            "byte_count": self.byte_count,
            "line_count": self.line_count,
            "contains_nul": self.contains_nul,
            "replacement_count": self.replacement_count,
        }


@dataclass(frozen=True, slots=True)
class SubprocessAuditResult:
    returncode: int
    worker_pid: int
    stdout: StreamCaptureMetrics
    stderr: StreamCaptureMetrics

    def to_payload(self) -> dict[str, Any]:
        return {
            "returncode": self.returncode,
            "worker_pid": self.worker_pid,
            "stdout": self.stdout.to_payload(),
            "stderr": self.stderr.to_payload(),
        }


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sanitize_fragment(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value.strip())
    return sanitized or "unknown"


def build_run_id(prefix: str) -> str:
    return f"{sanitize_fragment(prefix)}-{uuid4().hex[:12]}"


def default_runtime_audit_root() -> Path:
    env_root = getenv_compat(OPERATIONAL_AUDIT_ROOT_ENV)
    if env_root and env_root.strip():
        return (Path(env_root).resolve() / "runtime").resolve()
    session_root = getenv_compat(RUNTIME_SESSION_ROOT_ENV)
    if session_root and session_root.strip():
        return (Path(session_root).resolve().parent / "operational_audit" / "runtime").resolve()
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return (base / "EnhengClaw" / "runtime" / "operational_audit" / "runtime").resolve()


def default_ingestion_audit_root(artifacts_root: str | Path) -> Path:
    return (Path(artifacts_root).resolve() / "operational_audit" / "ingestion").resolve()


def prepare_run_root(audit_root: str | Path, run_id: str) -> Path:
    root = Path(audit_root).resolve() / "runs" / sanitize_fragment(run_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def task_lock_path_for(audit_root: str | Path, task_key: str) -> Path:
    lock_root = Path(audit_root).resolve() / "locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    return lock_root / f"{sanitize_fragment(task_key)}.json"


def business_intent_record_path_for(audit_root: str | Path, business_request_id: str) -> Path:
    intent_root = Path(audit_root).resolve() / "business_intents"
    intent_root.mkdir(parents=True, exist_ok=True)
    return intent_root / f"{sanitize_fragment(business_request_id)}.json"


def build_worker_request_envelope(
    *,
    request_kind: str,
    run_id: str,
    task_key: str,
    audit_root: str | Path,
    task_lock_path: str | Path,
    payload: dict[str, Any],
    controller_pid: int | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": WORKER_REQUEST_SCHEMA_VERSION,
        "request_kind": request_kind,
        "run_id": run_id,
        "task_key": task_key,
        "controller_pid": os.getpid() if controller_pid is None else int(controller_pid),
        "audit_root": str(Path(audit_root).resolve()),
        "task_lock_path": str(Path(task_lock_path).resolve()),
        "created_at_utc": format_utc_timestamp(utc_now()),
        "payload": dict(payload),
    }


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    replace_retry_attempts: int = 1,
    replace_retry_delay_seconds: float = 0.0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep temp file names short so long Windows artifact paths still fit.
    temp_path = path.parent / f".tmp-{uuid4().hex}.json"
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _replace_path_with_retry(
        temp_path,
        path,
        attempts=replace_retry_attempts,
        delay_seconds=replace_retry_delay_seconds,
    )


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def load_worker_request_envelope(path: Path, *, expected_kind: str) -> WorkerRequestEnvelope:
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkerRequestSchemaError(f"worker request does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkerRequestSchemaError(f"worker request is not valid JSON: {exc.msg}") from exc
    if not isinstance(raw_payload, dict):
        raise WorkerRequestSchemaError("worker request must be a JSON object")
    schema_version = str(raw_payload.get("schema_version", "")).strip()
    if schema_version != WORKER_REQUEST_SCHEMA_VERSION:
        raise WorkerRequestSchemaError(
            f"worker request schema version mismatch: expected '{WORKER_REQUEST_SCHEMA_VERSION}', observed '{schema_version or '<missing>'}'"
        )
    request_kind = str(raw_payload.get("request_kind", "")).strip()
    if request_kind != expected_kind:
        raise WorkerRequestSchemaError(
            f"worker request kind mismatch: expected '{expected_kind}', observed '{request_kind or '<missing>'}'"
        )
    payload = raw_payload.get("payload")
    if not isinstance(payload, dict):
        raise WorkerRequestSchemaError("worker request payload must be a JSON object")
    controller_pid = raw_payload.get("controller_pid")
    if isinstance(controller_pid, bool):
        raise WorkerRequestSchemaError("worker request controller_pid must be an integer")
    try:
        controller_pid_value = int(controller_pid)
    except (TypeError, ValueError) as exc:
        raise WorkerRequestSchemaError("worker request controller_pid must be an integer") from exc
    envelope = WorkerRequestEnvelope(
        schema_version=schema_version,
        request_kind=request_kind,
        run_id=_require_non_empty_string(raw_payload.get("run_id"), field="run_id"),
        task_key=_require_non_empty_string(raw_payload.get("task_key"), field="task_key"),
        controller_pid=controller_pid_value,
        audit_root=_require_non_empty_string(raw_payload.get("audit_root"), field="audit_root"),
        task_lock_path=_require_non_empty_string(raw_payload.get("task_lock_path"), field="task_lock_path"),
        created_at_utc=_require_non_empty_string(raw_payload.get("created_at_utc"), field="created_at_utc"),
        payload=payload,
    )
    return envelope


def initialize_audit_record(
    run_root: Path,
    *,
    component: str,
    run_id: str,
    task_key: str,
    controller_pid: int,
    request_path: str | Path,
    request_kind: str,
    request_schema_version: str,
) -> None:
    write_json_atomic(
        run_root / "audit_record.json",
        {
            "component": component,
            "run_id": run_id,
            "task_key": task_key,
            "status": "created",
            "controller_pid": controller_pid,
            "worker_pid": None,
            "lease_id": None,
            "request_kind": request_kind,
            "request_schema_version": request_schema_version,
            "request_path": str(Path(request_path).resolve()),
            "created_at_utc": format_utc_timestamp(utc_now()),
            "started_at_utc": None,
            "ended_at_utc": None,
            "exit_code": None,
            "interruption_reason": None,
            "failure_category": None,
            "requested_scope": None,
            "operation": None,
            "stdout": None,
            "stderr": None,
            "cleanup": [],
        },
    )


def read_audit_record(run_root: Path) -> dict[str, Any]:
    target = run_root / "audit_record.json"
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def update_audit_record(run_root: Path, **fields: Any) -> dict[str, Any]:
    payload = read_audit_record(run_root)
    payload.update(fields)
    write_json_atomic(run_root / "audit_record.json", payload)
    return payload


def read_business_intent_record(audit_root: str | Path, business_request_id: str) -> dict[str, Any]:
    target = business_intent_record_path_for(audit_root, business_request_id)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def update_business_intent_record(
    audit_root: str | Path,
    business_request_id: str,
    *,
    defaults: dict[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = {}
    if defaults:
        payload.update(defaults)
    existing = read_business_intent_record(audit_root, business_request_id)
    if existing:
        payload.update(existing)
    payload.update(fields)
    write_json_atomic(
        business_intent_record_path_for(audit_root, business_request_id),
        payload,
    )
    return payload


def append_audit_event(run_root: Path, event: str, **fields: Any) -> None:
    audit_record = read_audit_record(run_root)
    enriched_fields = dict(fields)
    if audit_record:
        for key in ("run_id", "task_key", "controller_pid"):
            if key not in enriched_fields and key in audit_record:
                enriched_fields[key] = audit_record[key]
        if "component" not in enriched_fields and "component" in audit_record:
            enriched_fields["component"] = audit_record["component"]
    append_jsonl(
        run_root / "events.jsonl",
        {
            "timestamp_utc": format_utc_timestamp(utc_now()),
            "event": event,
            **enriched_fields,
        },
    )


def copy_request_artifact(source_path: Path, run_root: Path) -> None:
    target = run_root / "request.json"
    target.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")


def acquire_task_lock(
    *,
    audit_root: str | Path,
    task_key: str,
    run_id: str,
    controller_pid: int,
    stale_after_seconds: float = TASK_LOCK_STALE_SECONDS,
) -> tuple[Path, dict[str, Any] | None]:
    lock_path = task_lock_path_for(audit_root, task_key)
    record = {
        "task_key": task_key,
        "run_id": run_id,
        "status": "active",
        "controller_pid": controller_pid,
        "worker_pid": None,
        "lease_id": None,
        "created_at_utc": format_utc_timestamp(utc_now()),
        "updated_at_utc": format_utc_timestamp(utc_now()),
        "failure_category": None,
    }
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = _load_lock_record(lock_path)
        if _lock_is_active(existing, stale_after_seconds=stale_after_seconds):
            raise WorkerTaskActiveError(
                f"task '{task_key}' is already active under run '{existing.get('run_id', '<unknown>')}'"
            )
        orphaned = existing if isinstance(existing, dict) else None
        if orphaned is not None:
            orphaned = {
                **orphaned,
                "worker_pid_state": probe_process_state(orphaned.get("worker_pid")),
                "controller_pid_state": probe_process_state(orphaned.get("controller_pid")),
                "lock_updated_at_utc": orphaned.get("updated_at_utc"),
                "reclaim_reason": _classify_lock_reclaim_reason(
                    orphaned,
                    stale_after_seconds=stale_after_seconds,
                ),
            }
            orphaned_dir = lock_path.parent / "orphaned"
            orphaned_dir.mkdir(parents=True, exist_ok=True)
            orphaned_name = (
                f"reclaimed-{hashlib.sha1(task_key.encode('utf-8')).hexdigest()[:12]}-{uuid4().hex[:12]}.json"
            )
            write_json_atomic(
                orphaned_dir / orphaned_name,
                orphaned,
            )
        write_json_atomic(lock_path, record)
        return lock_path, orphaned
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(record, indent=2, sort_keys=True))
        return lock_path, None


def heartbeat_task_lock(
    lock_path: str | Path,
    *,
    controller_pid: int | None = None,
    worker_pid: int | None = None,
    lease_id: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    payload = _load_lock_record(Path(lock_path))
    if not isinstance(payload, dict):
        raise WorkerTaskActiveError(f"task lock is missing or invalid: {lock_path}")
    payload["status"] = "active"
    payload["updated_at_utc"] = format_utc_timestamp(utc_now())
    if controller_pid is not None:
        payload["controller_pid"] = int(controller_pid)
    if worker_pid is not None:
        payload["worker_pid"] = int(worker_pid)
    if lease_id is not None:
        payload["lease_id"] = lease_id
    if extra_fields:
        payload.update(extra_fields)
    write_json_atomic(
        Path(lock_path),
        payload,
        replace_retry_attempts=8,
        replace_retry_delay_seconds=0.05,
    )


def _replace_path_with_retry(
    temp_path: Path,
    target_path: Path,
    *,
    attempts: int,
    delay_seconds: float,
) -> None:
    normalized_attempts = max(int(attempts), 1)
    last_error: OSError | None = None
    for attempt in range(1, normalized_attempts + 1):
        try:
            temp_path.replace(target_path)
            return
        except OSError as exc:
            last_error = exc
            if attempt >= normalized_attempts or not _is_retryable_windows_replace_error(exc):
                break
            time.sleep(max(delay_seconds, 0.0))
    try:
        if temp_path.exists():
            temp_path.unlink()
    except OSError:
        pass
    if last_error is not None:
        raise last_error


def _is_retryable_windows_replace_error(exc: OSError) -> bool:
    return getattr(exc, "winerror", None) in _WINDOWS_REPLACE_RETRYABLE_WINERRORS


def release_task_lock(
    lock_path: str | Path,
    *,
    status: str,
    failure_category: str | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    payload = _load_lock_record(Path(lock_path))
    if not isinstance(payload, dict):
        return
    payload["status"] = status
    payload["failure_category"] = failure_category
    payload["updated_at_utc"] = format_utc_timestamp(utc_now())
    if extra_fields:
        payload.update(extra_fields)
    write_json_atomic(Path(lock_path), payload)


def audited_subprocess_run(
    command: list[str],
    *,
    env: dict[str, str],
    run_root: Path,
    cwd: str | Path | None = None,
) -> SubprocessAuditResult:
    stdout_log = run_root / "worker.stdout.log"
    stderr_log = run_root / "worker.stderr.log"
    process = subprocess.Popen(
        command,
        cwd=None if cwd is None else str(Path(cwd).resolve()),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    stdout_capture = _StreamCapture(
        stream_name="stdout",
        stream=process.stdout,
        target_path=stdout_log,
        mirror_stream=sys.stdout,
    )
    stderr_capture = _StreamCapture(
        stream_name="stderr",
        stream=process.stderr,
        target_path=stderr_log,
        mirror_stream=sys.stderr,
    )
    stdout_capture.start()
    stderr_capture.start()
    returncode = process.wait()
    stdout_metrics = stdout_capture.finish()
    stderr_metrics = stderr_capture.finish()
    return SubprocessAuditResult(
        returncode=returncode,
        worker_pid=process.pid,
        stdout=stdout_metrics,
        stderr=stderr_metrics,
    )


def _load_lock_record(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _lock_is_active(payload: dict[str, Any] | None, *, stale_after_seconds: float) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("status", "")).strip() != "active":
        return False
    updated_at = _parse_utc(payload.get("updated_at_utc"))
    if updated_at is None:
        return False
    if updated_at < utc_now() - timedelta(seconds=stale_after_seconds):
        return False
    if probe_process_state(payload.get("worker_pid")) == "alive":
        return True
    if probe_process_state(payload.get("controller_pid")) == "alive":
        return True
    return False


def _classify_lock_reclaim_reason(payload: dict[str, Any], *, stale_after_seconds: float) -> str:
    status = str(payload.get("status", "")).strip() or "unknown"
    if status != "active":
        return f"inactive_status_{status}"
    updated_at = _parse_utc(payload.get("updated_at_utc"))
    if updated_at is None:
        return "invalid_lock_payload"
    if updated_at < utc_now() - timedelta(seconds=stale_after_seconds):
        return "stale_active_lock"
    worker_pid_state = probe_process_state(payload.get("worker_pid"))
    controller_pid_state = probe_process_state(payload.get("controller_pid"))
    if worker_pid_state != "alive" and controller_pid_state != "alive":
        return "all_pids_dead"
    return "inactive_active_lock"


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _require_non_empty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerRequestSchemaError(f"worker request field '{field}' must be a non-empty string")
    return value.strip()


class _StreamCapture:
    def __init__(
        self,
        *,
        stream_name: str,
        stream: Any,
        target_path: Path,
        mirror_stream: Any,
    ) -> None:
        self.stream_name = stream_name
        self.stream = stream
        self.target_path = target_path
        self.mirror_stream = mirror_stream
        self.byte_count = 0
        self.line_count = 0
        self.contains_nul = False
        self.replacement_count = 0
        self._thread = threading.Thread(
            target=self._pump,
            name=f"capture-{stream_name}",
            daemon=True,
        )

    def start(self) -> None:
        self.target_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread.start()

    def finish(self) -> StreamCaptureMetrics:
        self._thread.join()
        return StreamCaptureMetrics(
            stream_name=self.stream_name,
            byte_count=self.byte_count,
            line_count=self.line_count,
            contains_nul=self.contains_nul,
            replacement_count=self.replacement_count,
        )

    def _pump(self) -> None:
        if self.stream is None:
            return
        with self.target_path.open("w", encoding="utf-8") as handle:
            try:
                while True:
                    chunk = self.stream.read(4096)
                    if not chunk:
                        break
                    self.byte_count += len(chunk)
                    self.contains_nul = self.contains_nul or (b"\x00" in chunk)
                    text = chunk.decode("utf-8", errors="replace")
                    self.replacement_count += text.count("\ufffd")
                    self.line_count += text.count("\n")
                    handle.write(text)
                    handle.flush()
                    self.mirror_stream.write(text)
                    self.mirror_stream.flush()
            finally:
                self.stream.close()
