# src quant_research binance_canonical_h10d reporting render contract dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _binance_canonical_reporting report-render helpers and root facade compatibility`

## Decision

Do not move source in this phase.

`_render_markdown_report(...)` and `_metric_row(...)` already live in
`src/enhengclaw/quant_research/_binance_canonical_reporting.py` and are
re-exported by the root facade
`src/enhengclaw/quant_research/binance_canonical_h10d.py`.

The next safe automation step is a tiny static contract that freezes only:

- internal-module importability;
- root-facade re-export compatibility;
- `inspect.signature` shape;
- one `_metric_row(...)` numeric-formatting sample;
- a minimal `_render_markdown_report(...)` structural sample that checks
  section presence and sidecar-policy wording.

Do not create a full markdown golden snapshot. The report is a research evidence
surface and may need wording, section, or payload evolution while h10d hardening
continues.

## Current Consumer Map

| consumer | dependency | current role | risk |
| --- | --- | --- | --- |
| `write_validation_artifacts(...)` | calls `_render_markdown_report(validation_report, paths)` | Writes the final human-readable validation report after JSON/CSV artifacts are emitted. | medium |
| root module importers | `binance_canonical_h10d._render_markdown_report` and `_metric_row` remain importable | Preserves compatibility after the reporting slice extraction. | low |
| docs and governance contracts | mention reporting as an extracted slice | Documents the facade-first decomposition boundary. | low |

No scripts or tests currently call `_binance_canonical_reporting.py` directly.
The visible compatibility surface should remain the root facade unless a later
owner-approved source refactor changes the package architecture.

## Path-Sensitive Inputs

`_render_markdown_report(...)` reads the following artifact labels from the
`paths` mapping:

- `validation_report`
- `dataset_manifest`
- `gap_audit`
- `feature_manifest`
- `aligned_period_returns`
- `universe_membership`
- `position_attribution`
- `attribution_by_side_year`
- `attribution_by_symbol_year`
- `factor_leave_one_out`
- `factor_leave_one_out_summary`
- `factor_leave_one_out_by_side`
- `factor_leave_one_out_by_year`
- `factor_leave_one_out_by_side_year`
- `paper_shadow_execution_ledger`
- `paper_shadow_execution_summary`
- `ablation_summary`
- `ablation_period_returns`

The contract may check that the Artifact Paths section still renders these
labels, but it must not freeze real output roots, run IDs, dates, or full
artifact schemas.

## Existing Protection

Nearby protected surfaces already exist:

- `src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract`
  protects `_write_json` and `_frame_or_empty` and explicitly excludes
  markdown report content.
- `src_quant_research_binance_canonical_h10d_run_metadata_helpers_contract`
  protects run metadata helpers and explicitly excludes markdown report content.
- `src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_contract`
  protects metric sanitation helpers and explicitly excludes full validation
  report payloads.
- `_run_backtest`, validation status, funding cost status, stratified holdout,
  risk-brake, and PIT universe contracts protect upstream behavior without
  turning report text into promotion evidence.

This reporting-render contract should fill only the remaining compatibility
gap between the extracted internal module and the root facade.

## Allowed Contract Shape

Allowed:

- verify `source_module ==
  enhengclaw.quant_research._binance_canonical_reporting`;
- verify `facade_module ==
  enhengclaw.quant_research.binance_canonical_h10d`;
- require `_render_markdown_report` and `_metric_row` to exist in both modules;
- require the facade objects to be the same callables exported by the internal
  module;
- freeze `inspect.signature` for both helpers;
- test one `_metric_row(...)` sample for numeric formatting;
- render one minimal report payload and assert a small set of expected substrings
  such as the title, status line, metrics table row, Holdout Gates section,
  Artifact Paths section, and sidecar-policy exclusion sentence.

Not allowed:

- exact full report text snapshots;
- exact artifact path roots or Windows path separators;
- exact validation metrics beyond the tiny helper sample;
- full blocker ordering;
- full falsification output;
- promotion or live-readiness decisions;
- source movement or package-layout expansion.

## Explicit Deferred / Owner-Gated

Keep deferred unless a later owner-approved dry-run says otherwise:

- moving `write_validation_artifacts(...)`;
- changing markdown section semantics;
- changing artifact path ownership;
- freezing validation report payload schemas;
- direct script imports from `_binance_canonical_reporting.py`;
- splitting report rendering into multiple formatter modules;
- treating report text as canonical promotion evidence.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No source files move.
- No full markdown report golden snapshot is introduced.
- Any implementation commit stays limited to a small contract JSON plus
  `tests/test_static_contracts.py`.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
