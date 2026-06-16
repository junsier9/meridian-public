# MF-05: Cross-venue inventory stress

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T2`

---

## Economic story

When Binance, Coinbase, OKX, Bybit, and other major venues quote *the same
asset* at different prices or basis levels, the dispersion is a direct
measure of arbitrage friction. The friction is real: cross-venue arbitrage
requires KYC at multiple exchanges, withdrawal latency for spot leg, taxes
across jurisdictions, and venue-specific margin systems that do not net.
Dispersion above the 60-day 95th percentile is mechanically transient — once
the arbitrage capacity rebuilds, prices converge in 3–7 days. The
*direction* of convergence is informative for the cross-section.

A second pattern: when basis-proxy or funding dispersion across venues is
extreme but realised volatility is low, the friction has been *binding* for
multiple sessions without resolution. That is a stronger signal than the
naive z-score because it removes the case where dispersion just reflects
high vol everywhere.

## Why this alpha persists

- **Operational friction**: the constraint set above is structural and slow
  to evolve. New arbitrage capacity is bounded by KYC throughput and
  treasury approvals at the desk level.
- **Capital constraint**: cross-venue inventory needs balance-sheet on each
  venue separately; capital cannot be netted across.
- **Data engineering cost**: maintaining a clean multi-venue PIT-aligned
  panel is a several-week ingest project. Most quant teams stop at one venue.

## Required primitives

- `coinapi_spot_sync` multi-venue spot prices — **[T2] file present in repo
  (`coinapi_spot_sync.py`) but the cross-sectional panel does not yet
  consume it**. M2.1 in §H.
- Per-venue basis_proxy — **[T2] not present**.
- Per-venue funding_rate — **[T2] not present**.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F14 | `cross_venue_funding_dispersion` (TBD) | + (high dispersion = arb capacity exhausted → reversion) | 3–6 | T2 | not implemented |
| F15 | `cross_venue_basis_arbitrage_stress` (TBD) | + (extreme range = arbitrageur capital strained → discount reverts) | 4–7 | T2 | not implemented |

The frontier-direction §E.3 names additional factors implied by topology
across more than two venues; treat those as v_alpha_v2+ once F14 / F15 land.

## Expected sign and half-life

Both factors carry positive sign (high dispersion → mean reversion). EHL is
short (3–7 days) because cross-venue arbitrageurs are professional and
restore parity quickly once the binding constraint relaxes.

## Regime where strongest

Pre-arbitrage-completion windows. Risk-off windows where withdrawal latency
becomes especially costly (e.g. major-exchange outage, regulator action).

## Failure modes

- Venue data delays — different venues report at different cadences; PIT
  alignment is non-trivial. A factor evaluated on partly-stale data gives a
  spurious reading.
- Symbol mapping breakage — a coin listed under different ticker conventions
  across venues needs a stable mapping table.
- Holidays / regional outages — a Korean-only outage, for example, will
  produce dispersion that is an operational artifact rather than economic.
- Structural shift in venue mix (e.g. a venue is delisted, a new venue
  becomes top-3) requires re-baselining the dispersion z-score.

## Falsification path

- Rolling 60d cross-venue dispersion factor IC measured on the z>2 subset
  alone < 0.10 → reject the family (§E.3 frontier-direction line).
- BTC basis shock followed by alts basis impulse-response 1d-after t-stat
  < 2 → reject the cross-asset propagation hypothesis (§E.16).

## Implementation status

- in `features.py`: none. Family is fully T2; gated on M2.1.
- admitted via `feature_admission.py`: none. Once F14 / F15 land, an
  allowlist extension with `cross_venue_*` prefix and a corresponding
  provenance entry is required.
- present in any active manifest: none.
- report-carded: none.

Next action: M2.1 (Day 31–60) — extend the cross-sectional dataset profile
to consume `coinapi_spot_sync.py` outputs, derive per-venue
`basis_proxy_<venue>` columns, then compute F14 / F15. The single largest
risk is PIT timestamp alignment across venues; build the alignment layer
before any factor logic.

## Cross-references

- Alpha ontology memo §B (MF-05 row), §D (Family MF-04 table for F14 / F15),
  §E.3 (cross-exchange inventory stress), §E.8 (cross-asset basis topology
  graph), §E.16 (cross-asset basis topology shock propagation).
- Existing-but-unused script: `src/enhengclaw/data/coinapi_spot_sync.py`.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
