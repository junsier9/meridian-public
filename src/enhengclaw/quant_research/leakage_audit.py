from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import portable_path, read_json
from .falsification_audit import raise_placeholder_audit_retired


ROOT = Path(__file__).resolve().parents[3]
LEAKAGE_AUDIT_CONTRACT_VERSION = "quant_leakage_audit.v1"
LEAKAGE_AUDIT_STATUSES = ("pending", "confirmed_leakage", "cleared", "inconclusive")


def leakage_audit_root(*, artifacts_root: Path) -> Path:
    return artifacts_root / "governance" / "leakage_audits"


def leakage_audit_path(*, artifacts_root: Path, as_of: str, alpha_id: str) -> Path:
    return leakage_audit_root(artifacts_root=artifacts_root) / as_of / f"{alpha_id}.leakage_audit.json"


def load_leakage_audit(*, artifacts_root: Path, as_of: str, alpha_id: str) -> dict[str, Any] | None:
    path = leakage_audit_path(artifacts_root=artifacts_root, as_of=as_of, alpha_id=alpha_id)
    if not path.exists():
        return None
    payload = read_json(path)
    payload["leakage_audit_path"] = portable_path(path, repo_root=ROOT)
    return payload


def leakage_audit_status(*, artifacts_root: Path, as_of: str, alpha_id: str) -> str | None:
    payload = load_leakage_audit(artifacts_root=artifacts_root, as_of=as_of, alpha_id=alpha_id)
    if payload is None:
        return None
    return str(payload.get("status") or "").strip() or None


def leakage_audit_is_required(
    *,
    alpha_card: dict[str, Any],
    quality_blockers: list[str] | None = None,
) -> bool:
    validation = str(alpha_card.get("validation") or "").strip()
    experiment_status = str(alpha_card.get("experiment_status") or "").strip()
    blockers = [str(item) for item in quality_blockers or alpha_card.get("quality_summary", {}).get("quality_blockers", [])]
    return (
        validation == "leakage_audit_required"
        or experiment_status == "quarantined"
        or any(item.startswith("sharpe_anomaly=") for item in blockers)
        or any(item.startswith("leakage_audit.") for item in blockers)
    )


def write_pending_leakage_audit(
    *,
    artifacts_root: Path,
    as_of: str,
    alpha_card_path: Path,
    alpha_card: dict[str, Any],
    quality_blockers: list[str] | None = None,
    overwrite_existing_pending: bool = False,
) -> dict[str, Any] | None:
    raise_placeholder_audit_retired()


def _audit_reason(*, blockers: list[str], alpha_card: dict[str, Any]) -> str:
    if any(item.startswith("sharpe_anomaly=") for item in blockers):
        return "sharpe_anomaly"
    if str(alpha_card.get("experiment_status") or "").strip() == "quarantined":
        return "quarantined_experiment"
    return "validation_requires_leakage_audit"
