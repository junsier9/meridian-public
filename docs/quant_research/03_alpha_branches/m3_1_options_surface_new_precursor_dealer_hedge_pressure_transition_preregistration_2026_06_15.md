# M3.1 New Precursor: Dealer Hedge Pressure Transition

`Status: closed failed mechanism evidence; no confirmation-threshold tuning`
`Date: 2026-06-15`
`Scope: v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`
`Predecessor reset: m3_1_options_surface_precursor_mechanism_reset_2026_06_15`
`Trading action: none`
`Live impact: none`

## Decision

Open exactly one new M3.1 precursor mechanism hypothesis:

```text
m3_1_options_surface_dealer_hedge_pressure_transition_precursor_v0
```

This is a precursor-only hypothesis. It is not an overlay, not a throttle, not a
score-layer feature, not a portfolio multiplier, and not a trading rule. Its
first allowed output was a retained loss-state proof, which has now failed.

## Mechanism Hypothesis

The closed v0/v1/v2 path treated options-surface stress as a static portfolio
risk flag. That failed because the triggered windows were mostly
baseline-positive.

This new precursor asks a different question:

```text
Does a transition in dealer hedging pressure, confirmed by BTC/ETH spot/perp
tape before the decision window, identify baseline loss states?
```

The mechanism claim is:

```text
dealer hedging pressure transitions from stabilizing/neutral to adverse
AND BTC/ETH underlying/perp tape confirms one-way downside pressure
=> current h10d baseline is more likely to be in or entering a loss state
```

The word "transition" is essential. A high options-surface reading is not enough
and must not be reused as a v1-style threshold event.

## Why This Is New Versus v0/v1/v2

This precursor intentionally avoids the closed shape:

- it does not use `q70`, `q90`, or nearby quantile micro-tuning;
- it does not treat high IV-RV spread, steep term slope, signed gamma, or
  vanna/charm as a standalone stress trigger;
- it requires a state transition, not a static extreme;
- it requires independent BTC/ETH spot/perp tape confirmation;
- it produces only a warning label for loss-state proof, not a portfolio target
  change.

## PIT-Safe Input Contract

All inputs must be known strictly before the evaluated decision window.

Required options-surface fields, computed from the retained Tardis Deribit
options panel:

- `dealer_gamma_proxy`
- `vanna_charm_window`
- `iv_25d_skew_residual`
- `iv_term_slope`

Required BTC/ETH spot/perp confirmation fields, computed from the current
baseline feature panel or another retained PIT-safe feature panel:

- `return_1`
- `momentum_5`
- `basis_velocity_3d`
- `coinglass_taker_net_volume_24h` or `coinglass_taker_imbalance_5d_sum`
- `perp_quote_volume_usd`

The proof runner must retain exact source paths and SHA256 hashes for every
input file. If BTC/ETH tape rows are missing, duplicated, stale, or timestamped
at or after the decision window start, the precursor is false for that
decision.

## Precursor Definition

This preregistration defines a mechanism shape, not a trading action.

The proof runner instantiates the precursor only with non-optimized
state-transition rules:

```text
options_transition =
    top2 signed dealer gamma moves from non-negative/neutral to negative
    OR top2 signed dealer gamma becomes more negative for two consecutive
       PIT-safe daily observations

expiry_pressure_context =
    vanna_charm_window is rising over the same PIT-safe observation sequence
    OR iv_25d_skew_residual is rising while iv_term_slope is flattening

tape_confirmation =
    BTC/ETH top2 underlying/perp tape shows downside pressure before the
    decision window
```

Then the precursor label is:

```text
dealer_hedge_pressure_transition_precursor =
    options_transition
    AND expiry_pressure_context
    AND tape_confirmation
```

The exact implementation must be separately coded and audited. This document
does not authorize choosing thresholds by looking at returns.

## Tape Confirmation Rules

The first implementation must avoid optimized numeric thresholds. It may use
only sign and direction conditions such as:

```text
top2_return_1_median < 0
top2_momentum_5_median < 0
top2_basis_velocity_3d_median <= 0
top2_taker_pressure_median <= 0
```

At least two independent tape-confirmation families must agree:

- price path: `return_1` or `momentum_5`;
- derivatives pressure: `basis_velocity_3d`, taker pressure, or perp quote
  volume expansion.

The runner must record which families fired. If the proof later shows that one
family dominates false positives, that is a diagnostic result, not permission
to tune a replacement threshold in place.

## Required Loss-State Proof

Before any downstream use, the precursor must pass retained Stage A
loss-state proof.

Required artifacts:

```text
precursor_definition.json
precursor_loss_state_alignment_summary.json
precursor_loss_state_alignment_windows.csv
precursor_input_audit.json
```

Minimum gates:

```text
triggered_window_count >= 16
triggered_baseline_loss_fraction >= 0.60
loss_fraction_lift >= 0.10
triggered_baseline_positive_fraction <= 0.40
triggered_baseline_net_return_sum <= 0
join_key_duplicate_count = 0
missing_join_count = 0
```

If any gate fails, the precursor is a failed mechanism diagnostic. No Stage B
return ablation may be interpreted.

## Proof Runner

The precursor-only runner is:

```text
scripts/quant_research/h10d_current_diagnostics/run_m3_1_options_surface_dealer_hedge_pressure_precursor_proof.py
```

It writes only retained proof artifacts:

```text
artifacts/quant_research/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_dealer_hedge_pressure_transition_precursor_v0_proof/
```

It does not define, evaluate, or execute any portfolio target multiplier,
exposure change, long/short replacement, score-layer candidate, paper-shadow
path, remote-runner action, timer action, scheduler action, or live action.

## Retained Loss-State Proof Result

The proof was run locally on 2026-06-15 and failed:

```text
status = computed_failed_loss_state_proof
loss_state_proof_allowed = false
stage_b_return_ablation_allowed = false
trading_action_authorized = false
```

Retained artifacts:

```text
precursor_loss_state_alignment_summary.json sha256=561951f4e2ad011fc8f3f1093fb3c0f368fceeb9733c3a4501c93a7e1f845dc7
precursor_loss_state_alignment_windows.csv  sha256=5818e1a809cd4b3331b62b7d55f2b5915ceee835ab09ee99dc42b0d3c6c3aeb5
precursor_definition.json                   sha256=c25eecbc98cae6e4baada75b0e0407ee00cd7a481dd805c22403a72d830c95d7
precursor_input_audit.json                  sha256=fd6f243dd3c349453a644f1d0f8f03166c161867625b8dac0202cc7f5b084a94
```

Key metrics:

```text
all_window_count = 320
all_baseline_loss_count = 101
all_window_baseline_loss_fraction = 0.315625
precursor_triggered_window_count = 16
precursor_triggered_decision_count = 16
triggered_baseline_loss_count = 5
triggered_baseline_loss_fraction = 0.3125
triggered_baseline_positive_count = 11
triggered_baseline_positive_fraction = 0.6875
loss_fraction_lift = -0.003125
triggered_baseline_net_return_sum = +0.47273070367336345
join_key_duplicate_count = 0
missing_join_count = 0
```

Blockers:

```text
triggered_baseline_loss_fraction_below_0_60
loss_fraction_lift_below_0_10
triggered_baseline_positive_fraction_above_0_40
triggered_baseline_net_return_sum_positive
```

Interpretation: the new mechanism cleared the minimum trigger count exactly
(`16`), but it still did not concentrate on baseline-loss states. Triggered
windows were baseline-positive `11/16` times, and triggered-window baseline
net return was positive. Therefore this precursor remains failed mechanism
evidence only.

## Closure Decision

Close `m3_1_options_surface_dealer_hedge_pressure_transition_precursor_v0` as
failed mechanism evidence.

Do not continue this path by tuning any confirmation condition, including:

- `return_1` sign or magnitude;
- `momentum_5` sign or magnitude;
- `basis_velocity_3d` sign or magnitude;
- taker-pressure sign or magnitude;
- perp quote-volume expansion;
- the number of prior options or tape observations;
- alternative AND/OR wiring among the same options-transition and tape families.

Reason: the retained proof already showed the core failure mode. The precursor
did not primarily identify baseline-loss states after clearing the count floor.
Changing confirmation thresholds on the same family would be post-failure
selection, not a genuinely new precursor mechanism.

Any future M3.1 precursor must be preregistered as a new mechanism before
implementation and must again pass retained loss-state proof before any return
ablation, score-layer interpretation, paper-shadow use, or trading action.

## Explicit Non-Actions

This document forbids:

- portfolio target multipliers;
- exposure reductions;
- long/short replacement;
- score-layer admission;
- active manifest mutation;
- v1 admission-policy mutation;
- paper-shadow use;
- live, timer, scheduler, or remote-runner use;
- tuning the above confirmation conditions to repair this failed precursor;
- deriving any trading action from this hypothesis before retained loss-state
  proof.

## Current Status

This is the first post-reset M3.1 precursor mechanism hypothesis. It has now
been implemented only as a precursor proof runner, run locally, and rejected by
retained loss-state proof. It is not admitted and is now closed as failed
mechanism evidence. No Stage B return ablation may be interpreted, no
confirmation-threshold repair path is open, and no trading action may be
derived from it.
