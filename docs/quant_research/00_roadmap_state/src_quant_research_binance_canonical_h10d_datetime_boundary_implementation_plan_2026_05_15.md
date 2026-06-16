# src quant_research binance_canonical_h10d datetime boundary implementation plan

`Status: approved medium-risk facade-first implementation plan`
`Date: 2026-05-15`
`Scope: _parse_date / _date_to_ms / _ms_to_date / _date_utc_series helper extraction`

## Decision

Create `src/enhengclaw/quant_research/_binance_canonical_time.py` and move
only the low-level UTC date/timestamp helpers into it. Keep
`binance_canonical_h10d.py` as the root facade through explicit imports so the
existing private root attribute surface remains compatible.

This implementation is allowed because the datetime boundary contract now
freezes:

- `_parse_date` signature and representative ISO/date/aware-UTC samples;
- `_date_to_ms` signature and UTC midnight millisecond samples;
- `_ms_to_date` signature and UTC millisecond-to-date samples;
- `_date_utc_series` signature and mixed valid/null/bad timestamp conversion
  samples.

## Approved Move Set

Move these names into `_binance_canonical_time.py` and import them back into
`binance_canonical_h10d.py`:

- `_parse_date`
- `_date_to_ms`
- `_ms_to_date`
- `_date_utc_series`

## Root Facade Must Keep

`binance_canonical_h10d.py` must continue to expose all four moved helper names
via explicit imports. Existing internal callers and tests may still access:

- `binance_canonical_h10d._parse_date`
- `binance_canonical_h10d._date_to_ms`
- `binance_canonical_h10d._ms_to_date`
- `binance_canonical_h10d._date_utc_series`

## Explicit Deferred Surfaces

Do not move or change:

- `_partition_month`, because it is still shared by kline archive and funding
  partition boundaries.
- funding facade helpers or funding entrypoints.
- PIT universe freeze logic.
- validation gates or report-generation behavior.
- artifact writer helpers such as `_write_json`, `_frame_or_empty`, and
  `_write_universe_membership`.
- naive datetime semantics or missing timestamp semantics beyond the identity
  samples already frozen in the contract.

## Compatibility Strategy

- Keep function signatures identical to
  `config/quant_research/src_quant_research_binance_canonical_h10d_datetime_boundary_contract.json`.
- Avoid importing `binance_canonical_h10d.py` from the new helper module.
- Keep the helper module dependency-light: `datetime` and `pandas` only.
- Do not edit callers; the root facade import keeps existing internal accesses
  stable.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_time.py
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- `_parse_date.__module__`, `_date_to_ms.__module__`, `_ms_to_date.__module__`,
  and `_date_utc_series.__module__` point at `_binance_canonical_time`.
- Root facade attribute access still works from `binance_canonical_h10d.py`.
- Static datetime boundary contract stays green.
- No artifact paths are staged or committed.
