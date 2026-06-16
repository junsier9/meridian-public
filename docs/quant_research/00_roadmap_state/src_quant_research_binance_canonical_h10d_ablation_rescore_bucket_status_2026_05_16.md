# src quant_research binance_canonical_h10d ablation and rescore bucket status

`Status: owner-gated status baseline`
`Date: 2026-05-16`
`Scope: ablations_and_feature_subset_rescore root-surface bucket`

## Decision

Do not add a broad runtime contract and do not move source for this bucket in
the automatic pass.

Supersession note: the later owner-delegated terminal batch adds a narrow
signature-plus-smoke contract for this bucket. That contract does not approve
source movement, ablation metric snapshots, period-return payload snapshots, or
score/risk-brake formula freezes.

`ablations_and_feature_subset_rescore` is execution-dependent and score-surface
adjacent. It combines diagnostic ablation variants, core20 eligibility filters,
feature-subset rescoring, backtest calls, period-return export preparation, and
report-facing ablation summaries. The current test coverage is useful, but it
does not justify freezing ablation metric values, period payloads, core20
membership semantics, or source placement.

## Boundary Map

| surface | current role | risk |
| --- | --- | --- |
| `run_binance_core_ablations(...)` | Builds long-only, short-disabled, short-veto, and optional core20 diagnostic variants; calls `_run_backtest(...)` and emits summary plus period returns. | high |
| `add_core20_ablation_eligibility(...)` | Adds core20/non-core long/short eligibility columns based on reference subjects, decision eligibility, and liquidity bucket. | medium/high |
| `_reference_core20_subjects(...)` | Resolves configured or default reference core20 subjects. | medium |
| `_rescore_for_feature_subset(...)` | Recomputes score for leave-one-out and feature-subset attribution while preserving purity checks. | high |

## Existing Protection

Existing tests and adjacent contracts protect pieces of the bucket:

- `test_ablation_runner_reports_long_only_short_disabled_and_short_veto`
  confirms the main diagnostic variant names and period returns are present;
- risk-brake behavior contract requires that ablation test to remain present;
- `_run_backtest(...)` is covered by the run-backtest contract;
- reporting metric sanitation explicitly excludes full ablation report schemas;
- score surface and feature subset purity are governed by separate contracts.

This is enough for terminal signature/smoke coverage, not enough for automatic
source movement or broad runtime contract implementation.

## Required Before Any Future Contract Expansion

A future dry-run must decide whether any expansion beyond the terminal
signature/smoke contract should cover:

- behavior beyond import/signature for `run_binance_core_ablations(...)`;
- tiny synthetic eligibility behavior for `add_core20_ablation_eligibility(...)`;
- config-resolution behavior for `_reference_core20_subjects(...)`;
- behavior beyond signature-only protection for `_rescore_for_feature_subset(...)`.

That future dry-run must explicitly exclude ablation metric values,
period-return payload values, strategy pass/fail status, score formulas, risk
brake formulas, and full report schemas.

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- source movement for this bucket;
- broad ablation runner contracts beyond the terminal signature/smoke contract;
- exact ablation metric snapshots;
- exact period-return payload snapshots;
- exact core20 membership snapshots beyond synthetic fixtures;
- score formula snapshots;
- risk-brake formula behavior;
- validation report payload snapshots;
- caller-count contracts.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This status document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The bucket remains explicitly owner-gated.
- Future work starts from a narrower dry-run instead of silently widening
  adjacent risk-brake, score-surface, or backtest contracts.
