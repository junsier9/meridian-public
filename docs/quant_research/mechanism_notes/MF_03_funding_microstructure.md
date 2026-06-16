# MF-03: Funding-rate microstructure (term skew + sign flip)

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1 (most factors); T2 (sub-day funding term skew)`

---

## Economic story

Perp funding is paid every 8h. That settlement is a forced cashflow on every
open position: longs pay shorts when funding > 0, and vice versa. Because
the settlement clock is fixed and known, *the funding rate at hour 7 of the
8h cycle is essentially a PIT-known cashflow at hour 8*. Holders who do not
want to pay re-balance before the settlement; holders who collect become
sticky. The sign-flip event — funding crossing zero after a sustained run —
is a leverage-cycle inflection: the side that has been receiving funding now
has to start paying, so they unwind.

Within a day there are 3 funding observations (00:00 / 08:00 / 16:00 UTC).
That sub-day series carries *term-structure* information that is destroyed
when daily-aggregated. The skew of the 3 observations within a day, and the
trajectory across the past several settlements, distinguish "structural
crowding" from "transient spike". Most public crypto factors collapse the
8-hour series into a single daily mean and lose this signal entirely.

## Why this alpha persists

- **Settlement is rule-driven**: cashflow is mechanical at the 8h boundary;
  participants cannot opt out.
- **Capital constraint**: leveraged longs that would prefer to ride out a
  negative-funding regime get forced out by margin / cost; short funding
  windows directly hit P&L.
- **Data resolution**: most quant pipelines daily-aggregate funding. The
  term-skew and sign-flip dynamics are visible only at the 8h-bar resolution.

## Required primitives

- `funding_rate` — already daily-aggregated in panel.
- `funding_rate` 8h series — **[T2] partial**: present in derivatives sync
  but not exposed as a column in the cross-sectional panel.
- `basis_proxy` — daily.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F06 | `funding_persistence_score` (TBD) | − (high persistence = crowding) | 7–14 | T1 | not implemented |
| F07 | `funding_sign_flip_rate` (TBD) | + (high flip = low crowding, more rebound headroom) | 5–10 | T1 | not implemented |
| F08 | `funding_term_skew` (TBD) | − | 5–10 | **T2** (needs 8h obs) | not implemented |
| F09 | `funding_basis_residual_20` | cond (residual > 0 → longs penalised) | 4–7 | T1 | **W1.1 implemented**, report-carded, **G6 FAIL** (residual IC −0.015) |
| F10 | `funding_oi_divergence` (TBD) | + (divergence = unwind end-stage → rebound) | 5–8 | T1 | not implemented |

## Expected sign and half-life

Most factors mean-revert in 5–14 days. Sign-flip-based factors are slower
(leverage cycle ≈ weeks). F09 carry residual is the fastest (4–7 days).

## Regime where strongest

Sustained-leverage / crowded-long regimes (where funding has stayed one-sided
for ≥ 30 days). Sign-flip factors are strongest at the cycle inflection
itself.

## Failure modes

- Funding-rate data gaps for individual symbols on individual settlement
  windows (handled by `derivatives_quality.py` ready-flag tracking).
- Sub-day funding factor (F08) requires accumulating ≥ 30 days of 8h obs
  before producing a stable estimate; treat as `watch` for first 30 days
  after deploy.
- Sign-flip events are sparse — rolling-IC estimators may be unstable on
  short evaluation windows.

## Falsification path

- Rolling 60d residual IC of F09 stays below 0.02 for 90 consecutive days →
  retire F09. (Already at the boundary in the W1.3 cards: residual IC
  −0.015 means F09 currently fails G6.)
- Funding-vs-basis rolling 60d correlation drops below 0.10 for 60 days →
  the no-arbitrage relation underlying F09 is broken; mechanism falsified.
- Per-quarter sign of F06 / F10 IC inconsistent across ≥ 3 of last 4 quarters
  → demote.

## Implementation status

- in `features.py`: F09 (`funding_basis_residual_20`) implemented in W1.1.
- admitted via `feature_admission.py`: F09 admitted via the W1.2 prefix
  `funding_basis_residual_*`.
- present in any active manifest: F09 is **not** in
  `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1.json`
  because it failed G6 in the W1.3 report card (residual IC −0.015 < 0.02).
- report-carded: see
  `artifacts/quant_research/factor_reports/2026-04-29/F09_funding_basis_residual.{json,txt}`.

Next action: implement F06 (funding persistence) and F07 (funding sign-flip
rate) on the existing daily funding column; report-card them. F08 (sub-day
term skew) requires exposing the 8h funding observations as a separate
column from the derivatives sync — coordinate with the derivatives quality
module first.

## Cross-references

- Alpha ontology memo §B (MF-03 row), §D (Family MF-03 table), §E.10
  (settlement-cycle hour-of-day premium), §E.11 (funding-OI-basis triangle).
- Threshold provenance log: `config/quant_research/threshold_provenance.md`
  W1.2 entry (admission) and W1.3 / W1.4 entry (report card + manifest
  decision on F09).

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
