# MF-02: Dealer gamma & vol-surface topology

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T2 (BTC/ETH); T3 (alts)`

---

## Economic story

Options dealers must delta-hedge their books. The size and direction of that
hedging flow are a deterministic function of (spot, strike, gamma, vega) — a
rule, not a view. When dealer net gamma is negative across the strike grid
near the money, intraday spot moves *amplify* hedge demand: a tick up forces
the dealer to buy more, which pushes spot further up, which forces more
buying. Positive net gamma compresses range. The vol surface (level, skew,
wing) carries enough information about dealer positioning that its *changes*
are predictive of next-day spot direction; the *level* of skew is much less
informative.

In crypto specifically, BTC and ETH have liquid weekly + monthly Deribit
options; alts have negligible options open interest. The mechanism is real
for BTC/ETH around expiry windows and for alts essentially absent. SVI
parameter dynamics (level, slope, wing) capture the same information at
lower dimensionality than per-strike OI maps.

## Why this alpha persists

- **Rule-driven**: dealer hedging is not a choice variable. The flow appears
  whenever spot moves through a strike-density cluster.
- **Data scarcity**: crypto options data is harder to acquire than US equity
  OPRA; few quant teams maintain Deribit historical OI-by-strike snapshots.
- **Modelling cost**: building a usable simplified BSM grid + SVI fit is a
  several-week engineering effort; teams that stop at single ATM IV miss most
  of the information.

## Required primitives

- `iv_25d_put`, `iv_25d_call`, `iv_atm_front`, `iv_atm_mid` — **[T2] not
  ingested** (Deribit API; M3.1 in §H).
- `iv_term_slope` — derived from front / mid IV.
- OI by strike snapshot (daily) — **[T2] not ingested** (Deribit).
- `spot_close` — already in panel.

The whole family is gated on M3.1 (Day 61–90) ingesting Deribit IV / OI by
strike via a new module `src/enhengclaw/quant_research/options_surface.py`.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F56 | `iv_25d_skew_residual` (TBD) | + (residual long-tail = priced-in hedging) | 5–10 | T2 | not implemented |
| F57 | `iv_rv_spread` (TBD) | − (IV high = vol risk premium) | 7–14 | T2 | not implemented |
| F58 | `iv_term_slope` (TBD) | cond (inversion = short-term stress) | 4–7 | T2 | not implemented |
| F59 | `dealer_gamma_proxy` (TBD) | regime gating | 3–7 | T2 | not implemented |
| F60 | `vanna_charm_window` (TBD) | cond (high near expiry compresses range) | 1–3 | T2 | not implemented |

## Expected sign and half-life

Mostly conditional or regime-gating. F56 and F60 are strong sub-7-day
signals; F57 and F58 are 5–14 day mean-reversion signals.

## Regime where strongest

Around weekly Friday + monthly last-Friday Deribit option expiries. F60 is
exclusively an expiry-window factor (near-zero outside 3-day expiry vicinity).
F59 (dealer gamma) is most informative when net gamma magnitude is large
relative to spot ADV.

## Failure modes

- Holidays / low-volume Fridays where dealer hedging is dispersed.
- Illiquid strikes producing noisy SVI fits (mostly an alt issue, also affects
  far-OTM BTC strikes).
- Snapshot frequency — daily snapshots may miss intra-day gamma profile shifts
  on volatile days.

## Falsification path

- Rolling 60d dealer-gamma proxy IC vs BTC 1d-forward |return| < 0.03 →
  reject family for BTC.
- Distribution of expiry-week vs non-expiry-week 5-day BTC forward returns:
  KS test p > 0.05 → reject F60.
- SVI 1-day-ahead parameter change cross-asset rank IC vs spot 5d-forward
  return < 0.05 → reject F58 / SVI dynamics.

## Implementation status

- in `features.py`: none. Family is fully T2; gated on M3.1.
- admitted via `feature_admission.py`: none. Once M3.1 produces columns, the
  W1.2-style allowlist extension will need a `iv_*` and `dealer_gamma_*`
  prefix addition with a corresponding provenance entry.
- present in any active manifest: none.
- report-carded: none.

Next action: M3.1 (Day 61–90) — implement `options_surface.py` to ingest
Deribit and produce F56-F60 columns + admission policy update.

## Cross-references

- Alpha ontology memo §B (MF-02 row), §D (Family MF-02 table), §E.1
  (frontier: dealer-gamma topology), §E.2 (SVI dynamics), §E.15 (expiry
  hedge unwind).
- Strategy upgrade roadmap: `docs/quant_research/00_roadmap_state/strategy_upgrade_roadmap.md`
  Phase 4 options extension.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
