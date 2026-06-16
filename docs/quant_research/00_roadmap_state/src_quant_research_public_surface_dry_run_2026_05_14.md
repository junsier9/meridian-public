# src quant_research Public Surface Dry-Run

`Status: S3/S4 owner-gated dry-run baseline`
`Scope: src/enhengclaw/quant_research public surfaces, reverse dependencies, loader boundaries, and legacy guardrails`
`Date: 2026-05-14`
`Mode: read-only governance artifact; no source refactor approved`

This dry-run follows the S2 manifest lifecycle catalog contract. It decides
whether the next governance step can safely move or split source files. The
answer is no: the package has broad public and private caller surfaces, mutable
loader globals, and active fail-closed legacy guardrails. Any source refactor
must be owner-gated and facade-first.

## Decision

Do not move, split, delete, or rename these root modules without a separate
owner-approved implementation plan:

- `src/enhengclaw/quant_research/features.py`
- `src/enhengclaw/quant_research/lab.py`
- `src/enhengclaw/quant_research/hypothesis_batch.py`
- `src/enhengclaw/quant_research/contracts.py`
- `src/enhengclaw/quant_research/runtime_support.py`
- `src/enhengclaw/quant_research/legacy_surface.py`
- `src/enhengclaw/quant_research/bridge.py`
- `src/enhengclaw/quant_research/bridge_contracts.py`
- `src/enhengclaw/quant_research/__init__.py`

The viable future path is facade-preserving extraction, not direct source
relocation.

## Reverse Dependency Baseline

AST scan scope: `scripts/`, `tests/`, and `src/`, covering 734 Python files with
no parse errors.

| surface | scripts direct import files | tests direct import files | src internal import files | governance read |
| --- | ---: | ---: | ---: | --- |
| `features.py` | 32 | 7 | 7 | high-risk public and private scoring surface |
| `lab.py` | 26 | 8 | 15 | orchestration/backtest facade and patch target |
| `hypothesis_batch.py` | 23 | 1 | 0 | mutable manifest/version runtime surface |
| `contracts.py` | 18 | 14 | 42 | stable shared substrate |
| `runtime_support.py` | 8 | 3 | not counted in internal baseline | runtime root/helper surface |
| `legacy_surface.py` | 2 | 2 | active internal callers | fail-closed compatibility API |
| `bridge.py` | 1 | 1 | active internal callers | frozen bridge facade |
| `bridge_contracts.py` | 1 | 2 | active internal callers | active artifact verification |

Key examples:

- package lazy root export: `scripts/quant_research/run_quant_hypothesis_batch_cycle.py`
- feature scorer import: `scripts/quant_research/alpha_branch_reports/compute_orderbook_inventory_event_study.py`
- lab private helper import: `scripts/quant_research/audit_coinglass_h10d_parent_blocker_attribution.py`
- hypothesis batch module alias and runtime patching:
  `scripts/quant_research/alpha_ontology_cycles/run_alpha_ontology_horizon_cycle_oneoff.py`
- test import of hypothesis batch:
  `tests/test_quant_hypothesis_batch.py`

## Private Imports And Patch Surface

Private `from ... import _name` occurrences found in scripts/tests:

| module | private import count | examples |
| --- | ---: | --- |
| `features.py` | 23 | `_xs_alpha_ontology_v5_h10d_base_raw_score`, `_xs_alpha_ontology_v6_h10d_spk_short_replacement_score`, `_timestamp_percentile_rank`, `_safe_rolling_skew` |
| `lab.py` | 48 | `_apply_universe_filter`, `_resolved_execution_cost_models`, `_backtest_cross_sectional`, `_chronological_split`, `_fit_and_score`, `_run_walk_forward` |
| `hypothesis_batch.py` | 16 | `_compute_hypothesis_candidate_spec_hash`, `_materialize_strict_strategy_entry` |
| `contracts.py` | 0 | no private imports found |

Private attribute access through module aliases appears 36 times, mostly as
`hb._...` in scripts/tests. High-risk examples include
`hb._feature_set_for_candidate`, `hb._select_candidate_feature_columns`,
`hb._run_fast_reject_candidate`, `hb._write_strict_results`, and test calls to
`hypothesis_batch._normalize_profile_constraints`.

Patch and assignment patterns are also broad:

- scripts contain 34 direct assignments to `hb.HYPOTHESIS_BATCH_*`,
  `hb.EXPECTED_*`, and related batch constants;
- tests contain 14 patches against `enhengclaw.quant_research.hypothesis_batch.*`;
- tests contain 18 patches against `enhengclaw.quant_research.lab.*`.

This makes `hypothesis_batch.py` especially refactor-sensitive: callers rely on
facade-visible mutable module globals, not just functions.

## Loader And Manifest Boundaries

The S2 lifecycle catalog is the source of manifest lifecycle classification,
but runtime path truth remains in code/config:

| protected file | class / stance | source of truth |
| --- | --- | --- |
| `cross_sectional_hypothesis_batch_manifest_v97.json` | `active_runtime_loaded` / `do_not_move` | `hypothesis_batch.py:HYPOTHESIS_BATCH_MANIFEST_PATH` |
| `cross_sectional_hypothesis_batch_manifest_v83.json` | `documented_static_baseline` / `do_not_move` | roadmap/archive/static historical anchor |
| `deterministic_strategy_manifest.json` | `active_runtime_loaded` / `do_not_move` | `deterministic_core.py:DETERMINISTIC_STRATEGY_MANIFEST_PATH` |
| `strategy_library_thesis_seed.json` | `source_truth` / `do_not_move` | `governance.py:THESIS_TASK_SEED_FILENAME` |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json` | `runtime_path_sensitive` / `do_not_move` | `config/quant_research/active_h10d_registry.json` |

A source refactor must not change:

- `HYPOTHESIS_BATCH_MANIFEST_PATH` or v97 hypothesis batch contract constants;
- `DETERMINISTIC_STRATEGY_MANIFEST_PATH`;
- thesis seed resolution in `governance.py`;
- active h10d registry canonical parent semantics;
- root `src/enhengclaw/quant_research/*.json` manifest locations;
- the S2 catalog separation between v97 runtime default and v83 Phase 0
  documented baseline.

## Legacy Bridge Guardrail

`legacy_surface.py`, `bridge.py`, and `bridge_contracts.py` are active
fail-closed/public-surface guardrails, not historical cleanup targets.

Current behavior:

- `legacy_surface.py` defines `legacy_quant_surface_frozen`, exit code `78`,
  `LegacyQuantSurfaceFrozenError`, `legacy_surface_summary()`, and
  `raise_legacy_surface_frozen()`.
- `bridge.py::export_passed_alphas_to_workbench()` immediately raises the
  frozen surface error for `operation="bridge_export"`; legacy workbench writes
  are intentionally unreachable.
- `bridge_contracts.py::verify_bridge_summary_contract()` still validates
  checked-in bridge artifacts and repo-health drift checks.
- project stage remains `stage_1_research_readiness_only`, where publication
  surfaces are archive-only.

Must remain import-compatible:

- `enhengclaw.quant_research.legacy_surface` constants, error type,
  `legacy_surface_summary()`, and `raise_legacy_surface_frozen()`;
- `enhengclaw.quant_research.bridge.export_passed_alphas_to_workbench(...)`
  signature and frozen behavior;
- `enhengclaw.quant_research.bridge_contracts.find_bridge_summary_paths` and
  `verify_bridge_summary_contract`;
- `scripts/quant_research/export_passed_alphas_to_workbench.py` CLI behavior:
  print frozen JSON and return exit code `78`.

Do not add `export_passed_alphas_to_workbench` to package-root `__all__`; the
runtime contract expects it not to be exported from `enhengclaw.quant_research`.

## Facade-First Refactor Strategy

If an owner later approves source refactor, use this strategy:

- keep current root modules as compatibility facades;
- extract implementation into internal modules only after import/patch
  compatibility tests exist;
- preserve current public names, private aliases used by scripts/tests, runtime
  roots, mutable `hypothesis_batch` globals, and CLI behavior;
- avoid replacing mutable module globals with an internal config object unless
  the facade still reflects assignments made by existing callers;
- split one surface at a time and keep each implementation commit small.

## Not Approved

This dry-run does not approve:

- moving or deleting source modules;
- moving root manifests;
- changing loader constants;
- changing package lazy exports;
- deleting unreachable legacy bridge implementation code;
- thawing the frozen bridge;
- adding new package-root exports;
- rewriting scripts/tests to stop using private imports.

## Required Evidence Before Any Implementation

Any future implementation plan must include:

- AST import report for target modules;
- list of direct script/test callers;
- list of private imports and module-alias private attribute accesses;
- list of monkey-patch or assignment targets;
- loader/path-sensitive files touched or explicitly not touched;
- compatibility shim/facade plan;
- targeted validation commands and expected pass/fail semantics.

## Validation Matrix

Minimum before source refactor implementation:

```powershell
python -m compileall -q src scripts tests
python -m pytest tests\test_static_contracts.py tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py tests\test_quant_research_lab.py tests\test_quant_research_core.py tests\test_quant_gap_remediation.py -q
python -m pytest tests\test_derivatives_quality.py tests\test_feature_admission.py tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
python -m pytest tests\test_quant_m3_3_strict_event_state_scorer.py tests\test_quant_m3_3_hype_chatter_gate_stage0.py tests\test_stablecoin_flow_interaction_scores.py -q
git diff --check
git status --short
```

For loader/manifest-only review, use the narrower S2 matrix from
`src_quant_research_manifest_lifecycle_catalog_dry_run_2026_05_14.md`.

## Next Gate

The next actionable step is not a move. It is an owner decision on whether to
fund a facade-compatibility test layer for one target surface. The safest first
candidate, if any, is a read-only compatibility contract around
`hypothesis_batch.py` mutable globals and private helper imports; no extraction
should start until that contract exists and passes.
