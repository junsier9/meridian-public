# src quant_research binance_canonical_h10d attribution and paper-shadow owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-16`
`Scope: attribution_and_paper_shadow root-surface bucket`

## Decision

Do not move attribution or paper-shadow source code in this pass.

The bucket mixes execution-dependent attribution runners, paper-shadow ledger
construction, schema-bearing empty payload helpers, and a few tiny pure helpers.
Only the smallest pure helpers are safe for an automatic follow-up
import/signature plus synthetic-smoke contract.

Approved for a minimal follow-up:

- `_row_float(...)`;
- `_paper_shadow_action(...)`.

Everything else in the bucket remains owner-gated until a separate dry-run
proves a safe facade-first split or a smaller contract boundary.

## Boundary Map

| layer | functions | current role | risk |
| --- | --- | --- | --- |
| Attribution runners | `compute_position_attribution(...)`, `compute_factor_leave_one_out_attribution(...)` | Compute realized position attribution and leave-one-out factor attribution using execution path, funding cost, rescoring, backtest, and aggregation helpers. | high |
| Paper-shadow runner | `build_paper_shadow_execution_ledger(...)` | Builds manual-only paper-shadow ledger rows, cost fields, position/order counts, and data-gap blockers. | high |
| Empty payload helpers | `_empty_position_attribution(...)`, `_empty_factor_leave_one_out(...)`, `_empty_paper_shadow_execution_ledger(...)` | Define fallback payload shape for validation report artifacts. | medium |
| Tiny pure helpers | `_row_float(...)`, `_paper_shadow_action(...)` | Convert row values to float and classify synthetic paper-shadow action transitions. | low |
| Aggregation helpers | `_summarize_paper_shadow_ledger(...)`, `_decision_rank_by_subject(...)`, `_summarize_position_attribution(...)`, `_factor_position_delta(...)`, `_aggregate_position_contribution(...)`, `_records(...)` | Build report-facing summaries, ranking metadata, contribution deltas, and JSON-record payloads. | medium/high |
| Risk overlay helper | `_apply_short_position_multiplier(...)` | Applies configured short multiplier columns to target weights. | high, adjacent to risk-brake behavior |

## Current Test Baseline

Direct behavior coverage exists for the three high-level runners:

- `test_attribution_exposes_short_leg_loss`;
- `test_factor_leave_one_out_reports_realized_metric_deltas`;
- `test_paper_shadow_execution_ledger_records_no_live_orders`.

These tests are useful execution smoke tests, but they are not sufficient to
freeze exact attribution payloads, ledger schemas, metric values, or source
movement.

## Approved Minimal Helper Contract

Automation may add a tiny contract for `_row_float(...)` and
`_paper_shadow_action(...)` only.

Allowed:

- contract JSON under `config/quant_research/`;
- one static test in `tests/test_static_contracts.py`;
- one tiny synthetic behavior smoke in `tests/test_binance_canonical_h10d.py`;
- root-level symbol presence and `inspect.signature` checks;
- explicit exclusions for source movement, runner behavior, exact attribution
  metrics, ledger schemas, report payloads, risk-brake formulas, and caller
  counts.

## Explicit Deferred / Owner-Gated

Do not automatically contract or move:

- `compute_position_attribution(...)`;
- `compute_factor_leave_one_out_attribution(...)`;
- `build_paper_shadow_execution_ledger(...)`;
- empty payload helper schemas;
- paper-shadow ledger summary schemas;
- position attribution aggregation formulas;
- factor leave-one-out delta formulas;
- `_apply_short_position_multiplier(...)`;
- `_records(...)` JSON payload behavior;
- full validation report artifact payloads.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No source movement is approved.
- Any follow-up implementation stays limited to the tiny helper smoke plus
  contract JSON/static test.
