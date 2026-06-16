# binance_canonical_h10d Archive Helper Slice Dry-Run

`Status: read-only Phase B follow-up dry-run`
`Scope: low-coupling archive helpers in src/enhengclaw/quant_research/binance_canonical_h10d.py`
`Date: 2026-05-15`

## Decision

Do not move the whole archive slice yet.

The second candidate slice should stay narrower than `build_symbol_feature_frame`
or PIT universe logic. The current lowest-risk implementation candidate is
`_read_kline_path`, with `_coerce_kline_frame` allowed only if its constants are
handled explicitly. `_partition_month` should be deferred because it is shared
with funding-cost loading, which is outside this dry-run boundary.

## Candidate Helpers

| helper | current callers | dependencies | risk | decision |
| --- | --- | --- | --- | --- |
| `_read_kline_path(path)` | `build_symbol_feature_frame` | `gzip`, `pd`, `Path`; reads `.parquet` and `.csv.gz` archive partitions | low | approve for future narrow implementation plan |
| `_coerce_kline_frame(frame)` | `aggregate_1m_klines`, `build_symbol_feature_frame` | mutates DataFrame in place; uses `KLINE_INT_COLUMNS`, `KLINE_FLOAT_COLUMNS`, `pd` | low/medium | possible, but only with constant re-export strategy |
| `_partition_month(path)` | `_symbol_partition_paths`, `load_funding_cost_daily` | `re`, `Path` | medium | defer because funding caller crosses boundary |

## Read-Only Evidence

Search scope:

```powershell
rg -n "_read_kline_path|_coerce_kline_frame|_partition_month|_symbol_partition_paths|build_symbol_feature_frame" src scripts tests docs -g "*.py" -g "*.md"
```

Observed direct usage:

- `build_symbol_feature_frame`
  - calls `_symbol_partition_paths`;
  - calls `_read_kline_path` for each kline partition;
  - concatenates frames and calls `_coerce_kline_frame`;
  - then continues into aggregation and feature-panel construction.
- `aggregate_1m_klines`
  - calls `_coerce_kline_frame` on a local copy before bucket aggregation.
- `_symbol_partition_paths`
  - calls `_partition_month` when filtering kline partitions.
- `load_funding_cost_daily`
  - also calls `_partition_month` when filtering funding partitions.
- `tests/test_binance_canonical_h10d.py`
  - covers the archive read path indirectly through
    `test_symbol_feature_builder_reads_archive_partition_and_marks_daily_coverage`.

No scripts/tests directly import the three candidate helpers from
`binance_canonical_h10d.py`, but they are near-private internal surfaces and
should remain available from the root facade if moved.

## Boundary

Approved for next implementation plan:

- target internal module name:
  - `src/enhengclaw/quant_research/_binance_canonical_archive.py`
- keep `binance_canonical_h10d.py` as root facade;
- preserve root importability for moved helper names;
- do not change archive file format handling or coercion behavior.

Do not include in the next implementation:

- `build_symbol_feature_frame`;
- `_symbol_partition_paths`;
- `aggregate_1m_klines`;
- `freeze_binance_ohlcv_universe`;
- `apply_point_in_time_rolling_universe`;
- funding helpers or `load_funding_cost_daily`;
- validation, falsification, attribution, paper ledger, or risk-brake code.

## Constant Handling For `_coerce_kline_frame`

`_coerce_kline_frame` depends on:

- `KLINE_INT_COLUMNS`
- `KLINE_FLOAT_COLUMNS`

Those constants are currently root module constants. A future implementation may
choose either:

- move the two constants into `_binance_canonical_archive.py` and re-export them
  from `binance_canonical_h10d.py`; or
- leave `_coerce_kline_frame` root-local until a broader archive helper plan.

Do not make `_binance_canonical_archive.py` import these constants from
`binance_canonical_h10d.py`, because the root facade would then import the helper
module and create avoidable circular-import risk.

## Why `_partition_month` Is Deferred

`_partition_month` looks small, but it is not archive-only in current behavior.
It is used by:

- `_symbol_partition_paths` for kline archive filtering;
- `load_funding_cost_daily` for funding-cost partition filtering.

Moving it in the same slice would make a supposedly pure archive extraction
touch the funding boundary. That violates this dry-run's explicit constraint:
do not touch funding sync or funding loaders.

Future options:

- keep `_partition_month` in root until a shared path utility plan exists;
- move it later into a neutral helper module after a funding dry-run;
- duplicate a tiny local parser only if an owner explicitly accepts divergence
  risk. This is not recommended now.

## Proposed Next Implementation Scope

Lowest-risk next implementation:

- create `_binance_canonical_archive.py`;
- move `_read_kline_path`;
- optionally move `KLINE_INT_COLUMNS`, `KLINE_FLOAT_COLUMNS`, and
  `_coerce_kline_frame` only if the plan explicitly preserves root re-exports;
- leave `_partition_month` and `_symbol_partition_paths` in root.

Even for this narrow implementation, the root module should continue to expose:

- `_read_kline_path`;
- `_coerce_kline_frame` if moved;
- `KLINE_INT_COLUMNS` and `KLINE_FLOAT_COLUMNS` if moved.

## Validation Commands

For a docs-only dry-run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

For a future implementation:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_binance_canonical_h10d.py -k "aggregation or archive or symbol_feature" -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Current Recommendation

Write a small implementation plan next, but keep it to one of two scopes:

1. `_read_kline_path` only; or
2. `_read_kline_path` plus `_coerce_kline_frame` and the two kline column
   constants, with root re-exports.

Do not include `_partition_month` in the first archive helper implementation.
