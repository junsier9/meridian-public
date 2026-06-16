# hv_balanced multi-phase sleeve ensemble diagnostic

- generated_at_utc: `2026-05-22T15:23:43Z`
- status: `passed`
- gate_status: `passed`
- scenario: `base`
- config_path: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\config\quant_research\binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json`
- phases: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]`
- sleeve_weight: `0.1`
- raw_scored_row_count: `142262`
- eligible_scored_row_count: `140441`
- multiphase_execution_gap_policy_status: `ok`
- multiphase_excluded_symbols: `['ZECUSDT']`
- ensemble_net_return: `3.2417753244542533`
- ensemble_sharpe_daily_booking_approx: `3.569629670302714`
- ensemble_max_drawdown: `0.16950990122559106`
- true_daily_mtm_net_return: `2.6710908117318963`
- true_daily_mtm_sharpe: `1.1792002607110752`
- true_daily_mtm_max_drawdown: `0.24072503119729158`
- max_aggregate_gross_weight: `1.0000000000000002`
- max_event_target_turnover: `0.10000000000000007`

## Decision

- This is a paper-only diagnostic target construction; it does not alter the live supervisor and does not touch Binance APIs.
- The equal-weight 10-sleeve design is the preferred repair path for phase instability because it removes dependence on a single arbitrary 10d start date instead of selecting a historically lucky phase.
- The historical multi-phase target book now applies an explicit execution-path eligible-universe rule before target aggregation; this is a validation policy, not live authorization.
- Promotion path is still gated: executable paper shadow first, then no-order live target comparison, then live supervisor integration only after explicit approval.

## Execution-Path Eligibility Policy

- mode: `drop_selected_path_gap_symbols_across_phases`
- status: `ok`
- excluded_symbols: `['ZECUSDT']`
- residual_data_gap_blockers: `0`
- future_execution_path_availability_usage: `True`
- live_transfer_policy: `not live-tradable as-is; live integration must use current exchange symbol filters, fresh market data, and order-size rules instead of historical future-path exclusion`

## Metrics

| label | net_return | sharpe | max_drawdown | max_aggregate_gross_weight |
| --- | --- | --- | --- | --- |
| single_phase0 | 3.241191 | 1.270222 | 0.279320 | 1.000000 |
| single_phase7_weak | 0.689077 | 0.538309 | 0.273467 | 1.000000 |
| equal_weight_10_phase_sleeves | 3.241775 | 3.569630 | 0.169510 | 1.000000 |

## True Daily MTM

- This section marks every active sleeve position from its fill price through each daily close, then books fee/slippage on fill dates.
- It is the stricter paper-ledger check for the headline Sharpe; event-booked metrics remain a phase-robustness diagnostic.

| date_utc | active_position_day_count | active_symbol_count | active_sleeve_count | gross_return_before_costs | funding_cost_return | fee_cost_return | slippage_cost_return | net_daily_return | daily_mtm_equity | daily_mtm_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-19 | 66 | 11 | 10 | 0.011070 | 0.000045 | 0.000019 | 0.000005 | 0.011001 | 3.647782 | 0.014963 |
| 2026-04-20 | 66 | 10 | 10 | 0.004563 | 0.000218 | 0.000020 | 0.000005 | 0.004320 | 3.663539 | 0.010708 |
| 2026-04-21 | 60 | 10 | 10 | -0.001186 | 0.000098 | 0.000060 | 0.000015 | -0.001360 | 3.658557 | 0.012053 |
| 2026-04-22 | 54 | 10 | 9 | 0.006022 | 0.000060 | 0.000060 | 0.000015 | 0.005886 | 3.680092 | 0.006238 |
| 2026-04-23 | 48 | 10 | 8 | 0.000093 | 0.000083 | 0.000060 | 0.000015 | -0.000065 | 3.679851 | 0.006303 |
| 2026-04-24 | 42 | 10 | 7 | -0.002635 | 0.000016 | 0.000060 | 0.000015 | -0.002726 | 3.669819 | 0.009012 |
| 2026-04-25 | 36 | 9 | 6 | 0.001094 | -0.000015 | 0.000060 | 0.000015 | 0.001034 | 3.673613 | 0.007987 |
| 2026-04-26 | 30 | 9 | 5 | 0.001989 | 0.000105 | 0.000060 | 0.000015 | 0.001808 | 3.680256 | 0.006194 |
| 2026-04-27 | 24 | 9 | 4 | -0.002404 | 0.000035 | 0.000038 | 0.000009 | -0.002486 | 3.671107 | 0.008664 |
| 2026-04-28 | 18 | 8 | 3 | -0.001443 | 0.000002 | 0.000038 | 0.000009 | -0.001492 | 3.665629 | 0.010143 |
| 2026-04-29 | 12 | 6 | 2 | 0.001371 | 0.000005 | 0.000055 | 0.000014 | 0.001298 | 3.670386 | 0.008859 |
| 2026-04-30 | 6 | 6 | 1 | 0.000267 | 0.000000 | 0.000060 | 0.000015 | 0.000192 | 3.671091 | 0.008669 |

## Phase Metrics

| phase_offset_days | net_return | net_return_ratio_vs_phase0 | sharpe | max_drawdown | turnover | trade_count | rebalance_count | data_gap_blocker_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 3.241191 | 1.000000 | 1.270222 | 0.279320 | 115.327476 | 173 | 183 | 0 |
| 1 | 2.696012 | 0.831797 | 1.068616 | 0.285370 | 121.925007 | 175 | 183 | 0 |
| 2 | 2.155949 | 0.665172 | 1.032601 | 0.200850 | 116.658579 | 168 | 183 | 0 |
| 3 | 2.102424 | 0.648658 | 0.981979 | 0.295930 | 119.491812 | 169 | 183 | 0 |
| 4 | 4.246283 | 1.310100 | 1.389621 | 0.294106 | 113.982048 | 173 | 183 | 0 |
| 5 | 2.035205 | 0.627919 | 0.988399 | 0.224505 | 119.568333 | 174 | 182 | 0 |
| 6 | 2.814419 | 0.868329 | 1.109957 | 0.234879 | 121.729563 | 171 | 182 | 0 |
| 7 | 0.689077 | 0.212600 | 0.538309 | 0.273467 | 114.772056 | 174 | 182 | 0 |
| 8 | 3.885060 | 1.198652 | 1.405254 | 0.176194 | 118.890741 | 174 | 182 | 0 |
| 9 | 4.024780 | 1.241760 | 1.510946 | 0.168790 | 118.633553 | 172 | 182 | 0 |

## Recent Aggregate Target Book

| date_utc | aggregate_position_count | aggregate_gross_weight | aggregate_long_gross_weight | aggregate_short_gross_weight | aggregate_net_weight | max_abs_symbol_weight | aggregate_target_turnover_vs_previous_event | active_sleeve_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-04-19 | 10 | 0.916594 | 0.495797 | 0.420797 | 0.075000 | 0.165266 | 0.031343 | 10 |
| 2026-04-20 | 10 | 0.916594 | 0.495797 | 0.420797 | 0.075000 | 0.165266 | 0.033333 | 10 |
| 2026-04-21 | 10 | 0.816594 | 0.445797 | 0.370797 | 0.075000 | 0.148599 | 0.100000 | 9 |
| 2026-04-22 | 10 | 0.716594 | 0.395797 | 0.320797 | 0.075000 | 0.131932 | 0.100000 | 8 |
| 2026-04-23 | 10 | 0.616594 | 0.345797 | 0.270797 | 0.075000 | 0.115266 | 0.100000 | 7 |
| 2026-04-24 | 9 | 0.516594 | 0.295797 | 0.220797 | 0.075000 | 0.098599 | 0.100000 | 6 |
| 2026-04-25 | 9 | 0.416594 | 0.245797 | 0.170797 | 0.075000 | 0.081932 | 0.100000 | 5 |
| 2026-04-26 | 9 | 0.316594 | 0.195797 | 0.120797 | 0.075000 | 0.065266 | 0.100000 | 4 |
| 2026-04-27 | 8 | 0.254094 | 0.145797 | 0.108297 | 0.037500 | 0.048599 | 0.062500 | 3 |
| 2026-04-28 | 6 | 0.191594 | 0.095797 | 0.095797 | 0.000000 | 0.031932 | 0.062500 | 2 |
| 2026-04-29 | 6 | 0.100000 | 0.050000 | 0.050000 | 0.000000 | 0.016667 | 0.091594 | 1 |
| 2026-04-30 | 0 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.100000 | 0 |

## Reconciliation

| phase_offset_days | status | official_period_count | fast_period_count | timestamp_join_mismatch_count | net_period_return_max_abs_delta_fast_minus_official | gross_return_before_costs_max_abs_delta_fast_minus_official | funding_cost_return_max_abs_delta_fast_minus_official |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | passed | 183 | 183 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 1 | passed | 183 | 183 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 2 | passed | 183 | 183 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 3 | passed | 183 | 183 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 4 | passed | 183 | 183 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 5 | passed | 182 | 182 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 6 | passed | 182 | 182 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 7 | passed | 182 | 182 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 8 | passed | 182 | 182 | 0 | 0.000000 | 0.000000 | 0.000000 |
| 9 | passed | 182 | 182 | 0 | 0.000000 | 0.000000 | 0.000000 |

## Gate Failures

- none

## Blockers

- none

## Artifacts

- summary_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\summary.json`
- phase_metrics_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\phase_metrics.csv`
- ensemble_metrics_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\ensemble_metrics.csv`
- sleeve_period_returns_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\sleeve_period_returns.csv`
- ensemble_period_returns_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\ensemble_period_returns.csv`
- sleeve_position_attribution_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\sleeve_position_attribution.csv`
- sleeve_paper_shadow_ledger_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\sleeve_paper_shadow_ledger.csv`
- aggregate_targets_by_event_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\aggregate_targets_by_event.csv`
- aggregate_target_totals_by_event_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\aggregate_target_totals_by_event.csv`
- phase_fast_reconciliation_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\phase_fast_reconciliation.csv`
- multiphase_execution_gap_policy_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\multiphase_execution_gap_policy.json`
- true_daily_mtm_position_ledger_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\true_daily_mtm_position_ledger.csv`
- true_daily_mtm_returns_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\true_daily_mtm_returns.csv`
- true_daily_mtm_metrics_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\hv_balanced_multiphase_sleeve_ensemble_20260521\true_daily_mtm_metrics.json`
- markdown_report: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\docs\quant_research\03_alpha_branches\hv_balanced_multiphase_sleeve_ensemble_2026_05_21.md`

## Method Notes

- Each sleeve runs the original frozen `hv_balanced` 10d policy with one different daily start offset.
- Per-sleeve returns, costs, funding, and targets are scaled by `1/10`; aggregate targets are summed across active sleeves.
- Return metrics are daily-booking approximations over sleeve rebalance events, matching the phase sensitivity diagnostic style.
- True daily MTM metrics use the daily close-to-close mark path of each fixed-quantity sleeve holding and book trade costs on fill dates.
- This runner is intentionally offline and should be treated as a candidate repair artifact, not as live authorization.
