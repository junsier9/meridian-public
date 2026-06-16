# Binance PIT HV Rebound + Soft Portfolio Budget

This slice keeps the surviving component from the risk-brake split:

`v5_binance_pit_top_mid_h10d_pruned3_high_vol_rebound_short_brake`

Then it tests a softer portfolio risk budget. The old hard portfolio drawdown brake started at 5% / 10% drawdown and failed stratified holdout. The new design uses closed-PnL rolling drawdown only, but scales gross linearly and much later.

## Implementation

Execution layer:

- Added `dd_throttle_mode = soft_linear`.
- The throttle is PIT-safe: it only sees closed prior period equity.
- It writes `portfolio_throttle_multiplier` and `portfolio_throttle_drawdown` into period returns for audit.

Pre-registered variants:

| Variant | Start DD | Full DD | Gross floor | Window |
| --- | ---: | ---: | ---: | ---: |
| `hv_tail` | 15% | 30% | 85% | 180d |
| `hv_mild` | 12% | 28% | 85% | 180d |
| `hv_balanced` | 10% | 25% | 80% | 180d |

All variants keep alpha, PIT universe, high-vol short brake, costs, funding, bucket gate, shuffle tests, and stratified holdout fixed.

## Artifact Roots

| Variant | Artifact root |
| --- | --- |
| high-vol base | `artifacts/qr/hv/` |
| tail-only soft budget | `artifacts/qr/hv_tail/` |
| mild soft budget | `artifacts/qr/hv_mild/` |
| balanced soft budget | `artifacts/qr/hv_balanced/` |

## Gate Results

| Variant | Status | Base net | Sharpe | Max DD | Stress net | Stress Sharpe | Stratified holdout | Min fold | Median fold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| high-vol base | passed | 3.509528 | 1.295984 | 0.285178 | 3.469171 | 1.289035 | 13 / 16 | -0.280978 | 0.549423 |
| hv_tail | passed | 3.400482 | 1.285004 | 0.283569 | 3.360634 | 1.277986 | 13 / 16 | -0.288272 | 0.548533 |
| hv_mild | passed | 3.361901 | 1.282160 | 0.282072 | 3.322109 | 1.275080 | 13 / 16 | -0.277899 | 0.552644 |
| hv_balanced | passed | 3.241191 | 1.270222 | 0.279320 | 3.202118 | 1.263026 | 13 / 16 | -0.264864 | 0.553959 |
| combined v1 reference | passed | 1.461132 | 1.012967 | 0.210697 | 1.444297 | 1.006065 | 12 / 16 | -0.390415 | 0.380289 |

## Budget Trigger Audit

| Variant | Throttled periods | Min multiplier | Avg multiplier | Max observed throttle DD |
| --- | ---: | ---: | ---: | ---: |
| hv_tail | 25 | 0.866431 | 0.992885 | 0.283569 |
| hv_mild | 41 | 0.850000 | 0.988035 | 0.282072 |
| hv_balanced | 48 | 0.800000 | 0.977376 | 0.279320 |

The soft budget behaves as intended: it is much less invasive than combined v1's hard risk brake and does not reduce the stratified holdout pass count.

## Liquidity Bucket Effect

| Variant | Mid-liquidity net | Mid-liquidity DD | Top-liquidity net | Top-liquidity DD |
| --- | ---: | ---: | ---: | ---: |
| high-vol base | 0.768592 | 0.567569 | 0.545118 | 0.528546 |
| hv_tail | 0.713955 | 0.550857 | 0.598324 | 0.507158 |
| hv_mild | 0.728081 | 0.546329 | 0.612825 | 0.502848 |
| hv_balanced | 0.737569 | 0.531753 | 0.650047 | 0.487604 |

The redesigned budget improves both top- and mid-liquidity bucket drawdowns. The improvement is still modest compared with combined v1, but it does not pay the combined v1 penalty in return and holdout stability.

## Interpretation

The high-vol rebound short brake remains the real structural improvement. Soft portfolio budgeting is a second-order risk smoother, not a new alpha:

- It preserves `13 / 16` stratified holdout across all three variants.
- It improves max drawdown gradually from `0.285178` to `0.279320`.
- It gives up some return as the budget becomes stronger.
- It avoids the hard-brake failure mode where holdout fell to `11 / 16`.

Among the three, `hv_balanced` is the cleanest redesigned budget if the goal is better liveability without sacrificing the validated high-vol short brake. It has the best DD, best min fold, best median fold, and still keeps net return above `3.20`.

## Decision

Promote the research candidate to:

`v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget`

Do not revive the old hard portfolio drawdown brake or short-squeeze veto. The next validation slice should compare:

- high-vol base
- `hv_balanced`
- combined v1 reference

with by-side/year attribution and paper/shadow ledger deltas focused on the throttled periods.
