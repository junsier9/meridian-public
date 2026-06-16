# Binance PIT Pruned3 Risk-Brake Component Ablation

This report splits `v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1` into three one-component overlays:

- `portfolio_drawdown_brake`: closed-PnL portfolio throttle only.
- `high_vol_rebound_short_brake`: Binance OHLCV high-vol rebound short multiplier only.
- `short_squeeze_veto`: Binance OHLCV short-squeeze veto only.

The alpha, PIT rolling universe, costs, funding-cost input, holdout policy, liquidity bucket gate, shuffle gates, and `base_max_drawdown_max = 0.325` are kept fixed.

## Artifact Roots

| Variant | Artifact root |
| --- | --- |
| pruned3 baseline | `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidPruned3Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3/` |
| combined risk-brake v1 | `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1/` |
| portfolio drawdown brake | `artifacts/quant_research/binance_canonical_h10d/20260512TpitTopMidPruned3PortfolioDrawdownBrakeBackfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_portfolio_drawdown_brake/` |
| high-vol rebound short brake | `artifacts/qr/hv/` |
| short-squeeze veto | `artifacts/quant_research/binance_canonical_h10d/20260512TpitTopMidPruned3ShortSqueezeVetoBackfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_short_squeeze_veto/` |

The high-vol component was first run under the default deep artifact root and produced a valid `validation_report.json`, but Windows path length blocked later `factor_leave_one_out_*` outputs. The complete rerun is under the shorter `artifacts/qr/hv/` root.

For portfolio-drawdown variants, the decision in this report uses `validation_report.json` base/stress/falsification metrics. The position-level paper ledger is not used to attribute the drawdown throttle because that throttle is stateful across closed periods, while the current ledger attribution path is position-row based.

## Gate Results

| Variant | Status | Base net | Sharpe | Max DD | Stress net | Stress Sharpe | Stratified holdout | DD cap | Liquidity buckets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pruned3 baseline | passed | 2.704409 | 1.055884 | 0.357654 | 2.671102 | 1.049608 | 13 / 16 | n/a | 2 |
| portfolio drawdown brake | failed | 2.249333 | 1.172440 | 0.242156 | 2.226960 | 1.166343 | 11 / 16 | pass | 2 |
| high-vol rebound short brake | passed | 3.509528 | 1.295984 | 0.285178 | 3.469171 | 1.289035 | 13 / 16 | pass | 2 |
| short-squeeze veto | failed | 2.205194 | 0.987196 | 0.354911 | 2.176094 | 0.980542 | 12 / 16 | fail | 2 |
| combined risk-brake v1 | passed | 1.461132 | 1.012967 | 0.210697 | 1.444297 | 1.006065 | 12 / 16 | pass | 2 |

## Component Read

High-vol rebound short brake is the only one-component overlay that passes the full gates. It improves both return and max drawdown versus pruned3:

- net return: `2.704409 -> 3.509528`
- max drawdown: `0.357654 -> 0.285178`
- stratified holdout remains `13 / 16`
- minimum stratified fold improves from `-0.360083` to `-0.280978`

This means high-vol rebound is not the reason combined v1 lost return or only passed holdout at the boundary. The prior suspicion was directionally wrong after isolation.

Portfolio drawdown brake is useful for tail control but not robust enough alone:

- max drawdown improves to `0.242156`
- stress net stays strong at `2.226960`
- but stratified holdout falls to `11 / 16`, below the hard 75% gate

It is probably responsible for most of the combined v1 tail compression, but also for making the result less stable across subject holdouts.

Short-squeeze veto is not worth keeping in this form:

- selected short positions hit by the veto: only `2`
- max drawdown stays bad at `0.354911`, failing the `0.325` cap
- base net and Sharpe both fall versus pruned3
- minimum stratified fold worsens to `-0.491512`

## Trigger Audit

| Variant | Universe rows multiplier < 1 | Universe rows zeroed | Selected short rows hit | Selected short hit net contribution |
| --- | ---: | ---: | ---: | ---: |
| high-vol rebound | 11,152 | 0 | 51 | -0.033115 |
| short-squeeze veto | 6,218 | 6,218 | 2 | -0.012123 |
| combined v1 | 16,584 | 6,218 | 48 | -0.067650 |

High-vol rebound acts on the actual selected short book. Short-squeeze mostly fires in the universe but rarely overlaps selected shorts, so it creates broad-looking activity without meaningful portfolio protection.

## Liquidity Bucket Tail

| Variant | Mid-liquidity net | Mid-liquidity DD | Top-liquidity net | Top-liquidity DD |
| --- | ---: | ---: | ---: | ---: |
| pruned3 baseline | 0.477344 | 0.662054 | 0.545118 | 0.528546 |
| portfolio drawdown brake | 1.554727 | 0.248635 | 1.598360 | 0.208618 |
| high-vol rebound short brake | 0.768592 | 0.567569 | 0.545118 | 0.528546 |
| short-squeeze veto | 0.310270 | 0.624650 | 0.545118 | 0.528546 |
| combined risk-brake v1 | 1.054090 | 0.237273 | 1.598360 | 0.208618 |

The liquidity-bucket tail improvement mostly comes from the portfolio drawdown brake, not the high-vol short brake. The high-vol component improves the aggregate portfolio but does not solve bucket-level tail risk by itself.

## Decision

Keep `high_vol_rebound_short_brake` as the only surviving component from this split. Drop the current `short_squeeze_veto`. Do not promote `portfolio_drawdown_brake` as-is; it should be reworked as a gentler or bucket-aware risk budget rule because it fixes drawdown but fails stratified holdout.

The next clean candidate should be:

`v5_binance_pit_top_mid_h10d_pruned3_hv_rebound_short_brake`

Then test one new risk-budget variant on top of that candidate, with the short-squeeze veto removed.
