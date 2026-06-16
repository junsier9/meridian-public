# src quant_research features.py Compatibility Dry-Run

`Status: read-only dry-run baseline`
`Scope: src/enhengclaw/quant_research/features.py external import surface`
`Date: 2026-05-14`
`Mode: documentation-only; no static contract approved`

This artifact records the current `features.py` compatibility surface before any
source split, facade extraction, or scorer migration. It intentionally does not
create a JSON static contract. The surface is too broad and too research-heavy
to freeze in one pass.

## Decision

Do not create a full `features.py` compatibility static contract yet.

Do not move, split, rename, or delete `src/enhengclaw/quant_research/features.py`
without a separate owner-approved implementation plan. The viable future path is
facade-first and family-by-family, not a whole-file contract.

This dry-run is only a map of the current external import surface.

## Scan Scope

AST scan scope:

- `scripts/**/*.py`
- `tests/**/*.py`
- module target: `enhengclaw.quant_research.features`

Observed shape:

| metric | count |
| --- | ---: |
| parse errors | 0 |
| direct import files | 39 |
| script direct import files | 32 |
| test direct import files | 7 |
| imported names | 72 |
| public scorer import names | 60 |
| private import names | 6 |
| builder/evaluator import names | 3 |
| public constants | 3 |
| module alias attribute access | 0 |
| module attribute assignments | 0 |
| `patch("enhengclaw.quant_research.features.*")` string targets | 0 |

Source shape:

| metric | count |
| --- | ---: |
| module-level functions | 186 |
| private functions | 34 |
| scorer-like functions | 151 |

Governance read: unlike `hypothesis_batch.py`, this is not a mutable-global or
monkey-patch surface. The risk is direct import compatibility across many
research scripts and tests.

## Directory Surface

| caller group | import files | governance read |
| --- | ---: | --- |
| `scripts/quant_research/alpha_stage0_quarantine/` | 17 | highest-risk; quarantined/stage0 research relies on current and historical scorer internals |
| `scripts/quant_research/` root evaluators | 8 | v5/v6 h10d AB and branch evaluator surface |
| `tests/` | 7 | coverage anchors; should not automatically become public API |
| `scripts/quant_research/report_writers/` | 2 | report writer utility/helper use |
| `scripts/quant_research/alpha_branch_reports/` | 1 | branch evidence writer |
| `scripts/quant_research/historical_h10d_diagnostics/` | 1 | historical diagnostic |
| `scripts/quant_research/m3_mf_spk_support/` | 1 | support evaluator |
| `scripts/quant_research/feature_panel_tools/` | 1 | label constant only |
| `scripts/quant_research/provider_diagnostics/` | 1 | label constant only |

## Private Import Surface

These names are already repo-local public-by-use, but they are not clean public
APIs. Treat them as migration shims until a narrower plan exists.

| imported private name | caller count | primary caller class | governance read |
| --- | ---: | --- | --- |
| `_xs_alpha_ontology_v5_h10d_base_raw_score` | 8 | `alpha_stage0_quarantine` | current-parent/stage0 coupling; owner-gated |
| `_xs_alpha_ontology_v6_h10d_spk_short_replacement_score` | 8 | `alpha_stage0_quarantine` plus one test | SP-K replacement coupling; owner-gated |
| `_xs_alpha_ontology_v6_h10d_base_raw_score` | 1 | v6 news-veto diagnostic | branch diagnostic; owner-gated |
| `_timestamp_percentile_rank` | 1 | M3.2 canonical-parent stage0 | utility-like but embedded in stage0 evidence |
| `_timestamp_zscore` | 1 | v6 news-veto diagnostic | utility-like but under-tested |
| `_safe_rolling_skew` | 1 | subday funding report writer | utility-like; candidate for future small contract |

Current observation: there are no external `features.NAME = ...` assignments
and no string patch targets against `features.py`.

## Public Scorer Surface

The public scorer import surface is large and mixed. It should be split by
research family before any contract.

High-frequency examples:

| scorer family / name | caller count | main caller class |
| --- | ---: | --- |
| `xs_alpha_ontology_v5_score` | 18 | `alpha_stage0_quarantine` |
| `xs_alpha_ontology_v6_h10d_score` | 8 | v6 h10d evaluators and diagnostics |
| `xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score` | 6 | v6 SP-K branch evaluators |
| `xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score` | 5 | SP-K stage0 and v5 evaluator |
| v6 MF01/SP-K/news-veto one-off scorers | 1-2 each | branch evaluator scripts |
| pair / relative-value / residualized scorers | tests-only | historical coverage anchors |
| v11 stablecoin flow scorers | tests-only | focused stablecoin score tests |
| M3.3 strict event-state scorer | tests-only | strict event-state scorer test |

Tests-only scorer imports are coverage anchors. They should not be treated as
approval to expose every historical scorer as a stable public API.

## Builder And Constant Surface

| imported name | caller count | governance read |
| --- | ---: | --- |
| `build_cross_sectional_feature_bundle` | 8 | central feature construction and branch-report dependency |
| `build_cross_sectional_features` | 1 | lab test construction path |
| `evaluate_no_future_leakage` | 1 | integrity test helper |
| `DEFAULT_LABEL_CONTRACT_ID` | 3 | label contract constant |
| `EXECUTION_ALIGNED_LABEL_CONTRACT_ID` | 1 | factor report card label constant |
| `PARTICIPATION_DRIFT_LABEL_CONTRACT_ID` | 1 | hypothesis-batch test constant |

The builder/label surface is more sensitive than scorer importability because
feature construction can merge sidecar panels based on available files. Any
future builder contract must explicitly prove sidecar provenance, label
contract behavior, and no-future-leakage boundaries.

## Not Approved

This dry-run does not approve:

- a full `features.py` JSON static contract;
- moving or splitting `features.py`;
- rewriting scorer formulas;
- removing private imports from stage0 or historical scripts;
- blessing all tests-only scorers as stable public APIs;
- changing feature-bundle sidecar merge behavior;
- changing label contract constants or target-label semantics;
- adding broad golden-value tests for every scorer family.

## Future Contract Path

Use staged contracts only after owner approval:

| phase | target | allowed scope | validation shape |
| --- | --- | --- | --- |
| F0 | this dry-run baseline | docs-only import map | static contract not applicable |
| F1 | utility helpers | `_safe_rolling_skew`, `_timestamp_percentile_rank`, `_timestamp_zscore` | import contract plus tiny synthetic Series/DataFrame behavior tests |
| F2 | raw scorer shims | v5/v6 private raw-score helpers | owner-gated; preserve importability, avoid formula freeze unless explicitly approved |
| F3 | scorer families | v5/v6/SP-K/v11/pair families in separate batches | family-specific import contract plus existing targeted tests |
| F4 | builders and labels | `build_cross_sectional_feature_bundle`, label constants, leakage helper | owner-gated; must prove sidecar provenance and label boundaries |

## Owner-Gated Boundaries

Owner approval is required before:

- changing any manifest-linked scorer dispatch path;
- changing `build_cross_sectional_feature_bundle` or sidecar merge behavior;
- changing `DEFAULT_LABEL_CONTRACT_ID` or execution-aligned label semantics;
- moving private raw-score helpers out of `features.py`;
- converting stage0/quarantine private imports into public API;
- removing a scorer used by tests without a replacement coverage plan;
- adding a whole-file `features.py` compatibility contract.

## Future Validation Matrix

If a future static contract is added without runtime changes:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```

If utility helpers are changed:

```powershell
python -m pytest tests\test_static_contracts.py tests\test_quant_research_integrity.py -q
```

Add a tiny focused utility test before changing `_safe_rolling_skew`,
`_timestamp_percentile_rank`, or `_timestamp_zscore`.

If scorer behavior changes, run only the affected family tests first:

```powershell
python -m pytest tests\test_quant_hypothesis_batch.py -q
python -m pytest tests\test_quant_m3_3_hype_chatter_gate_stage0.py tests\test_quant_m3_3_strict_event_state_scorer.py -q
python -m pytest tests\test_stablecoin_flow_interaction_scores.py -q
```

If builders, sidecars, labels, or leakage behavior change:

```powershell
python -m pytest tests\test_derivatives_quality.py tests\test_quant_research_lab.py tests\test_quant_research_integrity.py -q
```

## Next Gate

The next gate is not a contract. The next gate is owner review on whether the
small utility-helper subset deserves its own narrow compatibility contract. Keep
stage0 raw scorers and builder/label surfaces owner-gated until then.
