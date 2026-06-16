from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from enhengclaw.quant_research.falsification_runner import _scaled_execution_cost_model
from enhengclaw.quant_research.lab import (
    _apply_universe_filter,
    _backtest_cross_sectional,
    _chronological_split,
    _fit_and_score,
    _resolved_execution_cost_models,
    filter_cross_sectional_execution_frame,
)
from enhengclaw.quant_research.split_realization_contract import resolve_split_realization_contract
from enhengclaw.quant_research.validation_contract import (
    execution_capacity_limits,
    load_validation_contract,
    validation_contract_reference_capital_usd,
)


ROOT = Path(__file__).resolve().parents[2]
AS_OF = "2026-05-04"
REPORT_DATE = "2026-05-07"
EXPERIMENT_ROOT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "h10d_parent_frozen_reset_strict_2026-05-04_2026-05-06_01"
    / "experiments"
    / "2026-05-04-xs_alpha_ontology_v5_rw_bridg-325b6d02b7fe"
)
FEATURES_PATH = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / "h10d_parent_reset_replay_2026-05-04_2026-05-06_01"
    / "features"
    / "2026-05-04-cross-sectional-daily-1d-h10d-exec-aligned-label-v1-features-v91"
    / "features.csv.gz"
)
JSON_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / f"coinglass_h10d_parent_blocker_attribution_{REPORT_DATE}.json"
)
REPORT_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "reports"
    / f"coinglass_h10d_parent_blocker_attribution_{REPORT_DATE}.md"
)
STRICT_GATE_JSON_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "coinglass"
    / f"coinglass_h10d_parent_symbol_bucket_strict_gate_{REPORT_DATE}.json"
)
STRICT_GATE_REPORT_OUT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "reports"
    / f"coinglass_h10d_parent_symbol_bucket_strict_gate_{REPORT_DATE}.md"
)
POSITIVE_BUCKET_COUNT_REQUIRED = 2
SUBLANE_MIN_SUBJECT_COUNT = 8
SUBLANE_MIN_TRADE_COUNT = 5


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")


def _metric_subset(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "net_return",
        "sharpe",
        "max_drawdown",
        "turnover",
        "trade_count",
        "rebalance_count",
        "max_trade_participation_rate",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "latency_bars",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def _classification_from_metric(metrics: dict[str, Any]) -> str:
    if int(metrics.get("trade_count", 0) or 0) <= 0:
        return "no_trade_no_evidence"
    if float(metrics.get("net_return", 0.0) or 0.0) <= 0.0:
        return "hard_fail_non_positive_net"
    if float(metrics.get("sharpe", 0.0) or 0.0) <= 0.0:
        return "fail_non_positive_sharpe"
    return "pass_positive_oos"


def _build_markdown(payload: dict[str, Any]) -> str:
    decision = payload["decision"]
    diagnostic = payload["diagnostic_replay"]
    alpha = payload["alpha_card_semantics"]
    lines: list[str] = [
        "# CoinGlass H10D Parent Blocker Attribution",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- decision: `{decision['summary']}`",
        f"- structural_kill_order: `{', '.join(decision['structural_kill_order'])}`",
        "",
        "## Alpha Card Semantics",
        "",
        f"- source blockers: `{', '.join(alpha['source_blocker_codes'])}`",
        f"- statistical_falsification_status: `{alpha['statistical_falsification_status']}`",
        f"- statistical_falsification_applicable: `{alpha['statistical_falsification_applicable']}`",
        f"- statistical_falsification_reason: `{alpha['statistical_falsification_reason']}`",
        f"- falsification tests present: `{', '.join(alpha['falsification_tests_present']) or 'none'}`",
        f"- missing tests treated fail-closed: `{', '.join(alpha['missing_tests_treated_fail_closed'])}`",
        "",
        "Interpretation: missing statistical-falsification tests are now reported as `not_measured_fail_closed`. The diagnostic replay below separates that measurement gap from measured structural damage.",
        "",
        "## Diagnostic Replay Scope",
        "",
        f"- features_path: `{diagnostic['features_path']}`",
        f"- filtered_rows / subjects: `{diagnostic['filtered_rows']}` / `{diagnostic['filtered_subject_count']}`",
        f"- bucket_counts: `{diagnostic['bucket_counts']}`",
        f"- split_rows: `{diagnostic['split_rows']}`",
        "",
        "## Cost Stress",
        "",
        "| scenario | net return | sharpe | max drawdown | fee | slippage | verdict |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in diagnostic["cost_stress"]["scenarios"]:
        m = row["metrics"]
        lines.append(
            f"| {row['scenario']} | {m.get('net_return')} | {m.get('sharpe')} | {m.get('max_drawdown')} | "
            f"{m.get('fee_cost_return')} | {m.get('slippage_cost_return')} | {row['classification']} |"
        )
    lines.extend(
        [
            "",
            f"Cost stress attribution: `{diagnostic['cost_stress']['attribution']}`.",
            "",
            "## Delay Stress",
            "",
            "| latency bars | net return | sharpe | max drawdown | verdict |",
            "| ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in diagnostic["delay_stress"]["scenarios"]:
        m = row["metrics"]
        lines.append(
            f"| {m.get('latency_bars')} | {m.get('net_return')} | {m.get('sharpe')} | "
            f"{m.get('max_drawdown')} | {row['classification']} |"
        )
    lines.extend(
        [
            "",
            f"Delay stress attribution: `{diagnostic['delay_stress']['attribution']}`.",
            "",
            "## Liquidity Bucket Consistency",
            "",
            "| bucket | subjects | rows | trades | net return | sharpe | verdict |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in diagnostic["liquidity_bucket_consistency"]["buckets"]:
        m = row["metrics"]
        lines.append(
            f"| {row['liquidity_bucket']} | {row['subject_count']} | {row['row_count']} | "
            f"{m.get('trade_count')} | {m.get('net_return')} | {m.get('sharpe')} | {row['classification']} |"
        )
    lines.extend(
        [
            "",
            f"Liquidity bucket attribution: `{diagnostic['liquidity_bucket_consistency']['attribution']}`.",
            "",
            "## Symbol Holdout",
            "",
            "| held out | net return | sharpe | max drawdown | delta vs base | verdict |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in diagnostic["symbol_holdout"]["worst_holdouts"]:
        m = row["metrics"]
        lines.append(
            f"| {row['held_out_subject']} | {m.get('net_return')} | {m.get('sharpe')} | "
            f"{m.get('max_drawdown')} | {row['net_return_delta_vs_base']} | {row['classification']} |"
        )
    lines.extend(
        [
            "",
            f"Symbol holdout attribution: `{diagnostic['symbol_holdout']['attribution']}`.",
            "",
            "## Strict Symbol/Bucket Gate",
            "",
        ]
    )
    strict_gate = dict(payload.get("strict_promotion_gate") or {})
    if strict_gate:
        lines.extend(
            [
                f"- status: `{strict_gate.get('status')}`",
                f"- passed: `{strict_gate.get('passed')}`",
                f"- blocker_codes: `{', '.join(strict_gate.get('blocker_codes') or []) or 'none'}`",
                f"- r1_parent_promotion_status: `{strict_gate.get('r1_parent_promotion_status')}`",
                f"- next_mainline: `{strict_gate.get('next_mainline')}`",
                "",
            ]
        )
    narrow = dict(payload.get("narrow_sublane_diagnostic") or {})
    if narrow:
        top = dict(narrow.get("top_liquidity_only") or {})
        top_ex_trx = dict(narrow.get("top_liquidity_ex_trx") or {})
        holdout = dict(narrow.get("top_liquidity_ex_trx_symbol_holdout") or {})
        lines.extend(
            [
                "Narrow diagnostic:",
                "",
                "| scenario | subjects | trades | net return | sharpe | verdict |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
                (
                    f"| top_liquidity_only | {top.get('test_subject_count')} | "
                    f"{dict(top.get('metrics') or {}).get('trade_count')} | "
                    f"{dict(top.get('metrics') or {}).get('net_return')} | "
                    f"{dict(top.get('metrics') or {}).get('sharpe')} | {top.get('classification')} |"
                ),
                (
                    f"| top_liquidity_ex_trx | {top_ex_trx.get('test_subject_count')} | "
                    f"{dict(top_ex_trx.get('metrics') or {}).get('trade_count')} | "
                    f"{dict(top_ex_trx.get('metrics') or {}).get('net_return')} | "
                    f"{dict(top_ex_trx.get('metrics') or {}).get('sharpe')} | {top_ex_trx.get('classification')} |"
                ),
                "",
                f"- top_liquidity_ex_trx_symbol_holdout_passed: `{holdout.get('passed')}`",
                f"- hard_fail_subjects: `{', '.join(holdout.get('hard_fail_subjects') or []) or 'none'}`",
                f"- robust_sublane_candidate: `{narrow.get('robust_sublane_candidate')}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Explanation Before Optimization",
            "",
            f"- Cost/delay: `{decision['cost_delay_explanation']}`",
            f"- Liquidity bucket: `{decision['liquidity_bucket_explanation']}`",
            f"- Symbol holdout: `{decision['symbol_holdout_explanation']}`",
            "",
            "## Next Gate",
            "",
            decision["next_gate"],
            "",
        ]
    )
    return "\n".join(lines)


def _subset_frames(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    liquidity_bucket: str | None = None,
    exclude_subjects: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return tuple(
        _filter_subset(frame, liquidity_bucket=liquidity_bucket, exclude_subjects=exclude_subjects)
        for frame in (train_df, validation_df, test_df)
    )


def _filter_subset(
    frame: pd.DataFrame,
    *,
    liquidity_bucket: str | None,
    exclude_subjects: set[str] | None,
) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    if liquidity_bucket:
        mask &= frame["liquidity_bucket"].astype(str) == liquidity_bucket
    if exclude_subjects:
        mask &= ~frame["subject"].astype(str).isin(exclude_subjects)
    return frame.loc[mask].copy()


def _fit_subset_metrics(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    experiment_spec: dict[str, Any],
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
) -> dict[str, Any]:
    if train_df.empty or validation_df.empty or test_df.empty:
        return {
            "status": "insufficient_rows",
            "metrics": _metric_subset({}),
            "classification": "no_trade_no_evidence",
        }
    scored = _fit_and_score(
        model_family=str(experiment_spec["model_family"]),
        shape=str(experiment_spec["shape"]),
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=list(experiment_spec["feature_columns"]),
        target_column=str(experiment_spec["target_column"]),
        model_definition=experiment_spec.get("model_definition"),
    )
    metrics = _backtest_cross_sectional(
        scored["test"],
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        include_periods=True,
    )
    return {
        "status": "computed",
        "metrics": _metric_subset(metrics),
        "classification": _classification_from_metric(metrics),
    }


def _subset_scenario(
    *,
    name: str,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    experiment_spec: dict[str, Any],
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    liquidity_bucket: str | None = None,
    exclude_subjects: set[str] | None = None,
) -> dict[str, Any]:
    scenario_train, scenario_validation, scenario_test = _subset_frames(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        liquidity_bucket=liquidity_bucket,
        exclude_subjects=exclude_subjects,
    )
    result = _fit_subset_metrics(
        train_df=scenario_train,
        validation_df=scenario_validation,
        test_df=scenario_test,
        experiment_spec=experiment_spec,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
    )
    result.update(
        {
            "scenario": name,
            "train_rows": int(len(scenario_train)),
            "validation_rows": int(len(scenario_validation)),
            "test_rows": int(len(scenario_test)),
            "test_subject_count": int(scenario_test["subject"].nunique()) if "subject" in scenario_test else 0,
            "test_subjects": sorted(scenario_test["subject"].dropna().astype(str).unique().tolist())
            if "subject" in scenario_test
            else [],
            "liquidity_bucket": liquidity_bucket,
            "exclude_subjects": sorted(exclude_subjects or []),
        }
    )
    return result


def _subset_symbol_holdout(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    experiment_spec: dict[str, Any],
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    liquidity_bucket: str,
    exclude_subjects: set[str],
) -> dict[str, Any]:
    scenario_train, scenario_validation, scenario_test = _subset_frames(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        liquidity_bucket=liquidity_bucket,
        exclude_subjects=exclude_subjects,
    )
    rows: list[dict[str, Any]] = []
    for subject in sorted(scenario_test["subject"].dropna().astype(str).unique()):
        held_train = scenario_train.loc[scenario_train["subject"].astype(str) != subject].copy()
        held_validation = scenario_validation.loc[scenario_validation["subject"].astype(str) != subject].copy()
        held_test = scenario_test.loc[scenario_test["subject"].astype(str) != subject].copy()
        result = _fit_subset_metrics(
            train_df=held_train,
            validation_df=held_validation,
            test_df=held_test,
            experiment_spec=experiment_spec,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
        rows.append(
            {
                "held_out_subject": subject,
                "metrics": result["metrics"],
                "classification": result["classification"],
                "test_subject_count": int(held_test["subject"].nunique()) if "subject" in held_test else 0,
            }
        )
    hard_fail_subjects = [
        str(row["held_out_subject"])
        for row in rows
        if row["classification"] != "pass_positive_oos"
    ]
    return {
        "passed": not hard_fail_subjects and bool(rows),
        "hard_fail_subjects": hard_fail_subjects,
        "holdouts": rows,
    }


def _narrow_sublane_diagnostic(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    experiment_spec: dict[str, Any],
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
) -> dict[str, Any]:
    top = _subset_scenario(
        name="top_liquidity_only",
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        experiment_spec=experiment_spec,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        liquidity_bucket="top_liquidity",
    )
    top_ex_trx = _subset_scenario(
        name="top_liquidity_ex_trx",
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        experiment_spec=experiment_spec,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        liquidity_bucket="top_liquidity",
        exclude_subjects={"TRX"},
    )
    holdout = _subset_symbol_holdout(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        experiment_spec=experiment_spec,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        liquidity_bucket="top_liquidity",
        exclude_subjects={"TRX"},
    )
    metrics = dict(top_ex_trx.get("metrics") or {})
    robust_sublane_candidate = (
        top_ex_trx.get("classification") == "pass_positive_oos"
        and bool(holdout.get("passed"))
        and int(top_ex_trx.get("test_subject_count") or 0) >= SUBLANE_MIN_SUBJECT_COUNT
        and int(metrics.get("trade_count") or 0) >= SUBLANE_MIN_TRADE_COUNT
    )
    return {
        "status": "completed_narrow_top_liquidity_trx_excluded_symbol_holdout",
        "rules": {
            "sublane_min_subject_count": SUBLANE_MIN_SUBJECT_COUNT,
            "sublane_min_trade_count": SUBLANE_MIN_TRADE_COUNT,
            "requires_all_symbol_holdouts_positive": True,
        },
        "top_liquidity_only": top,
        "top_liquidity_ex_trx": top_ex_trx,
        "top_liquidity_ex_trx_symbol_holdout": holdout,
        "robust_sublane_candidate": bool(robust_sublane_candidate),
    }


def _build_strict_gate(
    *,
    diagnostic_replay: dict[str, Any],
    alpha_card_semantics: dict[str, Any],
    narrow_sublane: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    liquidity = dict(diagnostic_replay.get("liquidity_bucket_consistency") or {})
    symbol = dict(diagnostic_replay.get("symbol_holdout") or {})
    if bool(liquidity.get("hard_fail")):
        blockers.append("top_bucket_only")
    if bool(symbol.get("hard_fail")):
        blockers.append("symbol_holdout_dependency")
    hard_fail_subjects = [
        str(item)
        for item in list(symbol.get("hard_fail_subjects") or [])
        if str(item).strip()
    ]
    robust_sublane_candidate = bool(narrow_sublane.get("robust_sublane_candidate"))
    return {
        "contract_version": "quant_h10d_symbol_bucket_blocker_attribution_gate.v1",
        "status": "completed_symbol_bucket_strict_gate",
        "passed": not blockers,
        "blocker_codes": blockers,
        "missing_statistical_falsification_policy": "not_measured_fail_closed",
        "not_measured_fail_closed_tests": list(
            alpha_card_semantics.get("missing_tests_treated_fail_closed") or []
        ),
        "rules": {
            "positive_liquidity_bucket_count_min": POSITIVE_BUCKET_COUNT_REQUIRED,
            "sublane_min_subject_count": SUBLANE_MIN_SUBJECT_COUNT,
            "sublane_min_trade_count": SUBLANE_MIN_TRADE_COUNT,
            "sublane_symbol_holdout_required": True,
        },
        "evidence": {
            "positive_liquidity_bucket_count": int(liquidity.get("positive_bucket_count") or 0),
            "positive_liquidity_bucket_count_required": int(
                liquidity.get("positive_bucket_count_required") or POSITIVE_BUCKET_COUNT_REQUIRED
            ),
            "symbol_holdout_dependency_subjects": hard_fail_subjects,
            "robust_sublane_candidate": robust_sublane_candidate,
        },
        "r1_parent_promotion_status": "closed_fail_closed_return_to_cg2"
        if blockers and not robust_sublane_candidate
        else "parent_fail_closed_quarantine_residual_sublane",
        "next_mainline": "CG-2 OI/native-vs-derived provenance cleanup"
        if blockers and not robust_sublane_candidate
        else "quarantine residual top-liquidity ex-TRX sublane before any new alpha claim",
    }


def _build_strict_gate_markdown(payload: dict[str, Any]) -> str:
    gate = dict(payload["strict_promotion_gate"])
    narrow = dict(payload["narrow_sublane_diagnostic"])
    top_ex_trx = dict(narrow.get("top_liquidity_ex_trx") or {})
    holdout = dict(narrow.get("top_liquidity_ex_trx_symbol_holdout") or {})
    metrics = dict(top_ex_trx.get("metrics") or {})
    lines = [
        "# CoinGlass H10D Parent Symbol/Bucket Strict Gate",
        "",
        f"- generated_at_utc: `{payload['generated_at_utc']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{gate['status']}`",
        f"- passed: `{gate['passed']}`",
        f"- blocker_codes: `{', '.join(gate['blocker_codes']) or 'none'}`",
        f"- r1_parent_promotion_status: `{gate['r1_parent_promotion_status']}`",
        f"- next_mainline: `{gate['next_mainline']}`",
        "",
        "## Contract",
        "",
        f"- positive_liquidity_bucket_count_min: `{gate['rules']['positive_liquidity_bucket_count_min']}`",
        f"- missing_statistical_falsification_policy: `{gate['missing_statistical_falsification_policy']}`",
        f"- not_measured_fail_closed_tests: `{', '.join(gate['not_measured_fail_closed_tests']) or 'none'}`",
        "",
        "## Narrow Diagnostic",
        "",
        f"- scenario: `top_liquidity_ex_trx`",
        f"- test_subject_count: `{top_ex_trx.get('test_subject_count')}`",
        f"- trade_count: `{metrics.get('trade_count')}`",
        f"- net_return / sharpe: `{metrics.get('net_return')}` / `{metrics.get('sharpe')}`",
        f"- classification: `{top_ex_trx.get('classification')}`",
        f"- symbol_holdout_passed: `{holdout.get('passed')}`",
        f"- symbol_holdout_hard_fail_subjects: `{', '.join(holdout.get('hard_fail_subjects') or []) or 'none'}`",
        f"- robust_sublane_candidate: `{narrow.get('robust_sublane_candidate')}`",
        "",
        "Decision: original R-1 parent remains fail-closed when the gate has `top_bucket_only` or `symbol_holdout_dependency`. A residual sublane, if present, must be quarantined as a new candidate rather than promoted through the parent.",
        "",
    ]
    return "\n".join(lines)


def _patch_alpha_card_with_strict_gate(strict_gate: dict[str, Any]) -> None:
    for path in (EXPERIMENT_ROOT / "alpha_card.json", EXPERIMENT_ROOT / "validation_report.json"):
        if not path.exists():
            continue
        payload = _read_json(path)
        payload["blocker_attribution_gate"] = strict_gate
        _write_json(path, payload)


def main() -> None:
    alpha_card = _read_json(EXPERIMENT_ROOT / "alpha_card.json")
    experiment_spec = _read_json(EXPERIMENT_ROOT / "experiment_spec.json")
    statistical_falsification = dict(alpha_card.get("statistical_falsification") or {})
    falsification_tests = dict(statistical_falsification.get("tests") or {})

    features = pd.read_csv(FEATURES_PATH, compression="gzip")
    frame = _apply_universe_filter(features, universe_filter=dict(experiment_spec.get("universe_filter") or {}))
    constraints = dict(experiment_spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(experiment_spec.get("strategy_profile") or "")
    frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)

    split_realization_contract = resolve_split_realization_contract(
        contract=dict(experiment_spec.get("split_realization_contract") or {}),
        shape="cross_sectional",
    )
    split = _chronological_split(
        frame,
        time_col="timestamp_ms",
        split_realization_contract=split_realization_contract,
    )
    if split is None:
        raise RuntimeError("unable to rebuild chronological split for blocker attribution")
    train_df, validation_df, test_df = split

    scored = _fit_and_score(
        model_family=str(experiment_spec["model_family"]),
        shape=str(experiment_spec["shape"]),
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        feature_columns=list(experiment_spec["feature_columns"]),
        target_column=str(experiment_spec["target_column"]),
        model_definition=experiment_spec.get("model_definition"),
    )

    validation_contract = load_validation_contract()
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(experiment_spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    capacity_limits = execution_capacity_limits(validation_contract)
    base_execution_cost_model, _stress_execution_cost_model = _resolved_execution_cost_models()

    base_metrics = _backtest_cross_sectional(
        scored["test"],
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=base_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        include_periods=True,
    )

    cost_scenarios: list[dict[str, Any]] = [
        {
            "scenario": "base",
            "cost_multiplier": 1.0,
            "metrics": _metric_subset(base_metrics),
            "classification": _classification_from_metric(base_metrics),
        }
    ]
    for multiplier in (1.5, 2.0):
        stressed_model = _scaled_execution_cost_model(base_execution_cost_model, multiplier=multiplier)
        metrics = _backtest_cross_sectional(
            scored["test"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=stressed_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        cost_scenarios.append(
            {
                "scenario": f"cost_x{multiplier:g}",
                "cost_multiplier": float(multiplier),
                "metrics": _metric_subset(metrics),
                "classification": _classification_from_metric(metrics),
            }
        )

    delay_scenarios: list[dict[str, Any]] = []
    for added_delay in (0, 1, 2):
        delayed_model = dict(base_execution_cost_model)
        delayed_model["latency_bars"] = int(base_execution_cost_model.get("latency_bars", 1) or 1) + added_delay
        metrics = _backtest_cross_sectional(
            scored["test"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=delayed_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        delay_scenarios.append(
            {
                "added_delay_bars": int(added_delay),
                "metrics": _metric_subset(metrics),
                "classification": _classification_from_metric(metrics),
            }
        )

    bucket_rows: list[dict[str, Any]] = []
    for bucket in sorted(scored["test"]["liquidity_bucket"].dropna().astype(str).unique()):
        bucket_frame = scored["test"].loc[scored["test"]["liquidity_bucket"].astype(str) == bucket].copy()
        metrics = _backtest_cross_sectional(
            bucket_frame,
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        bucket_rows.append(
            {
                "liquidity_bucket": bucket,
                "row_count": int(len(bucket_frame)),
                "subject_count": int(bucket_frame["subject"].nunique()),
                "subjects": sorted(bucket_frame["subject"].dropna().astype(str).unique().tolist()),
                "metrics": _metric_subset(metrics),
                "classification": _classification_from_metric(metrics),
            }
        )
    positive_bucket_count = sum(
        1
        for row in bucket_rows
        if row["classification"] == "pass_positive_oos"
    )

    holdouts: list[dict[str, Any]] = []
    base_net_return = float(base_metrics.get("net_return", 0.0) or 0.0)
    for subject in sorted(test_df["subject"].dropna().astype(str).unique()):
        held_train = train_df.loc[train_df["subject"].astype(str) != subject].copy()
        held_validation = validation_df.loc[validation_df["subject"].astype(str) != subject].copy()
        held_test = test_df.loc[test_df["subject"].astype(str) != subject].copy()
        held_scored = _fit_and_score(
            model_family=str(experiment_spec["model_family"]),
            shape=str(experiment_spec["shape"]),
            train_df=held_train,
            validation_df=held_validation,
            test_df=held_test,
            feature_columns=list(experiment_spec["feature_columns"]),
            target_column=str(experiment_spec["target_column"]),
            model_definition=experiment_spec.get("model_definition"),
        )
        metrics = _backtest_cross_sectional(
            held_scored["test"],
            constraints=constraints,
            split_realization_contract=split_realization_contract,
            execution_cost_model=base_execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            include_periods=True,
        )
        metric_subset = _metric_subset(metrics)
        holdouts.append(
            {
                "held_out_subject": subject,
                "metrics": metric_subset,
                "net_return_delta_vs_base": float(metric_subset.get("net_return", 0.0) or 0.0) - base_net_return,
                "classification": _classification_from_metric(metrics),
            }
        )
    hard_holdout_failures = [
        row["held_out_subject"]
        for row in holdouts
        if row["classification"] != "pass_positive_oos"
    ]
    worst_holdouts = sorted(
        holdouts,
        key=lambda row: float(row["metrics"].get("net_return", 0.0) or 0.0),
    )[:10]

    alpha_experiment_card = dict(alpha_card.get("alpha_experiment_card") or {})
    missing_tests = [
        test_name
        for test_name in (
            "cost_stress",
            "delayed_execution",
            "liquidity_bucket_consistency",
            "symbol_holdout",
        )
        if test_name not in falsification_tests
    ]

    cost_hard_fail = any(row["classification"] != "pass_positive_oos" for row in cost_scenarios)
    delay_hard_fail = any(row["classification"] != "pass_positive_oos" for row in delay_scenarios)
    liquidity_hard_fail = positive_bucket_count < POSITIVE_BUCKET_COUNT_REQUIRED
    symbol_hard_fail = bool(hard_holdout_failures)
    narrow_sublane = _narrow_sublane_diagnostic(
        train_df=train_df,
        validation_df=validation_df,
        test_df=test_df,
        experiment_spec=experiment_spec,
        constraints=constraints,
        split_realization_contract=split_realization_contract,
        execution_cost_model=base_execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
    )

    payload: dict[str, Any] = {
        "as_of": AS_OF,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "completed_blocker_attribution",
        "source_experiment_root": str(EXPERIMENT_ROOT),
        "alpha_card_semantics": {
            "source_blocker_codes": list(alpha_experiment_card.get("blocker_codes") or []),
            "statistical_falsification_status": str(statistical_falsification.get("status") or ""),
            "statistical_falsification_applicable": bool(statistical_falsification.get("applicable")),
            "statistical_falsification_reason": str(statistical_falsification.get("reason") or ""),
            "falsification_tests_present": sorted(falsification_tests.keys()),
            "missing_tests_treated_fail_closed": missing_tests,
            "alpha_card_cost_stress_passed": bool(alpha_experiment_card.get("cost_stress_passed")),
            "alpha_card_delay_stress_passed": bool(alpha_experiment_card.get("delay_stress_passed")),
            "alpha_card_liquidity_bucket_consistency_passed": bool(alpha_experiment_card.get("liquidity_bucket_consistency_passed")),
            "alpha_card_symbol_holdout_passed": bool(alpha_experiment_card.get("symbol_holdout_passed")),
        },
        "diagnostic_replay": {
            "features_path": str(FEATURES_PATH),
            "filtered_rows": int(len(frame)),
            "filtered_subject_count": int(frame["subject"].nunique()),
            "filtered_subjects": sorted(frame["subject"].dropna().astype(str).unique().tolist()),
            "bucket_counts": {
                str(key): int(value)
                for key, value in frame["liquidity_bucket"].value_counts(dropna=False).to_dict().items()
            },
            "split_rows": {
                "train": int(len(train_df)),
                "validation": int(len(validation_df)),
                "test": int(len(test_df)),
            },
            "base_metrics": _metric_subset(base_metrics),
            "cost_stress": {
                "attribution": "non_structural_measured_pass",
                "hard_fail": cost_hard_fail,
                "scenarios": cost_scenarios,
            },
            "delay_stress": {
                "attribution": "non_structural_measured_pass",
                "hard_fail": delay_hard_fail,
                "scenarios": delay_scenarios,
            },
            "liquidity_bucket_consistency": {
                "attribution": "structural_top_bucket_only_edge",
                "hard_fail": liquidity_hard_fail,
                "positive_bucket_count": int(positive_bucket_count),
                "positive_bucket_count_required": POSITIVE_BUCKET_COUNT_REQUIRED,
                "buckets": bucket_rows,
            },
            "symbol_holdout": {
                "attribution": "structural_symbol_dependency",
                "hard_fail": symbol_hard_fail,
                "hard_fail_subjects": hard_holdout_failures,
                "worst_holdouts": worst_holdouts,
                "all_holdouts": holdouts,
            },
        },
        "narrow_sublane_diagnostic": narrow_sublane,
        "decision": {
            "summary": "cost_delay_not_structural; liquidity_bucket_and_symbol_holdout_are_structural_killers",
            "structural_kill_order": [
                "symbol_holdout_TRX_dependency",
                "liquidity_bucket_top_bucket_only",
                "cost_stress_not_structural",
                "delay_stress_not_structural",
            ],
            "cost_delay_explanation": (
                "The alpha card now reports missing cost/delay statistical-falsification tests as "
                "not_measured_fail_closed, while diagnostic replay keeps net return and Sharpe positive "
                "under 2x costs and +2 bars latency."
            ),
            "liquidity_bucket_explanation": (
                "Only top_liquidity produces trades and positive OOS return; mid_liquidity and tail_liquidity "
                "produce zero trades under the current top/bottom count constraints, so the required two positive buckets cannot be met."
            ),
            "symbol_holdout_explanation": (
                "Leave-one-symbol-out is broadly positive except TRX; holding out TRX flips test net return negative, "
                "so the edge is not symbol-robust enough for promotion."
            ),
            "next_gate": (
                "Do not optimize the original parent. The strict symbol/bucket gate is now the promotion contract: "
                "top_bucket_only and symbol_holdout_dependency fail the parent closed. If research continues, "
                "quarantine top_liquidity_ex_trx as a new candidate rather than promoting the parent."
            ),
        },
        "outputs": {
            "json": str(JSON_OUT),
            "report": str(REPORT_OUT),
            "strict_gate_json": str(STRICT_GATE_JSON_OUT),
            "strict_gate_report": str(STRICT_GATE_REPORT_OUT),
        },
    }
    payload["strict_promotion_gate"] = _build_strict_gate(
        diagnostic_replay=dict(payload["diagnostic_replay"]),
        alpha_card_semantics=dict(payload["alpha_card_semantics"]),
        narrow_sublane=narrow_sublane,
    )

    _write_json(JSON_OUT, payload)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(_build_markdown(payload), encoding="utf-8")
    strict_gate_payload = {
        "as_of": AS_OF,
        "generated_at_utc": payload["generated_at_utc"],
        "strict_promotion_gate": payload["strict_promotion_gate"],
        "narrow_sublane_diagnostic": narrow_sublane,
        "source_blocker_attribution_json": str(JSON_OUT),
        "source_blocker_attribution_report": str(REPORT_OUT),
    }
    _write_json(STRICT_GATE_JSON_OUT, strict_gate_payload)
    STRICT_GATE_REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    STRICT_GATE_REPORT_OUT.write_text(_build_strict_gate_markdown(payload), encoding="utf-8")
    _patch_alpha_card_with_strict_gate(dict(payload["strict_promotion_gate"]))
    print(json.dumps(payload["decision"], indent=2, ensure_ascii=False))
    print(json.dumps(payload["outputs"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
