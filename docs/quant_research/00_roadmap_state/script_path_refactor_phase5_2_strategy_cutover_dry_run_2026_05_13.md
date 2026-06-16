# Phase 5.2 Strategy Cutover Maintenance Script Path Refactor Dry-Run

`Date: 2026-05-13`
`Baseline commit: 7a5467e Phase 5.1 maintenance script path refactor`
`Scope: dry-run plus implementation in the same repair batch`
`Checklist: script_path_refactor_checklist.md`
`Decision: final low-risk maintenance cleanup batch`

## Decision

Move `run_quant_strategy_library_thesis_cutover.py` into
`scripts/quant_research/maintenance/` and keep the old root path as a
compatibility wrapper.

This is the last low-risk maintenance candidate found by the post-Phase-5.1
scan. It is a legacy strategy-library cutover/repair script, has no direct
`config`, `scripts`, `src`, or `tests` references, and can keep historical
runbook commands valid through a wrapper.

## Dry-Run Inputs

Commands used for this decision:

```powershell
git status --short
git log -1 --oneline
rg -n "run_quant_strategy_library_thesis_cutover" config docs scripts src tests -g "*.py" -g "*.ps1" -g "*.md" -g "*.json" -g "*.toml" -g "*.yaml" -g "*.yml"
python scripts\quant_research\run_quant_strategy_library_thesis_cutover.py --help
python -m compileall -q scripts\quant_research\run_quant_strategy_library_thesis_cutover.py
```

Observed baseline:

- latest commit was `7a5467e Phase 5.1 maintenance script path refactor`
- only historical/doc references were found:
  `docs/QUANT_RESEARCH_LAB.md` and
  `script_path_refactor_dry_run_phase2a_2026_05_12.md`
- no scheduled-task, config, source, or test references were found

## Move Contract

| current public path | implementation target | wrapper required | decision |
| --- | --- | --- | --- |
| `scripts/quant_research/run_quant_strategy_library_thesis_cutover.py` | `scripts/quant_research/maintenance/run_quant_strategy_library_thesis_cutover.py` | yes | move implementation, keep root wrapper |

Catalog semantics:

- root wrapper: `supporting` / `supporting_tool` / `safe-to-move = no`
- moved implementation: `supporting` / `supporting_tool` /
  `safe-to-move = yes-with-wrapper`

## Deferred

No other utility cleanup script qualifies for `maintenance/` in this pass.

- Factor-report writers remain deferred because they are report surfaces, not
  maintenance surfaces, and several have config/source references.
- Provider probes remain deferred because they are data-foundation capability
  surfaces, not maintenance surfaces.
- Crypto-news dataset scripts remain deferred because tests import helper
  symbols from the root module paths.
- Exporters, diagnostics, and dataset processors need their own target
  directories if moved later; they should not be placed in `maintenance/`.

## Validation For Implementation

```powershell
python -m compileall -q scripts\quant_research\maintenance scripts\quant_research\run_quant_strategy_library_thesis_cutover.py
$repo=(Get-Location).Path; $tmp=$env:TEMP; Push-Location $tmp; try { python "$repo\scripts\quant_research\run_quant_strategy_library_thesis_cutover.py" --help } finally { Pop-Location }
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```
