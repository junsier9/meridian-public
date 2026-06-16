from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import read_json


ROOT = Path(__file__).resolve().parents[3]
FIXED_SET_COMPARISON_CONTRACT_PATH = ROOT / "config" / "quant_research" / "fixed_set_comparison_contract.json"
FIXED_SET_COMPARISON_CONTRACT_VERSION = "quant_fixed_set_comparison_contract.v1"


def load_fixed_set_comparison_contract(*, path: Path | None = None) -> dict[str, Any]:
    contract_path = (path or FIXED_SET_COMPARISON_CONTRACT_PATH).expanduser().resolve()
    payload = dict(read_json(contract_path))
    contract_version = str(payload.get("contract_version") or "").strip()
    if contract_version != FIXED_SET_COMPARISON_CONTRACT_VERSION:
        raise ValueError(
            "fixed set comparison contract_version mismatch: "
            f"{contract_version or 'missing'}"
        )
    reference_set = [
        dict(item)
        for item in list(payload.get("reference_set") or [])
        if isinstance(item, dict)
    ]
    if not reference_set:
        raise ValueError("fixed set comparison contract missing reference_set")
    return {
        "path": str(contract_path),
        "contract_version": contract_version,
        "applicability": dict(payload.get("applicability") or {}),
        "reference_set": reference_set,
        "bootstrap": dict(payload.get("bootstrap") or {}),
        "promotion_gate": dict(payload.get("promotion_gate") or {}),
    }


def fixed_set_reference_entries(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item)
        for item in list(contract.get("reference_set") or [])
        if isinstance(item, dict)
    ]


def fixed_set_reference_labels(contract: dict[str, Any]) -> list[str]:
    return [
        str(item.get("label") or "").strip()
        for item in fixed_set_reference_entries(contract)
        if str(item.get("label") or "").strip()
    ]


def resolve_fixed_set_candidate_label(*, strategy_id: str | None, contract: dict[str, Any]) -> str:
    normalized = str(strategy_id or "").strip()
    for entry in fixed_set_reference_entries(contract):
        if normalized and normalized in {
            str(entry.get("label") or "").strip(),
            str(entry.get("strategy_id") or "").strip(),
            str(entry.get("experiment_id") or "").strip(),
        }:
            return str(entry.get("label") or normalized).strip()
    return normalized or "candidate"


def fixed_set_comparison_applicability(
    *,
    shape: str,
    bar_interval_ms: int,
    target_horizon_bars: int,
    label_contract_id: str,
    research_lane: str | None,
    contract: dict[str, Any],
) -> dict[str, Any]:
    rules = dict(contract.get("applicability") or {})
    reasons: list[str] = []
    expected_shape = str(rules.get("shape") or "").strip()
    if expected_shape and str(shape).strip() != expected_shape:
        reasons.append("shape_mismatch")
    expected_bar_interval_ms = int(rules.get("bar_interval_ms") or 0)
    if expected_bar_interval_ms and int(bar_interval_ms) != expected_bar_interval_ms:
        reasons.append("bar_interval_mismatch")
    expected_horizon = int(rules.get("target_horizon_bars") or 0)
    if expected_horizon and int(target_horizon_bars) != expected_horizon:
        reasons.append("target_horizon_mismatch")
    allowed_label_contract_ids = {
        str(item).strip()
        for item in list(rules.get("label_contract_ids") or [])
        if str(item).strip()
    }
    if allowed_label_contract_ids and str(label_contract_id).strip() not in allowed_label_contract_ids:
        reasons.append("label_contract_mismatch")
    required_research_lanes = {
        str(item).strip()
        for item in list(rules.get("required_research_lanes") or [])
        if str(item).strip()
    }
    if required_research_lanes and str(research_lane or "").strip() not in required_research_lanes:
        reasons.append("research_lane_mismatch")
    return {
        "applicable": not reasons,
        "reason_codes": sorted(reasons),
        "rules": rules,
    }


def periods_per_year(*, bar_interval_ms: int, evaluation_step_bars: int) -> int:
    return max(int((365 * 24 * 60 * 60 * 1000) / (int(bar_interval_ms) * max(int(evaluation_step_bars), 1))), 1)


def performance_summary(period_returns: pd.Series, *, periods_per_year: int) -> dict[str, float]:
    cleaned = pd.to_numeric(period_returns, errors="coerce").fillna(0.0).astype("float64")
    if cleaned.empty:
        return {"net_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    equity_curve = (1.0 + cleaned).cumprod()
    running_max = equity_curve.cummax()
    drawdown = ((running_max - equity_curve) / running_max.replace(0.0, np.nan)).fillna(0.0)
    std = float(cleaned.std(ddof=0))
    sharpe = 0.0 if std == 0.0 else float(cleaned.mean() / std * math.sqrt(periods_per_year))
    return {
        "net_return": float(equity_curve.iloc[-1] - 1.0),
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.max()) if not drawdown.empty else 0.0,
    }


def extract_period_frame(*, candidate_label: str, walk_forward: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for window_index, window in enumerate(list(walk_forward.get("windows") or [])):
        for period in list(window.get("periods") or []):
            timestamp_ms = int(period["timestamp_ms"])
            rows.append(
                {
                    "candidate_label": candidate_label,
                    "window_index": int(window_index),
                    "timestamp_ms": timestamp_ms,
                    "timestamp_utc": pd.to_datetime(timestamp_ms, unit="ms", utc=True).isoformat().replace("+00:00", "Z"),
                    "net_period_return": float(period["net_period_return"]),
                    "gross_return_before_costs": float(period["gross_return_before_costs"]),
                    "fee_cost_return": float(period["fee_cost_return"]),
                    "slippage_cost_return": float(period["slippage_cost_return"]),
                    "funding_cost_return": float(period["funding_cost_return"]),
                    "borrow_cost_return": float(period["borrow_cost_return"]),
                    "turnover": float(period["turnover"]),
                    "trade_participation_rate": float(period["trade_participation_rate"]),
                    "inventory_participation_rate": float(period["inventory_participation_rate"]),
                    "max_participation_rate": float(period["max_participation_rate"]),
                    "capacity_breach_count": int(period["capacity_breach_count"]),
                }
            )
    period_frame = pd.DataFrame.from_records(rows).sort_values(["timestamp_ms", "window_index"]).reset_index(drop=True)
    if period_frame.empty:
        return period_frame
    if period_frame["timestamp_ms"].duplicated().any():
        raise ValueError(f"{candidate_label} has duplicate OOS period timestamps")
    return period_frame


def auto_block_length(n_periods: int) -> int:
    if n_periods <= 1:
        return 1
    return max(2, min(n_periods, int(round(n_periods ** (1.0 / 3.0)))))


def _two_sided_sign_test(*, wins: int, losses: int) -> float | None:
    n = int(wins) + int(losses)
    if n <= 0:
        return None
    k = min(int(wins), int(losses))
    tail = sum(math.comb(n, idx) for idx in range(k + 1))
    probability = min(1.0, (2.0 * tail) / float(2**n))
    return float(probability)


def _circular_block_sample_indices(
    *,
    length: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    sampled: list[int] = []
    while len(sampled) < length:
        start = int(rng.integers(0, length))
        sampled.extend(int((start + offset) % length) for offset in range(block_length))
    return np.asarray(sampled[:length], dtype="int64")


def paired_block_bootstrap(
    *,
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    periods_per_year: int,
    iterations: int,
    block_length: int,
    seed: int,
) -> dict[str, Any]:
    if len(returns_a) == 0 or len(returns_b) == 0:
        return {
            "iterations": int(iterations),
            "block_length": int(block_length),
            "mean_period_return_diff_ci_95": [0.0, 0.0],
            "cumulative_return_diff_ci_95": [0.0, 0.0],
            "sharpe_diff_ci_95": [0.0, 0.0],
            "probability_a_beats_b_on_cumulative_return": 0.0,
            "probability_a_beats_b_on_sharpe": 0.0,
        }
    rng = np.random.default_rng(seed)
    mean_diffs: list[float] = []
    cumulative_diffs: list[float] = []
    sharpe_diffs: list[float] = []
    cumulative_a_wins = 0
    sharpe_a_wins = 0
    n_periods = len(returns_a)
    for _ in range(iterations):
        indices = _circular_block_sample_indices(length=n_periods, block_length=block_length, rng=rng)
        sample_a = pd.Series(returns_a[indices], dtype="float64")
        sample_b = pd.Series(returns_b[indices], dtype="float64")
        perf_a = performance_summary(sample_a, periods_per_year=periods_per_year)
        perf_b = performance_summary(sample_b, periods_per_year=periods_per_year)
        mean_diffs.append(float(sample_a.mean() - sample_b.mean()))
        cumulative_diffs.append(float(perf_a["net_return"] - perf_b["net_return"]))
        sharpe_diffs.append(float(perf_a["sharpe"] - perf_b["sharpe"]))
        if perf_a["net_return"] > perf_b["net_return"]:
            cumulative_a_wins += 1
        if perf_a["sharpe"] > perf_b["sharpe"]:
            sharpe_a_wins += 1

    def _ci(values: list[float]) -> list[float]:
        return [
            float(np.quantile(values, 0.025)),
            float(np.quantile(values, 0.975)),
        ]

    return {
        "iterations": int(iterations),
        "block_length": int(block_length),
        "mean_period_return_diff_ci_95": _ci(mean_diffs),
        "cumulative_return_diff_ci_95": _ci(cumulative_diffs),
        "sharpe_diff_ci_95": _ci(sharpe_diffs),
        "probability_a_beats_b_on_cumulative_return": float(cumulative_a_wins / iterations),
        "probability_a_beats_b_on_sharpe": float(sharpe_a_wins / iterations),
    }


def pairwise_comparison(
    *,
    label_a: str,
    label_b: str,
    periods_a: pd.DataFrame,
    periods_b: pd.DataFrame,
    periods_per_year: int,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    aligned = periods_a[["timestamp_ms", "timestamp_utc", "net_period_return"]].merge(
        periods_b[["timestamp_ms", "net_period_return"]],
        on="timestamp_ms",
        how="outer",
        suffixes=("_a", "_b"),
        indicator=True,
    ).sort_values("timestamp_ms").reset_index(drop=True)
    both = aligned.loc[aligned["_merge"] == "both"].copy()
    only_a = int((aligned["_merge"] == "left_only").sum())
    only_b = int((aligned["_merge"] == "right_only").sum())
    returns_a = both["net_period_return_a"].astype("float64").to_numpy()
    returns_b = both["net_period_return_b"].astype("float64").to_numpy()
    diff = returns_a - returns_b
    wins = int(np.sum(diff > 0.0))
    losses = int(np.sum(diff < 0.0))
    ties = int(np.sum(diff == 0.0))
    performance_a = performance_summary(pd.Series(returns_a), periods_per_year=periods_per_year)
    performance_b = performance_summary(pd.Series(returns_b), periods_per_year=periods_per_year)
    block_length = auto_block_length(len(both))
    bootstrap = paired_block_bootstrap(
        returns_a=returns_a,
        returns_b=returns_b,
        periods_per_year=periods_per_year,
        iterations=iterations,
        block_length=block_length,
        seed=seed,
    )
    return {
        "candidate_a": label_a,
        "candidate_b": label_b,
        "aligned_period_count": int(len(both)),
        "timestamps_only_in_a": int(only_a),
        "timestamps_only_in_b": int(only_b),
        "observed_mean_period_return_diff": float(diff.mean()) if len(diff) else 0.0,
        "observed_cumulative_return_diff": float(performance_a["net_return"] - performance_b["net_return"]),
        "observed_sharpe_diff": float(performance_a["sharpe"] - performance_b["sharpe"]),
        "period_win_count_a_gt_b": wins,
        "period_loss_count_a_lt_b": losses,
        "period_tie_count": ties,
        "period_win_rate_a_gt_b": float(wins / (wins + losses)) if (wins + losses) else None,
        "sign_test_pvalue": _two_sided_sign_test(wins=wins, losses=losses),
        "bootstrap": bootstrap,
    }


def pairwise_lookup(
    *,
    pairwise_results: list[dict[str, Any]],
    candidate_a: str,
    candidate_b: str,
) -> dict[str, Any] | None:
    for item in pairwise_results:
        left = str(item.get("candidate_a") or "").strip()
        right = str(item.get("candidate_b") or "").strip()
        if left == candidate_a and right == candidate_b:
            return dict(item)
        if left == candidate_b and right == candidate_a:
            flipped = dict(item)
            flipped["candidate_a"] = candidate_a
            flipped["candidate_b"] = candidate_b
            flipped["observed_mean_period_return_diff"] = -float(item.get("observed_mean_period_return_diff", 0.0) or 0.0)
            flipped["observed_cumulative_return_diff"] = -float(item.get("observed_cumulative_return_diff", 0.0) or 0.0)
            flipped["observed_sharpe_diff"] = -float(item.get("observed_sharpe_diff", 0.0) or 0.0)
            flipped["period_win_count_a_gt_b"] = int(item.get("period_loss_count_a_lt_b", 0) or 0)
            flipped["period_loss_count_a_lt_b"] = int(item.get("period_win_count_a_gt_b", 0) or 0)
            bootstrap = dict(item.get("bootstrap") or {})
            flipped["bootstrap"] = dict(bootstrap)
            if "mean_period_return_diff_ci_95" in bootstrap:
                low, high = list(bootstrap["mean_period_return_diff_ci_95"])
                flipped["bootstrap"]["mean_period_return_diff_ci_95"] = [float(-high), float(-low)]
            if "cumulative_return_diff_ci_95" in bootstrap:
                low, high = list(bootstrap["cumulative_return_diff_ci_95"])
                flipped["bootstrap"]["cumulative_return_diff_ci_95"] = [float(-high), float(-low)]
            if "sharpe_diff_ci_95" in bootstrap:
                low, high = list(bootstrap["sharpe_diff_ci_95"])
                flipped["bootstrap"]["sharpe_diff_ci_95"] = [float(-high), float(-low)]
            if "probability_a_beats_b_on_cumulative_return" in bootstrap:
                flipped["bootstrap"]["probability_a_beats_b_on_cumulative_return"] = float(
                    1.0 - float(bootstrap["probability_a_beats_b_on_cumulative_return"])
                )
            if "probability_a_beats_b_on_sharpe" in bootstrap:
                flipped["bootstrap"]["probability_a_beats_b_on_sharpe"] = float(
                    1.0 - float(bootstrap["probability_a_beats_b_on_sharpe"])
                )
            return flipped
    return None


def build_promotion_gate_assessment(
    *,
    candidate_label: str,
    candidate_summaries: list[dict[str, Any]],
    pairwise_results: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    promotion_gate_contract = dict(contract.get("promotion_gate") or {})
    candidate_summary = next(
        (dict(item) for item in candidate_summaries if str(item.get("candidate_label") or "").strip() == candidate_label),
        None,
    )
    if candidate_summary is None:
        return {
            "passed": False,
            "blocker_codes": ["candidate_summary_missing"],
            "control_pairwise": None,
            "best_static_baseline_pairwise": None,
            "rules": promotion_gate_contract,
        }

    blockers: list[str] = []
    control_label = str(promotion_gate_contract.get("control_label") or "").strip()
    best_static_baseline_label = str(promotion_gate_contract.get("best_static_baseline_label") or "").strip()
    best_methodology_baseline_label = str(
        promotion_gate_contract.get("best_methodology_baseline_label") or ""
    ).strip()
    control_pairwise = None
    best_static_pairwise = None
    best_methodology_pairwise = None

    if control_label and candidate_label != control_label:
        control_pairwise = pairwise_lookup(
            pairwise_results=pairwise_results,
            candidate_a=candidate_label,
            candidate_b=control_label,
        )
        if control_pairwise is None:
            blockers.append("missing_control_pairwise")
        else:
            if float(control_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0) < float(
                promotion_gate_contract.get("control_observed_cumulative_return_diff_min", 0.0) or 0.0
            ):
                blockers.append("control_cumulative_return_diff_below_min")
            probability = float(
                dict(control_pairwise.get("bootstrap") or {}).get(
                    "probability_a_beats_b_on_cumulative_return", 0.0
                )
                or 0.0
            )
            if probability < float(
                promotion_gate_contract.get("control_probability_a_beats_b_on_cumulative_return_min", 0.0) or 0.0
            ):
                blockers.append("control_bootstrap_probability_below_min")

    if best_static_baseline_label and candidate_label != best_static_baseline_label:
        best_static_pairwise = pairwise_lookup(
            pairwise_results=pairwise_results,
            candidate_a=candidate_label,
            candidate_b=best_static_baseline_label,
        )
        if best_static_pairwise is None:
            blockers.append("missing_best_static_baseline_pairwise")
        else:
            if float(best_static_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0) < -float(
                promotion_gate_contract.get("best_static_baseline_max_cumulative_return_underperformance", 0.0) or 0.0
            ):
                blockers.append("best_static_baseline_underperformance_too_large")
            if float(best_static_pairwise.get("observed_sharpe_diff", 0.0) or 0.0) < -float(
                promotion_gate_contract.get("best_static_baseline_max_sharpe_underperformance", 0.0) or 0.0
            ):
                blockers.append("best_static_baseline_sharpe_underperformance_too_large")

    if best_methodology_baseline_label and candidate_label != best_methodology_baseline_label:
        best_methodology_pairwise = pairwise_lookup(
            pairwise_results=pairwise_results,
            candidate_a=candidate_label,
            candidate_b=best_methodology_baseline_label,
        )
        if best_methodology_pairwise is None:
            blockers.append("missing_best_methodology_baseline_pairwise")
        else:
            if float(best_methodology_pairwise.get("observed_cumulative_return_diff", 0.0) or 0.0) < -float(
                promotion_gate_contract.get("best_methodology_baseline_max_cumulative_return_underperformance", 0.0)
                or 0.0
            ):
                blockers.append("best_methodology_baseline_underperformance_too_large")
            if float(best_methodology_pairwise.get("observed_sharpe_diff", 0.0) or 0.0) < -float(
                promotion_gate_contract.get("best_methodology_baseline_max_sharpe_underperformance", 0.0) or 0.0
            ):
                blockers.append("best_methodology_baseline_sharpe_underperformance_too_large")

    return {
        "passed": not blockers,
        "blocker_codes": blockers,
        "candidate_summary": candidate_summary,
        "control_pairwise": control_pairwise,
        "best_static_baseline_pairwise": best_static_pairwise,
        "best_methodology_baseline_pairwise": best_methodology_pairwise,
        "rules": promotion_gate_contract,
    }
