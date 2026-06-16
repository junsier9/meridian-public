from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.execution_backtest import filter_cross_sectional_execution_frame
from enhengclaw.quant_research.fixed_set_comparison import (
    fixed_set_reference_entries,
    load_fixed_set_comparison_contract,
)
from enhengclaw.quant_research.lab import (
    QUANT_ARTIFACTS_ROOT,
    _apply_universe_filter,
    _experiment_directory_name,
    _resolved_execution_cost_models,
    _run_walk_forward,
)
from enhengclaw.quant_research.validation_contract import (
    execution_capacity_limits,
    validation_contract_reference_capital_usd,
)


FIXED_SET_CONTRACT = load_fixed_set_comparison_contract()
DEFAULT_CANDIDATES: tuple[tuple[str, str], ...] = tuple(
    (
        str(entry.get("label") or "").strip(),
        str(entry.get("experiment_id") or "").strip(),
    )
    for entry in fixed_set_reference_entries(FIXED_SET_CONTRACT)
    if str(entry.get("label") or "").strip() and str(entry.get("experiment_id") or "").strip()
)
H10D_VALIDATION_CONTRACT_PATH = ROOT / "config" / "quant_research" / "validation_contract_h10d.json"
BOOTSTRAP_SEED = int(dict(FIXED_SET_CONTRACT.get("bootstrap") or {}).get("seed", 20260502) or 20260502)
BOOTSTRAP_ITERATIONS = int(dict(FIXED_SET_CONTRACT.get("bootstrap") or {}).get("iterations", 4000) or 4000)


def _resolve_repo_path(path_text: str | Path) -> Path:
    candidate = Path(str(path_text))
    if candidate.is_absolute():
        return candidate
    return (ROOT / candidate).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_candidate_artifact(experiment_id: str, *, artifacts_root: Path) -> dict[str, Any]:
    experiment_root = artifacts_root / "experiments" / _experiment_directory_name(experiment_id)
    if not experiment_root.exists():
        raise FileNotFoundError(f"experiment artifact missing: {experiment_root}")
    experiment_spec = _read_json(experiment_root / "experiment_spec.json")
    validation_report = _read_json(experiment_root / "validation_report.json")
    feature_manifest = _read_json(_resolve_repo_path(experiment_spec["feature_manifest_path"]))
    return {
        "label": "",
        "experiment_id": experiment_id,
        "experiment_root": experiment_root,
        "experiment_spec": experiment_spec,
        "validation_report": validation_report,
        "feature_manifest": feature_manifest,
        "profile_constraints_override": {},
    }


def _periods_per_year(*, bar_interval_ms: int, evaluation_step_bars: int) -> int:
    return max(int((365 * 24 * 60 * 60 * 1000) / (int(bar_interval_ms) * max(int(evaluation_step_bars), 1))), 1)


def _performance_summary(period_returns: pd.Series, *, periods_per_year: int) -> dict[str, float]:
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


def _two_sided_sign_test(*, wins: int, losses: int) -> float | None:
    n = int(wins) + int(losses)
    if n <= 0:
        return None
    k = min(int(wins), int(losses))
    tail = sum(math.comb(n, idx) for idx in range(k + 1))
    probability = min(1.0, (2.0 * tail) / float(2**n))
    return float(probability)


def _auto_block_length(n_periods: int) -> int:
    if n_periods <= 1:
        return 1
    return max(2, min(n_periods, int(round(n_periods ** (1.0 / 3.0)))))


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


def _paired_block_bootstrap(
    *,
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    periods_per_year: int,
    iterations: int,
    block_length: int,
    seed: int,
) -> dict[str, Any]:
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
        perf_a = _performance_summary(sample_a, periods_per_year=periods_per_year)
        perf_b = _performance_summary(sample_b, periods_per_year=periods_per_year)
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


def _reported_worst_regime(report: dict[str, Any]) -> float | None:
    if report.get("worst_regime_median_oos_sharpe") is not None:
        return float(report["worst_regime_median_oos_sharpe"])
    regime_holdout = dict(report.get("regime_holdout") or {})
    value = regime_holdout.get("worst_regime_median_oos_sharpe")
    if value is None:
        return None
    return float(value)


def _reported_execution_stress_max_trade_participation_rate(report: dict[str, Any]) -> float | None:
    if report.get("execution_stress_max_trade_participation_rate") is not None:
        return float(report["execution_stress_max_trade_participation_rate"])
    execution_stress = dict(report.get("execution_stress") or {})
    value = execution_stress.get("max_trade_participation_rate")
    if value is None:
        return None
    return float(value)


def _build_constraints(
    *,
    experiment_spec: dict[str, Any],
    feature_manifest: dict[str, Any],
    profile_constraints_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    constraints = dict(experiment_spec.get("profile_constraints") or {})
    for key, value in dict(profile_constraints_override or {}).items():
        if value is None:
            constraints.pop(str(key), None)
        else:
            constraints[str(key)] = value
    constraints["strategy_profile"] = str(experiment_spec.get("strategy_profile") or "")
    overlay_context = {
        "features_path": str(feature_manifest.get("features_path") or ""),
        "feature_manifest_path": str(experiment_spec.get("feature_manifest_path") or ""),
        "universe_snapshot_path": str(feature_manifest.get("universe_snapshot_path") or ""),
    }
    if any(str(value).strip() for value in overlay_context.values()):
        constraints["position_multiplier_overlay_context"] = overlay_context
    return constraints


def _load_shared_feature_frame(candidate_artifacts: list[dict[str, Any]]) -> pd.DataFrame:
    feature_manifest_paths = {
        str(item["experiment_spec"].get("feature_manifest_path") or "").strip()
        for item in candidate_artifacts
    }
    if len(feature_manifest_paths) != 1:
        raise ValueError(f"fixed-set comparison expects a shared feature manifest, got: {sorted(feature_manifest_paths)}")
    shared_manifest = candidate_artifacts[0]["feature_manifest"]
    features_path = _resolve_repo_path(shared_manifest["features_path"])
    return pd.read_csv(features_path, low_memory=False)


def _extract_period_frame(
    *,
    candidate_label: str,
    walk_forward: dict[str, Any],
) -> pd.DataFrame:
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
        raise ValueError(f"{candidate_label} has duplicate OOS period timestamps; cannot form paired panel safely")
    return period_frame


def _recompute_candidate_walk_forward(
    *,
    feature_frame: pd.DataFrame,
    candidate_artifact: dict[str, Any],
    validation_contract: dict[str, Any],
    base_execution_cost_model: dict[str, Any],
    stress_execution_cost_model: dict[str, Any],
) -> dict[str, Any]:
    spec = candidate_artifact["experiment_spec"]
    feature_manifest = candidate_artifact["feature_manifest"]
    frame = _apply_universe_filter(feature_frame, universe_filter=spec.get("universe_filter"))
    constraints = _build_constraints(
        experiment_spec=spec,
        feature_manifest=feature_manifest,
        profile_constraints_override=dict(candidate_artifact.get("profile_constraints_override") or {}),
    )
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    walk_forward = _run_walk_forward(
        frame=frame,
        shape=str(spec.get("shape") or "cross_sectional"),
        model_family=str(spec["model_family"]),
        feature_columns=list(spec.get("feature_columns") or []),
        constraints=constraints,
        split_realization_contract=dict(spec["split_realization_contract"]),
        target_column=str(spec.get("target_column") or "target_up"),
        execution_cost_model=base_execution_cost_model,
        stress_execution_cost_model=stress_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=execution_capacity_limits(validation_contract),
        validation_contract=validation_contract,
        model_definition=None,
        include_periods=True,
    )
    periods = _extract_period_frame(candidate_label=candidate_artifact["label"], walk_forward=walk_forward)
    periods_per_year = _periods_per_year(
        bar_interval_ms=int(spec["split_realization_contract"]["bar_interval_ms"]),
        evaluation_step_bars=int(spec["split_realization_contract"]["realization_step_bars"]),
    )
    performance = _performance_summary(periods["net_period_return"], periods_per_year=periods_per_year)
    loss_period_fraction = (
        float((periods["net_period_return"] < 0.0).mean())
        if not periods.empty
        else 0.0
    )
    summary = {
        "candidate_label": candidate_artifact["label"],
        "experiment_id": str(candidate_artifact["experiment_id"]),
        "reported_walk_forward_median_oos_sharpe": float(
            candidate_artifact["validation_report"].get("walk_forward_median_oos_sharpe")
            or candidate_artifact["validation_report"].get("walk_forward", {}).get("median_oos_sharpe")
            or 0.0
        ),
        "recomputed_walk_forward_median_oos_sharpe": float(walk_forward.get("median_oos_sharpe") or 0.0),
        "reported_worst_regime_median_oos_sharpe": _reported_worst_regime(candidate_artifact["validation_report"]),
        "reported_execution_stress_max_trade_participation_rate": _reported_execution_stress_max_trade_participation_rate(
            candidate_artifact["validation_report"]
        ),
        "full_oos_period_count": int(len(periods)),
        "full_oos_start_utc": str(periods["timestamp_utc"].iloc[0]) if not periods.empty else None,
        "full_oos_end_utc": str(periods["timestamp_utc"].iloc[-1]) if not periods.empty else None,
        "full_oos_cumulative_net_return": float(performance["net_return"]),
        "full_oos_period_sharpe": float(performance["sharpe"]),
        "full_oos_max_drawdown": float(performance["max_drawdown"]),
        "full_oos_loss_period_fraction": float(loss_period_fraction),
        "full_oos_mean_period_return": float(periods["net_period_return"].mean()) if not periods.empty else 0.0,
        "full_oos_turnover_total": float(periods["turnover"].sum()) if not periods.empty else 0.0,
        "full_oos_max_trade_participation_rate": float(periods["trade_participation_rate"].max()) if not periods.empty else 0.0,
    }
    return {
        "walk_forward": walk_forward,
        "periods": periods,
        "summary": summary,
        "periods_per_year": int(periods_per_year),
    }


def _pairwise_comparison(
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
    performance_a = _performance_summary(pd.Series(returns_a), periods_per_year=periods_per_year)
    performance_b = _performance_summary(pd.Series(returns_b), periods_per_year=periods_per_year)
    block_length = _auto_block_length(len(both))
    bootstrap = _paired_block_bootstrap(
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


def _write_markdown(
    *,
    output_path: Path,
    as_of: str,
    candidate_summaries: list[dict[str, Any]],
    pairwise_results: list[dict[str, Any]],
    aligned_period_returns_path: Path,
    pairwise_csv_path: Path,
) -> None:
    lines: list[str] = []
    lines.append("# Alpha Ontology H10D Fixed-Set Paired Comparison")
    lines.append("")
    lines.append(f"- As of: `{as_of}`")
    lines.append(f"- Candidates: `{', '.join(item['candidate_label'] for item in candidate_summaries)}`")
    lines.append(f"- Aligned period returns: `{aligned_period_returns_path.relative_to(ROOT)}`")
    lines.append(f"- Pairwise CSV: `{pairwise_csv_path.relative_to(ROOT)}`")
    lines.append("")
    lines.append("## Candidate Summary")
    lines.append("")
    lines.append("| Candidate | Reported WF Median | Recomputed WF Median | Full OOS CumRet | Full OOS Sharpe | Loss Period Frac | Worst Regime | Max Trade Part. |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in candidate_summaries:
        worst_regime = item["reported_worst_regime_median_oos_sharpe"]
        worst_regime_text = "n/a" if worst_regime is None else f"{worst_regime:.3f}"
        lines.append(
            "| {label} | {reported:.3f} | {recomputed:.3f} | {cumret:.3f} | {sharpe:.3f} | {loss_frac:.3f} | {worst} | {max_part:.4f} |".format(
                label=item["candidate_label"],
                reported=item["reported_walk_forward_median_oos_sharpe"],
                recomputed=item["recomputed_walk_forward_median_oos_sharpe"],
                cumret=item["full_oos_cumulative_net_return"],
                sharpe=item["full_oos_period_sharpe"],
                loss_frac=item["full_oos_loss_period_fraction"],
                worst=worst_regime_text,
                max_part=item["full_oos_max_trade_participation_rate"],
            )
        )
    lines.append("")
    lines.append("## Pairwise Results")
    lines.append("")
    lines.append("| A | B | N | CumRet Diff | Sharpe Diff | Win Rate | Sign p | Bootstrap CumRet CI95 | P(A>B CumRet) |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |")
    for item in pairwise_results:
        ci_low, ci_high = item["bootstrap"]["cumulative_return_diff_ci_95"]
        lines.append(
            "| {a} | {b} | {n} | {cumdiff:.3f} | {shdiff:.3f} | {winrate} | {pvalue} | [{ci_low:.3f}, {ci_high:.3f}] | {prob:.3f} |".format(
                a=item["candidate_a"],
                b=item["candidate_b"],
                n=item["aligned_period_count"],
                cumdiff=item["observed_cumulative_return_diff"],
                shdiff=item["observed_sharpe_diff"],
                winrate=("n/a" if item["period_win_rate_a_gt_b"] is None else f"{item['period_win_rate_a_gt_b']:.3f}"),
                pvalue=("n/a" if item["sign_test_pvalue"] is None else f"{item['sign_test_pvalue']:.4f}"),
                ci_low=ci_low,
                ci_high=ci_high,
                prob=item["bootstrap"]["probability_a_beats_b_on_cumulative_return"],
            )
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paired full-period comparison for the fixed alpha ontology h10d set.")
    parser.add_argument("--as-of", default="2026-04-29")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--bootstrap-iterations", type=int, default=BOOTSTRAP_ITERATIONS)
    parser.add_argument("--output-date", default=datetime.now(UTC).date().isoformat())
    args = parser.parse_args(argv)

    validation_contract = _read_json(H10D_VALIDATION_CONTRACT_PATH)
    base_execution_cost_model, stress_execution_cost_model = _resolved_execution_cost_models()

    candidate_artifacts: list[dict[str, Any]] = []
    for entry in fixed_set_reference_entries(FIXED_SET_CONTRACT):
        label = str(entry.get("label") or "").strip()
        experiment_id = str(entry.get("experiment_id") or "").strip()
        artifact = _load_candidate_artifact(experiment_id=experiment_id, artifacts_root=args.artifacts_root)
        artifact["label"] = label
        artifact["role"] = str(entry.get("role") or "").strip()
        artifact["profile_constraints_override"] = dict(entry.get("profile_constraints_override") or {})
        candidate_artifacts.append(artifact)

    feature_frame = _load_shared_feature_frame(candidate_artifacts)
    results_by_label: dict[str, dict[str, Any]] = {}
    for artifact in candidate_artifacts:
        results_by_label[artifact["label"]] = _recompute_candidate_walk_forward(
            feature_frame=feature_frame,
            candidate_artifact=artifact,
            validation_contract=validation_contract,
            base_execution_cost_model=base_execution_cost_model,
            stress_execution_cost_model=stress_execution_cost_model,
        )

    candidate_summaries = [results_by_label[label]["summary"] for label, _ in DEFAULT_CANDIDATES]
    candidate_summaries = sorted(
        candidate_summaries,
        key=lambda item: float(item["full_oos_cumulative_net_return"]),
        reverse=True,
    )

    all_period_frames = []
    for label, _ in DEFAULT_CANDIDATES:
        period_frame = results_by_label[label]["periods"].copy()
        period_frame.rename(columns={"net_period_return": label}, inplace=True)
        all_period_frames.append(period_frame[["timestamp_ms", "timestamp_utc", label]])
    aligned_period_returns = all_period_frames[0]
    for frame in all_period_frames[1:]:
        aligned_period_returns = aligned_period_returns.merge(frame, on=["timestamp_ms", "timestamp_utc"], how="outer")
    aligned_period_returns = aligned_period_returns.sort_values("timestamp_ms").reset_index(drop=True)

    pairwise_results: list[dict[str, Any]] = []
    for pair_index, ((label_a, _), (label_b, _)) in enumerate(combinations(DEFAULT_CANDIDATES, 2)):
        periods_per_year = int(results_by_label[label_a]["periods_per_year"])
        pairwise_results.append(
            _pairwise_comparison(
                label_a=label_a,
                label_b=label_b,
                periods_a=results_by_label[label_a]["periods"],
                periods_b=results_by_label[label_b]["periods"],
                periods_per_year=periods_per_year,
                iterations=int(args.bootstrap_iterations),
                seed=BOOTSTRAP_SEED + pair_index,
            )
        )

    output_root = args.artifacts_root / "factor_reports" / f"{args.output_date}-alpha_ontology_h10d_fixed_set_comparison"
    output_root.mkdir(parents=True, exist_ok=True)
    aligned_period_returns_path = output_root / "aligned_period_returns.csv"
    pairwise_csv_path = output_root / "pairwise_comparisons.csv"
    summary_json_path = output_root / "summary.json"
    summary_md_path = output_root / "summary.md"

    aligned_period_returns.to_csv(aligned_period_returns_path, index=False)
    pd.DataFrame.from_records(pairwise_results).to_csv(pairwise_csv_path, index=False)

    summary_payload = {
        "analysis_date": str(args.output_date),
        "as_of": str(args.as_of),
        "candidate_order": [label for label, _ in DEFAULT_CANDIDATES],
        "candidate_summaries": candidate_summaries,
        "pairwise_results": pairwise_results,
        "artifacts": {
            "aligned_period_returns_csv": str(aligned_period_returns_path.relative_to(ROOT)),
            "pairwise_comparisons_csv": str(pairwise_csv_path.relative_to(ROOT)),
            "summary_md": str(summary_md_path.relative_to(ROOT)),
        },
    }
    summary_json_path.write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(
        output_path=summary_md_path,
        as_of=str(args.as_of),
        candidate_summaries=candidate_summaries,
        pairwise_results=pairwise_results,
        aligned_period_returns_path=aligned_period_returns_path,
        pairwise_csv_path=pairwise_csv_path,
    )
    print(json.dumps(summary_payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
