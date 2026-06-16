"""factor_lifecycle — G.5 state machine for factor demotion/retirement.

Implements the lifecycle state machine declared in
`docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md` §G.5:

  active   passes admission                                            weight from posterior
  watch    rolling 60d (residual) IC < 0.02 for 2 consecutive windows  weight × 0.5, flag in audit
  decay    60d (residual) IC < 0.01 sustained for 30d                  weight × 0.0, audit-only
  retired  90d cumulative IC < 0 OR mechanism falsified by doc test    remove from manifest, archive
  revived  retired factor with shadow-OOS 90d IC > 0.05                re-run admission

The state machine consumes a per-factor *time series* of rolling residual
IC (against an admitted baseline), applies the transition rules, and
emits a recommended next state plus a transition reason. Mechanism
falsification is an external override (sourced from
`threshold_provenance.md` "falsified per doc test" markers).

Doc anchors:
  - §G.5 Lifecycle Management — state transitions
  - §G.4 Standard report card — IC primitives reused (per_timestamp_rank_ic,
    orthogonalize)
  - data_utilization_roadmap.md M2.5 — Day 60 exit criterion bullet 3
    ("factor_lifecycle 跑过一轮自动 demotion 实验")

This module is a *recommendation engine*, not an enforcement layer.
Manifest edits remain owner-driven: lifecycle.py output is consumed by
`scripts/quant_research/run_factor_lifecycle_demotion_experiment.py`
which writes a JSON report; humans then update manifest `lifecycle`
fields based on the report. This keeps the Stage-1 invariant that no
auto-runtime mutation of admitted-factor state happens without owner
review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .feature_admission_v2 import orthogonalize, per_timestamp_rank_ic


FACTOR_LIFECYCLE_CONTRACT_VERSION = "quant_factor_lifecycle.v1"

# G.5 thresholds (verbatim from doc §G.5)
ROLLING_60D_WINDOW_DAYS = 60
ROLLING_30D_WINDOW_DAYS = 30
ROLLING_90D_WINDOW_DAYS = 90

WATCH_RESID_IC_THRESHOLD = 0.02       # below this: watch trigger
WATCH_CONSECUTIVE_WINDOWS = 2         # require 2 consecutive 60d windows < 0.02

DECAY_RESID_IC_THRESHOLD = 0.01       # below this for 30d sustained: decay
DECAY_SUSTAIN_DAYS = 30               # consecutive days below decay threshold

RETIRED_CUM_90D_THRESHOLD = 0.0       # 90d cumulative IC < 0: retired
REVIVED_SHADOW_OOS_THRESHOLD = 0.05   # shadow OOS 90d IC > 0.05: consider revived

# Raw IC sanity check thresholds — used to FLAG (not override) G.5 demote
# verdicts that may be self-residual measurement artifacts. The lsk3
# late-2026 decay diagnostic found that self-residual IC can produce
# systematic false-positive demotion when baseline factors are mutually
# highly correlated (e.g., iv_smooth_60 ↔ dh_60 corr=-0.522). When G.5
# recommends demote but raw IC remains stable, the demotion is flagged
# as "likely_self_residual_artifact" — owner-side reviews actual decision.
RAW_IC_SANITY_STABLE_FLOOR = 0.02      # |raw IC| above this: factor "stable"
RAW_IC_SANITY_STRONG_FLOOR = 0.04      # |raw IC| above G1 floor: factor "strong"

VALID_STATES = ("active", "watch", "decay", "retired", "revived")


@dataclass(frozen=True)
class FactorLifecycleSignal:
    """Per-factor lifecycle evaluation signal.

    Residual IC values are computed against the admitted baseline (or
    against `lsk3 minus self` for lsk3 factors). Raw IC values are
    computed without baseline residualization — used for the raw-IC
    sanity check on G.5 verdicts (per the lsk3-late-2026 decay
    diagnostic finding that self-residual IC can produce systematic
    false-positive demotion in high-internal-correlation baselines).
    """

    factor_id: str
    n_observations: int
    rolling_60d_resid_ic_latest: float
    rolling_60d_resid_ic_prev: float | None
    rolling_30d_resid_ic_latest: float | None
    rolling_90d_cum_ic_latest: float | None
    consecutive_60d_below_watch: int
    days_60d_below_decay: int
    mechanism_falsified: bool
    # Raw IC (NO baseline residualization), used for sanity check
    rolling_60d_raw_ic_latest: float | None = None
    rolling_90d_cum_raw_ic_latest: float | None = None


def _rolling_mean_ic(
    *, factor: pd.Series, target: pd.Series, timestamps: pd.Series, window_days: int,
    baseline: pd.DataFrame | None = None,
) -> pd.Series:
    """Compute rolling-`window_days` mean of per-timestamp rank IC.

    If `baseline` is provided, residualize factor against baseline first.
    Returns Series indexed by timestamp_ms.
    """
    factor_clean = pd.to_numeric(factor, errors="coerce").fillna(0.0)
    if baseline is not None and len(baseline.columns) > 0:
        factor_clean = orthogonalize(factor_clean, baseline)
    target_clean = pd.to_numeric(target, errors="coerce")
    ic = per_timestamp_rank_ic(factor_clean, target_clean, timestamps).dropna().sort_index()
    if ic.empty:
        return ic
    rolling = ic.rolling(window=window_days, min_periods=max(10, window_days // 3)).mean()
    return rolling


def evaluate_factor_state(
    signal: FactorLifecycleSignal,
    *,
    current_state: str = "active",
) -> dict:
    """Apply G.5 state machine to a single factor's lifecycle signal.

    Returns dict with `recommended_state`, `transition_reason`,
    `weight_multiplier`, and the input signal echoed back.
    """
    if current_state not in VALID_STATES:
        raise ValueError(f"unknown current_state {current_state!r}; expected one of {VALID_STATES}")

    # Mechanism falsification overrides everything → retired
    if signal.mechanism_falsified:
        return {
            "factor_id": signal.factor_id,
            "current_state": current_state,
            "recommended_state": "retired",
            "transition_reason": "mechanism_falsified_by_doc_test",
            "weight_multiplier": 0.0,
            "signal": signal.__dict__,
        }

    # Retired-factor revival check
    if current_state == "retired":
        # Revival requires shadow-OOS 90d IC > 0.05 (sourced from external
        # shadow-OOS pipeline, NOT the same panel that retired the factor).
        # In this implementation, we only flag candidacy; actual revival
        # decision is owner-side.
        if (
            signal.rolling_90d_cum_ic_latest is not None
            and signal.rolling_90d_cum_ic_latest > REVIVED_SHADOW_OOS_THRESHOLD
        ):
            return {
                "factor_id": signal.factor_id,
                "current_state": current_state,
                "recommended_state": "revived",
                "transition_reason": (
                    f"retired_factor_90d_cum_ic_{signal.rolling_90d_cum_ic_latest:.4f}_"
                    f"above_revival_threshold_{REVIVED_SHADOW_OOS_THRESHOLD}"
                ),
                "weight_multiplier": 0.0,  # still 0 until re-admission
                "signal": signal.__dict__,
            }
        return {
            "factor_id": signal.factor_id,
            "current_state": current_state,
            "recommended_state": "retired",
            "transition_reason": "no_change_remains_retired",
            "weight_multiplier": 0.0,
            "signal": signal.__dict__,
        }

    # Retired trigger: 90d cumulative IC < 0
    if (
        signal.rolling_90d_cum_ic_latest is not None
        and signal.rolling_90d_cum_ic_latest < RETIRED_CUM_90D_THRESHOLD
    ):
        return {
            "factor_id": signal.factor_id,
            "current_state": current_state,
            "recommended_state": "retired",
            "transition_reason": (
                f"90d_cum_resid_ic_{signal.rolling_90d_cum_ic_latest:.4f}_"
                f"below_retire_threshold_{RETIRED_CUM_90D_THRESHOLD}"
            ),
            "weight_multiplier": 0.0,
            "signal": signal.__dict__,
        }

    # Decay trigger: 60d IC < 0.01 sustained for 30d
    if signal.days_60d_below_decay >= DECAY_SUSTAIN_DAYS:
        return {
            "factor_id": signal.factor_id,
            "current_state": current_state,
            "recommended_state": "decay",
            "transition_reason": (
                f"60d_resid_ic_below_{DECAY_RESID_IC_THRESHOLD}_for_"
                f"{signal.days_60d_below_decay}_days"
            ),
            "weight_multiplier": 0.0,
            "signal": signal.__dict__,
        }

    # Watch trigger: 60d IC < 0.02 for 2 consecutive windows
    if signal.consecutive_60d_below_watch >= WATCH_CONSECUTIVE_WINDOWS:
        return {
            "factor_id": signal.factor_id,
            "current_state": current_state,
            "recommended_state": "watch",
            "transition_reason": (
                f"60d_resid_ic_below_{WATCH_RESID_IC_THRESHOLD}_for_"
                f"{signal.consecutive_60d_below_watch}_consecutive_windows"
            ),
            "weight_multiplier": 0.5,
            "signal": signal.__dict__,
        }

    # Healthy: stay active
    return {
        "factor_id": signal.factor_id,
        "current_state": current_state,
        "recommended_state": "active",
        "transition_reason": (
            f"60d_resid_ic_{signal.rolling_60d_resid_ic_latest:.4f}_above_thresholds"
        ),
        "weight_multiplier": 1.0,
        "signal": signal.__dict__,
    }


def compute_factor_lifecycle_signal(
    *,
    factor_id: str,
    panel: pd.DataFrame,
    factor_column: str,
    target_column: str,
    baseline_columns: Iterable[str] | None,
    mechanism_falsified: bool = False,
) -> FactorLifecycleSignal:
    """Compute the rolling-IC time series and derive a FactorLifecycleSignal.

    `baseline_columns` may be None or empty (raw IC mode, e.g., for lsk3
    factors where the baseline IS the lsk3 set itself; a baseline can't
    self-residualize).
    """
    factor_series = panel[factor_column]
    target_series = panel[target_column]
    timestamps = panel["timestamp_ms"]
    baseline_df: pd.DataFrame | None = None
    if baseline_columns:
        cols = [c for c in baseline_columns if c in panel.columns and c != factor_column]
        if cols:
            baseline_df = panel[cols].apply(pd.to_numeric, errors="coerce")

    rolling_60 = _rolling_mean_ic(
        factor=factor_series,
        target=target_series,
        timestamps=timestamps,
        window_days=ROLLING_60D_WINDOW_DAYS,
        baseline=baseline_df,
    )
    rolling_30 = _rolling_mean_ic(
        factor=factor_series,
        target=target_series,
        timestamps=timestamps,
        window_days=ROLLING_30D_WINDOW_DAYS,
        baseline=baseline_df,
    )
    rolling_90 = _rolling_mean_ic(
        factor=factor_series,
        target=target_series,
        timestamps=timestamps,
        window_days=ROLLING_90D_WINDOW_DAYS,
        baseline=baseline_df,
    )
    # Raw IC (no residualization) — used for sanity check
    rolling_60_raw = _rolling_mean_ic(
        factor=factor_series,
        target=target_series,
        timestamps=timestamps,
        window_days=ROLLING_60D_WINDOW_DAYS,
        baseline=None,
    )
    rolling_90_raw = _rolling_mean_ic(
        factor=factor_series,
        target=target_series,
        timestamps=timestamps,
        window_days=ROLLING_90D_WINDOW_DAYS,
        baseline=None,
    )

    if rolling_60.empty:
        return FactorLifecycleSignal(
            factor_id=factor_id,
            n_observations=0,
            rolling_60d_resid_ic_latest=float("nan"),
            rolling_60d_resid_ic_prev=None,
            rolling_30d_resid_ic_latest=None,
            rolling_90d_cum_ic_latest=None,
            consecutive_60d_below_watch=0,
            days_60d_below_decay=0,
            mechanism_falsified=mechanism_falsified,
            rolling_60d_raw_ic_latest=None,
            rolling_90d_cum_raw_ic_latest=None,
        )

    rolling_60_clean = rolling_60.dropna()
    n_obs = int(len(rolling_60_clean))

    latest_60 = float(rolling_60_clean.iloc[-1]) if n_obs > 0 else float("nan")
    # "previous" 60d window: take the value 30d (~30 timestamps) earlier as a
    # reasonable approximation for "previous consecutive 60d window". Doc says
    # "2 consecutive windows" without specifying overlap; we use 30d step.
    prev_idx = max(0, n_obs - 1 - ROLLING_30D_WINDOW_DAYS)
    prev_60 = float(rolling_60_clean.iloc[prev_idx]) if n_obs > ROLLING_30D_WINDOW_DAYS else None

    rolling_30_clean = rolling_30.dropna()
    latest_30 = float(rolling_30_clean.iloc[-1]) if len(rolling_30_clean) > 0 else None

    rolling_90_clean = rolling_90.dropna()
    latest_90 = float(rolling_90_clean.iloc[-1]) if len(rolling_90_clean) > 0 else None

    # Consecutive 60d-window count below watch threshold:
    # Count how many of the last (1+30d-step) 60d-window snapshots are below threshold.
    if not np.isnan(latest_60):
        snapshots = []
        # Sample at 30d intervals walking back from the end
        idx = n_obs - 1
        while idx >= 0:
            snapshots.append(float(rolling_60_clean.iloc[idx]))
            idx -= ROLLING_30D_WINDOW_DAYS
        # Count consecutive (from latest backwards) that are < threshold
        consecutive_watch = 0
        for v in snapshots:
            if v < WATCH_RESID_IC_THRESHOLD:
                consecutive_watch += 1
            else:
                break
    else:
        consecutive_watch = 0

    # Days below decay threshold (sustained):
    # Count trailing consecutive days where rolling_60d < DECAY threshold.
    days_decay = 0
    for v in reversed(rolling_60_clean.values):
        if pd.isna(v):
            break
        if v < DECAY_RESID_IC_THRESHOLD:
            days_decay += 1
        else:
            break

    rolling_60_raw_clean = rolling_60_raw.dropna()
    latest_60_raw = float(rolling_60_raw_clean.iloc[-1]) if len(rolling_60_raw_clean) > 0 else None
    rolling_90_raw_clean = rolling_90_raw.dropna()
    latest_90_raw = float(rolling_90_raw_clean.iloc[-1]) if len(rolling_90_raw_clean) > 0 else None

    return FactorLifecycleSignal(
        factor_id=factor_id,
        n_observations=n_obs,
        rolling_60d_resid_ic_latest=latest_60,
        rolling_60d_resid_ic_prev=prev_60,
        rolling_30d_resid_ic_latest=latest_30,
        rolling_90d_cum_ic_latest=latest_90,
        consecutive_60d_below_watch=consecutive_watch,
        days_60d_below_decay=days_decay,
        mechanism_falsified=mechanism_falsified,
        rolling_60d_raw_ic_latest=latest_60_raw,
        rolling_90d_cum_raw_ic_latest=latest_90_raw,
    )


def assess_raw_ic_sanity_check(verdict: dict) -> dict:
    """Augment a G.5 verdict with raw-IC sanity check metadata.

    Per the lsk3-late-2026 decay diagnostic finding:
    self-residual IC can produce systematic false-positive demotion
    when baseline factors are mutually highly correlated. Specifically:
    when factor A and factor B both have raw IC strengthening late but
    are negatively correlated (e.g., iv_smooth_60 ↔ dh_60 corr=-0.522),
    A's self-residual IC can collapse to ~0 because B's projection
    "explains" most of A's signal. This is a structural artifact, not
    a sign that A itself has decayed.

    The sanity check rule:
      - If G.5 recommends `watch` / `decay` / `retired` BUT raw IC
        magnitude is still ≥ RAW_IC_SANITY_STABLE_FLOOR, flag as
        `likely_self_residual_artifact`.
      - If G.5 recommends `retired` BUT raw IC magnitude ≥
        RAW_IC_SANITY_STRONG_FLOOR (G1 floor), flag as
        `likely_self_residual_artifact_strong` — owner-side should
        keep the factor and investigate baseline restructuring instead.
      - The sanity check NEVER overrides the G.5 verdict (preserves
        doc compliance) — it only annotates.

    Returns the verdict dict with new keys:
      raw_ic_sanity_check: "stable" | "noisy" | "weak" | "missing"
      sanity_artifact_flag: None | "likely_artifact" | "likely_artifact_strong"
      sanity_note: str (human-readable reason)
    """
    signal = verdict.get("signal", {})
    raw_60 = signal.get("rolling_60d_raw_ic_latest")
    recommended = verdict["recommended_state"]

    # Decision branches
    if raw_60 is None:
        verdict["raw_ic_sanity_check"] = "missing"
        verdict["sanity_artifact_flag"] = None
        verdict["sanity_note"] = "raw IC not available"
        return verdict

    abs_raw = abs(raw_60)
    if abs_raw >= RAW_IC_SANITY_STRONG_FLOOR:
        sanity_status = "strong"
    elif abs_raw >= RAW_IC_SANITY_STABLE_FLOOR:
        sanity_status = "stable"
    elif abs_raw >= 0.005:
        sanity_status = "noisy"
    else:
        sanity_status = "weak"
    verdict["raw_ic_sanity_check"] = sanity_status

    # Sanity check fires only when G.5 demote is recommended
    if recommended in ("watch", "decay", "retired") and not signal.get("mechanism_falsified", False):
        if abs_raw >= RAW_IC_SANITY_STRONG_FLOOR:
            verdict["sanity_artifact_flag"] = "likely_artifact_strong"
            verdict["sanity_note"] = (
                f"G.5 recommends {recommended} on residual IC, but raw IC "
                f"={raw_60:+.4f} (|raw|>=G1 floor 0.04). Likely a self-"
                "residual measurement artifact from baseline internal "
                "correlation. Owner-side: keep factor + investigate "
                "baseline restructuring."
            )
        elif abs_raw >= RAW_IC_SANITY_STABLE_FLOOR:
            verdict["sanity_artifact_flag"] = "likely_artifact"
            verdict["sanity_note"] = (
                f"G.5 recommends {recommended} on residual IC, but raw IC "
                f"={raw_60:+.4f} (|raw|>=stable floor 0.02). Possible "
                "self-residual artifact; owner-side review."
            )
        else:
            verdict["sanity_artifact_flag"] = None
            verdict["sanity_note"] = (
                f"G.5 demote recommendation matches raw IC weakness "
                f"(|raw|={abs_raw:.4f}<{RAW_IC_SANITY_STABLE_FLOOR}). "
                "Demotion likely reflects genuine decay."
            )
    else:
        verdict["sanity_artifact_flag"] = None
        verdict["sanity_note"] = (
            f"G.5 keeps factor active (or already retired); sanity check N/A."
        )

    return verdict


def evaluate_factor_lifecycle_batch(
    *,
    panel: pd.DataFrame,
    target_column: str,
    factor_specs: list[dict],
) -> dict:
    """Batch lifecycle evaluation across many factors.

    `factor_specs` is a list of dicts with keys:
      factor_id (str)
      column (str) — column name in panel
      baseline_columns (list[str] | None) — admitted baseline for residualization
      current_state (str) — current lifecycle state (active / watch / decay / retired)
      mechanism_falsified (bool, default False)

    Returns:
      {
        "contract_version": ...,
        "evaluated_at_utc": ...,
        "factor_results": [{factor_id, current_state, recommended_state,
                            transition_reason, weight_multiplier, signal}, ...],
        "summary": {n_total, n_active, n_watch, n_decay, n_retired, n_revived,
                    n_recommended_demote, n_recommended_promote_revival, ...}
      }
    """
    results: list[dict] = []
    for spec in factor_specs:
        signal = compute_factor_lifecycle_signal(
            factor_id=spec["factor_id"],
            panel=panel,
            factor_column=spec["column"],
            target_column=target_column,
            baseline_columns=spec.get("baseline_columns"),
            mechanism_falsified=bool(spec.get("mechanism_falsified", False)),
        )
        verdict = evaluate_factor_state(
            signal,
            current_state=str(spec.get("current_state", "active")),
        )
        verdict["mechanism_family"] = spec.get("mechanism_family")
        verdict["mechanism_note"] = spec.get("note")
        # Augment with raw-IC sanity check (does not override G.5 verdict)
        verdict = assess_raw_ic_sanity_check(verdict)
        results.append(verdict)

    summary = {
        "n_total": len(results),
        "n_active": sum(1 for r in results if r["recommended_state"] == "active"),
        "n_watch": sum(1 for r in results if r["recommended_state"] == "watch"),
        "n_decay": sum(1 for r in results if r["recommended_state"] == "decay"),
        "n_retired": sum(1 for r in results if r["recommended_state"] == "retired"),
        "n_revived_candidates": sum(1 for r in results if r["recommended_state"] == "revived"),
        "n_recommended_demote": sum(
            1
            for r in results
            if VALID_STATES.index(r["recommended_state"])
            > VALID_STATES.index(r["current_state"])
            and r["current_state"] != "retired"
            and r["recommended_state"] != "revived"
        ),
        "n_recommended_revival_check": sum(
            1
            for r in results
            if r["current_state"] == "retired" and r["recommended_state"] == "revived"
        ),
        "n_likely_self_residual_artifact": sum(
            1 for r in results if r.get("sanity_artifact_flag") == "likely_artifact"
        ),
        "n_likely_self_residual_artifact_strong": sum(
            1 for r in results if r.get("sanity_artifact_flag") == "likely_artifact_strong"
        ),
    }

    return {
        "contract_version": FACTOR_LIFECYCLE_CONTRACT_VERSION,
        "evaluated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "factor_results": results,
        "summary": summary,
    }


__all__ = [
    "FACTOR_LIFECYCLE_CONTRACT_VERSION",
    "VALID_STATES",
    "WATCH_RESID_IC_THRESHOLD",
    "WATCH_CONSECUTIVE_WINDOWS",
    "DECAY_RESID_IC_THRESHOLD",
    "DECAY_SUSTAIN_DAYS",
    "RETIRED_CUM_90D_THRESHOLD",
    "REVIVED_SHADOW_OOS_THRESHOLD",
    "RAW_IC_SANITY_STABLE_FLOOR",
    "RAW_IC_SANITY_STRONG_FLOOR",
    "ROLLING_60D_WINDOW_DAYS",
    "FactorLifecycleSignal",
    "compute_factor_lifecycle_signal",
    "evaluate_factor_state",
    "assess_raw_ic_sanity_check",
    "evaluate_factor_lifecycle_batch",
]
