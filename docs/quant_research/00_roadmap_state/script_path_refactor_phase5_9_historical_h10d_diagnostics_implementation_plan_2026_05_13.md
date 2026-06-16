# Phase 5.9 Historical H10D Diagnostics Implementation Plan

`Status: implementation plan`
`Date: 2026-05-13`
`Scope: 7 wrapper-safe historical h10d diagnostics`
`Baseline commit: a08910b Phase 5.8 h10d diagnostics dry-run baseline`

## Decision

Use `scripts/quant_research/historical_h10d_diagnostics/` as the target
directory.

Do not use `scripts/quant_research/h10d_diagnostics/` for this first batch.
The selected scripts are all historical evidence, not current-line h10d
entrypoints. The longer directory name keeps the boundary explicit and avoids
making current Binance PIT h10d hardening look like it has been demoted or
moved.

## Files Selected

Move exactly these seven implementations:

- `scripts/quant_research/combine_alpha_ontology_h10d_overlay_ablation_partials.py`
- `scripts/quant_research/compare_alpha_ontology_h10d_fixed_set.py`
- `scripts/quant_research/compare_alpha_ontology_h10d_overlay_ablation.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_short_overlay.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_drift.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_rebaseline.py`
- `scripts/quant_research/audit_coinglass_h10d_parent_strict_cycle_probe.py`

Keep all seven old root paths as thin CLI wrappers.

## Why These Seven

Phase 5.8 classified these as `wrapper-safe`:

- historical or `historical_do_not_start_here`;
- no discovered in-repo Python module import dependency;
- `main(argv: list[str] | None = None)` plus `parse_args(argv)` wrapper shape;
- no scheduled/config hard reference found;
- root CLI compatibility can be preserved with a thin wrapper.

## Explicitly Out Of Scope

Do not move:

- active/default h10d entrypoints:
  - `analyze_binance_pit_drawdown_attribution.py`
  - `build_binance_hv_balanced_anti_overfit_package.py`
  - `run_binance_canonical_h10d_validation.py`
  - `run_baseline_alpha_proof.py`
  - `run_baseline_alpha_survival.py`
  - `run_binance_spot_concordance_baseline.py`
  - `validate_baseline_alpha_confidence.py`
- module-import-dependent h10d evaluators:
  - `evaluate_v5_h10d_post_pump_short_replacement.py`
  - `evaluate_v6_h10d_mf01_narrow_ab.py`
  - `evaluate_v6_h10d_orderbook_short_replacement.py`
  - `evaluate_v6_h10d_post_pump_news_veto_ab.py`
  - `evaluate_v6_h10d_post_pump_selected_short_exposure_ab.py`
  - `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
  - `evaluate_v6_h10d_post_pump_short_replacement.py`
  - `run_coinglass_h10d_parent_frozen_reset_strict.py`
- historical-only scripts without standard argv-forwarding shape:
  - `audit_coinglass_h10d_parent_blocker_attribution.py`
  - `audit_coinglass_h10d_parent_fast_reject_stages.py`
- stage0, falsification, provider diagnostics, provider probes, data-sync
  pipelines, scheduled surfaces, or current default entrypoints.

## Directory Contract

`historical_h10d_diagnostics/` is for superseded or historical h10d diagnostic
implementations whose outputs remain useful as evidence but should not be used
as the current roadmap starting point.

It must not contain:

- current Binance PIT h10d default entrypoints;
- active h10d hardening scripts;
- stage0 or strict-falsification alpha evaluators;
- provider validation/provenance diagnostics;
- provider capability probes;
- provider/data sync pipelines;
- scheduled runners or registration scripts.

## Implementation Steps

1. Start from a clean or understood worktree.
2. Create `scripts/quant_research/historical_h10d_diagnostics/`.
3. Move the seven selected implementation files into that directory.
4. Replace each old root path with a thin wrapper:
   - insert repo root into `sys.path`;
   - import `main` from
     `scripts.quant_research.historical_h10d_diagnostics.<module>`;
   - call `main(sys.argv[1:])`.
5. Update moved implementation root discovery:
   - for files using `SCRIPT_DIR = Path(__file__).resolve().parent` and
     `ROOT = SCRIPT_DIR.parents[1]`, change to `ROOT = SCRIPT_DIR.parents[2]`;
   - for files using `ROOT = Path(__file__).resolve().parents[2]`, change to
     `ROOT = Path(__file__).resolve().parents[3]`.
6. Leave historical document references to old root paths unchanged unless they
   explicitly describe the root file as the implementation. The root wrappers
   preserve those CLI paths.
7. Update `quant_research_script_catalog.md`:
   - root wrapper rows: `status = supporting`,
     `run priority = supporting_tool`, `safe-to-move = no`;
   - moved implementation rows: keep `status = historical`,
     `run priority = historical_do_not_start_here`,
     `safe-to-move = yes-with-wrapper`.
8. Update `scripts/quant_research/README.md` counts and Path Policy.
9. Update `script_path_refactor_checklist.md` with the
   `historical_h10d_diagnostics/` admission rule.
10. Do not move current-line or module-import-dependent h10d scripts in this
    commit.

## Expected Count Deltas

If the seven implementations move and seven root wrappers remain:

- script files: 220 -> 227;
- Python files: 201 -> 208;
- PowerShell files: stays 19;
- root-level files: stays 162;
- `historical_h10d_diagnostics/`: 0 -> 7;
- `canonical_h10d_and_binance_pit`: 23 -> 27;
- `coinglass_foundation_and_r_lanes`: 24 -> 27;
- `historical`: stays 27;
- `supporting`: 89 -> 96;
- `historical_do_not_start_here`: stays 29;
- `supporting_tool`: 109 -> 116;
- `safe-to-move = no`: 50 -> 57;
- `safe-to-move = yes`: 43 -> 40;
- `safe-to-move = yes-with-wrapper`: 127 -> 130.

## Known Implementation Notes

- `evaluate_v6_h10d_post_pump_short_overlay.py` invokes
  `run_alpha_ontology_horizon_cycle_oneoff.py` through a `ROOT`-anchored
  absolute path and `subprocess.run(..., cwd=str(ROOT))`. The move is safe only
  if `ROOT` is rewritten correctly.
- `audit_coinglass_h10d_parent_drift.py` and
  `audit_coinglass_h10d_parent_strict_cycle_probe.py` currently compute `ROOT`
  directly from `Path(__file__).resolve().parents[2]`; after the move they need
  `parents[3]`.
- The implementation commit should not introduce root re-export shims. These
  seven are not known module dependencies, so CLI wrappers are sufficient.

## Required Verification

```powershell
python -m compileall -q scripts\quant_research\historical_h10d_diagnostics scripts\quant_research\combine_alpha_ontology_h10d_overlay_ablation_partials.py scripts\quant_research\compare_alpha_ontology_h10d_fixed_set.py scripts\quant_research\compare_alpha_ontology_h10d_overlay_ablation.py scripts\quant_research\evaluate_v6_h10d_post_pump_short_overlay.py scripts\quant_research\audit_coinglass_h10d_parent_drift.py scripts\quant_research\audit_coinglass_h10d_parent_rebaseline.py scripts\quant_research\audit_coinglass_h10d_parent_strict_cycle_probe.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\combine_alpha_ontology_h10d_overlay_ablation_partials.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compare_alpha_ontology_h10d_fixed_set.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compare_alpha_ontology_h10d_overlay_ablation.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\evaluate_v6_h10d_post_pump_short_overlay.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_coinglass_h10d_parent_drift.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_coinglass_h10d_parent_rebaseline.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\audit_coinglass_h10d_parent_strict_cycle_probe.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the local Markdown link checker because catalog, README, checklist, and
this plan are documentation surfaces.

## Completion Criteria

- `historical_h10d_diagnostics/` contains exactly the seven selected
  historical implementations.
- Old root CLI paths still respond to `--help` from outside the repo cwd.
- No current h10d default entrypoint is moved.
- No module-import-dependent h10d evaluator is moved.
- Catalog rows distinguish root wrappers from historical implementations.
- README and checklist explain the new directory boundary.
- Static, runtime/scheduled, Markdown link, and diff checks pass.
