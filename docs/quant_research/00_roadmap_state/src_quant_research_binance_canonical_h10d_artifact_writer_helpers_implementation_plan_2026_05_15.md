# src quant_research binance_canonical_h10d artifact writer helpers implementation plan

`Status: approved medium-risk facade-first implementation plan`
`Date: 2026-05-15`
`Scope: _write_json / _frame_or_empty helper extraction`

## Decision

Create `src/enhengclaw/quant_research/_binance_canonical_artifacts.py` and
move only the two generic artifact support helpers into it:

- `_write_json`
- `_frame_or_empty`

Keep `binance_canonical_h10d.py` as the root facade through explicit imports.
Do not move `_write_universe_membership` in this implementation.

## Approved Move Set

Move these names into `_binance_canonical_artifacts.py` and import them back
into `binance_canonical_h10d.py`:

- `_write_json`
- `_frame_or_empty`

## Root Facade Must Keep

Existing internal and ad hoc callers may continue to access:

- `binance_canonical_h10d._write_json`
- `binance_canonical_h10d._frame_or_empty`

The static contract covers root-facade importability and helper-level behavior
samples after the move.

## Explicit Deferred Surfaces

Do not move or change:

- `_write_universe_membership`;
- `BINANCE_RISK_BRAKE_COLUMNS`;
- `write_validation_artifacts`;
- `_render_markdown_report` / `_metric_row`;
- funding entrypoints;
- PIT universe construction;
- feature/risk-brake construction;
- artifact filenames or output root selection;
- CSV schemas or universe membership columns.

## Compatibility Strategy

- Keep function signatures identical to
  `config/quant_research/src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract.json`.
- Avoid importing `binance_canonical_h10d.py` from the new helper module.
- Keep the helper module dependency-light: `json`, `Path`, `Any`, and `pandas`
  only.
- Leave `_write_universe_membership` in the root module because it depends on
  root-owned `BINANCE_RISK_BRAKE_COLUMNS`.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_artifacts.py
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- `_write_json.__module__` and `_frame_or_empty.__module__` point at
  `_binance_canonical_artifacts`.
- Root facade attribute access still works from `binance_canonical_h10d.py`.
- `_write_universe_membership.__module__` remains
  `enhengclaw.quant_research.binance_canonical_h10d`.
- Static artifact writer helper contract stays green.
- No artifact paths are staged or committed.
