# src quant_research binance_canonical_h10d score surface bucket closure

`Status: bucket closure baseline`
`Date: 2026-05-16`
`Scope: score_surface_and_feature_manifest root-surface bucket`

## Decision

The `score_surface_and_feature_manifest` bucket is closed at the current
minimal-contract layer.

The bucket now has:

- an owner-gated score-surface dry-run;
- a score-surface behavior contract covering root-facade importability,
  signatures, alpha allowlist, core weights, and tiny behavior samples;
- an assertion-helper contract covering `assert_alpha_feature_purity(...)`,
  `assert_alpha_feature_subset_purity(...)`, and `_allow_feature_subset(...)`;
- explicit exclusions for source movement, full score formula snapshots,
  exact generated timestamps, feature-manifest hash identity, dataset/backtest
  payloads, validation status, PIT behavior, risk-brake behavior, and caller
  counts.

No further score-surface automation should widen behavior coverage or move
source without a new owner-approved dry-run artifact.

## Covered Surfaces

| surface | governance state | current boundary |
| --- | --- | --- |
| `validate_alpha_feature_columns(...)` | covered by score-surface behavior contract | importability, signature, allowlist/forbidden-pattern samples, and strict/subset purity samples |
| `assert_alpha_feature_purity(...)` | covered by assertion-helper contract | importability, signature, and tiny raise/no-raise samples |
| `assert_alpha_feature_subset_purity(...)` | covered by assertion-helper contract | importability, signature, and tiny raise/no-raise samples |
| `_allow_feature_subset(...)` | covered by assertion-helper contract | importability, signature, and tiny boolean config samples |
| `build_feature_manifest(...)` | covered by score-surface behavior contract | importability, signature, selected pruned-subset fields, normalized weights, and purity status |
| `score_binance_ohlcv_core(...)` | covered by score-surface behavior contract | importability, signature, and one tiny timestamp-grouped score fixture |
| `prepare_scored_backtest_frame(...)` | covered by score-surface behavior contract and h10d behavior tests | importability, signature, and sidecar-exclusion/feature-gating behavior presence |

## Do Not Expand Automatically

Automation must not add the following without a fresh dry-run and owner
approval:

- source movement for this bucket;
- full score formula snapshots;
- broader golden score outputs beyond the tiny fixture;
- feature allowlist or weight edits;
- `feature_manifest_hash` identity freeze;
- exact `generated_at_utc` values;
- full dataset manifest schemas;
- backtest metrics or validation status;
- PIT universe or risk-brake behavior;
- `features.py` scorer formulas;
- caller-count contracts.

## Validation Baseline

Use the same validation set as the active score-surface contracts:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_quant_features_utility_helpers.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This closure document is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Score surface work is treated as governance-complete at the current
  minimal-contract layer.
- Future work starts from a new owner-gated artifact instead of silently
  widening existing score, assertion, backtest, PIT, or risk-brake contracts.
