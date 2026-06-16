# Intraday Baseline Contract

`Status: preregistered baseline contract`
`Date: 2026-06-16`
`Scope: independent intraday research baseline for Tardis-backed 1h/sub-1h lanes`
`Trading action: none`
`Live impact: none`

## Decision

Intraday research must use a baseline stack that is separate from the h10d
cross-sectional baseline.

The h10d baseline can remain an opportunity-cost reference or a later bridge
comparison, but it is not the primary baseline for intraday mechanism proof.
Intraday candidates must first prove event-time information, cost feasibility,
delay robustness, and control-group separation against intraday controls.

This contract must be satisfied before opening the next intraday mechanism
design. It defines labels, cost layers, delay rules, control groups, universe
coverage, proof gates, and artifacts. It does not define a trading strategy,
portfolio construction, position sizing, order type, or live execution path.

## Baseline Layers

The intraday baseline stack has three layers.

### Layer 1: Mechanism Baseline

Purpose: prove whether the event or state variable contains information.

Allowed outputs:

```text
event labels
control labels
effect size
bootstrap confidence interval
shuffle tests
holdout tests
cost feasibility diagnostics
```

Forbidden outputs:

```text
strategy PnL
portfolio allocation
position sizing
live target
order instruction
```

### Layer 2: Executability Baseline

Purpose: prove the effect is not an artifact of midprice, zero latency, or
unrealistic fill assumptions.

Allowed outputs:

```text
bid/ask-adjusted label diagnostics
spread and fee stress
top-book depth feasibility
decision-delay sensitivity
funding-accrual sensitivity when relevant
```

This layer still does not authorize trading actions. It is a feasibility
filter before any Stage B return ablation.

### Layer 3: Naive Intraday Strategy Baseline

Purpose: after Layer 1 and Layer 2 pass, compare a future mechanism candidate
against a deliberately simple intraday rule.

This layer is not active yet. A future document must preregister it separately
before computing strategy PnL. The naive rule must be simple enough to be a
control, for example fixed event family, fixed direction, fixed delay, fixed
horizon, and fixed cost model.

## Universe Contract

BTCUSDT and ETHUSDT are required anchor symbols, but they are not sufficient for
a generalized intraday baseline.

### Tier 0: Anchor-Only Universe

```text
symbols = BTCUSDT, ETHUSDT
allowed_use = infrastructure smoke, timestamp sanity, anchor mechanism proof
generalized_intraday_baseline_allowed = false
```

Tier 0 is useful because BTC and ETH have deep liquidity, high data quality,
and stable Tardis coverage. It is not enough because:

- two symbols cannot test cross-sectional generality;
- BTC and ETH share market-beta and macro liquidity regimes;
- symbol holdout is nearly meaningless with only two names;
- liquidity-bucket proof collapses into one high-liquidity bucket;
- a BTC/ETH-only result can be a large-cap crypto index effect rather than an
  intraday mechanism.

Any BTC/ETH-only pass must be labeled:

```text
anchor_mechanism_evidence_only
not_generalized_intraday_baseline
```

### Tier 1: Frozen Liquid-Perp Core

A generalized intraday baseline requires a frozen point-in-time liquid-perp
core selected before label inspection.

Minimum scope:

```text
exchange = binance-futures first
symbols_total_min = 12
non_btc_eth_symbols_min = 8
distinct_liquidity_buckets_min = 3
distinct_months_with_min_events_min = 18
```

Preferred scope:

```text
symbols_total_target = 20
non_btc_eth_symbols_target = 18
```

Selection must use only predeclared liquidity inputs, for example:

```text
median traded notional
median quote volume
median top5 depth notional
missing raw partition fraction
stale book fraction
instrument continuity
```

Selection must not use forward returns, event labels, strategy outcomes, or any
post-event response variable. The universe-selection artifact must record
selection date, lookback window, ranked candidate list, included symbols,
excluded symbols, and hashes of all input partitions.

### Frozen Core v1 Selector

The first implementation of the Tier 1 universe contract is:

```text
scripts/quant_research/parallel_1h/build_tardis_intraday_liquid_perp_core_universe.py
```

It is a universe-freeze and staging-plan runner only. It does not download
Tardis data, scan raw files, normalize parquet, run Stage A, compute strategy
PnL, or authorize trading actions.

The retained local freeze artifact for `2026-06-16-intraday-liquid-perp-core-v1`
uses the latest retained PIT liquidity universe input:

```text
source = artifacts/quant_research/_quant_inputs/pit-liquidity-top100-2026-05-31.quant_universe.json
source_sha256 = 59853073aa5f3258fe57b9e3387956615d8aeda4f0542d1b640cc3a5d59502a9
summary = artifacts/quant_research/factor_reports/2026-06-16-intraday-liquid-perp-core-v1/intraday_liquid_perp_core_universe/intraday_liquid_perp_core_universe_summary.json
summary_sha256 = 5e45f375524460fd7ef9823de94ed9279f4b2fd6d36383868a4eded3c33f5d37
status = frozen_scope_passed_historical_stage_a_blocked
stage_a_universe_scope_ready = true
historical_stage_a_scope_ready = false
stage_a_proof_computed = false
strategy_pnl_computed = false
trading_action_authorized = false
```

The frozen core is:

```text
BTCUSDT, ETHUSDT, SOLUSDT, ZECUSDT, XRPUSDT, DOGEUSDT, BNBUSDT, SUIUSDT,
LTCUSDT, AAVEUSDT, DASHUSDT, UNIUSDT, ENAUSDT, ASTERUSDT, WLDUSDT, FETUSDT,
ALGOUSDT, POLUSDT, ETCUSDT, OPUSDT
```

This clears the Tier 1 symbol-scope gate: `20` total symbols, `18` non-BTC/ETH
symbols, and `3` liquidity buckets. It does not clear generalized historical
Stage A scope because the current PIT-valid forward proof window is only
`2026-06-01` through `2026-06-13`, so `distinct_months_with_planned_staging = 1`
is below the `18`-month requirement. That forward window has since been staged
and rerun as core20 columnar Stage A evidence. Longer historical expansion must
not reuse this fixed core backward; it must use the rolling PIT contract below.

### Tier 2: Holdout Universe

For generalized proof, the runner must retain:

```text
btc_eth_holdout
btc_eth_excluded_holdout
single_symbol_leave_one_out
liquidity_bucket_holdout
month_holdout
```

The mechanism may be allowed to depend on a liquidity bucket only if the bucket
dependence is explicitly declared as the mechanism. Otherwise, bucket-only
survival is a fail-closed condition.

## Label Contract

Labels are proof labels, not trade labels.

### Price Labels

For every event timestamp, compute both mid/mark informational labels and
bid/ask-adjusted feasibility labels:

```text
fwd_return_5m
fwd_return_15m
fwd_return_1h
fwd_return_4h
fwd_return_24h
max_adverse_move_15m
max_adverse_move_1h
max_adverse_move_4h
max_favorable_move_15m
max_favorable_move_1h
max_favorable_move_4h
```

Primary direction must be declared before execution:

```text
continuation = response moves with event-side pressure
reversal = response moves against event-side pressure
```

The primary horizon must also be declared before execution:

```text
primary_horizon in {5m, 15m, 1h, 4h, 24h}
```

### Liquidity And Derivative-State Labels

The baseline must compute liquidity and derivative-state confirmation labels:

```text
realized_vol_15m
realized_vol_1h
realized_vol_4h
spread_change_5m
spread_change_15m
spread_change_1h
top5_depth_recovery_15m
top5_depth_recovery_1h
book_imbalance_change_15m
book_imbalance_change_1h
open_interest_change_1h
funding_or_basis_change_4h
stale_quote_fraction
```

Price response alone is not sufficient when the proposed mechanism is a
liquidity-shock or microstructure state. At least one non-price confirmation
label must support the event interpretation.

## Cost Contract

Every intraday proof must report four cost layers.

```text
C0_mid_informational:
  midprice or mark-price response only.
  Used for mechanism discovery, never for executability claims.

C1_spread_fee:
  bid/ask side selection plus taker fee or configured conservative fee.
  Required before any "tradable-looking" wording.

C2_depth_slippage:
  spread_fee plus top-book or top5 depth impact proxy.
  Must report feasible notional and depth exhaustion risk.

C3_stress:
  doubled spread and fee, plus adverse one-bar slippage.
  Used as the fail-closed stress layer.
```

Funding must be included when a label horizon crosses a funding timestamp or
when the mechanism explicitly depends on funding, open interest, basis, or
carry.

Cost pass conditions:

```text
estimated_spread_fee_bps < 50% of primary_effect_bps
C2_depth_feasible_for_research_notional = true
C3_stress_does_not_reverse_primary_direction = true
event_bar_spread_worst_5pct_fraction <= 0.40
```

If C0 passes but C1 or C2 fails, the result may be retained only as
non-tradable mechanism evidence.

## Delay Contract

All inputs must be strictly point-in-time.

```text
feature_timestamp < decision_timestamp
label_start_timestamp >= decision_timestamp
raw_partition_hash_recorded = true
```

The baseline must report:

```text
D0_zero_delay_diagnostic
D1_plus_1_event_bar
D2_plus_5m
D3_plus_15m
D4_plus_1h
```

Delay pass conditions:

```text
D1_plus_1_event_bar_preserves_primary_direction = true
D1_plus_1_event_bar_effect_bps >= 50% of D0 effect bps
D2_plus_5m_preserves_primary_direction = true for 5m or faster mechanisms
D3_plus_15m_preserves_primary_direction = true for 15m to 1h mechanisms
D4_plus_1h_reported = true for all mechanisms
```

If the mechanism works only at D0 and fails at D1, it is classified as
timestamp-sensitive and cannot proceed to Stage B.

## Control Groups

The runner must build control panels that do not use future labels.

Required controls:

```text
same_symbol_time_of_day_matched_non_event
same_symbol_month_matched_non_event
same_symbol_time_shift_shuffle
same_timestamp_cross_symbol_shuffle
label_shuffle
pre_event_placebo_window
post_event_delayed_placebo_window
btc_eth_holdout
btc_eth_excluded_holdout
liquidity_bucket_matched_control
volatility_bucket_matched_control
```

Control pass conditions:

```text
observed_effect_abs > q95_abs_same_symbol_time_shift_effect
observed_effect_abs > q95_abs_cross_symbol_shuffle_effect
observed_effect_abs > q95_abs_label_shuffle_effect
pre_event_placebo_does_not_reproduce_effect = true
time_of_day_matched_control_effect_smaller = true
volatility_bucket_control_effect_smaller = true
```

## Proof Gates

### Coverage Gates

Anchor-only proof gates:

```text
symbols = BTCUSDT, ETHUSDT
event_count_total >= 300
event_count_by_primary_symbol >= 40
distinct_months_with_min_events >= 18
missing_required_input_fraction <= 0.02
duplicate_event_key_count = 0
result_scope = anchor_mechanism_evidence_only
generalized_intraday_baseline_allowed = false
```

Generalized intraday baseline gates:

```text
symbols_total >= 12
non_btc_eth_symbols >= 8
event_count_total >= 2000
event_count_by_symbol_min >= 40
distinct_months_with_min_events >= 18
liquidity_buckets_with_min_events >= 3
event_count_by_liquidity_bucket_min >= 150
missing_required_input_fraction <= 0.02
raw_source_hashes_recorded = true
columnar_partition_hashes_recorded = true
duplicate_event_key_count = 0
btc_eth_event_fraction <= 0.40
btc_eth_positive_evidence_fraction <= 0.40
largest_symbol_positive_evidence_fraction <= 0.25
```

### Mechanism Gates

```text
primary_direction_effect_sign_consistent = true
primary_horizon_abs_mean_or_median_effect_bps >= 5
primary_horizon_bootstrap_ci_excludes_zero = true
tail_response_diff_vs_control_nonzero = true
realized_vol_or_liquidity_response_confirms_shock = true
```

The 5 bps floor may be too high for some ultra-liquid BTC/ETH effects and too
low for small alts. Any future runner may add a cost-relative floor, but it may
not remove the absolute bps floor without a new contract amendment.

### Robustness Gates

```text
same_symbol_time_shift_shuffle_fails_to_reproduce_effect = true
same_timestamp_cross_symbol_shuffle_fails_to_reproduce_effect = true
label_shuffle_fails_to_reproduce_effect = true
monthly_holdout_directional_consistency >= 0.60
symbol_holdout_directional_consistency >= 0.60
btc_eth_excluded_holdout_preserves_direction = true
btc_eth_holdout_does_not_fully_erase_effect = true
liquidity_bucket_consistency_passes = true
delay_D1_passes = true
cost_C1_passes = true
```

### Stage Advancement Gates

Stage A may pass only if coverage, mechanism, cost C1, delay D1, and robustness
gates all pass.

Stage B return ablation may be opened only after Stage A passes and after a
separate preregistration defines:

```text
naive intraday strategy baseline
entry timestamp
exit timestamp
direction rule
cost layer
delay assumption
notional/capacity assumption
turnover cap
paper-only artifact boundary
```

No Stage B result may be interpreted from this contract alone.

## Required Artifacts

A baseline runner must retain:

```text
intraday_baseline_definition.json
intraday_baseline_universe_selection_audit.json
intraday_baseline_input_audit.json
intraday_baseline_label_panel.parquet
intraday_baseline_control_panel.parquet
intraday_baseline_cost_delay_report.json
intraday_baseline_robustness.json
intraday_baseline_coverage_report.json
intraday_baseline_summary.json
intraday_baseline_profile.json
```

The summary must include:

```text
result_scope
generalized_intraday_baseline_allowed
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

## Relation To Current Tardis Liquidity-Shock Work

The retained BTC/ETH liquidity-shock Stage A run is valid as Tier 0 anchor
evidence and as a data-platform proof. It is not a generalized intraday
baseline, because it has only BTCUSDT and ETHUSDT.

The next intraday data expansion should not merely add more days for BTC and
ETH. It should add a frozen liquid-perp core selected by point-in-time
liquidity criteria, then rerun the baseline proof with BTC/ETH-excluded and
liquidity-bucket holdouts.

Status update on 2026-06-16: the frozen 20-symbol liquid-perp core has now been
staged as raw Tardis partitions, normalized to parquet, and rerun through the
same Stage A proof runner in `normalized_parquet_only` mode. This execution is
no longer BTC/ETH-only and no longer raw-missing, but it still fails the
generalized Stage A contract because the PIT-valid forward window currently has
only one eligible month versus the 18-month gate, and the mechanism/robustness
proof gates do not pass. No Stage B, strategy PnL, trading action, or live path
is authorized.

Follow-up contract on 2026-06-16:
`rolling_pit_core_universe_contract_2026_06_16.md` defines the only approved
historical expansion path for the generalized intraday universe. Longer history
must use monthly pre-evaluation freeze dates, pre-freeze selection lookbacks,
monthly candidate pools, monthly selected symbols, and retained hash lineage.
The `2026-05-31` fixed core must not be backfilled into older months to satisfy
the 18-month gate.

## Non-Authorization

This contract does not authorize:

- strategy PnL;
- return ablation;
- portfolio construction;
- score-layer admission;
- h10d bridge admission;
- manifest mutation;
- paper-shadow ledger creation;
- live, timer, scheduler, or remote-runner activation;
- order generation or trading action.
