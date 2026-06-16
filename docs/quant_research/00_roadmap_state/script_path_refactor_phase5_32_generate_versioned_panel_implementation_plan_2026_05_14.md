# Phase 5.32 Generate Versioned Panel Implementation Plan

Date: 2026-05-14

Status: implementation plan only. This document does not move scripts, create
wrappers, rewrite imports, or change catalog rows.

Baseline: after `ef375fa Document Phase 5.31 feature panel dry run`.

## Purpose

Phase 5.32 prepares a single-script path refactor for
`scripts/quant_research/generate_versioned_panel.py`.

The target outcome is:

- move the implementation to
  `scripts/quant_research/feature_panel_tools/generate_versioned_panel.py`;
- preserve the old root CLI path with a thin wrapper at
  `scripts/quant_research/generate_versioned_panel.py`;
- keep feature-panel tooling separate from provider sync, h10d surfaces,
  report writers, and alpha stage-0/quarantine implementations.

## Approved Scope

Move exactly one implementation:

- `scripts/quant_research/generate_versioned_panel.py`

Create exactly one root compatibility wrapper:

- `scripts/quant_research/generate_versioned_panel.py`

Create exactly one target directory if it does not already exist:

- `scripts/quant_research/feature_panel_tools/`

Update supporting governance files in the same implementation commit:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `scripts/quant_research/README.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`

## Explicitly Out Of Scope

Do not move:

- `run_quant_deterministic_daily_sample.py`;
- provider sync pipelines;
- scheduled/config entrypoints;
- provider probes or diagnostics;
- report writers;
- h10d diagnostics or validation surfaces;
- alpha stage-0/quarantine scripts;
- M3.2 feature-panel builders such as `build_m3_2_feature_panel.py`.

Do not change generated feature semantics, output locations, label contracts,
provider loading, universe loading, or hypothesis-batch behavior.

## Directory Admission Rule

Use `scripts/quant_research/feature_panel_tools/` only for cross-sectional
feature-panel materializers or panel-only feature build helpers that write
canonical panel artifacts such as:

```text
artifacts/quant_research/features/.../features.csv.gz
```

This directory must not become a generic feature, data-sync, report-writing, or
M3/MF/SP-K support drawer.

## Implementation Steps

1. Create `scripts/quant_research/feature_panel_tools/`.
2. Move the current implementation from the root path into
   `feature_panel_tools/generate_versioned_panel.py`.
3. In the moved implementation, update repo-root discovery:

   ```python
   SCRIPT_DIR = Path(__file__).resolve().parent
   ROOT = SCRIPT_DIR.parents[2]
   ```

4. Keep the moved implementation's `main(argv: list[str] | None = None) -> int`
   signature and argument behavior unchanged.
5. Replace the old root file with a thin CLI wrapper that:

   - resolves the repository root from the old root script path;
   - inserts `ROOT` and `SRC` into `sys.path` if needed;
   - imports `main` from
     `scripts.quant_research.feature_panel_tools.generate_versioned_panel`;
   - forwards `sys.argv[1:]`;
   - exits through `raise SystemExit(main(sys.argv[1:]))`.

6. Do not rewrite historical docs that intentionally mention the old public CLI
   path. The root CLI path remains valid.

## Catalog Plan

Update the existing root row:

- path: `scripts/quant_research/generate_versioned_panel.py`
- category: `data_foundation_sync`
- status: `supporting`
- run priority: `supporting_tool`
- purpose: compatibility wrapper for the moved feature-panel implementation
- primary inputs: old root CLI path and forwarded CLI args
- primary outputs: delegates to moved `feature_panel_tools` implementation
- safe-to-move: `no`

Add a moved implementation row:

- path:
  `scripts/quant_research/feature_panel_tools/generate_versioned_panel.py`
- category: `data_foundation_sync`
- status: `active`
- run priority: `supporting_tool`
- purpose: generate a versioned cross-sectional feature panel without invoking
  the hypothesis-batch fast-reject / strict validation cycle
- primary inputs: provider APIs, local credentials, local warehouse state, and
  quant universe snapshots
- primary outputs:
  `artifacts/quant_research/features/.../features.csv.gz`
- related doc: `docs/quant_research/01_data_foundation/market_data_inventory.md`
- safe-to-move: `yes-with-wrapper`

Expected summary count changes after implementation:

- coverage: `278` -> `279` script files;
- Python: `259` -> `260`;
- PowerShell: unchanged at `19`;
- root-level: unchanged at `162`;
- add `1 under feature_panel_tools`;
- status `supporting`: `147` -> `148`;
- run priority `supporting_tool`: `167` -> `168`;
- safe-to-move `no`: `124` -> `125`;
- safe-to-move `yes-with-wrapper`: remains `122`;
- category `data_foundation_sync`: `34` -> `35`.

## README Plan

Update `scripts/quant_research/README.md` to:

- mention Phase 5.32 in the opening path-policy sentence;
- update coverage counts to include `1 under feature_panel_tools`;
- update `data_foundation_sync` from `34` to `35`;
- update `supporting_tool` from `167` to `168`;
- add a Path Policy bullet pointing to the Phase 5.31 dry-run and this Phase
  5.32 plan;
- add a narrow directory rule for `feature_panel_tools/`.

## Checklist Plan

Update `script_path_refactor_checklist.md` directory admission with:

- `feature_panel_tools/` is only for cross-sectional feature-panel materializers
  or panel-only feature build helpers that write canonical
  `artifacts/quant_research/features/.../features.csv.gz` outputs;
- do not move provider sync, provider diagnostics, report writers, h10d
  surfaces, alpha stage-0/quarantine scripts, scheduled entrypoints, default
  entrypoints, or M3/MF/SP-K support scripts into `feature_panel_tools/`.

## Wrapper Compatibility Requirements

The root wrapper must pass:

```powershell
python scripts\quant_research\generate_versioned_panel.py --help
```

It must also pass from outside the repository working directory:

```powershell
Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\generate_versioned_panel.py --help
Pop-Location
```

No in-repo Python caller rewrite is expected because Phase 5.31 found no
non-self Python caller. If a caller appears during implementation, stop and
rewrite it to the package path before moving forward.

## Validation Commands

Run after implementation:

```powershell
python -m compileall -q scripts\quant_research\feature_panel_tools scripts\quant_research\generate_versioned_panel.py
python scripts\quant_research\generate_versioned_panel.py --help
Push-Location $env:TEMP; python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\generate_versioned_panel.py --help; Pop-Location
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Run Markdown link checking if the implementation changes any Markdown links
instead of only backticked path text.

## Stop Conditions

Stop before implementation commit if any of these appear:

- a scheduled/config hard reference to the old file is found;
- a non-self import requires module-level compatibility beyond the CLI wrapper;
- the moved implementation cannot resolve the same repo root from its new depth;
- the catalog cannot be made one-row-per-script without stale counts;
- the directory semantics would need to include M3/MF/SP-K, provider sync, h10d,
  report-writer, or alpha stage-0 behavior.

## Recommendation

Proceed with a single Phase 5.32 implementation commit for
`generate_versioned_panel.py` only.

Keep `run_quant_deterministic_daily_sample.py` deferred to a separate
deterministic-support dry-run or root-freeze decision.
