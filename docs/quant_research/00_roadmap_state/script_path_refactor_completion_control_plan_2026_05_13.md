# Script Path Refactor Completion Control Plan

`Status: read-only control baseline`
`Scope: remaining root-level scripts/quant_research classification`
`Owner: quant_research_maintainer`
`Date: 2026-05-13`

This control plan replaces step-by-step operator approval for the remaining
low-risk script-path refactor work. It keeps the existing Phase 5 rhythm:
dry-run artifact, narrow implementation commit, post-commit review, and
fail-closed validation. High-risk public surfaces remain review-gated.

## Current Inventory

Source of truth: `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
at commit `838b045`.

- Total catalog coverage: 231 script files.
- Root-level catalog rows: 162.
- Root-level `safe-to-move = yes-with-wrapper`: 85.
- Root-level `safe-to-move = yes`: 13.
- Root-level `safe-to-move = no`: 64.

The 64 `safe-to-move = no` root rows are already classified as public,
scheduled, compatibility-wrapper, or hard-boundary surfaces. They are not part
of autonomous implementation.

## Autonomous Stop Rules

Autonomous implementation may continue only while all of these are true:

- The batch has a dedicated dry-run or this control plan explicitly identifies
  it as a low-risk follow-up batch.
- Old root CLI compatibility is preserved through a wrapper or documented as
  intentionally unnecessary for a historical `safe-to-move = yes` script.
- Module-import compatibility is preserved by a package-import caller rewrite
  or a root re-export shim when a root module import exists.
- Catalog and README counts are updated in the same implementation commit.
- `tests/test_static_contracts.py` passes before commit.

Stop for owner review before moving:

- scheduled wrappers or scheduler-facing runner paths;
- active data-foundation default entrypoints;
- provider sync pipelines with config/test/scheduled references;
- current h10d default entrypoints, promotion guards, baseline public
  validation surfaces, or h10d module-import-dependent evaluators;
- generic research-cycle default entrypoints;
- `factor_report_card.py` until its caller/import semantics are separately
  reviewed.

## Remaining Classification

### P10 - M3/MF/SP-K support candidates

Risk: low to low-medium. These are supporting tools, not default entrypoints.
Some have root module imports from tests or sibling scripts, so implementation
must preserve module compatibility, not just CLI compatibility.

Target directory: `scripts/quant_research/m3_mf_spk_support/`.

- `audit_mf05_venue_local_data_gate.py`
- `audit_mf07_participant_stack_r7_gate.py`
- `build_m3_2_feature_panel.py`
- `evaluate_m3_3_strict_event_state_ab.py`
- `evaluate_mf13_tron_cross_sectional_gate_increment.py`
- `evaluate_mf13_tron_regime_gate_ab.py`
- `evaluate_mf14_cross_sectional_gate_increment.py`
- `evaluate_mf14_regime_gate_ab.py`
- `evaluate_post_pump_stall_cycle_increment.py`
- `evaluate_stablecoin_flow_interaction_cycle_increment.py`
- `evaluate_stablecoin_overlay_cycle_increment.py`
- `explore_btc_options_signals.py`

Implementation rule: move in small batches. Keep wrappers at old root paths for
`yes-with-wrapper` rows. For `yes` rows, prefer root wrappers only when docs or
callers still use the old root path.

### P20 - News dataset processors

Risk: low-medium. These are long-running dataset utilities, not default
research entrypoints.

Candidate target: `scripts/quant_research/news_dataset_processors/`.

- `process_cryptonewsdataset_llm.py`
- `review_cryptonewsdataset_strong_model.py`

Implementation rule: dry-run first because these can be operationally long
running and may have local artifact conventions.

### P30 - Historical legacy remnants

Risk: low-medium. These are already historical, but two were previously
deferred because docs/source references existed.

Candidate targets:

- `scripts/quant_research/legacy_candidates/phase1_factor_weighting/`
- `scripts/quant_research/legacy_candidates/v71_v83/`

Candidates:

- `phase_1c_factor_correlation_analysis.py`
- `phase_1d_dynamic_weight_schedule.py`
- `run_v83_shadow_oos.py`

Implementation rule: update surviving doc/source references in the same commit
or keep root compatibility wrappers.

### P35 - Alpha Stage-0 / quarantine candidates

Risk: medium. These are not current default entrypoints, but they are
quarantined falsification implementations and should not be mixed into
`report_writers/` or `alpha_branch_reports/`.

Candidate target: `scripts/quant_research/alpha_stage0/` or a narrower
`scripts/quant_research/m3_mf_spk_stage0/`.

Candidates:

- `audit_m3_1_options_regime_stage0.py`
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
- `evaluate_m3_3_strict_event_state_stage0.py`
- `evaluate_mf05_cross_venue_boundary_stage0.py`
- `evaluate_mf05_cross_venue_spk_stage0.py`
- `evaluate_mf07_etf_onchain_transition_falsification.py`
- `evaluate_mf07_participant_disagreement_spk_stage0.py`
- `evaluate_mf07_subday_participant_pivot_stage0.py`
- `evaluate_post_capitulation_long_replacement_stage0.py`
- `evaluate_spk_crowding_confirmation_stage0.py`
- `evaluate_spk_non_kline_confirmation_stage0.py`

Implementation rule: dry-run before moving. The target directory name must make
the quarantine boundary obvious and must not imply current admission.

### P45 - CoinGlass diagnostics

Risk: medium. These are supporting diagnostics/report writers, not provider
sync pipelines.

Candidate target: `scripts/quant_research/coinglass_diagnostics/`.

- `run_coinglass_capability_matrix.py`
- `write_coinglass_coverage_reset_report.py`

Implementation rule: keep separate from CoinGlass sync pipelines and h10d
parent historical scripts.

### P50 - Utilities support candidates

Risk: mixed. Several are support utilities, but some are runtime/bootstrap or
shadow proposal surfaces referenced by tests.

Candidate target: decide by dry-run; do not default to `maintenance/`.
Phase 5.35 moved the report/evidence writer subset to
`scripts/quant_research/report_writers/`; remaining items still require their
own target decision.
Phase 5.36 found no valid batch among the remaining four. Phase 5.37 closed
bootstrap and quantagent shadow cycle as catalog-only root-freeze decisions;
Phase 5.39 moved the OHLCV lane diagnostic implementation under
`scripts/quant_research/data_lane_diagnostics/`. Phase 5.41 closed the
workbench export root as a frozen public bridge.

`Closed: no remaining Utility Support paths.`

Implementation rule: dry-run and split into smaller semantic directories if
needed. Do not re-open the Phase 5.37 root-freeze pair unless the runtime or
shadow-cycle contracts are deliberately redesigned first. Do not re-open the
Phase 5.39 OHLCV lane diagnostic move unless the data-lane diagnostics
admission rule changes. Do not re-open the Phase 5.41 workbench export root
unless the frozen workbench bridge contract is deliberately redesigned first.

### P55 - CoinGlass quarantine

Risk: medium.

- `run_coinglass_r1a_top_liquidity_ex_trx_strict.py`
- `write_coinglass_spot_concordance_quarantine.py`

Implementation rule: do not mix with CoinGlass diagnostics or sync. Candidate
target needs a dry-run.

### P60/P75/P80 - Data foundation sync and default entrypoints

Risk: high unless proven otherwise.

These include active sync pipelines, default data-refresh entrypoints, and
provider/data foundation support tools. They require owner review before any
implementation move.

Representative groups:

- data support: `generate_versioned_panel.py`,
  `run_quant_deterministic_daily_sample.py`;
- sync pipelines: `sync_*`, `backfill_*`, and provider history sync tools;
- default entrypoints: `run_quant_coinapi_spot_sync.py`,
  `run_quant_cryptoquant_m3_2_sync_cycle.py`,
  `run_quant_deribit_options_chain_snapshot_cycle.py`,
  `run_quant_derivatives_sync_cycle.py`,
  `run_quant_stablecoin_ethereum_sync_cycle.py`,
  `run_quant_universe_freeze.py`,
  `run_quant_universe_input_producer.py`.

Implementation rule: owner review gate. If approved later, use a dedicated
`data_sync/` dry-run with scheduled/config/test reference mapping.

### P65/P80/P85 - General research-cycle surfaces

Risk: medium-high to high.

- alpha ontology runners:
  - `compute_alpha_ontology_v3_weights.py`
  - `run_alpha_ontology_horizon_cycle_oneoff.py`
  - `run_alpha_ontology_v1_cycle_oneoff.py`
- default research-cycle entrypoints:
  - `run_quant_hypothesis_batch_cycle.py`
  - `run_quant_research_cycle.py`
  - `run_quant_strategy_proposal_cycle.py`
- held out:
  - `factor_report_card.py`

Implementation rule: owner review gate for default entrypoints and
`factor_report_card.py`. Alpha ontology runners require a separate import/caller
dry-run.

### P90 - h10d boundary defer

Risk: high for this completion pass. These are intentionally not part of the
autonomous low-risk work so Phase 5.10 does not get blurred.

The defer set includes current h10d default entrypoints, promotion/baseline
surfaces, h10d historical remnants, and CoinGlass h10d-parent historical
scripts.

Implementation rule: owner review gate after non-h10d root cleanup stabilizes.

### P99 - Hard boundary keep-root

Risk: not movable in this pass.

These include scheduled wrappers, root compatibility wrappers created by
earlier phases, and scripts explicitly cataloged `safe-to-move = no`.

Implementation rule: keep root. Do not move during autonomous cleanup.

## Execution Order

1. Phase 5.11: move first P10 M3/MF/SP-K support batch, preserving root CLI and
   module-import compatibility.
2. Phase 5.12: finish the remaining P10 support batch if Phase 5.11 validates.
3. Phase 5.13: dry-run and move P30 historical legacy remnants.
4. Phase 5.14: dry-run P20 news dataset processors and P45 CoinGlass
   diagnostics separately.
5. Phase 5.15: dry-run P35 alpha stage-0 quarantine target directory.
6. Stop for owner review with P50/P55/P60/P65/P70/P75/P80/P85/P90/P99 summary.

## Verification Contract

Every implementation commit must run:

```powershell
python -m compileall -q <moved-directory> <root-wrapper-files>
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

When wrappers are present, smoke each old root path from outside the repo cwd
with `--help` or an equivalent non-mutating command.

## Completion Criteria

- Every root-level script is either:
  - moved into a semantic subdirectory with an old-path wrapper or documented
    compatibility decision;
  - classified into a deferred owner-review group;
  - cataloged `safe-to-move = no` as a public/scheduled/wrapper boundary.
- The catalog covers every script exactly once.
- README path policy lists every new target directory and every high-risk
  owner-review boundary.
- The final owner-review package contains only high-risk or intentionally
  root-stable paths.
