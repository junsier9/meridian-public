# Phase 5.10 H10D Current Diagnostics Dry-Run

`Status: read-only dry-run`
`Date: 2026-05-13`
`Scope: current-line h10d diagnostic/support scripts`
`Baseline commit: d214cd7 Phase 5.9 historical h10d diagnostics script path refactor`

## Decision

Create a design target for `scripts/quant_research/h10d_current_diagnostics/`,
but do not move scripts in this dry-run.

The directory is useful, but it is not a continuation of
`historical_h10d_diagnostics/`. Phase 5.9 intentionally separated old h10d
evidence from current h10d work. Phase 5.10 should preserve that boundary:
current-line diagnostics can be grouped, but they must remain visibly different
from superseded A/B evidence and from current default entrypoints.

## Candidate Scope

First-batch candidates for a future implementation plan:

| script | catalog status | current evidence role | wrapper shape | dry-run posture |
| --- | --- | --- | --- | --- |
| `scripts/quant_research/compute_lsk3_baseline_decay_diagnostic.py` | `active` / `supporting_tool` | 5-step lsk3 decay diagnostic referenced by `threshold_provenance.md` | `main()` parses `sys.argv` internally | possible Phase 5.10 implementation candidate |
| `scripts/quant_research/compute_lsk3_decay_deep_dive.py` | `active` / `supporting_tool` | lsk3 per-quarter/per-regime follow-up diagnostic referenced by `threshold_provenance.md` | `main()` parses `sys.argv` internally | possible Phase 5.10 implementation candidate |
| `scripts/quant_research/compute_multi_horizon_factor_audit.py` | `supporting` / `supporting_tool` | multi-horizon factor audit referenced by `threshold_provenance.md` and alpha roadmap notes | `main()` parses `sys.argv` internally | possible Phase 5.10 implementation candidate |
| `scripts/quant_research/run_factor_lifecycle_demotion_experiment.py` | `supporting` / `supporting_tool` | factor lifecycle recommendation report referenced by `threshold_provenance.md` and lifecycle docs | `main()` parses `sys.argv` internally | possible Phase 5.10 implementation candidate |

These four are current h10d support tools, not stale evidence. They write
diagnostic or lifecycle reports under:

- `artifacts/quant_research/factor_reports/<as-of>/...`
- `artifacts/quant_research/factor_lifecycle/<as-of>/...`

## Directory Contract

`h10d_current_diagnostics/` is for current-line h10d support tools whose main
job is to explain, audit, or lifecycle-check the current canonical h10d/lsk3
evidence chain.

Admit a script only when all are true:

- it serves the current h10d evidence chain;
- it is not a default roadmap entrypoint;
- it is not a scheduled-task surface;
- it is not a config-defined public guard;
- it is not a historical or superseded A/B experiment;
- root CLI compatibility can be preserved with a wrapper;
- moving it does not require broad import rewrites.

Do not admit:

- current/default h10d entrypoints;
- promotion guards referenced by config contracts;
- baseline public validation runners;
- module-import-dependent h10d evaluator graph scripts;
- stage0 or strict-falsification alpha evaluators;
- provider sync, provider probe, or provider diagnostic scripts;
- historical-only evidence scripts.

## Boundary With Historical H10D Diagnostics

`historical_h10d_diagnostics/` keeps superseded or historical h10d evidence
that should not be used as a roadmap starting point.

`h10d_current_diagnostics/` keeps active support tools that still inform the
current h10d line, even if they are not default entrypoints.

Use this rule:

- If the script answers "why is the current h10d/lsk3 line healthy or weak
  right now?", it may belong in `h10d_current_diagnostics/`.
- If the script answers "what did an older h10d branch or rejected comparator
  show?", it belongs in `historical_h10d_diagnostics/` or stays deferred.
- If the script starts the current roadmap path, gates promotion, or is called
  by config/tests as a public surface, keep it at root.

## Wrapper Strategy

The four candidates do not expose the Phase 5.9 `main(argv)` shape. They use
`main()` and parse `sys.argv` internally. A future implementation should not
wrap them with `main(sys.argv[1:])`.

Recommended root wrapper pattern:

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

This keeps the old root CLI path and its original `sys.argv[1:]` behavior
because the moved module still runs as `__main__` and calls its own `main()`.

Moved implementations need root-depth rewrites:

- current: `ROOT = SCRIPT_DIR.parents[1]`
- after move: `ROOT = SCRIPT_DIR.parents[2]`

## Required Reference Updates For A Future Implementation

Must update in the same implementation commit:

- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
  - one row for each root wrapper: `status = supporting`,
    `run priority = supporting_tool`, `safe-to-move = no`;
  - one row for each moved implementation with its existing lifecycle status
    (`active` for the two lsk3 scripts, `supporting` for multi-horizon and
    lifecycle tools), `run priority = supporting_tool`, and
    `safe-to-move = yes-with-wrapper`;
  - expected count delta if all four move:
    - script files: 227 -> 231;
    - Python files: 208 -> 212;
    - root-level files: stays 162;
    - `h10d_current_diagnostics/`: 0 -> 4;
    - `canonical_h10d_and_binance_pit`: 27 -> 31;
    - `active`: stays 36;
    - `supporting`: 96 -> 100;
    - `supporting_tool`: 116 -> 120;
    - `safe-to-move = no`: 57 -> 61;
    - `safe-to-move = yes-with-wrapper`: stays 130.
- `scripts/quant_research/README.md`
  - coverage counts;
  - Path Policy note for `h10d_current_diagnostics/`;
  - directory boundary against `historical_h10d_diagnostics/`.
- `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`
  - add the directory admission rule;
  - forbid current diagnostics from being moved into
    `historical_h10d_diagnostics/`.

Review before deciding whether to edit:

- `config/quant_research/threshold_provenance.md`
  - contains direct root-path references to the four tools;
  - leave as public CLI references if root wrappers remain authoritative;
  - update only if the text explicitly claims the root file is the
    implementation rather than the compatibility path.
- `docs/quant_research/00_roadmap_state/data_utilization_roadmap.md`
- `docs/quant_research/00_roadmap_state/algorithm_choices.md`
- prior Phase 5 dry-run docs
  - preserve historical statements unless they create a live-path ambiguity.

## Explicit Deferred List

Keep these root-level for now:

### Default h10d entrypoints

- `scripts/quant_research/analyze_binance_pit_drawdown_attribution.py`
- `scripts/quant_research/build_binance_hv_balanced_anti_overfit_package.py`
- `scripts/quant_research/run_binance_canonical_h10d_validation.py`

### Public guards and baseline validation surfaces

- `scripts/quant_research/assert_h10d_promotion_evidence.py`
  - config hard reference in `config/quant_research/active_h10d_registry.json`.
- `scripts/quant_research/run_baseline_alpha_proof.py`
- `scripts/quant_research/run_baseline_alpha_survival.py`
- `scripts/quant_research/run_binance_spot_concordance_baseline.py`
- `scripts/quant_research/validate_baseline_alpha_confidence.py`

### Module-import-dependent h10d evaluator graph

- `scripts/quant_research/evaluate_v5_h10d_post_pump_short_replacement.py`
- `scripts/quant_research/evaluate_v6_h10d_mf01_narrow_ab.py`
- `scripts/quant_research/evaluate_v6_h10d_orderbook_short_replacement.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_short_replacement.py`
- `scripts/quant_research/run_coinglass_h10d_parent_frozen_reset_strict.py`

### Historical-only but nonstandard wrapper shape

- `scripts/quant_research/audit_coinglass_h10d_parent_blocker_attribution.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_fast_reject_stages.py`

## Risk Assessment

`Risk: medium-low`

The import graph is simple for the four candidates, but the path contract is
not identical to Phase 5.9 because all four scripts use `main()` and internal
`argparse`. The implementation should therefore be separate from historical
h10d moves and should smoke each wrapper from outside the repo cwd.

Do not combine this with module-import-dependent evaluator rewrites.

## Verification For A Future Implementation

If the four candidates move, run:

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
checklist, and this dry-run are documentation surfaces.

## Completion Criteria For A Future Implementation

- `h10d_current_diagnostics/` contains only the four selected current support
  tools.
- Old root CLI paths still respond to `--help` from outside the repo cwd.
- No default h10d entrypoint, promotion guard, public baseline runner, or
  module-import-dependent evaluator is moved.
- Catalog rows distinguish root wrappers from current diagnostic
  implementations.
- README and checklist explain the difference between
  `h10d_current_diagnostics/` and `historical_h10d_diagnostics/`.
- Static, runtime/scheduled, Markdown link, and diff checks pass.
