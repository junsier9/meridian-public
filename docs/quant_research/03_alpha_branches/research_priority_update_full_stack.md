# Research Priority Update After CoinGlass Full-Stack Reopening

`Snapshot date: 2026-05-09`
`Status: closure artifact; no alpha promotion`
`Scope: main roadmap position after CoinGlass data foundation and R-1 through R-8 reopening passes`

---

## Decision

The CoinGlass full-stack reopening cycle is complete for this roadmap pass.

This does not mean CoinGlass is useless. It means the first-pass data fill and
the pre-registered research reopenings have produced hard statuses:

- data foundation: ready as a catalog / sidecar layer
- h10d promotion: not allowed
- manifest A/B: not allowed from any CoinGlass reopening lane
- live use: not allowed
- next mainline: move to a new pre-registered mechanism or native venue-trust
  unlock, not another CoinGlass confirmation filter

The main roadmap is now past the `Day 3+ / research expansion block` in
`coinglass_full_stack_data_research_roadmap.md`. The current state is:

```text
CoinGlass data foundation complete
-> data-sensitive reopening lanes tested
-> no strict survivor
-> CoinGlass reopening cycle closed
-> next roadmap step is non-CoinGlass mechanism design or native venue trust
```

---

## Canonical References

- Catalog:
  [`coinglass_full_stack_foundation_sync.md`](../01_data_foundation/coinglass_full_stack_foundation_sync.md)
- CoinGlass roadmap:
  [`coinglass_full_stack_data_research_roadmap.md`](../01_data_foundation/coinglass_full_stack_data_research_roadmap.md)
- Main roadmap index:
  [`next_stage_alpha_map.md`](../00_roadmap_state/next_stage_alpha_map.md)
- Parallel 1h lane:
  [`parallel_1h_alpha_mining_roadmap.md`](../04_parallel_1h/parallel_1h_alpha_mining_roadmap.md)
- Data sponsorship / external data case:
  [`data_sponsorship_investment_plan_2026_05.md`](../01_data_foundation/data_sponsorship_investment_plan_2026_05.md)

---

## Roadmap Position

The main roadmap previously said to execute the CoinGlass data foundation,
re-baseline the h10d parent, and reopen only data-sensitive lanes:

- true `cross_sectional_intraday_1h`
- M3.2 sparse boundary activation
- SP-K canonical-parent short replacement
- MF-05 sub-day venue stress
- MF-01 orderbook / inventory
- M3.1 options-regime
- MF-07 participant stack only after the above

That queue has now been executed far enough to close the current CoinGlass
cycle. The roadmap is no longer at "fill CoinGlass data" or "try the obvious
CoinGlass sidecars." It is at the next decision point:

1. run native venue-concordance work if the goal is data trust; or
2. pre-register a new mechanical-flow candidate if the goal is alpha search.

Do not continue by tuning thresholds on M3.2, R-8, MF-07, or generic SP-K
non-kline confirmations.

---

## Closure Ledger

| lane | current status | decisive reason | allowed next action |
| --- | --- | --- | --- |
| `CG-0` capability matrix | `complete_diagnostic` | endpoint surface and schema smoke exist; not alpha evidence | use catalog before any future CoinGlass lane |
| `CG-1` spot OHLCV | `quarantined` | coverage and provider concordance remain separate; CoinGlass OHLC is not canonical price truth | use Binance/canonical price path; keep CoinGlass spot as sidecar until concordance passes |
| `CG-2` futures OI provenance | `sidecar_ready` | native USD OI preferred; derived OI requires provenance | use only with explicit native/derived flags |
| `CG-3` microstructure / participant panels | `sidecar_ready` | liquidation, orderbook, taker, and participant panels exist but do not imply alpha | use only inside pre-registered mechanism tests |
| `CG-4/CG-5` ETF and on-chain sidecars | `sidecar_ready_with_quarantine` | ETF/whale fields are PIT-lagged; exchange transfers remain latest-event / semantic-quarantine | no directionality from exchange transfers without new semantic proof |
| `CG-6` options aggregate sidecar | `quarantined_market_gate_only` | option volume shock is market-level; OI/max-pain are not full PIT surface topology | keep as mechanism evidence; no parent overlay |
| `R-1` parent rebaseline | `fail_closed_parent` | original parent still fails strict symbol/bucket gates | do not promote original parent |
| `R-1a` `top_liquidity_ex_trx` | `quarantined_fail_closed` | full strict falsification failed time/label shuffle, delay, cost, symbol holdout, and liquidity buckets | do not optimize without a new mechanism reason |
| `R-2` true 1h feasibility | `zero_admitted_alpha` | first 1h battery and fake-liquidity repair attempts fail or remain quarantined | only new exogenous sidecar or new pre-registered 1h mechanism |
| `R-3/R-3b` M3.2 boundary + ETF/on-chain | `closed_comparator_only` | direct boundary and CoinGlass ETF/on-chain confirmations have zero strict survivors | no M3.2 A/B without materially new activation definition |
| `R-4` SP-K non-kline confirmation | `closed_current_forms` | funding/OI, liquidation, taker/orderbook, participant, and stablecoin filters do not beat raw SP-K | reopen only with a narrower pre-registered landing shape |
| `R-5` MF-05 venue stress | `blocked_by_data_trust` | venue sidecar exists, but OKX/Bybit/Coinbase lack native local concordance | native venue concordance is the next data-side unlock |
| `R-6` MF-01 orderbook / inventory | `mechanism_evidence_only` | best confirmation forms are too sparse and do not transmit parent edge | revisit only with breadth/cost/holdout pre-registration |
| `R-7/R-7b` MF-07 participant stack | `closed_current_forms` | daily, sub-day pivot, and ETF/whale transition forms have zero Stage 0 survivors | do not rerun current participant-stack variants |
| `R-8/R-8b` M3.1 options-regime | `quarantined_mechanism_evidence` | option volume shock passes several checks but fails liquidity-bucket consistency | no M3.1 exposure gate; wait for richer options surface or new design |
| vendor indicators | `diagnostic_only` | opaque vendor calculations are not PIT-recomputed locally | dashboard / slicing only |

---

## Main Roadmap State

The main roadmap is now here:

```text
2026-05-03: canonical parent corrected to v5_rw_bridge_no_overlay_h10d
2026-05-04: M3.3 exhausted; M3.2 boundary became next falsification queue
2026-05-04 to 2026-05-07: CoinGlass full-stack data foundation executed
2026-05-07 to 2026-05-09: data-sensitive reopening lanes closed or blocked
2026-05-09: CoinGlass reopening cycle frozen by this artifact
```

The next roadmap step should therefore be one of two paths.

### Path A: Data-Trust Unlock

Run native venue concordance for the venue sidecar:

- Bybit native 1h sample beyond BTC/ETH/XRP
- OKX native 1h close and volume concordance
- Coinbase native 1h close and volume concordance
- provider timestamp, missingness, and symbol mapping audit

This path aims to unblock MF-05 / venue-concentration research. It is data work,
not alpha work.

### Path B: New Pre-Registered Mechanism

Open a fresh 1h mechanism only if it is pre-registered before coding. The
preferred current-data shape is:

```text
depth_velocity_collapse_exit_stage0_1h
```

It must be explicitly different from the already failed
`post_pump_bid_replenishment_failure_stage0_1h`. The thesis should be delayed
entry after a pump/trap only when bid-depth velocity collapses together with
taker/price failure, not a generic bid-replenishment filter.

Required gates:

- primary direction
- time / label shuffle
- symbol holdout
- liquidity-bucket consistency
- +1h / +6h / +24h delay robustness
- cost, funding, capacity, and adverse-tail stress

No h10d bridge is allowed unless an independent 1h Stage 0 survivor exists.

---

## Stop Rules

Do not spend the next roadmap slot on:

- another M3.2 ETF/on-chain confirmation filter
- another R-8 option-volume threshold variant
- another MF-07 participant-stack transition using the same fields
- generic funding/OI crowding
- broad smooth overlays
- CoinGlass spot-price promotion before concordance
- exchange-transfer directionality before semantic proof

The only acceptable reopening trigger is a materially new information set or a
materially new landing shape that is pre-registered before the evaluator is
written.

---

## Bottom Line

The project has moved from:

```text
Can CoinGlass fill the missing data surface?
```

to:

```text
Which non-price mechanism or native venue-trust unlock can survive strict
falsification?
```

For the main roadmap, CoinGlass is now a reusable catalog and sidecar source,
not the active alpha-search frontier.
