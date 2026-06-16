# src quant_research binance_canonical_h10d config/provider entrypoints signature dry-run

`Status: owner-gated signature-only dry-run`
`Date: 2026-05-15`
`Scope: config_and_provider_entrypoints root-surface bucket`

## Decision

Approve only a tiny importability/signature contract for the
`config_and_provider_entrypoints` bucket.

Do not move source and do not freeze runtime behavior in this batch.

Covered root-defined functions:

- `load_strategy_config`
- `default_strategy_config`
- `discover_usdm_perp_symbols`

## Read-Only Caller Baseline

Observed callers:

- `build_binance_canonical_dataset(...)` calls `load_strategy_config(...)` when
  no config dict is provided.
- `build_binance_canonical_dataset(...)` calls `discover_usdm_perp_symbols(...)`
  when no explicit symbol list is provided.
- `build_feature_manifest(...)` and `score_binance_ohlcv_core(...)` call
  `load_strategy_config(...)` for default config resolution.
- `run_binance_canonical_validation(...)` calls `load_strategy_config(...)`.
- `scripts/quant_research/run_binance_canonical_h10d_validation.py` imports
  `load_strategy_config` from the root facade.

## Approved Contract Shape

Allowed:

- assert root-facade importability;
- assert root-level symbols exist in `binance_canonical_h10d.py`;
- assert `inspect.signature` for the three functions;
- assert the root-surface classification contract still assigns them to
  `config_and_provider_entrypoints`;
- assert the CLI wrapper still imports `load_strategy_config` from the root
  facade.

Not allowed:

- calling `load_strategy_config(...)`;
- reading or writing real strategy config files;
- freezing the full `default_strategy_config()` dictionary;
- freezing provider/store discovery behavior;
- changing `DEFAULT_CONFIG_PATH`, `DEFAULT_STORE_ROOT`, or provider paths;
- moving these functions into an internal module.

## Deferred / Owner-Gated

Fresh dry-run required before:

- extracting config defaults into a new module;
- freezing default config payload keys or nested values;
- changing provider discovery path layout;
- changing CLI wrapper import strategy;
- turning `discover_usdm_perp_symbols(...)` into provider API behavior.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- A later implementation commit, if added, contains only contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this dry-run batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
