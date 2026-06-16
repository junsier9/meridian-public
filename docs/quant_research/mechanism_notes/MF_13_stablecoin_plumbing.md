# MF-13: Stablecoin plumbing & monetary aggregates

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T3 (high ROI)`

---

## Economic story

Stablecoins are the M0 of the crypto economy. USDT, USDC, and (to a lesser
extent) DAI represent the cash held against future risk-asset deployment.
Issuance and redemption flows are observable on-chain and are *leading*
indicators of risk-asset capital deployment.

Three sub-mechanisms within the family:

1. **Supply growth velocity**: weekly net issuance of USDT + USDC, scaled by
   total stablecoin supply. Acceleration above the 30-day baseline signals
   capital being prepared for deployment. Historically leads BTC return by
   ~14 days.
2. **Stablecoin-to-BTC market-cap ratio**: when the ratio rises, "dry
   powder" sitting on the sidelines is growing. Mean-reverts over 30+ day
   windows.
3. **Exchange flow asymmetry**: stablecoin moving onto exchanges while BTC
   is moving off exchanges → buy preparation. The reverse → distribution.

The signal lifetimes are long (≥ 14 days for the supply-velocity factor,
≥ 30 days for the marketcap-ratio factor). They are macro-conditioning
signals more than score components — useful both for direct
cross-sectional prediction (via XS-z over the universe) and for
regime-gating multipliers on the universe level.

## Why this alpha persists

- **Cross-chain aggregation cost**: USDT lives on Tron, Ethereum, Solana,
  Avalanche, BSC, and others. USDC has its own chain footprint. Aggregating
  to a single PIT-clean total requires per-chain ingest pipelines that
  most teams treat as out of scope.
- **Issuer-level data parity**: Tether and Circle publish at different
  cadences and granularities. PIT-aligning their outputs is non-trivial.
- **Slow half-life**: ≥ 14d signals are unappealing to HFT; ≥ 30d signals
  are too fast for monthly-rebalanced funds. The window in between is
  exactly where alpha persists.

## Required primitives

- USDT supply (multi-chain) — **[T3] not ingested**.
- USDC supply (multi-chain) — **[T3] not ingested**.
- DAI / FRAX / others — optional, but USDT + USDC capture ~95% of total.
- Exchange-side stablecoin balance — **[T3] not ingested** (Glassnode /
  CryptoQuant).
- BTC market cap — derivable from `spot_close` × supply (supply is roughly
  static day-to-day).

The whole family is gated on M3.2 (Day 61–90) on-chain ingest module
`src/enhengclaw/quant_research/onchain.py`.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F61 | `stable_supply_growth_velocity` (TBD) | + universe-wide risk-on | 14–30 | T3 | not implemented |
| F62 | `stable_to_btc_marketcap_ratio` (TBD) | + (high ratio = dry powder) | 30+ | T3 | not implemented |
| F63 | `exchange_inflow_stable_vs_outflow_btc` (TBD) | + | 7–14 | T3 | not implemented |

§E.5 (stablecoin plumbing as macro regime detector) is the corresponding
frontier-direction entry.

## Expected sign and half-life

All three factors carry positive sign for forward returns. Half-life is
long: F62 is the slowest at 30+ days; F63 is the fastest at 7–14 days.

## Regime where strongest

Macro accumulation phases (post-drawdown re-allocation, ETF flow
build-up). F61 / F62 are weak during sustained risk-off because the M0
mechanism only matters when capital wants to deploy.

## Failure modes

- Issuance schedule events — Tether and Circle publish quarterly attestation
  reports that produce step-function visible-supply changes that are not
  flow events. Treat as a known noise source and exclude attestation days
  from the rolling window.
- Cross-chain bridging artefacts — a USDT bridge from Tron to Ethereum is
  not a net supply change but appears as one if either side is double-
  counted.
- Exchange address labelling drift — same risk as MF-14.

## Falsification path

- F61 IC vs BTC forward 14d return < 0.05 → reject (§E.5 frontier line).
- Per-factor rolling 60d residual IC < 0.02 for 90 days → retire.
- Family-level: if combined family residual IC after orthogonalisation to
  the v91 baseline drops below 0.03 → demote family to `watch`.

## Implementation status

- in `features.py`: none. Family is fully T3; gated on M3.2.
- admitted via `feature_admission.py`: none. Once F61-F63 columns land, an
  allowlist extension with a `stable_*` or `onchain_*` prefix and a
  corresponding provenance entry is required.
- present in any active manifest: none.
- report-carded: none.

Next action: M3.2 (Day 61–90) — build `src/enhengclaw/quant_research/
onchain.py` with cross-chain stablecoin supply aggregation and exchange-
balance series. F61 is the highest-ROI single deliverable; F62 / F63
follow.

## Cross-references

- Alpha ontology memo §B (MF-13 row), §D (Family MF-13 table), §E.5
  (stablecoin plumbing as macro regime detector).
- Strategy upgrade roadmap Phase 4 on-chain extension.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
