"""run_factor_lifecycle_demotion_experiment.py — M2.5 / Day 60 exit
criterion bullet 3.

Runs the factor_lifecycle G.5 state machine across the full factor
inventory (lsk3 baseline + score-integrated extensions + plumbed
candidates + falsified candidates) and writes a lifecycle report JSON.

Doc anchor: alpha_ontology_and_factor_library.md §G.5 + §H.3 M2.5
("写 factor_lifecycle.py: 实现 G.5 中的 active/watch/decay/retired 状态机")
+ data_utilization_roadmap.md Snapshot status section.

The experiment evaluates rolling-60d / rolling-30d / rolling-90d
residual IC for each factor against the appropriate admitted baseline,
then applies the state machine. Output is owner-actionable: lists
factors recommended for demotion (active → watch / decay / retired)
and for revival (retired → revived candidate).

Output:
  artifacts/quant_research/factor_lifecycle/<as-of>/lifecycle_report.json

This is a *recommendation engine*, not auto-mutation: manifest edits
remain owner-driven. Lifecycle markers in
cross_sectional_hypothesis_batch_manifest_alpha_ontology_v*.json
remain the source of truth and are updated by humans after reviewing
this report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.factor_lifecycle import (  # noqa: E402
    FACTOR_LIFECYCLE_CONTRACT_VERSION,
    evaluate_factor_lifecycle_batch,
)
from enhengclaw.quant_research.regime_gating import (  # noqa: E402
    DEFAULT_FEATURES_ARTIFACT,
    _load_panel,
    _rebuild_features_with_w3_columns,
)


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

LIVE_HV_BALANCED_BASELINE = (
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "downside_upside_vol_ratio_30",
)

RESEARCH_V5_RW_BRIDGE_NO_OVERLAY_H10D_BASELINE = (
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
    "settlement_cycle_premium_60d",
)

BASELINE_PRESETS: dict[str, tuple[str, ...]] = {
    "lsk3": LSK3_BASELINE,
    "live_hv_balanced": LIVE_HV_BALANCED_BASELINE,
    "research_v5_rw_bridge_no_overlay_h10d": RESEARCH_V5_RW_BRIDGE_NO_OVERLAY_H10D_BASELINE,
}

STATIC_SCORE_SIGNS = {
    "intraday_realized_vol_4h_to_1d_smooth_60": -1.0,
    "realized_volatility_5": -1.0,
    "distance_to_high_60": 1.0,
    "distance_to_high_5": 1.0,
    "coinglass_top_trader_long_pct_smooth_5": -1.0,
    "liquidity_stress_qv_iv": -1.0,
    "momentum_decay_5_20": -1.0,
    "coinglass_taker_imb_intraday_dispersion_24h": 1.0,
    "quality_funding_oi": -1.0,
    "downside_upside_vol_ratio_30": 1.0,
    "funding_basis_residual_implied_repo_30": 1.0,
    "settlement_cycle_premium_60d": -1.0,
    "funding_basis_residual_20": -1.0,
    "funding_flip_decay_phase": -1.0,
    "triangle_residual_60d": -1.0,
    "realized_skew_20_xs_z": -1.0,
    "realized_kurt_20_xs_z": -1.0,
}


def _parse_columns(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(col.strip() for col in raw.split(",") if col.strip())


def _make_factor_spec(
    *,
    factor_id: str,
    column: str,
    baseline_columns: tuple[str, ...],
    current_state: str,
    note: str,
    mechanism_family: str | None = None,
    mechanism_falsified: bool = False,
) -> dict:
    return {
        "factor_id": factor_id,
        "column": column,
        "mechanism_family": mechanism_family or _mechanism_family_for(column),
        "current_state": current_state,
        "baseline_columns": [c for c in baseline_columns if c != column],
        "mechanism_falsified": mechanism_falsified,
        "note": note,
    }


def _build_factor_inventory(
    *,
    baseline_columns: tuple[str, ...] = LSK3_BASELINE,
    baseline_label: str = "lsk3",
) -> list[dict]:
    """Inventory of all factors known to the lifecycle evaluator, with
    current state (sourced from manifest lifecycle markers + threshold
    provenance) and mechanism falsification flags (sourced from
    threshold_provenance.md "FALSIFIED" sections).

    Each spec contains: factor_id, column, mechanism_family, current_state,
    baseline_columns, mechanism_falsified, note.
    """
    # Selected baseline factors: residualize each against the rest of the selected baseline.
    selected_baseline = tuple(baseline_columns)
    baseline_specs = [
        _make_factor_spec(
            factor_id=col,
            column=col,
            baseline_columns=selected_baseline,
            current_state="active",
            note=f"{baseline_label} baseline factor",
        )
        for col in selected_baseline
    ]

    legacy_lsk3_candidates = [
        {
            "factor_id": f"legacy_{col}",
            "column": col,
            "mechanism_family": _mechanism_family_for(col),
            "current_state": "watch",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "legacy lsk3 factor not active in the selected baseline; audit as carry-forward candidate",
        }
        for col in LSK3_BASELINE
    ]

    # Score-integrated extensions (against selected baseline)
    score_extensions = [
        {
            "factor_id": "F-cascade_liq_cascade_recency_score_5d",
            "column": "liq_cascade_recency_score_5d",
            "mechanism_family": "MF-12",
            "current_state": "active",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "SP-A winner; in v6_h5d (active_alternative) + v6_h10d (active_alternative)",
        },
        {
            "factor_id": "F62_settlement_cycle_premium_60d",
            "column": "settlement_cycle_premium_60d",
            "mechanism_family": "MF-15",
            "current_state": "watch",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "in v5 (experimental); regime-fragile at h10d; lifecycle marker manually set to watch",
        },
        {
            "factor_id": "F47_funding_flip_decay_phase",
            "column": "funding_flip_decay_phase",
            "mechanism_family": "MF-08",
            "current_state": "watch",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "in v8 (experimental); borderline G6 at h5d; +0.08 walk-forward only",
        },
        {
            "factor_id": "F1_funding_intraday_dispersion_30d",
            "column": "funding_intraday_dispersion_30d",
            "mechanism_family": "MF-03",
            "current_state": "watch",
            "baseline_columns": list(selected_baseline) + ["liq_cascade_recency_score_5d"],
            "mechanism_falsified": False,
            "note": "SP-F admission winner (G6 +0.040 vs lsk3+F08); in v9 (experimental); cycle non-additive",
        },
    ]

    # Plumbed but G6-fail candidates (admission-failed at panel grain)
    plumbed_candidates = [
        # SP-B microstructure — plumbed but not admitted
        {
            "factor_id": "B3a_top_trader_velocity_1h_abs_24h",
            "column": "top_trader_velocity_1h_abs_24h",
            "mechanism_family": "MF-07",
            "current_state": "watch",
            "baseline_columns": list(selected_baseline) + ["liq_cascade_recency_score_5d"],
            "mechanism_falsified": False,
            "note": "SP-B partial; G6 PASS standalone but +0.94 sibling-corr with F-cascade",
        },
        # SP-F siblings
        {
            "factor_id": "F2_funding_sign_flip_count_30d_4h",
            "column": "funding_sign_flip_count_30d_4h",
            "mechanism_family": "MF-03",
            "current_state": "watch",
            "baseline_columns": list(selected_baseline) + ["funding_term_skew_60"],
            "mechanism_falsified": False,
            "note": "SP-F secondary; G6 PASS h10d; not stacked (sibling-corr with F1)",
        },
        {
            "factor_id": "F3_funding_term_skew_30d_4h",
            "column": "funding_term_skew_30d_4h",
            "mechanism_family": "MF-03",
            "current_state": "decay",
            "baseline_columns": list(selected_baseline) + ["funding_term_skew_60"],
            "mechanism_falsified": False,
            "note": "SP-F: F08 collinear; G6 fails; vol-skew dimension saturated at panel grain",
        },
        # M2.4 triangle
        {
            "factor_id": "F-triangle_residual_60d",
            "column": "triangle_residual_60d",
            "mechanism_family": "MF-04",
            "current_state": "watch",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "M2.4 doc E.11 PASS; standalone G6 fail (lsk3 saturation)",
        },
        # M2.1 cross-venue
        {
            "factor_id": "M2.1_cross_venue_spot_dispersion",
            "column": "cross_venue_spot_dispersion",
            "mechanism_family": "MF-05",
            "current_state": "decay",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "M2.1: G6 fail (collinear w/ vol factors); cross-venue lane needs SP-J data uplift",
        },
    ]

    # Empirically falsified candidates (mechanism_falsified=True per
    # threshold_provenance.md; mechanism direction verified incorrect or
    # signal sub-significance)
    falsified_candidates = [
        {
            "factor_id": "SP-D_alt_basis_residual_after_btc_60d",
            "column": "alt_basis_residual_after_btc_60d",
            "mechanism_family": "MF-04",
            "current_state": "active",  # treat as still admitted to test demotion
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": True,
            "note": "SP-D §E.16 falsified (t=1.39<2.0; MF-04 saturation under lsk3+F12)",
        },
        {
            "factor_id": "SP-D_basis_propagation_lag_corr_30d",
            "column": "basis_propagation_lag_corr_30d",
            "mechanism_family": "MF-04",
            "current_state": "active",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": True,
            "note": "SP-D §E.16 falsified (sibling of D2; raw IC 0.007 << 0.04 floor)",
        },
        {
            "factor_id": "SP-E_btc_eth_realized_corr_30d",
            "column": "btc_eth_corr_30d",
            "mechanism_family": "MF-09",
            "current_state": "active",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": True,
            "note": "SP-E §E.17 falsified (tertile-stratified IC ratio 0.90 REVERSED vs doc)",
        },
        {
            "factor_id": "SP-H_expiry_window_x_rv20",
            "column": "expiry_window_x_rv20",
            "mechanism_family": "MF-08",
            "current_state": "active",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": True,
            "note": "SP-H §E.15 falsified (KS p=0.128>0.05; vol dim saturated by lsk3)",
        },
    ]

    # W1.1 / W3.x leftovers — admission failed
    leftovers = [
        {
            "factor_id": "F09_funding_basis_residual",
            "column": "funding_basis_residual_20",
            "mechanism_family": "MF-04",
            "current_state": "decay",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "W1.1 admission fail vs lsk3; F12 absorbs",
        },
        {
            "factor_id": "F31_realized_skew_20",
            "column": "realized_skew_20_xs_z",
            "mechanism_family": "MF-10",
            "current_state": "decay",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "W1.1 admission fail; vol dimension absorbed",
        },
        {
            "factor_id": "F32_realized_kurt_20",
            "column": "realized_kurt_20_xs_z",
            "mechanism_family": "MF-10",
            "current_state": "decay",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "W1.1 admission fail; vol dimension absorbed",
        },
        {
            "factor_id": "F35_vol_of_vol_60",
            "column": "vol_of_vol_60",
            "mechanism_family": "MF-10",
            "current_state": "decay",
            "baseline_columns": list(selected_baseline),
            "mechanism_falsified": False,
            "note": "W1.1 admission fail; vol-of-vol dimension subsumed by intraday_realized_vol_4h_to_1d_smooth_60",
        },
    ]

    ordered_specs = (
        baseline_specs
        + legacy_lsk3_candidates
        + score_extensions
        + plumbed_candidates
        + falsified_candidates
        + leftovers
    )
    deduped_specs: list[dict] = []
    seen_columns: set[str] = set()
    for spec in ordered_specs:
        column = str(spec["column"])
        if column in seen_columns:
            continue
        deduped_specs.append(spec)
        seen_columns.add(column)
    return deduped_specs


def _mechanism_family_for(column: str) -> str:
    """Heuristic family assignment for lsk3 factors (matches doc §B / §D map)."""
    if column.startswith("intraday_realized_vol") or column.startswith("realized_volatility") \
            or column == "downside_upside_vol_ratio_30":
        return "MF-10"
    if column.startswith("distance_to_") or column.startswith("range_position_"):
        return "MF-11"
    if "top_trader" in column:
        return "MF-07"
    if column.startswith("liquidity_stress_") or column.startswith("crowd_") or column == "stress_liq_conc_iv":
        return "MF-04"
    if column.startswith("momentum_decay_"):
        return "MF-09"
    if "taker_imb" in column:
        return "MF-06"
    if column == "quality_funding_oi" or column.startswith("funding_basis_residual"):
        return "MF-04"
    return "unknown"


def _add_forward_return_target(panel: pd.DataFrame, horizon_days: int) -> tuple[pd.DataFrame, str]:
    """Add a raw close-to-close forward return target for the requested horizon."""
    if horizon_days == 5 and "target_forward_return" in panel.columns:
        return panel, "target_forward_return"
    if horizon_days <= 0:
        raise ValueError("--target-horizon-days must be positive")
    required = {"subject", "timestamp_ms", "spot_close"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise RuntimeError(
            "cannot build lifecycle target; missing columns: " + ", ".join(missing)
        )
    out = panel.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True).copy()
    close = pd.to_numeric(out["spot_close"], errors="coerce")
    future_close = out.groupby("subject", sort=False)["spot_close"].transform(
        lambda s: pd.to_numeric(s, errors="coerce").shift(-horizon_days)
    )
    target_col = f"target_forward_return_h{horizon_days}d"
    out[target_col] = future_close / close.mask(close.eq(0.0)) - 1.0
    return out, target_col


def _orient_factor_specs(
    panel: pd.DataFrame,
    factor_specs: list[dict],
    *,
    orientation: str,
) -> tuple[pd.DataFrame, list[dict], dict[str, float]]:
    """Optionally orient factor columns so positive IC means useful signal."""
    if orientation == "raw":
        return panel, factor_specs, {}
    if orientation != "score_sign":
        raise ValueError(f"unknown factor orientation: {orientation}")
    out = panel.copy()
    oriented_specs: list[dict] = []
    used_signs: dict[str, float] = {}
    for spec in factor_specs:
        original_column = str(spec["column"])
        sign = float(STATIC_SCORE_SIGNS.get(original_column, 1.0))
        used_signs[original_column] = sign
        if sign < 0.0 and original_column in out.columns:
            oriented_column = f"__lifecycle_oriented__{original_column}"
            out[oriented_column] = -pd.to_numeric(out[original_column], errors="coerce")
        else:
            oriented_column = original_column
        adjusted = dict(spec)
        adjusted["column"] = oriented_column
        adjusted["raw_column"] = original_column
        adjusted["factor_orientation_sign"] = sign
        oriented_specs.append(adjusted)
    return out, oriented_specs, used_signs


def main() -> int:
    parser = argparse.ArgumentParser(description="M2.5 factor_lifecycle demotion experiment.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_ARTIFACT)
    parser.add_argument(
        "--baseline-preset",
        choices=sorted(BASELINE_PRESETS),
        default="lsk3",
        help=(
            "Baseline used for residual IC. Use live_hv_balanced for the current "
            "remote live baseline and research_v5_rw_bridge_no_overlay_h10d for "
            "the follow-on research baseline."
        ),
    )
    parser.add_argument(
        "--baseline-columns",
        default="",
        help="Comma-separated baseline columns; overrides --baseline-preset.",
    )
    parser.add_argument(
        "--baseline-label",
        default="",
        help="Human-readable baseline label written into the report.",
    )
    parser.add_argument(
        "--target-horizon-days",
        type=int,
        default=5,
        help="Forward-return horizon for lifecycle IC target (default: 5).",
    )
    parser.add_argument(
        "--factor-orientation",
        choices=("raw", "score_sign"),
        default="raw",
        help=(
            "Use raw columns, or orient known score factors by static score sign "
            "so positive IC means useful signal. Default raw preserves legacy behavior."
        ),
    )
    parser.add_argument(
        "--run-label",
        default="",
        help="Optional subdirectory under <output-dir>/<as-of> to avoid overwriting runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_lifecycle",
    )
    args = parser.parse_args()
    baseline_columns = _parse_columns(args.baseline_columns) or BASELINE_PRESETS[args.baseline_preset]
    baseline_label = args.baseline_label.strip() or args.baseline_preset

    print(f"=== M2.5 lifecycle demotion experiment ===")
    print(f"  features: {args.features}")
    print(f"  baseline: {baseline_label} ({len(baseline_columns)} columns)")
    print(f"  target horizon: h{args.target_horizon_days}d")
    print(f"  factor orientation: {args.factor_orientation}")
    raw_panel = _load_panel(args.features)
    print(f"  raw panel shape: {raw_panel.shape}")
    print("  rebuilding W3 + sub-day funding + cascade columns...")
    panel = _rebuild_features_with_w3_columns(raw_panel)
    print(f"  rebuilt panel shape: {panel.shape}")
    print()

    panel, target_column = _add_forward_return_target(panel, args.target_horizon_days)
    print(f"  target column: {target_column}")

    factor_specs = _build_factor_inventory(
        baseline_columns=baseline_columns,
        baseline_label=baseline_label,
    )
    panel, factor_specs, orientation_signs = _orient_factor_specs(
        panel,
        factor_specs,
        orientation=args.factor_orientation,
    )
    # Filter out specs whose column is missing from the rebuilt panel
    available_specs = []
    skipped = []
    for spec in factor_specs:
        if spec["column"] in panel.columns:
            available_specs.append(spec)
        else:
            skipped.append(spec["factor_id"])
    print(f"  factors available: {len(available_specs)} / {len(factor_specs)}")
    if skipped:
        print(f"  skipped (column missing in panel): {skipped}")
    print()

    print("=== Evaluating lifecycle state machine across factor inventory ===")
    report = evaluate_factor_lifecycle_batch(
        panel=panel,
        target_column=target_column,
        factor_specs=available_specs,
    )
    spec_by_id = {str(spec["factor_id"]): spec for spec in available_specs}
    for result in report["factor_results"]:
        spec = spec_by_id.get(str(result["factor_id"]), {})
        result["column"] = spec.get("raw_column", spec.get("column"))
        result["evaluated_column"] = spec.get("column")
        result["factor_orientation_sign"] = spec.get("factor_orientation_sign", 1.0)

    # Pretty-print summary
    print()
    print("=== Lifecycle summary ===")
    s = report["summary"]
    print(f"  Total evaluated:                       {s['n_total']}")
    print(f"  Recommended state distribution:")
    print(f"    active:                              {s['n_active']}")
    print(f"    watch:                               {s['n_watch']}")
    print(f"    decay:                               {s['n_decay']}")
    print(f"    retired:                             {s['n_retired']}")
    print(f"    revived candidates:                  {s['n_revived_candidates']}")
    print(f"  Demotion-recommended count:            {s['n_recommended_demote']}")
    print(f"  Revival-check count:                   {s['n_recommended_revival_check']}")
    print(f"  Sanity check artifact flags:")
    print(f"    likely_self_residual_artifact:       {s.get('n_likely_self_residual_artifact', 0)}")
    print(f"    likely_self_residual_artifact_strong:{s.get('n_likely_self_residual_artifact_strong', 0)}")
    print()

    # Per-factor lines
    print("=== Per-factor verdict ===")
    for r in report["factor_results"]:
        sig = r["signal"]
        ic_60d = sig.get("rolling_60d_resid_ic_latest")
        ic_60d_str = f"{ic_60d:+.4f}" if isinstance(ic_60d, (int, float)) and not pd.isna(ic_60d) else "n/a"
        raw_60d = sig.get("rolling_60d_raw_ic_latest")
        raw_60d_str = f"{raw_60d:+.4f}" if isinstance(raw_60d, (int, float)) and raw_60d is not None and not pd.isna(raw_60d) else "n/a"
        arrow = (
            "->"
            if r["current_state"] != r["recommended_state"]
            else "."
        )
        flag = r.get("sanity_artifact_flag")
        flag_str = f"  [SANITY: {flag}]" if flag else ""
        print(
            f"  {r['factor_id']:50s}  {r['current_state']:9s} {arrow} {r['recommended_state']:9s}  "
            f"resid60d={ic_60d_str}  raw60d={raw_60d_str}  w*{r['weight_multiplier']:.1f}{flag_str}"
        )

    # Persist JSON report
    out_dir = args.output_dir / args.as_of
    if args.run_label.strip():
        out_dir = out_dir / args.run_label.strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "lifecycle_report.json"
    payload = {
        "contract_version": FACTOR_LIFECYCLE_CONTRACT_VERSION,
        "as_of": args.as_of,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "features_artifact": str(args.features),
        "baseline_label": baseline_label,
        "baseline_preset": args.baseline_preset,
        "baseline_columns_requested": list(baseline_columns),
        "target_column": target_column,
        "target_horizon_days": args.target_horizon_days,
        "factor_orientation": args.factor_orientation,
        "factor_orientation_signs": orientation_signs,
        "n_factors_evaluated": len(report["factor_results"]),
        "n_factors_skipped_panel_missing": len(skipped),
        "skipped_factors": skipped,
        "summary": report["summary"],
        "factor_results": report["factor_results"],
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print()
    print(f"=== Done. Report at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
