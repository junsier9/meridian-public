# Quant Research Script Path Refactor Dry Run - Phase 2a

`Snapshot date: 2026-05-12`
`Status: dry-run artifact plus Phase 2a partial execution ledger`
`Scope: scripts/quant_research direct .py/.ps1 files only`
`Source of truth: quant_research_script_catalog.md`

This document is the first path-refactor plan after the script catalog and
entrypoint cleanup. It originally proposed the first low-risk move batch without
executing any `git mv`; the M3/MF/SP-K clean historical subset has now been
executed and is recorded below.

## Decision

Phase 2a has started. The remaining executable path-refactor sequence is:

1. Move the `parallel_1h` scripts marked `safe-to-move = yes` as a group into
   `scripts/quant_research/parallel_1h/`.
2. Keep the executed clean M3/MF/SP-K historical scripts under
   `scripts/quant_research/legacy_candidates/`.
3. Do not move `utilities_and_reports` in Phase 2a. A strict zero-reference
   scan found no utility scripts with no explicit external references.

Scheduled wrappers, default h10d entrypoints, and `safe-to-move = no` scripts
are out of scope for this dry run.

## Scan Method

Inputs:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- exact filename/path scans across `config`, `docs`, `scripts`, `src`, and
  `tests`
- import-reference scan for bare Python module imports in the parallel 1h lane

Excluded from "external reference" counts:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `scripts/quant_research/README.md`
- the script file itself

Important limitation: exact filename/path references and Python import
references are different risks. A script can have zero path references and still
be imported by another sibling script.

## Proposed Target Directories

| target directory | purpose | first-batch policy |
| --- | --- | --- |
| `scripts/quant_research/parallel_1h/` | quarantined 1h manipulation/mechanical-flow lane scripts | move as a group; update sibling imports in the same commit |
| `scripts/quant_research/legacy_candidates/v71_v83/` | v71/v72/v83 historical exploration and shadow scripts | move zero-reference historical scripts first |
| `scripts/quant_research/legacy_candidates/phase1_factor_weighting/` | Phase 1c/1d historical factor-correlation and dynamic-weight diagnostics | split: move zero-reference diagnostic first; defer scripts referenced by runtime/source docs |
| `scripts/quant_research/utilities/one_off/` | one-off support tools | dry-run target only; no Phase 2a move because strict zero-reference count is 0 |

## Phase 2a Candidate Summary

| group | matching scripts | first-batch move count | target | notes |
| --- | ---: | ---: | --- | --- |
| `parallel_1h`, `safe-to-move = yes` | 20 | 20 | `scripts/quant_research/parallel_1h/` | path refs are zero, but sibling imports require grouped move/import fix |
| `m3_mf_spk_legacy_candidates`, historical/quarantined, `safe-to-move = yes` | 9 | 7 | `scripts/quant_research/legacy_candidates/` | 2 have source/runtime references and should be deferred |
| `utilities_and_reports`, strict zero external refs | 0 | 0 | `scripts/quant_research/utilities/one_off/` | no strict candidates; doc-only candidates can be considered later |

## First Batch A: Parallel 1h

Move target: `scripts/quant_research/parallel_1h/`

All rows below are `category = parallel_1h`, `status = quarantined`,
`run priority = quarantined_falsification`, and `safe-to-move = yes`.
Exact path/filename reference count is 0 after excluding catalog/README/self.

| script | target path | exact external refs |
| --- | --- | ---: |
| `scripts/quant_research/audit_parallel_1h_fake_liquidity_parent_symbol_provider_sensitivity.py` | `scripts/quant_research/parallel_1h/audit_parallel_1h_fake_liquidity_parent_symbol_provider_sensitivity.py` | 0 |
| `scripts/quant_research/audit_parallel_1h_venue_concentration_sidecar.py` | `scripts/quant_research/parallel_1h/audit_parallel_1h_venue_concentration_sidecar.py` | 0 |
| `scripts/quant_research/build_parallel_1h_stage0_decision_ledger.py` | `scripts/quant_research/parallel_1h/build_parallel_1h_stage0_decision_ledger.py` | 0 |
| `scripts/quant_research/build_parallel_1h_venue_concentration_sidecar.py` | `scripts/quant_research/parallel_1h/build_parallel_1h_venue_concentration_sidecar.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_fake_liquidity_atomic_decomposition.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_fake_liquidity_atomic_decomposition.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_funding_normalization_after_deep_negative_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_funding_normalization_after_deep_negative_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_funding_settlement_squeeze_window_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_funding_settlement_squeeze_window_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_liquidation_cluster_aftershock_veto_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_liquidation_cluster_aftershock_veto_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_low_float_squeeze_trap_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_low_float_squeeze_trap_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_low_liquidity_hour_kill_switch_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_low_liquidity_hour_kill_switch_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_post_pump_bid_replenishment_failure_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_post_pump_bid_replenishment_failure_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_post_squeeze_exit_short_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_post_squeeze_exit_short_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0.py` | 0 |
| `scripts/quant_research/evaluate_parallel_1h_top_trader_fade_retail_chase_veto_stage0.py` | `scripts/quant_research/parallel_1h/evaluate_parallel_1h_top_trader_fade_retail_chase_veto_stage0.py` | 0 |
| `scripts/quant_research/simulate_parallel_1h_fake_liquidity_age_gated_parent_interaction.py` | `scripts/quant_research/parallel_1h/simulate_parallel_1h_fake_liquidity_age_gated_parent_interaction.py` | 0 |
| `scripts/quant_research/simulate_parallel_1h_fake_liquidity_age_sidecar.py` | `scripts/quant_research/parallel_1h/simulate_parallel_1h_fake_liquidity_age_sidecar.py` | 0 |
| `scripts/quant_research/simulate_parallel_1h_fake_liquidity_parent_interaction.py` | `scripts/quant_research/parallel_1h/simulate_parallel_1h_fake_liquidity_parent_interaction.py` | 0 |
| `scripts/quant_research/validate_parallel_1h_venue_volume_concordance.py` | `scripts/quant_research/parallel_1h/validate_parallel_1h_venue_volume_concordance.py` | 0 |

### Parallel 1h Import Caveat

The parallel 1h scripts have sibling imports. The real move must either update
imports or move the whole dependency cluster together.

Resolved strategy artifact:
`parallel_1h_import_rewrite_strategy_2026_05_13.md`.

Observed candidate modules imported by other scripts:

- `evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0`
- `evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0`
- `evaluate_parallel_1h_low_float_squeeze_trap_stage0`
- `evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0`
- `simulate_parallel_1h_fake_liquidity_parent_interaction`

Additional `parallel_1h` scripts marked `safe-to-move = yes-with-wrapper`
import some of these candidate modules. If the strict `safe-to-move = yes`
batch is executed first, update those holdout imports to the new package path
or include compatibility shims in the same commit.

Holdouts to inspect before execution:

- `scripts/quant_research/audit_parallel_1h_native_exchange_flow_sidecar.py`
- `scripts/quant_research/build_parallel_1h_trust_masked_venue_concentration_sidecar.py`
- `scripts/quant_research/evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py`

## First Batch B: Clean M3/MF/SP-K Historical Scripts

Move targets:

- v71/v72/v83 historical scripts:
  `scripts/quant_research/legacy_candidates/v71_v83/`
- Phase 1 historical diagnostics:
  `scripts/quant_research/legacy_candidates/phase1_factor_weighting/`

Rows below are `category = m3_mf_spk_legacy_candidates`,
`status = historical`, `run priority = historical_do_not_start_here`, and
`safe-to-move = yes`.

| previous path | current/target path | exact external refs | Phase 2a action |
| --- | --- | ---: | --- |
| `scripts/quant_research/check_v72_gate_alignment.py` | `scripts/quant_research/legacy_candidates/v71_v83/check_v72_gate_alignment.py` | 0 | moved |
| `scripts/quant_research/explore_v71_composite_ic.py` | `scripts/quant_research/legacy_candidates/v71_v83/explore_v71_composite_ic.py` | 0 | moved |
| `scripts/quant_research/explore_v71_extended_features_ic.py` | `scripts/quant_research/legacy_candidates/v71_v83/explore_v71_extended_features_ic.py` | 0 | moved |
| `scripts/quant_research/explore_v71_gen2_xs_factors.py` | `scripts/quant_research/legacy_candidates/v71_v83/explore_v71_gen2_xs_factors.py` | 0 | moved |
| `scripts/quant_research/explore_v71_xs_rank_ic.py` | `scripts/quant_research/legacy_candidates/v71_v83/explore_v71_xs_rank_ic.py` | 0 | moved |
| `scripts/quant_research/phase_1d_wf_ic_stability_diagnostic.py` | `scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1d_wf_ic_stability_diagnostic.py` | 0 | moved |
| `scripts/quant_research/run_v83_cycle_equivalent_shadow.py` | `scripts/quant_research/legacy_candidates/v71_v83/run_v83_cycle_equivalent_shadow.py` | 0 | moved |
| `scripts/quant_research/phase_1c_factor_correlation_analysis.py` | `scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1c_factor_correlation_analysis.py` | 2 | defer until source/doc refs are updated |
| `scripts/quant_research/phase_1d_dynamic_weight_schedule.py` | `scripts/quant_research/legacy_candidates/phase1_factor_weighting/phase_1d_dynamic_weight_schedule.py` | 4 | defer until runtime/source refs are updated |

Defer reasons:

- `phase_1c_factor_correlation_analysis.py` is referenced from
  `src/enhengclaw/quant_research/features.py` and
  `scripts/quant_research/generate_versioned_panel.py`.
- `phase_1d_dynamic_weight_schedule.py` is referenced from
  `src/enhengclaw/quant_research/features.py` and
  `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v99.json`.

## Utilities And Reports

Strict Phase 2a result: no utility scripts qualify as "no external references"
after excluding only catalog/README/self.

Therefore no `utilities_and_reports` script should move in the first batch.
The target directory is reserved only:

```text
scripts/quant_research/utilities/one_off/
```

Doc-only or near-doc-only utility candidates for a later batch:

| script | current references | possible later target |
| --- | --- | --- |
| `scripts/quant_research/compute_stablecoin_issuance_velocity_overlay_candidate.py` | one staging-plan doc reference | `scripts/quant_research/utilities/one_off/` |
| `scripts/quant_research/export_passed_alphas_to_workbench.py` | one `docs/QUANT_RESEARCH_LAB.md` command reference | `scripts/quant_research/utilities/one_off/` |
| `scripts/quant_research/run_quant_ohlcv_lane_ab.py` | one `docs/QUANT_RESEARCH_LAB.md` command reference | `scripts/quant_research/utilities/one_off/` |
| `scripts/quant_research/run_quant_overlap_legacy_cleanup.py` | one `docs/QUANT_RESEARCH_LAB.md` command reference | `scripts/quant_research/utilities/one_off/` |
| `scripts/quant_research/run_quant_strategy_library_thesis_cutover.py` | one `docs/QUANT_RESEARCH_LAB.md` command reference | `scripts/quant_research/utilities/one_off/` |

These are not first-batch moves because the user requested no-reference
utilities. If promoted later, update the doc command examples in the same
commit.

## Actual Move Checklist

Before executing Phase 2a:

1. Re-run this scan from a clean worktree.
2. Create target directories.
3. Move only the listed `move` rows.
4. Update `quant_research_script_catalog.md` script paths and category table
   counts if needed.
5. Update `scripts/quant_research/README.md` default/functional maps if paths
   appear there.
6. Update affected Python imports for the parallel 1h dependency cluster.
7. Re-run exact path scans for old paths.
8. Run static and runtime contracts.

Minimum validation:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Optional validation after parallel 1h import rewiring:

```powershell
python -m compileall scripts\quant_research
```

## Out Of Scope

- no scheduled wrapper movement
- no active Binance PIT h10d default-entrypoint movement
- no CoinGlass foundation default-entrypoint movement
- no artifact movement
- no deletion of historical or rejected scripts
