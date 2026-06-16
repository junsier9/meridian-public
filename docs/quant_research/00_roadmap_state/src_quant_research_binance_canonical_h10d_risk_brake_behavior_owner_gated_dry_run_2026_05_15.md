# src quant_research binance_canonical_h10d risk-brake behavior owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: add_short_squeeze_veto_multiplier / add_binance_risk_brake_columns / _add_high_vol_rebound_short_brake`

## Decision

Do not move risk-brake formula source code in this automation pass.

The risk-brake surface is an active strategy-hardening layer. It binds
short-squeeze veto logic, high-vol rebound market-state detection, multiplier
combination, support-column retention, ablation reporting, and validation
consumers. It is not a generic utility slice.

Automation may add a minimal static contract that freezes root-facade
importability/signatures and requires the existing behavior tests to remain
present. Automation must not create broad formula snapshots, move source, or
claim validation performance coverage from this contract.

## Boundary Map

| layer | functions / contract | current role | risk |
| --- | --- | --- | --- |
| Short-squeeze veto | `add_short_squeeze_veto_multiplier(...)` | Ranks 5d realized volatility and close-to-high distance by timestamp, then emits veto multiplier and flag. | high |
| High-vol rebound brake | `_add_high_vol_rebound_short_brake(...)` | Uses decision-time market-state medians/shares and rolling thresholds to reduce short exposure. | high |
| Overlay combiner | `add_binance_risk_brake_columns(...)` | Initializes support columns, applies enabled brakes, and combines short multipliers with `min(...)`. | high |
| Column registry | `BINANCE_RISK_BRAKE_COLUMNS` / universe-membership writer contract | Already covered by `src_quant_research_binance_canonical_h10d_universe_membership_writer_contract.json`. | medium, already governed |
| Downstream consumers | `prepare_scored_backtest_frame(...)`, ablations, validation artifacts | Retain and consume risk-brake columns without admitting them as alpha features. | high |

## Current Behavior Test Baseline

Existing tests protect the current behavior boundary:

- `test_risk_brake_columns_are_retained_without_entering_alpha_features`
- `test_high_vol_rebound_brake_uses_decision_time_market_state`
- `test_ablation_runner_reports_long_only_short_disabled_and_short_veto`

The existing universe-membership writer contract separately freezes the
`BINANCE_RISK_BRAKE_COLUMNS` tuple and writer projection sample. This dry-run
does not reopen that column-registry decision.

## Approved Minimal Contract

Allowed in the follow-up implementation:

- contract JSON under `config/quant_research/`;
- one static test in `tests/test_static_contracts.py`;
- root-facade importability and `inspect.signature` checks for the three
  risk-brake behavior functions;
- explicit list of required existing behavior test method names;
- explicit reference to the existing universe-membership writer contract as the
  column-registry contract;
- explicit exclusions for source migration, full formula snapshots, validation
  metrics, ablation metric values, and downstream execution behavior.

## Explicit Non-Goals

Do not freeze or move:

- exact risk-brake formula output beyond existing behavior tests;
- `BINANCE_RISK_BRAKE_COLUMNS` again;
- full universe membership schema;
- validation report payloads;
- ablation metric values;
- funding behavior;
- PIT universe behavior;
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
