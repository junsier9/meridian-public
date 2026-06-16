# binance_canonical_h10d Reporting Slice Implementation Plan

`Status: Phase B implementation plan`
`Scope: first facade-first slice for binance_canonical_h10d.py decomposition`
`Date: 2026-05-15`

## Decision

Implement the first low-risk facade-first slice by extracting only the markdown
report rendering helpers from `binance_canonical_h10d.py`.

Approved movement:

- `_render_markdown_report`
- `_metric_row`

Target internal module:

- `src/enhengclaw/quant_research/_binance_canonical_reporting.py`

Root facade requirement:

- `src/enhengclaw/quant_research/binance_canonical_h10d.py` must continue to
  expose `_render_markdown_report` and `_metric_row` as importable names via
  module import/re-export.

## B0 Matrix Summary

| slice | approximate functions | approximate lines | caller/test surface | decision |
| --- | ---: | ---: | --- | --- |
| config/path defaults | 6 | 109 | CLI imports `DEFAULT_*`, config loader | defer |
| archive/data foundation | 15 | 544 | archive/PIT tests; path-sensitive store roots | future candidate |
| funding sync | 14 | 277 | funding tests; data-sync adjacent | defer |
| features/risk | 17 | 619 | feature purity, risk-brake tests | defer |
| execution analysis | 21 | 939 | attribution/ledger tests; `execution_backtest.py` private helpers | high-risk defer |
| validation/falsification | 13 | 614 | gate/status tests | high-risk defer |
| reporting/artifact writes | 6 | 333 | no external direct caller for render helpers | approve first narrow slice |

## Approved Boundary

Move only pure markdown string formatting:

- `_render_markdown_report(validation_report, paths)`
- `_metric_row(name, metrics)`

Keep in root for now:

- `write_validation_artifacts`
- `_write_json`
- `_frame_or_empty`
- `_write_universe_membership`
- `_today_compact`

Rationale:

- `write_validation_artifacts` still owns artifact path creation, CSV/JSON
  writes, and report path selection.
- `_write_json`, `_frame_or_empty`, and `_write_universe_membership` are shared
  with funding sync or attribution code and should not be moved in the first
  slice.
- `_render_markdown_report` and `_metric_row` are pure formatting helpers with
  no external direct import surface discovered in scripts/tests.

## Explicit Non-Goals

Do not:

- change markdown content, headings, artifact path labels, or numeric
  formatting;
- move or rewrite `write_validation_artifacts`;
- move config defaults, archive loaders, funding sync, risk-brake logic,
  validation gates, attribution, paper ledger, or ablation logic;
- change CLI behavior in `scripts/quant_research/run_binance_canonical_h10d_validation.py`;
- touch `execution_backtest.py` private-helper dependencies;
- add broad static contracts for the whole module.

## Compatibility Strategy

`binance_canonical_h10d.py` imports the moved helpers from
`._binance_canonical_reporting`, preserving root-level import compatibility for
current and future callers.

No caller rewrites are required because the only in-repo call site is still
`write_validation_artifacts` inside the root module.

## Validation Commands

Run after implementation:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Post-Commit Review Questions

- Does `binance_canonical_h10d.py` remain the visible facade?
- Did the new internal module stay limited to report rendering?
- Did the extraction avoid changing artifact path creation or report content?
- Is archive/data foundation still the best next candidate, or should reporting
  stay as the only approved low-risk slice for now?
