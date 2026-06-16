# Research Document Governance Audit - 2026-05-13

`Status: governance audit artifact`
`Scope: repo Markdown with emphasis on docs/quant_research`
`Mode: read-only inventory first; low-risk Markdown governance may follow`

This audit does not revise alpha conclusions. It records document-state risks
and the safe governance boundary for making the research roadmap easier to
resume.

## Initial Worktree State

The required pre-audit command was run first:

```powershell
git status --short
```

Initial state:

```text
 M docs/quant_research/00_roadmap_state/script_path_refactor_dry_run_phase2a_2026_05_12.md
 M scripts/quant_research/README.md
?? docs/quant_research/00_roadmap_state/parallel_1h_import_rewrite_strategy_2026_05_13.md
```

Those files were treated as pre-existing work and not reverted.

## Audit Commands

Core inventory commands:

```powershell
git ls-files --cached --others --exclude-standard -- "*.md"
Get-ChildItem -Path . -Recurse -Filter *.md
rg -n "docs/quant_research/|quant_research_roadmap_state_2026_05_12|quant_research_script_catalog|threshold_provenance" docs scripts src config tests
```

A local Markdown-link scan over versioned and unignored Markdown found:

```text
broken_local_links = 0
```

Earlier apparent misses were `file.py:line` style links; after stripping line
suffixes they resolved.

## Current Document Map

Repo-level Markdown inventory, excluding ignored files:

| area | count / role | governance read |
| --- | ---: | --- |
| all versioned or unignored Markdown | 627 | includes docs plus checked-in evidence cards |
| `docs/quant_research` | 89 before this governance batch | main research documentation surface |
| `docs/quant_research/00_roadmap_state` | 14 before this governance batch | roadmap state, script catalog, advisory spine, refactor plans |
| `docs/quant_research/01_data_foundation` | 8 before this governance batch | provider registry, market inventory, data foundation plans |
| `docs/quant_research/02_binance_pit_h10d` | 18 | current active h10d validation frontier and supporting reports |
| `docs/quant_research/03_alpha_branches` | 29 | failed, quarantined, and closed mechanism branches |
| `docs/quant_research/04_parallel_1h` | 2 | separate 1h lane, not admitted to h10d |
| `docs/quant_research/mechanism_notes` | 17 | mechanism ontology and preregistration scaffolding |
| `artifacts/quant_research/**.md` | many | historical evidence layer, not a doc-governance move target |
| `config/quant_research/threshold_provenance.md` | 1 | audit lineage and threshold contract, must stay under config |
| `scripts/quant_research/README.md` | 1 | script entrypoint contract, tests read it |
| root Markdown | 6 | repo/operator entrypoints, not quant-research move targets |

The static contract currently requires exactly one immediate-root Markdown file
under `docs/quant_research`:

```text
docs/quant_research/quant_research_roadmap_state_2026_05_12.md
```

Do not add additional `docs/quant_research/*.md` root files unless the static
contract is intentionally updated.

## Canonical Entrypoints To Keep

| question | canonical entrypoint | move policy |
| --- | --- | --- |
| Where is the current mainline? | `docs/quant_research/quant_research_roadmap_state_2026_05_12.md` | do not move |
| Which scripts are safe to run? | `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md` | do not move without static contract update |
| What is the active h10d frontier? | `docs/quant_research/02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12.md` plus later 2026-05-12 h10d hardening reports | keep in `02_binance_pit_h10d` |
| What is the data foundation? | `docs/quant_research/01_data_foundation/market_data_inventory.md` and `provider_api_registry.md` | keep in `01_data_foundation` |
| What happened to CoinGlass/R lanes? | `docs/quant_research/03_alpha_branches/research_priority_update_full_stack.md` | keep as alpha-branch closure evidence |
| What is the separate 1h lane? | `docs/quant_research/04_parallel_1h/parallel_1h_alpha_mining_roadmap.md` | keep separate from h10d |
| What is the audit lineage? | `config/quant_research/threshold_provenance.md` | do not move |
| What is the script path-refactor state? | `docs/quant_research/00_roadmap_state/script_path_refactor_dry_run_phase2a_2026_05_12.md` and `parallel_1h_import_rewrite_strategy_2026_05_13.md` | keep in `00_roadmap_state` |

## Gaps Found

### Root or Directory-Scattered Research Docs

| file | finding | recommendation |
| --- | --- | --- |
| `docs/QUANT_RESEARCH_LAB.md` | broad historical lab runbook with live command examples and script references | do not move in first batch; later demote or split only with dry-run and command-link update |
| `docs/QUANT_NEXT_DATA_SPECS.md` | data-provider requirements doc in generic docs root | low-risk move to `docs/quant_research/01_data_foundation/` |
| `docs/strategy/research_track_position_2026-04-22.md` | old track-position note with stale and garbled text | low-risk move to historical archive under `docs/quant_research/` |
| `config/quant_research/threshold_provenance.md` | quant audit lineage outside docs tree | correct location because config/tests refer to it |
| `scripts/quant_research/README.md` | script entry contract outside docs tree | correct location because tests read it |

### Duplicate Or Same-Name Markdown

Expected duplicates:

| name | count | governance read |
| --- | ---: | --- |
| `alpha_card.md` | 459 | experiment evidence cards under artifacts; do not consolidate or move |
| `quant_cycle_summary.md` | 23 | cycle summaries under artifacts; do not consolidate or move |
| `README.md` | 9 | directory-local README files; expected |
| `fixed_set_comparison.md` | 9 | experiment evidence sidecars; do not move |
| `overlay_ablation.md` | 3 | experiment evidence sidecars; do not move |

The duplicate-name risk is mostly in `artifacts/**`, not in source research
docs.

### Orphan Or Under-Indexed Source Docs

The current root roadmap indexed 83 quant docs, while 6 source docs were not
yet represented in its coverage/index:

| file | reason | governance action |
| --- | --- | --- |
| `00_roadmap_state/parallel_1h_import_rewrite_strategy_2026_05_13.md` | created after prior consolidation | add to roadmap coverage |
| `00_roadmap_state/script_path_refactor_dry_run_phase2a_2026_05_12.md` | refactor plan not included in original coverage index | add to roadmap coverage |
| `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12_hv_balanced_soft_budget.md` | newer h10d report | add to h10d coverage |
| `02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12_hv_mild_soft_budget.md` | newer h10d report | add to h10d coverage |
| `02_binance_pit_h10d/binance_pit_hv_balanced_anti_overfit_validation_2026_05_12.md` | newer freeze/anti-overfit report | add to h10d coverage |
| `02_binance_pit_h10d/binance_pit_hv_soft_portfolio_budget_2026_05_12.md` | newer risk-budget report | add to h10d coverage |

This is a catalog/index problem, not a research-conclusion problem.

### Stale Active Or Current Language

The main conflict pattern is older docs saying `Status: active` or `current`
while later roadmap state demotes them. Examples:

| file | stale/conflicting phrase shape | current governance read |
| --- | --- | --- |
| `00_roadmap_state/strategy_upgrade_roadmap.md` | `Status: active`, `Active baseline: xs_minimal_v3_h5d` | original roadmap spine; advisory/historical |
| `00_roadmap_state/alpha_ontology_and_factor_library.md` | `Status: active` as canonical research-direction memo | advisory ontology, not current execution state |
| `00_roadmap_state/data_utilization_roadmap.md` | active candidates and older Day 90 framing | partly superseded by 2026-05-12 roadmap state |
| `00_roadmap_state/h10d_strategy_model_factor_contributions_2026_05_09.md` | current h10d canonical parent language | benchmark/shadow-only after Binance PIT turn |
| `docs/QUANT_RESEARCH_LAB.md` | older active/pass terminology and command examples | operational history; needs later demotion/splitting |
| `docs/strategy/research_track_position_2026-04-22.md` | old current-evidence note | historical archive only |

Rule: when these conflict, prefer
`docs/quant_research/quant_research_roadmap_state_2026_05_12.md` and newer
2026-05-12 h10d reports.

## Files Recommended For Historical/Archive Demotion

| file | demotion target | risk |
| --- | --- | --- |
| `docs/strategy/research_track_position_2026-04-22.md` | move to `docs/quant_research/05_historical_archive/` | low |
| `00_roadmap_state/strategy_upgrade_roadmap.md` | keep in place, label as advisory from the main roadmap | low |
| `00_roadmap_state/alpha_ontology_and_factor_library.md` | keep in place, label as advisory from the main roadmap | low |
| `00_roadmap_state/data_utilization_roadmap.md` | keep in place, label as partly superseded from the main roadmap | low |
| `docs/QUANT_RESEARCH_LAB.md` | defer; possible later split into historical runbook plus current entry pointers | medium |

## First-Batch Move List

Only Markdown files qualify. No scripts, artifacts, configs, or tests move.

| current path | target path | link updates required | risk |
| --- | --- | --- | --- |
| `docs/QUANT_NEXT_DATA_SPECS.md` | `docs/quant_research/01_data_foundation/quant_next_data_specs.md` | update `docs/QUANT_RESEARCH_LAB.md` and `data_sponsorship_investment_plan_2026_05.md` | low |
| `docs/strategy/research_track_position_2026-04-22.md` | `docs/quant_research/05_historical_archive/research_track_position_2026-04-22.md` | add root-roadmap historical coverage | low |

Execution record:

- executed in this governance batch after the read-only audit;
- `docs/QUANT_RESEARCH_LAB.md` link updated to the new data-foundation path;
- `data_sponsorship_investment_plan_2026_05.md` reference updated to the new data-foundation path;
- `quant_research_roadmap_state_2026_05_12.md` coverage index updated for the moved docs, governance artifacts, and post-consolidation h10d reports;
- post-move `docs/quant_research` source-doc count is 93, still with only one immediate-root Markdown file.

## Internal Links To Update

| source file | update |
| --- | --- |
| `docs/QUANT_RESEARCH_LAB.md` | replace absolute local link to `docs/QUANT_NEXT_DATA_SPECS.md` with relative link to the new data-foundation path |
| `docs/quant_research/01_data_foundation/data_sponsorship_investment_plan_2026_05.md` | update table row for the data-spec document |
| `docs/quant_research/quant_research_roadmap_state_2026_05_12.md` | index new governance docs, h10d hardening reports, moved data spec, and historical archive file |

## Do Not Move

| path | reason |
| --- | --- |
| `docs/quant_research/quant_research_roadmap_state_2026_05_12.md` | static contract protects it as the only root quant-research Markdown |
| `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md` | tests parse it against every script |
| `scripts/quant_research/README.md` | tests assert shared entry language |
| `config/quant_research/threshold_provenance.md` | threshold/publication contracts and tests refer to config location |
| `artifacts/**` | evidence layer, not documentation governance source |
| `src/enhengclaw/agents/prompts/*.system.md` | prompt assets consumed by agent definitions |
| `docs/live_trading/hv_balanced_binance_usdm_pipeline/README.md` | live-trading plan context, outside quant-doc cleanup |
| `.claude/worktrees/**` | local sidecar worktrees, not source governance |

## Risk Register

| risk | level | notes |
| --- | --- | --- |
| Moving root quant docs into immediate `docs/quant_research/*.md` | high | violates static consolidation contract unless tests are updated |
| Moving script catalog or script README | high | static tests and operators depend on them |
| Moving `threshold_provenance.md` | high | config path is a contract |
| Moving artifacts evidence cards | high | breaks lineage and artifact references |
| Moving `docs/QUANT_RESEARCH_LAB.md` | medium | contains many command examples and historical operational claims |
| Moving `docs/QUANT_NEXT_DATA_SPECS.md` into data foundation | low | few references and natural data-foundation home |
| Moving old strategy track-position note into archive | low | no strong active references found |
| Adding index links for under-indexed h10d reports | low | catalog-only governance |

## Operations Requiring Dry-Run First

These must be planned and validated before execution:

- any move of Markdown under `scripts/`, `config/`, `src`, or root entrypoint docs;
- any move that changes paths referenced by tests or JSON manifests;
- any move involving `docs/QUANT_RESEARCH_LAB.md`;
- any future creation of `docs/quant_research/*.md` root files;
- any script-path refactor, even if the moved files are not Markdown;
- any artifact movement or evidence-card consolidation;
- any change to scheduled-task manifest paths.

Minimum dry-run commands:

```powershell
git status --short
git ls-files --cached --others --exclude-standard -- "*.md"
rg -n "old/path/or/filename" docs scripts src config tests
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

For scheduled or script-catalog path changes, also run:

```powershell
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
```
