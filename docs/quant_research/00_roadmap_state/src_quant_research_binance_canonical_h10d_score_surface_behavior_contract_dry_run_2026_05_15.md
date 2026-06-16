# src quant_research binance_canonical_h10d score surface behavior contract dry-run

`Status: owner-gated behavior-contract dry-run`
`Date: 2026-05-15`
`Scope: ALLOWED_ALPHA_FEATURES / feature purity / score surface tiny behavior samples`

## Decision

Approve a minimal behavior contract for the active Binance-canonical h10d score
surface, but do not move source code in this batch.

The prior owner-gated dry-run kept `validate_alpha_feature_columns(...)`,
`build_feature_manifest(...)`, `score_binance_ohlcv_core(...)`,
`prepare_scored_backtest_frame(...)`, `ALLOWED_ALPHA_FEATURES`, and
`BINANCE_OHLCV_CORE_WEIGHTS` at the package root. This follow-up narrows the
next automated step to a static/behavior contract that protects current caller
expectations before any future facade-first split.

## Contract Candidate

The smallest approved contract should freeze:

- root-facade importability and signatures for
  `validate_alpha_feature_columns(...)`, `build_feature_manifest(...)`,
  `score_binance_ohlcv_core(...)`, and `prepare_scored_backtest_frame(...)`;
- the current `ALLOWED_ALPHA_FEATURES` tuple;
- the current `BINANCE_OHLCV_CORE_WEIGHTS` mapping;
- `validate_alpha_feature_columns(...)` behavior for a forbidden sidecar column;
- strict versus subset feature-purity behavior for a pruned feature list;
- `score_binance_ohlcv_core(...)` output on one tiny timestamp-grouped fixture;
- score invariance when the fixture includes an ignored non-core sidecar column;
- selected `build_feature_manifest(...)` fields for an allowed pruned subset,
  especially normalized weights and purity status.

## Explicit Non-Goals

The contract must not freeze:

- source migration or internal module layout;
- full score formula behavior beyond the tiny fixture;
- broader alpha feature admission behavior;
- exact `generated_at_utc` values;
- `feature_manifest_hash` identity;
- full dataset, backtest, validation, or funding behavior;
- PIT universe behavior or risk-brake behavior;
- caller counts;
- `features.py` scorer formulas or helper behavior.

## Fixture Shape

Use a six-row, two-timestamp, three-subject fixture with all
`ALLOWED_ALPHA_FEATURES` populated by deterministic numeric offsets. The fixture
is intentionally small enough for static-contract tests and is not a replacement
for `tests/test_binance_canonical_h10d.py`.

Expected score sample from the current implementation:

```text
[0.716297870199, 0.291312612452, -0.291312612452,
 -0.291312612452, 0.291312612452, 0.716297870199]
```

The behavior sample should also add
`coinglass_top_trader_long_pct_smooth_5` as a non-core sidecar column and assert
that score output remains unchanged.

## Manifest Sample Boundary

The manifest sample should use a two-feature pruned subset with
`feature_subset_policy.allow_pruned_subset = true` and raw weights `-2.0` and
`1.0`. The contract may assert normalized weights of `-0.6666666666666666` and
`0.3333333333333333`, selected labels, allowed sources, and
`purity_check.passed = true`.

Do not assert the exact `generated_at_utc` timestamp or the
`feature_manifest_hash` in the first behavior contract. Hash identity can be
considered later only if a source move or manifest-loader refactor requires it.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_features_utility_helpers.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- The follow-up implementation, if performed, touches only a contract JSON and
  `tests/test_static_contracts.py`.
- No `src/enhengclaw/quant_research` files move or change.
- No checked-in artifact paths are staged.
