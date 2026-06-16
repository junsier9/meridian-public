# MF-XX: <Family Name>

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: <draft | active | watch | decay | retired>`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: <T1 immediate | T2 medium-data | T3 frontier-data>`

> Standard 1-page mechanism note per `alpha_ontology_and_factor_library.md` §G.1.
> One file per mechanism family in §B. The economic story, the imbalance, the
> expected sign and half-life, and the falsification path are the load-bearing
> fields. Implementation status keeps the note a live document rather than a
> static reference.

---

## Economic story

Two to three short paragraphs explaining the real-world imbalance, behavioural
bias, inventory constraint, or risk-transfer channel that creates the alpha.
Concrete enough that a non-quant trader on the desk can read it and recognise
the situation in tape; abstract enough to survive minor mechanic changes (data
provider, contract spec).

## Why this alpha persists

What prevents it from being arbitraged away in equilibrium. Pick one or more:

- **Capital constraint**: arbitrageurs can absorb only N notional before margin
  binds.
- **Operational friction**: KYC, withdrawal latency, settlement lag.
- **Mechanism type**: rule-driven flow (e.g. funding settlement, dealer hedge)
  is not a choice variable.
- **Belief vs information asymmetry**: heterogeneous priors with no PIT-clean
  way to update.
- **Attention bottleneck**: zero-sum cognitive bandwidth across narratives.

If the answer is "no one's looked", that is not persistence — that is an
edge that vanishes once the family is published. Re-classify as `watch`.

## Required primitives

Reference §C in the alpha-ontology memo. List the *minimum* raw fields needed,
not the engineered features:

- `<primitive_1>` — what it is, source provider
- `<primitive_2>` — ...

Flag any primitive that is **not yet ingested in the repo** with `[T2]` or
`[T3]` and link to the M2.x / M3.x roadmap item from §H of the memo.

## Candidate factors

Table of the §D blueprints that belong to this family. One row per `factor_id`.

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| FXX_<short> | `<column>` | `+ / − / cond` | a-b | T1/T2/T3 | not implemented / W1.1 features.py / admitted / in active manifest |

Implementation states:

- `not implemented` — column does not exist anywhere in `features.py`.
- `W1.1 features.py` — column produced by `_build_feature_bundle` but not yet
  scored against the 11-gate report card.
- `report-carded` — `factor_report_card.py` ran on it; record is in
  `artifacts/quant_research/factor_reports/<date>/`.
- `admitted` — `feature_admission.feature_admission_status` returns
  `admitted` for the column.
- `in active manifest` — column appears in the `required_feature_columns` of a
  current `cross_sectional_hypothesis_batch_manifest_*.json`.

## Expected sign and half-life

One-line summary across the family. If signs are heterogeneous across factors,
state per factor or per regime.

## Regime where strongest

Which market state amplifies the mechanism. Reference §B if the family is
universe-wide-only or asset-specific.

## Failure modes

Concrete situations where the mechanism breaks down. Examples: provider data
outage, contract roll, sparse-event windows, regime breaks that invert the
mechanism's sign. This is not the same as the falsification path — it is the
*operational* watch list.

## Falsification path

Empirical test that, if executed and showing the result, would invalidate the
family. Stated as a hard threshold and a window. Examples:

- "Rolling 60d residual IC of any admitted factor in this family stays below
  0.02 for 90 consecutive days → demote family to `watch`."
- "Per-quarter rank IC sign flips on 3+ regimes within a 12-month window →
  retire."

The §E memo entries also contain a "Falsification" line for each frontier
direction; copy the relevant one here verbatim where applicable.

## Implementation status

State which factors are currently:

- in `features.py`
- admitted via `feature_admission.py`
- present in any `cross_sectional_hypothesis_batch_manifest_*.json`
- evaluated by `factor_report_card.py` and where the cards are stored

The next-action item belongs at the bottom: what needs to land for the family
to graduate from its current state.

## Cross-references

- Alpha ontology memo: `docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md` §B (family overview), §D (blueprint table), §E (frontier direction if any), §H (roadmap)
- Factor library row(s): §D Family `MF-XX`
- Strategy upgrade roadmap: `docs/quant_research/00_roadmap_state/strategy_upgrade_roadmap.md`
- Threshold provenance log entries: `config/quant_research/threshold_provenance.md`

---

## Change log

- `2026-04-29` — initial note created from §B / §D content (W1.5).
