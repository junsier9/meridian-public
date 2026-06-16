# Phase 5.41 Workbench Export Root Freeze

`Status: complete`
`Date: 2026-05-14`
`Scope: catalog and README policy only`

## Decision

Phase 5.41 permanently freezes this root path:

- `scripts/quant_research/export_passed_alphas_to_workbench.py`

No scripts were moved and no Python implementation changed. The only catalog
state change is `safe-to-move = yes-with-wrapper` to `safe-to-move = no` for
the workbench export root CLI.

## Evidence

Phase 5.40 found that this file is a frozen public workbench bridge:

- `docs/QUANT_RESEARCH_LAB.md` documents the root command.
- In-repo Python callers use the package function
  `enhengclaw.quant_research.bridge.export_passed_alphas_to_workbench`, not the
  root script module.
- The package bridge currently raises `LegacyQuantSurfaceFrozenError`; the
  root CLI catches it, prints `legacy_quant_surface_frozen` JSON, and exits with
  the frozen legacy-surface exit code.

Creating `scripts/quant_research/workbench_exports/` now would make an
intentionally frozen write surface look like an active implementation family.
Keep the public root command as the compatibility/status surface until an
owner-approved workbench bridge redesign thaws or replaces it.

## Catalog Delta

Total script coverage remains 284 files. Directory counts remain unchanged.

| safe-to-move | before | after |
| --- | ---: | ---: |
| `no` | 132 | 133 |
| `yes` | 32 | 32 |
| `yes-with-wrapper` | 120 | 119 |

## Queue Delta

The Utility Support owner queue is now closed:

- closed as root-freeze: `bootstrap_quant_runtime.py`
- moved to `data_lane_diagnostics/`: `run_quant_ohlcv_lane_ab.py`
- closed as root-freeze: `run_quantagent_shadow_proposal_cycle.py`
- closed as root-freeze: `export_passed_alphas_to_workbench.py`

Do not re-open `export_passed_alphas_to_workbench.py` as a movable utility
unless the frozen workbench bridge contract is deliberately redesigned first.

## Validation

Run after this catalog-only change:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```
