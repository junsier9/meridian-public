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


CONTRACT_VERSION = "parallel_1h_fake_liquidity_atomic_decomposition.v1"
RESEARCH_ID = "fake_liquidity_atomic_decomposition_1h"
DEFAULT_HORIZONS = haircut_eval.DEFAULT_HORIZONS
DEFAULT_SHUFFLE_ITERATIONS = 200
DEFAULT_COMPONENTS = (
    "aggregate_haircut",
    "volume_oi_brushing_extreme",
    "thin_capacity",
    "book_thinness",
    "taker_book_dislocation",
    "slippage_proxy_extreme",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Atomic decomposition for the passing fake-liquidity capacity-haircut Stage 0 state. "
            "Research diagnostic only; does not touch h10d promotion state."
        )
    )
    parser.add_argument("--market-history-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shuffle-iterations", type=int, default=DEFAULT_SHUFFLE_ITERATIONS)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--symbol-limit", type=int, default=0)
    parser.add_argument(
        "--components",
        default=",".join(DEFAULT_COMPONENTS),
        help="Comma-separated component names. Empty means default core components.",
    )
    return parser


def _component_catalog(frame: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "aggregate_haircut": frame["fake_liquidity_capacity_haircut_flag"].fillna(False).astype(bool),
        "volume_oi_brushing_extreme": frame["volume_oi_brushing_extreme_flag"].fillna(False).astype(bool),
        "thin_capacity": frame["thin_capacity_flag"].fillna(False).astype(bool),
        "book_thinness": frame["book_thinness_flag"].fillna(False).astype(bool),
        "taker_book_dislocation": frame["taker_book_dislocation_flag"].fillna(False).astype(bool),
        "slippage_proxy_extreme": frame["slippage_proxy_extreme_flag"].fillna(False).astype(bool),
    }


def _parse_components(text: str) -> list[str]:
    values = [item.strip() for item in str(text or "").split(",") if item.strip()]
    return values or list(DEFAULT_COMPONENTS)


def _effect_delta(
    events: pd.DataFrame,
    *,
    flag_column: str,
    horizon: int = 24,
) -> dict[str, Any]:
    if events.empty or flag_column not in events.columns:
        return {
            "status": "insufficient",
            "flagged_count": 0,
            "control_count": 0,
            "short_return_delta": None,
        }
    flag = events[flag_column].fillna(False).astype(bool)
    short_ret = pd.to_numeric(events[f"forward_{horizon}h_short_return"], errors="coerce")
    flagged_ret = short_ret.loc[flag].dropna()
    control_ret = short_ret.loc[~flag].dropna()
    if flagged_ret.empty or control_ret.empty:
        return {
            "status": "insufficient",
            "flagged_count": int(len(flagged_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    return {
        "status": "ok",
        "flagged_count": int(len(flagged_ret)),
        "control_count": int(len(control_ret)),
        "flagged_short_return_mean": float(flagged_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(flagged_ret.mean() - control_ret.mean()),
        "interpretation": "negative_delta_means_flagged_rows_are_worse_shorts_than_control",
    }


def _shuffle_summary(arr: np.ndarray, observed_delta: float, iterations: int) -> dict[str, Any]:
    if arr.size == 0:
        return {"passed": False, "iterations": int(iterations), "valid_iterations": 0}
    observed_lower_tail_quantile = float((arr <= observed_delta).mean())
    return {
        "passed": bool(observed_delta < 0.0 and observed_lower_tail_quantile <= 0.10),
        "iterations": int(iterations),
        "valid_iterations": int(arr.size),
        "observed_short_return_delta": float(observed_delta),
        "shuffle_mean_delta": float(np.nanmean(arr)),
        "shuffle_p05_delta": float(np.nanpercentile(arr, 5)),
        "shuffle_p50_delta": float(np.nanpercentile(arr, 50)),
        "observed_lower_tail_quantile": observed_lower_tail_quantile,
        "pass_rule": "observed delta must be negative and in bottom 10pct of shuffled deltas",
    }


def _array_delta_value(short_return: np.ndarray, flag: np.ndarray) -> float | None:
    valid = np.isfinite(short_return)
    flagged = flag & valid
    control = ~flag & valid
    if int(flagged.sum()) == 0 or int(control.sum()) == 0:
        return None
    return float(short_return[flagged].mean() - short_return[control].mean())


def _groups_from_values(values: np.ndarray) -> list[np.ndarray]:
    buckets: dict[Any, list[int]] = {}
    for idx, value in enumerate(values):
        buckets.setdefault(value, []).append(idx)
    return [
        np.asarray(indices, dtype=np.int64)
        for indices in buckets.values()
        if len(indices) > 1
    ]


def _shuffle_tests(events: pd.DataFrame, *, iterations: int, horizon: int = 24) -> dict[str, Any]:
    observed = _effect_delta(events, flag_column="_component_flag", horizon=horizon)
    observed_delta = observed.get("short_return_delta")
    if observed_delta is None:
        return {"status": "insufficient", "observed": observed, "tests": {}, "passed": False}
    rng = np.random.default_rng(20260510)
    tests: dict[str, Any] = {}
    flag = events["_component_flag"].to_numpy(dtype=bool)
    short_return = pd.to_numeric(
        events[f"forward_{horizon}h_short_return"],
        errors="coerce",
    ).to_numpy(dtype="float64")
    time_groups = _groups_from_values(events["open_time_ms"].to_numpy())
    subject_groups = _groups_from_values(events["subject"].astype(str).to_numpy())

    feature_deltas: list[float] = []
    for _ in range(iterations):
        shuffled = flag.copy()
        for idx in time_groups:
            shuffled[idx] = rng.permutation(flag[idx])
        delta = _array_delta_value(short_return, shuffled)
        if delta is not None:
            feature_deltas.append(float(delta))
    tests["same_timestamp_feature_shuffle"] = _shuffle_summary(
        np.asarray(feature_deltas, dtype="float64"),
        float(observed_delta),
        iterations,
    )

    shifted_deltas: list[float] = []
    for _ in range(iterations):
        shifted = flag.copy()
        for idx in subject_groups:
            offset = int(rng.integers(1, len(idx)))
            shifted[idx] = np.roll(flag[idx], offset)
        delta = _array_delta_value(short_return, shifted)
        if delta is not None:
            shifted_deltas.append(float(delta))
    tests["symbol_time_shift_shuffle"] = _shuffle_summary(
        np.asarray(shifted_deltas, dtype="float64"),
        float(observed_delta),
        iterations,
    )

    label_deltas: list[float] = []
    for _ in range(iterations):
        shuffled_short = short_return.copy()
        for idx in time_groups:
            shuffled_short[idx] = rng.permutation(short_return[idx])
        delta = _array_delta_value(shuffled_short, flag)
        if delta is not None:
            label_deltas.append(float(delta))
    tests["same_timestamp_label_shuffle"] = _shuffle_summary(
        np.asarray(label_deltas, dtype="float64"),
        float(observed_delta),
        iterations,
    )
    return {
        "status": "ok",
        "horizon": f"h{horizon}",
        "observed": observed,
        "tests": tests,
        "passed": bool(observed_delta < 0.0 and all(test.get("passed") for test in tests.values())),
    }


def _symbol_holdout(events: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    observed = _effect_delta(events, flag_column="_component_flag", horizon=horizon)
    rows: dict[str, Any] = {}
    for subject, group in events.groupby("subject"):
        local = _effect_delta(group, flag_column="_component_flag", horizon=horizon)
        if int(local.get("flagged_count") or 0) >= 3 and int(local.get("control_count") or 0) >= 3:
            rows[str(subject)] = local
    leave_one_out: dict[str, Any] = {}
    for subject in sorted(events["subject"].astype(str).unique()):
        local = events.loc[events["subject"].astype(str).ne(subject)]
        leave_one_out[subject] = _effect_delta(local, flag_column="_component_flag", horizon=horizon)
    eligible = [row for row in rows.values() if row.get("short_return_delta") is not None]
    sign_consistent = [float(row["short_return_delta"]) < 0.0 for row in eligible]
    counts = events.loc[events["_component_flag"].fillna(False).astype(bool)].groupby("subject").size()
    total = int(counts.sum())
    top_share = float(counts.max() / total) if total else 1.0
    leave_one_deltas = [
        row.get("short_return_delta")
        for row in leave_one_out.values()
        if row.get("short_return_delta") is not None
    ]
    leave_one_pass = bool(leave_one_deltas and all(float(delta) < 0.0 for delta in leave_one_deltas))
    sign_fraction = float(np.mean(sign_consistent)) if sign_consistent else 0.0
    passed = bool(
        observed.get("short_return_delta") is not None
        and float(observed["short_return_delta"]) < 0.0
        and len(eligible) >= 3
        and sign_fraction >= 0.60
        and top_share <= 0.30
        and leave_one_pass
    )
    return {
        "horizon": f"h{horizon}",
        "observed": observed,
        "eligible_symbol_count": int(len(eligible)),
        "directionally_consistent_symbol_fraction": sign_fraction,
        "top_component_symbol_event_share": top_share,
        "by_symbol": rows,
        "leave_one_symbol_out": leave_one_out,
        "passed": passed,
    }


def _liquidity_bucket_consistency(events: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for bucket, group in events.groupby("liquidity_bucket"):
        rows[str(bucket)] = _effect_delta(group, flag_column="_component_flag", horizon=horizon)
    eligible = [
        row
        for row in rows.values()
        if int(row.get("flagged_count") or 0) >= 10
        and int(row.get("control_count") or 0) >= 10
        and row.get("short_return_delta") is not None
    ]
    passed = bool(len(eligible) >= 2 and all(float(row["short_return_delta"]) < 0.0 for row in eligible))
    return {
        "horizon": f"h{horizon}",
        "bucket_results": rows,
        "eligible_bucket_count": int(len(eligible)),
        "passed": passed,
        "pass_rule": "at least two buckets with >=10 component/control observations and negative short-return delta",
    }


def _delayed_effect(frame: pd.DataFrame, *, component_mask: pd.Series, delay_h: int, horizon: int = 24) -> dict[str, Any]:
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    columns = [f"forward_{horizon}h_short_return", f"forward_{horizon}h_log_return"]
    flagged_delayed = haircut_eval._cohort_after_delay(
        frame,
        mask=candidates & component_mask,
        delay_h=delay_h,
        columns=columns,
    )
    control_delayed = haircut_eval._cohort_after_delay(
        frame,
        mask=candidates & ~component_mask,
        delay_h=delay_h,
        columns=columns,
    )
    if flagged_delayed.empty or control_delayed.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "flagged_count": int(len(flagged_delayed)),
            "control_count": int(len(control_delayed)),
            "short_return_delta": None,
        }
    flagged_ret = pd.to_numeric(flagged_delayed[f"forward_{horizon}h_short_return"], errors="coerce").dropna()
    control_ret = pd.to_numeric(control_delayed[f"forward_{horizon}h_short_return"], errors="coerce").dropna()
    if flagged_ret.empty or control_ret.empty:
        return {
            "delay_h": int(delay_h),
            "status": "insufficient",
            "flagged_count": int(len(flagged_ret)),
            "control_count": int(len(control_ret)),
            "short_return_delta": None,
        }
    return {
        "delay_h": int(delay_h),
        "status": "ok",
        "flagged_count": int(len(flagged_ret)),
        "control_count": int(len(control_ret)),
        "flagged_short_return_mean": float(flagged_ret.mean()),
        "control_short_return_mean": float(control_ret.mean()),
        "short_return_delta": float(flagged_ret.mean() - control_ret.mean()),
    }


def _delay_robustness(frame: pd.DataFrame, *, component_mask: pd.Series, horizon: int = 24) -> dict[str, Any]:
    scenarios = {
        f"delay_{delay}h": _delayed_effect(frame, component_mask=component_mask, delay_h=delay, horizon=horizon)
        for delay in (0, 1, 6, 24)
    }
    stress = [
        row
        for label, row in scenarios.items()
        if label in {"delay_1h", "delay_6h", "delay_24h"}
    ]
    passed = bool(
        stress
        and all(
            row.get("short_return_delta") is not None
            and float(row["short_return_delta"]) < 0.0
            and int(row.get("flagged_count") or 0) >= 10
            and int(row.get("control_count") or 0) >= 10
            for row in stress
        )
    )
    return {"horizon": f"h{horizon}", "scenarios": scenarios, "passed": passed}


def _capacity_component_diagnostic(events: pd.DataFrame, *, horizon: int = 24) -> dict[str, Any]:
    flagged = events["_component_flag"].fillna(False).astype(bool)
    flagged_subset = events.loc[flagged].copy()
    control_subset = events.loc[~flagged].copy()
    effect = _effect_delta(events, flag_column="_component_flag", horizon=horizon)
    flagged_summary = haircut_eval._capacity_summary_for_subset(flagged_subset, horizon=horizon)
    control_summary = haircut_eval._capacity_summary_for_subset(control_subset, horizon=horizon)
    changed_fraction = float(len(flagged_subset) / max(len(events), 1))

    def _num(summary: dict[str, Any], key: str) -> float | None:
        return haircut_eval._to_float(summary.get(key))

    capacity_lower = (
        _num(flagged_summary, "capacity_proxy_usd_median") is not None
        and _num(control_summary, "capacity_proxy_usd_median") is not None
        and _num(flagged_summary, "capacity_proxy_usd_median") < _num(control_summary, "capacity_proxy_usd_median")
    )
    slippage_higher = (
        _num(flagged_summary, "slippage_proxy_mean") is not None
        and _num(control_summary, "slippage_proxy_mean") is not None
        and _num(flagged_summary, "slippage_proxy_mean") > _num(control_summary, "slippage_proxy_mean")
    )
    fake_risk_higher = (
        _num(flagged_summary, "fake_liquidity_risk_fraction") is not None
        and _num(control_summary, "fake_liquidity_risk_fraction") is not None
        and _num(flagged_summary, "fake_liquidity_risk_fraction")
        > _num(control_summary, "fake_liquidity_risk_fraction")
    )
    adverse_higher = (
        _num(flagged_summary, "adverse_squeeze_gt_5pct_fraction") is not None
        and _num(control_summary, "adverse_squeeze_gt_5pct_fraction") is not None
        and _num(flagged_summary, "adverse_squeeze_gt_5pct_fraction")
        > _num(control_summary, "adverse_squeeze_gt_5pct_fraction")
    )
    delta = haircut_eval._to_float(effect.get("short_return_delta"))
    passed = bool(
        len(flagged_subset) >= 30
        and len(control_subset) >= 30
        and changed_fraction <= 0.75
        and delta is not None
        and delta < 0.0
        and adverse_higher
        and (capacity_lower or slippage_higher or fake_risk_higher)
    )
    return {
        "horizon": f"h{horizon}",
        "flagged_summary": flagged_summary,
        "control_summary": control_summary,
        "changed_fraction": changed_fraction,
        "effect": effect,
        "capacity_lower_than_control": capacity_lower,
        "slippage_higher_than_control": slippage_higher,
        "fake_liquidity_risk_higher_than_control": fake_risk_higher,
        "adverse_squeeze_tail_higher_than_control": adverse_higher,
        "passed": passed,
    }


def _component_report(
    frame: pd.DataFrame,
    *,
    name: str,
    mask: pd.Series,
    iterations: int,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    candidates = frame["capacity_haircut_candidate_flag"].fillna(False).astype(bool)
    events = frame.loc[candidates].copy()
    events["_component_flag"] = mask.loc[events.index].fillna(False).astype(bool)
    flag = events["_component_flag"].fillna(False).astype(bool)
    shuffle_tests = _shuffle_tests(events, iterations=iterations, horizon=24)
    symbol_holdout = _symbol_holdout(events, horizon=24)
    liquidity_bucket_consistency = _liquidity_bucket_consistency(events, horizon=24)
    delay_robustness = _delay_robustness(frame, component_mask=mask, horizon=24)
    capacity_diagnostic = _capacity_component_diagnostic(events, horizon=24)
    failed = []
    if not capacity_diagnostic.get("passed"):
        failed.append("capacity_component_diagnostic_failed")
    if not shuffle_tests.get("passed"):
        failed.append("shuffle_tests_failed")
    if not symbol_holdout.get("passed"):
        failed.append("symbol_holdout_failed")
    if not liquidity_bucket_consistency.get("passed"):
        failed.append("liquidity_bucket_consistency_failed")
    if not delay_robustness.get("passed"):
        failed.append("delay_robustness_failed")
    blockers = []
    if len(events) < 100:
        blockers.append("candidate_count_below_100")
    if int(flag.sum()) < 30:
        blockers.append("component_event_count_below_30")
    label = "blocked" if blockers else ("fail" if failed else "pass")
    return {
        "component": name,
        "label": label,
        "blockers": blockers,
        "failed_checks": failed,
        "candidate_count": int(len(events)),
        "component_event_count": int(flag.sum()),
        "component_fraction": float(flag.mean()) if len(flag) else None,
        "event_count_by_symbol": {
            str(key): int(value)
            for key, value in events.loc[flag].groupby("subject").size().sort_values(ascending=False).items()
        },
        "event_count_by_liquidity_bucket": {
            str(key): int(value)
            for key, value in events.loc[flag].groupby("liquidity_bucket").size().sort_values(ascending=False).items()
        },
        "forward_return_table_h1_h3_h6_h12_h24_h48_h72": {
            "component_flagged_rows": haircut_eval._mask_summary(events, flag, horizons),
            "candidate_control_rows": haircut_eval._mask_summary(events, ~flag, horizons),
            "all_capacity_haircut_candidates": haircut_eval._mask_summary(events, pd.Series(True, index=events.index), horizons),
        },
        "capacity_component_diagnostic": capacity_diagnostic,
        "shuffle_tests": shuffle_tests,
        "symbol_holdout": symbol_holdout,
        "liquidity_bucket_consistency": liquidity_bucket_consistency,
        "delay_robustness": delay_robustness,
    }


def _rank_components(component_reports: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, report in component_reports.items():
        effect = report.get("capacity_component_diagnostic", {}).get("effect", {})
        rows.append(
            {
                "component": name,
                "label": report.get("label"),
                "component_event_count": report.get("component_event_count"),
                "component_fraction": report.get("component_fraction"),
                "short_return_delta_h24": effect.get("short_return_delta"),
                "failed_checks": report.get("failed_checks", []),
                "shuffle_passed": report.get("shuffle_tests", {}).get("passed"),
                "symbol_holdout_passed": report.get("symbol_holdout", {}).get("passed"),
                "liquidity_bucket_consistency_passed": report.get("liquidity_bucket_consistency", {}).get("passed"),
                "delay_robustness_passed": report.get("delay_robustness", {}).get("passed"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            0 if row["label"] == "pass" else 1,
            row["short_return_delta_h24"] if row["short_return_delta_h24"] is not None else 999.0,
        ),
    )


def _write_report(
    *,
    frame: pd.DataFrame,
    meta: dict[str, Any],
    root: Path,
    output_path: Path,
    as_of: str,
    components: list[str],
    shuffle_iterations: int,
) -> dict[str, Any]:
    catalog = _component_catalog(frame)
    unknown = [name for name in components if name not in catalog]
    if unknown:
        raise ValueError(f"Unknown components: {unknown}; known={sorted(catalog)}")
    component_reports = {
        name: _component_report(
            frame,
            name=name,
            mask=catalog[name],
            iterations=shuffle_iterations,
            horizons=tuple(DEFAULT_HORIZONS),
        )
        for name in components
    }
    ranked = _rank_components(component_reports)
    survivors = [row["component"] for row in ranked if row["label"] == "pass"]
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
        "components_tested": components,
        "shuffle_iterations": int(shuffle_iterations),
        "component_reports": component_reports,
        "ranked_components": ranked,
        "pass_fail_decision": {
            "label": "pass" if survivors else "fail",
            "survivor_components": survivors,
            "failed_components": [row["component"] for row in ranked if row["label"] != "pass"],
            "decision_rule": (
                "a component survives only if capacity diagnostic, shuffle, symbol holdout, "
                "liquidity bucket, and +1h/+6h/+24h delay all pass"
            ),
        },
        "next_landing_shape": {
            "recommended_shape": "decompose_passed_components_before_parent_simulator"
            if survivors
            else "aggregate_only_requires_redefinition",
            "next_step": (
                "Use surviving atomic components as explicit switch inputs in the quarantined 1h "
                "parent-interaction simulator; do not use failed components as standalone gates."
            )
            if survivors
            else "Do not proceed to a parent simulator until the aggregate state is redefined.",
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
    output_path = output_dir / "fake_liquidity_atomic_decomposition_1h.json"
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
        components=_parse_components(args.components),
        shuffle_iterations=int(args.shuffle_iterations),
    )
    compact = {
        "output_path": str(output_path),
        "research_id": report["research_id"],
        "loaded_symbol_count": report["data_sources_and_coverage"].get("loaded_symbol_count"),
        "row_count": report["data_sources_and_coverage"].get("row_count"),
        "components_tested": report["components_tested"],
        "ranked_components": report["ranked_components"],
        "pass_fail_decision": report["pass_fail_decision"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
