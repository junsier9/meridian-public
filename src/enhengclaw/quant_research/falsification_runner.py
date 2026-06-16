from __future__ import annotations

import hashlib
from typing import Any, Callable

import numpy as np
import pandas as pd

from enhengclaw.compat.naming import getenv_compat

from .fixed_set_comparison import pairwise_comparison, periods_per_year


STATISTICAL_FALSIFICATION_CONTRACT_VERSION = "quant_statistical_falsification.v1"
DEFAULT_LABEL_SHUFFLE_ITERATIONS = 120
DEFAULT_SCORE_SHUFFLE_ITERATIONS = 120
DEFAULT_TIME_SHUFFLE_ITERATIONS = 1000
DEFAULT_BUCKET_COUNT_REQUIRED = 2
SUPPORTED_INCREMENTAL_MODEL_FAMILIES = {
    "xs_alpha_ontology_v5_h10d_rw_bridge_spk_short_replace_mid_v1",
    "xs_alpha_ontology_v5_h10d_rw_bridge_mf01_combo_replace_v1",
    "xs_alpha_ontology_v5_h10d_rw_bridge_m3_3_strict_event_state_q1_noise0",
}
SUPPORTED_SUBLANE_PARENT_MODEL_FAMILIES = {
    "r1a_top_liquidity_ex_trx_h10d": "xs_alpha_ontology_v5_h10d_rw_bridge",
}


def _iteration_count(*, env_name: str, default: int) -> int:
    raw_value = str(getenv_compat(env_name) or "").strip()
    if not raw_value:
        return int(default)
    try:
        return max(int(raw_value), 1)
    except ValueError:
        return int(default)


def run_statistical_falsification(
    *,
    experiment_spec: dict[str, Any],
    strategy_entry: dict[str, Any],
    prediction_bundle: dict[str, pd.DataFrame],
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    fit_and_score_fn: Callable[..., dict[str, pd.DataFrame]],
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    model_family = str(experiment_spec.get("model_family") or "").strip()
    label_contract_id = str(experiment_spec.get("label_contract_id") or "").strip()
    shape = str(experiment_spec.get("shape") or "").strip()
    strategy_id = str(strategy_entry.get("strategy_id") or "").strip()
    sublane_parent_model_family = str(SUPPORTED_SUBLANE_PARENT_MODEL_FAMILIES.get(strategy_id) or "").strip()
    if (
        shape != "cross_sectional"
        or label_contract_id != "forward_return_execution_aligned.v1"
        or (
            model_family not in SUPPORTED_INCREMENTAL_MODEL_FAMILIES
            and model_family != sublane_parent_model_family
        )
    ):
        return {
            "contract_version": STATISTICAL_FALSIFICATION_CONTRACT_VERSION,
            "status": "skipped",
            "applicable": False,
            "reason": "unsupported_experiment",
            "blocker_codes": [],
        }
    parent_model_family = _infer_parent_model_family(prediction_bundle=prediction_bundle)
    if not parent_model_family and sublane_parent_model_family:
        parent_model_family = sublane_parent_model_family
    if not parent_model_family:
        return {
            "contract_version": STATISTICAL_FALSIFICATION_CONTRACT_VERSION,
            "status": "failed",
            "applicable": True,
            "reason": "parent_model_family_missing",
            "blocker_codes": ["parent_model_family_missing"],
        }

    candidate_metrics = backtest_cross_sectional_fn(
        prediction_bundle["test"],
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        include_periods=True,
    )
    parent_prediction_bundle = fit_and_score_fn(
        model_family=parent_model_family,
        shape="cross_sectional",
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=feature_columns,
        target_column=target_column,
        model_definition=None,
    )
    parent_metrics = backtest_cross_sectional_fn(
        parent_prediction_bundle["test"],
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        include_periods=True,
    )
    period_frame_candidate = _period_frame(candidate_metrics, label="candidate")
    period_frame_parent = _period_frame(parent_metrics, label="parent")
    observed = _pairwise(
        periods_a=period_frame_candidate,
        periods_b=period_frame_parent,
        label_a="candidate",
        label_b="parent",
        split_realization_contract=split_realization_contract,
        seed=20260503,
    )
    time_shuffle_iterations = _iteration_count(
        env_name="ENHENGCLAW_STAT_FALSIFICATION_TIME_ITERATIONS",
        default=DEFAULT_TIME_SHUFFLE_ITERATIONS,
    )
    score_shuffle_iterations = _iteration_count(
        env_name="ENHENGCLAW_STAT_FALSIFICATION_SCORE_ITERATIONS",
        default=DEFAULT_SCORE_SHUFFLE_ITERATIONS,
    )
    label_shuffle_iterations = _iteration_count(
        env_name="ENHENGCLAW_STAT_FALSIFICATION_LABEL_ITERATIONS",
        default=DEFAULT_LABEL_SHUFFLE_ITERATIONS,
    )

    time_shuffle = _time_shuffle_test(
        candidate_test_frame=prediction_bundle["test"],
        parent_periods=period_frame_parent,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        backtest_cross_sectional_fn=backtest_cross_sectional_fn,
        observed=observed,
        iterations=time_shuffle_iterations,
    )
    score_shuffle = _score_shuffle_test(
        candidate_test_frame=prediction_bundle["test"],
        parent_periods=period_frame_parent,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        backtest_cross_sectional_fn=backtest_cross_sectional_fn,
        observed=observed,
        iterations=score_shuffle_iterations,
    )
    label_shuffle = _label_shuffle_test(
        model_family=model_family,
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=feature_columns,
        target_column=target_column,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        fit_and_score_fn=fit_and_score_fn,
        backtest_cross_sectional_fn=backtest_cross_sectional_fn,
        parent_periods=period_frame_parent,
        observed=observed,
        iterations=label_shuffle_iterations,
    )
    delayed_execution = _delay_stress_test(
        candidate_test_frame=prediction_bundle["test"],
        parent_test_frame=parent_prediction_bundle["test"],
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        backtest_cross_sectional_fn=backtest_cross_sectional_fn,
    )
    cost_stress = _cost_stress_test(
        candidate_test_frame=prediction_bundle["test"],
        parent_test_frame=parent_prediction_bundle["test"],
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        backtest_cross_sectional_fn=backtest_cross_sectional_fn,
    )
    symbol_holdout = _symbol_holdout_test(
        model_family=model_family,
        parent_model_family=parent_model_family,
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=feature_columns,
        target_column=target_column,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        fit_and_score_fn=fit_and_score_fn,
        backtest_cross_sectional_fn=backtest_cross_sectional_fn,
        observed=observed,
    )
    liquidity_bucket_consistency = _liquidity_bucket_consistency_test(
        candidate_test_frame=prediction_bundle["test"],
        parent_test_frame=parent_prediction_bundle["test"],
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        backtest_cross_sectional_fn=backtest_cross_sectional_fn,
    )

    blocker_codes: list[str] = []
    if not time_shuffle["passed"]:
        blocker_codes.append("time_shuffle_failed")
    if not score_shuffle["passed"]:
        blocker_codes.append("symbol_shuffle_failed")
    if not label_shuffle["passed"]:
        blocker_codes.append("label_shuffle_failed")
    if not delayed_execution["passed"]:
        blocker_codes.append("delay_stress_failed")
    if not cost_stress["passed"]:
        blocker_codes.append("cost_stress_failed")
    if not symbol_holdout["passed"]:
        blocker_codes.append("symbol_holdout_failed")
    if not liquidity_bucket_consistency["passed"]:
        blocker_codes.append("liquidity_bucket_consistency_failed")

    return {
        "contract_version": STATISTICAL_FALSIFICATION_CONTRACT_VERSION,
        "applicable": True,
        "status": "cleared" if not blocker_codes else "failed",
        "candidate_model_family": model_family,
        "parent_model_family": parent_model_family,
        "observed_candidate_vs_parent": observed,
        "iteration_config": {
            "time_shuffle_iterations": time_shuffle_iterations,
            "score_shuffle_iterations": score_shuffle_iterations,
            "label_shuffle_iterations": label_shuffle_iterations,
        },
        "tests": {
            "time_shuffle": time_shuffle,
            "symbol_shuffle": score_shuffle,
            "label_shuffle": label_shuffle,
            "delayed_execution": delayed_execution,
            "cost_stress": cost_stress,
            "symbol_holdout": symbol_holdout,
            "liquidity_bucket_consistency": liquidity_bucket_consistency,
        },
        "credible_incremental_edge": not blocker_codes,
        "blocker_codes": blocker_codes,
        "strategy_id": strategy_id,
    }


def _infer_parent_model_family(*, prediction_bundle: dict[str, pd.DataFrame]) -> str:
    fit_metadata = dict(prediction_bundle.get("fit_metadata") or {})
    spk_boundary_rule = dict(fit_metadata.get("spk_boundary_rule") or {})
    return str(
        fit_metadata.get("parent_model_family")
        or spk_boundary_rule.get("parent_model_family")
        or ""
    ).strip()


def _period_frame(metrics: dict[str, Any], *, label: str) -> pd.DataFrame:
    periods = pd.DataFrame.from_records(list(metrics.get("periods") or []))
    if periods.empty:
        return pd.DataFrame(columns=["candidate_label", "timestamp_ms", "timestamp_utc", "net_period_return"])
    periods = periods.copy()
    if "timestamp_ms" not in periods.columns:
        if "timestamp_utc" not in periods.columns:
            raise KeyError("period metrics missing timestamp_ms and timestamp_utc")
        timestamp_utc = pd.to_datetime(periods["timestamp_utc"], utc=True, errors="coerce")
        periods["timestamp_ms"] = (
            timestamp_utc.view("int64") // 1_000_000
        ).where(timestamp_utc.notna())
    if "timestamp_utc" not in periods.columns:
        timestamp_ms = pd.to_numeric(periods["timestamp_ms"], errors="coerce")
        timestamp_utc = pd.to_datetime(timestamp_ms, unit="ms", utc=True, errors="coerce")
        periods["timestamp_utc"] = timestamp_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ").where(timestamp_utc.notna())
    periods["candidate_label"] = label
    return periods[["candidate_label", "timestamp_ms", "timestamp_utc", "net_period_return"]].copy()


def _pairwise(
    *,
    periods_a: pd.DataFrame,
    periods_b: pd.DataFrame,
    label_a: str,
    label_b: str,
    split_realization_contract: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    return pairwise_comparison(
        label_a=label_a,
        label_b=label_b,
        periods_a=periods_a,
        periods_b=periods_b,
        periods_per_year=periods_per_year(
            bar_interval_ms=int(split_realization_contract.get("bar_interval_ms", 86_400_000) or 86_400_000),
            evaluation_step_bars=int(split_realization_contract.get("realization_step_bars", 1) or 1),
        ),
        iterations=800,
        seed=seed,
    )


def _time_shuffle_test(
    *,
    candidate_test_frame: pd.DataFrame,
    parent_periods: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
    observed: dict[str, Any],
    iterations: int,
) -> dict[str, Any]:
    if candidate_test_frame.empty:
        return {"passed": False, "reason": "insufficient_periods", "iterations": 0}
    observed_cum = float(observed.get("observed_cumulative_return_diff", 0.0) or 0.0)
    observed_sharpe = float(observed.get("observed_sharpe_diff", 0.0) or 0.0)
    rng = np.random.default_rng(20260503)
    shuffled_cum_diffs: list[float] = []
    shuffled_sharpes: list[float] = []
    for _ in range(iterations):
        shuffled = _time_shift_scores_by_subject(
            frame=candidate_test_frame,
            rng=rng,
        )
        shuffled_metrics = backtest_cross_sectional_fn(
            shuffled,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        shuffled_pairwise = _pairwise(
            periods_a=_period_frame(shuffled_metrics, label="time_shuffled"),
            periods_b=parent_periods,
            label_a="time_shuffled",
            label_b="parent",
            split_realization_contract=split_realization_contract,
            seed=20260503,
        )
        shuffled_cum_diffs.append(float(shuffled_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0))
        shuffled_sharpes.append(float(shuffled_pairwise.get("observed_sharpe_diff", 0.0) or 0.0))
    cum_quantile = float(np.mean(np.asarray(shuffled_cum_diffs) <= observed_cum))
    sharpe_quantile = float(np.mean(np.asarray(shuffled_sharpes) <= observed_sharpe))
    passed = cum_quantile >= 0.95 and sharpe_quantile >= 0.95
    return {
        "passed": passed,
        "iterations": int(iterations),
        "observed_cumulative_return_diff": observed_cum,
        "observed_sharpe_diff": observed_sharpe,
        "observed_cumulative_return_quantile": cum_quantile,
        "observed_sharpe_quantile": sharpe_quantile,
    }


def _score_shuffle_test(
    *,
    candidate_test_frame: pd.DataFrame,
    parent_periods: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
    observed: dict[str, Any],
    iterations: int,
) -> dict[str, Any]:
    if candidate_test_frame.empty:
        return {"passed": False, "reason": "empty_candidate_test_frame", "iterations": 0}
    rng = np.random.default_rng(20260504)
    shuffled_diffs: list[float] = []
    shuffled_sharpes: list[float] = []
    for _ in range(iterations):
        shuffled = candidate_test_frame.copy()
        shuffled = _shuffle_frame_columns_within_timestamp(
            frame=shuffled,
            columns=["score"],
            rng=rng,
        )
        shuffled_metrics = backtest_cross_sectional_fn(
            shuffled,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        shuffled_pairwise = _pairwise(
            periods_a=_period_frame(shuffled_metrics, label="shuffled"),
            periods_b=parent_periods,
            label_a="shuffled",
            label_b="parent",
            split_realization_contract=split_realization_contract,
            seed=20260504,
        )
        shuffled_diffs.append(float(shuffled_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0))
        shuffled_sharpes.append(float(shuffled_pairwise.get("observed_sharpe_diff", 0.0) or 0.0))
    observed_cum = float(observed.get("observed_cumulative_return_diff", 0.0) or 0.0)
    observed_sharpe = float(observed.get("observed_sharpe_diff", 0.0) or 0.0)
    cum_quantile = float(np.mean(np.asarray(shuffled_diffs) <= observed_cum))
    sharpe_quantile = float(np.mean(np.asarray(shuffled_sharpes) <= observed_sharpe))
    return {
        "passed": cum_quantile >= 0.90 and sharpe_quantile >= 0.90,
        "iterations": int(iterations),
        "observed_cumulative_return_diff": observed_cum,
        "observed_sharpe_diff": observed_sharpe,
        "observed_cumulative_return_quantile": cum_quantile,
        "observed_sharpe_quantile": sharpe_quantile,
    }


def _label_shuffle_test(
    *,
    model_family: str,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    fit_and_score_fn: Callable[..., dict[str, pd.DataFrame]],
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
    parent_periods: pd.DataFrame,
    observed: dict[str, Any],
    iterations: int,
) -> dict[str, Any]:
    if train_df.empty:
        return {"passed": False, "reason": "empty_train_frame", "iterations": 0}
    rng = np.random.default_rng(20260505)
    shuffled_diffs: list[float] = []
    shuffled_sharpes: list[float] = []
    label_columns = [
        column
        for column in (
            "target_execution_forward_return",
            "target_execution_forward_return_raw",
            "target_execution_up",
            "target_execution_is_neutral",
            "target_execution_class",
        )
        if column in train_df.columns
    ]
    if "target_execution_forward_return" not in label_columns:
        return {"passed": False, "reason": "missing_execution_label_columns", "iterations": 0}
    for _ in range(iterations):
        shuffled_train = train_df.copy()
        shuffled_train = _shuffle_frame_columns_within_timestamp(
            frame=shuffled_train,
            columns=label_columns,
            rng=rng,
        )
        shuffled_prediction = fit_and_score_fn(
            model_family=model_family,
            shape="cross_sectional",
            train_df=shuffled_train,
            validation_df=validation_df,
            test_df=test_df,
            feature_columns=feature_columns,
            target_column=target_column,
            model_definition=None,
        )
        shuffled_metrics = backtest_cross_sectional_fn(
            shuffled_prediction["test"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        shuffled_pairwise = _pairwise(
            periods_a=_period_frame(shuffled_metrics, label="label_shuffled"),
            periods_b=parent_periods,
            label_a="label_shuffled",
            label_b="parent",
            split_realization_contract=split_realization_contract,
            seed=20260505,
        )
        shuffled_diffs.append(float(shuffled_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0))
        shuffled_sharpes.append(float(shuffled_pairwise.get("observed_sharpe_diff", 0.0) or 0.0))
    observed_cum = float(observed.get("observed_cumulative_return_diff", 0.0) or 0.0)
    observed_sharpe = float(observed.get("observed_sharpe_diff", 0.0) or 0.0)
    cum_quantile = float(np.mean(np.asarray(shuffled_diffs) <= observed_cum))
    sharpe_quantile = float(np.mean(np.asarray(shuffled_sharpes) <= observed_sharpe))
    return {
        "passed": cum_quantile >= 0.90 and sharpe_quantile >= 0.90,
        "iterations": int(iterations),
        "observed_cumulative_return_diff": observed_cum,
        "observed_sharpe_diff": observed_sharpe,
        "observed_cumulative_return_quantile": cum_quantile,
        "observed_sharpe_quantile": sharpe_quantile,
    }


def _delay_stress_test(
    *,
    candidate_test_frame: pd.DataFrame,
    parent_test_frame: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for delay in (1, 2):
        delayed_model = dict(execution_cost_model)
        delayed_model["latency_bars"] = int(execution_cost_model.get("latency_bars", 1) or 1) + delay
        candidate_metrics = backtest_cross_sectional_fn(
            candidate_test_frame,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=delayed_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        parent_metrics = backtest_cross_sectional_fn(
            parent_test_frame,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=delayed_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        pairwise = _pairwise(
            periods_a=_period_frame(candidate_metrics, label=f"delay_{delay}"),
            periods_b=_period_frame(parent_metrics, label=f"delay_parent_{delay}"),
            label_a=f"delay_{delay}",
            label_b=f"delay_parent_{delay}",
            split_realization_contract=split_realization_contract,
            seed=20260510 + delay,
        )
        scenarios.append(
            {
                "delay_bars_added": delay,
                "candidate_vs_parent": pairwise,
            }
        )
    hard_scenario = next((scenario for scenario in scenarios if int(scenario["delay_bars_added"]) == 1), None)
    hard_diff = float(dict(hard_scenario or {}).get("candidate_vs_parent", {}).get("observed_cumulative_return_diff", 0.0) or 0.0)
    return {
        "passed": hard_diff > 0.0,
        "scenarios": scenarios,
    }


def _cost_stress_test(
    *,
    candidate_test_frame: pd.DataFrame,
    parent_test_frame: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for multiplier in (1.5, 2.0):
        stressed_model = _scaled_execution_cost_model(execution_cost_model, multiplier=multiplier)
        candidate_metrics = backtest_cross_sectional_fn(
            candidate_test_frame,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=stressed_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        parent_metrics = backtest_cross_sectional_fn(
            parent_test_frame,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=stressed_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        pairwise = _pairwise(
            periods_a=_period_frame(candidate_metrics, label=f"cost_{multiplier}"),
            periods_b=_period_frame(parent_metrics, label=f"cost_parent_{multiplier}"),
            label_a=f"cost_{multiplier}",
            label_b=f"cost_parent_{multiplier}",
            split_realization_contract=split_realization_contract,
            seed=20260520 + int(multiplier * 10),
        )
        scenarios.append(
            {
                "cost_multiplier": multiplier,
                "candidate_vs_parent": pairwise,
            }
        )
    hard_scenario = next((scenario for scenario in scenarios if float(scenario["cost_multiplier"]) == 2.0), None)
    hard_diff = float(dict(hard_scenario or {}).get("candidate_vs_parent", {}).get("observed_cumulative_return_diff", 0.0) or 0.0)
    return {
        "passed": hard_diff > 0.0,
        "scenarios": scenarios,
    }


def _symbol_holdout_test(
    *,
    model_family: str,
    parent_model_family: str,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    fit_and_score_fn: Callable[..., dict[str, pd.DataFrame]],
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
    observed: dict[str, Any],
) -> dict[str, Any]:
    observed_diff = float(observed.get("observed_cumulative_return_diff", 0.0) or 0.0)
    if observed_diff <= 0.0:
        return {"passed": False, "reason": "non_positive_observed_edge", "holdouts": []}
    holdouts: list[dict[str, Any]] = []
    subjects = sorted({str(item).strip() for item in test_df["subject"].dropna().astype(str).tolist() if str(item).strip()})
    sign_flip_subjects: list[str] = []
    for subject in subjects:
        held_train = train_df.loc[train_df["subject"].astype(str) != subject].copy()
        held_validation = validation_df.loc[validation_df["subject"].astype(str) != subject].copy()
        held_test = test_df.loc[test_df["subject"].astype(str) != subject].copy()
        if held_train.empty or held_test.empty:
            continue
        candidate_prediction = fit_and_score_fn(
            model_family=model_family,
            shape="cross_sectional",
            train_df=held_train,
            validation_df=held_validation,
            test_df=held_test,
            feature_columns=feature_columns,
            target_column=target_column,
            model_definition=None,
        )
        parent_prediction = fit_and_score_fn(
            model_family=parent_model_family,
            shape="cross_sectional",
            train_df=held_train,
            validation_df=held_validation,
            test_df=held_test,
            feature_columns=feature_columns,
            target_column=target_column,
            model_definition=None,
        )
        candidate_metrics = backtest_cross_sectional_fn(
            candidate_prediction["test"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        parent_metrics = backtest_cross_sectional_fn(
            parent_prediction["test"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        pairwise = _pairwise(
            periods_a=_period_frame(candidate_metrics, label=f"holdout_{subject}_candidate"),
            periods_b=_period_frame(parent_metrics, label=f"holdout_{subject}_parent"),
            label_a=f"holdout_{subject}_candidate",
            label_b=f"holdout_{subject}_parent",
            split_realization_contract=split_realization_contract,
            seed=_seed_from_subject(subject),
        )
        cumulative_diff = float(pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0)
        if cumulative_diff <= 0.0:
            sign_flip_subjects.append(subject)
        holdouts.append(
            {
                "subject": subject,
                "candidate_vs_parent": pairwise,
            }
        )
    return {
        "passed": not sign_flip_subjects,
        "sign_flip_subjects": sign_flip_subjects,
        "holdouts": holdouts,
    }


def _liquidity_bucket_consistency_test(
    *,
    candidate_test_frame: pd.DataFrame,
    parent_test_frame: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    backtest_cross_sectional_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    if "liquidity_bucket" not in candidate_test_frame.columns:
        return {"passed": False, "reason": "liquidity_bucket_missing", "buckets": []}
    buckets: list[dict[str, Any]] = []
    positive_bucket_count = 0
    for bucket in sorted({str(item).strip() for item in candidate_test_frame["liquidity_bucket"].dropna().astype(str).tolist() if str(item).strip()}):
        candidate_bucket = candidate_test_frame.loc[candidate_test_frame["liquidity_bucket"].astype(str) == bucket].copy()
        parent_bucket = parent_test_frame.loc[parent_test_frame["liquidity_bucket"].astype(str) == bucket].copy()
        if candidate_bucket.empty or parent_bucket.empty:
            continue
        candidate_metrics = backtest_cross_sectional_fn(
            candidate_bucket,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        parent_metrics = backtest_cross_sectional_fn(
            parent_bucket,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        pairwise = _pairwise(
            periods_a=_period_frame(candidate_metrics, label=f"bucket_{bucket}_candidate"),
            periods_b=_period_frame(parent_metrics, label=f"bucket_{bucket}_parent"),
            label_a=f"bucket_{bucket}_candidate",
            label_b=f"bucket_{bucket}_parent",
            split_realization_contract=split_realization_contract,
            seed=_seed_from_subject(bucket),
        )
        cumulative_diff = float(pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0)
        if cumulative_diff > 0.0:
            positive_bucket_count += 1
        buckets.append({"liquidity_bucket": bucket, "candidate_vs_parent": pairwise})
    return {
        "passed": positive_bucket_count >= DEFAULT_BUCKET_COUNT_REQUIRED,
        "positive_bucket_count": positive_bucket_count,
        "buckets": buckets,
    }


def _scaled_execution_cost_model(execution_cost_model: dict[str, Any], *, multiplier: float) -> dict[str, Any]:
    stressed = dict(execution_cost_model)
    stressed["spot_short_borrow_bps_per_day"] = float(execution_cost_model.get("spot_short_borrow_bps_per_day", 0.0) or 0.0) * multiplier
    stressed["liquidity_volume_scale"] = float(execution_cost_model.get("liquidity_volume_scale", 1.0) or 1.0) / multiplier
    venues: dict[str, Any] = {}
    for venue_name, venue_payload in dict(execution_cost_model.get("venues") or {}).items():
        resolved = dict(venue_payload or {})
        venues[str(venue_name)] = {
            "fee_bps_one_way": float(resolved.get("fee_bps_one_way", 0.0) or 0.0) * multiplier,
            "half_spread_bps": float(resolved.get("half_spread_bps", 0.0) or 0.0) * multiplier,
            "impact_coefficient_bps": float(resolved.get("impact_coefficient_bps", 0.0) or 0.0) * multiplier,
        }
    stressed["venues"] = venues
    return stressed


def _seed_from_subject(subject: str) -> int:
    return int(hashlib.sha1(subject.encode("utf-8")).hexdigest()[:8], 16)


def _shuffle_frame_columns_within_timestamp(
    *,
    frame: pd.DataFrame,
    columns: list[str],
    rng: np.random.Generator,
) -> pd.DataFrame:
    shuffled = frame.copy().reset_index(drop=True)
    available_columns = [column for column in columns if column in shuffled.columns]
    if not available_columns or "timestamp_ms" not in shuffled.columns:
        return shuffled
    grouped_indices = shuffled.groupby("timestamp_ms", sort=False).indices
    for row_indices in grouped_indices.values():
        index_list = list(row_indices)
        if len(index_list) <= 1:
            continue
        current_values = shuffled.loc[index_list, available_columns].to_numpy(copy=True)
        shuffled.loc[index_list, available_columns] = current_values[rng.permutation(len(index_list))]
    return shuffled


def _time_shift_scores_by_subject(
    *,
    frame: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    shifted = frame.sort_values(["subject", "timestamp_ms"]).reset_index(drop=True).copy()
    if shifted.empty or "subject" not in shifted.columns or "score" not in shifted.columns:
        return shifted
    grouped_indices = shifted.groupby("subject", sort=False).indices
    for row_indices in grouped_indices.values():
        index_list = list(row_indices)
        if len(index_list) <= 1:
            continue
        offset = int(rng.integers(1, len(index_list)))
        current_values = shifted.loc[index_list, "score"].to_numpy(copy=True)
        shifted.loc[index_list, "score"] = np.roll(current_values, offset)
    return shifted
