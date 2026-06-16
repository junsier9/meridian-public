from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.testing.execution_testbed import execution_testbed
from enhengclaw.core.execution_control import (
    ALLOW_WRITABLE_TRUST_ROOT_ENV,
    InvalidExecutionPermitError,
    TRUST_ROOT_DIR_ENV,
    load_execution_permit,
)


def main() -> int:
    with execution_testbed() as bed:
        permit_path, permit = bed.issue_permit(
            slug="phase0",
            scope="spot+perp",
            capabilities=["runtime.execute"],
            allowed_operations=["runtime.*"],
        )
        assert load_execution_permit(permit_path).permit_id == permit.permit_id

        repo_trust_root = ROOT / "artifacts" / "verify_phase0_repo_trust"
        repo_trust_root.mkdir(parents=True, exist_ok=True)
        try:
            (repo_trust_root / "allowed_signers").write_text(
                (bed.trust_root / "allowed_signers").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            os.environ[TRUST_ROOT_DIR_ENV] = str(repo_trust_root)
            try:
                load_execution_permit(permit_path)
            except InvalidExecutionPermitError:
                pass
            else:
                raise AssertionError("repo-local trust root was accepted")
        finally:
            if (repo_trust_root / "allowed_signers").exists():
                (repo_trust_root / "allowed_signers").unlink()
            if repo_trust_root.exists():
                repo_trust_root.rmdir()

        os.environ[TRUST_ROOT_DIR_ENV] = str(bed.trust_root)
        os.environ.pop(ALLOW_WRITABLE_TRUST_ROOT_ENV, None)
        try:
            load_execution_permit(permit_path)
        except InvalidExecutionPermitError:
            return 0
        raise AssertionError("writable trust root was accepted without override")


if __name__ == "__main__":
    raise SystemExit(main())
