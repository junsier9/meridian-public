# v5_rw_bridge_no_overlay_h10d vs hv_balanced Trade Diff

## Scope

- Generated at: 2026-05-18
- v5 source: `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/experiments/2026-04-29-xs_alpha_ontology_v5_rw_bridg-6054571c70ef/fixed_set_aligned_period_returns.csv`
- hv source: `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/qr/hv_balanced/aligned_period_returns.csv`
- Comparison mode: nearest 10d-cycle match, `64` v5 fill timestamps from `2023-09-02T00:00:00Z` to `2026-03-30T00:00:00Z`; max match lag `3.0` days.
- v5 position reconstruction max absolute return parity error vs fixed-set file: `9.71445146547e-17`.

2026-06-03 baseline supersession:

- This comparison used nearest matched single-phase 10d cycles.
- It is historical trade-difference evidence, not the current live/research baseline definition.
- The current live baseline is `v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget:multiphase_10_sleeve`.
- The current follow-on research baseline is `v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`.

## Paired Metrics

| strategy | periods | start_utc | end_utc | net_return | sharpe | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- |
| v5_rw_bridge_no_overlay_h10d | 64 | 2023-09-02T00:00:00Z | 2026-03-30T00:00:00Z | 1.765913 | 2.199218 | 0.174568 |
| hv_balanced_nearest_cycle | 64 | 2023-09-02T00:00:00Z | 2026-03-30T00:00:00Z | 0.757028 | 1.386992 | 0.169732 |

## Full Native Windows

- v5 native fixed-set full OOS: net `1.765913`, Sharpe `2.199`, Max DD `0.174568`, periods `64`.
- hv native frozen full sample: net `3.241191`, Sharpe `1.270`, Max DD `0.279320`, periods `183`.

## Component Sums On Matched Cycles

| component | v5_sum | hv_sum | diff_v5_minus_hv |
| --- | --- | --- | --- |
| gross_return_before_costs | 0.137365 | 0.661780 | -0.524415 |
| fee_cost_return | 0.031600 | 0.024602 | 0.006998 |
| slippage_cost_return | 0.009040 | 0.006250 | 0.002789 |
| funding_cost_return | -0.998982 | 0.008469 | -1.007452 |
| turnover | 52.666667 | 41.002755 | 11.663912 |

## Position Difference Summary

- Period wins/losses for v5 vs hv: `39` / `25`.
- Mean subject-set Jaccard overlap: `0.270`; exact same subject set periods: `0` / `64`.
- Periods with at least one opposite-direction same-symbol leg: `6` / `64`.
- All leg-level differences are in `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/position_diffs.csv`.
- Largest contribution differences are in `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/top_leg_diffs.csv`.

## Top v5 Outperformance Periods

| pair_date_utc | v5_fill_date_utc | hv_fill_date_utc | match_lag_days | v5_return | hv_return | return_diff_v5_minus_hv | top_leg_diffs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-04-24 | 2025-04-24 | 2025-04-21 | 3.0 | 0.075248 | -0.044406 | 0.119653 | AAVE: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0348; UNI: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0339; CRV: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0334; LTC: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=-0.0226; HBAR: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0162; DOGE: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0157; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=0.0075; ETH: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0013 |
| 2024-03-30 | 2024-03-30 | 2024-03-27 | 3.0 | 0.077045 | -0.040493 | 0.117539 | DOGE: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0457; BCH: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0456; NEAR: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0323; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=-0.0296; ETH: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=0.0085; ETC: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0072 |
| 2024-03-10 | 2024-03-10 | 2024-03-07 | 3.0 | 0.074954 | -0.035957 | 0.110911 | LINK: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0966; UNI: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0962; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=-0.0396; BNB: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=-0.0333; BCH: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0116; LTC: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0064 |
| 2025-02-23 | 2025-02-23 | 2025-02-20 | 3.0 | 0.037861 | -0.071803 | 0.109664 | HBAR: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0315; RUNE: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0209; SOL: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0182; NEAR: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0141; ETH: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=0.0135; ETC: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0129; CRV: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0093; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=-0.0003 |
| 2025-06-03 | 2025-06-03 | 2025-05-31 | 3.0 | 0.018574 | -0.083785 | 0.102359 | CRV: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0179; DOGE: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0171; XRP: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=-0.0100; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=-0.0030 |

## Top hv Outperformance Periods

| pair_date_utc | v5_fill_date_utc | hv_fill_date_utc | match_lag_days | v5_return | hv_return | return_diff_v5_minus_hv | top_leg_diffs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-11-30 | 2025-11-30 | 2025-11-27 | 3.0 | -0.051222 | 0.114277 | -0.165499 | ZEN: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0491; DASH: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0389; DOT: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=-0.0278; ICP: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0254; AVAX: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=-0.0240; LINK: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=-0.0037; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=-0.0032; NEAR: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0028 |
| 2024-02-29 | 2024-02-29 | 2024-02-26 | 3.0 | -0.017502 | 0.113487 | -0.130990 | DOGE: opposite_direction, v5_w=-0.1667, hv_w=0.1667, netdiff=-0.1102; LINK: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0700; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=-0.0289; ICP: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0223; TRB: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0201 |
| 2024-11-05 | 2024-11-05 | 2024-11-02 | 3.0 | -0.051842 | 0.028574 | -0.080416 | XRP: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=-0.0629; NEAR: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=-0.0525; HBAR: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=-0.0493; AAVE: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0491; BTC: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=-0.0441; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=0.0408; SOL: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=0.0160; RUNE: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0093 |
| 2024-08-27 | 2024-08-27 | 2024-08-24 | 3.0 | -0.015067 | 0.050304 | -0.065371 | NEAR: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0437; DOT: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0308; LINK: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0275; BNB: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=0.0175; AAVE: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=0.0131; UNI: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=-0.0126; HBAR: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0113; DOGE: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=0.0100 |
| 2023-09-12 | 2023-09-12 | 2023-09-09 | 3.0 | -0.045063 | 0.020121 | -0.065184 | SOL: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=-0.0354; XLM: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=-0.0164; TRX: v5_only, v5_w=0.1667, hv_w=0.0000, netdiff=0.0076; NEAR: v5_only, v5_w=-0.1667, hv_w=0.0000, netdiff=-0.0012; ETH: hv_only, v5_w=0.0000, hv_w=0.1667, netdiff=-0.0007; CRV: hv_only, v5_w=0.0000, hv_w=-0.1667, netdiff=0.0002 |

## Artifacts

- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/paired_mtm_v5_rw_vs_hv_balanced.png`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/paired_mtm_curve.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/paired_summary_metrics.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/paired_period_component_returns.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/component_summary.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/reconstructed_v5_positions.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/v5_reconstruction_return_parity.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/position_diffs.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/period_position_diff_summary.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/top_period_trade_differences.csv`
- `C:/Users/user/Documents/Claude/Projects/EnhengClaw/artifacts/quant_research/h10d_v5_rw_vs_hv_balanced_20260518/top_leg_diffs.csv`
