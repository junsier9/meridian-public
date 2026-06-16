# MF-01 Orderbook / Inventory R-6 Retest

`Run date: 2026-05-07`
`Parent: v5_rw_bridge_no_overlay_h10d`
`As-of: 2026-05-03`
`Status: MF-01 confirmation rejected for manifest A/B; mechanism evidence only`

---

## Question

R-6 asks whether MF-01 orderbook / inventory state can repair a sparse but
mechanistically attractive short-boundary problem. The specific retest checks:

> If high-quality M3.3 event-state short candidates are also confirmed by
> MF-01 orderbook fragility, do they become a cleaner current-parent boundary
> replacement?

The answer is **no for this landing shape**. MF-01 confirmation improves the
quality of the few rows it allows, but it is too sparse to transmit into the
canonical parent.

---

## Artifacts

- evaluator implementation:
  `scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_3_mf01_confirmation_stage0.py`
- unit tests:
  `tests/test_quant_m3_3_mf01_confirmation_stage0.py`
- primary fresh report:
  `artifacts/quant_research/factor_reports/2026-05-07-mf01-orderbook-inventory-stage0/m3_3_mf01_confirmation_stage0.json`
- logs:
  `artifacts/quant_research/factor_reports/2026-05-07-mf01-orderbook-inventory-stage0/run.stdout.log`
  and
  `artifacts/quant_research/factor_reports/2026-05-07-mf01-orderbook-inventory-stage0/run.stderr.log`

Related prior context:

- `docs/quant_research/03_alpha_branches/m3_3_mf01_confirmation_stage0.md`
- `docs/quant_research/03_alpha_branches/mf01_canonical_parent_alpha_validation.md`

---

## Results

| variant | Stage0 pass | changed timestamps | entered rows | entered subjects | entered h10d mean | entered-minus-exited h10d | edge vs parent |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `q2_event_only_max3` | yes | 19.95% | 237 | 14 | -1.77% | -0.72% | +0.052% |
| `q2_event_only_one` | no | 19.95% | 218 | 14 | -1.72% | -0.45% | +0.030% |
| `q2_mf01_any_flag_one` | no | 1.65% | 18 | 5 | -2.59% | -0.28% | +0.002% |
| `q2_mf01_boundary_flag_one` | no | 1.65% | 18 | 5 | -2.59% | -0.28% | +0.002% |
| `q2_mf01_combo_negative_one` | no | 1.65% | 18 | 5 | -2.59% | -0.28% | +0.002% |

The three MF-01 confirmation variants collapse to the same realized set in
this panel:

- entered row count: `18`
- entered subject count: `5`
- confirmed entered rows are all `boundary_fragile_orderbook` rows
- `pump_bid_replenishment_failure` contributes no entered rows

---

## Interpretation

MF-01 is real as a row-quality filter:

- confirmed entered rows have a strong negative h10d mean (`-2.59%`);
- confirmed rows are directionally better than the rows they replace;
- both mid-liquidity and top-liquidity confirmed buckets are negative.

MF-01 fails as a parent-strategy candidate here:

- activity collapses from `19.95%` changed timestamps for event-only to `1.65%`
  for MF-01-confirmed variants;
- entered rows collapse from `237` to `18`;
- parent-level mean edge falls from `+0.052%` to effectively zero (`+0.002%`);
- subject coverage is only `5`, leaving symbol-holdout fragility unresolved;
- prior canonical-parent MF-01 validation remains `research_only / no_go`
  because strict falsification failed time shuffle, label shuffle, cost stress,
  symbol holdout, and liquidity-bucket consistency.

---

## Decision

Do not open a manifest A/B for R-6 MF-01 orderbook / inventory from this
landing shape.

Keep MF-01 as mechanism evidence and a possible future component, but only if a
new pre-registered variant directly addresses breadth, cost, symbol holdout,
and liquidity-bucket consistency. Do not spend the next roadmap slot on another
broad bottom-boundary MF-01 replacement.

The roadmap should move to R-7 participant disagreement 2.0 or R-8 options
regime, with R-7 only if the richer participant stack has enough non-overlap
with the already failed SP-K non-kline filters.
