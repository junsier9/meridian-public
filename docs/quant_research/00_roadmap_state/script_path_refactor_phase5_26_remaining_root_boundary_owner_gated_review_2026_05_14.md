# Phase 5.26 Remaining Root Boundary Owner-Gated Review

Date: 2026-05-14

Status: read-only owner-gated review artifact. This document does not move
scripts, change catalog counts, or approve an implementation plan.

Baseline: after `fd7a342 Fix Phase 5.25 catalog summary counts`.

## Purpose

Phase 5.25 moved the first-batch leaf provider sync helpers into
`scripts/quant_research/provider_leaf_sync_helpers/` while preserving four root
CLI wrappers. The remaining root implementation candidates are now mostly public
interfaces, active data writers, h10d proof surfaces, CoinGlass boundary scripts,
research-cycle entrypoints, or mixed utility support.

This review decides the next governance boundary:

- which root helpers should be treated as permanent keep-root interfaces;
- which helpers may only be considered through a future root-wrapper pattern;
- which helpers require owner approval before an implementation plan can be
  written.

## Non-Movement Guarantee

No scripts are moved by this artifact.

No `scripts/`, `config/`, `tests/`, `artifacts/`, or catalog rows are changed by
this artifact.

Do not interpret `future-wrapper-only` as movement approval. It only describes
the allowed shape if a later owner-approved implementation happens.

## Current Boundary Counts

After Phase 5.25:

- total script coverage: 278 files;
- root-level files: 162;
- root compatibility wrappers: 89;
- `provider_leaf_sync_helpers/`: 4 implementation files;
- remaining root implementation files with `safe-to-move != no`: 54.

The 54 remaining root implementation candidates are:

- Data Sync / Data Foundation: 18 remaining after the 4 Phase 5.25 moves;
- H10D / Binance PIT Boundary: 15;
- CoinGlass Sync / H10D Parent Boundary: 7;
- Utility Support: 7;
- Alpha Ontology Cycles: 3;
- Research-Cycle Default Entrypoints: 3;
- Factor Report Card: 1.

Scheduled PowerShell surfaces and compatibility wrappers remain root-level
public paths but are not movement candidates.

## Policy Definitions

`permanent keep-root` means the root path is a stable public interface. Do not
rename, delete, or move the root interface. If implementation is ever split
behind that root path, it requires a separate owner-approved plan.

`future-wrapper-only` means the only acceptable implementation shape is a moved
implementation plus a root compatibility wrapper or shim. The root path must
remain callable. This status does not grant approval to write an implementation
plan.

`owner approval before implementation plan` means do not write a movement plan
for that path until the owner explicitly approves the selected subset and target
directory.

## Permanent Keep-Root Interfaces

These root paths should remain visible at root indefinitely. They are not good
next implementation-plan targets.

### Scheduled Surfaces

All `register_openclaw_*` and `run_openclaw_*_runner.ps1` scheduled-task
surfaces remain permanent root paths. They stay governed by
`config/scheduled_tasks/manifest.json` and the scheduled-task contract.

### Data-Foundation Default Entrypoints

- `run_quant_coinapi_spot_sync.py`
- `run_quant_cryptoquant_m3_2_sync_cycle.py`
- `run_quant_deribit_options_chain_snapshot_cycle.py`
- `run_quant_derivatives_sync_cycle.py`
- `run_quant_stablecoin_ethereum_sync_cycle.py`
- `run_quant_universe_freeze.py`
- `run_quant_universe_input_producer.py`

Reason: these are data-foundation refresh/default surfaces. A future internal
split is possible only if the root path remains and owner approval explicitly
accepts the compatibility plan.

### Research-Cycle Default Entrypoints

- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`

Reason: these are default manual or automation-adjacent research-cycle surfaces,
not cleanup candidates.

### Current H10D Public Surfaces

- `analyze_binance_pit_drawdown_attribution.py`
- `assert_h10d_promotion_evidence.py`
- `build_binance_hv_balanced_anti_overfit_package.py`
- `run_baseline_alpha_proof.py`
- `run_baseline_alpha_survival.py`
- `run_binance_canonical_h10d_validation.py`
- `run_binance_spot_concordance_baseline.py`
- `validate_baseline_alpha_confidence.py`

Reason: these paths anchor current h10d validation, proof, promotion, baseline,
or confidence surfaces. Do not demote them into diagnostics or historical
directories.

### CoinGlass Boundary Entrypoints

- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`

Reason: these are CoinGlass sync/default or sidecar boundary surfaces. They must
not be absorbed by provider probes, provider diagnostics, quarantine folders, or
generic data-sync directories.

### Runtime Bootstrap Boundary

- `bootstrap_quant_runtime.py`

Reason: scheduled helper logic depends on the root runtime bootstrap path. Keep
it root-level unless the scheduler contract is explicitly redesigned.

## Future-Wrapper-Only Candidates

These paths may be considered in future dry-runs, but only with old root paths
preserved as wrappers or module-compatible shims. Do not delete or rename the
root interface.

### Data-Foundation Helpers

- `backfill_stablecoin_history.py`
- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `run_quant_stablecoin_ethereum_backfill.py`
- `sync_alchemy_stablecoin_ethereum.py`
- `sync_binance_derivatives_history.py`
- `sync_coinapi_multi_venue_spot.py`
- `sync_deribit_dvol_history.py`
- `sync_deribit_options_chain.py`
- `sync_ethereum_address_labels.py`

Notes:

- `generate_versioned_panel.py` is a panel materializer, not a leaf provider
  sync helper.
- `run_quant_derivatives_sync_evidence.py` writes by-as-of derivatives evidence
  and can route through CoinGlass under `--provider auto`.
- `run_quant_stablecoin_ethereum_backfill.py`,
  `sync_ethereum_address_labels.py`, and `sync_deribit_options_chain.py` have
  stronger caller/scheduler adjacency and are not leaf-only.

### Historical H10D Evidence

- `evaluate_v5_h10d_post_pump_short_replacement.py`
- `evaluate_v6_h10d_mf01_narrow_ab.py`
- `evaluate_v6_h10d_orderbook_short_replacement.py`
- `evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_short_replacement.py`

These should remain historical if ever moved. A future target directory must not
make them look like current-line h10d entrypoints.

### CoinGlass H10D Parent Historical Evidence

- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`

These may be wrapperable as historical evidence only. They should not be moved
into CoinGlass diagnostics, provider probes, or current h10d directories without
a dedicated owner-approved boundary plan.

### Utility And Ontology Support

- `compute_alpha_ontology_v3_weights.py`
- `compute_stablecoin_issuance_velocity_overlay_candidate.py`
- `diagnose_shadow_vs_cycle.py`
- `export_passed_alphas_to_workbench.py`
- `run_alpha_ontology_horizon_cycle_oneoff.py`
- `run_alpha_ontology_v1_cycle_oneoff.py`
- `run_quant_ohlcv_lane_ab.py`
- `run_quantagent_shadow_proposal_cycle.py`
- `validate_week_2_exit.py`

These are not one directory family. A future dry-run should split ontology,
shadow/workbench, OHLCV lane, and overlay/support utilities rather than creating
a generic `utility/` drawer.

### Factor Report Card

- `factor_report_card.py`

This is mechanically wrapperable but broad enough to be a public report surface.
It needs a dedicated caller/import review before any target directory is chosen.

## Owner Approval Required Before Implementation Plan

The following groups are blocked from autonomous implementation planning. A
future implementation plan must start only after the owner explicitly approves
the exact subset and target directory.

### Data Sync / Data Foundation

All remaining data-foundation root implementations are owner-gated, including
the future-wrapper-only helpers listed above and the permanent default
entrypoints:

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
- `sync_deribit_dvol_history.py`
- `sync_deribit_options_chain.py`
- `sync_ethereum_address_labels.py`

### H10D / Binance PIT Boundary

All current and historical h10d root boundary paths are owner-gated:

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

All CoinGlass sync and h10d-parent boundary paths are owner-gated:

- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`
- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`
- `sync_coinglass_oi_provenance_sidecar.py`

### Research Cycle And Factor Report Surface

- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`
- `factor_report_card.py`

Reason: these are broad manual/reporting surfaces. Do not move them under
generic utility directories.

## Deferred But Lower-Risk Read-Only Work

If more read-only governance is useful before the next implementation, the
lowest-risk next dry-run is not another data-sync move. It is a utility-support
classification dry-run that separates:

- ontology cycle support;
- shadow/workbench helpers;
- OHLCV lane support;
- overlay/support report helpers;
- broad report-card surface.

That dry-run should not approve moves. It should decide whether any narrow
directory names are justified.

## Stop Condition

Autonomous Phase 5.x movement should remain stopped at this boundary.

Do not write another implementation plan until the owner chooses one of these
explicit paths:

1. permanently freeze data-foundation default entrypoints at root;
2. approve a specific owner-gated data-foundation helper subset for a dry-run;
3. approve historical h10d/CoinGlass parent evidence for a wrapper-only dry-run;
4. run a utility-support classification dry-run with no implementation.

Recommended next action: choose path 4 if the goal is lower risk, or path 1 if
the goal is to close the data-sync/root-boundary governance loop.
