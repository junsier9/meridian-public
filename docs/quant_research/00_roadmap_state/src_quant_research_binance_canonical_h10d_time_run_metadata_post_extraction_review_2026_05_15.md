# src quant_research binance_canonical_h10d time/run metadata post-extraction review

`Status: post-extraction review baseline`
`Date: 2026-05-15`
`Scope: _binance_canonical_time.py and _binance_canonical_run_metadata.py`

## Decision

Do not move source in this phase.

Two low-level support modules already exist and should remain narrow internal
implementation modules:

- `src/enhengclaw/quant_research/_binance_canonical_run_metadata.py`
- `src/enhengclaw/quant_research/_binance_canonical_time.py`

`src/enhengclaw/quant_research/binance_canonical_h10d.py` remains the visible
root facade by importing and re-exporting these helpers.

The next safe automation step is a pair of tiny internal-module identity
contracts. They should reuse the existing root facade contracts for signatures
and behavior samples, then add only the missing assertion that the facade
exports the exact same callables as the internal modules.

## Current Module Shape

Run metadata module:

- `utc_now`
- `_default_run_id`
- `_today_compact`

Time boundary module:

- `_parse_date`
- `_date_to_ms`
- `_ms_to_date`
- `_date_utc_series`

## Existing Protection

Already covered by
`config/quant_research/src_quant_research_binance_canonical_h10d_run_metadata_helpers_contract.json`:

- root-facade importability;
- signatures for `utc_now`, `_default_run_id`, and `_today_compact`;
- timestamp/date output regexes;
- `_default_run_id(...)` strategy-label sanitization.

Already covered by
`config/quant_research/src_quant_research_binance_canonical_h10d_datetime_boundary_contract.json`:

- root-facade importability;
- signatures for `_parse_date`, `_date_to_ms`, `_ms_to_date`, and
  `_date_utc_series`;
- small UTC date and timestamp identity samples;
- missing/bad timestamp behavior for `_date_utc_series`.

Current missing protection:

- no static contract asserts `utc_now`, `_default_run_id`, and
  `_today_compact` are owned by `_binance_canonical_run_metadata.py`;
- no static contract asserts `_parse_date`, `_date_to_ms`, `_ms_to_date`, and
  `_date_utc_series` are owned by `_binance_canonical_time.py`;
- no static contract asserts the root facade exports the same callable objects
  as those internal modules.

## Approved Next Contract Shape

Allowed:

- assert internal-module symbols exist;
- assert root facade symbols exist;
- assert root facade callables are identical to the internal-module callables;
- reuse existing root facade contracts as signature and behavior-sample source;
- assert `utc_now.__module__`, `_default_run_id.__module__`,
  `_today_compact.__module__`, `_parse_date.__module__`, `_date_to_ms.__module__`,
  `_ms_to_date.__module__`, and `_date_utc_series.__module__` point at the
  corresponding internal modules.

Not allowed:

- exact timestamp values;
- clock source replacement;
- output root or artifact path ownership;
- full validation report payloads;
- downstream validation, funding, PIT universe, backtest, or promotion behavior;
- moving helpers into generic repo-wide utilities.

## Deferred / Owner-Gated

Owner approval and a fresh dry-run are required before:

- replacing either internal module with a shared generic time utility;
- changing accepted `_parse_date(...)` input types;
- changing UTC conversion behavior;
- changing run-id timestamp shape or strategy-label sanitization;
- making these helpers public API outside the root facade.

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
