# M3.1 Options Surface Overlay v2 Loss-State Preregistration

`Status: Stage A loss-state alignment complete; options-stress-to-portfolio-throttle pattern closed`
`Date: 2026-06-15`
`Scope: v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`
`Predecessors: m3_1_options_surface_top2_context_throttle_v0, m3_1_options_surface_signed_gamma_put_skew_throttle_v1`
`Live impact: none`

## Decision

Open a new report-only M3.1 options-surface design candidate:

```text
m3_1_options_surface_loss_state_confirmed_throttle_v2
```

This is not a continuation of the v0 or v1 pass/fail decisions. Both v0 and v1
remain failed and quarantined comparator evidence. v2 exists only to design and
pre-register a loss-state proof and decision-time confirmation gate before any
portfolio throttle may be evaluated.

No active h10d registry, active manifest, score-layer admission policy, live
runner, timer, scheduler, remote runner, or execution control may be changed
from this preregistration.

## Why v2 Is Needed

The v0 and v1 failures were not primarily threshold-selection failures. Both
candidates triggered only `8 / 640` windows, and the retained v1 attribution
showed that `6 / 8` triggered windows were baseline-positive. The triggered
baseline net-return sum remained positive enough that a throttle reduced
return even when it fired rarely.

Therefore v2 must not continue by micro-tuning options quantile thresholds. The
next valid question is narrower:

```text
Do options-surface stress events identify periods when the current h10d
baseline is already in, or entering, a loss state?
```

If the answer is no, an options-surface portfolio throttle is not justified on
this panel, regardless of small Sharpe or holdout improvements.

## Non-Negotiable Boundary

v2 freezes the following boundary before any implementation:

- no post-v1 micro-tuning of `iv_rv_spread`, `iv_term_slope`,
  `dealer_gamma_proxy`, `vanna_charm_window`, or put-skew quantile thresholds;
- no selecting an options trigger because its return ablation looks best;
- no using the same future baseline return both to decide a throttle and to
  score the throttle;
- no interpreting a proof pass as research-watch, score-layer, manifest,
  paper-shadow, live, timer, scheduler, or remote-runner approval.

The first v2 implementation must treat the v1 options-stress predicate as the
starting precursor. If a future design changes the options trigger itself, it
must open a separate preregistration and repeat the loss-state proof from
scratch.

## Proof Versus Confirmation

v2 separates two concepts that must not be mixed.

### Ex-Post Loss-State Proof

The proof is an attribution diagnostic. It may use realized future baseline
window returns only to answer whether the candidate's trigger set historically
landed on baseline-loss windows. It must not be used as a decision input inside
the candidate rule.

Define the same-window baseline loss label for each evaluation window:

```text
baseline_loss_window =
    baseline_no_options_surface_overlay.net_return < 0
```

The label is keyed by:

```text
phase_offset_days
window_index
test_start_utc
test_end_utc
```

For every precursor-triggered options window, join the corresponding baseline
window and compute:

```text
triggered_window_count
triggered_baseline_loss_count
triggered_baseline_loss_fraction
triggered_baseline_positive_count
triggered_baseline_positive_fraction
triggered_baseline_net_return_sum
all_window_baseline_loss_fraction
loss_fraction_lift =
    triggered_baseline_loss_fraction - all_window_baseline_loss_fraction
```

The proof fails closed if any join key is missing, duplicated, or if baseline
and candidate window calendars disagree.

### Ex-Ante Loss-State Confirmation Gate

The confirmation gate is the only loss-state input allowed inside a v2 throttle
decision. It must use only baseline state known before the decision window.

For each decision date and phase, compute:

```text
prior_closed_same_phase_baseline_window_return =
    net_return of the latest baseline window for the same phase_offset_days
    whose test_end_utc < current_decision_start_utc

trailing_10d_baseline_return =
    compounded baseline daily net_period_return over the last 10 calendar days
    ending before current_decision_start_utc

trailing_20d_baseline_drawdown =
    max drawdown of baseline daily net_period_return over the last 20 calendar
    days ending before current_decision_start_utc
```

Then:

```text
baseline_loss_state_confirmed =
    prior_closed_same_phase_baseline_window_return < 0
    OR (
        trailing_10d_baseline_return < 0
        AND trailing_20d_baseline_drawdown > 0
    )
```

If the prior closed same-phase window or trailing baseline daily returns are
unavailable, stale, duplicated, or not strictly before the decision start, the
confirmation gate is false for that decision.

This gate intentionally uses sign and availability checks rather than optimized
quantile thresholds. Its purpose is to prevent throttling positive baseline
states, not to maximize the backtest.

## Frozen v2 Rule Skeleton

The first v2 implementation may evaluate only this skeleton:

```text
options_stress_precursor =
    v1_vol_put_stress_trigger OR v1_gamma_expiry_trigger

v2_throttle_trigger =
    options_stress_precursor
    AND baseline_loss_state_confirmed

portfolio_target_multiplier =
    0.90 if v2_throttle_trigger else 1.00
```

The v1 options-stress precursor means the already preregistered v1 signed-gamma
and put-skew logic, including train-only thresholds and readiness rules. It
does not permit changing v1 options thresholds after reading v1 or v2 returns.

## Stage A: Loss-State Proof Gate

Before any v2 return ablation is interpreted, the runner must write a retained
loss-state proof summary and pass all of these gates:

```text
loss_state_proof_triggered_count_min = 16
triggered_baseline_loss_fraction_min = 0.60
loss_fraction_lift_min = 0.10
triggered_baseline_positive_fraction_max = 0.40
triggered_baseline_net_return_sum_max = 0.0
```

Required Stage A blockers:

- `loss_state_proof_trigger_count_below_min_16`
- `triggered_baseline_loss_fraction_below_0_60`
- `loss_fraction_lift_below_0_10`
- `triggered_baseline_positive_fraction_above_0_40`
- `triggered_baseline_net_return_sum_positive`
- `loss_state_join_key_missing_or_duplicated`
- `loss_state_calendar_mismatch`

If Stage A fails, the v2 result is a failed loss-state diagnostic. The runner
may still retain the diagnostic artifact, but it must not present return
ablation metrics as promotable evidence.

## Stage B: Report-Only Throttle Ablation

Stage B is allowed only if Stage A passes. The ablation must compare:

```text
baseline_no_options_surface_overlay
m3_1_options_surface_loss_state_confirmed_throttle_v2
```

against:

```text
v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve
```

Stage B must fail closed if any of the following are true:

- full-OOS cumulative return is worse than baseline;
- full-OOS h10d-equivalent Sharpe is worse than baseline;
- full-OOS max drawdown is worse than baseline;
- exclude-first-60-context-dates cumulative return is worse than baseline;
- exclude-first-60-context-dates h10d-equivalent Sharpe is worse than baseline;
- capacity breach count is non-zero;
- active h10d registry or active manifest hash changes;
- any v2 decision used baseline returns dated at or after its decision start.

Small holdout or Sharpe improvements cannot override a failed Stage A proof.

## Required Artifacts

A future v2 runner must write a new output directory and must not overwrite v0
or v1 artifacts.

Required Stage A artifacts:

- `loss_state_alignment_summary.json`
- `loss_state_alignment_windows.csv`
- `loss_state_alignment_daily_inputs.csv`

Required Stage B artifacts, only if Stage A passes:

- `summary.json`
- `summary.md`
- `overlay_definitions.json`
- `overlay_windows.csv`
- `overlay_period_returns_long.csv`
- `overlay_train_thresholds.csv`

The machine-readable summary must include:

```text
status
stage_a_loss_state_proof_allowed
stage_b_return_ablation_allowed
research_watch_state_allowed
eligible_for_research_watch_review
score_layer_admission_allowed
active_manifest_mutation_authorized
live_or_timer_overlay_activation_authorized
blockers
active_h10d_registry_before_sha256
active_h10d_registry_after_sha256
active_manifest_before_sha256
active_manifest_after_sha256
```

All authorization fields must remain false unless a separate owner-approved
promotion gate exists. This preregistration provides no such gate.

## Forbidden Actions

The following are explicitly forbidden:

- changing v1 options quantile thresholds to increase trigger count;
- using candidate return deltas to choose a loss-state definition;
- using future same-window baseline return in the confirmation gate;
- treating Stage A proof as live or paper approval;
- mutating active registry, active manifest, scheduled-task manifests, timers,
  live runner config, or remote execution controls;
- replacing v0 or v1 artifacts;
- re-labeling v0 or v1 as research-watch approved.

## Expected Failure Mode

Because v1 triggered only `8 / 640` windows, the first v2 implementation may
fail Stage A immediately on trigger count. That is an acceptable result. The
correct response is to retain the failure and close or redesign the mechanism,
not to lower the proof gates or loosen options thresholds after seeing returns.

## Stage A Loss-State Alignment Result (2026-06-15)

The Stage A diagnostic runner has been implemented and executed:

```text
scripts/quant_research/h10d_current_diagnostics/run_m3_1_options_surface_v2_loss_state_alignment.py
```

Retained local artifacts:

```text
artifacts/quant_research/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_v2_loss_state_alignment/loss_state_alignment_summary.json
artifacts/quant_research/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_v2_loss_state_alignment/loss_state_alignment_windows.csv
artifacts/quant_research/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_v2_loss_state_alignment/loss_state_alignment_daily_inputs.csv
```

Retained hashes:

```text
loss_state_alignment_summary.json sha256=6aa7746b785df707216a874b59f8247b16dda0036c54748d9a2c1cb0fc8339ad
loss_state_alignment_windows.csv sha256=0ea6df04e177bf1c1b3996d8a296b8a11af4cd653494ac7b925c087d8fc44189
```

Stage A result:

```text
status = computed_failed_stage_a
stage_a_loss_state_proof_allowed = false
stage_b_return_ablation_allowed = false
```

Blockers:

- `loss_state_proof_trigger_count_below_min_16`
- `triggered_baseline_loss_fraction_below_0_60`
- `loss_fraction_lift_below_0_10`
- `triggered_baseline_positive_fraction_above_0_40`
- `triggered_baseline_net_return_sum_positive`

Metrics:

- triggered windows: `8`
- triggered decisions: `8`
- triggered baseline-loss windows: `2 / 8` (`0.25`)
- triggered baseline-positive windows: `6 / 8` (`0.75`)
- all-window baseline-loss fraction: `101 / 320` (`0.315625`)
- loss-fraction lift: `-0.06562499999999999`
- triggered baseline net-return sum: `0.3732706799509657`
- vol-put stress trigger count: `2`
- signed-gamma expiry trigger count: `6`
- join-key duplicate count: `0`
- missing join count: `0`

Interpretation: v1 precursor triggers directly fail the v2 loss-state proof.
They are not merely too sparse (`8 < 16`); they are also directionally wrong
for a defensive throttle because the triggered set is less loss-concentrated
than all baseline windows and has strongly positive baseline return leakage.

Conclusion: Stage B return ablation is not allowed. Do not lower the Stage A
proof gates, loosen v1 options thresholds, or tune a new options quantile rule
from this failure.

## Closure Decision (2026-06-15)

Close the current M3.1 `options stress -> portfolio throttle` shape.

Closed shape:

```text
options-surface stress precursor
=> portfolio-level target multiplier throttle
```

This closure covers v0, v1, and the v2 loss-state-confirmed continuation of the
same shape. The reason is not just sparse coverage. The retained Stage A proof
shows that the v1 precursor triggered mostly baseline-positive windows, had
positive baseline return leakage, and was less concentrated in baseline-loss
windows than the full baseline window set.

Reopening conditions:

- a future candidate must be a new preregistered design, not a v0/v1/v2
  continuation;
- the precursor must be a new mechanism, not micro-tuned options quantile
  thresholds or relaxed v1 trigger thresholds;
- the action must not be interpreted as promotable until a Stage A loss-state
  proof passes on retained artifacts;
- the Stage A proof gates in this document remain the minimum bar unless a
  separate preregistration justifies stricter gates;
- no Stage B return ablation may be interpreted before Stage A passes.

Allowed future direction: a new non-threshold-microtuned precursor may be
proposed if it first explains why it should identify baseline loss states and
then passes the retained loss-state proof. Anything else should be treated as a
rerun of a closed false-positive defensive-throttle pattern.

## Current Status

The v2 Stage A diagnostic is implemented and failed. The current
`options stress -> portfolio throttle` shape is closed. No report-only v2
throttle ablation has been executed or may be interpreted. No research-watch,
score-layer, manifest, paper-shadow, live, timer, scheduler, or remote-runner
authorization exists.
