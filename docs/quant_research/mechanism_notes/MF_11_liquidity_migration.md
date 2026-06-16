# MF-11: Liquidity migration & universe rotation

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1`

---

## Economic story

Capital does not stay still. Across a 4–8 week window, allocation flows
between large-cap (BTC / ETH) and mid-cap (top-20 ex-BTC/ETH), between
spot and perp, between already-listed names and newly-listed names, and
between active universe members and stablecoins. The flows leave footprints
in cross-asset quote-volume *share* — the percentage of total universe
quote-volume captured by each name — and in the rank of each name within
that share distribution.

A name whose share is rising faster than the cross-section is attracting
capital. The reverse — a name whose share has been falling for ≥ 30 days —
is losing capital. The lead-lag relationship between share velocity and
forward returns is real and slow (10–30 day half-life).

A second universe-wide pattern: the **dispersion of returns**. When the
cross-section is wide (some names up 8%, others down 6%, on the same day),
there is meaningful *idiosyncratic alpha* available to extract. When
dispersion is compressed (everyone moves together), single-name alpha
collapses and the regime is dominated by beta. Per §G.3, dispersion is
properly used as a position-size multiplier, not as a score component.

## Why this alpha persists

- **Rotation is physical**: capital cannot teleport. Wallet-level flow,
  exchange treasury flow, and stablecoin re-deployment leave traces with
  consistent timing.
- **Slow half-life**: 14–30 day signals are too slow for HFT firms to
  arbitrage and too fast for monthly-rebalanced quant funds. The window in
  between is empirically under-arbitraged.
- **Universe definition asymmetry**: a name graduating from mid-cap to
  large-cap status by quote-volume is a real flow event, but most factor
  pipelines lock the universe and lose this signal.

## Required primitives

- `daily_quote_volume` per asset — **partial**: panel has
  `spot_quote_volume` and `rolling_median_quote_volume_usd_30d`; an
  explicit per-asset daily series and the universe-wide aggregate are
  derivable but not yet exposed as columns.
- Per-asset rank within universe — derivable from existing columns.
- `return_1` — already in panel.

No external data ingest required.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F41 | `quote_share_change_30d` (TBD) | + (rising share = inflow) | 14–30 | T1 | not implemented |
| F42 | `universe_rank_velocity` (TBD) | + | 10–20 | T1 | not implemented |
| F43 | `capital_attraction_concentration` (TBD) | universe-wide regime gate | 30+ | T1 | not implemented |
| F44 | `dispersion_of_returns` (TBD) | universe-wide gating multiplier | 7–14 | T1 | not implemented |
| F45 | `idiosyncratic_share` (TBD) | + (high idio = alpha extractable) | 14–30 | T1 | not implemented |

§F top-20 ranks F44 at #4 (24/25 score) and F45 at #11 (22/25). F44 is
particularly important as a regime-gating multiplier — the doc's W1.4
recommendation explicitly mentioned F44 / F26 / F55 as the gating layer.

## Expected sign and half-life

F41 / F42 are positive-sign rotation factors with 10–30 day half-lives.
F44 / F45 are universe-wide states with longer effective lifetimes (≥ 14
days). F43 is a slow concentration measure used for regime gating.

## Regime where strongest

Mid-cap rotation phases (large-cap consolidating, capital seeking yield in
smaller names). Risk-on phases for F41 / F42; risk-off compresses
dispersion, so F44 / F45 are most useful as *gating-out* signals (turn
the strategy down when dispersion compresses).

## Failure modes

- Universe rotation churn — when the membership of `liquid_perp_core_20`
  changes, F41 / F42 produce spikes that look like flow but are universe
  artefacts. Stable measures require a pre-rotation universe baseline.
- Stablecoin pair churn — symbols moving between USDT-quoted and USDC-quoted
  pairs across exchanges create false flow signals.
- Slow half-life means evaluation requires ≥ 90 days of OOS data to gain
  statistical power; faster validation methods over-reject.

## Falsification path

- F41 / F42 rolling 60d residual IC < 0.02 for 90 days → retire.
- F44 / F45 as gating multipliers: their inclusion must improve `regime
  worst median sharpe` from the v91 baseline by ≥ 0.20 (per §G.6) over
  ≥ 60 days of measurement → otherwise retire from gating role.
- §E.9 (liquidity migration to new listings): post-listing 7-day window
  abnormal return for incumbent mid-caps not significantly negative → reject
  the new-listing migration hypothesis.

## Implementation status

- in `features.py`: none. The current builder operates per-subject; F41-F45
  require universe-wide aggregation.
- admitted via `feature_admission.py`: none.
- present in any active manifest: none.
- report-carded: none.

Next action: W3.3 (Day 14–30) — extend `_build_feature_bundle` with a
`_build_universe_rotation_features` step that runs after the per-subject
loop and computes F41 / F42 / F44 / F45. F44 belongs in the new
`regime_gating.py` (per §G.3 / W3.5), not in the score column list.

## Cross-references

- Alpha ontology memo §B (MF-11 row), §D (Family MF-11 table), §E.9
  (liquidity migration to new listings).
- §G.3 factor combination rule — gating multipliers vs score components.
- Strategy upgrade roadmap Phase 1 30-factor target.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
