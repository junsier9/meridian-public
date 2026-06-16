# src quant_research binance_canonical_h10d funding module post-extraction review

`Status: post-extraction review baseline`
`Date: 2026-05-15`
`Scope: _binance_canonical_funding.py internal module and root facade compatibility`

## Decision

Do not move source in this phase.

`src/enhengclaw/quant_research/_binance_canonical_funding.py` already owns the
funding helper implementation, while
`src/enhengclaw/quant_research/binance_canonical_h10d.py` remains the root
facade by importing and re-exporting those helpers.

The existing funding facade contract protects root importability and
`inspect.signature` shape, but it does not verify that the root facade still
exports the same callables from `_binance_canonical_funding.py`. The next safe
automation step is a small internal-module identity contract with tiny
path/month samples.

## Current Module Shape

Internal module:

- `DEFAULT_FUNDING_COST_ROOT`
- `DEFAULT_MARKET_TYPE`
- `_funding_columns`
- `funding_symbol_root`
- `funding_partition_path`
- `funding_symbol_manifest_path`
- `funding_sync_summary_path`
- `_read_funding_partition`
- `_dedupe_funding_rows`
- `_http_get_json`
- `_resolve_funding_root`
- `_month_key_from_ms`
- `_month_start_ms`
- `_month_end_ms`

Root facade currently imports these names from `_binance_canonical_funding.py`
and exposes them through `binance_canonical_h10d.py`.

## Existing Protection

Already covered by
`config/quant_research/src_quant_research_binance_canonical_h10d_funding_facade_contract.json`:

- protected funding entrypoints remain callable from the root facade;
- helper signatures remain stable at the root facade;
- provider HTTP behavior, HTTP retry semantics, formula behavior, funding-root
  relocation, artifact schemas, CSV compression, and `_partition_month` remain
  excluded surfaces.

Nearby contracts now also protect:

- archive helper module identity and tiny archive samples;
- `_partition_month` and `_symbol_partition_paths` as root-local shared
  archive/funding boundaries.

## Approved Next Contract Shape

Allowed:

- assert funding helpers exist in `_binance_canonical_funding.py`;
- assert the root facade exports the exact same callable objects;
- assert `inspect.signature` shape for the same helper set already listed by
  the funding facade contract;
- check tiny pure samples:
  - `_funding_columns()` returns the funding CSV column order;
  - `funding_symbol_root(...)`, `funding_partition_path(...)`,
    `funding_symbol_manifest_path(...)`, and `funding_sync_summary_path(...)`
    construct expected local path suffixes;
  - `_resolve_funding_root(...)` honors explicit `funding_root` and configured
    `funding_cost_root`;
  - `_month_key_from_ms(...)`, `_month_start_ms(...)`, and `_month_end_ms(...)`
    keep UTC month identity for one fixed month.

Not allowed:

- provider HTTP calls or retry behavior;
- live Binance API behavior;
- full `sync_funding_cost_history(...)` behavior;
- full `load_funding_cost_daily(...)` behavior;
- `_read_funding_partition(...)` file IO snapshots;
- `_dedupe_funding_rows(...)` row semantics;
- changing default funding roots;
- moving `_partition_month(...)`.

## Deferred / Owner-Gated

Owner approval and a fresh dry-run are required before any future change that:

- rewrites provider HTTP behavior;
- changes funding storage roots or partition naming;
- changes funding CSV schema beyond the tiny `_funding_columns()` sample;
- moves funding entrypoints out of the root facade;
- creates a broader provider/funding sync module boundary;
- moves `_partition_month(...)` into a neutral partition helper.

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
