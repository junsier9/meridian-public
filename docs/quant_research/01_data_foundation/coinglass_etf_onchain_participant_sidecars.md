# CoinGlass ETF / On-chain Participant Sidecars

`Run date: 2026-05-07`
`Contract: coinglass_etf_onchain_participant_sidecars.v1`
`Status: PIT sidecar data layer filled; alpha integration still blocked`

---

## Purpose

This slice fills the local PIT sidecars required before ETF and on-chain
participant context can be tested in MF-07 / M3.2 style transition rules.

It does not promote an alpha and it does not modify the canonical parent.
The output is a data-layer artifact set only.

---

## Artifacts

- sync script:
  `scripts/quant_research/sync_coinglass_etf_onchain_participant_sidecars.py`
- tests:
  `tests/test_quant_coinglass_etf_onchain_participant_sidecars.py`
- sync report:
  `artifacts/quant_research/factor_reports/2026-05-07-coinglass-etf-onchain-participant-sidecars/coinglass_etf_onchain_participant_sidecars.json`
- ETF daily sidecar:
  `artifacts/quant_research/coinglass/etf_daily_state_1d.csv.gz`
- exchange transfer sidecar:
  `artifacts/quant_research/coinglass/exchange_transfers_1d.csv.gz`
- whale transfer sidecar:
  `artifacts/quant_research/coinglass/whale_transfers_1d.csv.gz`
- combined participant context:
  `artifacts/quant_research/coinglass/participant_context_1d.csv.gz`

---

## Live API Result

| slice | input rows | input time range | output rows | output decision-date range |
| --- | ---: | --- | ---: | --- |
| BTC ETF flow | `598` | `2024-01-11` to `2026-05-06` | merged into ETF sidecar | `2024-01-12` to `2026-05-07` |
| ETH ETF flow | `460` | `2024-07-23` to `2026-05-06` | merged into ETF sidecar | `2024-01-12` to `2026-05-07` |
| IBIT ETF history | `565` | `2024-01-26` to `2026-05-05` | merged into ETF sidecar | `2024-01-12` to `2026-05-07` |
| Exchange transfers | `8,511` | `2026-04-07T06:43:11Z` to `2026-05-07T05:43:59Z` | `31` | `2026-04-08` to `2026-05-08` |
| Whale transfers | `61,703` | `2025-11-08T06:06:21Z` to `2026-05-07T05:37:32Z` | `181` | `2025-11-09` to `2026-05-08` |
| Combined participant context | n/a | n/a | `657` | `2024-01-12` to `2026-05-08` |

Final report warnings were empty after whale windows were changed to adaptive
splits when the vendor returned a 1000-row page cap.

The `2026-05-08` on-chain decision-date rows are expected: they come from
`2026-05-07` UTC events after applying the one-day PIT lag. They should not be
read as current-day tradable information.

---

## PIT Contract

ETF:

- endpoints: `/etf/bitcoin/flow-history`, `/etf/ethereum/flow-history`,
  `/etf/bitcoin/history?ticker=IBIT`
- native timestamps are daily UTC milliseconds
- decision date is `source_date + 1 day`
- no publication timestamp is assumed

Exchange transfers:

- endpoint: `/exchange/chain/tx/list`
- native timestamp is `transaction_time` in seconds
- output is event-day plus one-day lag
- local probes showed start/end filters are ignored, so this sidecar is a
  paginated latest-event feed, not arbitrary historical backfill
- `transfer_type` is retained as a raw vendor code; it is not promoted as a
  semantic inflow/outflow label

Whale transfers:

- endpoint: `/chain/v2/whale-transfer`
- native timestamp is `block_timestamp` in seconds
- start/end query parameters use milliseconds
- output is event-day plus one-day lag
- windows are split adaptively when the API returns a 1000-row batch

---

## Research Status

`sidecar_data_layer_filled = True`

`alpha_rerun_allowed = False`

The sidecars are now present, but they are not yet integrated into the daily
feature panel and have not been falsified as a pre-registered transition. The
correct next step is a narrow integration and strict falsification pass, not a
manifest A/B.
