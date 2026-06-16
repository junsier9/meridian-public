# src quant_research binance_canonical_h10d funding facade owner-gated plan

`Status: read-only owner-gated facade plan`
`Date: 2026-05-15`
`Scope: binance_canonical_h10d funding sync/load helpers`

## Decision

Do not move funding helpers yet. The funding surface is a medium-risk
data-foundation boundary because it combines provider HTTP access, UTC month
partitioning, funding-root path policy, CSV partition writes, manifest writes,
daily aggregation, and downstream PIT eligibility coverage.

The next safe automation step is a test-first contract, not a source move. A
future implementation may create a private `_binance_canonical_funding.py`
module and keep root facade imports, but only after import/signature and
behavior smoke coverage are explicit.

## Correction To Prior Matrix

The Phase B closure matrix originally overstated one caller risk: the M3.1
options-regime audit imports `_http_get_json` from
`enhengclaw.quant_research.coinglass_capability_matrix`, not from
`enhengclaw.quant_research.binance_canonical_h10d`.

Current AST import scan found no repo-local direct import of
`binance_canonical_h10d._http_get_json`, funding path helpers, or funding month
helpers outside `binance_canonical_h10d.py`. This lowers module-import risk, but
does not lower the funding helper group to low-risk movement because the
behavior is still path-sensitive and artifact-sensitive.

## Funding Surface Map

| Surface | Helpers / functions | Role | Risk |
| --- | --- | --- | --- |
| Provider fetch | `_http_get_json`, `fetch_funding_rate_rows` | Binance USD-M `/fapi/v1/fundingRate` page fetch and dedupe window | medium |
| Funding sync entry | `sync_funding_cost_history` | User-facing funding sync orchestration and summary JSON write | medium/high |
| Partition writer | `write_funding_cost_rows`, `_funding_columns`, `_read_funding_partition`, `_dedupe_funding_rows` | Month-partition CSV append/replace semantics and symbol manifest write | medium/high |
| Root/path policy | `funding_symbol_root`, `funding_partition_path`, `funding_symbol_manifest_path`, `funding_sync_summary_path`, `_resolve_funding_root` | Stable funding-root layout and config/default fallback | medium |
| Month filters | `_month_key_from_ms`, `_month_start_ms`, `_month_end_ms`, `_partition_month` | UTC month keying and partition range filtering | medium/high |
| Daily loader | `load_funding_cost_daily`, `attach_funding_cost_to_panel` | Daily funding aggregation and feature-panel attach behavior | medium/high |

## Existing Coverage Baseline

- `tests/test_binance_canonical_h10d.py::test_funding_cost_sync_writes_daily_cost_only_rows_and_attaches_to_panel`
  covers fake-provider sync, monthly partition write, daily load, sample counts,
  and panel attach.
- Existing PIT eligibility tests depend on `funding_rate` and
  `funding_sample_count` semantics after attach.
- No current test freezes private helper import/signature shape for a future
  facade-first move.

## Proposed Facade Strategy

Preferred future target:

- Create `src/enhengclaw/quant_research/_binance_canonical_funding.py`.
- Move funding-only helpers in one coherent batch:
  - `_funding_columns`
  - `funding_symbol_root`
  - `funding_partition_path`
  - `funding_symbol_manifest_path`
  - `funding_sync_summary_path`
  - `_read_funding_partition`
  - `_dedupe_funding_rows`
  - `_http_get_json`
  - `_resolve_funding_root`
  - `_month_key_from_ms`
  - `_month_start_ms`
  - `_month_end_ms`
- Keep root facade imports in `binance_canonical_h10d.py` for every moved name.
- Do not move `_partition_month` in the same batch unless the archive/funding
  partition boundary is redesigned, because it is still shared with kline
  archive path filtering.

## Required Test-First Gates

Before any source move:

1. Add an importability/signature-only static contract for the funding facade
   candidate helpers.
2. Keep existing behavior coverage for:
   - fake HTTP funding sync;
   - partition write/read and dedupe;
   - UTC month filtering;
   - daily aggregation;
   - `attach_funding_cost_to_panel`.
3. Add a tiny behavior smoke if the future implementation touches month helper
   placement or changes the `_partition_month` dependency.

## Explicit Non-Goals

- Do not share `_http_get_json` across Binance and CoinGlass provider modules.
- Do not move `_partition_month` alone.
- Do not move funding helpers together with validation, PIT universe, artifact
  report writers, or feature normalization helpers.
- Do not change funding root defaults, manifest names, partition naming, or CSV
  compression.
- Do not change `sync_funding_cost_history`, `load_funding_cost_daily`, or
  `attach_funding_cost_to_panel` behavior in the same commit as a facade move.

## Next Automation Decision

Approved next automatic step: implement a tiny importability/signature-only
static contract for the funding facade candidate. That contract should not move
source and should explicitly exclude provider behavior, HTTP retry semantics,
funding formula behavior, PIT eligibility behavior, path relocation, and source
migration.

## Validation Commands

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -k funding -q
python -m pytest tests\test_static_contracts.py -q
python -m pytest tests\test_quant_research_integrity.py -q
git diff --check
```
