# M3.2 Boundary Activation Stage 0

`Run date: 2026-05-04`
`Parent: v5_rw_bridge_no_overlay_h10d`
`As-of: 2026-05-03`
`Status: Stage0-positive for four sparse boundary variants; follow-up strict hard-gate failed on 2026-05-07`

---

## Question

The previous M3.2 canonical-parent check showed that old MF13/MF14 smooth
score perturbations do not transmit through `v5_rw_bridge_no_overlay_h10d`.
This test asks a narrower question:

> Can M3.2 on-chain / stablecoin states work as sparse, discrete long/short
> boundary activation rules rather than as smooth global score overlays?

The answer is **yes for selected sparse boundary rules**, but only at Stage 0.
The result opens a falsification lane; it does not justify a manifest A/B or
production promotion yet.

---

## Method

Evaluator:

- `scripts/quant_research/alpha_stage0_quarantine/evaluate_m3_2_boundary_activation_stage0.py`
- unit tests: `tests/test_quant_m3_2_boundary_activation_stage0.py`
- output artifact:
  `artifacts/quant_research/factor_reports/2026-05-03-m3-2-boundary-activation-stage0/m3_2_boundary_activation_stage0.json`

The evaluator rebuilds the canonical parent risk frame via the same feature
artifact path used by the current SP-K / v5 diagnostics, then merges all
`m3_2_*` state columns from:

- `artifacts/quant_research/onchain/m3_2_feature_panel_1d.csv`

Merge key:

- parent `decision_date` / `date_utc`
- M3.2 panel `decision_date_utc`

This matters because the older canonical-parent M3.2 helper only merged a
subset of landing-shape columns. For this test, the native state columns are
fully available in the ready window.

Boundary rule contract:

- work only when `m3_2_panel_ready = true`
- activate only when the relevant state exceeds `0.75`
- modify only the parent long or short boundary slots
- keep the canonical parent unchanged outside active timestamps
- compare candidate versus parent on active-window, ready-window, and full
  sample long-short mean

Stage0-positive rule:

- active timestamp count `>= 10`
- active-window long-short mean improvement `> 0.0005`
- active-window changed timestamp fraction `>= 5%` on the modified side

---

## Coverage

The current M3.2 panel has `113` ready timestamps out of `1093` parent
timestamps (`10.34%`).

Ready-window state activity:

| state | ready > 0.75 count | ready q75 | ready q90 |
| --- | ---: | ---: | ---: |
| `m3_2_stable_supply_impulse_state` | 29 | 0.7784 | 0.9624 |
| `m3_2_stable_dry_powder_state` | 11 | 0.4176 | 0.7124 |
| `m3_2_reflexive_rebound_state` | 12 | 0.4060 | 0.7535 |
| `m3_2_btc_sell_pressure_state` | 16 | 0.4225 | 0.8608 |
| `m3_2_tron_flow_impulse_state` | 22 | 0.6910 | 0.9769 |
| `m3_2_tron_speculative_heat_state` | 23 | 0.7131 | 0.8512 |

---

## Results

| variant | side/action | active timestamps | changed fraction | active long-short delta | verdict |
| --- | --- | ---: | ---: | ---: | --- |
| `tron_impulse_short_high_beta_rs` | short `replace_high` | 22 | 90.91% | +0.009474 | `stage0_positive` |
| `tron_heat_short_high_rs` | short `replace_high` | 23 | 86.96% | +0.007439 | `stage0_positive` |
| `rebound_long_idio` | long `replace_high` | 12 | 91.67% | +0.006026 | `stage0_positive` |
| `sell_pressure_short_high_beta_rs` | short `replace_high` | 16 | 81.25% | +0.005579 | `stage0_positive` |
| `dry_powder_long_idio_rs` | long `replace_high` | 11 | 100.00% | -0.002850 | `stage0_negative` |
| `stable_supply_long_high_beta_rs` | long `replace_high` | 29 | 62.07% | -0.004061 | `stage0_negative` |
| `stable_supply_short_veto_high_beta` | short `veto_high` | 29 | 100.00% | -0.013892 | `stage0_negative` |
| `sell_pressure_long_veto_high_beta` | long `veto_high` | 16 | 100.00% | -0.014958 | `stage0_negative` |

Interpretation:

- The old smooth MF13/MF14 shapes remain closed.
- The positive result is concentrated in sparse, high-state boundary activation.
- The best current short-side rule is `tron_impulse_short_high_beta_rs`.
- The best current long-side rule is `rebound_long_idio`.
- Stable supply impulse is harmful in both tested landing shapes.
- BTC sell-pressure works as short replacement, not as long veto.

---

## Decision

M3.2 should be re-opened, but only as a falsification lane for the four
Stage0-positive variants:

1. `tron_impulse_short_high_beta_rs`
2. `tron_heat_short_high_rs`
3. `rebound_long_idio`
4. `sell_pressure_short_high_beta_rs`

Rejected variants should not be carried forward:

- `dry_powder_long_idio_rs`
- `stable_supply_long_high_beta_rs`
- `stable_supply_short_veto_high_beta`
- `sell_pressure_long_veto_high_beta`

Do not open a production manifest A/B yet. The active samples are sparse, and
the current positive evidence is still a local Stage 0 boundary diagnostic.

---

## Next Falsification

The next executable slice should run a strict Stage 0.5 falsification harness
for the four positive variants:

- `+1d` delayed activation
- active-state time shuffle
- active-state label shuffle
- active-state symbol shuffle
- symbol holdout
- liquidity-bucket consistency
- 2x cost stress
- best-variant selection lock before any manifest A/B

Promotion can only be considered if at least one variant keeps positive
active-window edge after delay / shuffle controls and does not concentrate in a
single symbol or liquidity bucket.

2026-05-07 follow-up:

- strict hard-gate card:
  `docs/quant_research/03_alpha_branches/m3_2_full_stack_boundary_falsification.md`
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-07-m3-2-boundary-activation-falsification-iter1-all/m3_2_boundary_activation_falsification.json`
- result: all four Stage0-positive variants failed; no manifest A/B is allowed
  from the current direct boundary definitions.
