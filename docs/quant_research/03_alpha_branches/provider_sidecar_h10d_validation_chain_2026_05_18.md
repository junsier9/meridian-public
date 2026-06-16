# provider_sidecar_h10d Validation Chain

Generated local date: 2026-05-18

## Hard Status

- `provider_sidecar_h10d_phase0_ready`: **false**
- `live_shadow_available_at_bootstrap`: **true**
- `overlap_only_diagnostic_passed`: **false**
- `paper_shadow_paired_comparison_completed`: **true**
- `small_risk_overlay_shadow_allowed`: **false**
- `small_risk_overlay_live_allowed`: **false**
- `alpha_score_changed`: **false**
- `live_config_changed`: **false**

## Decision

The validation chain is complete as a bootstrap package, but the provider sidecar is **not approved for live order impact**. The small CoinGlass short-brake overlay remains a default-off blocked candidate until the overlap coverage gate and a forward no-manual-tuning shadow window both pass.

## Blockers

- Overlap diagnostic gates failed: {'coverage_ratio_min_95pct': False, 'max_drawdown_not_worse': False, 'net_return_drawdown_tradeoff_not_catastrophic': True, 'has_overlay_triggers': True}.
- Phase 0 remains not ready for full-window promotion; keep provider overlay shadow/paper-only.
- Forward paper/shadow evidence has only a bootstrap sample; live order impact requires a no-manual-tuning forward window.

## Live Shadow

- request count: `140`
- success count: `140`
- error count: `0`
- median latency ms: `125.856`
- p95 latency ms: `264.839499999999`
- available_at recorded: `True`

## Overlap Paired Comparison

| variant | net_return | sharpe | max_drawdown | period_count |
| --- | --- | --- | --- | --- |
| hv_balanced_overlap_base | 1.055458 | 1.709 | 0.155835 | 68 |
| coinglass_short_brake_small | 1.020993 | 1.738 | 0.157341 | 68 |

Paired delta:

- mean delta return: `-0.00032323`
- sum delta return: `-0.02197981`
- positive delta share: `0.1618`
- overlay triggers: `36`

## Artifacts

- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\validation_chain_20260518\live_shadow_available_at.jsonl`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\validation_chain_20260518\live_shadow_summary.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\validation_chain_20260518\overlap_only_mtm_curve.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\validation_chain_20260518\overlap_only_overlay_position_decisions.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\validation_chain_20260518\overlap_only_paired_comparison_summary.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\validation_chain_20260518\risk_overlay_shadow_candidate.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\validation_chain_20260518\validation_chain_summary.json`
