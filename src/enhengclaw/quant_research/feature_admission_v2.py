"""feature_admission_v2 — evidence-driven 11-gate factor admission.

Implements the standard report card defined in
`docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md` §G.4 against the
11-gate admission policy declared in §G.2:

    G1  IC mean                 (full-period rank IC magnitude >= threshold)
    G2  IC stability            (rolling-60d IC > 0 fraction >= threshold)
    G3  IC sign consistency     (per-regime IC same-sign fraction >= threshold)
    G4  Concentration           (single-asset IC contribution share <= threshold)
    G5  VIF                     (max VIF vs admitted baseline <= threshold)
    G6  Orthogonal residual IC  (residual IC vs admitted baseline >= threshold)
    G7  Turnover                (per-subject lag-30 autocorrelation-derived turnover <= threshold)
    G8  Capacity-aware IC       (IC retention on top-half-by-capacity >= threshold)
    G9  Crowding                (residual IC vs public factors >= threshold)
    G10 Out-of-universe         (IC on bottom-half-by-capacity >= threshold)
    G11 Falsification trigger   (declared, non-empty)

Relationship to v1 admission. `feature_admission.py` (v1) is a strict-
whitelist policy enforced at panel-build / manifest-validate time: it
controls which columns are *allowed* into a strategy manifest's
`required_feature_columns`. v2 is the *evidence-driven* layer: of the
columns admitted by v1, which actually meet the empirical bar to enter
a score? v2 is consulted at research time (factor_report_card,
admission audit), not at runtime — so v1 is unchanged. The two layers
compose: candidate must pass v1 (schema) and v2 (evidence) to be a
score component.

Contract. Threshold values live in
`config/quant_research/feature_admission_v2_contract.json` and are read
by `load_feature_admission_v2_contract()`. The constant
`FEATURE_ADMISSION_V2_CONTRACT_VERSION` mirrors the JSON's
`contract_version` field for code-side equality checks.

Helpers. `per_timestamp_rank_ic`, `per_subject_rank_ic`,
`orthogonalize`, `autocorr_per_subject`, and `build_regime_by_ts` are
exposed as primitives reusable by other research scripts.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .contracts import read_json


ROOT = Path(__file__).resolve().parents[3]
FEATURE_ADMISSION_V2_CONTRACT_PATH = (
    ROOT / "config" / "quant_research" / "feature_admission_v2_contract.json"
)
FEATURE_ADMISSION_V2_CONTRACT_VERSION = "quant_feature_admission_v2.v1"


def load_feature_admission_v2_contract(path: Path | None = None) -> dict[str, Any]:
    contract_path = (path or FEATURE_ADMISSION_V2_CONTRACT_PATH).expanduser().resolve()
    payload = dict(read_json(contract_path))
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != FEATURE_ADMISSION_V2_CONTRACT_VERSION:
        raise ValueError(
            "feature_admission_v2 contract_version mismatch: "
            f"{contract_version or 'missing'} != {FEATURE_ADMISSION_V2_CONTRACT_VERSION}"
        )
    return payload


def _threshold(contract: dict[str, Any], section: str, field: str, default: float) -> float:
    section_payload = contract.get(section) or {}
    if not isinstance(section_payload, dict):
        return float(default)
    raw = section_payload.get(field, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


# === Core IC primitives ===


def per_timestamp_rank_ic(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
) -> pd.Series:
    """Per-timestamp Spearman rank IC of `factor` against `target`.

    Returns a Series indexed by unique timestamp values. Missing observations
    are dropped before the per-timestamp rank correlation is computed. Single-
    observation timestamps yield NaN (no cross-section).
    """
    df = pd.DataFrame({"f": factor, "t": target, "ts": timestamps}).dropna()
    if df.empty:
        return pd.Series(dtype="float64")
    fr = df.groupby("ts")["f"].rank(method="average")
    tr = df.groupby("ts")["t"].rank(method="average")
    fr_mean = fr.groupby(df["ts"]).transform("mean")
    tr_mean = tr.groupby(df["ts"]).transform("mean")
    fr_dev = fr - fr_mean
    tr_dev = tr - tr_mean
    num = (fr_dev * tr_dev).groupby(df["ts"]).sum()
    denom = np.sqrt(
        (fr_dev * fr_dev).groupby(df["ts"]).sum()
        * (tr_dev * tr_dev).groupby(df["ts"]).sum()
    )
    return (num / denom.replace(0.0, np.nan)).rename("ic")


def per_subject_rank_ic(
    factor: pd.Series,
    target: pd.Series,
    subjects: pd.Series,
    *,
    min_obs: int = 30,
) -> pd.Series:
    """Per-subject Spearman rank IC of `factor` against `target`.

    Subjects with fewer than `min_obs` valid observations are excluded.
    """
    df = pd.DataFrame({"f": factor, "t": target, "s": subjects}).dropna()
    if df.empty:
        return pd.Series(dtype="float64")
    fr = df.groupby("s")["f"].rank(method="average")
    tr = df.groupby("s")["t"].rank(method="average")
    fr_mean = fr.groupby(df["s"]).transform("mean")
    tr_mean = tr.groupby(df["s"]).transform("mean")
    fr_dev = fr - fr_mean
    tr_dev = tr - tr_mean
    num = (fr_dev * tr_dev).groupby(df["s"]).sum()
    denom = np.sqrt(
        (fr_dev * fr_dev).groupby(df["s"]).sum() * (tr_dev * tr_dev).groupby(df["s"]).sum()
    )
    counts = df.groupby("s").size()
    ic = num / denom.replace(0.0, np.nan)
    ic[counts < min_obs] = np.nan
    return ic.dropna()


def orthogonalize(factor: pd.Series, baseline_df: pd.DataFrame) -> pd.Series:
    """Returns `factor` minus the OLS projection on `baseline_df` columns
    (with implicit intercept).

    Output is aligned to `factor.index`. Insufficient data (< 30 rows or
    < 1 baseline column) yields NaN-filled output.
    """
    df = pd.concat([factor.rename("f"), baseline_df], axis=1).dropna()
    out = pd.Series(np.nan, index=factor.index, dtype="float64")
    if df.shape[0] < 30 or df.shape[1] < 2:
        return out
    y = df["f"].values
    x = df.drop(columns=["f"]).values
    x_aug = np.column_stack([np.ones(x.shape[0]), x])
    try:
        beta, *_ = np.linalg.lstsq(x_aug, y, rcond=None)
    except np.linalg.LinAlgError:
        return out
    residual = y - x_aug @ beta
    out.loc[df.index] = residual
    return out


def autocorr_per_subject(
    factor: pd.Series,
    subjects: pd.Series,
    *,
    lag: int = 30,
    min_obs_buffer: int = 5,
) -> pd.Series:
    """Per-subject autocorrelation at the requested lag.

    Subjects with fewer than `lag + min_obs_buffer` valid observations are
    excluded (autocorr at long lag with too few samples is meaningless).
    """
    out: dict[str, float] = {}
    for s, g in factor.groupby(subjects):
        gd = g.dropna()
        if gd.shape[0] < lag + min_obs_buffer:
            continue
        ac = gd.autocorr(lag=lag)
        if pd.notna(ac):
            out[str(s)] = float(ac)
    return pd.Series(out, dtype="float64")


def build_regime_by_ts(
    features: pd.DataFrame,
    *,
    anchor_subject: str = "BTC",
    vol_column: str = "realized_volatility_20",
) -> pd.Series:
    """Build a per-timestamp regime label using the anchor subject's vol tertile.

    Returns a Series indexed by `timestamp_ms` with values in
    {"low_vol", "mid_vol", "high_vol"}. Raises `RuntimeError` if the anchor
    subject is missing or has no vol data — caller should pre-validate.
    """
    if "subject" not in features.columns or "timestamp_ms" not in features.columns:
        raise RuntimeError("features must contain 'subject' and 'timestamp_ms' columns")
    anchor = features[features["subject"] == anchor_subject]
    if anchor.empty or vol_column not in anchor.columns:
        available = sorted(features["subject"].dropna().unique().tolist())
        raise RuntimeError(
            f"anchor_subject={anchor_subject!r} not found or has no {vol_column}; "
            f"available subjects: {available[:10]}{'...' if len(available) > 10 else ''}"
        )
    rv = (
        pd.to_numeric(anchor.set_index("timestamp_ms")[vol_column], errors="coerce")
        .replace(0.0, np.nan)
        .dropna()
    )
    if rv.empty:
        raise RuntimeError(f"{anchor_subject} {vol_column} is all NaN")
    q_lo, q_hi = rv.quantile([1.0 / 3, 2.0 / 3]).tolist()

    def _tag(x: float) -> str:
        if pd.isna(x):
            return "unknown"
        if x < q_lo:
            return "low_vol"
        if x > q_hi:
            return "high_vol"
        return "mid_vol"

    return rv.apply(_tag)


# === Gate primitives ===


def _gate_nan(metric: str, threshold: float | str) -> dict[str, Any]:
    return {"metric": metric, "value": float("nan"), "threshold": threshold, "passed": False}


def gate_g1_ic_mean(
    ic_series: pd.Series, *, contract: dict[str, Any] | None = None
) -> dict[str, Any]:
    threshold = _threshold(contract or {}, "g1_ic_mean", "abs_min", 0.04)
    valid = ic_series.dropna()
    if valid.empty:
        return _gate_nan("ic_mean", threshold)
    mean = float(valid.mean())
    std = float(valid.std())
    ir = mean / std if std and std > 0 else float("nan")
    pos = float((valid > 0).mean())
    return {
        "metric": "ic_mean",
        "value": mean,
        "std": std,
        "ir": ir,
        "pos_day_rate": pos,
        "n_days": int(valid.shape[0]),
        "threshold": threshold,
        "passed": bool(abs(mean) >= threshold),
    }


def gate_g2_ic_stability(
    ic_series: pd.Series, *, contract: dict[str, Any] | None = None
) -> dict[str, Any]:
    section = (contract or {}).get("g2_ic_stability", {}) or {}
    window = int(section.get("window", 60) or 60)
    threshold = _threshold(contract or {}, "g2_ic_stability", "pos_fraction_min", 0.55)
    valid = ic_series.dropna().sort_index()
    if valid.shape[0] < window:
        return _gate_nan("rolling_60d_ic_pos_fraction", threshold)
    rolling = valid.rolling(window).mean().dropna()
    if rolling.empty:
        return _gate_nan("rolling_60d_ic_pos_fraction", threshold)
    pos = float((rolling > 0).mean())
    return {
        "metric": "rolling_60d_ic_pos_fraction",
        "value": pos,
        "window": window,
        "max_drop": float(rolling.min()),
        "max_rise": float(rolling.max()),
        "threshold": threshold,
        "passed": bool(pos >= threshold),
    }


def gate_g3_regime_consistency(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    regime_by_ts: pd.Series,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    threshold = _threshold(contract or {}, "g3_regime_consistency", "same_sign_fraction_min", 0.60)
    ic = per_timestamp_rank_ic(factor, target, timestamps)
    if ic.empty:
        return _gate_nan("regime_ic_same_sign_fraction", threshold)
    aligned = pd.DataFrame(
        {"ic": ic, "regime": regime_by_ts.reindex(ic.index)}
    ).dropna()
    if aligned.empty:
        return _gate_nan("regime_ic_same_sign_fraction", threshold)
    means = aligned.groupby("regime")["ic"].mean()
    if len(means) < 2:
        return _gate_nan("regime_ic_same_sign_fraction", threshold)
    overall_sign = np.sign(means.mean())
    if overall_sign == 0:
        return _gate_nan("regime_ic_same_sign_fraction", threshold)
    same = float((np.sign(means) == overall_sign).mean())
    return {
        "metric": "regime_ic_same_sign_fraction",
        "value": same,
        "regime_ic": {str(k): float(v) for k, v in means.items()},
        "threshold": threshold,
        "passed": bool(same >= threshold),
    }


def gate_g4_concentration(
    factor: pd.Series,
    target: pd.Series,
    subjects: pd.Series,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    threshold = _threshold(contract or {}, "g4_concentration", "top1_share_max", 0.30)
    per_asset = per_subject_rank_ic(factor, target, subjects)
    if per_asset.empty:
        return _gate_nan("top1_asset_ic_share", threshold)
    abs_total = float(per_asset.abs().sum())
    if abs_total <= 0:
        return _gate_nan("top1_asset_ic_share", threshold)
    top1 = float(per_asset.abs().max() / abs_total)
    top1_subject = str(per_asset.abs().idxmax())
    return {
        "metric": "top1_asset_ic_share",
        "value": top1,
        "top_subject": top1_subject,
        "per_asset_ic": {str(k): float(v) for k, v in per_asset.items()},
        "threshold": threshold,
        "passed": bool(top1 <= threshold),
    }


def gate_g5_vif(
    factor: pd.Series,
    baseline_df: pd.DataFrame,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    threshold = _threshold(contract or {}, "g5_vif", "vif_max", 5.0)
    df = pd.concat([factor.rename("f"), baseline_df], axis=1).dropna()
    if df.shape[0] < 30 or df.shape[1] < 2:
        return _gate_nan("vif_vs_admitted_baseline", threshold)
    y = df["f"].values
    x = df.drop(columns=["f"]).values
    x_aug = np.column_stack([np.ones(x.shape[0]), x])
    try:
        beta, *_ = np.linalg.lstsq(x_aug, y, rcond=None)
    except np.linalg.LinAlgError:
        return _gate_nan("vif_vs_admitted_baseline", threshold)
    residual = y - x_aug @ beta
    ss_res = float((residual ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    vif = 1.0 / (1.0 - r2) if r2 < 1.0 else float("inf")
    return {
        "metric": "vif_vs_admitted_baseline",
        "value": float(vif),
        "r2": float(r2),
        "threshold": threshold,
        "passed": bool(vif <= threshold),
    }


def gate_g6_residual_ic(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    baseline_df: pd.DataFrame,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    threshold = _threshold(contract or {}, "g6_orthogonal_residual_ic", "abs_min", 0.02)
    residual = orthogonalize(factor, baseline_df)
    ic = per_timestamp_rank_ic(residual, target, timestamps)
    valid = ic.dropna()
    if valid.empty:
        return _gate_nan("residual_ic_vs_admitted_baseline", threshold)
    mean = float(valid.mean())
    return {
        "metric": "residual_ic_vs_admitted_baseline",
        "value": mean,
        "std": float(valid.std()),
        "n_days": int(valid.shape[0]),
        "threshold": threshold,
        "passed": bool(abs(mean) >= threshold),
    }


def gate_g7_turnover(
    factor: pd.Series,
    subjects: pd.Series,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    section = (contract or {}).get("g7_turnover", {}) or {}
    lag = int(section.get("lag", 30) or 30)
    threshold = _threshold(contract or {}, "g7_turnover", "turnover_max", 0.80)
    autos = autocorr_per_subject(factor, subjects, lag=lag)
    if autos.empty:
        return _gate_nan("turnover_30d", threshold)
    auto_mean = float(autos.mean())
    turnover = 1.0 - auto_mean
    return {
        "metric": "turnover_30d",
        "value": float(turnover),
        "mean_autocorr_lag": float(auto_mean),
        "lag": lag,
        "threshold": threshold,
        "passed": bool(turnover <= threshold),
    }


def gate_g8_capacity_ic(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    capacity_score: pd.Series,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    section = (contract or {}).get("g8_capacity_aware_ic", {}) or {}
    top_quantile = float(section.get("top_capacity_quantile", 0.5) or 0.5)
    threshold = _threshold(contract or {}, "g8_capacity_aware_ic", "retention_min", 0.70)
    full_ic = per_timestamp_rank_ic(factor, target, timestamps)
    full_mean = float(full_ic.dropna().mean()) if full_ic.notna().any() else float("nan")
    df = pd.DataFrame(
        {"f": factor, "t": target, "ts": timestamps, "c": capacity_score}
    ).dropna()
    if df.empty:
        return _gate_nan("capacity_ic_retention_ratio", threshold)
    df["cap_rank"] = df.groupby("ts")["c"].rank(pct=True)
    top_subset = df[df["cap_rank"] >= top_quantile]
    if top_subset.empty:
        return _gate_nan("capacity_ic_retention_ratio", threshold)
    cap_ic = per_timestamp_rank_ic(top_subset["f"], top_subset["t"], top_subset["ts"])
    cap_mean = float(cap_ic.dropna().mean()) if cap_ic.notna().any() else float("nan")
    if math.isnan(full_mean) or full_mean == 0 or math.isnan(cap_mean):
        return _gate_nan("capacity_ic_retention_ratio", threshold)
    ratio = abs(cap_mean) / abs(full_mean)
    return {
        "metric": "capacity_ic_retention_ratio",
        "value": float(ratio),
        "full_ic": full_mean,
        "capacity_ic": cap_mean,
        "top_quantile": top_quantile,
        "threshold": threshold,
        "passed": bool(ratio >= threshold),
    }


def gate_g9_crowding(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    public_df: pd.DataFrame,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    threshold = _threshold(contract or {}, "g9_crowding", "abs_min", 0.02)
    residual = orthogonalize(factor, public_df)
    ic = per_timestamp_rank_ic(residual, target, timestamps)
    valid = ic.dropna()
    if valid.empty:
        return _gate_nan("residual_ic_vs_public_factors", threshold)
    mean = float(valid.mean())
    return {
        "metric": "residual_ic_vs_public_factors",
        "value": mean,
        "public_factors": list(public_df.columns),
        "threshold": threshold,
        "passed": bool(abs(mean) >= threshold),
    }


def gate_g10_out_of_universe(
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    capacity_score: pd.Series,
    *,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    section = (contract or {}).get("g10_out_of_universe", {}) or {}
    capacity_quantile_max = float(section.get("capacity_quantile_max", 0.5) or 0.5)
    threshold = _threshold(contract or {}, "g10_out_of_universe", "ic_abs_min", 0.03)
    df = pd.DataFrame(
        {"f": factor, "t": target, "ts": timestamps, "c": capacity_score}
    ).dropna()
    if df.empty:
        return _gate_nan("midcap_subset_ic", threshold)
    df["cap_rank"] = df.groupby("ts")["c"].rank(pct=True)
    bottom_subset = df[df["cap_rank"] < capacity_quantile_max]
    if bottom_subset.empty:
        return _gate_nan("midcap_subset_ic", threshold)
    ic = per_timestamp_rank_ic(bottom_subset["f"], bottom_subset["t"], bottom_subset["ts"])
    valid = ic.dropna()
    if valid.empty:
        return _gate_nan("midcap_subset_ic", threshold)
    mean = float(valid.mean())
    return {
        "metric": "midcap_subset_ic",
        "value": mean,
        "n_days": int(valid.shape[0]),
        "capacity_quantile_max": capacity_quantile_max,
        "threshold": threshold,
        "passed": bool(abs(mean) >= threshold),
    }


def gate_g11_falsification(declaration: str | None) -> dict[str, Any]:
    return {
        "metric": "falsification_declared",
        "value": declaration if declaration else None,
        "threshold": "non_empty_declaration",
        "passed": bool(declaration and declaration.strip()),
    }


# === Top-level evaluation ===


def evaluate_admission_v2(
    *,
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    subjects: pd.Series,
    baseline_df: pd.DataFrame,
    public_df: pd.DataFrame,
    capacity_score: pd.Series,
    regime_by_ts: pd.Series,
    falsification: str,
    contract: dict[str, Any] | None = None,
    self_exclusion_column: str | None = None,
) -> dict[str, Any]:
    """Evaluate the 11-gate admission for a single factor.

    `self_exclusion_column` (when provided) drops the named column from
    `baseline_df` and `public_df` before running G5 / G6 / G9; this avoids
    the trivial "factor regressed on itself" case when scoring an existing
    baseline factor against the baseline.

    Returns a dict with `gates` (per-gate detail), `gate_pass_count`,
    `gate_total`, `all_passed`, plus a top-level `verdict` string in
    `{"strict_pass", "boundary", "fail"}`. `boundary` is reserved for
    factors that pass G6 to within 5% of the threshold (a practical
    near-miss tag observed in the W1.4 manifest's F12 admission).
    """
    if self_exclusion_column:
        baseline_for_factor = baseline_df.drop(columns=[self_exclusion_column], errors="ignore")
        public_for_factor = public_df.drop(columns=[self_exclusion_column], errors="ignore")
    else:
        baseline_for_factor = baseline_df
        public_for_factor = public_df

    ic_series = per_timestamp_rank_ic(factor, target, timestamps)
    gates = {
        "G1_ic_mean": gate_g1_ic_mean(ic_series, contract=contract),
        "G2_ic_stability": gate_g2_ic_stability(ic_series, contract=contract),
        "G3_regime_consistency": gate_g3_regime_consistency(factor, target, timestamps, regime_by_ts, contract=contract),
        "G4_concentration": gate_g4_concentration(factor, target, subjects, contract=contract),
        "G5_vif": gate_g5_vif(factor, baseline_for_factor, contract=contract),
        "G6_orthogonal_residual_ic": gate_g6_residual_ic(factor, target, timestamps, baseline_for_factor, contract=contract),
        "G7_turnover": gate_g7_turnover(factor, subjects, contract=contract),
        "G8_capacity_aware_ic": gate_g8_capacity_ic(factor, target, timestamps, capacity_score, contract=contract),
        "G9_crowding": gate_g9_crowding(factor, target, timestamps, public_for_factor, contract=contract),
        "G10_out_of_universe": gate_g10_out_of_universe(factor, target, timestamps, capacity_score, contract=contract),
        "G11_falsification": gate_g11_falsification(falsification),
    }
    pass_count = sum(1 for g in gates.values() if g.get("passed"))
    g6 = gates["G6_orthogonal_residual_ic"]
    g3 = gates["G3_regime_consistency"]
    # The strict admission decision is "G6 PASS AND G3 PASS" — the doc's
    # §G.6 / §G.4 binding combination. Boundary = G6 within 5% of the
    # threshold (the F12 case observed in W1.4).
    g6_value = g6.get("value")
    g6_threshold = g6.get("threshold", 0.02)
    boundary = (
        isinstance(g6_value, (int, float))
        and not (isinstance(g6_value, float) and (math.isnan(g6_value) or math.isinf(g6_value)))
        and g3.get("passed")
        and abs(g6_value) >= 0.95 * g6_threshold
        and abs(g6_value) < g6_threshold
    )
    if g6.get("passed") and g3.get("passed"):
        verdict = "strict_pass"
    elif boundary:
        verdict = "boundary"
    else:
        verdict = "fail"
    return {
        "gates": gates,
        "gate_pass_count": int(pass_count),
        "gate_total": int(len(gates)),
        "all_passed": bool(pass_count == len(gates)),
        "verdict": verdict,
        "g6_strict_pass": bool(g6.get("passed")),
        "g3_strict_pass": bool(g3.get("passed")),
    }


def sanitize_for_json(obj: Any) -> Any:
    """Convert NaN/Inf/numpy scalars to JSON-safe values."""
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return [sanitize_for_json(v) for v in obj.tolist()]
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else obj
    return obj
