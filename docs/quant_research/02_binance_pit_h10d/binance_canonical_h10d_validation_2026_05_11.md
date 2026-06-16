# Binance-Canonical H10D Validation

`Strategy: v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1`
`Parent: v5_binance_pit_top_mid_h10d_pruned3`
`Status: passed`

## Metrics

| Scenario | Net return | Sharpe | Max DD | Rebalances | Max trade participation |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 1.461132 | 1.013 | 0.210697 | 183 | 0.000015 |
| stress | 1.444297 | 1.006 | 0.211540 | 183 | 0.000030 |

## Blockers

- none

## Execution Gap Policy

- mode: `pit_recent_completeness_only`
- excluded_symbols: `none`
- residual_data_gap_blockers: `0`

## Risk Overlay

- mode: `pruned3_risk_brake_v1`
- source_boundary: `binance_ohlcv_features_and_closed_strategy_pnl_only`
- portfolio_drawdown_brake: `enabled=True, window_days=120, dd_5pct_multiplier=0.700, dd_10pct_multiplier=0.500`
- short_squeeze_brake_enabled: `True`
- high_vol_rebound_short_brake: `enabled=True, short_multiplier=0.500, severe_short_multiplier=0.250`
- base_max_drawdown_under_cap: `True`

## Attribution

| Side | Gross contrib | Funding cost | Net before trade cost | Positions | Hit rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| long | 0.791666 | 0.096206 | 0.695461 | 545 | 0.534 |
| short | 0.936677 | -0.041929 | 0.978607 | 536 | 0.565 |

## Factor Leave-One-Out

- method: `leave_one_out_rescore_full_portfolio`
- baseline_base_net_return: `1.461132`

| Removed feature | Weight share | Base-minus-LOO net | Base-minus-LOO Sharpe |
| --- | ---: | ---: | ---: |
| intraday_realized_vol_4h_to_1d_smooth_60 | 0.274 | 1.016289 | 0.521 |
| realized_volatility_5 | 0.137 | 0.584121 | 0.250 |
| distance_to_high_60 | 0.247 | 0.556058 | 0.269 |
| distance_to_high_5 | 0.205 | 0.418072 | 0.177 |
| downside_upside_vol_ratio_30 | 0.137 | 0.228351 | 0.119 |

## Paper Shadow Execution

- execution_mode: `paper_shadow_no_live_orders`
- ledger_row_count: `1429`
- order_row_count: `830`
- net_contribution: `1.585821`
- max_trade_participation_rate: `0.000015`
- data_gap_blockers: `0`

## Ablations

| Ablation | Base net | Base Sharpe | Stress net | Max participation |
| --- | ---: | ---: | ---: | ---: |
| long_only_gross_1x | 0.238308 | 0.282 | 0.233766 | 0.000003 |
| short_disabled_cash_half | 1.598360 | 0.977 | 1.592631 | 0.000003 |
| short_veto_ohlcv_squeeze_guard | 1.140087 | 0.836 | 1.125335 | 0.000015 |

## Holdout Gates

- legacy_a_b_role: `diagnostic`
- legacy_a_b_positive_count: `1`
- legacy_a_b_gate_diagnostic: `False`
- stratified_repeated_hard_gate: `True`
- stratified_policy: `repeat_count=8, min_positive_fraction=0.750, require_gap_free=True`

| Holdout | Fold count | Positive folds | Positive fraction | Gap-free folds | Min net | Median net | Max net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stratified_repeated | 16 | 12 | 0.750 | 16 | -0.390415 | 0.380289 | 1.580929 |

| Diagnostic split | Net return | Sharpe | Subject count |
| --- | ---: | ---: | ---: |
| holdout_a | 0.716362 | 0.737 | 40 |
| holdout_b | -0.343789 | -0.186 | 38 |

## Artifact Paths

- validation_report: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\validation_report.json`
- dataset_manifest: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\dataset_manifest.json`
- gap_audit: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\gap_audit.json`
- feature_manifest: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\feature_manifest.json`
- aligned_period_returns: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\aligned_period_returns.csv`
- universe_membership: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\universe_membership.csv`
- position_attribution: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\position_attribution.csv`
- attribution_by_side_year: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\attribution_by_side_year.csv`
- attribution_by_symbol_year: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\attribution_by_symbol_year.csv`
- factor_leave_one_out: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\factor_leave_one_out.csv`
- factor_leave_one_out_summary: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\factor_leave_one_out_summary.json`
- factor_leave_one_out_by_side: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\factor_leave_one_out_by_side.csv`
- factor_leave_one_out_by_year: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\factor_leave_one_out_by_year.csv`
- factor_leave_one_out_by_side_year: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\factor_leave_one_out_by_side_year.csv`
- paper_shadow_execution_ledger: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\paper_shadow_execution_ledger.csv`
- paper_shadow_execution_summary: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\paper_shadow_execution_summary.json`
- ablation_summary: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\ablation_summary.json`
- ablation_period_returns: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1\ablation_period_returns.csv`

## Sidecar Policy

CoinGlass, OI, liquidation, orderbook, top-trader, taker, funding, and basis columns are excluded from core alpha.
