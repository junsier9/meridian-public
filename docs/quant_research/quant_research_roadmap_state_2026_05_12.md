# Quant Research Roadmap State Map - 2026-05-12

`Snapshot date: 2026-05-12`
`Status: consolidation artifact`
`Scope: all 81 pre-existing Markdown source documents under docs/quant_research, excluding this consolidation artifact`
`Purpose: reconcile the original roadmap, later branches, data-foundation work, and the current active h10d validation frontier`

---

## Decision

The roadmap is no longer at the original broad "find more factors" stage, and
it is no longer inside the CoinGlass reopening cycle.

Current state:

```text
original multi-quarter roadmap
-> h10d canonical-parent correction and strict falsification loop
-> M3/MF/SP-K branch tests
-> CoinGlass full-stack data foundation and R-lane reopenings
-> parallel 1h manipulation/mechanical-flow lane
-> live/research baseline split after remote live operation started
```

As of the 2026-06-02 owner update, documentation must separate three identities:

1. Current remote live-operations baseline:

```text
v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget:multiphase_10_sleeve
```

This is the effective live config lineage recorded by
`docs/MERIDIAN_REMOTE_LIVE_STATE_2026_06_01.md` through the
`hv_balanced_binance_usdm_live_2x_full_balance_candidate` remote artifact/state
namespace. The effective construction is `target_engine = multiphase_equal_sleeve`:
ten 10d sleeves, daily phase offsets `0..9`, equal sleeve weight `0.1`, and
aggregate target weights summed across sleeves.

2. Default follow-on h10d research baseline:

```text
v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve
```

New h10d research branches should attach to the `v5_rw_bridge_no_overlay_h10d`
score parent by default, but performance, portfolio-construction, overlay, and
live-alignment studies should use the 10-phase equal-sleeve construction as the
research baseline unless a newer roadmap document explicitly overrides it.

3. Latest Binance-only PIT validation challenger:

```text
v5_binance_pit_top_mid_h10d_pruned3_hv_tail_only_soft_budget
```

It has passed the current Binance-only PIT validation gates, but it is not the
currently documented remote live config and is not the default follow-on
research baseline. CoinGlass, OI, liquidation, orderbook, top-trader, taker,
funding, and basis columns remain excluded from the core alpha in that
validation.

---

## How To Read The Folder Now

Read in this order:

1. This file: current map and branch ledger.
2. `00_roadmap_state/quant_research_script_catalog.md`: script entrypoint catalog to check before
   running, moving, or adding quant-research scripts.
3. `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12.md`: latest Binance-only PIT
   challenger status.
4. `02_binance_pit_h10d/binance_pit_pruned3_risk_brake_component_ablation_2026_05_12.md`: why the
   latest risk layer exists.
5. `03_alpha_branches/research_priority_update_full_stack.md`: why the CoinGlass/R-lane cycle is
   frozen.
6. `04_parallel_1h/parallel_1h_alpha_mining_roadmap.md`: what remains separate in the 1h lane.
7. `03_alpha_branches/provider_sidecar_h10d_preregistration_2026_05_17.md`: new
   provider-sidecar h10d branch anchored to frozen `hv_balanced` control.
8. `00_roadmap_state/next_stage_alpha_map.md`: historical index and rediscovery hook.

The older strategic documents are still useful, but they are not the current
execution state unless a newer report points back to them.

---

## Current Entry Contract

Use the same entry language in this roadmap and in
`scripts/quant_research/README.md`:

1. First decide the task type from the table below.
2. Then open `00_roadmap_state/quant_research_script_catalog.md`.
3. Run only scripts whose `run priority` matches that task type.
4. If the script is not `default_entrypoint`, treat the pointing doc as the
   authority for why it is being used.

| task type | entry document | script run priority | rule |
| --- | --- | --- | --- |
| follow-on h10d research | `config/quant_research/active_h10d_registry.json` plus `v5_rw_bridge_no_overlay_h10d` score-parent artifact and 10-phase construction note | `default_entrypoint` | attach new h10d branches to `v5_rw_bridge_no_overlay_h10d` by default; report current baseline performance with 10-phase equal-sleeve construction |
| current Binance PIT h10d hardening | `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12.md` | `default_entrypoint` | use only when the task explicitly concerns the Binance-only PIT challenger |
| data-foundation refresh | `01_data_foundation/market_data_inventory.md` plus provider-specific sync docs | `default_entrypoint` | refresh data substrates before alpha claims |
| CoinGlass sidecar/catalog work | `01_data_foundation/coinglass_full_stack_foundation_sync.md` | `default_entrypoint` or `supporting_tool` | sidecar/catalog only unless a new preregistered mechanism reopens it |
| scheduled automation | `config/scheduled_tasks/manifest.json` | `scheduled_only` | use scheduler contract, not ad hoc manual execution |
| quarantined falsification | preregistration or falsification report for that lane | `quarantined_falsification` | run only for that named quarantine test |
| historical audit or rediscovery | branch ledger row plus older report | `historical_do_not_start_here` | read for evidence; do not use as a new start point |
| one-off diagnostic/report writing | current roadmap/report that asks for it | `supporting_tool` | supporting tools require an explicit caller or doc reason |

The current default manual research route is therefore:

```text
roadmap state
-> script catalog
-> default_entrypoint rows in canonical_h10d_and_binance_pit
-> active_h10d_registry
-> v5_rw_bridge_no_overlay_h10d parent artifact
-> 10-phase equal-sleeve construction baseline
-> preregistered candidate branch report
```

---

## Original Complete Roadmap

`00_roadmap_state/strategy_upgrade_roadmap.md` defined the initial multi-quarter path:

| phase | original intent | current interpretation |
| --- | --- | --- |
| Phase 0 baseline | establish shadow-only baseline | completed and later superseded as a benchmark layer |
| Phase 1 factor engineering | expand factor families, de-correlate, dynamic weights | partially explored; broad smooth-factor expansion repeatedly failed strict incremental tests |
| Phase 2 portfolio construction | risk model, capacity sizing, optimization, drawdown throttle | now reappearing as Binance PIT risk-budget / drawdown hardening |
| Phase 3 alpha lifecycle | decay detection, throttling, retirement | not the active implementation layer yet |
| Phase 4 data extension | on-chain, options, microstructure, cross-asset spillovers | CoinGlass and related sidecars filled much of this, but did not produce a promoted alpha |
| Phase 5 model upgrade | linear ensemble, walk-forward retraining, shrinkage, optional NN | deferred until a clean alpha/risk base is stable |
| Phase 6 production hardening | realtime inference, risk monitoring, production audit | not reached for the latest h10d challenger |

The important correction is that the roadmap did not progress linearly from
Phase 1 to Phase 6. It branched because each new data class had to be tested for
incremental, point-in-time, out-of-sample value before it could be admitted.

---

## Actual Path Taken

| date | route | outcome |
| --- | --- | --- |
| 2026-05-03 | canonical h10d parent correction | `v5_rw_bridge_no_overlay_h10d` became the relevant parent for strict comparison; legacy `v6_h10d`, `regime_gating_v2`, and older SP-K variants became comparators |
| 2026-05-03 to 2026-05-04 | M3.3, M3.2, MF-01, MF-05, MF-07, SP-K branch tests | sparse/event selection ideas were useful, but most current forms failed strict falsification or became closed comparators |
| 2026-05-04 to 2026-05-09 | CoinGlass full-stack foundation and R-lane reopening | data catalog and sidecars became reusable; no CoinGlass reopening produced a strict survivor, manifest A/B candidate, or live candidate |
| 2026-05-07 onward | parallel 1h manipulation/mechanical-flow lane | kept separate from h10d; current first pass has no admitted 1h alpha |
| 2026-05-10 to 2026-05-12 | Binance-only PIT h10d reroute | frozen-universe/lookahead risk was diagnosed; rolling PIT top/mid universe, backfill, factor pruning, and risk-brake work produced the current passed challenger |
| 2026-06-03 | baseline construction correction | live baseline identity is `hv_balanced:multiphase_10_sleeve`; follow-on research baseline becomes `v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve` so single-phase 10d evidence is historical/comparator evidence, not the current default baseline |
| 2026-06-15 | M3.1 Tardis full backfill and options overlay v0 report-only ablation | raw backfill and full options-surface panel completed, but `m3_1_options_surface_top2_context_throttle_v0` failed research-watch; `context_allowed` / `overlay_context_research_allowed` means ablation permission only, not overlay availability |
| 2026-06-15 | M3.1 options surface v1 report-only ablation | `m3_1_options_surface_signed_gamma_put_skew_throttle_v1` completed report-only ablation and failed research-watch; trigger count stayed `8/640`, full-OOS return and max drawdown were worse than baseline, and no score-layer, manifest, v1 policy, live, timer, or scheduler authorization exists |
| 2026-06-15 | M3.1 options surface v2 Stage A loss-state diagnostic | `m3_1_options_surface_loss_state_confirmed_throttle_v2` Stage A was implemented and failed; v1 precursor triggers hit only `8` windows, only `2/8` were baseline-loss, `6/8` were baseline-positive, Stage B return ablation is not allowed, and the current `options stress -> portfolio throttle` shape is closed |
| 2026-06-15 | M3.1 options precursor mechanism reset | M3.1 options work returns to new precursor mechanism hypotheses only; no portfolio-throttle repair, no threshold micro-tuning, and no Stage B return ablation before retained loss-state proof |
| 2026-06-15 | M3.1 dealer hedge-pressure transition precursor closure | `m3_1_options_surface_dealer_hedge_pressure_transition_precursor_v0` was implemented only as a retained loss-state proof runner, failed, and is closed as failed mechanism evidence; trigger count reached `16`, but triggered baseline-loss fraction was only `5/16 = 0.3125`, positive leakage was `11/16 = 0.6875`, Stage B is not allowed, no trading action exists, and same-family confirmation-threshold tuning is forbidden |
| 2026-06-15 | Tardis intraday liquidity-shock impulse Stage A runner | `tardis_intraday_liquidity_shock_impulse_v0` opened as an independent intraday mechanism-proof lane under `04_parallel_1h`; the Stage A proof runner was implemented, local raw-missing and one-day/cross-month coverage smokes were retained, then external raw staging was expanded to the preregistered `2025-01-01` through `2026-06-13` 18-month window without changing the runner and without Stage B; storage manifest `sha256=bf35c47323606f318c1b0624d1ddd106d7dbc7894afb53079bfa5446ed3c0026` retained `5290/5290` BTC/ETH `binance-futures` partitions, failed `0`, and staged `338,327,222,114` raw bytes; the same Stage A runner reran to `computed_failed_stage_a` with summary `sha256=578088971fe4dd59f5a98abe3491149066ba928c3606dcb5a29fec27979accc1`; coverage gates are green (`event_count_total=57672`, BTCUSDT `29454`, ETHUSDT `28218`, `distinct_months_with_min_events=18`, missing fraction `0.0`), but mechanism/robustness gates fail on tiny primary effect (`0.1158457815` bps versus `5.0`), bootstrap CI including zero, same-timestamp cross-symbol shuffle, label shuffle, monthly holdout consistency `0.5 < 0.6`, and BTC/ETH holdout erasure/insufficiency; no strategy PnL, trading action, h10d bridge, Stage B return ablation, manifest mutation, live/timer/scheduler use, remote-runner use, or Tardis download by the runner is authorized |
| 2026-06-15 | Tardis intraday columnar staging and profiling pipeline | raw-to-columnar normalizer added for retained Tardis gzip/CSV partitions; Stage A runner contract moved to `v2_columnar`, rejects `--raw-root`, scans only normalized parquet staging, and writes a profile artifact. Remote profiling retained `1058/1058` normalized parquet partitions (`79M`, manifest `sha256=a39b36f6ac28064dcf24db83e9c11f99e6bd328e779da3fc8363eed4d864fdc8`) and a columnar-only Stage A rerun (`summary sha256=d3ab7a5c5b64c3a215f477d1e74c0b0dd30d6dffa1c24bf657422632795b13db`) with coverage still green (`event_count_total=57637`, `distinct_months_with_min_events=18`) but mechanism proof still failed. Profile says normalizer raw gzip/CSV decode plus aggregation is the bottleneck (`normalize_and_write_seconds=4739.878081`; summed written aggregation `18940.63924` worker-seconds), while parquet writing is only `2.503075` seconds and Stage A columnar proof is `3.753678` seconds. This is an infrastructure/profiling change only: no full-stack language rewrite, Stage B, strategy PnL, trading action, h10d bridge, manifest mutation, live, timer, or scheduler path is authorized |
| 2026-06-16 | Intraday baseline contract | `04_parallel_1h/intraday_baseline_contract_2026_06_16.md` defines the separate intraday baseline stack before new mechanism design: mechanism labels, cost layers C0-C3, delay layers D0-D4, control groups, universe tiers, proof gates, and required artifacts. It explicitly treats BTCUSDT/ETHUSDT as Tier 0 anchor-only evidence, not a generalized intraday baseline; generalized proof requires a frozen PIT liquid-perp core with at least `12` symbols, at least `8` non-BTC/ETH symbols, at least `3` liquidity buckets, BTC/ETH-excluded holdout, symbol holdout, and liquidity-bucket holdout. This contract authorizes no Stage B, strategy PnL, trading action, h10d bridge, manifest mutation, live, timer, scheduler, or remote-runner path |
| 2026-06-16 | Intraday PIT liquid-perp core universe freeze | `scripts/quant_research/parallel_1h/build_tardis_intraday_liquid_perp_core_universe.py` freezes the Tier 1 scope required by the intraday baseline contract without running Stage A, downloading Tardis data, scanning raw files, computing strategy PnL, or creating trading actions. It uses retained PIT input `pit-liquidity-top100-2026-05-31.quant_universe.json` (`sha256=59853073aa5f3258fe57b9e3387956615d8aeda4f0542d1b640cc3a5d59502a9`) and writes local artifact summary `sha256=5e45f375524460fd7ef9823de94ed9279f4b2fd6d36383868a4eded3c33f5d37` with `status=frozen_scope_passed_historical_stage_a_blocked`. The selected core is `20` symbols and `18` non-BTC/ETH names across `3` liquidity buckets (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `ZECUSDT`, `XRPUSDT`, `DOGEUSDT`, `BNBUSDT`, `SUIUSDT`, `LTCUSDT`, `AAVEUSDT`, `DASHUSDT`, `UNIUSDT`, `ENAUSDT`, `ASTERUSDT`, `WLDUSDT`, `FETUSDT`, `ALGOUSDT`, `POLUSDT`, `ETCUSDT`, `OPUSDT`). The universe scope gate is green, but generalized historical Stage A scope remains blocked because the PIT-valid forward window currently has `1` planned distinct month versus the required `18`; that forward-only core has since been staged and rerun as core20 columnar Stage A evidence, and longer historical expansion must use rolling monthly PIT freezes rather than backfilling this fixed core |
| 2026-06-16 | Rolling PIT intraday core universe contract | `04_parallel_1h/rolling_pit_core_universe_contract_2026_06_16.md` defines the valid way to use longer Tardis history for generalized intraday proof without hiding PIT leakage: each evaluation month gets its own pre-month freeze date, 90-day selection lookback, PIT candidate pool, selected symbols, liquidity buckets, raw partition hashes, normalized partition hashes, and monthly freeze manifest before Stage A is interpreted. It explicitly rejects backfilling the `2026-05-31` core into older months. The next allowed code step is a proof-only monthly freeze/dry-run staging-plan runner; the next data step, if separately requested, is owner-approved external raw staging for the selection lookback and evaluation windows. This contract authorizes no Tardis download execution by itself, Stage B, strategy PnL, trading action, h10d bridge, manifest mutation, live, timer, scheduler, or remote-runner path |
| 2026-06-16 | Rolling PIT monthly freeze dry-run plan runner | `scripts/quant_research/parallel_1h/build_tardis_intraday_rolling_pit_core_universe_plan.py` implements only the rolling monthly freeze and dry-run staging-plan artifact layer. The retained local dry-run under `artifacts/quant_research/factor_reports/2026-06-16-rolling-pit-core-v1-dry-run/rolling_pit_core_universe/` writes 18 monthly freeze artifact sets, a candidate-pool audit, monthly selection audits, raw/normalized staging plans, coverage/input-audit placeholders, summary, and profile. Summary `sha256=f460bcc23014134c8d949e00b5324f1e00b835025655c172740e497bfe0467b5` has `status=dry_run_plan_written_waiting_for_monthly_raw_selection_metrics`, `candidate_seed_symbol_count=90`, `dry_run_proxy_selected_symbol_count=20`, `evaluation_month_count=18`, `first_selection_lookback_start=2024-10-03`, `last_evaluation_end=2026-06-13`, and `planned_unique_raw_partition_count=270450`; monthly freeze plan `sha256=a17d47300edd450a5b7216ab332adcf4ae647f29f11a8d8fe05e4bf31448995e`, raw staging manifest `sha256=e89a0314bdfeb9b7518c431d4377f9c87b70a5a0e174681de5529027a9e2dff8`. It intentionally remains blocked on `candidate_seed_pit_valid_for_historical_selection`, `monthly_raw_selection_metrics_present`, and `stage_a_monthly_universe_masks_ready`; dry-run proxy selections are not Stage A eligible monthly universe masks. It executed no downloads, no raw scan, no normalization, no Stage A, no Stage B, no strategy PnL, no trading action, no h10d bridge, no manifest mutation, and no live/timer/scheduler/remote-runner activation |

This is why the folder feels messy: several branches were real research
frontiers when opened, but later became evidence, diagnostics, or closed
comparators.

---

## Current Active Candidate

Latest report:

```text
docs/quant_research/02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12.md
```

Latest strategy:

```text
v5_binance_pit_top_mid_h10d_pruned3_hv_tail_only_soft_budget
```

Parent:

```text
v5_binance_pit_top_mid_h10d_pruned3_high_vol_rebound_short_brake
```

Validation status:

| item | value |
| --- | ---: |
| status | passed |
| base net return | 3.400482 |
| base Sharpe | 1.285 |
| base max DD | 0.283569 |
| stress net return | 3.360634 |
| stress Sharpe | 1.278 |
| stress max DD | 0.283870 |
| max trade participation | 0.000015 base / 0.000030 stress |
| stratified repeated holdout | 13 / 16 positive folds |
| paper shadow ledger rows | 1453 |
| paper shadow order rows | 822 |
| residual execution gap blockers | 0 |

Risk overlay:

```text
pruned3_hv_tail_only_soft_portfolio_budget
```

Core five-feature set inherited from pruned3:

- `intraday_realized_vol_4h_to_1d_smooth_60`
- `realized_volatility_5`
- `distance_to_high_60`
- `distance_to_high_5`
- `downside_upside_vol_ratio_30`

Current caution:

- `distance_to_high_5` is a negative leave-one-out contributor in the latest
  run.
- The result is Binance-only and explicitly excludes CoinGlass/sidecar columns
  from core alpha.
- The paper-shadow section proves simulated execution accounting, not live
  readiness.

---

## Branch Ledger

| branch | representative docs | current status | next allowed action |
| --- | --- | --- | --- |
| strategic spine | `00_roadmap_state/strategy_upgrade_roadmap.md`, `00_roadmap_state/alpha_ontology_and_factor_library.md`, `00_roadmap_state/data_utilization_roadmap.md`, `00_roadmap_state/next_stage_alpha_map.md` | advisory spine; partly stale | use as context, but let newer validation reports control current status |
| pre-Binance h10d canonical parent | `00_roadmap_state/h10d_strategy_model_factor_contributions_2026_05_09.md` | benchmark/shadow-only research parent | compare against it when relevant; do not infer live readiness |
| CoinGlass full stack / R lanes | `01_data_foundation/coinglass_full_stack_data_research_roadmap.md`, `01_data_foundation/coinglass_full_stack_foundation_sync.md`, `03_alpha_branches/research_priority_update_full_stack.md` | foundation ready; reopening cycle frozen; no strict survivor | use as sidecar catalog only unless a new pre-registered mechanism needs it |
| provider-sidecar h10d | `03_alpha_branches/provider_sidecar_h10d_preregistration_2026_05_17.md`, `01_data_foundation/coinglass_full_stack_foundation_sync.md`, `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12_hv_balanced_soft_budget.md` | pre-registered; `hv_balanced` remains frozen control; no live config change | run Phase 0 provider smoke and PIT coverage audit only |
| M3.2 boundary / ETF-onchain | `03_alpha_branches/m3_2_boundary_activation_stage0.md`, `03_alpha_branches/m3_2_full_stack_boundary_falsification.md`, `03_alpha_branches/m3_2_etf_onchain_sidecar_falsification.md` | current forms closed as alpha candidates | reopen only with materially new activation definition |
| M3.3 event tape | `m3_3_*`, `03_alpha_branches/event_tape_narrative_research_plan.md` | current event-state representation exhausted | needs new event source or persistence definition |
| SP-K and post-pump routes | `03_alpha_branches/spk_non_kline_confirmation_stage0.md`, `03_alpha_branches/small_cap_post_pump_short_proposal.md`, `03_alpha_branches/crime_pump_playbook_alpha_research_note.md` | useful mechanism evidence; current confirmations closed | keep as mechanism inspiration, not current promotion evidence |
| MF-01 orderbook/inventory | `mf01_*`, `03_alpha_branches/orderbook_inventory_risk_transfer_proposal.md` | mechanism evidence only | revisit only with breadth, cost, and holdout pre-registration |
| MF-05 cross-venue | `mf05_*`, `03_alpha_branches/mf05_venue_local_data_gate.md` | blocked by native venue trust | run native venue concordance before alpha claims |
| MF-07 participant disagreement | `mf07_*` | current daily/sub-day/ETF-onchain forms closed | do not rerun same participant-stack variants |
| M3.1 options | `03_alpha_branches/m3_1_options_regime_r8_stage0.md`, `03_alpha_branches/m3_1_options_volume_shock_veto_falsification.md` | quarantined mechanism evidence | wait for richer PIT options surface or new design |
| M3.1 options surface v0 overlay | `03_alpha_branches/m3_1_options_surface_overlay_preregistration_2026_06_13.md`, `01_data_foundation/tardis_remote_research_platform_plan_2026_06_15.md` | report-only ablation complete; failed research-watch gate | treat `context_allowed` / `overlay_context_research_allowed` as report-only ablation permission only; no overlay, manifest, v1 policy, live, or timer use |
| M3.1 options surface v1 overlay | `03_alpha_branches/m3_1_options_surface_overlay_v1_preregistration_2026_06_15.md` | report-only ablation complete; failed research-watch gate | failed on sparse trigger gate plus worse full-OOS return and max drawdown; keep as quarantined comparator evidence, no score-layer, manifest, v1 policy, live, timer, or scheduler use; do not continue by quantile-threshold micro-tuning, next design needs baseline-loss trigger proof or an explicit loss-state confirmation gate |
| M3.1 options surface v2 loss-state design | `03_alpha_branches/m3_1_options_surface_overlay_v2_loss_state_preregistration_2026_06_15.md` | closed pattern; Stage A diagnostic failed loss-state proof | current `options stress -> portfolio throttle` shape is closed after v1 precursor failed on count (`8 < 16`) and loss alignment (`2/8` baseline-loss, `6/8` baseline-positive, loss-fraction lift `-0.065625`, triggered baseline net-return sum `+0.373271`); only a new non-threshold-microtuned precursor with retained Stage A proof may reopen this lane |
| M3.1 options precursor mechanism reset | `03_alpha_branches/m3_1_options_surface_precursor_mechanism_reset_2026_06_15.md` | mechanism-hypothesis reset; no candidate admitted | future M3.1 work must start with a new precursor mechanism hypothesis and retained loss-state proof; no portfolio-throttle multiplier, v0/v1 trigger repair, score-layer admission, manifest mutation, live, timer, or scheduler use |
| M3.1 dealer hedge-pressure transition precursor | `03_alpha_branches/m3_1_options_surface_new_precursor_dealer_hedge_pressure_transition_preregistration_2026_06_15.md` | closed failed mechanism evidence | retained proof summary `sha256=561951f4e2ad011fc8f3f1093fb3c0f368fceeb9733c3a4501c93a7e1f845dc7`; trigger count reached `16`, but loss-state alignment failed (`5/16` baseline-loss, `11/16` baseline-positive, loss-fraction lift `-0.003125`, triggered baseline net return `+0.472731`); do not continue by tuning `return_1`, `momentum_5`, `basis_velocity_3d`, taker pressure, perp-volume expansion, prior-observation count, or same-family AND/OR wiring; no trading action, multiplier, Stage B ablation, score-layer, manifest, live, timer, or scheduler use |
| parallel 1h lane | `04_parallel_1h/parallel_1h_alpha_mining_roadmap.md`, `04_parallel_1h/parallel_1h_fake_liquidity_age_sidecar_preregistration.md`, `04_parallel_1h/tardis_intraday_liquidity_shock_impulse_preregistration_2026_06_15.md`, `04_parallel_1h/intraday_baseline_contract_2026_06_16.md`, `04_parallel_1h/rolling_pit_core_universe_contract_2026_06_16.md` | separate lane; Tardis intraday liquidity-shock Stage A coverage passed, mechanism proof failed; columnar-only profiling pipeline implemented and profiled; intraday baseline contract opened; PIT liquid-perp core scope frozen; rolling PIT core contract and dry-run planning runner opened; no admitted 1h alpha | 18-month external raw staging cleared raw-missing, event-count, and distinct-month coverage blockers (`event_count_total=57672`, `distinct_months_with_min_events=18`, missing fraction `0.0`) for BTC/ETH anchor evidence, but the retained Stage A still fails on effect size, bootstrap CI, shuffle robustness, monthly holdout consistency, and BTC/ETH holdout. The follow-on columnar-only rerun kept BTC/ETH coverage green (`event_count_total=57637`, `distinct_months_with_min_events=18`, missing fraction `0.0`) and proved the measured engineering bottleneck is raw gzip/CSV normalization and aggregation, not Stage A proof evaluation. The first `2026-05-31` PIT core selected `20` symbols, `18` non-BTC/ETH names, and `3` liquidity buckets, then a forward-only core20 columnar Stage A rerun moved past raw-missing with `event_count_total=12388` but failed because only one PIT-valid forward month was available and mechanism/robustness gates did not pass. Longer history must now use the rolling PIT contract and dry-run plan runner: one pre-month freeze, selection lookback, candidate pool, hash lineage, and monthly universe mask per evaluation month. The current dry-run plan writes 18 monthly freeze artifact sets and 270,450 planned unique raw partitions, but it deliberately remains Stage A-blocked until monthly raw selection metrics exist and Stage A-eligible monthly universe masks are materialized. No h10d bridge, strategy PnL, trading action, Stage B return ablation, manifest mutation, live, timer, scheduler, remote-runner use, or downloader behavior is authorized by the proof runner, baseline contract, universe freeze, rolling PIT contract, or dry-run plan runner |
| Binance PIT h10d | `binance_*_2026_05_10.md` through `binance_*_2026_05_12.md` | active validation frontier; latest candidate passed current gates | harden promotion-readiness, audit residual factor/risk issues, then decide paper/live gate explicitly |
| mechanism library | `mechanism_notes/MF_*.md` | idea library and ontology | use for pre-registration, not as evidence by itself |

---

## Why The R-Side Search Did Not Promote Alpha

The R-side and CoinGlass-side failures should be read as incremental-alpha
failures, not necessarily as "the economics are fake."

Several mechanisms can be economically plausible while still failing promotion:

- The canonical h10d parent or later Binance-only OHLCV features may already
  absorb part of the same behavior through volatility, proximity-to-high,
  drawdown, and selection effects.
- A sidecar may describe the market state correctly but arrive too late,
  sparsely, or noisily to improve the portfolio after costs, holdouts, and
  bucket tests.
- A signal can improve one liquidity bucket or one symbol family while failing
  the cross-sectional execution requirement.
- A mechanism can be useful for diagnosis or risk controls without being an
  additive alpha feature.

So the right conclusion is not "CoinGlass data is useless." The right conclusion
is:

```text
CoinGlass is now a reusable catalog and sidecar source.
It is not the current active alpha-search frontier.
```

---

## Next Clean Step

The most coherent next roadmap step is not another broad data-fill pass.

Recommended next step:

```text
Run the next h10d factor/admission packet from the
v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve research baseline, while
keeping the remote hv_balanced multiphase live line as a separate
live-operations control.
```

Minimum contents:

- declare whether the candidate is a `v5_rw_bridge_no_overlay_h10d` score-parent
  extension using the 10-phase construction baseline, a live-control diagnostic
  against `hv_balanced:multiphase_10_sleeve`, or a Binance-only PIT challenger
  follow-up;
- keep live operations and research admission evidence in separate sections;
- for any `hv_tail_only` follow-up, reconcile the negative LOO on
  `distance_to_high_5`;
- preserve the stratified holdout, liquidity bucket, cost, funding, and
  execution-gap gates;
- explicitly decide whether the result is only research evidence, a paper-shadow
  candidate, or a live-control comparison. Do not imply a live config switch
  without a fresh remote config readback.

Only after that packet is closed should the roadmap choose between:

1. Binance PIT risk/portfolio hardening;
2. native venue concordance for MF-05-style work;
3. a fresh pre-registered 1h mechanism.

2026-05-17 update:

```text
provider_sidecar_h10d is now open as a pre-registered research branch.
```

This does not change the current live-pipeline candidate. It creates a narrow
path to test whether CoinGlass/provider sidecars can first improve risk-overlay
behavior against frozen `hv_balanced`, and only later support a 12-factor
rescore if Phase 0 coverage and PIT gates are clean.

---

## Full Coverage Index

This index originally listed the 81 source documents read for this
consolidation. The 2026-05-13 governance pass keeps that original state intact
and adds post-consolidation index hooks below so newer documents are not
orphaned. It does not include this file itself.

Strategic spine and governance:

- `00_roadmap_state/algorithm_choices.md`
- `00_roadmap_state/alpha_ontology_and_factor_library.md`
- `00_roadmap_state/baseline_alpha_confidence_validation.md`
- `00_roadmap_state/data_utilization_roadmap.md`
- `00_roadmap_state/experiment_catalog.md`
- `00_roadmap_state/factor_audit_trail.md`
- `00_roadmap_state/h10d_strategy_model_factor_contributions_2026_05_09.md`
- `00_roadmap_state/newer_alpha_search_validation_2026_05_03.md`
- `00_roadmap_state/next_stage_alpha_map.md`
- `00_roadmap_state/parallel_1h_import_rewrite_strategy_2026_05_13.md`
- `00_roadmap_state/script_path_refactor_phase5_parallel_1h_dry_run_review_2026_05_13.md`
- `00_roadmap_state/strategy_upgrade_roadmap.md`
- `00_roadmap_state/script_path_refactor_dry_run_phase2a_2026_05_12.md`
- `00_roadmap_state/research_doc_governance_audit_2026_05_13.md`
- `00_roadmap_state/research_doc_governance_index.md`
- `00_roadmap_state/research_doc_governance_roadmap_2026_05_13.md`
- `00_roadmap_state/worktree_staging_plan_2026-05-07.md`

Data and provider foundation:

- `01_data_foundation/binance_1m_five_year_store.md`
- `01_data_foundation/coinglass_etf_onchain_participant_sidecars.md`
- `01_data_foundation/coinglass_full_stack_data_research_roadmap.md`
- `01_data_foundation/coinglass_full_stack_foundation_sync.md`
- `01_data_foundation/cryptoquant_alchemy_m3_2_plan.md`
- `01_data_foundation/data_sponsorship_investment_plan_2026_05.md`
- `01_data_foundation/market_data_inventory.md`
- `01_data_foundation/provider_api_registry.md`
- `01_data_foundation/quant_next_data_specs.md`

M3, MF, SP-K, and R-lane branch reports:

- `03_alpha_branches/crime_pump_playbook_alpha_research_note.md`
- `03_alpha_branches/event_tape_narrative_research_plan.md`
- `03_alpha_branches/funding_oi_crowded_squeeze_failure_experiment_4.md`
- `03_alpha_branches/m3_1_options_regime_r8_stage0.md`
- `03_alpha_branches/m3_1_options_volume_shock_veto_falsification.md`
- `03_alpha_branches/m3_2_boundary_activation_stage0.md`
- `03_alpha_branches/m3_2_canonical_parent_stage0.md`
- `03_alpha_branches/m3_2_etf_onchain_sidecar_falsification.md`
- `03_alpha_branches/m3_2_full_stack_boundary_falsification.md`
- `03_alpha_branches/m3_3_event_state_feature_stage0.md`
- `03_alpha_branches/m3_3_event_tape_spk_stage0.md`
- `03_alpha_branches/m3_3_hype_chatter_gate_stage0.md`
- `03_alpha_branches/m3_3_mf01_confirmation_stage0.md`
- `03_alpha_branches/m3_3_robustness_v2_stage0.md`
- `03_alpha_branches/m3_3_strict_event_state_stage0.md`
- `03_alpha_branches/mf01_canonical_parent_alpha_validation.md`
- `03_alpha_branches/mf01_orderbook_inventory_r6_retest.md`
- `03_alpha_branches/mf05_cross_venue_boundary_stage0.md`
- `03_alpha_branches/mf05_cross_venue_spk_stage0.md`
- `03_alpha_branches/mf05_venue_local_data_gate.md`
- `03_alpha_branches/mf07_etf_onchain_transition_falsification.md`
- `03_alpha_branches/mf07_participant_disagreement_spk_stage0.md`
- `03_alpha_branches/mf07_participant_stack_r7_gate.md`
- `03_alpha_branches/mf07_subday_participant_pivot_stage0.md`
- `03_alpha_branches/orderbook_inventory_risk_transfer_proposal.md`
- `03_alpha_branches/post_capitulation_long_replacement_experiment_5.md`
- `03_alpha_branches/provider_sidecar_h10d_preregistration_2026_05_17.md`
- `03_alpha_branches/research_priority_update_full_stack.md`
- `03_alpha_branches/small_cap_post_pump_short_proposal.md`
- `03_alpha_branches/spk_non_kline_confirmation_stage0.md`

Parallel 1h lane:

- `04_parallel_1h/parallel_1h_alpha_mining_roadmap.md`
- `04_parallel_1h/parallel_1h_fake_liquidity_age_sidecar_preregistration.md`
- `04_parallel_1h/tardis_intraday_liquidity_shock_impulse_preregistration_2026_06_15.md`
- `04_parallel_1h/intraday_baseline_contract_2026_06_16.md`
- `04_parallel_1h/rolling_pit_core_universe_contract_2026_06_16.md`

Binance-only PIT h10d line:

- `02_binance_pit_h10d/binance_canonical_h10d_core20_short_filter_ablation_2026_05_11.md`
- `02_binance_pit_h10d/binance_canonical_h10d_liquidity_bucket_attribution_2026_05_10.md`
- `02_binance_pit_h10d/binance_canonical_h10d_lookahead_risk_check_2026_05_11.md`
- `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_10.md`
- `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_11.md`
- `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12.md`
- `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12_hv_balanced_soft_budget.md`
- `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12_hv_mild_soft_budget.md`
- `02_binance_pit_h10d/binance_pit_factor_attribution_shadow_ledger_2026_05_11.md`
- `02_binance_pit_h10d/binance_pit_hv_balanced_anti_overfit_validation_2026_05_12.md`
- `02_binance_pit_h10d/binance_pit_hv_soft_portfolio_budget_2026_05_12.md`
- `02_binance_pit_h10d/binance_pit_lifetime_maturity_sensitivity_2026_05_11.md`
- `02_binance_pit_h10d/binance_pit_pruned3_drawdown_attribution_2026_05_11.md`
- `02_binance_pit_h10d/binance_pit_pruned3_factor_ablation_2026_05_11.md`
- `02_binance_pit_h10d/binance_pit_pruned3_risk_brake_component_ablation_2026_05_12.md`
- `02_binance_pit_h10d/binance_pit_pruned3_risk_brake_v1_2026_05_11.md`
- `02_binance_pit_h10d/binance_pit_stratified_holdout_gate_2026_05_11.md`
- `02_binance_pit_h10d/binance_pit_top_mid_liquidity_bucket_breakdown_2026_05_11.md`

Mechanism notes:

- `mechanism_notes/MF_01_inventory_risk_transfer.md`
- `mechanism_notes/MF_02_dealer_gamma.md`
- `mechanism_notes/MF_03_funding_microstructure.md`
- `mechanism_notes/MF_04_carry_residuals.md`
- `mechanism_notes/MF_05_cross_venue_inventory.md`
- `mechanism_notes/MF_06_reflexive_flow.md`
- `mechanism_notes/MF_07_participant_disagreement.md`
- `mechanism_notes/MF_08_event_impulse.md`
- `mechanism_notes/MF_09_cojump_contagion.md`
- `mechanism_notes/MF_10_higher_moment_fragility.md`
- `mechanism_notes/MF_11_liquidity_migration.md`
- `mechanism_notes/MF_12_state_space_regime.md`
- `mechanism_notes/MF_13_stablecoin_plumbing.md`
- `mechanism_notes/MF_14_onchain_reflexivity.md`
- `mechanism_notes/MF_15_settlement_friction.md`
- `mechanism_notes/MF_16_narrative_state.md`
- `mechanism_notes/TEMPLATE.md`

Historical archive:

- `05_historical_archive/research_track_position_2026-04-22.md`
