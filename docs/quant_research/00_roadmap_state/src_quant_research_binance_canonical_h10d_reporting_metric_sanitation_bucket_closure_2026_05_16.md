# src quant_research binance_canonical_h10d reporting metric sanitation bucket closure

`Status: bucket closure baseline`
`Date: 2026-05-16`
`Scope: reporting_metric_sanitation root-surface bucket`

## Decision

The `reporting_metric_sanitation` bucket is closed at the current
minimal-contract layer.

The bucket now has:

- an owner-gated behavior-contract dry-run;
- a static contract covering root-facade importability, signatures, and tiny
  behavior samples for the four reporting sanitation helpers;
- downstream references from run-backtest, reporting-render, and gap-policy
  contracts;
- explicit exclusions for source movement, full validation payloads,
  falsification metrics, ablation schemas, period-return construction,
  execution ledger behavior, PIT/risk-brake/funding behavior, and caller counts.

No further automation should widen reporting payload or metric behavior coverage
without a new owner-approved dry-run artifact.

## Covered Surfaces

| surface | governance state | current boundary |
| --- | --- | --- |
| `_rank_ic_summary(...)` | covered by reporting metric sanitation contract | importability, signature, one tiny two-period rank-IC sample, and empty-output behavior |
| `_strip_periods(...)` | covered by reporting metric sanitation contract | importability, signature, and top-level `periods` removal sample |
| `_drop_periods_from_metrics(...)` | covered by reporting metric sanitation contract | importability, signature, and nested report-bucket `periods` removal sample |
| `_split_contract(...)` | covered by reporting metric sanitation contract | importability, signature, one explicit `4h` / `15` bar sample, and one default sample |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- source movement for this bucket;
- exact validation report payload snapshots;
- exact falsification or ablation metric snapshots;
- full period-return construction behavior;
- `_run_backtest(...)` behavior;
- execution ledger behavior;
- PIT universe or risk-brake behavior;
- funding cost behavior;
- caller-count contracts;
- formula or threshold changes in the h10d validation pipeline.

## Validation Baseline

Use the same validation set as the active reporting sanitation contract:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This closure document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Reporting sanitation work is treated as governance-complete at the current
  minimal-contract layer.
- Future work starts from a new owner-gated artifact instead of silently
  widening validation, reporting, falsification, ablation, execution, PIT,
  risk-brake, or funding contracts.
