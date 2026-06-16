from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk  # noqa: E402
from enhengclaw.quant_research.features import (  # noqa: E402
    _xs_alpha_ontology_v5_h10d_base_raw_score,
    _xs_alpha_ontology_v6_h10d_spk_short_replacement_score,
    xs_alpha_ontology_v5_score,
)


CONTRACT_VERSION = "mf05_cross_venue_spk_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_CROSS_VENUE_PANEL = (
    ROOT / "artifacts" / "quant_research" / "cross_venue" / "cross_venue_panel_1d.csv"
)


@dataclass(frozen=True)
class VariantSpec:
    label: str
    candidate_veto_column: str | None
    interpretation: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Event-conditioned MF-05 cross-venue confirmation around SP-K replacements."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--cross-venue-panel", type=Path, default=DEFAULT_CROSS_VENUE_PANEL)
    parser.add_argument("--quantile", type=float, default=0.90)
    parser.add_argument("--min-venues", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _variant_specs() -> list[VariantSpec]:
    return [
        VariantSpec(
            label="spk_raw",
            candidate_veto_column=None,
            interpretation="Unmodified SP-K replacement on the canonical parent.",
        ),
        VariantSpec(
            label="spk_confirm_high_dispersion",
            candidate_veto_column="mf05_not_high_dispersion_flag",
            interpretation="Allow SP-K replacement only when cross-venue spot dispersion is high.",
        ),
        VariantSpec(
            label="spk_veto_high_dispersion",
            candidate_veto_column="mf05_high_dispersion_flag",
            interpretation="Block SP-K replacement when cross-venue spot dispersion is high.",
        ),
        VariantSpec(
            label="spk_confirm_high_abs_premium",
            candidate_veto_column="mf05_not_high_abs_binance_premium_flag",
            interpretation="Allow SP-K replacement only when absolute Binance premium is high.",
        ),
        VariantSpec(
            label="spk_veto_high_abs_premium",
            candidate_veto_column="mf05_high_abs_binance_premium_flag",
            interpretation="Block SP-K replacement when absolute Binance premium is high.",
        ),
        VariantSpec(
            label="spk_confirm_any_cross_venue_stress",
            candidate_veto_column="mf05_not_any_cross_venue_stress_flag",
            interpretation="Allow SP-K replacement only when dispersion or absolute premium is high.",
        ),
        VariantSpec(
            label="spk_veto_any_cross_venue_stress",
            candidate_veto_column="mf05_any_cross_venue_stress_flag",
            interpretation="Block SP-K replacement when dispersion or absolute premium is high.",
        ),
    ]


def _load_frame(
    *,
    as_of: str,
    target_horizon_bars: int,
    cross_venue_panel: Path,
    quantile: float,
    min_venues: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    features_artifact = v5_spk.base_eval._features_artifact_path(as_of)
    risk = v5_spk.base_eval._build_risk_frame(
        features_artifact,
        target_horizon_bars=target_horizon_bars,
    )
    if "date_utc" not in risk.columns:
        risk = risk.copy()
        risk["date_utc"] = pd.to_datetime(
            risk["timestamp_ms"], unit="ms", utc=True, errors="coerce"
        ).dt.date.astype(str)
    panel = pd.read_csv(cross_venue_panel)
    keep = [
        "subject",
        "date_utc",
        "n_venues",
        "cross_venue_spot_dispersion",
        "cross_venue_spot_binance_premium",
    ]
    missing = [column for column in keep if column not in panel.columns]
    if missing:
        raise ValueError(f"cross-venue panel missing required columns: {missing}")
    merged = risk.merge(panel[keep], on=["subject", "date_utc"], how="left")
    merged["n_venues"] = pd.to_numeric(merged["n_venues"], errors="coerce").fillna(0).astype(int)
    merged["cross_venue_spot_dispersion"] = pd.to_numeric(
        merged["cross_venue_spot_dispersion"], errors="coerce"
    )
    merged["cross_venue_abs_binance_premium"] = pd.to_numeric(
        merged["cross_venue_spot_binance_premium"], errors="coerce"
    ).abs()

    ready = merged["n_venues"].ge(int(min_venues))
    dispersion_threshold = _quantile_threshold(
        merged.loc[ready, "cross_venue_spot_dispersion"],
        quantile=float(quantile),
    )
    premium_threshold = _quantile_threshold(
        merged.loc[ready, "cross_venue_abs_binance_premium"],
        quantile=float(quantile),
    )
    merged["mf05_high_dispersion_flag"] = (
        ready & merged["cross_venue_spot_dispersion"].ge(dispersion_threshold)
    )
    merged["mf05_high_abs_binance_premium_flag"] = (
        ready & merged["cross_venue_abs_binance_premium"].ge(premium_threshold)
    )
    merged["mf05_any_cross_venue_stress_flag"] = (
        merged["mf05_high_dispersion_flag"] | merged["mf05_high_abs_binance_premium_flag"]
    )
    merged["mf05_not_high_dispersion_flag"] = ~merged["mf05_high_dispersion_flag"]
    merged["mf05_not_high_abs_binance_premium_flag"] = ~merged[
        "mf05_high_abs_binance_premium_flag"
    ]
    merged["mf05_not_any_cross_venue_stress_flag"] = ~merged[
        "mf05_any_cross_venue_stress_flag"
    ]
    meta = {
        "features_artifact": str(features_artifact),
        "cross_venue_panel": str(cross_venue_panel),
        "quantile": float(quantile),
        "min_venues": int(min_venues),
        "dispersion_threshold": dispersion_threshold,
        "abs_binance_premium_threshold": premium_threshold,
        "cross_venue_row_coverage": float(
            merged["cross_venue_spot_dispersion"].notna().mean()
        ),
        "min_venue_row_coverage": float(ready.mean()),
    }
    return merged, meta


def _quantile_threshold(values: pd.Series, *, quantile: float) -> float:
    cleaned = pd.to_numeric(values, errors="coerce").dropna()
    if cleaned.empty:
        return float("inf")
    return float(cleaned.quantile(float(quantile)))


def _spk_scorer(candidate_veto_column: str | None = None) -> Callable[[pd.DataFrame], pd.Series]:
    def _score(frame: pd.DataFrame) -> pd.Series:
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            frame,
            base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            candidate_veto_column=candidate_veto_column,
        )

    return _score


def _short_rows(
    frame: pd.DataFrame,
    *,
    score_column: str,
    target_horizon_bars: int,
    short_count: int = 3,
) -> pd.DataFrame:
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        score_column,
        "post_pump_stall_core_score_3d",
        "n_venues",
        "cross_venue_spot_dispersion",
        "cross_venue_abs_binance_premium",
        "mf05_high_dispersion_flag",
        "mf05_high_abs_binance_premium_flag",
        "mf05_any_cross_venue_stress_flag",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep = [column for column in keep if column in frame.columns]
    rows: list[dict[str, Any]] = []
    for _, group in frame.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values(score_column, ascending=True).head(min(short_count, len(group)))
        rows.extend(shorts[keep].to_dict("records"))
    return pd.DataFrame(rows)


def _selection_change(
    frame: pd.DataFrame,
    *,
    baseline_score: str,
    candidate_score: str,
    target_horizon_bars: int,
    short_count: int = 3,
) -> dict[str, Any]:
    hcol = f"forward_{target_horizon_bars}d_log_return"
    entered: list[dict[str, Any]] = []
    exited: list[dict[str, Any]] = []
    changed = 0
    total = 0
    for _, group in frame.groupby("timestamp_ms", sort=False):
        total += 1
        baseline = group.sort_values(baseline_score, ascending=True).head(min(short_count, len(group))).copy()
        candidate = group.sort_values(candidate_score, ascending=True).head(min(short_count, len(group))).copy()
        baseline_subjects = set(baseline["subject"].astype(str))
        candidate_subjects = set(candidate["subject"].astype(str))
        if baseline_subjects == candidate_subjects:
            continue
        changed += 1
        entered.extend(candidate.loc[~candidate["subject"].astype(str).isin(baseline_subjects)].to_dict("records"))
        exited.extend(baseline.loc[~baseline["subject"].astype(str).isin(candidate_subjects)].to_dict("records"))
    entered_df = pd.DataFrame(entered)
    exited_df = pd.DataFrame(exited)
    entered_summary = _summarize_rows(entered_df, target_horizon_bars=target_horizon_bars)
    exited_summary = _summarize_rows(exited_df, target_horizon_bars=target_horizon_bars)
    edge = None
    if entered_summary.get(f"next_{target_horizon_bars}d_mean") is not None and exited_summary.get(
        f"next_{target_horizon_bars}d_mean"
    ) is not None:
        edge = float(exited_summary[f"next_{target_horizon_bars}d_mean"]) - float(
            entered_summary[f"next_{target_horizon_bars}d_mean"]
        )
    return {
        "timestamp_count": int(total),
        "changed_timestamp_count": int(changed),
        "changed_timestamp_fraction": float(changed / max(total, 1)),
        "entered": entered_summary,
        "exited": exited_summary,
        f"entered_edge_vs_exited_{target_horizon_bars}d": edge,
    }


def _summarize_rows(rows: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    if rows.empty:
        return {"row_count": 0}
    hcol = f"forward_{target_horizon_bars}d_log_return"
    h = pd.to_numeric(rows.get(hcol), errors="coerce").dropna()
    one = pd.to_numeric(rows.get("forward_1d_log_return"), errors="coerce").dropna()
    out = {
        "row_count": int(len(rows)),
        "timestamp_count": int(rows["timestamp_ms"].nunique()) if "timestamp_ms" in rows.columns else None,
        "subject_count": int(rows["subject"].astype(str).nunique()) if "subject" in rows.columns else None,
        "next_1d_mean": float(one.mean()) if len(one) else None,
        "next_1d_squeeze_gt_5pct_fraction": float((one > 0.05).mean()) if len(one) else None,
        f"next_{target_horizon_bars}d_mean": float(h.mean()) if len(h) else None,
        f"next_{target_horizon_bars}d_negative_fraction": float((h < 0.0).mean()) if len(h) else None,
    }
    for column in (
        "mf05_high_dispersion_flag",
        "mf05_high_abs_binance_premium_flag",
        "mf05_any_cross_venue_stress_flag",
    ):
        if column in rows.columns:
            out[f"{column}_fraction"] = float(rows[column].fillna(False).astype(bool).mean())
    return out


def _compare_short_baskets(
    *,
    candidate: dict[str, Any],
    baseline: dict[str, Any],
    target_horizon_bars: int,
) -> dict[str, Any]:
    field = f"next_{target_horizon_bars}d_mean"
    lhs = baseline.get(field)
    rhs = candidate.get(field)
    edge = None if lhs is None or rhs is None else float(lhs) - float(rhs)
    if edge is not None and edge > 0.0005:
        verdict = "stage0_positive"
    elif edge is not None and abs(edge) <= 0.0005:
        verdict = "stage0_at_par"
    else:
        verdict = "stage0_negative"
    return {f"short_basket_edge_vs_baseline_{target_horizon_bars}d": edge, "verdict": verdict}


def _evaluate_variant(
    frame: pd.DataFrame,
    *,
    spec: VariantSpec,
    parent_summary: dict[str, Any],
    spk_raw_summary: dict[str, Any],
    target_horizon_bars: int,
) -> dict[str, Any]:
    work = frame.copy()
    work["candidate_score"] = _spk_scorer(spec.candidate_veto_column)(work)
    short_rows = _short_rows(
        work,
        score_column="candidate_score",
        target_horizon_bars=target_horizon_bars,
    )
    summary = _summarize_rows(short_rows, target_horizon_bars=target_horizon_bars)
    return {
        "label": spec.label,
        "interpretation": spec.interpretation,
        "candidate_veto_column": spec.candidate_veto_column,
        "short_basket_summary": summary,
        "vs_parent": _compare_short_baskets(
            candidate=summary,
            baseline=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "vs_spk_raw": _compare_short_baskets(
            candidate=summary,
            baseline=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "selection_vs_parent": _selection_change(
            work,
            baseline_score="parent_score",
            candidate_score="candidate_score",
            target_horizon_bars=target_horizon_bars,
        ),
        "selection_vs_spk_raw": _selection_change(
            work,
            baseline_score="spk_raw_score",
            candidate_score="candidate_score",
            target_horizon_bars=target_horizon_bars,
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-mf05-cross-venue-spk-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    frame, input_meta = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        cross_venue_panel=Path(args.cross_venue_panel),
        quantile=float(args.quantile),
        min_venues=int(args.min_venues),
    )
    frame["parent_score"] = xs_alpha_ontology_v5_score(frame)
    frame["spk_raw_score"] = _spk_scorer()(frame)
    parent_summary = _summarize_rows(
        _short_rows(frame, score_column="parent_score", target_horizon_bars=int(args.target_horizon_bars)),
        target_horizon_bars=int(args.target_horizon_bars),
    )
    spk_raw_summary = _summarize_rows(
        _short_rows(frame, score_column="spk_raw_score", target_horizon_bars=int(args.target_horizon_bars)),
        target_horizon_bars=int(args.target_horizon_bars),
    )
    evaluations = {
        spec.label: _evaluate_variant(
            frame,
            spec=spec,
            parent_summary=parent_summary,
            spk_raw_summary=spk_raw_summary,
            target_horizon_bars=int(args.target_horizon_bars),
        )
        for spec in _variant_specs()
    }
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "input_meta": input_meta,
        "frame_rows": int(len(frame)),
        "timestamp_count": int(frame["timestamp_ms"].nunique()),
        "parent_short_basket_summary": parent_summary,
        "spk_raw_short_basket_summary": spk_raw_summary,
        "evaluation": evaluations,
        "decision_rules": {
            "short_return_sign": "For selected shorts, more negative forward return is better.",
            "promote_to_manifest_ab_if": [
                "candidate improves raw SP-K short basket by at least 5 bps",
                "candidate remains positive versus canonical parent",
                "selection vs SP-K raw has non-trivial changed timestamp fraction",
                "entered rows are better shorts than exited rows",
            ],
        },
    }
    report_path = output_dir / "mf05_cross_venue_spk_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote MF-05 cross-venue SP-K Stage 0 report to {report_path}")
    summary = {
        label: {
            "vs_parent": payload["vs_parent"]["verdict"],
            "vs_spk_raw": payload["vs_spk_raw"]["verdict"],
            "edge_vs_spk_raw": payload["vs_spk_raw"].get(
                f"short_basket_edge_vs_baseline_{int(args.target_horizon_bars)}d"
            ),
            "changed_vs_spk_raw": payload["selection_vs_spk_raw"]["changed_timestamp_fraction"],
            "entered_edge_vs_exited": payload["selection_vs_spk_raw"].get(
                f"entered_edge_vs_exited_{int(args.target_horizon_bars)}d"
            ),
        }
        for label, payload in evaluations.items()
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
