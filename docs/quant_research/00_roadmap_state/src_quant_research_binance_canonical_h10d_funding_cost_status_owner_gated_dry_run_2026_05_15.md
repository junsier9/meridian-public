# src quant_research binance_canonical_h10d funding cost status owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: _funding_cost_status / validation funding readiness blocker`

## Decision

Do not move source and do not add a static contract in this pass.

`_funding_cost_status(...)` is a validation blocker, not a provider sync
helper. It sits after the funding facade has joined `funding_rate` and
`funding_sample_count` onto the scored frame, and before
`run_binance_canonical_validation(...)` decides whether a strategy is blocked
for live-readiness. Freezing it together with the funding facade would blur two
separate governance surfaces:

- funding data sync/load/attach behavior;
- validation readiness gating and blocker payload behavior.

The next safe automation step, if approved, is a tiny
import/signature-and-test-presence contract for `_funding_cost_status(...)`
only. That contract should not freeze full validation output schemas, provider
fetch behavior, or live-readiness authorization.

## Boundary Map

| layer | function / field | current role | risk |
| --- | --- | --- | --- |
| Funding facade input | `funding_rate`, `funding_sample_count` | Columns expected to be present after funding cost attach. | medium |
| Validation blocker | `_funding_cost_status(...)` | Converts scored-frame funding coverage into `ok` or `blocked`. | high but contractable |
| Active-universe scope | `universe_active` + `_truthy_series(...)` | Narrows coverage to active rows when available and non-empty. | medium/high |
| Validation runner | `run_binance_canonical_validation(...)` | Adds the funding blocker to `blockers` and writes `funding_cost_status` into the report. | very high |
| Funding facade | `sync_funding_cost_history(...)`, `load_funding_cost_daily(...)`, `attach_funding_cost_to_panel(...)` | Upstream data-foundation behavior already governed separately. | separate surface |

## Current Behavior Summary

`_funding_cost_status(...)` currently:

- returns `funding_cost_history_missing` when the scored frame is empty;
- returns `funding_cost_history_missing` when either `funding_rate` or
  `funding_sample_count` is missing;
- uses all rows by default;
- switches to `universe_active_rows` when `universe_active` exists and has at
  least one truthy row;
- treats positive `funding_sample_count` as covered;
- blocks when coverage is below the current `0.85` gate;
- returns `funding_cost_history_ok` when coverage is at or above the gate.

This dry-run records the behavior shape for future review. It does not approve
changing the gate, snapshotting full validation reports, or promoting any
strategy to live-readiness.

## Existing Behavior Test Baseline

Current direct behavior coverage:

- `tests/test_binance_canonical_h10d.py::BinanceCanonicalH10DTests::test_funding_status_ignores_inactive_price_rows`

Adjacent but separate coverage:

- funding facade sync/load/attach coverage in
  `test_funding_cost_sync_writes_daily_cost_only_rows_and_attaches_to_panel`;
- PIT eligibility tests that use `funding_rate` and
  `funding_sample_count` as part of decision eligibility;
- validation-status tests that aggregate blockers, but intentionally exclude
  funding blocker behavior from the existing validation-status contract.

## Existing Adjacent Contracts

Do not duplicate these surfaces:

- funding sync/load/path facade is covered by
  `src_quant_research_binance_canonical_h10d_funding_facade_contract.json`;
- validation status aggregation is covered by
  `src_quant_research_binance_canonical_h10d_validation_status_contract.json`;
- PIT universe eligibility is covered by
  `src_quant_research_binance_canonical_h10d_pit_universe_eligibility_contract.json`.

## Approved Next Automation

Allowed as the next small implementation batch:

- a contract JSON for `_funding_cost_status(...)` only;
- a static test that checks root-facade importability and `inspect.signature`;
- a required direct behavior-test presence check for
  `test_funding_status_ignores_inactive_price_rows`;
- explicit exclusions for funding facade behavior, provider HTTP behavior, full
  validation runner behavior, artifact schemas, and promotion/live-readiness
  decisions.

Optional owner-approved later tests:

- empty-frame blocker behavior;
- missing-column blocker behavior;
- active-universe coverage behavior around the `0.85` threshold.

## Explicit Deferred / Owner-Gated

Do not move or broad-freeze:

- `run_binance_canonical_validation(...)`;
- `_funding_cost_status(...)` source placement;
- funding provider fetch/sync/load/attach behavior;
- PIT eligibility behavior;
- full validation report payloads;
- full blocker list ordering;
- funding root path policy;
- artifact path selection;
- strategy promotion or live-readiness authorization.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No `src/enhengclaw/quant_research` files move or change.
- No contract JSON is introduced in this docs-only commit.
- No checked-in artifact paths are staged.
