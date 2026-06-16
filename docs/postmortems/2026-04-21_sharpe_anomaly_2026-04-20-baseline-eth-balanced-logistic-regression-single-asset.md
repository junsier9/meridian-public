# Sharpe Anomaly Postmortem: `2026-04-20-baseline-eth-balanced-logistic-regression-single-asset`

## Claim

This postmortem reconstructs the checked-in single-asset experiment and tests whether the anomalous Sharpe is better explained by `look_ahead_bias`, `overlap`, `timestamp_misalignment`, or `survivorship`. The primary root cause is `overlap`.

## Observed Metrics

- Validation Sharpe: `10.831956`
- Test Sharpe: `16.925255`
- Test max drawdown: `0.159927`
- Walk-forward median OOS Sharpe: `9.887089`
- Walk-forward window count: `4`

## Data / Label / Split Facts

- Subject: `ETH`
- Dataset provenance: `C:\Users\user\AppData\Local\Temp\quant-repo-health-tests-d_zrcw3l\artifacts\quant_research\datasets\2026-04-20-single-asset-4h\panel.csv.gz` rebuilt via `build_single_asset_features()`
- Label horizon: `6` bars / `24.0` hours
- Bar interval: `4.0` hours
- Adjacent label overlap fraction: `0.833333`
- Train split: `2025-08-01T00:00:00Z` -> `2026-01-04T20:00:00Z` (`942` rows)
- Validation split: `2026-01-05T00:00:00Z` -> `2026-02-26T04:00:00Z` (`314` rows)
- Test split: `2026-02-26T08:00:00Z` -> `2026-04-19T12:00:00Z` (`314` rows)
- Boundary contamination counts: train->validation=`6`, validation->test=`6`
- Backtest cadence mismatch: `detected=True` (`label_horizon_bars=6`, `evaluation_step_bars=1`, `rebalance_count=314`)

Walk-forward windows reconstructed via `_run_walk_forward()`:

- `1` train_end=`2025-10-30T00:00:00Z` validation_end=`2025-11-29T00:00:00Z` test_end=`2025-12-29T00:00:00Z` sharpe=`6.562222` train->validation contamination=`6` validation->test contamination=`6`
- `2` train_end=`2025-11-29T00:00:00Z` validation_end=`2025-12-29T00:00:00Z` test_end=`2026-01-28T00:00:00Z` sharpe=`-1.910793` train->validation contamination=`6` validation->test contamination=`6`
- `3` train_end=`2025-12-29T00:00:00Z` validation_end=`2026-01-28T00:00:00Z` test_end=`2026-02-27T00:00:00Z` sharpe=`13.211956` train->validation contamination=`6` validation->test contamination=`6`
- `4` train_end=`2026-01-28T00:00:00Z` validation_end=`2026-02-27T00:00:00Z` test_end=`2026-03-29T00:00:00Z` sharpe=`20.994248` train->validation contamination=`6` validation->test contamination=`6`

## Evidence for Each Candidate Cause

- `look_ahead_bias`: not supported. No direct t+ feature dependency was proven from the checked-in single-asset feature builder; the forward shift is confined to the target column, which is not in the model feature set.
  - `target_forward_return` is defined separately from model inputs and `target_forward_return` is not in `feature_columns` (57 columns checked).
  - Current leakage checks were `True` but they only attest to strict split ordering, not to forward-window reuse.
- `overlap`: supported. Supported. The 24h / 6-bar label overlaps heavily at a 4h evaluation cadence, split boundaries lack purge/embargo, and `_backtest_single_asset()` realizes the multi-bar forward return on every bar.
  - Split contamination counts are train->validation=`6` and validation->test=`6`.
  - Each reconstructed walk-forward window has train->validation contamination=`6` and validation->test contamination=`6` under the same 6-bar label horizon.
  - Backtest mismatch detected=`True` with `label_horizon_bars=6` and `evaluation_step_bars=1`.
- `timestamp_misalignment`: not supported. Not proven by the checked-in artifact set. This reconstruction reproduces the anomaly from the exported ETH panel without requiring any future-aligned join.
  - The rebuilt single-asset panel is monotonic in `timestamp_ms` and the anomaly is reproduced before introducing any alternate timestamp joins.
  - No checked-in audit evidence currently shows spot, perp, or event rows being joined from a future bucket.
- `survivorship`: not supported. Not applicable as the primary explanation: this is a fixed-subject ETH single-asset experiment, not a changing cross-sectional universe.
  - The experiment subject is fixed at `ETH`.
  - Universe survival bias could affect discovery scope, but it does not explain this card's single-asset Sharpe anomaly.

## Primary Root Cause

2026-04-20-baseline-eth-balanced-logistic-regression-single-asset is best explained by overlap: a 24h forward label is evaluated on every 4h bar, split boundaries have cross-window label contamination, and the backtest realizes that overlapping forward return on each rebalance step.

## Secondary Causes

- No secondary root cause was proven by the checked-in artifact set.

## Why current leakage_checks passed anyway

- `passed=True` because the current check only enforced strict timestamp ordering between train/validation/test windows.
- It did not apply purge or embargo around split boundaries, so multi-bar forward labels could still cross into the next split.
- It did not test whether `_backtest_single_asset()` was realizing a multi-bar forward label on every single 4h bar.

## Immediate Remediation

- Introduce non-overlapping target realization, or evaluate the single-asset strategy only every 6th bar when the label horizon is 24 hours.
- Add purge and embargo logic around train/validation/test and walk-forward boundaries.
- Align walk-forward window construction with the label horizon so boundary labels cannot reach into the next validation or test segment.
- Re-run this anomaly card only after the overlap and split-integrity changes are in place.
