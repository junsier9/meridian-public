from __future__ import annotations

import os
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.core.execution_control import (
    CAP_RUNTIME_EXECUTE,
    WORKER_LEASE_ID_ENV,
    WORKER_MODE_ENV,
    WORKER_PERMIT_PATH_ENV,
    ExecutionLeaseError,
    GlobalFreezeActiveError,
        InvalidExecutionPermitError,
    acquire_execution_lease,
    clear_global_freeze,
    release_execution_lease,
    require_active_worker_lease,
    trigger_global_freeze,
)
from enhengclaw.testing.execution_testbed import execution_testbed


def main() -> int:
    with execution_testbed() as bed:
        freeze_path = bed.root / "global-freeze.json"
        permit_path, permit = bed.issue_permit(
            slug="phase3",
            scope="spot+perp",
            capabilities=[CAP_RUNTIME_EXECUTE],
            allowed_operations=["runtime.*"],
            expires_after=time_delta(seconds=2),
            global_freeze_path=freeze_path,
        )
        lease = acquire_execution_lease(
            permit,
            permit_path=permit_path,
            operation="runtime.verify.phase3.runtime",
            requested_scope="spot+perp",
            required_capabilities={CAP_RUNTIME_EXECUTE},
        )
        _saved = {
            WORKER_MODE_ENV: os.getenv(WORKER_MODE_ENV),
            WORKER_LEASE_ID_ENV: os.getenv(WORKER_LEASE_ID_ENV),
            WORKER_PERMIT_PATH_ENV: os.getenv(WORKER_PERMIT_PATH_ENV),
        }
        os.environ[WORKER_MODE_ENV] = "1"
        os.environ[WORKER_LEASE_ID_ENV] = lease.lease_id
        os.environ[WORKER_PERMIT_PATH_ENV] = str(permit_path)
        try:
            require_active_worker_lease(
                operation="runtime.verify.phase3.initial",
                required_capabilities={CAP_RUNTIME_EXECUTE},
                requested_scope="spot+perp",
            )
            try:
                acquire_execution_lease(
                    permit,
                    permit_path=permit_path,
                    operation="runtime.verify.phase3.replay",
                    requested_scope="spot+perp",
                    required_capabilities={CAP_RUNTIME_EXECUTE},
                )
            except ExecutionLeaseError:
                pass
            else:
                raise AssertionError("permit replay was accepted")

            trigger_global_freeze(reason="phase3-freeze", freeze_path=freeze_path)
            try:
                require_active_worker_lease(
                    operation="runtime.verify.phase3.freeze",
                    required_capabilities={CAP_RUNTIME_EXECUTE},
                    requested_scope="spot+perp",
                )
            except GlobalFreezeActiveError:
                pass
            else:
                raise AssertionError("global freeze did not interrupt active lease")
            clear_global_freeze(freeze_path)

            time.sleep(3.0)
            try:
                require_active_worker_lease(
                    operation="runtime.verify.phase3.expiry",
                    required_capabilities={CAP_RUNTIME_EXECUTE},
                    requested_scope="spot+perp",
                )
            except (ExecutionLeaseError, InvalidExecutionPermitError):
                return 0
            raise AssertionError("expired permit was still accepted")
        finally:
            try:
                release_execution_lease(lease, status="completed")
            except ExecutionLeaseError:
                pass
            for key, value in _saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def time_delta(*, seconds: int):
    from datetime import timedelta

    return timedelta(seconds=seconds)


if __name__ == "__main__":
    raise SystemExit(main())
