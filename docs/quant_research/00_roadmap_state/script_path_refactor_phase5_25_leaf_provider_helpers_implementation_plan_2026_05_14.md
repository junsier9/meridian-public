# Phase 5.25 Leaf Provider Helpers Implementation Plan

Date: 2026-05-14

Status: implementation plan only. This artifact does not move scripts.

Baseline: after `764e58a Document Phase 5.24 leaf data-sync helper dry run`.

## Decision

Approved for implementation planning only:

- `sync_okx_funding_history.py`
- `sync_cryptoquant_stablecoin_history.py`
- `sync_cryptoquant_reflexivity_history.py`
- `sync_tronscan_stablecoin_tron.py`

Not approved in this batch:

- `generate_versioned_panel.py`
- `run_quant_derivatives_sync_evidence.py`
- scheduled/default data-sync entrypoints
- CoinGlass full-stack or sidecar sync boundaries
- h10d/current-line validation boundaries
- stablecoin Ethereum backfill/address-label paths

## Target Directory

Use:

```text
scripts/quant_research/provider_leaf_sync_helpers/
```

Rationale:

- narrower than the Phase 5.24 provisional name `leaf_data_sync_helpers/`;
- distinct from `provider_probes/`, which remains capability-probe only;
- distinct from broad names like `data_sync/`, `data_foundation/`, or
  `provider_sync/`, which would overstate directory semantics;
- explicit that these are leaf provider sync helpers, not scheduled pipelines,
  default sync entrypoints, h10d evidence gates, or CoinGlass full-stack sync.

## File Moves

Move these implementation files into the target directory:

| Root path today | New implementation path |
| --- | --- |
| `scripts/quant_research/sync_okx_funding_history.py` | `scripts/quant_research/provider_leaf_sync_helpers/sync_okx_funding_history.py` |
| `scripts/quant_research/sync_cryptoquant_stablecoin_history.py` | `scripts/quant_research/provider_leaf_sync_helpers/sync_cryptoquant_stablecoin_history.py` |
| `scripts/quant_research/sync_cryptoquant_reflexivity_history.py` | `scripts/quant_research/provider_leaf_sync_helpers/sync_cryptoquant_reflexivity_history.py` |
| `scripts/quant_research/sync_tronscan_stablecoin_tron.py` | `scripts/quant_research/provider_leaf_sync_helpers/sync_tronscan_stablecoin_tron.py` |

Keep root files at the original four paths as CLI compatibility wrappers.

## Implementation Edits

### Shared Implementation Path Fix

Each moved implementation currently derives repo root from:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
```

After moving one directory deeper, update each moved implementation to:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
```

This is required before any wrapper smoke test. Without it, `ROOT` resolves to
`scripts/` instead of the repository root.

### `sync_okx_funding_history.py`

Root wrapper strategy:

```python
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.provider_leaf_sync_helpers.sync_okx_funding_history import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

Required implementation adjustment:

- change `parse_args()` to `parse_args(argv: list[str] | None = None)`;
- parse with `parser.parse_args(argv)`;
- change `main(argv: list[str] | None = None)` to call `parse_args(argv)`.

Reason: this makes the wrapper truly argv-forwarding instead of relying on
ambient `sys.argv`.

### `sync_cryptoquant_stablecoin_history.py`

Root wrapper strategy:

```python
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.provider_leaf_sync_helpers.sync_cryptoquant_stablecoin_history import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

No module re-export is required because the dry-run found no package caller that
imports from the root script.

### `sync_cryptoquant_reflexivity_history.py`

Root wrapper strategy:

```python
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.provider_leaf_sync_helpers.sync_cryptoquant_reflexivity_history import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

No module re-export is required because active callers use
`src/enhengclaw/quant_research/onchain_cryptoquant.py`, not the root script.

### `sync_tronscan_stablecoin_tron.py`

Root wrapper strategy:

```python
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quant_research.provider_leaf_sync_helpers.sync_tronscan_stablecoin_tron import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

No module re-export is required because tests and active code import
`run_m3_2_tron_stablecoin_sync` from `src`, not the root script.

## Documentation Updates

### Script Catalog

Update `docs/quant_research/00_roadmap_state/quant_research_script_catalog.md`:

- coverage count: `274` -> `278`;
- Python count: `255` -> `259`;
- root-level count remains `162`;
- root compatibility wrappers: `85` -> `89`;
- add new directory count: `4 under provider_leaf_sync_helpers`;
- add Phase 5.25 to the path-policy summary;
- convert the four old root rows into compatibility-wrapper rows:
  - status/posture should remain supporting, not default entrypoint;
  - input should be old root CLI path and forwarded args;
  - output should delegate to moved `provider_leaf_sync_helpers` implementation;
  - `safe-to-move` should be `no`;
- add four moved implementation rows under
  `scripts/quant_research/provider_leaf_sync_helpers/`:
  - catalog category remains `data_foundation_sync`;
  - status should remain `active` only for the implementation rows;
  - role remains `supporting_tool`;
  - `safe-to-move` remains `yes-with-wrapper`.

### README

Update `scripts/quant_research/README.md`:

- coverage count: `274` -> `278`;
- Python count: `255` -> `259`;
- root compatibility wrappers: `85` -> `89`;
- add `4 under provider_leaf_sync_helpers`;
- add a Phase 5.25 Path Policy line;
- add a directory rule:
  - provider leaf sync helpers belong in `provider_leaf_sync_helpers/`;
  - do not put scheduled provider runners, default sync entrypoints, provider
    capability probes, CoinGlass full-stack sync, or h10d boundaries there.

### Checklist

Update `docs/quant_research/00_roadmap_state/script_path_refactor_checklist.md`:

- add `provider_leaf_sync_helpers/` as an allowed target directory;
- define it as only for leaf provider sync helpers with no scheduled/config
  hard reference and no active script-level caller;
- explicitly keep `provider_probes/` for capability probes only;
- explicitly keep provider sync pipelines and default entrypoints owner-gated.

### Data Foundation Docs

Update implementation-path references where the document is an inventory or
provider registry rather than a command example:

- `docs/quant_research/01_data_foundation/provider_api_registry.md`
- `docs/quant_research/01_data_foundation/market_data_inventory.md`
- `docs/quant_research/01_data_foundation/cryptoquant_alchemy_m3_2_plan.md`

Keep root CLI examples valid if they are written as commands. The old root paths
will continue to work through wrappers.

### Governance Index

Update `docs/quant_research/00_roadmap_state/research_doc_governance_index.md`
to include this implementation plan.

## Do Not Update

Do not churn historical Phase 5.x dry-run artifacts just because they mention
old root paths. The root compatibility wrappers preserve those historical links.

Do not update scheduled-task manifests. The dry-run found no scheduled/config
references to these four root paths.

Do not update `run_quant_cryptoquant_m3_2_sync_cycle.py`; it imports the
underlying `src` functions directly and does not call the root helper scripts.

## Verification Commands

Run these after the implementation patch:

```powershell
python -m py_compile `
  scripts\quant_research\sync_okx_funding_history.py `
  scripts\quant_research\sync_cryptoquant_stablecoin_history.py `
  scripts\quant_research\sync_cryptoquant_reflexivity_history.py `
  scripts\quant_research\sync_tronscan_stablecoin_tron.py `
  scripts\quant_research\provider_leaf_sync_helpers\sync_okx_funding_history.py `
  scripts\quant_research\provider_leaf_sync_helpers\sync_cryptoquant_stablecoin_history.py `
  scripts\quant_research\provider_leaf_sync_helpers\sync_cryptoquant_reflexivity_history.py `
  scripts\quant_research\provider_leaf_sync_helpers\sync_tronscan_stablecoin_tron.py

python scripts\quant_research\sync_okx_funding_history.py --help
python scripts\quant_research\provider_leaf_sync_helpers\sync_okx_funding_history.py --help
python scripts\quant_research\sync_cryptoquant_stablecoin_history.py --help
python scripts\quant_research\provider_leaf_sync_helpers\sync_cryptoquant_stablecoin_history.py --help
python scripts\quant_research\sync_cryptoquant_reflexivity_history.py --help
python scripts\quant_research\provider_leaf_sync_helpers\sync_cryptoquant_reflexivity_history.py --help
python scripts\quant_research\sync_tronscan_stablecoin_tron.py --help
python scripts\quant_research\provider_leaf_sync_helpers\sync_tronscan_stablecoin_tron.py --help

python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_onchain_cryptoquant.py tests\test_onchain_stablecoin_tron.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

Do not run live provider syncs as validation. `--help`, `py_compile`, static
contracts, and existing unit/contract tests are the correct non-network
verification layer for this path refactor.

## Completion Criteria

Implementation can be considered complete only if:

- all four old root paths still exist;
- all four moved implementation paths exist under `provider_leaf_sync_helpers/`;
- root wrappers preserve CLI arguments;
- moved implementations resolve repo root correctly through `SCRIPT_DIR.parents[2]`;
- no scheduled/config manifest path is changed;
- catalog and README counts are consistent;
- provider registry and market inventory point at the new implementation paths
  where appropriate;
- the verification command set above passes or any failure is documented as an
  environment-only blocker.
