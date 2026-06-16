from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import utc_now


LEGACY_QUANT_SURFACE_ERROR_CODE = "legacy_quant_surface_frozen"
LEGACY_QUANT_SURFACE_EXIT_CODE = 78


class LegacyQuantSurfaceFrozenError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        as_of: str | None = None,
        artifacts_root: Path | None = None,
        workbench_root: Path | None = None,
    ) -> None:
        self.operation = str(operation or "").strip() or "legacy_operation"
        self.as_of = str(as_of or "").strip() or None
        self.artifacts_root = None if artifacts_root is None else str(Path(artifacts_root).expanduser().resolve())
        self.workbench_root = None if workbench_root is None else str(Path(workbench_root).expanduser().resolve())
        message = (
            f"{LEGACY_QUANT_SURFACE_ERROR_CODE}: operation={self.operation} "
            "is frozen; deterministic quant core no longer permits legacy writes"
        )
        super().__init__(message)


def legacy_surface_summary(
    *,
    operation: str,
    as_of: str | None = None,
    artifacts_root: Path | None = None,
    workbench_root: Path | None = None,
) -> dict[str, Any]:
    return {
        "status": "frozen",
        "success": False,
        "error_code": LEGACY_QUANT_SURFACE_ERROR_CODE,
        "operation": str(operation or "").strip() or "legacy_operation",
        "as_of": str(as_of or "").strip() or None,
        "produced_at_utc": utc_now(),
        "artifacts_root": None if artifacts_root is None else str(Path(artifacts_root).expanduser().resolve()),
        "workbench_root": None if workbench_root is None else str(Path(workbench_root).expanduser().resolve()),
        "message": "Deterministic quant core is active; legacy quant write paths are frozen.",
    }


def raise_legacy_surface_frozen(
    *,
    operation: str,
    as_of: str | None = None,
    artifacts_root: Path | None = None,
    workbench_root: Path | None = None,
) -> None:
    raise LegacyQuantSurfaceFrozenError(
        operation=operation,
        as_of=as_of,
        artifacts_root=artifacts_root,
        workbench_root=workbench_root,
    )
