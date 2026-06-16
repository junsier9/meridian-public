# Phase 5.5 Alpha Branch Reports Dry Run

`Status: read-only dry-run`
`Date: 2026-05-13`
`Scope: scripts/quant_research branch-specific report and event-study writers`
`Baseline commit: 296f831 Phase 5.4 report writer script path refactor`

## Decision

Do not expand `scripts/quant_research/report_writers/`.

Phase 5.4 intentionally reserved `report_writers/` for utility factor-report,
admission-report, overlay diagnostic, and audit writers that are not tied to a
single alpha branch lifecycle. The branch-specific scripts reviewed here carry
SP-K, SP-L, M3, MF, or other alpha-branch semantics, so they need a separate
directory boundary if moved.

Recommended future target directory:

- `scripts/quant_research/alpha_branch_reports/`

Use this directory only for branch evidence writers whose primary job is to
produce branch report, event-study, admission-report, universe-headroom, or
sidecar-review artifacts for `docs/quant_research/03_alpha_branches`.

Do not use it for:

- `factor_report_card.py`;
- canonical h10d current-line diagnostics;
- `evaluate_*_stage0.py` stage0 evaluators;
- quarantined or strict-falsification implementations;
- provider probes;
- data-sync pipelines;
- scheduled entrypoints;
- current default entrypoints.

## Pre-Implementation Gate Decision

Decision: the first Phase 5.5 implementation batch should move exactly five
low / low-medium branch evidence writers into
`scripts/quant_research/alpha_branch_reports/`.

Move in the first batch:

- `scripts/quant_research/analyze_small_cap_universe_expansion.py`
- `scripts/quant_research/audit_small_cap_universe_expansion.py`
- `scripts/quant_research/compute_m3_2_admission_report.py`
- `scripts/quant_research/compute_small_cap_post_pump_event_study.py`
- `scripts/quant_research/compute_small_cap_post_pump_factor_report.py`

Keep old root CLI wrappers for all five scripts, even where tracked references
do not require one. This keeps manual command compatibility stable and makes
Phase 5.5 match the earlier wrapper-preserving path-refactor pattern.

Explicitly exclude from the first batch:

- `scripts/quant_research/compute_orderbook_inventory_event_study.py`

Reason: `scripts/quant_research/evaluate_v6_h10d_orderbook_short_replacement.py`
imports it as a module and reads constants plus helper functions. A CLI-only
root wrapper would break that module-level compatibility. Move it only in a
separate medium-risk batch after choosing either a package-import rewrite in
the caller or a root re-export shim.

Expected first-batch count deltas if all five root wrappers are kept:

- script files: 209 -> 214;
- Python files: 190 -> 195;
- root-level files: stays 162;
- `alpha_branch_reports/`: 0 -> 5;
- `m3_mf_spk_legacy_candidates`: 50 -> 55;
- `supporting`: 78 -> 83;
- `supporting_tool`: 98 -> 103;
- `safe-to-move = no`: 39 -> 44;
- `safe-to-move = yes`: 45 -> 43;
- `safe-to-move = yes-with-wrapper`: 125 -> 127.

## Read-Only Inventory

The current clean baseline has:

- 209 scripts under `scripts/quant_research`;
- 9 implementations already under `report_writers/`;
- no tracked config, scheduled-manifest, or test references to the clean
  Phase 5.5 candidates;
- one script-to-script import that makes one candidate higher risk:
  `evaluate_v6_h10d_orderbook_short_replacement.py` imports
  `compute_orderbook_inventory_event_study` as a module and uses constants and
  helper functions from it.

## Candidate Classification

| script | classification | tracked references | wrapper strategy | risk |
| --- | --- | --- | --- | --- |
| `scripts/quant_research/analyze_small_cap_universe_expansion.py` | SP-K branch sidecar review writer | catalog only | no wrapper required by tracked references; optional old-path CLI wrapper if manual compatibility is desired | low |
| `scripts/quant_research/audit_small_cap_universe_expansion.py` | SP-K branch universe-headroom audit writer | catalog only | no wrapper required by tracked references; optional old-path CLI wrapper if manual compatibility is desired | low |
| `scripts/quant_research/compute_m3_2_admission_report.py` | M3.2 branch admission-report writer | catalog plus old worktree staging plan | keep old root CLI wrapper forwarding `sys.argv[1:]` | low-medium |
| `scripts/quant_research/compute_small_cap_post_pump_event_study.py` | SP-K branch event-study writer | alpha-branch proposal plus catalog | keep old root CLI wrapper forwarding `sys.argv[1:]` | low-medium |
| `scripts/quant_research/compute_small_cap_post_pump_factor_report.py` | SP-K branch factor-diagnostic writer | alpha-branch proposal plus catalog | keep old root CLI wrapper forwarding `sys.argv[1:]` | low-medium |
| `scripts/quant_research/compute_orderbook_inventory_event_study.py` | SP-L branch event-study writer and module dependency | alpha-branch proposal, catalog, and direct import from `evaluate_v6_h10d_orderbook_short_replacement.py` | do not use CLI-only wrapper; either update the importer to package import first, or keep a root compatibility shim that re-exports module symbols plus forwards CLI | medium |

## Deferred In This Dry Run

Keep these out of the first Phase 5.5 implementation batch:

- `scripts/quant_research/factor_report_card.py`: central report-card surface,
  not branch-specific.
- `scripts/quant_research/compute_lsk3_baseline_decay_diagnostic.py`
- `scripts/quant_research/compute_lsk3_decay_deep_dive.py`
- `scripts/quant_research/compute_multi_horizon_factor_audit.py`
- `scripts/quant_research/validate_baseline_alpha_confidence.py`
- any `evaluate_*_stage0.py` script.
- any `evaluate_*_falsification.py` script.
- `audit_m3_*` and `audit_mf*` branch gate audits.
- `evaluate_*_cycle_increment.py` branch evaluators.
- provider sync, data refresh, and scheduled-task surfaces.

`compute_small_cap_post_pump_event_study.py` and
`compute_orderbook_inventory_event_study.py` are in scope only because they are
`compute_*_event_study.py` evidence writers. They are not precedent for moving
`evaluate_*_stage0.py` evaluators into the same directory.

## Implementation Preconditions

Before any Phase 5.5 move:

1. Confirm the worktree is clean or the dirty files are understood with
   `git status --short`.
2. Re-run path-reference search across `config`, `docs`, `scripts`, `src`, and
   `tests`.
3. Decide whether the first implementation batch excludes
   `compute_orderbook_inventory_event_study.py`; excluding it keeps the first
   batch mostly CLI-wrapper-only.
4. If including `compute_orderbook_inventory_event_study.py`, first choose one
   compatibility strategy:
   - update `evaluate_v6_h10d_orderbook_short_replacement.py` to import the
     moved module via package path; or
   - leave a root shim that re-exports the moved module's constants and helper
     functions, not just `main`.
5. Normalize moved script root discovery from `SCRIPT_DIR.parents[1]` to
   `SCRIPT_DIR.parents[2]`.
6. Normalize any `main()` / `parser.parse_args()` pair to
   `main(argv: list[str] | None = None)` / `parser.parse_args(argv)` before
   writing old-path CLI wrappers.

## Future Move Shape

Conservative first batch:

- Move exactly the five SP-K/M3 branch evidence writers that have no
  script-to-script import dependency:
  - `analyze_small_cap_universe_expansion.py`
  - `audit_small_cap_universe_expansion.py`
  - `compute_m3_2_admission_report.py`
  - `compute_small_cap_post_pump_event_study.py`
  - `compute_small_cap_post_pump_factor_report.py`
- Keep root CLI wrappers for all five to preserve both tracked and untracked
  command compatibility.

Separate medium-risk batch:

- Move `compute_orderbook_inventory_event_study.py` only after the module import
  compatibility decision is explicit.

## Verification Commands For A Future Implementation

```powershell
python -m compileall -q scripts\quant_research\alpha_branch_reports <old-root-wrapper-files>

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_m3_2_admission_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_small_cap_post_pump_event_study.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_small_cap_post_pump_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\analyze_small_cap_universe_expansion.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_small_cap_universe_expansion.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

If `compute_orderbook_inventory_event_study.py` moves, also verify module-level
compatibility:

```powershell
python - <<'PY'
import sys
from pathlib import Path
root = Path(r"C:\Users\user\Documents\Claude\Projects\EnhengClaw")
sys.path.insert(0, str(root / "scripts" / "quant_research"))
import compute_orderbook_inventory_event_study as m
assert hasattr(m, "MIN_HOURLY_BARS_PER_DAY")
assert hasattr(m, "_load_daily_panel")
assert hasattr(m, "_build_orderbook_state_panel")
PY
```

## Completion Criteria For A Future Implementation

- `report_writers/` remains at exactly the Phase 5.4 utility-report boundary.
- `alpha_branch_reports/` contains only approved branch evidence writers.
- `factor_report_card.py`, h10d diagnostics, stage0 evaluators, and strict
  falsification scripts remain unmoved.
- Old root CLI commands still work where wrappers are required.
- Any old root module import either still resolves the required symbols or has
  been rewritten to the moved package path.
- Catalog and README counts match the filesystem.
- Static contracts pass.
