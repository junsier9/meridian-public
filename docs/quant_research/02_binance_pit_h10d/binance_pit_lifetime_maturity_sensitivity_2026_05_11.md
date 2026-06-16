# Binance PIT Lifetime Maturity Sensitivity

`Strategy: v5_binance_pit_top_mid_h10d`  
`Control variable: pit_data_eligibility_policy.min_lifetime_valid_days`  
`Invariant controls: PIT rolling quote-volume universe, same-bucket stability, short rank buffer, corrected decision-time liquidity bucket gate`

## Runs

| Min lifetime days | Run ID | Status | Blockers |
| ---: | --- | --- | ---: |
| 0 | `20260511TpitTopMidDecisionBucketLife0-1k-v5_binance_pit_top_mid_h10d` | failed | 0 |
| 30 | `20260511TpitTopMidDecisionBucketLife30-1k-v5_binance_pit_top_mid_h10d` | failed | 0 |
| 180 | `20260511TpitTopMidDecisionBucket-1k-v5_binance_pit_top_mid_h10d` | failed | 0 |

## Core Metrics

| Min lifetime days | Base net | Base Sharpe | Stress net | Max DD | Long-only net | Short-disabled net |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 2.256414 | 1.004 | 2.224887 | 0.320742 | 0.413314 | 0.419775 |
| 30 | 2.256414 | 1.004 | 2.224887 | 0.320742 | 0.413314 | 0.419775 |
| 180 | 1.581492 | 0.858 | 1.558251 | 0.320742 | -0.330267 | -0.049362 |

## Corrected Liquidity Bucket Gate

All rows below use decision-time bucket filtering while retaining the full fill/exit execution path. Data-gap blockers are zero in every bucket run.

| Min lifetime days | Top bucket net | Top Sharpe | Mid bucket net | Mid Sharpe | Positive buckets | Gate |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 0.419775 | 0.384 | 0.479053 | 0.397 | 2 | pass |
| 30 | 0.419775 | 0.384 | 0.479053 | 0.397 | 2 | pass |
| 180 | -0.049362 | 0.095 | 0.866197 | 0.509 | 1 | fail |

## Holdout Gate

| Min lifetime days | Holdout positive count | Gate |
| ---: | ---: | --- |
| 0 | 1 | fail |
| 30 | 1 | fail |
| 180 | 2 | pass |

## Interpretation

The top-liquidity deterioration is not caused by PIT rolling universe or by the corrected decision-time bucket runner. It is caused by the 180-day lifetime maturity filter.

With `min_lifetime_valid_days=0` or `30`, top-liquidity recovers to positive net return and the corrected liquidity bucket gate passes. With `180`, top-liquidity turns negative and the gate fails.

The 0-day and 30-day runs are identical because the other PIT eligibility requirements already impose enough recent visible history:

- `lookback_days=30`
- `min_coverage_ratio=0.95`
- `min_consecutive_valid_days=10`
- `min_same_bucket_days=10`
- current funding sample required

So a separate 30-day lifetime floor is non-binding under the current policy.

The tradeoff is clear:

- `0/30` preserves top-liquidity long evidence and passes liquidity buckets, but fails symbol holdout.
- `180` passes symbol holdout, but cuts enough early top-liquidity long exposure that top bucket fails.

## Decision

The 180-day maturity rule is too blunt as a liveability fix. It changes alpha evidence, not just data hygiene.

The strategy still remains fail-closed because neither setting passes all gates:

- `0/30`: `holdout_positive_gate=false`
- `180`: `liquidity_positive_bucket_gate=false`

Next work should replace the blunt lifetime gate with a more targeted PIT data-risk rule, or test a pre-registered `mid_short_only` challenger separately.
