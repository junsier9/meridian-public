# M3.1 Options Surface Overlay v1 Preregistration

`Status: report-only ablation complete; failed research-watch gate`
`Date: 2026-06-15`
`Scope: v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`
`Predecessor: m3_1_options_surface_top2_context_throttle_v0`
`Live impact: none`

## Decision

Open a new report-only M3.1 options-surface overlay candidate:

```text
m3_1_options_surface_signed_gamma_put_skew_throttle_v1
```

This v1 candidate is a new preregistered rule, not a continuation of the v0
pass/fail decision. The v0 candidate remains failed and quarantined comparator
evidence. v1 may be evaluated only by a future report-only ablation against the
current h10d research baseline:

```text
v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve
```

No active h10d registry, active manifest, feature-admission policy, live runner,
timer, scheduler, or remote execution control may be changed from this
preregistration.

## Why v0 Failed Despite Only 8 Of 640 Triggers

The v0 result is not paradoxical. It is the expected failure mode for a sparse,
direction-ambiguous portfolio throttle.

Observed v0 facts:

- triggered decisions: `8 / 640` threshold windows, or about `1.25%`;
- full OOS baseline cumulative return: `2.124384806883999`;
- full OOS candidate cumulative return: `2.106043196354828`;
- candidate full OOS return delta: `-0.01834161052917116`;
- baseline full OOS h10d-equivalent Sharpe: `1.9572510925856097`;
- candidate full OOS h10d-equivalent Sharpe: `1.9512974578311548`;
- candidate Sharpe delta: `-0.005953634754454873`;
- full OOS capacity breach count: `0`.

Diagnostic interpretation:

1. The v0 trigger was mechanically sparse. It required two train-window
   extremes to fire at the same time:

   ```text
   q90 IV-RV AND q10 term slope
   OR
   q90 abs dealer gamma AND q90 vanna/charm
   ```

   Under weak independence, each two-condition branch has an expected hit rate
   near `1%`. The observed `1.25%` full decision hit rate is therefore not
   surprising.

2. Sparse is not safe when the action is a full portfolio throttle. v0 cut the
   entire constructed h10d portfolio target to `0.75` on each trigger. If the
   selected eight windows were net positive baseline windows, the candidate
   would lose return even though it barely traded.

3. The observed return drag implies the triggered windows were not loss
   windows for the baseline. As a rough attribution, a `0.25` target reduction
   producing about `-0.01834` full-OOS cumulative-return delta means the eight
   selected events carried positive baseline contribution on the order of
   `0.01834 / 0.25`, before compounding and cost interactions.

4. v0 used `abs(dealer_gamma_proxy)`, which erased sign. In the current builder,
   `dealer_gamma_proxy` is call-positive and put-negative. Taking the absolute
   value can mix call-side convexity concentration, put-side fragility, and
   stabilizing near-expiry structure into one undirected "extreme" bucket.

5. v0 treated BTC/ETH options context as an unconditional portfolio-level risk
   flag for a broader h10d universe. It did not require put-skew confirmation,
   signed gamma fragility, or any baseline loss-state confirmation before
   reducing exposure.

Conclusion: v0 most likely failed as a false-positive de-risking rule. It found
rare options-surface extremes, but those extremes were not reliably adverse for
the h10d baseline.

## v1 Hypothesis

The options surface should be tested as a directional fragility filter, not as a
generic high-volatility throttle.

v1 changes the mechanism in three ways:

- keep the signed `dealer_gamma_proxy` instead of using absolute gamma;
- require put-skew or signed-gamma confirmation before throttling;
- use a softer multiplier so a false positive cannot dominate the result from a
  tiny number of events.

The intended edge is downside selectivity:

```text
options surface says fragility
AND the signal is directionally put/skew or negative-gamma confirmed
=> reduce portfolio target modestly
```

This must be proven by ablation. It is not assumed true.

## Frozen Inputs

Use only the full-backfill Tardis Deribit options-surface feature panel and the
existing h10d baseline feature/return artifacts used by the v0 ablation.

Required options columns:

- `iv_25d_skew_residual` (F56): put-skew residual confirmation;
- `iv_rv_spread` (F57): volatility risk premium;
- `iv_term_slope` (F58): front-vs-mid term structure stress;
- `dealer_gamma_proxy` (F59): signed gamma-distance proxy;
- `vanna_charm_window` (F60): near-expiry ATM OI concentration.

F56 is no longer observation-only for v1, but it may trigger only when its
method is the rolling-baseline residual:

```text
iv_25d_skew_residual_method = skew_minus_rolling_60d_mean
```

Rows using the raw-skew fallback must be treated as incomplete v1 context and
fail open to multiplier `1.00`.

## Frozen Context Aggregates

For each decision date, build BTC/ETH top-2 options context:

```text
top2_iv_rv_spread_median = median(BTC, ETH iv_rv_spread)
top2_iv_term_slope_min = min(BTC, ETH iv_term_slope)
top2_iv_25d_skew_residual_median = median(BTC, ETH iv_25d_skew_residual)
top2_signed_dealer_gamma_median = median(BTC, ETH dealer_gamma_proxy)
top2_vanna_charm_max = max(BTC, ETH vanna_charm_window)
```

Context is ready only when both BTC and ETH are present, F56-F60 are ready, and
the F56 residual method is `skew_minus_rolling_60d_mean` for both subjects.

## Frozen Train-Only Thresholds

For each h10d walk-forward train window, estimate thresholds only from ready
train context. The decision row and future/test rows must be excluded.

```text
iv_rv_spread_q70 = q70(top2_iv_rv_spread_median)
iv_term_slope_q30 = q30(top2_iv_term_slope_min)
iv_25d_skew_residual_q70 = q70(top2_iv_25d_skew_residual_median)
signed_dealer_gamma_q30 = q30(top2_signed_dealer_gamma_median)
vanna_charm_q70 = q70(top2_vanna_charm_max)
```

These thresholds are intentionally less extreme than v0 because v0's `8 / 640`
hit rate was too sparse for a reliable portfolio-level risk rule. This is a
new preregistered design choice, not an allowed post-ablation tuning knob.

## Frozen Rule

In the future validation/test window, compute:

```text
vol_put_stress_trigger =
  top2_iv_rv_spread_median >= train_iv_rv_spread_q70
  AND top2_iv_term_slope_min <= train_iv_term_slope_q30
  AND top2_iv_25d_skew_residual_median >= train_iv_25d_skew_residual_q70

signed_gamma_expiry_trigger =
  top2_signed_dealer_gamma_median <= train_signed_dealer_gamma_q30
  AND top2_vanna_charm_max >= train_vanna_charm_q70
```

When either trigger fires:

```text
portfolio_target_multiplier = 0.90
```

Otherwise:

```text
portfolio_target_multiplier = 1.00
```

The multiplier applies after existing h10d top/bottom selection and target
construction. It must not alter rankings, factor weights, long/short counts,
universe membership, score contribution, execution constraints, or capacity
limits.

Missing or incomplete v1 options context is fail-open for report-only ablation:

```text
missing_context_multiplier = 1.00
```

## Outcome-Blind Trigger Gate

Before comparing returns, the v1 ablation must report trigger coverage and fail
closed if the rule is unusably sparse or pathologically broad:

- total candidate triggered decision count must be at least `16`;
- total candidate triggered decision fraction must be between `0.025` and
  `0.20`, inclusive;
- both trigger branch counts must be reported separately;
- if one branch contributes zero triggers, the run is still allowed only if the
  total trigger gate passes and the zero branch is recorded as a design finding;
- no threshold retuning is allowed after reading the trigger preview.

## Evaluation Rules

The ablation may compare only:

- `baseline_no_options_surface_overlay`;
- `m3_1_options_surface_signed_gamma_put_skew_throttle_v1`.

Minimum research-watch pass conditions:

- trigger gate passes;
- full OOS cumulative return is not worse than baseline;
- full OOS h10d-overlap-adjusted Sharpe is not worse than baseline;
- full OOS max drawdown improves or is not worse than baseline;
- untouched holdout cumulative return is not worse than baseline;
- capacity breach count remains zero;
- excluding the first 60 ready context dates is not worse than baseline on
  cumulative return or h10d-equivalent Sharpe;
- active h10d registry and active manifest hashes remain unchanged.

Passing this packet would mean only:

```text
eligible_for_research_watch_review = true
```

It would not mean score-layer admission, active manifest admission, paper-shadow
approval, live approval, timer approval, or remote-runner approval.

## Required Future Runner Delta

A future implementation may add a new runner or extend the existing v0 runner,
but it must preserve v0 artifacts and labels. The v1 run must write:

- v1 context daily CSV with signed gamma and F56 residual-method readiness;
- v1 train-threshold CSV;
- v1 trigger branch counts;
- period returns for baseline and v1;
- triggered-period attribution showing whether v1 cut positive or negative
  baseline windows;
- non-mutation audit for active registry and active manifest hashes;
- machine-readable summary with all pass/fail blockers.

The runner must not silently reuse v0 `abs_dealer_gamma_proxy` thresholds.

## Forbidden Actions

This preregistration does not permit:

- changing `config/quant_research/active_h10d_registry.json`;
- changing any active h10d manifest;
- changing feature-admission allowlists;
- promoting F56-F60 into a score layer;
- treating trigger coverage as alpha evidence by itself;
- running live, timer, scheduler, OpenClaw, or remote-runner mutations;
- reusing v0 as if it were research-watch approved;
- tuning v1 thresholds after seeing v1 ablation returns.

## Full Backfill Ablation Result (2026-06-15)

Status:

```text
M3.1 overlay v1 report-only failed research-watch gate
```

Evidence:

- compute summary: `/data/meridian/artifacts/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_v1_ablation/summary.json`
- storage summary: `/tank/meridian/report_archive/factor_reports/2026-06-15-full-backfill-20230401-20260613/compute_outputs/m3_1_options_surface_overlay_v1_ablation/summary.json`
- local retained copy: `artifacts/quant_research/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_v1_ablation/summary.json`
- summary sha256: `753bbdec5fa71e73da116bc049341dba7c535e6e519d4df2f7771c17cc7214e2`
- definitions sha256: `6bdf7354efddb1664dfaf11ece1b782485f77e7d281048ba5d9e8ce3c13efc14`

Retained verdict:

```text
research_watch_state_allowed = false
eligible_for_research_watch_review = false
score_layer_admission_allowed = false
active_manifest_mutation_authorized = false
v1_admission_policy_mutation_authorized = false
live_or_timer_overlay_activation_authorized = false
```

Blockers:

- `trigger_count_below_min_16`;
- `trigger_fraction_below_min_0_025`;
- `full_oos_cumulative_return_worse_than_baseline`;
- `full_oos_max_drawdown_worse_than_baseline`;
- `exclude_first_60_context_dates_cumulative_return_worse_than_baseline`.

Key comparison:

- baseline full OOS cumulative return: `2.124384806883999`;
- candidate full OOS cumulative return: `2.1166871370712266`;
- candidate delta full OOS cumulative return: `-0.007697669812772645`;
- baseline full OOS h10d-equivalent Sharpe: `1.9572510925856097`;
- candidate full OOS h10d-equivalent Sharpe: `1.9575739992388688`;
- candidate delta full OOS h10d-equivalent Sharpe: `0.00032290665325906964`;
- baseline full OOS max drawdown: `0.16413712274836034`;
- candidate full OOS max drawdown: `0.1641414512923032`;
- holdout return delta: `0.0015238658688490059`;
- exclude-first-60-context return delta: `-0.007765342460541724`;
- capacity breach count: `0`.

Trigger diagnostics:

- threshold windows: `640`;
- v1 triggered decisions: `8` (`0.0125`);
- preregistered trigger gate: at least `16` triggers and fraction between
  `0.025` and `0.20`;
- `vol_put_stress_trigger_count = 2`;
- `signed_gamma_expiry_trigger_count = 6`;
- ready context days: `203` of `1170` context rows;
- exclude-first-context date cutoff: `2023-11-01`.

Triggered-window attribution:

- triggered windows: `8`;
- positive baseline triggered windows: `6`;
- baseline triggered-window net-return sum: `0.3732706799509657`;
- candidate triggered-window net-return sum: `0.3476631497197138`;
- triggered-window delta sum: `-0.02560753023125189`.

Interpretation: v1 improved the v0 false-positive drag, but did not fix the
root failure. The trigger remained `8 / 640`, below the preregistered
outcome-blind trigger gate, and most triggered windows were still baseline
positive. The slight Sharpe and holdout improvements are not enough to override
the failed full-OOS return, drawdown, and trigger-coverage gates.

Conclusion: `m3_1_options_surface_signed_gamma_put_skew_throttle_v1` is failed
and quarantined as comparator evidence. Do not promote this v1 overlay to
research-watch, score-layer admission, manifest admission, v1 admission policy,
paper-shadow, live, timer, scheduler, or remote-runner use. Any future M3.1
options overlay must be a new preregistered design that first addresses sparse
coverage and confirms that triggered windows are baseline-loss windows before
applying a portfolio throttle. Do not continue by micro-tuning quantile
thresholds; the next design must either prove that triggers primarily land on
baseline-loss windows or include an explicit loss-state confirmation gate before
any throttle is applied.
