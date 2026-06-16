# src quant_research binance_canonical_h10d identity/normalization post-extraction review

`Status: post-extraction review baseline`
`Date: 2026-05-15`
`Scope: _binance_canonical_identity.py and _binance_canonical_normalization.py`

## Decision

Do not move source in this phase.

Two narrow internal support modules already exist and should remain h10d-local
implementation modules:

- `src/enhengclaw/quant_research/_binance_canonical_identity.py`
- `src/enhengclaw/quant_research/_binance_canonical_normalization.py`

`src/enhengclaw/quant_research/binance_canonical_h10d.py` remains the visible
root facade by importing and re-exporting these helpers.

The next safe automation step is a pair of tiny internal-module identity
contracts. They should reuse the existing root facade contracts for signatures
and behavior samples, then add only the missing assertion that the facade
exports the exact same callables as the internal modules.

## Current Module Shape

Identity module:

- `_stable_hash`
- `_stable_int`

Timestamp normalization module:

- `_timestamp_zscore`
- `_timestamp_percentile_rank`

## Existing Protection

Already covered by
`config/quant_research/src_quant_research_binance_canonical_h10d_hash_identity_contract.json`:

- root-facade importability;
- signatures for `_stable_hash` and `_stable_int`;
- small deterministic hash samples;
- deterministic subject holdout bucket samples.

Already covered by
`config/quant_research/src_quant_research_binance_canonical_h10d_timestamp_normalization_helpers_contract.json`:

- root-facade importability;
- signatures for `_timestamp_zscore` and `_timestamp_percentile_rank`;
- tiny per-timestamp z-score and percentile-rank behavior samples;
- explicit approval that the timestamp-normalization implementation module is
  `enhengclaw.quant_research._binance_canonical_normalization`.

Current missing protection:

- no static contract asserts `_stable_hash` and `_stable_int` are owned by
  `_binance_canonical_identity.py`;
- no static contract asserts `_timestamp_zscore` and
  `_timestamp_percentile_rank` are owned by
  `_binance_canonical_normalization.py`;
- no static contract asserts the root facade exports the same callable objects
  as those internal modules.

## Approved Next Contract Shape

Allowed:

- assert internal-module symbols exist;
- assert root facade symbols exist;
- assert root facade callables are identical to the internal-module callables;
- reuse existing root facade contracts as signature and behavior-sample source;
- assert `_stable_hash.__module__` and `_stable_int.__module__` point at
  `enhengclaw.quant_research._binance_canonical_identity`;
- assert `_timestamp_zscore.__module__` and
  `_timestamp_percentile_rank.__module__` point at
  `enhengclaw.quant_research._binance_canonical_normalization`.

Not allowed:

- formula-level scorer behavior;
- feature weights or selected feature subsets;
- full feature manifest content;
- falsification metrics, validation status, or promotion decisions;
- backtest output snapshots;
- caller counts;
- moving either helper family into a generic repo-wide utility.

## Deferred / Owner-Gated

Owner approval and a fresh dry-run are required before:

- changing hash serialization details;
- changing subject-to-holdout bucket identity;
- reusing `_stable_hash` or `_stable_int` as a repo-wide utility;
- changing timestamp group normalization formulas beyond the existing tiny
  samples;
- merging h10d-local timestamp normalization with similarly named helpers in
  `features.py`;
- changing full alpha scorer formulas that consume these helpers.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This review is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Later implementation commits, if added, stay limited to contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this review batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
