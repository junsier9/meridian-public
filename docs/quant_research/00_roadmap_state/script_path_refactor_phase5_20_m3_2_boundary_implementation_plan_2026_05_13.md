# Phase 5.20 M3.2 Boundary Implementation Plan

`Status: approved implementation plan`
`Date: 2026-05-13`
`Scope: M3.2 boundary activation and ETF/on-chain sidecar scripts`

Owner approval: migrate the M3.2 boundary/sidecar subcluster as the first
high-risk M3 implementation batch.

## Implementation Decision

Move exactly these four implementation scripts into
`scripts/quant_research/alpha_stage0_quarantine/`:

- `evaluate_m3_2_boundary_activation_stage0.py`
- `evaluate_m3_2_boundary_activation_falsification.py`
- `evaluate_m3_2_canonical_parent_stage0.py`
- `evaluate_m3_2_etf_onchain_sidecar_falsification.py`

Keep exactly four same-name root compatibility shims under
`scripts/quant_research/`.

Do not move:

- M3.1 options-regime scripts.
- M3.3 event-state scripts.
- M3/MF/SP-K support scripts already under `m3_mf_spk_support/`.
- Data-sync, scheduled, h10d current-line, or guard surfaces.

## Target Directory Semantics

`alpha_stage0_quarantine/` remains an implementation directory for quarantined
or not-yet-admitted alpha stage-0/falsification code. M3.2 fits because this
batch is branch-specific boundary activation, canonical-parent diagnostics, and
ETF/on-chain sidecar falsification. The move does not make M3.2 a current
default entrypoint.

## Import Rewrites

Required implementation rewrites:

- `evaluate_m3_2_boundary_activation_stage0.py`
  - Set `ROOT = SCRIPT_DIR.parents[2]`.
  - Rewrite `evaluate_v5_h10d_post_pump_short_replacement` to package import:
    `from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk`.
- `evaluate_m3_2_boundary_activation_falsification.py`
  - Set `ROOT = SCRIPT_DIR.parents[2]`.
  - Rewrite stage0 import to:
    `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_stage0 as stage0`.
- `evaluate_m3_2_canonical_parent_stage0.py`
  - Set `ROOT = SCRIPT_DIR.parents[2]`.
  - Rewrite `evaluate_v5_h10d_post_pump_short_replacement` to package import:
    `from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_spk`.
- `evaluate_m3_2_etf_onchain_sidecar_falsification.py`
  - Set `ROOT = SCRIPT_DIR.parents[2]`.
  - Rewrite hardgate import to:
    `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_falsification as hardgate`.
  - Rewrite stage0 import to:
    `from scripts.quant_research.alpha_stage0_quarantine import evaluate_m3_2_boundary_activation_stage0 as stage0`.

## Root Shim Contract

Each root shim must:

- Import the moved module with `import_module`.
- Insert repo root into `sys.path` before importing.
- Re-export non-dunder public attributes with `globals().update(...)`.
- Preserve CLI behavior with `raise SystemExit(_IMPL.main())`.
- Contain no business logic.

This is module-compatible, not just CLI-compatible, because the M3.2 tests import
root module paths and future local callers may do the same.

## Docs And Catalog Updates

Update implementation links for current branch reports:

- `docs/quant_research/03_alpha_branches/m3_2_boundary_activation_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_2_full_stack_boundary_falsification.md`
- `docs/quant_research/03_alpha_branches/m3_2_etf_onchain_sidecar_falsification.md`

Do not churn historical planning docs such as
`docs/quant_research/00_roadmap_state/worktree_staging_plan_2026-05-07.md`.

Synchronize:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `scripts/quant_research/README.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_remaining_owner_review_queue_2026_05_13.md`
- `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`

Catalog semantics:

- Root shims: `supporting` / `supporting_tool` / `safe-to-move=no`.
- Moved implementations: `quarantined` / `quarantined_falsification` /
  `safe-to-move=yes-with-wrapper`.

## Validation Commands

Run all of:

```powershell
python -m compileall scripts\quant_research\alpha_stage0_quarantine scripts\quant_research -q
python -m pytest tests\test_quant_m3_2_boundary_activation_stage0.py tests\test_quant_m3_2_boundary_activation_falsification.py tests\test_quant_m3_2_canonical_parent_stage0.py tests\test_quant_m3_2_etf_onchain_sidecar_falsification.py -q
python scripts\quant_research\evaluate_m3_2_boundary_activation_stage0.py --help
python scripts\quant_research\evaluate_m3_2_boundary_activation_falsification.py --help
python scripts\quant_research\evaluate_m3_2_canonical_parent_stage0.py --help
python scripts\quant_research\evaluate_m3_2_etf_onchain_sidecar_falsification.py --help
@'
from importlib import import_module
for name in [
    "scripts.quant_research.evaluate_m3_2_boundary_activation_stage0",
    "scripts.quant_research.evaluate_m3_2_boundary_activation_falsification",
    "scripts.quant_research.evaluate_m3_2_canonical_parent_stage0",
    "scripts.quant_research.evaluate_m3_2_etf_onchain_sidecar_falsification",
]:
    import_module(name)
'@ | python -
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run a local Markdown link check for changed Markdown files.

## Completion Criteria

- Four implementation files are under `alpha_stage0_quarantine/`.
- Four root files are thin module-compatible shims.
- M3.2 sibling imports use package paths and no longer depend on execution from
  the root script directory.
- Current branch docs point implementation links to moved paths while command
  examples may still use root shims.
- Catalog coverage and README counts are truthful.
- Targeted tests, static contracts, runtime/scheduled contracts, local link
  checks, and diff checks pass.

## Deferred

- M3.1 options-regime remains deferred because of the active
  `sync_coinglass_full_stack_foundation.py` caller.
- M3.3 event-state remains deferred because it is a wider dependency hub and
  needs a separate owner-approved implementation plan.
