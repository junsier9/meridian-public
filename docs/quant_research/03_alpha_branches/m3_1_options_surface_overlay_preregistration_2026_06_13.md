# M3.1 Options Surface Overlay Preregistration

`Status: preregistered research candidate`
`Date: 2026-06-13`
`Scope: v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve`
`Live impact: none`

## Decision

Freeze the following research-only overlay candidate:

```text
m3_1_options_surface_top2_context_throttle_v0
```

This candidate uses BTC/ETH Deribit options-surface context from the M3.1
Tardis builder as a portfolio-level exposure throttle. It is not a score-layer
factor set, does not change the active h10d manifest, does not change the v1
feature-admission allowlist, and does not authorize live or timer overlay use.

The 2026-06-13 preregistered report card allows only a research overlay-context
ablation:

```text
score_layer_admission_allowed = false
overlay_context_research_allowed = true
```

This flag is only permission to run the frozen report-only ablation. It must
not be read as overlay availability, research-watch approval, score-layer
admission, manifest admission, v1 admission-policy mutation, or live/timer
authorization.

## Frozen Inputs

Use only the following feature columns from the M3.1 options-surface panel:

- `iv_rv_spread` (F57): vol-risk-premium context.
- `iv_term_slope` (F58): short-dated term-structure stress context.
- `dealer_gamma_proxy` (F59): dealer-gamma regime context.
- `vanna_charm_window` (F60): expiry-window context.

`iv_25d_skew_residual` (F56) remains an observation-only diagnostic in this
v0 overlay. It must be reported, but it must not trigger or tune the v0 rule.

The source panel must be produced by:

```powershell
python .\scripts\quant_research\build_tardis_deribit_options_surface_features.py ...
```

and audited by:

```powershell
python .\scripts\quant_research\report_writers\compute_options_surface_overlay_context_report.py --as-of 2026-06-13
```

## Frozen Rule

For each h10d walk-forward train window, build daily BTC/ETH top-2 options
context at `decision_date_utc`:

```text
top2_iv_rv_spread_median = median(BTC, ETH iv_rv_spread)
top2_iv_term_slope_min = min(BTC, ETH iv_term_slope)
top2_abs_dealer_gamma_max = max(abs(BTC, ETH dealer_gamma_proxy))
top2_vanna_charm_max = max(BTC, ETH vanna_charm_window)
```

Estimate only train-window thresholds:

```text
iv_rv_spread_q90 = q90(top2_iv_rv_spread_median)
iv_term_slope_q10 = q10(top2_iv_term_slope_min)
abs_dealer_gamma_q90 = q90(top2_abs_dealer_gamma_max)
vanna_charm_q90 = q90(top2_vanna_charm_max)
```

In the future validation/test window, trigger the overlay when either frozen
condition fires:

```text
vol_stress_trigger =
  top2_iv_rv_spread_median >= train_iv_rv_spread_q90
  AND top2_iv_term_slope_min <= train_iv_term_slope_q10

gamma_expiry_trigger =
  top2_abs_dealer_gamma_max >= train_abs_dealer_gamma_q90
  AND top2_vanna_charm_max >= train_vanna_charm_q90
```

When either trigger fires:

```text
portfolio_target_multiplier = 0.75
```

Otherwise:

```text
portfolio_target_multiplier = 1.00
```

The multiplier applies after the existing h10d top/bottom selection and target
construction. It must not alter rankings, factor weights, long/short counts,
or any individual score contribution. Missing or non-ready options context is
fail-open for research ablation only:

```text
missing_context_multiplier = 1.00
```

## Evaluation Rules

The overlay ablation may compare only:

- `baseline_no_options_surface_overlay`
- `m3_1_options_surface_top2_context_throttle_v0`

No parameter grid is allowed. The quantiles (`q90`, `q10`) and multiplier
(`0.75`) are frozen before the ablation.

Minimum research pass conditions:

- full OOS cumulative return is not worse than baseline;
- full OOS h10d-overlap-adjusted Sharpe is not worse than baseline;
- full OOS max drawdown improves or is not worse than baseline;
- untouched holdout cumulative return is not worse than baseline;
- capacity breach count remains zero;
- trigger rate is non-zero and not pathologically frequent;
- result is robust to excluding the first 30 options-context decision dates.

Passing this packet is only evidence for a research overlay watch state. It is
not score-layer admission, not paper-shadow approval, and not live approval.

## Forbidden Actions

This preregistration does not permit:

- modifying `config/quant_research/active_h10d_registry.json`;
- modifying the active h10d manifest;
- adding `iv_`, `dealer_gamma_`, or `vanna_charm_` prefixes to v1 admission;
- using BTC/ETH-only diagnostics as top20 score-layer evidence;
- changing live, timer, or remote-runner configuration;
- tuning thresholds after seeing ablation results.

## Evidence Inputs

Current preregistration evidence:

- `artifacts/quant_research/factor_reports/2026-06-13/m3_1_tardis_deribit_options_surface_probe.json`
- `artifacts/quant_research/factor_reports/2026-06-13/m3_1_tardis_deribit_options_surface_builder.json`
- `artifacts/quant_research/factor_reports/2026-06-13/m3_1_tardis_deribit_options_surface_admission_manifest_audit.json`
- `artifacts/quant_research/factor_reports/2026-06-13/m3_1_options_surface_overlay_context_report_card.json`
- `artifacts/quant_research/options_surface/2026-06-13/tardis_deribit_options_surface_features.csv`

## Full Backfill Ablation Result (2026-06-15)

Status:

```text
M3.1 overlay v0 report-only failed research-watch gate
```

Remote raw history and the full feature panel were successfully built, but the
frozen v0 overlay did not pass the research-watch gate.

Evidence:

- raw backfill summary: `/tank/meridian/report_archive/factor_reports/20260615T035231Z_tardis_backfill_20230401_20260613/backfill_controller_summary.json`
- final storage panel: `/tank/meridian/options_surface_feature_panels/2026-06-15-full-backfill-20230401-20260613/tardis_deribit_options_surface_features.csv`
- compute context report: `/data/meridian/artifacts/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_context_report_card.json`
- compute ablation summary: `/data/meridian/artifacts/factor_reports/2026-06-15-full-backfill-20230401-20260613/m3_1_options_surface_overlay_ablation/summary.json`
- storage ablation summary: `/tank/meridian/report_archive/factor_reports/2026-06-15-full-backfill-20230401-20260613/compute_outputs/m3_1_options_surface_overlay_ablation/summary.json`

Raw and panel coverage:

- backfill range: `2023-04-01` through `2026-06-13`;
- monthly shards: `39/39` succeeded;
- raw daily partitions: `1170`, failed partitions `0`, missing partitions `0`;
- final panel rows: `2340` (`1170` days x BTC/ETH);
- h10d overlap rows: `2226` feature rows, `2206` target rows.

Context report interpretation:

```text
overlay_context_research_allowed = true
score_layer_admission_allowed = false
```

`overlay_context_research_allowed = true` means only that the frozen v0
report-only ablation was allowed to run. It is not evidence that the overlay is
usable.

Ablation verdict:

```text
research_watch_state_allowed = false
score_layer_admission_allowed = false
active_manifest_mutation_authorized = false
v1_admission_policy_mutation_authorized = false
live_or_timer_overlay_activation_authorized = false
```

Blockers:

- `full_oos_cumulative_return_worse_than_baseline`;
- `full_oos_h10d_equivalent_sharpe_worse_than_baseline`;
- `exclude_first_30_context_dates_cumulative_return_worse_than_baseline`;
- `exclude_first_30_context_dates_h10d_sharpe_worse_than_baseline`.

Key comparison:

- baseline full OOS cumulative return: `2.124384806883999`;
- candidate full OOS cumulative return: `2.106043196354828`;
- candidate delta full OOS cumulative return: `-0.01834161052917116`;
- baseline full OOS h10d-equivalent Sharpe: `1.9572510925856097`;
- candidate full OOS h10d-equivalent Sharpe: `1.9512974578311548`;
- candidate delta full OOS h10d-equivalent Sharpe: `-0.005953634754454873`;
- candidate triggered decision count: `8` of `640` threshold windows;
- full OOS capacity breach count: `0`.

Conclusion: `m3_1_options_surface_top2_context_throttle_v0` is failed and
quarantined as comparator evidence. Any future M3.1 overlay work needs a new
pre-registered candidate or rule. Do not reinterpret `context_allowed` or
`overlay_context_research_allowed` as overlay availability.

## Next Step

Do not promote this v0 overlay to research-watch, score-layer admission,
manifest admission, v1 admission policy, paper-shadow, live, or timer use. The
only valid continuation is a new pre-registered options-surface candidate or
rule that explicitly treats this v0 result as failed comparator evidence.
