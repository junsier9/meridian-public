# H10D Strategy Model And Factor Contributions

`Snapshot date: 2026-05-09`
`Strategy: v5_rw_bridge_no_overlay_h10d`
`Status: research benchmark / shadow-only / archived-only`

This note writes down the current h10d canonical-parent strategy model, factor
composition, latest measured factor contribution, and paper backtest results.
It is not a live-trading authorization. The strategy remains subject to the
repo's promotion guard and Stage-1 research-readiness boundary.

---

## 1. Strategy Model

Canonical strategy id:

`xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d`

Artifact source:

- Manifest:
  `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json`
- Latest matching alpha card used for this note:
  `artifacts/quant_research/experiments/2026-05-02-xs_alpha_ontology_v5_rw_bridg-54814da2622b/alpha_card.json`

Model structure:

| field | value |
| --- | --- |
| Shape | cross-sectional long/short |
| Venue assumption | perp |
| Universe | `liquid_perp_core_20` |
| Eligible OOS subjects | 17 in fixed-set summary |
| Holding horizon | `h10d`, 10 daily bars |
| Construction | top 3 long, bottom 3 short |
| Gross leverage | 1.0 |
| Long leverage | 0.5, split across top 3 |
| Short leverage | 0.5, split across bottom 3 |
| Portfolio overlay | none |
| Score transform | `tanh((percentile_rank(raw_score) - 0.5) * 1.80)` |

For each train split/window, the model:

1. Cross-sectionally z-scores each required factor at each timestamp.
2. Computes daily cross-sectional Spearman IC against
   `target_execution_forward_return`.
3. Converts each factor to IR: `mean(IC) / std(IC)`.
4. Assigns the factor sign from `mean(IC)`.
5. Normalizes signed absolute IR weights so `sum(abs(weight)) = 1.0`.
6. Applies the learned train-only weights to validation/test rows.
7. Ranks names by the transformed score and trades top/bottom 3.

Formula:

```text
z_f(i,t) = cross_sectional_zscore(feature_f(i,t))
IR_f = mean(IC_f_train) / std(IC_f_train)
w_f = signed_abs_IR_f / sum_f(abs(signed_abs_IR_f))

raw_score(i,t) = sum_f(w_f * z_f(i,t))
score(i,t) = tanh((percentile_rank_t(raw_score(i,t)) - 0.5) * 1.80)

target_weight(i,t) =
  +0.5 / 3 for the top 3 names
  -0.5 / 3 for the bottom 3 names
   0 otherwise
```

---

## 2. Economic Interpretation

The strategy is a liquid-perp relative-value selector, not a directional market
timing system. It tries to own the stronger liquid names and short the weaker
liquid names over a 10-day horizon.

The economic thesis has five components:

| component | interpretation |
| --- | --- |
| Volatility fragility | High realized or intraday volatility tends to mark unstable names that should receive lower rank. |
| Structural proximity | Names holding near short/medium-term highs are treated as stronger, unless other fragility terms dominate. |
| Crowding and participant behavior | Excess top-trader long positioning and unstable taker imbalance are treated as crowding or weak-quality flow. |
| Liquidity and carry stress | Funding, OI, basis, quote-volume expansion, and volatility interactions proxy crowded perp pressure and execution stress. |
| Settlement-cycle behavior | Pre-settlement-hour drift captures a recurring microstructure premium/penalty around funding settlement rhythm. |

The model's strongest current learned contributions are from top-trader
crowding, distance to 60-day high, momentum decay, and volatility fragility.

---

## 3. Factor Contribution And Composition

Contribution below means latest alpha-card model contribution to the score,
measured as the learned signed-IR weight from
`2026-05-02-xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d`.
It is not a realized PnL attribution.

| rank | factor | learned weight | abs contribution | mean IC | IR | observations | construction | economic read |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `coinglass_top_trader_long_pct_smooth_5` | -0.2257 | 22.57% | -0.0822 | -0.2969 | 651 | 5-bar rolling mean of `coinglass_top_trader_long_pct`. | Fade crowded top-trader long positioning; high top-trader long percent ranks worse. |
| 2 | `distance_to_high_60` | +0.1765 | 17.65% | +0.0755 | +0.2322 | 619 | `spot_close / rolling_60d_high(spot_high) - 1`. | Names closer to 60-day highs rank better, capturing persistent relative strength. |
| 3 | `momentum_decay_5_20` | -0.1528 | 15.28% | -0.0605 | -0.2010 | 655 | `momentum_5 - momentum_20`. | Penalize short-term acceleration versus medium trend when it behaves like exhaustion/decay. |
| 4 | `intraday_realized_vol_4h_to_1d_smooth_60` | -0.0996 | 9.96% | -0.0502 | -0.1311 | 619 | 60-bar rolling mean of `intraday_realized_vol_4h_to_1d`. | Penalize persistent intraday volatility fragility. |
| 5 | `realized_volatility_5` | -0.0873 | 8.73% | -0.0361 | -0.1148 | 655 | 5-bar rolling standard deviation of daily returns. | Penalize short-term realized-volatility stress. |
| 6 | `distance_to_high_5` | +0.0633 | 6.33% | +0.0267 | +0.0833 | 655 | `spot_close / rolling_5d_high(spot_high) - 1`. | Reward near-term strength that has not fully broken down. |
| 7 | `downside_upside_vol_ratio_30` | +0.0626 | 6.26% | +0.0224 | +0.0823 | 655 | 30-bar downside-return std divided by 30-bar upside-return std, each with minimum side observations. | Measures asymmetric volatility state; current learned sign treats higher ratio as positive in this horizon/parent. |
| 8 | `quality_funding_oi` | +0.0440 | 4.40% | +0.0152 | +0.0579 | 650 | `funding_rate * oi_change_5`. | Joint funding/OI pressure quality term; distinguishes carry with positioning expansion/contraction. |
| 9 | `coinglass_taker_imb_intraday_dispersion_24h` | -0.0394 | 3.94% | -0.0152 | -0.0519 | 276 | CoinGlass 1h taker-imbalance dispersion aggregated over 24h. | Penalize unstable intraday taker-flow dispersion. Sparse coverage makes this a smaller, noisier term. |
| 10 | `settlement_cycle_premium_60d` | +0.0248 | 2.48% | +0.0090 | +0.0326 | 262 | Per-subject 60-day rolling pre-settlement-hour drift from 1h perp returns, merged from the settlement-cycle panel. | Captures recurring funding-settlement rhythm. Current h10d learned sign is positive in this card. |
| 11 | `liquidity_stress_qv_iv` | -0.0124 | 1.24% | -0.0048 | -0.0164 | 655 | `quote_volume_expansion * intraday_realized_vol_4h_to_1d`. | Penalize volume expansion when it coincides with intraday volatility stress. |
| 12 | `funding_basis_residual_implied_repo_30` | -0.0114 | 1.14% | -0.0041 | -0.0150 | 626 | `(rolling_30_mean(funding_rate) - rolling_30_mean(basis_proxy)) / atr_proxy_20`. | Carry residual term comparing funding-implied repo with basis; latest rolling-weight card gives it only a small negative contribution. |

Important sign note: older static alpha-ontology variants used hand-picked
weights for some of these factors. This h10d bridge intentionally re-estimates
weights inside each train split/window, so the table above is the measured
latest learned contribution, not the old static formula.

---

## 4. Paper Backtest Results

Latest matching alpha card:
`2026-05-02-xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d`

| split / view | net return | Sharpe | max drawdown | trades / periods | notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Validation | +35.52% | 2.690 | 9.58% | 18 trades | validation contract passed |
| Test | +37.12% | 2.278 | 9.57% | 20 trades | paper test slice |
| Full OOS fixed-set | +176.59% cumulative | 2.199 period Sharpe | 17.46% | 64 periods | `2023-09-02` to `2026-03-30` |
| Walk-forward | n/a | 3.360 median OOS Sharpe | n/a | 32 windows | all windows contract-passed in the card |

Capacity / execution-stress summary:

| metric | value |
| --- | ---: |
| Full OOS turnover total | 52.6667 |
| Full OOS loss-period fraction | 31.25% |
| Full OOS max trade participation rate | 0.1945% |
| Strict participation cap reference | 0.5% |

Fixed-set context:

| comparison | observed cumulative return diff | sign-test p-value | interpretation |
| --- | ---: | ---: | --- |
| vs `lsk3_g_v2_h10d` control | +1.0822 | 0.0328 | positive against control baseline |
| vs `v5_h10d` static baseline | +0.8175 | 0.0599 | positive but marginal by sign test |
| vs `v6_h10d` legacy comparator | +1.0863 | 0.0328 | positive against legacy comparator |
| vs `v5_rw_bridge_h10d` with `regime_gating_v2` | +0.7799 | 0.0169 | no-overlay version beats the gated comparator on cumulative return |

---

## 5. Fail-Closed Boundary

This strategy is the current h10d canonical parent for research comparison, but
the repo should not treat it as live-ready. Current status remains:

- `credible_research_evidence = true`
- `publication_status = archived_only`
- `promotion_state = shadow_only`
- `daily_executable = false`

The strategy is useful as the parent benchmark for new h10d candidates and for
shadow/paper evaluation. It is not a Binance execution payload and should not be
routed to live trading without a separate passed promotion guard, execution
approval, paper/live feasibility gate, and repo-stage unlock.
