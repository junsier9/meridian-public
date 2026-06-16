from __future__ import annotations

import argparse
import json
import sys
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

from enhengclaw.compat.naming import getenv_compat  # noqa: E402
from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_stage0 as stage0  # noqa: E402


CONTRACT_VERSION = "m3_2_boundary_activation_falsification.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_RANDOM_ITERATIONS = 80
DEFAULT_SEED = 20260504
DEFAULT_POSITIVE_LABELS = [
    "tron_impulse_short_high_beta_rs",
    "tron_heat_short_high_rs",
    "rebound_long_idio",
    "sell_pressure_short_high_beta_rs",
]
EXPOSURE_COLUMNS = [
    "lead_lag_beta_btc",
    "relative_strength_20",
    "idiosyncratic_share",
    "realized_volatility_20",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 0.5 falsification for sparse M3.2 boundary activation candidates."
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--panel-path", type=Path, default=stage0.DEFAULT_PANEL_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--labels", nargs="*", default=DEFAULT_POSITIVE_LABELS)
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--base-replacement-cost-bps", type=float, default=10.0)
    parser.add_argument("--delay-retention-threshold", type=float, default=0.50)
    return parser


def _iteration_count(value: int | None) -> int:
    if value is not None:
        return max(int(value), 1)
    raw = str(getenv_compat("ENHENGCLAW_M3_2_FALSIFICATION_ITERATIONS") or "").strip()
    if raw:
        try:
            return max(int(raw), 1)
        except ValueError:
            pass
    return DEFAULT_RANDOM_ITERATIONS


def _specs_for_labels(labels: list[str]) -> list[stage0.BoundarySpec]:
    specs = {spec.label: spec for spec in stage0._variant_specs()}
    missing = sorted(set(labels).difference(specs))
    if missing:
        raise ValueError(f"unknown M3.2 boundary labels: {missing}")
    return [specs[label] for label in labels]


def _with_parent_score(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    if "parent_score" not in work.columns:
        work["parent_score"] = stage0.xs_alpha_ontology_v5_score(work)
    return work


def _evaluate_locked(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
) -> dict[str, Any]:
    work = _with_parent_score(frame)
    parent_sides, _parent_changes = stage0._apply_boundary_rule(
        work,
        spec,
        score_column="parent_score",
        apply_replacement=False,
    )
    candidate_sides, candidate_changes = stage0._apply_boundary_rule(
        work,
        spec,
        score_column="parent_score",
    )
    parent_portfolio = stage0._portfolio_from_sides(
        parent_sides,
        target_horizon_bars=target_horizon_bars,
    )
    candidate_portfolio = stage0._portfolio_from_sides(
        candidate_sides,
        target_horizon_bars=target_horizon_bars,
    )
    parent_summary = stage0._summarize_portfolio(parent_portfolio)
    candidate_summary = stage0._summarize_portfolio(candidate_portfolio)
    return {
        "comparison_vs_parent": stage0._compare(candidate_summary, parent_summary, candidate_changes),
        "boundary_change": candidate_changes,
        "parent_portfolio": parent_summary,
        "candidate_portfolio": candidate_summary,
        "parent_sides": parent_sides,
        "candidate_sides": candidate_sides,
    }


def _active_delta(evaluation: dict[str, Any]) -> float | None:
    value = evaluation["comparison_vs_parent"].get("delta_active_long_short_mean")
    return None if value is None else float(value)


def _timestamp_values(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    keep = ["timestamp_ms", "date_utc", *columns]
    return frame[keep].drop_duplicates("timestamp_ms").sort_values("timestamp_ms").reset_index(drop=True)


def _replace_timestamp_values(frame: pd.DataFrame, values: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    work = frame.drop(columns=[column for column in columns if column in frame.columns]).copy()
    return work.merge(values[["timestamp_ms", *columns]], on="timestamp_ms", how="left")


def _delay_state_by_timestamp(frame: pd.DataFrame, spec: stage0.BoundarySpec, *, lags: int = 1) -> pd.DataFrame:
    columns = ["m3_2_panel_ready", spec.state_column]
    values = _timestamp_values(frame, columns)
    delayed = values[["timestamp_ms"]].copy()
    for column in columns:
        delayed[column] = values[column].shift(lags)
    return _replace_timestamp_values(frame, delayed, columns)


def _shuffle_state_by_timestamp(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    rng: np.random.Generator,
) -> pd.DataFrame:
    columns = ["m3_2_panel_ready", spec.state_column]
    values = _timestamp_values(frame, columns)
    shuffled = values[["timestamp_ms"]].copy()
    order = rng.permutation(len(values))
    for column in columns:
        shuffled[column] = values[column].iloc[order].to_numpy()
    return _replace_timestamp_values(frame, shuffled, columns)


def _shuffle_forward_returns_within_timestamp(
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


def _shuffle_exposure_bundle_within_timestamp(
    frame: pd.DataFrame,
    *,
    rng: np.random.Generator,
) -> pd.DataFrame:
    work = frame.copy()
    columns = [column for column in EXPOSURE_COLUMNS if column in work.columns]
    for _timestamp, group in work.groupby("timestamp_ms", sort=False):
        idx = group.index.to_numpy()
        order = rng.permutation(len(idx))
        for column in columns:
            values = work.loc[idx, column].to_numpy(copy=True)
            work.loc[idx, column] = values[order]
    return work


def _random_control(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
    observed_delta: float,
    iterations: int,
    seed: int,
    transform: Callable[[pd.DataFrame, stage0.BoundarySpec, np.random.Generator], pd.DataFrame],
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    deltas: list[float] = []
    for _ in range(iterations):
        transformed = transform(frame, spec, rng)
        evaluation = _evaluate_locked(transformed, spec, target_horizon_bars=target_horizon_bars)
        delta = _active_delta(evaluation)
        if delta is not None and np.isfinite(delta):
            deltas.append(float(delta))
    if not deltas:
        return {"passed": False, "reason": "no_valid_random_deltas", "iterations": int(iterations)}
    values = np.asarray(deltas, dtype="float64")
    q95 = float(np.quantile(values, 0.95))
    mean = float(np.mean(values))
    p_value = float((np.sum(values >= observed_delta) + 1.0) / (len(values) + 1.0))
    return {
        "passed": bool(observed_delta > q95 and p_value <= 0.05),
        "iterations": int(len(values)),
        "random_mean_delta_active_long_short": mean,
        "random_q95_delta_active_long_short": q95,
        "empirical_p_value_random_ge_observed": p_value,
    }


def _delay_test(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
    observed_delta: float,
    retention_threshold: float,
) -> dict[str, Any]:
    delayed = _delay_state_by_timestamp(frame, spec, lags=1)
    evaluation = _evaluate_locked(delayed, spec, target_horizon_bars=target_horizon_bars)
    delta = _active_delta(evaluation)
    retention = None if delta is None or observed_delta <= 0 else float(delta / observed_delta)
    passed = bool(
        delta is not None
        and delta > 0.0005
        and retention is not None
        and retention >= retention_threshold
        and int(evaluation["boundary_change"].get("active_timestamp_count") or 0) >= 10
    )
    return {
        "passed": passed,
        "delta_active_long_short_mean": delta,
        "retention_vs_observed": retention,
        "active_timestamp_count": evaluation["boundary_change"].get("active_timestamp_count"),
        "retention_threshold": float(retention_threshold),
    }


def _cost_stress_test(
    observed_evaluation: dict[str, Any],
    *,
    base_replacement_cost_bps: float,
) -> dict[str, Any]:
    delta = _active_delta(observed_evaluation)
    changes = observed_evaluation["boundary_change"]
    long_change = float(changes.get("long_active_changed_timestamp_fraction") or 0.0)
    short_change = float(changes.get("short_active_changed_timestamp_fraction") or 0.0)
    active_change = max(long_change, short_change)
    two_x_cost_rate = 2.0 * float(base_replacement_cost_bps) / 10000.0
    stressed_delta = None if delta is None else float(delta - two_x_cost_rate * active_change)
    return {
        "passed": bool(stressed_delta is not None and stressed_delta > 0.0005),
        "base_replacement_cost_bps": float(base_replacement_cost_bps),
        "two_x_cost_rate": two_x_cost_rate,
        "active_changed_timestamp_fraction": active_change,
        "cost_stressed_delta_active_long_short_mean": stressed_delta,
    }


def _symbol_holdout_test(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for subject in sorted(frame["subject"].astype(str).unique()):
        held = frame[frame["subject"].astype(str).ne(subject)].copy()
        evaluation = _evaluate_locked(held, spec, target_horizon_bars=target_horizon_bars)
        rows.append(
            {
                "held_out_subject": subject,
                "delta_active_long_short_mean": _active_delta(evaluation),
                "active_timestamp_count": evaluation["boundary_change"].get("active_timestamp_count"),
            }
        )
    deltas = [
        float(row["delta_active_long_short_mean"])
        for row in rows
        if row["delta_active_long_short_mean"] is not None and np.isfinite(row["delta_active_long_short_mean"])
    ]
    if not deltas:
        return {"passed": False, "reason": "no_valid_holdout_deltas", "by_subject": rows}
    positive_fraction = float(np.mean(np.asarray(deltas) > 0.0005))
    min_delta = float(np.min(deltas))
    return {
        "passed": bool(min_delta > 0.0 and positive_fraction >= 0.70),
        "positive_fraction": positive_fraction,
        "min_delta_active_long_short_mean": min_delta,
        "median_delta_active_long_short_mean": float(np.median(deltas)),
        "by_subject": rows,
    }


def _side_bucket_edge(
    parent_sides: pd.DataFrame,
    candidate_sides: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
    min_rows: int = 6,
) -> dict[str, Any]:
    hcol = f"forward_{target_horizon_bars}d_log_return"
    parent = parent_sides[
        parent_sides["side"].eq(spec.side) & parent_sides["_m3_2_active"].fillna(False).astype(bool)
    ]
    candidate = candidate_sides[
        candidate_sides["side"].eq(spec.side) & candidate_sides["_m3_2_active"].fillna(False).astype(bool)
    ]
    buckets = sorted(
        set(parent.get("liquidity_bucket", pd.Series(dtype=str)).dropna().astype(str)).union(
            set(candidate.get("liquidity_bucket", pd.Series(dtype=str)).dropna().astype(str))
        )
    )
    by_bucket: list[dict[str, Any]] = []
    for bucket in buckets:
        parent_values = pd.to_numeric(parent.loc[parent["liquidity_bucket"].astype(str).eq(bucket), hcol], errors="coerce").dropna()
        candidate_values = pd.to_numeric(
            candidate.loc[candidate["liquidity_bucket"].astype(str).eq(bucket), hcol],
            errors="coerce",
        ).dropna()
        row_count = int(min(len(parent_values), len(candidate_values)))
        if row_count < min_rows:
            continue
        parent_mean = float(parent_values.mean())
        candidate_mean = float(candidate_values.mean())
        improvement = candidate_mean - parent_mean if spec.side == "long" else parent_mean - candidate_mean
        by_bucket.append(
            {
                "liquidity_bucket": bucket,
                "row_count": row_count,
                "parent_side_mean": parent_mean,
                "candidate_side_mean": candidate_mean,
                "side_edge_improvement": float(improvement),
            }
        )
    if not by_bucket:
        return {"passed": False, "reason": "no_bucket_with_min_rows", "by_bucket": []}
    improvements = [float(row["side_edge_improvement"]) for row in by_bucket]
    positive_count = sum(value > 0.0 for value in improvements)
    return {
        "passed": bool(len(by_bucket) >= 2 and positive_count == len(by_bucket)),
        "bucket_count": int(len(by_bucket)),
        "positive_bucket_count": int(positive_count),
        "min_bucket_side_edge_improvement": float(min(improvements)),
        "by_bucket": by_bucket,
    }


def _evaluate_falsification(
    frame: pd.DataFrame,
    spec: stage0.BoundarySpec,
    *,
    target_horizon_bars: int,
    iterations: int,
    seed: int,
    base_replacement_cost_bps: float,
    delay_retention_threshold: float,
) -> dict[str, Any]:
    observed = _evaluate_locked(frame, spec, target_horizon_bars=target_horizon_bars)
    observed_delta = _active_delta(observed)
    if observed_delta is None:
        return {
            "label": spec.label,
            "status": "failed",
            "reason": "observed_delta_missing",
            "blocker_codes": ["observed_delta_missing"],
        }

    tests = {
        "delayed_activation": _delay_test(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
            observed_delta=observed_delta,
            retention_threshold=delay_retention_threshold,
        ),
        "active_state_time_shuffle": _random_control(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
            observed_delta=observed_delta,
            iterations=iterations,
            seed=seed + 101,
            transform=lambda work, candidate_spec, rng: _shuffle_state_by_timestamp(
                work,
                candidate_spec,
                rng=rng,
            ),
        ),
        "label_shuffle": _random_control(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
            observed_delta=observed_delta,
            iterations=iterations,
            seed=seed + 202,
            transform=lambda work, _candidate_spec, rng: _shuffle_forward_returns_within_timestamp(
                work,
                target_horizon_bars=target_horizon_bars,
                rng=rng,
            ),
        ),
        "symbol_exposure_shuffle": _random_control(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
            observed_delta=observed_delta,
            iterations=iterations,
            seed=seed + 303,
            transform=lambda work, _candidate_spec, rng: _shuffle_exposure_bundle_within_timestamp(
                work,
                rng=rng,
            ),
        ),
        "symbol_holdout": _symbol_holdout_test(
            frame,
            spec,
            target_horizon_bars=target_horizon_bars,
        ),
        "liquidity_bucket_consistency": _side_bucket_edge(
            observed["parent_sides"],
            observed["candidate_sides"],
            spec,
            target_horizon_bars=target_horizon_bars,
        ),
        "two_x_cost_stress": _cost_stress_test(
            observed,
            base_replacement_cost_bps=base_replacement_cost_bps,
        ),
    }
    blocker_codes = [name + "_failed" for name, payload in tests.items() if not bool(payload.get("passed"))]
    return {
        "label": spec.label,
        "status": "cleared" if not blocker_codes else "failed",
        "credible_incremental_edge": not blocker_codes,
        "blocker_codes": blocker_codes,
        "observed": {
            "comparison_vs_parent": observed["comparison_vs_parent"],
            "boundary_change": observed["boundary_change"],
        },
        "tests": tests,
    }


def _compact(results: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, payload in results.items():
        observed = payload.get("observed", {})
        comparison = observed.get("comparison_vs_parent", {})
        tests = payload.get("tests", {})
        out[label] = {
            "status": payload.get("status"),
            "observed_delta_active_long_short_mean": comparison.get("delta_active_long_short_mean"),
            "passed_tests": [name for name, test in tests.items() if test.get("passed")],
            "blocker_codes": payload.get("blocker_codes", []),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    iterations = _iteration_count(args.iterations)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-m3-2-boundary-activation-falsification"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = stage0._load_frame(
        as_of=str(args.as_of),
        target_horizon_bars=int(args.target_horizon_bars),
        panel_path=Path(args.panel_path),
    )
    frame = _with_parent_score(frame)
    specs = _specs_for_labels(list(args.labels))
    results = {
        spec.label: _evaluate_falsification(
            frame,
            spec,
            target_horizon_bars=int(args.target_horizon_bars),
            iterations=iterations,
            seed=int(args.seed),
            base_replacement_cost_bps=float(args.base_replacement_cost_bps),
            delay_retention_threshold=float(args.delay_retention_threshold),
        )
        for spec in specs
    }
    cleared = [label for label, payload in results.items() if payload.get("status") == "cleared"]
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "target_horizon_bars": int(args.target_horizon_bars),
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "labels": [spec.label for spec in specs],
        "random_iterations": iterations,
        "seed": int(args.seed),
        "base_replacement_cost_bps": float(args.base_replacement_cost_bps),
        "delay_retention_threshold": float(args.delay_retention_threshold),
        "status": "cleared" if cleared else "failed",
        "cleared_variants": cleared,
        "results": results,
    }
    output_path = output_dir / "m3_2_boundary_activation_falsification.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"=== Wrote M3.2 boundary activation falsification report to {output_path}")
    print(json.dumps(_compact(results), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
