# Phase 5.23 Data Sync Root-Boundary Keep-Root Strategy

Date: 2026-05-14

Status: read-only strategy artifact. This document does not authorize script moves,
import rewrites, or catalog count changes.

Baseline: after `606f633 Fix Phase 5.22 catalog summary counts`.

## Purpose

Phase 5.22 closed the approved alpha stage-0/M3 refactor lane. The remaining
root-level implementation files are no longer a generic cleanup backlog. They
include data-sync entrypoints, scheduled-task surfaces, provider foundation
writers, h10d validation boundaries, and research-cycle defaults.

This artifact sets the root-boundary policy before any further Phase 5.x
implementation:

- which root paths should keep a permanent root interface;
- which paths may still become future root wrappers around moved implementations;
- which paths require explicit owner approval before any move, wrapper split, or
  import rewrite.

## Non-Movement Guarantee

No root script is moved by this artifact.

No `scripts/`, `config/`, `tests/`, or artifact-output paths are changed by this
artifact.

No path listed as `owner approval required` should be touched in autonomous
implementation mode.

## Boundary Definitions

`permanent keep-root` means the exact root-level path is a stable public
interface. Future implementation may delegate internally only if the root file
remains and owner approval explicitly allows the split.

`future wrapper candidate` means the root file may remain as a thin compatibility
wrapper while implementation moves to a subdirectory in a later phase. This is
not approval to move it now.

`owner approval required` means no script move, wrapper split, import rewrite,
catalog semantic change, or README path-policy change should happen without an
explicit owner go-ahead.

## Current Inventory Reading

The Phase 5.22 catalog baseline reports:

- 274 scripts covered by the catalog.
- 162 root-level catalog rows.
- 85 root compatibility wrappers.
- 19 scheduled PowerShell root surfaces.
- 58 remaining root implementation files with `safe-to-move != no`.
- 0 remaining alpha stage-0/quarantine candidates.

The next decision is therefore not "move the next easiest file." The next
decision is whether a root path is a public boundary that should stay visible at
root even if its implementation is later split behind a wrapper.

## Permanent Keep-Root Interfaces

These paths should retain a root-level interface indefinitely. If they are ever
split internally, the root path must remain callable/importable and the change
must be reviewed as a boundary-preserving wrapper refactor.

### Scheduled PowerShell Surfaces

These are scheduled-task or scheduler-adjacent root surfaces. They are already
`safe-to-move: no` in the catalog and should remain root-level:

- `cleanup_old_quant_shadow_ingestion_runs.ps1`
- `install_openclaw_quant_runner_task.ps1`
- `register_openclaw_news_intake_task.ps1`
- `register_openclaw_quant_agent_proposal_task.ps1`
- `register_openclaw_quant_coinapi_spot_sync_task.ps1`
- `register_openclaw_quant_cryptoquant_m3_2_sync_task.ps1`
- `register_openclaw_quant_deribit_options_chain_snapshot_task.ps1`
- `register_openclaw_quant_derivatives_sync_task.ps1`
- `register_openclaw_quant_hypothesis_batch_task.ps1`
- `register_openclaw_quant_stablecoin_ethereum_sync_task.ps1`
- `register_openclaw_quant_strategy_proposal_task.ps1`
- `register_openclaw_shadow_ingestion_task.ps1`
- `run_openclaw_news_intake_runner.ps1`
- `run_openclaw_quant_agent_proposal_runner.ps1`
- `run_openclaw_quant_coinapi_spot_sync_runner.ps1`
- `run_openclaw_quant_derivatives_sync_runner.ps1`
- `run_openclaw_quant_hypothesis_batch_runner.ps1`
- `run_openclaw_quant_stablecoin_ethereum_sync_runner.ps1`
- `run_openclaw_quant_strategy_proposal_runner.ps1`

### Data Foundation Default Entrypoints

These paths are public data-foundation entrypoints. Root visibility is part of
their operational contract:

- `run_quant_coinapi_spot_sync.py`
- `run_quant_cryptoquant_m3_2_sync_cycle.py`
- `run_quant_deribit_options_chain_snapshot_cycle.py`
- `run_quant_derivatives_sync_cycle.py`
- `run_quant_stablecoin_ethereum_sync_cycle.py`
- `run_quant_universe_freeze.py`
- `run_quant_universe_input_producer.py`

### CoinGlass Sync Boundary Entrypoints

These remain root because they are high-risk boundary surfaces between provider
sync, sidecar provenance, and h10d parent research:

- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`

### Research-Cycle Default Entrypoints

These paths are user-facing/manual/scheduled research cycle entrypoints and
should remain root interfaces:

- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`

### Current H10D Public Boundary Entrypoints

These paths anchor current h10d validation, evidence packaging, or proof
surfaces. Keep them root-level unless an owner-approved wrapper plan proves the
root interface remains intact:

- `analyze_binance_pit_drawdown_attribution.py`
- `assert_h10d_promotion_evidence.py`
- `build_binance_hv_balanced_anti_overfit_package.py`
- `run_baseline_alpha_proof.py`
- `run_baseline_alpha_survival.py`
- `run_binance_canonical_h10d_validation.py`
- `run_binance_spot_concordance_baseline.py`
- `validate_baseline_alpha_confidence.py`

### Runtime Bootstrap Boundary

This path is referenced by scheduled-task helper logic and should remain a root
runtime boundary:

- `bootstrap_quant_runtime.py`

## Future Wrapper Candidates

These paths still look mechanically wrapperable, but they should only move after
a dedicated dry-run proves caller paths, artifact writes, docs links, and tests.
The expected implementation shape is: keep a root compatibility wrapper, move
the implementation into a narrowly named subdirectory, then update catalog and
README semantics.

### Data-Sync Helper Candidates

These are not approved for movement now. They are candidate implementation-split
targets only if a later dry-run confirms no scheduled/config hard boundary is
being weakened:

- `backfill_stablecoin_history.py`
- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`
- `run_quant_deterministic_daily_sample.py`
- `run_quant_stablecoin_ethereum_backfill.py`
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

### CoinGlass Sidecar/Parent Evidence Candidates

These may be wrapperable, but they sit near the CoinGlass full-stack and h10d
parent boundary. They require owner approval before implementation movement:

- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`
- `sync_coinglass_oi_provenance_sidecar.py`

### Historical H10D Evidence Candidates

These are historical evidence scripts. A future wrapper split can be considered
only if catalog semantics keep them historical and do not re-promote them as
current h10d entrypoints:

- `evaluate_v5_h10d_post_pump_short_replacement.py`
- `evaluate_v6_h10d_mf01_narrow_ab.py`
- `evaluate_v6_h10d_orderbook_short_replacement.py`
- `evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_short_replacement.py`

### Utility/Support Candidates

These are lower than the data-sync/h10d boundary work, but they still need
dedicated dry-runs because some appear in docs, scheduled helper text, or
research-cycle context:

- `compute_stablecoin_issuance_velocity_overlay_candidate.py`
- `diagnose_shadow_vs_cycle.py`
- `export_passed_alphas_to_workbench.py`
- `run_quant_ohlcv_lane_ab.py`
- `run_quantagent_shadow_proposal_cycle.py`
- `validate_week_2_exit.py`

### Alpha Ontology Cycle Candidates

These can be considered in a separate ontology-specific dry-run. They should not
be mixed into data-sync or h10d root-boundary work:

- `compute_alpha_ontology_v3_weights.py`
- `run_alpha_ontology_horizon_cycle_oneoff.py`
- `run_alpha_ontology_v1_cycle_oneoff.py`

## Owner Approval Required Before Touching

The following groups are high-risk or boundary-sensitive. They require explicit
owner approval before any implementation move or wrapper split.

### Data Sync / Data Foundation

Reason: these paths write, backfill, freeze, or produce canonical provider and
data foundation inputs. Even if wrapperable, their root behavior is operationally
meaningful.

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

Reason: these paths define current or historical h10d proof, promotion,
drawdown, baseline, and replacement evidence. Misplacing them can blur current
mainline surfaces with archived falsification evidence.

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

Reason: these paths sit between provider sync, sidecar provenance, and h10d
parent evidence. A wrapper move must preserve both CLI behavior and module
imports from full-stack foundation callers.

- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`
- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`
- `sync_coinglass_oi_provenance_sidecar.py`

### Research-Cycle Default Entrypoints

Reason: these are current-line orchestration entrypoints. They should stay root
until the owner explicitly approves a runner/wrapper split strategy:

- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`

### Factor Report Card

Reason: this path is a report writer and a likely human-facing CLI surface, but
its caller/import contract has not been isolated enough for movement:

- `factor_report_card.py`

## Deferred Directory Names

Do not create these directories without a follow-up dry-run and owner approval:

- `data_sync/`
- `data_foundation/`
- `provider_sync/`
- `h10d_root_boundary/`
- `h10d_current_boundary/`
- `research_cycle_entrypoints/`

The naming risk is semantic rather than mechanical: a broad directory name can
make helpers look like canonical entrypoints or make historical h10d evidence
look current.

## Future Dry-Run Requirements

Any future implementation proposal for these root-boundary paths must include:

- exact root paths selected and exact target directory name;
- root wrapper strategy, including CLI argument forwarding and import/re-export
  behavior;
- caller inventory from `rg`, including docs, tests, config, scheduled tasks,
  and package imports;
- artifact output path inventory;
- catalog row changes and count deltas;
- README Path Policy changes;
- static-contract impact;
- verification commands and expected pass/fail interpretation;
- explicit owner approval statement if the selected paths are in an
  owner-gated group above.

## Minimum Verification for Any Later Implementation

At minimum, any later movement under this boundary must run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

If the implementation touches provider sync, data foundation, or scheduled task
surfaces, also run the narrow provider/scheduler tests discovered by the dry-run
caller inventory.

## Phase 5.23 Decision

Do not start data-sync/root-boundary movement automatically.

The lowest-risk next action is to freeze this strategy as a governance baseline,
then choose one of two owner-reviewed paths:

- declare the data-sync default entrypoints permanent root interfaces and stop
  moving them;
- approve one small, leaf-only data-sync helper dry-run with root wrapper
  compatibility and no scheduled/config hard references.
