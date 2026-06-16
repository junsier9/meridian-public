"""M3.1 options-surface preregistered report card and overlay context audit.

This writer consumes the Tardis Deribit options-surface feature panel produced
by build_tardis_deribit_options_surface_features.py and audits F56-F60 against
the current h10d research baseline boundaries.

The output is deliberately report-only:
  * no active manifest mutation
  * no v1 admission allowlist mutation
  * no overlay activation

Because Deribit options coverage is currently BTC/ETH only, the standard
top20/top30 cross-sectional score-layer report-card gates are marked blocked.
The script still computes transparent T2 overlay diagnostics over the available
BTC/ETH overlap with the h10d feature panel.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.feature_admission import (  # noqa: E402
    FEATURE_ADMISSION_POLICY_VERSION,
    feature_admission_status,
)
from enhengclaw.quant_research.feature_admission_v2 import (  # noqa: E402
    FEATURE_ADMISSION_V2_CONTRACT_VERSION,
    load_feature_admission_v2_contract,
    orthogonalize,
    per_timestamp_rank_ic,
    sanitize_for_json,
)


CARD_CONTRACT_VERSION = "quant_m3_1_options_surface_overlay_context_report_card.v1"
DEFAULT_AS_OF = "2026-06-13"
DEFAULT_OPTIONS_PANEL = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "options_surface"
    / DEFAULT_AS_OF
    / "tardis_deribit_options_surface_features.csv"
)
DEFAULT_BUILDER_REPORT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / DEFAULT_AS_OF
    / "m3_1_tardis_deribit_options_surface_builder.json"
)
DEFAULT_ADMISSION_MANIFEST_AUDIT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / DEFAULT_AS_OF
    / "m3_1_tardis_deribit_options_surface_admission_manifest_audit.json"
)
DEFAULT_FEATURES_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)
DEFAULT_ACTIVE_H10D_REGISTRY = ROOT / "config" / "quant_research" / "active_h10d_registry.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "quant_research" / "factor_reports"

REQUIRED_SUBJECTS = ("BTC", "ETH")
HORIZONS = (1, 3, 5, 10)
MIN_SCORE_SUBJECTS = 20
MIN_SCORE_TIMESTAMPS = 60
SAMPLE_RV_PROXY_COLUMNS = (
    "realized_vol_sample_seconds",
    "realized_vol_underlying_1d",
    "realized_vol_input_point_count",
    "realized_vol_resampled_point_count",
)

CANDIDATES: tuple[dict[str, str], ...] = (
    {
        "factor_id": "F56",
        "column": "iv_25d_skew_residual",
        "ready_column": "f56_ready",
        "mechanism_family": "MF-02",
        "expected_direction": "+",
        "overlay_role": "vol_surface_skew_context",
        "half_life_days": "5-10",
    },
    {
        "factor_id": "F57",
        "column": "iv_rv_spread",
        "ready_column": "f57_ready",
        "mechanism_family": "MF-02",
        "expected_direction": "-",
        "overlay_role": "vol_risk_premium_context",
        "half_life_days": "7-14",
    },
    {
        "factor_id": "F58",
        "column": "iv_term_slope",
        "ready_column": "f58_ready",
        "mechanism_family": "MF-02",
        "expected_direction": "conditional",
        "overlay_role": "term_structure_stress_context",
        "half_life_days": "4-7",
    },
    {
        "factor_id": "F59",
        "column": "dealer_gamma_proxy",
        "ready_column": "f59_ready",
        "mechanism_family": "MF-02",
        "expected_direction": "conditional",
        "overlay_role": "dealer_gamma_regime_context",
        "half_life_days": "3-7",
    },
    {
        "factor_id": "F60",
        "column": "vanna_charm_window",
        "ready_column": "f60_ready",
        "mechanism_family": "MF-02",
        "expected_direction": "conditional",
        "overlay_role": "expiry_window_context",
        "half_life_days": "1-3",
    },
)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_dir = args.output_dir / args.as_of
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json = output_dir / "m3_1_options_surface_overlay_context_report_card.json"
    output_text = output_dir / "m3_1_options_surface_overlay_context_report_card.txt"

    panel = _load_csv(args.options_panel)
    builder_report = _read_json_if_exists(args.builder_report)
    manifest_audit = _read_json_if_exists(args.admission_manifest_audit)
    registry = _read_json(args.active_h10d_registry)
    active_manifest_path = _active_manifest_path(registry)
    active_manifest = _read_json_if_exists(active_manifest_path)
    active_required = _active_required_feature_columns(active_manifest)
    features = _load_csv(args.features_artifact)

    merged = _build_overlay_overlap(
        options_panel=panel,
        features=features,
        horizons=HORIZONS,
        required_subjects=REQUIRED_SUBJECTS,
    )
    admission_contract = load_feature_admission_v2_contract()
    factor_cards = {
        candidate["factor_id"]: _factor_card(
            candidate=candidate,
            panel=panel,
            merged=merged,
            active_required=active_required,
            admission_contract=admission_contract,
        )
        for candidate in CANDIDATES
    }

    score_layer = _score_layer_admission(
        panel=panel,
        merged=merged,
        factor_cards=factor_cards,
        manifest_audit=manifest_audit,
        active_required=active_required,
    )
    overlay_context = _overlay_context_audit(
        panel=panel,
        merged=merged,
        factor_cards=factor_cards,
        builder_report=builder_report,
        score_layer=score_layer,
    )
    decision = {
        "report_card_status": "complete",
        "score_layer_admission_allowed": False,
        "overlay_context_research_allowed": bool(overlay_context["allowed_for_research_overlay_context"]),
        "manifest_mutation_authorized": False,
        "v1_admission_policy_mutation_authorized": False,
        "live_or_timer_overlay_activation_authorized": False,
        "next_allowed_step": (
            "pre_register_options_surface_overlay_rule_and_run_h10d_overlay_ablation"
            if overlay_context["allowed_for_research_overlay_context"]
            else "repair_options_surface_panel_or_h10d_overlap_before_overlay_ablation"
        ),
    }

    payload = {
        "contract_version": CARD_CONTRACT_VERSION,
        "generated_at_utc": _utc_now(),
        "as_of": args.as_of,
        "inputs": {
            "options_panel_path": str(args.options_panel),
            "builder_report_path": str(args.builder_report),
            "admission_manifest_audit_path": str(args.admission_manifest_audit),
            "features_artifact_path": str(args.features_artifact),
            "active_h10d_registry_path": str(args.active_h10d_registry),
            "active_manifest_path": str(active_manifest_path) if active_manifest_path else None,
        },
        "contracts": {
            "report_card": CARD_CONTRACT_VERSION,
            "feature_admission_v1": FEATURE_ADMISSION_POLICY_VERSION,
            "feature_admission_v2": FEATURE_ADMISSION_V2_CONTRACT_VERSION,
            "feature_admission_v2_thresholds": _admission_threshold_summary(admission_contract),
        },
        "panel_coverage": _panel_coverage(panel),
        "h10d_overlap": _overlap_summary(merged),
        "active_h10d_context": {
            "registry_label": _registry_label(registry),
            "required_feature_columns": active_required,
            "candidate_columns_absent_from_active_manifest": [
                candidate["column"] for candidate in CANDIDATES if candidate["column"] not in active_required
            ],
        },
        "factor_cards": factor_cards,
        "score_layer_admission": score_layer,
        "overlay_context_audit": overlay_context,
        "decision": decision,
    }

    output_json.write_text(
        json.dumps(sanitize_for_json(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    output_text.write_text(_render_text(payload), encoding="utf-8")
    print(f"wrote {output_json}")
    print(f"wrote {output_text}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="M3.1 options-surface preregistered factor report card and overlay context audit."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--options-panel", type=Path, default=DEFAULT_OPTIONS_PANEL)
    parser.add_argument("--builder-report", type=Path, default=DEFAULT_BUILDER_REPORT)
    parser.add_argument("--admission-manifest-audit", type=Path, default=DEFAULT_ADMISSION_MANIFEST_AUDIT)
    parser.add_argument("--features-artifact", type=Path, default=DEFAULT_FEATURES_ARTIFACT)
    parser.add_argument("--active-h10d-registry", type=Path, default=DEFAULT_ACTIVE_H10D_REGISTRY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    compression = "gzip" if str(path).lower().endswith(".gz") else None
    return pd.read_csv(path, compression=compression, low_memory=False)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return _read_json(path)


def _active_manifest_path(registry: dict[str, Any]) -> Path | None:
    canonical_parent = registry.get("canonical_parent")
    if not isinstance(canonical_parent, dict):
        return None
    raw = canonical_parent.get("manifest_path")
    if not raw:
        return None
    candidate = Path(str(raw))
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def _active_required_feature_columns(manifest: dict[str, Any]) -> list[str]:
    entries = manifest.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("required_feature_columns"), list):
                return [str(value) for value in entry["required_feature_columns"]]
    if isinstance(manifest.get("required_feature_columns"), list):
        return [str(value) for value in manifest["required_feature_columns"]]
    return []


def _registry_label(registry: dict[str, Any]) -> str:
    effective = registry.get("effective_research_baseline")
    if isinstance(effective, dict) and effective.get("label"):
        return str(effective["label"])
    canonical = registry.get("canonical_parent")
    if isinstance(canonical, dict) and canonical.get("label"):
        return str(canonical["label"])
    return "unknown"


def _panel_coverage(panel: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {
        "row_count": int(panel.shape[0]),
        "column_count": int(panel.shape[1]),
        "subjects": sorted(panel["subject"].astype(str).unique().tolist()) if "subject" in panel else [],
        "date_start": str(panel["date_utc"].min()) if "date_utc" in panel and not panel.empty else None,
        "date_end": str(panel["date_utc"].max()) if "date_utc" in panel and not panel.empty else None,
        "decision_date_start": (
            str(panel["decision_date_utc"].min()) if "decision_date_utc" in panel and not panel.empty else None
        ),
        "decision_date_end": (
            str(panel["decision_date_utc"].max()) if "decision_date_utc" in panel and not panel.empty else None
        ),
        "duplicate_subject_date_rows": int(panel.duplicated(["subject", "date_utc"]).sum())
        if {"subject", "date_utc"}.issubset(panel.columns)
        else None,
        "sample_rv_proxy_columns_present": [column for column in SAMPLE_RV_PROXY_COLUMNS if column in panel.columns],
        "latest_by_subject": {},
    }
    for candidate in CANDIDATES:
        ready_col = candidate["ready_column"]
        if ready_col in panel.columns:
            out[f"{ready_col}_count"] = int(panel[ready_col].fillna(False).astype(bool).sum())
    if {"subject", "date_utc"}.issubset(panel.columns):
        for subject, group in panel.sort_values("date_utc").groupby("subject"):
            latest = group.tail(1).iloc[0]
            out["latest_by_subject"][str(subject)] = {
                "date_utc": str(latest.get("date_utc")),
                "decision_date_utc": str(latest.get("decision_date_utc")),
                "panel_ready": bool(latest.get("m3_1_options_surface_panel_ready")),
                "rv_symbol": _none_if_nan(latest.get("rv_symbol")),
            }
            for candidate in CANDIDATES:
                column = candidate["column"]
                ready_col = candidate["ready_column"]
                out["latest_by_subject"][str(subject)][column] = _finite_or_none(latest.get(column))
                out["latest_by_subject"][str(subject)][ready_col] = bool(latest.get(ready_col))
    return out


def _build_overlay_overlap(
    *,
    options_panel: pd.DataFrame,
    features: pd.DataFrame,
    horizons: tuple[int, ...],
    required_subjects: tuple[str, ...],
) -> pd.DataFrame:
    opts = options_panel.copy()
    opts["subject"] = opts["subject"].astype(str).str.upper()
    opts["decision_date_utc"] = opts["decision_date_utc"].astype(str)
    feats = features.copy()
    feats["subject"] = feats["subject"].astype(str).str.upper()
    feats = feats[feats["subject"].isin(required_subjects)].copy()
    feats["date_utc"] = feats["date_utc"].astype(str)
    feats["spot_close"] = pd.to_numeric(feats["spot_close"], errors="coerce")
    feats = feats.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True)
    for horizon in horizons:
        target = pd.Series(np.nan, index=feats.index, dtype="float64")
        for _, group in feats.groupby("subject"):
            ordered = group.sort_values("timestamp_ms")
            close = pd.to_numeric(ordered["spot_close"], errors="coerce")
            target.loc[ordered.index] = np.log(close.shift(-horizon) / close)
        feats[f"target_forward_return_h{horizon}d"] = target
    feats = feats.rename(columns={"date_utc": "decision_date_utc"})
    return opts.merge(
        feats,
        on=["subject", "decision_date_utc"],
        how="left",
        suffixes=("_options", "_h10d"),
    )


def _overlap_summary(merged: pd.DataFrame) -> dict[str, Any]:
    out = {
        "row_count": int(merged.shape[0]),
        "subjects": sorted(merged["subject"].dropna().astype(str).unique().tolist()) if "subject" in merged else [],
        "decision_date_start": (
            str(merged["decision_date_utc"].min()) if "decision_date_utc" in merged and not merged.empty else None
        ),
        "decision_date_end": (
            str(merged["decision_date_utc"].max()) if "decision_date_utc" in merged and not merged.empty else None
        ),
        "feature_overlap_rows": int(pd.to_numeric(merged.get("timestamp_ms"), errors="coerce").notna().sum())
        if "timestamp_ms" in merged
        else 0,
        "target_rows_by_horizon": {},
    }
    for horizon in HORIZONS:
        column = f"target_forward_return_h{horizon}d"
        if column in merged.columns:
            out["target_rows_by_horizon"][column] = int(
                pd.to_numeric(merged[column], errors="coerce").notna().sum()
            )
    return out


def _factor_card(
    *,
    candidate: dict[str, str],
    panel: pd.DataFrame,
    merged: pd.DataFrame,
    active_required: list[str],
    admission_contract: dict[str, Any],
) -> dict[str, Any]:
    column = candidate["column"]
    ready_column = candidate["ready_column"]
    status_v1 = feature_admission_status(column)
    full_factor = pd.to_numeric(panel[column], errors="coerce") if column in panel.columns else pd.Series(dtype=float)
    ready = panel[ready_column].fillna(False).astype(bool) if ready_column in panel.columns else pd.Series(dtype=bool)
    card: dict[str, Any] = {
        "factor_id": candidate["factor_id"],
        "column": column,
        "mechanism_family": candidate["mechanism_family"],
        "expected_direction": candidate["expected_direction"],
        "overlay_role": candidate["overlay_role"],
        "half_life_days": candidate["half_life_days"],
        "feature_admission_v1_status": status_v1,
        "present_in_active_h10d_manifest": column in active_required,
        "coverage": {
            "non_null_rows": int(full_factor.notna().sum()),
            "ready_rows": int(ready.sum()) if len(ready) else 0,
            "ready_subjects_latest": _latest_ready_by_subject(panel, ready_column),
        },
        "exploratory_horizon_diagnostics": {},
        "baseline_overlap": _baseline_overlap(column=column, merged=merged, active_required=active_required),
        "score_layer_gate_status": "blocked_not_score_admission_grade",
    }
    for horizon in HORIZONS:
        card["exploratory_horizon_diagnostics"][f"h{horizon}d"] = _horizon_diagnostic(
            merged=merged,
            factor_col=column,
            target_col=f"target_forward_return_h{horizon}d",
            active_required=active_required,
            expected_direction=candidate["expected_direction"],
            admission_contract=admission_contract,
        )
    return card


def _latest_ready_by_subject(panel: pd.DataFrame, ready_column: str) -> dict[str, bool]:
    if not {"subject", "date_utc", ready_column}.issubset(panel.columns):
        return {}
    out: dict[str, bool] = {}
    for subject, group in panel.sort_values("date_utc").groupby("subject"):
        out[str(subject)] = bool(group.tail(1).iloc[0].get(ready_column))
    return out


def _horizon_diagnostic(
    *,
    merged: pd.DataFrame,
    factor_col: str,
    target_col: str,
    active_required: list[str],
    expected_direction: str,
    admission_contract: dict[str, Any],
) -> dict[str, Any]:
    if factor_col not in merged.columns or target_col not in merged.columns:
        return {"status": "missing_factor_or_target"}
    factor = pd.to_numeric(merged[factor_col], errors="coerce")
    target = pd.to_numeric(merged[target_col], errors="coerce")
    timestamps = pd.to_numeric(merged.get("timestamp_ms"), errors="coerce")
    valid = factor.notna() & target.notna() & timestamps.notna()
    n_obs = int(valid.sum())
    n_ts = int(merged.loc[valid, "decision_date_utc"].nunique()) if "decision_date_utc" in merged else 0
    n_subjects = int(merged.loc[valid, "subject"].nunique()) if "subject" in merged else 0
    ic = per_timestamp_rank_ic(factor, target, timestamps).dropna()
    subject_ts = _subject_timeseries_correlations(merged, factor_col=factor_col, target_col=target_col)
    baseline_columns = [column for column in active_required if column in merged.columns]
    residual_ic = _residual_ic(
        factor=factor,
        target=target,
        timestamps=timestamps,
        baseline=merged[baseline_columns].apply(pd.to_numeric, errors="coerce") if baseline_columns else pd.DataFrame(),
    )
    direction_score = _direction_score(ic, expected_direction)
    return {
        "status": "exploratory_t2_only",
        "n_observations": n_obs,
        "n_timestamps": n_ts,
        "n_subjects": n_subjects,
        "cross_sectional_rank_ic": _series_summary(ic),
        "residual_ic_vs_active_h10d_available_baseline": residual_ic,
        "subject_timeseries_spearman": subject_ts,
        "expected_direction_alignment": direction_score,
        "admission_thresholds_reference": {
            "g1_abs_min": _contract_threshold(admission_contract, "g1_ic_mean", "abs_min"),
            "g6_abs_min": _contract_threshold(admission_contract, "g6_orthogonal_residual_ic", "abs_min"),
        },
        "score_layer_admission_grade": False,
        "score_layer_blockers": _horizon_blockers(n_subjects=n_subjects, n_ts=n_ts),
    }


def _series_summary(series: pd.Series) -> dict[str, Any]:
    valid = series.dropna()
    if valid.empty:
        return {"n": 0, "mean": None, "std": None, "pos_rate": None}
    std = float(valid.std()) if valid.shape[0] > 1 else None
    return {
        "n": int(valid.shape[0]),
        "mean": float(valid.mean()),
        "std": std,
        "pos_rate": float((valid > 0).mean()),
        "min": float(valid.min()),
        "max": float(valid.max()),
    }


def _subject_timeseries_correlations(
    merged: pd.DataFrame,
    *,
    factor_col: str,
    target_col: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for subject, group in merged.groupby("subject"):
        factor = pd.to_numeric(group[factor_col], errors="coerce")
        target = pd.to_numeric(group[target_col], errors="coerce")
        valid = factor.notna() & target.notna()
        if int(valid.sum()) < 5:
            out[str(subject)] = {"n": int(valid.sum()), "spearman": None, "pearson": None}
            continue
        out[str(subject)] = {
            "n": int(valid.sum()),
            "spearman": _corr(factor[valid].rank(), target[valid].rank()),
            "pearson": _corr(factor[valid], target[valid]),
        }
    return out


def _corr(left: pd.Series, right: pd.Series) -> float | None:
    value = left.corr(right)
    if pd.isna(value):
        return None
    return float(value)


def _residual_ic(
    *,
    factor: pd.Series,
    target: pd.Series,
    timestamps: pd.Series,
    baseline: pd.DataFrame,
) -> dict[str, Any]:
    if baseline.empty:
        return {"status": "no_active_baseline_columns_available", "n": 0}
    residual = orthogonalize(factor, baseline)
    ic = per_timestamp_rank_ic(residual, target, timestamps).dropna()
    summary = _series_summary(ic)
    summary["status"] = "exploratory_t2_only" if summary["n"] else "insufficient_data"
    summary["baseline_columns_used"] = list(baseline.columns)
    return summary


def _direction_score(ic: pd.Series, expected_direction: str) -> dict[str, Any]:
    if expected_direction == "conditional":
        return {"status": "not_scored_conditional_factor"}
    valid = ic.dropna()
    if valid.empty:
        return {"status": "insufficient_data", "passed": False}
    expected_sign = 1.0 if expected_direction == "+" else -1.0
    mean = float(valid.mean())
    return {
        "expected_direction": expected_direction,
        "ic_mean": mean,
        "aligned": bool(np.sign(mean) == expected_sign),
    }


def _horizon_blockers(*, n_subjects: int, n_ts: int) -> list[str]:
    blockers = []
    if n_subjects < MIN_SCORE_SUBJECTS:
        blockers.append(f"subject_count_{n_subjects}_below_score_min_{MIN_SCORE_SUBJECTS}")
    if n_ts < MIN_SCORE_TIMESTAMPS:
        blockers.append(f"timestamp_count_{n_ts}_below_score_min_{MIN_SCORE_TIMESTAMPS}")
    blockers.append("deribit_options_scope_is_btc_eth_t2_context_not_liquid_perp_core_20")
    return blockers


def _baseline_overlap(*, column: str, merged: pd.DataFrame, active_required: list[str]) -> dict[str, Any]:
    available = [name for name in active_required if name in merged.columns]
    missing = [name for name in active_required if name not in merged.columns]
    factor = pd.to_numeric(merged[column], errors="coerce") if column in merged.columns else pd.Series(dtype=float)
    correlations: dict[str, float] = {}
    for name in available:
        baseline = pd.to_numeric(merged[name], errors="coerce")
        valid = factor.notna() & baseline.notna()
        if int(valid.sum()) >= 10:
            value = factor[valid].corr(baseline[valid], method="spearman")
            if pd.notna(value):
                correlations[name] = float(value)
    max_item = None
    if correlations:
        max_name = max(correlations, key=lambda item: abs(correlations[item]))
        max_item = {"column": max_name, "spearman": correlations[max_name]}
    return {
        "active_required_available": available,
        "active_required_missing_from_features_artifact": missing,
        "spearman_corr_vs_active_required": correlations,
        "max_abs_corr": max_item,
    }


def _score_layer_admission(
    *,
    panel: pd.DataFrame,
    merged: pd.DataFrame,
    factor_cards: dict[str, Any],
    manifest_audit: dict[str, Any],
    active_required: list[str],
) -> dict[str, Any]:
    subjects = sorted(panel["subject"].dropna().astype(str).unique().tolist()) if "subject" in panel else []
    max_h10d_n_ts = 0
    if "target_forward_return_h10d" in merged.columns:
        factor_cols = [candidate["column"] for candidate in CANDIDATES if candidate["column"] in merged.columns]
        if factor_cols:
            factor_valid = merged[factor_cols].apply(pd.to_numeric, errors="coerce").notna().any(axis=1)
            target_valid = pd.to_numeric(merged["target_forward_return_h10d"], errors="coerce").notna()
            max_h10d_n_ts = int(merged.loc[factor_valid & target_valid, "decision_date_utc"].nunique())
    rejected_v1 = [
        card["column"]
        for card in factor_cards.values()
        if card.get("feature_admission_v1_status") != "admitted"
    ]
    absent_manifest = [
        candidate["column"] for candidate in CANDIDATES if candidate["column"] not in active_required
    ]
    inherited_blockers = []
    decision = manifest_audit.get("decision")
    if isinstance(decision, dict) and isinstance(decision.get("blockers"), list):
        inherited_blockers = [str(value) for value in decision["blockers"]]
    blockers = []
    if rejected_v1:
        blockers.append("feature_admission_v1_rejects_candidate_columns")
    if absent_manifest:
        blockers.append("active_h10d_manifest_does_not_reference_f56_f60")
    if len(subjects) < MIN_SCORE_SUBJECTS:
        blockers.append("btc_eth_only_scope_below_liquid_perp_core_20")
    if max_h10d_n_ts < MIN_SCORE_TIMESTAMPS:
        blockers.append("h10d_target_overlap_too_short_for_v2_score_admission")
    blockers.extend(value for value in inherited_blockers if value not in blockers)
    return {
        "allowed": False,
        "status": "blocked",
        "blockers": blockers,
        "subjects": subjects,
        "subject_count": len(subjects),
        "max_h10d_target_timestamps": max_h10d_n_ts,
        "candidate_columns_rejected_by_v1": rejected_v1,
        "candidate_columns_absent_from_active_manifest": absent_manifest,
        "required_before_score_manifest_change": [
            "explicit v1 admission policy update with provenance",
            "admission-v2 empirical gate on a score-grade universe or explicitly registered regime-overlay design",
            "active h10d fixed-set comparison and overlay ablation",
            "owner approval for any manifest mutation",
        ],
    }


def _overlay_context_audit(
    *,
    panel: pd.DataFrame,
    merged: pd.DataFrame,
    factor_cards: dict[str, Any],
    builder_report: dict[str, Any],
    score_layer: dict[str, Any],
) -> dict[str, Any]:
    latest_ready = {}
    if {"subject", "date_utc", "m3_1_options_surface_panel_ready"}.issubset(panel.columns):
        for subject, group in panel.sort_values("date_utc").groupby("subject"):
            latest_ready[str(subject)] = bool(group.tail(1).iloc[0]["m3_1_options_surface_panel_ready"])
    builder_green = bool(
        ((builder_report.get("phase1_decision") or {}).get("all_required_subjects_latest_ready"))
        or all(latest_ready.values())
    )
    sample_proxy_absent = not any(column in panel.columns for column in SAMPLE_RV_PROXY_COLUMNS)
    overlap_h10d_rows = 0
    if "target_forward_return_h10d" in merged.columns:
        overlap_h10d_rows = int(pd.to_numeric(merged["target_forward_return_h10d"], errors="coerce").notna().sum())
    blockers = []
    if not builder_green:
        blockers.append("options_surface_builder_not_green")
    if not sample_proxy_absent:
        blockers.append("sample_rv_proxy_columns_present")
    if overlap_h10d_rows == 0:
        blockers.append("no_h10d_overlap_for_context_diagnostics")
    allowed = not blockers
    return {
        "allowed_for_research_overlay_context": allowed,
        "status": "eligible_for_research_overlay_context_only" if allowed else "blocked",
        "blockers": blockers,
        "latest_panel_ready_by_subject": latest_ready,
        "sample_rv_proxy_absent": sample_proxy_absent,
        "h10d_overlap_rows": overlap_h10d_rows,
        "candidate_overlay_roles": {
            card["column"]: {
                "factor_id": card["factor_id"],
                "overlay_role": card["overlay_role"],
                "score_layer_admission_grade": False,
            }
            for card in factor_cards.values()
        },
        "allowed_next_actions": [
            "pre-register a concrete options-surface overlay rule",
            "run h10d overlay ablation against v5_rw_bridge_no_overlay_h10d and 10-sleeve research baseline",
            "extend Tardis store/history for longer out-of-sample overlay diagnostics",
        ]
        if allowed
        else [],
        "forbidden_actions": [
            "do_not_mutate_active_h10d_manifest_from_this_card",
            "do_not_change_feature_admission_v1_from_this_card",
            "do_not_arm_live_or_timer_overlay_from_this_card",
        ],
        "score_layer_admission_reference": {
            "allowed": bool(score_layer.get("allowed")),
            "status": score_layer.get("status"),
        },
    }


def _admission_threshold_summary(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "g1_abs_min": _contract_threshold(contract, "g1_ic_mean", "abs_min"),
        "g3_same_sign_fraction_min": _contract_threshold(
            contract, "g3_regime_consistency", "same_sign_fraction_min"
        ),
        "g6_abs_min": _contract_threshold(contract, "g6_orthogonal_residual_ic", "abs_min"),
    }


def _contract_threshold(contract: dict[str, Any], section: str, key: str) -> float | None:
    payload = contract.get(section)
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finite_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _none_if_nan(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _render_text(payload: dict[str, Any]) -> str:
    decision = payload["decision"]
    panel = payload["panel_coverage"]
    score = payload["score_layer_admission"]
    overlay = payload["overlay_context_audit"]
    lines = [
        "M3.1 Options Surface Report Card",
        "",
        f"as_of: {payload['as_of']}",
        f"contract_version: {payload['contract_version']}",
        "",
        "Decision",
        f"- report_card_status: {decision['report_card_status']}",
        f"- score_layer_admission_allowed: {decision['score_layer_admission_allowed']}",
        f"- overlay_context_research_allowed: {decision['overlay_context_research_allowed']}",
        f"- next_allowed_step: {decision['next_allowed_step']}",
        "",
        "Coverage",
        f"- panel rows: {panel['row_count']}  subjects: {panel['subjects']}",
        f"- panel dates: {panel['date_start']} -> {panel['date_end']}",
        f"- decision dates: {panel['decision_date_start']} -> {panel['decision_date_end']}",
        f"- sample RV proxy columns present: {panel['sample_rv_proxy_columns_present']}",
        "",
        "Score-Layer Admission",
        f"- status: {score['status']}",
        f"- blockers: {', '.join(score['blockers'])}",
        "",
        "Overlay Context",
        f"- status: {overlay['status']}",
        f"- blockers: {', '.join(overlay['blockers']) if overlay['blockers'] else 'none'}",
        f"- h10d overlap rows: {overlay['h10d_overlap_rows']}",
        "",
        "Factor Snapshot",
    ]
    for factor_id, card in payload["factor_cards"].items():
        h10 = card["exploratory_horizon_diagnostics"].get("h10d", {})
        ic = (h10.get("cross_sectional_rank_ic") or {}).get("mean")
        residual = (h10.get("residual_ic_vs_active_h10d_available_baseline") or {}).get("mean")
        lines.append(
            f"- {factor_id} {card['column']}: v1={card['feature_admission_v1_status']}, "
            f"ready={card['coverage']['ready_rows']}, h10d_ic={ic}, h10d_residual_ic={residual}"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
