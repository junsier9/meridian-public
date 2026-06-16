# MF-14: On-chain reflexivity

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T2 (exchange flow); T3 (long-term holder cohorts)`

---

## Economic story

On-chain settlement is **real**: it is not an exchange's bookkeeping
entry, it is a final-settlement state transition with cryptographic proof.
Several chain-native series carry information that *precedes* what shows
up on the CEX tape:

1. **Exchange net flow**: BTC moving onto exchanges signals impending sell
   intent; BTC moving off signals accumulation. The unconditional flow is
   noisy; the *residual* after explaining flow with concurrent return
   captures the leading-indicator portion.
2. **Long-term holder (LTH) supply change**: an aggregate of UTXOs older
   than 155 days. When LTH supply rises (older holders accumulating), it is
   a high-conviction signal because LTHs have demonstrated holding behaviour
   and are not noise traders.
3. **Spent output profit ratio (SOPR)** and similar realised-loss indicators
   — when SOPR < 1 sustained, holders are realising losses; the population
   that is willing to do so is signalling capitulation.

The mechanism is reflexive in the same sense as MF-06: chain flow → CEX
price → renewed chain flow. The first arrow is ahead of the second by
1–3 days for whale-scale transactions and by weeks for LTH cohort changes.

## Why this alpha persists

- **Data engineering cost**: building a clean, PIT-aligned, label-stable
  on-chain pipeline from raw blocks (or via Glassnode / CryptoQuant /
  Coin Metrics) is a multi-month engineering project. Most teams either
  use the dashboards directly (and inherit the dashboard's lag) or skip
  on-chain entirely.
- **Wallet labelling drift**: addresses identified as "exchange wallet"
  today may not be the same actor 12 months from now. Re-validation is
  ongoing.
- **Tail / wash trade contamination**: large transactions that look like
  "whale flow" are sometimes internal exchange rebalancing or
  cold-storage reorganisation. Filtering these requires per-transaction
  heuristics.

## Required primitives

- Exchange net flow (BTC, ETH, top 20) — **[T2] not ingested** (Glassnode /
  CryptoQuant API).
- LTH supply (BTC, ETH) — **[T3] not ingested** (Glassnode definition).
- SOPR — **[T3] not ingested**.
- Whale-tier transaction count / size — **[T3] not ingested**.

All gated on M3.2 (Day 61–90) `src/enhengclaw/quant_research/onchain.py`.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F64 | `exchange_net_flow_residual` (TBD) | − (residual inflow = sell pressure) | 3–7 | T2 | not implemented |
| F65 | `lth_supply_change` (TBD) | + (LTH increase = high-conviction confidence) | 30+ | T3 | not implemented |

§E.4 (whale → retail cascade) and §E.14 (KOL / on-chain whale lead-lag)
are the corresponding frontier directions.

## Expected sign and half-life

F64 is fast (3–7 days) and negative-sign on residual inflow (more inflow
than the concurrent return predicts → forthcoming sell pressure). F65 is
slow (30+ days) and positive-sign (LTH accumulation → multi-week strength).

## Regime where strongest

F64: event-driven windows (post-shock, post-cascade) where exchange flow
deviates most from the steady-state pattern. F65: sustained accumulation
phases (typical of late-bear / early-bull regimes).

## Failure modes

- Exchange-address labelling drift, see "why persists" above.
- API quality variance — Glassnode and CryptoQuant disagree on definitions
  of "exchange" and on labels for borderline addresses. Cross-source
  validation is required.
- Definition boundary drift for LTH — if the 155-day threshold is changed
  upstream, F65 needs re-baselining.
- Whale-cohort change events (e.g. major OTC desk re-organisation) shift
  the whale-flow distribution structurally.

## Falsification path

- F64 rolling 60d residual IC < 0.02 for 90 days → retire.
- F65 rolling 90d residual IC < 0.02 for 180 days → retire (longer window
  required because of the slower half-life).
- §E.4 frontier line: whale tx flow lag-2 IC < 0.04 → reject the
  whale-led-by-2-days hypothesis.

## Implementation status

- in `features.py`: none. Family is fully T2/T3; gated on M3.2.
- admitted via `feature_admission.py`: none. Once F64 / F65 columns land,
  an allowlist extension with `exchange_flow_*` / `lth_*` / `sopr_*`
  prefix is required, with PIT-clean replay audit (the on-chain ingest
  must be timestamp-validated against on-chain block times, not provider
  publish times).
- present in any active manifest: none.
- report-carded: none.

Next action: M3.2 (Day 61–90) — build `onchain.py` with
- a labelled-address registry,
- per-day exchange net-flow series for BTC and ETH,
- LTH supply series for BTC,
- a PIT-clean replay audit suite.

F64 is the highest-ROI single deliverable; F65 follows once the LTH
definition is finalised.

## Cross-references

- Alpha ontology memo §B (MF-14 row), §D (Family MF-14 table), §E.4
  (on-chain reflexivity), §E.14 (KOL / on-chain whale lead-lag).
- Strategy upgrade roadmap Phase 4 on-chain extension.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
