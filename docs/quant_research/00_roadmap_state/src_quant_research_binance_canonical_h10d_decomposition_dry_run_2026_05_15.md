# binance_canonical_h10d Oversized-Module Decomposition Dry-Run

`Status: read-only owner-gated dry-run`
`Scope: src/enhengclaw/quant_research/binance_canonical_h10d.py oversized-module decomposition`
`Date: 2026-05-15`
`Mode: docs-only governance artifact; no source refactor approved`

## Decision

`binance_canonical_h10d.py` needs a facade-first decomposition plan before any
source movement.

Do not split this module directly. It is not merely oversized; it is a factual
runtime facade for the current Binance PIT h10d hardening lane, and tests/scripts
already rely on both public and near-private names from the root module.

The next approved step is a separate implementation plan, not code movement.

## Read-Only Evidence

Current module shape:

- `src/enhengclaw/quant_research/binance_canonical_h10d.py`
  - about 3,816 lines;
  - 102 top-level functions;
  - 1 dataclass: `BinanceCanonicalDataset`;
  - explicitly allowlisted by `tests/test_static_contracts.py` as an oversized
    Python file.
- `tests/test_binance_canonical_h10d.py`
  - directly imports current root names such as `aggregate_1m_klines`,
    `prepare_scored_backtest_frame`, `compute_position_attribution`,
    `build_paper_shadow_execution_ledger`, `run_binance_core_ablations`,
    `_run_falsification_suite`, `_validation_status`, and
    `_funding_cost_status`.
- `scripts/quant_research/run_binance_canonical_h10d_validation.py`
  - imports `DEFAULT_CONFIG_PATH`, `DEFAULT_STORE_ROOT`,
    `DEFAULT_FUNDING_COST_ROOT`, `DEFAULT_OUTPUT_ROOT`, `DEFAULT_REPORT_ROOT`,
    and `run_binance_canonical_validation` from the root module.
- Existing watchlist:
  - `src_quant_research_binance_canonical_h10d_execution_private_helper_watchlist_2026_05_15.md`
    records that this module imports private helpers from
    `execution_backtest.py`.

## Current Responsibility Map

| responsibility | representative current names | governance read |
| --- | --- | --- |
| config and path defaults | `ROOT`, `DEFAULT_CONFIG_PATH`, `DEFAULT_STORE_ROOT`, `DEFAULT_FUNDING_COST_ROOT`, `DEFAULT_OUTPUT_ROOT`, `DEFAULT_REPORT_ROOT`, `load_strategy_config`, `default_strategy_config` | path-sensitive runtime surface |
| archive/data foundation | `aggregate_1m_klines`, `build_binance_canonical_dataset`, `build_symbol_feature_frame`, `_read_kline_path`, `_coerce_kline_frame`, `_symbol_partition_paths` | candidate internal slice, but keep facade exports |
| funding-cost sync | `sync_funding_cost_history`, `fetch_funding_rate_rows`, `write_funding_cost_rows`, `load_funding_cost_daily`, `attach_funding_cost_to_panel`, funding path helpers | data-sync adjacent and path-sensitive |
| PIT universe and eligibility | `freeze_binance_ohlcv_universe`, `apply_point_in_time_rolling_universe`, `add_pit_strategy_eligibility`, `_pit_recent_data_eligible` | current h10d hardening surface |
| feature scoring and purity | `validate_alpha_feature_columns`, `assert_alpha_feature_purity`, `score_binance_ohlcv_core`, `prepare_scored_backtest_frame`, `add_binance_ohlcv_core_features` | behavior-sensitive alpha surface |
| risk brakes | `add_short_squeeze_veto_multiplier`, `add_binance_risk_brake_columns`, `_add_high_vol_rebound_short_brake` | active strategy hardening surface |
| validation and falsification | `run_binance_canonical_validation`, `_run_falsification_suite`, `_run_stratified_repeated_symbol_holdout`, `_validation_status`, `_funding_cost_status`, `_rank_ic_summary` | gate/status surface |
| attribution and paper ledger | `compute_position_attribution`, `compute_factor_leave_one_out_attribution`, `build_paper_shadow_execution_ledger`, `run_binance_core_ablations` | high-risk execution-helper dependent surface |
| reporting and artifact writes | `write_validation_artifacts`, `_write_universe_membership`, `_render_markdown_report`, `_write_json` | report/artifact contract surface |

## Facade-First Boundary

`src/enhengclaw/quant_research/binance_canonical_h10d.py` must remain the stable
facade until a later implementation plan proves compatibility.

Future extracted modules, if approved, must be internal implementation modules
behind root re-exports. Existing script and test imports should continue to work
unchanged unless a separate owner-approved compatibility break is documented.

The root facade must continue to expose, at minimum:

- runtime constants used by scripts:
  - `DEFAULT_CONFIG_PATH`
  - `DEFAULT_STORE_ROOT`
  - `DEFAULT_FUNDING_COST_ROOT`
  - `DEFAULT_OUTPUT_ROOT`
  - `DEFAULT_REPORT_ROOT`
- primary runtime entry:
  - `run_binance_canonical_validation`
- config and dataset surfaces:
  - `load_strategy_config`
  - `default_strategy_config`
  - `BinanceCanonicalDataset`
  - `aggregate_1m_klines`
  - `build_binance_canonical_dataset`
  - `build_symbol_feature_frame`
  - `freeze_binance_ohlcv_universe`
  - `apply_point_in_time_rolling_universe`
- feature and scoring surfaces imported by tests:
  - `ALLOWED_ALPHA_FEATURES`
  - `validate_alpha_feature_columns`
  - `score_binance_ohlcv_core`
  - `prepare_scored_backtest_frame`
  - `add_binance_ohlcv_core_features`
  - `add_binance_risk_brake_columns`
- attribution, ledger, and validation surfaces:
  - `compute_position_attribution`
  - `compute_factor_leave_one_out_attribution`
  - `build_paper_shadow_execution_ledger`
  - `run_binance_core_ablations`
  - `_run_falsification_suite`
  - `_validation_status`
  - `_funding_cost_status`

This list is a compatibility floor, not approval to add a broad static contract.

## Candidate Internal Modules

These names are planning placeholders. They are not approved paths.

| tentative module | possible contents | risk |
| --- | --- | --- |
| `_binance_canonical_config.py` | path defaults, strategy config loading, labels, alpha feature constants | medium because scripts import defaults |
| `_binance_canonical_archive.py` | kline path reads, 1m aggregation, symbol feature frame construction, dataset manifest/gap audit | medium because archive path semantics are fragile |
| `_binance_canonical_funding.py` | funding API rows, partition writes, daily funding cost attach/status helpers | medium/high because data-sync and default funding roots are path-sensitive |
| `_binance_canonical_features.py` | OHLCV feature construction, alpha purity checks, core score, PIT eligibility helpers | high because alpha behavior must not drift |
| `_binance_canonical_validation.py` | validation runner internals, falsification, stratified holdout, status helpers | high because it gates promotion/readiness |
| `_binance_canonical_execution_analysis.py` | position attribution, factor LOO, paper shadow ledger, ablations, execution helper adapters | high because it depends on `execution_backtest.py` private helpers |
| `_binance_canonical_reporting.py` | artifact writing and markdown rendering | medium because docs/artifact paths are referenced in research evidence |

If implemented, each slice should move behind root re-exports in a small commit,
with tests proving unchanged importability and behavior for that slice.

## Explicit Do Not Do

Do not:

- move, rename, or delete `binance_canonical_h10d.py`;
- change `scripts/quant_research/run_binance_canonical_h10d_validation.py` CLI
  compatibility as part of a decomposition-only change;
- change `DEFAULT_*` path semantics;
- change active h10d validation, live-readiness, promotion, or fail-closed gate
  status;
- change formulas, feature weights, alpha purity rules, risk brakes, or
  validation thresholds;
- rename private imports from `execution_backtest.py` without an explicit
  execution facade plan;
- broaden this into an `execution_backtest.py` refactor;
- create a whole-module static contract freezing every function in
  `binance_canonical_h10d.py`;
- move data artifacts, reports, or configs while decomposing source.

## Required Implementation Plan Before Code Movement

A future implementation plan must include:

- exact target slice and tentative internal module name;
- import report for scripts, tests, and src callers of all moved names;
- root facade re-export strategy;
- whether any near-private `_name` must remain import-compatible;
- `execution_backtest.py` private-helper dependency impact;
- artifact and config path impact;
- rollback plan;
- validation command list;
- explicit non-goals.

## Minimum Validation Commands

Run before and after any future implementation touching this boundary:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -q
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
python -m pytest tests\test_static_contracts.py -q
git diff --check
```

Add narrower tests when the target slice is known:

- archive/data slice:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -k "aggregation or archive or funding or symbol_feature" -q
```

- feature/risk-brake slice:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -k "feature or purity or risk_brake or high_vol_rebound" -q
```

- validation/falsification slice:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -k "validation_status or falsification or holdout" -q
```

- attribution/ledger slice:

```powershell
python -m pytest tests\test_binance_canonical_h10d.py -k "attribution or ledger or ablation or cost" -q
python -m pytest tests\test_execution_backtest.py -k "quality_bucket_pairs or pair" -q
```

## Current Recommendation

Approve a docs-only facade-first decomposition plan as the next governance step.
Do not approve source movement yet.

The first possible code implementation, after plan approval, should target one
low-blast-radius slice behind root re-exports. The current best candidates are
report rendering or pure archive helpers. Attribution, paper ledger, validation
status, risk brakes, funding sync, and execution-helper adapters should remain
owner-gated until their behavior coverage is explicitly named.
