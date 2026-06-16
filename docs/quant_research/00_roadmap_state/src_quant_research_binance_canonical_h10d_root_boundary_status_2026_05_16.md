# src quant_research binance_canonical_h10d root-boundary status

`Status: root-local / root-facade freeze baseline`
`Date: 2026-05-16`
`Scope: partition boundary and config/provider entrypoint contracts`

## Decision

The partition boundary and config/provider entrypoint buckets are not migration
targets for automatic governance.

They are frozen at their current root-local or root-facade contract layer:

- `_partition_month(...)` and `_symbol_partition_paths(...)` stay root-local in
  `binance_canonical_h10d.py`;
- `load_strategy_config(...)`, `default_strategy_config(...)`, and
  `discover_usdm_perp_symbols(...)` stay root-facade entrypoints.

This status does not approve source movement, config payload freezing, provider
store scans, or runtime behavior contracts.

## Current Contract Coverage

| bucket | contract | current boundary |
| --- | --- | --- |
| partition boundary | `src_quant_research_binance_canonical_h10d_partition_boundary_contract.json` | root-local placement, signatures, tiny partition filename samples, and synthetic partition-window filtering |
| config/provider entrypoints | `src_quant_research_binance_canonical_h10d_config_provider_entrypoints_contract.json` | root-facade importability, signatures, root-surface classification, and CLI import anchor |

## Keep Root / Do Not Move

| surface | reason |
| --- | --- |
| `_partition_month(...)` | shared by kline archive discovery and funding-cost loading; moving it into archive-specific code would distort module ownership |
| `_symbol_partition_paths(...)` | owns local archive partition filtering and depends on the root-local partition month parser |
| `load_strategy_config(...)` | public config resolver used by validation, scoring, dataset building, and CLI wrapper imports |
| `default_strategy_config(...)` | config payload source; freezing full payload content would overstate the current contract |
| `discover_usdm_perp_symbols(...)` | provider/store discovery entrypoint; signature-only protection is enough for now |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- moving `_partition_month(...)` or `_symbol_partition_paths(...)`;
- creating a neutral partition module;
- changing local archive or funding partition filename contracts;
- freezing `load_funding_cost_daily(...)` behavior through partition helpers;
- freezing full `default_strategy_config()` payloads;
- scanning real provider stores;
- changing `DEFAULT_CONFIG_PATH`, `DEFAULT_STORE_ROOT`, or provider path
  ownership;
- moving config/provider entrypoints into an internal module;
- runtime execution contracts for provider discovery or validation;
- caller-count contracts.

## Validation Baseline

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This status document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Partition and config/provider surfaces remain root-owned.
- Future movement or runtime behavior coverage starts from a new owner-gated
  artifact.
