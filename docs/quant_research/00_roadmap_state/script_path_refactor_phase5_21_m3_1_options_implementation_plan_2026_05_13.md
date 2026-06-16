# Phase 5.21 M3.1 Options Dry-Run And Implementation Plan

`Status: dry-run implementation plan`
`Date: 2026-05-13`
`Scope: M3.1 options-regime stage0 and options-volume veto falsification`

This artifact is a plan only. It does not move scripts. It resolves the active
caller strategy for the M3.1 options cluster before any implementation commit.

## Decision

M3.1 can be migrated as the next high-risk alpha-stage0 quarantine batch, but
only with module-compatible root shims and an explicit active caller policy.

Recommended implementation strategy:

- Move exactly two M3.1 implementations into
  `scripts/quant_research/alpha_stage0_quarantine/`.
- Keep exactly two root shims at the old paths.
- Do not rewrite `sync_coinglass_full_stack_foundation.py` in the first
  migration commit.
- Require the root shim for `audit_m3_1_options_regime_stage0.py` to re-export
  `_fetch_options_payloads` and `_build_options_panel`, because the active sync
  caller imports those names directly.

Rationale: `sync_coinglass_full_stack_foundation.py` is an active data
foundation surface. Keeping its existing import path stable minimizes behavior
change in the same commit. A later extraction of the options-panel builder into
`src/enhengclaw/quant_research/` can remove the active caller's dependency on a
quarantined alpha-stage0 module, but that is a separate refactor, not a
script-path move.

## Candidate Scripts

Move in one batch:

- `scripts/quant_research/audit_m3_1_options_regime_stage0.py`
- `scripts/quant_research/evaluate_m3_1_options_volume_shock_veto_falsification.py`

Do not move in Phase 5.21:

- M3.2 scripts already migrated in Phase 5.20.
- M3.3 event-state scripts.
- Deribit provider probes under `provider_probes/`.
- `sync_coinglass_full_stack_foundation.py`.
- Scheduled runners, data-sync pipelines, h10d current-line surfaces, guards,
  or default research-cycle entrypoints.

## Active Caller Strategy

Active caller:

- `scripts/quant_research/sync_coinglass_full_stack_foundation.py`

Current import:

```python
from scripts.quant_research.audit_m3_1_options_regime_stage0 import (
    _build_options_panel,
    _fetch_options_payloads,
)
```

Call site:

- `_write_options_panel()` calls `_fetch_options_payloads()`.
- `_write_options_panel()` calls `_build_options_panel(...)`.

Phase 5.21 strategy:

- Keep this import unchanged during the script move.
- Make the old root path a module-compatible re-export shim, not a CLI-only
  wrapper.
- Validate the active caller with an import smoke that imports
  `sync_coinglass_full_stack_foundation.py` and imports the two named helpers
  through the old root path.

Rejected for the first implementation commit:

- Rewriting the active caller directly to
  `scripts.quant_research.alpha_stage0_quarantine.audit_m3_1_options_regime_stage0`.

Reason: that would make an active data-foundation pipeline explicitly import a
quarantined alpha-stage0 implementation. The hidden dependency already exists,
but the first migration should preserve public path compatibility and avoid
semantic expansion. Direct import rewrite or helper extraction belongs in a
separate, data-foundation-aware follow-up.

## Import Rewrite Plan

### `audit_m3_1_options_regime_stage0.py`

When moved to `alpha_stage0_quarantine/`:

- Set `ROOT = SCRIPT_DIR.parents[2]`.
- Keep `SRC = ROOT / "src"`.
- Rewrite:

```python
import evaluate_v5_h10d_post_pump_short_replacement as v5_eval
```

to:

```python
from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_eval
```

### `evaluate_m3_1_options_volume_shock_veto_falsification.py`

When moved to `alpha_stage0_quarantine/`:

- Set `ROOT = SCRIPT_DIR.parents[2]`.
- Keep `SRC = ROOT / "src"`.
- Rewrite:

```python
import audit_m3_1_options_regime_stage0 as stage0
```

to:

```python
from scripts.quant_research.alpha_stage0_quarantine import audit_m3_1_options_regime_stage0 as stage0
```

## Root Shim Contract

Both old root paths must remain as same-name compatibility shims under
`scripts/quant_research/`.

Required properties:

- Import the moved implementation with `import_module`.
- Insert repo root into `sys.path` before importing.
- Re-export all non-dunder names with `globals().update(...)`.
- Preserve CLI behavior with `raise SystemExit(_IMPL.main())`.
- Contain no business logic.

Specific active-caller requirement:

- `scripts/quant_research/audit_m3_1_options_regime_stage0.py` must re-export
  `_build_options_panel` and `_fetch_options_payloads`.
- Do not add an `__all__` filter that drops single-underscore helpers.

## Docs And Catalog Updates

Update current branch-report implementation links:

- `docs/quant_research/03_alpha_branches/m3_1_options_regime_r8_stage0.md`
- `docs/quant_research/03_alpha_branches/m3_1_options_volume_shock_veto_falsification.md`

Do not churn historical planning docs such as
`docs/quant_research/00_roadmap_state/worktree_staging_plan_2026-05-07.md`.

Synchronize if implementation proceeds:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `scripts/quant_research/README.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_remaining_owner_review_queue_2026_05_13.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`

Catalog semantics:

- Root shims: `supporting` / `supporting_tool` / `safe-to-move=no`.
- Moved implementations: `quarantined` / `quarantined_falsification` /
  `safe-to-move=yes-with-wrapper`.

Projected post-implementation counts if this plan is executed:

- total script files: `268`;
- Python files: `249`;
- PowerShell files: `19`;
- root-level files: `162`;
- `alpha_stage0_quarantine/`: `16`;
- root compatibility wrappers: `79`;
- remaining root implementation files with `safe-to-move != no`: `64`.

## Validation Commands

Run all of these after any later implementation commit:

```powershell
python -m compileall scripts\quant_research\alpha_stage0_quarantine scripts\quant_research -q
python -m pytest tests\test_quant_m3_1_options_regime_stage0.py tests\test_quant_m3_1_options_volume_shock_veto_falsification.py -q
python -m pytest tests\test_quant_coinglass_full_stack_foundation.py -q
python scripts\quant_research\audit_m3_1_options_regime_stage0.py --help
python scripts\quant_research\evaluate_m3_1_options_volume_shock_veto_falsification.py --help
@'
from importlib import import_module
from scripts.quant_research.audit_m3_1_options_regime_stage0 import (
    _build_options_panel,
    _fetch_options_payloads,
)

assert callable(_build_options_panel)
assert callable(_fetch_options_payloads)
import_module("scripts.quant_research.sync_coinglass_full_stack_foundation")
import_module("scripts.quant_research.evaluate_m3_1_options_volume_shock_veto_falsification")
print("m3_1 active caller imports ok")
'@ | python -
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the local Markdown link checker for changed Markdown files.

## Completion Criteria

- Two M3.1 implementations are under `alpha_stage0_quarantine/`.
- Two old root paths are thin module-compatible shims.
- `sync_coinglass_full_stack_foundation.py` imports continue to work unchanged.
- `_fetch_options_payloads` and `_build_options_panel` are importable from the
  old root path.
- M3.1 branch docs point implementation links to the moved paths while command
  examples may keep using root shims.
- M3.3 remains deferred and no event-state script moves in this phase.
- Targeted tests, active caller smoke, static contracts, runtime/scheduled
  contracts, link checks, and diff checks pass.

## Deferred

- Direct rewrite of `sync_coinglass_full_stack_foundation.py` to import from the
  moved package path.
- Extraction of CoinGlass options-panel helpers into a data-foundation module.
- M3.3 event-state migration.
