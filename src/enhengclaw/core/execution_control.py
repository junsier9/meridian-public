from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatch
import json
import os
from pathlib import Path, PureWindowsPath
import sqlite3
import subprocess
import sys
import tempfile
import threading
from typing import Any, Iterator
from uuid import uuid4

from enhengclaw.compat.naming import env_aliases_text, getenv_compat


EXECUTION_PERMIT_PATH_ENV = "ENHENGCLAW_EXECUTION_PERMIT_PATH"
TRUST_ROOT_DIR_ENV = "ENHENGCLAW_TRUST_ROOT_DIR"
LEASE_REGISTRY_PATH_ENV = "ENHENGCLAW_LEASE_REGISTRY_PATH"
ALLOW_WRITABLE_TRUST_ROOT_ENV = "ENHENGCLAW_ALLOW_WRITABLE_TRUST_ROOT"
WORKER_MODE_ENV = "ENHENGCLAW_WORKER_MODE"
WORKER_LEASE_ID_ENV = "ENHENGCLAW_WORKER_LEASE_ID"
WORKER_PERMIT_PATH_ENV = "ENHENGCLAW_WORKER_PERMIT_PATH"
WORKER_LEASE_HEARTBEAT_SECONDS = 2.0
WORKER_LEASE_STALE_SECONDS = WORKER_LEASE_HEARTBEAT_SECONDS * 3.0
DEFAULT_SCOPE_WILDCARD = "*"
DEFAULT_SHADOW_INGEST_SCOPE = "shadow_ingestion"
DEFAULT_PERMIT_SIGNER_IDENTITY = "execution-permit"
SSH_SIGNATURE_NAMESPACE = "enhengclaw-execution"

CAP_RUNTIME_EXECUTE = "runtime.execute"
CAP_PROVIDER_FETCH = "provider.fetch"
CAP_PROVIDER_STREAM = "provider.stream"
CAP_PROVIDER_TRANSPORT = "provider.transport"
CAP_PROVIDER_SELECT_INCLUDE_SHADOW = "provider.select.include_shadow"
CAP_PROVIDER_SELECT_MANUAL_OVERRIDE = "provider.select.manual_override"
CAP_PROVIDER_SELECT_RETIRED_OVERRIDE = "provider.select.retired_override"
CAP_CLI_SHADOW_INGEST = "cli.shadow_ingest"
CAP_SCRIPT_SHADOW_24H = "script.shadow_24h"
RUNTIME_WORKER_ENTRYPOINT = "enhengclaw.orchestration.runtime_worker"
INGESTION_WORKER_ENTRYPOINT = "enhengclaw.orchestration.ingestion_worker"


class ExecutionControlError(PermissionError):
    pass


class MissingExecutionPermitError(ExecutionControlError):
    pass


class InvalidExecutionPermitError(ExecutionControlError):
    pass


class ExecutionCapabilityError(ExecutionControlError):
    pass


class GlobalFreezeActiveError(ExecutionControlError):
    pass


class ExecutionLeaseError(ExecutionControlError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionPermit:
    permit_id: str
    batch_id: str
    scope: str
    issued_by: str
    issued_at_utc: datetime
    expires_at_utc: datetime
    owner_review_ref: str
    batch_approval_ref: str
    allowed_operations: tuple[str, ...]
    capabilities: tuple[str, ...]
    signer_identity: str = DEFAULT_PERMIT_SIGNER_IDENTITY
    global_freeze_path: str | None = None
    signature: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ExecutionPermit:
        return cls(
            permit_id=str(payload["permit_id"]),
            batch_id=str(payload["batch_id"]),
            scope=str(payload["scope"]),
            issued_by=str(payload["issued_by"]),
            issued_at_utc=_parse_utc_timestamp(payload["issued_at_utc"], field_name="issued_at_utc"),
            expires_at_utc=_parse_utc_timestamp(payload["expires_at_utc"], field_name="expires_at_utc"),
            owner_review_ref=str(payload["owner_review_ref"]),
            batch_approval_ref=str(payload["batch_approval_ref"]),
            allowed_operations=tuple(str(item) for item in payload.get("allowed_operations", [])),
            capabilities=tuple(str(item) for item in payload.get("capabilities", [])),
            signer_identity=str(payload.get("signer_identity", DEFAULT_PERMIT_SIGNER_IDENTITY)),
            global_freeze_path=None
            if payload.get("global_freeze_path") in {None, ""}
            else str(payload["global_freeze_path"]),
            signature=str(payload.get("signature", "")),
        )

    def to_payload(self, *, include_signature: bool = True) -> dict[str, Any]:
        payload = {
            "permit_id": self.permit_id,
            "batch_id": self.batch_id,
            "scope": self.scope,
            "issued_by": self.issued_by,
            "issued_at_utc": _format_utc_timestamp(self.issued_at_utc),
            "expires_at_utc": _format_utc_timestamp(self.expires_at_utc),
            "owner_review_ref": self.owner_review_ref,
            "batch_approval_ref": self.batch_approval_ref,
            "allowed_operations": list(self.allowed_operations),
            "capabilities": list(self.capabilities),
            "signer_identity": self.signer_identity,
            "global_freeze_path": self.global_freeze_path,
        }
        if include_signature:
            payload["signature"] = self.signature
        return payload


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    permit: ExecutionPermit
    operation: str
    requested_scope: str
    started_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ExecutionLease:
    lease_id: str
    permit_id: str
    permit_path: str
    operation: str
    requested_scope: str
    worker_pid: int
    acquired_at_utc: datetime
    heartbeat_at_utc: datetime
    expires_at_utc: datetime
    freeze_path: str | None


_CURRENT_EXECUTION_CONTEXT: ContextVar[ExecutionContext | None] = ContextVar(
    "enhengclaw_current_execution_context",
    default=None,
)
_WORKER_INTERRUPT_LOCK = threading.Lock()
_WORKER_INTERRUPT_REASON: str | None = None


def load_execution_permit(path: str | Path | None = None) -> ExecutionPermit:
    permit_path = _resolve_permit_path(path)
    payload = json.loads(permit_path.read_text(encoding="utf-8"))
    permit = ExecutionPermit.from_payload(payload)
    validate_execution_permit(permit)
    return permit


def issue_execution_permit(
    *,
    permit_path: str | Path,
    signing_private_key_path: str | Path,
    batch_id: str,
    scope: str,
    issued_by: str,
    owner_review_ref: str | Path,
    batch_approval_ref: str | Path,
    allowed_operations: list[str],
    capabilities: list[str],
    expires_at_utc: datetime,
    global_freeze_path: str | Path | None = None,
    permit_id: str | None = None,
    signer_identity: str = DEFAULT_PERMIT_SIGNER_IDENTITY,
) -> ExecutionPermit:
    permit = ExecutionPermit(
        permit_id=permit_id or f"permit-{uuid4()}",
        batch_id=batch_id,
        scope=scope,
        issued_by=issued_by,
        issued_at_utc=datetime.now(UTC),
        expires_at_utc=expires_at_utc.astimezone(UTC),
        owner_review_ref=str(Path(owner_review_ref).resolve()),
        batch_approval_ref=str(Path(batch_approval_ref).resolve()),
        allowed_operations=tuple(allowed_operations),
        capabilities=tuple(capabilities),
        signer_identity=signer_identity,
        global_freeze_path=None if global_freeze_path is None else str(Path(global_freeze_path).resolve()),
        signature="",
    )
    signature = sign_execution_permit_payload(
        permit.to_payload(include_signature=False),
        signing_private_key_path=signing_private_key_path,
    )
    signed = ExecutionPermit(
        permit_id=permit.permit_id,
        batch_id=permit.batch_id,
        scope=permit.scope,
        issued_by=permit.issued_by,
        issued_at_utc=permit.issued_at_utc,
        expires_at_utc=permit.expires_at_utc,
        owner_review_ref=permit.owner_review_ref,
        batch_approval_ref=permit.batch_approval_ref,
        allowed_operations=permit.allowed_operations,
        capabilities=permit.capabilities,
        signer_identity=permit.signer_identity,
        global_freeze_path=permit.global_freeze_path,
        signature=signature,
    )
    target = Path(permit_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(signed.to_payload(), indent=2), encoding="utf-8")
    return signed


def sign_execution_permit_payload(
    payload: dict[str, Any],
    *,
    signing_private_key_path: str | Path,
) -> str:
    canonical = _canonical_payload(payload)
    key_path = Path(signing_private_key_path).resolve()
    if not key_path.exists():
        raise InvalidExecutionPermitError(f"execution signing key does not exist: {key_path}")
    with tempfile.TemporaryDirectory() as tmpdir:
        payload_path = Path(tmpdir) / "execution_permit_payload.json"
        payload_path.write_bytes(canonical)
        result = _run_ssh_keygen(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-q",
                "-f",
                str(key_path),
                "-n",
                SSH_SIGNATURE_NAMESPACE,
                str(payload_path),
            ]
        )
        if result.returncode != 0:
            raise InvalidExecutionPermitError(
                f"failed to sign execution permit payload: {_process_detail(result)}"
            )
        signature_path = Path(f"{payload_path}.sig")
        if not signature_path.exists():
            raise InvalidExecutionPermitError("ssh-keygen did not produce an execution permit signature file")
        return signature_path.read_text(encoding="utf-8")


def validate_execution_permit(
    permit: ExecutionPermit,
    *,
    operation: str | None = None,
    required_capabilities: set[str] | None = None,
    requested_scope: str | None = None,
) -> ExecutionPermit:
    assert_global_not_frozen(permit.global_freeze_path)
    if permit.expires_at_utc <= datetime.now(UTC):
        raise InvalidExecutionPermitError(f"execution permit '{permit.permit_id}' is expired")
    if not permit.allowed_operations:
        raise InvalidExecutionPermitError("execution permit is missing allowed_operations")
    if not permit.capabilities:
        raise InvalidExecutionPermitError("execution permit is missing capabilities")
    if not permit.signature.strip():
        raise InvalidExecutionPermitError("execution permit is missing signature")

    _verify_permit_signature(permit)
    _validate_owner_review_artifact(permit)
    _validate_batch_approval_artifact(permit)

    effective_scope = requested_scope or permit.scope
    if not _scope_matches(permit.scope, effective_scope):
        raise InvalidExecutionPermitError(
            f"execution permit scope '{permit.scope}' does not allow requested scope '{effective_scope}'"
        )

    if operation is not None and not any(fnmatch(operation, allowed) for allowed in permit.allowed_operations):
        raise InvalidExecutionPermitError(
            f"execution permit '{permit.permit_id}' does not allow operation '{operation}'"
        )

    missing_capabilities = set(required_capabilities or set()) - set(permit.capabilities)
    if missing_capabilities:
        missing = ", ".join(sorted(missing_capabilities))
        raise ExecutionCapabilityError(
            f"execution permit '{permit.permit_id}' is missing required capabilities: {missing}"
        )
    return permit


def resolve_execution_permit(execution_permit: ExecutionPermit | None = None) -> ExecutionPermit:
    if execution_permit is not None:
        return execution_permit
    current = get_current_execution_context()
    if current is not None:
        return current.permit
    permit_path = getenv_compat(WORKER_PERMIT_PATH_ENV)
    if permit_path and permit_path.strip():
        return load_execution_permit(permit_path)
    raise MissingExecutionPermitError("no active execution permit is bound to the current execution context")


@contextmanager
def bind_execution_context(
    execution_permit: ExecutionPermit | None = None,
    *,
    operation: str,
    required_capabilities: set[str] | None = None,
    requested_scope: str | None = None,
) -> Iterator[ExecutionContext]:
    permit = resolve_execution_permit(execution_permit)
    effective_scope = requested_scope or permit.scope
    validate_execution_permit(
        permit,
        operation=operation,
        required_capabilities=required_capabilities,
        requested_scope=effective_scope,
    )
    context = ExecutionContext(
        permit=permit,
        operation=operation,
        requested_scope=effective_scope,
        started_at_utc=datetime.now(UTC),
    )
    token = _CURRENT_EXECUTION_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_EXECUTION_CONTEXT.reset(token)


def require_execution_context(
    *,
    operation: str,
    required_capabilities: set[str] | None = None,
    requested_scope: str | None = None,
) -> ExecutionContext:
    context = get_current_execution_context()
    if context is None:
        raise MissingExecutionPermitError(
            f"operation '{operation}' requires an active execution context but none is bound"
        )
    validate_execution_permit(
        context.permit,
        operation=operation,
        required_capabilities=required_capabilities,
        requested_scope=requested_scope or context.requested_scope,
    )
    return context


def get_current_execution_context() -> ExecutionContext | None:
    context = _CURRENT_EXECUTION_CONTEXT.get()
    if context is None:
        return None
    assert_global_not_frozen(context.permit.global_freeze_path)
    return context


def current_execution_capabilities() -> set[str]:
    context = get_current_execution_context()
    if context is None:
        return set()
    return set(context.permit.capabilities)


def acquire_execution_lease(
    permit: ExecutionPermit,
    *,
    permit_path: str | Path,
    operation: str,
    requested_scope: str,
    required_capabilities: set[str] | None = None,
    worker_pid: int | None = None,
) -> ExecutionLease:
    validate_execution_permit(
        permit,
        operation=operation,
        required_capabilities=required_capabilities,
        requested_scope=requested_scope,
    )
    pid = os.getpid() if worker_pid is None else worker_pid
    lease = ExecutionLease(
        lease_id=f"lease-{uuid4()}",
        permit_id=permit.permit_id,
        permit_path=str(Path(permit_path).resolve()),
        operation=operation,
        requested_scope=requested_scope,
        worker_pid=pid,
        acquired_at_utc=datetime.now(UTC),
        heartbeat_at_utc=datetime.now(UTC),
        expires_at_utc=permit.expires_at_utc,
        freeze_path=permit.global_freeze_path,
    )
    try:
        with _lease_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT status, lease_id FROM execution_leases WHERE permit_id = ?",
                (permit.permit_id,),
            ).fetchone()
            if existing is not None:
                status = str(existing[0])
                existing_lease_id = str(existing[1])
                raise ExecutionLeaseError(
                    f"execution permit '{permit.permit_id}' is already consumed by lease '{existing_lease_id}' with status '{status}'"
                )
            conn.execute(
                """
                INSERT INTO execution_leases (
                    permit_id,
                    lease_id,
                    permit_path,
                    operation,
                    requested_scope,
                    worker_pid,
                    status,
                    acquired_at_utc,
                    heartbeat_at_utc,
                    expires_at_utc,
                    freeze_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lease.permit_id,
                    lease.lease_id,
                    lease.permit_path,
                    lease.operation,
                    lease.requested_scope,
                    lease.worker_pid,
                    "active",
                    _format_utc_timestamp(lease.acquired_at_utc),
                    _format_utc_timestamp(lease.heartbeat_at_utc),
                    _format_utc_timestamp(lease.expires_at_utc),
                    lease.freeze_path,
                ),
            )
    except sqlite3.OperationalError as exc:
        raise ExecutionLeaseError(f"execution lease registry write failed: {exc}") from exc
    return lease


def heartbeat_execution_lease(lease: ExecutionLease) -> None:
    now = datetime.now(UTC)
    try:
        with _lease_connection() as conn:
            updated = conn.execute(
                """
                UPDATE execution_leases
                SET heartbeat_at_utc = ?
                WHERE lease_id = ? AND status = 'active'
                """,
                (_format_utc_timestamp(now), lease.lease_id),
            ).rowcount
    except sqlite3.OperationalError as exc:
        raise ExecutionLeaseError(f"execution lease heartbeat failed: {exc}") from exc
    if updated == 0:
        raise ExecutionLeaseError(f"execution lease '{lease.lease_id}' is no longer active")


def release_execution_lease(lease: ExecutionLease, *, status: str) -> None:
    try:
        with _lease_connection() as conn:
            updated = conn.execute(
                """
                UPDATE execution_leases
                SET status = ?, heartbeat_at_utc = ?
                WHERE lease_id = ?
                """,
                (status, _format_utc_timestamp(datetime.now(UTC)), lease.lease_id),
            ).rowcount
    except sqlite3.OperationalError as exc:
        raise ExecutionLeaseError(f"execution lease release failed: {exc}") from exc
    if updated == 0:
        raise ExecutionLeaseError(f"execution lease '{lease.lease_id}' does not exist")


def list_execution_leases(*, status: str | None = None) -> list[dict[str, Any]]:
    query = (
        """
        SELECT permit_id, lease_id, permit_path, operation, requested_scope, worker_pid,
               acquired_at_utc, heartbeat_at_utc, expires_at_utc, freeze_path, status
        FROM execution_leases
        """
    )
    params: tuple[object, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY acquired_at_utc ASC"
    try:
        with _lease_connection() as conn:
            rows = conn.execute(query, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise ExecutionLeaseError(f"execution lease registry read failed: {exc}") from exc
    return [_lease_row_to_record(row) for row in rows]


def snapshot_execution_lease_registry(
    *,
    registry_path: str | Path | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    resolved_path = Path(registry_path or getenv_compat(LEASE_REGISTRY_PATH_ENV) or default_lease_registry_path()).resolve()
    snapshot: dict[str, Any] = {
        "registry_path": str(resolved_path),
        "exists": resolved_path.exists(),
        "size_bytes": None,
        "last_modified_utc": None,
        "status_filter": status,
        "leases": [],
        "read_error": None,
    }
    if not resolved_path.exists():
        return snapshot

    stat = resolved_path.stat()
    snapshot["size_bytes"] = stat.st_size
    snapshot["last_modified_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    if stat.st_size == 0:
        return snapshot

    query = (
        """
        SELECT permit_id, lease_id, permit_path, operation, requested_scope, worker_pid,
               acquired_at_utc, heartbeat_at_utc, expires_at_utc, freeze_path, status
        FROM execution_leases
        """
    )
    params: tuple[object, ...] = ()
    if status is not None:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY acquired_at_utc ASC"
    try:
        conn = sqlite3.connect(f"file:{resolved_path.as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        snapshot["read_error"] = str(exc)
        return snapshot

    snapshot["leases"] = [_lease_row_to_record(row) for row in rows]
    return snapshot


def cleanup_orphan_execution_leases(
    *,
    stale_after_seconds: float = WORKER_LEASE_STALE_SECONDS,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    stale_before = now - timedelta(seconds=stale_after_seconds)
    cleaned: list[dict[str, Any]] = []
    try:
        with _lease_connection() as conn:
            rows = conn.execute(
                """
                SELECT permit_id, lease_id, permit_path, operation, requested_scope, worker_pid,
                       acquired_at_utc, heartbeat_at_utc, expires_at_utc, freeze_path, status
                FROM execution_leases
                WHERE status = 'active'
                """
            ).fetchall()
            for row in rows:
                record = _lease_row_to_record(row)
                lease_id = str(record["lease_id"])
                new_status = None
                reason = None
                expires_at = _parse_utc_timestamp(record["expires_at_utc"], field_name="expires_at_utc")
                heartbeat_at = _parse_utc_timestamp(record["heartbeat_at_utc"], field_name="heartbeat_at_utc")
                worker_pid = int(record["worker_pid"])
                worker_pid_state = probe_process_state(worker_pid)
                heartbeat_age_seconds = max(0.0, (now - heartbeat_at).total_seconds())
                if expires_at <= now:
                    new_status = "expired"
                    reason = "permit_expired"
                elif worker_pid_state != "alive":
                    new_status = "orphaned"
                    reason = "worker_pid_not_alive"
                elif heartbeat_at < stale_before:
                    new_status = "orphaned"
                    reason = "heartbeat_stale"
                if new_status is None:
                    continue
                updated = conn.execute(
                    """
                    UPDATE execution_leases
                    SET status = ?, heartbeat_at_utc = ?
                    WHERE lease_id = ? AND status = 'active'
                    """,
                    (
                        new_status,
                        _format_utc_timestamp(now),
                        lease_id,
                    ),
                ).rowcount
                if updated == 0:
                    continue
                cleaned.append(
                    {
                        **record,
                        "status": new_status,
                        "cleanup_reason": reason,
                        "heartbeat_age_seconds": round(heartbeat_age_seconds, 3),
                        "worker_pid_state": worker_pid_state,
                        "cleaned_at_utc": _format_utc_timestamp(now),
                    }
                )
    except sqlite3.OperationalError as exc:
        raise ExecutionLeaseError(f"execution lease cleanup failed: {exc}") from exc
    return cleaned


def require_active_worker_lease(
    *,
    operation: str,
    required_capabilities: set[str] | None = None,
    requested_scope: str | None = None,
    allowed_entrypoints: set[str] | None = None,
) -> ExecutionLease:
    require_worker_not_interrupted()
    if getenv_compat(WORKER_MODE_ENV) != "1":
        raise ExecutionLeaseError(f"operation '{operation}' requires the runtime worker execution boundary")
    if allowed_entrypoints:
        _require_worker_entrypoint(operation=operation, allowed_entrypoints=allowed_entrypoints)
    lease_id = getenv_compat(WORKER_LEASE_ID_ENV)
    if lease_id is None or not lease_id.strip():
        raise ExecutionLeaseError(f"operation '{operation}' requires an active worker lease")
    permit_path = getenv_compat(WORKER_PERMIT_PATH_ENV)
    if permit_path is None or not permit_path.strip():
        raise ExecutionLeaseError(f"operation '{operation}' requires a bound worker permit path")
    lease = _load_execution_lease(lease_id.strip())
    if lease.worker_pid != os.getpid():
        raise ExecutionLeaseError(
            f"execution lease '{lease.lease_id}' belongs to pid {lease.worker_pid}, not current pid {os.getpid()}"
        )
    permit = load_execution_permit(permit_path)
    if permit.permit_id != lease.permit_id:
        raise ExecutionLeaseError(
            f"worker lease '{lease.lease_id}' is bound to permit '{lease.permit_id}', not '{permit.permit_id}'"
        )
    validate_execution_permit(
        permit,
        operation=operation,
        required_capabilities=required_capabilities,
        requested_scope=requested_scope or lease.requested_scope,
    )
    return lease


def mark_worker_interrupted(reason: str) -> None:
    global _WORKER_INTERRUPT_REASON
    with _WORKER_INTERRUPT_LOCK:
        _WORKER_INTERRUPT_REASON = str(reason)


def clear_worker_interrupted() -> None:
    global _WORKER_INTERRUPT_REASON
    with _WORKER_INTERRUPT_LOCK:
        _WORKER_INTERRUPT_REASON = None


def get_worker_interrupt_reason() -> str | None:
    with _WORKER_INTERRUPT_LOCK:
        return _WORKER_INTERRUPT_REASON


def require_worker_not_interrupted() -> None:
    reason = get_worker_interrupt_reason()
    if reason is not None:
        raise ExecutionLeaseError(f"runtime worker execution was interrupted: {reason}")


def trigger_global_freeze(
    *,
    reason: str,
    freeze_path: str | Path | None = None,
    details: dict[str, Any] | None = None,
) -> Path:
    target = _resolve_freeze_path(freeze_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "frozen": True,
        "reason": reason,
        "triggered_at_utc": _format_utc_timestamp(datetime.now(UTC)),
        "details": details or {},
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def clear_global_freeze(freeze_path: str | Path | None = None) -> None:
    target = _resolve_freeze_path(freeze_path)
    if target.exists():
        target.unlink()


def assert_global_not_frozen(freeze_path: str | Path | None = None) -> None:
    target = _resolve_freeze_path(freeze_path)
    if not target.exists():
        return
    payload = json.loads(target.read_text(encoding="utf-8"))
    if bool(payload.get("frozen", True)):
        reason = payload.get("reason", "global freeze active")
        raise GlobalFreezeActiveError(f"global execution freeze is active: {reason}")


def default_trust_root_dir() -> Path:
    base = Path(os.getenv("PROGRAMDATA") or (Path.home() / "AppData" / "Local"))
    return (base / "EnhengClaw" / "trust").resolve()


def resolve_allowed_signers_path() -> Path:
    trust_root = Path(getenv_compat(TRUST_ROOT_DIR_ENV) or default_trust_root_dir()).resolve()
    allowed_signers = trust_root / "allowed_signers"
    _assert_trust_root_secure(allowed_signers)
    return allowed_signers


def default_lease_registry_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return (base / "EnhengClaw" / "runtime" / "execution_leases.sqlite3").resolve()


def _resolve_permit_path(path: str | Path | None) -> Path:
    candidate = path or getenv_compat(EXECUTION_PERMIT_PATH_ENV)
    if candidate is None or not str(candidate).strip():
        raise MissingExecutionPermitError(
            f"missing execution permit path; provide a path or set {env_aliases_text(EXECUTION_PERMIT_PATH_ENV)}"
        )
    resolved = Path(candidate).resolve()
    if not resolved.exists():
        raise MissingExecutionPermitError(f"execution permit file does not exist: {resolved}")
    return resolved


def _resolve_freeze_path(path: str | Path | None) -> Path:
    if path is None or not str(path).strip():
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return (base / "EnhengClaw" / "runtime" / "global_freeze.json").resolve()
    return Path(path).resolve()


def _assert_trust_root_secure(allowed_signers_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    trust_root_dir = allowed_signers_path.parent
    if _is_relative_to(allowed_signers_path, repo_root):
        raise InvalidExecutionPermitError(
            f"execution trust root must be external to the repository workspace: {allowed_signers_path}"
        )
    if not allowed_signers_path.exists():
        raise MissingExecutionPermitError(
            f"execution permit allowed signers file does not exist: {allowed_signers_path}"
        )
    if getenv_compat(ALLOW_WRITABLE_TRUST_ROOT_ENV) != "1":
        if _runtime_user_can_write_path(allowed_signers_path):
            raise InvalidExecutionPermitError(
                f"execution trust root must be read-only to the runtime user: {allowed_signers_path}"
            )
        if _runtime_user_can_write_path(trust_root_dir):
            raise InvalidExecutionPermitError(
                f"execution trust root directory must be read-only to the runtime user: {trust_root_dir}"
            )


def _runtime_user_can_write_path(path: Path) -> bool:
    if path.is_dir():
        probe = path / f".trust_write_probe_{uuid4().hex}"
        try:
            probe.write_text("probe", encoding="utf-8")
            return True
        except OSError:
            return False
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        with path.open("a", encoding="utf-8"):
            pass
        return True
    except OSError:
        return False


def _verify_permit_signature(permit: ExecutionPermit) -> None:
    allowed_signers_path = resolve_allowed_signers_path()
    signer_identity = permit.signer_identity.strip()
    if not signer_identity:
        raise InvalidExecutionPermitError("execution permit is missing signer_identity")
    canonical = _canonical_payload(permit.to_payload(include_signature=False))
    with tempfile.TemporaryDirectory() as tmpdir:
        signature_path = Path(tmpdir) / "execution_permit.sig"
        signature_path.write_text(permit.signature, encoding="utf-8")
        result = _run_ssh_keygen(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-q",
                "-f",
                str(allowed_signers_path),
                "-I",
                signer_identity,
                "-n",
                SSH_SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path),
            ],
            input_bytes=canonical,
        )
        if result.returncode != 0:
            raise InvalidExecutionPermitError(
                f"execution permit '{permit.permit_id}' has an invalid signature: {_process_detail(result)}"
            )


@contextmanager
def _lease_connection() -> Iterator[sqlite3.Connection]:
    registry_path = Path(getenv_compat(LEASE_REGISTRY_PATH_ENV) or default_lease_registry_path()).resolve()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(registry_path, timeout=30, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _ensure_lease_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_lease_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_leases (
            permit_id TEXT PRIMARY KEY,
            lease_id TEXT NOT NULL UNIQUE,
            permit_path TEXT NOT NULL,
            operation TEXT NOT NULL,
            requested_scope TEXT NOT NULL,
            worker_pid INTEGER NOT NULL,
            status TEXT NOT NULL,
            acquired_at_utc TEXT NOT NULL,
            heartbeat_at_utc TEXT NOT NULL,
            expires_at_utc TEXT NOT NULL,
            freeze_path TEXT
        )
        """
    )


def _load_execution_lease(lease_id: str) -> ExecutionLease:
    try:
        with _lease_connection() as conn:
            row = conn.execute(
                """
                SELECT permit_id, lease_id, permit_path, operation, requested_scope, worker_pid,
                       acquired_at_utc, heartbeat_at_utc, expires_at_utc, freeze_path, status
                FROM execution_leases
                WHERE lease_id = ?
                """,
                (lease_id,),
            ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ExecutionLeaseError(f"execution lease registry read failed: {exc}") from exc
    if row is None:
        raise ExecutionLeaseError(f"execution lease '{lease_id}' does not exist")
    status = str(row[10])
    if status != "active":
        raise ExecutionLeaseError(f"execution lease '{lease_id}' is not active (status={status})")
    lease = ExecutionLease(
        permit_id=str(row[0]),
        lease_id=str(row[1]),
        permit_path=str(row[2]),
        operation=str(row[3]),
        requested_scope=str(row[4]),
        worker_pid=int(row[5]),
        acquired_at_utc=_parse_utc_timestamp(row[6], field_name="acquired_at_utc"),
        heartbeat_at_utc=_parse_utc_timestamp(row[7], field_name="heartbeat_at_utc"),
        expires_at_utc=_parse_utc_timestamp(row[8], field_name="expires_at_utc"),
        freeze_path=None if row[9] in {None, ""} else str(row[9]),
    )
    if lease.expires_at_utc <= datetime.now(UTC):
        raise ExecutionLeaseError(f"execution lease '{lease.lease_id}' is expired")
    assert_global_not_frozen(lease.freeze_path)
    return lease


def _require_worker_entrypoint(*, operation: str, allowed_entrypoints: set[str]) -> None:
    current_entrypoint = _current_main_entrypoint()
    if current_entrypoint in allowed_entrypoints:
        return
    allowed_text = ", ".join(sorted(allowed_entrypoints))
    observed = current_entrypoint or "<unknown>"
    raise ExecutionLeaseError(
        f"operation '{operation}' requires worker entrypoint [{allowed_text}], observed '{observed}'"
    )


def _current_main_entrypoint() -> str | None:
    main_module = sys.modules.get("__main__")
    if main_module is None:
        return None
    spec = getattr(main_module, "__spec__", None)
    name = getattr(spec, "name", None)
    if isinstance(name, str) and name.strip():
        return name
    file_path = getattr(main_module, "__file__", None)
    if isinstance(file_path, str) and file_path.strip():
        return Path(file_path).stem
    return None


def process_exists(pid: int) -> bool:
    return probe_process_state(pid) == "alive"


def probe_process_state(raw_pid: object) -> str:
    if isinstance(raw_pid, bool):
        return "invalid"
    try:
        pid = int(raw_pid)
    except (TypeError, ValueError):
        return "invalid"
    if pid <= 0:
        return "invalid"
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if handle == 0:
            return "alive" if ctypes.get_last_error() == ERROR_ACCESS_DENIED else "not_alive"
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) == 0:
                return "alive"
            return "alive" if exit_code.value == STILL_ACTIVE else "not_alive"
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return "alive"
    except OSError:
        return "not_alive"
    return "alive"


def _lease_row_to_record(row: tuple[object, ...]) -> dict[str, Any]:
    return {
        "permit_id": str(row[0]),
        "lease_id": str(row[1]),
        "permit_path": str(row[2]),
        "operation": str(row[3]),
        "requested_scope": str(row[4]),
        "worker_pid": int(row[5]),
        "acquired_at_utc": str(row[6]),
        "heartbeat_at_utc": str(row[7]),
        "expires_at_utc": str(row[8]),
        "freeze_path": None if row[9] in {None, ""} else str(row[9]),
        "status": str(row[10]),
    }


def _run_ssh_keygen(
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            arguments,
            input=input_bytes,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MissingExecutionPermitError("ssh-keygen is required for execution permit verification") from exc


def _process_detail(result: subprocess.CompletedProcess[bytes]) -> str:
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    if stderr:
        return stderr
    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    if stdout:
        return stdout
    return f"exit code {result.returncode}"


def _validate_owner_review_artifact(permit: ExecutionPermit) -> None:
    path = _coerce_cross_platform_ref_path(permit.owner_review_ref).resolve()
    if not path.exists():
        raise InvalidExecutionPermitError(f"owner review artifact does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    status = str(payload.get("status", "")).strip().lower()
    if status != "passed":
        raise InvalidExecutionPermitError(f"owner review artifact '{path}' is not passed")
    recorded_scope = str(payload.get("scope", permit.scope))
    if not _scope_matches(recorded_scope, permit.scope):
        raise InvalidExecutionPermitError(
            f"owner review scope '{recorded_scope}' does not match execution permit scope '{permit.scope}'"
        )


def _validate_batch_approval_artifact(permit: ExecutionPermit) -> None:
    path = _coerce_cross_platform_ref_path(permit.batch_approval_ref).resolve()
    if not path.exists():
        raise InvalidExecutionPermitError(f"batch approval artifact does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("approved") is not True:
        raise InvalidExecutionPermitError(f"batch approval artifact '{path}' is not approved")
    batch_id = str(payload.get("batch_id", "")).strip()
    if batch_id != permit.batch_id:
        raise InvalidExecutionPermitError(
            f"batch approval batch_id '{batch_id}' does not match execution permit batch_id '{permit.batch_id}'"
        )
    recorded_scope = str(payload.get("scope", permit.scope))
    if not _scope_matches(recorded_scope, permit.scope):
        raise InvalidExecutionPermitError(
            f"batch approval scope '{recorded_scope}' does not match execution permit scope '{permit.scope}'"
        )
    _parse_utc_timestamp(payload.get("timestamp_utc"), field_name="timestamp_utc")


def _scope_matches(permit_scope: str, requested_scope: str) -> bool:
    if permit_scope == DEFAULT_SCOPE_WILDCARD:
        return True
    return permit_scope == requested_scope


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _coerce_cross_platform_ref_path(value: str | Path) -> Path:
    text = str(value)
    if os.name != "nt" and len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"}:
        windows = PureWindowsPath(text)
        drive = windows.drive[0].lower()
        tail = "/".join(windows.parts[1:])
        return Path(f"/mnt/{drive}/{tail}") if tail else Path(f"/mnt/{drive}")
    if os.name == "nt" and text.startswith("/mnt/") and len(text) > 7 and text[5].isalpha() and text[6] == "/":
        drive = text[5].upper()
        suffix = text[7:].replace("/", "\\")
        return Path(f"{drive}:\\{suffix}")
    return Path(text)


def _parse_utc_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InvalidExecutionPermitError(f"execution control field '{field_name}' must be a non-empty UTC timestamp")
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).astimezone(UTC)
    except ValueError as exc:
        raise InvalidExecutionPermitError(
            f"execution control field '{field_name}' must be an ISO-8601 UTC timestamp"
        ) from exc


def _format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
