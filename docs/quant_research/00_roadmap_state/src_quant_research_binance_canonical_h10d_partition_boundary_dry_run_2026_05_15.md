# binance_canonical_h10d Partition Boundary Dry-Run

`Status: read-only boundary dry-run`
`Scope: _symbol_partition_paths / _partition_month and shared archive-funding partition helpers`
`Date: 2026-05-15`

## Decision

Do not move `_symbol_partition_paths` or `_partition_month` in the next
implementation batch.

The archive helper extraction should pause after `_read_kline_path` and
`_coerce_kline_frame`. `_partition_month` is a shared boundary between kline
archive loading and funding-cost loading. Moving it into
`_binance_canonical_archive.py` would make funding code depend on an archive
module, which is the wrong direction for the package boundary.

The next safe action is docs-only: keep these helpers root-local unless a future
plan creates a neutral partition/path helper module.

## Current Call Map

| name | current caller(s) | dependency shape | decision |
| --- | --- | --- | --- |
| `_symbol_partition_paths` | `build_symbol_feature_frame` | archive-specific; depends on `MARKET_TYPE`, `INTERVAL_1M`, and `_partition_month` | keep root for now |
| `_partition_month` | `_symbol_partition_paths`, `load_funding_cost_daily` | shared month parser for kline and funding `.csv.gz`/`.parquet` names | keep root for now |
| `_month_key_from_ms` | `write_funding_cost_rows` | funding partition writer | keep root |
| `_month_start_ms` | `load_funding_cost_daily` | funding date-window filter | keep root |
| `_month_end_ms` | `load_funding_cost_daily` | funding date-window filter | keep root |
| `funding_partition_path` | `write_funding_cost_rows` | funding path constructor | keep root |

## Read-Only Evidence

Search command:

```powershell
rg -n "_symbol_partition_paths|_partition_month|funding_partition_path|load_funding_cost_daily|_month_start_ms|_month_end_ms|_month_key_from_ms" src scripts tests docs -g "*.py" -g "*.md"
```

Observed in `binance_canonical_h10d.py`:

- `build_symbol_feature_frame` calls `_symbol_partition_paths`.
- `_symbol_partition_paths` calls `_partition_month`.
- `load_funding_cost_daily` also calls `_partition_month`.
- `load_funding_cost_daily` also uses `_month_start_ms` and `_month_end_ms`.
- `write_funding_cost_rows` uses `_month_key_from_ms` and
  `funding_partition_path`.

Existing tests cover both sides indirectly:

- `tests/test_binance_canonical_h10d.py::test_symbol_feature_builder_reads_archive_partition_and_marks_daily_coverage`
- `tests/test_binance_canonical_h10d.py::test_funding_cost_sync_writes_daily_cost_only_rows_and_attaches_to_panel`

## Why Not Move To `_binance_canonical_archive.py`

`_binance_canonical_archive.py` currently owns only:

- kline partition file reads;
- kline numeric coercion;
- kline column constants.

Moving `_partition_month` there would force funding loaders to import from an
archive-specific module or leave duplicate month parsing in root. Both choices
make the boundary less clean:

- funding -> archive import creates misleading module semantics;
- duplicate parser creates drift risk across kline and funding partition names.

## Future Options

Option A: keep root-local indefinitely.

- Lowest risk.
- Accepts that `binance_canonical_h10d.py` remains the local coordination layer
  for shared path helpers.
- No implementation needed.

Option B: create a neutral internal module later.

- Candidate name:
  - `src/enhengclaw/quant_research/_binance_canonical_partitions.py`
- Candidate contents:
  - `_partition_month`
  - possibly `_month_key_from_ms`
  - possibly `_month_start_ms`
  - possibly `_month_end_ms`
- Requires a separate implementation plan because it touches both archive and
  funding boundaries.

Option C: move only `_symbol_partition_paths`.

- Not recommended now.
- It would require `_symbol_partition_paths` to import a root-local
  `_partition_month`, creating a circular dependency if imported by the root
  facade.

## Explicit Non-Goals

Do not:

- move `_partition_month` into `_binance_canonical_archive.py`;
- move `_symbol_partition_paths` alone;
- move funding loaders or funding path helpers;
- create `_binance_canonical_partitions.py` in this dry-run;
- change `MARKET_TYPE`, `INTERVAL_1M`, funding partition naming, or month-window
  filtering;
- touch PIT universe, validation, risk-brake, attribution, or ledger logic.

## Required Plan Before Any Future Implementation

Any future implementation must:

- decide whether the target module is neutral partition/path support rather than
  archive support;
- prove root facade import compatibility for `_partition_month`;
- prove archive and funding tests both pass;
- avoid circular imports between `binance_canonical_h10d.py`,
  `_binance_canonical_archive.py`, and any new partition helper;
- keep the first implementation small enough to review in one commit.

## Validation Commands

For this docs-only dry-run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

For a future implementation touching this boundary:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_binance_canonical_h10d.py -k "archive or symbol_feature or funding" -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Current Recommendation

Keep `_symbol_partition_paths` and `_partition_month` root-local for now.

Do not continue archive helper movement until there is a stronger reason to
extract a neutral partition helper. The next better automation target is likely
another low-risk pure helper family outside funding and PIT boundaries, or a
docs-only review that marks the remaining partition helpers as intentionally
root-local.
