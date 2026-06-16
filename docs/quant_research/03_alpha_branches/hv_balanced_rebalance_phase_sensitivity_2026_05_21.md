# hv_balanced 10d rebalance phase sensitivity

- generated_at_utc: `2026-05-21T12:01:17Z`
- hard_status: `blocked`
- robustness_status: `failed`
- scenario: `base`
- fixed_config: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\config\quant_research\binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json`
- horizon_days: `10`
- phase_offsets_days: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`
- score_frame_reused_across_phases: `True`
- selected_universe_count: `68`
- scored_row_count: `142262`
- dataset_reproduction_status: `passed`
- phase0_frozen_baseline_reproduction_status: `passed`
- funding_sample_positive_row_count: `122417`

## Metric table

| phase_offset_days | start_date_utc | net_return | net_return_ratio_vs_phase0 | sharpe | sharpe_delta_vs_phase0 | max_drawdown | max_drawdown_delta_vs_phase0 | turnover | trade_count | rebalance_count | data_gap_blocker_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 2021-05-01 | 3.241191 | 1.000000 | 1.270222 | 0.000000 | 0.279320 | 0.000000 | 115.327476 | 173 | 183 | 0 |
| 1 | 2021-05-02 | 2.696012 | 0.831797 | 1.068616 | -0.201606 | 0.285370 | 0.006050 | 121.925007 | 175 | 183 | 0 |
| 2 | 2021-05-03 | 2.155949 | 0.665172 | 1.032601 | -0.237621 | 0.200850 | -0.078470 | 116.658579 | 168 | 183 | 0 |
| 3 | 2021-05-04 | 2.099790 | 0.647845 | 0.981358 | -0.288864 | 0.295930 | 0.016610 | 119.792068 | 169 | 183 | 0 |
| 4 | 2021-05-05 | 4.200202 | 1.295882 | 1.382744 | 0.112522 | 0.294106 | 0.014787 | 113.648714 | 173 | 183 | 1 |
| 5 | 2021-05-06 | 2.035205 | 0.627919 | 0.988399 | -0.281823 | 0.224505 | -0.054815 | 119.568333 | 174 | 182 | 0 |
| 6 | 2021-05-07 | 2.814419 | 0.868329 | 1.109957 | -0.160265 | 0.234879 | -0.044441 | 121.729563 | 171 | 182 | 0 |
| 7 | 2021-05-08 | 0.689077 | 0.212600 | 0.538309 | -0.731913 | 0.273467 | -0.005853 | 114.772056 | 174 | 182 | 0 |
| 8 | 2021-05-09 | 3.885060 | 1.198652 | 1.405254 | 0.135033 | 0.176194 | -0.103126 | 118.890741 | 174 | 182 | 0 |
| 9 | 2021-05-10 | 4.024780 | 1.241760 | 1.510946 | 0.240724 | 0.168790 | -0.110530 | 118.633553 | 172 | 182 | 0 |

## MTM return correlation vs phase 0

| phase_offset_days | mtm_return_corr_vs_phase0 |
| --- | --- |
| 0 | 1.000000 |
| 1 | -0.003655 |
| 2 | -0.003535 |
| 3 | -0.003364 |
| 4 | -0.004686 |
| 5 | -0.003378 |
| 6 | -0.003782 |
| 7 | -0.001855 |
| 8 | -0.004745 |
| 9 | -0.005084 |

## Robustness thresholds

- min_net_return_ratio_vs_phase0: `0.5`
- min_sharpe: `0.75`
- max_dd_abs: `0.45`
- max_dd_delta_vs_phase0: `0.1`

## Interpretation guardrails

- This test keeps alpha score, features, PIT universe policy, eligibility, risk brakes, reference capital, and execution cost scenario fixed.
- The only changed variable is the 10d rebalance phase: phase 0 starts from the original first timestamp; phase 1 starts one daily bar later; ...; phase 9 starts nine daily bars later.
- Each shifted phase uses the remaining available history to mimic choosing a different initial 10d anchor at launch.
- This is a robustness diagnostic, not a live-trading permission gate by itself.

## Robustness failures

- `phase_data_gap_blockers` phase=4: {'code': 'phase_data_gap_blockers', 'phase_offset_days': 4, 'net_return': 4.200201843042721, 'sharpe': 1.38274377136253, 'max_drawdown': 0.29410644762163457, 'net_return_ratio_vs_phase0': 1.2958823700014377, 'max_drawdown_delta_vs_phase0': 0.014786646017364125}
- `phase_net_return_ratio_too_low` phase=7: {'code': 'phase_net_return_ratio_too_low', 'phase_offset_days': 7, 'net_return': 0.6890774783373126, 'sharpe': 0.5383091690547039, 'max_drawdown': 0.2734669313255272, 'net_return_ratio_vs_phase0': 0.2126001056881324, 'max_drawdown_delta_vs_phase0': -0.005852870278743261}
- `phase_sharpe_too_low` phase=7: {'code': 'phase_sharpe_too_low', 'phase_offset_days': 7, 'net_return': 0.6890774783373126, 'sharpe': 0.5383091690547039, 'max_drawdown': 0.2734669313255272, 'net_return_ratio_vs_phase0': 0.2126001056881324, 'max_drawdown_delta_vs_phase0': -0.005852870278743261}

## Blockers

- `phase_execution_data_gap_blockers`: {'code': 'phase_execution_data_gap_blockers', 'phase_offset_days': 4, 'data_gap_blocker_count': 1, 'sample': ['ZEC: missing fill row for execution venue']}

## Artifacts

- summary_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase_sensitivity_20260521\summary.json`
- phase_metrics_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase_sensitivity_20260521\phase_metrics.csv`
- period_returns_long_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase_sensitivity_20260521\period_returns_long.csv`
- paired_mtm_curve_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase_sensitivity_20260521\paired_mtm_curve.csv`
- phase_correlation_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase_sensitivity_20260521\phase_correlation.csv`
- scored_frame_diagnostics_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase_sensitivity_20260521\scored_frame_diagnostics.json`
- markdown_report: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\docs\quant_research\03_alpha_branches\hv_balanced_rebalance_phase_sensitivity_2026_05_21.md`
