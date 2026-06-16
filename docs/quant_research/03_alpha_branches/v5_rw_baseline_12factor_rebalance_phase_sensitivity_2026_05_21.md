# v5_rw_bridge_no_overlay_h10d 12-factor 10d phase sensitivity

- generated_at_utc: `2026-05-21T14:41:22Z`
- baseline_label: `v5_rw_bridge_no_overlay_h10d`
- strategy_id: `xs_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d`
- source_features: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\features\2026-04-29-cross-sectional-daily-1d-h10d-exec-aligned-label-v1-features-v91\features.csv.gz`
- phase0_reconciliation: `passed` max_abs_diff=`9.71445146547012e-17`
- robustness_status: `failed`

2026-06-03 baseline supersession:

- This document is historical single-phase phase-sensitivity evidence.
- It does not define the current follow-on research baseline.
- The current research baseline is `v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`: the same score parent with 10-phase equal-sleeve construction.
- The phase fragility shown here is one reason the current baseline should be read through the smoothed construction layer.

## Interpretation

The original 12-factor 10d baseline is not robust to all 0..9 day rebalance-anchor shifts under this gate.
Worst non-zero phase by net return is phase `9` with net `0.623458`, sharpe `0.979919`, max DD `0.281592`, ratio vs phase0 `0.3530516252368101`.

## Phase Metrics

| Phase | Start | Periods | Net | Ratio vs phase0 | Sharpe | Max DD | WF median | Loss frac |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 2023-04-24 | 64 | 1.765913 | 1.000 | 2.199218 | 0.174568 | 3.359836 | 0.312 |
| 1 | 2023-04-25 | 64 | 2.253664 | 1.276 | 2.353010 | 0.184490 | 4.526361 | 0.328 |
| 2 | 2023-04-26 | 64 | 2.899127 | 1.642 | 2.602253 | 0.137752 | 3.029369 | 0.344 |
| 3 | 2023-04-27 | 64 | 3.949779 | 2.237 | 3.402843 | 0.138923 | 5.445332 | 0.297 |
| 4 | 2023-04-28 | 64 | 1.566077 | 0.887 | 1.658620 | 0.321022 | 7.235825 | 0.266 |
| 5 | 2023-04-29 | 64 | 2.361260 | 1.337 | 2.203330 | 0.241620 | 9.130860 | 0.234 |
| 6 | 2023-04-30 | 64 | 2.714495 | 1.537 | 2.665884 | 0.124856 | 3.983110 | 0.359 |
| 7 | 2023-05-01 | 64 | 1.211984 | 0.686 | 1.471385 | 0.230553 | 3.190847 | 0.406 |
| 8 | 2023-05-02 | 64 | 0.637319 | 0.361 | 0.895762 | 0.414911 | 3.072237 | 0.375 |
| 9 | 2023-05-03 | 64 | 0.623458 | 0.353 | 0.979919 | 0.281592 | 2.034667 | 0.391 |

## Gate Failures

- `phase_max_drawdown_delta_too_high` phase=`4` net=`1.5660769059162831` sharpe=`1.6586200338486072` max_dd=`0.32102155729309906` ratio=`0.8868371140280071`
- `phase_net_return_ratio_too_low` phase=`8` net=`0.6373194554147188` sharpe=`0.895762426377932` max_dd=`0.4149106007854258` ratio=`0.36090088833996503`
- `phase_max_drawdown_delta_too_high` phase=`8` net=`0.6373194554147188` sharpe=`0.895762426377932` max_dd=`0.4149106007854258` ratio=`0.36090088833996503`
- `phase_net_return_ratio_too_low` phase=`9` net=`0.6234583421619377` sharpe=`0.9799187306099411` max_dd=`0.28159226734179005` ratio=`0.3530516252368101`
- `phase_max_drawdown_delta_too_high` phase=`9` net=`0.6234583421619377` sharpe=`0.9799187306099411` max_dd=`0.28159226734179005` ratio=`0.3530516252368101`

## Artifacts

- summary_json: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\v5_rw_baseline_rebalance_phase_sensitivity_20260521\summary.json`
- phase_metrics_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\v5_rw_baseline_rebalance_phase_sensitivity_20260521\phase_metrics.csv`
- phase_period_returns_csv: `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\v5_rw_baseline_rebalance_phase_sensitivity_20260521\phase_period_returns.csv`

## Method Notes

- This is a research replay only; it does not touch live trading code or Binance APIs.
- The runner holds the original experiment spec, 12 factor list, train-only signed-IR weight formula, WFO shape, execution cost model, and `liquid_perp_core_20` universe fixed.
- Phase means the first eligible daily timestamp is shifted by `phase_offset_days`; subsequent WFO anchors follow from that shifted start.
- Phase0 is reconciled to the archived fixed-set aligned period returns before interpreting the sweep.
