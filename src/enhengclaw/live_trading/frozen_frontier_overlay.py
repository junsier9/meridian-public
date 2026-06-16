"""frozen_frontier_overlay — the dth60 q90/crowded-zero risk overlay as a FROZEN
PIT rule applied AFTER frontier scoring.

Rule (research-frozen): on a row, the distance_to_high_60 factor's contribution is
multiplied by 0.0 (zeroed) when
    (shock_co_occurrence_index >= train_q90) OR (co_jump_count_3d >= train_q90)
    OR (rank_pct(distance_to_high_60) >= 0.75 AND rank_pct(coinglass_top_trader_long_pct_smooth_5) >= 0.80)
else multiplied by 1.0. ONLY distance_to_high_60 is affected; every other factor's
contribution is unchanged. The overlay carries NO factor weights of its own
(reuses the frozen frontier vector).

q90 thresholds MUST come from a PIT train window (decision row excluded); synthetic
thresholds are forbidden for live. This module provides the trigger + fail-closed
validation; the raw-score zeroing is wired into the scorer at integration time.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "hv_balanced_dth60_shock_q90_or_crowded_top20_overlay.v1"
OVERLAY_ID = "dth60_hybrid_shock_q90_or_crowded_top20_zero"
TARGET_FACTOR = "distance_to_high_60"
CROWDED_FACTOR = "coinglass_top_trader_long_pct_smooth_5"
NEAR_HIGH_RANK_GATE = 0.75
CROWDED_RANK_GATE = 0.80


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_overlay_contract(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists() or not resolved.is_file():
        return {}
    try:
        return dict(json.loads(resolved.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return {}


def overlay_spec_hash(contract: dict[str, Any]) -> str:
    subset = {
        "overlay_id": contract.get("overlay_id"),
        "target_factor": contract.get("target_factor"),
        "multiplier_on_trigger": contract.get("multiplier_on_trigger"),
        "multiplier_off_trigger": contract.get("multiplier_off_trigger"),
        "trigger_rule": contract.get("trigger_rule"),
        "gauges": contract.get("gauges"),
        "threshold_contract": contract.get("threshold_contract"),
    }
    return hashlib.sha256(
        json.dumps(subset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def compute_overlay_trigger(
    *,
    shock_co_occurrence_index: Any,
    co_jump_count_3d: Any,
    shock_q90: Any,
    co_jump_q90: Any,
    distance_to_high_60_rank_pct: Any,
    coinglass_top_trader_rank_pct: Any,
) -> dict[str, Any]:
    """Return the trigger booleans. Fail-closed semantics belong to the caller:
    a missing/non-finite gauge here yields branch=False, so the CALLER must
    independently BLOCK on missing gauges (never silently treat as no-trigger)."""
    shock = _finite(shock_co_occurrence_index)
    sq = _finite(shock_q90)
    cj = _finite(co_jump_count_3d)
    cq = _finite(co_jump_q90)
    shock_branch = bool(shock is not None and sq is not None and shock >= sq)
    cojump_branch = bool(cj is not None and cq is not None and cj >= cq)
    dh = _finite(distance_to_high_60_rank_pct)
    tt = _finite(coinglass_top_trader_rank_pct)
    crowded_branch = bool(
        dh is not None and tt is not None and dh >= NEAR_HIGH_RANK_GATE and tt >= CROWDED_RANK_GATE
    )
    triggered = shock_branch or cojump_branch or crowded_branch
    return {
        "triggered": triggered,
        "shock_branch": shock_branch,
        "cojump_branch": cojump_branch,
        "crowded_branch": crowded_branch,
        "target_multiplier": 0.0 if triggered else 1.0,
    }


def validate_thresholds_pit(thresholds_meta: dict[str, Any]) -> list[str]:
    """Fail-closed PIT checks on how the q90 thresholds were produced."""
    blockers: list[str] = []
    m = dict(thresholds_meta or {})
    if not bool(m.get("from_input_panel")):
        blockers.append("overlay_thresholds_not_from_input_panel")  # synthetic banned
    if bool(m.get("train_includes_decision_row")):
        blockers.append("overlay_thresholds_train_includes_decision_row")
    if not bool(m.get("current_row_excluded")):
        blockers.append("overlay_thresholds_current_row_not_excluded")
    if _finite(m.get("shock_co_occurrence_index_q90")) is None:
        blockers.append("overlay_shock_q90_unreadable")
    if _finite(m.get("co_jump_count_3d_q90")) is None:
        blockers.append("overlay_co_jump_q90_unreadable")
    return sorted(set(blockers))


def validate_overlay_contract(
    *,
    path: str | Path | None,
    expected_file_sha256: str | None = None,
    expected_spec_hash: str | None = None,
    require_configured: bool = True,
) -> dict[str, Any]:
    blockers: list[str] = []
    resolved = Path(path) if path else None
    if resolved is None or not resolved.exists() or not resolved.is_file():
        if require_configured:
            blockers.append("overlay_contract_path_missing")
        return {"status": "blocked" if blockers else "not_configured",
                "passed": not blockers, "blockers": blockers, "spec_hash": None}
    contract = load_overlay_contract(resolved)
    if not contract:
        return {"status": "blocked", "passed": False,
                "blockers": ["overlay_contract_unreadable"], "spec_hash": None}

    actual_file_sha = file_sha256(resolved)
    if expected_file_sha256 and actual_file_sha != str(expected_file_sha256):
        blockers.append("overlay_file_sha256_mismatch")
    actual_spec = overlay_spec_hash(contract)
    embedded = str(contract.get("overlay_spec_hash") or "")
    if embedded and embedded != actual_spec:
        blockers.append("overlay_internal_spec_hash_mismatch")
    if expected_spec_hash and actual_spec != str(expected_spec_hash):
        blockers.append("overlay_spec_hash_mismatch")

    if str(contract.get("target_factor") or "") != TARGET_FACTOR:
        blockers.append("overlay_target_factor_not_distance_to_high_60")
    if bool(contract.get("has_own_factor_weights")):
        blockers.append("overlay_must_not_carry_own_factor_weights")
    if _finite(contract.get("multiplier_on_trigger")) != 0.0:
        blockers.append("overlay_multiplier_on_trigger_not_zero")
    if _finite(contract.get("multiplier_off_trigger")) != 1.0:
        blockers.append("overlay_multiplier_off_trigger_not_one")
    tc = dict(contract.get("threshold_contract") or {})
    if not bool(tc.get("requires_input_panel")):
        blockers.append("overlay_threshold_contract_must_require_input_panel")

    blockers = sorted(set(blockers))
    return {
        "status": "ready" if not blockers else "blocked",
        "passed": not blockers,
        "blockers": blockers,
        "file_sha256": actual_file_sha,
        "spec_hash": actual_spec,
        "overlay_id": str(contract.get("overlay_id") or ""),
    }
