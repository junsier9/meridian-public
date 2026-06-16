from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    _timestamp_percentile_rank,
    _xs_alpha_ontology_v5_h10d_base_raw_score,
    xs_alpha_ontology_v5_score,
)


CONTRACT_VERSION = "m3_2_canonical_parent_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_PANEL_PATH = ROOT / "artifacts" / "quant_research" / "onchain" / "m3_2_feature_panel_1d.csv"


@dataclass(frozen=True)
class VariantSpec:
    label: str
    state_column: str
    exposure_column: str
    weight: float
    mode: str
    second_exposure_column: str | None = None
    second_weight: float = 0.0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 0 canonical-parent diagnostics for M3.2 MF13/MF14 gates."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--panel-path", type=Path, default=DEFAULT_PANEL_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _variant_specs() -> list[VariantSpec]:
    return [
        VariantSpec(
            label="mf14_sell_beta_v5_parent",
            state_column="m3_2_btc_sell_pressure_state",
            exposure_column="lead_lag_beta_btc",
            weight=-0.032,
            mode="sell_pressure",
        ),
        VariantSpec(
            label="mf14_sell_mid_short_v5_parent",
            state_column="m3_2_btc_sell_pressure_state",
            exposure_column="lead_lag_beta_btc",
            weight=-0.028,
            mode="sell_pressure_mid",
            second_exposure_column="relative_strength_20",
            second_weight=0.50,
        ),
        VariantSpec(
            label="mf14_rebound_idio_v5_parent",
            state_column="m3_2_reflexive_rebound_state",
            exposure_column="idiosyncratic_share",
            weight=0.024,
            mode="rebound",
        ),
        VariantSpec(
            label="mf13_tron_impulse_def_beta_v5_parent",
            state_column="m3_2_tron_flow_impulse_state",
            exposure_column="lead_lag_beta_btc",
            weight=-0.030,
            mode="tron_impulse",
        ),
    ]


def _load_frame(*, as_of: str, target_horizon_bars: int, panel_path: Path) -> pd.DataFrame:
    features_artifact = v5_spk.base_eval._features_artifact_path(as_of)
    risk_frame = v5_spk.base_eval._build_risk_frame(
        features_artifact,
        target_horizon_bars=target_horizon_bars,
    )
    if "date_utc" not in risk_frame.columns:
        risk_frame = risk_frame.copy()
        risk_frame["date_utc"] = pd.to_datetime(
            risk_frame["timestamp_ms"], unit="ms", utc=True, errors="coerce"
        ).dt.date.astype(str)
    panel = pd.read_csv(panel_path)
    state_columns = [
        "decision_date_utc",
        "m3_2_panel_ready",
        "m3_2_btc_sell_pressure_state",
        "m3_2_reflexive_rebound_state",
        "m3_2_tron_flow_impulse_state",
    ]
    missing = [column for column in state_columns if column not in panel.columns]
    if missing:
        raise ValueError(f"M3.2 panel missing required columns: {missing}")
    states = panel[state_columns].copy()
    states["date_utc"] = states["decision_date_utc"].astype(str)
    states = states.drop(columns=["decision_date_utc"])
    merged = risk_frame.merge(states, on="date_utc", how="left", suffixes=("", "_m3_2_panel"))
    for column in state_columns:
        if column == "decision_date_utc":
            continue
        panel_column = f"{column}_m3_2_panel"
        if panel_column in merged.columns:
            merged[column] = merged[panel_column].combine_first(merged.get(column))
            merged = merged.drop(columns=[panel_column])
    merged["m3_2_panel_ready"] = merged["m3_2_panel_ready"].fillna(False).astype(bool)
    for column in [
        "m3_2_btc_sell_pressure_state",
        "m3_2_reflexive_rebound_state",
        "m3_2_tron_flow_impulse_state",
    ]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    return merged


def _z_by_timestamp(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame.get(column, pd.Series(0.0, index=frame.index)), errors="coerce")
    grouped = values.groupby(frame["timestamp_ms"])
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0.0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _activation(frame: pd.DataFrame, spec: VariantSpec) -> pd.Series:
    state = pd.to_numeric(frame[spec.state_column], errors="coerce").fillna(0.0)
    active = frame["m3_2_panel_ready"].fillna(False).astype(bool)
    if spec.mode in {"sell_pressure", "sell_pressure_mid"}:
        raw = np.tanh(np.clip((state - 0.75) / 0.65, 0.0, None))
    elif spec.mode == "rebound":
        raw = np.tanh(np.clip((state - 0.75) / 0.65, 0.0, None))
    elif spec.mode == "tron_impulse":
        raw = np.tanh(np.clip((state - 1.0) / 0.55, 0.0, None))
    else:
        raise ValueError(f"unknown mode: {spec.mode}")
    return pd.Series(np.where(active, raw, 0.0), index=frame.index, dtype="float64")


def _mid_liquidity_mask(frame: pd.DataFrame) -> pd.Series:
    if "liquidity_bucket" not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return frame["liquidity_bucket"].astype(str).str.lower().eq("mid_liquidity").astype("float64")


def _score_variant(frame: pd.DataFrame, spec: VariantSpec) -> pd.Series:
    base_raw = _xs_alpha_ontology_v5_h10d_base_raw_score(frame).astype("float64")
    exposure = _z_by_timestamp(frame, spec.exposure_column)
    if spec.mode == "sell_pressure_mid":
        second = _z_by_timestamp(frame, str(spec.second_exposure_column)).clip(lower=0.0)
        exposure = _mid_liquidity_mask(frame) * (exposure.clip(lower=0.0) + float(spec.second_weight) * second)
    interaction = float(spec.weight) * _activation(frame, spec) * exposure
    raw = (base_raw + interaction).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def _portfolio_rows(
    frame: pd.DataFrame,
    *,
    score_column: str,
    target_horizon_bars: int,
    side_count: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    hcol = f"forward_{target_horizon_bars}d_log_return"
    sides: list[dict[str, Any]] = []
    portfolio: list[dict[str, Any]] = []
    keep_extra = [
        "date_utc",
        "timestamp_ms",
        "subject",
        "liquidity_bucket",
        score_column,
        "m3_2_panel_ready",
        "m3_2_btc_sell_pressure_state",
        "m3_2_reflexive_rebound_state",
        "m3_2_tron_flow_impulse_state",
        "forward_1d_log_return",
        hcol,
    ]
    keep_extra = [column for column in keep_extra if column in frame.columns]
    for timestamp, group in frame.groupby("timestamp_ms", sort=False):
        ordered = group.sort_values(score_column, ascending=False).copy()
        if len(ordered) < side_count * 2:
            continue
        longs = ordered.head(side_count).copy()
        shorts = ordered.tail(side_count).copy()
        long_ret = pd.to_numeric(longs[hcol], errors="coerce").mean()
        short_ret = pd.to_numeric(shorts[hcol], errors="coerce").mean()
        portfolio.append(
            {
                "timestamp_ms": int(timestamp),
                "date_utc": str(group["date_utc"].iloc[0]),
                "long_mean_return": float(long_ret) if pd.notna(long_ret) else None,
                "short_mean_return": float(short_ret) if pd.notna(short_ret) else None,
                "long_short_return": float(long_ret - short_ret)
                if pd.notna(long_ret) and pd.notna(short_ret)
                else None,
                "m3_2_panel_ready": bool(group["m3_2_panel_ready"].fillna(False).astype(bool).any()),
            }
        )
        long_rows = longs[keep_extra].copy()
        long_rows["side"] = "long"
        short_rows = shorts[keep_extra].copy()
        short_rows["side"] = "short"
        sides.extend(pd.concat([long_rows, short_rows], axis=0).to_dict("records"))
    return pd.DataFrame(sides), pd.DataFrame(portfolio)


def _summarize_portfolio(rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {"timestamp_count": 0}
    returns = pd.to_numeric(rows["long_short_return"], errors="coerce").dropna()
    ready = rows.loc[rows["m3_2_panel_ready"].fillna(False).astype(bool)]
    ready_returns = pd.to_numeric(ready["long_short_return"], errors="coerce").dropna()
    return {
        "timestamp_count": int(len(rows)),
        "ready_timestamp_count": int(len(ready)),
        "ready_timestamp_fraction": float(len(ready) / max(len(rows), 1)),
        "long_short_mean": float(returns.mean()) if len(returns) else None,
        "long_short_positive_fraction": float((returns > 0.0).mean()) if len(returns) else None,
        "ready_long_short_mean": float(ready_returns.mean()) if len(ready_returns) else None,
        "ready_long_short_positive_fraction": float((ready_returns > 0.0).mean()) if len(ready_returns) else None,
    }


def _boundary_change_summary(parent_sides: pd.DataFrame, candidate_sides: pd.DataFrame) -> dict[str, Any]:
    key = ["timestamp_ms", "side"]
    parent_sets = parent_sides.groupby(key)["subject"].apply(lambda x: frozenset(x.astype(str)))
    candidate_sets = candidate_sides.groupby(key)["subject"].apply(lambda x: frozenset(x.astype(str)))
    rows: list[dict[str, Any]] = []
    for idx in sorted(set(parent_sets.index).intersection(set(candidate_sets.index))):
        parent = parent_sets.loc[idx]
        candidate = candidate_sets.loc[idx]
        rows.append(
            {
                "timestamp_ms": int(idx[0]),
                "side": str(idx[1]),
                "changed": bool(parent != candidate),
                "entered_count": int(len(candidate - parent)),
                "exited_count": int(len(parent - candidate)),
            }
        )
    change = pd.DataFrame(rows)
    out: dict[str, Any] = {}
    for side, group in change.groupby("side") if not change.empty else []:
        out[f"{side}_changed_timestamp_fraction"] = float(group["changed"].mean())
        out[f"{side}_mean_entered_count"] = float(group["entered_count"].mean())
    return out


def _compare(candidate: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in [
        "long_short_mean",
        "long_short_positive_fraction",
        "ready_long_short_mean",
        "ready_long_short_positive_fraction",
    ]:
        lhs = parent.get(field)
        rhs = candidate.get(field)
        out[f"delta_{field}"] = None if lhs is None or rhs is None else float(rhs) - float(lhs)
    delta_ready = out.get("delta_ready_long_short_mean")
    if delta_ready is not None and delta_ready > 0.0005:
        verdict = "stage0_positive"
    elif delta_ready is not None and abs(delta_ready) <= 0.0005:
        verdict = "stage0_at_par"
    else:
        verdict = "stage0_negative"
    out["verdict"] = verdict
    return out


def _evaluate(frame: pd.DataFrame, *, spec: VariantSpec, target_horizon_bars: int) -> dict[str, Any]:
    work = frame.copy()
    work["candidate_score"] = _score_variant(work, spec)
    work["parent_score"] = xs_alpha_ontology_v5_score(work)
    parent_sides, parent_portfolio = _portfolio_rows(
        work,
        score_column="parent_score",
        target_horizon_bars=target_horizon_bars,
    )
    candidate_sides, candidate_portfolio = _portfolio_rows(
        work,
        score_column="candidate_score",
        target_horizon_bars=target_horizon_bars,
    )
    parent_summary = _summarize_portfolio(parent_portfolio)
    candidate_summary = _summarize_portfolio(candidate_portfolio)
    return {
        "label": spec.label,
        "spec": {
            "state_column": spec.state_column,
            "exposure_column": spec.exposure_column,
            "weight": spec.weight,
            "mode": spec.mode,
            "second_exposure_column": spec.second_exposure_column,
            "second_weight": spec.second_weight,
        },
        "parent_portfolio": parent_summary,
        "candidate_portfolio": candidate_summary,
        "comparison_vs_parent": _compare(candidate_summary, parent_summary),
        "boundary_change": _boundary_change_summary(parent_sides, candidate_sides),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-2-canonical-parent-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        panel_path=Path(args.panel_path),
    )
    evaluations = {
        spec.label: _evaluate(frame, spec=spec, target_horizon_bars=int(args.target_horizon_bars))
        for spec in _variant_specs()
    }
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "panel_path": str(args.panel_path),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "frame_rows": int(len(frame)),
        "timestamp_count": int(frame["timestamp_ms"].nunique()),
        "m3_2_ready_timestamp_count": int(
            frame.loc[frame["m3_2_panel_ready"].fillna(False).astype(bool), "timestamp_ms"].nunique()
        ),
        "evaluation": evaluations,
        "decision_rules": {
            "promote_to_manifest_ab_if": [
                "ready long-short mean improves parent by at least 5 bps",
                "boundary change is not effectively zero",
                "improvement is not only inherited from legacy v6 reports",
            ],
            "fail_closed_if": [
                "candidate is at-par or negative versus canonical parent",
                "candidate changes too few boundary names for transmission",
            ],
        },
    }
    report_path = output_dir / "m3_2_canonical_parent_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.2 canonical-parent Stage 0 report to {report_path}")
    summary = {
        label: {
            "verdict": payload["comparison_vs_parent"]["verdict"],
            "delta_ready_long_short_mean": payload["comparison_vs_parent"].get(
                "delta_ready_long_short_mean"
            ),
            "long_changed_timestamp_fraction": payload["boundary_change"].get(
                "long_changed_timestamp_fraction"
            ),
            "short_changed_timestamp_fraction": payload["boundary_change"].get(
                "short_changed_timestamp_fraction"
            ),
        }
        for label, payload in evaluations.items()
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
