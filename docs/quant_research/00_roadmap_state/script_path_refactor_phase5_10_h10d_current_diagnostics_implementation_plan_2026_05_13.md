# Phase 5.10 H10D Current Diagnostics Implementation Plan

`Status: implementation plan`
`Date: 2026-05-13`
`Scope: 4 current-line h10d diagnostic/support implementations`
`Baseline commit: e0b3023 Phase 5.10 h10d current diagnostics dry run`

## Decision

Move the first batch of current-line h10d diagnostic implementations into:

`scripts/quant_research/h10d_current_diagnostics/`

Keep the four old root paths as CLI compatibility wrappers.

This directory is separate from
`scripts/quant_research/historical_h10d_diagnostics/`. The scripts in this
batch are still current h10d evidence-chain tools, not superseded A/B evidence
and not roadmap starting points.

## Files Selected

Move exactly these four implementations:

- `scripts/quant_research/compute_lsk3_baseline_decay_diagnostic.py`
- `scripts/quant_research/compute_lsk3_decay_deep_dive.py`
- `scripts/quant_research/compute_multi_horizon_factor_audit.py`
- `scripts/quant_research/run_factor_lifecycle_demotion_experiment.py`

Keep all four old root paths as thin CLI wrappers.

## Why These Four

The Phase 5.10 dry-run classified these as current-line support tools:

- they serve the current h10d/lsk3 evidence chain;
- they are not default h10d entrypoints;
- they are not scheduled-task surfaces;
- they are not config-defined public guards;
- they are not historical or superseded A/B experiments;
- no in-repo Python module import dependency was discovered;
- root CLI compatibility can be preserved with wrappers.

Their output families remain:

- `artifacts/quant_research/factor_reports/<as-of>/...`;
- `artifacts/quant_research/factor_lifecycle/<as-of>/...`.

## Explicitly Out Of Scope

Do not move:

- current/default h10d entrypoints:
  - `analyze_binance_pit_drawdown_attribution.py`
  - `build_binance_hv_balanced_anti_overfit_package.py`
  - `run_binance_canonical_h10d_validation.py`
- config-defined promotion guard:
  - `assert_h10d_promotion_evidence.py`
- public baseline validation surfaces:
  - `run_baseline_alpha_proof.py`
  - `run_baseline_alpha_survival.py`
  - `run_binance_spot_concordance_baseline.py`
  - `validate_baseline_alpha_confidence.py`
- module-import-dependent h10d evaluator graph:
  - `evaluate_v5_h10d_post_pump_short_replacement.py`
  - `evaluate_v6_h10d_mf01_narrow_ab.py`
  - `evaluate_v6_h10d_orderbook_short_replacement.py`
  - `evaluate_v6_h10d_post_pump_news_veto_ab.py`
  - `evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py`
  - `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
  - `evaluate_v6_h10d_post_pump_short_replacement.py`
  - `run_coinglass_h10d_parent_frozen_reset_strict.py`
- historical-only but nonstandard wrapper-shape scripts:
  - `audit_coinglass_h10d_parent_blocker_attribution.py`
  - `audit_coinglass_h10d_parent_fast_reject_stages.py`

## Directory Contract

`h10d_current_diagnostics/` is for current-line h10d support tools whose main
job is to explain, audit, or lifecycle-check the current canonical h10d/lsk3
evidence chain.

It must not contain:

- default h10d roadmap entrypoints;
- config-defined promotion guards;
- baseline public validation runners;
- module-import-dependent h10d evaluators;
- historical h10d evidence;
- stage0 or strict-falsification alpha evaluators;
- provider sync/probe/diagnostic scripts;
- scheduled runners or registration scripts.

## Wrapper Strategy

These four scripts expose `main()` and parse `sys.argv` internally. Do not use
the Phase 5.9 `main(sys.argv[1:])` wrapper template.

Use a root wrapper that executes the moved module as `__main__`:

```python
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    runpy.run_module(
        "scripts.quant_research.h10d_current_diagnostics.<module>",
        run_name="__main__",
    )
```

This preserves old root CLI behavior because the moved module keeps reading
the original `sys.argv[1:]` through its own `argparse` call.

## Implementation Steps

1. Start from a clean or understood worktree.
2. Create `scripts/quant_research/h10d_current_diagnostics/`.
3. Move the four selected implementation files into that directory.
4. Replace each old root path with the `runpy.run_module(..., run_name="__main__")`
   wrapper.
5. Update moved implementation root discovery:
   - `ROOT = SCRIPT_DIR.parents[1]` -> `ROOT = SCRIPT_DIR.parents[2]`.
6. Update `quant_research_script_catalog.md`:
   - root wrapper rows: `status = supporting`,
     `run priority = supporting_tool`, `safe-to-move = no`;
   - moved implementation rows:
     - `compute_lsk3_baseline_decay_diagnostic.py`: keep `status = active`;
     - `compute_lsk3_decay_deep_dive.py`: keep `status = active`;
     - `compute_multi_horizon_factor_audit.py`: keep `status = supporting`;
     - `run_factor_lifecycle_demotion_experiment.py`: keep
       `status = supporting`;
     - all moved rows keep `run priority = supporting_tool` and
       `safe-to-move = yes-with-wrapper`.
7. Update `scripts/quant_research/README.md` counts and Path Policy.
8. Update `script_path_refactor_checklist.md` with the
   `h10d_current_diagnostics/` admission rule.
9. Leave `threshold_provenance.md`, `data_utilization_roadmap.md`, and
   `algorithm_choices.md` root CLI references unchanged unless a line
   explicitly claims the root path is the implementation. Root wrappers remain
   the public CLI paths.
10. Do not move default entrypoints, public guards, baseline validation
    surfaces, module-import-dependent evaluators, or historical-only scripts in
    this commit.

## Expected Count Deltas

If the four implementations move and four root wrappers remain:

- script files: 227 -> 231;
- Python files: 208 -> 212;
- PowerShell files: stays 19;
- root-level files: stays 162;
- `h10d_current_diagnostics/`: 0 -> 4;
- `historical_h10d_diagnostics/`: stays 7;
- `canonical_h10d_and_binance_pit`: 27 -> 31;
- `active`: stays 36;
- `supporting`: 96 -> 100;
- `supporting_tool`: 116 -> 120;
- `safe-to-move = no`: 57 -> 61;
- `safe-to-move = yes`: stays 40;
- `safe-to-move = yes-with-wrapper`: stays 130.

## Known Implementation Notes

- All four selected scripts currently use `SCRIPT_DIR = Path(__file__).resolve().parent`
  and `ROOT = SCRIPT_DIR.parents[1]`; after the move they need
  `ROOT = SCRIPT_DIR.parents[2]`.
- `runpy.run_module(..., run_name="__main__")` should be smoked from outside
  the repo cwd so the old root CLI path is tested in the same way a human would
  call it.
- Do not introduce root re-export shims. These four are not known Python module
  dependencies; root CLI wrappers are sufficient.

## Required Verification

```powershell
python -m compileall -q scripts\quant_research\h10d_current_diagnostics scripts\quant_research\compute_lsk3_baseline_decay_diagnostic.py scripts\quant_research\compute_lsk3_decay_deep_dive.py scripts\quant_research\compute_multi_horizon_factor_audit.py scripts\quant_research\run_factor_lifecycle_demotion_experiment.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_lsk3_baseline_decay_diagnostic.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_lsk3_decay_deep_dive.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_multi_horizon_factor_audit.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\run_factor_lifecycle_demotion_experiment.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the tracked Markdown local-link checker because catalog, README,
checklist, and this plan are documentation surfaces.

## Completion Criteria

- `h10d_current_diagnostics/` contains exactly the four selected current
  support implementations.
- Old root CLI paths still respond to `--help` from outside the repo cwd.
- No default h10d entrypoint, promotion guard, public baseline runner, or
  module-import-dependent evaluator is moved.
- Catalog rows distinguish root wrappers from current diagnostic
  implementations.
- README and checklist explain the boundary between
  `h10d_current_diagnostics/` and `historical_h10d_diagnostics/`.
- Static, runtime/scheduled, Markdown link, and diff checks pass.
