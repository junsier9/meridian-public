# M3.3 + MF-01 Confirmation Stage 0

`Snapshot date: 2026-05-04`
`Status: diagnostic complete; mechanism useful but too sparse for manifest A/B`

## Research Question

M3.3 threshold-v2 did not solve robustness: the best local event-state rule,
`v2_q2_noise0`, still had weak cross-bucket evidence and a recurring holdout
problem. The next plausible branch was not more event-threshold tuning, but
mechanical confirmation:

> If a high-quality M3.3 event-state short candidate is also confirmed by MF-01
> orderbook fragility, does it become a cleaner short-boundary replacement?

## Implementation

New diagnostic script:

[`evaluate_m3_3_mf01_confirmation_stage0.py`](../../../scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_3_mf01_confirmation_stage0.py:1)

Output report:

`artifacts/quant_research/factor_reports/2026-05-03-m3-3-mf01-confirmation-stage0/m3_3_mf01_confirmation_stage0.json`

2026-05-07 R-6 rerun:

- `docs/quant_research/03_alpha_branches/mf01_orderbook_inventory_r6_retest.md`
- `artifacts/quant_research/factor_reports/2026-05-07-mf01-orderbook-inventory-stage0/m3_3_mf01_confirmation_stage0.json`

The script starts from canonical `v5_rw_bridge_no_overlay_h10d` parent score,
uses the M3.3 `q2/noise0/no-hype` event-state condition, and optionally requires
MF-01 confirmation from:

- `boundary_fragile_orderbook_flag`
- `pump_bid_replenishment_failure_flag`
- `mf01_short_boundary_combo_score < 0`

## Result

| variant | Stage0 pass | changed timestamps | entered rows | entered h10d mean | edge vs parent |
| --- | --- | ---: | ---: | ---: | ---: |
| `q2_event_only_max3` | yes | `19.95%` | 237 | `-1.77%` | `+0.052%` |
| `q2_event_only_one` | no | `19.95%` | 218 | `-1.72%` | `+0.030%` |
| `q2_mf01_any_flag_one` | no | `1.65%` | 18 | `-2.59%` | `+0.002%` |
| `q2_mf01_boundary_flag_one` | no | `1.65%` | 18 | `-2.59%` | `+0.002%` |
| `q2_mf01_combo_negative_one` | no | `1.65%` | 18 | `-2.59%` | `+0.002%` |

The three MF-01 confirmation modes collapse to the same realized set in this
panel: all confirmed entered rows are `boundary_fragile_orderbook` rows, none
are `pump_bid_replenishment_failure` rows.

## What Improved

MF-01 confirmation improves the quality of the rows it allows:

- entered h10d mean improves from `-1.77%` to `-2.59%`
- entered-minus-exited remains negative at about `-0.28%`
- entered rows split across both available liquidity buckets:
  - `mid_liquidity`: `-2.34%`
  - `top_liquidity`: `-2.85%`

This is useful mechanism evidence: orderbook fragility is a real confirmation
filter for M3.3 event-state shorts.

## What Failed

The confirmation is too sparse for a parent-strategy candidate:

- changed timestamps collapse from `19.95%` to `1.65%`
- entered rows collapse from `237` to `18`
- parent-level mean edge falls from `+0.052%` to effectively zero (`+0.002%`)
- the confirmed sample covers only five subjects

So MF-01 solves the *row-quality* problem but not the *portfolio transmission*
problem.

## Decision

Do **not** open a formal manifest A/B for M3.3 + MF-01 confirmation.

Keep this as mechanism evidence:

- M3.3 alone has enough breadth but weak robustness.
- MF-01 confirmation has better row quality but too little breadth.
- The next viable route needs either broader mechanical confirmation, or a new
  event-state definition that is already robust before MF-01 is applied.

2026-05-07 update: this conclusion still holds. The fresh R-6 run reproduced
the same structure: event-only `q2_event_only_max3` is the only Stage0-pass
variant, while MF-01 confirmation remains higher quality but too sparse for
manifest A/B.
