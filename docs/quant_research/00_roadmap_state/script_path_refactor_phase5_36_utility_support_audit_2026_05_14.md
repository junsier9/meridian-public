# Phase 5.36 Utility Support Audit

`Status: read-only dry-run baseline`
`Date: 2026-05-14`
`Scope: remaining Utility Support root scripts after Phase 5.35`

## Starting State

`git status --short` showed only local untracked artifacts under
`artifacts/quant_research/...`; no tracked source/doc changes were present at
the start of this audit.

This phase moves no scripts. It classifies the four remaining Utility Support
root paths and decides whether a batch migration is appropriate.

## Audit Commands

```powershell
git status --short
Select-String -Path docs\quant_research\00_roadmap_state\quant_research_script_catalog.md -Pattern 'bootstrap_quant_runtime|export_passed_alphas_to_workbench|run_quant_ohlcv_lane_ab|run_quantagent_shadow_proposal_cycle'
rg -n "bootstrap_quant_runtime|export_passed_alphas_to_workbench|run_quant_ohlcv_lane_ab|run_quantagent_shadow_proposal_cycle" config docs scripts src tests -g "!docs/quant_research/00_roadmap_state/quant_research_script_catalog.md" -g "!scripts/quant_research/README.md"
rg -n "scripts/quant_research/(bootstrap_quant_runtime|export_passed_alphas_to_workbench|run_quant_ohlcv_lane_ab|run_quantagent_shadow_proposal_cycle)\.py|scripts\\quant_research\\(bootstrap_quant_runtime|export_passed_alphas_to_workbench|run_quant_ohlcv_lane_ab|run_quantagent_shadow_proposal_cycle)\.py" config docs scripts src tests -g "!docs/quant_research/00_roadmap_state/quant_research_script_catalog.md" -g "!scripts/quant_research/README.md"
```

## Classification

| class | script | hard refs / callers | artifact/output surface | decision |
| --- | --- | --- | --- | --- |
| bootstrap/root-freeze | `scripts/quant_research/bootstrap_quant_runtime.py` | `scripts/common/openclaw_scheduled_task_helpers.ps1` returns this root path; `src/enhengclaw/quant_research/runtime_bootstrap.py` reports this root path; `tests/test_quant_runtime_contracts.py` executes the root path and checks scheduler helper text | runtime bootstrap/check-only JSON; no research artifact family | permanent keep-root; next phase should be catalog-only `safe-to-move = no` |
| workbench export | `scripts/quant_research/export_passed_alphas_to_workbench.py` | public doc command in `docs/QUANT_RESEARCH_LAB.md`; package function is used by `src/enhengclaw/quant_research/{discovery,overlap_rerun,repo_health,validation_remediation,single_asset_repair}.py` and tests, but those callers do not import the CLI script path | workbench intake/archive snapshots plus `bridge_summary.json` under the workbench export root | no batch migration; future single-script plan may define `workbench_exports/` or keep root if workbench CLI is treated as a public bridge |
| OHLCV lane diagnostic | `scripts/quant_research/run_quant_ohlcv_lane_ab.py` | public doc command in `docs/QUANT_RESEARCH_LAB.md`; package function is tested directly; no scheduled/config hard reference | `artifacts/benchmarks/quant_ohlcv_lanes/<run_stamp>/lane_ab_summary.{json,md}` plus lane-local QA/WB outputs | no batch migration; future single-script plan may move to `provider_diagnostics/` only if its admission rule explicitly covers OHLCV lane A/B diagnostics |
| quantagent shadow cycle | `scripts/quant_research/run_quantagent_shadow_proposal_cycle.py` | `tests/test_quant_runtime_contracts.py` runs the root CLI; `tests/test_quant_shadow_proposals.py` loads this exact root file with `importlib.util.spec_from_file_location` and monkeypatches the module-level `run_quantagent_shadow_proposal_cycle` symbol before calling `main()` | `artifacts/quant_research/cycles/<as_of>/eth_shadow_grid_daily_sample.json`, `shadow_grid/<as_of>/...`, and `shadow_candidates/<as_of>/shadow_candidate_list.json` | keep-root unless the shadow-cycle runtime contract is redesigned; a thin wrapper would not preserve the current monkeypatch/module API semantics |

## Batch Decision

Do not run a 3-8 script batch for this set.

Reasons:

- the four scripts split into four different semantics;
- `bootstrap_quant_runtime.py` is already a root runtime boundary;
- `run_quantagent_shadow_proposal_cycle.py` has active root-file module API
  semantics in tests, not just a CLI path;
- `export_passed_alphas_to_workbench.py` is a workbench bridge and needs its
  own target-directory rule before movement;
- `run_quant_ohlcv_lane_ab.py` is a data-lane diagnostic, not a generic report
  writer or sync helper.

## Recommended Next Phases

1. Phase 5.37 catalog-only root-freeze:
   - set `bootstrap_quant_runtime.py` to `safe-to-move = no`;
   - set `run_quantagent_shadow_proposal_cycle.py` to `safe-to-move = no`;
   - update README/catalog policy text only; move no scripts.

2. Phase 5.38 OHLCV lane diagnostic target decision:
   - decide whether `run_quant_ohlcv_lane_ab.py` belongs in
     `provider_diagnostics/` or needs a narrower `data_lane_diagnostics/`
     directory;
   - keep root CLI wrapper if moved;
   - do not combine it with workbench export.

3. Phase 5.39 workbench export target decision:
   - decide whether `export_passed_alphas_to_workbench.py` should stay as a
     public workbench bridge at root or move under a new workbench-specific
     directory with a root wrapper.

## Validation For This Audit

This read-only phase should run:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

No runtime/scheduled contract command is required unless the follow-up
catalog-only root-freeze edits catalog/README semantics. If Phase 5.37 touches
catalog/README, run:

```powershell
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
```
