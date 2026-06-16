# binance_canonical_h10d _coerce_kline_frame Implementation Plan

`Status: Phase B archive-helper implementation plan`
`Scope: facade-first extraction of _coerce_kline_frame and kline column constants`
`Date: 2026-05-15`

## Decision

Extract `_coerce_kline_frame` together with its two local kline column
constants into the existing internal archive helper module:

- `src/enhengclaw/quant_research/_binance_canonical_archive.py`

Root facade requirement:

- `binance_canonical_h10d.py` must continue to expose `_coerce_kline_frame`,
  `KLINE_INT_COLUMNS`, and `KLINE_FLOAT_COLUMNS` as importable names.

## Approved Movement

Move:

- `KLINE_FLOAT_COLUMNS`
- `KLINE_INT_COLUMNS`
- `_coerce_kline_frame(frame: pd.DataFrame) -> None`

Keep in root:

- `_partition_month`
- `_symbol_partition_paths`
- `aggregate_1m_klines`
- `build_symbol_feature_frame`
- all funding helpers and funding loaders
- all PIT universe, validation, attribution, paper ledger, risk-brake, and
  reporting orchestration code.

## Rationale

`_coerce_kline_frame` is a small archive-normalization helper used by:

- `aggregate_1m_klines`;
- `build_symbol_feature_frame`.

It mutates a DataFrame in place and depends only on pandas plus the two kline
column constants. Moving the helper and constants together avoids circular
imports and keeps archive file-read/coercion behavior in one internal module.

No in-repo scripts/tests directly import this helper from
`binance_canonical_h10d.py`, but root re-export preserves near-private
compatibility.

## Explicit Non-Goals

Do not:

- move `_partition_month`;
- move `_symbol_partition_paths`;
- move `INTERVAL_MS`, `MARKET_TYPE`, or `INTERVAL_1M`;
- touch funding-cost loading or sync;
- change archive partition naming, compression, numeric coercion, or in-place
  mutation behavior;
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

- Does `binance_canonical_h10d.py` still expose `_coerce_kline_frame` and both
  kline constants?
- Does `_binance_canonical_archive.py` remain limited to archive file-read and
  kline coercion behavior?
- Did the implementation avoid `_partition_month`, funding, PIT universe, and
  validation boundaries?
- Should archive extraction pause here before any broader helper movement?
