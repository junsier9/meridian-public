# Phase 5.37 Catalog-Only Root Freeze

`Status: complete`
`Date: 2026-05-14`
`Scope: catalog and README policy only`

## Decision

Phase 5.37 permanently freezes these root paths:

- `scripts/quant_research/bootstrap_quant_runtime.py`
- `scripts/quant_research/run_quantagent_shadow_proposal_cycle.py`

No scripts were moved and no Python implementation changed. The only catalog
state change is `safe-to-move = yes-with-wrapper` to `safe-to-move = no` for
the two rows above.

## Evidence

### `bootstrap_quant_runtime.py`

This file is a root runtime boundary, not a generic utility:

- `scripts/common/openclaw_scheduled_task_helpers.ps1` returns
  `scripts\quant_research\bootstrap_quant_runtime.py` from
  `Get-OpenClawQuantRuntimeBootstrapPath`.
- `src/enhengclaw/quant_research/runtime_bootstrap.py` defines
  `BOOTSTRAP_SCRIPT = ROOT / "scripts" / "quant_research" /
  "bootstrap_quant_runtime.py"` and reports that path in bootstrap/check-only
  JSON.
- `tests/test_quant_runtime_contracts.py` executes the root script with
  `--check-only` and asserts the scheduler helper text contains
  `bootstrap_quant_runtime.py`.

Moving this path would change scheduler/runtime-contract semantics unless those
contracts were redesigned first.

### `run_quantagent_shadow_proposal_cycle.py`

This file has active root-file module semantics, not only CLI compatibility:

- `tests/test_quant_runtime_contracts.py` runs the exact root CLI path with
  `--help`.
- `tests/test_quant_shadow_proposals.py` loads the exact root file via
  `importlib.util.spec_from_file_location("quant_shadow_grid_cli", script_path)`.
- The same test monkeypatches the loaded module-level
  `run_quantagent_shadow_proposal_cycle` symbol before calling `main()`, which
  a thin wrapper move would not preserve without redesigning the test/runtime
  API.

Moving this path would alter module-load and monkeypatch behavior, so it stays
root-bound.

## Catalog Delta

Total script coverage remains 283 files. Directory counts remain unchanged.

| safe-to-move | before | after |
| --- | ---: | ---: |
| `no` | 129 | 131 |
| `yes` | 32 | 32 |
| `yes-with-wrapper` | 122 | 120 |

## Queue Delta

The Utility Support owner queue is reduced from four remaining paths to two:

- remaining: `export_passed_alphas_to_workbench.py`
- remaining: `run_quant_ohlcv_lane_ab.py`
- closed as root-freeze: `bootstrap_quant_runtime.py`
- closed as root-freeze: `run_quantagent_shadow_proposal_cycle.py`

Do not re-audit the closed root-freeze pair as generic utility support unless
the scheduler/runtime bootstrap contract or shadow-cycle module-load contract
is intentionally redesigned first.

## Validation

Run after this catalog-only change:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```
