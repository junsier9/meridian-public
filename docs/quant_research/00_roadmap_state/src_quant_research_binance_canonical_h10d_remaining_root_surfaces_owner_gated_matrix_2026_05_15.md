# src quant_research binance_canonical_h10d remaining root surfaces owner-gated matrix

`Status: owner-gated root-surface classification baseline`
`Date: 2026-05-15`
`Scope: root-defined functions in binance_canonical_h10d.py after low-risk internal-module identity closure`

## Decision

Do not move additional source from
`src/enhengclaw/quant_research/binance_canonical_h10d.py` in the next automatic
batch.

The low-risk internal-module identity track is closed. The remaining
root-defined functions are behavior, orchestration, data-foundation, validation,
or shared-boundary surfaces. They should be governed first by a classification
contract that requires every root-defined function to be named in one owner
bucket, without freezing signatures, formulas, caller counts, line numbers, or
artifact schemas.

## Read-Only Inventory Result

AST scan found 70 root-defined functions in
`src/enhengclaw/quant_research/binance_canonical_h10d.py`.

Existing contracts already cover several behavior surfaces, including:

- partition boundary root-local placement;
- funding facade import/signature surface;
- score surface and feature-manifest tiny behavior samples;
- PIT universe and risk-brake behavior-test presence;
- validation/falsification status surfaces;
- reporting metric sanitation;
- run-backtest presence;
- extracted internal-module identity surfaces.

The remaining governance gap is not a missing behavior sample for one helper.
It is the lack of a single classification rule saying every root function must
belong to exactly one known owner bucket.

## Owner Buckets

| bucket | functions | automation stance |
| --- | --- | --- |
| `config_and_provider_entrypoints` | `load_strategy_config`, `default_strategy_config`, `discover_usdm_perp_symbols` | keep root; future signature-only dry-run allowed |
| `score_surface_and_feature_manifest` | `validate_alpha_feature_columns`, `assert_alpha_feature_purity`, `assert_alpha_feature_subset_purity`, `_allow_feature_subset`, `build_feature_manifest`, `score_binance_ohlcv_core`, `prepare_scored_backtest_frame` | no source move; existing score contract remains behavior boundary |
| `archive_data_foundation_and_feature_panel` | `aggregate_1m_klines`, `build_binance_canonical_dataset`, `build_symbol_feature_frame`, `_daily_bars_to_feature_panel`, `add_binance_ohlcv_core_features`, `_intraday_realized_vol_by_day`, `_settlement_premium_by_day` | owner-gated; do not split without data-foundation dry-run |
| `pit_universe_and_eligibility` | `freeze_binance_ohlcv_universe`, `apply_point_in_time_rolling_universe`, `add_pit_strategy_eligibility`, `_pit_recent_data_eligible`, `_truthy_series` | owner-gated; behavior-test presence only |
| `funding_facade_entrypoints` | `sync_funding_cost_history`, `fetch_funding_rate_rows`, `write_funding_cost_rows`, `load_funding_cost_daily`, `attach_funding_cost_to_panel` | keep root facade; provider sync behavior is not low risk |
| `validation_orchestration_and_artifacts` | `run_binance_canonical_validation`, `write_validation_artifacts`, `_validation_status`, `_funding_cost_status` | keep root; orchestration and artifact semantics are high-risk |
| `backtest_and_gap_policy` | `_run_backtest`, `apply_selected_path_gap_symbol_exclusion`, `_execution_data_gap_blockers_for_frame`, `_subjects_from_data_gap_blockers` | owner-gated; no golden backtest snapshots |
| `attribution_and_paper_shadow` | `compute_position_attribution`, `compute_factor_leave_one_out_attribution`, `build_paper_shadow_execution_ledger`, `_empty_position_attribution`, `_empty_factor_leave_one_out`, `_empty_paper_shadow_execution_ledger`, `_row_float`, `_paper_shadow_action`, `_summarize_paper_shadow_ledger`, `_apply_short_position_multiplier`, `_decision_rank_by_subject`, `_summarize_position_attribution`, `_factor_position_delta`, `_aggregate_position_contribution`, `_records` | medium/high; split only after behavior-smoke dry-run |
| `ablations_and_feature_subset_rescore` | `run_binance_core_ablations`, `add_core20_ablation_eligibility`, `_reference_core20_subjects`, `_rescore_for_feature_subset` | owner-gated; tied to score surface and artifact semantics |
| `risk_brake_behavior` | `add_short_squeeze_veto_multiplier`, `add_binance_risk_brake_columns`, `_add_high_vol_rebound_short_brake` | owner-gated; registry tuple contract does not approve formula movement |
| `falsification_and_holdout` | `_run_falsification_suite`, `_decision_time_liquidity_bucket_frame`, `_run_stratified_repeated_symbol_holdout`, `_stratified_holdout_policy`, `_symbol_stratification_frame`, `_stratified_two_way_subject_split`, `_stratum_counts` | high-risk; split only after falsification/holdout dry-run |
| `reporting_metric_sanitation` | `_rank_ic_summary`, `_strip_periods`, `_drop_periods_from_metrics`, `_split_contract` | keep root for now; reporting module expansion needs dry-run |
| `root_local_partition_boundary` | `_symbol_partition_paths`, `_partition_month` | root-local frozen by existing partition contract |

## Recommended Static Contract

Add a classification-only contract:

- read `binance_canonical_h10d.py` with AST;
- collect root-level `FunctionDef` names;
- require the union of all owner buckets to exactly match the AST function set;
- require each function to appear in exactly one bucket;
- require this matrix document to remain the approval artifact;
- explicitly exclude signatures, formula behavior, output schemas, line numbers,
  caller counts, source migration, and exact metrics.

This contract should not call any h10d runtime function.

## Deferred / Owner-Gated

Fresh dry-run required before:

- moving any function out of `binance_canonical_h10d.py`;
- adding a new internal module for data foundation, attribution, PIT universe,
  falsification, or reporting sanitation;
- changing partition placement;
- promoting a behavior contract into a source-migration approval;
- freezing full artifacts, markdown reports, validation payload schemas, or
  backtest golden outputs.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This matrix is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- A later implementation commit, if added, contains only a contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this classification batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
