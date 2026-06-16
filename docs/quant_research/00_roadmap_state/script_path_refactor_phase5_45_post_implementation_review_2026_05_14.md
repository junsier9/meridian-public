# Phase 5.45 Alpha Ontology Cycles Post-Implementation Review

`Status: post-implementation review baseline`
`Date: 2026-05-14`
`Scope: alpha_ontology_cycles/ migration and remaining owner-gated root boundary`

## Decision

Phase 5.45 did not create a script-path or document-governance blocker.

The two one-off alpha-ontology cycle runner implementations now belong under
`scripts/quant_research/alpha_ontology_cycles/`, with root compatibility
wrappers retained. The directory remains narrow: it is for non-default
alpha-ontology one-off hypothesis-batch cycle runners that locally override
manifest, horizon, candidate, or validation-contract constants.

This review does not approve moving `compute_alpha_ontology_v3_weights.py`.
That script remains a root/deferred config-materializer surface and would need
a separate owner-approved dry-run before any path change.

## Wrapper Review

| root wrapper | verdict | reason |
| --- | --- | --- |
| `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py` | keep | Thin wrapper with required module-compatible re-export for `_patch_hypothesis_batch_for_variant`; needed by historical h10d audit callers. |
| `scripts/quant_research/run_alpha_ontology_v1_cycle_oneoff.py` | keep | Thin CLI wrapper that forwards to the moved implementation. |

Both wrappers should stay cataloged as `supporting` / `supporting_tool` /
`safe-to-move = no`. The moved implementations carry the real implementation
semantics.

## Catalog And README Review

- `quant_research_script_catalog.md` covers all 286 scripts and records
  `alpha_ontology_cycles = 2`.
- The root wrapper rows are compatibility surfaces, not quarantined
  falsification implementations.
- The moved v1 implementation remains historical/deprecated. The moved horizon
  runner remains a supporting one-off cycle implementation.
- `scripts/quant_research/README.md` and the reusable script-path checklist
  both describe `alpha_ontology_cycles/` as a narrow target directory.

## Remaining Root Boundary

The following are still deferred and must not be moved by autonomous cleanup:

- `compute_alpha_ontology_v3_weights.py`: root/deferred config materializer.
- Historical h10d dependent cluster:
  `evaluate_v6_h10d_post_pump_news_veto_ab.py`,
  `evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`, and
  `evaluate_v6_h10d_post_pump_short_replacement.py`.
- CoinGlass h10d-parent historical evidence trio.
- `factor_report_card.py`.
- Current h10d proof/guard/default surfaces, research-cycle default entrypoints,
  scheduled surfaces, and data-foundation default entrypoints.

These remaining roots are owner-gated. Any future movement needs a dedicated
dry-run, explicit target-directory admission rule, wrapper or import strategy,
and targeted verification.

## Repo-Level Doc Governance Follow-Up

The post-implementation doc audit found no orphaned `docs/quant_research`
Markdown. The remaining misleading surfaces were repo-level entrypoint docs:

- `PROJECT_STATE.md` still used an older `data_utilization_roadmap.md` first
  read order and old `active/current` language.
- `docs/README_FOR_AGENT.md` still described `docs/quant_research/` by old
  root-level file names rather than the current layered map.

These are low-risk doc-only fixes because they do not change research
conclusions, script behavior, configs, artifacts, or test contracts. They align
the first screen of repo onboarding with the already-indexed quant-research
governance structure.

## Verification

Required after this review and the repo-level doc follow-up:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run a local Markdown-link scan when docs change.

## Next Allowed Action

Stop autonomous script movement at the current owner-gated boundary. The next
safe automation target is documentation consistency only: keep repo-level
entrypoints, the script catalog, and the governance index aligned with the
current roadmap.
