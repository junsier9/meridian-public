"""frozen_frontier_contract — load + fail-closed validation of the FROZEN 12-factor
frontier weight contract for the live path.

Principle (owner, 2026-06-09): going live must NOT modify research factor weights.
The live 12-factor frontier consumes a single FROZEN signed-IR weight vector, pinned
verbatim from a named promotion alpha card, NEVER the latest_wfo_carry_forward
diagnostic (which is research_exact_parity=false and sign-flips
funding_basis_residual_implied_repo_30).

This module is the analogue of the existing frozen_config_sha256 check
(mainnet_rebalance_plan_runner.py) but binds TWO hashes (file-level + content
spec-hash) plus 12-factor structural asserts and a carry-forward detector. It is
config/data only — no scoring, no orders.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


REQUIRED_FEATURE_COUNT = 12
CONTRACT_VERSION = "hv_balanced_12factor_frozen_frontier_weights.v1"
CONFIG_FLAG_SECTION = "strategy"
CONFIG_FLAG_KEY = "frontier"
# The carry-forward diagnostic vector sign-flipped this factor to +0.0184; the
# research frontier weight is strictly negative. Any frozen vector with this factor
# >= 0 is the forbidden carry-forward signature and must fail closed.
CARRY_FORWARD_SENTINEL_FACTOR = "funding_basis_residual_implied_repo_30"
_FUTURE_LABEL_SUBSTRINGS = ("forward_return", "target_execution", "future_", "label")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frozen_frontier(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    try:
        return dict(json.loads(resolved.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return {}


def frontier_spec_hash(contract: dict[str, Any]) -> str:
    """Content hash over ONLY {feature_columns, feature_weights} — the binding
    identity of the frozen vector, independent of provenance/comment fields."""
    subset = {
        "feature_columns": list(contract.get("feature_columns") or []),
        "feature_weights": dict(contract.get("feature_weights") or {}),
    }
    return hashlib.sha256(
        json.dumps(subset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def frontier_config(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(dict(payload.get(CONFIG_FLAG_SECTION) or {}).get(CONFIG_FLAG_KEY) or {})


def frontier_enabled(payload: dict[str, Any]) -> bool:
    value = frontier_config(payload).get("enabled")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def validate_frontier_contract(
    *,
    path: str | Path | None,
    expected_file_sha256: str | None = None,
    expected_spec_hash: str | None = None,
    require_configured: bool = True,
) -> dict[str, Any]:
    """Fail-closed validation. Every problem appends a blocker; status is
    ``ready`` only when there are none."""
    blockers: list[str] = []
    resolved = Path(path) if path else None
    if resolved is None or not resolved.exists() or not resolved.is_file():
        if require_configured:
            blockers.append("frontier_contract_path_missing")
        return {
            "status": "blocked" if blockers else "not_configured",
            "passed": not blockers,
            "blockers": blockers,
            "file_sha256": None,
            "spec_hash": None,
            "feature_count": 0,
        }

    contract = load_frozen_frontier(resolved)
    if not contract:
        blockers.append("frontier_contract_unreadable")
        return {"status": "blocked", "passed": False, "blockers": blockers,
                "file_sha256": None, "spec_hash": None, "feature_count": 0}

    actual_file_sha = file_sha256(resolved)
    if expected_file_sha256 and actual_file_sha != str(expected_file_sha256):
        blockers.append(
            f"frontier_file_sha256_mismatch:{actual_file_sha[:12]}!={str(expected_file_sha256)[:12]}"
        )

    columns = [str(c) for c in (contract.get("feature_columns") or [])]
    weights = dict(contract.get("feature_weights") or {})
    actual_spec = frontier_spec_hash(contract)
    # internal self-consistency: the embedded hash must match the recomputed one
    embedded = str(contract.get("frozen_frontier_spec_hash") or "")
    if embedded and embedded != actual_spec:
        blockers.append("frontier_internal_spec_hash_mismatch")
    if expected_spec_hash and actual_spec != str(expected_spec_hash):
        blockers.append(
            f"frontier_spec_hash_mismatch:{actual_spec[:12]}!={str(expected_spec_hash)[:12]}"
        )

    if len(columns) != REQUIRED_FEATURE_COUNT:
        blockers.append(f"frontier_feature_count_not_12:{len(columns)}")
    if set(columns) != set(weights.keys()):
        blockers.append("frontier_feature_columns_weights_key_mismatch")
    future = sorted(
        c for c in columns if any(sub in c for sub in _FUTURE_LABEL_SUBSTRINGS)
    )
    if future:
        blockers.append(f"frontier_contains_future_label_columns:{','.join(future)}")

    abs_sum = sum(abs(_finite(v) or 0.0) for v in weights.values())
    if not (abs_sum > 0.0):
        blockers.append("frontier_weights_abs_sum_zero")
    if any(_finite(v) is None for v in weights.values()):
        blockers.append("frontier_weights_non_finite")

    if not str(dict(contract.get("provenance") or {}).get("source_card_sha256") or "").strip():
        blockers.append("frontier_provenance_missing_source_card_sha256")

    # Carry-forward signature: the forbidden diagnostic vector flipped this factor
    # positive. Research frontier weight is strictly negative. Reject >= 0.
    cf = _finite(weights.get(CARRY_FORWARD_SENTINEL_FACTOR))
    if cf is None or cf >= 0.0:
        blockers.append(
            f"frontier_carry_forward_signature_detected:{CARRY_FORWARD_SENTINEL_FACTOR}={cf}"
        )

    blockers = sorted(set(blockers))
    return {
        "status": "ready" if not blockers else "blocked",
        "passed": not blockers,
        "blockers": blockers,
        "file_sha256": actual_file_sha,
        "spec_hash": actual_spec,
        "feature_count": len(columns),
        "abs_sum": float(abs_sum),
        "strategy_id": str(contract.get("strategy_id") or ""),
        "source_card_id": str(dict(contract.get("provenance") or {}).get("source_card_id") or ""),
    }
