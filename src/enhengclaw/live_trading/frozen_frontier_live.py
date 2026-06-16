"""frozen_frontier_live — the single source of truth that resolves whether the FROZEN
12-factor frontier (+ optional dth60 risk overlay) is *armed* for a live plan, and, if
so, the exact hash-pinned scoring inputs the live path must use.

Design contract (owner, 2026-06-09):
  * DEFAULT-OFF. With ``strategy.frontier.enabled`` falsey the resolution is ``dormant``
    and the live path is byte-for-byte the baseline 5-factor behaviour — no file IO, no
    contract load, nothing to go wrong.
  * FAIL-CLOSED WHEN ARMED. If the flag is on but ANY precondition fails (missing/unpinned
    hash, contract mismatch, carry-forward signature, synthetic overlay thresholds, scoring
    config that is not a real 12-factor frontier config, kill-switch/pause), the resolution
    is ``blocked`` with explicit blockers. It NEVER silently falls back to the baseline
    weights — the snapshot builder treats ``blocked`` as a hard stop.
  * ONE CHOKEPOINT, NO SPLIT-BRAIN. Both the single-phase plan runner and the multiphase
    twin call THIS function and pass the result into the one shared scorer
    (``build_live_hv_balanced_snapshot``). There is no second place to keep in sync.
  * ARM→SUBMIT BINDING. ``arm_binding`` is a digest over every hash-pinned input. The plan
    runner persists it; the delta-execution submit gate re-resolves and refuses to submit
    unless the freshly-resolved binding still matches and is still ``armed_ready``.
  * TERMINAL DISARM. Operator pause / kill-switch (``operator_state.paused``) forces the
    resolution ``blocked`` regardless of config — frontier cannot score under a kill-switch.

This module performs NO scoring and submits NO orders. It only validates + resolves.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from enhengclaw.live_trading.config import resolve_repo_path
from enhengclaw.live_trading.frozen_frontier_contract import (
    REQUIRED_FEATURE_COUNT,
    file_sha256 as contract_file_sha256,
    frontier_config,
    frontier_enabled,
    load_frozen_frontier,
    validate_frontier_contract,
)
from enhengclaw.live_trading.frozen_frontier_overlay import (
    OVERLAY_ID,
    TARGET_FACTOR,
    load_overlay_contract,
    validate_overlay_contract,
    validate_thresholds_pit,
)


FRONTIER_PLAN_ARTIFACT = "frontier_plan.json"
# Marks a scoring config as a genuine 12-factor frontier config (derivatives permitted),
# so an armed run can never silently point back at the 5-factor OHLCV baseline.
FRONTIER_SCORING_MARKER_KEY = "frontier_namespace"
FRONTIER_SCORING_MARKER_VALUE = "frozen_12factor_frontier"


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class FrontierResolution:
    """Immutable verdict for one live plan. ``status`` is the only thing callers branch on."""

    status: str  # "dormant" | "armed_ready" | "blocked"
    enabled: bool
    overlay_enabled: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    arm_binding: str | None = None
    feature_columns: list[str] = field(default_factory=list)
    weights_file_sha256: str | None = None
    weights_spec_hash: str | None = None
    overlay_spec_hash: str | None = None
    scoring_config_sha256: str | None = None
    effective_config_sha256: str | None = None
    terminal_disarm: bool = False
    # Heavy payloads consumed by the scorer; excluded from the persisted artifact / binding.
    effective_config: dict[str, Any] | None = field(default=None, repr=False)
    overlay_contract: dict[str, Any] | None = field(default=None, repr=False)
    overlay_thresholds: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def is_dormant(self) -> bool:
        return self.status == "dormant"

    @property
    def is_armed_ready(self) -> bool:
        return self.status == "armed_ready"

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    def to_artifact(self) -> dict[str, Any]:
        """Stable, hash-friendly view persisted as ``frontier_plan.json``. Excludes the
        bulky effective config / loaded contracts (their identity is captured by the
        recorded hashes + ``arm_binding``)."""
        return {
            "status": self.status,
            "enabled": self.enabled,
            "overlay_enabled": self.overlay_enabled,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "arm_binding": self.arm_binding,
            "feature_columns": list(self.feature_columns),
            "weights_file_sha256": self.weights_file_sha256,
            "weights_spec_hash": self.weights_spec_hash,
            "overlay_spec_hash": self.overlay_spec_hash,
            "scoring_config_sha256": self.scoring_config_sha256,
            "effective_config_sha256": self.effective_config_sha256,
            "terminal_disarm": self.terminal_disarm,
        }


def _dormant(*, enabled: bool = False) -> FrontierResolution:
    return FrontierResolution(status="dormant", enabled=enabled, overlay_enabled=False)


def _blocked(
    *,
    enabled: bool,
    overlay_enabled: bool,
    blockers: list[str],
    terminal_disarm: bool = False,
    **extra: Any,
) -> FrontierResolution:
    return FrontierResolution(
        status="blocked",
        enabled=enabled,
        overlay_enabled=overlay_enabled,
        blockers=sorted(set(blockers)),
        terminal_disarm=terminal_disarm,
        **extra,
    )


def resolve_frontier_live_plan(
    payload: dict[str, Any],
    *,
    operator_state: dict[str, Any] | None = None,
) -> FrontierResolution:
    """Resolve the frontier verdict for a live plan from the live-config ``payload``.

    ``operator_state`` is the ``state_store.read_operator_state()`` dict; it is REQUIRED
    when the flag is enabled (an unknown operator state while armed is itself fail-closed).
    """
    cfg = frontier_config(payload)
    enabled = frontier_enabled(payload)
    if not enabled:
        # Default-off: do not even touch the filesystem. Baseline path is untouched.
        return _dormant(enabled=False)

    overlay_cfg = dict(cfg.get("overlay") or {})
    overlay_enabled = _flag(overlay_cfg.get("enabled"))

    # --- Terminal disarm: kill-switch / pause forces blocked, never armed. ---
    if operator_state is None:
        return _blocked(
            enabled=True,
            overlay_enabled=overlay_enabled,
            blockers=["frontier_operator_state_unavailable"],
        )
    if bool(operator_state.get("paused")):
        last_action = str(operator_state.get("last_action_type") or "paused")
        return _blocked(
            enabled=True,
            overlay_enabled=overlay_enabled,
            blockers=[f"frontier_terminal_disarm_operator_paused_or_kill_switch:{last_action}"],
            terminal_disarm=True,
        )

    blockers: list[str] = []
    warnings: list[str] = []

    # --- Frozen frontier weight contract (hashes REQUIRED to arm). ---
    weights_path = _resolve_optional_path(cfg.get("weights_contract_path"))
    weights_file_sha = _clean(cfg.get("weights_file_sha256"))
    weights_spec_hash = _clean(cfg.get("weights_spec_hash"))
    if not weights_path:
        blockers.append("frontier_weights_contract_path_missing")
    if not weights_file_sha:
        blockers.append("frontier_weights_file_sha256_not_pinned")
    if not weights_spec_hash:
        blockers.append("frontier_weights_spec_hash_not_pinned")
    contract = load_frozen_frontier(weights_path) if weights_path else {}
    weight_result = validate_frontier_contract(
        path=weights_path,
        expected_file_sha256=weights_file_sha or None,
        expected_spec_hash=weights_spec_hash or None,
        require_configured=True,
    )
    if not weight_result.get("passed"):
        blockers.extend(weight_result.get("blockers") or [])
    feature_columns = [str(c) for c in (contract.get("feature_columns") or [])]
    feature_weights = dict(contract.get("feature_weights") or {})

    # --- 12-factor scoring config (前置-2): provides the scoring machinery the frozen
    #     weight vector is consumed by; pins everything except the weights themselves. ---
    scoring_path = _resolve_optional_path(cfg.get("scoring_config_path"))
    scoring_config_sha_expected = _clean(cfg.get("scoring_config_sha256"))
    scoring_config: dict[str, Any] = {}
    scoring_config_sha: str | None = None
    if not scoring_path:
        blockers.append("frontier_scoring_config_path_missing")
    elif not scoring_path.exists() or not scoring_path.is_file():
        blockers.append("frontier_scoring_config_not_found")
    else:
        try:
            scoring_config = dict(json.loads(scoring_path.read_text(encoding="utf-8-sig")))
        except (ValueError, TypeError):
            scoring_config = {}
            blockers.append("frontier_scoring_config_unreadable")
        scoring_config_sha = contract_file_sha256(scoring_path)
        if not scoring_config_sha_expected:
            blockers.append("frontier_scoring_config_sha256_not_pinned")
        elif scoring_config_sha != scoring_config_sha_expected:
            blockers.append(
                f"frontier_scoring_config_sha256_mismatch:{scoring_config_sha[:12]}!={scoring_config_sha_expected[:12]}"
            )
        if scoring_config:
            marker = str(scoring_config.get(FRONTIER_SCORING_MARKER_KEY) or "")
            if marker != FRONTIER_SCORING_MARKER_VALUE:
                # Guards against arming with the 5-factor OHLCV baseline by mistake.
                blockers.append("frontier_scoring_config_not_marked_frontier")
            scoring_columns = sorted(str(c) for c in (scoring_config.get("feature_columns") or []))
            if feature_columns and scoring_columns != sorted(feature_columns):
                blockers.append("frontier_scoring_config_columns_mismatch_with_weight_contract")
            if len(scoring_columns) != REQUIRED_FEATURE_COUNT:
                blockers.append(f"frontier_scoring_config_feature_count_not_12:{len(scoring_columns)}")

    # --- Optional dth60 risk overlay (independent sub-gate). ---
    overlay_spec_hash: str | None = None
    overlay_contract: dict[str, Any] | None = None
    overlay_thresholds: dict[str, Any] | None = None
    if overlay_enabled:
        overlay_path = _resolve_optional_path(overlay_cfg.get("contract_path"))
        overlay_file_sha = _clean(overlay_cfg.get("file_sha256"))
        overlay_spec_expected = _clean(overlay_cfg.get("spec_hash"))
        if not overlay_path:
            blockers.append("frontier_overlay_contract_path_missing")
        if not overlay_file_sha:
            blockers.append("frontier_overlay_file_sha256_not_pinned")
        if not overlay_spec_expected:
            blockers.append("frontier_overlay_spec_hash_not_pinned")
        overlay_result = validate_overlay_contract(
            path=overlay_path,
            expected_file_sha256=overlay_file_sha or None,
            expected_spec_hash=overlay_spec_expected or None,
            require_configured=True,
        )
        if not overlay_result.get("passed"):
            blockers.extend(overlay_result.get("blockers") or [])
        overlay_spec_hash = overlay_result.get("spec_hash")
        if overlay_path and overlay_path.exists():
            overlay_contract = load_overlay_contract(overlay_path)
            if str(overlay_contract.get("overlay_id") or "") != OVERLAY_ID:
                blockers.append("frontier_overlay_id_mismatch")
        # PIT thresholds (前置-1): synthetic thresholds are forbidden for live.
        overlay_thresholds = dict(overlay_cfg.get("thresholds") or {})
        threshold_blockers = validate_thresholds_pit(overlay_thresholds)
        blockers.extend(threshold_blockers)
        if not overlay_thresholds:
            blockers.append("frontier_overlay_thresholds_missing")

    blockers = sorted(set(blockers))
    if blockers:
        return _blocked(
            enabled=True,
            overlay_enabled=overlay_enabled,
            blockers=blockers,
            warnings=warnings,
            feature_columns=feature_columns,
            weights_file_sha256=weights_file_sha or None,
            weights_spec_hash=weights_spec_hash or None,
            overlay_spec_hash=overlay_spec_hash,
            scoring_config_sha256=scoring_config_sha,
        )

    # --- Armed + fully validated: build the contract-pinned effective scoring config. ---
    effective_config = dict(scoring_config)
    effective_config["feature_columns"] = list(feature_columns)
    # The frozen frontier vector pins the weights VERBATIM; the scoring config never overrides.
    effective_config["feature_weights"] = dict(feature_weights)
    effective_config_sha = _canonical_sha256(effective_config)

    arm_binding = _canonical_sha256(
        {
            "weights_file_sha256": weights_file_sha,
            "weights_spec_hash": weights_spec_hash,
            "scoring_config_sha256": scoring_config_sha,
            "effective_config_sha256": effective_config_sha,
            "feature_columns": sorted(feature_columns),
            "overlay_enabled": overlay_enabled,
            "overlay_spec_hash": overlay_spec_hash or "",
            # The live q90 threshold VALUES live in the YAML (not the sha-pinned overlay
            # contract), so bind their canonical view here too: a post-arm threshold edit
            # must trip the submit-gate binding compare, not slip through silently.
            "overlay_thresholds": _canonical_threshold_view(overlay_thresholds) if overlay_enabled else None,
        }
    )

    return FrontierResolution(
        status="armed_ready",
        enabled=True,
        overlay_enabled=overlay_enabled,
        blockers=[],
        warnings=warnings,
        arm_binding=arm_binding,
        feature_columns=list(feature_columns),
        weights_file_sha256=weights_file_sha,
        weights_spec_hash=weights_spec_hash,
        overlay_spec_hash=overlay_spec_hash,
        scoring_config_sha256=scoring_config_sha,
        effective_config_sha256=effective_config_sha,
        terminal_disarm=False,
        effective_config=effective_config,
        overlay_contract=overlay_contract,
        overlay_thresholds=overlay_thresholds,
    )


def resolve_live_frontier(live_config: Any, payload: dict[str, Any]) -> FrontierResolution:
    """Convenience wrapper used by the plan runners: sources operator state (for
    terminal disarm) ONLY when the flag is on, so the default-off path stays
    side-effect-free (no state-store construction, no sqlite init)."""
    operator_state = _frontier_operator_state(live_config) if frontier_enabled(payload) else None
    return resolve_frontier_live_plan(payload, operator_state=operator_state)


def _frontier_operator_state(live_config: Any) -> dict[str, Any] | None:
    """Operator state for terminal disarm. Returns None on unavailability so an ARMED
    frontier fails closed — an unknown kill-switch/pause state must never score."""
    try:
        from enhengclaw.live_trading.state_store import LiveTradingStateStore

        return LiveTradingStateStore(live_config.sqlite_path).read_operator_state()
    except Exception:
        return None


def overlay_target_factor() -> str:
    return TARGET_FACTOR


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _coerce_finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _canonical_threshold_view(thresholds: dict[str, Any] | None) -> dict[str, Any] | None:
    """Stable view of the overlay q90 thresholds for the arm binding. Finite numerics are
    encoded with ``float.hex()`` — an EXACT, canonical, int/float-agnostic (``4`` and ``4.0``
    hash identically) and COLLISION-FREE form that round-trips every distinct double, so an
    arm-time vs submit-time YAML parse can never differ and no real edit is ever lost to
    rounding. Booleans (PIT-provenance flags) are kept verbatim and handled before the numeric
    coercion (``float(True) == 1.0``). Non-finite / non-numeric values get a deterministic
    string form (NaN/Inf q90s are already fail-closed upstream by ``validate_thresholds_pit``)."""
    if not thresholds:
        return None
    view: dict[str, Any] = {}
    for key in sorted(thresholds):
        value = thresholds[key]
        if isinstance(value, bool):
            view[str(key)] = value
            continue
        num = _coerce_finite(value)
        view[str(key)] = num.hex() if num is not None else f"raw:{value!r}"
    return view


def _resolve_optional_path(raw: Any) -> Path | None:
    text = _clean(raw)
    if not text:
        return None
    return resolve_repo_path(text)
