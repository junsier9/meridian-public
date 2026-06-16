# src quant_research binance_canonical_h10d run metadata helpers implementation plan

`Status: approved medium-risk facade-first implementation plan`
`Date: 2026-05-15`
`Scope: utc_now / _default_run_id / _today_compact extraction`

## Decision

Create `src/enhengclaw/quant_research/_binance_canonical_run_metadata.py` and
move only the run metadata helpers into it:

- `utc_now`
- `_default_run_id`
- `_today_compact`

Keep `binance_canonical_h10d.py` as the root facade through explicit imports.

## Approved Move Set

Move these names into `_binance_canonical_run_metadata.py` and import them back
into `binance_canonical_h10d.py`:

- `utc_now`
- `_default_run_id`
- `_today_compact`

## Root Facade Must Keep

Existing internal and ad hoc callers may continue to access:

- `binance_canonical_h10d.utc_now`
- `binance_canonical_h10d._default_run_id`
- `binance_canonical_h10d._today_compact`

## Explicit Deferred Surfaces

Do not move or change:

- `run_binance_canonical_validation(...)`;
- `write_validation_artifacts(...)`;
- artifact output root selection;
- markdown report filename template;
- markdown report rendering;
- validation report payload structure;
- dataset or feature manifest schemas;
- funding sync behavior.

## Compatibility Strategy

- Keep signatures and output formats aligned with
  `config/quant_research/src_quant_research_binance_canonical_h10d_run_metadata_helpers_contract.json`.
- Avoid importing `binance_canonical_h10d.py` from the new helper module.
- Keep the helper module dependency-light: `datetime` and `re` only.
- Do not freeze exact timestamps; only format and sanitization are contract
  surfaces.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_run_metadata.py
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- `utc_now.__module__`, `_default_run_id.__module__`, and
  `_today_compact.__module__` point at `_binance_canonical_run_metadata`.
- Root facade attribute access still works from `binance_canonical_h10d.py`.
- Static run metadata helper contract stays green.
- No artifact paths are staged or committed.
