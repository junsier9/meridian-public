# Phase 5.31 Generate Versioned Panel Feature-Panel Dry-Run

Date: 2026-05-14

Status: read-only dry-run artifact. This document does not move scripts,
rewrite imports, change catalog rows, create directories, or approve an
implementation commit.

Baseline: after `92cedba Freeze Phase 5.30 Tier B evidence cache roots`.

## Purpose

Phase 5.30 left only two data-foundation root helpers as `yes-with-wrapper`:

- `generate_versioned_panel.py`
- `run_quant_deterministic_daily_sample.py`

This dry-run focuses only on `generate_versioned_panel.py` and decides whether
it should be migrated under a dedicated `feature_panel_tools/` directory or
frozen permanently at root.

## Non-Movement Guarantee

No script is moved by this artifact.

No root wrapper is created by this artifact.

No `scripts/`, `src/`, `config/`, `tests/`, catalog row, README path policy, or
scheduled-task file is changed by this artifact.

## Read-Only Evidence

Commands used:

```powershell
git status --short
git log -5 --oneline
Get-Content scripts\quant_research\generate_versioned_panel.py
rg -n "generate_versioned_panel|feature_panel|features.csv.gz|feature-set-version|phase_1c_factor_correlation_analysis|build_quant_feature_sets" scripts src tests config docs -g "*.py" -g "*.ps1" -g "*.json" -g "*.md"
Test-Path scripts\quant_research\feature_panel_tools
python scripts\quant_research\generate_versioned_panel.py --help
```

Findings:

- `scripts/quant_research/feature_panel_tools/` does not currently exist.
- `generate_versioned_panel.py --help` succeeds.
- No non-self Python caller for `generate_versioned_panel.py` was found.
- No scheduled-task, PowerShell runner, or config hard reference was found.
- The script writes
  `artifacts/quant_research/features/<as_of>-cross-sectional-daily-1d-h5d-features-<version>/features.csv.gz`.
- The script reuses lab dataset and feature-set assembly helpers, then bypasses
  the hypothesis-batch manifest gate for panel-only materialization.
- The script references `phase_1c_factor_correlation_analysis.py` in its
  docstring as the downstream scorer, but does not import it.

## Classification

`generate_versioned_panel.py` is a feature-panel materializer, not:

- a provider sync pipeline;
- a scheduled/default data-refresh entrypoint;
- a provider capability probe;
- a provider diagnostic;
- a report writer;
- an alpha stage-0 or strict-falsification implementation;
- a current h10d public surface.

It is currently cataloged as:

- `category = data_foundation_sync`
- `status = active`
- `run priority = supporting_tool`
- `safe-to-move = yes-with-wrapper`

That catalog posture is still appropriate after this dry-run.

## Directory Decision

Recommended target directory, if a later implementation is approved:

- `scripts/quant_research/feature_panel_tools/`

Admission rule:

- Use `feature_panel_tools/` only for cross-sectional feature-panel
  materializers or panel-only feature build helpers that write canonical
  `artifacts/quant_research/features/.../features.csv.gz` panel artifacts.

Do not use `feature_panel_tools/` for:

- M3.2 on-chain panel builders such as `build_m3_2_feature_panel.py`, which are
  already governed by M3/MF/SP-K support semantics;
- feature-panel readers, analyzers, or report writers;
- provider sync, diagnostics, probes, or scheduled entrypoints;
- h10d current-line validation surfaces;
- alpha stage-0/quarantine evaluators.

## Root-Freeze Decision

Do not permanently freeze `generate_versioned_panel.py` at root at this time.

Reason:

- no hard scheduled/config reference was found;
- no non-self Python caller was found;
- `--help` already works as a narrow CLI;
- the script is semantically narrow enough to justify a dedicated feature-panel
  tools directory;
- a root CLI wrapper can preserve old command compatibility.

## Wrapper Strategy If Approved Later

Use a root CLI compatibility wrapper at:

- `scripts/quant_research/generate_versioned_panel.py`

Move implementation to:

- `scripts/quant_research/feature_panel_tools/generate_versioned_panel.py`

Implementation notes:

- adjust moved implementation root discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[2]`;
- keep the moved implementation's `main(argv: list[str] | None = None) -> int`;
- make the root wrapper thin and forward `sys.argv[1:]` to the moved `main`;
- preserve old CLI behavior exactly;
- do not rewrite historical docs unless they point to the implementation path
  rather than the public root CLI path.

## Catalog And README Strategy If Approved Later

Catalog expectations:

- root wrapper row:
  - `status = supporting`
  - `run priority = supporting_tool`
  - `safe-to-move = no`
  - purpose should say it is a compatibility wrapper;
- moved implementation row:
  - `category = data_foundation_sync` unless a future catalog taxonomy adds a
    more specific feature-panel category;
  - `status = active`
  - `run priority = supporting_tool`
  - `safe-to-move = yes-with-wrapper`.

README expectations:

- add `feature_panel_tools/` to coverage counts;
- add a Path Policy bullet that keeps the directory narrowly scoped to
  cross-sectional feature-panel materializers;
- explicitly say it does not absorb M3.2 panel builders, provider sync,
  report writers, h10d surfaces, or stage-0 evaluators.

## Verification Commands For A Later Implementation

Minimum commands:

```powershell
python -m compileall -q scripts\quant_research\feature_panel_tools scripts\quant_research\generate_versioned_panel.py
python scripts\quant_research\generate_versioned_panel.py --help
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

If the implementation also changes README counts or catalog summary counts, run:

```powershell
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
```

## Recommendation

Approve a later implementation plan for moving `generate_versioned_panel.py`
into `feature_panel_tools/` with a root CLI wrapper.

Do not combine it with `run_quant_deterministic_daily_sample.py`. That remaining
Tier B helper should receive a separate deterministic-support dry-run.
