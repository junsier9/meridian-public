# src quant_research binance_canonical_h10d risk-brake behavior bucket closure

`Status: bucket closure baseline`
`Date: 2026-05-16`
`Scope: short-squeeze veto, high-vol rebound brake, and risk-brake combiner`

## Decision

The risk-brake behavior bucket is closed for automatic low-risk governance
work.

The bucket now has:

- a root-surface classification entry for the three risk-brake behavior
  functions;
- a signature and required-behavior-test contract for the active risk-brake
  helpers;
- an adjacent universe-membership writer contract for the retained risk-brake
  output columns;
- explicit exclusions that block source movement, broad formula snapshots,
  validation metric claims, ablation metric value freezes, and caller counts.

No further risk-brake source movement, formula freezing, or strategy-performance
interpretation should be performed by automation without a new owner-approved
dry-run artifact.

## Covered Surfaces

| surface | governance state | current boundary |
| --- | --- | --- |
| `add_short_squeeze_veto_multiplier(...)` | covered by risk-brake behavior static contract | importability, signature, and required behavior-test presence only |
| `add_binance_risk_brake_columns(...)` | covered by risk-brake behavior static contract | importability, signature, and required behavior-test presence only |
| `_add_high_vol_rebound_short_brake(...)` | covered by risk-brake behavior static contract | importability, signature, and required behavior-test presence only |
| `BINANCE_RISK_BRAKE_COLUMNS` | covered by universe-membership writer contract | column registry and writer projection sample only |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- exact formula-output snapshots beyond the existing behavior tests;
- validation or ablation metric value snapshots;
- strategy pass/fail or live-readiness claims;
- PIT universe behavior snapshots;
- funding behavior snapshots;
- execution ledger behavior;
- internal module extraction;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the active risk-brake contract:

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
- Risk-brake behavior work is treated as governance-complete at the current
  minimal-contract layer.
- Future work starts from a new owner-gated artifact instead of silently
  widening the existing contracts.
