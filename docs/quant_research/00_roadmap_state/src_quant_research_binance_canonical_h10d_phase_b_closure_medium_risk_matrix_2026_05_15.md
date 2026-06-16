# src quant_research binance_canonical_h10d Phase B closure medium-risk matrix

`Status: read-only Phase B closure baseline`
`Date: 2026-05-15`
`Scope: src/enhengclaw/quant_research/binance_canonical_h10d.py remaining private helpers`

## Decision

The Phase B low-risk facade-first extraction series should pause after the
archive/reporting helper slices already completed. The remaining root-local
private helpers are no longer clean low-risk archive/reporting utilities. They
cross funding, PIT eligibility, validation, falsification, artifact-writing,
runtime path, hash identity, or time-boundary behavior.

Do not continue automatic code movement from this matrix. The next automated
step may write owner-gated plans, but implementation should require a narrow
behavior contract or explicit owner approval per group.

## Completed Low-Risk Slices

| Slice | Target module | Boundary preserved |
| --- | --- | --- |
| `_read_kline_path` | `_binance_canonical_archive.py` | Archive reader only. |
| `_coerce_kline_frame` | `_binance_canonical_archive.py` | Kline numeric coercion only. |
| `_summarize_symbol_audits` | `_binance_canonical_archive.py` | Symbol audit summary only. |
| `symbol_to_subject` | `_binance_canonical_archive.py` | USDT subject normalization only. |
| `_metric_row`, `_render_markdown_report` | `_binance_canonical_reporting.py` | Markdown report rendering only. |

## Remaining Helper Matrix

| Helper group | Representative helpers | Current callers / contracts | Risk | Decision |
| --- | --- | --- | --- | --- |
| Reporting metric sanitation | `_rank_ic_summary`, `_strip_periods`, `_drop_periods_from_metrics`, `_split_contract` | Validation report, ablations, falsification, split-realization contract construction | medium | Keep root until behavior smoke exists for validation/falsification summary output. |
| Archive/funding partition boundary | `_symbol_partition_paths`, `_partition_month` | Kline archive path filtering and `load_funding_cost_daily` funding partition filtering | medium | Keep root; prior partition-boundary dry-run already rejected a narrow archive move. |
| Funding path and sync helpers | `_funding_columns`, `funding_symbol_root`, `funding_partition_path`, `funding_symbol_manifest_path`, `funding_sync_summary_path`, `_read_funding_partition`, `_dedupe_funding_rows`, `_http_get_json`, `_resolve_funding_root`, `_month_key_from_ms`, `_month_start_ms`, `_month_end_ms` | `sync_funding_cost_history`, `write_funding_cost_rows`, `load_funding_cost_daily`; no repo-local direct import of these helpers was found outside `binance_canonical_h10d.py` during the follow-up AST scan | medium/high | Keep root until a dedicated funding facade plan exists. |
| Date/time conversion helpers | `_parse_date`, `_date_to_ms`, `_ms_to_date`, `_date_utc_series` | PIT freeze, feature build, funding sync, validation reports, attribution ledgers, paper-shadow ledgers | medium | Keep root until a date-boundary behavior contract covers UTC conversion and output type. |
| Hash/identity helpers | `_stable_hash`, `_stable_int` | Feature manifest hash and stratified symbol holdout assignment | medium/high | Keep root; any move must prove hash identity and holdout bucket stability. |
| Artifact writer helpers | `_write_json`, `_frame_or_empty`, `_write_universe_membership` | Funding summary, validation artifacts, attribution CSVs, report payloads, universe membership output | medium/high | Keep root until artifact schema/path contract exists. |
| Runtime naming helpers | `_default_run_id`, `_today_compact` | Validation run id and report filename generation | medium | Keep root until time-source behavior is tested or intentionally injected. |
| Generic-looking helpers with semantic weight | `_records`, `_truthy_series` | Attribution summaries, falsification summaries, PIT eligibility masks, active universe masks | medium | Keep root; `_truthy_series` is eligibility semantics, not a generic utility. |
| Feature normalization helpers | `_timestamp_zscore`, `_timestamp_percentile_rank` | Feature construction and existing feature helper tests/static contracts | medium | Do not move in this series; they belong to a separate feature-helper governance line. |

## External Caller Notes

- Follow-up AST import scan found no repo-local direct import of
  `binance_canonical_h10d._http_get_json`, funding path helpers, or funding
  month helpers outside `binance_canonical_h10d.py`. The M3.1 options-regime
  audit imports `_http_get_json` from `coinglass_capability_matrix`, not from
  this module.
- Existing docs already document `_partition_month` as a shared archive/funding
  boundary. This closure matrix keeps that decision intact.
- Existing tests import several root surfaces directly from
  `binance_canonical_h10d.py`; facade-first moves must preserve those imports.

## Allowed Next Automation

Automation may continue with docs-only or test-first work:

1. Write a funding facade owner-gated plan before moving any funding helper.
2. Write a date/hash/io behavior-contract plan before moving date, hash, or
   artifact helpers.
3. Add tiny behavior tests first when a helper controls identity, UTC conversion,
   artifact shape, or eligibility masks.
4. Keep implementation commits small and separate from docs-only baselines.

## Disallowed Next Automation

- Do not move `_partition_month` alone.
- Do not move `_http_get_json` without a funding facade contract, even though
  the M3.1 audit script does not import this module's helper.
- Do not move `_stable_int` without a holdout bucket identity test.
- Do not move `_write_json`, `_frame_or_empty`, or `_write_universe_membership`
  without artifact output contract coverage.
- Do not treat `_truthy_series` as a harmless utility; it gates eligibility
  masks across multiple validation paths.

## Validation For This Baseline

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

No runtime-heavy quant tests are required for this docs-only closure baseline.
