# Binance PIT Pruned3 Drawdown Attribution

Date: 2026-05-11

## Decision

`pruned3` has a higher max drawdown than the full PIT version. The extra drawdown is concentrated in its worst `2023-10-19` to `2023-12-18` peak-to-trough window rather than being a uniform increase in volatility across the whole sample.

## Worst Episodes

| Run | Peak | Trough | Recovery | Max DD | Peak-to-trough return | Periods |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Full PIT | 2024-07-25 | 2024-11-22 | 2025-11-27 | 0.320742 | -0.320742 | 12 |
| Pruned3 | 2023-10-09 | 2023-12-18 | 2024-06-25 | 0.357654 | -0.357654 | 7 |

## Same-Window Comparison

Pruned3 worst peak-to-trough window: `2023-10-19` to `2023-12-18`, `7` h10d periods.

| Window Metric | Full PIT | Pruned3 | Delta |
| --- | ---: | ---: | ---: |
| Compounded return | -0.290793 | -0.357654 | -0.066860 |
| Worst period return | -0.131269 | -0.119275 | 0.011993 |
| Periods where pruned3 worse | 4 | 7 | |

## Extra Loss By Side

| side | full_net_contribution | pruned3_net_contribution | delta_pruned3_minus_full_net_contribution | full_row_count | pruned3_row_count |
| --- | --- | --- | --- | --- | --- |
| long | 0.282314 | 0.213516 | -0.068798 | 24 | 25 |
| short | -0.604839 | -0.632504 | -0.027665 | 26 | 26 |
| flat | -0.001786 | -0.001380 | 0.000407 | 17 | 11 |

## Extra Loss By Year And Side

| year | side | full_net_contribution | pruned3_net_contribution | delta_pruned3_minus_full_net_contribution |
| --- | --- | --- | --- | --- |
| 2023 | long | 0.282314 | 0.213516 | -0.068798 |
| 2023 | short | -0.604839 | -0.632504 | -0.027665 |
| 2023 | flat | -0.001786 | -0.001380 | 0.000407 |

## Extra Loss By Liquidity Bucket

| liquidity_bucket | side | full_net_contribution | pruned3_net_contribution | delta_pruned3_minus_full_net_contribution |
| --- | --- | --- | --- | --- |
| top_liquidity | long | 0.282314 | 0.213516 | -0.068798 |
| mid_liquidity | short | -0.603920 | -0.638877 | -0.034956 |
| not_in_universe | flat | -0.000157 | -0.000126 | 0.000031 |
| mid_liquidity | flat | -0.000502 | -0.000377 | 0.000125 |
| top_liquidity | flat | -0.001127 | -0.000877 | 0.000250 |
| top_liquidity | short | -0.000919 | 0.006373 | 0.007291 |

## Extra Loss By Symbol

| subject | usdm_symbol | side | full_net_contribution | pruned3_net_contribution | delta_pruned3_minus_full_net_contribution |
| --- | --- | --- | --- | --- | --- |
| LINK | LINKUSDT | long | 0.074048 | 0.000000 | -0.074048 |
| AVAX | AVAXUSDT | short | 0.007672 | -0.032120 | -0.039792 |
| TRB | TRBUSDT | short | -0.109156 | -0.124750 | -0.015594 |
| ETC | ETCUSDT | short | 0.013546 | 0.000000 | -0.013546 |
| XRP | XRPUSDT | long | 0.000000 | -0.011586 | -0.011586 |
| FIL | FILUSDT | short | -0.021054 | -0.028099 | -0.007045 |
| BNB | BNBUSDT | long | 0.081890 | 0.077226 | -0.004664 |
| ADA | ADAUSDT | long | 0.016833 | 0.012380 | -0.004453 |
| ATOM | ATOMUSDT | short | -0.020807 | -0.022993 | -0.002186 |
| CRV | CRVUSDT | flat | -0.000157 | -0.000251 | -0.000095 |
| ADA | ADAUSDT | flat | -0.000031 | -0.000125 | -0.000094 |
| DOGE | DOGEUSDT | flat | -0.000219 | -0.000251 | -0.000031 |
| AVAX | AVAXUSDT | flat | -0.000219 | -0.000251 | -0.000031 |
| BTC | BTCUSDT | flat | -0.000125 | -0.000125 | 0.000000 |
| DOT | DOTUSDT | flat | -0.000125 | -0.000125 | 0.000000 |

## Read

The pruned3 drawdown penalty is not an all-period volatility problem. In the worst same-window comparison, the largest deterioration comes from top-liquidity long exposure. Mid-liquidity shorts also worsen, but they are not the main incremental drawdown source in this window.

This points to a risk-layer problem rather than an alpha-pruning failure: pruned3 is still stronger on full-sample and falsification metrics, but it needs a Binance-only ex-ante drawdown/volatility brake before paper readiness.

## Artifacts

- drawdown_periods_full_pit: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\drawdown_periods_full_pit.csv`
- drawdown_periods_pruned3: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\drawdown_periods_pruned3.csv`
- drawdown_episodes: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\drawdown_episodes.csv`
- pruned3_worst_window_period_returns: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\pruned3_worst_window_period_returns.csv`
- pruned3_worst_window_side_attribution: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\pruned3_worst_window_side_attribution.csv`
- pruned3_worst_window_symbol_attribution: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\pruned3_worst_window_symbol_attribution.csv`
- pruned3_worst_window_year_side_attribution: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\pruned3_worst_window_year_side_attribution.csv`
- pruned3_worst_window_liquidity_bucket_attribution: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\pruned3_worst_window_liquidity_bucket_attribution.csv`
- summary: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\drawdown_attribution_20260511Tpruned3_vs_full\drawdown_attribution_summary.json`
- markdown_report: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\docs\quant_research\02_binance_pit_h10d\binance_pit_pruned3_drawdown_attribution_2026_05_11.md`
