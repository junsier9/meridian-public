# CoinGlass Full-Stack Foundation Sync

`Run date: 2026-05-07`
`Contract: coinglass_full_stack_foundation_sync.v1`
`Status: foundation catalog ready; alpha still fail-closed`

---

## Purpose

This is the default CoinGlass data catalog to check before opening a new
roadmap lane. It consolidates local raw caches, normalized sidecars,
coverage artifacts, and quarantine status so research does not rediscover
data gaps one lane at a time.

It is not alpha evidence and it does not modify the canonical parent.

---

## Execution Summary

- as_of: `2026-05-07`
- catalog_only: `False`
- symbol_count: `99`
- step_status_counts: `{'success': 4, 'skipped': 3}`
- foundation_catalog_ready: `True`
- alpha_rerun_allowed: `False`

| step | status | seconds | note |
| --- | --- | ---: | --- |
| `capability_matrix` | `success` | `6.943` |  |
| `spot_ohlcv` | `skipped` | `0.0` | explicit skip flag |
| `oi_provenance` | `skipped` | `0.0` | explicit skip flag |
| `extended_microstructure_refresh` | `skipped` | `0.0` | explicit skip flag |
| `microstructure_participant_panel_build` | `success` | `199.666` |  |
| `etf_onchain_participant_sidecars` | `success` | `103.808` |  |
| `options_regime_panel` | `success` | `1.504` |  |

---

## Catalog

| entry | family | research status | rows/files | date range | notes |
| --- | --- | --- | ---: | --- | --- |
| `capability_matrix` | `provider_capability` | `diagnostic_only` | `25` | n/a | Endpoint capability smoke only; not data readiness. |
| `spot_ohlcv` | `spot_ohlcv` | `quarantined_until_provider_concordance_passes` | `99` | n/a | Coverage and strict provider concordance remain separate gates. |
| `futures_oi_provenance` | `futures_core` | `sidecar_context_with_native_usd_preferred` | `90` | n/a | Native USD OI is preferred; derived OI requires provenance and formula audit. |
| `microstructure_panel_1h` | `microstructure` | `sidecar_context_only` | `1359148` | 2024-05-07 to 2026-04-27 | Contains liquidation, orderbook, taker flow, top/global participant state. |
| `microstructure_panel_1d` | `microstructure` | `sidecar_context_only` | `56726` | 2024-05-07 to 2026-04-27 | 1h extended rows aggregated to daily by fixed sum/last rules. |
| `participant_panel_1d` | `participant_state` | `sidecar_context_only` | `56726` | 2024-05-07 to 2026-04-27 | Top/global/taker participant panel; not an alpha by itself. |
| `participant_panel_1h` | `participant_state` | `sidecar_context_only` | `1359148` | 2024-05-07 to 2026-04-27 | Hourly top/global/taker participant panel; not an alpha by itself. |
| `etf_daily_state` | `etf` | `sidecar_context_only_pit_lagged` | `598` | 2024-01-12 to 2026-05-07 | Daily source date plus one-day PIT lag unless publication timestamp is proven. |
| `exchange_transfers` | `onchain_exchange_transfer` | `quarantined_latest_event_feed` | `31` | 2026-04-08 to 2026-05-08 | Page-based latest-event feed; raw transfer_type is not semantic inflow/outflow. |
| `whale_transfers` | `onchain_whale_transfer` | `sidecar_context_only_pit_lagged` | `181` | 2025-11-09 to 2026-05-08 | Event sidecar with exchange-entity direction heuristic. |
| `participant_context` | `combined_context` | `sidecar_context_only` | `657` | 2024-01-12 to 2026-05-08 | Combined ETF/on-chain daily context for narrow pre-registered transition tests. |
| `options_regime` | `options_aggregate` | `quarantined_market_gate_only` | `2142` | 2020-06-24 to 2026-05-07 | Market-level options aggregates; max-pain remains snapshot-only unless PIT history is proven. |
| `vendor_indicators` | `vendor_indicator` | `diagnostic_only_not_synced` | `n/a` | n/a | Opaque vendor indicators are not foundation alpha inputs. |

---

## Non-Negotiable Policy

- Coverage and concordance remain separate gates.
- Snapshot, latest-event, and opaque vendor-indicator data stay quarantined.
- ETF and on-chain rows require PIT lag before entering a decision frame.
- A sidecar can support Stage 0 design, but cannot open manifest A/B without strict falsification.

## Default Use

Before starting a new CoinGlass-backed research lane, inspect this catalog
and use the `research_status` field to decide whether the input is
`sidecar_context_only`, `quarantined`, or `diagnostic_only`. If a required
entry is missing, refresh this foundation script first rather than adding
one-off data pulls inside the research script.

## Downstream Consumers

| consumer | catalog entries used | result |
| --- | --- | --- |
| `docs/quant_research/03_alpha_branches/m3_2_etf_onchain_sidecar_falsification.md` | `participant_context`, `etf_daily_state`, `whale_transfers`, quarantined `exchange_transfers` context | R-3b fail-closed; no M3.2 sidecar A/B |
| `docs/quant_research/03_alpha_branches/m3_1_options_volume_shock_veto_falsification.md` | `options_regime` | R-8b fail-closed on liquidity-bucket consistency; no M3.1 options exposure gate |
| `docs/quant_research/03_alpha_branches/mf07_etf_onchain_transition_falsification.md` | `participant_context`, `etf_daily_state`, `whale_transfers`, quarantined `exchange_transfers` context | R-7b fail-closed at Stage 0; no MF-07 participant transition |
