# src quant_research binance_canonical_h10d identity/normalization bucket closure

`Status: bucket closure baseline`
`Date: 2026-05-16`
`Scope: hash identity and timestamp normalization helper buckets`

## Decision

The identity/normalization helper bucket is closed at the current
minimal-contract layer.

The bucket now has:

- a post-extraction review for `_binance_canonical_identity.py` and
  `_binance_canonical_normalization.py`;
- a hash identity contract covering root-facade importability, signatures,
  deterministic hash samples, and deterministic subject holdout bucket samples;
- a timestamp normalization helper contract covering root-facade importability,
  signatures, and tiny per-timestamp z-score/percentile-rank samples;
- explicit exclusions for source migration, full feature manifest content,
  scorer formulas, score outputs, feature weights/subsets, falsification
  metrics, backtest outputs, pass/fail decisions, subject normalization changes,
  generic utility extraction, and caller counts.

No further automation should widen this bucket into scorer behavior, manifest
identity, falsification metrics, or generic utility ownership without a new
owner-approved dry-run artifact.

## Covered Surfaces

| surface | governance state | current boundary |
| --- | --- | --- |
| `_stable_hash(...)` | covered by hash identity contract | importability, signature, minimal deterministic hash samples, and stable JSON ordering sample |
| `_stable_int(...)` | covered by hash identity contract | importability, signature, deterministic integer samples, and subject holdout bucket samples |
| `_timestamp_zscore(...)` | covered by timestamp normalization contract | importability, signature, and tiny per-timestamp z-score sample |
| `_timestamp_percentile_rank(...)` | covered by timestamp normalization contract | importability, signature, and tiny per-timestamp percentile-rank sample |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- source movement for this bucket;
- exact full feature manifest content;
- formula-level scorer behavior;
- score output snapshots;
- feature weights or selected feature subsets;
- falsification metrics or seeded split payloads;
- backtest outputs or validation pass/fail decisions;
- subject normalization behavior;
- generic repo-wide hash/normalization utility extraction;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the active identity/normalization contracts:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This closure document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Identity/normalization work is treated as governance-complete at the current
  minimal-contract layer.
- Future work starts from a new owner-gated artifact instead of silently
  widening hash, timestamp-normalization, score, manifest, falsification,
  validation, backtest, or generic-utility contracts.
