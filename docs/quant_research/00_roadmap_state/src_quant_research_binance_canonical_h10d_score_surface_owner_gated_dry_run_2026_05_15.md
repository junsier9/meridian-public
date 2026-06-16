# src quant_research binance_canonical_h10d score surface owner-gated dry-run

`Status: owner-gated dry-run baseline`
`Date: 2026-05-15`
`Scope: score_binance_ohlcv_core / build_feature_manifest / alpha feature purity`

## Decision

Do not move `score_binance_ohlcv_core(...)`, `build_feature_manifest(...)`,
`validate_alpha_feature_columns(...)`, or the root alpha feature constants in
this automation pass.

The remaining score-adjacent surface is not a low-risk utility slice. It joins
feature allowlisting, sidecar exclusion, feature-weight normalization, missing
feature gating, and the h10d score formula. Moving any one of these without a
broader scoring contract would create a misleading boundary.

## Caller Baseline

### `build_feature_manifest(...)`

Owns:

- feature column resolution from config;
- feature subset policy interpretation;
- alpha purity check against `ALLOWED_ALPHA_FEATURES` and
  `FORBIDDEN_ALPHA_PATTERNS`;
- feature-weight normalization;
- manifest hash payload construction;
- generated timestamp assignment.

### `score_binance_ohlcv_core(...)`

Owns:

- strict versus subset alpha feature purity enforcement;
- missing feature hard failure;
- feature-weight normalization;
- grouped timestamp z-score composition;
- final percentile-rank centering and `tanh` score transform.

### `prepare_scored_backtest_frame(...)`

Owns:

- feature purity and missing feature blockers;
- price-valid and feature-valid masks;
- universe-active gating;
- score assignment through `score_binance_ohlcv_core(...)`;
- decision eligibility and support-column retention.

## Evidence From Tests

Existing h10d tests already treat this as behavior-sensitive:

- `test_score_uses_only_allowed_feature_columns` proves sidecar columns do not
  affect the score.
- `test_prepare_scored_frame_drops_non_core_sidecar_columns` protects support
  column retention and sidecar exclusion.
- risk-brake tests protect that support columns are retained without entering
  alpha features.

These tests are behavior tests for the active h10d scoring surface, not just
import compatibility checks.

## Risk Classification

| surface | risk | decision | rationale |
| --- | --- | --- | --- |
| `ALLOWED_ALPHA_FEATURES` | high | keep root | Compatibility floor and active allowlist for h10d score purity. |
| `BINANCE_OHLCV_CORE_WEIGHTS` | high | keep root | Directly controls score composition and manifest hash payloads. |
| `validate_alpha_feature_columns(...)` | high | keep root | Fail-closed sidecar exclusion and missing-feature policy. |
| `build_feature_manifest(...)` | high | keep root | Binds feature subset policy, normalized weights, and manifest hash. |
| `score_binance_ohlcv_core(...)` | high | keep root | Active formula surface. |
| `prepare_scored_backtest_frame(...)` | high | keep root | Active gating surface before backtest/validation. |

## Explicit Deferred Surfaces

Do not move or change:

- `ALLOWED_ALPHA_FEATURES`;
- `BINANCE_OHLCV_CORE_WEIGHTS`;
- `FORBIDDEN_ALPHA_PATTERNS`;
- `validate_alpha_feature_columns(...)`;
- `assert_alpha_feature_purity(...)`;
- `assert_alpha_feature_subset_purity(...)`;
- `_allow_feature_subset(...)`;
- `build_feature_manifest(...)`;
- `score_binance_ohlcv_core(...)`;
- `prepare_scored_backtest_frame(...)`;
- `add_binance_ohlcv_core_features(...)`.

## Future Owner-Gated Path

A future score-surface refactor may proceed only after an owner-approved plan
defines:

- root facade compatibility requirements;
- exact scope of formula behavior to freeze;
- whether manifest hash identity must be frozen before movement;
- behavior tests for full score output on a tiny fixture;
- behavior tests for sidecar exclusion and subset policy;
- whether constants move into a registry or remain root-owned.

## Validation Commands

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_features_utility_helpers.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This dry-run baseline is indexed by
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- No score-surface source code is moved.
- No score formula, feature weight, or feature allowlist behavior changes.
- No artifact paths are staged or committed.
