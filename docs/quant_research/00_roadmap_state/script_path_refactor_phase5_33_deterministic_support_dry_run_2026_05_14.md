# Phase 5.33 Deterministic Support Dry-Run

Date: 2026-05-14

Status: read-only dry-run artifact. This document does not move scripts,
create directories, create wrappers, rewrite imports, change catalog rows, or
approve an implementation commit.

Baseline: after `630d823 Move feature panel generator behind wrapper`.

## Purpose

Phase 5.33 evaluates the remaining Phase 5.30 Tier B helper:

- `scripts/quant_research/run_quant_deterministic_daily_sample.py`

The decision is whether this script should:

- move later into a dedicated `scripts/quant_research/deterministic_support/`
  directory with a root CLI wrapper; or
- be frozen permanently at root.

## Non-Movement Guarantee

No script is moved by this artifact.

No `scripts/quant_research/deterministic_support/` directory is created by this
artifact.

No catalog, README, checklist, scheduled manifest, test, config, or source-code
path is changed by this artifact.

## Read-Only Evidence

Commands used:

```powershell
git status --short
git log -5 --oneline
Get-Content scripts\quant_research\run_quant_deterministic_daily_sample.py
rg -n "run_quant_deterministic_daily_sample|deterministic_daily_sample|deterministic_support|daily sample" scripts src tests config docs -g "*.py" -g "*.ps1" -g "*.json" -g "*.md"
Select-String -Path docs\quant_research\00_roadmap_state\quant_research_script_catalog.md -Pattern 'run_quant_deterministic_daily_sample' -Context 0,2
Test-Path scripts\quant_research\deterministic_support
python scripts\quant_research\run_quant_deterministic_daily_sample.py --help
```

Findings:

- `scripts/quant_research/deterministic_support/` does not currently exist.
- `python scripts\quant_research\run_quant_deterministic_daily_sample.py --help`
  succeeds.
- No scheduled-task manifest, PowerShell runner, or config hard reference to
  the root script was found.
- No in-repo Python caller imports the root script.
- Tests and active package code use the package function
  `enhengclaw.quant_research.deterministic_survival.run_quant_deterministic_daily_sample`.
- `src/enhengclaw/quant_research/shadow_proposals.py` imports the package
  function, not the root script, when building ETH shadow-grid daily samples.
- The root script is a CLI adapter around the package function and writes the
  package result as JSON.
- The package output path is
  `artifacts/quant_research/cycles/<as_of>/deterministic_daily_sample.json`.

## Current Catalog State

Current row:

```text
scripts/quant_research/run_quant_deterministic_daily_sample.py
category = data_foundation_sync
status = active
run priority = supporting_tool
safe-to-move = yes-with-wrapper
```

This posture remains correct after the dry-run. The script is active support
surface, but not a default data-foundation entrypoint and not a scheduled path.

## Classification

`run_quant_deterministic_daily_sample.py` is a deterministic research-support
CLI.

It is not:

- a provider sync pipeline;
- a scheduled/default data-refresh entrypoint;
- a provider capability probe;
- a provider diagnostic;
- a feature-panel materializer;
- a report writer;
- an h10d validation surface;
- an alpha stage-0/quarantine implementation.

The underlying behavior belongs to the deterministic-survival support layer:

- build or read the relevant daily research-cycle context;
- sample deterministic strategy outcomes;
- write cycle-level deterministic evidence;
- expose the package result as JSON for manual inspection or downstream support.

## Root-Freeze Assessment

Do not permanently root-freeze the script at this time.

Reasons:

- the root script is not a scheduled/config/public operational contract;
- no non-self Python caller imports the root script;
- the active code path is already the package function in
  `src/enhengclaw/quant_research/deterministic_survival.py`;
- the root CLI can be preserved exactly through a thin wrapper;
- keeping it at root would preserve a misleading data-foundation placement even
  though earlier Phase 5.24/5.27/5.29 artifacts classify it as research support,
  not data sync.

Root-freeze remains available only if a later owner decision wants all
cycle-support CLIs to stay root-level for operational ergonomics.

## Directory Decision

Recommended target directory for a later implementation plan:

- `scripts/quant_research/deterministic_support/`

Admission rule:

- Use `deterministic_support/` only for deterministic sample, survival,
  longitudinal-selection, or cycle-support CLIs whose implementation delegates
  to package functions and writes deterministic cycle evidence under
  `artifacts/quant_research/cycles/...`.

Do not use `deterministic_support/` for:

- provider sync, probes, diagnostics, or leaf helpers;
- feature-panel materializers;
- report writers;
- h10d default entrypoints, guards, or validation surfaces;
- alpha stage-0/quarantine implementations;
- scheduled entrypoints;
- default research-cycle, hypothesis-batch, universe-freeze, or strategy-cycle
  public entrypoints.

## Wrapper Strategy If Approved Later

Keep the old root CLI path:

- `scripts/quant_research/run_quant_deterministic_daily_sample.py`

Move implementation to:

- `scripts/quant_research/deterministic_support/run_quant_deterministic_daily_sample.py`

Implementation notes:

- update moved implementation root discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[2]`;
- keep `main(argv: list[str] | None = None) -> int`;
- keep `_json_default` and CLI argument behavior unchanged;
- make the root wrapper thin and forward `sys.argv[1:]` to the moved `main`;
- preserve the old root CLI command exactly;
- no package caller rewrite is expected because callers already import the
  package function.

## Catalog And README Strategy If Approved Later

Catalog expectations:

- root wrapper row:
  - `category = data_foundation_sync` unless a future catalog taxonomy adds a
    more precise deterministic-support category;
  - `status = supporting`;
  - `run priority = supporting_tool`;
  - `safe-to-move = no`;
  - purpose should say it is a compatibility wrapper for the moved
    deterministic-support implementation;
- moved implementation row:
  - `category = data_foundation_sync` unless a future catalog taxonomy adds a
    more precise deterministic-support category;
  - `status = active`;
  - `run priority = supporting_tool`;
  - `safe-to-move = yes-with-wrapper`;
  - primary output should name
    `artifacts/quant_research/cycles/<as_of>/deterministic_daily_sample.json`.

Expected count changes after a later implementation:

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

README and checklist expectations:

- add `deterministic_support/` to coverage counts;
- add a Path Policy bullet pointing to this dry-run and the later
  implementation plan;
- add a narrow directory admission rule for `deterministic_support/`;
- explicitly state it does not absorb scheduled/default entrypoints, provider
  sync, feature-panel tools, h10d surfaces, report writers, or alpha
  stage-0/quarantine implementations.

## Verification Commands For A Later Implementation

Minimum commands:

```powershell
python -m compileall -q scripts\quant_research\deterministic_support scripts\quant_research\run_quant_deterministic_daily_sample.py
python scripts\quant_research\run_quant_deterministic_daily_sample.py --help
Push-Location $env:TEMP; python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\run_quant_deterministic_daily_sample.py --help; Pop-Location
python -m pytest tests\test_quant_deterministic_survival.py tests\test_quant_shadow_proposals.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

## Stop Conditions

Stop before any implementation commit if:

- a scheduled/config hard reference to the root script appears;
- an in-repo caller imports the root script rather than the package function;
- the root wrapper cannot preserve `--help` and existing CLI arguments;
- the target directory would need to include provider sync, feature-panel,
  report-writing, h10d, or stage-0 semantics;
- catalog counts cannot remain one-row-per-script.

## Recommendation

Proceed to a separate Phase 5.34 implementation plan for moving
`run_quant_deterministic_daily_sample.py` into `deterministic_support/` with a
root CLI wrapper.

Do not root-freeze it now.

Do not combine it with any other remaining root helper.
