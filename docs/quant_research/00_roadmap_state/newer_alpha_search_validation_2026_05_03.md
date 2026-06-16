# Newer Alpha Search And Validation - 2026-05-03

## Verdict

No newer alpha candidate is promotable over the canonical parent
`v5_rw_bridge_no_overlay_h10d` as of the 2026-05-03 scan.

The strongest newer candidate is
`xs_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d`.
It is a valid research-keep candidate, but not a promotion candidate. The
standalone return stream is positive, yet the canonical-parent paired edge is
too thin and fails strict falsification.

## Search Scope

The scan prioritized candidates that were newer than the MF-01 validation pass
and that came from adjacent mechanisms rather than the same MF-01 combo logic:

- post-pump / SP-K short replacement on the canonical parent
- stablecoin issuance, exchange absorption, and whale-to-exchange overlays
- MF-13 TRON / stablecoin flow gates
- MF-14 exchange-flow sell pressure and rebound gates
- post-pump news-veto and selected-short veto variants
- orderbook inventory short-replacement diagnostics

## Best Newer Candidate: SP-K Short Replacement

Candidate:
`xs_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d`

Primary artifacts:

- `artifacts/quant_research/hypothesis_batches/2026-05-02/families/xs_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d/fast_reject_report.json`
- `artifacts/quant_research/hypothesis_batches/2026-05-02/families/xs_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d/strict_result.json`
- `artifacts/quant_research/experiments/2026-05-02-xs_alpha_ontology_v5_rw_bridg-588799ecdc8e/alpha_card.json`
- `artifacts/quant_research/experiments/2026-05-02-xs_alpha_ontology_v5_rw_bridg-588799ecdc8e/statistical_falsification_report.json`
- `artifacts/quant_research/factor_reports/2026-05-03-spk-newer-alpha-validation/baseline_alpha_confidence_validation.md`

Fast-reject result:

- `fast_reject_passed=true`
- rank IC mean: `0.1192226891`
- rank IC positive rate: `0.6047619048`
- top-minus-bottom return: `0.0169396772`
- walk-forward median OOS Sharpe: `2.4929970971`
- worst regime median OOS Sharpe: `-3.7269963580`

Black-box fixed-set validation:

- confidence label: `medium_high`
- checks passed: `4/6`
- standalone sum: `1.1218625055`
- standalone win fraction: `0.640625`
- paired sum versus canonical parent: `0.0261552383`
- paired win fraction versus canonical parent: `0.359375`
- second-half paired diff versus canonical parent: `-0.0255660940`
- paired diff after dropping best 3 periods versus canonical parent: `-0.0902789364`
- warning: edge versus canonical parent has non-positive 2025 paired contribution

Strict validation:

- `strict_validation_passed=false`
- `credible_research_evidence=false`
- experiment status: `quarantined`
- blockers: `time_shuffle_failed`, `label_shuffle_failed`,
  `delay_stress_failed`, `cost_stress_failed`, `symbol_holdout_failed`,
  `liquidity_bucket_consistency_failed`
- strict observed candidate-vs-parent cumulative diff: `-0.0714349174`
- strict observed candidate-vs-parent Sharpe diff: `-0.3352967399`
- strict probability candidate beats parent on cumulative return: `0.035`

Interpretation:

SP-K has a real standalone return stream and improves against legacy/static
references, but the edge is not reliable against the canonical parent. It should
remain a research-keep lane for short-side selection, not a deployable alpha.

## Stablecoin / On-Chain Overlay Candidates

Stablecoin data availability is healthy:

- stablecoin issuance velocity overlay has `125` ready signal days
- exchange absorption and whale stress overlays have `120` ready signal days
- latest stablecoin sync cycle status is `success`
- latest full day is `2026-05-01`, decision date `2026-05-02`

However, the strategy-level overlay diagnostics are not promotable:

- `stablecoin_overlay_cycle_increment_diagnostic.json`: `incremental_negative`
- `stablecoin_overlay_v1_cycle_increment_diagnostic.json`: `incremental_negative`
- `stablecoin_overlay_v2_cycle_increment_diagnostic.json`: `incremental_negative`
- `stablecoin_exchange_absorption_overlay_v1_cycle_increment_diagnostic.json`:
  `incremental_negative`
- `stablecoin_whale_to_exchange_stress_overlay_v1_cycle_increment_diagnostic.json`:
  `incremental_negative`
- `stablecoin_flow_interaction_cycle_diagnostic.json`: best walk-forward
  candidate `drain_relative_strength_v1`, verdict counts `2`
  incremental-negative and `1` no-material-change

Interpretation:

Stablecoin flow is ready as context/evidence, but current daily overlays are too
coarse as alpha. They are more suitable as veto/regime context than as direct
replacement signals.

## MF-13 / MF-14 On-Chain Gates

Admission diagnostics include several attractive local gate signals, but the
strategy-level increment does not hold:

- `MF13_tron_flow_impulse_defensive_beta_gate_v1`: h10d IC `0.0409255100`,
  residual IC `0.0498706994`, 11 active timestamps, strict-pass admission
- `MF13_tron_speculative_heat_defensive_beta_gate_v1`: h10d IC
  `0.2027768076`, residual IC `0.1077744981`, only 3 active timestamps
- `MF14_capitulation_rebound_idio_gate_v1`: h10d IC `0.0772426853`,
  residual IC `0.0869686344`, 12 active timestamps

But the increment diagnostics are not promotable:

- MF-13 TRON cross-sectional gate increment: `incremental_negative`
- MF-13 TRON regime gate AB: `no_material_change`
- MF-14 cross-sectional gate increment: `no_material_change`
- MF-14 regime gate AB: `no_material_change`

Interpretation:

The local gates are useful mechanism probes, especially for future narrow event
conditioning, but their active sample is too small or their strategy-level
transmission is too weak.

## Event / News / Short-Veto Candidates

The selected-short news-veto family improved some validation and walk-forward
fields relative to older `v6_h10d`, but not enough for the current canonical
parent question:

- selected-short no-news replacement improved validation Sharpe and
  walk-forward median versus the older v6 baseline, but it was not evaluated as
  a current-parent promotion candidate
- selected-short veto variants reduced test return versus that older baseline
- the current-parent SP-K rerun is the cleaner modern comparison, and it fails
  strict falsification against `v5_rw_bridge_no_overlay_h10d`

Interpretation:

Event/news logic remains a promising way to narrow short-side replacement, but
the next test should be a current-parent event-veto slice, not another legacy v6
overlay comparison.

## Decision

Do not promote any newer alpha from this scan.

Recommended ranking:

1. Continue SP-K as a research-keep short-side selection lane.
2. Build a narrower event-conditioned SP-K variant on the canonical parent.
3. Use stablecoin/on-chain overlays as veto/context filters, not direct score
   overlays.
4. Keep MF-13/MF-14 local gates as mechanism probes until they have stronger
   active-sample support and positive strategy-level transmission.

The next executable slice should not relax canonical-parent paired evidence.
Instead, it should reduce the candidate's active replacement scope so that the
strict aligned-period paired test turns positive against
`v5_rw_bridge_no_overlay_h10d`.
