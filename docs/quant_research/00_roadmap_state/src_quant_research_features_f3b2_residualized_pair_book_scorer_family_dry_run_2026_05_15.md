# src quant_research features.py F3-B2 Residualized Pair Book Scorer-Family Dry-Run

`Status: read-only docs-only dry-run baseline`
`Scope: src/enhengclaw/quant_research/features.py F3-B2 residualized_pair_book scorer family`
`Date: 2026-05-15`
`Mode: documentation-only; no static contract, no source migration approved`

This artifact records the F3-B2 slice of the broader
`pair_relative_residualized` scorer surface. It intentionally separates
`residualized_pair_book` from `relative_value_spread` and `pair_book`, because
the current test surface for this family is thinner than F3-B1 and should not
be converted directly into a signature contract.

## Decision

Do not proceed directly to an importability/signature-only static contract.

F3-B2 must first add a tiny behavior smoke test for
`xs_residualized_pair_book_v1_score` and `xs_residualized_pair_book_v2_score`.
After that smoke passes, owner approval may allow a narrow
importability/signature-only contract for the two names.

The smoke test should prove only that both scorers:

- are callable on a small cross-sectional frame;
- preserve a `float64` Series with the original index and row count;
- return bounded values for the synthetic frame;
- rank a cheap but clean-quality row above a similarly cheap broken-tape row.

Do not freeze formula output, exact scores, complete rank ordering, alpha
quality, promotion status, or archived-manifest semantics.

## In Scope

| scorer | source line | current direct caller surface | coverage read |
| --- | ---: | --- | --- |
| `xs_residualized_pair_book_v1_score` | `features.py:5372` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v23 manifest | imported but not called |
| `xs_residualized_pair_book_v2_score` | `features.py:5474` | `lab.py`, `tests/test_quant_hypothesis_batch.py`, archived v24 manifest | imported but not called |

Both scorer signatures currently use:

```python
def scorer(frame: pd.DataFrame, *, feature_columns: Iterable[str] | None = None) -> pd.Series
```

The `feature_columns` parameter is part of the scorer facade shape. F3-B2 may
freeze that signature shape later, but only after the behavior smoke creates a
minimal runtime baseline.

## Existing Coverage

`tests/test_quant_hypothesis_batch.py` imports both residualized pair book
scorers, but no current test calls either scorer.

Focused command observation:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -k residualized_pair -q
```

Current result before this F3-B2 smoke gate: zero selected tests. That means an
import/signature-only contract would freeze names without proving that the
runtime scorer functions still execute on even a tiny representative frame.

## Behavior Smoke Gate

The first test should use a four-row single-timestamp frame with these roles:

| role | intended distinction |
| --- | --- |
| `clean_cheap` | derivatives/spot cheapness plus intact relative strength, slope, support, and low stress |
| `broken_cheap` | similar cheapness but weak relative strength, weak slope, broken support, high volatility, and poor reset |
| `expensive_quality` | clean tape but not cheap |
| `neutral` | middle-of-book reference row |

The test should assert only the narrow compatibility facts:

- both scorer results preserve the input index;
- both scorer results have length `4`;
- both scorer results are `float64`;
- all synthetic-frame scores are within `[-1.0, 1.0]`;
- `clean_cheap` scores above `broken_cheap` for both v1 and v2.

This is a smoke gate, not a formula snapshot. Do not assert exact numeric
scores and do not use this smoke to claim the scorer family is promoted or
research-valid.

## Boundary Notes

F3-B2 is more sensitive than F3-B1 because its current test coverage is import
only:

- no scripts directly import the two residualized pair book scorers;
- `lab.py` imports and dispatches both names;
- archived Phase 0 manifests reference the historical candidates;
- `tests/test_quant_hypothesis_batch.py` imports both names but does not call
  them before the smoke gate;
- no `hypothesis_batch.py` pair-construction allowlist was found for this
  scorer family.

The family is still research-heavy. The functions are formula variants, not a
stable alpha-quality guarantee.

## Explicitly Out Of Scope

This dry-run does not approve:

- a full `features.py` scorer-family contract;
- moving or splitting `features.py`;
- moving residualized pair book scorers into a new source module;
- freezing exact formula output, score ordering, alpha quality, or promotion
  status;
- freezing archived manifest lifecycle semantics;
- changing `lab.py` registry or scoring-family dispatch behavior;
- changing `build_cross_sectional_feature_bundle` or feature sidecar merges;
- changing `_feature_series`, `_timestamp_percentile_rank`, or
  `_timestamp_zscore`;
- including `xs_pair_spread_book_v*` scorers;
- including `xs_relative_value_spread_v*` scorers;
- including `relative_strength_score` or `xs_relative_strength_score`;
- touching `hypothesis_batch.py` pair-construction normalization.

## Future Contract Shape

If owner-approved after the behavior smoke passes, the first F3-B2 contract
should be import/signature only:

- source module: `enhengclaw.quant_research.features`;
- target names: `xs_residualized_pair_book_v1_score` and
  `xs_residualized_pair_book_v2_score`;
- validation mode: `importability_signature_only`;
- expected signature: `frame` positional/keyword plus optional keyword-only
  `feature_columns`;
- required precondition: the residualized pair book behavior smoke is present
  and passing;
- excluded surfaces: formulas, exact score values, complete ordering, alpha
  quality, archived manifests, lab dispatch semantics, caller counts, pair
  book, relative-value spread, and source migration.

## Validation Matrix

For this docs-only dry-run:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

After the smoke gate is added:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -k residualized_pair -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

If a future import/signature-only contract is added:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -k residualized_pair -q
git diff --check
```

If formula behavior, feature construction, or lab dispatch changes, this F3-B2
boundary is insufficient; return to an owner-gated dry-run that includes the
affected runtime path.

## Next Gate

The next gate is the tiny residualized pair book behavior smoke. Only after it
passes should F3-B2 move to an owner-approved import/signature-only contract.
