# Phase 5.43 Owner-Gated High-Risk Root Review

`Status: read-only review baseline`
`Date: 2026-05-14`
`Scope: remaining scripts/quant_research root yes-with-wrapper boundary`

## Decision

No implementation is approved by this artifact.

After the Phase 5.42 autonomous closure, the remaining root
`safe-to-move = yes-with-wrapper` paths are not low-risk cleanup candidates.
They are public entrypoints, active h10d proof surfaces, data-foundation
boundaries, module-import-dependent historical evidence, or broad research
cycle/report-card interfaces.

The correct next posture is owner selection, not another autonomous move.

## Evidence Commands

Read-only commands used for this review:

```powershell
git status --short
Get-Content docs\quant_research\00_roadmap_state\script_path_refactor_phase5_42_autonomous_closure_2026_05_14.md
Select-String -Path docs\quant_research\00_roadmap_state\quant_research_script_catalog.md -Pattern '<remaining root names>'
rg -n --glob '!artifacts/**' '<remaining root names>' config docs scripts src tests
Get-Content config\quant_research\active_h10d_registry.json
Get-Content scripts\quant_research\README.md
Get-Content docs\quant_research\00_roadmap_state\script_path_refactor_checklist.md
```

Current worktree boundary at review time: only local untracked generated
artifacts under `artifacts/quant_research/...` plus this read-only governance
artifact work. The generated artifacts remain outside versioned governance.

## Group Classification

### Permanent Keep-Root Unless Owner Redesigns The Public Surface

These should not receive an implementation plan under the normal Phase 5.x
path-cleanup flow.

#### Research-cycle default/manual surfaces

- `run_quant_hypothesis_batch_cycle.py`
- `run_quant_research_cycle.py`
- `run_quant_strategy_proposal_cycle.py`

Reason: these are default manual or automation-adjacent public paths. Evidence:
`docs/QUANT_RESEARCH_LAB.md`, `scripts/quant_research/README.md`, package tests,
and scheduled/runner-adjacent PowerShell references all treat these as public
execution boundaries. Moving them would require a research-cycle interface
redesign, not a wrapper cleanup.

#### Current h10d public/default surfaces

- `analyze_binance_pit_drawdown_attribution.py`
- `assert_h10d_promotion_evidence.py`
- `build_binance_hv_balanced_anti_overfit_package.py`
- `run_baseline_alpha_proof.py`
- `run_baseline_alpha_survival.py`
- `run_binance_canonical_h10d_validation.py`
- `run_binance_spot_concordance_baseline.py`
- `validate_baseline_alpha_confidence.py`

Reason: these anchor current Binance PIT / h10d validation, proof, promotion
evidence, and baseline confidence. Evidence:
`config/quant_research/active_h10d_registry.json` hard-references
`assert_h10d_promotion_evidence.py`; current h10d docs call
`run_binance_canonical_h10d_validation.py`; `tests/test_quant_baseline_alpha_confidence.py`
imports `validate_baseline_alpha_confidence` from the root script path. These
are public h10d surfaces, not diagnostics.

#### CoinGlass data-foundation/default boundary

- `run_quant_coinglass_spot_sync.py`
- `sync_coinglass_etf_onchain_participant_sidecars.py`
- `sync_coinglass_full_stack_foundation.py`
- `sync_coinglass_oi_provenance_sidecar.py`

Reason: these sit at the CoinGlass data-foundation and sidecar boundary. They
must not be absorbed by `provider_probes/`, `provider_diagnostics/`,
`provider_leaf_sync_helpers/`, or `coinglass_quarantine/`. A future internal
split would need an owner-approved data-foundation redesign and root public
wrappers.

## Owner-Gated Dry-Run Candidates

These are not approved to move. They are only the least-bad candidates if the
owner explicitly wants a next dry-run.

### Candidate A: alpha ontology cycle support

- `compute_alpha_ontology_v3_weights.py`
- `run_alpha_ontology_horizon_cycle_oneoff.py`
- `run_alpha_ontology_v1_cycle_oneoff.py`

Risk: medium-high.

Reason: this is the narrowest remaining semantic cluster. The one-off runners
patch `hypothesis_batch` and sometimes validation-contract module constants at
runtime; `threshold_provenance.md` documents that behavior. If approved, the
dry-run should evaluate a dedicated target such as
`scripts/quant_research/alpha_ontology_cycles/`, root CLI wrappers, and whether
`compute_alpha_ontology_v3_weights.py` belongs with cycle runners or should
stay root because it writes checked-in config.

Required before implementation:

- inspect all docs that mention alpha ontology one-off cycles;
- inspect imports/callers for root-module assumptions;
- decide whether checked-in config generation is allowed behind a wrapper;
- run wrapper `--help` smoke tests from outside repo cwd;
- run `tests/test_quant_hypothesis_batch.py`, static contracts, and diff checks.

### Candidate B: historical h10d dependent trio

- `evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `evaluate_v6_h10d_post_pump_short_replacement.py`

Risk: high.

Reason: this is historical evidence, but it has root-module dependencies:
`evaluate_v6_h10d_post_pump_news_veto_ab.py` imports
`evaluate_v6_h10d_post_pump_short_replacement` as `base_eval`, and
`evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py` imports both the
news veto and base replacement modules by root module name. A CLI-only wrapper
would be insufficient.

Required before implementation:

- move only as a dependent trio;
- use module-compatible root re-export shims or package-import rewrites;
- keep catalog status historical / do-not-start-here;
- do not place them in `h10d_current_diagnostics/`;
- run compile, root import smoke, root CLI help/smoke, and targeted h10d tests.

### Candidate C: CoinGlass h10d-parent historical evidence

- `audit_coinglass_h10d_parent_blocker_attribution.py`
- `audit_coinglass_h10d_parent_fast_reject_stages.py`
- `run_coinglass_h10d_parent_frozen_reset_strict.py`

Risk: high.

Reason: these are historical / strict h10d-parent evidence at the CoinGlass
boundary. They are not provider diagnostics and not current h10d diagnostics.
The target directory is not yet approved. Candidate target names would need to
avoid expanding `coinglass_diagnostics/` or `historical_h10d_diagnostics/`.

Required before implementation:

- choose a specific target name that preserves h10d-parent evidence semantics;
- verify no current docs treat them as current-line entrypoints;
- preserve root wrappers or module-compatible shims;
- update h10d/CoinGlass docs and catalog without making them current starts.

### Candidate D: factor report-card surface

- `factor_report_card.py`

Risk: medium-high.

Reason: mechanically it resembles a report writer, but semantically it is the
central 11-gate factor-admission/report-card surface. Moving it into
`report_writers/` may incorrectly make the current factor-report authority look
like a generic writer. It needs a dedicated caller/import and docs-authority
review before choosing a target.

Required before implementation:

- inspect all docs that cite factor report-card authority;
- decide whether `report_writers/` is semantically acceptable;
- preserve root CLI compatibility;
- run targeted factor-report smoke tests plus static contracts.

## Explicit Non-Candidates

Do not write an implementation plan for these without a new owner decision:

- research-cycle default/manual surfaces;
- active h10d public/default surfaces;
- CoinGlass data-foundation/default sync and sidecar paths.

Do not create a generic `utility/`, `misc/`, `tools/`, or `support/` directory
to absorb these paths.

## Recommended Next Owner Choice

The lowest-risk next review is Candidate A, a read-only alpha ontology cycle
support dry-run. It is narrow, three files, and has a clear semantic boundary.
It is still not an automatic move because the runners monkey-patch active
hypothesis-batch module constants and one script writes checked-in config.

If the owner wants to reduce high-risk root clutter without touching active
surfaces, Candidate B is the next alternative, but it must be treated as a
dependent historical h10d trio with module-compatible shims.

## Verification For This Artifact

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```
