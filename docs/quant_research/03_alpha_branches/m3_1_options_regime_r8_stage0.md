# M3.1 Options-Regime R-8 Stage0

`Run date: 2026-05-07`
`Parent boundary: v5_rw_bridge_no_overlay_h10d is not modified`
`Status: quarantined market-gate candidate; no h10d manifest A/B`

---

## Question

R-8 asks whether CoinGlass aggregate options data can reopen M3.1 as a narrow
market-level regime slice, without pretending that aggregate options endpoints
are a full dealer-gamma surface.

This run asks the first executable question:

> Can CoinGlass option volume, option/futures OI ratio, option OI, and max-pain
> support an immediate parent exposure gate?

The answer is **not yet**. One options-volume shock diagnostic is interesting
enough to keep in quarantine, but the data surface is not promotion-grade.

---

## Artifacts

- R-8 evaluator:
  `scripts/quant_research/alpha_stage0_quarantine/audit_m3_1_options_regime_stage0.py`
- unit tests:
  `tests/test_quant_m3_1_options_regime_stage0.py`
- primary report:
  `artifacts/quant_research/factor_reports/2026-05-07-m3-1-options-regime-stage0/m3_1_options_regime_stage0.json`
- generated sidecar:
  `artifacts/quant_research/coinglass/options_regime_panel_1d.csv.gz`

The generated sidecar is market-level, not symbol-level. It should be treated
as a candidate exposure-gate input, not as a cross-sectional rank factor.

---

## Data Surface

The CoinGlass options panel contains:

- rows: `2,142`
- date range: `2020-06-24` to `2026-05-07`
- BTC/ETH option volume coverage on parent dates: `98.90%`
- BTC/ETH option-vs-futures OI ratio coverage on parent dates: `100.00%`
- BTC/ETH option OI coverage on parent dates: `0.00%`

The hard data split is important:

- option volume and option/futures OI ratio have enough historical coverage to
  build a market-regime sidecar;
- option OI currently behaves like a short-window/recent endpoint for this
  use, not a historical backtest input;
- max-pain is a current Deribit snapshot list, not PIT history.

---

## Conditional Parent Diagnostic

The script aligned the options sidecar to the canonical parent short basket:

- parent features artifact:
  `artifacts/quant_research/features/2026-05-03-cross-sectional-daily-1d-features-v1/features.csv.gz`
- parent short rows: `3,279`
- parent short dates: `1,093`
- risk-frame subjects: `17`

Candidate market gates:

| gate | active dates | active fraction | active next h mean | inactive next h mean | edge active minus inactive | status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `r8_high_option_volume_shock_flag` | `153` | `14.13%` | `+0.0298` | `-0.0069` | `+0.0366` | keep quarantined |
| `r8_high_option_vs_futures_ratio_flag` | `283` | `26.13%` | `+0.0070` | `-0.0047` | `+0.0117` | fail split stability |
| `r8_any_options_stress_flag` | `385` | `35.55%` | `+0.0088` | `-0.0074` | `+0.0162` | fail split stability |

For `r8_high_option_volume_shock_flag`, the interpretation is:

> when aggregate BTC/ETH option volume shock is high, the parent short basket
> tends to rally more, so the only plausible landing shape is a short-exposure
> veto or throttle.

Train/test split check:

- train edge: `+0.0411`
- test edge: `+0.0289`

This is real enough to preserve as a quarantined market-gate candidate. It is
not enough to open a manifest A/B because the gate is market-level, the OI and
max-pain parts are not PIT-historical, and no strict randomized falsification
has run.

---

## Decision

`stage0_status = stage0_quarantined_market_gate_candidate_no_manifest`

`kept_variants = ["r8_high_option_volume_shock_flag"]`

`alpha_rerun_allowed = False`

`manifest_ab_allowed = False`

Blockers:

- `btc_option_oi_usd_total_history_not_backfilled`
- `eth_option_oi_usd_total_history_not_backfilled`
- `market_level_only_not_cross_sectional_rank_factor`
- `max_pain_current_snapshot_not_pit_history`

Do not promote R-8 into h10d manifest A/B yet. The next valid R-8 action is a
pre-registered short-exposure throttle/veto falsification using only PIT-safe
volume and ratio fields, while separately backfilling or quarantining option
OI and max-pain.

2026-05-09 follow-up:

- R-8b strict card:
  `docs/quant_research/03_alpha_branches/m3_1_options_volume_shock_veto_falsification.md`
- result: `r8_high_option_volume_shock_flag` passes delay, era split, symbol
  holdout, and random shuffle controls, but fails liquidity-bucket consistency
  because `tail_liquidity` has eligible sample and negative edge.
- decision: keep as quarantined mechanism evidence only; no parent overlay and
  no manifest A/B.
