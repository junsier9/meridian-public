# M3.2 Sparse Boundary Falsification Card

`Run date: 2026-05-07`
`Parent: v5_rw_bridge_no_overlay_h10d`
`As-of: 2026-05-03`
`Status: failed hard-gate falsification; no cleared variants`

---

## Question

The 2026-05-04 Stage 0 result reopened M3.2 only as a sparse boundary
activation lane. This card asks whether the four Stage0-positive boundary
rules survive the next strict falsification step before any manifest A/B.

The answer is **no**. All four candidates remain research evidence only and
should not be promoted, optimized, or bridged into the canonical h10d parent.

---

## Artifacts

Primary hard-gate run:

- `scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_2_boundary_activation_falsification.py`
- `artifacts/quant_research/factor_reports/2026-05-07-m3-2-boundary-activation-falsification-iter1-all/m3_2_boundary_activation_falsification.json`
- `artifacts/quant_research/factor_reports/2026-05-07-m3-2-boundary-activation-falsification-iter1-all/run.stdout.log`
- `artifacts/quant_research/factor_reports/2026-05-07-m3-2-boundary-activation-falsification-iter1-all/run.stderr.log`

Operational note:

- A default 80-iteration monolithic run was started in
  `artifacts/quant_research/factor_reports/2026-05-07-m3-2-boundary-activation-falsification/`
  and stopped after `3292` CPU seconds with no JSON artifact written.
- That aborted run is not interpreted as evidence.
- The reported decision below uses the same falsification harness with
  `--iterations 1` only to expose deterministic hard gates and first random
  controls. Because every candidate fails at least one deterministic strict
  blocker, full random-tail completion is not required for rejection.

---

## Strict Gate Results

| variant | Stage 0 active delta | status | deterministic hard blockers | deterministic passes |
| --- | ---: | --- | --- | --- |
| `tron_impulse_short_high_beta_rs` | +0.009474 | `failed` | delay, liquidity bucket | symbol holdout, 2x cost |
| `tron_heat_short_high_rs` | +0.007439 | `failed` | delay, symbol holdout, liquidity bucket | 2x cost |
| `rebound_long_idio` | +0.006026 | `failed` | liquidity bucket | delay, symbol holdout, 2x cost |
| `sell_pressure_short_high_beta_rs` | +0.005579 | `failed` | liquidity bucket | delay, symbol holdout, 2x cost |

Random-control fields in the primary artifact are first-iteration diagnostics,
not promotion evidence. They are useful only as additional warning lights:
none of the four candidates cleared the random-control checks in that run.

---

## Failure Details

`tron_impulse_short_high_beta_rs`:

- delay retention collapses to `0.1333`
- liquidity-bucket minimum side-edge improvement is `-0.049043`
- symbol holdout and 2x cost stress pass, but they cannot rescue the delay and
  bucket failures

`tron_heat_short_high_rs`:

- delay retention collapses to `0.0542`
- symbol holdout minimum delta is negative (`-0.003097`)
- liquidity-bucket minimum side-edge improvement is `-0.011987`

`rebound_long_idio`:

- delay, symbol holdout, and 2x cost stress pass
- liquidity-bucket test has only one eligible bucket and its side-edge
  improvement is negative (`-0.005400`)
- the candidate is too bucket-fragile to proceed

`sell_pressure_short_high_beta_rs`:

- delay, symbol holdout, and 2x cost stress pass
- liquidity-bucket consistency fails with only one of two buckets positive and
  minimum side-edge improvement of `-0.001557`
- the apparent edge is not stable enough for a boundary rule

---

## Decision

All four Stage0-positive M3.2 sparse boundary variants are rejected for direct
manifest A/B.

The branch may be reopened only if a new exogenous ETF/on-chain sidecar changes
the activation definition and then passes the deterministic hard gates first.
Before any future 80-iteration random-tail run, the falsification executor
should be made resumable or exact-fast enough to write per-label partial
artifacts.

Do not reintroduce the older smooth MF13/MF14 M3.2 overlays. They remain closed.
