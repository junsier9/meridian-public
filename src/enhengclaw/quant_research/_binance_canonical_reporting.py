from __future__ import annotations

from pathlib import Path
from typing import Any


def _render_markdown_report(validation_report: dict[str, Any], paths: dict[str, Path]) -> str:
    metrics = dict(validation_report.get("metrics") or {})
    base = dict(metrics.get("base") or {})
    stress = dict(metrics.get("stress") or {})
    blockers = list(validation_report.get("blockers") or [])
    attribution = dict(validation_report.get("attribution") or {})
    factor_attribution = dict(validation_report.get("factor_attribution") or {})
    paper_shadow_execution = dict(validation_report.get("paper_shadow_execution") or {})
    ablations = dict(validation_report.get("ablations") or {})
    execution_gap_policy = dict(validation_report.get("execution_gap_policy") or {})
    risk_overlay_policy = dict(validation_report.get("risk_overlay_policy") or {})
    falsification = dict(validation_report.get("falsification") or {})
    gate_results = dict(validation_report.get("gate_results") or {})
    legacy_holdout = dict(falsification.get("symbol_holdout") or {})
    stratified_holdout = dict(falsification.get("stratified_repeated_symbol_holdout") or {})
    stratified_summary = dict(stratified_holdout.get("summary") or {})
    stratified_policy = dict(stratified_holdout.get("policy") or {})
    lines = [
        "# Binance-Canonical H10D Validation",
        "",
        f"`Strategy: {validation_report.get('strategy_label')}`",
        f"`Parent: {validation_report.get('parent_label')}`",
        f"`Status: {validation_report.get('status')}`",
        "",
        "## Metrics",
        "",
        "| Scenario | Net return | Sharpe | Max DD | Rebalances | Max trade participation |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        _metric_row("base", base),
        _metric_row("stress", stress),
        "",
        "## Blockers",
        "",
    ]
    if blockers:
        lines.extend(f"- `{item.get('code', 'unknown')}`: {item.get('message') or item.get('detail') or item}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Execution Gap Policy", ""])
    lines.append(f"- mode: `{execution_gap_policy.get('mode', 'none')}`")
    excluded_symbols = list(execution_gap_policy.get("excluded_symbols") or [])
    lines.append(f"- excluded_symbols: `{', '.join(excluded_symbols) if excluded_symbols else 'none'}`")
    lines.append(f"- residual_data_gap_blockers: `{len(execution_gap_policy.get('residual_data_gap_blockers') or [])}`")
    if risk_overlay_policy:
        drawdown_policy = dict(risk_overlay_policy.get("portfolio_drawdown_brake") or {})
        squeeze_policy = dict(risk_overlay_policy.get("short_squeeze_brake") or {})
        rebound_policy = dict(risk_overlay_policy.get("high_vol_rebound_short_brake") or {})
        lines.extend(["", "## Risk Overlay", ""])
        lines.append(f"- mode: `{risk_overlay_policy.get('mode', 'unavailable')}`")
        lines.append(f"- source_boundary: `{risk_overlay_policy.get('source_boundary', 'binance_ohlcv_and_closed_pnl_only')}`")
        lines.append(
            "- portfolio_drawdown_brake: "
            f"`enabled={bool(drawdown_policy.get('enabled', False))}, "
            f"window_days={int(drawdown_policy.get('window_days', 0) or 0)}, "
            f"dd_5pct_multiplier={float(drawdown_policy.get('dd_5pct_multiplier', 0.0) or 0.0):.3f}, "
            f"dd_10pct_multiplier={float(drawdown_policy.get('dd_10pct_multiplier', 0.0) or 0.0):.3f}`"
        )
        lines.append(f"- short_squeeze_brake_enabled: `{bool(squeeze_policy.get('enabled', False))}`")
        lines.append(
            "- high_vol_rebound_short_brake: "
            f"`enabled={bool(rebound_policy.get('enabled', False))}, "
            f"short_multiplier={float(rebound_policy.get('short_multiplier', 1.0) or 1.0):.3f}, "
            f"severe_short_multiplier={float(rebound_policy.get('severe_short_multiplier', 1.0) or 1.0):.3f}`"
        )
        lines.append(f"- base_max_drawdown_under_cap: `{bool(gate_results.get('base_max_drawdown_under_cap', True))}`")
    lines.extend(["", "## Attribution", ""])
    side_rows = list(attribution.get("side_summary") or [])
    if side_rows:
        lines.extend(
            [
                "| Side | Gross contrib | Funding cost | Net before trade cost | Positions | Hit rate |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in side_rows:
            lines.append(
                f"| {item.get('side')} | {float(item.get('gross_contribution', 0.0) or 0.0):.6f} | "
                f"{float(item.get('funding_cost_return', 0.0) or 0.0):.6f} | "
                f"{float(item.get('net_before_trade_cost_contribution', 0.0) or 0.0):.6f} | "
                f"{int(item.get('position_count', 0) or 0)} | "
                f"{float(item.get('profitable_position_rate', 0.0) or 0.0):.3f} |"
            )
    else:
        lines.append("- attribution unavailable")
    lines.extend(["", "## Factor Leave-One-Out", ""])
    loo_rows = list(factor_attribution.get("top_positive_contributors") or [])
    negative_rows = list(factor_attribution.get("negative_contributors") or [])
    baseline = dict(factor_attribution.get("baseline") or {})
    baseline_base = dict(baseline.get("base") or {})
    lines.append(f"- method: `{factor_attribution.get('method', 'unavailable')}`")
    lines.append(f"- baseline_base_net_return: `{float(baseline_base.get('net_return', 0.0) or 0.0):.6f}`")
    if loo_rows:
        lines.extend(
            [
                "",
                "| Removed feature | Weight share | Base-minus-LOO net | Base-minus-LOO Sharpe |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for item in loo_rows:
            lines.append(
                f"| {item.get('feature')} | "
                f"{float(item.get('absolute_weight_share', 0.0) or 0.0):.3f} | "
                f"{float(item.get('net_return_delta_baseline_minus_loo', 0.0) or 0.0):.6f} | "
                f"{float(item.get('sharpe_delta_baseline_minus_loo', 0.0) or 0.0):.3f} |"
            )
    else:
        lines.append("- factor leave-one-out unavailable")
    if negative_rows:
        lines.extend(["", "Negative LOO contributors:"])
        for item in negative_rows[:5]:
            lines.append(
                f"- `{item.get('feature')}` base-minus-LOO net "
                f"`{float(item.get('net_return_delta_baseline_minus_loo', 0.0) or 0.0):.6f}`"
            )
    lines.extend(["", "## Paper Shadow Execution", ""])
    lines.append(f"- execution_mode: `{paper_shadow_execution.get('execution_mode', 'unavailable')}`")
    lines.append(f"- ledger_row_count: `{int(paper_shadow_execution.get('ledger_row_count', 0) or 0)}`")
    lines.append(f"- order_row_count: `{int(paper_shadow_execution.get('order_row_count', 0) or 0)}`")
    lines.append(f"- net_contribution: `{float(paper_shadow_execution.get('net_contribution', 0.0) or 0.0):.6f}`")
    lines.append(f"- max_trade_participation_rate: `{float(paper_shadow_execution.get('max_trade_participation_rate', 0.0) or 0.0):.6f}`")
    lines.append(f"- data_gap_blockers: `{len(paper_shadow_execution.get('data_gap_blockers') or [])}`")
    lines.extend(["", "## Ablations", ""])
    if ablations:
        lines.extend(
            [
                "| Ablation | Base net | Base Sharpe | Stress net | Max participation |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, payload in sorted(ablations.items()):
            base_metrics = dict(dict(payload).get("base") or {})
            stress_metrics = dict(dict(payload).get("stress") or {})
            lines.append(
                f"| {name} | {float(base_metrics.get('net_return', 0.0) or 0.0):.6f} | "
                f"{float(base_metrics.get('sharpe', 0.0) or 0.0):.3f} | "
                f"{float(stress_metrics.get('net_return', 0.0) or 0.0):.6f} | "
                f"{float(base_metrics.get('max_trade_participation_rate', 0.0) or 0.0):.6f} |"
            )
    else:
        lines.append("- ablations unavailable")
    lines.extend(["", "## Holdout Gates", ""])
    lines.append("- legacy_a_b_role: `diagnostic`")
    lines.append(
        f"- legacy_a_b_positive_count: `{int(gate_results.get('legacy_holdout_positive_count', gate_results.get('holdout_positive_count', 0)) or 0)}`"
    )
    lines.append(f"- legacy_a_b_gate_diagnostic: `{bool(gate_results.get('legacy_holdout_positive_gate_diagnostic', False))}`")
    lines.append(f"- stratified_repeated_hard_gate: `{bool(gate_results.get('stratified_holdout_gate', False))}`")
    lines.append(
        "- stratified_policy: "
        f"`repeat_count={int(stratified_policy.get('repeat_count', 0) or 0)}, "
        f"min_positive_fraction={float(stratified_policy.get('min_positive_fraction', 0.0) or 0.0):.3f}, "
        f"require_gap_free={bool(stratified_policy.get('require_gap_free', False))}`"
    )
    lines.extend(
        [
            "",
            "| Holdout | Fold count | Positive folds | Positive fraction | Gap-free folds | Min net | Median net | Max net |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            f"| stratified_repeated | {int(stratified_summary.get('fold_count', 0) or 0)} | "
            f"{int(stratified_summary.get('positive_fold_count', 0) or 0)} | "
            f"{float(stratified_summary.get('positive_fraction', 0.0) or 0.0):.3f} | "
            f"{int(stratified_summary.get('gap_free_fold_count', 0) or 0)} | "
            f"{float(stratified_summary.get('min_net_return', 0.0) or 0.0):.6f} | "
            f"{float(stratified_summary.get('median_net_return', 0.0) or 0.0):.6f} | "
            f"{float(stratified_summary.get('max_net_return', 0.0) or 0.0):.6f} |",
        ]
    )
    if legacy_holdout:
        lines.extend(
            [
                "",
                "| Diagnostic split | Net return | Sharpe | Subject count |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for name, payload in sorted(legacy_holdout.items()):
            metrics = dict(dict(payload).get("metrics") or {})
            subjects = list(dict(payload).get("subjects") or [])
            lines.append(
                f"| {name} | {float(metrics.get('net_return', 0.0) or 0.0):.6f} | "
                f"{float(metrics.get('sharpe', 0.0) or 0.0):.3f} | "
                f"{int(len(subjects))} |"
            )
    lines.extend(
        [
            "",
            "## Artifact Paths",
            "",
            f"- validation_report: `{paths['validation_report']}`",
            f"- dataset_manifest: `{paths['dataset_manifest']}`",
            f"- gap_audit: `{paths['gap_audit']}`",
            f"- feature_manifest: `{paths['feature_manifest']}`",
            f"- aligned_period_returns: `{paths['aligned_period_returns']}`",
            f"- universe_membership: `{paths['universe_membership']}`",
            f"- position_attribution: `{paths['position_attribution']}`",
            f"- attribution_by_side_year: `{paths['attribution_by_side_year']}`",
            f"- attribution_by_symbol_year: `{paths['attribution_by_symbol_year']}`",
            f"- factor_leave_one_out: `{paths['factor_leave_one_out']}`",
            f"- factor_leave_one_out_summary: `{paths['factor_leave_one_out_summary']}`",
            f"- factor_leave_one_out_by_side: `{paths['factor_leave_one_out_by_side']}`",
            f"- factor_leave_one_out_by_year: `{paths['factor_leave_one_out_by_year']}`",
            f"- factor_leave_one_out_by_side_year: `{paths['factor_leave_one_out_by_side_year']}`",
            f"- paper_shadow_execution_ledger: `{paths['paper_shadow_execution_ledger']}`",
            f"- paper_shadow_execution_summary: `{paths['paper_shadow_execution_summary']}`",
            f"- ablation_summary: `{paths['ablation_summary']}`",
            f"- ablation_period_returns: `{paths['ablation_period_returns']}`",
            "",
            "## Sidecar Policy",
            "",
            "CoinGlass, OI, liquidation, orderbook, top-trader, taker, funding, and basis columns are excluded from core alpha.",
        ]
    )
    return "\n".join(lines) + "\n"


def _metric_row(name: str, metrics: dict[str, Any]) -> str:
    return (
        f"| {name} | {float(metrics.get('net_return', 0.0) or 0.0):.6f} | "
        f"{float(metrics.get('sharpe', 0.0) or 0.0):.3f} | "
        f"{float(metrics.get('max_drawdown', 0.0) or 0.0):.6f} | "
        f"{int(metrics.get('rebalance_count', 0) or 0)} | "
        f"{float(metrics.get('max_trade_participation_rate', 0.0) or 0.0):.6f} |"
    )
