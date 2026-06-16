# Binance-Canonical H10D Validation

`Strategy: v5_binance_ohlcv_core_h10d`
`Parent: v5_rw_bridge_no_overlay_h10d`
`Status: failed`

## Metrics

| Scenario | Net return | Sharpe | Max DD | Rebalances | Max trade participation |
| --- | ---: | ---: | ---: | ---: | ---: |
| base | 1.231062 | 0.635 | 0.433703 | 183 | 0.000024 |
| stress | 1.211219 | 0.630 | 0.434042 | 183 | 0.000047 |

## Blockers

- none

## Execution Gap Policy

- mode: `drop_selected_path_gap_symbols`
- excluded_symbols: `LTCUSDT, NEARUSDT, ONEUSDT, SANDUSDT, SOLUSDT, XRPUSDT`
- residual_data_gap_blockers: `0`

## Attribution

| Side | Gross contrib | Funding cost | Net before trade cost | Positions | Hit rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| long | 0.986161 | 0.067149 | 0.919012 | 559 | 0.549 |
| short | 0.402460 | 0.096169 | 0.306290 | 580 | 0.571 |

## Ablations

| Ablation | Base net | Base Sharpe | Stress net | Max participation |
| --- | ---: | ---: | ---: | ---: |
| long_only_gross_1x | 1.500969 | 0.598 | 1.488470 | 0.000013 |
| short_disabled_cash_half | 0.964179 | 0.610 | 0.959014 | 0.000006 |
| short_veto_ohlcv_squeeze_guard | 0.768032 | 0.509 | 0.752148 | 0.000024 |

## Artifact Paths

- validation_report: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\validation_report.json`
- dataset_manifest: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\dataset_manifest.json`
- gap_audit: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\gap_audit.json`
- feature_manifest: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\feature_manifest.json`
- aligned_period_returns: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\aligned_period_returns.csv`
- universe_membership: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\universe_membership.csv`
- position_attribution: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\position_attribution.csv`
- attribution_by_side_year: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\attribution_by_side_year.csv`
- attribution_by_symbol_year: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\attribution_by_symbol_year.csv`
- ablation_summary: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\ablation_summary.json`
- ablation_period_returns: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\ablation_period_returns.csv`

## Sidecar Policy

CoinGlass, OI, liquidation, orderbook, top-trader, taker, funding, and basis columns are excluded from core alpha.
