# src quant_research binance_canonical_h10d internal module identity closure

`Status: low-risk internal-module identity closure`
`Date: 2026-05-15`
`Scope: extracted _binance_canonical_* support modules`

## Decision

The low-risk internal-module identity track is now closed.

Do not add more automatic source moves under `binance_canonical_h10d.py` without
a fresh owner-gated dry-run. The remaining root-local surfaces are no longer
low-risk identity cleanups; they are behavior, orchestration, partition-boundary,
or validation surfaces.

## Covered Internal Modules

| Internal module | Governed surface | Contract |
| --- | --- | --- |
| `_binance_canonical_archive.py` | low-coupling archive helpers and kline constants | `config/quant_research/src_quant_research_binance_canonical_archive_helpers_contract.json` |
| `_binance_canonical_artifacts.py` | artifact writer helpers and universe-membership writer re-export identity | `config/quant_research/src_quant_research_binance_canonical_artifacts_module_contract.json` |
| `_binance_canonical_funding.py` | funding facade helpers with existing root contract samples | `config/quant_research/src_quant_research_binance_canonical_funding_module_contract.json` |
| `_binance_canonical_identity.py` | `_stable_hash` and `_stable_int` internal ownership and root facade identity | `config/quant_research/src_quant_research_binance_canonical_identity_module_contract.json` |
| `_binance_canonical_normalization.py` | timestamp normalization helper internal ownership and root facade identity | `config/quant_research/src_quant_research_binance_canonical_normalization_module_contract.json` |
| `_binance_canonical_reporting.py` | report render helpers, root facade identity, and tiny render samples | `config/quant_research/src_quant_research_binance_canonical_h10d_reporting_render_contract.json` |
| `_binance_canonical_risk_columns.py` | `BINANCE_RISK_BRAKE_COLUMNS` registry ownership and root facade identity | `config/quant_research/src_quant_research_binance_canonical_risk_columns_module_contract.json` |
| `_binance_canonical_run_metadata.py` | run metadata helper ownership and root facade identity | `config/quant_research/src_quant_research_binance_canonical_run_metadata_module_contract.json` |
| `_binance_canonical_time.py` | datetime helper ownership and root facade identity | `config/quant_research/src_quant_research_binance_canonical_time_module_contract.json` |

## Still Root-Local / Owner-Gated

These are intentionally not part of the low-risk identity closure:

- `_partition_month` and `_symbol_partition_paths`, because the partition dry-run
  classified them as an archive/funding boundary;
- score surface and feature-manifest construction, because behavior contracts
  intentionally avoid source movement;
- risk-brake formula behavior, because the registry tuple contract does not
  authorize formula relocation;
- PIT universe, validation, falsification, and stratified holdout surfaces;
- `run_binance_canonical_validation(...)` orchestration and
  `run_backtest_for_config(...)`;
- reporting metric sanitation helpers that still belong to root behavior
  contracts rather than a new module split.

## Guardrails For Future Automation

Allowed without owner approval:

- fix stale docs/catalog references to the contracts above;
- add missing governance-index links for docs-only artifacts;
- tighten tests that assert already-approved module/facade identity.

Not allowed without owner approval:

- move another helper out of `binance_canonical_h10d.py`;
- expand `_binance_canonical_reporting.py` to own metric sanitation;
- move `_partition_month` into archive, funding, or a generic path module;
- convert root-local behavior contracts into source-migration approvals;
- freeze full markdown reports, full artifact schemas, validation metrics, or
  backtest outputs as golden snapshots.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- All extracted `_binance_canonical_*` support modules have either an explicit
  internal-module/facade identity contract or an existing contract that already
  covers that identity.
- Remaining root-local surfaces are named as owner-gated, not silently treated
  as low-risk cleanup.
- This closure is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
