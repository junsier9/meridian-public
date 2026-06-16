from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_m3_1_options_surface_overlay_ablation as v0  # noqa: E402


CONTRACT_VERSION = "quant_m3_1_options_surface_overlay_v1_ablation.v1"
DEFAULT_AS_OF = "2026-06-15-full-backfill-20230401-20260613"
BASELINE_VARIANT_LABEL = v0.BASELINE_VARIANT_LABEL
CANDIDATE_LABEL = "m3_1_options_surface_signed_gamma_put_skew_throttle_v1"
DEFAULT_PREREG_DOC = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "m3_1_options_surface_overlay_v1_preregistration_2026_06_15.md"
)
DEFAULT_OPTIONS_PANEL = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "options_surface"
    / DEFAULT_AS_OF
    / "tardis_deribit_options_surface_features.csv"
)
DEFAULT_CONTEXT_REPORT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / DEFAULT_AS_OF
    / "m3_1_options_surface_overlay_context_report_card.json"
)
DEFAULT_OUTPUT_SUBDIR = "m3_1_options_surface_overlay_v1_ablation"

V1_TRIGGER_COLUMNS = (
    "iv_25d_skew_residual",
    "iv_rv_spread",
    "iv_term_slope",
    "dealer_gamma_proxy",
    "vanna_charm_window",
)
V1_READY_COLUMNS = ("f56_ready", "f57_ready", "f58_ready", "f59_ready", "f60_ready")
REQUIRED_F56_METHOD = "skew_minus_rolling_60d_mean"
FROZEN_MULTIPLIER = 0.90
FAIL_OPEN_MULTIPLIER = 1.0
MIN_TRIGGER_COUNT = 16
MIN_TRIGGER_FRACTION = 0.025
MAX_TRIGGER_FRACTION = 0.20
EXCLUDE_FIRST_CONTEXT_DATES = 60

VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "label": BASELINE_VARIANT_LABEL,
        "kind": "baseline",
        "portfolio_target_multiplier": 1.0,
        "description": "No options-surface overlay.",
    },
    {
        "label": CANDIDATE_LABEL,
        "kind": "options_surface_signed_gamma_put_skew_throttle",
        "portfolio_target_multiplier": FROZEN_MULTIPLIER,
        "description": "Frozen M3.1 signed-gamma / put-skew confirmed top2 context throttle.",
    },
)

ORIGINAL_WRITE_JSON = v0.write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the preregistered M3.1 options-surface v1 signed-gamma / put-skew "
            "portfolio-throttle A/B under the current v5_rw 10-sleeve h10d baseline."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--baseline-experiment-id", default=v0.BASELINE_EXPERIMENT_ID)
    parser.add_argument("--artifacts-root", type=Path, default=v0.QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--validation-contract", type=Path, default=v0.H10D_VALIDATION_CONTRACT_PATH)
    parser.add_argument("--options-panel", type=Path, default=None)
    parser.add_argument("--context-report", type=Path, default=None)
    parser.add_argument("--active-h10d-registry", type=Path, default=v0.DEFAULT_ACTIVE_H10D_REGISTRY)
    parser.add_argument("--preregistration-doc", type=Path, default=DEFAULT_PREREG_DOC)
    parser.add_argument("--holdout-start", default="2025-10-01")
    parser.add_argument("--exclude-first-context-dates", type=int, default=EXCLUDE_FIRST_CONTEXT_DATES)
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    if args.output_root is None:
        args.output_root = v0.DEFAULT_OUTPUT_PARENT / str(args.as_of) / DEFAULT_OUTPUT_SUBDIR
    return args


def resolve_default_options_panel(as_of: str) -> Path:
    if as_of == DEFAULT_AS_OF:
        return DEFAULT_OPTIONS_PANEL
    return ROOT / "artifacts" / "quant_research" / "options_surface" / as_of / "tardis_deribit_options_surface_features.csv"


def resolve_default_context_report(as_of: str) -> Path:
    if as_of == DEFAULT_AS_OF:
        return DEFAULT_CONTEXT_REPORT
    return (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / as_of
        / "m3_1_options_surface_overlay_context_report_card.json"
    )


def _normalise_subject(value: Any) -> str:
    text = str(value or "").strip().upper()
    for suffix in ("USDT", "USD", "-PERP", "PERP"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def _nan_to_none(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def _float_or_none(value: Any) -> float | None:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def build_top2_options_context(options_panel: pd.DataFrame) -> pd.DataFrame:
    required = {
        "subject",
        "decision_date_utc",
        "iv_25d_skew_residual_method",
        *V1_TRIGGER_COLUMNS,
    }
    missing = sorted(required - set(options_panel.columns))
    if missing:
        raise RuntimeError(f"options panel missing required v1 columns: {missing}")

    working = options_panel.copy()
    working["subject"] = working["subject"].map(_normalise_subject)
    working = working.loc[working["subject"].isin(v0.REQUIRED_OPTION_SUBJECTS)].copy()
    working["decision_date_utc"] = pd.to_datetime(
        working["decision_date_utc"],
        utc=True,
        errors="coerce",
    ).dt.date.astype(str)
    for column in V1_TRIGGER_COLUMNS:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    if set(V1_READY_COLUMNS).issubset(working.columns):
        ready_frame = pd.DataFrame({column: v0._bool_series(working[column]) for column in V1_READY_COLUMNS})
        working["row_ready"] = ready_frame.all(axis=1)
    else:
        working["row_ready"] = working[list(V1_TRIGGER_COLUMNS)].notna().all(axis=1)
    working["f56_residual_method_ready"] = working["iv_25d_skew_residual_method"].astype(str).eq(REQUIRED_F56_METHOD)

    rows: list[dict[str, Any]] = []
    for decision_date, group in working.sort_values(["decision_date_utc", "subject"]).groupby("decision_date_utc"):
        subject_rows = group.drop_duplicates("subject", keep="last").set_index("subject")
        required_values = subject_rows.reindex(v0.REQUIRED_OPTION_SUBJECTS)
        required_present = [subject in subject_rows.index for subject in v0.REQUIRED_OPTION_SUBJECTS]
        ready_subjects = [
            bool(subject_rows.loc[subject, "row_ready"]) if subject in subject_rows.index else False
            for subject in v0.REQUIRED_OPTION_SUBJECTS
        ]
        residual_methods_ready = [
            bool(subject_rows.loc[subject, "f56_residual_method_ready"]) if subject in subject_rows.index else False
            for subject in v0.REQUIRED_OPTION_SUBJECTS
        ]
        trigger_ready = bool(required_values[list(V1_TRIGGER_COLUMNS)].notna().to_numpy().all())
        context_ready = bool(
            all(required_present)
            and all(ready_subjects)
            and all(residual_methods_ready)
            and trigger_ready
        )
        rows.append(
            {
                "decision_date_utc": str(decision_date),
                "subject_count": int(subject_rows.shape[0]),
                "required_subject_count": int(sum(required_present)),
                "ready_required_subject_count": int(sum(ready_subjects)),
                "f56_residual_method_ready_subject_count": int(sum(residual_methods_ready)),
                "context_ready": context_ready,
                "top2_iv_rv_spread_median": _nan_to_none(required_values["iv_rv_spread"].median()),
                "top2_iv_term_slope_min": _nan_to_none(required_values["iv_term_slope"].min()),
                "top2_iv_25d_skew_residual_median": _nan_to_none(
                    required_values["iv_25d_skew_residual"].median()
                ),
                "top2_signed_dealer_gamma_median": _nan_to_none(required_values["dealer_gamma_proxy"].median()),
                "top2_vanna_charm_max": _nan_to_none(required_values["vanna_charm_window"].max()),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("decision_date_utc").reset_index(drop=True)


def train_thresholds_for_window(train_df: pd.DataFrame, context: pd.DataFrame) -> dict[str, Any]:
    if context.empty:
        return {
            "status": "no_options_context",
            "train_context_day_count": 0,
            "iv_rv_spread_q70": None,
            "iv_term_slope_q30": None,
            "iv_25d_skew_residual_q70": None,
            "signed_dealer_gamma_q30": None,
            "vanna_charm_q70": None,
        }
    train_dates = set(v0._date_series_from_timestamp_ms(train_df["timestamp_ms"]).dropna().tolist())
    train_context = context.loc[context["decision_date_utc"].isin(train_dates)].copy()
    ready = train_context.loc[train_context["context_ready"].fillna(False).astype(bool)].copy()
    thresholds = {
        "status": "ok" if not ready.empty else "no_ready_train_context",
        "train_context_day_count": int(train_context.shape[0]),
        "train_ready_context_day_count": int(ready.shape[0]),
        "train_context_date_start": str(train_context["decision_date_utc"].min()) if not train_context.empty else None,
        "train_context_date_end": str(train_context["decision_date_utc"].max()) if not train_context.empty else None,
        "train_ready_context_date_start": str(ready["decision_date_utc"].min()) if not ready.empty else None,
        "train_ready_context_date_end": str(ready["decision_date_utc"].max()) if not ready.empty else None,
        "iv_rv_spread_q70": v0._safe_quantile(ready["top2_iv_rv_spread_median"], 0.70),
        "iv_term_slope_q30": v0._safe_quantile(ready["top2_iv_term_slope_min"], 0.30),
        "iv_25d_skew_residual_q70": v0._safe_quantile(ready["top2_iv_25d_skew_residual_median"], 0.70),
        "signed_dealer_gamma_q30": v0._safe_quantile(ready["top2_signed_dealer_gamma_median"], 0.30),
        "vanna_charm_q70": v0._safe_quantile(ready["top2_vanna_charm_max"], 0.70),
    }
    required = (
        "iv_rv_spread_q70",
        "iv_term_slope_q30",
        "iv_25d_skew_residual_q70",
        "signed_dealer_gamma_q30",
        "vanna_charm_q70",
    )
    if thresholds["status"] == "ok" and any(thresholds[key] is None for key in required):
        thresholds["status"] = "incomplete_train_thresholds"
    return thresholds


def options_overlay_lookup(
    *,
    decision_timestamp_ms: int,
    context_by_date: dict[str, dict[str, Any]],
    thresholds: dict[str, Any],
    variant_label: str,
) -> dict[str, Any]:
    decision_date = v0._date_from_ms(decision_timestamp_ms)
    base = {
        "decision_timestamp_ms": int(decision_timestamp_ms),
        "decision_date_utc": decision_date,
        "options_context_available": False,
        "options_context_ready": False,
        "options_overlay_triggered": False,
        "vol_stress_trigger": False,
        "gamma_expiry_trigger": False,
        "portfolio_target_multiplier": FAIL_OPEN_MULTIPLIER,
        "overlay_reason": "baseline_or_fail_open",
    }
    if variant_label == BASELINE_VARIANT_LABEL:
        base["overlay_reason"] = "baseline"
        return base
    if thresholds.get("status") != "ok":
        base["overlay_reason"] = f"fail_open_{thresholds.get('status')}"
        return base
    row = context_by_date.get(decision_date)
    if not row:
        base["overlay_reason"] = "fail_open_missing_options_context"
        return base
    base["options_context_available"] = True
    base["options_context_ready"] = bool(row.get("context_ready"))
    if not base["options_context_ready"]:
        base["overlay_reason"] = "fail_open_options_context_not_ready"
        return base

    iv_rv = _float_or_none(row.get("top2_iv_rv_spread_median"))
    term = _float_or_none(row.get("top2_iv_term_slope_min"))
    skew = _float_or_none(row.get("top2_iv_25d_skew_residual_median"))
    signed_gamma = _float_or_none(row.get("top2_signed_dealer_gamma_median"))
    vanna = _float_or_none(row.get("top2_vanna_charm_max"))
    if any(value is None for value in (iv_rv, term, skew, signed_gamma, vanna)):
        base["overlay_reason"] = "fail_open_options_context_incomplete"
        return base

    vol_put_stress = bool(
        iv_rv >= float(thresholds["iv_rv_spread_q70"])
        and term <= float(thresholds["iv_term_slope_q30"])
        and skew >= float(thresholds["iv_25d_skew_residual_q70"])
    )
    signed_gamma_expiry = bool(
        signed_gamma <= float(thresholds["signed_dealer_gamma_q30"])
        and vanna >= float(thresholds["vanna_charm_q70"])
    )
    triggered = vol_put_stress or signed_gamma_expiry
    if vol_put_stress and signed_gamma_expiry:
        reason = "triggered_both"
    elif vol_put_stress:
        reason = "triggered_vol_put_stress"
    elif signed_gamma_expiry:
        reason = "triggered_signed_gamma_expiry"
    else:
        reason = "ready_not_triggered"
    base.update(
        {
            "vol_stress_trigger": vol_put_stress,
            "gamma_expiry_trigger": signed_gamma_expiry,
            "options_overlay_triggered": triggered,
            "portfolio_target_multiplier": FROZEN_MULTIPLIER if triggered else FAIL_OPEN_MULTIPLIER,
            "overlay_reason": reason,
        }
    )
    return base


def research_gate(summary: pd.DataFrame) -> dict[str, Any]:
    candidate = summary.loc[summary["label"].eq(CANDIDATE_LABEL)]
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)]
    if candidate.empty or baseline.empty:
        return {"research_watch_state_allowed": False, "blockers": ["missing_baseline_or_candidate_row"]}
    row = candidate.iloc[0]
    blockers: list[str] = []
    trigger_count = int(row["overlay_triggered_decision_count"])
    trigger_fraction = float(row["overlay_triggered_decision_fraction"])
    if trigger_count < MIN_TRIGGER_COUNT:
        blockers.append("trigger_count_below_min_16")
    if trigger_fraction < MIN_TRIGGER_FRACTION:
        blockers.append("trigger_fraction_below_min_0_025")
    if trigger_fraction > MAX_TRIGGER_FRACTION:
        blockers.append("trigger_fraction_above_max_0_20")
    if float(row["delta_full_oos_cumulative_return_vs_baseline"]) < -1e-12:
        blockers.append("full_oos_cumulative_return_worse_than_baseline")
    if float(row["delta_full_oos_h10d_equivalent_sharpe_vs_baseline"]) < -1e-12:
        blockers.append("full_oos_h10d_equivalent_sharpe_worse_than_baseline")
    if float(row["delta_full_oos_max_drawdown_vs_baseline"]) > 1e-12:
        blockers.append("full_oos_max_drawdown_worse_than_baseline")
    if float(row["delta_holdout_cumulative_return_vs_baseline"]) < -1e-12:
        blockers.append("holdout_cumulative_return_worse_than_baseline")
    if int(row["full_oos_capacity_breach_count"]) != 0:
        blockers.append("capacity_breach_count_nonzero")
    if int(row["exclude_first_context_period_count"]) <= 0:
        blockers.append("exclude_first_60_context_dates_slice_empty")
    else:
        if float(row["delta_exclude_first_context_cumulative_return_vs_baseline"]) < -1e-12:
            blockers.append("exclude_first_60_context_dates_cumulative_return_worse_than_baseline")
        if float(row["delta_exclude_first_context_h10d_equivalent_sharpe_vs_baseline"]) < -1e-12:
            blockers.append("exclude_first_60_context_dates_h10d_sharpe_worse_than_baseline")
    allowed = not blockers
    return {
        "research_watch_state_allowed": allowed,
        "eligible_for_research_watch_review": allowed,
        "blockers": blockers,
        "trigger_count": trigger_count,
        "trigger_fraction": trigger_fraction,
        "min_trigger_count": MIN_TRIGGER_COUNT,
        "min_trigger_fraction": MIN_TRIGGER_FRACTION,
        "max_trigger_fraction": MAX_TRIGGER_FRACTION,
        "vol_put_stress_trigger_count": int(row.get("vol_stress_trigger_count", 0) or 0),
        "signed_gamma_expiry_trigger_count": int(row.get("gamma_expiry_trigger_count", 0) or 0),
    }


def render_markdown(path: Path, payload: dict[str, Any], summary: pd.DataFrame) -> None:
    candidate = summary.loc[summary["label"].eq(CANDIDATE_LABEL)].iloc[0].to_dict()
    baseline = summary.loc[summary["label"].eq(BASELINE_VARIANT_LABEL)].iloc[0].to_dict()
    exclude_n = int((payload.get("options_context") or {}).get("exclude_first_context_dates") or EXCLUDE_FIRST_CONTEXT_DATES)
    decision = dict(payload.get("decision") or {})
    lines = [
        "# M3.1 Options Surface Overlay v1 Ablation",
        "",
        f"- Generated at UTC: `{payload['generated_at_utc']}`",
        f"- Contract: `{CONTRACT_VERSION}`",
        f"- Effective research baseline: `{payload['effective_research_baseline']}`",
        f"- Candidate: `{CANDIDATE_LABEL}`",
        f"- Research watch allowed: `{decision.get('research_watch_state_allowed')}`",
        f"- Blockers: `{decision.get('blockers')}`",
        "",
        "## Boundary",
        "",
        "- Report-only h10d overlay ablation.",
        "- No active registry, active manifest, v1 feature-admission, live, timer, scheduler, or remote-runner mutation.",
        "- The overlay applies only a portfolio target multiplier after existing top/bottom selection.",
        "- F56 is active only when its residual method is the rolling 60d baseline residual.",
        "",
        "## Frozen Rule",
        "",
        "| trigger | train threshold | test condition |",
        "| --- | --- | --- |",
        "| vol_put_stress | q70 top2 IV-RV, q30 top2 term slope, q70 top2 put-skew residual | IV-RV >= q70 and term slope <= q30 and skew residual >= q70 |",
        "| signed_gamma_expiry | q30 top2 signed dealer gamma, q70 top2 vanna/charm | signed gamma <= q30 and vanna/charm >= q70 |",
        "",
        "When either trigger fires, `portfolio_target_multiplier = 0.90`; otherwise or missing context, `1.0`.",
        "",
        "## Trigger Gate",
        "",
        f"- triggered decisions: `{decision.get('trigger_count')}`",
        f"- triggered fraction: `{decision.get('trigger_fraction')}`",
        f"- vol_put_stress branch count: `{decision.get('vol_put_stress_trigger_count')}`",
        f"- signed_gamma_expiry branch count: `{decision.get('signed_gamma_expiry_trigger_count')}`",
        f"- required trigger count/fraction: `>= {MIN_TRIGGER_COUNT}`, `{MIN_TRIGGER_FRACTION} <= fraction <= {MAX_TRIGGER_FRACTION}`",
        "",
        "## A/B Summary",
        "",
        "| label | full ret | full Sharpe | full DD | holdout ret | trigger frac | breaches |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (baseline, candidate):
        lines.append(
            "| `{label}` | {ret:.6f} | {sharpe:.6f} | {dd:.6f} | {holdout:.6f} | {trigger:.6f} | {breaches} |".format(
                label=row["label"],
                ret=float(row["full_oos_cumulative_return"]),
                sharpe=float(row["full_oos_h10d_equivalent_sharpe"]),
                dd=float(row["full_oos_max_drawdown"]),
                holdout=float(row["holdout_cumulative_return"]),
                trigger=float(row["overlay_triggered_decision_fraction"]),
                breaches=int(row["full_oos_capacity_breach_count"]),
            )
        )
    lines.extend(
        [
            "",
            "## Candidate Deltas",
            "",
            f"- full OOS return delta: `{candidate['delta_full_oos_cumulative_return_vs_baseline']}`",
            f"- full OOS h10d-equivalent Sharpe delta: `{candidate['delta_full_oos_h10d_equivalent_sharpe_vs_baseline']}`",
            f"- full OOS max-drawdown delta: `{candidate['delta_full_oos_max_drawdown_vs_baseline']}`",
            f"- holdout return delta: `{candidate['delta_holdout_cumulative_return_vs_baseline']}`",
            f"- exclude-first-{exclude_n}-context return delta: `{candidate['delta_exclude_first_context_cumulative_return_vs_baseline']}`",
            f"- exclude-first-{exclude_n}-context h10d Sharpe delta: `{candidate['delta_exclude_first_context_h10d_equivalent_sharpe_vs_baseline']}`",
            "",
            "## Artifacts",
            "",
        ]
    )
    for key, value in sorted(dict(payload.get("artifacts") or {}).items()):
        lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.name == "overlay_definitions.json":
        payload = {
            "contract_version": CONTRACT_VERSION,
            "variants": list(VARIANTS),
            "frozen_rule": {
                "required_subjects": list(v0.REQUIRED_OPTION_SUBJECTS),
                "trigger_columns": list(V1_TRIGGER_COLUMNS),
                "f56_required_residual_method": REQUIRED_F56_METHOD,
                "portfolio_target_multiplier_when_triggered": FROZEN_MULTIPLIER,
                "missing_context_multiplier": FAIL_OPEN_MULTIPLIER,
                "train_thresholds": {
                    "iv_rv_spread_q70": "q70(top2_iv_rv_spread_median)",
                    "iv_term_slope_q30": "q30(top2_iv_term_slope_min)",
                    "iv_25d_skew_residual_q70": "q70(top2_iv_25d_skew_residual_median)",
                    "signed_dealer_gamma_q30": "q30(top2_signed_dealer_gamma_median)",
                    "vanna_charm_q70": "q70(top2_vanna_charm_max)",
                },
                "trigger_gate": {
                    "min_trigger_count": MIN_TRIGGER_COUNT,
                    "min_trigger_fraction": MIN_TRIGGER_FRACTION,
                    "max_trigger_fraction": MAX_TRIGGER_FRACTION,
                },
            },
        }
    ORIGINAL_WRITE_JSON(path, payload)


def patch_v0_runner() -> None:
    v0.CONTRACT_VERSION = CONTRACT_VERSION
    v0.DEFAULT_AS_OF = DEFAULT_AS_OF
    v0.DEFAULT_OPTIONS_PANEL = DEFAULT_OPTIONS_PANEL
    v0.DEFAULT_CONTEXT_REPORT = DEFAULT_CONTEXT_REPORT
    v0.DEFAULT_PREREG_DOC = DEFAULT_PREREG_DOC
    v0.CANDIDATE_LABEL = CANDIDATE_LABEL
    v0.FROZEN_MULTIPLIER = FROZEN_MULTIPLIER
    v0.FAIL_OPEN_MULTIPLIER = FAIL_OPEN_MULTIPLIER
    v0.MAX_NON_PATHOLOGICAL_TRIGGER_FRACTION = MAX_TRIGGER_FRACTION
    v0.TRIGGER_COLUMNS = V1_TRIGGER_COLUMNS
    v0.OBSERVATION_ONLY_COLUMNS = ()
    v0.VARIANTS = VARIANTS
    v0.parse_args = parse_args
    v0._resolve_default_options_panel = resolve_default_options_panel
    v0._resolve_default_context_report = resolve_default_context_report
    v0.build_top2_options_context = build_top2_options_context
    v0.train_thresholds_for_window = train_thresholds_for_window
    v0.options_overlay_lookup = options_overlay_lookup
    v0.research_gate = research_gate
    v0.render_markdown = render_markdown
    v0.write_json = write_json


def main() -> int:
    patch_v0_runner()
    return v0.main()


if __name__ == "__main__":
    raise SystemExit(main())
