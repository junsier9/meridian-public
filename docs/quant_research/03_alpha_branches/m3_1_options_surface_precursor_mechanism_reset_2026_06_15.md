# M3.1 Options Surface Precursor Mechanism Reset

`Status: mechanism-hypothesis reset; no candidate admitted`
`Date: 2026-06-15`
`Scope: v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`
`Predecessors: M3.1 overlay v0, v1, and v2 Stage A loss-state diagnostic`
`Live impact: none`

## Decision

Return M3.1 options-surface work to the precursor mechanism-hypothesis layer.

The current path is no longer:

```text
options stress -> portfolio throttle
```

That shape is closed. Do not continue by repairing the portfolio-throttle form,
loosening v1 thresholds, lowering Stage A gates, or searching for a nearby
quantile combination that makes the backtest look better.

The only allowed next M3.1 path is:

```text
new precursor mechanism hypothesis
-> retained loss-state proof
-> only then consider whether any downstream action is worth preregistering
```

This document opens no runnable candidate, no score-layer feature, no manifest
entry, no paper-shadow path, and no live/timer/scheduler authority.

## Evidence For Reset

The reset is required by retained evidence:

- v0 was sparse and return-negative despite only `8 / 640` triggered decisions;
- v1 remained sparse at `8 / 640`, worsened full-OOS return and max drawdown,
  and triggered mostly baseline-positive windows;
- v2 Stage A proved that the v1 precursor was not a loss-state detector:
  - triggered windows: `8`;
  - triggered baseline-loss windows: `2 / 8` (`0.25`);
  - triggered baseline-positive windows: `6 / 8` (`0.75`);
  - all-window baseline-loss fraction: `101 / 320` (`0.315625`);
  - loss-fraction lift: `-0.06562499999999999`;
  - triggered baseline net-return sum: `0.3732706799509657`.

This means the failure is mechanistic, not cosmetic. The current options-stress
precursor selected a set of windows that were less loss-concentrated than the
overall baseline population.

## What Counts As A New Precursor

A future M3.1 precursor must be a mechanism claim, not a threshold variant.

It must state:

1. what options-surface condition is supposed to precede baseline loss;
2. why that condition should be adverse for the current h10d baseline rather
   than merely unusual in the options market;
3. what information is known before the decision window;
4. how the precursor will be evaluated by loss-state proof before any return
   ablation;
5. which old v0/v1/v2 assumptions it intentionally does not reuse.

Acceptable precursor forms may include event-state or sequence definitions,
cross-market confirmation, or a non-throttle warning label. They may not start
as a portfolio target multiplier.

## Examples Of Mechanism-Level Hypotheses

These are hypothesis families, not approved candidates.

### Dealer Hedging Pressure Transition

Claim shape:

```text
signed gamma structure changes
AND underlying/perp tape confirms one-way hedging pressure
=> baseline loss-state risk rises
```

This is different from v1 because signed gamma alone is not enough. The
precursor must identify a transition in hedging pressure that is confirmed by
spot/perp behavior known before the decision window.

### Vol-Risk Repricing Sequence

Claim shape:

```text
options vol-risk repricing sequence
AND realized market state confirms stress transmission
=> baseline loss-state risk rises
```

This is different from v0 because a high IV-RV spread or term-slope extreme is
not treated as a portfolio risk signal by itself. The mechanism must specify a
sequence and a transmission state.

### Expiry-Flow Path Dependency

Claim shape:

```text
expiry/strike concentration
AND pre-expiry underlying path enters adverse zone
=> baseline loss-state risk rises
```

This is different from generic expiry stress. The precursor must anchor to an
event window and a path condition known before the decision window, not a global
options-surface extreme.

### Cross-Market Confirmation Precursor

Claim shape:

```text
options-surface stress
AND independent non-options PIT confirmation
=> baseline loss-state risk rises
```

The confirmation source must not be another transformed version of the same
options threshold. It can be considered only if the source is PIT-safe,
available before the decision, and independently justified.

## Required Precursor Proof Sequence

Any future precursor must first run a loss-state proof before return ablation.

Minimum retained artifacts:

```text
precursor_definition.json
precursor_loss_state_alignment_windows.csv
precursor_loss_state_alignment_summary.json
precursor_input_audit.json
```

Minimum proof metrics:

```text
precursor_triggered_window_count
precursor_triggered_decision_count
triggered_baseline_loss_fraction
all_window_baseline_loss_fraction
loss_fraction_lift
triggered_baseline_positive_fraction
triggered_baseline_net_return_sum
join_key_duplicate_count
missing_join_count
```

Minimum gates remain the v2 Stage A bars unless a stricter preregistration is
opened:

```text
triggered_window_count >= 16
triggered_baseline_loss_fraction >= 0.60
loss_fraction_lift >= 0.10
triggered_baseline_positive_fraction <= 0.40
triggered_baseline_net_return_sum <= 0
```

If the proof fails, the result is a failed precursor diagnostic. No downstream
return ablation may be interpreted.

## Forbidden Shortcuts

The following do not count as new precursor work:

- changing q70/q30/q90-style thresholds around the v1 trigger family;
- replacing `0.90` with another portfolio multiplier;
- reducing the Stage A proof bars to fit the observed trigger count;
- using future same-window baseline return to decide the precursor;
- choosing a precursor because its return ablation looks best;
- calling a warning label a portfolio overlay without a new preregistration;
- treating a loss-state proof pass as score-layer, manifest, paper-shadow, or
  live approval.

## Next Allowed Document Shape

The next M3.1 document, if any, should look like:

```text
docs/quant_research/03_alpha_branches/
  m3_1_options_surface_new_precursor_<mechanism_slug>_preregistration_<date>.md
```

It must contain:

- mechanism hypothesis;
- predecessor failures it avoids;
- PIT-safe input contract;
- loss-state proof plan;
- proof gates;
- forbidden tuning actions;
- explicit non-authorization statement.

It must not contain a portfolio-throttle multiplier or Stage B return-ablation
claim unless a retained Stage A proof already passed under a separately
recorded artifact.

## Current Status

M3.1 options-surface work is reset to mechanism-hypothesis design. The closed
portfolio-throttle evidence remains useful as negative evidence, but it is no
longer a path to repair. No new precursor is approved, implemented, or run from
this reset note.
