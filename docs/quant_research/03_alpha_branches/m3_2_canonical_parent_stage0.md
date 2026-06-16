# M3.2 Canonical-Parent Stage 0

`Snapshot date: 2026-05-04`
`Parent: v5_rw_bridge_no_overlay_h10d`
`Artifact: artifacts/quant_research/factor_reports/2026-05-03-m3-2-canonical-parent-stage0/m3_2_canonical_parent_stage0.json`

## Question

Do the existing `MF-13 / MF-14` M3.2 gates still create measurable strategy lift
when re-anchored to the current canonical h10d parent, instead of the older
`v6_h10d` baseline used by the first M3.2 scripts?

## Method

The Stage 0 script merges the daily M3.2 on-chain panel into the canonical
`v5_rw_bridge_no_overlay_h10d` risk frame by `date_utc`, then replays the old
MF13/MF14 score perturbations on top of the v5 raw score:

- `mf14_sell_beta_v5_parent`
- `mf14_sell_mid_short_v5_parent`
- `mf14_rebound_idio_v5_parent`
- `mf13_tron_impulse_def_beta_v5_parent`

It compares top/bottom-3 long-short returns and boundary turnover versus the
canonical parent. Promotion to manifest A/B requires at least `+5 bps` ready
window long-short mean improvement plus non-trivial boundary transmission.

## Result

Coverage is still narrow at the canonical-parent horizon:

- frame rows: `18,576`
- timestamps: `1,093`
- M3.2-ready timestamps: `113`

| variant | ready long-short delta | long boundary changed | short boundary changed | Stage 0 verdict |
| --- | ---: | ---: | ---: | --- |
| `mf13_tron_impulse_def_beta_v5_parent` | `0.0000` | `0.00%` | `0.00%` | `stage0_at_par` |
| `mf14_rebound_idio_v5_parent` | `0.0000` | `0.00%` | `0.00%` | `stage0_at_par` |
| `mf14_sell_beta_v5_parent` | `+0.000445` | `0.00%` | `0.18%` | `stage0_at_par` |
| `mf14_sell_mid_short_v5_parent` | `0.0000` | `0.00%` | `0.00%` | `stage0_at_par` |

## Decision

Do not open a canonical manifest A/B for these M3.2 score perturbations.

`MF14_sell_beta` is directionally the best current slice, but it misses the
`+5 bps` Stage 0 threshold and changes only about `0.18%` of short boundaries.
That is too little transmission for a robust mother-strategy candidate. The
other three variants are exact at-par against the canonical parent.

## Next

M3.2 should stay active as a data lane, but the next alpha attempt should not
be another tiny smooth score perturbation. Re-open only with one of:

- a discrete boundary replacement rule using high-conviction on-chain stress
  states;
- a broader ready-window history after more M3.2 accumulation;
- an interaction with a separate mechanical event source that materially
  increases boundary change rate.
