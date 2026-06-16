# Quant Next Data Specs

This document defines the next data upgrades that are worth paying for. It is intentionally narrow: each spec is tied to a blocked hypothesis family, not to a generic infrastructure roadmap.

## What This Unlocks

- CoinAPI spot breadth:
  - restores real cross-sectional rotation testing instead of a `3`-subject pseudo panel
- Long-history derivatives:
  - reopens crowding, regime-conditioned, and meta-labeling theses that currently fail closed on `derivatives_history_gap`
- Temporal event tape:
  - is the minimum requirement before `event_drift` can become an executable research family

## Derivatives History Spec

Blocked thesis families:

- `meta_labeling`
- `carry_funding`
- `basis_divergence`
- any future thesis with non-empty `data_dependencies.derivatives_fields`

Required fields:

- `funding_rate`
- `open_interest`
- `open_interest_value`
- `perp_close`

Required intervals:

- `4h`
- `1d`

Minimum historical depth:

- `>= 730d`

Replay and evidence requirements:

- must support `as_of`-aligned replay
- must support immutable evidence snapshots for historical reruns
- must preserve enough provenance to prove which rows were visible as of a given run date

Readiness target before derivatives theses are executable again:

- `train_ready_row_fraction >= 0.8`
- `validation_ready_row_fraction >= 0.8`
- `test_ready_row_fraction >= 0.8`
- no provider-cap warnings
- no provider start-gap warnings

Why this is the threshold:

- below this level, the current meta-labeling and derivatives-conditioned families cannot be falsified cleanly; they just amplify missing-data noise

## Temporal Event Tape Spec

Blocked thesis family:

- `event_drift`

Minimum fields:

- `subject`
- `event_time_utc`
- `event_type`
- `event_direction` or `event_weight`

Minimum behavior:

- timestamped, append-only, replayable by `as_of`
- enough event typing to distinguish meaningfully different catalysts instead of collapsing all events into one generic flag

What does not count:

- static `event_flag_count`
- static `narrative_tag_count`
- any universe snapshot field without event-time semantics

Why this is the threshold:

- without a temporal event tape, event hypotheses have no event-study boundary and no falsifiable timing claim

## Spot Breadth Requirement

This gap is already partially solved by the local CoinAPI sidecar and should not trigger a new provider project in phase 1.

Current requirement for executable cross-sectional research:

- mixed spot lane enabled by default
- `large_cap + mid_cap` executable subject count `>= 30`
- cross-sectional input requires both `spot 1d` and `spot 1h`

Current requirement for single-asset spot research:

- target subject must have both `spot 4h` and `spot 1d`

Why this matters:

- if the system can only build `ETH/SUI/UNI`-scale panels, any cross-sectional claim is structurally weak regardless of model complexity

## Decision Rule

Do not add a new provider or a new abstraction layer unless it satisfies one of these concrete hypothesis gaps:

- restores `>= 30` executable cross-sectional spot subjects
- provides `730d+` replayable derivatives history for `funding/open_interest/open_interest_value/perp_close`
- provides a replayable temporal event tape with per-event timestamps

If a proposed data project cannot be mapped to one of those unlocks, it is probably infrastructure theater rather than alpha research support.
