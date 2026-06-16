# Phase 5.34 Deterministic Support Implementation Plan

Date: 2026-05-14

Status: implementation plan only. This document does not move scripts, create
wrappers, rewrite imports, or change catalog rows.

Baseline: after `4df2226 Document Phase 5.33 deterministic support dry run`.

## Purpose

Phase 5.34 prepares a single-script path refactor for:

- `scripts/quant_research/run_quant_deterministic_daily_sample.py`

The target outcome is:

- move the implementation to
  `scripts/quant_research/deterministic_support/run_quant_deterministic_daily_sample.py`;
- preserve the old root CLI path with a thin wrapper at
  `scripts/quant_research/run_quant_deterministic_daily_sample.py`;
- keep deterministic cycle-support tooling separate from provider sync,
  feature-panel tools, scheduled/default entrypoints, h10d surfaces, report
  writers, and alpha stage-0/quarantine implementations.

## Approved Scope

Move exactly one implementation:

- `scripts/quant_research/run_quant_deterministic_daily_sample.py`

Create exactly one root compatibility wrapper:

- `scripts/quant_research/run_quant_deterministic_daily_sample.py`

Create exactly one target directory if it does not already exist:

- `scripts/quant_research/deterministic_support/`

Update supporting governance files in the same implementation commit:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `scripts/quant_research/README.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`

## Explicitly Out Of Scope

Do not move:

- provider sync pipelines;
- scheduled/config entrypoints;
- default research-cycle, hypothesis-batch, universe-freeze, or strategy-cycle
  public entrypoints;
- provider probes or diagnostics;
- feature-panel materializers;
- report writers;
- h10d diagnostics, guards, or validation surfaces;
- alpha stage-0/quarantine scripts.

Do not change deterministic-survival behavior, package APIs, sample selection,
artifact schema, output paths, or exception handling semantics.

Do not rewrite package callers unless a new in-repo root-script import appears
during implementation. Current callers import the package function, not the
root script.

## Directory Admission Rule

Use `scripts/quant_research/deterministic_support/` only for deterministic
sample, survival, longitudinal-selection, or cycle-support CLIs whose
implementation delegates to package functions and writes deterministic cycle
evidence under:

```text
artifacts/quant_research/cycles/...
```

This directory must not become a generic data-foundation, provider, h10d,
report-writing, or alpha-quarantine drawer.

## Implementation Steps

1. Create `scripts/quant_research/deterministic_support/`.
2. Move the current implementation from the root path into
   `deterministic_support/run_quant_deterministic_daily_sample.py`.
3. In the moved implementation, update repo-root discovery:

   ```python
   SCRIPT_DIR = Path(__file__).resolve().parent
   ROOT = SCRIPT_DIR.parents[2]
   ```

4. Keep the moved implementation's `main(argv: list[str] | None = None) -> int`
   signature and argument behavior unchanged.
5. Preserve `_json_default`, `traceback` handling, printed JSON shape, and all
   CLI options.
6. Replace the old root file with a thin CLI wrapper that:

   - resolves the repository root from the old root script path;
   - inserts `ROOT` and `SRC` into `sys.path` if needed;
   - imports `main` from
     `scripts.quant_research.deterministic_support.run_quant_deterministic_daily_sample`;
   - forwards `sys.argv[1:]`;
   - exits through `raise SystemExit(main(sys.argv[1:]))`.

7. Do not rewrite historical docs that intentionally mention the old public CLI
   path. The root CLI path remains valid.

## Catalog Plan

Update the existing root row:

- path: `scripts/quant_research/run_quant_deterministic_daily_sample.py`
- category: `data_foundation_sync`
- status: `supporting`
- run priority: `supporting_tool`
- purpose: compatibility wrapper for the moved deterministic-support
  implementation
- primary inputs: old root CLI path and forwarded CLI args
- primary outputs: delegates to moved `deterministic_support` implementation
- related doc: `docs/quant_research/01_data_foundation/market_data_inventory.md`
- safe-to-move: `no`

Add a moved implementation row:

- path:
  `scripts/quant_research/deterministic_support/run_quant_deterministic_daily_sample.py`
- category: `data_foundation_sync` unless a future catalog taxonomy adds a more
  precise deterministic-support category
- status: `active`
- run priority: `supporting_tool`
- purpose: run one deterministic daily sample for longitudinal survival
  tracking
- primary inputs: quant input snapshots, workbench state, provider-derived
  local artifacts, and cycle context
- primary outputs:
  `artifacts/quant_research/cycles/<as_of>/deterministic_daily_sample.json`
- related doc: `docs/quant_research/01_data_foundation/market_data_inventory.md`
- safe-to-move: `yes-with-wrapper`

Expected summary count changes after implementation:

- coverage: `279` -> `280` script files;
- Python: `260` -> `261`;
- PowerShell: unchanged at `19`;
- root-level: unchanged at `162`;
- add `1 under deterministic_support`;
- status `supporting`: `148` -> `149`;
- run priority `supporting_tool`: `168` -> `169`;
- safe-to-move `no`: `125` -> `126`;
- safe-to-move `yes-with-wrapper`: remains `122`;
- category `data_foundation_sync`: `35` -> `36`.

## README Plan

Update `scripts/quant_research/README.md` to:

- mention Phase 5.34 in the opening path-policy sentence;
- update coverage counts to include `1 under deterministic_support`;
- update `data_foundation_sync` from `35` to `36`;
- update `supporting_tool` from `168` to `169`;
- add a Path Policy bullet pointing to the Phase 5.33 dry-run and this Phase
  5.34 plan;
- add a narrow directory rule for `deterministic_support/`.

## Checklist Plan

Update `script_path_refactor_checklist.md` directory admission with:

- `deterministic_support/` is only for deterministic sample, survival,
  longitudinal-selection, or cycle-support CLIs that delegate to package
  functions and write deterministic cycle evidence under
  `artifacts/quant_research/cycles/...`;
- do not move provider sync, provider diagnostics, feature-panel materializers,
  report writers, h10d surfaces, alpha stage-0/quarantine scripts, scheduled
  entrypoints, default entrypoints, or public research-cycle entrypoints into
  `deterministic_support/`.

## Wrapper Compatibility Requirements

The root wrapper must pass:

```powershell
python scripts\quant_research\run_quant_deterministic_daily_sample.py --help
```

It must also pass from outside the repository working directory:

```powershell
Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\run_quant_deterministic_daily_sample.py --help
Pop-Location
```

The moved implementation may also be smoke-tested directly:

```powershell
python scripts\quant_research\deterministic_support\run_quant_deterministic_daily_sample.py --help
```

No in-repo Python caller rewrite is expected because Phase 5.33 found package
callers using `enhengclaw.quant_research.deterministic_survival`, not the root
script. If an implementation-time scan finds a root-script import, stop and
choose either a package-import rewrite or a module-compatible root shim before
moving forward.

## Validation Commands

Run after implementation:

```powershell
python -m compileall -q scripts\quant_research\deterministic_support scripts\quant_research\run_quant_deterministic_daily_sample.py
python scripts\quant_research\run_quant_deterministic_daily_sample.py --help
Push-Location $env:TEMP; python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\run_quant_deterministic_daily_sample.py --help; Pop-Location
python scripts\quant_research\deterministic_support\run_quant_deterministic_daily_sample.py --help
python -m pytest tests\test_quant_deterministic_survival.py tests\test_quant_shadow_proposals.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Run Markdown link checking if the implementation changes any Markdown links
instead of only backticked path text.

## Stop Conditions

Stop before implementation commit if any of these appear:

- a scheduled/config hard reference to the old root file is found;
- an in-repo caller imports the root script rather than the package function;
- the root wrapper cannot preserve `--help` and the existing CLI arguments;
- the moved implementation cannot resolve the same repo root from its new
  depth;
- the catalog cannot be made one-row-per-script without stale counts;
- the target directory would need to include provider sync, feature-panel, h10d,
  report-writing, stage-0, or public research-cycle behavior.

## Recommendation

Proceed with a single Phase 5.34 implementation commit for
`run_quant_deterministic_daily_sample.py` only.

Do not combine it with any other remaining root helper.
