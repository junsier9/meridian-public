# src quant_research features.py F3-B1 Relative Value Spread Scorer-Family Dry-Run

`Status: read-only docs-only dry-run baseline`
`Scope: src/enhengclaw/quant_research/features.py F3-B1 relative_value_spread scorer family`
`Date: 2026-05-15`
`Mode: documentation-only; no static contract, no code change, no migration approved`

This artifact records the F3-B1 slice of the broader
`pair_relative_residualized` scorer surface. It intentionally separates
`relative_value_spread` from `pair_book` and `residualized_pair_book`, because
those adjacent surfaces carry different runtime and governance risks.

## Decision

F3-B1 may proceed to a future importability/signature-only contract after owner
approval.

The approved candidate scope is `xs_relative_value_spread_v1_score` through
`xs_relative_value_spread_v9_score`. Do not include pair book, residualized pair
book, relative-strength base scorers, hypothesis-batch pair-construction
normalization, or archived manifest lifecycle behavior in the same contract.

Do not freeze formula output, rank ordering, alpha quality, admission results,
or archived-manifest semantics.

## In Scope

| scorer | source line | current direct caller surface | coverage read |
| --- | ---: | --- | --- |
| `xs_relative_value_spread_v1_score` | `features.py:2316` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v22 manifest | direct behavior test |
| `xs_relative_value_spread_v2_score` | `features.py:2390` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v52 manifest | direct behavior test |
| `xs_relative_value_spread_v3_score` | `features.py:2462` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v53 manifest | direct behavior test |
| `xs_relative_value_spread_v4_score` | `features.py:2543` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v54 manifest | direct behavior test |
| `xs_relative_value_spread_v5_score` | `features.py:2633` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v55 manifest | direct behavior test |
| `xs_relative_value_spread_v6_score` | `features.py:2726` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v56 manifest | direct behavior test |
| `xs_relative_value_spread_v7_score` | `features.py:2822` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v57 manifest | direct behavior test |
| `xs_relative_value_spread_v8_score` | `features.py:5241` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v58 manifest | direct behavior test |
| `xs_relative_value_spread_v9_score` | `features.py:5096` | `lab.py`, archived v59 manifest | no direct behavior test found |

All nine scorer signatures currently use:

```python
def scorer(frame: pd.DataFrame, *, feature_columns: Iterable[str] | None = None) -> pd.Series
```

The `feature_columns` parameter is part of the scorer facade shape. F3-B1 may
freeze that signature shape later, but this dry-run does not freeze formulas.

## Existing Coverage

Focused behavior coverage exists in `tests/test_quant_hypothesis_batch.py` for
`v1` through `v8`:

| test | scorer focus |
| --- | --- |
| `test_relative_value_spread_prefers_derivatives_cheap_but_spot_intact` | `v1` |
| `test_relative_value_spread_v2_score_is_distinct_and_prefers_cheap_quality_names` | `v1`, `v2` |
| `test_relative_value_spread_v3_score_penalizes_extreme_capitulation` | `v2`, `v3` |
| `test_relative_value_spread_v4_score_prefers_cheap_leaders_over_capitulation` | `v3`, `v4` |
| `test_relative_value_spread_v5_score_favors_light_discount_leaders` | `v4`, `v5` |
| `test_relative_value_spread_v6_score_narrows_discount_and_keeps_leadership_first` | `v5`, `v6` |
| `test_relative_value_spread_v7_score_prefers_leader_reset_window_over_froth` | `v6`, `v7` |
| `test_relative_value_spread_v8_score_demotes_frothy_leaders_vs_v7` | `v7`, `v8` |

No direct behavior test was found for `v9`. That does not block a future
import/signature-only contract, but it should block any claim that the whole
`v1-v9` family has formula behavior coverage.

## Boundary Notes

F3-B1 is cleaner than pair book:

- no scripts directly import the nine relative-value spread scorers;
- `lab.py` imports and dispatches all nine names;
- archived Phase 0 manifests reference the historical candidates;
- `tests/test_quant_hypothesis_batch.py` imports `v1-v8` directly;
- no `hypothesis_batch.py` pair-construction allowlist was found for this
  scorer family.

The family is still research-heavy. The functions are formula variants, not a
stable alpha-quality guarantee.

## Explicitly Out Of Scope

This dry-run does not approve:

- a full `features.py` scorer-family contract;
- moving or splitting `features.py`;
- moving the relative-value spread scorers into a new source module;
- freezing formula output, score ordering, alpha quality, or promotion status;
- freezing archived manifest lifecycle semantics;
- changing `lab.py` registry or scoring-family dispatch behavior;
- changing `build_cross_sectional_feature_bundle` or feature sidecar merges;
- changing `_feature_series`, `_timestamp_percentile_rank`, or `_timestamp_zscore`;
- including `xs_pair_spread_book_v*` scorers;
- including `xs_residualized_pair_book_v*` scorers;
- including `relative_strength_score` or `xs_relative_strength_score`;
- touching `hypothesis_batch.py` pair-construction normalization.

## Future Contract Shape

If owner-approved, the first F3-B1 contract should be import/signature only:

- source module: `enhengclaw.quant_research.features`;
- target names: `xs_relative_value_spread_v1_score` through
  `xs_relative_value_spread_v9_score`;
- validation mode: `importability_signature_only`;
- expected signature: `frame` positional/keyword plus optional keyword-only
  `feature_columns`;
- excluded surfaces: formulas, score ordering, alpha quality, archived
  manifests, lab dispatch semantics, caller counts, pair book, residualized pair
  book, and source migration.

Decision nuance:

- `v1-v8` are reasonable contract candidates because they already have focused
  behavior tests.
- `v9` may be included in an import/signature-only contract because it is
  present in `features.py`, `lab.py`, and an archived manifest, but it must be
  labeled as signature-only with no behavior coverage.
- If the owner wants behavior confidence for every target before any contract,
  split `v9` out or add a tiny separate smoke test before including it.

## Validation Matrix

For this docs-only dry-run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -k relative_value_spread -q
git diff --check
```

If a future import/signature-only contract is added:

```powershell
python -m pytest tests\test_static_contracts.py tests\test_quant_hypothesis_batch.py -k relative_value_spread -q
git diff --check
```

If formula behavior, feature construction, or lab dispatch changes, this
F3-B1 boundary is insufficient; return to an owner-gated dry-run that includes
the affected runtime path.

## Next Gate

The next gate is an owner decision on whether to implement the F3-B1
import/signature-only contract for `v1-v9`, or to split out `v9` until it has a
dedicated behavior smoke. Do not include pair book or residualized pair book in
that contract.
