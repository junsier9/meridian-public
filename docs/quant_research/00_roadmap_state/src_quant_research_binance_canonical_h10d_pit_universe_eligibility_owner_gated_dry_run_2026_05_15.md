# src quant_research binance_canonical_h10d PIT universe eligibility owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: freeze_binance_ohlcv_universe / apply_point_in_time_rolling_universe / add_pit_strategy_eligibility / _pit_recent_data_eligible`

## Decision

Do not move PIT universe or eligibility source code in this automation pass.

The PIT surface is higher risk than the previous score-surface and reporting
sanitation contracts. It binds point-in-time universe membership, quote-volume
ranking, rolling coverage, funding-sample eligibility, bucket stability, edge
rank exclusion, lifetime history, and prepared backtest-frame retention.

Automation may add a minimal static contract that freezes root-facade
importability/signatures and requires the existing behavior tests to remain
present. Automation must not create a broad behavior snapshot or source move
without owner approval.

## Boundary Map

| layer | functions | current role | risk |
| --- | --- | --- | --- |
| Frozen quote-volume universe | `freeze_binance_ohlcv_universe(...)` | Uses historical quote volume and coverage to produce frozen membership records. | high |
| Point-in-time rolling universe | `apply_point_in_time_rolling_universe(...)` | Applies rolling quote-volume selection and marks `universe_active`, rank, and liquidity buckets per timestamp. | high |
| PIT eligibility masks | `add_pit_strategy_eligibility(...)`, `_pit_recent_data_eligible(...)` | Computes recent/lifetime data eligibility, funding-sample requirements, bucket stability, top-long/mid-short masks, and active-long masks. | high |
| Downstream consumers | `prepare_scored_backtest_frame(...)`, falsification and validation paths | Consume PIT columns as active trading/validation gates. | high |

## Current Behavior Test Baseline

Existing tests already protect the core behavior:

- `test_universe_freeze_uses_quote_volume_without_open_interest`
- `test_pit_rolling_universe_uses_only_point_in_time_quote_volume`
- `test_pit_top_mid_eligibility_uses_recent_visible_completeness`
- `test_pit_mid_short_eligibility_requires_visible_bucket_stability`
- `test_pit_mid_short_eligibility_can_exclude_edge_rank_symbols`
- `test_pit_data_eligibility_requires_point_in_time_lifetime_history`

These tests are sufficient for a minimal static contract that requires the PIT
behavior test baseline to remain discoverable. They are not sufficient for a
source move.

## Approved Minimal Contract

Allowed in the follow-up implementation:

- contract JSON under `config/quant_research/`;
- one static test in `tests/test_static_contracts.py`;
- root-facade importability and `inspect.signature` checks for the four PIT
  functions;
- explicit list of required existing behavior test method names;
- explicit exclusions for source migration, full behavior snapshots, validation
  pass/fail metrics, and downstream execution behavior.

## Explicit Non-Goals

Do not freeze or move:

- full universe membership snapshots;
- exact prepared backtest-frame schemas;
- validation report payloads;
- falsification outputs;
- funding sync behavior;
- risk-brake behavior;
- execution ledger behavior;
- `_truthy_series(...)` as a generic utility;
- caller counts;
- source migration or internal module layout.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The follow-up implementation, if performed, touches only a contract JSON and
  `tests/test_static_contracts.py`.
- No `src/enhengclaw/quant_research` files move or change.
- No checked-in artifact paths are staged.
