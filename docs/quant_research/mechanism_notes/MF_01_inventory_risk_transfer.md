# MF-01: Inventory & risk transfer (microstructure)

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1`

---

## Economic story

Market makers and proprietary liquidity providers operate within tight
inventory limits. When taker order flow lifts the offer (or hits the bid)
beyond their absorption budget, they re-skew quotes against the flow and
hedge in adjacent venues or instruments. The result is a *mechanical* drift
in the public price after the inventory shock — the MM is *forced* to bring
quote balance back, not because of any belief revision but because of risk
limits.

The same mechanism shows up in OI dynamics: a large futures OI build with
crowded same-side funding implies leveraged longs (or shorts) that the
clearing system holds against margin. When margin compresses, those positions
unwind on a forced timeline and the unwind footprint shows up in OI delta,
basis dislocations, and quote-volume bursts.

## Why this alpha persists

Inventory pressure is **mechanical**, not belief-driven. There is no
information event, no narrative, no rerating. The MM has to rebalance in N
hours regardless of view. Capital constraints and risk-limit infrastructure
are slow-moving; they do not get arbitraged away by other participants who
face the same constraints.

## Required primitives

- `open_interest`, `oi_change_5` — Binance derivatives quality module.
- `funding_rate` — Binance derivatives quality module.
- `quote_volume_expansion` — derived from `spot_quote_volume` rolling-20 mean.
- `coinglass_taker_imb_intraday_dispersion_24h` — Coinglass taker imbalance.
- `basis_zscore_20`, `realized_volatility_20` — derived in `features.py`.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F01 | `oi_shock_residual_5d` (TBD) | cond: + if funding > 0 else − | 4–7 | T1 | not implemented |
| F02 | `oi_unwind_velocity` (TBD) | − | 5–10 | T1 | not implemented |
| F03 | `funding_oi_compression` (TBD) | − | 3–5 | T1 | not implemented (overlaps with v91 `quality_funding_oi`) |
| F04 | `basis_volatility_compression` (TBD) | − | 3–6 | T1 | not implemented |
| F05 | `quote_taker_concordance` (TBD) | cond | 2–4 | T1 | not implemented |

## Expected sign and half-life

Conditional on funding sign and OI direction. Most factors mean-revert in
3–10 days post-shock; the unwind-velocity factor has the slowest decay
(5–10d).

## Regime where strongest

Trending vol-up or crowded-long phases (where carry pain is structurally
asymmetric); also post-cascade windows where the unwind has already begun.

## Failure modes

- OI data outages or contract roll (exchange-side maintenance).
- Fund rotation noise that masquerades as unwind.
- Sub-day flow signals folded into daily bars losing sign information.

## Falsification path

- Rolling 60d residual IC of any admitted factor in this family stays below
  0.02 for 90 consecutive days → demote family to `watch`.
- Per-quarter rank IC sign-flips on ≥ 3 regime windows within 12 months →
  retire family.

## Implementation status

- in `features.py`: none of F01-F05 yet (W1.1 prioritised MF-04 / MF-06 /
  MF-10 instead).
- admitted via `feature_admission.py`: none.
- present in any active manifest: none.
- report-carded: only the v91 baseline factors that *partially* overlap MF-01
  (`coinglass_taker_imb_intraday_dispersion_24h`, `quality_funding_oi`,
  `oi_change_5`) — see
  `artifacts/quant_research/factor_reports/2026-04-29/v91_taker_imb_dispersion.{json,txt}`
  and `v91_quality_funding_oi.{json,txt}`.

Next action: implement F01 (oi_shock_residual via AR(1) residual on
`oi_change_5`) as the first dedicated MF-01 factor; report-card it; if G6
passes against v91 baseline, fold into a v_alpha_v2 manifest expansion.

## Cross-references

- Alpha ontology memo §B (MF-01 row), §D (Family MF-01 / Inventory & risk
  transfer table).
- Strategy upgrade roadmap: `docs/quant_research/00_roadmap_state/strategy_upgrade_roadmap.md`.
- Threshold provenance log: `config/quant_research/threshold_provenance.md`.

---

## Change log

- `2026-04-29` — initial note created from §B / §D content (W1.5).
