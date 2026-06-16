# Binance PIT Top/Mid Liquidity Bucket Breakdown

`Run: 20260511TpitTopMidDecisionBucket-1k-v5_binance_pit_top_mid_h10d`  
`Strategy: v5_binance_pit_top_mid_h10d`  
`Status: failed`  
`Reason: liquidity_positive_bucket_gate=false`

## Gate Result

The failed bucket is `top_liquidity`, not `mid_liquidity`.

| Bucket | Standalone net | Sharpe | Max DD | Trades | Turnover | Funding cost | Data-gap rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `mid_liquidity` | 0.866197 | 0.509 | 0.650605 | 157 | 80.667 | -0.033652 | 0 |
| `top_liquidity` | -0.049362 | 0.095 | 0.540016 | 107 | 39.000 | 0.075861 | 0 |
| `not_in_universe` | 0.000000 | 0.000 | 0.000000 | 0 | 0.000 | 0.000000 | 0 |

The validation requires at least two positive liquidity buckets. Only `mid_liquidity` is positive, so the gate fails.

## Runner Fix

The liquidity bucket falsification now filters bucket membership at decision time only. Fill, exit, and funding rows remain available from the full execution frame, so symbol bucket migration during the holding path no longer creates artificial missing fill/exit blockers.

The corrected run confirms `data_gap_blockers=[]` for `mid_liquidity`, `top_liquidity`, and `not_in_universe`.

## Actual Position Attribution

| Bucket | Side | Positions | Gross contribution | Funding cost | Net before trade cost | Hit rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `top_liquidity` | long | 505 | 0.225264 | 0.076066 | 0.149197 | 0.519 |
| `top_liquidity` | short | 3 | -0.000569 | 0.000104 | -0.000672 | 0.333 |
| `mid_liquidity` | short | 517 | 1.029987 | -0.031570 | 1.061557 | 0.561 |
| `not_in_universe` | short | 1 | 0.003176 | -0.000147 | 0.003322 | 1.000 |

The liveable challenger's realized edge is dominated by `mid_liquidity` shorts. The `top_liquidity` sleeve is mostly the long sleeve, and it is weak enough that the standalone top-bucket falsification turns negative after costs and funding.

## Bucket By Year

| Bucket | Year | Net before trade cost | Gross | Funding cost | Positions | Hit rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `mid_liquidity` | 2021 | 0.109528 | 0.095518 | -0.014010 | 23 | 0.609 |
| `mid_liquidity` | 2022 | 0.967982 | 1.041210 | 0.073228 | 114 | 0.667 |
| `mid_liquidity` | 2023 | -0.434332 | -0.462319 | -0.027987 | 124 | 0.500 |
| `mid_liquidity` | 2024 | -0.213442 | -0.278170 | -0.064729 | 108 | 0.519 |
| `mid_liquidity` | 2025 | 0.419233 | 0.414899 | -0.004334 | 115 | 0.539 |
| `mid_liquidity` | 2026 | 0.212589 | 0.218850 | 0.006261 | 33 | 0.606 |
| `top_liquidity` | 2021 | -0.175773 | -0.164940 | 0.010833 | 22 | 0.364 |
| `top_liquidity` | 2022 | -0.470212 | -0.478089 | -0.007877 | 110 | 0.436 |
| `top_liquidity` | 2023 | 0.421213 | 0.443075 | 0.021862 | 120 | 0.575 |
| `top_liquidity` | 2024 | 0.394951 | 0.434218 | 0.039267 | 108 | 0.546 |
| `top_liquidity` | 2025 | 0.065592 | 0.077690 | 0.012098 | 115 | 0.539 |
| `top_liquidity` | 2026 | -0.087247 | -0.087259 | -0.000012 | 33 | 0.515 |

The top-liquidity sleeve is not uniformly dead, but it is regime-fragile. It loses hard in 2021, 2022, and 2026, and only works in 2023-2025.

The mid-liquidity short sleeve also has bad years, especially 2023 and 2024, but its 2022, 2025, and early-2026 contribution dominates the aggregate.

## Worst Concentrations

### Top Liquidity

| Year | Symbol | Side | Positions | Net before trade cost | Hit rate |
| ---: | --- | --- | ---: | ---: | ---: |
| 2022 | ETH | long | 21 | -0.142286 | 0.333 |
| 2022 | BTC | long | 34 | -0.131895 | 0.500 |
| 2022 | ADA | long | 10 | -0.129669 | 0.100 |
| 2021 | BTC | long | 7 | -0.067221 | 0.429 |
| 2021 | ETH | long | 7 | -0.051194 | 0.429 |
| 2021 | XRP | long | 3 | -0.049883 | 0.000 |
| 2026 | BNB | long | 11 | -0.049803 | 0.545 |
| 2023 | LTC | long | 3 | -0.049419 | 0.333 |

### Mid Liquidity

| Symbol | Side | Positions | Net before trade cost | Hit rate |
| --- | --- | ---: | ---: | ---: |
| NEAR | short | 59 | -0.195419 | 0.492 |
| ADA | short | 5 | -0.134637 | 0.400 |
| RUNE | short | 15 | -0.127854 | 0.467 |
| AAVE | short | 35 | -0.124665 | 0.457 |
| RLC | short | 2 | -0.070944 | 0.000 |
| OGN | short | 2 | -0.036582 | 0.000 |
| BCH | short | 10 | -0.030996 | 0.500 |
| AVAX | short | 19 | -0.024374 | 0.474 |

## Interpretation

This is not a simple "low-liquidity bucket drags the strategy" failure. The main failed bucket is the high-liquidity/top bucket, which mostly corresponds to the long sleeve.

That agrees with the earlier ablations:

- `long_only_gross_1x`: base net `-0.330267`
- `short_disabled_cash_half`: base net `-0.049362`
- full PIT top/mid core: base net `1.581492`

So the current Binance-only core is not a balanced long/short alpha. It is effectively a mid-liquidity short strategy with a weak or regime-dependent top-liquidity long sleeve. Because the high-liquidity bucket does not stand on its own, the strategy should remain fail-closed for paper/live promotion.

## Next Allowed Work

1. Do not promote `v5_binance_pit_top_mid_h10d` to paper/live; it still fails the corrected liquidity bucket gate.
2. Test a pre-registered `mid_short_only` challenger if the research question is whether the Binance-only short sleeve is independently liveable.
3. Keep the current top-liquidity long sleeve out of promotion unless a separate, pre-registered long-side replacement passes the same corrected bucket gate.
