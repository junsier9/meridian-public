# Binance PIT Pruned3 Factor Ablation

Date: 2026-05-11

## Decision

`v5_binance_pit_top_mid_h10d_pruned3` passed the same Binance-only PIT validation gates after removing:

- `settlement_cycle_premium_60d`
- `momentum_decay_5_20`
- `liquidity_stress_qv_iv`

This is evidence that the three-factor prune is a structural improvement over the current PIT top/mid challenger, not just a cosmetic attribution artifact. The improvement is not free: net return and Sharpe improve, but max drawdown is worse.

## Runs

| Run | Strategy | Status | Notes |
| --- | --- | --- | --- |
| `20260511TpitTopMidFullSideYearLooBackfilled-1k-v5_binance_pit_top_mid_h10d` | `v5_binance_pit_top_mid_h10d` | `passed` | Full 8-factor baseline, rerun to emit by-side/by-year LOO. |
| `20260511TpitTopMidPruned3Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3` | `v5_binance_pit_top_mid_h10d_pruned3` | `passed` | Same PIT universe/cost/holdout/bucket/shuffle gates, 5 remaining factors. |

## Gate Comparison

| Metric | Full PIT | Pruned3 | Delta |
| --- | ---: | ---: | ---: |
| Base net return | 2.198882 | 2.704409 | +0.505527 |
| Base Sharpe | 0.989767 | 1.055884 | +0.066117 |
| Base max DD | 0.320742 | 0.357654 | -0.036912 |
| Stress net return | 2.167903 | 2.671102 | +0.503199 |
| Stress Sharpe | 0.982648 | 1.049608 | +0.066960 |
| Max trade participation | 0.00002009 | 0.00001507 | better |
| Stratified holdout positive folds | 14/16 | 13/16 | still passes |
| Liquidity positive buckets | 2 | 2 | unchanged pass |
| Rank IC mean | 0.151502 | 0.152551 | +0.001050 |
| Funding cost coverage | 0.999917 | 0.999917 | unchanged |

Pruned3 also improves falsification posture on time shuffle: the shuffled run drops to net `-0.038470`, while the full PIT time shuffle still leaves net `+0.171857`. Label-shuffle rank IC remains near noise for pruned3 at `0.009265`.

## Pruned3 Side Attribution

Position attribution is gross plus funding-cost-only by held leg, so it should be read as direction/selection diagnosis rather than exact net account PnL.

| Side | Full PIT net before trade cost | Pruned3 net before trade cost | Delta |
| --- | ---: | ---: | ---: |
| Long | 0.578153 | 0.677631 | +0.099478 |
| Short | 0.873062 | 0.934074 | +0.061012 |

The group prune improves both legs. The earlier suspicion that the damage was mainly short-side is only partially true: `liquidity_stress_qv_iv` is mostly a short-side drag, but `momentum_decay_5_20` and `settlement_cycle_premium_60d` hurt the long leg more.

## Full-Baseline LOO By Side

Negative delta means removing the feature improved that side.

| Feature | Long delta | Short delta | Read |
| --- | ---: | ---: | --- |
| `settlement_cycle_premium_60d` | -0.102245 | -0.039159 | Mainly long-leg drag, with additional short drag. |
| `momentum_decay_5_20` | -0.139738 | +0.027463 | Long-leg drag; short side slightly benefited from keeping it. |
| `liquidity_stress_qv_iv` | -0.016394 | -0.082143 | Mainly short-leg drag. |

## Full-Baseline LOO By Year

Negative delta means removing the feature improved that year.

| Feature | Main drag years | Helped years |
| --- | --- | --- |
| `settlement_cycle_premium_60d` | 2025 `-0.083496`, 2024 `-0.060133`, 2021 `-0.037115` | 2022 `+0.041080`, 2023 `+0.001979` |
| `momentum_decay_5_20` | 2025 `-0.070158`, 2024 `-0.057277`, 2021 `-0.033100` | 2022 `+0.044618`, 2023 `+0.002168` |
| `liquidity_stress_qv_iv` | 2023 `-0.093774`, 2022 `-0.036184`, 2025 `-0.015878` | 2024 `+0.034275`, 2026 `+0.011134`, 2021 `+0.001889` |

## Diagnosis

`settlement_cycle_premium_60d` is not a clean funding/carry feature. It is a Binance kline-return proxy for settlement-window drift. In this PIT universe it mostly suppresses profitable long exposure in 2024 and profitable short exposure in 2025. That makes it a stale seasonal proxy rather than a robust alpha component.

`momentum_decay_5_20` is the clearest long-leg conflict. Its negative weight penalizes short-term acceleration relative to 20-day momentum. The LOO split says this mostly blocks good longs rather than preventing bad shorts. It fights the strategy's stronger trend/proximity-to-high sleeve.

`liquidity_stress_qv_iv` is the one that matches the short-side suspicion. The factor treats volume expansion plus intraday volatility as stress, but in perp markets that often marks informed trend participation. Its largest drag appears in short selection, especially 2022-2023, where it likely pushes the book into names that should not be shorted.

## Artifact Pointers

- Full baseline validation: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFullSideYearLooBackfilled-1k-v5_binance_pit_top_mid_h10d/validation_report.json`
- Full baseline by-side LOO: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFullSideYearLooBackfilled-1k-v5_binance_pit_top_mid_h10d/factor_leave_one_out_by_side.csv`
- Full baseline by-year LOO: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFullSideYearLooBackfilled-1k-v5_binance_pit_top_mid_h10d/factor_leave_one_out_by_year.csv`
- Full baseline by-side-year LOO: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidFullSideYearLooBackfilled-1k-v5_binance_pit_top_mid_h10d/factor_leave_one_out_by_side_year.csv`
- Pruned3 validation: `artifacts/quant_research/binance_canonical_h10d/20260511TpitTopMidPruned3Backfilled-1k-v5_binance_pit_top_mid_h10d_pruned3/validation_report.json`
- Pruned3 config: `config/quant_research/binance_pit_top_mid_h10d_pruned3.json`

## Next Gate

Treat `v5_binance_pit_top_mid_h10d_pruned3` as the stronger Binance-only challenger, but not yet as a live strategy. The next gate should be a drawdown-focused check: pruned3 improved return quality and falsification posture, but max DD increased from `0.320742` to `0.357654`.
