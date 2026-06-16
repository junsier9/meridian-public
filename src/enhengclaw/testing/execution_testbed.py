from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Iterator

from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon
from enhengclaw.core.execution_control import (
    ALLOW_WRITABLE_TRUST_ROOT_ENV,
    CAP_PROVIDER_FETCH,
    CAP_PROVIDER_STREAM,
    CAP_PROVIDER_TRANSPORT,
    CAP_RUNTIME_EXECUTE,
    LEASE_REGISTRY_PATH_ENV,
    RUNTIME_WORKER_ENTRYPOINT,
    TRUST_ROOT_DIR_ENV,
    ExecutionPermit,
    ExecutionLease,
    WORKER_LEASE_ID_ENV,
    WORKER_MODE_ENV,
    WORKER_PERMIT_PATH_ENV,
    acquire_execution_lease,
    issue_execution_permit,
    load_execution_permit,
    release_execution_lease,
)
from enhengclaw.core.session import RUNTIME_SESSION_ROOT_ENV
from enhengclaw.core.signals import Signal


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"


@dataclass(frozen=True, slots=True)
class ExecutionTestbed:
    root: Path
    trust_root: Path
    session_root: Path
    lease_registry_path: Path
    signing_private_key: Path

    def issue_permit(
        self,
        *,
        slug: str,
        scope: str,
        capabilities: list[str],
        allowed_operations: list[str],
        expires_after: timedelta = timedelta(hours=1),
        global_freeze_path: Path | None = None,
    ) -> tuple[Path, ExecutionPermit]:
        permit_root = self.root / slug
        permit_root.mkdir(parents=True, exist_ok=True)
        owner_review = permit_root / "owner_review.json"
        owner_review.write_text('{"status":"passed","scope":"%s"}' % scope, encoding="utf-8")
        batch_approval = permit_root / "batch_approval.json"
        batch_approval.write_text(
            '{"batch_id":"batch-test","scope":"%s","approved":true,"timestamp_utc":"%s"}'
            % (scope, datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")),
            encoding="utf-8",
        )
        permit_path = permit_root / "execution_permit.json"
        issue_execution_permit(
            permit_path=permit_path,
            signing_private_key_path=self.signing_private_key,
            batch_id="batch-test",
            scope=scope,
            issued_by="verification-script",
            owner_review_ref=owner_review,
            batch_approval_ref=batch_approval,
            allowed_operations=allowed_operations,
            capabilities=capabilities,
            expires_at_utc=datetime.now(UTC) + expires_after,
            global_freeze_path=global_freeze_path,
        )
        return permit_path, load_execution_permit(permit_path)


@dataclass(frozen=True, slots=True)
class RuntimeWorkerHarness:
    testbed: ExecutionTestbed
    permit_path: Path
    permit: ExecutionPermit
    lease: ExecutionLease


@contextmanager
def execution_testbed() -> Iterator[ExecutionTestbed]:
    with tempfile.TemporaryDirectory(prefix="enhengclaw_verify_", ignore_cleanup_errors=True) as tmpdir:
        root = Path(tmpdir)
        trust_root = root / "trust-root"
        trust_root.mkdir(parents=True, exist_ok=True)
        session_root = root / "runtime-sessions"
        session_root.mkdir(parents=True, exist_ok=True)
        lease_registry_path = root / "execution-leases.sqlite3"
        signing_private_key = root / "execution_signer"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(signing_private_key),
            ],
            check=True,
            capture_output=True,
        )
        public_key = signing_private_key.with_suffix(".pub").read_text(encoding="utf-8").strip()
        (trust_root / "allowed_signers").write_text("execution-permit %s\n" % public_key, encoding="utf-8")
        saved_env = {
            TRUST_ROOT_DIR_ENV: os.getenv(TRUST_ROOT_DIR_ENV),
            ALLOW_WRITABLE_TRUST_ROOT_ENV: os.getenv(ALLOW_WRITABLE_TRUST_ROOT_ENV),
            LEASE_REGISTRY_PATH_ENV: os.getenv(LEASE_REGISTRY_PATH_ENV),
            RUNTIME_SESSION_ROOT_ENV: os.getenv(RUNTIME_SESSION_ROOT_ENV),
        }
        os.environ[TRUST_ROOT_DIR_ENV] = str(trust_root)
        os.environ[ALLOW_WRITABLE_TRUST_ROOT_ENV] = "1"
        os.environ[LEASE_REGISTRY_PATH_ENV] = str(lease_registry_path)
        os.environ[RUNTIME_SESSION_ROOT_ENV] = str(session_root)
        try:
            yield ExecutionTestbed(
                root=root,
                trust_root=trust_root,
                session_root=session_root,
                lease_registry_path=lease_registry_path,
                signing_private_key=signing_private_key,
            )
        finally:
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


@contextmanager
def runtime_worker_harness(
    *,
    slug: str = "runtime-worker",
    scope: str = "*",
    capabilities: list[str] | None = None,
    allowed_operations: list[str] | None = None,
    expires_after: timedelta = timedelta(hours=1),
) -> Iterator[RuntimeWorkerHarness]:
    requested_capabilities = capabilities or [
        CAP_RUNTIME_EXECUTE,
        CAP_PROVIDER_FETCH,
        CAP_PROVIDER_STREAM,
        CAP_PROVIDER_TRANSPORT,
    ]
    requested_operations = allowed_operations or ["*"]

    with execution_testbed() as testbed:
        permit_path, permit = testbed.issue_permit(
            slug=slug,
            scope=scope,
            capabilities=requested_capabilities,
            allowed_operations=requested_operations,
            expires_after=expires_after,
        )
        lease = acquire_execution_lease(
            permit,
            permit_path=permit_path,
            operation="runtime.worker.test_harness",
            requested_scope=scope,
            required_capabilities={CAP_RUNTIME_EXECUTE},
        )

        saved_env = {
            WORKER_MODE_ENV: os.getenv(WORKER_MODE_ENV),
            WORKER_PERMIT_PATH_ENV: os.getenv(WORKER_PERMIT_PATH_ENV),
            WORKER_LEASE_ID_ENV: os.getenv(WORKER_LEASE_ID_ENV),
        }
        main_module = sys.modules.get("__main__")
        saved_main_spec = None if main_module is None else getattr(main_module, "__spec__", None)
        os.environ[WORKER_MODE_ENV] = "1"
        os.environ[WORKER_PERMIT_PATH_ENV] = str(permit_path)
        os.environ[WORKER_LEASE_ID_ENV] = lease.lease_id
        if main_module is not None:
            main_module.__spec__ = SimpleNamespace(name=RUNTIME_WORKER_ENTRYPOINT)

        try:
            yield RuntimeWorkerHarness(
                testbed=testbed,
                permit_path=permit_path,
                permit=permit,
                lease=lease,
            )
        finally:
            try:
                release_execution_lease(lease, status="completed")
            except Exception:
                pass
            if main_module is not None:
                main_module.__spec__ = saved_main_spec
            for key, value in saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def sample_signals(prefix: str) -> list[Signal]:
    return [
        Signal(
            f"{prefix}-1",
            ObjectType.ASSET,
            "AIX",
            "spot_breakout",
            "spot volume expansion",
            ClaimType.MEASUREMENT,
            Direction.BULLISH,
            SourceFamily.CEX,
            EvidenceLevel.E4,
            82,
            time_horizon=TimeHorizon.INTRADAY,
        ),
        Signal(
            f"{prefix}-2",
            ObjectType.ASSET,
            "AIX",
            "wallet_buy",
            "smart money buying",
            ClaimType.FLOW,
            Direction.BULLISH,
            SourceFamily.ONCHAIN,
            EvidenceLevel.E4,
            78,
            time_horizon=TimeHorizon.INTRADAY,
        ),
    ]
