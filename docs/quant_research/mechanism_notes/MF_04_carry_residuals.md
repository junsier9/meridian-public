# MF-04: Carry & convenience-yield residuals

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: active`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1 (single-venue); T2 (cross-venue)`

---

## Economic story

In a frictionless market the perp-spot basis would equal the cumulative
funding paid over the holding period — that is the no-arbitrage statement
for a non-expiring perp contract. In practice basis and funding decouple
because the arbitrage is *capital-constrained*: cash-and-carry positions
need margin, balance-sheet capacity, and access to both the spot and perp
venue at scale. The residual `basis − funding-implied basis` is therefore
not noise — it measures how *binding* the arbitrage capacity constraint is
right now.

Residual carry pressure has a clear economic interpretation: when implied
repo from funding exceeds the spot-perp basis (i.e. perp longs are
"overpaying" for leverage relative to what the basis would provide), the
crowded long side is in the asymmetric risk-of-unwind position. The reverse
holds for crowded shorts. Cross-venue extensions of the same logic — e.g.
basis dispersion across Binance / OKX / Bybit — measure venue-specific
arbitrage friction and predict regression to the cross-venue mean.

## Why this alpha persists

- **Capital constraint**: cash-and-carry takes balance-sheet space; not all
  participants can deploy at scale. The residual reflects how much arbitrage
  *capacity* is left.
- **Operational friction**: cross-venue execution requires KYC at multiple
  exchanges, withdrawal latency, tax treatment differences. These do not get
  arbitraged away by smaller participants.
- **Data + modelling cost**: building a robust funding-implied repo requires
  careful handling of compounding, settlement timing, and convenience yield;
  most teams use a single basis z-score and miss the residual.

## Required primitives

- `funding_rate` — daily aggregate from derivatives sync.
- `basis_proxy` — daily aggregate, perp-spot premium ratio.
- `realized_volatility_20`, `atr_proxy_20` — derived in `features.py` for
  vol-normalisation of the residual.
- `daily_quote_volume` per venue — **[T2] not ingested as cross-venue** for
  F14 / F15 (single-venue is in panel).

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F11 | `basis_velocity_3d_xs_z` | cond | 2–4 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC +0.003) |
| F12 | `funding_basis_residual_implied_repo_30` | + (residual carry mean reverts) | 5–10 | T1 | **W1.1 implemented**, **admitted**, **in active manifest** (`xs_alpha_ontology_v1`) |
| F13 | `basis_carry_convexity_3d` | cond | 4–7 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC +0.013) |
| F14 | `cross_venue_funding_dispersion` (TBD) | + | 3–6 | **T2** | not implemented (needs cross-venue data; M2.1) |
| F15 | `cross_venue_basis_arbitrage_stress` (TBD) | + | 4–7 | **T2** | not implemented (M2.1) |

## Expected sign and half-life

F12 is the load-bearing positive-sign carry-residual factor in the family
(IC +0.023, 100% regime same-sign in the W1.3 cards). F11 / F13 are sub-G6
on current data — the per-bar carry derivatives carry less marginal
information than the rolling residual.

## Regime where strongest

Active arbitrage / regime change windows. F12 is strongest when funding has
been one-sided for ≥ 7 days and the basis is reverting toward mean (high
carry stress). F14 / F15 (cross-venue) are strongest in pre-arbitrage-
completion windows (extreme dispersion that has not yet been arbed).

## Failure modes

- Structural change in arbitrage capacity (e.g. major exchange listing
  delisted, prime broker withdrawing) shifts the residual mean and breaks the
  rolling z-score.
- `basis_proxy` data gaps on individual symbols (handled by ready-flag).
- Funding-implied repo model assumes no convenience yield; if a structural
  yield premium emerges (e.g. ETH staking yield arb), the model needs to
  net it out.

## Falsification path

- Rolling 60d residual IC of F12 stays below 0.02 for 90 consecutive days →
  retire F12. (Direct falsification trigger written into the
  `xs_alpha_ontology_v1` manifest's `falsification_conditions`.)
- Rolling 60d correlation between `funding_rate` and `basis_proxy` drops
  below 0.10 for 60 days → the no-arbitrage relation is broken; mechanism
  falsified at the family level.
- Cross-venue dispersion factor IC at z>2 subset < 0.10 → reject E.3
  frontier direction.

## Implementation status

- in `features.py`: F11 (`basis_velocity_3d` + `_xs_z`), F12
  (`funding_basis_residual_implied_repo_30`), F13 (`basis_carry_convexity_3d`)
  all from W1.1.
- admitted via `feature_admission.py`: all three via W1.2 (F12 by prefix
  `funding_basis_residual_*`; F11 + F13 via exact-column allowlist).
- present in any active manifest: F12 in
  `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1.json` with
  weight +0.07.
- report-carded: see
  `artifacts/quant_research/factor_reports/2026-04-29/F1{1,2,3}_*.{json,txt}`.

Next action: produce the cross-venue T2 extension (M2.1, Day 31–60). This
requires consuming the existing but-unused `coinapi_spot_sync.py` to ingest
multi-venue spot prices, then computing F14 / F15. Cross-venue data is also
the gating dependency for §E.3 (cross-exchange inventory stress) and §E.16
(cross-asset basis topology shock propagation).

## Cross-references

- Alpha ontology memo §B (MF-04 row), §D (Family MF-04 table), §E.3
  (cross-exchange inventory stress), §E.11 (funding-OI-basis triangle),
  §E.16 (cross-asset basis topology).
- Active manifest:
  `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1.json`.
- Threshold provenance log: `config/quant_research/threshold_provenance.md`
  W1.2 + W1.3/W1.4 entries.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
  Status set to `active` because F12 is in the live manifest.
