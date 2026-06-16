# src quant_research binance_canonical_h10d assertion helpers behavior dry-run

`Status: owner-gated tiny behavior dry-run`
`Date: 2026-05-15`
`Scope: assert_alpha_feature_purity / assert_alpha_feature_subset_purity / _allow_feature_subset`

## Decision

Approve a tiny behavior contract for the assertion-helper portion of the
`score_surface_and_feature_manifest` bucket.

Do not move source and do not expand the existing score-surface formula
contract.

Covered root-defined functions:

- `assert_alpha_feature_purity`
- `assert_alpha_feature_subset_purity`
- `_allow_feature_subset`

## Current Boundary

`validate_alpha_feature_columns(...)` is already governed by
`config/quant_research/src_quant_research_binance_canonical_h10d_score_surface_behavior_contract.json`.

The assertion helpers are thin wrappers around that validator:

- `assert_alpha_feature_purity(...)` should raise when the strict all-feature
  purity check fails.
- `assert_alpha_feature_subset_purity(...)` should allow missing allowed
  features but still raise for forbidden or unexpected columns.
- `_allow_feature_subset(...)` should read only
  `config["feature_subset_policy"]["allow_pruned_subset"]` as a boolean.

## Approved Contract Shape

Allowed:

- assert root-facade importability;
- assert root-level symbols exist in `binance_canonical_h10d.py`;
- assert `inspect.signature` for the three helpers;
- assert the root-surface classification contract still assigns them to
  `score_surface_and_feature_manifest`;
- assert the existing score-surface contract still owns
  `validate_alpha_feature_columns(...)`;
- run tiny no-raise / raise samples for the two assertion helpers;
- run tiny boolean samples for `_allow_feature_subset(...)`.

Not allowed:

- freezing scorer formulas;
- freezing full score output snapshots;
- freezing feature weights beyond the existing score-surface contract;
- changing or freezing full `default_strategy_config()` contents;
- changing source placement;
- adding broad behavior around `build_feature_manifest(...)`,
  `score_binance_ohlcv_core(...)`, or `prepare_scored_backtest_frame(...)`.

## Deferred / Owner-Gated

Fresh dry-run required before:

- moving any feature purity helper out of `binance_canonical_h10d.py`;
- changing the allow-list or forbidden source patterns;
- broadening the score-surface contract beyond tiny fixtures;
- introducing formula golden outputs;
- merging this surface with `features.py` scorer contracts.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- A later implementation commit, if added, contains only contract JSON plus
  `tests/test_static_contracts.py`.
- No production source moves in this dry-run batch.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
