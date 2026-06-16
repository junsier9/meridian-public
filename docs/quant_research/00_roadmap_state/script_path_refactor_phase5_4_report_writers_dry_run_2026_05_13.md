# Phase 5.4 Report Writers Dry Run

`Status: dry-run and implementation boundary`
`Date: 2026-05-13`
`Scope: scripts/quant_research factor-report writer path refactor`
`Move status: first implementation batch may move only the listed utility writers`

## Decision

Use a new implementation directory:

- `scripts/quant_research/report_writers/`

This directory is for utility scripts whose primary job is to generate report,
diagnostic, admission, or audit artifacts, usually under:

- `artifacts/quant_research/factor_reports/<as-of>/`

Do not use this directory for:

- h10d current-line diagnostics;
- stage0, quarantine, or branch falsification implementations;
- provider capability probes;
- data-sync pipelines;
- scheduled-task runners or registration scripts;
- current default entrypoints.

Root CLI compatibility wrappers must be kept for moved scripts.

## Inventory Summary

The read-only scan found about 68 root-level scripts that mention
`factor_reports` or report-card language. They are not one move group.

| group | decision |
| --- | --- |
| Utility report/admission writers | First implementation batch. Move 9 selected scripts with wrappers. |
| `factor_report_card.py` | Deferred. It is a central W1.3/admission-v2 entry referenced by `threshold_provenance.md` and mechanism docs. Move only in a later dedicated batch. |
| Canonical h10d diagnostics | Deferred. These are current h10d evidence or validation helpers, not generic report writers. |
| Stage0/quarantine evaluators | Deferred. These are alpha-branch/falsification implementations even if they write `factor_reports` artifacts. |
| Data-sync/scheduled-adjacent surfaces | Deferred. Some are active default entrypoints or PowerShell runner targets. |
| Existing `parallel_1h/` and `provider_probes/` scripts | Out of scope. They already have a directory boundary. |

## First Batch

Move these 9 implementations to `scripts/quant_research/report_writers/` and
keep old root paths as wrappers:

- `scripts/quant_research/compute_basis_propagation_factor_report.py`
- `scripts/quant_research/compute_correlation_dvol_overlay_diagnostic.py`
- `scripts/quant_research/compute_cross_venue_factor_report.py`
- `scripts/quant_research/compute_cross_venue_funding_factor_report.py`
- `scripts/quant_research/compute_cross_venue_v1_factor_report.py`
- `scripts/quant_research/compute_expiry_hedge_unwind_factor_report.py`
- `scripts/quant_research/compute_liquidation_cascade_factor_report.py`
- `scripts/quant_research/compute_subday_funding_factor_report.py`
- `scripts/quant_research/compute_v6_dual_horizon_ensemble.py`

Why this batch:

- all 9 are `utilities_and_reports` rows;
- all 9 are `supporting_tool`;
- all 9 are safe only with wrappers;
- none are scheduled-task surfaces;
- none are active data-foundation/default sync entrypoints;
- none are h10d current-line diagnostics.

## Deferred

Do not move in this batch:

- `scripts/quant_research/factor_report_card.py`
- `scripts/quant_research/compute_lsk3_baseline_decay_diagnostic.py`
- `scripts/quant_research/compute_lsk3_decay_deep_dive.py`
- `scripts/quant_research/compute_multi_horizon_factor_audit.py`
- `scripts/quant_research/validate_baseline_alpha_confidence.py`
- `scripts/quant_research/validate_week_2_exit.py`
- any `evaluate_*_stage0.py`, `audit_m3_*`, `audit_mf*`, or branch falsification script
- `scripts/quant_research/run_quant_cryptoquant_m3_2_sync_cycle.py`
- `scripts/quant_research/run_quant_stablecoin_ethereum_backfill.py`
- `scripts/quant_research/run_quant_stablecoin_ethereum_sync_cycle.py`
- `scripts/quant_research/sync_coinglass_full_stack_foundation.py`
- `scripts/quant_research/sync_coinglass_etf_onchain_participant_sidecars.py`

## Reference Findings

The first batch has multiple current or historical documentation references,
especially in `threshold_provenance.md` and `data_utilization_roadmap.md`.

Compatibility strategy:

- keep old root CLI wrappers so existing references and old commands still run;
- catalog the old root paths as compatibility wrappers;
- catalog moved implementations as the real report-writer implementations;
- update current high-level state references where useful, but do not rewrite
  every historical mention unless a future review finds ambiguity.

Strong scheduled references were found only for deferred sync/backfill scripts,
not for the first-batch report writers.

## Implementation Requirements

For each moved script:

- update `ROOT = SCRIPT_DIR.parents[1]` to `ROOT = SCRIPT_DIR.parents[2]`;
- normalize `main()` to `main(argv: list[str] | None = None) -> int`;
- normalize `parser.parse_args()` to `parser.parse_args(argv)`;
- keep old root wrapper thin: root insertion, moved `main` import, and
  `main(sys.argv[1:])`;
- update README and catalog counts;
- keep one catalog row per script file.

## Verification Commands

```powershell
python -m compileall -q scripts\quant_research\report_writers scripts\quant_research\compute_basis_propagation_factor_report.py scripts\quant_research\compute_correlation_dvol_overlay_diagnostic.py scripts\quant_research\compute_cross_venue_factor_report.py scripts\quant_research\compute_cross_venue_funding_factor_report.py scripts\quant_research\compute_cross_venue_v1_factor_report.py scripts\quant_research\compute_expiry_hedge_unwind_factor_report.py scripts\quant_research\compute_liquidation_cascade_factor_report.py scripts\quant_research\compute_subday_funding_factor_report.py scripts\quant_research\compute_v6_dual_horizon_ensemble.py

Push-Location $env:TEMP
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_basis_propagation_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_correlation_dvol_overlay_diagnostic.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_cross_venue_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_cross_venue_funding_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_cross_venue_v1_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_expiry_hedge_unwind_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_liquidation_cascade_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_subday_funding_factor_report.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\compute_v6_dual_horizon_ensemble.py --help
Pop-Location

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the local Markdown link checker because README, catalog, and
governance index change.

## Completion Criteria

- `report_writers/` contains exactly the 9 first-batch implementations.
- The 9 old root paths still run as thin wrappers.
- `factor_report_card.py` remains at root and is explicitly deferred.
- h10d diagnostics, stage0 evaluators, and data-sync/scheduled entrypoints are
  unchanged.
- Catalog and README counts match the filesystem.
- Static contracts pass.
