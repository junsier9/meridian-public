from __future__ import annotations

import argparse
import json
import sys
import warnings
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

warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="Downcasting object dtype arrays on .fillna",
)

from scripts.quant_research.alpha_stage0_quarantine import (  # noqa: E402
    evaluate_mf07_participant_disagreement_spk_stage0 as mf07_stage0,
)
from enhengclaw.quant_research.features import (  # noqa: E402
    _xs_alpha_ontology_v5_h10d_base_raw_score,
    _xs_alpha_ontology_v6_h10d_spk_short_replacement_score,
    xs_alpha_ontology_v5_score,
)


CONTRACT_VERSION = "mf07_etf_onchain_transition_falsification.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_PARTICIPANT_CONTEXT_PATH = (
    ROOT / "artifacts" / "quant_research" / "coinglass" / "participant_context_1d.csv.gz"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-09-r7-mf07-etf-onchain-transition-falsification"
)


@dataclass(frozen=True)
class TransitionSpec:
    label: str
    flag_column: str
    landing_shape: str
    interpretation: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "R-7 MF-07 PIT ETF/on-chain participant-transition Stage0 and "
            "strict fail-closed falsification."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--participant-context-path", type=Path, default=DEFAULT_PARTICIPANT_CONTEXT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260509)
    parser.add_argument("--min-edge-vs-raw-spk", type=float, default=0.0005)
    parser.add_argument("--min-changed-timestamp-fraction", type=float, default=0.05)
    parser.add_argument("--min-entered-edge-vs-exited", type=float, default=0.0)
    return parser


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pre_registered_specs() -> list[TransitionSpec]:
    return [
        TransitionSpec(
            label="confirm_any_mf07_stress_cg_risk_off",
            flag_column="r7_any_mf07_stress_cg_risk_off_flag",
            landing_shape="candidate_confirm",
            interpretation=(
                "Allow SP-K replacement candidates only when an MF-07 participant-stress "
                "state is confirmed by ETF outflow or whale-to-exchange stress."
            ),
        ),
        TransitionSpec(
            label="confirm_high_gap_cg_risk_off",
            flag_column="r7_high_gap_cg_risk_off_flag",
            landing_shape="candidate_confirm",
            interpretation=(
                "Allow SP-K replacement candidates only when top/global positioning gap "
                "is high and CoinGlass ETF/whale context confirms risk-off."
            ),
        ),
        TransitionSpec(
            label="confirm_low_corr_cg_risk_off",
            flag_column="r7_low_corr_cg_risk_off_flag",
            landing_shape="candidate_confirm",
            interpretation=(
                "Allow SP-K replacement candidates only when top/global correlation is "
                "low and CoinGlass ETF/whale context confirms risk-off."
            ),
        ),
        TransitionSpec(
            label="confirm_high_velocity_cg_risk_off",
            flag_column="r7_high_velocity_cg_risk_off_flag",
            landing_shape="candidate_confirm",
            interpretation=(
                "Allow SP-K replacement candidates only when top-trader velocity is high "
                "and CoinGlass ETF/whale context confirms risk-off."
            ),
        ),
        TransitionSpec(
            label="veto_any_mf07_stress_cg_risk_on",
            flag_column="r7_any_mf07_stress_cg_risk_on_flag",
            landing_shape="selected_short_veto",
            interpretation=(
                "Eject one already-selected SP-K short when MF-07 participant stress "
                "coincides with ETF inflow or whale-from-exchange relief."
            ),
        ),
        TransitionSpec(
            label="veto_low_corr_cg_risk_off",
            flag_column="r7_low_corr_cg_risk_off_flag",
            landing_shape="selected_short_veto",
            interpretation=(
                "Eject one already-selected SP-K short when top/global correlation breaks "
                "while ETF/whale context confirms participant stress."
            ),
        ),
    ]


def _read_participant_context(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"participant context sidecar not found: {path}")
    frame = pd.read_csv(path)
    if "date_utc" not in frame.columns:
        raise ValueError(f"participant context sidecar missing date_utc: {path}")
    frame = frame.copy()
    frame["date_utc"] = frame["date_utc"].astype(str)
    keep = [
        "date_utc",
        "total_btc_eth_etf_flow_usd_10d_sum",
        "total_btc_eth_etf_flow_usd_z30",
        "whale_net_to_exchange_usd_z30",
        "whale_transfer_total_usd_z30",
        "exchange_transfer_total_usd_z30",
        "participant_context_sources",
        "participant_context_pit_policies",
    ]
    keep = [column for column in keep if column in frame.columns]
    return frame[keep].drop_duplicates("date_utc").sort_values("date_utc")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    text = series.astype(str).str.strip().str.lower()
    return text.isin({"true", "1", "yes", "y"})


def _merge_participant_context(frame: pd.DataFrame, path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    context = _read_participant_context(path)
    work = frame.copy()
    if "date_utc" not in work.columns:
        work["date_utc"] = pd.to_datetime(
            work["timestamp_ms"],
            unit="ms",
            utc=True,
            errors="coerce",
        ).dt.date.astype(str)
    else:
        work["date_utc"] = work["date_utc"].astype(str)
    return work.merge(context, on="date_utc", how="left"), context


def _add_sidecar_transition_flags(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    etf_flow_10d = _numeric(out, "total_btc_eth_etf_flow_usd_10d_sum")
    etf_flow_z30 = _numeric(out, "total_btc_eth_etf_flow_usd_z30")
    whale_z30 = _numeric(out, "whale_net_to_exchange_usd_z30")
    whale_activity_z30 = _numeric(out, "whale_transfer_total_usd_z30")
    exchange_activity_z30 = _numeric(out, "exchange_transfer_total_usd_z30")

    out["cg_etf_context_available"] = etf_flow_10d.notna()
    out["cg_whale_context_available"] = whale_z30.notna()
    out["cg_exchange_context_available"] = exchange_activity_z30.notna()
    out["cg_etf_outflow_state"] = etf_flow_10d.lt(0.0).fillna(False)
    out["cg_etf_inflow_state"] = etf_flow_10d.gt(0.0).fillna(False)
    out["cg_whale_to_exchange_stress_state"] = whale_z30.ge(1.0).fillna(False)
    out["cg_whale_from_exchange_relief_state"] = whale_z30.le(-1.0).fillna(False)
    out["cg_whale_activity_shock_state"] = whale_activity_z30.ge(1.0).fillna(False)
    out["cg_exchange_activity_quarantine_state"] = exchange_activity_z30.ge(1.0).fillna(False)

    out["cg_risk_off_state"] = out["cg_etf_outflow_state"] | out["cg_whale_to_exchange_stress_state"]
    out["cg_risk_on_state"] = out["cg_etf_inflow_state"] | out["cg_whale_from_exchange_relief_state"]
    out["r7_any_mf07_stress_cg_risk_off_flag"] = (
        _as_bool(out["mf07_any_participant_stress_flag"]) & out["cg_risk_off_state"]
    )
    out["r7_high_gap_cg_risk_off_flag"] = (
        _as_bool(out["mf07_high_abs_tt_retail_gap_flag"]) & out["cg_risk_off_state"]
    )
    out["r7_low_corr_cg_risk_off_flag"] = (
        _as_bool(out["mf07_low_top_global_corr_flag"]) & out["cg_risk_off_state"]
    )
    out["r7_high_velocity_cg_risk_off_flag"] = (
        _as_bool(out["mf07_high_tt_velocity_flag"]) & out["cg_risk_off_state"]
    )
    out["r7_any_mf07_stress_cg_risk_on_flag"] = (
        _as_bool(out["mf07_any_participant_stress_flag"]) & out["cg_risk_on_state"]
    )

    for column in [
        "cg_risk_off_state",
        "cg_risk_on_state",
        "r7_any_mf07_stress_cg_risk_off_flag",
        "r7_high_gap_cg_risk_off_flag",
        "r7_low_corr_cg_risk_off_flag",
        "r7_high_velocity_cg_risk_off_flag",
        "r7_any_mf07_stress_cg_risk_on_flag",
    ]:
        out[f"not_{column}"] = ~_as_bool(out[column])

    one = out.drop_duplicates("timestamp_ms")
    meta = {
        "etf_context_timestamp_coverage": float(one["cg_etf_context_available"].mean()),
        "whale_context_timestamp_coverage": float(one["cg_whale_context_available"].mean()),
        "exchange_context_timestamp_coverage": float(one["cg_exchange_context_available"].mean()),
        "exchange_activity_quarantined": True,
    }
    for column in [
        "cg_etf_outflow_state",
        "cg_etf_inflow_state",
        "cg_whale_to_exchange_stress_state",
        "cg_whale_from_exchange_relief_state",
        "cg_risk_off_state",
        "cg_risk_on_state",
        "r7_any_mf07_stress_cg_risk_off_flag",
        "r7_high_gap_cg_risk_off_flag",
        "r7_low_corr_cg_risk_off_flag",
        "r7_high_velocity_cg_risk_off_flag",
        "r7_any_mf07_stress_cg_risk_on_flag",
    ]:
        meta[column] = {
            "row_fraction": float(_as_bool(out[column]).mean()),
            "timestamp_count": int(out.loc[_as_bool(out[column]), "timestamp_ms"].nunique()),
        }
    return out, meta


def _load_frame(
    *,
    as_of: str,
    target_horizon_bars: int,
    participant_context_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    frame, base_meta = mf07_stage0._load_frame(
        as_of=as_of,
        target_horizon_bars=target_horizon_bars,
    )
    frame, context = _merge_participant_context(frame, participant_context_path)
    frame, sidecar_meta = _add_sidecar_transition_flags(frame)
    frame["parent_score"] = xs_alpha_ontology_v5_score(frame)
    frame["spk_raw_score"] = mf07_stage0._spk_scorer()(frame)
    meta = {
        **base_meta,
        "participant_context_path": str(participant_context_path),
        "participant_context_rows": int(len(context)),
        "participant_context_first_date": str(context["date_utc"].min()) if len(context) else None,
        "participant_context_last_date": str(context["date_utc"].max()) if len(context) else None,
        "sidecar_transition_meta": sidecar_meta,
    }
    return frame, context, meta


def _score_for_spec(frame: pd.DataFrame, spec: TransitionSpec) -> pd.Series:
    if spec.landing_shape == "candidate_confirm":
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            frame,
            base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            candidate_veto_column=f"not_{spec.flag_column}",
        )
    if spec.landing_shape == "candidate_veto":
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            frame,
            base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            candidate_veto_column=spec.flag_column,
        )
    if spec.landing_shape == "selected_short_veto":
        return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
            frame,
            base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
            replacement_pool_size=6,
            signal_threshold=0.0,
            max_replacements_per_timestamp=1,
            selected_short_veto_column=spec.flag_column,
            selected_short_veto_pool_size=10,
            max_selected_short_veto_replacements=1,
        )
    raise ValueError(f"unknown landing shape: {spec.landing_shape}")


def _evaluate_variant(
    frame: pd.DataFrame,
    *,
    spec: TransitionSpec,
    parent_summary: dict[str, Any],
    spk_raw_summary: dict[str, Any],
    target_horizon_bars: int,
) -> dict[str, Any]:
    work = frame.copy()
    work["candidate_score"] = _score_for_spec(work, spec)
    rows = mf07_stage0._short_rows(
        work,
        score_column="candidate_score",
        target_horizon_bars=target_horizon_bars,
    )
    summary = mf07_stage0._summarize_rows(rows, target_horizon_bars=target_horizon_bars)
    return {
        "label": spec.label,
        "flag_column": spec.flag_column,
        "landing_shape": spec.landing_shape,
        "interpretation": spec.interpretation,
        "flag_row_fraction": float(_as_bool(frame[spec.flag_column]).mean()),
        "flag_timestamp_count": int(frame.loc[_as_bool(frame[spec.flag_column]), "timestamp_ms"].nunique()),
        "short_basket_summary": summary,
        "vs_parent": mf07_stage0._compare_short_baskets(
            candidate=summary,
            baseline=parent_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "vs_spk_raw": mf07_stage0._compare_short_baskets(
            candidate=summary,
            baseline=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        ),
        "selection_vs_spk_raw": mf07_stage0._selection_change(
            work,
            baseline_score="spk_raw_score",
            candidate_score="candidate_score",
            target_horizon_bars=target_horizon_bars,
        ),
    }


def _stage0_pass(
    evaluation: dict[str, Any],
    *,
    target_horizon_bars: int,
    min_edge_vs_raw_spk: float,
    min_changed_timestamp_fraction: float,
    min_entered_edge_vs_exited: float,
) -> bool:
    edge = evaluation.get("vs_spk_raw", {}).get(f"short_basket_edge_vs_baseline_{target_horizon_bars}d")
    changed = evaluation.get("selection_vs_spk_raw", {}).get("changed_timestamp_fraction")
    entered_edge = evaluation.get("selection_vs_spk_raw", {}).get(
        f"entered_edge_vs_exited_{target_horizon_bars}d"
    )
    return bool(
        edge is not None
        and float(edge) >= float(min_edge_vs_raw_spk)
        and changed is not None
        and float(changed) >= float(min_changed_timestamp_fraction)
        and entered_edge is not None
        and float(entered_edge) > float(min_entered_edge_vs_exited)
    )


def _compact_stage0(evaluations: dict[str, Any], *, target_horizon_bars: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, payload in evaluations.items():
        out[label] = {
            "landing_shape": payload.get("landing_shape"),
            "flag_timestamp_count": payload.get("flag_timestamp_count"),
            "edge_vs_spk_raw": payload.get("vs_spk_raw", {}).get(
                f"short_basket_edge_vs_baseline_{target_horizon_bars}d"
            ),
            "vs_spk_raw_verdict": payload.get("vs_spk_raw", {}).get("verdict"),
            "changed_timestamp_fraction": payload.get("selection_vs_spk_raw", {}).get(
                "changed_timestamp_fraction"
            ),
            "entered_edge_vs_exited": payload.get("selection_vs_spk_raw", {}).get(
                f"entered_edge_vs_exited_{target_horizon_bars}d"
            ),
            "stage0_pass": payload.get("stage0_pass"),
        }
    return out


def _replace_flag_values(frame: pd.DataFrame, flag_column: str, values: pd.DataFrame) -> pd.DataFrame:
    work = frame.drop(columns=[flag_column, f"not_{flag_column}"], errors="ignore").copy()
    work = work.merge(values[["timestamp_ms", "subject", flag_column]], on=["timestamp_ms", "subject"], how="left")
    work[flag_column] = _as_bool(work[flag_column])
    work[f"not_{flag_column}"] = ~work[flag_column]
    return work


def _delay_flag_by_subject(frame: pd.DataFrame, flag_column: str) -> pd.DataFrame:
    values = frame[["timestamp_ms", "subject", flag_column]].drop_duplicates().sort_values(
        ["subject", "timestamp_ms"]
    )
    values[flag_column] = values.groupby("subject", sort=False)[flag_column].shift(1).fillna(False)
    return _replace_flag_values(frame, flag_column, values)


def _shuffle_flag_by_timestamp(frame: pd.DataFrame, flag_column: str, *, rng: np.random.Generator) -> pd.DataFrame:
    values = frame[["timestamp_ms", "subject", flag_column]].drop_duplicates().sort_values(
        ["timestamp_ms", "subject"]
    )
    by_ts = values[["timestamp_ms"]].drop_duplicates().copy()
    shuffled_ts = rng.permutation(by_ts["timestamp_ms"].to_numpy())
    mapping = dict(zip(by_ts["timestamp_ms"].to_numpy(), shuffled_ts))
    shuffled = values[["timestamp_ms", "subject"]].copy()
    source = values.copy()
    source["timestamp_ms"] = source["timestamp_ms"].map({v: k for k, v in mapping.items()})
    shuffled = shuffled.merge(source[["timestamp_ms", "subject", flag_column]], on=["timestamp_ms", "subject"], how="left")
    shuffled[flag_column] = _as_bool(shuffled[flag_column])
    return _replace_flag_values(frame, flag_column, shuffled)


def _shuffle_returns_within_timestamp(
    frame: pd.DataFrame,
    *,
    target_horizon_bars: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    work = frame.copy()
    columns = ["forward_1d_log_return", f"forward_{target_horizon_bars}d_log_return"]
    columns = [column for column in columns if column in work.columns]
    for _timestamp, group in work.groupby("timestamp_ms", sort=False):
        idx = group.index.to_numpy()
        for column in columns:
            values = work.loc[idx, column].to_numpy(copy=True)
            work.loc[idx, column] = rng.permutation(values)
    return work


def _bucket_consistency(
    frame: pd.DataFrame,
    *,
    spec: TransitionSpec,
    target_horizon_bars: int,
    min_rows: int = 6,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for bucket in sorted(frame["liquidity_bucket"].dropna().astype(str).unique()):
        local = frame[frame["liquidity_bucket"].astype(str).eq(bucket)].copy()
        parent_summary = mf07_stage0._summarize_rows(
            mf07_stage0._short_rows(local, score_column="parent_score", target_horizon_bars=target_horizon_bars),
            target_horizon_bars=target_horizon_bars,
        )
        raw_summary = mf07_stage0._summarize_rows(
            mf07_stage0._short_rows(local, score_column="spk_raw_score", target_horizon_bars=target_horizon_bars),
            target_horizon_bars=target_horizon_bars,
        )
        payload = _evaluate_variant(
            local,
            spec=spec,
            parent_summary=parent_summary,
            spk_raw_summary=raw_summary,
            target_horizon_bars=target_horizon_bars,
        )
        changed_rows = payload["selection_vs_spk_raw"].get("entered", {}).get("row_count") or 0
        edge = payload["vs_spk_raw"].get(f"short_basket_edge_vs_baseline_{target_horizon_bars}d")
        eligible = int(changed_rows) >= int(min_rows)
        rows.append(
            {
                "liquidity_bucket": bucket,
                "eligible": bool(eligible),
                "entered_row_count": int(changed_rows),
                "edge_vs_spk_raw": edge,
                "bucket_passed": bool(eligible and edge is not None and float(edge) > 0.0),
            }
        )
    eligible = [row for row in rows if row["eligible"]]
    return {
        "passed": bool(len(eligible) >= 2 and all(row["bucket_passed"] for row in eligible)),
        "eligible_bucket_count": int(len(eligible)),
        "positive_eligible_bucket_count": int(sum(row["bucket_passed"] for row in eligible)),
        "by_bucket": rows,
    }


def _strict_falsification(
    frame: pd.DataFrame,
    *,
    spec: TransitionSpec,
    parent_summary: dict[str, Any],
    spk_raw_summary: dict[str, Any],
    observed: dict[str, Any],
    target_horizon_bars: int,
    iterations: int,
    seed: int,
    min_edge_vs_raw_spk: float,
) -> dict[str, Any]:
    observed_edge = observed["vs_spk_raw"].get(f"short_basket_edge_vs_baseline_{target_horizon_bars}d")
    if observed_edge is None:
        return {
            "label": spec.label,
            "status": "failed",
            "blocker_codes": ["observed_edge_missing"],
        }
    rng = np.random.default_rng(seed)

    def _edge(payload: dict[str, Any]) -> float | None:
        return payload.get("vs_spk_raw", {}).get(f"short_basket_edge_vs_baseline_{target_horizon_bars}d")

    delayed_payload = _evaluate_variant(
        _delay_flag_by_subject(frame, spec.flag_column),
        spec=spec,
        parent_summary=parent_summary,
        spk_raw_summary=spk_raw_summary,
        target_horizon_bars=target_horizon_bars,
    )
    delayed_edge = _edge(delayed_payload)
    delayed_retention = None if delayed_edge is None or observed_edge <= 0 else float(delayed_edge / observed_edge)
    delayed = {
        "passed": bool(
            delayed_edge is not None and delayed_edge >= min_edge_vs_raw_spk and delayed_retention is not None and delayed_retention >= 0.50
        ),
        "edge_vs_spk_raw": delayed_edge,
        "retention_vs_observed": delayed_retention,
    }

    symbol_rows: list[dict[str, Any]] = []
    for subject in sorted(frame["subject"].astype(str).unique()):
        local = frame[frame["subject"].astype(str).ne(subject)].copy()
        payload = _evaluate_variant(
            local,
            spec=spec,
            parent_summary=mf07_stage0._summarize_rows(
                mf07_stage0._short_rows(local, score_column="parent_score", target_horizon_bars=target_horizon_bars),
                target_horizon_bars=target_horizon_bars,
            ),
            spk_raw_summary=mf07_stage0._summarize_rows(
                mf07_stage0._short_rows(local, score_column="spk_raw_score", target_horizon_bars=target_horizon_bars),
                target_horizon_bars=target_horizon_bars,
            ),
            target_horizon_bars=target_horizon_bars,
        )
        symbol_rows.append({"held_out_subject": subject, "edge_vs_spk_raw": _edge(payload)})
    holdout_edges = [float(row["edge_vs_spk_raw"]) for row in symbol_rows if row["edge_vs_spk_raw"] is not None]
    symbol_holdout = {
        "passed": bool(holdout_edges and min(holdout_edges) > 0.0 and np.mean(np.asarray(holdout_edges) >= min_edge_vs_raw_spk) >= 0.70),
        "min_edge_vs_spk_raw": float(min(holdout_edges)) if holdout_edges else None,
        "positive_fraction_at_min_edge": float(np.mean(np.asarray(holdout_edges) >= min_edge_vs_raw_spk)) if holdout_edges else None,
        "by_subject": symbol_rows,
    }

    time_edges: list[float] = []
    label_edges: list[float] = []
    for _ in range(max(int(iterations), 1)):
        shuffled_flag = _shuffle_flag_by_timestamp(frame, spec.flag_column, rng=rng)
        payload = _evaluate_variant(
            shuffled_flag,
            spec=spec,
            parent_summary=parent_summary,
            spk_raw_summary=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        )
        value = _edge(payload)
        if value is not None:
            time_edges.append(float(value))

        shuffled_returns = _shuffle_returns_within_timestamp(
            frame,
            target_horizon_bars=target_horizon_bars,
            rng=rng,
        )
        payload = _evaluate_variant(
            shuffled_returns,
            spec=spec,
            parent_summary=parent_summary,
            spk_raw_summary=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        )
        value = _edge(payload)
        if value is not None:
            label_edges.append(float(value))

    def _random_result(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"passed": False, "reason": "no_valid_random_edges", "iterations": int(iterations)}
        arr = np.asarray(values, dtype="float64")
        q95 = float(np.quantile(arr, 0.95))
        p_value = float((np.sum(arr >= float(observed_edge)) + 1.0) / (len(arr) + 1.0))
        return {
            "passed": bool(float(observed_edge) > q95 and p_value <= 0.05),
            "iterations": int(len(arr)),
            "random_mean_edge": float(arr.mean()),
            "random_q95_edge": q95,
            "empirical_p_value_random_ge_observed": p_value,
        }

    tests = {
        "delayed_transition": delayed,
        "symbol_holdout": symbol_holdout,
        "liquidity_bucket_consistency": _bucket_consistency(
            frame,
            spec=spec,
            target_horizon_bars=target_horizon_bars,
        ),
        "transition_time_shuffle": _random_result(time_edges),
        "label_shuffle": _random_result(label_edges),
    }
    blocker_codes = [name + "_failed" for name, payload in tests.items() if not bool(payload.get("passed"))]
    return {
        "label": spec.label,
        "status": "cleared" if not blocker_codes else "failed",
        "credible_incremental_edge": not blocker_codes,
        "blocker_codes": blocker_codes,
        "observed": observed,
        "tests": tests,
    }


def _decision(
    *,
    evaluations: dict[str, Any],
    strict_results: dict[str, Any],
) -> dict[str, Any]:
    stage0_survivors = [label for label, payload in evaluations.items() if payload.get("stage0_pass")]
    strict_cleared = [label for label, payload in strict_results.items() if payload.get("status") == "cleared"]
    blockers: list[str] = []
    if not stage0_survivors:
        blockers.append("no_stage0_positive_mf07_etf_onchain_transition")
    for label in stage0_survivors:
        payload = strict_results.get(label)
        if not payload:
            blockers.append(f"{label}_strict_falsification_not_run")
        elif payload.get("status") != "cleared":
            for code in payload.get("blocker_codes", []) or ["strict_falsification_failed"]:
                blockers.append(f"{label}_{code}")
    return {
        "status": "cleared" if strict_cleared else "failed",
        "alpha_rerun_allowed": bool(strict_cleared),
        "manifest_ab_allowed": False,
        "stage0_survivors": stage0_survivors,
        "strict_cleared_variants": strict_cleared,
        "blocker_codes": sorted(set(blockers)),
        "next_action": (
            "Fail closed; keep MF-07 ETF/on-chain transitions out of the parent overlay."
            if not strict_cleared
            else "Design a separate parent-level simulator for cleared MF-07 transitions before any manifest decision."
        ),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def run(args: argparse.Namespace) -> dict[str, Any]:
    target_horizon_bars = int(args.target_horizon_bars)
    frame, _context, input_meta = _load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=target_horizon_bars,
        participant_context_path=Path(args.participant_context_path),
    )
    parent_summary = mf07_stage0._summarize_rows(
        mf07_stage0._short_rows(frame, score_column="parent_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )
    spk_raw_summary = mf07_stage0._summarize_rows(
        mf07_stage0._short_rows(frame, score_column="spk_raw_score", target_horizon_bars=target_horizon_bars),
        target_horizon_bars=target_horizon_bars,
    )

    specs = _pre_registered_specs()
    evaluations = {
        spec.label: _evaluate_variant(
            frame,
            spec=spec,
            parent_summary=parent_summary,
            spk_raw_summary=spk_raw_summary,
            target_horizon_bars=target_horizon_bars,
        )
        for spec in specs
    }
    for label, payload in evaluations.items():
        payload["stage0_pass"] = _stage0_pass(
            payload,
            target_horizon_bars=target_horizon_bars,
            min_edge_vs_raw_spk=float(args.min_edge_vs_raw_spk),
            min_changed_timestamp_fraction=float(args.min_changed_timestamp_fraction),
            min_entered_edge_vs_exited=float(args.min_entered_edge_vs_exited),
        )

    strict_results: dict[str, Any] = {}
    spec_by_label = {spec.label: spec for spec in specs}
    for label, payload in evaluations.items():
        if not payload.get("stage0_pass"):
            strict_results[label] = {
                "label": label,
                "status": "not_run",
                "reason": "stage0_not_positive",
                "blocker_codes": ["stage0_not_positive"],
            }
            continue
        strict_results[label] = _strict_falsification(
            frame,
            spec=spec_by_label[label],
            parent_summary=parent_summary,
            spk_raw_summary=spk_raw_summary,
            observed=payload,
            target_horizon_bars=target_horizon_bars,
            iterations=int(args.iterations),
            seed=int(args.seed),
            min_edge_vs_raw_spk=float(args.min_edge_vs_raw_spk),
        )

    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": _now_utc(),
        "as_of": str(args.as_of),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "target_horizon_bars": target_horizon_bars,
        "parent_short_basket_summary": parent_summary,
        "spk_raw_short_basket_summary": spk_raw_summary,
        "input_meta": input_meta,
        "pre_registration": {
            "scope": (
                "Only PIT-lagged ETF/whale sidecars are allowed as transition confirmations; "
                "exchange transfer activity is reported but quarantined from semantic direction."
            ),
            "admission_rules": {
                "min_edge_vs_raw_spk": float(args.min_edge_vs_raw_spk),
                "min_changed_timestamp_fraction": float(args.min_changed_timestamp_fraction),
                "min_entered_edge_vs_exited": float(args.min_entered_edge_vs_exited),
            },
            "variants": [
                {
                    "label": spec.label,
                    "flag_column": spec.flag_column,
                    "landing_shape": spec.landing_shape,
                    "interpretation": spec.interpretation,
                }
                for spec in specs
            ],
        },
        "stage0_evaluation": evaluations,
        "strict_falsification": strict_results,
        "decision": _decision(evaluations=evaluations, strict_results=strict_results),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run(args)
    output_path = output_dir / "mf07_etf_onchain_transition_falsification.json"
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    compact = {
        "report_path": str(output_path),
        "decision": report["decision"],
        "stage0": _compact_stage0(
            report["stage0_evaluation"],
            target_horizon_bars=int(args.target_horizon_bars),
        ),
    }
    print(json.dumps(compact, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
