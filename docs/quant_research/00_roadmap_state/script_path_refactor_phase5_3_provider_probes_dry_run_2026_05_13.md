# Phase 5.3 Provider Capability Probes Dry Run

`Status: dry-run only`
`Date: 2026-05-13`
`Scope: scripts/quant_research provider capability probes`
`Move status: no files moved in this review`

## Decision

The provider capability probe group is a valid Phase 5.3 candidate, but it is a
medium-risk path-refactor batch, not a cleanup batch.

Recommended destination:

- `scripts/quant_research/provider_probes/`

Recommended implementation boundary:

- Move the 4 probe implementations together.
- Keep 4 root compatibility wrappers at the current public paths.
- Update catalog and README counts in the same change.
- Update provenance references where the path is used as current evidence
  provenance.
- Do not move artifacts, scheduled-task files, or provider sync pipelines.

This group should not go under `maintenance/`. These scripts describe provider
capability, paid/free data paths, and data-foundation feasibility. They are not
cleanup or remediation utilities.

## Inventory

| Script | Current role | CLI shape | Root discovery | Strong references | Risk | Dry-run decision |
| --- | --- | --- | --- | --- | --- | --- |
| `scripts/quant_research/probe_cryptoquant_stablecoin_tokens.py` | CryptoQuant stablecoin token capability probe | `main(argv)` already forwards parser argv | `SCRIPT_DIR.parents[1]`; also injects `ROOT` and `SRC` into `sys.path` | Catalog and historical staging plan only | Low | Moveable with wrapper; update root depth to new subdir. |
| `scripts/quant_research/probe_deribit_authenticated_historical_capability.py` | Deribit authenticated historical capability probe | `main()` with internal `parse_args()` | `SCRIPT_DIR.parents[1]` | Catalog and historical staging plan only | Medium-low | Moveable only after normalizing to `main(argv)` and `parse_args(argv)`. |
| `scripts/quant_research/probe_deribit_historical_trades_capability.py` | Deribit public historical trades capability probe | `main()` with internal `parse_args()`; `--as-of` required | `SCRIPT_DIR.parents[1]` | `config/quant_research/threshold_provenance.md:3450`, `:3517`; `PROJECT_STATE.md:135`; catalog | Medium | Moveable with wrapper, argv normalization, and provenance-path update. |
| `scripts/quant_research/probe_deribit_options_surface_feasibility.py` | Deribit options surface feasibility probe | `main()` with internal `parse_args()`; `--as-of` required, `--offline` available | `SCRIPT_DIR.parents[1]` | `config/quant_research/threshold_provenance.md:3314`; `PROJECT_STATE.md:133`; catalog | Medium | Moveable with wrapper, argv normalization, and provenance-path update. |

## Reference Findings

Path search found no scheduled-task manifest reference and no test/config import
that directly executes these probe files.

Current references that must be considered during implementation:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `docs/quant_research/00_roadmap_state/worktree_staging_plan_2026-05-07.md`
- `config/quant_research/threshold_provenance.md`
- `PROJECT_STATE.md`
- self-references in module docstrings for the authenticated Deribit probe

`worktree_staging_plan_2026-05-07.md` is historical planning evidence. It does
not have to be rewritten if root wrappers remain and Markdown link validation
still passes.

`threshold_provenance.md` and `PROJECT_STATE.md` are more current evidence
surfaces. For an implementation commit, prefer updating those references to the
new implementation paths and adding a short note that the old root paths remain
compatibility wrappers.

## Wrapper Compatibility Strategy

Use the same wrapper pattern as the existing Phase 5 wrappers:

```python
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.provider_probes.<module_name> import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

Compatibility requirements:

- Preserve the 4 old CLI paths as root wrappers.
- Keep wrapper logic minimal: root path insertion, implementation import, argv
  forwarding only.
- Normalize the 3 Deribit implementations from `main()` to
  `main(argv: list[str] | None = None) -> int` and from `parse_args()` to
  `parse_args(argv)`.
- Leave the CryptoQuant probe's existing `main(argv)` shape intact.
- Update moved implementation root discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[2]` after moving one directory deeper.
- Smoke every old root path with `--help` from outside the repo cwd.

## Files Not To Move In This Batch

Do not move these adjacent provider/data-foundation scripts in Phase 5.3:

- `scripts/quant_research/sync_deribit_options_chain.py`
- `scripts/quant_research/run_quant_deribit_options_chain_snapshot_cycle.py`
- `scripts/quant_research/sync_deribit_dvol_history.py`
- `scripts/quant_research/sync_cryptoquant_stablecoin_history.py`
- `scripts/quant_research/sync_cryptoquant_reflexivity_history.py`
- `scripts/quant_research/run_quant_cryptoquant_m3_2_sync_cycle.py`
- scheduled-task registration scripts or runners

Those files are live data-sync or scheduled-adjacent surfaces. They need a
separate dry-run if they are ever moved.

## Dry-Run Verification Already Completed

Read-only checks:

```powershell
git status --short
rg -n "probe_(cryptoquant_stablecoin_tokens|deribit_authenticated_historical_capability|deribit_historical_trades_capability|deribit_options_surface_feasibility)\.py" .
Select-String -Path scripts\quant_research\probe_*.py -Pattern '^SCRIPT_DIR|^ROOT|^SRC|sys\.path|def main|parse_args|if __name__'
python scripts\quant_research\probe_cryptoquant_stablecoin_tokens.py --help
python scripts\quant_research\probe_deribit_authenticated_historical_capability.py --help
python scripts\quant_research\probe_deribit_historical_trades_capability.py --help
python scripts\quant_research\probe_deribit_options_surface_feasibility.py --help
python -m compileall -q scripts\quant_research\probe_cryptoquant_stablecoin_tokens.py scripts\quant_research\probe_deribit_authenticated_historical_capability.py scripts\quant_research\probe_deribit_historical_trades_capability.py scripts\quant_research\probe_deribit_options_surface_feasibility.py
```

Result:

- Working tree was clean at dry-run start.
- All 4 current root CLI paths return help successfully.
- All 4 current implementation files compile.
- No scheduled manifest or test hard-reference was found.
- Two Deribit files have current provenance references in
  `config/quant_research/threshold_provenance.md`.

## Implementation Verification Required

If Phase 5.3 is implemented, run:

```powershell
python -m compileall -q scripts\quant_research\provider_probes scripts\quant_research\probe_cryptoquant_stablecoin_tokens.py scripts\quant_research\probe_deribit_authenticated_historical_capability.py scripts\quant_research\probe_deribit_historical_trades_capability.py scripts\quant_research\probe_deribit_options_surface_feasibility.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\probe_cryptoquant_stablecoin_tokens.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\probe_deribit_authenticated_historical_capability.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\probe_deribit_historical_trades_capability.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\probe_deribit_options_surface_feasibility.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the repo Markdown link checker used for the doc-governance phase.

## Completion Criteria For A Future Phase 5.3 Commit

- `provider_probes/` contains exactly the 4 moved implementations.
- The 4 old root paths still work as thin wrappers.
- `threshold_provenance.md` preserves evidence meaning after the path update.
- `PROJECT_STATE.md` does not imply the wrapper is the implementation.
- Catalog has one row per script file and counts wrappers separately from
  provider probe implementations.
- README counts match the catalog and filesystem.
- No artifacts or scheduled-task surfaces are moved.
