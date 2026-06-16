# src quant_research binance_canonical_h10d partition boundary root-local decision

`Status: owner-gated root-local decision`
`Date: 2026-05-15`
`Scope: _partition_month / _symbol_partition_paths archive-funding boundary`

## Decision

Keep `_partition_month(...)` and `_symbol_partition_paths(...)` root-local in
`src/enhengclaw/quant_research/binance_canonical_h10d.py`.

This is a root-local freeze, not a source extraction plan. The prior partition
dry-run already showed that `_partition_month(...)` is shared by both:

- kline archive discovery through `_symbol_partition_paths(...)`; and
- funding-cost loading through `load_funding_cost_daily(...)`.

Moving `_partition_month(...)` into `_binance_canonical_archive.py` would make
funding code import an archive-specific module. Moving only
`_symbol_partition_paths(...)` would either duplicate month parsing or create a
circular facade dependency. Both outcomes make the boundary less honest.

## Current Root-Local Surfaces

| surface | role | current stance |
| --- | --- | --- |
| `_partition_month(path)` | Extracts `YYYY-MM` from local partition filenames that begin with a month key. | root-local frozen |
| `_symbol_partition_paths(...)` | Filters kline archive partition files by symbol, interval, and optional month range. | root-local frozen |
| `_month_key_from_ms(...)` | Funding writer month key. | governed by funding facade contract |
| `_month_start_ms(...)` | Funding loader lower-bound helper. | governed by funding facade contract |
| `_month_end_ms(...)` | Funding loader upper-bound helper. | governed by funding facade contract |

## Approved Next Contract Shape

Allowed:

- assert `_partition_month(...)` and `_symbol_partition_paths(...)` still live
  in `binance_canonical_h10d.py`;
- assert they are not exported from `_binance_canonical_archive.py`;
- freeze `inspect.signature` only for both helpers;
- check tiny path samples:
  - `2026-01.csv.gz` -> `2026-01`;
  - `2026-02.parquet` -> `2026-02`;
  - `BTCUSDT-1m-2026-01.csv.gz` -> `None`, because the current local store
    contract expects month-prefixed local partition files;
  - `_symbol_partition_paths(...)` filters a synthetic local store to a
    requested month window.

Not allowed:

- moving source;
- introducing `_binance_canonical_partitions.py`;
- changing archive path layout;
- changing funding partition naming or UTC month filtering;
- broad-freezing `load_funding_cost_daily(...)` behavior;
- treating this as an approval to refactor funding sync.

## Deferred

Any future source movement must write a fresh implementation plan first if it:

- creates a neutral `_binance_canonical_partitions.py` module;
- moves `_partition_month(...)`;
- moves `_symbol_partition_paths(...)`;
- rewrites funding path helpers;
- changes the local partition filename contract.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This decision is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- A later contract commit, if added, contains only JSON plus static tests.
- No production source moves in this root-local decision batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
