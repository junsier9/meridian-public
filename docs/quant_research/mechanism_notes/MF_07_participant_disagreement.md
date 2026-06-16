# MF-07: Participant disagreement

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1 (CEX positioning columns); T2 (whale on-chain leg)`

---

## Economic story

Different participant cohorts hold different priors over the future
distribution of returns. When CoinGlass top-trader long%, aggregate retail
long%, and on-chain whale activity diverge — e.g. top-traders rotating into
shorts while retail loads longs and whales accumulate — the divergence
itself is informative. The cohort that has historically been right
("smart money") is taking the other side of the cohort that has been wrong
("retail"), and the price typically follows the smart-money side over the
next 5–10 days.

A weaker but real signal is the *velocity* of any single cohort's
positioning, independent of the other cohorts. A top-trader long% that
rises 5pp over a 5-day window often precedes price strength even when
funding has not yet caught up. This is not magic — it is the same
information leakage that institutional flow generates in equity markets,
just with a noisier proxy.

The W1.3 cards show that the v91 baseline factor
`coinglass_top_trader_long_pct_smooth_5` carries a real but modest IC
(−0.026, 7/11 gates). The full family is much richer than this single
column suggests — the v91 baseline samples one slice (5-bar smoothing,
level-only) of a 4-dimensional space (cohort × scale × dimension ×
timeframe).

## Why this alpha persists

- **Information asymmetry**: cohort identification is a real cost. Mapping
  wallet → entity for whale-watching, separating top-trader API from retail
  noise, and aligning these to PIT timestamps requires per-source
  infrastructure that few teams maintain.
- **Belief heterogeneity**: even when the data is observable, participants
  *disagree* about whether to follow it. That disagreement keeps the signal
  from being arbed.

## Required primitives

- `coinglass_top_trader_long_pct` — daily Coinglass series; in panel.
- `coinglass_global_account_long_pct` — daily aggregate Coinglass series; in
  panel (used by `disagree_tt_retail` already).
- `coinglass_top_trader_intraday_volatility_24h` — in panel.
- Whale on-chain transaction series — **[T2] not ingested** (Glassnode /
  CryptoQuant, M3.2 in §H).
- `funding_rate` — used to *infer* aggregate long% via implied positioning.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F21 | `top_trader_vs_aggregate` (TBD) | cond (top trader is right) | 5–10 | T1 | not implemented (overlaps `disagree_tt_retail`) |
| F22 | `top_trader_velocity` (TBD) | + | 4–7 | T1 | not implemented |
| F23 | `top_trader_position_vol` (TBD) | − (high vol = unreliable signal) | 7–14 | T1 | not implemented |
| F24 | `disagreement_to_realized_vol` (TBD) | + | 3–6 | T1 | not implemented |
| F25 | `whale_retail_spread` (TBD) | + | 5–10 | **T2** | not implemented (needs on-chain ingest, M3.2) |

The existing v91 baseline factor `coinglass_top_trader_long_pct_smooth_5`
is the level-only slice; the family proposes velocity, vol, and
disagreement-vs-vol slices on top.

## Expected sign and half-life

F22 (velocity) and F25 (whale-retail spread) carry positive sign — top-
trader / whale moves predict same-direction returns. F23 carries negative
sign (high signal vol = noise). F21 / F24 are conditional on which cohort
is "right" in the current regime.

## Regime where strongest

Low-conviction regimes (everyone hedging, low realised vol) for F24 (the
divergence amplification factor); pre-breakout windows for F22 (velocity);
trending regimes for F21 (cohort difference resolves).

## Failure modes

- Coinglass data delay or schema change — affects all CEX-positioning
  factors uniformly.
- Wallet-labeling drift for F25 — a wallet identified as "whale" 12 months
  ago may not be the same actor today. Re-validate quarterly.
- "Top trader" cohort definition is opaque (Coinglass-internal). Treat as
  an instrument, not a ground truth.

## Falsification path

- Rolling 60d residual IC of any admitted factor in the family stays below
  0.02 for 90 days → retire that factor.
- For F25 specifically: leave-one-wallet-out cross-validation IC < 0.04 →
  reject (the signal is concentrated in too few wallets to be robust).
- §E.14 frontier-direction line: KOL / whale lead-lag IC < 0.04 in
  leave-one-wallet-out → reject the lead-lag interpretation.

## Implementation status

- in `features.py`: only the v91 baseline derivative
  `coinglass_top_trader_long_pct_smooth_5` and the existing
  `disagree_tt_retail` from Phase 1b. The MF-07 family-specific F21-F25
  blueprints are not yet implemented.
- admitted via `feature_admission.py`: the v91-baseline columns are
  admitted via existing exact-column allowlist; F21-F25 columns would need
  new entries.
- present in any active manifest:
  `coinglass_top_trader_long_pct_smooth_5` is in
  `cross_sectional_hypothesis_batch_manifest_v91.json` and
  `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1.json` with
  weight −0.07.
- report-carded: `v91_tt_long_smooth_5` card is at
  `artifacts/quant_research/factor_reports/2026-04-29/v91_tt_long_smooth_5.{json,txt}`
  (7/11 gates).

Next action: implement F22 (top-trader velocity = `T_diff(tt_long_pct, 5)
then XS_z`) as the highest-ROI single addition; it does not require any new
data and tests the velocity hypothesis directly. Report-card it. If G6
passes against v91 + alpha_ontology_v1 baseline, fold into a v_alpha_v2
manifest expansion. F25 (whale-retail spread) is gated on M3.2 on-chain
ingest.

## Cross-references

- Alpha ontology memo §B (MF-07 row), §D (Family MF-07 table), §E.14 (KOL /
  on-chain whale lead-lag frontier).
- Strategy upgrade roadmap Phase 4 on-chain extension.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
