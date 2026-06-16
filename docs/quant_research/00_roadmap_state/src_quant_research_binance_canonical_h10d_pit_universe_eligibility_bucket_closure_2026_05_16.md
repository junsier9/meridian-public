# src quant_research binance_canonical_h10d PIT universe eligibility bucket closure

`Status: bucket closure baseline`
`Date: 2026-05-16`
`Scope: PIT universe, PIT eligibility, and root-local truthy mask helper`

## Decision

The PIT universe and eligibility bucket is closed for automatic low-risk
governance work.

The bucket now has:

- a root-surface classification entry for all PIT universe and eligibility
  functions;
- a signature and required-behavior-test contract for the four public/root
  PIT helpers;
- a tiny root-local behavior contract for `_truthy_series(...)`;
- explicit exclusions that block source movement, broad behavior snapshots,
  membership snapshots, validation metrics, funding behavior, and caller counts.

No further PIT universe or eligibility source movement should be performed by
automation without a new owner-approved dry-run artifact.

## Covered Surfaces

| surface | governance state | current boundary |
| --- | --- | --- |
| `freeze_binance_ohlcv_universe(...)` | covered by PIT eligibility static contract | importability, signature, and required behavior-test presence only |
| `apply_point_in_time_rolling_universe(...)` | covered by PIT eligibility static contract | importability, signature, and required behavior-test presence only |
| `add_pit_strategy_eligibility(...)` | covered by PIT eligibility static contract | importability, signature, and required behavior-test presence only |
| `_pit_recent_data_eligible(...)` | covered by PIT eligibility static contract | importability, signature, and required behavior-test presence only |
| `_truthy_series(...)` | covered by dedicated root-local truthy mask contract | importability, signature, and tiny synthetic bool/text samples only |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- exact PIT universe membership snapshots;
- prepared backtest-frame schema snapshots;
- validation or falsification result snapshots;
- funding sample behavior snapshots;
- risk-brake formula behavior;
- caller-count contracts;
- internal module extraction;
- generic utility extraction for `_truthy_series(...)`.

## Validation Baseline

Use the same validation set as the two active contracts:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This closure document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- PIT universe and eligibility work is treated as governance-complete at the
  current minimal-contract layer.
- Future work starts from a new owner-gated artifact instead of silently
  widening the existing contracts.
