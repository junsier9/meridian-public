# Rolling PIT Core Universe Contract

`Status: rolling PIT contract; owner-approved raw staging completed; Stage A eligible monthly masks ready`
`Date: 2026-06-16`
`Scope: rolling point-in-time core universe for Tardis-backed intraday Stage A proof`
`Trading action: none`
`Live impact: none`

## Decision

The fixed `2026-05-31` 20-symbol frozen core cannot be backfilled into prior
months to satisfy the 18-month intraday coverage gate. That would leak future
liquidity and survival information into historical months.

The next valid historical expansion must use a rolling point-in-time core:

```text
monthly freeze before evaluation month
-> select liquid-perp core using only pre-freeze information
-> stage raw Tardis data for that month's selected symbols
-> normalize to parquet
-> run Stage A only on the monthly PIT-selected universe
```

This contract defines the monthly freeze dates, selection lookback, candidate
symbol rules, data types, hash lineage, batch staging boundaries, Stage A
integration rules, proof gates, and required artifacts. It does not authorize
Tardis download execution by itself, Stage B return ablation, strategy PnL,
portfolio construction, live targets, order generation, or trading action.

## Research Identifier

```text
rolling_pit_intraday_liquid_perp_core_v1
```

This is a universe and data-lineage contract, not a precursor mechanism and not
a trading strategy.

## Problem Statement

The 20-symbol core frozen on `2026-05-31` is valid only for forward data:

```text
freeze_date = 2026-05-31
first_valid_evaluation_date = 2026-06-01
```

Using that same selected list for `2025-01` through `2026-05` would be
lookahead-biased because the selection already knows which symbols were liquid,
listed, and surviving as of `2026-05-31`.

The rolling contract fixes this by assigning each evaluation month its own
freeze date and universe selection.

## Calendar Contract

All dates are UTC calendar dates. The first proposed historical proof window is:

```text
evaluation_months = 2025-01 through 2026-06
evaluation_start = first day of each evaluation month
evaluation_end = last available day in that month
latest_partial_month_end = 2026-06-13 unless fresher Tardis raw data is staged
```

For every evaluation month:

```text
freeze_date = last calendar day before evaluation_month starts
lookback_end = freeze_date
lookback_start = freeze_date - 89 calendar days
selection_lookback_days_target = 90
selection_lookback_days_min = 30
first_valid_label_timestamp >= evaluation_month_start 00:00:00 UTC
last_valid_feature_timestamp <= decision_timestamp
```

Examples:

| evaluation month | freeze date | lookback start | lookback end | evaluation window |
| --- | --- | --- | --- | --- |
| `2025-01` | `2024-12-31` | `2024-10-03` | `2024-12-31` | `2025-01-01` through `2025-01-31` |
| `2025-02` | `2025-01-31` | `2024-11-03` | `2025-01-31` | `2025-02-01` through `2025-02-28` |
| `2026-05` | `2026-04-30` | `2026-01-31` | `2026-04-30` | `2026-05-01` through `2026-05-31` |
| `2026-06` | `2026-05-31` | `2026-03-03` | `2026-05-31` | `2026-06-01` through latest staged day |

The selection lookback may require staging raw data before the first evaluation
month. For a `2025-01` proof, selection data may begin on `2024-10-03`. Those
lookback rows are selection inputs only and must not be counted as Stage A label
months for `2025-01`.

## Candidate Symbol Contract

The first venue is:

```text
exchange = binance-futures
instrument_type = USDT-margined linear perpetual
```

The candidate pool for each freeze date must be derived only from PIT-available
inputs, such as Tardis instrument metadata, retained raw coverage, and pre-freeze
liquidity observations. It must not use future returns, future listings,
future delistings, event labels, strategy outcomes, or post-event response
variables.

Eligible symbols:

```text
symbol suffix = USDT
contract is perpetual or perpetual-equivalent in Tardis binance-futures data
symbol has at least selection_lookback_days_min valid lookback days
symbol has required raw data coverage within the lookback window
symbol is not a dated quarterly future
symbol is not a stablecoin/fiat proxy unless explicitly approved by a later contract
```

Required anchors:

```text
BTCUSDT
ETHUSDT
```

The anchors are included if they pass PIT eligibility. If either anchor fails
raw coverage or listing eligibility for a month, that month fails closed rather
than silently replacing the anchor.

Target selected core:

```text
symbols_total_target = 20
symbols_total_min = 12
non_btc_eth_symbols_target = 18
non_btc_eth_symbols_min = 8
distinct_liquidity_buckets_min = 3
```

If fewer than 20 symbols pass PIT eligibility in a month, the month may remain
usable only if it still satisfies the minimum gates. If it falls below a
minimum gate, the monthly freeze is retained as failed coverage evidence.

## Selection Lookback Metrics

The monthly ranking may use only pre-freeze observations:

```text
median_trade_notional_90d
median_quote_count_or_update_count_90d
median_top5_depth_notional_90d
median_spread_bps_90d
raw_partition_missing_fraction_90d
stale_quote_fraction_90d
instrument_continuity_days
lookback_valid_days
```

The default ranking score is a deterministic liquidity composite:

```text
rank_score =
  + rank_pct(median_trade_notional_90d)
  + rank_pct(median_top5_depth_notional_90d)
  + rank_pct(instrument_continuity_days)
  - rank_pct(median_spread_bps_90d)
  - rank_pct(raw_partition_missing_fraction_90d)
  - rank_pct(stale_quote_fraction_90d)
```

This score is a selection device only. It must not be interpreted as an alpha
signal or trading feature.

Liquidity buckets are assigned after selection using PIT rank score quantiles:

```text
bucket_high_liquidity
bucket_mid_liquidity
bucket_tail_liquidity
```

The monthly selection artifact must record the exact bucket boundaries and
membership. Bucket membership may change month to month.

## Data Type Contract

### Selection Inputs

The selection runner may read the following retained Tardis raw data types from
the lookback window:

```text
trades
book_ticker
book_snapshot_5
derivative_ticker
```

`liquidations` may be staged for downstream Stage A continuity but must not be
used to rank the universe unless a later contract explicitly allows
forced-flow activity as a selection dimension.

### Stage A Inputs

The Stage A mechanism proof uses the same data surface as the current
liquidity-shock lane:

```text
trades
liquidations
book_ticker
book_snapshot_5
derivative_ticker
```

For each evaluation month, Stage A may use only symbols selected by that
month's PIT freeze. Raw data for non-selected candidates may be retained for
lineage and future diagnostics, but the Stage A event and label panels must
exclude them from proof counts and effect estimates.

## Raw And Columnar Staging Contract

Raw vendor data stays outside the repo checkout.

Expected external roots follow the existing two-host pattern:

```text
storage raw root = /tank/tardis/raw_stores/tardis_intraday_liquidity_shock
compute raw root = /data/meridian/hot_stage/tardis_intraday_liquidity_shock
compute normalized root = /data/meridian/hot_stage/tardis_intraday_liquidity_shock_columnar_rolling_pit_core_v1_<window>
```

Batch staging must execute in this order:

```text
1. write dry-run monthly freeze plan
2. stage raw lookback partitions needed for monthly selection
3. compute monthly PIT universe selection artifacts
4. stage raw evaluation-month partitions for selected symbols
5. normalize retained raw data to parquet
6. run Stage A proof only from normalized parquet
```

The Stage A runner must remain columnar-only:

```text
raw_scan_executed_by_runner = false
downloads_executed_by_runner = false
input_mode = normalized_parquet_only
```

No Stage A proof runner may call Tardis, scan raw gzip/CSV, mutate raw staging,
or infer a universe from labels.

## Hash Lineage Contract

Every monthly freeze artifact must retain:

```text
contract_id
contract_version
evaluation_month
freeze_date
lookback_start
lookback_end
exchange
candidate_pool_version
candidate_symbols
selected_symbols
excluded_symbols_with_reason
liquidity_bucket_assignments
selection_metric_definitions
selection_config_sha256
selection_code_sha256
source_raw_partition_hashes
source_metadata_hashes
raw_partition_missing_fraction
label_free_selection_assertion = true
future_data_used_for_selection = false
strategy_pnl_computed = false
trading_action_authorized = false
```

The raw staging manifest must retain one record per staged partition:

```text
exchange
data_type
symbol
date
raw_path
raw_size_bytes
raw_sha256
download_status
source_url_or_dataset_id_without_api_key
```

The normalized manifest must link back to both raw and monthly freeze lineage:

```text
monthly_freeze_manifest_sha256
raw_staging_manifest_sha256
normalized_partition_path
normalized_partition_sha256
source_raw_partition_hashes
normalizer_code_sha256
normalizer_config_sha256
raw_source_missing_required_input_fraction
normalized_missing_required_input_fraction
```

The aggregate Stage A summary must link every evaluated event to:

```text
evaluation_month
monthly_freeze_manifest_sha256
selected_symbol_for_month = true
normalized_partition_sha256
```

If any monthly freeze manifest is missing, malformed, unhashable, or uses data
after its freeze date, the aggregate proof must fail closed.

## Batch Stage A Integration

Two execution shapes are allowed:

```text
monthly_stage_a_then_aggregate:
  run Stage A separately for each evaluation month and aggregate proof labels
  only after all monthly runs retain valid freeze lineage.

single_batch_stage_a_with_monthly_mask:
  pass an explicit monthly universe mask to a batch runner so each event month
  uses only symbols selected before that month.
```

Both shapes must produce the same semantic audit fields:

```text
monthly_freeze_count
monthly_freeze_fail_count
monthly_freeze_manifest_sha256_by_month
symbols_by_month
liquidity_buckets_by_month
event_count_by_month
event_count_by_symbol
event_count_by_liquidity_bucket
btc_eth_event_fraction
btc_eth_excluded_holdout_result
symbol_holdout_result
liquidity_bucket_holdout_result
```

It is forbidden to run one fixed symbol list across all months unless that list
was selected before the first evaluation month and explicitly retained as a
separate fixed-PIT historical core contract. The `2026-05-31` core is not such
a contract.

## Coverage Gates

The rolling PIT universe proof can satisfy the 18-month coverage gate only if:

```text
evaluation_month_count >= 18
valid_monthly_freeze_manifest_count >= 18
monthly_freeze_manifest_missing_count = 0
future_data_used_for_selection_count = 0
monthly_selected_symbols_min >= 12
monthly_non_btc_eth_symbols_min >= 8
monthly_liquidity_bucket_count_min >= 3
monthly_raw_source_hashes_recorded = true for every month
monthly_columnar_partition_hashes_recorded = true for every month
aggregate_missing_required_input_fraction <= 0.02
duplicate_event_key_count = 0
event_count_total >= 2000
event_count_by_month_min >= 5
event_count_by_symbol_min >= 40 for symbols counted in generalized proof
event_count_by_liquidity_bucket_min >= 150
btc_eth_event_fraction <= 0.40
largest_symbol_event_fraction <= 0.25
```

Months with insufficient PIT candidates, missing anchors, missing raw coverage,
or invalid freeze lineage remain retained failed evidence and cannot be patched
by borrowing symbols from later months.

## Mechanism And Robustness Gates

This contract does not change the intraday Stage A mechanism gates. The rolling
proof still inherits the baseline contract gates:

```text
primary_direction_effect_sign_consistent = true
primary_horizon_abs_mean_or_median_effect_bps >= 5
primary_horizon_bootstrap_ci_excludes_zero = true
tail_response_diff_vs_control_nonzero = true
realized_vol_or_liquidity_response_confirms_shock = true
same_symbol_time_shift_shuffle_fails_to_reproduce_effect = true
same_timestamp_cross_symbol_shuffle_fails_to_reproduce_effect = true
label_shuffle_fails_to_reproduce_effect = true
monthly_holdout_directional_consistency >= 0.60
symbol_holdout_directional_consistency >= 0.60
btc_eth_excluded_holdout_preserves_direction = true
liquidity_bucket_consistency_passes = true
delay_D1_passes = true
cost_C1_passes = true
```

A rolling PIT coverage pass does not by itself create mechanism proof. If the
effect remains weak or shuffle-reproducible, Stage A still fails.

## Required Artifacts

The first implementation must retain:

```text
rolling_pit_core_universe_definition.json
rolling_pit_core_monthly_freeze_plan.json
rolling_pit_core_candidate_pool_audit.json
rolling_pit_core_monthly_selection_audit.json
rolling_pit_core_raw_staging_manifest.json
rolling_pit_core_normalized_manifest.json
rolling_pit_core_stage_a_input_audit.json
rolling_pit_core_stage_a_coverage_report.json
rolling_pit_core_stage_a_summary.json
rolling_pit_core_stage_a_profile.json
```

Monthly freeze artifacts must also be materialized as one file per evaluation
month:

```text
monthly_freezes/<YYYY-MM>/monthly_universe_selection_audit.json
monthly_freezes/<YYYY-MM>/selected_symbols.csv
monthly_freezes/<YYYY-MM>/candidate_ranking.csv
monthly_freezes/<YYYY-MM>/hash_lineage.json
```

The aggregate summary must include:

```text
rolling_pit_contract_id
rolling_pit_contract_version
stage_a_proof_allowed
stage_b_return_ablation_allowed
strategy_pnl_computed
trading_action_authorized
live_or_timer_use_authorized
```

For this contract, the last four fields must remain:

```text
stage_b_return_ablation_allowed = false unless a later Stage A pass exists
strategy_pnl_computed = false
trading_action_authorized = false
live_or_timer_use_authorized = false
```

## Next Allowed Implementation

Implemented dry-run code step:

```text
scripts/quant_research/parallel_1h/build_tardis_intraday_rolling_pit_core_universe_plan.py
```

This runner materializes the rolling monthly freeze artifacts and dry-run
staging plan. It may not download Tardis data, normalize parquet, run Stage A,
compute strategy PnL, or create trading actions unless those later steps are
separately requested and bounded by this contract. Its dry-run proxy selection
is explicitly not a Stage A eligible monthly universe mask; Stage A still
requires monthly PIT selection computed from retained pre-freeze raw metrics.

The next data step, if separately requested, is owner-approved external raw
staging for:

```text
selection lookback window: 2024-10-03 through 2026-05-31
evaluation window: 2025-01-01 through latest staged 2026-06 date
```

The exact end date must be fixed in the run manifest before download starts.

Owner-approved raw staging and monthly mask construction have now been executed
for the first `2025-01` through `2026-06` window on the storage host. The
retained raw staging manifest is:

```text
/tank/tardis/manifests/tardis_intraday_liquidity_shock/20260616T_rolling_pit_core_v1_raw_from_manifest_retry1.json
sha256=cf48959b9b19fe536532d3a72c5a4caa7063d4f21ed30f4b5fcd3813802f0300
```

It retained `250111` available raw files under:

```text
/tank/tardis/raw_stores/tardis_intraday_liquidity_shock
```

The manifest remains `success=false` only because one upstream Tardis partition
failed after retries:

```text
TONUSDT derivative_ticker 2026-04-30
http_status=500
body.code=20
attempt_count=11
```

That failure is retained as upstream failed-partition evidence and must not be
silently converted to missing data.

The retained Stage A eligible monthly universe masks are:

```text
/tank/tardis/artifacts/rolling_pit_core_v1_monthly_masks/20260616T_rolling_pit_core_v1_monthly_masks_from_raw_retry1/rolling_pit_core_monthly_universe_masks.json
sha256=cdd44874917ef43c52c147485737b481d172fe834e5e9b140dbcf0ccaf9408d0
```

The corresponding summary is:

```text
/tank/tardis/artifacts/rolling_pit_core_v1_monthly_masks/20260616T_rolling_pit_core_v1_monthly_masks_from_raw_retry1/rolling_pit_core_stage_a_summary.json
sha256=fd84f26efd9b36fd1290a95d2c93fe03fc7f7f401cc1b3e1339d8e554dcfcb3e
status=stage_a_monthly_universe_masks_ready
stage_a_monthly_universe_masks_ready=true
valid_monthly_freeze_manifest_count=18
blocking_gates=[]
```

This mask runner scanned retained pre-freeze raw metrics only. It did not
normalize parquet, run Stage A proof, compute strategy PnL, or create trading
actions. The next implementation step must be separately requested and should
start with monthly-mask-aware `raw -> normalized parquet` staging, followed by a
columnar-only Stage A proof runner that consumes these monthly masks.

## Non-Authorization

This contract does not authorize:

- Tardis download execution by itself;
- Stage B return ablation;
- strategy PnL;
- portfolio construction;
- position sizing;
- score-layer admission;
- h10d bridge admission;
- manifest mutation;
- paper-shadow ledger creation;
- live, timer, scheduler, or remote-runner activation;
- order generation or trading action.
