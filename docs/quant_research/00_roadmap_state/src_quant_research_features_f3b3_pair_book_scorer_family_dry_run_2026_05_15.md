# src quant_research features.py F3-B3 Pair Book Scorer-Family Dry-Run

`Status: read-only docs-only dry-run baseline`
`Scope: src/enhengclaw/quant_research/features.py F3-B3 pair_book scorer family`
`Date: 2026-05-15`
`Mode: documentation-only; no static contract, no code change, no source migration approved`

This artifact records the F3-B3 slice of the broader
`pair_relative_residualized` scorer surface. It intentionally separates pair
book scorer import/signature stability from hypothesis-batch pair construction,
execution `quality_bucket_pairs`, archived manifests, and `lab.py` dispatch.

## Decision

Do not freeze the entire pair-book surface in one contract.

The pair-book family must be split into four boundaries:

1. F3-B3a `v1-v12`: eligible for a future importability/signature-only
   contract after this docs baseline, because the names are runtime scorers and
   have direct behavior coverage in `tests/test_quant_hypothesis_batch.py`.
2. F3-B3b `v16-v24`: alias-only runtime scorers that currently dispatch to
   `v8`; keep owner-gated until a tiny alias smoke or separate
   import/signature-only decision exists.
3. Deferred `v13-v15`: archive-only manifest references with no runtime scorer
   definitions; do not include them in a runtime scorer contract.
4. Separate pair-construction surfaces: `hypothesis_batch.py`,
   `execution_backtest.py`, and `lab.py` dispatch are compatibility-sensitive
   but must not be frozen as a side effect of a scorer-family contract.

The first possible contract should therefore target only `v1-v12`, and should
remain import/signature only. It must not freeze formula outputs, exact scores,
complete ordering, alpha quality, `quality_bucket_pairs`, lab dispatch,
archived manifests, caller counts, or source migration.

## Boundary 1: F3-B3a v1-v12 Runtime Scorers

| scorer | source line | implementation shape | current behavior coverage |
| --- | ---: | --- | --- |
| `xs_pair_spread_book_v1_score` | `features.py:5580` | formula scorer | direct behavior call |
| `xs_pair_spread_book_v2_score` | `features.py:5674` | inverse of `v1` | direct behavior call |
| `xs_pair_spread_book_v3_score` | `features.py:5682` | formula variant using `v2` | direct behavior call |
| `xs_pair_spread_book_v4_score` | `features.py:5731` | formula variant using `v3` | direct behavior call |
| `xs_pair_spread_book_v5_score` | `features.py:5785` | formula variant using `v3` | direct behavior call |
| `xs_pair_spread_book_v6_score` | `features.py:5838` | formula variant using `v3` | direct behavior call |
| `xs_pair_spread_book_v7_score` | `features.py:5900` | formula variant using `v3` | direct behavior call |
| `xs_pair_spread_book_v8_score` | `features.py:5952` | formula variant using `v3` | direct behavior call |
| `xs_pair_spread_book_v9_score` | `features.py:6004` | formula variant using `v8` | direct behavior call |
| `xs_pair_spread_book_v10_score` | `features.py:6066` | `v8` alias | direct behavior call |
| `xs_pair_spread_book_v11_score` | `features.py:6074` | `v8` alias | direct behavior call |
| `xs_pair_spread_book_v12_score` | `features.py:6082` | `v8` alias | direct behavior call |

All twelve scorer signatures currently use:

```python
def scorer(frame: pd.DataFrame, *, feature_columns: Iterable[str] | None = None) -> pd.Series
```

`tests/test_quant_hypothesis_batch.py` calls `v1-v12` in the pair-book behavior
test. The test checks several narrow relationships, including `v2 == -v1`,
formula-family distinctness, positive cheap-quality row scores, `v9` distinct
from `v8`, and `v10-v12 == v8`.

Contract implication: `v1-v12` are reasonable candidates for a future
import/signature-only contract, but not for formula or golden-output freezing.

## Boundary 2: F3-B3b v16-v24 Alias-Only Runtime Scorers

| scorer | source line | implementation shape | current behavior coverage |
| --- | ---: | --- | --- |
| `xs_pair_spread_book_v16_score` | `features.py:6090` | `v8` alias | imported but not directly called |
| `xs_pair_spread_book_v17_score` | `features.py:6098` | `v8` alias | no direct behavior test found |
| `xs_pair_spread_book_v18_score` | `features.py:6106` | `v8` alias | no direct behavior test found |
| `xs_pair_spread_book_v19_score` | `features.py:6114` | `v8` alias | no direct behavior test found |
| `xs_pair_spread_book_v20_score` | `features.py:6122` | `v8` alias | no direct behavior test found |
| `xs_pair_spread_book_v21_score` | `features.py:6130` | `v8` alias | no direct behavior test found |
| `xs_pair_spread_book_v22_score` | `features.py:6138` | `v8` alias | no direct behavior test found |
| `xs_pair_spread_book_v23_score` | `features.py:6146` | `v8` alias | no direct behavior test found |
| `xs_pair_spread_book_v24_score` | `features.py:6154` | `v8` alias | no direct behavior test found |

`lab.py` imports and dispatches these names, and archived manifests reference
them. `tests/test_quant_hypothesis_batch.py` imports `v16`, but the focused AST
read found direct calls only for `v1-v12`.

Contract implication: do not bundle `v16-v24` into the first F3-B3 contract.
Either add a tiny alias smoke first, or write a separate owner-gated
import/signature-only contract that clearly labels them as alias-only with no
behavior coverage.

## Boundary 3: Deferred v13-v15 Archive-Only References

Archived manifests reference `xs_pair_spread_book_v13`,
`xs_pair_spread_book_v14`, and `xs_pair_spread_book_v15`, but no corresponding
runtime scorer definitions were found in `features.py`.

| archived model family | reference location | runtime scorer status |
| --- | --- | --- |
| `xs_pair_spread_book_v13` | archived manifest v40 | no runtime scorer |
| `xs_pair_spread_book_v14` | archived manifest v41 | no runtime scorer |
| `xs_pair_spread_book_v15` | archived manifest v42 | no runtime scorer |

Contract implication: permanently exclude `v13-v15` from runtime scorer
contracts unless a future owner-approved compatibility bridge is explicitly
designed. Their status belongs to manifest lifecycle/archive governance, not
current runtime scorer importability.

## Boundary 4: Separate Pair-Construction And Dispatch Surfaces

F3-B3 has three important non-scorer surfaces:

| surface | source line | why separate |
| --- | ---: | --- |
| pair-book profile normalization | `hypothesis_batch.py:349` | special allowlist for `v1-v12/v16-v24`, required `quality_bucket_pairs`, pair-count and pair-quality constraints |
| frozen benchmark pointer | `hypothesis_batch.py:62` | `xs_pair_spread_book_v8_h5d` is the frozen benchmark candidate |
| execution pair construction | `execution_backtest.py:691` | `quality_bucket_pairs` routes into pair target-weight construction |
| lab model-family dispatch | `lab.py:6378` | runtime scoring path for `model_family` values |
| lab scoring-family dispatch | `lab.py:6736` | runtime scoring path for `scoring_family` values |

These surfaces may deserve future contracts, but they must be separate from a
scorer import/signature contract. Freezing a scorer name must not silently
freeze pair construction, execution target weights, benchmark status, or lab
registry behavior.

## Existing Coverage

Focused verification from the dry-run:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -k "pair_book or pair_spread_book" -q
```

Observed result: `3 passed, 26 deselected`.

This covers pair-book scorer behavior for `v1-v12` plus hypothesis-batch
profile constraint rejection.

```powershell
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
```

Observed result: `9 passed, 15 deselected`.

This covers execution-level pair construction behavior. It is related evidence,
not permission to include execution pair construction in a scorer-family
contract.

No direct script imports of `xs_pair_spread_book_v*_score` were found under
`scripts/**/*.py` during this dry-run.

## Explicitly Out Of Scope

This dry-run does not approve:

- a full `features.py` scorer-family contract;
- a combined `pair_relative_residualized` contract;
- moving or splitting `features.py`;
- freezing formula output, exact scores, complete score ordering, alpha
  quality, promotion status, or frozen benchmark status;
- freezing `hypothesis_batch.py` pair-construction normalization;
- freezing `execution_backtest.py` `quality_bucket_pairs` target-weight logic;
- freezing `lab.py` model-family or scoring-family dispatch;
- freezing archived manifest lifecycle semantics;
- including `v13-v15` runtime targets;
- including `v16-v24` in the first F3-B3 contract;
- including residualized pair book or relative-value spread scorers;
- changing `_feature_series`, `_timestamp_percentile_rank`, or
  `_timestamp_zscore`;
- source migration.

## Future Contract Shape

If owner-approved, the first F3-B3 contract should be import/signature only:

- source module: `enhengclaw.quant_research.features`;
- target names: `xs_pair_spread_book_v1_score` through
  `xs_pair_spread_book_v12_score`;
- validation mode: `importability_signature_only`;
- expected signature: `frame` positional/keyword plus optional keyword-only
  `feature_columns`;
- required precondition: pair-book focused tests continue to pass;
- excluded surfaces: formulas, exact score values, complete ordering, alpha
  quality, frozen benchmark status, archived manifests, lab dispatch semantics,
  pair-construction normalization, execution target-weight logic, caller
  counts, alias-only `v16-v24`, archive-only `v13-v15`, and source migration.

Do not include `v16-v24` unless a separate alias-only gate is approved. Do not
include `v13-v15` unless a future compatibility bridge exists.

## Validation Matrix

For this docs-only dry-run:

```powershell
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Before a future F3-B3a `v1-v12` contract:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -k "pair_book or pair_spread_book" -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Before any separate pair-construction contract:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -k pair_book -q
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
git diff --check
```

If formula behavior, execution weights, benchmark handling, archived manifests,
or lab dispatch changes, this F3-B3 scorer boundary is insufficient; return to
an owner-gated dry-run for the affected runtime path.

## Next Gate

The next gate is an owner decision on the narrow F3-B3a contract:

- recommended: implement an import/signature-only contract for `v1-v12`;
- defer: `v16-v24` alias-only targets until an alias smoke or separate owner
  gate exists;
- permanently exclude from runtime contract: archive-only `v13-v15`;
- keep separate: hypothesis-batch pair construction, execution
  `quality_bucket_pairs`, and `lab.py` dispatch.
