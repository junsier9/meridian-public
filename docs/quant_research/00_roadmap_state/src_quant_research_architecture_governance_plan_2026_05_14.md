# src/enhengclaw/quant_research Architecture Governance Plan

`Status: governance baseline plan`
`Scope: src/enhengclaw/quant_research architecture, public surfaces, manifests, and compatibility boundaries`
`Date: 2026-05-14`
`Mode: documentation-only baseline; no source moves in this batch`

This plan records the architecture baseline for `src/enhengclaw/quant_research`
after the script-path governance series. It does not change research
conclusions, imports, manifest loading, wrappers, or runtime behavior. Its
purpose is to prevent source-package cleanup from accidentally breaking public
surfaces that are already used by scripts and tests.

## Current Package Shape

`src/enhengclaw/quant_research` is still a mostly flat package:

| area | count / state | governance read |
| --- | ---: | --- |
| non-pycache source files | 204 | large source surface; not a simple cleanup target |
| Python modules | 79 | many modules are directly imported by scripts and tests |
| JSON files | 124 | package root contains runtime and evidence manifests |
| root JSON files | 44 | do not move without loader and caller review |
| archived manifest JSON files | 80 | immutable Phase 0 historical record under `manifests_archive/phase0_v1_v82/` |

The only durable package subdirectory today is `manifests_archive/`. That
archive is intentional: its README states that v1 through v82 are not loaded by
runtime. Root manifests remain in the package root for lifecycle-specific
reasons: v97 is the current `hypothesis_batch.py` runtime default; v83 is the
Phase 0 documented baseline/static historical anchor; other root manifests are
retained as evidence, retired, quarantined, or cataloged artifacts. Moving any
of them requires lifecycle-catalog plus loader/caller review.

## Architecture Map

| layer | representative modules | role | governance stance |
| --- | --- | --- | --- |
| contracts / runtime | `contracts.py`, `validation_contract.py`, `runtime_support.py` | shared schemas, validation, and runtime helpers | stable public substrate |
| lab / hypothesis batch | `lab.py`, `hypothesis_batch.py`, `deterministic_survival.py` | research orchestration and manifest-driven batch execution | public entry surface |
| features / admission | `features.py`, `feature_admission.py`, `feature_admission_v2.py`, `regime_gating.py` | feature construction, registry behavior, admission checks | facade-first only |
| providers / data foundation | `binance_*`, `coinglass_*`, `onchain_*`, `stablecoin_*`, `market_data.py` | provider adapters, panels, and data readiness support | split only after caller audit |
| governance / promotion | `governance.py`, `promotion.py`, `repo_health.py`, `experiment_status.py` | lifecycle state, promotion gates, and repo health | preserve fail-closed behavior |
| legacy / archive | `legacy_surface.py`, `bridge.py`, `legacy_experiments.py`, `overlap_rerun.py` | historical compatibility, archived-only publication, bridge evidence | active guardrail, not dead code |
| root manifests | `cross_sectional_hypothesis_batch_manifest_v97.json`, `cross_sectional_hypothesis_batch_manifest_v83.json`, `cross_sectional_hypothesis_batch_manifest*.json`, `deterministic_strategy_manifest.json`, `strategy_library_thesis_seed.json` | runtime default, documented baselines, retired, quarantined, or evidence-bearing manifests | path-sensitive; governed by the S2 lifecycle catalog |

## Reverse Dependency Baseline

The package is already a public API for repo-local callers:

| imported module | current caller pattern | governance implication |
| --- | --- | --- |
| `features.py` | heavily imported by scripts and tests | cannot be moved or split without stable re-export coverage |
| `lab.py` | imported by scripts, tests, and lazy package exports | orchestration facade must remain stable |
| `hypothesis_batch.py` | imported by scripts and manifest-driven runners | constants and manifest paths are compatibility surface |
| `contracts.py` | broad internal, script, and test dependency | base contract layer must not be churned casually |

No non-`quant_research` `src/enhengclaw` package currently depends back on
`quant_research` as a package-level implementation detail. Preserve that clean
outer boundary.

## Do Not Move Without Redesign

The following surfaces are frozen until a dedicated dry-run proves compatibility:

- `src/enhengclaw/quant_research/__init__.py` lazy exports and the modules they
  expose.
- Root JSON manifests loaded by constants or documented runtime paths.
- `legacy_surface.py`, `bridge.py`, and archived-only publication guardrails.
- `contracts.py`, `features.py`, `lab.py`, and `hypothesis_batch.py`.
- Any module whose relocation would require script caller rewrites, test caller
  rewrites, manifest path rewrites, or compatibility shims.

Any future source move must prove all of the following before implementation:

- public API imports remain valid;
- script callers either keep their existing import or are rewritten with a
  root-compatible wrapper/facade strategy;
- test imports remain valid;
- manifest path loading remains valid;
- legacy/archive guardrails still fail closed.

## Governance Phases

| phase | goal | allowed actions | forbidden actions | completion signal |
| --- | --- | --- | --- | --- |
| S0 baseline / index | record package architecture and index this plan | docs-only baseline and governance-index hook | source moves, import rewrites, manifest moves | static docs contract passes |
| S1 src architecture static contract | define public source surfaces and frozen boundaries | add tests/docs that classify public surfaces | moving modules before the contract exists | contract blocks unreviewed source churn |
| S2 manifest lifecycle catalog | classify root JSON as active, retired, quarantined, historical, or config | catalog and metadata normalization | moving root manifests without loader redesign | root JSON status is discoverable |
| S3 facade-first split readiness | prepare internal splits behind stable imports | new internal modules plus re-exports after dry-run | breaking direct callers or lazy exports | scripts and tests pass unchanged |
| S4 owner-approved source refactor | perform high-risk source cleanup only with approval | small implementation commits with compatibility shims | broad package reshapes or silent behavior edits | targeted tests plus static contracts pass |

## Deferred / Owner-Gated

These are not approved by this plan:

- splitting `features.py` or `lab.py`;
- relocating `hypothesis_batch.py` or changing its manifest constants;
- moving root JSON manifests into a new directory;
- relocating legacy compatibility or archive-only guardrail modules;
- introducing a new provider/data-foundation source subpackage without a caller
  audit and import-compatibility plan.

Each item above requires a separate dry-run artifact before any implementation
commit. The dry-run must list direct callers, script reverse dependencies, test
imports, path-sensitive artifact outputs, and validation commands.

## Verification Commands

For this documentation-only baseline:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
rg -n "src_quant_research_architecture_governance_plan_2026_05_14" docs\quant_research\00_roadmap_state\research_doc_governance_index.md
git status --short
```

Runtime-heavy quant tests are not required for this batch because no Python
behavior, manifest loader, script wrapper, or artifact path is changed.
