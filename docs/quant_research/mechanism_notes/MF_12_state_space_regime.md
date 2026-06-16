# MF-12: State-space regime persistence

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1`

---

## Economic story

Some variables are continuous; some are discrete. Crypto markets exhibit
*regime* behaviour at both fast and slow scales — vol regimes (low / mid /
high), funding regimes (one-sided / mixed), basis regimes, dispersion
regimes, ETF-flow regimes. The *state* of these regimes is more stable
than the underlying continuous variable, and *time spent in the current
state* is itself informative.

A name in a high-vol regime that has just *entered* the regime behaves
differently from a name that has been in the regime for 20 days. The fresh
entry tends to revert to the prior regime more often; the long stay tends
to break out into a yet-higher state. Regime-quantile factors (e.g.
funding's current value's percentile within its 60-day distribution)
capture the same conditioning at a higher resolution than a binary "high
regime / not high regime" cut.

The MF-12 family is most useful as a **regime-gating layer** — variables
that modulate position size or factor weighting based on the universe-wide
state — rather than as score components. Per §G.3, the alpha-ontology memo
explicitly recommends keeping these out of the score: F44 / F26 / F55 / F35
should enter the position-size multiplier, not the score.

## Why this alpha persists

- **State-space discretisation cost**: choosing the right break points for
  low / mid / high regimes is empirical. Teams that discretise wrong reject
  the family.
- **Slow rebalancing**: regime transitions are 30+ day events; quant
  pipelines focused on 5-day forward returns under-detect the gating value.
- **Conditioning is hard**: gating multipliers introduce non-linearity that
  walk-forward weight optimizers do not handle well.

## Required primitives

- `realized_volatility_20` — derived in `features.py`.
- `funding_rate`, `basis_proxy` — daily.
- BTC `realized_volatility_20` — per-anchor-subject, used by F55 and the
  factor-report-card G3 regime classifier.
- Universe dispersion (from MF-11 F44) — derivable.

No new ingest required.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F51 | `vol_regime_persistence` (TBD) | cond | 14–30 | T1 | not implemented |
| F52 | `funding_regime_quantile` (TBD) | − (>80%ile = crowded) | 5–10 | T1 | not implemented |
| F53 | `basis_regime_quantile` (TBD) | − | 5–10 | T1 | not implemented |
| F54 | `dispersion_regime_label` (TBD) | universe-wide gate | 30+ | T1 | not implemented |
| F55 | `btc_vol_regime_quantile` (TBD) | universe-wide gate | 14–30 | T1 | not implemented |

§F top-20 ranks F51 at #17 (22/25). F44 / F55 are the recommended gating
multipliers in §G.3.

## Expected sign and half-life

F52 / F53 are negative-sign mean-reverting quantile factors (extremes
revert). F51 carries conditional sign — the *direction* of next regime
transition depends on which regime the asset is currently in. F54 / F55
act as universe-wide gating multipliers and do not have a single IC sign.

## Regime where strongest

F52 / F53: most informative at extreme quantile readings (>80% or <20%).
F51: most informative when an asset has been in a regime for either very
short (<5 days, transition risk) or very long (>30 days, breakout risk).
F54 / F55: gating role, not factor role.

## Failure modes

- Break-point miscalibration — a 33/67 percentile cut may not be optimal in
  every market state. Using rolling-window percentile is robust to level
  shifts but increases parameter count.
- Regime persistence bias — fitted on a panel that is dominated by one
  regime (e.g. 2023-2024 sustained bull) under-weights cross-regime
  generalisability.
- Slow horizons — 14–30 day half-lives mean ≥ 90 days of OOS data is
  needed for evaluation power.

## Falsification path

- F52 / F53 rolling 60d residual IC < 0.02 for 90 days → retire.
- F44 / F55 as gating multipliers: per §G.6 exit criterion, must improve
  regime-worst median sharpe from the v91 baseline (-2.0 from §H.2 entry)
  to ≥ -1.5 over a ≥ 60-day evaluation window → otherwise retire from
  gating role.
- §E.17 (realised correlation regime switch): if the cross-section IC in
  the low-correlation regime is not at least 1.2x the all-regime baseline
  → reject as a useful gate.

## Implementation status

- in `features.py`: none of the F51-F55 blueprints. Note that the W1.3
  factor report card script (`factor_report_card.py`) implements a
  3-tertile BTC realised-vol regime classifier internally — that is the
  closest the repo currently has to F55 and is reusable as a starting
  point.
- admitted via `feature_admission.py`: none.
- present in any active manifest: none.
- report-carded: G3 in the W1.3 cards uses the BTC regime tertile, which
  is methodologically equivalent to F55 used as G3 input. The output is
  recorded in the per-factor cards' `G3_regime_consistency.regime_ic`
  field.

Next action: W3.5 (Day 14–30) — implement
`src/enhengclaw/quant_research/regime_gating.py` per §G.3 / §H.2 W3.5
recommendation. The module owns F44 / F55 / F26 (from MF-09 / MF-11) and
exposes a position-size multiplier rather than a score component. F51 /
F52 / F53 can be added as regular score factors in a v_alpha_v2
manifest expansion subject to W1.3-style report-card admission.

## Cross-references

- Alpha ontology memo §B (MF-12 row), §D (Family MF-12 table), §E.17
  (realised correlation regime switch), §G.3 (factor combination rule).
- `scripts/quant_research/factor_report_card.py` — BTC realised-vol
  tertile classifier.
- `cross_sectional_hypothesis_batch_manifest_v91.json` and
  `_alpha_ontology_v1.json` — the score-component-only baseline manifests
  that this family eventually multiplies.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
