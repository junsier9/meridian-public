# Binance-Canonical H10D Liquidity Bucket Attribution

`Strategy: v5_binance_ohlcv_core_h10d`
`Run: 20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d`
`Reference capital: 1000 USD`
`Status: failed`

## Decision

The failure is not concentrated in the lower-liquidity sleeve.

The official liquidity-bucket falsification gate fails because only one bucket has positive net return. The bucket-level report says `top_liquidity` is negative and `mid_liquidity` is positive. However, that test filters the entire scored frame by bucket before running the backtest, which also removes later fill or exit rows when a symbol changes bucket. The bucket test therefore carries many artificial fill/exit gap blockers and should be treated as a fail-closed diagnostic rather than clean attribution.

The cleaner read is entry-bucket attribution from actual selected positions. On that basis, `mid_liquidity` contributes most of the strategy profit, while `top_liquidity` is fragile: top long is positive, but top short is strongly negative after funding.

This means a simple "top-liquidity only" liveable universe would not rescue the core. The current Binance-only core is not ready for paper trading as-is.

## Official Bucket Gate

Source: `validation_report.json -> falsification.liquidity_bucket`

| Bucket | Net return | Sharpe | Gross before costs | Funding cost | Trade count | Max participation | Data gap blockers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| top_liquidity | -0.096340 | 0.064705 | 0.196856 | 0.219040 | 155 | 0.000003 | yes |
| mid_liquidity | 0.025049 | 0.143967 | 0.193968 | 0.071675 | 173 | 0.000011 | yes |
| not_in_universe | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0 | 0.000000 | no |

Gate result: `liquidity_positive_bucket_count = 1`, required minimum `2`.

## Entry-Bucket Attribution

Source: `position_attribution.csv`, grouped by the bucket recorded at decision time for actually selected positions. This excludes portfolio-level fee and slippage, which remain in the validation metrics, but includes funding cost by held leg.

| Entry bucket | Positions | Symbols | Mean rank | Gross contribution | Funding cost | Net before trade cost | Hit rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| top_liquidity | 639 | 34 | 4.47 | 0.324277 | 0.198946 | 0.125331 | 0.560 |
| mid_liquidity | 482 | 53 | 15.87 | 1.048940 | -0.035545 | 1.084485 | 0.562 |
| not_in_universe | 18 | 7 | n/a | 0.015404 | -0.000083 | 0.015486 | 0.500 |

## Entry-Bucket By Side

| Entry bucket | Side | Positions | Symbols | Gross contribution | Funding cost | Net before trade cost | Hit rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| top_liquidity | long | 440 | 9 | 0.624240 | 0.079708 | 0.544532 | 0.548 |
| top_liquidity | short | 199 | 31 | -0.299963 | 0.119238 | -0.419201 | 0.588 |
| mid_liquidity | long | 114 | 13 | 0.344338 | -0.012809 | 0.357148 | 0.553 |
| mid_liquidity | short | 368 | 51 | 0.704602 | -0.022736 | 0.727338 | 0.565 |
| not_in_universe | long | 5 | 1 | 0.017583 | 0.000250 | 0.017333 | 0.600 |
| not_in_universe | short | 13 | 6 | -0.002179 | -0.000333 | -0.001847 | 0.462 |

## Entry-Bucket By Year

| Entry bucket | Year | Positions | Symbols | Net before trade cost | Gross contribution | Funding cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| top_liquidity | 2021 | 69 | 9 | 0.121157 | 0.137351 | 0.016194 |
| top_liquidity | 2022 | 133 | 21 | 0.207237 | 0.206711 | -0.000527 |
| top_liquidity | 2023 | 136 | 19 | 0.197530 | 0.321925 | 0.124396 |
| top_liquidity | 2024 | 144 | 15 | 0.005261 | 0.019338 | 0.014076 |
| top_liquidity | 2025 | 119 | 12 | -0.212852 | -0.201686 | 0.011166 |
| top_liquidity | 2026 | 38 | 6 | -0.193001 | -0.159360 | 0.033641 |
| mid_liquidity | 2021 | 54 | 17 | -0.198087 | -0.236936 | -0.038850 |
| mid_liquidity | 2022 | 100 | 31 | 0.733624 | 0.766964 | 0.033340 |
| mid_liquidity | 2023 | 100 | 28 | -0.278710 | -0.293679 | -0.014969 |
| mid_liquidity | 2024 | 87 | 22 | 0.155531 | 0.105914 | -0.049617 |
| mid_liquidity | 2025 | 110 | 17 | 0.435875 | 0.445321 | 0.009446 |
| mid_liquidity | 2026 | 31 | 10 | 0.236251 | 0.261355 | 0.025104 |

## Interpretation

`mid_liquidity` is not the drag. In actual selected positions it is the main positive contributor, including the short sleeve.

`top_liquidity` is not cleanly robust. It remains slightly positive before portfolio-level fee and slippage in entry-bucket attribution, but the contribution is narrow and depends on the long sleeve offsetting a strongly negative top-liquidity short sleeve. It is also negative in the official isolated bucket backtest, even though that test needs a cleaner entry-bucket implementation.

The most defensible next gate is not "top 10 only." It is a stricter follow-up run that either disables top-liquidity shorts, adds an OHLCV-only squeeze veto to high-liquidity shorts, or tests a long-only / short-disabled liveable variant under the same rolling universe and gap policy. Until that passes, the Binance-only core should remain failed and should not move to paper trading.

## Source Artifacts

- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\validation_report.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\binance_canonical_h10d\20260510TrollingGapClean-1k-v5_binance_ohlcv_core_h10d\position_attribution.csv`
