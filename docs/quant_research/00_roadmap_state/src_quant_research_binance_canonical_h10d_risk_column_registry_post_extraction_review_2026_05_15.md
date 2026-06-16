# src quant_research binance_canonical_h10d risk column registry post-extraction review

`Status: post-extraction review baseline`
`Date: 2026-05-15`
`Scope: _binance_canonical_risk_columns.py`

## Decision

Do not move source in this phase.

`src/enhengclaw/quant_research/_binance_canonical_risk_columns.py` is a narrow
internal registry module for `BINANCE_RISK_BRAKE_COLUMNS`.

`src/enhengclaw/quant_research/binance_canonical_h10d.py` remains the visible
root facade by importing and re-exporting the tuple.

The next safe automation step is a tiny registry identity contract. It should
reuse the existing universe-membership writer contract as the canonical column
list source, then add only the missing assertion that the root facade exports
the same tuple object as the internal registry module.

## Current Module Shape

Risk column registry:

- `BINANCE_RISK_BRAKE_COLUMNS`

No formulas, scorers, IO helpers, artifact writers, or validation gates belong
in this module.

## Existing Protection

Already covered by
`config/quant_research/src_quant_research_binance_canonical_h10d_universe_membership_writer_contract.json`:

- root-facade importability for `BINANCE_RISK_BRAKE_COLUMNS`;
- the exact current risk-brake support column tuple;
- tiny universe-membership writer projection/sort sample;
- approval that the registry module after move is
  `enhengclaw.quant_research._binance_canonical_risk_columns`.

Current missing protection:

- no static contract asserts the registry tuple is owned by
  `_binance_canonical_risk_columns.py`;
- no static contract asserts the root facade exports the same tuple object as
  the internal registry module.

## Approved Next Contract Shape

Allowed:

- assert internal-module symbol exists;
- assert root facade symbol exists;
- assert root facade tuple is identical to the internal-module tuple;
- assert tuple contents match the existing universe-membership writer contract;
- assert the universe-membership writer contract still names
  `enhengclaw.quant_research._binance_canonical_risk_columns` as the approved
  registry module.

Not allowed:

- risk-brake formula behavior;
- full universe-membership schemas;
- feature subset behavior;
- validation metrics or promotion decisions;
- artifact path selection;
- caller counts;
- moving this tuple into a generic repo-wide risk registry.

## Deferred / Owner-Gated

Owner approval and a fresh dry-run are required before:

- adding or removing risk-brake support columns;
- changing `_write_universe_membership(...)` projection behavior;
- merging this registry with risk-brake formula implementation;
- relocating the tuple outside the h10d-local `binance_canonical` support
  modules.

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
- Later implementation commits, if added, stay limited to contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this review batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
