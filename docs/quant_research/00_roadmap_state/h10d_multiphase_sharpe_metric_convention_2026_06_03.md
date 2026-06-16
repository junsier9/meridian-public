# H10D Multiphase Sharpe Metric Convention

`Status: active metric convention`
`Date: 2026-06-03`
`Scope: h10d_current_diagnostics, v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`

## Correction

Headline Sharpe for h10d multiphase diagnostics must use an overlap-adjusted
h10d-equivalent annualization. It must not annualize overlapping 10-sleeve
booking returns by the observed daily aggregate count.

Correct rule:

```text
independent_period_bars = max(target_horizon_bars, realization_step_bars)
periods_per_year = 365 / independent_period_bars
sharpe = mean(period_return) / std(period_return) * sqrt(periods_per_year)
```

For the current 10-sleeve h10d research baseline:

```text
target_horizon_bars = 10
realization_step_bars = 10
periods_per_year = 365 / 10 = 36.5
```

The incorrect convention was to use the empirical count of aggregated output
timestamps, which is close to daily frequency and therefore near `365` periods
per year. That overstates Sharpe by roughly `sqrt(10)` for current h10d
overlapping booking-return diagnostics.

## Field Names

Use these fields as headline metrics:

- `full_oos_h10d_equivalent_sharpe`
- `baseline_full_oos_h10d_equivalent_sharpe`
- `delta_full_oos_h10d_equivalent_sharpe_vs_baseline`

Deprecated audit-only fields must be explicitly named as deprecated:

- `full_oos_observed_frequency_sharpe_deprecated`
- `full_oos_observed_frequency_periods_per_year_deprecated`

Do not display deprecated observed-frequency Sharpe in report tables except as
an explicit audit comparison.

## Implementation

The shared helper is:

- `src/enhengclaw/quant_research/horizon_metrics.py`

Current scripts patched to use this convention:

- `scripts/quant_research/h10d_current_diagnostics/run_portfolio_construction_experiment.py`
- `scripts/quant_research/h10d_current_diagnostics/run_multiphase_factor_drawdown_ablation.py`
- `scripts/quant_research/h10d_current_diagnostics/run_dth60_conditional_overlay_ablation.py`

## Guardrail

If a report uses true daily mark-to-market returns, it may report daily-MTM
Sharpe. If a report uses h10d booking returns, fixed-set h10d labels, or
10-sleeve aggregated booking returns, it must use the overlap-adjusted
h10d-equivalent convention above.

Promotion or baseline-comparison language must not rely on
observed-frequency Sharpe from overlapping booking returns.
