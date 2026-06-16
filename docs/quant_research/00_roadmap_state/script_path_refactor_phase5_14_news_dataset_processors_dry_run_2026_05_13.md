# Phase 5.14 News Dataset Processors Dry Run

`Status: read-only dry-run baseline`
`Scope: crypto-news LLM dataset processor scripts`
`Date: 2026-05-13`

## Decision

Create `scripts/quant_research/news_dataset_processors/` for long-running
crypto-news dataset ingestion and review processors. These are utilities for
research enrichment, not raw market-data sync pipelines and not default roadmap
entrypoints.

## Move Set

| old root path | new implementation path | compatibility requirement |
| --- | --- | --- |
| `scripts/quant_research/process_cryptonewsdataset_llm.py` | `scripts/quant_research/news_dataset_processors/process_cryptonewsdataset_llm.py` | root tests import private helpers; keep root re-export shim |
| `scripts/quant_research/review_cryptonewsdataset_strong_model.py` | `scripts/quant_research/news_dataset_processors/review_cryptonewsdataset_strong_model.py` | root tests import private helpers; keep root re-export shim |

## Reference Audit

Strong references:

- `tests/test_quant_cryptonewsdataset_processing.py`
- `tests/test_quant_cryptonewsdataset_strong_review.py`

Doc references:

- `docs/quant_research/01_data_foundation/provider_api_registry.md`
- `docs/quant_research/01_data_foundation/market_data_inventory.md`

Old root paths remain valid through shims, so this batch does not need to edit
provider registry or market-data inventory language.

## Implementation Rules

- Move only the two news dataset processor implementations.
- Update moved implementation root discovery from `SCRIPT_DIR.parents[1]` to
  `SCRIPT_DIR.parents[2]`.
- Rewrite `review_cryptonewsdataset_strong_model.py` to import helper symbols
  from the moved package path.
- Keep root re-export shims at old paths because tests import private helpers.
- Do not move provider sync pipelines or raw data refresh entrypoints into this
  directory.

## Expected Count Changes

Starting from Phase 5.13:

- Total script files: 246 -> 248.
- Python script files: 227 -> 229.
- Root-level count: stays 162.
- `news_dataset_processors/`: 0 -> 2.
- `utilities_and_reports`: 42 -> 44.
- `supporting`: 115 -> 117.
- `supporting_tool`: 135 -> 137.
- `safe-to-move = no`: 76 -> 78.

## Verification Commands

```powershell
python -m compileall -q scripts\quant_research\news_dataset_processors scripts\quant_research\process_cryptonewsdataset_llm.py scripts\quant_research\review_cryptonewsdataset_strong_model.py
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\process_cryptonewsdataset_llm.py --help
python C:\Users\user\Documents\Claude\Projects\EnhengClaw\scripts\quant_research\review_cryptonewsdataset_strong_model.py --help
python -m pytest tests\test_quant_cryptonewsdataset_processing.py tests\test_quant_cryptonewsdataset_strong_review.py -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_runtime_contracts.py tests\test_scheduled_task_contracts.py -q
git diff --check
```

## Deferred

- Data-sync pipelines remain owner-review gated.
- Generic utility/default-cycle entrypoints remain separate from news dataset
  processors.
