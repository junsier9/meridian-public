# src quant_research binance_canonical_h10d run metadata helpers owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: utc_now / _default_run_id / _today_compact`

## Decision

Approve a contract-first facade extraction for the run metadata helpers:

- `utc_now`
- `_default_run_id`
- `_today_compact`

These helpers are format and naming helpers, not validation or strategy logic.
They can move into a small internal module if the root facade continues to
export them and the contract freezes only output formats and label
sanitization, not current timestamp values.

## Caller Baseline

### `utc_now`

Internal callers in `binance_canonical_h10d.py`:

- `build_binance_canonical_dataset(...)` for dataset and feature manifest
  timestamps;
- `sync_funding_cost_history(...)` for funding sync summary timestamps;
- `write_funding_cost_rows(...)` for funding symbol manifest timestamps;
- `build_feature_manifest(...)` for feature manifest timestamps;
- `run_binance_canonical_validation(...)` for validation report timestamps.

### `_default_run_id`

Internal caller:

- `run_binance_canonical_validation(...)`

Observed behavior:

- emits a UTC timestamp prefix in `%Y%m%dT%H%M%SZ` format;
- appends a sanitized strategy label;
- replaces non `[a-zA-Z0-9_.-]` runs with `-`;
- strips leading/trailing `-` from the strategy label suffix.

### `_today_compact`

Internal caller:

- `write_validation_artifacts(...)`

Observed behavior:

- emits `%Y_%m_%d`;
- participates in markdown report filename
  `binance_canonical_h10d_validation_YYYY_MM_DD.md`.

## Risk Classification

| helper | risk | decision | rationale |
| --- | --- | --- | --- |
| `utc_now` | low/medium | move with root facade | Timestamp format is widely used, but behavior is simple and format-testable. |
| `_default_run_id` | medium | move with root facade | Affects output directory naming; contract must cover suffix sanitization and timestamp shape. |
| `_today_compact` | medium | move with root facade | Affects markdown report filename; contract must cover date format only. |

## Required Contract Before Movement

Before implementation, add a minimal static contract that freezes only:

- root-facade importability;
- `inspect.signature` shape;
- `utc_now()` output regex:
  `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`;
- `_default_run_id(strategy_label=...)` output regex and sanitized suffix for a
  label containing spaces and punctuation;
- `_today_compact()` output regex: `YYYY_MM_DD`.

The contract must explicitly exclude:

- exact timestamp values;
- clock source replacement;
- output root selection;
- artifact path ownership;
- markdown report content;
- validation metrics;
- strategy pass/fail status;
- caller counts.

## Approved Next Automation

If the contract is green, the next automated implementation may:

1. create `src/enhengclaw/quant_research/_binance_canonical_run_metadata.py`;
2. move only `utc_now`, `_default_run_id`, and `_today_compact` there;
3. import those names back into `binance_canonical_h10d.py`;
4. leave `write_validation_artifacts(...)` and
   `run_binance_canonical_validation(...)` in the root facade.

## Explicit Deferred Surfaces

Do not move or change:

- `run_binance_canonical_validation(...)`;
- `write_validation_artifacts(...)`;
- artifact output root resolution;
- markdown report rendering;
- validation report payload structure;
- funding sync behavior;
- dataset or feature manifest schemas.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- The dry-run baseline is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No exact current timestamp is frozen.
- No artifact path or validation behavior changes in the dry-run commit.
- No artifact paths are staged or committed.
