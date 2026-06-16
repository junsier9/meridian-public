# provider_sidecar_h10d Phase 0 CoinGlass Coverage Audit

Generated local date: 2026-05-18

## Hard Status

- `provider_sidecar_h10d_phase0_ready`: **false**
- `overlap_only_diagnostic_ready`: **true**
- Frozen control: `hv_balanced`
- Live config changed: **false**

## Decision

Phase 0 is **not promotion-ready** for a full `hv_balanced` paired h10d rerun. CoinGlass endpoint access is live and the required futures sidecar endpoint smoke passed, but the local sidecar history does not cover the full frozen-control window and the current sidecar panels do not carry an explicit provider `available_at` timestamp.

## Blockers

- Current endpoint smoke does not verify the full 1820-day frozen-control history window; observed required endpoint history days: {'futures_open_interest_history_usd': 365, 'futures_funding_rate_history': 365, 'futures_taker_buy_sell_volume': 365, 'futures_liquidation_history': 180, 'futures_orderbook_ask_bids_history': 30, 'futures_global_long_short_account_ratio': 180, 'futures_top_long_short_position_ratio': 180}.
- Local sidecar history does not cover the full frozen-control window 2021-05-02 to 2026-04-26; family full-window flags: {'liquidation': False, 'orderbook': False, 'taker_flow': False, 'global_long_short': False, 'top_trader': False, 'funding_oi': False}.
- Local sidecar panels have no explicit provider available_at timestamp; Phase 1 must encode a conservative lag before any PIT-safe paired comparison.

## Key / Endpoint Audit

| scope | name | present | length |
| --- | --- | --- | --- |
| Process | CoinglassAPI | True | 32 |
| Process | COINGLASSAPI | True | 32 |
| Process | COINGLASS_API_KEY | False | 0 |
| User | CoinglassAPI | True | 32 |
| User | COINGLASSAPI | True | 32 |
| User | COINGLASS_API_KEY | False | 0 |
| Machine | CoinglassAPI | False | 0 |
| Machine | COINGLASSAPI | False | 0 |
| Machine | COINGLASS_API_KEY | False | 0 |

Required futures endpoints:

| endpoint_id | status | classification | history_days | history_row_count | history_first_utc | history_last_utc |
| --- | --- | --- | --- | --- | --- | --- |
| futures_open_interest_history_usd | success | core_research_input | 365.0 | 168.0 | 2025-05-10T17:00:00Z | 2025-05-17T16:00:00Z |
| futures_funding_rate_history | success | core_research_input | 365.0 | 168.0 | 2025-05-10T17:00:00Z | 2025-05-17T16:00:00Z |
| futures_taker_buy_sell_volume | success | core_research_input | 365.0 | 168.0 | 2025-05-10T17:00:00Z | 2025-05-17T16:00:00Z |
| futures_liquidation_history | success | core_research_input | 180.0 | 168.0 | 2025-11-11T17:00:00Z | 2025-11-18T16:00:00Z |
| futures_orderbook_ask_bids_history | success | core_research_input | 30.0 | 168.0 | 2026-04-10T17:00:00Z | 2026-04-17T16:00:00Z |
| futures_global_long_short_account_ratio | success | sidecar_context | 180.0 | 168.0 | 2025-11-11T17:00:00Z | 2025-11-18T16:00:00Z |
| futures_top_long_short_position_ratio | success | sidecar_context | 180.0 | 168.0 | 2025-11-11T17:00:00Z | 2025-11-18T16:00:00Z |

## Local Sidecar Windows

| family | row_count | symbol_count | first_date_utc | last_date_utc |
| --- | --- | --- | --- | --- |
| liquidation | 56726 | 90 | 2024-05-07 | 2026-04-27 |
| orderbook | 56699 | 90 | 2024-05-07 | 2026-04-27 |
| taker_flow | 56726 | 90 | 2024-05-07 | 2026-04-27 |
| global_long_short | 56613 | 90 | 2024-05-07 | 2026-04-27 |
| top_trader | 56613 | 90 | 2024-05-07 | 2026-04-27 |
| funding_oi | 36017 | 39 | 2023-04-24 | 2026-05-16 |

Control overlap:

| family | control_rebalance_overlap_count | position_decision_overlap_count |
| --- | --- | --- |
| liquidation | 72 | 71 |
| orderbook | 72 | 71 |
| taker_flow | 72 | 71 |
| global_long_short | 72 | 71 |
| top_trader | 72 | 71 |
| funding_oi | 110 | 109 |

## Liquidity Bucket Coverage

Top bucket only:

| family | active_rows | covered_rows | coverage_ratio | overlap_active_rows | overlap_covered_rows | overlap_coverage_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| liquidation | 18010 | 7015 | 0.389505830094392 | 7210 | 7015 | 0.9729542302357836 |
| orderbook | 18010 | 7015 | 0.389505830094392 | 7210 | 7015 | 0.9729542302357836 |
| taker_flow | 18010 | 7015 | 0.389505830094392 | 7210 | 7015 | 0.9729542302357836 |
| global_long_short | 18010 | 7015 | 0.389505830094392 | 7210 | 7015 | 0.9729542302357836 |
| top_trader | 18010 | 7015 | 0.389505830094392 | 7210 | 7015 | 0.9729542302357836 |
| funding_oi | 18010 | 10389 | 0.576846196557468 | 11030 | 10389 | 0.9418857660924751 |

## Output Artifacts

- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\phase0_summary.json`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\endpoint_status.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\key_scope_status.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\sidecar_history_windows.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\sidecar_coverage_by_symbol.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\sidecar_coverage_by_liquidity_bucket.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\family_rebalance_overlap.csv`
- `C:\Users\user\Documents\Claude\Projects\EnhengClaw\artifacts\quant_research\provider_sidecar_h10d\phase0_coverage_20260518\pit_lag_policy.csv`
