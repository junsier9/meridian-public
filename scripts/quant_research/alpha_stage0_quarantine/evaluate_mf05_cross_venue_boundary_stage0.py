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
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_score  # noqa: E402


CONTRACT_VERSION = "mf05_cross_venue_boundary_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_CROSS_VENUE_PANEL = (
    ROOT / "artifacts" / "quant_research" / "cross_venue" / "cross_venue_panel_1d.csv"
)


@dataclass(frozen=True)
class BoundarySpec:
    label: str
    signal_column: str
    mode: str
    quantile: float = 0.90
    min_venues: int = 3
    max_replacements: int = 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MF-05 cross-venue boundary diagnostics on canonical h10d parent."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--cross-venue-panel", type=Path, default=DEFAULT_CROSS_VENUE_PANEL)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _specs() -> list[BoundarySpec]:
    return [
        BoundarySpec(
            label="veto_high_dispersion_q90",
            signal_column="cross_venue_spot_dispersion",
            mode="veto",
        ),
        BoundarySpec(
            label="select_high_dispersion_q90",
            signal_column="cross_venue_spot_dispersion",
            mode="select",
        ),
        BoundarySpec(
            label="veto_abs_binance_premium_q90",
            signal_column="cross_venue_abs_binance_premium",
            mode="veto",
        ),
        BoundarySpec(
            label="select_abs_binance_premium_q90",
            signal_column="cross_venue_abs_binance_premium",
            mode="select",
        ),
    ]


def _load_frame(*, as_of: str, target_horizon_bars: int, cross_venue_panel: Path) -> pd.DataFrame:
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
        "cross_venue_spot_max_minus_min_over_mean",
        "cross_venue_spot_binance_premium",
    ]
    missing = [column for column in keep if column not in panel.columns]
    if missing:
        raise ValueError(f"cross-venue panel missing required columns: {missing}")
    merged = risk.merge(panel[keep], on=["subject", "date_utc"], how="left")
    merged["n_venues"] = pd.to_numeric(merged["n_venues"], errors="coerce").fillna(0).astype(int)
    for column in [
        "cross_venue_spot_dispersion",
        "cross_venue_spot_max_minus_min_over_mean",
        "cross_venue_spot_binance_premium",
    ]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    merged["cross_venue_abs_binance_premium"] = merged[
        "cross_venue_spot_binance_premium"
    ].abs()
    return merged


def _threshold(frame: pd.DataFrame, *, column: str, quantile: float, min_venues: int) -> float:
    values = pd.to_numeric(
        frame.loc[frame["n_venues"].ge(int(min_venues)), column],
        errors="coerce",
    ).dropna()
    if values.empty:
        return float("nan")
    return float(values.quantile(float(quantile)))


def _signal_mask(frame: pd.DataFrame, *, spec: BoundarySpec, threshold: float) -> pd.Series:
    if not np.isfinite(threshold):
        return pd.Series(False, index=frame.index)
    signal = pd.to_numeric(frame[spec.signal_column], errors="coerce")
    return frame["n_venues"].ge(int(spec.min_venues)) & signal.ge(float(threshold))


def _summarize(rows: pd.DataFrame, *, target_horizon_bars: int) -> dict[str, Any]:
    if rows.empty:
        return {"row_count": 0}
    hcol = f"forward_{target_horizon_bars}d_log_return"
    one = pd.to_numeric(rows.get("forward_1d_log_return"), errors="coerce").dropna()
    h = pd.to_numeric(rows.get(hcol), errors="coerce").dropna()
    return {
        "row_count": int(len(rows)),
        "timestamp_count": int(rows["timestamp_ms"].nunique()) if "timestamp_ms" in rows.columns else None,
        "subject_count": int(rows["subject"].astype(str).nunique()) if "subject" in rows.columns else None,
        "next_1d_mean": float(one.mean()) if len(one) else None,
        f"next_{target_horizon_bars}d_mean": float(h.mean()) if len(h) else None,
        f"next_{target_horizon_bars}d_negative_fraction": float((h < 0.0).mean()) if len(h) else None,
        "next_1d_squeeze_gt_5pct_fraction": float((one > 0.05).mean()) if len(one) else None,
    }


def _compare(candidate: dict[str, Any], parent: dict[str, Any], *, target_horizon_bars: int) -> dict[str, Any]:
    field = f"next_{target_horizon_bars}d_mean"
    lhs = parent.get(field)
    rhs = candidate.get(field)
    delta = None if lhs is None or rhs is None else float(lhs) - float(rhs)
    # For selected shorts, lower future return is better; parent - candidate > 0 is improvement.
    if delta is not None and delta > 0.0005:
        verdict = "stage0_positive"
    elif delta is not None and abs(delta) <= 0.0005:
        verdict = "stage0_at_par"
    else:
        verdict = "stage0_negative"
    return {
        f"selected_short_edge_vs_parent_{target_horizon_bars}d": delta,
        "verdict": verdict,
    }


def _select_rows(
    frame: pd.DataFrame,
    *,
    spec: BoundarySpec,
    threshold: float,
    target_horizon_bars: int,
    short_count: int = 3,
    pool_size: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    work = frame.copy()
    work["parent_score"] = xs_alpha_ontology_v5_score(work)
    work["cross_venue_signal"] = _signal_mask(work, spec=spec, threshold=threshold)
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "parent_score",
        "n_venues",
        "cross_venue_signal",
        "cross_venue_spot_dispersion",
        "cross_venue_spot_max_minus_min_over_mean",
        "cross_venue_spot_binance_premium",
        "cross_venue_abs_binance_premium",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep = [column for column in keep if column in work.columns]
    parent_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    entered_rows: list[dict[str, Any]] = []
    exited_rows: list[dict[str, Any]] = []
    total = 0
    changed = 0
    signal_ts = 0
    for _, group in work.groupby("timestamp_ms", sort=False):
        total += 1
        ordered = group.sort_values("parent_score", ascending=False).copy()
        if len(ordered) <= short_count:
            continue
        parent_shorts = ordered.tail(short_count).copy()
        tail_pool = ordered.tail(min(pool_size, len(ordered))).copy()
        signal_pool = tail_pool.loc[tail_pool["cross_venue_signal"]].copy()
        if not signal_pool.empty:
            signal_ts += 1
        selected = parent_shorts.copy()
        if spec.mode == "veto":
            vetoed = selected.loc[selected["cross_venue_signal"]].copy()
            if not vetoed.empty:
                replacements = tail_pool.loc[
                    ~tail_pool["subject"].astype(str).isin(parent_shorts["subject"].astype(str))
                    & ~tail_pool["cross_venue_signal"]
                ].sort_values("parent_score", ascending=True)
                selected = pd.concat(
                    [
                        selected.loc[~selected["cross_venue_signal"]],
                        replacements.head(min(int(spec.max_replacements), len(vetoed))),
                    ],
                    axis=0,
                ).sort_values("parent_score", ascending=True).head(short_count)
        elif spec.mode == "select":
            entrants = signal_pool.loc[
                ~signal_pool["subject"].astype(str).isin(parent_shorts["subject"].astype(str))
            ].sort_values("parent_score", ascending=True).head(int(spec.max_replacements))
            if not entrants.empty:
                keep_parent = parent_shorts.sort_values("parent_score", ascending=True).head(
                    max(short_count - len(entrants), 0)
                )
                selected = pd.concat([entrants, keep_parent], axis=0).head(short_count)
        else:
            raise ValueError(f"unknown mode: {spec.mode}")
        parent_subjects = set(parent_shorts["subject"].astype(str))
        selected_subjects = set(selected["subject"].astype(str))
        if parent_subjects != selected_subjects:
            changed += 1
        parent_rows.extend(parent_shorts[keep].to_dict("records"))
        selected_rows.extend(selected[keep].to_dict("records"))
        entered_rows.extend(selected.loc[~selected["subject"].astype(str).isin(parent_subjects), keep].to_dict("records"))
        exited_rows.extend(parent_shorts.loc[~parent_shorts["subject"].astype(str).isin(selected_subjects), keep].to_dict("records"))
    meta = {
        "timestamp_count": int(total),
        "signal_timestamp_count": int(signal_ts),
        "changed_timestamp_count": int(changed),
        "signal_timestamp_fraction": float(signal_ts / max(total, 1)),
        "changed_timestamp_fraction": float(changed / max(total, 1)),
    }
    return (
        pd.DataFrame(parent_rows),
        pd.DataFrame(selected_rows),
        pd.DataFrame(entered_rows),
        pd.DataFrame(exited_rows),
        meta,
    )


def _evaluate(frame: pd.DataFrame, *, spec: BoundarySpec, target_horizon_bars: int) -> dict[str, Any]:
    threshold = _threshold(
        frame,
        column=spec.signal_column,
        quantile=spec.quantile,
        min_venues=spec.min_venues,
    )
    parent, selected, entered, exited, meta = _select_rows(
        frame,
        spec=spec,
        threshold=threshold,
        target_horizon_bars=target_horizon_bars,
    )
    parent_summary = _summarize(parent, target_horizon_bars=target_horizon_bars)
    selected_summary = _summarize(selected, target_horizon_bars=target_horizon_bars)
    return {
        "label": spec.label,
        "spec": {
            "signal_column": spec.signal_column,
            "mode": spec.mode,
            "quantile": spec.quantile,
            "min_venues": spec.min_venues,
            "max_replacements": spec.max_replacements,
            "threshold": threshold,
        },
        "activity": meta,
        "parent_short_summary": parent_summary,
        "selected_summary": selected_summary,
        "selected_vs_parent": _compare(
            selected_summary,
            parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "entered": _summarize(entered, target_horizon_bars=target_horizon_bars),
        "exited": _summarize(exited, target_horizon_bars=target_horizon_bars),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-mf05-cross-venue-boundary-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        cross_venue_panel=Path(args.cross_venue_panel),
    )
    evaluations = {
        spec.label: _evaluate(frame, spec=spec, target_horizon_bars=int(args.target_horizon_bars))
        for spec in _specs()
    }
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "cross_venue_panel": str(args.cross_venue_panel),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "frame_rows": int(len(frame)),
        "timestamp_count": int(frame["timestamp_ms"].nunique()),
        "cross_venue_row_coverage": float(
            frame["cross_venue_spot_dispersion"].notna().mean()
        ),
        "evaluation": evaluations,
        "decision_rules": {
            "short_return_sign": "For selected shorts, more negative forward return is better.",
            "promote_to_manifest_ab_if": [
                "selected shorts improve parent h10d mean by at least 5 bps",
                "changed timestamp fraction is materially non-zero",
                "entered rows are better shorts than exited rows",
            ],
        },
    }
    report_path = output_dir / "mf05_cross_venue_boundary_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote MF-05 cross-venue boundary Stage 0 report to {report_path}")
    summary = {
        label: {
            "verdict": payload["selected_vs_parent"]["verdict"],
            "edge": payload["selected_vs_parent"].get(
                f"selected_short_edge_vs_parent_{int(args.target_horizon_bars)}d"
            ),
            "changed_timestamp_fraction": payload["activity"]["changed_timestamp_fraction"],
            "entered_next_h_mean": payload["entered"].get(f"next_{int(args.target_horizon_bars)}d_mean"),
            "exited_next_h_mean": payload["exited"].get(f"next_{int(args.target_horizon_bars)}d_mean"),
        }
        for label, payload in evaluations.items()
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
