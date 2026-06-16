# Phase 5.15 CoinGlass Diagnostics Dry Run

`Status: read-only dry-run baseline`
`Scope: CoinGlass diagnostic/report support scripts`
`Date: 2026-05-13`

## Decision

Move two CoinGlass diagnostic/report support implementations into
`scripts/quant_research/coinglass_diagnostics/`.

This directory is for CoinGlass capability/coverage diagnostics. It must remain
separate from provider sync pipelines, default CoinGlass data-refresh
entrypoints, CoinGlass quarantine scripts, and h10d-parent historical scripts.

## Move Set

| old root path | new implementation path | notes |
| --- | --- | --- |
| `scripts/quant_research/run_coinglass_capability_matrix.py` | `scripts/quant_research/coinglass_diagnostics/run_coinglass_capability_matrix.py` | active support diagnostic; old root shim retained |
| `scripts/quant_research/write_coinglass_coverage_reset_report.py` | `scripts/quant_research/coinglass_diagnostics/write_coinglass_coverage_reset_report.py` | coverage reset report writer; old root shim retained |

## Reference Audit

No config/test/scheduled strong references were found. Older staging and
governance docs mention the old root paths. Old root shims preserve those paths.

## Implementation Rules

- Move only the two scripts listed above.
- Update root discovery:
  - `run_coinglass_capability_matrix.py`: `SCRIPT_DIR.parents[1]` ->
    `SCRIPT_DIR.parents[2]`.
  - `write_coinglass_coverage_reset_report.py`: `Path(__file__).parents[2]` ->
    `Path(__file__).parents[3]`.
- Keep root re-export shims at both old paths.
- Do not move CoinGlass sync/default entrypoints, quarantine scripts, provider
  diagnostics already moved in Phase 5.7, or h10d-parent historical scripts.

## Expected Count Changes

Starting from Phase 5.14:

- Total script files: 248 -> 250.
- Python script files: 229 -> 231.
- Root-level count: stays 162.
- `provider_diagnostics/`: stays 5.
- `coinglass_diagnostics/`: 0 -> 2.
- `coinglass_foundation_and_r_lanes`: 27 -> 29.
- `supporting`: 117 -> 119.
- `supporting_tool`: 137 -> 139.
- `safe-to-move = no`: 78 -> 80.

## Verification Commands

```powershell
python -m compileall -q scripts\quant_research\coinglass_diagnostics scripts\quant_research\run_coinglass_capability_matrix.py scripts\quant_research\write_coinglass_coverage_reset_report.py
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\run_coinglass_capability_matrix.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\write_coinglass_coverage_reset_report.py
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

`write_coinglass_coverage_reset_report.py` has no argparse help path; use
compile/import smoke or run only when required artifacts are present.

## Deferred

- CoinGlass sync/default entrypoints.
- CoinGlass quarantine scripts.
- CoinGlass h10d-parent historical scripts.
