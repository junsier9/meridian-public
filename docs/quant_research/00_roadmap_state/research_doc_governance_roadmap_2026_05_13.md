# Research Document Governance Roadmap - 2026-05-13

`Status: staged governance plan`
`Scope: research Markdown, roadmap/catalog contracts, and script-path coordination`
`Principle: preserve conclusions; improve discoverability and path safety`

## Phase 0: Inventory / Link Audit

Goal:

- produce a reproducible inventory of source Markdown, artifact Markdown, local
  links, duplicate names, and code/config/test references to document paths.

Movable file scope:

- none. This phase is read-only.

Forbidden:

- no moves;
- no link edits;
- no deletion;
- no artifact rewrites.

Verification commands:

```powershell
git status --short
git ls-files --cached --others --exclude-standard -- "*.md"
rg -n "docs/quant_research/|quant_research_script_catalog|threshold_provenance" docs scripts src config tests
python -m pytest tests\test_static_contracts.py -q
```

Completion criteria:

- inventory counts are recorded;
- local Markdown link check has zero unexplained broken links;
- files strongly referenced by tests/config/scripts are labeled before any move.

## Phase 1: Entrypoint Compression

Goal:

- make the current read order explicit and prevent older `active/current`
  language from becoming the execution source by accident.

Movable file scope:

- source Markdown only, but prefer link/index edits over moves in this phase.

Forbidden:

- do not change alpha conclusions;
- do not add new immediate-root files under `docs/quant_research`;
- do not move `quant_research_roadmap_state_2026_05_12.md`,
  `quant_research_script_catalog.md`, `scripts/quant_research/README.md`, or
  `config/quant_research/threshold_provenance.md`.

Verification commands:

```powershell
python -m pytest tests\test_static_contracts.py -q
rg -n "docs/quant_research/[A-Za-z0-9_-]+\.md" config docs scripts src tests
git diff --check
```

Completion criteria:

- the root quant-research roadmap links the active h10d frontier, data
  foundation, parallel 1h lane, script catalog, and governance artifacts;
- older roadmap-spine docs are labeled by the root roadmap as advisory or
  historical when appropriate;
- no static-contract root Markdown violation is introduced.

## Phase 2: Safe Markdown Moves

Goal:

- move only obvious source Markdown into the right governance bucket, with
  all internal links updated in the same change.

Movable file scope:

- low-risk docs-root provider/data specs into
  `docs/quant_research/01_data_foundation/`;
- stale research-position notes into
  `docs/quant_research/05_historical_archive/`;
- future source Markdown only after a path-reference scan.

Forbidden:

- do not move scripts;
- do not move artifacts;
- do not delete history;
- do not move config docs;
- do not move prompt `.system.md` files;
- do not move anything with script/config/test hard references until those
  references are explicitly updated.

Verification commands:

```powershell
rg -n "old/path/or/filename" docs scripts src config tests
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Completion criteria:

- no old moved path remains in repo source text;
- moved docs are reachable from a canonical roadmap or catalog;
- local Markdown link check remains zero-broken;
- static contracts pass.

## Phase 3: Stale-Entry Demotion

Goal:

- demote older active-looking docs without erasing their evidence value.

Movable file scope:

- usually none; demotion should be done by index status labels, short
  supersession notes, or archive folder moves only for clearly isolated files.

Forbidden:

- do not edit reported metrics or pass/fail conclusions;
- do not rewrite old branch documents to sound current;
- do not collapse failed/quarantined candidates into the active h10d lane.

Verification commands:

```powershell
rg -n "Status: active|Active baseline|current canonical parent|current active" docs/quant_research docs/QUANT_RESEARCH_LAB.md docs/strategy
python -m pytest tests\test_static_contracts.py -q
```

Completion criteria:

- every stale-looking `active/current` document has a newer index-level status
  explaining whether it is current, advisory, historical, or quarantined;
- old docs remain available for evidence and rediscovery.

## Phase 4: Catalog / Static Contracts

Goal:

- make governance enforceable so new research docs do not become islands.
- require every `docs/quant_research/**/*.md` source document to be referenced
  by the main roadmap, script catalog, or governance index.

Movable file scope:

- none by default. This phase changes catalog/static-contract logic only if the
  owner intentionally wants that guardrail.

Forbidden:

- do not loosen static contracts just to make a messy move pass;
- do not let script catalog paths drift from the actual filesystem;
- do not add source docs that lack an index hook.
- do not add a new governance-index source without updating the static
  contract intentionally.

Verification commands:

```powershell
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Completion criteria:

- script catalog covers every script;
- `scripts/quant_research/README.md` and the roadmap state file share entry
  language;
- root quant-research Markdown remains intentionally consolidated;
- new governance docs are reachable from the roadmap state;
- `test_quant_research_markdown_docs_are_indexed` fails if a new
  `docs/quant_research/**/*.md` file is not discoverable from one sanctioned
  index source.

## Phase 5: Optional Script-Path Refactor Coordination

Goal:

- coordinate document governance with script path refactors only when the
  script move plan has already been accepted and validated.

Movable file scope:

- Markdown may update catalog/readme links;
- scripts move only under the separate script refactor plan, not under this
  document-governance roadmap.

Forbidden:

- no script moves inside a Markdown-only governance batch;
- no scheduled wrapper moves without preserving public entrypoints;
- no parallel 1h partial move without the import rewrite plan;
- no artifact movement.

Verification commands:

```powershell
python -m compileall -q scripts\quant_research
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Completion criteria:

- script catalog, README, imports, and scheduled-task contracts agree;
- any moved script has either no external caller or a wrapper where the catalog
  requires one;
- document links to moved paths are updated in the same change.
