# Phase 5.1 Overlap Maintenance Script Path Refactor Dry-Run

`Date: 2026-05-13`
`Baseline commit: b27d21b Refine quant script wrapper governance`
`Scope: dry-run only; no script moves`
`Checklist: script_path_refactor_checklist.md`
`Decision: recommended next low-risk batch`
`Follow-up: Phase 5.1 implementation executed after this dry-run; keep observed baseline below as pre-move evidence`

## Decision

The next lowest-risk script-path refactor batch is the overlap and validation
maintenance group:

- move 3 implementation scripts into `scripts/quant_research/maintenance/`
- keep 3 root-level compatibility wrappers at the current public paths
- keep historical command examples in `docs/QUANT_RESEARCH_LAB.md` valid via
  those wrappers
- update catalog and README counts in the implementation commit

This is lower risk than the next-visible alternatives because these scripts
have no direct references from `config`, `scripts`, `src`, or `tests`. Their
only current non-catalog command references are in a historical lab runbook.

## Dry-Run Inputs

Commands used for this dry-run:

```powershell
git status --short
git log -1 --oneline
rg -n "run_quant_overlap_legacy_cleanup|run_quant_overlap_rerun_remediation|run_quant_validation_contract_remediation" config scripts src tests -g "*.py" -g "*.ps1" -g "*.md" -g "*.json" -g "*.toml" -g "*.yaml" -g "*.yml"
rg -n "run_quant_overlap_legacy_cleanup|run_quant_overlap_rerun_remediation|run_quant_validation_contract_remediation" docs -g "*.md"
python scripts\quant_research\run_quant_overlap_legacy_cleanup.py --help
python scripts\quant_research\run_quant_overlap_rerun_remediation.py --help
python scripts\quant_research\run_quant_validation_contract_remediation.py --help
python -m compileall -q scripts\quant_research\run_quant_overlap_legacy_cleanup.py scripts\quant_research\run_quant_overlap_rerun_remediation.py scripts\quant_research\run_quant_validation_contract_remediation.py
```

Observed baseline:

- working tree was clean before this dry-run artifact
- latest commit was `b27d21b Refine quant script wrapper governance`
- the 3 target scripts all compile
- the 3 current root CLI paths all support `--help`
- exact scan found no `config`, `scripts`, `src`, or `tests` references

## Recommended Move Batch

Target directory:

```text
scripts/quant_research/maintenance/
```

| current public path | implementation target | current catalog status | wrapper required | strong refs |
| --- | --- | --- | --- | --- |
| `scripts/quant_research/run_quant_overlap_legacy_cleanup.py` | `scripts/quant_research/maintenance/run_quant_overlap_legacy_cleanup.py` | `deprecated_candidate` / `historical_do_not_start_here` | yes | none outside docs/catalog |
| `scripts/quant_research/run_quant_overlap_rerun_remediation.py` | `scripts/quant_research/maintenance/run_quant_overlap_rerun_remediation.py` | `supporting` / `supporting_tool` | yes | none outside docs/catalog |
| `scripts/quant_research/run_quant_validation_contract_remediation.py` | `scripts/quant_research/maintenance/run_quant_validation_contract_remediation.py` | `supporting` / `supporting_tool` | yes | none outside docs/catalog |

## Reference Findings

Strong code/config references:

- `config`: none found
- `scripts`: none found
- `src`: none found
- `tests`: none found
- scheduled manifest: no matching scheduled-task path found

Markdown references to preserve or update:

- `docs/QUANT_RESEARCH_LAB.md` contains historical command examples for all
  3 current public paths.
- `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`
  contains the 3 current catalog rows.
- `docs/quant_research/00_roadmap_state/script_path_refactor_dry_run_phase2a_2026_05_12.md`
  mentions `run_quant_overlap_legacy_cleanup.py` as an earlier utility
  candidate.

Because `docs/QUANT_RESEARCH_LAB.md` is explicitly superseded historical
evidence, the actual move may leave those commands unchanged if the wrappers
remain. The catalog must still distinguish wrappers from moved implementations.

## Import And Root-Path Notes

The 3 target scripts do not import each other.

Root-path calculations must still change after moving one directory deeper:

- `run_quant_overlap_legacy_cleanup.py` currently uses
  `SCRIPT_DIR.parents[1]`; moved implementation should use
  `SCRIPT_DIR.parents[2]`.
- `run_quant_overlap_rerun_remediation.py` currently uses
  `SCRIPT_DIR.parents[1]`; moved implementation should use
  `SCRIPT_DIR.parents[2]`.
- `run_quant_validation_contract_remediation.py` currently uses
  `Path(__file__).resolve().parents[2]`; moved implementation should use an
  equivalent one-level-deeper repo-root calculation.

Wrapper shape should stay minimal:

```python
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.maintenance.run_quant_overlap_rerun_remediation import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

For `run_quant_validation_contract_remediation.py`, normalize the moved
implementation to `main(argv: list[str] | None = None)` before wrapping so the
wrapper can forward `sys.argv[1:]` consistently.

## Catalog And README Contract

Actual move commit should:

- add 3 moved implementation rows under the existing `utilities_and_reports`
  category
- keep 3 root wrapper rows as `status = supporting` and
  `run priority = supporting_tool`
- keep the moved `run_quant_overlap_legacy_cleanup.py` implementation as
  `deprecated_candidate` / `historical_do_not_start_here`
- keep the two remediation implementations as `supporting` /
  `supporting_tool`
- set wrapper rows to `safe-to-move = no`
- update script coverage counts from 192 to 195
- update root/subdirectory counts to include
  `3 under maintenance`

## Risk Rating

| candidate group | risk | dry-run decision |
| --- | --- | --- |
| overlap and validation maintenance, 3 scripts | low | recommended next batch |
| crypto-news dataset review, 2 scripts | medium | defer; tests import internal helper symbols from root modules |
| provider capability probes | medium | defer; two Deribit probes are referenced by `config/quant_research/threshold_provenance.md` |
| factor-report writers | medium-high | defer; broad `threshold_provenance.md` config references and some script/source references |
| scheduled wrappers or active default entrypoints | high | do not move in this batch |

## Actual Move Contract

Allowed:

- create `scripts/quant_research/maintenance/`
- move only the 3 listed implementation scripts
- add root wrappers for the 3 old paths
- fix moved implementation root-path calculations
- normalize `run_quant_validation_contract_remediation.py` to accept
  `main(argv)`
- update catalog rows, summary counts, and README counts
- leave `docs/QUANT_RESEARCH_LAB.md` historical commands unchanged if wrapper
  smoke tests prove the old paths still work

Forbidden:

- do not move artifacts
- do not move scheduled wrappers
- do not move current default-entrypoint research scripts
- do not change remediation behavior
- do not delete or rewrite historical evidence
- do not mix this with crypto-news, provider-probe, or factor-report moves

## Validation Commands For Actual Move

Run after implementation:

```powershell
python -m compileall -q scripts\quant_research\maintenance scripts\quant_research\run_quant_overlap_legacy_cleanup.py scripts\quant_research\run_quant_overlap_rerun_remediation.py scripts\quant_research\run_quant_validation_contract_remediation.py
$repo=(Get-Location).Path; $tmp=$env:TEMP; Push-Location $tmp; try { python "$repo\scripts\quant_research\run_quant_overlap_legacy_cleanup.py" --help; python "$repo\scripts\quant_research\run_quant_overlap_rerun_remediation.py" --help; python "$repo\scripts\quant_research\run_quant_validation_contract_remediation.py" --help } finally { Pop-Location }
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Also run the local Markdown link checker if catalog or README links are
changed.

## Deferred

- No scripts were moved in this dry-run.
- No imports were rewritten in this dry-run.
- No catalog rows were changed in this dry-run.
- Crypto-news dataset scripts are deferred because tests import helpers from
  root module paths; they need either test import rewrites or re-exporting
  compatibility wrappers.
- Factor-report writers and provider probes are deferred because config
  references must be updated deliberately, not as an incidental path cleanup.
