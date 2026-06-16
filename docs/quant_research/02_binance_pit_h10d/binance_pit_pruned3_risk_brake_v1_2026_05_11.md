# Binance PIT Pruned3 Risk-Brake V1

`v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1` was implemented as a risk overlay on top of the frozen pruned3 alpha. It does not add a new alpha feature and does not admit sidecar data. The overlay only uses Binance OHLCV-derived decision-time state plus closed strategy PnL for the portfolio drawdown brake.

## What Changed

- Kept the pruned3 alpha feature set unchanged:
  - `intraday_realized_vol_4h_to_1d_smooth_60`
  - `realized_volatility_5`
  - `distance_to_high_60`
  - `distance_to_high_5`
  - `downside_upside_vol_ratio_30`
- Added a short-side risk multiplier column:
  - `binance_risk_brake_short_multiplier`
  - min of `binance_short_squeeze_veto_multiplier` and `binance_high_vol_rebound_short_multiplier`
- Added a PIT closed-PnL portfolio drawdown throttle:
  - 120-day window
  - drawdown over 5% scales gross to `0.70`
  - drawdown over 10% scales gross to `0.50`
- Added a hard validation gate:
  - `base_max_drawdown_max = 0.325`

## Full-Gate Result

Run root:

`artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1/`

Validation report:

`artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidPruned3RiskBrakeV1Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1/validation_report.json`

Status: `passed`

| Strategy | Status | Base net | Base Sharpe | Max DD | Stress net | Stress Sharpe | Stratified holdout | Liquidity positive buckets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full PIT | passed | 2.198882 | 0.989767 | 0.320742 | 2.167903 | 0.982648 | 14 / 16 | 2 |
| pruned3 | passed | 2.704409 | 1.055884 | 0.357654 | 2.671102 | 1.049608 | 13 / 16 | 2 |
| pruned3 risk-brake v1 | passed | 1.461132 | 1.012967 | 0.210697 | 1.444297 | 1.006065 | 12 / 16 | 2 |

## Interpretation

Risk-brake v1 fixes the specific pruned3 weakness it was built for: max drawdown falls from `35.77%` to `21.07%`, well below both pruned3 and full PIT. Liquidity buckets also become much healthier:

| Strategy | Mid-liquidity net | Mid-liquidity DD | Top-liquidity net | Top-liquidity DD |
| --- | ---: | ---: | ---: | ---: |
| full PIT | 0.452380 | 0.650605 | 0.422818 | 0.539030 |
| pruned3 | 0.477344 | 0.662054 | 0.545118 | 0.528546 |
| pruned3 risk-brake v1 | 1.054090 | 0.237273 | 1.598360 | 0.208618 |

The cost is real: base net return drops from `2.704409` to `1.461132`. The overlay is therefore not a free lunch. It converts a high-return, high-drawdown challenger into a lower-return, cleaner-tail challenger.

The holdout result is the main caution. Stratified repeated holdout passes at exactly `12 / 16`, which is the configured 75% threshold. The minimum fold is still negative at `-0.390415`. This means the risk brake is liveability-positive, but not yet a robust promotion argument by itself.

## Overlay Trigger Audit

Universe-membership rows:

- `binance_risk_brake_short_multiplier < 1`: `16,584`
- `binance_risk_brake_short_multiplier = 0`: `6,218`
- short-squeeze veto flag rows: `6,218`
- high-vol rebound flag rows: `11,152`
- high-vol rebound severe flag rows: `7,410`

Selected short positions:

- selected short rows: `536`
- selected short rows with multiplier `< 1`: `48`
- selected short rows with multiplier `= 0`: `1`
- selected short rows hit by short-squeeze flag: `1`
- selected short rows hit by high-vol rebound flag: `47`

The overlay is mostly acting through the high-vol rebound short brake on selected positions. The short-squeeze veto is broad in the universe but rarely overlaps actual selected shorts.

## Decision

`v5_binance_pit_top_mid_h10d_pruned3_risk_brake_v1` is a valid passed challenger, but it should not replace pruned3 or enter paper/live as-is. It should enter the next diagnostic slice: isolate the drawdown throttle, high-vol rebound short brake, and short-squeeze veto as separate pre-registered components, then rerun the same gates. The component that preserves most of the drawdown improvement without pushing stratified holdout to the boundary is the only one worth keeping.
