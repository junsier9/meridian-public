# Phase 5 Parallel 1h Script Path Refactor Dry-Run Review

`Date: 2026-05-13`
`Baseline commit: 649c509 quant research doc governance static contract`
`Scope: pre-Phase-5 script-path dry-run only`
`Mutation policy: no script moves, no import rewrites, no artifact moves`
`Follow-up: Phase 5 implementation executed after this dry-run; keep observed baseline below as pre-move evidence`

## Decision

The `parallel_1h` move remains the next lowest-risk script-path refactor path,
but only if it is executed as a cohesive package move:

- move all 23 `parallel_1h` implementation scripts into
  `scripts/quant_research/parallel_1h/`
- keep root-level wrappers for the 3 roadmap-visible entrypoints
- rewrite sibling imports and root-path calculations in the same change
- update the script catalog, README counts, and documented smoke commands in
  the same change

A 20-file-only move is not the lowest-risk next step. It would leave the lane
split across root and `parallel_1h/`, increasing import ambiguity without
meaningfully reducing public-entrypoint risk.

## Dry-Run Inputs

Commands used for this refresh:

```powershell
git status --short
git log -1 --oneline
Get-ChildItem -Path scripts\quant_research -File -Filter '*parallel_1h*.py'
rg -n "parallel_1h" config tests src -g "*.py" -g "*.toml" -g "*.yaml" -g "*.yml" -g "*.json"
rg -n "from (audit|build|evaluate|simulate|validate)_parallel_1h|import (audit|build|evaluate|simulate|validate)_parallel_1h|import scripts\.quant_research\.evaluate_parallel_1h" scripts\quant_research -g "*parallel_1h*.py"
rg -n "SCRIPT_DIR|parents\[|ROOT =|REPO_ROOT" scripts\quant_research -g "*parallel_1h*.py"
rg -n "scripts/quant_research/.+parallel_1h.+\.py|scripts\\quant_research\\.+parallel_1h.+\.py" config docs scripts src tests -g "!docs/quant_research/00_roadmap_state/quant_research_script_catalog.md" -g "!scripts/quant_research/README.md"
```

Observed baseline:

- working tree was clean before this dry-run artifact
- latest commit was `649c509 quant research doc governance static contract`
- current `scripts/quant_research` has 23 root-level `*parallel_1h*.py` files
- current script catalog marks 20 as `safe-to-move = yes`
- current script catalog marks 3 as `safe-to-move = yes-with-wrapper`
- `scripts/quant_research/parallel_1h/` does not yet exist

## Current Inventory

Target implementation directory:

```text
scripts/quant_research/parallel_1h/
```

Implementation files to move as a group:

| Current file | Move mode |
| --- | --- |
| `scripts/quant_research/audit_parallel_1h_fake_liquidity_parent_symbol_provider_sensitivity.py` | move implementation |
| `scripts/quant_research/audit_parallel_1h_native_exchange_flow_sidecar.py` | move implementation, keep wrapper |
| `scripts/quant_research/audit_parallel_1h_venue_concentration_sidecar.py` | move implementation |
| `scripts/quant_research/build_parallel_1h_stage0_decision_ledger.py` | move implementation |
| `scripts/quant_research/build_parallel_1h_trust_masked_venue_concentration_sidecar.py` | move implementation, keep wrapper |
| `scripts/quant_research/build_parallel_1h_venue_concentration_sidecar.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_fake_liquidity_atomic_decomposition.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_fake_liquidity_capacity_atoms_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_fake_liquidity_capacity_haircut_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_funding_normalization_after_deep_negative_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_funding_settlement_squeeze_window_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_liquidation_cluster_aftershock_veto_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_low_float_squeeze_trap_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_low_liquidity_hour_kill_switch_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_post_pump_bid_replenishment_failure_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_post_squeeze_exit_short_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_short_liquidation_completion_cooldown_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_top_trader_fade_retail_chase_veto_stage0.py` | move implementation |
| `scripts/quant_research/evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py` | move implementation, keep wrapper |
| `scripts/quant_research/simulate_parallel_1h_fake_liquidity_age_gated_parent_interaction.py` | move implementation |
| `scripts/quant_research/simulate_parallel_1h_fake_liquidity_age_sidecar.py` | move implementation |
| `scripts/quant_research/simulate_parallel_1h_fake_liquidity_parent_interaction.py` | move implementation |
| `scripts/quant_research/validate_parallel_1h_venue_volume_concordance.py` | move implementation |

Root wrappers to keep:

- `scripts/quant_research/audit_parallel_1h_native_exchange_flow_sidecar.py`
- `scripts/quant_research/build_parallel_1h_trust_masked_venue_concentration_sidecar.py`
- `scripts/quant_research/evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py`

## Reference Findings

Strong external code/config references:

- `config`: none found
- `src`: none found
- `tests`: no direct script-path references; only
  `tests/test_static_contracts.py` recognizes `parallel_1h` as an indexed docs
  ownership layer

Markdown references that must be synchronized in the actual move:

- `docs/quant_research/04_parallel_1h/parallel_1h_alpha_mining_roadmap.md`
  references the 3 wrapper entrypoints.
- `docs/quant_research/00_roadmap_state/parallel_1h_import_rewrite_strategy_2026_05_13.md`
  documents the wrapper commands and target package path.
- `docs/quant_research/00_roadmap_state/script_path_refactor_dry_run_phase2a_2026_05_12.md`
  records the earlier 20-file safe-to-move table and the 3 wrapper candidates.
- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
  contains all 23 script rows and must be updated atomically with the move.
- `scripts/quant_research/README.md` contains script inventory counts and
  should be updated with the new subdirectory count.

## Import And Path Risks

Sibling import scan found 25 import statements that must be rewritten during
the move:

- 23 bare sibling imports such as
  `import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval`
- 2 current fully qualified root imports in
  `evaluate_parallel_1h_low_liquidity_hour_kill_switch_stage0.py`

Required target import style:

```python
from scripts.quant_research.parallel_1h import evaluate_parallel_1h_low_float_squeeze_trap_stage0 as trap_eval
```

Root-path scan found 22 files with `SCRIPT_DIR`, `ROOT`, or `REPO_ROOT`
calculations tied to the current root-level location. After moving into
`scripts/quant_research/parallel_1h/`, implementation files need their
repository-root calculation refreshed. Wrapper files should remain thin and
should not duplicate the implementation root/path logic.

## Risk Rating

| Candidate | Risk | Dry-run decision |
| --- | --- | --- |
| Move 20 `safe-to-move = yes` scripts only | medium | defer; split-lane imports are avoidable risk |
| Move all 23 implementations and keep 3 wrappers | low-medium | recommended next batch |
| Move wrapper-visible root scripts without wrappers | high | do not do this |
| Move scheduled/default h10d or active data scripts next | medium-high | defer until parallel 1h package proves the pattern |
| Refactor utility/shared scripts next | medium | defer; broader blast radius |

## Actual Move Contract

Allowed in the next Phase 5 implementation batch:

- create `scripts/quant_research/parallel_1h/`
- move the 23 implementation files into that directory
- add `scripts/quant_research/parallel_1h/__init__.py` if needed for stable
  package imports
- leave the 3 root wrappers listed above
- rewrite all 25 sibling import statements
- fix root-path calculations in moved implementation files
- update script catalog paths and `safe-to-move` values
- update relevant Markdown references and README inventory counts

Forbidden in that batch:

- do not move artifacts
- do not move scheduled manifests
- do not refactor unrelated h10d, provider, or shared utility scripts
- do not change research conclusions or promotion state
- do not remove historical docs
- do not mix runtime behavior changes with the path refactor

Dry-run first if any additional direct references appear in `config`, `tests`,
`src`, scheduled manifests, or automation metadata.

## Validation Commands For The Actual Move

Run after the implementation batch:

```powershell
python -m compileall -q scripts\quant_research\parallel_1h
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
python scripts\quant_research\audit_parallel_1h_native_exchange_flow_sidecar.py --help
python scripts\quant_research\build_parallel_1h_trust_masked_venue_concentration_sidecar.py --help
python scripts\quant_research\evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py --help
git diff --check
```

Also re-run the local Markdown link checker because the script catalog and
roadmap contain relative links that will change.

## Deferred

- No scripts were moved in this dry-run.
- No imports were rewritten in this dry-run.
- No catalog rows were changed in this dry-run.
- The actual Phase 5 batch followed this dry-run as a dedicated commit after
  the move and validations passed.
