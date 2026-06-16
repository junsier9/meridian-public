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


CONTRACT_VERSION = "m3_2_boundary_activation_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_PANEL_PATH = ROOT / "artifacts" / "quant_research" / "onchain" / "m3_2_feature_panel_1d.csv"


@dataclass(frozen=True)
class BoundarySpec:
    label: str
    side: str
    action: str
    state_column: str
    state_threshold: float
    exposure_mode: str
    interpretation: str
    pool_size: int = 8
    side_count: int = 3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 0 diagnostics for discrete M3.2 on-chain boundary activation."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--panel-path", type=Path, default=DEFAULT_PANEL_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def _variant_specs() -> list[BoundarySpec]:
    return [
        BoundarySpec(
            label="stable_supply_long_high_beta_rs",
            side="long",
            action="replace_high",
            state_column="m3_2_stable_supply_impulse_state",
            state_threshold=0.75,
            exposure_mode="high_beta_rs",
            interpretation="Risk-on stablecoin supply impulse: replace weak long with higher beta/relative-strength name.",
        ),
        BoundarySpec(
            label="dry_powder_long_idio_rs",
            side="long",
            action="replace_high",
            state_column="m3_2_stable_dry_powder_state",
            state_threshold=0.75,
            exposure_mode="idio_rs",
            interpretation="Dry-powder state: replace weak long with idiosyncratic rebound/relative-strength name.",
        ),
        BoundarySpec(
            label="rebound_long_idio",
            side="long",
            action="replace_high",
            state_column="m3_2_reflexive_rebound_state",
            state_threshold=0.75,
            exposure_mode="idio",
            interpretation="Reflexive rebound state: replace weak long with higher idiosyncratic-share name.",
        ),
        BoundarySpec(
            label="sell_pressure_short_high_beta_rs",
            side="short",
            action="replace_high",
            state_column="m3_2_btc_sell_pressure_state",
            state_threshold=0.75,
            exposure_mode="high_beta_rs",
            interpretation="BTC sell-pressure state: replace weak short with high-beta/high-RS name.",
        ),
        BoundarySpec(
            label="tron_impulse_short_high_beta_rs",
            side="short",
            action="replace_high",
            state_column="m3_2_tron_flow_impulse_state",
            state_threshold=0.75,
            exposure_mode="high_beta_rs",
            interpretation="TRON stablecoin impulse state: replace weak short with high-beta/high-RS name.",
        ),
        BoundarySpec(
            label="tron_heat_short_high_rs",
            side="short",
            action="replace_high",
            state_column="m3_2_tron_speculative_heat_state",
            state_threshold=0.75,
            exposure_mode="high_rs",
            interpretation="TRON speculative heat state: replace weak short with high relative-strength name.",
        ),
        BoundarySpec(
            label="sell_pressure_long_veto_high_beta",
            side="long",
            action="veto_high",
            state_column="m3_2_btc_sell_pressure_state",
            state_threshold=0.75,
            exposure_mode="high_beta_rs",
            interpretation="BTC sell-pressure state: veto high-beta/high-RS names already in the long basket.",
        ),
        BoundarySpec(
            label="stable_supply_short_veto_high_beta",
            side="short",
            action="veto_high",
            state_column="m3_2_stable_supply_impulse_state",
            state_threshold=0.75,
            exposure_mode="high_beta_rs",
            interpretation="Risk-on stablecoin impulse: avoid shorting high-beta/high-RS names.",
        ),
    ]


def _as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    text = series.astype(str).str.strip().str.lower()
    return text.isin({"true", "1", "yes", "y"})


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
    state_columns = [column for column in panel.columns if column.startswith("m3_2_")]
    required = {"decision_date_utc", "m3_2_panel_ready", *[spec.state_column for spec in _variant_specs()]}
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise ValueError(f"M3.2 panel missing required columns: {missing}")
    states = panel[["decision_date_utc", *state_columns]].copy()
    states["date_utc"] = states["decision_date_utc"].astype(str)
    states = states.drop(columns=["decision_date_utc"])
    merged = risk_frame.merge(states, on="date_utc", how="left", suffixes=("", "_m3_2_panel"))
    for column in state_columns:
        panel_column = f"{column}_m3_2_panel"
        if panel_column in merged.columns:
            merged[column] = merged[panel_column].combine_first(merged.get(column))
            merged = merged.drop(columns=[panel_column])
    merged["m3_2_panel_ready"] = _as_bool(merged["m3_2_panel_ready"])
    for column in state_columns:
        if column == "m3_2_panel_ready":
            continue
        merged[column] = pd.to_numeric(merged[column], errors="coerce")
    return merged


def _timestamp_zscore(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame.get(column, pd.Series(0.0, index=frame.index)), errors="coerce")
    grouped = values.groupby(frame["timestamp_ms"])
    mean = grouped.transform("mean")
    std = grouped.transform("std").replace(0.0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _exposure_score(frame: pd.DataFrame, mode: str) -> pd.Series:
    beta = _timestamp_zscore(frame, "lead_lag_beta_btc")
    rs = _timestamp_zscore(frame, "relative_strength_20")
    idio = _timestamp_zscore(frame, "idiosyncratic_share")
    vol = _timestamp_zscore(frame, "realized_volatility_20")
    if mode == "high_beta_rs":
        return (beta + 0.5 * rs).astype("float64")
    if mode == "high_rs":
        return rs.astype("float64")
    if mode == "idio":
        return idio.astype("float64")
    if mode == "idio_rs":
        return (idio + 0.5 * rs).astype("float64")
    if mode == "fragile_beta_vol":
        return (beta + 0.5 * vol).astype("float64")
    raise ValueError(f"unknown exposure mode: {mode}")


def _active_mask(frame: pd.DataFrame, spec: BoundarySpec) -> pd.Series:
    state = pd.to_numeric(frame.get(spec.state_column), errors="coerce")
    return frame["m3_2_panel_ready"].fillna(False).astype(bool) & state.ge(float(spec.state_threshold))


def _initial_selection(group: pd.DataFrame, *, score_column: str, side_count: int) -> tuple[list[int], list[int]]:
    ordered = group.sort_values(score_column, ascending=False)
    longs = list(ordered.head(side_count).index)
    shorts = list(ordered.tail(side_count).index)
    return longs, shorts


def _candidate_pool(
    group: pd.DataFrame,
    *,
    score_column: str,
    side: str,
    pool_size: int,
    current: list[int],
) -> pd.DataFrame:
    if side == "long":
        pool = group.sort_values(score_column, ascending=False).head(max(pool_size, len(current) + 1))
    elif side == "short":
        pool = group.sort_values(score_column, ascending=True).head(max(pool_size, len(current) + 1))
    else:
        raise ValueError(f"unknown side: {side}")
    return pool.loc[~pool.index.isin(current)].copy()


def _choose_replacement(
    selected: pd.DataFrame,
    pool: pd.DataFrame,
    *,
    side: str,
    action: str,
    score_column: str,
    exposure_column: str,
) -> tuple[int | None, int | None]:
    if selected.empty or pool.empty:
        return None, None
    exposure = pd.to_numeric(selected[exposure_column], errors="coerce")
    pool_exposure = pd.to_numeric(pool[exposure_column], errors="coerce")
    if action == "replace_high":
        candidate_idx = pool_exposure.idxmax()
        remove_idx = selected[score_column].idxmin() if side == "long" else selected[score_column].idxmax()
        if float(pool_exposure.loc[candidate_idx]) <= float(exposure.loc[remove_idx]):
            return None, None
        return int(remove_idx), int(candidate_idx)
    if action == "replace_low":
        candidate_idx = pool_exposure.idxmin()
        remove_idx = selected[score_column].idxmin() if side == "long" else selected[score_column].idxmax()
        if float(pool_exposure.loc[candidate_idx]) >= float(exposure.loc[remove_idx]):
            return None, None
        return int(remove_idx), int(candidate_idx)
    if action == "veto_high":
        remove_idx = exposure.idxmax()
        candidate_idx = pool_exposure.idxmin()
        if float(pool_exposure.loc[candidate_idx]) >= float(exposure.loc[remove_idx]):
            return None, None
        return int(remove_idx), int(candidate_idx)
    if action == "veto_low":
        remove_idx = exposure.idxmin()
        candidate_idx = pool_exposure.idxmax()
        if float(pool_exposure.loc[candidate_idx]) <= float(exposure.loc[remove_idx]):
            return None, None
        return int(remove_idx), int(candidate_idx)
    raise ValueError(f"unknown action: {action}")


def _apply_boundary_rule(
    frame: pd.DataFrame,
    spec: BoundarySpec,
    *,
    score_column: str = "parent_score",
    apply_replacement: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = frame.copy()
    work["_m3_2_exposure"] = _exposure_score(work, spec.exposure_mode)
    work["_m3_2_active"] = _active_mask(work, spec)
    hcols = [c for c in work.columns if c.startswith("forward_")]
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        score_column,
        "_m3_2_exposure",
        "_m3_2_active",
        "m3_2_panel_ready",
        spec.state_column,
        *hcols,
    ]
    keep = [column for column in keep if column in work.columns]
    rows: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for timestamp, group in work.groupby("timestamp_ms", sort=False):
        longs, shorts = _initial_selection(group, score_column=score_column, side_count=spec.side_count)
        parent_longs = list(longs)
        parent_shorts = list(shorts)
        active = bool(group["_m3_2_active"].fillna(False).astype(bool).any())
        ready = bool(group["m3_2_panel_ready"].fillna(False).astype(bool).any())
        removed_idx: int | None = None
        entered_idx: int | None = None
        if active and apply_replacement:
            current = longs if spec.side == "long" else shorts
            selected = group.loc[current].copy()
            pool = _candidate_pool(
                group,
                score_column=score_column,
                side=spec.side,
                pool_size=spec.pool_size,
                current=current,
            )
            removed_idx, entered_idx = _choose_replacement(
                selected,
                pool,
                side=spec.side,
                action=spec.action,
                score_column=score_column,
                exposure_column="_m3_2_exposure",
            )
            if removed_idx is not None and entered_idx is not None:
                if spec.side == "long":
                    longs = [entered_idx if idx == removed_idx else idx for idx in longs]
                else:
                    shorts = [entered_idx if idx == removed_idx else idx for idx in shorts]
        for side, indices in (("long", longs), ("short", shorts)):
            side_rows = group.loc[indices, keep].copy()
            side_rows["side"] = side
            rows.extend(side_rows.to_dict("records"))
        changes.append(
            {
                "timestamp_ms": int(timestamp),
                "date_utc": str(group["date_utc"].iloc[0]),
                "ready": ready,
                "active": active,
                "long_changed": set(parent_longs) != set(longs),
                "short_changed": set(parent_shorts) != set(shorts),
                "removed_subject": str(group.loc[removed_idx, "subject"]) if removed_idx is not None else None,
                "entered_subject": str(group.loc[entered_idx, "subject"]) if entered_idx is not None else None,
            }
        )
    side_rows = pd.DataFrame(rows)
    change_frame = pd.DataFrame(changes)
    meta = _summarize_changes(change_frame)
    return side_rows, meta


def _summarize_changes(change_frame: pd.DataFrame) -> dict[str, Any]:
    if change_frame.empty:
        return {"timestamp_count": 0}
    out = {
        "timestamp_count": int(len(change_frame)),
        "ready_timestamp_count": int(change_frame["ready"].sum()),
        "active_timestamp_count": int(change_frame["active"].sum()),
        "active_timestamp_fraction": float(change_frame["active"].mean()),
    }
    for side in ("long", "short"):
        changed = change_frame[f"{side}_changed"].fillna(False).astype(bool)
        out[f"{side}_changed_timestamp_fraction"] = float(changed.mean())
        active = change_frame["active"].fillna(False).astype(bool)
        ready = change_frame["ready"].fillna(False).astype(bool)
        out[f"{side}_active_changed_timestamp_fraction"] = float(changed[active].mean()) if active.any() else None
        out[f"{side}_ready_changed_timestamp_fraction"] = float(changed[ready].mean()) if ready.any() else None
    return out


def _portfolio_from_sides(
    sides: pd.DataFrame,
    *,
    target_horizon_bars: int,
) -> pd.DataFrame:
    if sides.empty:
        return pd.DataFrame()
    hcol = f"forward_{target_horizon_bars}d_log_return"
    rows: list[dict[str, Any]] = []
    for timestamp, group in sides.groupby("timestamp_ms", sort=False):
        longs = group[group["side"].eq("long")]
        shorts = group[group["side"].eq("short")]
        long_ret = pd.to_numeric(longs[hcol], errors="coerce").mean()
        short_ret = pd.to_numeric(shorts[hcol], errors="coerce").mean()
        rows.append(
            {
                "timestamp_ms": int(timestamp),
                "date_utc": str(group["date_utc"].iloc[0]),
                "m3_2_panel_ready": bool(group["m3_2_panel_ready"].fillna(False).astype(bool).any()),
                "_m3_2_active": bool(group["_m3_2_active"].fillna(False).astype(bool).any()),
                "long_mean_return": float(long_ret) if pd.notna(long_ret) else None,
                "short_mean_return": float(short_ret) if pd.notna(short_ret) else None,
                "long_short_return": float(long_ret - short_ret)
                if pd.notna(long_ret) and pd.notna(short_ret)
                else None,
            }
        )
    return pd.DataFrame(rows)


def _summarize_side_rows(rows: pd.DataFrame, *, side: str, target_horizon_bars: int) -> dict[str, Any]:
    side_rows = rows[rows["side"].eq(side)] if not rows.empty else pd.DataFrame()
    if side_rows.empty:
        return {"row_count": 0}
    hcol = f"forward_{target_horizon_bars}d_log_return"
    h = pd.to_numeric(side_rows[hcol], errors="coerce").dropna()
    one = pd.to_numeric(side_rows.get("forward_1d_log_return"), errors="coerce").dropna()
    return {
        "row_count": int(len(side_rows)),
        "timestamp_count": int(side_rows["timestamp_ms"].nunique()),
        "subject_count": int(side_rows["subject"].astype(str).nunique()),
        "next_1d_mean": float(one.mean()) if len(one) else None,
        f"next_{target_horizon_bars}d_mean": float(h.mean()) if len(h) else None,
        f"next_{target_horizon_bars}d_positive_fraction": float((h > 0.0).mean()) if len(h) else None,
        f"next_{target_horizon_bars}d_negative_fraction": float((h < 0.0).mean()) if len(h) else None,
    }


def _summarize_portfolio(rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {"timestamp_count": 0}

    def _mean(mask: pd.Series) -> float | None:
        values = pd.to_numeric(rows.loc[mask, "long_short_return"], errors="coerce").dropna()
        return float(values.mean()) if len(values) else None

    def _positive(mask: pd.Series) -> float | None:
        values = pd.to_numeric(rows.loc[mask, "long_short_return"], errors="coerce").dropna()
        return float((values > 0.0).mean()) if len(values) else None

    ready = rows["m3_2_panel_ready"].fillna(False).astype(bool)
    active = rows["_m3_2_active"].fillna(False).astype(bool)
    all_mask = pd.Series(True, index=rows.index)
    return {
        "timestamp_count": int(len(rows)),
        "ready_timestamp_count": int(ready.sum()),
        "active_timestamp_count": int(active.sum()),
        "long_short_mean": _mean(all_mask),
        "long_short_positive_fraction": _positive(all_mask),
        "ready_long_short_mean": _mean(ready),
        "ready_long_short_positive_fraction": _positive(ready),
        "active_long_short_mean": _mean(active),
        "active_long_short_positive_fraction": _positive(active),
    }


def _compare(candidate: dict[str, Any], parent: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field in [
        "long_short_mean",
        "ready_long_short_mean",
        "active_long_short_mean",
        "long_short_positive_fraction",
        "ready_long_short_positive_fraction",
        "active_long_short_positive_fraction",
    ]:
        lhs = parent.get(field)
        rhs = candidate.get(field)
        out[f"delta_{field}"] = None if lhs is None or rhs is None else float(rhs) - float(lhs)
    delta_active = out.get("delta_active_long_short_mean")
    active_count = int(changes.get("active_timestamp_count") or 0)
    long_active_change = changes.get("long_active_changed_timestamp_fraction") or 0.0
    short_active_change = changes.get("short_active_changed_timestamp_fraction") or 0.0
    active_change = max(float(long_active_change), float(short_active_change))
    if delta_active is not None and delta_active > 0.0005 and active_count >= 10 and active_change >= 0.05:
        verdict = "stage0_positive"
    elif delta_active is not None and abs(delta_active) <= 0.0005:
        verdict = "stage0_at_par"
    else:
        verdict = "stage0_negative"
    out["verdict"] = verdict
    return out


def _evaluate(frame: pd.DataFrame, *, spec: BoundarySpec, target_horizon_bars: int) -> dict[str, Any]:
    work = frame.copy()
    work["parent_score"] = xs_alpha_ontology_v5_score(work)
    work["_m3_2_exposure"] = _exposure_score(work, spec.exposure_mode)
    work["_m3_2_active"] = _active_mask(work, spec)
    parent_sides, parent_changes = _apply_boundary_rule(
        work,
        spec,
        score_column="parent_score",
        apply_replacement=False,
    )
    candidate_sides, candidate_changes = _apply_boundary_rule(work, spec, score_column="parent_score")
    parent_portfolio = _portfolio_from_sides(parent_sides, target_horizon_bars=target_horizon_bars)
    candidate_portfolio = _portfolio_from_sides(candidate_sides, target_horizon_bars=target_horizon_bars)
    parent_summary = _summarize_portfolio(parent_portfolio)
    candidate_summary = _summarize_portfolio(candidate_portfolio)
    return {
        "label": spec.label,
        "spec": {
            "side": spec.side,
            "action": spec.action,
            "state_column": spec.state_column,
            "state_threshold": spec.state_threshold,
            "exposure_mode": spec.exposure_mode,
            "pool_size": spec.pool_size,
            "side_count": spec.side_count,
        },
        "interpretation": spec.interpretation,
        "parent_portfolio": parent_summary,
        "candidate_portfolio": candidate_summary,
        "comparison_vs_parent": _compare(candidate_summary, parent_summary, candidate_changes),
        "boundary_change": candidate_changes,
        "candidate_long_summary": _summarize_side_rows(
            candidate_sides, side="long", target_horizon_bars=target_horizon_bars
        ),
        "candidate_short_summary": _summarize_side_rows(
            candidate_sides, side="short", target_horizon_bars=target_horizon_bars
        ),
    }
def _input_meta(frame: pd.DataFrame, *, panel_path: Path) -> dict[str, Any]:
    one = frame.drop_duplicates("timestamp_ms")
    ready = one["m3_2_panel_ready"].fillna(False).astype(bool)
    meta: dict[str, Any] = {
        "panel_path": str(panel_path),
        "ready_timestamp_count": int(ready.sum()),
        "ready_timestamp_fraction": float(ready.mean()) if len(ready) else 0.0,
    }
    for column in sorted({spec.state_column for spec in _variant_specs()}):
        values = pd.to_numeric(one.loc[ready, column], errors="coerce").dropna()
        meta[column] = {
            "ready_non_null_count": int(len(values)),
            "ready_mean": float(values.mean()) if len(values) else None,
            "ready_q75": float(values.quantile(0.75)) if len(values) else None,
            "ready_q90": float(values.quantile(0.90)) if len(values) else None,
            "ready_gt_0_75_count": int((values > 0.75).sum()) if len(values) else 0,
        }
    return meta


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-2-boundary-activation-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    target_horizon_bars = int(args.target_horizon_bars)
    frame = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
        panel_path=Path(args.panel_path),
    )
    evaluations = {
        spec.label: _evaluate(frame, spec=spec, target_horizon_bars=target_horizon_bars)
        for spec in _variant_specs()
    }
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": target_horizon_bars,
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "frame_rows": int(len(frame)),
        "timestamp_count": int(frame["timestamp_ms"].nunique()),
        "input_meta": _input_meta(frame, panel_path=Path(args.panel_path)),
        "evaluation": evaluations,
        "decision_rules": {
            "promote_to_manifest_ab_if": [
                "active-window long-short mean improves parent by at least 5 bps",
                "active-window boundary change is at least 5%",
                "active timestamp count is at least 10",
            ],
            "fail_closed_if": [
                "active-window edge is at-par or negative",
                "change transmission is too sparse",
                "improvement appears only outside M3.2 ready windows",
            ],
        },
    }
    output_path = output_dir / "m3_2_boundary_activation_stage0.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    compact = {
        label: {
            "verdict": payload["comparison_vs_parent"]["verdict"],
            "delta_active_long_short_mean": payload["comparison_vs_parent"].get(
                "delta_active_long_short_mean"
            ),
            "active_timestamp_count": payload["boundary_change"].get("active_timestamp_count"),
            "long_active_changed_timestamp_fraction": payload["boundary_change"].get(
                "long_active_changed_timestamp_fraction"
            ),
            "short_active_changed_timestamp_fraction": payload["boundary_change"].get(
                "short_active_changed_timestamp_fraction"
            ),
        }
        for label, payload in evaluations.items()
    }
    print(f"=== Wrote M3.2 boundary activation Stage 0 report to {output_path}")
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
