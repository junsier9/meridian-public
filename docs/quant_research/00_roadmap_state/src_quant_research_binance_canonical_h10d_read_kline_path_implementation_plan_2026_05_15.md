# binance_canonical_h10d _read_kline_path Implementation Plan

`Status: Phase B archive-helper implementation plan`
`Scope: facade-first extraction of _read_kline_path only`
`Date: 2026-05-15`

## Decision

Extract only `_read_kline_path` from
`src/enhengclaw/quant_research/binance_canonical_h10d.py` into an internal
archive helper module.

Target internal module:

- `src/enhengclaw/quant_research/_binance_canonical_archive.py`

Root facade requirement:

- `binance_canonical_h10d.py` must continue to expose `_read_kline_path` as an
  importable name.

## Approved Movement

Move:

- `_read_kline_path(path: Path) -> pd.DataFrame`

Keep in root:

- `_coerce_kline_frame`
- `_partition_month`
- `_symbol_partition_paths`
- `aggregate_1m_klines`
- `build_symbol_feature_frame`
- all funding helpers
- all PIT universe, validation, attribution, paper ledger, risk-brake, and
  reporting orchestration code.

## Rationale

`_read_kline_path` is the cleanest archive helper candidate:

- it is a pure file reader for `.parquet` and `.csv.gz` partitions;
- it does not depend on h10d strategy config, validation gates, funding roots,
  PIT universe state, or execution helpers;
- no scripts/tests directly import it;
- root re-export preserves near-private compatibility if a future caller does.

## Compatibility Strategy

`binance_canonical_h10d.py` imports `_read_kline_path` from
`._binance_canonical_archive`.

No caller rewrite is required. The existing root call site in
`build_symbol_feature_frame` continues to call `_read_kline_path` by the same
name.

## Explicit Non-Goals

Do not:

- move `_coerce_kline_frame`;
- move `KLINE_INT_COLUMNS` or `KLINE_FLOAT_COLUMNS`;
- move `_partition_month`;
- move or rewrite `_symbol_partition_paths`;
- touch funding-cost loading or sync;
- change archive partition naming, compression, encoding, or unsupported-format
  errors;
- change any h10d validation, score, risk-brake, attribution, or ledger logic.

## Validation Commands

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_binance_canonical_h10d.py -k "aggregation or archive or symbol_feature" -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Post-Commit Review Questions

- Does `binance_canonical_h10d.py` still expose `_read_kline_path`?
- Does `_binance_canonical_archive.py` contain only archive file-read behavior?
- Did the implementation avoid `_coerce_kline_frame`, `_partition_month`, and
  funding loader boundaries?
- Is `_coerce_kline_frame` plus kline constants worth a later separate plan, or
  should archive extraction pause here?
