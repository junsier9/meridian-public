# MF-07 Participant Stack R-7 Gate

`Run date: 2026-05-07`
`Parent boundary: v5_rw_bridge_no_overlay_h10d is not modified`
`Status: rejected current forms; PIT sidecars filled but not integrated`

---

## Question

R-7 asks whether MF-07 participant disagreement can be reopened with a richer
stack:

- top-trader long/short;
- global account long/short;
- taker buy/sell;
- CEX transfer direction;
- whale transfer direction;
- BTC/ETH ETF flow regime.

This gate asks whether that stack is ready for another alpha rerun. The answer
is **no**.

Two current participant forms were rerun and still have no admissible survivor.
The richer stack now has PIT ETF/on-chain sidecars, but those sidecars are not
yet integrated into the daily feature panel or a pre-registered transition.

---

## Artifacts

- R-7 gate:
  `scripts/quant_research/audit_mf07_participant_stack_r7_gate.py`
- PIT ETF/on-chain sync:
  `scripts/quant_research/sync_coinglass_etf_onchain_participant_sidecars.py`
- unit tests:
  `tests/test_quant_mf07_participant_stack_r7_gate.py`
- PIT sidecar tests:
  `tests/test_quant_coinglass_etf_onchain_participant_sidecars.py`
- PIT sidecar note:
  `docs/quant_research/01_data_foundation/coinglass_etf_onchain_participant_sidecars.md`
- primary gate report:
  `artifacts/quant_research/factor_reports/2026-05-07-r7-mf07-participant-stack-gate/mf07_participant_stack_r7_gate.json`
- PIT sidecar sync report:
  `artifacts/quant_research/factor_reports/2026-05-07-coinglass-etf-onchain-participant-sidecars/coinglass_etf_onchain_participant_sidecars.json`
- fresh daily participant-disagreement report:
  `artifacts/quant_research/factor_reports/2026-05-07-r7-mf07-participant-disagreement-spk-stage0/mf07_participant_disagreement_spk_stage0.json`
- fresh sub-day participant-pivot report:
  `artifacts/quant_research/factor_reports/2026-05-07-r7-mf07-subday-participant-pivot-stage0/mf07_subday_participant_pivot_stage0.json`

---

## Fresh Rerun Summary

The daily top/global SP-K-conditioned battery has:

- kept variants: `0`
- best non-admitted variant:
  `spk_veto_high_tt_velocity`
- edge versus raw SP-K: `+0.000488`
- changed timestamp fraction: `0.91%`
- reason not admitted: below the `+0.0005` edge bar and too sparse

The sub-day participant-pivot battery has:

- kept variants: `0`
- best non-admitted variant:
  `spk_veto_retail_outpaces_top`
- edge versus raw SP-K: `+0.000144`
- changed timestamp fraction: `3.02%`
- reason not admitted: weak and too sparse

The confirmation forms still transmit in the wrong direction: they change many
SP-K timestamps but worsen the raw SP-K short basket.

---

## Stack Availability

Feature artifact:

`artifacts/quant_research/features/2026-05-03-cross-sectional-daily-1d-features-v1/features.csv.gz`

Panel rows: `72,006`

Subjects: `99`

| stack slice | present columns | min coverage | status |
| --- | ---: | ---: | --- |
| top/global position | `4 / 4` | `25.34%` | present but current forms rejected |
| taker flow | `4 / 4` | `76.77%` | present but not enough alone for R-7 2.0 |
| CEX transfer partial stablecoin context | `3 / 3` | `17.36%` | too sparse / not native CoinGlass transfer panel |
| whale transfer partial stablecoin context | `3 / 3` | `17.36%` | too sparse / not native CoinGlass whale panel |
| ETF flow regime | `0 / 6` | `0.00%` | sidecar exists, not integrated |

Local sidecar status:

- `coinglass_extended` exists with `93` symbol directories.
- `artifacts/quant_research/coinglass/etf_daily_state_1d.csv.gz` exists with
  `598` rows, `52` columns, decision dates `2024-01-12` to `2026-05-07`.
- `artifacts/quant_research/coinglass/exchange_transfers_1d.csv.gz` exists
  with `31` rows, `30` columns, decision dates `2026-04-08` to `2026-05-08`.
- `artifacts/quant_research/coinglass/whale_transfers_1d.csv.gz` exists with
  `181` rows, `29` columns, decision dates `2025-11-09` to `2026-05-08`.
- `artifacts/quant_research/coinglass/participant_context_1d.csv.gz` exists
  with `657` rows, decision dates `2024-01-12` to `2026-05-08`.

CoinGlass smoke says ETF, on-chain, and participant/flow endpoint families are
available. The new sync run converts that capability into local PIT sidecars,
but it is still not alpha evidence.

---

## Decision

`stage0_status = r7_rejected_current_forms_full_stack_blocked`

`alpha_rerun_allowed = False`

`manifest_ab_allowed = False`

Blockers:

- `daily_top_global_mf07_no_stage0_survivor`
- `subday_participant_pivot_no_stage0_survivor`
- `cex_transfer_direction_partial_sidecar_not_integrated_into_feature_panel`
- `whale_transfer_direction_partial_sidecar_not_integrated_into_feature_panel`
- `etf_flow_regime_sidecar_not_integrated_into_feature_panel`

Do not spend another manifest slot on MF-07 top/global or 1h pivot flags. R-7
can reopen only after the PIT ETF/on-chain participant sidecars are integrated
into a new pre-registered transition definition that beats raw SP-K on the
canonical parent.

2026-05-09 follow-up:

- R-7b transition card:
  `docs/quant_research/03_alpha_branches/mf07_etf_onchain_transition_falsification.md`
- result: PIT ETF/whale sidecars were integrated into six pre-registered
  transition definitions; `stage0_survivors = []`.
- decision: current MF-07 participant-stack reopening remains closed. Do not
  add MF-07 ETF/on-chain transitions to the parent overlay.
