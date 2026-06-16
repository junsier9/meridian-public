# src quant_research binance_canonical_h10d universe membership risk columns implementation plan

`Status: approved medium-risk facade-first implementation plan`
`Date: 2026-05-15`
`Scope: BINANCE_RISK_BRAKE_COLUMNS registry / _write_universe_membership extraction`

## Decision

Implement the owner-gated path approved by the dry-run:

- create `src/enhengclaw/quant_research/_binance_canonical_risk_columns.py`;
- move only `BINANCE_RISK_BRAKE_COLUMNS` into that registry module;
- import `BINANCE_RISK_BRAKE_COLUMNS` back into `binance_canonical_h10d.py`;
- move `_write_universe_membership` into
  `src/enhengclaw/quant_research/_binance_canonical_artifacts.py`;
- import `_write_universe_membership` back into `binance_canonical_h10d.py`.

## Approved Move Set

Move these names:

- `BINANCE_RISK_BRAKE_COLUMNS`
- `_write_universe_membership`

## Root Facade Must Keep

Existing internal and ad hoc callers may continue to access:

- `binance_canonical_h10d.BINANCE_RISK_BRAKE_COLUMNS`
- `binance_canonical_h10d._write_universe_membership`

## Explicit Deferred Surfaces

Do not move or change:

- `add_binance_risk_brake_columns(...)`;
- `add_short_squeeze_veto_multiplier(...)`;
- `_add_high_vol_rebound_short_brake(...)`;
- `prepare_scored_backtest_frame(...)`;
- `write_validation_artifacts(...)`;
- risk overlay policy parsing;
- feature subset selection;
- validation artifact path selection;
- report rendering;
- risk-brake formulas or thresholds.

## Compatibility Strategy

- Keep the exact risk-brake column tuple frozen by
  `config/quant_research/src_quant_research_binance_canonical_h10d_universe_membership_writer_contract.json`.
- Keep `_write_universe_membership` signature and tiny projection/sort sample
  frozen by the same contract.
- Avoid importing `binance_canonical_h10d.py` from either internal helper
  module.
- Let `_binance_canonical_artifacts.py` import
  `BINANCE_RISK_BRAKE_COLUMNS` from `_binance_canonical_risk_columns.py`,
  avoiding duplicate tuples and circular imports.

## Validation Commands

```powershell
python -m py_compile src\enhengclaw\quant_research\binance_canonical_h10d.py src\enhengclaw\quant_research\_binance_canonical_artifacts.py src\enhengclaw\quant_research\_binance_canonical_risk_columns.py
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- Root facade access to `BINANCE_RISK_BRAKE_COLUMNS` still works.
- `_write_universe_membership.__module__` points at
  `_binance_canonical_artifacts`.
- Risk-brake behavior tests stay green.
- Static universe membership writer contract stays green.
- No artifact paths are staged or committed.
