# src quant_research binance_canonical_h10d low-risk decomposition closure

`Status: low-risk facade-first decomposition closed`
`Date: 2026-05-15`
`Scope: completed low-risk/internal-helper extraction series`

## Decision

Close the current low-risk `binance_canonical_h10d.py` facade-first
decomposition series.

The remaining root-owned surfaces are behavior-sensitive and must not be moved
by the automatic low-risk process. Further decomposition requires a separate
owner-approved medium/high-risk dry-run with behavior contracts.

## Completed Low-Risk Internal Modules

The following internal modules now sit behind the root
`binance_canonical_h10d.py` facade:

| module | moved surface | governance read |
| --- | --- | --- |
| `_binance_canonical_archive.py` | kline read/coerce/symbol audit helpers | archive helper support, root facade preserved |
| `_binance_canonical_artifacts.py` | generic artifact writers and universe membership writer | writer support only, not validation owner |
| `_binance_canonical_funding.py` | funding path/sync support helpers | funding helper support, entrypoints remain root |
| `_binance_canonical_identity.py` | stable hash/int identity helpers | deterministic identity support |
| `_binance_canonical_normalization.py` | h10d-local timestamp z-score/rank helpers | h10d-local normalization, distinct from `features.py` |
| `_binance_canonical_reporting.py` | markdown report rendering helpers | report rendering support only |
| `_binance_canonical_risk_columns.py` | risk-brake support column registry | column registry only, not risk-brake formula |
| `_binance_canonical_run_metadata.py` | timestamp/run-id helper formatting | run metadata formatting only |
| `_binance_canonical_time.py` | UTC date/timestamp boundary helpers | date boundary support |

Root facade imports remain the compatibility layer for current tests, scripts,
and ad hoc imports.

## Remaining Root-Owned Surfaces

These surfaces are explicitly not part of the low-risk lane:

| surface | representative names | required next gate |
| --- | --- | --- |
| config and path defaults | `DEFAULT_CONFIG_PATH`, `DEFAULT_STORE_ROOT`, `DEFAULT_OUTPUT_ROOT`, `load_strategy_config`, `default_strategy_config` | medium-risk path/default contract |
| dataset/archive builders | `aggregate_1m_klines`, `build_binance_canonical_dataset`, `build_symbol_feature_frame` | medium/high-risk data-foundation behavior contract |
| feature purity and scoring | `ALLOWED_ALPHA_FEATURES`, `BINANCE_OHLCV_CORE_WEIGHTS`, `validate_alpha_feature_columns`, `score_binance_ohlcv_core`, `prepare_scored_backtest_frame` | high-risk score-surface behavior contract |
| PIT universe and eligibility | `freeze_binance_ohlcv_universe`, `apply_point_in_time_rolling_universe`, `add_pit_strategy_eligibility` | high-risk PIT behavior contract |
| risk brakes | `add_short_squeeze_veto_multiplier`, `add_binance_risk_brake_columns`, `_add_high_vol_rebound_short_brake` | high-risk risk-overlay behavior contract |
| validation and falsification | `run_binance_canonical_validation`, `_run_falsification_suite`, `_validation_status`, `_rank_ic_summary` | high-risk validation gate contract |
| execution analysis | `compute_position_attribution`, `compute_factor_leave_one_out_attribution`, `build_paper_shadow_execution_ledger`, `run_binance_core_ablations` | high-risk execution/private-helper contract |
| partition boundary | `_partition_month` and shared month path boundaries | medium-risk partition dry-run already deferred |

## Why No Further Low-Risk Moves

The latest score-surface dry-run found no remaining pure helper around
`score_binance_ohlcv_core(...)`:

- feature constants are compatibility and formula inputs;
- feature purity helpers enforce fail-closed sidecar exclusion;
- normalized weights participate in manifest hash and score construction;
- missing feature handling is part of validation readiness;
- score output is active alpha behavior.

Moving those surfaces requires a behavior contract, not only import/signature
contracts.

## Required Future Workflow

For any future medium/high-risk decomposition:

1. Write a read-only dry-run artifact naming the exact surface.
2. Add a behavior contract or identify existing tests that prove unchanged
   behavior.
3. Keep `binance_canonical_h10d.py` as the root facade unless owner explicitly
   approves a compatibility break.
4. Run the narrow behavior tests plus:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This closure artifact is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No source movement is included in the closure commit.
- The next automation batch must begin with a new owner-gated dry-run, not an
  implementation commit.
- No artifact paths are staged or committed.
