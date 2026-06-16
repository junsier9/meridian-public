# Remaining Root-Level Script Refactor Dry-Run

`Status: dry-run decision artifact`
`Date: 2026-05-13`
`Scope: remaining root-level scripts under scripts/quant_research`
`Baseline commit: 9d7472e Phase 5.6 orderbook event study script path refactor`

## Decision

Do not try to empty `scripts/quant_research/`.

Keep root-level public entrypoints, scheduled surfaces, and compatibility
wrappers in place. Continue moving implementation files only when the target
directory has a narrow semantic boundary and the old root CLI path can be
preserved.

This dry-run uses the current script catalog as the inventory source. The
candidate universe is root-level scripts with `safe-to-move = yes` or
`safe-to-move = yes-with-wrapper`.

## Candidate Summary

- Root-level script rows in catalog: 162
- Root-level `safe-to-move = no`: 45
- Candidate universe: 117
- Existing root compatibility wrappers in the candidate universe: 0

The 45 `safe-to-move = no` rows are out of scope for this dry-run. They include
scheduled/public entrypoints and compatibility wrappers that should remain at
their root paths.

## Dry-Run Grouping

### data_sync

`Count: 20`
`Action: defer to provider/data-sync dry-run`

These are sync, backfill, provider refresh, universe, or data-cycle scripts.
Several are default entrypoints or have config/docs references. They should not
be batched with utility cleanup.

- `generate_versioned_panel.py`
- `run_quant_coinapi_spot_sync.py`
- `run_quant_cryptoquant_m3_2_sync_cycle.py`
- `run_quant_deribit_options_chain_snapshot_cycle.py`
- `run_quant_derivatives_sync_cycle.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `run_quant_universe_freeze.py`
- `run_quant_universe_input_producer.py`
- `sync_binance_derivatives_history.py`
- `sync_coinapi_multi_venue_spot.py`
- `sync_cryptoquant_reflexivity_history.py`
- `sync_cryptoquant_stablecoin_history.py`
- `sync_deribit_dvol_history.py`
- `sync_okx_funding_history.py`
- `sync_tronscan_stablecoin_tron.py`
- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`
- `sync_coinglass_oi_provenance_sidecar.py`

### h10d_diagnostics

`Count: 24`
`Action: defer to h10d diagnostics dry-run`

These scripts are too close to the current h10d, Binance PIT, or CoinGlass h10d
parent evidence surface. Several have module import or historical source/doc
references. Do not move them as generic utilities.

- `analyze_binance_pit_drawdown_attribution.py`
- `build_binance_hv_balanced_anti_overfit_package.py`
- `combine_alpha_ontology_h10d_overlay_ablation_partials.py`
- `compare_alpha_ontology_h10d_fixed_set.py`
- `compare_alpha_ontology_h10d_overlay_ablation.py`
- `evaluate_v5_h10d_post_pump_short_replacement.py`
- `evaluate_v6_h10d_mf01_narrow_ab.py`
- `evaluate_v6_h10d_orderbook_short_replacement.py`
- `evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_short_overlay.py`
- `evaluate_v6_h10d_post_pump_short_replacement.py`
- `run_baseline_alpha_proof.py`
- `run_baseline_alpha_survival.py`
- `run_binance_canonical_h10d_validation.py`
- `run_binance_spot_concordance_baseline.py`
- `validate_baseline_alpha_confidence.py`
- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_drift.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `audit_coinglass_h10d_parent_rebaseline.py`
- `audit_coinglass_h10d_parent_strict_cycle_probe.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`

### alpha_stage0

`Count: 37`
`Action: defer except for a later historical-only legacy batch`

This group contains stage-0 evaluators, strict falsification scripts,
quarantined candidates, and older alpha ontology phase scripts. It needs a
separate dry-run that distinguishes current quarantine contracts from purely
historical scripts.

- `run_coinglass_r1a_top_liquidity_ex_trx_strict.py`
- `write_coinglass_spot_concordance_quarantine.py`
- `audit_m3_1_options_regime_stage0.py`
- `audit_mf05_venue_local_data_gate.py`
- `audit_mf07_participant_stack_r7_gate.py`
- `build_m3_2_feature_panel.py`
- `compute_stablecoin_flow_overlay_candidates.py`
- `evaluate_funding_oi_crowded_squeeze_failure_stage0.py`
- `evaluate_m3_1_options_volume_shock_veto_falsification.py`
- `evaluate_m3_2_boundary_activation_falsification.py`
- `evaluate_m3_2_boundary_activation_stage0.py`
- `evaluate_m3_2_canonical_parent_stage0.py`
- `evaluate_m3_2_etf_onchain_sidecar_falsification.py`
- `evaluate_m3_3_event_state_feature_stage0.py`
- `evaluate_m3_3_event_tape_spk_stage0.py`
- `evaluate_m3_3_hype_chatter_gate_stage0.py`
- `evaluate_m3_3_mf01_confirmation_stage0.py`
- `evaluate_m3_3_robustness_v2_stage0.py`
- `evaluate_m3_3_strict_event_state_ab.py`
- `evaluate_m3_3_strict_event_state_stage0.py`
- `evaluate_mf05_cross_venue_boundary_stage0.py`
- `evaluate_mf05_cross_venue_spk_stage0.py`
- `evaluate_mf07_etf_onchain_transition_falsification.py`
- `evaluate_mf07_participant_disagreement_spk_stage0.py`
- `evaluate_mf07_subday_participant_pivot_stage0.py`
- `evaluate_mf13_tron_cross_sectional_gate_increment.py`
- `evaluate_mf13_tron_regime_gate_ab.py`
- `evaluate_mf14_cross_sectional_gate_increment.py`
- `evaluate_mf14_regime_gate_ab.py`
- `evaluate_post_capitulation_long_replacement_stage0.py`
- `evaluate_post_pump_stall_cycle_increment.py`
- `evaluate_spk_crowding_confirmation_stage0.py`
- `evaluate_spk_non_kline_confirmation_stage0.py`
- `evaluate_stablecoin_flow_interaction_cycle_increment.py`
- `explore_btc_options_signals.py`
- `phase_1c_factor_correlation_analysis.py`
- `phase_1d_dynamic_weight_schedule.py`

### utility

`Count: 17`
`Action: split; move only the low-risk provider-diagnostic subset now`

This bucket is not a single directory contract. It contains provider
diagnostics, default research-cycle entrypoints, dataset processors, exporters,
and one-off tools. The next low-risk batch should be a narrow provider
diagnostics subset, not a generic `utility/` drawer.

Low-risk provider diagnostics selected for the next implementation commit:

- `audit_coinglass_dataset_feature_smoke.py`
- `audit_coinglass_oi_compiler_integration.py`
- `audit_coinglass_oi_provenance.py`
- `validate_coinglass_spot_overlap.py`
- `validate_coinglass_spot_strict_concordance.py`

Utility candidates deferred:

- `run_coinglass_capability_matrix.py` - provider capability surface; consider
  `provider_probes/` or a separate capability-matrix dry-run.
- `write_coinglass_coverage_reset_report.py` - aggregation report with no
  `main(argv)` parser; move only after wrapper strategy is explicit.
- `bootstrap_quant_runtime.py`
- `compute_stablecoin_issuance_velocity_overlay_candidate.py`
- `export_passed_alphas_to_workbench.py`
- `process_cryptonewsdataset_llm.py`
- `review_cryptonewsdataset_strong_model.py`
- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_ohlcv_lane_ab.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`
- `run_quantagent_shadow_proposal_cycle.py`

### wrappers-only

`Count: 0 inside the 117-candidate universe`

Existing root compatibility wrappers are already cataloged as
`safe-to-move = no`, so they are intentionally outside this candidate set. Do
not move wrappers that exist only to preserve public root CLI paths.

### deferred

`Count: 19`
`Action: do not move in the next low-risk commit`

These were deferred because they have stronger source/config/docs references,
module import risk, current-line semantics, or explicit prior deferral pressure.

- `backfill_stablecoin_history.py`
- `run_quant_stablecoin_ethereum_backfill.py`
- `run_quant_stablecoin_ethereum_sync_cycle.py`
- `sync_alchemy_stablecoin_ethereum.py`
- `sync_deribit_options_chain.py`
- `sync_ethereum_address_labels.py`
- `assert_h10d_promotion_evidence.py`
- `compute_lsk3_baseline_decay_diagnostic.py`
- `compute_lsk3_decay_deep_dive.py`
- `compute_multi_horizon_factor_audit.py`
- `run_factor_lifecycle_demotion_experiment.py`
- `evaluate_stablecoin_overlay_cycle_increment.py`
- `run_v83_shadow_oos.py`
- `compute_alpha_ontology_v3_weights.py`
- `diagnose_shadow_vs_cycle.py`
- `factor_report_card.py`
- `run_alpha_ontology_horizon_cycle_oneoff.py`
- `run_alpha_ontology_v1_cycle_oneoff.py`
- `validate_week_2_exit.py`

## Next Low-Risk Implementation Batch

Move only the five selected CoinGlass provider-diagnostic implementations to:

- `scripts/quant_research/provider_diagnostics/`

Keep the five old root paths as thin CLI wrappers.

Do not move:

- provider sync pipelines;
- provider capability probes/capability matrices;
- scheduled entrypoints;
- current data-foundation default entrypoints;
- h10d current-line diagnostics;
- alpha stage-0 or strict-falsification scripts;
- generic utility scripts whose directory contract is still unclear.

## Required Implementation Updates

- Add `provider_diagnostics/` as a narrow directory contract for provider
  validation, provenance, concordance, and dataset smoke diagnostics.
- Update moved scripts from root discovery depth `parents[1]` to `parents[2]`.
- Keep old root paths as CLI wrappers that forward `sys.argv[1:]`.
- Split catalog rows into wrapper rows and implementation rows.
- Update README counts and path policy.
- Add this dry-run artifact to the governance index.

## Required Verification

```powershell
python -m compileall -q scripts\quant_research\provider_diagnostics scripts\quant_research\audit_coinglass_dataset_feature_smoke.py scripts\quant_research\audit_coinglass_oi_compiler_integration.py scripts\quant_research\audit_coinglass_oi_provenance.py scripts\quant_research\validate_coinglass_spot_overlap.py scripts\quant_research\validate_coinglass_spot_strict_concordance.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_coinglass_dataset_feature_smoke.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_coinglass_oi_compiler_integration.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_coinglass_oi_provenance.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\validate_coinglass_spot_overlap.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\validate_coinglass_spot_strict_concordance.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Run the local Markdown link checker because this dry-run, README, checklist,
and catalog are documentation surfaces.
