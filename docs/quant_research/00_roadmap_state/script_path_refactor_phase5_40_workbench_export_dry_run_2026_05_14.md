# Phase 5.40 Workbench Export Dry-Run

`Status: target decision only`
`Date: 2026-05-14`
`Scope: scripts/quant_research/export_passed_alphas_to_workbench.py`

## Decision

Keep `scripts/quant_research/export_passed_alphas_to_workbench.py` as a
permanent root public bridge for now.

Do not move it to `scripts/quant_research/workbench_exports/` under the current
legacy-surface contract. A future `workbench_exports/` directory should only be
created if the bridge is deliberately thawed or redesigned as an active
workbench-export implementation family.

This phase moved no scripts and changed no Python implementation.

## Evidence

### Root CLI Reference

`docs/QUANT_RESEARCH_LAB.md` documents the root command:

```powershell
python scripts\quant_research\export_passed_alphas_to_workbench.py --as-of 2026-04-20
```

That makes the root path a public operator-facing command surface.

### Package Function Callers

Reusable callers import the package function, not the root script module:

- `src/enhengclaw/quant_research/discovery.py`
- `src/enhengclaw/quant_research/overlap_rerun.py`
- `src/enhengclaw/quant_research/repo_health.py`
- `src/enhengclaw/quant_research/single_asset_repair.py`
- `src/enhengclaw/quant_research/validation_remediation.py`
- `tests/test_quant_research_lab.py`
- `tests/test_quant_research_integrity.py`

These callers use `enhengclaw.quant_research.bridge.export_passed_alphas_to_workbench`.
They do not require the CLI implementation file to move.

### Legacy-Surface Frozen Behavior

The package function currently calls `raise_legacy_surface_frozen(...)` at the
start of `src/enhengclaw/quant_research/bridge.py`.

The root CLI catches `LegacyQuantSurfaceFrozenError`, writes
`legacy_surface_summary(operation="bridge_export", ...)` as JSON, and exits with
`LEGACY_QUANT_SURFACE_EXIT_CODE` (`78`). Runtime contracts assert the
`legacy_quant_surface_frozen` error code for frozen legacy quant surfaces.

This makes the root script a compatibility/status bridge for a frozen legacy
write surface, not just a movable implementation helper.

## Why Not `workbench_exports/` Now

`workbench_exports/` would be a reasonable future directory for active
workbench publication/export implementations. It is not appropriate while this
script's current behavior is to expose a stable frozen-surface response at the
old public root command.

Moving now would create a new implementation directory whose only implementation
is intentionally blocked before writing export artifacts. That would make the
path tree look more active than the current contract allows.

## Wrapper Strategy

If a future owner-approved redesign thaws this bridge or introduces a real
`workbench_exports/` implementation family, the old root command should remain
as a compatibility wrapper.

The current script already exposes `main(argv: list[str] | None)`, so a thin
root wrapper forwarding `sys.argv[1:]` would be sufficient for CLI
compatibility.

No root re-export shim is currently required:

- tests and in-repo Python callers import the package bridge function;
- no discovered caller imports private helpers from the root script;
- no discovered test monkeypatches module-level symbols on the root script.

Re-check this before any future move if new callers begin importing the root
script module directly.

## Artifact Surface

Historical/active bridge artifact surfaces include:

- `artifacts/quant_research/bridge_exports/<as_of>/bridge_summary.json`
- workbench queue snapshots under `_incoming_quant` or the selected queue root
- archive/staged-only snapshots referenced from `exports` and
  `suppressed_exports`

The current frozen root CLI does not write those export artifacts. Instead it
prints a legacy frozen summary containing:

- `status = frozen`
- `success = false`
- `error_code = legacy_quant_surface_frozen`
- `operation = bridge_export`
- resolved `artifacts_root` and `workbench_root`

That frozen summary is the live operator-facing surface today.

## Recommendation

Catalog-only next phase:

- set `scripts/quant_research/export_passed_alphas_to_workbench.py` to
  `safe-to-move = no`;
- add README policy text naming it a frozen public workbench bridge;
- remove it from the remaining Utility Support queue.

Do not create `scripts/quant_research/workbench_exports/` until a separate
owner-approved workbench bridge redesign makes the export path active again.

## Validation For This Dry-Run

Run after this documentation-only decision:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```
