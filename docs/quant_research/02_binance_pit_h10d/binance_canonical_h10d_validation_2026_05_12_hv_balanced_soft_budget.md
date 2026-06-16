# Binance-Canonical H10D Validation

`Strategy: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget`
`Parent: v5_binance_pit_top_mid_h10d_pruned3_high_vol_rebound_short_brake`
`Status: passed`

## Metrics

| Scenario | Net return | Sharpe | Max DD | Rebalances | Max trade participation |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 3.241191 | 1.270 | 0.279320 | 183 | 0.000015 |
| stress | 3.202118 | 1.263 | 0.279618 | 183 | 0.000030 |

## Blockers

- none

## Execution Gap Policy

- mode: `pit_recent_completeness_only`
- excluded_symbols: `none`
- residual_data_gap_blockers: `0`

## Risk Overlay

- mode: `pruned3_hv_balanced_soft_portfolio_budget`
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
- baseline_base_net_return: `3.241191`

| Removed feature | Weight share | Base-minus-LOO net | Base-minus-LOO Sharpe |
| --- | ---: | ---: | ---: |
| downside_upside_vol_ratio_30 | 0.137 | 1.480090 | 0.356 |
| intraday_realized_vol_4h_to_1d_smooth_60 | 0.274 | 1.003452 | 0.201 |
| realized_volatility_5 | 0.137 | 0.759706 | 0.139 |
| distance_to_high_60 | 0.247 | 0.410136 | 0.106 |
| distance_to_high_5 | 0.205 | -0.202032 | -0.051 |

Negative LOO contributors:
- `distance_to_high_5` base-minus-LOO net `-0.202032`

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
| long_only_gross_1x | 0.970454 | 0.513 | 0.960752 | 0.000004 |
| short_disabled_cash_half | 0.650047 | 0.492 | 0.646037 | 0.000002 |
| short_veto_ohlcv_squeeze_guard | 1.997935 | 0.964 | 1.971313 | 0.000015 |

## Holdout Gates

- legacy_a_b_role: `diagnostic`
- legacy_a_b_positive_count: `2`
- legacy_a_b_gate_diagnostic: `True`
- stratified_repeated_hard_gate: `True`
- stratified_policy: `repeat_count=8, min_positive_fraction=0.750, require_gap_free=True`

| Holdout | Fold count | Positive folds | Positive fraction | Gap-free folds | Min net | Median net | Max net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stratified_repeated | 16 | 13 | 0.812 | 16 | -0.264864 | 0.553959 | 2.617039 |

| Diagnostic split | Net return | Sharpe | Subject count |
| --- | ---: | ---: | ---: |
| holdout_a | 1.197807 | 0.831 | 40 |
| holdout_b | 0.134215 | 0.244 | 38 |

## Artifact Paths

- validation_report: `artifacts\qr\hv_balanced\validation_report.json`
- dataset_manifest: `artifacts\qr\hv_balanced\dataset_manifest.json`
- gap_audit: `artifacts\qr\hv_balanced\gap_audit.json`
- feature_manifest: `artifacts\qr\hv_balanced\feature_manifest.json`
- aligned_period_returns: `artifacts\qr\hv_balanced\aligned_period_returns.csv`
- universe_membership: `artifacts\qr\hv_balanced\universe_membership.csv`
- position_attribution: `artifacts\qr\hv_balanced\position_attribution.csv`
- attribution_by_side_year: `artifacts\qr\hv_balanced\attribution_by_side_year.csv`
- attribution_by_symbol_year: `artifacts\qr\hv_balanced\attribution_by_symbol_year.csv`
- factor_leave_one_out: `artifacts\qr\hv_balanced\factor_leave_one_out.csv`
- factor_leave_one_out_summary: `artifacts\qr\hv_balanced\factor_leave_one_out_summary.json`
- factor_leave_one_out_by_side: `artifacts\qr\hv_balanced\factor_leave_one_out_by_side.csv`
- factor_leave_one_out_by_year: `artifacts\qr\hv_balanced\factor_leave_one_out_by_year.csv`
- factor_leave_one_out_by_side_year: `artifacts\qr\hv_balanced\factor_leave_one_out_by_side_year.csv`
- paper_shadow_execution_ledger: `artifacts\qr\hv_balanced\paper_shadow_execution_ledger.csv`
- paper_shadow_execution_summary: `artifacts\qr\hv_balanced\paper_shadow_execution_summary.json`
- ablation_summary: `artifacts\qr\hv_balanced\ablation_summary.json`
- ablation_period_returns: `artifacts\qr\hv_balanced\ablation_period_returns.csv`

## Sidecar Policy

CoinGlass, OI, liquidation, orderbook, top-trader, taker, funding, and basis columns are excluded from core alpha.
