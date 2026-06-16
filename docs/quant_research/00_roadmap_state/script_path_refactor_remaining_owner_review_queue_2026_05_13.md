# Remaining Script Path Refactor Owner-Review Queue

`Status: classification freeze`
`Date: 2026-05-13`
`Scope: remaining root-level implementation scripts after Phase 5.22`

## Decision

All remaining root-level implementation scripts are now classified. There is no
untriaged "miscellaneous" bucket left.

Do not try to empty `scripts/quant_research/`. The root directory must keep:

- scheduled PowerShell surfaces;
- current default entrypoints;
- public compatibility wrappers;
- high-risk data, h10d, and research-cycle boundaries until owner review.

## Current Counts

After Phase 5.22:

- total catalog coverage: 274 script files;
- root-level files: 162;
- root compatibility wrappers: 85;
- scheduled PowerShell surfaces: 19;
- remaining root implementation files with `safe-to-move != no`: 54.

Those 54 remaining root implementations are assigned below.

## Owner-Review Buckets

### Data Sync / Data Foundation

`Count: 22`
`Risk: high`
`Posture: owner review before any move`

Reason: active data-refresh, provider history, universe, or default data-cycle
surfaces. Several are default entrypoints or likely scheduled/config-adjacent.

- `backfill_stablecoin_history.py`
- `generate_versioned_panel.py`
- `run_quant_coinapi_spot_sync.py`
- `run_quant_cryptoquant_m3_2_sync_cycle.py`
- `run_quant_deribit_options_chain_snapshot_cycle.py`
- `run_quant_derivatives_sync_cycle.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `run_quant_stablecoin_ethereum_backfill.py`
- `run_quant_stablecoin_ethereum_sync_cycle.py`
- `run_quant_universe_freeze.py`
- `run_quant_universe_input_producer.py`
- `sync_alchemy_stablecoin_ethereum.py`
- `sync_binance_derivatives_history.py`
- `sync_coinapi_multi_venue_spot.py`
- `sync_cryptoquant_reflexivity_history.py`
- `sync_cryptoquant_stablecoin_history.py`
- `sync_deribit_dvol_history.py`
- `sync_deribit_options_chain.py`
- `sync_ethereum_address_labels.py`
- `sync_okx_funding_history.py`
- `sync_tronscan_stablecoin_tron.py`

### H10D / Binance PIT Boundary

`Count: 15`
`Risk: high`
`Posture: owner review before any move`

Reason: current default h10d entrypoints, baseline public surfaces, promotion
evidence, or historical h10d helper modules that are still imported by stage-0
scripts.

- `analyze_binance_pit_drawdown_attribution.py`
- `assert_h10d_promotion_evidence.py`
- `build_binance_hv_balanced_anti_overfit_package.py`
- `evaluate_v5_h10d_post_pump_short_replacement.py`
- `evaluate_v6_h10d_mf01_narrow_ab.py`
- `evaluate_v6_h10d_orderbook_short_replacement.py`
- `evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_short_replacement.py`
- `run_baseline_alpha_proof.py`
- `run_baseline_alpha_survival.py`
- `run_binance_canonical_h10d_validation.py`
- `run_binance_spot_concordance_baseline.py`
- `validate_baseline_alpha_confidence.py`

### CoinGlass Sync / H10D Parent Boundary

`Count: 7`
`Risk: high`
`Posture: owner review before any move`

Reason: CoinGlass sync/default entrypoints and h10d-parent historical scripts
must not be mixed with diagnostics, provider probes, or quarantine
implementations.

- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`
- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`
- `sync_coinglass_oi_provenance_sidecar.py`

### Alpha Stage-0 / Quarantine

`Count: 0`
`Risk: medium-high`
`Posture: Phase 5.17 first batch, Phase 5.18a MF05 pair, Phase 5.18b SP-K non-kline, Phase 5.18c MF07 subday, Phase 5.18d MF07 participant pair, Phase 5.20 M3.2, Phase 5.21 M3.1, and Phase 5.22 M3.3 moved`

Reason: all owner-approved alpha stage-0/quarantine subclusters have now moved.
The target directory `alpha_stage0_quarantine/` remains approved only for
owner-approved subclusters and must not absorb broader M3/MF, h10d, data-sync,
or support surfaces.

Moved in Phase 5.17 first batch:

- `compute_stablecoin_flow_overlay_candidates.py`
- `evaluate_funding_oi_crowded_squeeze_failure_stage0.py`
- `evaluate_post_capitulation_long_replacement_stage0.py`
- `evaluate_spk_crowding_confirmation_stage0.py`

Moved in Phase 5.18a MF05 batch:

- `evaluate_mf05_cross_venue_boundary_stage0.py`
- `evaluate_mf05_cross_venue_spk_stage0.py`

Moved in Phase 5.18b SP-K batch:

- `evaluate_spk_non_kline_confirmation_stage0.py`

Moved in Phase 5.18c MF07 subday batch:

- `evaluate_mf07_subday_participant_pivot_stage0.py`

Moved in Phase 5.18d MF07 participant pair:

- `evaluate_mf07_participant_disagreement_spk_stage0.py`
- `evaluate_mf07_etf_onchain_transition_falsification.py`

Moved in Phase 5.20 M3.2 boundary/sidecar batch:

- `evaluate_m3_2_boundary_activation_stage0.py`
- `evaluate_m3_2_boundary_activation_falsification.py`
- `evaluate_m3_2_canonical_parent_stage0.py`
- `evaluate_m3_2_etf_onchain_sidecar_falsification.py`

Moved in Phase 5.21 M3.1 options batch:

- `audit_m3_1_options_regime_stage0.py`
- `evaluate_m3_1_options_volume_shock_veto_falsification.py`

Moved in Phase 5.22 M3.3 event-state batch:

- `evaluate_m3_3_event_tape_spk_stage0.py`
- `evaluate_m3_3_event_state_feature_stage0.py`
- `evaluate_m3_3_strict_event_state_stage0.py`
- `evaluate_m3_3_robustness_v2_stage0.py`
- `evaluate_m3_3_mf01_confirmation_stage0.py`
- `evaluate_m3_3_hype_chatter_gate_stage0.py`

Remaining owner-review subclusters:

- none in alpha stage-0/quarantine.

See `script_path_refactor_phase5_17_alpha_stage0_quarantine_dry_run_2026_05_13.md`
and
`script_path_refactor_phase5_17_alpha_stage0_quarantine_owner_decision_2026_05_13.md`.
Phase 5.18 subcluster dry-run:
`script_path_refactor_phase5_18_mf05_mf07_spk_alpha_stage0_dry_run_2026_05_13.md`.
Phase 5.19/5.20/5.21/5.22 M3 dry-run and implementation plans:
`script_path_refactor_phase5_19_m3_high_risk_dry_run_2026_05_13.md`,
`script_path_refactor_phase5_20_m3_2_boundary_implementation_plan_2026_05_13.md`,
`script_path_refactor_phase5_21_m3_1_options_implementation_plan_2026_05_13.md`,
`script_path_refactor_phase5_22_m3_3_event_state_implementation_plan_2026_05_13.md`.

### Utility Support

`Count: 0`
`Risk: closed`
`Posture: no remaining Utility Support paths`

Reason: these are not one semantic family. Do not create a generic
`utility/` drawer without deciding whether they are runtime bootstrap,
workbench export, shadow-cycle support, or report/admission surfaces.
Phase 5.35 moved the report/evidence writer subset
(`compute_stablecoin_issuance_velocity_overlay_candidate.py`,
`diagnose_shadow_vs_cycle.py`, and `validate_week_2_exit.py`) behind
`report_writers/` wrappers.
Phase 5.36 split the remaining four into separate decisions. Phase 5.37 closed
bootstrap and quantagent shadow cycle as permanent catalog-only root-freeze
paths. Phase 5.39 moved the OHLCV lane diagnostic implementation under
`scripts/quant_research/data_lane_diagnostics/`. Phase 5.41 closed the
workbench export root as a frozen public bridge.

No remaining paths in this bucket.

### Alpha Ontology Cycles

`Count: 3`
`Risk: medium`
`Posture: separate dry-run required`

Reason: these are ontology/cycle runners with historical and current research
semantics. They should not be moved as generic utilities.

- `compute_alpha_ontology_v3_weights.py`
- `run_alpha_ontology_horizon_cycle_oneoff.py`
- `run_alpha_ontology_v1_cycle_oneoff.py`

### Research-Cycle Default Entrypoints

`Count: 3`
`Risk: high`
`Posture: keep root until owner review`

Reason: default manual or automation-adjacent research-cycle surfaces.

- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`

### Factor Report Card

`Count: 1`
`Risk: medium-high`
`Posture: keep root until dedicated caller/import review`

Reason: previously deferred; it is broad enough to be a public report surface
rather than a simple report writer.

- `factor_report_card.py`

## Stop Condition

Autonomous low-risk implementation is complete for this pass. Further path
changes should start only after the owner chooses the next review target:

1. complete a Phase 5.22 post-commit review for the M3.3 event-state batch;
2. choose whether data-sync entrypoints should remain root permanently;
3. decide whether utility support needs one directory or several narrower
   contracts.

Until then, the catalog and README are the operational baseline.
