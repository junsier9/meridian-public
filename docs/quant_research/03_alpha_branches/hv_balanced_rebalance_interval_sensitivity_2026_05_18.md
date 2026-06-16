# hv_balanced rebalance interval sensitivity

- generated_at_utc: `2026-05-18T11:28:52Z`
- hard_status: `blocked`
- scenario: `base`
- fixed_config: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\config\quant_research\binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json`
- score_frame_reused_across_intervals: `True`
- frozen_row_alignment_applied: `True`
- selected_universe_count: `68`
- scored_row_count: `142262`
- dataset_reproduction_status: `passed`
- baseline_reproduction_status: `passed`
- funding_sample_positive_row_count: `122417`

## Metric table

| interval_days | net_return | net_return_delta_vs_10d | sharpe | sharpe_delta_vs_10d | max_drawdown | max_drawdown_delta_vs_10d | turnover | trade_count | rebalance_count | data_gap_blocker_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 1.324744 | -1.916447 | 0.753149 | -0.517072 | 0.272150 | -0.007169 | 197.120537 | 345 | 365 | 0 |
| 7 | 2.610517 | -0.630674 | 1.084089 | -0.186132 | 0.277502 | -0.001818 | 155.557487 | 246 | 261 | 0 |
| 10 | 3.241191 | 0.000000 | 1.270222 | 0.000000 | 0.279320 | 0.000000 | 115.327476 | 173 | 183 | 0 |
| 15 | 1.207747 | -2.033444 | 0.748097 | -0.522125 | 0.315771 | 0.036452 | 87.310274 | 118 | 122 | 0 |
| 20 | 4.797901 | 1.556710 | 1.370350 | 0.100128 | 0.230541 | -0.048778 | 68.184495 | 88 | 92 | 0 |
| 30 | 0.046127 | -3.195063 | 0.239705 | -1.030517 | 0.575768 | 0.296449 | 45.583146 | 59 | 61 | 2 |

## Guardrails

- Alpha score, feature columns, feature weights, PIT universe policy, PIT eligibility, risk brake columns, reference capital, and execution cost scenario are fixed from the frozen hv_balanced config.
- The only swept field is `split_realization.target_horizon_bars`.
- Paired MTM is aligned on the union of fill dates and forward-filled between rebalance events; it is for curve comparison, not for adding extra trade decisions.
- Promotion use is blocked unless the 10d row reproduces the frozen hv_balanced base metrics within tolerance.

## Blockers

- `interval_execution_data_gap_blockers`: {'code': 'interval_execution_data_gap_blockers', 'interval_days': 30, 'data_gap_blocker_count': 2, 'sample': ['SUSHI: missing exit row for execution venue', 'SUSHI: missing fill row for execution venue']}

## Artifacts

- summary_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_interval_sensitivity_20260518\summary.json`
- interval_metrics_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_interval_sensitivity_20260518\interval_metrics.csv`
- period_returns_long_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_interval_sensitivity_20260518\period_returns_long.csv`
- paired_mtm_curve_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_interval_sensitivity_20260518\paired_mtm_curve.csv`
- paired_delta_vs_10d_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_interval_sensitivity_20260518\paired_delta_vs_10d.csv`
- scored_frame_diagnostics_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_interval_sensitivity_20260518\scored_frame_diagnostics.json`
- markdown_report: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\docs\quant_research\03_alpha_branches\hv_balanced_rebalance_interval_sensitivity_2026_05_18.md`
