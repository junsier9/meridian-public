# src quant_research Pair-Construction Contract Dry-Run

`Status: read-only docs-only dry-run baseline`
`Scope: hypothesis_batch pair normalization, execution quality_bucket_pairs, frozen pair benchmark`
`Date: 2026-05-15`
`Mode: documentation-only; no static contract, no code change, no manifest move approved`

This artifact follows the F3-B scorer-family contract series. The prior
F3-B1/B2/B3a/B3b contracts intentionally freeze only scorer importability and
`inspect.signature` shape. This dry-run separates the remaining pair
construction surfaces so they are not accidentally pulled into scorer-family
contracts.

## Decision

Do not write one combined pair-construction contract.

Split the surface into three independently testable boundaries:

1. `hypothesis_batch.py` profile normalization for pair-book model families.
2. `execution_backtest.py` `quality_bucket_pairs` target-weight construction.
3. frozen benchmark metadata for `xs_pair_spread_book_v8_h5d`.

Recommended order:

1. Add a small `hypothesis_batch` normalization behavior contract first.
2. Leave `execution_backtest.py` under its existing behavior tests unless a
   future refactor touches target-weight construction.
3. Keep frozen benchmark contract owner-gated until the `v35` path semantics
   are clarified, because the constant points to a root path while the checked
   in `v35` manifest currently lives in `manifests_archive/phase0_v1_v82/`.

## Boundary 1: hypothesis_batch Normalization

Primary source:

- `src/enhengclaw/quant_research/hypothesis_batch.py:349`

Current behavior:

- recognizes pair-book model families `xs_pair_spread_book_v1-v12` and
  `xs_pair_spread_book_v16-v24`;
- normalizes `pair_construction`, `pair_bucket_count`, `pair_count`,
  `pair_score_spread_min`, and `pair_quality_floor`;
- preserves optional stability and turnover parameters such as
  `pair_turnover_mode`, `pair_trend_crowding_soft_scale`,
  `pair_short_trend_crowding_soft_scale`, `pair_quality_balance_soft_scale`,
  `pair_switch_strength_ratio_min`, and related caps;
- requires the pair-book execution shape to remain short-enabled perp
  construction with `pair_construction = "quality_bucket_pairs"`;
- rejects out-of-range values for pair count, pair spread, pair quality, pair
  turnover mode, trend/quality soft scales, and switch strength ratio.

Current coverage:

- `tests/test_quant_hypothesis_batch.py::QuantHypothesisBatchTests::test_pair_book_profile_constraints_reject_out_of_range_stability_constraints`

Coverage gaps:

- no positive round-trip test currently asserts that a valid pair-book profile
  normalizes the required execution fields and preserves the optional
  pair-construction keys;
- no explicit test freezes the pair-book model-family allowlist independently
  from the scorer-family contracts.

Testing decision:

- **Yes, test next.**
- Add one focused behavior test for a valid `xs_pair_spread_book_v8_h5d`
  profile, asserting only normalized keys, expected execution shape, accepted
  value ranges, and optional-key preservation.
- Do not freeze the whole normalization function, every error message, or every
  formula-level scorer family.

Future contract shape:

- scope: pair-book profile normalization only;
- validation mode: behavior/static hybrid;
- required target: `_normalize_profile_constraints`;
- explicitly excluded: scorer formulas, scorer signatures, execution weight
  selection, lab dispatch, archived manifests, frozen benchmark path
  semantics, and caller counts.

## Boundary 2: execution_backtest quality_bucket_pairs

Primary sources:

- `src/enhengclaw/quant_research/execution_backtest.py:690`
- `src/enhengclaw/quant_research/execution_backtest.py:773`

Current behavior:

- routes `pair_construction = "quality_bucket_pairs"` into
  `_cross_sectional_pair_target_weights`;
- selects long/short pairs inside quality buckets;
- enforces pair count, score spread, quality floor, non-overlapping subjects,
  long/short leverage split, and optional pair-strength/quality/trend soft
  scales;
- supports pair-switch buffering through previous weights;
- uses execution inputs such as `score`, `relative_strength_20`,
  `ema_slope_5_20`, `distance_to_low_20`, `intraday_realized_vol_4h_to_1d`,
  and `realized_volatility_20`.

Current coverage:

- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_constructs_pairs_within_quality_buckets`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_cap_pair_strength`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_scale_trend_crowded_pairs`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_soft_scale_low_quality_balance_pair`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_require_strong_second_pair`
- `tests/test_execution_backtest.py::ExecutionBacktestTests::test_cross_sectional_target_weights_can_buffer_pair_switches`
- plus pair turnover tests around `exit_first`, `pair_hold`, and
  `pair_project`.

Testing decision:

- **Not first.**
- Existing behavior coverage is already richer than the static scorer
  contracts. Do not introduce a large JSON contract yet.
- If target-weight construction is refactored later, add a narrow contract that
  freezes supported `pair_construction` routing and high-level invariants only:
  signs, non-overlap, leverage budget, pair count, and switch-buffer behavior.

Explicit non-goals:

- do not freeze exact floating weights beyond existing tests;
- do not freeze ranking formulas used to form quality buckets;
- do not couple execution pair construction to scorer import/signature
  contracts.

## Boundary 3: Frozen Benchmark

Primary source:

- `src/enhengclaw/quant_research/hypothesis_batch.py:60`

Current metadata:

```python
FROZEN_BENCHMARK_MANIFEST_PATH = Path(__file__).with_name("cross_sectional_hypothesis_batch_manifest_v35.json")
FROZEN_BENCHMARK_SOURCE = "hypothesis_batch_manifest_v35"
FROZEN_BENCHMARK_CANDIDATE_IDS = ("xs_pair_spread_book_v8_h5d",)
```

Dry-run finding:

- `cross_sectional_hypothesis_batch_manifest_v35.json` is not currently present
  at `src/enhengclaw/quant_research/`;
- the checked-in `v35` manifest was found under
  `src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/`;
- no direct loader or test reference to `FROZEN_BENCHMARK_*` was found during
  this dry-run beyond the constants themselves.

Testing decision:

- **Owner-gated.**
- Do not add a test that requires the current root `v35` path to exist until
  the owner decides whether the frozen benchmark should be restored to package
  root, redirected to archive, or treated as stale metadata.
- The first safe test should freeze only the intended benchmark identity:
  `FROZEN_BENCHMARK_SOURCE = "hypothesis_batch_manifest_v35"` and
  `FROZEN_BENCHMARK_CANDIDATE_IDS = ("xs_pair_spread_book_v8_h5d",)`.
- A path-existence assertion needs a separate owner decision.

Explicit non-goals:

- do not move or copy archived manifests in this phase;
- do not reactivate archived `v35`;
- do not change active hypothesis-batch manifest loading;
- do not interpret frozen benchmark identity as promotion approval.

## Contract Boundary Matrix

| boundary | current risk | existing tests | next action |
| --- | --- | --- | --- |
| `hypothesis_batch` normalization | medium | negative validation coverage | add small positive behavior contract |
| execution `quality_bucket_pairs` | medium/high | broad behavior coverage | defer new contract unless refactor starts |
| frozen benchmark constants | medium | no direct tests found | owner-gated identity/path decision first |

## Explicitly Out Of Scope

This dry-run does not approve:

- changes to scorer-family contracts F3-B1/B2/B3a/B3b;
- moving or splitting `features.py`, `hypothesis_batch.py`, or
  `execution_backtest.py`;
- freezing scorer formulas, exact scores, complete ordering, alpha quality, or
  promotion status;
- freezing `lab.py` model-family or scoring-family dispatch;
- moving, copying, restoring, or reactivating archived manifests;
- changing active manifest loader behavior;
- changing `quality_bucket_pairs` target-weight formulas;
- changing `xs_pair_spread_book_v8_h5d` frozen benchmark semantics without
  owner approval.

## Validation Matrix

For this docs-only dry-run:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -k pair_book -q
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
git diff --check
```

Before a future hypothesis-batch normalization contract:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -k pair_book -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Before a future execution pair-construction contract:

```powershell
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
git diff --check
```

Before a future frozen benchmark contract:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Next Gate

The next gate is a small `hypothesis_batch` normalization behavior test. It
should prove that a valid pair-book profile normalizes into the required
`quality_bucket_pairs` execution shape and preserves optional pair constraints.
Do not touch the frozen benchmark path until owner review decides whether the
root `v35` pointer is intentional, stale, or should be redirected.
