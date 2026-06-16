# Binance-Canonical H10D Validation

`Strategy: v5_binance_pit_top_mid_h10d_pruned3_hv_mild_soft_budget`
`Parent: v5_binance_pit_top_mid_h10d_pruned3_high_vol_rebound_short_brake`
`Status: passed`

## Metrics

| Scenario | Net return | Sharpe | Max DD | Rebalances | Max trade participation |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 3.361901 | 1.282 | 0.282072 | 183 | 0.000015 |
| stress | 3.322109 | 1.275 | 0.282376 | 183 | 0.000030 |

## Blockers

- none

## Execution Gap Policy

- mode: `pit_recent_completeness_only`
- excluded_symbols: `none`
- residual_data_gap_blockers: `0`

## Risk Overlay

- mode: `pruned3_hv_mild_soft_portfolio_budget`
- source_boundary: `binance_ohlcv_features_and_closed_strategy_pnl_only`
- portfolio_drawdown_brake: `enabled=True, window_days=180, dd_5pct_multiplier=0.700, dd_10pct_multiplier=0.500`
- short_squeeze_brake_enabled: `False`
- high_vol_rebound_short_brake: `enabled=True, short_multiplier=0.500, severe_short_multiplier=0.250`
- base_max_drawdown_under_cap: `True`

## Attribution

| Side | Gross contrib | Funding cost | Net before trade cost | Positions | Hit rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| long | 0.793141 | 0.096085 | 0.697056 | 543 | 0.532 |
| short | 1.026825 | -0.040808 | 1.067632 | 564 | 0.574 |

## Factor Leave-One-Out

- method: `leave_one_out_rescore_full_portfolio`
- baseline_base_net_return: `3.361901`

| Removed feature | Weight share | Base-minus-LOO net | Base-minus-LOO Sharpe |
| --- | ---: | ---: | ---: |
| downside_upside_vol_ratio_30 | 0.137 | 1.514824 | 0.351 |
| intraday_realized_vol_4h_to_1d_smooth_60 | 0.274 | 1.059365 | 0.201 |
| realized_volatility_5 | 0.137 | 0.837118 | 0.148 |
| distance_to_high_60 | 0.247 | 0.446859 | 0.111 |
| distance_to_high_5 | 0.205 | -0.143540 | -0.045 |

Negative LOO contributors:
- `distance_to_high_5` base-minus-LOO net `-0.143540`

## Paper Shadow Execution

- execution_mode: `paper_shadow_no_live_orders`
- ledger_row_count: `1453`
- order_row_count: `822`
- net_contribution: `1.676713`
- max_trade_participation_rate: `0.000015`
- data_gap_blockers: `0`

## Ablations

| Ablation | Base net | Base Sharpe | Stress net | Max participation |
| --- | ---: | ---: | ---: | ---: |
| long_only_gross_1x | 0.900723 | 0.502 | 0.891335 | 0.000004 |
| short_disabled_cash_half | 0.612825 | 0.472 | 0.608878 | 0.000002 |
| short_veto_ohlcv_squeeze_guard | 2.062347 | 0.969 | 2.034671 | 0.000015 |

## Holdout Gates

- legacy_a_b_role: `diagnostic`
- legacy_a_b_positive_count: `2`
- legacy_a_b_gate_diagnostic: `True`
- stratified_repeated_hard_gate: `True`
- stratified_policy: `repeat_count=8, min_positive_fraction=0.750, require_gap_free=True`

| Holdout | Fold count | Positive folds | Positive fraction | Gap-free folds | Min net | Median net | Max net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stratified_repeated | 16 | 13 | 0.812 | 16 | -0.277899 | 0.552644 | 2.652119 |

| Diagnostic split | Net return | Sharpe | Subject count |
| --- | ---: | ---: | ---: |
| holdout_a | 1.184720 | 0.819 | 40 |
| holdout_b | 0.154283 | 0.257 | 38 |

## Artifact Paths

- validation_report: `artifacts\qr\hv_mild\validation_report.json`
- dataset_manifest: `artifacts\qr\hv_mild\dataset_manifest.json`
- gap_audit: `artifacts\qr\hv_mild\gap_audit.json`
- feature_manifest: `artifacts\qr\hv_mild\feature_manifest.json`
- aligned_period_returns: `artifacts\qr\hv_mild\aligned_period_returns.csv`
- universe_membership: `artifacts\qr\hv_mild\universe_membership.csv`
- position_attribution: `artifacts\qr\hv_mild\position_attribution.csv`
- attribution_by_side_year: `artifacts\qr\hv_mild\attribution_by_side_year.csv`
- attribution_by_symbol_year: `artifacts\qr\hv_mild\attribution_by_symbol_year.csv`
- factor_leave_one_out: `artifacts\qr\hv_mild\factor_leave_one_out.csv`
- factor_leave_one_out_summary: `artifacts\qr\hv_mild\factor_leave_one_out_summary.json`
- factor_leave_one_out_by_side: `artifacts\qr\hv_mild\factor_leave_one_out_by_side.csv`
- factor_leave_one_out_by_year: `artifacts\qr\hv_mild\factor_leave_one_out_by_year.csv`
- factor_leave_one_out_by_side_year: `artifacts\qr\hv_mild\factor_leave_one_out_by_side_year.csv`
- paper_shadow_execution_ledger: `artifacts\qr\hv_mild\paper_shadow_execution_ledger.csv`
- paper_shadow_execution_summary: `artifacts\qr\hv_mild\paper_shadow_execution_summary.json`
- ablation_summary: `artifacts\qr\hv_mild\ablation_summary.json`
- ablation_period_returns: `artifacts\qr\hv_mild\ablation_period_returns.csv`

## Sidecar Policy

CoinGlass, OI, liquidation, orderbook, top-trader, taker, funding, and basis columns are excluded from core alpha.
