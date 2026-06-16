from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from enhengclaw.live_trading.frozen_frontier_live import FrontierResolution
from enhengclaw.live_trading.frozen_frontier_overlay import (
    CROWDED_FACTOR,
    CROWDED_RANK_GATE,
    NEAR_HIGH_RANK_GATE,
    TARGET_FACTOR as OVERLAY_TARGET_FACTOR,
)
from enhengclaw.live_trading.models import LiveDecisionSnapshot
from enhengclaw.quant_research._binance_canonical_normalization import _timestamp_percentile_rank
from enhengclaw.quant_research.binance_canonical_h10d import (
    add_binance_risk_brake_columns,
    add_pit_strategy_eligibility,
    score_binance_ohlcv_core,
    validate_alpha_feature_columns,
)
from enhengclaw.quant_research.contracts import read_json


FUTURE_LABEL_COLUMNS = frozenset(
    {"target_forward_return", "target_up", "target_execution_forward_return", "target_execution_up"}
)
REQUIRED_PRICE_COLUMNS = ("timestamp_ms", "subject", "perp_close", "perp_quote_volume_usd")
# Panel columns the dth60 risk overlay needs to evaluate its trigger. The two rank factors
# are also frontier features; the two shock gauges are overlay-only. Absence fails closed.
_OVERLAY_GAUGE_COLUMNS = (
    "shock_co_occurrence_index",
    "co_jump_count_3d",
    OVERLAY_TARGET_FACTOR,
    CROWDED_FACTOR,
)


def file_sha256(path: Path) -> str:
    # Match the frozen anti-overfit package builder: read text, then hash the
    # UTF-8 encoded normalized string rather than raw platform-specific bytes.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def load_frozen_config(path: Path) -> dict[str, Any]:
    return dict(read_json(path))


def is_rebalance_slot(*, decision_time_ms: int, rebalance_interval_days: int, epoch_ms: int = 0) -> bool:
    if rebalance_interval_days <= 1:
        return True
    day_index = int((int(decision_time_ms) - int(epoch_ms)) // 86_400_000)
    return day_index >= 0 and day_index % int(rebalance_interval_days) == 0


def build_live_hv_balanced_snapshot(
    panel: pd.DataFrame,
    *,
    config: dict[str, Any],
    config_sha256: str,
    decision_time_ms: int,
    rebalance_interval_days: int = 10,
    rebalance_epoch_ms: int = 0,
    frontier: FrontierResolution | None = None,
) -> LiveDecisionSnapshot:
    # Frontier resolution gates the WHOLE scoring path:
    #   * None / dormant  -> baseline 5-factor behaviour, byte-for-byte unchanged.
    #   * armed_ready      -> swap in the contract-pinned 12-factor effective config + weights,
    #                         replace the OHLCV purity gate with the (tighter) hash-pinned
    #                         column check, and apply the dth60 risk overlay if enabled.
    #   * blocked          -> fail closed: a blocked snapshot, NEVER a silent baseline run.
    frontier_active = bool(frontier is not None and frontier.is_armed_ready)
    frontier_blocked = bool(frontier is not None and frontier.is_blocked)
    effective_config = frontier.effective_config if (frontier_active and frontier.effective_config) else config
    effective_sha = (
        str(frontier.effective_config_sha256)
        if (frontier_active and frontier.effective_config_sha256)
        else config_sha256
    )
    overlay_active = bool(frontier_active and frontier.overlay_enabled)
    overlay_thresholds = dict(frontier.overlay_thresholds or {}) if overlay_active else {}

    strategy_label = str(
        effective_config.get("strategy_label") or "v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget"
    )
    decision_id = f"{strategy_label}:{int(decision_time_ms)}"
    decision_date = datetime.fromtimestamp(int(decision_time_ms) / 1000, tz=UTC).date().isoformat()
    rebalance_slot = is_rebalance_slot(
        decision_time_ms=decision_time_ms,
        rebalance_interval_days=rebalance_interval_days,
        epoch_ms=rebalance_epoch_ms,
    )
    blockers: list[str] = []
    if frontier_blocked:
        # Armed but its contract/threshold preconditions failed: refuse to score.
        blockers.extend(f"frontier_blocked:{item}" for item in (frontier.blockers or []) or ["unspecified"])
    if panel.empty:
        blockers.append("empty_live_panel")
    future_columns = sorted(column for column in FUTURE_LABEL_COLUMNS if column in panel.columns)
    if future_columns:
        blockers.append(f"future_label_columns_present:{','.join(future_columns)}")
    feature_columns = [str(item) for item in effective_config.get("feature_columns") or []]
    allow_feature_subset = bool(
        dict(effective_config.get("feature_subset_policy") or {}).get("allow_pruned_subset", False)
    )
    if frontier_active:
        # Admission is the hash-verified frozen contract column set (validated upstream by
        # frozen_frontier_live); the OHLCV pattern allow-list deliberately forbids these
        # derivatives factors, so we assert the pinned set instead of the pattern gate.
        if sorted(feature_columns) != sorted(str(c) for c in (frontier.feature_columns or [])):
            blockers.append("frontier_effective_feature_columns_drift")
    else:
        purity = validate_alpha_feature_columns(feature_columns, require_all_allowed=not allow_feature_subset)
        if not bool(purity.get("passed")):
            blockers.append("feature_purity_failed")
    missing_features = [column for column in feature_columns if column not in panel.columns]
    if missing_features:
        blockers.append(f"missing_feature_columns:{','.join(missing_features)}")
    missing_price = [column for column in REQUIRED_PRICE_COLUMNS if column not in panel.columns]
    if missing_price:
        blockers.append(f"missing_price_columns:{','.join(missing_price)}")
    if overlay_active:
        overlay_missing = [c for c in _OVERLAY_GAUGE_COLUMNS if c not in panel.columns]
        if overlay_missing:
            blockers.append(f"frontier_overlay_gauge_columns_missing:{','.join(sorted(overlay_missing))}")
        if (
            _to_float(overlay_thresholds.get("shock_co_occurrence_index_q90")) is None
            or _to_float(overlay_thresholds.get("co_jump_count_3d_q90")) is None
        ):
            blockers.append("frontier_overlay_thresholds_non_finite")
    if not rebalance_slot:
        blockers.append("non_rebalance_slot")
    if blockers:
        return LiveDecisionSnapshot(
            decision_id=decision_id,
            strategy_label=strategy_label,
            config_sha256=effective_sha,
            decision_time_ms=int(decision_time_ms),
            decision_date_utc=decision_date,
            rebalance_slot=rebalance_slot,
            input_bar_end_ms=int(decision_time_ms),
            status="blocked",
            blockers=blockers,
        )

    scored = panel.copy()
    if "universe_active" not in scored.columns:
        scored["universe_active"] = True
    if "funding_rate" not in scored.columns:
        scored["funding_rate"] = np.nan
    if "funding_sample_count" not in scored.columns:
        scored["funding_sample_count"] = 0.0
    if "has_perp" not in scored.columns:
        scored["has_perp"] = True
    if "perp_execution_eligible" not in scored.columns:
        scored["perp_execution_eligible"] = True
    if "perp_executable_start_ms" not in scored.columns:
        scored["perp_executable_start_ms"] = pd.to_numeric(scored["timestamp_ms"], errors="coerce")

    feature_valid = pd.Series(True, index=scored.index, dtype="bool")
    for column in feature_columns:
        feature_valid &= pd.to_numeric(scored[column], errors="coerce").replace([np.inf, -np.inf], np.nan).notna()
    price_valid = pd.Series(True, index=scored.index, dtype="bool")
    for column in REQUIRED_PRICE_COLUMNS:
        if column == "subject":
            price_valid &= scored[column].notna()
        else:
            price_valid &= pd.to_numeric(scored[column], errors="coerce").replace([np.inf, -np.inf], np.nan).notna()
    universe_active = _truthy(scored["universe_active"])
    score_mask = feature_valid & price_valid & universe_active
    scored["binance_decision_eligible"] = score_mask
    scored["score"] = 0.0
    if bool(score_mask.any()):
        score_subframe = scored.loc[score_mask].copy()
        contribution_multipliers: dict[str, pd.Series] | None = None
        if overlay_active:
            # Gauge presence + threshold finiteness were already gated above, so this build
            # is total. ONLY distance_to_high_60's per-row contribution is masked.
            contribution_multipliers = _frontier_overlay_contribution_multipliers(
                score_subframe, thresholds=overlay_thresholds
            )
        scored.loc[score_mask, "score"] = score_binance_ohlcv_core(
            score_subframe,
            feature_columns=feature_columns,
            feature_weights=dict(effective_config.get("feature_weights") or {}),
            require_complete_feature_set=not allow_feature_subset,
            enforce_alpha_purity=not frontier_active,
            contribution_multipliers=contribution_multipliers,
        )
    scored = add_pit_strategy_eligibility(scored, config=effective_config)
    scored = add_binance_risk_brake_columns(scored, config=effective_config)
    decision_rows = scored.loc[pd.to_numeric(scored["timestamp_ms"], errors="coerce").eq(int(decision_time_ms))].copy()
    if decision_rows.empty:
        blockers.append("decision_timestamp_missing_from_panel")
    if not bool(decision_rows.get("binance_decision_eligible", pd.Series(dtype="bool")).any()):
        blockers.append("no_decision_eligible_rows")
    status = "ok" if not blockers else "blocked"
    return LiveDecisionSnapshot(
        decision_id=decision_id,
        strategy_label=strategy_label,
        config_sha256=effective_sha,
        decision_time_ms=int(decision_time_ms),
        decision_date_utc=decision_date,
        rebalance_slot=rebalance_slot,
        input_bar_end_ms=int(decision_time_ms),
        status=status,
        blockers=blockers,
        scores=decision_rows.reset_index(drop=True),
    )


def _truthy(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype("bool")
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def _to_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _frontier_overlay_contribution_multipliers(
    subframe: pd.DataFrame, *, thresholds: dict[str, Any]
) -> dict[str, pd.Series]:
    """Per-row contribution multiplier for the FROZEN dth60 overlay, keyed by the single
    affected factor (distance_to_high_60). Trigger semantics mirror
    ``frozen_frontier_overlay.compute_overlay_trigger`` exactly, vectorised over the
    cross-section the scorer sees:
        triggered = (shock >= shock_q90) OR (co_jump >= co_jump_q90)
                    OR (rank_pct(dth60) >= 0.75 AND rank_pct(crowded) >= 0.80)
    Ranks are per-timestamp percentile ranks (the same standardisation the scorer uses).
    Caller guarantees gauges present + thresholds finite (fail-closed upstream)."""
    timestamps = subframe["timestamp_ms"]
    shock_q90 = _to_float(thresholds.get("shock_co_occurrence_index_q90"))
    co_jump_q90 = _to_float(thresholds.get("co_jump_count_3d_q90"))
    shock = pd.to_numeric(subframe["shock_co_occurrence_index"], errors="coerce")
    cojump = pd.to_numeric(subframe["co_jump_count_3d"], errors="coerce")
    dh_rank = _timestamp_percentile_rank(
        pd.to_numeric(subframe[OVERLAY_TARGET_FACTOR], errors="coerce"), timestamps
    )
    tt_rank = _timestamp_percentile_rank(
        pd.to_numeric(subframe[CROWDED_FACTOR], errors="coerce"), timestamps
    )
    shock_branch = shock.notna() & (shock >= (shock_q90 if shock_q90 is not None else np.inf))
    cojump_branch = cojump.notna() & (cojump >= (co_jump_q90 if co_jump_q90 is not None else np.inf))
    crowded_branch = (dh_rank >= NEAR_HIGH_RANK_GATE) & (tt_rank >= CROWDED_RANK_GATE)
    triggered = (shock_branch | cojump_branch | crowded_branch).to_numpy()
    multiplier = pd.Series(np.where(triggered, 0.0, 1.0), index=subframe.index, dtype="float64")
    return {OVERLAY_TARGET_FACTOR: multiplier}


def augment_panel_with_overlay_shock_gauges(panel: pd.DataFrame) -> pd.DataFrame:
    """Add the two dth60-overlay shock gauges to a multi-subject daily panel, BYTE-MATCHING the
    research definition in enhengclaw.quant_research.features (per-subject 3-sigma vol-shock flag
    -> cross-sectional co-occurrence fraction + 3-timestamp co-jump count).

    Research source (features.py, verbatim formula):
        return_1   = spot_close.pct_change()            # per subject, time-sorted (line 161-163)
        rv_lag_20  = return_1.rolling(20).std().shift(1) # PIT: prior window (line 595)
        shock_today= (|return_1| > 3*rv_lag_20) & rv_lag_20.notna()                   (line 596)
        shock_co_occurrence_index = shock_today.groupby(timestamp_ms).mean()          (line 701-703)
        count_per_ts = shock_today.groupby(timestamp_ms).sum().sort_index()           (line 717-719)
        co_jump_count_3d = timestamp_ms.map(count_per_ts.rolling(3,min_periods=1).sum())(line 720-723)

    REQUIRES spot_close and ALWAYS derives return_1 from it (research definition,
    features.py:161-163: return_1 = spot_close.pct_change()). It deliberately does NOT consume any
    pre-existing return_1 column: the live panel carries a PERP-derived return_1
    (add_binance_ohlcv_core_features), and using it would silently mis-source the overlay to perp
    returns. Missing spot_close => panel returned UNCHANGED => the snapshot fails closed via
    frontier_overlay_gauge_columns_missing (never a perp approximation, never a fabricated gauge).
    """
    if panel is None or panel.empty:
        return panel
    if "subject" not in panel.columns or "timestamp_ms" not in panel.columns or "spot_close" not in panel.columns:
        return panel
    work = panel.copy()
    work["__ts_sort"] = pd.to_numeric(work["timestamp_ms"], errors="coerce")
    # Match the research per-subject time-sorted frame (features.py:159-160).
    work = work.loc[work.sort_values(["subject", "__ts_sort"]).index]
    subject = work["subject"]
    close = pd.to_numeric(work["spot_close"], errors="coerce").replace(0.0, np.nan)
    # #8: fail closed on INCOMPLETE spot coverage. fetch_live_spot_close_frame silently SKIPS a
    # symbol whose spot kline request failed, so after the left-merge that subject is all-NaN. Its
    # shock gauges would then be NaN->0 (biased low) and the overlay would silently FAIL to mask it.
    # If any subject in the decision (latest-timestamp) cross-section lacks a finite spot_close,
    # emit NO gauges -> the snapshot fails closed via frontier_overlay_gauge_columns_missing. Never
    # score a partially-spot-sourced overlay cross-section.
    _ts = pd.to_numeric(work["timestamp_ms"], errors="coerce")
    if _ts.notna().any() and not bool(close[_ts == _ts.max()].notna().all()):
        return panel
    ret1 = close.groupby(subject).transform(lambda s: s.pct_change())
    rv_lag_20 = ret1.groupby(subject).transform(lambda s: s.rolling(20).std().shift(1))
    shock_today = ((ret1.abs() > 3.0 * rv_lag_20) & rv_lag_20.notna()).astype("float64").fillna(0.0)
    ts = pd.to_numeric(work["timestamp_ms"], errors="coerce")
    work["shock_co_occurrence_index"] = shock_today.groupby(ts).transform("mean")
    count_per_ts = shock_today.groupby(ts).sum().sort_index()
    count_3d = count_per_ts.rolling(3, min_periods=1).sum()
    work["co_jump_count_3d"] = ts.map(count_3d).fillna(0.0)
    work = work.drop(columns="__ts_sort")
    return work.loc[panel.index]
