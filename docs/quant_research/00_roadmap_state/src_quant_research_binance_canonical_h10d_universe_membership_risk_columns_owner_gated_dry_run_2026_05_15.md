# src quant_research binance_canonical_h10d universe membership risk columns owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _write_universe_membership / BINANCE_RISK_BRAKE_COLUMNS`

## Decision

Do not permanently keep `_write_universe_membership` at root, but do not move it
directly either.

Approve a column-registry-first path:

1. extract only `BINANCE_RISK_BRAKE_COLUMNS` into a small internal registry
   module;
2. import the registry constant back into `binance_canonical_h10d.py` so the
   root facade remains compatible;
3. move `_write_universe_membership` into the existing artifact helper module;
4. import `_write_universe_membership` back into `binance_canonical_h10d.py`.

This keeps the writer helper out of feature/risk-brake logic while avoiding a
duplicate risk column tuple.

## Caller Baseline

### `BINANCE_RISK_BRAKE_COLUMNS`

In-repo source callers:

- `prepare_scored_backtest_frame(...)`: keeps risk-brake support columns in the
  scored frame without adding them to the alpha feature subset.
- `add_binance_risk_brake_columns(...)`: initializes and writes the risk-brake
  overlay columns.
- `_write_universe_membership(...)`: includes those support columns in
  `universe_membership.csv` when present.

In-repo tests and config references:

- `tests/test_binance_canonical_h10d.py` checks that risk-brake columns remain
  retained without entering alpha features.
- config files select
  `short_position_weight_multiplier_column = binance_risk_brake_short_multiplier`.
- historical h10d docs reference the risk-brake column names as evidence, not
  as import callers.

### `_write_universe_membership`

Direct in-repo caller:

- `write_validation_artifacts(...)`

Observed behavior:

- projects a fixed support-column order;
- appends risk-brake support columns via `*BINANCE_RISK_BRAKE_COLUMNS`;
- sorts output by `timestamp_ms` and `subject` when those columns are present;
- writes an empty schema frame when no approved columns are available.

## Risk Classification

| surface | risk | implementation decision | rationale |
| --- | --- | --- | --- |
| `BINANCE_RISK_BRAKE_COLUMNS` | medium | extract to registry with root re-export | Shared by feature support, risk-brake logic, and artifact writer; needs one owner. |
| `_write_universe_membership` | medium | move after contract | Single root caller, but coupled to the registry constant. |
| `add_binance_risk_brake_columns(...)` | high | do not move | Active strategy hardening behavior and tests live here. |
| `write_validation_artifacts(...)` | high | do not move | Owns artifact path selection and report package emission. |

## Required Contract Before Movement

Before implementation, add a minimal static contract that freezes only:

- root-facade importability of `BINANCE_RISK_BRAKE_COLUMNS`;
- exact current risk-brake column tuple;
- root-facade importability and `inspect.signature` for
  `_write_universe_membership`;
- a tiny writer behavior sample proving column projection, extra-column
  exclusion, and `timestamp_ms`/`subject` sorting.

The contract must explicitly exclude:

- risk-brake formula behavior;
- full universe membership schema;
- empty-frame full schema behavior;
- validation artifact path selection;
- strategy pass/fail metrics;
- CSV writer settings outside the tiny sample;
- caller counts.

## Approved Next Automation

If the contract is green, the next automated implementation may:

1. create `src/enhengclaw/quant_research/_binance_canonical_risk_columns.py`;
2. move only `BINANCE_RISK_BRAKE_COLUMNS` there;
3. import the constant back into `binance_canonical_h10d.py`;
4. move `_write_universe_membership` into
   `src/enhengclaw/quant_research/_binance_canonical_artifacts.py`;
5. import `_write_universe_membership` back into `binance_canonical_h10d.py`.

## Explicit Deferred Surfaces

Do not move or change:

- `add_binance_risk_brake_columns(...)`;
- `add_short_squeeze_veto_multiplier(...)`;
- `_add_high_vol_rebound_short_brake(...)`;
- `prepare_scored_backtest_frame(...)`;
- `write_validation_artifacts(...)`;
- risk overlay policy parsing;
- feature subset selection;
- artifact path selection;
- report rendering.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run baseline is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No risk-brake formula or validation artifact behavior is changed in the
  dry-run commit.
- No artifact paths are staged or committed.
