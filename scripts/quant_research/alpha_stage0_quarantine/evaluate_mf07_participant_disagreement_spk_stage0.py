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


CONTRACT_VERSION = "mf07_participant_disagreement_spk_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"


@dataclass(frozen=True)
class VariantSpec:
    label: str
    candidate_veto_column: str | None
    interpretation: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Event-conditioned MF-07 participant-disagreement diagnostics around SP-K."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _variant_specs() -> list[VariantSpec]:
    return [
        VariantSpec("spk_raw", None, "Unmodified SP-K replacement on the canonical parent."),
        VariantSpec(
            "spk_confirm_low_top_global_corr",
            "mf07_not_low_top_global_corr_flag",
            "Allow SP-K replacement only when top/global 1h correlation is low.",
        ),
        VariantSpec(
            "spk_veto_low_top_global_corr",
            "mf07_low_top_global_corr_flag",
            "Block SP-K replacement when top/global 1h correlation is low.",
        ),
        VariantSpec(
            "spk_confirm_high_abs_tt_retail_gap",
            "mf07_not_high_abs_tt_retail_gap_flag",
            "Allow SP-K replacement only when top-trader versus global long% gap is high.",
        ),
        VariantSpec(
            "spk_veto_high_abs_tt_retail_gap",
            "mf07_high_abs_tt_retail_gap_flag",
            "Block SP-K replacement when top-trader versus global long% gap is high.",
        ),
        VariantSpec(
            "spk_confirm_high_tt_velocity",
            "mf07_not_high_tt_velocity_flag",
            "Allow SP-K replacement only when top-trader 1h velocity is high.",
        ),
        VariantSpec(
            "spk_veto_high_tt_velocity",
            "mf07_high_tt_velocity_flag",
            "Block SP-K replacement when top-trader 1h velocity is high.",
        ),
        VariantSpec(
            "spk_confirm_any_mf07_stress",
            "mf07_not_any_participant_stress_flag",
            "Allow SP-K replacement only when any participant-disagreement stress flag is active.",
        ),
        VariantSpec(
            "spk_veto_any_mf07_stress",
            "mf07_any_participant_stress_flag",
            "Block SP-K replacement when any participant-disagreement stress flag is active.",
        ),
    ]


def _load_frame(*, as_of: str, target_horizon_bars: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    features_artifact = v5_spk.base_eval._features_artifact_path(as_of)
    frame = v5_spk.base_eval._build_risk_frame(
        features_artifact,
        target_horizon_bars=target_horizon_bars,
    )
    frame = _canonicalize_participant_columns(frame)
    frame, flag_meta = _add_mf07_flags(frame)
    meta = {"features_artifact": str(features_artifact), **flag_meta}
    return frame, meta


def _canonicalize_participant_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    aliases = {
        "top_global_disagreement_1h_30d": [
            "top_global_disagreement_1h_30d",
            "top_global_disagreement_1h_30d_x",
            "top_global_disagreement_1h_30d_y",
        ],
        "top_trader_velocity_1h_abs_24h": [
            "top_trader_velocity_1h_abs_24h",
            "top_trader_velocity_1h_abs_24h_x",
            "top_trader_velocity_1h_abs_24h_y",
        ],
        "top_trader_velocity_1h_signed_24h": [
            "top_trader_velocity_1h_signed_24h",
            "top_trader_velocity_1h_signed_24h_x",
            "top_trader_velocity_1h_signed_24h_y",
        ],
    }
    for target, candidates in aliases.items():
        if target in out.columns:
            continue
        for candidate in candidates:
            if candidate in out.columns:
                out[target] = out[candidate]
                break
    if "disagree_tt_retail" not in out.columns:
        top = pd.to_numeric(out.get("coinglass_top_trader_long_pct_smooth_5"), errors="coerce")
        glob = pd.to_numeric(out.get("coinglass_global_account_long_pct"), errors="coerce")
        out["disagree_tt_retail"] = top - glob
    return out


def _quantile(values: pd.Series, q: float) -> float:
    cleaned = pd.to_numeric(values, errors="coerce").dropna()
    if cleaned.empty:
        return float("nan")
    return float(cleaned.quantile(float(q)))


def _add_mf07_flags(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    corr = pd.to_numeric(out.get("top_global_disagreement_1h_30d"), errors="coerce")
    abs_gap = pd.to_numeric(out.get("disagree_tt_retail"), errors="coerce").abs()
    velocity = pd.to_numeric(out.get("top_trader_velocity_1h_abs_24h"), errors="coerce")

    corr_q10 = _quantile(corr, 0.10)
    gap_q90 = _quantile(abs_gap, 0.90)
    velocity_q90 = _quantile(velocity, 0.90)

    out["mf07_low_top_global_corr_flag"] = corr.le(corr_q10).fillna(False)
    out["mf07_high_abs_tt_retail_gap_flag"] = abs_gap.ge(gap_q90).fillna(False)
    out["mf07_high_tt_velocity_flag"] = velocity.ge(velocity_q90).fillna(False)
    out["mf07_any_participant_stress_flag"] = (
        out["mf07_low_top_global_corr_flag"]
        | out["mf07_high_abs_tt_retail_gap_flag"]
        | out["mf07_high_tt_velocity_flag"]
    )

    for column in (
        "mf07_low_top_global_corr_flag",
        "mf07_high_abs_tt_retail_gap_flag",
        "mf07_high_tt_velocity_flag",
        "mf07_any_participant_stress_flag",
    ):
        out[f"mf07_not_{column.removeprefix('mf07_')}"] = ~out[column]

    # Stable names for scorer candidate_veto_column.
    out["mf07_not_low_top_global_corr_flag"] = ~out["mf07_low_top_global_corr_flag"]
    out["mf07_not_high_abs_tt_retail_gap_flag"] = ~out["mf07_high_abs_tt_retail_gap_flag"]
    out["mf07_not_high_tt_velocity_flag"] = ~out["mf07_high_tt_velocity_flag"]
    out["mf07_not_any_participant_stress_flag"] = ~out["mf07_any_participant_stress_flag"]

    meta = {
        "top_global_corr_q10": corr_q10,
        "abs_tt_retail_gap_q90": gap_q90,
        "top_trader_velocity_abs_q90": velocity_q90,
        "top_global_corr_coverage": float(corr.notna().mean()),
        "abs_tt_retail_gap_coverage": float(abs_gap.notna().mean()),
        "top_trader_velocity_coverage": float(velocity.notna().mean()),
        "low_top_global_corr_fraction": float(out["mf07_low_top_global_corr_flag"].mean()),
        "high_abs_tt_retail_gap_fraction": float(out["mf07_high_abs_tt_retail_gap_flag"].mean()),
        "high_tt_velocity_fraction": float(out["mf07_high_tt_velocity_flag"].mean()),
        "any_participant_stress_fraction": float(out["mf07_any_participant_stress_flag"].mean()),
    }
    return out, meta


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
        "top_global_disagreement_1h_30d",
        "disagree_tt_retail",
        "top_trader_velocity_1h_abs_24h",
        "mf07_low_top_global_corr_flag",
        "mf07_high_abs_tt_retail_gap_flag",
        "mf07_high_tt_velocity_flag",
        "mf07_any_participant_stress_flag",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep = [column for column in keep if column in frame.columns]
    rows: list[dict[str, Any]] = []
    for _, group in frame.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values(score_column, ascending=True).head(min(short_count, len(group)))
        rows.extend(shorts[keep].to_dict("records"))
    return pd.DataFrame(rows)


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
        "mf07_low_top_global_corr_flag",
        "mf07_high_abs_tt_retail_gap_flag",
        "mf07_high_tt_velocity_flag",
        "mf07_any_participant_stress_flag",
    ):
        if column in rows.columns:
            out[f"{column}_fraction"] = float(rows[column].fillna(False).astype(bool).mean())
    return out


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
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "post_pump_stall_core_score_3d",
        "mf07_low_top_global_corr_flag",
        "mf07_high_abs_tt_retail_gap_flag",
        "mf07_high_tt_velocity_flag",
        "mf07_any_participant_stress_flag",
        "forward_1d_log_return",
        hcol,
    ]
    keep = [column for column in keep if column in frame.columns]
    for _, group in frame.groupby("timestamp_ms", sort=False):
        total += 1
        baseline = group.sort_values(baseline_score, ascending=True).head(min(short_count, len(group))).copy()
        candidate = group.sort_values(candidate_score, ascending=True).head(min(short_count, len(group))).copy()
        baseline_subjects = set(baseline["subject"].astype(str))
        candidate_subjects = set(candidate["subject"].astype(str))
        if baseline_subjects == candidate_subjects:
            continue
        changed += 1
        entered.extend(candidate.loc[~candidate["subject"].astype(str).isin(baseline_subjects), keep].to_dict("records"))
        exited.extend(baseline.loc[~baseline["subject"].astype(str).isin(candidate_subjects), keep].to_dict("records"))
    entered_summary = _summarize_rows(pd.DataFrame(entered), target_horizon_bars=target_horizon_bars)
    exited_summary = _summarize_rows(pd.DataFrame(exited), target_horizon_bars=target_horizon_bars)
    edge = None
    field = f"next_{target_horizon_bars}d_mean"
    if entered_summary.get(field) is not None and exited_summary.get(field) is not None:
        edge = float(exited_summary[field]) - float(entered_summary[field])
    return {
        "timestamp_count": int(total),
        "changed_timestamp_count": int(changed),
        "changed_timestamp_fraction": float(changed / max(total, 1)),
        "entered": entered_summary,
        "exited": exited_summary,
        f"entered_edge_vs_exited_{target_horizon_bars}d": edge,
    }


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
    summary = _summarize_rows(
        _short_rows(work, score_column="candidate_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )
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
        / f"{args.as_of}-mf07-participant-disagreement-spk-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    target_horizon_bars = int(args.target_horizon_bars)
    frame, input_meta = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
    )
    frame["parent_score"] = xs_alpha_ontology_v5_score(frame)
    frame["spk_raw_score"] = _spk_scorer()(frame)
    parent_summary = _summarize_rows(
        _short_rows(frame, score_column="parent_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )
    spk_raw_summary = _summarize_rows(
        _short_rows(frame, score_column="spk_raw_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )
    evaluations = {
        spec.label: _evaluate_variant(
            frame,
            spec=spec,
            parent_summary=parent_summary,
            spk_raw_summary=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        )
        for spec in _variant_specs()
    }
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": target_horizon_bars,
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
    report_path = output_dir / "mf07_participant_disagreement_spk_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote MF-07 participant-disagreement SP-K Stage 0 report to {report_path}")
    summary = {
        label: {
            "vs_parent": payload["vs_parent"]["verdict"],
            "vs_spk_raw": payload["vs_spk_raw"]["verdict"],
            "edge_vs_spk_raw": payload["vs_spk_raw"].get(
                f"short_basket_edge_vs_baseline_{target_horizon_bars}d"
            ),
            "changed_vs_spk_raw": payload["selection_vs_spk_raw"]["changed_timestamp_fraction"],
            "entered_edge_vs_exited": payload["selection_vs_spk_raw"].get(
                f"entered_edge_vs_exited_{target_horizon_bars}d"
            ),
        }
        for label, payload in evaluations.items()
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
