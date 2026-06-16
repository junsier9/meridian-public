# src quant_research binance_canonical_h10d archive/data-foundation bucket review

`Status: read-only bucket routing baseline`
`Date: 2026-05-16`
`Scope: archive_data_foundation_and_feature_panel after low-level helper contracts`

## Decision

Do not close the full `archive_data_foundation_and_feature_panel` bucket.

This bucket mixes archive IO, OHLCV aggregation, intraday diagnostics,
daily-panel schema assembly, factor/target construction, dataset manifests,
gap audits, funding attachment, and PIT universe selection. It must remain
owner-gated at the data-foundation entrypoint layer.

The only safe automatic action after the existing contracts is a partial
helper-level status/closure for the already contracted sub-slices.

Supersession note: the later owner-delegated terminal batch adds a narrow
signature-plus-smoke/static contract for `build_symbol_feature_frame(...)`.
That does not close the full data-foundation entrypoint layer, real archive
path discovery, daily feature-panel schema, dataset manifests, funding
attachment, PIT universe behavior, or `build_binance_canonical_dataset(...)`.

## Current Sub-Slice Routing

| sub-slice | current protection | routing decision |
| --- | --- | --- |
| low-coupling archive helpers | `src_quant_research_binance_canonical_archive_helpers_contract.json` | eligible for helper-level closure only |
| `aggregate_1m_klines(...)` | `src_quant_research_binance_canonical_h10d_aggregate_1m_contract.json` | eligible for helper-level closure only |
| `_intraday_realized_vol_by_day(...)` and `_settlement_premium_by_day(...)` | `src_quant_research_binance_canonical_h10d_intraday_settlement_contract.json` | eligible for helper-level closure only |
| `_daily_bars_to_feature_panel(...)` | owner-gated dry-run exists | status-only; no contract or closure expansion in this batch |
| `add_binance_ohlcv_core_features(...)` | indirectly protected by score-surface boundaries | owner-gated; do not freeze formula, targets, or full feature schema here |
| `build_symbol_feature_frame(...)` | terminal signature/smoke contract exists | root-facade signature and synthetic smoke only; archive/path + full feature-panel behavior remains owner-gated |
| `build_binance_canonical_dataset(...)` | no narrow contract approval | owner-gated data-foundation entrypoint |
| `_partition_month(...)` and `_symbol_partition_paths(...)` | partition/root-local docs exist; funding boundary remains shared | deferred / path-sensitive |

## Why Full Closure Is Not Approved

Full closure would blur several different stability layers:

- local archive partition discovery and file-format readers;
- minute-to-bar aggregation completeness rules;
- daily panel schema assembly;
- active OHLCV feature formulas and target label construction;
- funding-cost attachment timing;
- PIT universe and eligibility interaction;
- dataset manifest, feature manifest, and gap-audit payload shape;
- validation and artifact writer consumers.

The existing contracts intentionally protect only tiny synthetic helper samples
and root-facade import/signature stability. They do not prove full data
foundation behavior.

## Approved Automatic Follow-Up

Allowed:

- write a docs-only partial closure/status artifact for the contracted helper
  sub-slices;
- explicitly keep `_daily_bars_to_feature_panel(...)`,
  `add_binance_ohlcv_core_features(...)`, the full
  `build_symbol_feature_frame(...)` archive/path + feature-panel behavior, and
  `build_binance_canonical_dataset(...)` owner-gated;
- run only static and focused h10d validation commands.

Not allowed:

- source movement;
- new contract JSON in this batch;
- real archive reads or artifact snapshots;
- full feature-panel schema snapshots;
- exact target label or score output snapshots;
- funding attachment or PIT universe behavior changes;
- caller-count contracts.

## Validation Baseline

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This review is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The follow-up status artifact is docs-only.
- Full data-foundation entrypoints remain owner-gated.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
