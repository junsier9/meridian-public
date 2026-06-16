# src quant_research binance_canonical_h10d remaining contract bucket matrix

`Status: read-only automation routing baseline`
`Date: 2026-05-16`
`Scope: remaining binance_canonical_h10d contract/status buckets after helper closures`

## Purpose

This artifact routes the next automated governance steps for
`src/enhengclaw/quant_research/binance_canonical_h10d.py` and its extracted
internal helper modules.

It is intentionally read-only. It does not approve source movement, contract
expansion, report payload snapshots, real artifact snapshots, or caller-count
freezes.

## Already Closed At Minimal-Contract Layer

| bucket | closure/status artifact | automation state |
| --- | --- | --- |
| artifact helpers | `src_quant_research_binance_canonical_h10d_artifact_helpers_bucket_closure_2026_05_16.md` | closed |
| backtest gap policy helpers | `src_quant_research_binance_canonical_h10d_backtest_gap_policy_bucket_closure_2026_05_16.md` | closed for selected gap-policy helpers only |
| funding facade | `src_quant_research_binance_canonical_h10d_funding_facade_bucket_closure_2026_05_16.md` | closed |
| PIT universe eligibility | `src_quant_research_binance_canonical_h10d_pit_universe_eligibility_bucket_closure_2026_05_16.md` | closed, including `_truthy_series(...)` as h10d-local eligibility semantics |
| reporting metric sanitation | `src_quant_research_binance_canonical_h10d_reporting_metric_sanitation_bucket_closure_2026_05_16.md` | closed |
| reporting render | `src_quant_research_binance_canonical_h10d_reporting_render_bucket_closure_2026_05_16.md` | closed |
| risk-brake behavior | `src_quant_research_binance_canonical_h10d_risk_brake_behavior_bucket_closure_2026_05_16.md` | closed at tiny behavior-contract layer only |
| score surface | `src_quant_research_binance_canonical_h10d_score_surface_bucket_closure_2026_05_16.md` | closed |

## Safe Closure Candidates For This Automation Batch

| bucket | existing protection | reason it is safe to close now | forbidden expansion |
| --- | --- | --- | --- |
| time/run metadata helpers | `time_run_metadata_post_extraction_review`, `run_metadata_helpers_contract`, `datetime_boundary_contract` | low-level internal helper modules already exist; contracts cover root-facade signatures and tiny samples; no path ownership or validation orchestration is being changed | exact clock values, output roots, validation payloads, funding/PIT/backtest behavior |
| identity/normalization helpers | `identity_normalization_post_extraction_review`, `hash_identity_contract`, `timestamp_normalization_helpers_contract` | low-level internal helper modules already exist; contracts cover root-facade signatures and tiny identity/normalization samples; no scorer formulas are being frozen | feature formulas, score outputs, full feature manifests, falsification metrics, generic utility extraction |

## Keep Owner-Gated Or Status-Only

| bucket | current state | reason automation should not close or move it now |
| --- | --- | --- |
| archive/data foundation and feature panel | dry-runs/plans exist for archive helpers, `aggregate_1m_klines(...)`, intraday settlement, and feature-panel surfaces | data-foundation semantics and archive path behavior are path-sensitive; close only after a dedicated data-foundation bucket review |
| partition boundary | contract exists for root-local partition helpers | root-local and path-sensitive; leave as root-local status unless a future boundary review explicitly approves a closure |
| config/provider entrypoints | signature contract exists | provider/config entrypoints are public-facing operational surfaces; keep root-stable, not auto-moved |
| validation orchestration | status artifact exists | `run_binance_canonical_validation(...)` and `write_validation_artifacts(...)` own paths, reports, funding sync, scoring, backtests, falsification, attribution, and final status |
| validation status / funding cost status | contracts exist and are documented by validation orchestration status | lower-level helpers are protected, but they stay under the orchestration boundary rather than becoming a new migration target |
| falsification and holdout | partial closure/status artifacts exist | stratified/decision-time helpers are protected, but suite orchestration, seeded splits, strata payloads, and cost-stress routing remain owner-gated |
| attribution / paper shadow | partial status exists | tiny helpers are protected, but attribution math, paper-shadow ledger schemas, and aggregation payloads remain owner-gated |
| ablation / rescore | owner-gated status exists | rescoring and ablation summaries are tied to score surface and artifact semantics; no automatic movement |
| `_run_backtest(...)` | contract exists | backtest metrics, period construction, execution ledger, and validation consumers remain too central for automatic closure expansion |

## Automation Decision

Proceed in this batch only with docs-only closure artifacts for:

1. time/run metadata helpers;
2. identity/normalization helpers.

Do not touch source, imports, configs, manifests, scripts, tests, or artifacts in
this routing batch.

## Validation Baseline

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py tests\test_quant_research_integrity.py -q
git diff --check
```

## Completion Criteria

- This routing artifact is indexed in
  `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`.
- Any follow-up closure artifacts stay docs-only.
- Owner-gated orchestration/path/data-foundation buckets remain deferred unless
  a future dry-run explicitly narrows the surface.
- Untracked `artifacts/quant_research/...` paths remain unstaged.
