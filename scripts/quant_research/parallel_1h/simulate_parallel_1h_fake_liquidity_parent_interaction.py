from __future__ import annotations

import argparse
import json
import sys
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

from scripts.quant_research.parallel_1h import evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0 as haircut_eval  # noqa: E402


CONTRACT_VERSION = "parallel_1h_fake_liquidity_parent_interaction.v1"
RESEARCH_ID = "fake_liquidity_aggregate_parent_interaction_1h"
DEFAULT_HORIZONS = haircut_eval.DEFAULT_HORIZONS
DEFAULT_SHUFFLE_ITERATIONS = 200
HOUR_MS = haircut_eval.HOUR_MS
VARIANT_SIZE_ON_FLAG = {
    "baseline_parent": 1.0,
    "hard_veto": 0.0,
    "quarter_size": 0.25,
    "soft_multiplier": 0.50,
}
COST_BPS = (10, 50, 100)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Quarantined 1h parent-interaction simulator for aggregate fake-liquidity haircut. "
            "It compares hard-veto, quarter-size, and soft-multiplier policies against the raw "
            "post-pump low-float-proxy short parent."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    return parser


def _duration_days(events: pd.DataFrame) -> float:
    if events.empty:
        return 0.0
    start = int(events["open_time_ms"].min())
    end = int(events["open_time_ms"].max())
    return max((end - start) / (24.0 * HOUR_MS), 1.0)


def _variant_exposure(flag: pd.Series | np.ndarray, variant: str) -> np.ndarray:
    flag_arr = np.asarray(flag, dtype=bool)
    if variant == "baseline_parent":
        return np.ones(flag_arr.shape[0], dtype="float64")
    if variant not in VARIANT_SIZE_ON_FLAG:
        raise ValueError(f"Unknown variant: {variant}")
    return np.where(flag_arr, float(VARIANT_SIZE_ON_FLAG[variant]), 1.0).astype("float64")


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return out


def _mean(values: np.ndarray) -> float | None:
    valid = values[np.isfinite(values)]
    return float(valid.mean()) if valid.size else None


def _quantile(values: np.ndarray, q: float) -> float | None:
    valid = values[np.isfinite(values)]
    return float(np.nanquantile(valid, q)) if valid.size else None


def _portfolio_metrics(
    events: pd.DataFrame,
    exposure: np.ndarray,
    *,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "row_count": int(len(events)),
        "active_row_count": int((exposure > 0.0).sum()),
        "active_row_fraction": float((exposure > 0.0).mean()) if len(events) else None,
        "mean_exposure": float(np.nanmean(exposure)) if len(exposure) else None,
        "gross_exposure_units": float(np.nansum(exposure)) if len(exposure) else None,
    }
    for horizon in horizons:
        short_ret = pd.to_numeric(events[f"forward_{horizon}h_short_return"], errors="coerce").to_numpy(dtype="float64")
        long_ret = -short_ret
        valid = np.isfinite(short_ret)
        exp = exposure[valid]
        sr = short_ret[valid]
        lr = long_ret[valid]
        if sr.size == 0:
            out[f"h{horizon}"] = {"observation_count": 0}
            continue
        pnl = exp * sr
        abs_exp_sum = float(np.nansum(np.abs(exp)))
        metrics = {
            "observation_count": int(sr.size),
            "gross_pnl_per_candidate": float(np.nanmean(pnl)),
            "return_per_unit_exposure": float(np.nansum(pnl) / abs_exp_sum) if abs_exp_sum > 0.0 else None,
            "mean_short_return_unweighted": float(np.nanmean(sr)),
            "active_exposure_mean": float(np.nanmean(exp)),
            "adverse_squeeze_gt_5pct_fraction_weighted": float(
                np.nansum(np.abs(exp) * (lr > 0.05)) / abs_exp_sum
            )
            if abs_exp_sum > 0.0
            else None,
            "adverse_squeeze_gt_10pct_fraction_weighted": float(
                np.nansum(np.abs(exp) * (lr > 0.10)) / abs_exp_sum
            )
            if abs_exp_sum > 0.0
            else None,
        }
        for cost_bps in COST_BPS:
            cost = np.abs(exp) * (float(cost_bps) / 10_000.0)
            metrics[f"net_pnl_per_candidate_cost_{cost_bps}bps"] = float(np.nanmean(pnl - cost))
            metrics[f"net_return_per_unit_exposure_cost_{cost_bps}bps"] = (
                float(np.nansum(pnl - cost) / abs_exp_sum) if abs_exp_sum > 0.0 else None
            )
        out[f"h{horizon}"] = metrics
    return out


def _capacity_turnover_metrics(events: pd.DataFrame, exposure: np.ndarray, *, primary_horizon: int = 24) -> dict[str, Any]:
    active = exposure > 0.0
    days = _duration_days(events)
    capacity = pd.to_numeric(events["capacity_proxy_usd"], errors="coerce").to_numpy(dtype="float64")
    after = exposure * capacity
    by_hour = (
        pd.DataFrame({"open_time_ms": events["open_time_ms"].to_numpy(), "exposure": exposure})
        .groupby("open_time_ms")["exposure"]
        .sum()
    )
    active_by_hour = (
        pd.DataFrame({"open_time_ms": events["open_time_ms"].to_numpy(), "active": active.astype(int)})
        .groupby("open_time_ms")["active"]
        .sum()
    )
    return {
        "duration_days": float(days),
        "entry_rows": int(len(events)),
        "active_entry_rows": int(active.sum()),
        "active_entry_rows_per_day": float(active.sum() / days),
        "gross_exposure_units_per_day": float(np.nansum(exposure) / days),
        "estimated_active_position_units_h24": float((np.nansum(exposure) / days) * (primary_horizon / 24.0)),
        "mean_entry_exposure_units_per_hour": float(by_hour.mean()) if len(by_hour) else None,
        "p95_entry_exposure_units_per_hour": float(by_hour.quantile(0.95)) if len(by_hour) else None,
        "max_entry_exposure_units_per_hour": float(by_hour.max()) if len(by_hour) else None,
        "mean_active_entries_per_hour": float(active_by_hour.mean()) if len(active_by_hour) else None,
        "p95_active_entries_per_hour": float(active_by_hour.quantile(0.95)) if len(active_by_hour) else None,
        "capacity_proxy_usd_median_active": _quantile(capacity[active], 0.50),
        "capacity_proxy_usd_p10_active": _quantile(capacity[active], 0.10),
        "capacity_after_policy_usd_median_active": _quantile(after[active], 0.50),
        "capacity_after_policy_usd_p10_active": _quantile(after[active], 0.10),
        "capacity_after_policy_usd_sum_per_day": float(np.nansum(after) / days),
        "max_trade_participation_rate": 0.005,
        "max_inventory_participation_rate": 0.02,
    }


def _improvement(events: pd.DataFrame, exposure: np.ndarray, *, horizon: int = 24) -> float | None:
    short_ret = pd.to_numeric(events[f"forward_{horizon}h_short_return"], errors="coerce").to_numpy(dtype="float64")
    valid = np.isfinite(short_ret)
    if not valid.any():
        return None
    return float(np.nanmean((exposure[valid] - 1.0) * short_ret[valid]))


def _groups_from_values(values: np.ndarray) -> list[np.ndarray]:
    groups: dict[Any, list[int]] = {}
    for idx, value in enumerate(values):
        groups.setdefault(value, []).append(idx)
    return [np.asarray(idx, dtype=np.int64) for idx in groups.values() if len(idx) > 1]


def _shuffle_summary(values: np.ndarray, observed: float, iterations: int) -> dict[str, Any]:
    if values.size == 0:
        return {"passed": False, "valid_iterations": 0, "iterations": int(iterations)}
    observed_upper_tail_quantile = float((values <= observed).mean())
    return {
        "passed": bool(observed > 0.0 and observed_upper_tail_quantile >= 0.90),
        "iterations": int(iterations),
        "valid_iterations": int(values.size),
        "observed_improvement": float(observed),
        "shuffle_mean_improvement": float(np.nanmean(values)),
        "shuffle_p50_improvement": float(np.nanpercentile(values, 50)),
        "shuffle_p95_improvement": float(np.nanpercentile(values, 95)),
        "observed_upper_tail_quantile": observed_upper_tail_quantile,
        "pass_rule": "observed improvement must be positive and in top 10pct of shuffled improvements",
    }


def _policy_shuffle_tests(
    events: pd.DataFrame,
    *,
    variant: str,
    iterations: int,
    horizon: int = 24,
) -> dict[str, Any]:
    flag = events["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
    exposure = _variant_exposure(flag, variant)
    observed = _improvement(events, exposure, horizon=horizon)
    if observed is None:
        return {"status": "insufficient", "passed": False, "tests": {}}

    rng = np.random.default_rng(20260511)
    time_groups = _groups_from_values(events["open_time_ms"].to_numpy())
    subject_groups = _groups_from_values(events["subject"].astype(str).to_numpy())
    short_ret = pd.to_numeric(events[f"forward_{horizon}h_short_return"], errors="coerce").to_numpy(dtype="float64")
    valid = np.isfinite(short_ret)
    tests: dict[str, Any] = {}

    deltas: list[float] = []
    for _ in range(iterations):
        shuffled_flag = flag.copy()
        for idx in time_groups:
            shuffled_flag[idx] = rng.permutation(flag[idx])
        shuffled_exposure = _variant_exposure(shuffled_flag, variant)
        if valid.any():
            deltas.append(float(np.nanmean((shuffled_exposure[valid] - 1.0) * short_ret[valid])))
    tests["same_timestamp_policy_shuffle"] = _shuffle_summary(np.asarray(deltas, dtype="float64"), observed, iterations)

    deltas = []
    for _ in range(iterations):
        shifted_flag = flag.copy()
        for idx in subject_groups:
            offset = int(rng.integers(1, len(idx)))
            shifted_flag[idx] = np.roll(flag[idx], offset)
        shifted_exposure = _variant_exposure(shifted_flag, variant)
        if valid.any():
            deltas.append(float(np.nanmean((shifted_exposure[valid] - 1.0) * short_ret[valid])))
    tests["symbol_time_shift_policy_shuffle"] = _shuffle_summary(np.asarray(deltas, dtype="float64"), observed, iterations)

    deltas = []
    for _ in range(iterations):
        shuffled_short = short_ret.copy()
        for idx in time_groups:
            shuffled_short[idx] = rng.permutation(short_ret[idx])
        valid_local = np.isfinite(shuffled_short)
        if valid_local.any():
            deltas.append(float(np.nanmean((exposure[valid_local] - 1.0) * shuffled_short[valid_local])))
    tests["same_timestamp_label_shuffle"] = _shuffle_summary(np.asarray(deltas, dtype="float64"), observed, iterations)

    return {
        "status": "ok",
        "horizon": f"h{horizon}",
        "observed_improvement": float(observed),
        "tests": tests,
        "passed": bool(observed > 0.0 and all(test.get("passed") for test in tests.values())),
    }


def _symbol_holdout(events: pd.DataFrame, *, variant: str, horizon: int = 24) -> dict[str, Any]:
    flag = events["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
    exposure = _variant_exposure(flag, variant)
    observed = _improvement(events, exposure, horizon=horizon)
    rows: dict[str, Any] = {}
    for subject, group in events.groupby("subject"):
        local_flag = group["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
        local_exposure = _variant_exposure(local_flag, variant)
        local_improvement = _improvement(group, local_exposure, horizon=horizon)
        if local_improvement is not None and len(group) >= 30:
            rows[str(subject)] = {
                "row_count": int(len(group)),
                "policy_row_count": int(local_flag.sum()),
                "improvement": float(local_improvement),
            }
    leave_one: dict[str, Any] = {}
    for subject in sorted(events["subject"].astype(str).unique()):
        local = events.loc[events["subject"].astype(str).ne(subject)].copy()
        local_flag = local["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
        local_exposure = _variant_exposure(local_flag, variant)
        local_improvement = _improvement(local, local_exposure, horizon=horizon)
        leave_one[subject] = {
            "row_count": int(len(local)),
            "improvement": local_improvement,
        }
    eligible = [row for row in rows.values() if row.get("improvement") is not None]
    sign_fraction = float(np.mean([float(row["improvement"]) > 0.0 for row in eligible])) if eligible else 0.0
    policy_counts = events.loc[events["fake_liquidity_capacity_haircut_flag"].fillna(False)].groupby("subject").size()
    total = int(policy_counts.sum())
    top_share = float(policy_counts.max() / total) if total else 1.0
    leave_one_values = [row.get("improvement") for row in leave_one.values() if row.get("improvement") is not None]
    leave_one_pass = bool(leave_one_values and all(float(value) > 0.0 for value in leave_one_values))
    passed = bool(
        observed is not None
        and observed > 0.0
        and len(eligible) >= 3
        and sign_fraction >= 0.60
        and top_share <= 0.30
        and leave_one_pass
    )
    return {
        "horizon": f"h{horizon}",
        "observed_improvement": observed,
        "eligible_symbol_count": int(len(eligible)),
        "directionally_consistent_symbol_fraction": sign_fraction,
        "top_policy_symbol_event_share": top_share,
        "by_symbol": rows,
        "leave_one_symbol_out": leave_one,
        "passed": passed,
    }


def _liquidity_bucket_consistency(events: pd.DataFrame, *, variant: str, horizon: int = 24) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for bucket, group in events.groupby("liquidity_bucket"):
        local_flag = group["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
        local_exposure = _variant_exposure(local_flag, variant)
        local_improvement = _improvement(group, local_exposure, horizon=horizon)
        rows[str(bucket)] = {
            "row_count": int(len(group)),
            "policy_row_count": int(local_flag.sum()),
            "improvement": local_improvement,
        }
    eligible = [
        row
        for row in rows.values()
        if int(row.get("row_count") or 0) >= 30
        and int(row.get("policy_row_count") or 0) >= 10
        and row.get("improvement") is not None
    ]
    passed = bool(len(eligible) >= 2 and all(float(row["improvement"]) > 0.0 for row in eligible))
    return {
        "horizon": f"h{horizon}",
        "bucket_results": rows,
        "eligible_bucket_count": int(len(eligible)),
        "passed": passed,
        "pass_rule": "at least two buckets with >=10 policy rows and positive policy improvement",
    }


def _delayed_events(frame: pd.DataFrame, *, delay_h: int, horizon: int = 24) -> pd.DataFrame:
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    events = frame.loc[
        candidates,
        [
            "subject",
            "open_time_ms",
            "liquidity_bucket",
            "fake_liquidity_capacity_haircut_flag",
            "capacity_proxy_usd",
        ],
    ].copy()
    events["entry_open_time_ms"] = events["open_time_ms"] + int(delay_h) * HOUR_MS
    lookup = frame[
        [
            "subject",
            "open_time_ms",
            f"forward_{horizon}h_short_return",
            f"forward_{horizon}h_log_return",
        ]
    ].copy()
    lookup = lookup.rename(columns={"open_time_ms": "entry_open_time_ms"})
    return events.merge(lookup, on=["subject", "entry_open_time_ms"], how="inner")


def _delay_robustness(frame: pd.DataFrame, *, variant: str, horizon: int = 24) -> dict[str, Any]:
    scenarios: dict[str, Any] = {}
    for delay in (0, 1, 6, 24):
        events = _delayed_events(frame, delay_h=delay, horizon=horizon)
        flag = events["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
        exposure = _variant_exposure(flag, variant)
        improvement = _improvement(events, exposure, horizon=horizon)
        scenarios[f"delay_{delay}h"] = {
            "delay_h": int(delay),
            "row_count": int(len(events)),
            "policy_row_count": int(flag.sum()),
            "improvement": improvement,
            "status": "ok" if improvement is not None else "insufficient",
        }
    stress = [scenarios[key] for key in ("delay_1h", "delay_6h", "delay_24h")]
    passed = bool(
        stress
        and all(
            row.get("improvement") is not None
            and float(row["improvement"]) > 0.0
            and int(row.get("policy_row_count") or 0) >= 10
            for row in stress
        )
    )
    return {"horizon": f"h{horizon}", "scenarios": scenarios, "passed": passed}


def _variant_report(
    frame: pd.DataFrame,
    events: pd.DataFrame,
    *,
    variant: str,
    shuffle_iterations: int,
) -> dict[str, Any]:
    flag = events["fake_liquidity_capacity_haircut_flag"].to_numpy(dtype=bool)
    exposure = _variant_exposure(flag, variant)
    baseline_exposure = np.ones(len(events), dtype="float64")
    portfolio = _portfolio_metrics(events, exposure, horizons=tuple(DEFAULT_HORIZONS))
    baseline = _portfolio_metrics(events, baseline_exposure, horizons=tuple(DEFAULT_HORIZONS))
    primary = portfolio["h24"]
    primary_baseline = baseline["h24"]
    delta = {
        "gross_pnl_per_candidate_delta_h24": (
            _safe_float(primary.get("gross_pnl_per_candidate"))
            - _safe_float(primary_baseline.get("gross_pnl_per_candidate"))
        )
        if _safe_float(primary.get("gross_pnl_per_candidate")) is not None
        and _safe_float(primary_baseline.get("gross_pnl_per_candidate")) is not None
        else None,
        "return_per_unit_exposure_delta_h24": (
            _safe_float(primary.get("return_per_unit_exposure"))
            - _safe_float(primary_baseline.get("return_per_unit_exposure"))
        )
        if _safe_float(primary.get("return_per_unit_exposure")) is not None
        and _safe_float(primary_baseline.get("return_per_unit_exposure")) is not None
        else None,
        "adverse_squeeze_gt_5pct_delta_h24": (
            _safe_float(primary.get("adverse_squeeze_gt_5pct_fraction_weighted"))
            - _safe_float(primary_baseline.get("adverse_squeeze_gt_5pct_fraction_weighted"))
        )
        if _safe_float(primary.get("adverse_squeeze_gt_5pct_fraction_weighted")) is not None
        and _safe_float(primary_baseline.get("adverse_squeeze_gt_5pct_fraction_weighted")) is not None
        else None,
    }
    for cost_bps in COST_BPS:
        key = f"net_pnl_per_candidate_cost_{cost_bps}bps"
        primary_value = _safe_float(primary.get(key))
        baseline_value = _safe_float(primary_baseline.get(key))
        delta[f"{key}_delta_h24"] = (
            primary_value - baseline_value
            if primary_value is not None and baseline_value is not None
            else None
        )

    if variant == "baseline_parent":
        return {
            "variant": variant,
            "size_on_aggregate_haircut": 1.0,
            "portfolio_metrics": portfolio,
            "capacity_turnover_metrics": _capacity_turnover_metrics(events, exposure, primary_horizon=24),
            "comparison_to_baseline": {},
            "policy_shuffle_tests": {"passed": None, "status": "not_applicable"},
            "symbol_holdout": {"passed": None, "status": "not_applicable"},
            "liquidity_bucket_consistency": {"passed": None, "status": "not_applicable"},
            "delay_robustness": {"passed": None, "status": "not_applicable"},
            "pass_fail_decision": {"label": "baseline"},
        }

    shuffle_tests = _policy_shuffle_tests(events, variant=variant, iterations=shuffle_iterations, horizon=24)
    symbol_holdout = _symbol_holdout(events, variant=variant, horizon=24)
    bucket = _liquidity_bucket_consistency(events, variant=variant, horizon=24)
    delay = _delay_robustness(frame, variant=variant, horizon=24)
    failed = []
    if delta.get("gross_pnl_per_candidate_delta_h24") is None or float(delta["gross_pnl_per_candidate_delta_h24"]) <= 0.0:
        failed.append("gross_pnl_not_improved")
    if delta.get("adverse_squeeze_gt_5pct_delta_h24") is None or float(delta["adverse_squeeze_gt_5pct_delta_h24"]) >= 0.0:
        failed.append("adverse_tail_not_reduced")
    if not shuffle_tests.get("passed"):
        failed.append("policy_shuffle_failed")
    if not symbol_holdout.get("passed"):
        failed.append("symbol_holdout_failed")
    if not bucket.get("passed"):
        failed.append("liquidity_bucket_consistency_failed")
    if not delay.get("passed"):
        failed.append("delay_robustness_failed")
    label = "pass" if not failed else "fail"
    return {
        "variant": variant,
        "size_on_aggregate_haircut": VARIANT_SIZE_ON_FLAG[variant],
        "portfolio_metrics": portfolio,
        "capacity_turnover_metrics": _capacity_turnover_metrics(events, exposure, primary_horizon=24),
        "comparison_to_baseline": delta,
        "policy_shuffle_tests": shuffle_tests,
        "symbol_holdout": symbol_holdout,
        "liquidity_bucket_consistency": bucket,
        "delay_robustness": delay,
        "pass_fail_decision": {
            "label": label,
            "failed_checks": failed,
            "decision_rule": (
                "variant passes only if h24 gross PnL improves, adverse squeeze tail falls, "
                "policy shuffle, symbol holdout, liquidity buckets, and +1h/+6h/+24h delay all pass"
            ),
        },
    }


def _rank_variants(reports: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for variant, report in reports.items():
        if variant == "baseline_parent":
            continue
        comparison = report.get("comparison_to_baseline", {})
        portfolio = report.get("portfolio_metrics", {}).get("h24", {})
        capacity = report.get("capacity_turnover_metrics", {})
        rows.append(
            {
                "variant": variant,
                "label": report.get("pass_fail_decision", {}).get("label"),
                "size_on_aggregate_haircut": report.get("size_on_aggregate_haircut"),
                "gross_pnl_per_candidate_delta_h24": comparison.get("gross_pnl_per_candidate_delta_h24"),
                "adverse_squeeze_gt_5pct_delta_h24": comparison.get("adverse_squeeze_gt_5pct_delta_h24"),
                "mean_exposure": portfolio.get("active_exposure_mean"),
                "gross_exposure_units_per_day": capacity.get("gross_exposure_units_per_day"),
                "capacity_after_policy_usd_sum_per_day": capacity.get("capacity_after_policy_usd_sum_per_day"),
                "failed_checks": report.get("pass_fail_decision", {}).get("failed_checks", []),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            0 if row["label"] == "pass" else 1,
            -(row["gross_pnl_per_candidate_delta_h24"] or -999.0),
        ),
    )


def _write_report(
    *,
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    output_path: Path,
    as_of: str,
    shuffle_iterations: int,
) -> dict[str, Any]:
    candidates = frame.loc[frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)].copy()
    reports = {
        variant: _variant_report(
            frame,
            candidates,
            variant=variant,
            shuffle_iterations=shuffle_iterations,
        )
        for variant in VARIANT_SIZE_ON_FLAG
    }
    ranked = _rank_variants(reports)
    passing = [row["variant"] for row in ranked if row.get("label") == "pass"]
    report = {
        "artifact_family": "parallel_1h_alpha_mining_stage0",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": as_of,
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "data_sources_and_coverage": haircut_eval._data_sources_and_coverage(frame, meta, root),
        "parent_definition": {
            "parent": "capacity_haircut_candidate_flag",
            "parent_description": "post-pump low-float-proxy short candidate rows; this is not a live portfolio.",
            "interaction_state": "fake_liquidity_capacity_haircut_flag",
            "variants": {
                "baseline_parent": "short every parent row at unit exposure",
                "hard_veto": "set aggregate-haircut rows to zero exposure",
                "quarter_size": "set aggregate-haircut rows to 25pct exposure",
                "soft_multiplier": "set aggregate-haircut rows to 50pct exposure",
            },
        },
        "candidate_count": int(len(candidates)),
        "aggregate_haircut_row_count": int(candidates["fake_liquidity_capacity_haircut_flag"].sum()),
        "shuffle_iterations": int(shuffle_iterations),
        "variant_reports": reports,
        "ranked_variants": ranked,
        "pass_fail_decision": {
            "label": "pass" if passing else "fail",
            "passing_variants": passing,
            "failed_variants": [row["variant"] for row in ranked if row.get("label") != "pass"],
            "decision_rule": (
                "This only admits a quarantined simulator interaction. No h10d bridge or live use is allowed "
                "without venue-concentration repair and a separate promotion gate."
            ),
        },
        "next_landing_shape": {
            "recommended_shape": "quarantined_1h_parent_interaction_card",
            "next_step": (
                "Use the best passing policy as a research-only parent interaction card, then run "
                "venue-concentration/provider sensitivity before any bridge discussion."
            )
            if passing
            else "Redefine the aggregate state before further parent simulation.",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = haircut_eval.trap_eval._resolve_market_history_root(args.market_history_root)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_path = output_dir / "fake_liquidity_aggregate_parent_interaction_1h.json"
    symbols = haircut_eval.trap_eval._discover_symbols(
        root,
        requested=str(args.symbols),
        limit=int(args.symbol_limit),
    )
    base_frame, meta = haircut_eval.trap_eval._load_research_frame(root, symbols, tuple(DEFAULT_HORIZONS))
    frame = haircut_eval._add_fake_liquidity_capacity_state(base_frame) if not base_frame.empty else base_frame
    report = _write_report(
        frame=frame,
        meta=meta,
        root=root,
        output_path=output_path,
        as_of=str(args.as_of),
        shuffle_iterations=int(args.shuffle_iterations),
    )
    compact = {
        "output_path": str(output_path),
        "research_id": report["research_id"],
        "candidate_count": report["candidate_count"],
        "aggregate_haircut_row_count": report["aggregate_haircut_row_count"],
        "ranked_variants": report["ranked_variants"],
        "pass_fail_decision": report["pass_fail_decision"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
