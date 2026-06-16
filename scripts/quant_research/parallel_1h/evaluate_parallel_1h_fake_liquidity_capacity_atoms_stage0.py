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

from scripts.quant_research.parallel_1h import evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0 as cap_eval  # noqa: E402
from scripts.quant_research.parallel_1h import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval  # noqa: E402


CONTRACT_VERSION = "parallel_1h_fake_liquidity_capacity_atoms_stage0.v1"
RESEARCH_ID = "fake_liquidity_capacity_haircut_atoms_stage0_1h"
DEFAULT_HORIZONS = trap_eval.DEFAULT_HORIZONS
DEFAULT_SHUFFLE_ITERATIONS = 200
HOUR_MS = trap_eval.HOUR_MS


@dataclass(frozen=True)
class AtomSpec:
    atom_id: str
    flag_column: str
    definition: str
    use_shape: str
    invalidates_if: str


ATOM_SPECS = [
    AtomSpec(
        atom_id="thin_book_vs_flow",
        flag_column="thin_book_vs_flow_atom_flag",
        definition="(CoinGlass bids+asks) / Binance 1h quote volume <= shifted rolling q20 by symbol or <= 5%.",
        use_shape="reduce max participation / prefer post-only or no market order.",
        invalidates_if="flagged rows are not worse shorts, tail risk is not higher, or bucket/holdout/shuffle fail.",
    ),
    AtomSpec(
        atom_id="taker_churn_without_direction",
        flag_column="taker_churn_without_direction_atom_flag",
        definition=(
            "CoinGlass taker buy+sell volume is high versus Binance quote volume while absolute taker imbalance "
            "is low; intended to detect churn rather than directional exit."
        ),
        use_shape="capacity haircut / avoid assuming volume is executable liquidity.",
        invalidates_if="effect is just timestamp structure, or symbol holdout does not remain directionally consistent.",
    ),
    AtomSpec(
        atom_id="volume_oi_brushing",
        flag_column="volume_oi_brushing_atom_flag",
        definition="24h Binance quote volume / OI value >= shifted rolling q95 and >= 2.0.",
        use_shape="capacity haircut / venue-concentration suspect until provider concordance exists.",
        invalidates_if="volume/OI extreme is not linked to worse shorts or adverse squeeze tails.",
    ),
    AtomSpec(
        atom_id="high_slippage_proxy",
        flag_column="high_slippage_proxy_atom_flag",
        definition="abs(1h return) / sqrt(hourly quote volume in USD millions) >= shifted rolling q90.",
        use_shape="slippage stress / reduce order size or reject market order.",
        invalidates_if="slippage proxy is not associated with worse forward short outcome after falsification.",
    ),
    AtomSpec(
        atom_id="kill_switch_score_gte4",
        flag_column="kill_switch_score_gte4_atom_flag",
        definition=(
            "sum(volume_oi_brushing, thin_capacity, thin_book_vs_flow, thin_book_vs_oi, "
            "high_slippage_proxy, taker_churn_without_direction, liquidation_churn) >= 4."
        ),
        use_shape="kill-switch candidate / no new short and no market order.",
        invalidates_if="the concentrated risk score does not survive all falsification gates.",
    ),
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0 atom decomposition for the 1h fake-liquidity capacity-haircut lane. "
            "Research diagnostic only; does not touch h10d promotion state."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce").replace(0.0, np.nan)
    return num / den


def _rolling_quantile_by_symbol(grouped: Any, column: str, q: float) -> pd.Series:
    return grouped[column].transform(lambda s: trap_eval._rolling_quantile(s, q))


def _add_atom_state(frame: pd.DataFrame) -> pd.DataFrame:
    out = cap_eval._add_fake_liquidity_capacity_state(frame)
    out = out.sort_values(["subject", "open_time_ms"]).copy()
    grouped = out.groupby("subject", group_keys=False, sort=False)

    volume = pd.to_numeric(out["perp_quote_volume_usd"], errors="coerce")
    oi = pd.to_numeric(out["open_interest_value"], errors="coerce")
    orderbook_depth = pd.to_numeric(out["orderbook_depth_usd"], errors="coerce")
    taker_total = pd.to_numeric(out["taker_total_volume_usd"], errors="coerce")
    abs_taker_imbalance = pd.to_numeric(out["abs_taker_imbalance"], errors="coerce")
    liquidation_total = pd.to_numeric(out["liquidation_total_usd"], errors="coerce")
    slippage = pd.to_numeric(out["slippage_or_capacity_proxy"], errors="coerce")

    out["book_depth_to_oi"] = _safe_divide(orderbook_depth, oi)
    out["taker_total_to_binance_volume_1h"] = _safe_divide(taker_total, volume)
    out["liquidation_to_hourly_volume"] = _safe_divide(liquidation_total, volume)

    out["book_depth_to_oi_q20"] = _rolling_quantile_by_symbol(grouped, "book_depth_to_oi", 0.20)
    out["taker_total_to_binance_volume_q90"] = _rolling_quantile_by_symbol(
        grouped, "taker_total_to_binance_volume_1h", 0.90
    )
    out["abs_taker_imbalance_q25"] = _rolling_quantile_by_symbol(grouped, "abs_taker_imbalance", 0.25)
    out["liquidation_to_hourly_volume_q90"] = _rolling_quantile_by_symbol(
        grouped, "liquidation_to_hourly_volume", 0.90
    )

    out["thin_book_vs_flow_atom_flag"] = (
        pd.to_numeric(out["book_depth_to_volume_1h"], errors="coerce").le(
            pd.to_numeric(out["book_depth_to_volume_q20"], errors="coerce")
        )
        | pd.to_numeric(out["book_depth_to_volume_1h"], errors="coerce").le(0.05)
    ).fillna(False)
    out["taker_churn_without_direction_atom_flag"] = (
        (
            pd.to_numeric(out["taker_total_to_binance_volume_1h"], errors="coerce").ge(
                pd.to_numeric(out["taker_total_to_binance_volume_q90"], errors="coerce")
            )
            | pd.to_numeric(out["taker_total_to_binance_volume_1h"], errors="coerce").ge(1.20)
        )
        & (
            abs_taker_imbalance.le(pd.to_numeric(out["abs_taker_imbalance_q25"], errors="coerce"))
            | abs_taker_imbalance.le(0.10)
        )
    ).fillna(False)
    out["volume_oi_brushing_atom_flag"] = (
        pd.to_numeric(out["volume_oi_ratio_24h"], errors="coerce").ge(
            pd.to_numeric(out["volume_oi_ratio_24h_q95"], errors="coerce")
        )
        & pd.to_numeric(out["volume_oi_ratio_24h"], errors="coerce").ge(2.0)
    ).fillna(False)
    out["high_slippage_proxy_atom_flag"] = slippage.ge(
        pd.to_numeric(out["slippage_proxy_q90"], errors="coerce")
    ).fillna(False)
    out["thin_book_vs_oi_atom_flag"] = (
        pd.to_numeric(out["book_depth_to_oi"], errors="coerce").le(
            pd.to_numeric(out["book_depth_to_oi_q20"], errors="coerce")
        )
        | pd.to_numeric(out["book_depth_to_oi"], errors="coerce").le(0.02)
    ).fillna(False)
    out["liquidation_churn_atom_flag"] = (
        pd.to_numeric(out["liquidation_to_hourly_volume"], errors="coerce").ge(
            pd.to_numeric(out["liquidation_to_hourly_volume_q90"], errors="coerce")
        )
        & pd.to_numeric(out["liquidation_to_hourly_volume"], errors="coerce").gt(0.0)
    ).fillna(False)

    score_columns = [
        "volume_oi_brushing_atom_flag",
        "thin_capacity_flag",
        "thin_book_vs_flow_atom_flag",
        "thin_book_vs_oi_atom_flag",
        "high_slippage_proxy_atom_flag",
        "taker_churn_without_direction_atom_flag",
        "liquidation_churn_atom_flag",
    ]
    out["fake_liquidity_atom_score"] = out[score_columns].fillna(False).astype(int).sum(axis=1)
    out["kill_switch_score_gte4_atom_flag"] = out["fake_liquidity_atom_score"].ge(4).fillna(False)
    return out


def _event_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)].copy()


def _cohort_effect(events: pd.DataFrame, *, flag_column: str, horizon: int = 24) -> dict[str, Any]:
    if events.empty or flag_column not in events.columns:
        return {"status": "insufficient", "flagged_count": 0, "control_count": 0}
    flag = events[flag_column].fillna(False).astype(bool)
    forward = pd.to_numeric(events[f"forward_{horizon}h_log_return"], errors="coerce")
    short_ret = -forward
    capacity = pd.to_numeric(events["capacity_proxy_usd"], errors="coerce")
    slippage = pd.to_numeric(events["slippage_or_capacity_proxy"], errors="coerce")
    funding = pd.to_numeric(events[f"funding_h{horizon}h_short_pnl_estimate"], errors="coerce")
    valid = forward.notna()
    flagged = valid & flag
    control = valid & ~flag
    if not flagged.any() or not control.any():
        return {
            "status": "insufficient",
            "flagged_count": int(flagged.sum()),
            "control_count": int(control.sum()),
        }
    flagged_forward = forward.loc[flagged]
    control_forward = forward.loc[control]
    flagged_short = short_ret.loc[flagged]
    control_short = short_ret.loc[control]
    return {
        "status": "ok",
        "flagged_count": int(flagged.sum()),
        "control_count": int(control.sum()),
        "flagged_short_return_mean": float(flagged_short.mean()),
        "control_short_return_mean": float(control_short.mean()),
        "short_return_delta": float(flagged_short.mean() - control_short.mean()),
        "flagged_adverse_squeeze_gt_5pct_fraction": float((flagged_forward > 0.05).mean()),
        "control_adverse_squeeze_gt_5pct_fraction": float((control_forward > 0.05).mean()),
        "adverse_squeeze_gt_5pct_delta": float(
            (flagged_forward > 0.05).mean() - (control_forward > 0.05).mean()
        ),
        "flagged_adverse_squeeze_gt_10pct_fraction": float((flagged_forward > 0.10).mean()),
        "control_adverse_squeeze_gt_10pct_fraction": float((control_forward > 0.10).mean()),
        "flagged_capacity_proxy_usd_mean": float(capacity.loc[flagged].mean()),
        "control_capacity_proxy_usd_mean": float(capacity.loc[control].mean()),
        "capacity_proxy_usd_delta": float(capacity.loc[flagged].mean() - capacity.loc[control].mean()),
        "flagged_slippage_proxy_mean": float(slippage.loc[flagged].mean()),
        "control_slippage_proxy_mean": float(slippage.loc[control].mean()),
        "slippage_proxy_delta": float(slippage.loc[flagged].mean() - slippage.loc[control].mean()),
        "flagged_funding_horizon_mean": float(funding.loc[flagged].mean()),
        "control_funding_horizon_mean": float(funding.loc[control].mean()),
        "pass_direction": "short_return_delta<0 and adverse_squeeze_gt_5pct_delta>0",
    }


def _mask_summary(events: pd.DataFrame, mask: pd.Series, horizons: tuple[int, ...]) -> dict[str, Any]:
    subset = events.loc[mask].copy()
    if subset.empty:
        return {"row_count": 0}
    payload: dict[str, Any] = {
        "row_count": int(len(subset)),
        "symbol_count": int(subset["subject"].astype(str).nunique()),
        "timestamp_count": int(subset["open_time_ms"].nunique()),
        "start_utc": str(subset["timestamp_utc_text"].min()),
        "end_utc": str(subset["timestamp_utc_text"].max()),
    }
    for horizon in horizons:
        forward = pd.to_numeric(subset[f"forward_{horizon}h_log_return"], errors="coerce").dropna()
        short_ret = -forward
        payload[f"h{horizon}"] = {
            "observation_count": int(len(forward)),
            "mean_long_return": float(forward.mean()) if len(forward) else None,
            "median_long_return": float(forward.median()) if len(forward) else None,
            "mean_short_return": float(short_ret.mean()) if len(short_ret) else None,
            "median_short_return": float(short_ret.median()) if len(short_ret) else None,
            "short_win_fraction": float((short_ret > 0.0).mean()) if len(short_ret) else None,
            "adverse_squeeze_gt_5pct_fraction": float((forward > 0.05).mean()) if len(forward) else None,
            "adverse_squeeze_gt_10pct_fraction": float((forward > 0.10).mean()) if len(forward) else None,
        }
    return payload


def _forward_return_table_for_atom(events: pd.DataFrame, spec: AtomSpec, horizons: tuple[int, ...]) -> dict[str, Any]:
    flag = events[spec.flag_column].fillna(False).astype(bool)
    return {
        "flagged_rows": _mask_summary(events, flag, horizons),
        "control_rows": _mask_summary(events, ~flag, horizons),
        "all_post_pump_short_candidates": _mask_summary(events, pd.Series(True, index=events.index), horizons),
    }


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    valid = values.notna() & weights.notna() & weights.gt(0.0)
    if not valid.any():
        return None
    return float(np.average(values.loc[valid], weights=weights.loc[valid]))


def _weighted_tail(forward: pd.Series, weights: pd.Series, threshold: float) -> float | None:
    valid = forward.notna() & weights.notna() & weights.gt(0.0)
    if not valid.any():
        return None
    return float(np.average((forward.loc[valid] > threshold).astype(float), weights=weights.loc[valid]))


def _policy_effect(events: pd.DataFrame, spec: AtomSpec, *, horizon: int = 24) -> dict[str, Any]:
    flag = events[spec.flag_column].fillna(False).astype(bool)
    forward = pd.to_numeric(events[f"forward_{horizon}h_log_return"], errors="coerce")
    short_ret = -forward
    baseline = pd.Series(1.0, index=events.index)
    half_flagged = pd.Series(np.where(flag, 0.5, 1.0), index=events.index)
    drop_flagged = pd.Series(np.where(flag, 0.0, 1.0), index=events.index)
    base_short = _weighted_mean(short_ret, baseline)
    half_short = _weighted_mean(short_ret, half_flagged)
    drop_short = _weighted_mean(short_ret, drop_flagged)
    base_tail = _weighted_tail(forward, baseline, 0.05)
    half_tail = _weighted_tail(forward, half_flagged, 0.05)
    drop_tail = _weighted_tail(forward, drop_flagged, 0.05)
    return {
        "status": "ok" if base_short is not None else "insufficient",
        "horizon": f"h{horizon}",
        "baseline_gross_exposure": float(baseline.sum()),
        "half_flagged_gross_exposure": float(half_flagged.sum()),
        "drop_flagged_gross_exposure": float(drop_flagged.sum()),
        "half_flagged_exposure_retained_fraction": float(half_flagged.sum() / baseline.sum())
        if baseline.sum()
        else None,
        "drop_flagged_exposure_retained_fraction": float(drop_flagged.sum() / baseline.sum())
        if baseline.sum()
        else None,
        "baseline_weighted_short_return_mean": base_short,
        "half_flagged_weighted_short_return_mean": half_short,
        "drop_flagged_weighted_short_return_mean": drop_short,
        "half_flagged_short_return_delta_vs_baseline": (
            float(half_short - base_short) if half_short is not None and base_short is not None else None
        ),
        "drop_flagged_short_return_delta_vs_baseline": (
            float(drop_short - base_short) if drop_short is not None and base_short is not None else None
        ),
        "baseline_weighted_adverse_gt_5pct_fraction": base_tail,
        "half_flagged_weighted_adverse_gt_5pct_fraction": half_tail,
        "drop_flagged_weighted_adverse_gt_5pct_fraction": drop_tail,
    }


def _shuffle_flags_within_timestamp(events: pd.DataFrame, flag_column: str, rng: np.random.Generator) -> pd.Series:
    shuffled = pd.Series(False, index=events.index)
    for _, idx in events.groupby("open_time_ms").groups.items():
        values = events.loc[idx, flag_column].to_numpy(dtype=bool)
        shuffled.loc[idx] = rng.permutation(values)
    return shuffled.astype(bool)


def _time_shift_flags_by_symbol(events: pd.DataFrame, flag_column: str, rng: np.random.Generator) -> pd.Series:
    shifted = pd.Series(False, index=events.index)
    for _, idx in events.sort_values(["subject", "open_time_ms"]).groupby("subject").groups.items():
        ordered_idx = list(idx)
        values = events.loc[ordered_idx, flag_column].to_numpy(dtype=bool)
        if len(values) < 2:
            shifted.loc[ordered_idx] = values
            continue
        offset = int(rng.integers(1, len(values)))
        shifted.loc[ordered_idx] = np.roll(values, offset)
    return shifted.astype(bool)


def _shuffle_summary(
    short_deltas: np.ndarray,
    adverse_deltas: np.ndarray,
    observed_short_delta: float,
    observed_adverse_delta: float,
    iterations: int,
) -> dict[str, Any]:
    if short_deltas.size == 0 or adverse_deltas.size == 0:
        return {"passed": False, "iterations": int(iterations), "valid_iterations": 0}
    short_lower = float((short_deltas <= observed_short_delta).mean())
    adverse_upper = float((adverse_deltas <= observed_adverse_delta).mean())
    return {
        "passed": bool(
            observed_short_delta < 0.0
            and short_lower <= 0.10
            and observed_adverse_delta > 0.0
            and adverse_upper >= 0.90
        ),
        "iterations": int(iterations),
        "valid_iterations": int(min(short_deltas.size, adverse_deltas.size)),
        "observed_short_return_delta": float(observed_short_delta),
        "observed_adverse_squeeze_gt_5pct_delta": float(observed_adverse_delta),
        "shuffle_short_delta_mean": float(np.nanmean(short_deltas)),
        "shuffle_short_delta_p05": float(np.nanpercentile(short_deltas, 5)),
        "shuffle_short_delta_p50": float(np.nanpercentile(short_deltas, 50)),
        "shuffle_adverse_delta_mean": float(np.nanmean(adverse_deltas)),
        "shuffle_adverse_delta_p50": float(np.nanpercentile(adverse_deltas, 50)),
        "shuffle_adverse_delta_p95": float(np.nanpercentile(adverse_deltas, 95)),
        "observed_short_lower_tail_quantile": short_lower,
        "observed_adverse_upper_tail_quantile": adverse_upper,
        "pass_rule": "short delta bottom 10pct and adverse-tail delta top 10pct of shuffled deltas",
    }


def _shuffle_tests_for_atom(
    events: pd.DataFrame,
    spec: AtomSpec,
    *,
    iterations: int,
    horizon: int = 24,
) -> dict[str, Any]:
    observed = _cohort_effect(events, flag_column=spec.flag_column, horizon=horizon)
    observed_short = observed.get("short_return_delta")
    observed_adverse = observed.get("adverse_squeeze_gt_5pct_delta")
    if observed_short is None or observed_adverse is None:
        return {"status": "insufficient", "observed": observed, "tests": {}, "passed": False}
    rng = np.random.default_rng(abs(hash((spec.atom_id, 20260510))) % (2**32))
    tests: dict[str, Any] = {}

    for test_name, flag_builder in {
        "same_timestamp_feature_shuffle": lambda local: _shuffle_flags_within_timestamp(
            local, spec.flag_column, rng
        ),
        "symbol_time_shift_shuffle": lambda local: _time_shift_flags_by_symbol(local, spec.flag_column, rng),
    }.items():
        short_deltas: list[float] = []
        adverse_deltas: list[float] = []
        for _ in range(iterations):
            local = events.copy()
            local["_test_flag"] = flag_builder(local)
            effect = _cohort_effect(local, flag_column="_test_flag", horizon=horizon)
            if effect.get("short_return_delta") is not None:
                short_deltas.append(float(effect["short_return_delta"]))
                adverse_deltas.append(float(effect["adverse_squeeze_gt_5pct_delta"]))
        tests[test_name] = _shuffle_summary(
            np.asarray(short_deltas, dtype="float64"),
            np.asarray(adverse_deltas, dtype="float64"),
            float(observed_short),
            float(observed_adverse),
            iterations,
        )

    label_short: list[float] = []
    label_adverse: list[float] = []
    base_forward = events[f"forward_{horizon}h_log_return"].copy()
    for _ in range(iterations):
        local = events.copy()
        shuffled_forward = base_forward.copy()
        for _, idx in local.groupby("open_time_ms").groups.items():
            values = shuffled_forward.loc[idx].to_numpy(dtype="float64")
            shuffled_forward.loc[idx] = rng.permutation(values)
        local[f"forward_{horizon}h_log_return"] = shuffled_forward
        local[f"forward_{horizon}h_short_return"] = -shuffled_forward
        effect = _cohort_effect(local, flag_column=spec.flag_column, horizon=horizon)
        if effect.get("short_return_delta") is not None:
            label_short.append(float(effect["short_return_delta"]))
            label_adverse.append(float(effect["adverse_squeeze_gt_5pct_delta"]))
    tests["same_timestamp_label_shuffle"] = _shuffle_summary(
        np.asarray(label_short, dtype="float64"),
        np.asarray(label_adverse, dtype="float64"),
        float(observed_short),
        float(observed_adverse),
        iterations,
    )

    return {
        "status": "ok",
        "horizon": f"h{horizon}",
        "observed": observed,
        "tests": tests,
        "passed": bool(all(test.get("passed") for test in tests.values())),
    }


def _effect_from_arrays(flag: np.ndarray, forward: np.ndarray) -> tuple[float | None, float | None]:
    valid = np.isfinite(forward)
    flagged = valid & flag
    control = valid & ~flag
    if not flagged.any() or not control.any():
        return None, None
    flagged_forward = forward[flagged]
    control_forward = forward[control]
    short_delta = float((-flagged_forward).mean() - (-control_forward).mean())
    adverse_delta = float((flagged_forward > 0.05).mean() - (control_forward > 0.05).mean())
    return short_delta, adverse_delta


def _shuffle_tests_for_all_atoms(
    events: pd.DataFrame,
    specs: list[AtomSpec],
    *,
    iterations: int,
    horizon: int = 24,
) -> dict[str, Any]:
    if events.empty:
        return {
            spec.atom_id: {"status": "insufficient", "observed": {}, "tests": {}, "passed": False}
            for spec in specs
        }

    local_events = events.reset_index(drop=True).copy()
    forward = pd.to_numeric(local_events[f"forward_{horizon}h_log_return"], errors="coerce").to_numpy(
        dtype="float64"
    )
    flag_matrix = np.column_stack(
        [local_events[spec.flag_column].fillna(False).astype(bool).to_numpy() for spec in specs]
    )
    timestamp_groups = [
        np.asarray(idx, dtype="int64")
        for idx in local_events.groupby("open_time_ms", sort=False).indices.values()
        if len(idx) > 1
    ]
    ordered_events = local_events.sort_values(["subject", "open_time_ms"])
    symbol_groups = [
        np.asarray(list(idx), dtype="int64")
        for idx in ordered_events.groupby("subject", sort=False).groups.values()
        if len(idx) > 1
    ]
    rng = np.random.default_rng(20260510)

    observed = {
        spec.atom_id: _cohort_effect(local_events, flag_column=spec.flag_column, horizon=horizon)
        for spec in specs
    }
    buckets: dict[str, dict[str, list[float]]] = {
        spec.atom_id: {
            "feature_short": [],
            "feature_adverse": [],
            "shift_short": [],
            "shift_adverse": [],
            "label_short": [],
            "label_adverse": [],
        }
        for spec in specs
    }

    for _ in range(iterations):
        shuffled_flags = flag_matrix.copy()
        for idx in timestamp_groups:
            for col in range(shuffled_flags.shape[1]):
                shuffled_flags[idx, col] = rng.permutation(shuffled_flags[idx, col])
        for col, spec in enumerate(specs):
            short_delta, adverse_delta = _effect_from_arrays(shuffled_flags[:, col], forward)
            if short_delta is not None and adverse_delta is not None:
                buckets[spec.atom_id]["feature_short"].append(short_delta)
                buckets[spec.atom_id]["feature_adverse"].append(adverse_delta)

        shifted_flags = flag_matrix.copy()
        for idx in symbol_groups:
            for col in range(shifted_flags.shape[1]):
                offset = int(rng.integers(1, len(idx)))
                shifted_flags[idx, col] = np.roll(shifted_flags[idx, col], offset)
        for col, spec in enumerate(specs):
            short_delta, adverse_delta = _effect_from_arrays(shifted_flags[:, col], forward)
            if short_delta is not None and adverse_delta is not None:
                buckets[spec.atom_id]["shift_short"].append(short_delta)
                buckets[spec.atom_id]["shift_adverse"].append(adverse_delta)

        shuffled_forward = forward.copy()
        for idx in timestamp_groups:
            shuffled_forward[idx] = rng.permutation(shuffled_forward[idx])
        for col, spec in enumerate(specs):
            short_delta, adverse_delta = _effect_from_arrays(flag_matrix[:, col], shuffled_forward)
            if short_delta is not None and adverse_delta is not None:
                buckets[spec.atom_id]["label_short"].append(short_delta)
                buckets[spec.atom_id]["label_adverse"].append(adverse_delta)

    out: dict[str, Any] = {}
    for spec in specs:
        observed_short = observed[spec.atom_id].get("short_return_delta")
        observed_adverse = observed[spec.atom_id].get("adverse_squeeze_gt_5pct_delta")
        if observed_short is None or observed_adverse is None:
            out[spec.atom_id] = {
                "status": "insufficient",
                "horizon": f"h{horizon}",
                "observed": observed[spec.atom_id],
                "tests": {},
                "passed": False,
            }
            continue
        bucket = buckets[spec.atom_id]
        tests = {
            "same_timestamp_feature_shuffle": _shuffle_summary(
                np.asarray(bucket["feature_short"], dtype="float64"),
                np.asarray(bucket["feature_adverse"], dtype="float64"),
                float(observed_short),
                float(observed_adverse),
                iterations,
            ),
            "symbol_time_shift_shuffle": _shuffle_summary(
                np.asarray(bucket["shift_short"], dtype="float64"),
                np.asarray(bucket["shift_adverse"], dtype="float64"),
                float(observed_short),
                float(observed_adverse),
                iterations,
            ),
            "same_timestamp_label_shuffle": _shuffle_summary(
                np.asarray(bucket["label_short"], dtype="float64"),
                np.asarray(bucket["label_adverse"], dtype="float64"),
                float(observed_short),
                float(observed_adverse),
                iterations,
            ),
        }
        out[spec.atom_id] = {
            "status": "ok",
            "horizon": f"h{horizon}",
            "observed": observed[spec.atom_id],
            "tests": tests,
            "passed": bool(all(test.get("passed") for test in tests.values())),
        }
    return out


def _symbol_holdout_for_atom(events: pd.DataFrame, spec: AtomSpec, *, horizon: int = 24) -> dict[str, Any]:
    observed = _cohort_effect(events, flag_column=spec.flag_column, horizon=horizon)
    rows: dict[str, Any] = {}
    for subject, group in events.groupby("subject"):
        local = _cohort_effect(group, flag_column=spec.flag_column, horizon=horizon)
        if int(local.get("flagged_count") or 0) >= 10 and int(local.get("control_count") or 0) >= 10:
            rows[str(subject)] = local
    eligible = [row for row in rows.values() if row.get("short_return_delta") is not None]
    consistent = [
        row
        for row in eligible
        if float(row.get("short_return_delta") or 0.0) < 0.0
        and float(row.get("adverse_squeeze_gt_5pct_delta") or 0.0) > 0.0
    ]
    flagged_counts = events.loc[events[spec.flag_column].fillna(False).astype(bool)].groupby("subject").size()
    total_flagged = int(flagged_counts.sum())
    top_share = float(flagged_counts.max() / total_flagged) if total_flagged else 1.0
    leave_one: dict[str, Any] = {}
    for subject in sorted(events["subject"].astype(str).unique()):
        local = events.loc[events["subject"].astype(str).ne(subject)]
        leave_one[subject] = _cohort_effect(local, flag_column=spec.flag_column, horizon=horizon)
    leave_one_effects = [row for row in leave_one.values() if row.get("short_return_delta") is not None]
    leave_one_pass = bool(
        leave_one_effects
        and all(
            float(row["short_return_delta"]) < 0.0
            and float(row.get("adverse_squeeze_gt_5pct_delta") or 0.0) > 0.0
            for row in leave_one_effects
        )
    )
    fraction = float(len(consistent) / len(eligible)) if eligible else 0.0
    return {
        "passed": bool(len(eligible) >= 3 and fraction >= 0.60 and top_share <= 0.30 and leave_one_pass),
        "observed": observed,
        "eligible_symbol_count": int(len(eligible)),
        "directionally_consistent_symbol_count": int(len(consistent)),
        "directionally_consistent_symbol_fraction": fraction,
        "top_flagged_symbol_event_share": top_share,
        "leave_one_symbol_out": leave_one,
        "by_symbol": rows,
    }


def _liquidity_bucket_consistency_for_atom(events: pd.DataFrame, spec: AtomSpec, *, horizon: int = 24) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for bucket, group in events.groupby("liquidity_bucket"):
        rows[str(bucket)] = _cohort_effect(group, flag_column=spec.flag_column, horizon=horizon)
    eligible = [
        row
        for row in rows.values()
        if int(row.get("flagged_count") or 0) >= 50
        and int(row.get("control_count") or 0) >= 50
        and row.get("short_return_delta") is not None
    ]
    expected = [
        row
        for row in eligible
        if float(row["short_return_delta"]) < 0.0
        and float(row.get("adverse_squeeze_gt_5pct_delta") or 0.0) > 0.0
    ]
    return {
        "passed": bool(len(eligible) >= 2 and len(expected) == len(eligible)),
        "eligible_bucket_count": int(len(eligible)),
        "expected_direction_bucket_count": int(len(expected)),
        "by_bucket": rows,
    }


def _cohort_after_delay(
    frame: pd.DataFrame,
    *,
    mask: pd.Series,
    delay_h: int,
    columns: list[str],
) -> pd.DataFrame:
    base = frame.loc[mask, ["subject", "open_time_ms", "liquidity_bucket"]].copy()
    if base.empty:
        return pd.DataFrame()
    base["entry_open_time_ms"] = base["open_time_ms"] + int(delay_h) * HOUR_MS
    lookup = frame[["subject", "open_time_ms", *columns]].copy()
    lookup = lookup.rename(columns={"open_time_ms": "entry_open_time_ms"})
    return base.merge(lookup, on=["subject", "entry_open_time_ms"], how="inner")


def _delay_robustness_for_atom(frame: pd.DataFrame, spec: AtomSpec, *, horizon: int = 24) -> dict[str, Any]:
    candidates = frame["post_pump_short_candidate_flag"].fillna(False).astype(bool)
    flagged = frame[spec.flag_column].fillna(False).astype(bool)
    columns = [
        f"forward_{horizon}h_log_return",
        f"forward_{horizon}h_short_return",
        f"funding_h{horizon}h_short_pnl_estimate",
        "capacity_proxy_usd",
        "slippage_or_capacity_proxy",
    ]
    scenarios: dict[str, Any] = {}
    for delay in (0, 1, 6, 24):
        flagged_delayed = _cohort_after_delay(
            frame, mask=candidates & flagged, delay_h=delay, columns=columns
        )
        control_delayed = _cohort_after_delay(
            frame, mask=candidates & ~flagged, delay_h=delay, columns=columns
        )
        if flagged_delayed.empty or control_delayed.empty:
            scenarios[f"delay_{delay}h"] = {
                "status": "insufficient",
                "delay_h": int(delay),
                "flagged_count": int(len(flagged_delayed)),
                "control_count": int(len(control_delayed)),
            }
            continue
        delayed = pd.concat(
            [
                flagged_delayed.assign(_delay_flag=True),
                control_delayed.assign(_delay_flag=False),
            ],
            ignore_index=True,
        )
        effect = _cohort_effect(delayed, flag_column="_delay_flag", horizon=horizon)
        effect["delay_h"] = int(delay)
        scenarios[f"delay_{delay}h"] = effect
    passed = bool(
        scenarios
        and all(
            row.get("status") == "ok"
            and float(row.get("short_return_delta") or 0.0) < 0.0
            and float(row.get("adverse_squeeze_gt_5pct_delta") or 0.0) > 0.0
            for row in scenarios.values()
        )
    )
    return {
        "passed": passed,
        "scenarios": scenarios,
        "pass_rule": "delay_0h/1h/6h/24h all keep flagged rows worse with higher adverse squeeze tail",
    }


def _funding_drag_summary_for_atom(events: pd.DataFrame, spec: AtomSpec, horizons: tuple[int, ...]) -> dict[str, Any]:
    flag = events[spec.flag_column].fillna(False).astype(bool)
    out: dict[str, Any] = {}
    for cohort_name, mask in {"flagged_rows": flag, "control_rows": ~flag}.items():
        subset = events.loc[mask].copy()
        summary: dict[str, Any] = {"row_count": int(len(subset))}
        for horizon in horizons:
            values = pd.to_numeric(subset.get(f"funding_h{horizon}h_short_pnl_estimate"), errors="coerce").dropna()
            summary[f"h{horizon}"] = {
                "observation_count": int(len(values)),
                "mean_short_funding_pnl_estimate": float(values.mean()) if len(values) else None,
                "negative_funding_drag_fraction": float((values < 0.0).mean()) if len(values) else None,
            }
        out[cohort_name] = summary
    out["provider_semantics_note"] = (
        "Uses local binance_derivatives funding_rate as stored; cadence and units require provider-semantics audit."
    )
    return out


def _capacity_summary_for_atom(events: pd.DataFrame, spec: AtomSpec) -> dict[str, Any]:
    flag = events[spec.flag_column].fillna(False).astype(bool)
    out: dict[str, Any] = {}
    for cohort_name, mask in {"flagged_rows": flag, "control_rows": ~flag}.items():
        subset = events.loc[mask].copy()
        capacity = pd.to_numeric(subset.get("capacity_proxy_usd"), errors="coerce").dropna()
        slippage = pd.to_numeric(subset.get("slippage_or_capacity_proxy"), errors="coerce").dropna()
        vol_oi = pd.to_numeric(subset.get("volume_oi_ratio_24h"), errors="coerce").dropna()
        book_flow = pd.to_numeric(subset.get("book_depth_to_volume_1h"), errors="coerce").dropna()
        taker_churn = pd.to_numeric(subset.get("taker_total_to_binance_volume_1h"), errors="coerce").dropna()
        out[cohort_name] = {
            "row_count": int(len(subset)),
            "capacity_proxy_usd_mean": float(capacity.mean()) if len(capacity) else None,
            "capacity_proxy_usd_p10": float(capacity.quantile(0.10)) if len(capacity) else None,
            "capacity_proxy_usd_median": float(capacity.median()) if len(capacity) else None,
            "slippage_proxy_mean": float(slippage.mean()) if len(slippage) else None,
            "slippage_proxy_p90": float(slippage.quantile(0.90)) if len(slippage) else None,
            "volume_oi_ratio_24h_mean": float(vol_oi.mean()) if len(vol_oi) else None,
            "book_depth_to_volume_mean": float(book_flow.mean()) if len(book_flow) else None,
            "taker_total_to_binance_volume_mean": float(taker_churn.mean()) if len(taker_churn) else None,
        }
    out["capacity_rule"] = "capacity_proxy_usd = min(0.5% of current 1h quote volume, 2% of OI value)."
    out["provider_concordance_note"] = (
        "CoinGlass taker/orderbook coverage is not provider concordance; venue concentration remains unavailable."
    )
    return out


def _event_count_by_symbol_for_atom(events: pd.DataFrame, spec: AtomSpec) -> dict[str, int]:
    subset = events.loc[events[spec.flag_column].fillna(False).astype(bool)]
    counts = subset.groupby("subject").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _event_count_by_liquidity_bucket_for_atom(events: pd.DataFrame, spec: AtomSpec) -> dict[str, int]:
    subset = events.loc[events[spec.flag_column].fillna(False).astype(bool)]
    counts = subset.groupby("liquidity_bucket").size().sort_values(ascending=False)
    return {str(key): int(value) for key, value in counts.items()}


def _decision_for_atom(
    events: pd.DataFrame,
    spec: AtomSpec,
    *,
    primary_effect: dict[str, Any],
    policy_effect: dict[str, Any],
    shuffle_tests: dict[str, Any],
    symbol_holdout: dict[str, Any],
    liquidity_bucket_consistency: dict[str, Any],
    delay_robustness: dict[str, Any],
) -> dict[str, Any]:
    flag = events[spec.flag_column].fillna(False).astype(bool) if not events.empty else pd.Series(dtype=bool)
    blockers: list[str] = []
    failed: list[str] = []
    candidate_count = int(len(events))
    flagged_count = int(flag.sum())
    changed_fraction = float(flag.mean()) if candidate_count else None
    if candidate_count < 500:
        blockers.append("candidate_count_below_500")
    if flagged_count < 100:
        blockers.append("flagged_event_count_below_100")
    if changed_fraction is not None and changed_fraction > 0.75:
        failed.append("flag_too_broad_for_atomic_haircut")
    if not (
        primary_effect.get("status") == "ok"
        and float(primary_effect.get("short_return_delta") or 0.0) < 0.0
        and float(primary_effect.get("adverse_squeeze_gt_5pct_delta") or 0.0) > 0.0
    ):
        failed.append("primary_risk_direction_failed")
    if not (
        policy_effect.get("half_flagged_short_return_delta_vs_baseline") is not None
        and float(policy_effect["half_flagged_short_return_delta_vs_baseline"]) > 0.0
        and policy_effect.get("half_flagged_weighted_adverse_gt_5pct_fraction") is not None
        and policy_effect.get("baseline_weighted_adverse_gt_5pct_fraction") is not None
        and float(policy_effect["half_flagged_weighted_adverse_gt_5pct_fraction"])
        < float(policy_effect["baseline_weighted_adverse_gt_5pct_fraction"])
    ):
        failed.append("half_flagged_policy_does_not_improve_return_and_tail")
    if not shuffle_tests.get("passed"):
        failed.append("shuffle_tests_failed")
    if not symbol_holdout.get("passed"):
        failed.append("symbol_holdout_failed")
    if not liquidity_bucket_consistency.get("passed"):
        failed.append("liquidity_bucket_consistency_failed")
    if not delay_robustness.get("passed"):
        failed.append("delay_robustness_failed")
    label = "blocked" if blockers else ("pass" if not failed else "fail")
    return {
        "label": label,
        "blockers": blockers,
        "failed_checks": failed,
        "candidate_short_row_count": candidate_count,
        "flagged_event_count": flagged_count,
        "flagged_fraction": changed_fraction,
        "pass_rule": (
            "pass requires enough events, not-too-broad atomic flag, worse h24 shorts, higher adverse tails, "
            "positive half-size policy effect, shuffle pass, symbol holdout pass, bucket consistency pass, "
            "and +0/+1/+6/+24h delay robustness"
        ),
    }


def _atom_report(
    frame: pd.DataFrame,
    spec: AtomSpec,
    *,
    horizons: tuple[int, ...],
    shuffle_iterations: int,
    precomputed_shuffle_tests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events = _event_frame(frame)
    primary = _cohort_effect(events, flag_column=spec.flag_column, horizon=24)
    policy = _policy_effect(events, spec, horizon=24)
    shuffle_tests = precomputed_shuffle_tests or _shuffle_tests_for_atom(
        events, spec, iterations=shuffle_iterations, horizon=24
    )
    symbol_holdout = _symbol_holdout_for_atom(events, spec, horizon=24)
    bucket = _liquidity_bucket_consistency_for_atom(events, spec, horizon=24)
    delay = _delay_robustness_for_atom(frame, spec, horizon=24)
    decision = _decision_for_atom(
        events,
        spec,
        primary_effect=primary,
        policy_effect=policy,
        shuffle_tests=shuffle_tests,
        symbol_holdout=symbol_holdout,
        liquidity_bucket_consistency=bucket,
        delay_robustness=delay,
    )
    return {
        "atom_id": spec.atom_id,
        "flag_column": spec.flag_column,
        "definition": spec.definition,
        "entry_exit_use_shape": spec.use_shape,
        "invalidates_if": spec.invalidates_if,
        "event_count_by_symbol": _event_count_by_symbol_for_atom(events, spec),
        "event_count_by_liquidity_bucket": _event_count_by_liquidity_bucket_for_atom(events, spec),
        "forward_return_table_h1_h3_h6_h12_h24_h48_h72": _forward_return_table_for_atom(
            events, spec, horizons
        ),
        "selected_short_changed_rows_equivalent": {
            "interaction_type": "atomic_capacity_haircut_or_kill_switch_test",
            "candidate_short_rows": int(len(events)),
            "flagged_rows": int(events[spec.flag_column].fillna(False).astype(bool).sum()),
            "primary_effect_h24": primary,
            "policy_effect_h24": policy,
        },
        "funding_drag_summary": _funding_drag_summary_for_atom(events, spec, horizons),
        "slippage_or_capacity_proxy": _capacity_summary_for_atom(events, spec),
        "shuffle_tests": shuffle_tests,
        "symbol_holdout": symbol_holdout,
        "liquidity_bucket_consistency": bucket,
        "delay_robustness": delay,
        "pass_fail_decision": decision,
    }


def _data_sources_and_coverage(frame: pd.DataFrame, meta: dict[str, Any], root: Path) -> dict[str, Any]:
    payload = trap_eval._data_sources_and_coverage(frame, meta, root)
    payload["research_lane"] = RESEARCH_ID
    payload["source_reuse_note"] = (
        "Reuses low_float_squeeze_trap local 1h loader and fake_liquidity_capacity_haircut PIT feature builder."
    )
    payload["provider_gap_note"] = (
        "Venue concentration is still unavailable; atoms are volume/OI, orderbook, taker, liquidation, "
        "and slippage proxies only. Coverage is not provider concordance."
    )
    return payload


def _feature_definitions() -> dict[str, Any]:
    payload = {spec.atom_id: spec.definition for spec in ATOM_SPECS}
    payload.update(
        {
            "base_candidate": "post_pump_short_candidate_flag from the low-float squeeze-trap evaluator.",
            "fake_liquidity_atom_score": (
                "sum(volume_oi_brushing, thin_capacity, thin_book_vs_flow, thin_book_vs_oi, "
                "high_slippage_proxy, taker_churn_without_direction, liquidation_churn)."
            ),
            "pit_rule": "all rolling quantile thresholds are shifted one bar; forward returns are labels only.",
        }
    )
    return payload


def _overall_decision(atom_reports: dict[str, Any]) -> dict[str, Any]:
    labels = {atom_id: report["pass_fail_decision"]["label"] for atom_id, report in atom_reports.items()}
    passed = [atom_id for atom_id, label in labels.items() if label == "pass"]
    blocked = [atom_id for atom_id, label in labels.items() if label == "blocked"]
    failed = [atom_id for atom_id, label in labels.items() if label == "fail"]
    if passed:
        label = "pass"
    elif len(blocked) == len(labels):
        label = "blocked"
    else:
        label = "fail"
    return {
        "label": label,
        "atom_labels": labels,
        "passed_atoms": passed,
        "failed_atoms": failed,
        "blocked_atoms": blocked,
        "h10d_canonical_parent_status": "not_read_not_modified",
        "decision_rule": "overall pass means at least one atom passes; per-atom labels remain binding.",
    }


def _next_landing_shape(overall: dict[str, Any]) -> dict[str, Any]:
    passed = list(overall.get("passed_atoms") or [])
    if passed:
        return {
            "recommended_shape": "quarantined_atomic_capacity_sidecar",
            "atoms_to_carry_forward": passed,
            "next_step": (
                "Build a 1h parent-interaction simulator for only the passed atoms; "
                "do not use failed atoms and do not bridge to h10d without a separate gate."
            ),
        }
    if overall.get("label") == "blocked":
        return {
            "recommended_shape": "data_or_coverage_repair",
            "next_step": "Do not interpret the atom lane until blockers are repaired.",
        }
    return {
        "recommended_shape": "fail_closed",
        "next_step": "Do not use these atoms as standalone capacity rules; revisit venue concentration or stricter execution simulator.",
    }


def _write_report(
    *,
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    output_path: Path,
    as_of: str,
    horizons: tuple[int, ...],
    shuffle_iterations: int,
) -> dict[str, Any]:
    events = _event_frame(frame) if not frame.empty else pd.DataFrame()
    precomputed_shuffle_tests = (
        _shuffle_tests_for_all_atoms(events, ATOM_SPECS, iterations=shuffle_iterations, horizon=24)
        if not events.empty
        else {}
    )
    atom_reports = {
        spec.atom_id: _atom_report(
            frame,
            spec,
            horizons=horizons,
            shuffle_iterations=shuffle_iterations,
            precomputed_shuffle_tests=precomputed_shuffle_tests.get(spec.atom_id),
        )
        for spec in ATOM_SPECS
    } if not frame.empty else {}
    overall = _overall_decision(atom_reports) if atom_reports else {
        "label": "blocked",
        "atom_labels": {},
        "passed_atoms": [],
        "failed_atoms": [],
        "blocked_atoms": [spec.atom_id for spec in ATOM_SPECS],
        "h10d_canonical_parent_status": "not_read_not_modified",
    }
    report = {
        "artifact_family": "parallel_1h_alpha_mining_stage0",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "data_sources_and_coverage": _data_sources_and_coverage(frame, meta, root),
        "feature_definitions": _feature_definitions(),
        "event_count_by_symbol": {
            spec.atom_id: _event_count_by_symbol_for_atom(events, spec) for spec in ATOM_SPECS
        } if not events.empty else {},
        "event_count_by_liquidity_bucket": {
            spec.atom_id: _event_count_by_liquidity_bucket_for_atom(events, spec) for spec in ATOM_SPECS
        } if not events.empty else {},
        "forward_return_table_h1_h3_h6_h12_h24_h48_h72": {
            atom_id: atom_report["forward_return_table_h1_h3_h6_h12_h24_h48_h72"]
            for atom_id, atom_report in atom_reports.items()
        },
        "selected_short_changed_rows_equivalent": {
            atom_id: atom_report["selected_short_changed_rows_equivalent"]
            for atom_id, atom_report in atom_reports.items()
        },
        "funding_drag_summary": {
            atom_id: atom_report["funding_drag_summary"] for atom_id, atom_report in atom_reports.items()
        },
        "slippage_or_capacity_proxy": {
            atom_id: atom_report["slippage_or_capacity_proxy"] for atom_id, atom_report in atom_reports.items()
        },
        "shuffle_tests": {
            atom_id: atom_report["shuffle_tests"] for atom_id, atom_report in atom_reports.items()
        },
        "symbol_holdout": {
            atom_id: atom_report["symbol_holdout"] for atom_id, atom_report in atom_reports.items()
        },
        "liquidity_bucket_consistency": {
            atom_id: atom_report["liquidity_bucket_consistency"] for atom_id, atom_report in atom_reports.items()
        },
        "delay_robustness": {
            atom_id: atom_report["delay_robustness"] for atom_id, atom_report in atom_reports.items()
        },
        "atom_reports": atom_reports,
        "pass_fail_decision": overall,
        "next_landing_shape": _next_landing_shape(overall),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = trap_eval._resolve_market_history_root(args.market_history_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / "fake_liquidity_capacity_haircut_atoms_stage0_1h.json"
    horizons = tuple(DEFAULT_HORIZONS)
    symbols = trap_eval._discover_symbols(root, requested=str(args.symbols), limit=int(args.symbol_limit))
    base_frame, meta = trap_eval._load_research_frame(root, symbols, horizons)
    frame = _add_atom_state(base_frame) if not base_frame.empty else base_frame
    report = _write_report(
        frame=frame,
        meta=meta,
        root=root,
        output_path=output_path,
        as_of=str(args.as_of),
        horizons=horizons,
        shuffle_iterations=int(args.shuffle_iterations),
    )
    compact = {
        "research_id": report["research_id"],
        "loaded_symbol_count": report["data_sources_and_coverage"].get("loaded_symbol_count"),
        "row_count": report["data_sources_and_coverage"].get("row_count"),
        "overall_decision": report["pass_fail_decision"],
        "atom_summary": {
            atom_id: {
                "label": atom["pass_fail_decision"]["label"],
                "flagged_event_count": atom["pass_fail_decision"].get("flagged_event_count"),
                "flagged_fraction": atom["pass_fail_decision"].get("flagged_fraction"),
                "short_delta_h24": atom["selected_short_changed_rows_equivalent"]["primary_effect_h24"].get(
                    "short_return_delta"
                ),
                "adverse_delta_h24": atom["selected_short_changed_rows_equivalent"]["primary_effect_h24"].get(
                    "adverse_squeeze_gt_5pct_delta"
                ),
                "failed_checks": atom["pass_fail_decision"].get("failed_checks"),
                "shuffle_passed": atom["shuffle_tests"].get("passed"),
                "symbol_holdout_passed": atom["symbol_holdout"].get("passed"),
                "bucket_passed": atom["liquidity_bucket_consistency"].get("passed"),
                "delay_passed": atom["delay_robustness"].get("passed"),
            }
            for atom_id, atom in report["atom_reports"].items()
        },
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
