# Distance-to-High-60 Q90 Top20 Overlay Preregistration

`Status: preregistered research candidate`
`Date: 2026-06-03`
`Scope: v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`
`Live impact: none`

## Decision

Freeze the following score-layer overlay candidate for forward-style validation:

```text
dth60_hybrid_shock_q90_or_crowded_top20_zero
```

This candidate is a research-only overlay on `distance_to_high_60`. It does not
change the score parent, feature set, portfolio engine, live manifest, paper
shadow manifest, or remote live configuration.

## Frozen Rule

For each WFO train window:

1. Estimate train-window thresholds:
   - `shock_co_occurrence_index` q90
   - `co_jump_count_3d` q90
2. In the future test window, trigger the overlay when either condition is true:
   - timestamp-level shock cluster fires:

```text
shock_co_occurrence_index >= train_q90
OR co_jump_count_3d >= train_q90
```

   - row-level near-high crowded condition fires:

```text
rank_pct(distance_to_high_60) >= 0.75
AND rank_pct(coinglass_top_trader_long_pct_smooth_5) >= 0.80
```

3. When triggered, set only the `distance_to_high_60` score contribution
   multiplier to `0.0`. All other factor contributions stay unchanged.

## Selection Provenance

The candidate was selected by the 2026-06-03 robustness validation using:

```text
selection_ex_episode_pre_holdout
```

The selector excluded the 2024-10-31 to 2024-11-25 drawdown episode and excluded
the untouched holdout that starts on 2025-10-01.

The q85 variants ranked better on the holdout, but they must not be selected in
this preregistration. Selecting q85 from the holdout would convert the holdout
from evaluation evidence into a tuning set.

## Forward-Style Validation Command

Run:

```powershell
python .\scripts\quant_research\h10d_current_diagnostics\run_dth60_frozen_q90_top20_forward_validation.py
```

Default holdout boundary:

```text
holdout_start = 2025-10-01
```

## Evaluation Rules

The forward-style validation should compare only:

- `baseline_no_factor_overlay`
- `dth60_hybrid_shock_q90_or_crowded_top20_zero`

No parameter grid is allowed in this validation. The q90/top20 parameters are
fixed before the run.

Minimum research pass conditions:

- holdout cumulative return delta vs baseline is positive;
- holdout h10d-equivalent Sharpe delta vs baseline is positive;
- holdout max drawdown is not worse than baseline;
- full OOS max drawdown is not worse than baseline;
- capacity breach count is zero.

Passing this packet is only evidence for paper-shadow/watch status. It is not a
live-trading approval and does not imply remote config changes.

## Metric Convention

Headline Sharpe must use:

```text
quant_h10d_overlap_adjusted_sharpe.v1
```

Do not report observed-frequency Sharpe as a headline metric for overlapping
h10d booking returns.
