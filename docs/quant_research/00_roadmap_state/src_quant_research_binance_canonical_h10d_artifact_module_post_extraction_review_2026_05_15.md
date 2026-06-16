# src quant_research binance_canonical_h10d artifact module post-extraction review

`Status: post-extraction review baseline`
`Date: 2026-05-15`
`Scope: _binance_canonical_artifacts.py internal module and root facade compatibility`

## Decision

Do not move source in this phase.

`src/enhengclaw/quant_research/_binance_canonical_artifacts.py` now owns three
writer helpers:

- `_write_json`
- `_frame_or_empty`
- `_write_universe_membership`

`src/enhengclaw/quant_research/binance_canonical_h10d.py` remains the root
facade by importing and re-exporting those helpers.

The next safe automation step is a small module-identity contract that ties the
internal module to the already-existing root facade contracts. It should not add
new artifact schemas or broader writer behavior snapshots.

## Supersession Note

The older artifact writer helper dry-run originally kept
`_write_universe_membership` deferred because it depended on
`BINANCE_RISK_BRAKE_COLUMNS`.

That deferral has been superseded by the later universe-membership/risk-column
implementation plan:

- `BINANCE_RISK_BRAKE_COLUMNS` was moved into
  `_binance_canonical_risk_columns.py`;
- `_write_universe_membership` was moved into
  `_binance_canonical_artifacts.py`;
- the root facade still exposes both names;
- `src_quant_research_binance_canonical_h10d_universe_membership_writer_contract`
  protects the risk-column tuple and a tiny projection/sort sample.

The old dry-run remains useful historical evidence, but it is no longer the
current implementation state for `_write_universe_membership`.

## Existing Protection

Already protected:

- `_write_json` and `_frame_or_empty` root facade signature and small behavior
  samples via
  `src_quant_research_binance_canonical_h10d_artifact_writer_helpers_contract`;
- `_write_universe_membership` root facade signature, risk-column tuple, and a
  tiny projection/sort sample via
  `src_quant_research_binance_canonical_h10d_universe_membership_writer_contract`;
- `BINANCE_RISK_BRAKE_COLUMNS` tuple ownership via
  `_binance_canonical_risk_columns.py` and the universe-membership writer
  contract.

Current missing protection:

- no static contract asserts that the root facade exports the same callable
  objects as `_binance_canonical_artifacts.py`;
- no static contract records that `_write_universe_membership` now belongs to
  the artifact module rather than being root-local.

## Approved Next Contract Shape

Allowed:

- assert `_write_json`, `_frame_or_empty`, and `_write_universe_membership`
  exist in `_binance_canonical_artifacts.py`;
- assert root facade exports the same callable objects;
- reuse existing root facade contracts as the source of signatures and behavior
  samples;
- assert the universe-membership contract still names
  `_binance_canonical_artifacts.py` as the approved writer module after move.

Not allowed:

- adding new full artifact schemas;
- changing JSON writer formatting;
- changing CSV writer settings beyond existing samples;
- changing output path selection;
- changing report rendering;
- changing risk-brake formula behavior;
- moving validation/report/funding orchestration into the artifact module.

## Deferred / Owner-Gated

Owner approval and a fresh dry-run are required before:

- moving `write_validation_artifacts(...)`;
- expanding `_binance_canonical_artifacts.py` into report path ownership;
- freezing full `universe_membership.csv` schemas;
- changing risk-column ownership;
- making artifact writers public API outside the root facade.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This review is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- A later implementation commit, if added, stays limited to contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this review batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
