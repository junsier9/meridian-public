# src quant_research binance_canonical_h10d archive/data-foundation helper bucket status

`Status: partial closure / owner-gated data-foundation boundary`
`Date: 2026-05-16`
`Scope: contracted helper sub-slices inside archive_data_foundation_and_feature_panel`

## Decision

The low-level helper sub-slices of `archive_data_foundation_and_feature_panel`
are closed at the current minimal-contract layer.

Supersession note: the later owner-delegated terminal batch adds a narrow
signature-plus-smoke contract for `build_symbol_feature_frame(...)`. It does
not approve full daily feature-panel schema freezes, feature formula snapshots,
real local archive path contracts, funding attachment contracts, PIT behavior
contracts, or `build_binance_canonical_dataset(...)` coverage.

The full data-foundation bucket is not closed. Daily panel assembly, active
feature construction, archive path discovery, dataset building, manifest
payloads, funding attachment, and PIT universe selection remain owner-gated.

## Helper-Level Closed Surfaces

| surface | contract | current boundary |
| --- | --- | --- |
| `_read_kline_path(...)` | `src_quant_research_binance_canonical_archive_helpers_contract.json` | internal-module importability, root-facade identity, signature, tiny csv.gz read sample, and unsupported-format rejection |
| `_coerce_kline_frame(...)` | `src_quant_research_binance_canonical_archive_helpers_contract.json` | internal-module importability, root-facade identity, signature, kline constant identity, and tiny coercion sample |
| `symbol_to_subject(...)` | `src_quant_research_binance_canonical_archive_helpers_contract.json` | internal-module importability, root-facade identity, signature, and tiny symbol normalization samples |
| `_summarize_symbol_audits(...)` | `src_quant_research_binance_canonical_archive_helpers_contract.json` | internal-module importability, root-facade identity, signature, and tiny summary sample |
| `aggregate_1m_klines(...)` | `src_quant_research_binance_canonical_h10d_aggregate_1m_contract.json` | root-facade importability, signature, classification, complete/incomplete synthetic 1h samples, and unsupported interval rejection |
| `_intraday_realized_vol_by_day(...)` | `src_quant_research_binance_canonical_h10d_intraday_settlement_contract.json` | root-facade importability, signature, empty schema, and tiny synthetic 4h realized-vol sample |
| `_settlement_premium_by_day(...)` | `src_quant_research_binance_canonical_h10d_intraday_settlement_contract.json` | root-facade importability, signature, empty schema, and tiny synthetic 60d settlement-premium sample |

## Still Owner-Gated

| surface | reason |
| --- | --- |
| `_partition_month(...)` | shared archive/funding path boundary; not included in the archive helper contract |
| `_symbol_partition_paths(...)` | owns local partition discovery and path filtering |
| `_daily_bars_to_feature_panel(...)` | owns daily panel schema assembly and calls `add_binance_ohlcv_core_features(...)` |
| `add_binance_ohlcv_core_features(...)` | creates active feature columns and target labels |
| `build_symbol_feature_frame(...)` | crosses archive path discovery, partition reads, aggregation, as-of filtering, and feature-panel construction |
| `build_binance_canonical_dataset(...)` | crosses config defaults, symbol discovery, PIT universe, funding attachment, dataset manifests, gap audits, and feature manifests |
| funding loaders | separate provider/data-foundation behavior boundary |
| PIT universe helpers | already governed separately; do not merge into this bucket |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- source movement for any data-foundation entrypoint;
- contracts that read real local archive paths;
- full archive schemas or parquet engine behavior;
- full feature-panel schemas or column ordering;
- `add_binance_ohlcv_core_features(...)` formula behavior;
- target label construction;
- score output snapshots;
- dataset manifest, feature manifest, or gap-audit payload snapshots;
- funding attachment timing;
- PIT universe behavior;
- validation metrics, promotion status, or live-readiness authorization;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the active helper contracts:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This status document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Contracted helper sub-slices are treated as closed at the current
  minimal-contract layer.
- The full data-foundation bucket remains explicitly owner-gated.
- Future work starts from a new owner-gated artifact instead of silently
  widening archive, panel, feature, manifest, funding, PIT, validation, or
  promotion contracts.
