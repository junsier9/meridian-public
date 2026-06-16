# Phase 5.6 Orderbook Event Study Implementation Plan

`Status: medium-risk implementation plan`
`Date: 2026-05-13`
`Scope: compute_orderbook_inventory_event_study.py path refactor`
`Baseline commit: 1728d7e Phase 5.5 alpha branch report script path refactor`

## Decision

Use the package-import rewrite plus root CLI wrapper strategy.

Move the implementation:

- from `scripts/quant_research/compute_orderbook_inventory_event_study.py`
- to `scripts/quant_research/alpha_branch_reports/compute_orderbook_inventory_event_study.py`

Keep the old root path as a thin CLI wrapper only:

- `scripts/quant_research/compute_orderbook_inventory_event_study.py`

Rewrite the known module consumer:

- `scripts/quant_research/evaluate_v6_h10d_orderbook_short_replacement.py`

Preferred import after the move:

```python
from scripts.quant_research.alpha_branch_reports import (
    compute_orderbook_inventory_event_study as mf01_stage0,
)
```

This intentionally preserves old root CLI compatibility but does not preserve
old root module-import compatibility. The only tracked module consumer must be
rewritten in the same change.

## Why This Is Medium Risk

`compute_orderbook_inventory_event_study.py` is both:

- a CLI evidence writer for the SP-L orderbook / inventory risk-transfer event
  study; and
- a module dependency for
  `evaluate_v6_h10d_orderbook_short_replacement.py`.

The caller reads constants and helper functions from the module:

- `MIN_HOURLY_BARS_PER_DAY`
- `PUMP_SIGMA_THRESHOLD`
- `PUMP_RANGE_Z_THRESHOLD`
- `PUMP_QV_EXPANSION_THRESHOLD`
- `_load_daily_panel`
- `_build_risk_frame`
- `_build_orderbook_state_panel`
- `_attach_baseline_short_boundary`

A normal 15-line CLI wrapper would not expose those symbols. The package import
rewrite is therefore safer and clearer than a root re-export shim.

## Files In Scope

Implementation files:

- `scripts/quant_research/compute_orderbook_inventory_event_study.py`
- `scripts/quant_research/alpha_branch_reports/compute_orderbook_inventory_event_study.py`
- `scripts/quant_research/evaluate_v6_h10d_orderbook_short_replacement.py`

Governance/catalog files:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
- `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`
- `docs/quant_research/00_roadmap_state/script_path_refactor_phase5_6_orderbook_event_study_implementation_plan_2026_05_13.md`
- `scripts/quant_research/README.md`

Optional doc reference updates:

- `docs/quant_research/03_alpha_branches/orderbook_inventory_risk_transfer_proposal.md`

Keep historical references unchanged unless they become misleading. The old
root CLI remains valid after the wrapper is created.

## Files Explicitly Out Of Scope

- `factor_report_card.py`
- h10d current-line diagnostics other than the one caller import rewrite above
- `evaluate_*_stage0.py`
- strict-falsification scripts
- provider probes
- data-sync pipelines
- scheduled entrypoints
- current default entrypoints

Do not move `evaluate_v6_h10d_orderbook_short_replacement.py` in this phase.
Only rewrite its import.

## Expected Count Deltas

If the implementation is moved and the old root path remains as a wrapper:

- script files: 214 -> 215;
- Python files: 195 -> 196;
- PowerShell files: stays 19;
- root-level files: stays 162;
- `alpha_branch_reports/`: 5 -> 6;
- `report_writers/`: stays 9;
- `m3_mf_spk_legacy_candidates`: 55 -> 56;
- `supporting`: 83 -> 84;
- `supporting_tool`: 103 -> 104;
- `safe-to-move = no`: 44 -> 45;
- `safe-to-move = yes`: stays 43;
- `safe-to-move = yes-with-wrapper`: stays 127.

## Implementation Steps

1. Start from a clean or understood worktree with `git status --short`.
2. Move `compute_orderbook_inventory_event_study.py` into
   `scripts/quant_research/alpha_branch_reports/`.
3. In the moved implementation, update root discovery from
   `SCRIPT_DIR.parents[1]` to `SCRIPT_DIR.parents[2]`.
4. Keep its existing `main(argv: list[str] | None = None)` and
   `parser.parse_args(argv)` contract.
5. Replace the old root path with a thin CLI wrapper:
   - insert repo root into `sys.path`;
   - import `main` from the moved package path;
   - call `main(sys.argv[1:])`.
6. Rewrite `evaluate_v6_h10d_orderbook_short_replacement.py` to import
   `mf01_stage0` from the moved package path.
7. Update catalog rows:
   - old root path: compatibility wrapper, `safe-to-move = no`;
   - moved implementation path: real SP-L branch event-study writer,
     `safe-to-move = yes-with-wrapper`.
8. Update README counts and path policy.
9. Add this plan to the governance index.
10. Do not move or reclassify stage0/falsification scripts.

## Required Verification

```powershell
python -m compileall -q scripts\quant_research\alpha_branch_reports scripts\quant_research\compute_orderbook_inventory_event_study.py scripts\quant_research\evaluate_v6_h10d_orderbook_short_replacement.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_orderbook_inventory_event_study.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_v6_h10d_orderbook_short_replacement.py --help
Pop-Location

python - <<'PY'
from scripts.quant_research.alpha_branch_reports import compute_orderbook_inventory_event_study as m
assert hasattr(m, "MIN_HOURLY_BARS_PER_DAY")
assert hasattr(m, "PUMP_SIGMA_THRESHOLD")
assert hasattr(m, "_load_daily_panel")
assert hasattr(m, "_build_risk_frame")
assert hasattr(m, "_build_orderbook_state_panel")
assert hasattr(m, "_attach_baseline_short_boundary")
PY

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the local Markdown link checker because this plan and catalog/README
changes are documentation surfaces.

## Completion Criteria

- `compute_orderbook_inventory_event_study.py` implementation lives under
  `alpha_branch_reports/`.
- The old root CLI still responds to `--help` from outside the repo cwd.
- `evaluate_v6_h10d_orderbook_short_replacement.py` imports the moved module by
  package path and its `--help` smoke test passes from outside the repo cwd.
- The moved module exposes the constants/helpers used by the caller.
- No stage0 evaluator, strict-falsification script, provider probe, data-sync
  pipeline, scheduled entrypoint, or current default entrypoint is moved.
- Catalog and README counts match the filesystem.
- Static and runtime contracts pass.
