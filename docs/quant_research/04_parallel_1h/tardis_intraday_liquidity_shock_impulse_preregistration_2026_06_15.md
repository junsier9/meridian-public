# Tardis Intraday Liquidity-Shock Impulse Preregistration

`Status: BTC/ETH 18-month Stage A coverage passed but mechanism failed; 20-symbol PIT core columnar Stage A failed coverage/mechanism gates`
`Date: 2026-06-15`
`Scope: independent Tardis-backed intraday research lane`
`Trading action: none`
`Live impact: none`

## Decision

Open an independent Tardis-backed intraday research lane:

```text
tardis_intraday_liquidity_shock_impulse_v0
```

This is not a h10d overlay, not a portfolio throttle, not a score-layer feature,
not a paper-shadow rule, and not a trading strategy. It defines only data,
labels, proof gates, and retained artifacts for an intraday mechanism proof.

The lane is separate from the closed M3.1 options-surface portfolio-throttle
path. Options data may later appear as context, but the first proof is about
liquidity-shock impulse in trades, liquidations, derivatives state, and order
book state.

## Research Question

Does a point-in-time Tardis liquidity-shock event produce a stable and
tradable-looking short-horizon response in BTC/ETH and liquid perpetual swaps?

The first proof asks for mechanism evidence only:

```text
liquidity shock at event time t
=> measurable forward response in return, realized volatility, tail move,
   spread/book state, or derivative state over 15m, 1h, 4h, and 24h
```

No return ablation, position sizing, entry rule, exit rule, portfolio
construction, or live execution may be interpreted before this proof passes.

## Data Contract

All inputs must be sourced from retained Tardis raw partitions or retained
derived panels whose source partitions and hashes are recorded.

### Phase A Data Scope

Phase A keeps the input surface deliberately small:

| family | Tardis data type | required use |
| --- | --- | --- |
| Trades | `trades` | trade count, signed/aggressor flow proxy, volume burst, VWAP move |
| Liquidations | `liquidations` | forced-flow event trigger and side classification |
| Best bid/ask | `book_ticker` | spread, midprice, BBO movement, stale quote audit |
| Top book state | `book_snapshot_5` | top-5 imbalance, depth collapse, top-book recovery |
| Derivative state | `derivative_ticker` | open interest, funding rate, mark/index basis |

`book_snapshot_25` is allowed only as a Phase A sensitivity input when top-5
depth is insufficient. `incremental_book_L2` is explicitly out of scope for the
first proof because it can consume large storage/compute before the mechanism
is established.

### Exchange And Symbol Scope

Phase A starts narrow:

```text
exchanges = binance-futures first
symbols = BTCUSDT, ETHUSDT, plus a frozen top-liquid-perp set
```

The frozen top-liquid-perp set must be selected before label inspection using a
retained PIT liquidity snapshot, for example by median quote volume over a
pre-declared lookback. Bybit, OKX, Deribit perps, and cross-exchange
dislocation proofs are Phase B only.

### Timestamp Policy

- Use `local_timestamp` for partition ordering and ingestion completeness.
- Use exchange `timestamp` when available for event-time alignment, while
  retaining `local_timestamp` for latency and stale-message diagnostics.
- When multiple events share a timestamp, preserve CSV row order as the
  deterministic tie-breaker.
- A feature row is valid only if every input observation is strictly before the
  decision timestamp.
- Daily CSV partitions are treated as immutable vendor inputs after hash
  capture.

### Storage Boundary

Raw Tardis partitions stay outside the repo checkout. A proof runner may read
from an external raw store and write only derived proof artifacts under a
repo-local or operator-supplied artifacts root. Raw vendor CSV data, Tardis API
keys, and bearer tokens must not be checked into git or copied into reports.

## Event Definitions

The first implementation may define several event families, but they must be
predeclared and reported separately:

```text
liquidation_burst =
  liquidation_notional over the event bar is unusually high for the symbol
  and the event has a clear forced-flow side

trade_pressure_burst =
  trade notional and signed/aggressor-flow proxy expand over the event bar

book_thinning =
  top-5 same-side depth falls materially before or during the event

basis_oi_state_change =
  OI, funding, or mark-index basis moves in the same direction as forced flow
```

Allowed first-pass event bars:

```text
1m
5m
15m
```

The runner must report which event family fired. A combined event is diagnostic
only until each component family has standalone proof.

## Labels

Labels are proof labels, not trade labels.

### Price Response

For each event timestamp, compute forward midprice or mark-price returns:

```text
fwd_return_15m
fwd_return_1h
fwd_return_4h
fwd_return_24h
max_adverse_move_1h
max_favorable_move_1h
max_adverse_move_4h
max_favorable_move_4h
```

The label direction must be declared relative to the shock side:

```text
continuation = price moves with forced-flow pressure after the event
reversal = price moves against forced-flow pressure after the event
```

Both continuation and reversal can be measured, but one primary direction must
be preregistered per event family before pass/fail scoring.

### Volatility And Liquidity Response

Compute:

```text
realized_vol_15m
realized_vol_1h
realized_vol_4h
spread_change_15m
spread_change_1h
top5_depth_recovery_15m
top5_depth_recovery_1h
book_imbalance_change_15m
book_imbalance_change_1h
oi_change_1h
funding_or_basis_change_4h
```

These labels decide whether the event is a real liquidity shock even when the
return direction is weak.

## Proof Gates

The first retained proof may pass only if all hard gates clear.

### Coverage Gates

```text
raw_partition_hashes_recorded = true
event_input_observations_strictly_before_label = true
missing_required_input_fraction <= 0.02
duplicate_event_key_count = 0
event_count_total >= 300
event_count_by_primary_symbol >= 40 for BTC and ETH
event_count_by_month_min >= 5 for at least 18 distinct months
```

### Mechanism Gates

At least one primary event family must pass:

```text
primary_direction_effect_sign_consistent = true
primary_horizon_abs_mean_or_median_effect_bps >= 5
primary_horizon_bootstrap_ci_excludes_zero = true
tail_response_diff_vs_control_nonzero = true
realized_vol_or_liquidity_response_confirms_shock = true
```

The primary horizon is one of:

```text
15m
1h
4h
24h
```

It must be declared before the proof runner is executed.

### Robustness Gates

```text
same-symbol time-shift shuffle fails to reproduce effect
same-timestamp cross-symbol shuffle fails to reproduce effect
label shuffle fails to reproduce effect
monthly holdout directionally consistent in at least 60% of eligible months
BTC/ETH holdout does not fully erase the effect
liquidity bucket consistency passes or the bucket dependence is explicitly reported as the mechanism
```

### Cost And Feasibility Gates

The first proof is not a strategy, but it must still reject effects that are
obviously non-actionable:

```text
estimated_spread_cost_bps < 50% of primary_effect_bps
event bar spread is not in the worst 5% for more than 40% of passing events
top5 notional depth supports at least a small research notional without crossing all visible levels
effect survives a +1 event-bar decision delay
```

### Fail-Closed Conditions

The proof fails if:

- the effect appears only after using data timestamped at or after the label
  start;
- one symbol or one month supplies most positive evidence;
- event labels are driven by exchange downtime, reconnect artifacts, or stale
  book states;
- the conclusion depends on `incremental_book_L2` tuning in Phase A;
- the result is only a daily or h10d aggregate after intraday labels are
  collapsed.

## Required Artifacts

A proof runner must write only these retained artifacts:

```text
intraday_liquidity_shock_definition.json
intraday_liquidity_shock_input_audit.json
intraday_liquidity_shock_event_panel.parquet
intraday_liquidity_shock_event_panel_sample.csv
intraday_liquidity_shock_label_panel.parquet
intraday_liquidity_shock_summary.json
intraday_liquidity_shock_robustness.json
intraday_liquidity_shock_coverage_report.json
```

`event_panel_sample.csv` is for review only and must be bounded. Full raw Tardis
vendor rows must not be copied into the repo.

The summary must include:

```text
contract_version
research_id
generated_at_utc
status
proof_allowed
stage_b_return_ablation_allowed = false
trading_action_authorized = false
live_or_timer_use_authorized = false
raw_input_paths
raw_input_sha256
event_counts
coverage_gates
mechanism_gates
robustness_gates
cost_feasibility_gates
blockers
```

## Stage A Runner

The Stage A raw-to-columnar normalizer is:

```text
scripts/quant_research/parallel_1h/normalize_tardis_intraday_liquidity_shock_raw_to_parquet.py
```

It is the only entrypoint in this lane that may scan retained external Tardis
raw gzip/CSV partitions. It writes normalized parquet bar-feature partitions,
a manifest with raw-source hashes, and a normalization profile. It does not
compute Stage A proof, strategy PnL, return ablation, portfolio construction,
live targets, or trading actions.

The Stage A-only proof runner is:

```text
scripts/quant_research/parallel_1h/run_tardis_intraday_liquidity_shock_impulse_stage_a.py
```

It is a proof-artifact materializer only. Current contract version is
`quant_tardis_intraday_liquidity_shock_impulse_stage_a.v2_columnar`: the runner
must read retained normalized parquet staging plus the normalizer manifest. It
rejects `--raw-root` and records `raw_scan_executed_by_runner=false`. The runner
writes the required proof artifacts plus a profile artifact, and stops before
any strategy PnL, return ablation, entry/exit rule, sizing rule, portfolio
construction, score-layer admission, manifest mutation, paper-shadow path,
live/timer path, remote-runner path, or trading action.

The runner does not download Tardis data. It defaults to an external normalized
parquet boundary and records both `downloads_executed_by_runner=false` and
`raw_scan_executed_by_runner=false` in retained artifacts.

Canonical two-step execution shape:

```text
python scripts/quant_research/parallel_1h/normalize_tardis_intraday_liquidity_shock_raw_to_parquet.py \
  --as-of <AsOf> \
  --from-date <FromDate> \
  --to-date <ToDate> \
  --raw-root <ExternalRawRoot> \
  --source-input-audit <RetainedRawInputAuditJson> \
  --normalized-root <ExternalColumnarRoot> \
  --max-workers <N>

python scripts/quant_research/parallel_1h/run_tardis_intraday_liquidity_shock_impulse_stage_a.py \
  --as-of <AsOf> \
  --from-date <FromDate> \
  --to-date <ToDate> \
  --normalized-root <ExternalColumnarRoot> \
  --normalized-manifest <ExternalColumnarRoot>/manifests/<AsOf>.json \
  --output-root <RunArtifactsRoot>
```

The profile artifacts are part of the language/runtime decision boundary. Any
proposal to move kernels into C++, Rust, Numba, or Cython must first cite the
normalizer profile and Stage A profile, and identify the measured slowest
kernel or phase.

`--source-input-audit` is preferred when a retained Stage A raw input audit
already records raw partition paths and hashes. That avoids re-hashing hundreds
of GB of raw gzip files just to re-establish lineage.
`--max-workers` is the first allowed performance lever: it parallelizes
independent symbol/date normalization tasks while preserving Python orchestration
and retained profiling.

## Local Blocked Proof Run

A historical pre-columnar local Stage A proof run was executed on 2026-06-15
against the default Windows external raw-root boundary:

```text
%LOCALAPPDATA%\EnhengClaw\market_history\tardis_intraday_liquidity_shock
```

No raw partitions were present, so that retained proof was correctly blocked:

```text
status = blocked_missing_raw_partitions
proof_allowed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
downloads_executed_by_runner = false
event_counts = {bars: 0, events: 0, labels: 0}
```

Retained local artifact root:

```text
artifacts/quant_research/factor_reports/2026-06-15-stage-a/tardis_intraday_liquidity_shock_impulse_stage_a/
```

Artifact hashes:

```text
intraday_liquidity_shock_definition.json      sha256=41d4dcf08f0aa80cc0c1f5550b7b82bfb4198ae984109bd2a21d2f1bfb4239d8
intraday_liquidity_shock_input_audit.json     sha256=cd14c2c046a99ffabd1c2011bb32fab6d64349578510bf86fd6253a4f988ee90
intraday_liquidity_shock_event_panel.parquet  sha256=f5a4484b831c6f6c5c9e1efc90e5a8126b1c78513b501275b2d145368777f557
intraday_liquidity_shock_event_panel_sample.csv sha256=7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6
intraday_liquidity_shock_label_panel.parquet  sha256=f5a4484b831c6f6c5c9e1efc90e5a8126b1c78513b501275b2d145368777f557
intraday_liquidity_shock_summary.json         sha256=e1a88a5c0dfb3954d4bebc4c70a5a159725d7ea631c58255f760246b07b7d3c7
intraday_liquidity_shock_robustness.json      sha256=38d0b261ea86625002db14f027a4f485e7d7a011fec49ea5e99149c6ac3ce267
intraday_liquidity_shock_coverage_report.json sha256=ed4f986c279705a6715c7d6e46b0d93c2898029b1b3023971468fe7f1b1bb01a
```

## Explicit Non-Actions

This preregistration forbids:

- entry rules;
- exit rules;
- sizing rules;
- leverage rules;
- portfolio construction;
- score-layer admission;
- h10d bridge interpretation;
- manifest mutation;
- paper-shadow use;
- live, timer, scheduler, or remote-runner use;
- execution against Binance, Deribit, OKX, Bybit, or any other venue.

## Remote Data Staging Boundary

A non-blocked Stage A proof should still stage Tardis raw data on the remote
storage host before compute, because the proof depends on daily raw-source
lineage and wide intraday coverage. That staging is a separate owner-approved
data operation, not part of the Stage A proof runner. Raw data must remain
outside the repo. The raw-to-columnar normalizer consumes the raw-root, and the
Stage A runner is re-executed only after `--normalized-root` and the normalizer
manifest are available.

## Remote Stage A Smoke Run

A remote smoke run was executed on 2026-06-15 using only one staged date:

```text
exchange = binance-futures
symbols = BTCUSDT, ETHUSDT
data_types = trades, liquidations, book_ticker, book_snapshot_5, derivative_ticker
date = 2026-06-13
```

Raw staging retained 10/10 expected daily gzip partitions outside the repo:

```text
storage raw root = /tank/tardis/raw_stores/tardis_intraday_liquidity_shock
storage manifest = /tank/tardis/manifests/tardis_intraday_liquidity_shock/20260615T044420Z_stage_a_smoke_20260613.json
storage manifest sha256 = 4fe75a64d62a3a96d0cf2fafdf78fbbacb4a68be6b82bb9b809f14ec7d725e4c
expected_partition_count = 10
existing_or_downloaded_count = 10
failed_count = 0
raw_vendor_data_retained = true
strategy_pnl_computed = false
trading_action_authorized = false
```

The smoke partitions were staged to compute:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock
```

Then the Stage A runner was executed against that external raw root. The result
advanced from raw-missing into real Stage A mechanism evaluation, but still
failed the preregistered proof gates:

```text
status = computed_failed_stage_a
proof_allowed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
downloads_executed_by_runner = false
bars = 576
events = 104
labels = 104
raw_partition_hashes_recorded = true
missing_required_input_fraction = 0.0
event_count_by_symbol = {BTCUSDT: 58, ETHUSDT: 46}
```

Remaining blockers:

```text
event_count_total_below_300
distinct_months_with_min_events_below_18
primary_event_count_below_30
primary_horizon_bootstrap_ci_does_not_exclude_zero
```

Remote proof artifact root:

```text
/data/meridian/artifacts/factor_reports/2026-06-15-stage-a-smoke-20260613/tardis_intraday_liquidity_shock_impulse_stage_a/
```

Remote artifact hashes:

```text
intraday_liquidity_shock_definition.json         sha256=c1f5b3f4b00635348171764fbe57008a21fa7a54db6dbbe9c05048817c912fde
intraday_liquidity_shock_input_audit.json        sha256=f8e740f33689ee4a605ac727fa40820bbc965e53608acc388e0c3895051f5d4f
intraday_liquidity_shock_event_panel.parquet     sha256=149bea9f2a4dc4203e769ebf74563abe7d21013aad72ed2bf17bbbe8c5d37840
intraday_liquidity_shock_event_panel_sample.csv  sha256=294980d650f906446bf70b4d9cd9f53d4c8d7ddce4a25f1c191e169a8b076934
intraday_liquidity_shock_label_panel.parquet     sha256=34fa4b08b6ef1374a889afed139a02d4cc7a2b0ba045b45423b6fc124a3e333c
intraday_liquidity_shock_summary.json            sha256=5de181ee72528f06b2d82e094e105031ac27277fd573bc61bf351cc84d7604ce
intraday_liquidity_shock_robustness.json         sha256=0ffaad7677350a56ad3170b8ed38e9c5afa5bbdf46a8ebd6d6398ac592a01c14
intraday_liquidity_shock_coverage_report.json    sha256=a50fb97072769cd14dd2f4bc0f6ba7baeed06c30e629f03eb065dd9965d1a329
```

## Remote Cross-Month Stage A Rerun

The staging window was then expanded on 2026-06-15 to a continuous cross-month
window while keeping the same Stage A runner and the same no-Stage-B boundary:

```text
exchange = binance-futures
symbols = BTCUSDT, ETHUSDT
data_types = trades, liquidations, book_ticker, book_snapshot_5, derivative_ticker
from_date = 2026-05-27
to_date = 2026-06-13
distinct_calendar_months_staged = 2
```

Raw staging retained 180/180 expected daily gzip partitions outside the repo:

```text
storage raw root = /tank/tardis/raw_stores/tardis_intraday_liquidity_shock
storage manifest = /tank/tardis/manifests/tardis_intraday_liquidity_shock/20260615T045952Z_stage_a_cross_month_20260527_20260613.json
storage manifest sha256 = 9540a48c926b089de8c5bfc8c6c61b258091df4ca7afbd06a324a014c8feebf3
expected_partition_count = 180
existing_or_downloaded_count = 180
failed_count = 0
storage_partition_count = 180
compute_partition_count = 180
retained_raw_size_bytes = 13736523549
raw_vendor_data_retained = true
strategy_pnl_computed = false
trading_action_authorized = false
```

The cross-month partitions were staged to compute:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock
```

The same Stage A runner then wrote the retained proof artifacts under:

```text
/data/meridian/artifacts/factor_reports/2026-06-15-stage-a-cross-month-20260527-20260613/tardis_intraday_liquidity_shock_impulse_stage_a/
```

Result:

```text
status = computed_failed_stage_a
proof_allowed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
downloads_executed_by_runner = false
bars = 10360
events = 2082
labels = 2082
raw_partition_hashes_recorded = true
missing_required_input_fraction = 0.0
event_count_total = 2082
event_count_min = 300
event_count_by_symbol = {BTCUSDT: 1102, ETHUSDT: 980}
event_count_by_month = {2026-05: 572, 2026-06: 1510}
distinct_months_with_min_events = 2
distinct_months_with_min_events_min = 18
primary_event_count = 404
primary_horizon_bootstrap_ci_excludes_zero = false
```

This rerun clears the earlier `event_count_total_below_300` and
`primary_event_count_below_30` blockers and proves that the raw-missing state has
become a real cross-month mechanism test. It still fails the preregistered Stage
A proof because only 2 distinct months were staged versus the required 18, and
the primary 1h bootstrap confidence interval still includes zero.

Remaining blockers:

```text
distinct_months_with_min_events_below_18
primary_horizon_bootstrap_ci_does_not_exclude_zero
```

Remote cross-month artifact hashes:

```text
intraday_liquidity_shock_definition.json         sha256=e2b22b019a0baf597212f1fcb518fcf3579332cf0dff873db8c446a7404bfb81
intraday_liquidity_shock_input_audit.json        sha256=ff5a41a8110252d663fc0899ea45cd09bc134ecaa2f34be7ed773a4aad59a8b2
intraday_liquidity_shock_event_panel.parquet     sha256=4cee51293b043c40c807a8155cc6d5fba79f469b7f94793913f8dc598bdb282b
intraday_liquidity_shock_event_panel_sample.csv  sha256=6d4e9233cf7a5d36d5242360faf28fb7fcefdc038cc465df7d64805a26028e00
intraday_liquidity_shock_label_panel.parquet     sha256=d76262c096fe574511b46ba0bfa85a866289bf84f1527322cc6f7f86bb086d82
intraday_liquidity_shock_summary.json            sha256=61faa84b046b2f63a69f90a1121bb59be6b40f503cd90495ce4873ea27513c24
intraday_liquidity_shock_robustness.json         sha256=6baeda003c3f3d6ccdcf9fddd4fdc5ff2085143aeeee0d742526c865b0233351
intraday_liquidity_shock_coverage_report.json    sha256=2909c5d60909e1a74d024c22ba03498be2eed6fca6a50d171cec5f6e59e48bc8
```

## Remote 18-Month Stage A Rerun

The staging window was then expanded to the preregistered 18 distinct calendar
months while keeping the same Stage A runner and the same no-Stage-B boundary:

```text
exchange = binance-futures
symbols = BTCUSDT, ETHUSDT
data_types = trades, liquidations, book_ticker, book_snapshot_5, derivative_ticker
from_date = 2025-01-01
to_date = 2026-06-13
distinct_calendar_months_staged = 18
```

Raw staging retained 5290/5290 expected daily gzip partitions outside the repo:

```text
storage raw root = /tank/tardis/raw_stores/tardis_intraday_liquidity_shock
storage manifest = /tank/tardis/manifests/tardis_intraday_liquidity_shock/20260615T_stage_a_18m_20250101_20260613_parallel4.json
storage manifest sha256 = bf35c47323606f318c1b0624d1ddd106d7dbc7894afb53079bfa5446ed3c0026
expected_partition_count = 5290
completed_partition_count = 5290
downloaded_count = 4823
existing_count = 467
failed_count = 0
storage_partition_count = 5290
compute_partition_count = 5290
retained_raw_size_bytes = 338327222114
api_key_logged = false
raw_vendor_data_retained = true
strategy_pnl_computed = false
trading_action_authorized = false
```

The full staged archive was synchronized to compute:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock
```

The same Stage A runner then wrote the retained proof artifacts under:

```text
/data/meridian/artifacts/factor_reports/2026-06-15-stage-a-18m-20250101-20260613/tardis_intraday_liquidity_shock_impulse_stage_a/
```

Result:

```text
status = computed_failed_stage_a
proof_allowed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
downloads_executed_by_runner = false
bars = 304684
events = 57672
labels = 57672
raw_partition_hashes_recorded = true
missing_required_input_fraction = 0.0
event_count_total = 57672
event_count_min = 300
event_count_by_symbol = {BTCUSDT: 29454, ETHUSDT: 28218}
distinct_months_with_min_events = 18
distinct_months_with_min_events_min = 18
primary_event_count = 11518
primary_horizon_abs_mean_or_median_effect_bps = 0.11584578150806907
primary_horizon_abs_mean_or_median_effect_bps_min = 5.0
primary_horizon_bootstrap_ci = {ci_low: -0.0001523286730186117, ci_high: 0.00014887065823262894}
primary_horizon_bootstrap_ci_excludes_zero = false
monthly_holdout_directional_consistency = 0.5
monthly_holdout_directional_consistency_min = 0.6
```

This rerun clears the preregistered coverage gates. It still fails Stage A
because the primary 1h reversal effect is far below the 5 bps floor, the
bootstrap confidence interval includes zero, robustness shuffles reproduce the
effect, monthly holdout directionality is below the 60% floor, and BTC/ETH
holdout erases or cannot support the effect.

Remaining blockers:

```text
primary_horizon_effect_bps_below_5
primary_horizon_bootstrap_ci_does_not_exclude_zero
same_timestamp_cross_symbol_shuffle_reproduces_effect
label_shuffle_reproduces_effect
monthly_holdout_directional_consistency_below_0_60
btc_eth_holdout_erases_effect_or_insufficient
```

Remote 18-month artifact hashes:

```text
intraday_liquidity_shock_definition.json         sha256=71b2a2e064d03b573f8c71a6b7a0ca2e5a8a5920145fe091fbebc64e8a4e6098
intraday_liquidity_shock_input_audit.json        sha256=a1203591f7c67ef0dc26ffaa369492a4dbaacfab32c22eb71770fec4bd44964c
intraday_liquidity_shock_event_panel.parquet     sha256=6180f10044f90698d63c195579750bae3a3530c85fbc100d3809dd83780c3afd
intraday_liquidity_shock_event_panel_sample.csv  sha256=12a8787bf6a3640f0ada5531e46f4c3bed6e47e5182c67f2b1bc32c2ae8e7e13
intraday_liquidity_shock_label_panel.parquet     sha256=30a11618b78bdcb35b486438c6ae702cc5faa1fa66d66aef0a1c92cb20de8cd7
intraday_liquidity_shock_summary.json            sha256=578088971fe4dd59f5a98abe3491149066ba928c3606dcb5a29fec27979accc1
intraday_liquidity_shock_robustness.json         sha256=6e09d07d157c389b78ac949dbe0d728d92376149f0c16e5b68377abad6a70214
intraday_liquidity_shock_coverage_report.json    sha256=0f305bb4f0e9296d77a816439499cf7c610ddae207610b415c6e47dcdba0b5fe
```

## Columnar Pipeline Implementation

After the 18-month Stage A result, the execution substrate was updated without
changing the mechanism gates and without entering Stage B. The new boundary is:

```text
raw Tardis gzip/CSV -> normalized parquet bar_features -> Stage A proof runner
```

Local smoke coverage proves the normalizer can materialize a daily parquet
partition from all five raw Tardis data types and that the Stage A runner
rejects `--raw-root`. The Stage A runner now scans only columnar staging and
writes:

```text
intraday_liquidity_shock_profile.json
```

This implementation does not reinterpret the retained 18-month raw-run result.
The result remains `computed_failed_stage_a`.

## Remote Columnar Profiling Rerun

Remote profiling was then executed on the same 18-month staged raw window while
preserving the no-Stage-B boundary.

Columnar staging root:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock_columnar_v1_profile_20250101_20260613
```

Normalizer manifest:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock_columnar_v1_profile_20250101_20260613/manifests/2026-06-15-stage-a-18m-columnar-v1-20250101-20260613.json
sha256=a39b36f6ac28064dcf24db83e9c11f99e6bd328e779da3fc8363eed4d864fdc8
```

Normalizer retained:

```text
expected_normalized_partition_count = 1058
normalized_partition_count = 1058
skipped_normalized_partition_count = 0
normalized_missing_required_input_fraction = 0.0
raw_source_hashes_reused_from_input_audit = true
max_workers = 4
normalized_root_size = 79M
stage_a_proof_computed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
```

Normalizer profile:

```text
raw_input_audit_seconds = 0.033503
normalize_and_write_seconds = 4739.878081
total_seconds_before_manifest = 4739.912128
partition_profiles = 1058
written_partitions = 995
existing_reused_partitions = 63
sum_written_partition_aggregate_seconds = 18940.63924
sum_written_partition_write_seconds = 2.503075
```

Because this run reused `63` partitions left by an earlier interrupted serial
attempt, the retained wall-clock profile is not a pure cold-start benchmark.
It is still sufficient for the first language-runtime decision: the measured
hot work is raw gzip/CSV decode plus bar aggregation, while parquet writing is
negligible and the proof runner is no longer raw-bound.

The columnar-only Stage A rerun artifact root is:

```text
/data/meridian/artifacts/factor_reports/2026-06-15-stage-a-18m-columnar-v1-dedup-20250101-20260613/tardis_intraday_liquidity_shock_impulse_stage_a/
```

It retained:

```text
input_mode = normalized_parquet_only
raw_scan_executed_by_runner = false
downloads_executed_by_runner = false
status = computed_failed_stage_a
proof_allowed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
bars = 304684
events = 57637
labels = 57637
event_count_total = 57637
event_count_by_symbol = {BTCUSDT: 29434, ETHUSDT: 28203}
distinct_months_with_min_events = 18
missing_required_input_fraction = 0.0
raw_source_missing_required_input_fraction = 0.0
duplicate_event_key_count = 0
```

The mechanism verdict remains failed:

```text
primary_horizon_abs_mean_or_median_effect_bps = 0.16132385761609927
primary_horizon_abs_mean_or_median_effect_bps_min = 5.0
primary_horizon_bootstrap_ci_excludes_zero = false
monthly_holdout_directional_consistency = 0.5
monthly_holdout_directional_consistency_min = 0.6
same_timestamp_cross_symbol_shuffle_reproduces_effect
label_shuffle_reproduces_effect
btc_eth_holdout_erases_effect_or_insufficient
```

Stage A profile:

```text
total_before_profile_write = 3.753678
read_columnar_bars = 2.655415
build_events_and_labels = 0.508411
write_artifacts_before_summary = 0.300436
summarize_stage_a_proof = 0.198891
columnar_input_audit = 0.089989
setup = 0.000277
expected_columnar_partitions = 1058
found_columnar_partitions = 1058
columnar_input_bytes = 71156678
```

Remote columnar artifact hashes:

```text
intraday_liquidity_shock_definition.json         sha256=8f79dce98a445c1d1729432be21eac8aca01bd9239568c53bde076f8aae0141c
intraday_liquidity_shock_input_audit.json        sha256=3eea539fd0342c58210e6036f503eea3c87caf1fe7db4c5aab0b2c1c6e957181
intraday_liquidity_shock_event_panel.parquet     sha256=d3df6652727efe88994a80edef71fffd0c8b4f286155aae4960a1194cc0032ac
intraday_liquidity_shock_event_panel_sample.csv  sha256=7944f1c1a36adb9b2c67d43cd8424669833c844ec4f946636b682c4f47f36905
intraday_liquidity_shock_label_panel.parquet     sha256=a27e73ee981d3ab1d768a54b53b5cb39e73823fe380be53c69f5f8fb2e84c122
intraday_liquidity_shock_summary.json            sha256=d3ab7a5c5b64c3a215f477d1e74c0b0dd30d6dffa1c24bf657422632795b13db
intraday_liquidity_shock_robustness.json         sha256=2804229931e6e9badfdb7709004351c7d8a3e3297e601e0a75f3a970d1a8cf18
intraday_liquidity_shock_coverage_report.json    sha256=1e780092f9226b01ac36926a9863e1bbaedd281dcd01169971f67bb8aae9f85b
intraday_liquidity_shock_profile.json            sha256=2c8f36f6011ad747c3a495ed4eba35fdb3fff6aa9f8278434a5538fb2dabd05c
```

Profiling conclusion:

```text
bottleneck = raw gzip/CSV normalization and aggregation
not_bottleneck = columnar Stage A proof runner
not_bottleneck = parquet writing
language_rewrite_decision = defer full-stack rewrite
next_optimization_target = normalizer raw-decode/bar-aggregation kernel only
```

Any Rust/C++/Numba/Cython work must now target the slowest measured normalizer
kernel, not the whole research stack. Python remains the orchestration layer
until a narrower profiling run proves one or two kernels deserve replacement.

## Remote Frozen Core20 Columnar Stage A Run

On 2026-06-16 the frozen PIT liquid-perp core from
`intraday_baseline_contract_2026_06_16.md` was executed through the separated
data path:

```text
raw Tardis gzip/CSV -> normalized parquet bar_features -> Stage A proof runner
```

The run used the PIT-valid forward window after the `2026-05-31` universe
snapshot:

```text
exchange = binance-futures
symbols = BTCUSDT, ETHUSDT, SOLUSDT, ZECUSDT, XRPUSDT, DOGEUSDT, BNBUSDT,
          SUIUSDT, LTCUSDT, AAVEUSDT, DASHUSDT, UNIUSDT, ENAUSDT, ASTERUSDT,
          WLDUSDT, FETUSDT, ALGOUSDT, POLUSDT, ETCUSDT, OPUSDT
from_date = 2026-06-01
to_date = 2026-06-13
data_types = trades, liquidations, book_ticker, book_snapshot_5, derivative_ticker
```

Raw staging retained:

```text
storage manifest = /tank/tardis/manifests/tardis_intraday_liquidity_shock/20260616T_stage_a_core20_20260601_20260613_raw.json
storage manifest sha256 = 13054ee3f3ee0b8a170f91048e5d57149e4a9087fca118cf390edfd43b0234b3
expected_partition_count = 1300
completed_partition_count = 1300
failed_count = 0
distinct_calendar_months_completed = 1
retained_raw_size_bytes = 32418244301
api_key_logged = false
strategy_pnl_computed = false
trading_action_authorized = false
```

The staged raw archive was synchronized to compute and verified `1300/1300`
present under:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock
```

The temporary host-to-host rsync key marker `meridian-core20-rsync-20260616`
was removed from compute `authorized_keys`, its backup was removed, and
`/tmp/meridian_core20_rsync_ed25519*` was removed from storage.

Columnar staging root:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock_columnar_core20_v1_20260601_20260613
```

Normalizer manifest:

```text
/data/meridian/hot_stage/tardis_intraday_liquidity_shock_columnar_core20_v1_20260601_20260613/manifests/2026-06-16-stage-a-core20-columnar-v1-20260601-20260613.json
sha256=9192cfcff8c3a9a6cb79b1ebf8a0ddf11dcfa44f42f422b7298ed41f77afe302
```

Normalizer retained:

```text
expected_normalized_partition_count = 260
normalized_partition_count = 260
normalized_missing_required_input_fraction = 0.0
max_workers = 8
normalized_root_size = 19M
stage_a_proof_computed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
```

Normalizer profile:

```text
raw_input_audit_seconds = 20.234358
normalize_and_write_seconds = 238.192201
total_seconds_before_manifest = 258.426916
```

The columnar-only Stage A artifact root is:

```text
/data/meridian/artifacts/factor_reports/2026-06-16-stage-a-core20-columnar-v1-dedup-20260601-20260613/tardis_intraday_liquidity_shock_impulse_stage_a/
```

It retained:

```text
input_mode = normalized_parquet_only
raw_scan_executed_by_runner = false
downloads_executed_by_runner = false
status = computed_failed_stage_a
proof_allowed = false
stage_b_return_ablation_allowed = false
strategy_pnl_computed = false
trading_action_authorized = false
bars = 74780
events = 12388
labels = 12388
event_count_total = 12388
event_count_by_symbol = {AAVEUSDT: 636, ALGOUSDT: 530, ASTERUSDT: 611,
  BNBUSDT: 720, BTCUSDT: 733, DASHUSDT: 526, DOGEUSDT: 556, ENAUSDT: 554,
  ETCUSDT: 583, ETHUSDT: 696, FETUSDT: 538, LTCUSDT: 593, OPUSDT: 551,
  POLUSDT: 624, SOLUSDT: 596, SUIUSDT: 638, UNIUSDT: 635, WLDUSDT: 696,
  XRPUSDT: 619, ZECUSDT: 753}
event_count_by_month = {2026-06: 12388}
distinct_months_with_min_events = 1
distinct_months_with_min_events_min = 18
missing_required_input_fraction = 0.0
raw_source_missing_required_input_fraction = 0.0
duplicate_event_key_count = 0
```

The run therefore proves that the 20-symbol frozen core moved past raw-missing
into real mechanism evaluation. It still fails Stage A because the PIT-forward
window has only one eligible month and the primary effect does not pass the
preregistered mechanism or robustness gates:

```text
primary_horizon_abs_mean_or_median_effect_bps = 3.602503640186001
primary_horizon_abs_mean_or_median_effect_bps_min = 5.0
primary_horizon_bootstrap_ci_excludes_zero = false
same_timestamp_cross_symbol_shuffle_reproduces_effect
label_shuffle_reproduces_effect
```

Stage A profile:

```text
total_before_profile_write = 0.889913
read_columnar_bars = 0.578578
build_events_and_labels = 0.141444
write_artifacts_before_summary = 0.097004
summarize_stage_a_proof = 0.049831
columnar_input_audit = 0.022854
setup = 0.000157
expected_columnar_partitions = 260
found_columnar_partitions = 260
columnar_input_bytes = 16661862
```

Remote core20 artifact hashes:

```text
intraday_liquidity_shock_definition.json         sha256=8d40d2e5e22be5bd603b3d1fc714692b33b90e29345395afee1ddd386ad3cc36
intraday_liquidity_shock_input_audit.json        sha256=b4bcf7f2df08765cb4c40fb941009c58b7b894bd936b0e0a030160c4046d3534
intraday_liquidity_shock_event_panel.parquet     sha256=057c1d26b4183182d23b148b134d654a7f58a3614ea3c32d5a21f0f1cac7c0f5
intraday_liquidity_shock_event_panel_sample.csv  sha256=2a377abd47b69d69b87c6cfb90c641657375affe26438f07f494272c87c3e949
intraday_liquidity_shock_label_panel.parquet     sha256=fdc3abdd8253f5c296dabb918d8f46d3fd940142a152d67f2594f4635eb4888c
intraday_liquidity_shock_summary.json            sha256=b84bfde8f155856d6e28a30d31040ca6f7f6886a7d99dc42200e2fc43cff8f40
intraday_liquidity_shock_robustness.json         sha256=c6466e62e2e4a3b64e92a61de5571dc667a53e518913420f38b02d49a2efd8f6
intraday_liquidity_shock_coverage_report.json    sha256=8162c0824d9ef5ad50fffa06ec99c8b6a3bd47ee26e0361c3934d575cebbf9c7
intraday_liquidity_shock_profile.json            sha256=947fe84b7770a2bb71aadf7991e52617e969602dce027e63f019ac95c0f8f78f
```

## Next Allowed Step

The BTC/ETH 18-month coverage requirement has been met and the runner substrate
is now columnar-only. Profiling shows the current engineering bottleneck is raw
normalization and aggregation, not Stage A proof evaluation.

The frozen 20-symbol core has also been staged and rerun through the same
columnar-only Stage A runner. That run is no longer BTC/ETH-only and no longer
raw-missing, but it still fails because the PIT-forward window currently has
only one eligible month and the mechanism/robustness gates do not pass.

The next research step is now governed by:

```text
docs/quant_research/04_parallel_1h/intraday_baseline_contract_2026_06_16.md
docs/quant_research/04_parallel_1h/rolling_pit_core_universe_contract_2026_06_16.md
```

The retained BTC/ETH run is Tier 0 anchor-only evidence. It is valid for
infrastructure, timestamp sanity, and anchor mechanism diagnosis, but it is not
a generalized intraday baseline. Before any new or materially revised mechanism
hypothesis is interpreted, the lane must run the intraday baseline contract or
expand the frozen PIT liquid-perp core required by that contract.

The `2026-05-31` fixed 20-symbol core may not be backfilled into earlier months.
Any longer historical expansion must use the rolling PIT contract: one
pre-month freeze date, selection lookback, candidate pool, selected-symbol mask,
and hash lineage per evaluation month.

Because Stage A still failed, no Stage B return ablation, strategy PnL,
portfolio allocation, live target, or trade instruction may be created unless
Stage A first passes its retained proof gates.
