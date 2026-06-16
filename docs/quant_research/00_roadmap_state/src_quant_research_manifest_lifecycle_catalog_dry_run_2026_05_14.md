# src quant_research Manifest Lifecycle Catalog Dry-Run

`Status: S2 read-only dry-run baseline`
`Scope: src/enhengclaw/quant_research root JSON manifests`
`Date: 2026-05-14`
`Mode: catalog design only; no manifest moves approved`

This dry-run records the root JSON manifest state after the source architecture
baseline and static-contract commits. It is intentionally not a cleanup batch:
root JSON files are path-sensitive, and several are referenced by runtime
constants, scripts, tests, config, or historical documentation.

## Executive Decision

S2 should create a lifecycle catalog and a catalog-completeness contract before
any manifest relocation. Do not move root JSON files in the next implementation
batch.

The important mismatch to model is:

- `hypothesis_batch.py` currently defaults to
  `cross_sectional_hypothesis_batch_manifest_v97.json`.
- `cross_sectional_hypothesis_batch_manifest_v83.json` remains a documented
  Phase 0 baseline/static-contract artifact and a path-sensitive historical
  anchor.

S2 must represent both facts. It must not "fix" the mismatch by moving either
manifest or by silently relabeling v83 as the current runtime default.

## Evidence

Read-only scans used for this dry-run:

```powershell
git status --short
Get-ChildItem .\src\enhengclaw\quant_research -File -Filter *.json | Sort-Object Name
rg -n "cross_sectional_hypothesis_batch_manifest_v9[0-9]|cross_sectional_hypothesis_batch_manifest_v100|cross_sectional_hypothesis_batch_manifest_v8[3-9]" src scripts tests config docs -g "*.py" -g "*.json" -g "*.md"
rg -n "HYPOTHESIS_BATCH_MANIFEST_PATH|DETERMINISTIC_STRATEGY_MANIFEST_PATH|THESIS_TASK_SEED_FILENAME|manifest_path" src\enhengclaw\quant_research scripts\quant_research tests config\quant_research docs\quant_research -g "*.py" -g "*.json" -g "*.md"
```

Key references:

- `src/enhengclaw/quant_research/hypothesis_batch.py` sets
  `HYPOTHESIS_BATCH_MANIFEST_PATH` to
  `cross_sectional_hypothesis_batch_manifest_v97.json`.
- `src/enhengclaw/quant_research/deterministic_core.py` loads
  `deterministic_strategy_manifest.json` next to the module.
- `src/enhengclaw/quant_research/governance.py` resolves
  `strategy_library_thesis_seed.json`.
- `config/quant_research/active_h10d_registry.json` hard-references the
  canonical h10d parent manifest.
- `config/quant_research/threshold_provenance.md` records that v97 is the
  active hypothesis batch pipeline for the v64 B-batch IC track.
- `src/enhengclaw/quant_research/manifests_archive/phase0_v1_v82/README.md`
  preserves v83 as a parent-directory Phase 0 baseline artifact and notes that
  v85-v88 may later move to a follow-up archive.

## Root JSON Lifecycle Draft

| file | observed metadata | proposed S2 class | move stance |
| --- | --- | --- | --- |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1.json` | lifecycle=`superseded`; enabled=false | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1_lsk3.json` | lifecycle=`active`; one-off runner default | runtime_path_sensitive | do not move |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1_lsk3_g.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1_lsk3_g_v2.json` | lifecycle=`active_alternative` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1_lsk3_g_v2_h10d.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v1_topk7.json` | lifecycle=`falsified`; enabled=false | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v2_lsk3.json` | lifecycle=`active_alternative` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v3_lsk3_g_v2.json` | lifecycle=`active_alternative` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v4_lsk3_g_v2.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_lsk3_g_v2.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_lsk3_g_v2_h10d.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_lsk3_g_v2_h10d.json` | lifecycle=`legacy_comparator` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_lsk3_g_v2_h10d.json` | lifecycle=`active`; active h10d registry target | runtime_path_sensitive | do not move |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_mf01_combo_replace_v1_h10d.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d.json` | lifecycle=`quarantined`; script-hardref candidate | runtime_path_sensitive | do not move |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v2.json` | lifecycle=`active_alternative` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v2_h10d.json` | lifecycle=`retired`; script-hardref candidate | runtime_path_sensitive | do not move |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v3_h10d.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_spk_short_replace_mid_v1_h10d.json` | lifecycle=`research_only` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v7_lsk3_g_v2.json` | lifecycle=`active_alternative` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v8_lsk3_g_v2.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v8_lsk3_g_v2_h10d.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v9_lsk3_g_v2_h10d.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v10_regime_conditional_lsk3_g_v2_h10d.json` | lifecycle=`experimental` | recent_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_r1a_top_liquidity_ex_trx_h10d.json` | lifecycle=`quarantined`; Coinglass quarantine runner target | runtime_path_sensitive | do not move |
| `cross_sectional_hypothesis_batch_manifest_v83.json` | no lifecycle field; Phase 0 documented baseline | documented_static_baseline | do not move |
| `cross_sectional_hypothesis_batch_manifest_v85.json` | no lifecycle field; post-v83 disproved candidate | historical_archive_candidate | owner-gated dry-run only |
| `cross_sectional_hypothesis_batch_manifest_v86.json` | no lifecycle field; post-v83 disproved candidate | historical_archive_candidate | owner-gated dry-run only |
| `cross_sectional_hypothesis_batch_manifest_v87.json` | no lifecycle field; post-v83 disproved candidate | historical_archive_candidate | owner-gated dry-run only |
| `cross_sectional_hypothesis_batch_manifest_v88.json` | no lifecycle field; post-v83 disproved candidate | historical_archive_candidate | owner-gated dry-run only |
| `cross_sectional_hypothesis_batch_manifest_v89.json` | no lifecycle field | unknown_pending_owner | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v90.json` | no lifecycle field | unknown_pending_owner | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v91.json` | no lifecycle field; mechanism docs reference predecessor/active 9-factor | documented_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v92.json` | no lifecycle field; threshold provenance notes v92-v99 B-batch collision | b_batch_ic_extension_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v93.json` | no lifecycle field; v92-v99 B-batch range | b_batch_ic_extension_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v94.json` | no lifecycle field; v92-v99 B-batch range | b_batch_ic_extension_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v95.json` | no lifecycle field; v92-v99 B-batch range | b_batch_ic_extension_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v96.json` | no lifecycle field; v92-v99 B-batch range | b_batch_ic_extension_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v97.json` | no lifecycle field; current `hypothesis_batch.py` default | active_runtime_loaded | do not move |
| `cross_sectional_hypothesis_batch_manifest_v98.json` | no lifecycle field; v92-v99 B-batch range | b_batch_ic_extension_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v99.json` | no lifecycle field; v92-v99 B-batch range; script-path docs reference | b_batch_ic_extension_evidence | catalog-only |
| `cross_sectional_hypothesis_batch_manifest_v100.json` | no lifecycle field | unknown_pending_owner | catalog-only |
| `deterministic_strategy_manifest.json` | contract_version=`quant_deterministic_strategy_manifest.v1` | active_runtime_loaded | do not move |
| `strategy_library_thesis_seed.json` | governance seed source | source_truth | do not move |

## Static Contract Shape

The next implementation should add a catalog-completeness contract with these
rules:

- every root `*.json` under `src/enhengclaw/quant_research` appears in the S2
  catalog exactly once;
- catalog entries use a small allowed set of lifecycle classes;
- active/runtime-loaded entries resolve from the current code/config paths;
- hard-referenced entries are not classified as archive-move candidates;
- `unknown_pending_owner` is allowed but must be cataloged and must not be in a
  move allowlist.

The contract should compare the catalog to the discovered root JSON list. It
should not hard-code a fixed total count as the primary assertion.

## Not Approved

This dry-run does not approve:

- moving any root JSON manifest;
- changing `HYPOTHESIS_BATCH_MANIFEST_PATH`;
- changing `DETERMINISTIC_STRATEGY_MANIFEST_PATH`;
- changing thesis seed loading in `governance.py`;
- editing manifest payloads to add lifecycle fields;
- relabeling v83 as current runtime default;
- relabeling v97 as the Phase 0 baseline.

## Recommended S2 Implementation

1. Add a small checked-in catalog, preferably under
   `config/quant_research/`, that lists the 44 current root JSON files and their
   S2 lifecycle class.
2. Add a focused static contract to `tests/test_static_contracts.py` that checks
   catalog completeness and loader-protected path classes.
3. Update this dry-run or the architecture plan only if the catalog format
   intentionally diverges from this proposal.
4. Do not move manifests in the S2 implementation commit.

## Verification Matrix

Minimum S2 verification:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_hypothesis_batch.py::QuantHypothesisBatchTests::test_manifest_loads_all_expected_candidates -q
python -m pytest tests\test_quant_research_core.py::DeterministicQuantCoreTests::test_deterministic_manifest_entries_have_non_empty_thesis_profiles -q
python -m pytest tests\test_quant_research_governance.py::QuantResearchGovernanceTests::test_thesis_seed_state_is_preserved_across_library_ensure -q
git diff --check
git status --short
```

If the implementation changes source files, loader constants, script wrappers,
or scheduled/config paths, this dry-run is no longer sufficient and the change
must return to owner-gated review.
