"""compute_lsk3_baseline_decay_diagnostic.py — diagnose whether lsk3
baseline decay observed in M2.5 demotion experiment is panel regime
shift or internal-redundancy artifact.

Context. M2.5 factor_lifecycle demotion experiment found 7/11 lsk3
factors recommended `watch` / `decay` / `retired` based on rolling-
60d / 90d *self-residual* IC (each factor evaluated against the OTHER
10 lsk3 factors as baseline). 3 factors (coinglass_top_trader_long_pct
_smooth_5, momentum_decay_5_20, quality_funding_oi) crossed 90d cum
resid IC < 0 → recommended retire.

Two competing hypotheses:
  (a) Internal redundancy: lsk3 factors mutually absorb each other's
      signal → self-residual IC dominated by noise.
  (b) Regime shift: 2026 late-panel slice exhibits genuine signal decay
      in some lsk3 factors.

This diagnostic disentangles the two by computing:

  Step 1: Temporal split — raw IC (no residualization) on early 70% vs
          last 30% of panel. Strong-early-weak-late = regime shift.
          Weak-throughout = always redundant or always weak.

  Step 2: Temporal split — self-residual IC same split. If residual
          only goes negative late, baseline coverage may have shifted.

  Step 3: Internal correlation matrix — per-timestamp spearman corr
          across all 11 lsk3 pairs. High-corr pairs (>0.5) reveal
          mutual coverage that depletes self-residual IC.

  Step 4: Late-period bootstrap — 1000 row-bootstrap resamples of
          the late 30% panel, raw IC distribution per factor. Compare
          95% CI vs 0 and vs G1 admission floor 0.04.

  Step 5: Per-factor verdict — combines steps 1-4 into:
            regime_shift_evidence: bool (raw IC late-vs-early degraded)
            internal_redundancy_evidence: bool (max pairwise corr > 0.5)
            statistical_significance_late: bool (bootstrap CI excludes 0)
            recommended_action: keep / re-evaluate / restructure

Output:
  artifacts/quant_research/factor_reports/<as-of>/lsk3_baseline_decay_diagnostic.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.feature_admission_v2 import (  # noqa: E402
    orthogonalize,
    per_timestamp_rank_ic,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _rebuild_features_with_w3_columns,
)


CARD_CONTRACT_VERSION = "quant_lsk3_baseline_decay_diagnostic.v1"

LSK3_BASELINE = (
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
)

# Diagnostic parameters
EARLY_FRACTION = 0.70           # first 70% of timestamps = "early"
LATE_FRACTION = 0.30            # last 30% of timestamps = "late"
G1_ABS_MIN = 0.04               # admission floor for "raw IC strong"
INTERNAL_CORR_THRESHOLD = 0.50  # pairwise corr above this = redundancy evidence
BOOTSTRAP_ITERATIONS = 1000
RNG_SEED = 20260430


def _ic_with_t_stat(
    factor: pd.Series, target: pd.Series, timestamps: pd.Series
) -> tuple[float, float, int]:
    """Returns (mean_ic, t_stat, n_ts)."""
    factor_clean = pd.to_numeric(factor, errors="coerce").fillna(0.0)
    target_clean = pd.to_numeric(target, errors="coerce")
    ic = per_timestamp_rank_ic(factor_clean, target_clean, timestamps).dropna()
    if len(ic) < 5:
        return float("nan"), float("nan"), int(len(ic))
    m = float(ic.mean())
    s = float(ic.std()) if len(ic) > 1 else 0.0
    n = int(len(ic))
    t = float(m * np.sqrt(n) / s) if s > 0 else 0.0
    return m, t, n


def _split_panel_by_timestamp(panel: pd.DataFrame, early_frac: float = EARLY_FRACTION):
    """Split panel into early (first early_frac of unique timestamps) and
    late (remaining 1-early_frac). Returns (early_panel, late_panel,
    cutoff_timestamp_ms)."""
    unique_ts = sorted(panel["timestamp_ms"].unique())
    n_ts = len(unique_ts)
    cutoff_idx = int(n_ts * early_frac)
    cutoff_ts = unique_ts[cutoff_idx]
    early = panel[panel["timestamp_ms"] < cutoff_ts]
    late = panel[panel["timestamp_ms"] >= cutoff_ts]
    return early, late, int(cutoff_ts)


def step1_temporal_raw_ic(
    panel: pd.DataFrame, early: pd.DataFrame, late: pd.DataFrame
) -> dict:
    """Per-factor raw IC on full / early / late samples."""
    target_full = panel["target_forward_return"]
    target_early = early["target_forward_return"]
    target_late = late["target_forward_return"]
    ts_full = panel["timestamp_ms"]
    ts_early = early["timestamp_ms"]
    ts_late = late["timestamp_ms"]

    out = {}
    for col in LSK3_BASELINE:
        if col not in panel.columns:
            out[col] = {"status": "missing"}
            continue
        full_ic, full_t, full_n = _ic_with_t_stat(panel[col], target_full, ts_full)
        early_ic, early_t, early_n = _ic_with_t_stat(early[col], target_early, ts_early)
        late_ic, late_t, late_n = _ic_with_t_stat(late[col], target_late, ts_late)
        out[col] = {
            "full": {"raw_ic_mean": full_ic, "t_stat": full_t, "n_ts": full_n},
            "early_70pct": {"raw_ic_mean": early_ic, "t_stat": early_t, "n_ts": early_n},
            "late_30pct": {"raw_ic_mean": late_ic, "t_stat": late_t, "n_ts": late_n},
            "delta_late_minus_early": late_ic - early_ic,
            "regime_shift_evidence": _flag_regime_shift(early_ic, late_ic),
        }
    return out


def _flag_regime_shift(early_ic: float, late_ic: float) -> bool:
    """Heuristic: regime shift if (a) sign-flip between early and late OR
    (b) abs(late) drops more than 50% relative to abs(early) AND late
    abs IC < G1 floor 0.04.
    """
    if np.isnan(early_ic) or np.isnan(late_ic):
        return False
    if abs(early_ic) < 0.005:
        return False  # too weak to claim shift
    sign_flip = (early_ic > 0) != (late_ic > 0)
    magnitude_decay = abs(late_ic) < 0.5 * abs(early_ic) and abs(late_ic) < G1_ABS_MIN
    return sign_flip or magnitude_decay


def step2_temporal_residual_ic(
    panel: pd.DataFrame, early: pd.DataFrame, late: pd.DataFrame
) -> dict:
    """Per-factor self-residual IC (baseline = lsk3 minus self) on
    full / early / late.
    """
    out = {}
    for col in LSK3_BASELINE:
        if col not in panel.columns:
            out[col] = {"status": "missing"}
            continue
        baseline_cols = [c for c in LSK3_BASELINE if c != col and c in panel.columns]

        def _resid_ic(_panel: pd.DataFrame) -> tuple[float, float, int]:
            factor = _panel[col]
            target = _panel["target_forward_return"]
            ts = _panel["timestamp_ms"]
            baseline_df = _panel[baseline_cols].apply(pd.to_numeric, errors="coerce")
            factor_clean = pd.to_numeric(factor, errors="coerce").fillna(0.0)
            residual = orthogonalize(factor_clean, baseline_df)
            target_clean = pd.to_numeric(target, errors="coerce")
            ic = per_timestamp_rank_ic(residual, target_clean, ts).dropna()
            if len(ic) < 5:
                return float("nan"), float("nan"), int(len(ic))
            m = float(ic.mean())
            s = float(ic.std()) if len(ic) > 1 else 0.0
            n = int(len(ic))
            t = float(m * np.sqrt(n) / s) if s > 0 else 0.0
            return m, t, n

        full_ic, full_t, full_n = _resid_ic(panel)
        early_ic, early_t, early_n = _resid_ic(early)
        late_ic, late_t, late_n = _resid_ic(late)
        out[col] = {
            "full": {"resid_ic_mean": full_ic, "t_stat": full_t, "n_ts": full_n},
            "early_70pct": {"resid_ic_mean": early_ic, "t_stat": early_t, "n_ts": early_n},
            "late_30pct": {"resid_ic_mean": late_ic, "t_stat": late_t, "n_ts": late_n},
            "delta_late_minus_early": late_ic - early_ic,
        }
    return out


def step3_internal_correlation(panel: pd.DataFrame) -> dict:
    """11x11 lsk3 internal correlation matrix (per-timestamp mean of
    pairwise spearman correlations). High-corr pair (>0.5) flags
    redundancy evidence.
    """
    cols = [c for c in LSK3_BASELINE if c in panel.columns]
    pair_corrs = {}
    redundancy_pairs = []
    for i, c1 in enumerate(cols):
        for c2 in cols[i + 1:]:
            x = pd.to_numeric(panel[c1], errors="coerce")
            y = pd.to_numeric(panel[c2], errors="coerce")
            ts = panel["timestamp_ms"]
            df = pd.DataFrame({"x": x, "y": y, "ts": ts}).dropna()
            if df.empty:
                continue
            grouped = df.groupby("ts")
            corrs = []
            for _, g in grouped:
                if len(g) >= 5:
                    c = g["x"].corr(g["y"], method="spearman")
                    if pd.notna(c):
                        corrs.append(c)
            if not corrs:
                continue
            mean_corr = float(np.mean(corrs))
            pair_corrs[f"{c1}__vs__{c2}"] = {
                "mean_per_ts_spearman": mean_corr,
                "n_ts": len(corrs),
                "abs_above_threshold": abs(mean_corr) > INTERNAL_CORR_THRESHOLD,
            }
            if abs(mean_corr) > INTERNAL_CORR_THRESHOLD:
                redundancy_pairs.append((c1, c2, mean_corr))

    # Per-factor: max abs corr with any other factor
    per_factor_max = {}
    for col in cols:
        max_abs = 0.0
        max_partner = None
        for k, v in pair_corrs.items():
            if col in k:
                if abs(v["mean_per_ts_spearman"]) > max_abs:
                    max_abs = abs(v["mean_per_ts_spearman"])
                    other = k.replace(f"{col}__vs__", "").replace(f"__vs__{col}", "")
                    max_partner = other
        per_factor_max[col] = {
            "max_abs_pairwise_corr": max_abs,
            "max_corr_partner": max_partner,
            "internal_redundancy_evidence": max_abs > INTERNAL_CORR_THRESHOLD,
        }

    return {
        "redundancy_threshold": INTERNAL_CORR_THRESHOLD,
        "n_pairs_above_threshold": len(redundancy_pairs),
        "redundancy_pairs": [
            {"a": a, "b": b, "mean_per_ts_spearman": float(c)} for a, b, c in redundancy_pairs
        ],
        "per_factor_max_corr": per_factor_max,
    }


def step4_late_bootstrap(late: pd.DataFrame, *, iterations: int = BOOTSTRAP_ITERATIONS) -> dict:
    """Late-period bootstrap of raw IC per lsk3 factor. Per iteration:
    bootstrap-sample 80% of timestamps with replacement, compute IC.
    Output: per-factor 95% CI, std, fraction CI excluding 0.
    """
    rng = np.random.default_rng(RNG_SEED)
    unique_ts = late["timestamp_ms"].unique()
    n_ts = len(unique_ts)
    sample_size = max(int(n_ts * 0.8), 30)

    out = {}
    for col in LSK3_BASELINE:
        if col not in late.columns:
            out[col] = {"status": "missing"}
            continue
        ic_samples = []
        for _ in range(iterations):
            sample_ts = rng.choice(unique_ts, size=sample_size, replace=True)
            sub = late[late["timestamp_ms"].isin(sample_ts)]
            m, _, _ = _ic_with_t_stat(sub[col], sub["target_forward_return"], sub["timestamp_ms"])
            if not np.isnan(m):
                ic_samples.append(m)
        if not ic_samples:
            out[col] = {"status": "no_samples"}
            continue
        arr = np.asarray(ic_samples)
        ci_low = float(np.quantile(arr, 0.025))
        ci_high = float(np.quantile(arr, 0.975))
        ci_excludes_zero = (ci_low > 0 and ci_high > 0) or (ci_low < 0 and ci_high < 0)
        ci_excludes_g1 = (ci_low > G1_ABS_MIN and ci_high > G1_ABS_MIN) or (
            ci_low < -G1_ABS_MIN and ci_high < -G1_ABS_MIN
        )
        out[col] = {
            "n_iterations": int(len(ic_samples)),
            "bootstrap_mean_ic": float(arr.mean()),
            "bootstrap_std_ic": float(arr.std()),
            "ci_95_low": ci_low,
            "ci_95_high": ci_high,
            "ci_excludes_zero": bool(ci_excludes_zero),
            "ci_excludes_g1_floor": bool(ci_excludes_g1),
        }
    return out


def step5_per_factor_verdict(step1: dict, step2: dict, step3: dict, step4: dict) -> dict:
    """Combine steps 1-4 into per-factor verdict."""
    verdicts = {}
    for col in LSK3_BASELINE:
        s1 = step1.get(col, {})
        s2 = step2.get(col, {})
        s3 = step3.get("per_factor_max_corr", {}).get(col, {})
        s4 = step4.get(col, {})
        if "status" in s1:
            verdicts[col] = {"status": "missing"}
            continue

        regime_shift = bool(s1.get("regime_shift_evidence", False))
        internal_redundancy = bool(s3.get("internal_redundancy_evidence", False))
        late_significant = bool(s4.get("ci_excludes_zero", False))
        late_strong = bool(s4.get("ci_excludes_g1_floor", False))

        full_raw_ic = s1.get("full", {}).get("raw_ic_mean", float("nan"))
        late_raw_ic = s1.get("late_30pct", {}).get("raw_ic_mean", float("nan"))
        late_resid_ic = s2.get("late_30pct", {}).get("resid_ic_mean", float("nan"))

        # Decision tree
        if internal_redundancy and not regime_shift:
            action = "keep — internal redundancy explains negative self-residual IC; raw IC stable"
        elif regime_shift and not internal_redundancy:
            action = "re-evaluate — late-period raw IC degraded; possible signal decay"
        elif regime_shift and internal_redundancy:
            action = "restructure — both regime shift AND redundancy; lsk3 baseline composition needs review"
        elif not late_significant and not internal_redundancy:
            action = "keep — late IC noisy but no clear decay or redundancy"
        else:
            action = "keep — passes diagnostics"

        verdicts[col] = {
            "factor": col,
            "regime_shift_evidence": regime_shift,
            "internal_redundancy_evidence": internal_redundancy,
            "late_bootstrap_ci_excludes_zero": late_significant,
            "late_bootstrap_ci_excludes_g1_floor": late_strong,
            "full_raw_ic_mean": full_raw_ic,
            "late_raw_ic_mean": late_raw_ic,
            "late_resid_ic_mean": late_resid_ic,
            "max_pairwise_corr": s3.get("max_abs_pairwise_corr"),
            "max_corr_partner": s3.get("max_corr_partner"),
            "recommended_action": action,
        }
    return verdicts


def main() -> int:
    parser = argparse.ArgumentParser(description="lsk3 baseline late-2026 decay diagnostic.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_ARTIFACT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    parser.add_argument("--bootstrap-iterations", type=int, default=BOOTSTRAP_ITERATIONS)
    args = parser.parse_args()

    print(f"=== lsk3 baseline decay diagnostic (as-of {args.as_of}) ===")
    raw_panel = pd.read_csv(args.features, compression="gzip")
    print(f"  raw panel shape: {raw_panel.shape}")
    print("  rebuilding W3 columns...")
    panel = _rebuild_features_with_w3_columns(raw_panel)
    print(f"  rebuilt panel shape: {panel.shape}")
    print()

    print(f"=== Splitting panel: early {EARLY_FRACTION:.0%} vs late {LATE_FRACTION:.0%} ===")
    early, late, cutoff_ts = _split_panel_by_timestamp(panel, EARLY_FRACTION)
    cutoff_date = datetime.fromtimestamp(cutoff_ts / 1000, tz=timezone.utc).date().isoformat()
    print(f"  cutoff at timestamp_ms {cutoff_ts} (date {cutoff_date})")
    print(f"  early shape: {early.shape}  late shape: {late.shape}")
    print()

    print("=== Step 1: Temporal raw IC (no residualization) ===")
    s1 = step1_temporal_raw_ic(panel, early, late)
    for col, v in s1.items():
        if "status" in v:
            print(f"  {col}: {v['status']}")
            continue
        flag = "REGIME_SHIFT" if v["regime_shift_evidence"] else "stable"
        print(
            f"  {col:50s}  full IC={v['full']['raw_ic_mean']:+.4f}  "
            f"early IC={v['early_70pct']['raw_ic_mean']:+.4f}  "
            f"late IC={v['late_30pct']['raw_ic_mean']:+.4f}  "
            f"Δ={v['delta_late_minus_early']:+.4f}  [{flag}]"
        )
    print()

    print("=== Step 2: Temporal self-residual IC ===")
    s2 = step2_temporal_residual_ic(panel, early, late)
    for col, v in s2.items():
        if "status" in v:
            continue
        print(
            f"  {col:50s}  full resid IC={v['full']['resid_ic_mean']:+.4f}  "
            f"early={v['early_70pct']['resid_ic_mean']:+.4f}  "
            f"late={v['late_30pct']['resid_ic_mean']:+.4f}  "
            f"Δ={v['delta_late_minus_early']:+.4f}"
        )
    print()

    print("=== Step 3: Internal pairwise correlation (per-ts spearman mean) ===")
    s3 = step3_internal_correlation(panel)
    print(f"  pairs above |corr|>{INTERNAL_CORR_THRESHOLD}: {s3['n_pairs_above_threshold']}")
    if s3["redundancy_pairs"]:
        for p in s3["redundancy_pairs"]:
            print(f"    {p['a']:48s} <-> {p['b']:48s}  corr={p['mean_per_ts_spearman']:+.3f}")
    else:
        print("  no high-correlation pairs found")
    print()
    print("  per-factor max abs corr partner:")
    for col, v in s3["per_factor_max_corr"].items():
        flag = " REDUNDANCY" if v["internal_redundancy_evidence"] else ""
        print(
            f"    {col:50s}  max |corr|={v['max_abs_pairwise_corr']:.3f}  "
            f"partner={v.get('max_corr_partner','-')}{flag}"
        )
    print()

    print(f"=== Step 4: Late-period bootstrap raw IC ({args.bootstrap_iterations} iterations) ===")
    s4 = step4_late_bootstrap(late, iterations=args.bootstrap_iterations)
    for col, v in s4.items():
        if "status" in v:
            continue
        ci_zero = "≠0" if v["ci_excludes_zero"] else "incl0"
        ci_g1 = "|>G1|" if v["ci_excludes_g1_floor"] else "<G1"
        print(
            f"  {col:50s}  mean={v['bootstrap_mean_ic']:+.4f}  std={v['bootstrap_std_ic']:.4f}  "
            f"CI95=[{v['ci_95_low']:+.4f}, {v['ci_95_high']:+.4f}]  {ci_zero}  {ci_g1}"
        )
    print()

    print("=== Step 5: Per-factor verdict ===")
    s5 = step5_per_factor_verdict(s1, s2, s3, s4)
    for col, v in s5.items():
        if "status" in v:
            continue
        flags = []
        if v["regime_shift_evidence"]:
            flags.append("REGIME_SHIFT")
        if v["internal_redundancy_evidence"]:
            flags.append("REDUNDANT")
        if v["late_bootstrap_ci_excludes_zero"]:
            flags.append("LATE_SIG")
        flag_str = "/".join(flags) if flags else "stable"
        print(f"  {col:50s}  [{flag_str:30s}]  → {v['recommended_action']}")
    print()

    out = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "features_artifact": str(args.features),
        "early_fraction": EARLY_FRACTION,
        "late_fraction": LATE_FRACTION,
        "cutoff_timestamp_ms": cutoff_ts,
        "cutoff_date_utc": cutoff_date,
        "n_early_rows": int(len(early)),
        "n_late_rows": int(len(late)),
        "diagnostic_parameters": {
            "g1_abs_min": G1_ABS_MIN,
            "internal_corr_threshold": INTERNAL_CORR_THRESHOLD,
            "bootstrap_iterations": int(args.bootstrap_iterations),
        },
        "step1_temporal_raw_ic": s1,
        "step2_temporal_self_residual_ic": s2,
        "step3_internal_correlation": s3,
        "step4_late_bootstrap": s4,
        "step5_per_factor_verdict": s5,
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "lsk3_baseline_decay_diagnostic.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"=== Done. Diagnostic at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
