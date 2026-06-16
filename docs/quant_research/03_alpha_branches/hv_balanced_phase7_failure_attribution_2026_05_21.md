# hv_balanced phase 7 failure attribution

- generated_at_utc: `2026-05-21T13:37:56Z`
- status: `passed`
- scenario: `base`
- baseline_phase: `0`
- diagnosed_phase: `7`
- phase0_net_return: `3.241190666895222`
- phase7_net_return: `0.6890774783373126`
- phase7_vs_phase0_net_ratio: `0.2126001056881324`
- fast_period_reconciliation_status_phase0: `passed`
- fast_period_reconciliation_status_phase7: `passed`

## Worst phase 7 periods

| fill_date_utc | exit_date_utc | net_period_return | gross_return_before_costs | funding_cost_return | turnover | held_position_count | long_count | short_count | portfolio_throttle_multiplier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023-12-15 | 2023-12-25 | -0.212446 | -0.216243 | -0.004299 | 0.666667 | 6 | 3 | 3 | 1.000000 |
| 2025-11-04 | 2025-11-14 | -0.165831 | -0.161987 | 0.003594 | 0.333333 | 6 | 3 | 3 | 1.000000 |
| 2021-12-15 | 2021-12-25 | -0.124050 | -0.122950 | 0.000598 | 0.666667 | 6 | 3 | 3 | 1.000000 |
| 2021-12-25 | 2022-01-04 | -0.102317 | -0.102288 | -0.000238 | 0.354711 | 6 | 3 | 3 | 0.967934 |
| 2023-01-19 | 2023-01-29 | -0.093308 | -0.092995 | 0.000061 | 0.333333 | 6 | 3 | 3 | 1.000000 |
| 2025-07-07 | 2025-07-17 | -0.090487 | -0.089775 | 0.000210 | 0.666667 | 6 | 3 | 3 | 1.000000 |
| 2022-06-13 | 2022-06-23 | -0.088205 | -0.091174 | -0.003532 | 0.750228 | 6 | 3 | 3 | 1.000000 |
| 2022-12-30 | 2023-01-09 | -0.082986 | -0.080604 | 0.001880 | 0.666667 | 6 | 3 | 3 | 1.000000 |
| 2022-03-15 | 2022-03-25 | -0.078537 | -0.076155 | 0.001869 | 0.680206 | 6 | 3 | 3 | 1.000000 |
| 2022-07-13 | 2022-07-23 | -0.065522 | -0.061717 | 0.003053 | 1.000000 | 6 | 3 | 3 | 1.000000 |
| 2021-07-28 | 2021-08-07 | -0.062557 | -0.063119 | -0.000811 | 0.333333 | 6 | 3 | 3 | 1.000000 |
| 2021-10-16 | 2021-10-26 | -0.060980 | -0.065037 | -0.004558 | 0.666667 | 6 | 3 | 3 | 1.000000 |

## Worst symbol/side deltas vs phase 0

| subject | side | phase7_net_before_trade_cost_contribution | phase0_net_before_trade_cost_contribution | net_before_trade_cost_contribution_delta_phase7_minus_phase0 | phase7_position_count | phase0_position_count |
| --- | --- | --- | --- | --- | --- | --- |
| AXS | short | -0.166237 | 0.001155 | -0.167393 | 25.000000 | 27.000000 |
| CRV | short | -0.094710 | 0.039012 | -0.133722 | 58.000000 | 54.000000 |
| NEAR | short | -0.326433 | -0.204964 | -0.121469 | 62.000000 | 58.000000 |
| DOT | short | -0.004881 | 0.105337 | -0.110218 | 27.000000 | 28.000000 |
| DOGE | long | 0.041026 | 0.140796 | -0.099770 | 9.000000 | 7.000000 |
| AAVE | short | -0.075411 | 0.015406 | -0.090818 | 32.000000 | 38.000000 |
| 1000SHIB | short | 0.078608 | 0.150095 | -0.071487 | 19.000000 | 27.000000 |
| LINK | long | -0.046538 | 0.011617 | -0.058155 | 6.000000 | 3.000000 |
| THETA | short | -0.083056 | -0.027085 | -0.055971 | 4.000000 | 5.000000 |
| FIL | short | 0.173439 | 0.224239 | -0.050800 | 55.000000 | 48.000000 |
| DOGE | short | 0.024295 | 0.072344 | -0.048048 | 7.000000 | 6.000000 |
| CELR | short | -0.006634 | 0.040536 | -0.047170 | 1.000000 | 2.000000 |

## Worst year/side deltas vs phase 0

| year | side | phase7_net_before_trade_cost_contribution | phase0_net_before_trade_cost_contribution | net_before_trade_cost_contribution_delta_phase7_minus_phase0 |
| --- | --- | --- | --- | --- |
| 2025 | short | 0.143633 | 0.473949 | -0.330316 |
| 2021 | short | -0.259078 | 0.045822 | -0.304901 |
| 2022 | short | 0.577969 | 0.842646 | -0.264677 |
| 2025 | long | -0.040915 | 0.119707 | -0.160622 |
| 2024 | long | 0.314970 | 0.460894 | -0.145924 |
| 2026 | long | -0.123243 | -0.118884 | -0.004360 |
| 2022 | long | -0.424998 | -0.430137 | 0.005139 |
| 2023 | long | 0.438892 | 0.401746 | 0.037146 |
| 2023 | short | -0.443159 | -0.482941 | 0.039782 |
| 2026 | short | 0.229324 | 0.189375 | 0.039950 |
| 2024 | short | 0.053850 | -0.015442 | 0.069291 |
| 2021 | long | 0.316109 | 0.208278 | 0.107831 |

## Calendar-overlap comparison

| phase_fill_date_utc | phase_exit_date_utc | phase_net_period_return | baseline_fill_date_utc | baseline_exit_date_utc | baseline_net_period_return | overlap_days | net_period_return_delta_phase_minus_baseline |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2023-12-15 | 2023-12-25 | -0.212446 | 2023-12-18 | 2023-12-28 | -0.093670 | 7.000000 | -0.118776 |
| 2025-11-04 | 2025-11-14 | -0.165831 | 2025-11-07 | 2025-11-17 | 0.082738 | 7.000000 | -0.248569 |
| 2021-12-15 | 2021-12-25 | -0.124050 | 2021-12-18 | 2021-12-28 | -0.036365 | 7.000000 | -0.087685 |
| 2021-12-25 | 2022-01-04 | -0.102317 | 2021-12-28 | 2022-01-07 | -0.140248 | 7.000000 | 0.037930 |
| 2023-01-19 | 2023-01-29 | -0.093308 | 2023-01-22 | 2023-02-01 | 0.009226 | 7.000000 | -0.102533 |
| 2025-07-07 | 2025-07-17 | -0.090487 | 2025-07-10 | 2025-07-20 | -0.053828 | 7.000000 | -0.036659 |
| 2022-06-13 | 2022-06-23 | -0.088205 | 2022-06-16 | 2022-06-26 | -0.057606 | 7.000000 | -0.030599 |
| 2022-12-30 | 2023-01-09 | -0.082986 | 2023-01-02 | 2023-01-12 | -0.078891 | 7.000000 | -0.004095 |
| 2022-03-15 | 2022-03-25 | -0.078537 | 2022-03-18 | 2022-03-28 | -0.012302 | 7.000000 | -0.066234 |
| 2022-07-13 | 2022-07-23 | -0.065522 | 2022-07-16 | 2022-07-26 | 0.003367 | 7.000000 | -0.068889 |
| 2021-07-28 | 2021-08-07 | -0.062557 | 2021-07-31 | 2021-08-10 | -0.065010 | 7.000000 | 0.002453 |
| 2021-10-16 | 2021-10-26 | -0.060980 | 2021-10-19 | 2021-10-29 | 0.060741 | 7.000000 | -0.121722 |

## Diagnosis

- worst_5_phase7_period_return_sum: `-0.6979516255479202`
- phase7_negative_period_count: `69`
- phase7_median_period_return: `0.005731811144329737`
- recommended_response: `prefer_multi_phase_or_staggered_sleeves_over_anchor_selection`

## Decision

- Do not select a different single anchor just because phase 8/9 looked better in this backtest; that would be direct in-sample anchor overfit.
- Prefer a multi-phase / staggered-sleeve design: split capital across the 10 daily offsets and let each sleeve rebalance every 10 days. This lowers dependence on any one arbitrary start date while preserving the 10d holding logic.
- Paired MTM diagnostic from the phase sweep gives an equal-weight 10-phase ensemble net_return `3.237652`, approximate daily-booking Sharpe `3.567235`, and max_drawdown `0.169510`; this is diagnostic only and still needs a dedicated executable backtest before promotion.
- The failure pattern is not a single bad print. Phase 7 has `69` negative periods and recurring short-side timing damage, especially in rebound windows for AXS/CRV/NEAR/DOT/AAVE and selected 2021/2022/2025 short books.

## Guardrails

- This diagnostic does not change live trading state and does not submit orders.
- Fast ledger attribution is reconciled against official period returns before interpretation.
- Position rows explain concentration and direction; headline net return remains compounded at the portfolio period level.

## Blockers

- none

## Artifacts

- summary_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\summary.json`
- phase0_position_attribution_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\position_attribution_phase0.csv`
- phase7_position_attribution_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\position_attribution_phase7.csv`
- phase0_paper_shadow_ledger_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\paper_shadow_ledger_phase0.csv`
- phase7_paper_shadow_ledger_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\paper_shadow_ledger_phase7.csv`
- phase0_period_summary_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\period_summary_phase0.csv`
- phase7_period_summary_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\period_summary_phase7.csv`
- worst_phase7_periods_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\worst_phase7_periods.csv`
- symbol_side_delta_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\symbol_side_delta_phase7_minus_phase0.csv`
- year_side_delta_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\year_side_delta_phase7_minus_phase0.csv`
- symbol_year_side_delta_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\symbol_year_side_delta_phase7_minus_phase0.csv`
- calendar_overlap_compare_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase7_failure_attribution_20260521\calendar_overlap_compare.csv`
- phase_ensemble_diagnostic_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\rebalance_phase_sensitivity_20260521\phase_ensemble_diagnostic.csv`
- markdown_report: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\docs\quant_research\03_alpha_branches\hv_balanced_phase7_failure_attribution_2026_05_21.md`
