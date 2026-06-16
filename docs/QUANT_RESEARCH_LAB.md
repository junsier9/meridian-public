# Quant Research Lab

> **Supersession note (2026-05-13):** This is a historical lab runbook and
> command archive. For current quant-research state, start from
> [`quant_research_roadmap_state_2026_05_12.md`](quant_research/quant_research_roadmap_state_2026_05_12.md);
> for script execution priority, use
> [`scripts/quant_research/README.md`](../scripts/quant_research/README.md).
> Do not treat older `active`, `pass`, or promotion examples below as current
> roadmap status without checking those entrypoints first.

This subsystem adds a deterministic, history-driven quant workflow parallel to the existing thesis/workbench flow.

## Scope

- Research-only
- Historical-data driven
- Single-asset `4h` models
- Cross-sectional `1d` models
- `train / validation / test + walk-forward`
- Registry + bridge back into `artifacts/research_workbench/_incoming`

## Main Entrypoints

```powershell
python scripts\quant_research\run_quant_research_cycle.py --as-of 2026-04-20 --compiler-backend deterministic
```

If `%LOCALAPPDATA%\EnhengClaw\market_history\coinapi_ohlcv` exists, the daily and weekly Python entrypoints now auto-detect it as the default `spot_ohlcv_external_root`. You only need to pass `--spot-ohlcv-external-root` when overriding that default.

If this repo still carries the legacy Cartesian-product strategy inventory, cut it over to the thesis-task queue before the next daily or weekly run:

```powershell
python scripts\quant_research\run_quant_strategy_library_thesis_cutover.py --as-of 2026-04-22
```

If overlap interval evidence has been invalidated, run remediation before rerunning any affected day:

```powershell
python scripts\quant_research\run_quant_overlap_rerun_remediation.py
python scripts\quant_research\run_quant_overlap_rerun_remediation.py --as-of 2026-04-20
```

Remediation only marks affected canonical experiments as `needs_rerun_after_overlap_fix`; it does not retrain them. After remediation, rerun each affected day with `run_quant_research_cycle.py --as-of <date>`. Experiments in `needs_rerun_after_overlap_fix` are historical evidence only and must not count toward pass-rate, promotion, or bridge decisions.

Historical reruns also require `as_of`-aligned derivatives evidence. `last_sync_summary.json` is not sufficient for reruns because it only describes the latest sync pointer. Before rerunning any historical day, build a frozen `by_as_of` summary from the existing derivatives store:

```powershell
python scripts\quant_research\run_quant_derivatives_sync_evidence.py --as-of 2026-04-20 --provider auto
python scripts\quant_research\run_quant_research_cycle.py --as-of 2026-04-20 --compiler-backend deterministic
python scripts\quant_research\run_quant_overlap_legacy_cleanup.py --as-of 2026-04-20
```

The rerun gate now resolves derivatives evidence from:

- `%LOCALAPPDATA%\EnhengClaw\market_history\binance_derivatives\summaries\by_as_of\<as_of>\sync_summary.json`

If that archived summary does not exist, or if its `as_of` / `window_end_ms` contract is invalid, the historical rerun fails closed.

`run_quant_research_cycle.py` now also auto-archives superseded overlap-rerun experiment dirs after it writes the new canonical daily manifest. The one-off cleanup script is still useful for historical backfills that were rerun before this rule existed.

Validation validity is now fail-closed as well. A canonical experiment cannot remain `pass` or `publishable_*` unless `validation_report.json` includes:

- `split_integrity`
- `walk_forward_assessment`
- `execution_stress`
- `regime_holdout`
- `validation_contract`

If checked-in canonical `pass/publishable` experiments predate this contract, invalidate them before treating any historical metrics as decisive:

```powershell
python scripts\quant_research\run_quant_validation_contract_remediation.py
python scripts\quant_research\run_quant_validation_contract_remediation.py --as-of 2026-04-20
python scripts\quant_research\run_quant_research_cycle.py --as-of 2026-04-20 --compiler-backend deterministic
```

Experiments rewritten to `invalidated` with reason `validation_contract_v2_pending_rerun` are historical evidence only and must not count toward pass-rate, promotion, or bridge decisions.

```powershell
python scripts\quant_research\run_quant_coinapi_spot_sync.py --as-of 2026-04-20 --mode bootstrap --refresh-catalog
```

```powershell
python scripts\quant_research\run_quant_strategy_proposal_cycle.py --week-of 2026-04-20 --compiler-backend live
```

```powershell
python scripts\quant_research\run_quant_derivatives_sync_cycle.py --as-of 2026-04-20 --provider auto --mode refresh
```

```powershell
python scripts\quant_research\export_passed_alphas_to_workbench.py --as-of 2026-04-20
```

```powershell
python scripts\quant_research\run_quant_ohlcv_lane_ab.py --as-of 2026-04-20 --compiler-backend deterministic
```

## Input Contract

Drop normalized quant universe inputs under:

`artifacts\quant_research\_quant_inputs`

Each file should look like:

```json
{
  "as_of": "2026-04-20",
  "generated_at_utc": "2026-04-20T03:30:00Z",
  "candidates": [
    {
      "subject": "ETH",
      "market_cap_rank": 2,
      "market_cap_usd": 350000000000,
      "quote_volume_24h_usd": 18000000000,
      "listing_age_days": 2200,
      "spot_symbol": "ETHUSDT",
      "usdm_symbol": "ETHUSDT",
      "event_flags": ["etf_flow"],
      "narrative_tags": ["large_cap_l1"]
    }
  ]
}
```

## Artifact Layout

- `artifacts\quant_research\universe\<as_of>\universe_snapshot.json`
- `artifacts\quant_research\datasets\<dataset_id>\panel.csv.gz`
- `artifacts\quant_research\features\<feature_set_id>\features.csv.gz`
- `artifacts\quant_research\experiments\<experiment_id>\...`
- `artifacts\quant_research\registry\alpha_registry.json`
- `artifacts\quant_research\bridge_exports\<as_of>\...`
- `artifacts\quant_research\governance\strategy_catalog.json`
- `artifacts\quant_research\governance\strategy_library.json`
- `artifacts\quant_research\governance\weekly_reviews\<iso_week>\weekly_governance_summary.json`
- `artifacts\quant_research\proposals\<iso_week>\<proposal_id>\proposal_spec.json`
- `artifacts\quant_research\proposals\<iso_week>\<proposal_id>\proposal_evaluation.json`

## Governance Model

- `strategy_library.json` is now a thesis-driven queue, not a baseline inventory grid.
- The seed library is fixed at `12` hand-written tasks; normal operation keeps the library between `10` and `20` entries.
- `Daily` quant cycle executes only the thesis tasks in `active`, `watch`, and `candidate`; the default seed mix targets full daily utilization.
- The default seed currently splits into:
  - `7` spot-only executable tasks
  - `5` derivatives-required meta-labeling tasks kept in the library but frozen out of the daily executable set until derivatives history is research-ready
- `Weekly` discovery still generates recipe artifacts, but it does not dump every passing proposal into the library.
- Weekly limits are:
  - `24` screened recipes
  - `12` full validations
  - `4` shortlisted promotions
  - `2` promotions to `active`
  - `2` net-new tasks per week
  - `4` in-place task revisions per week
- Proposal outcomes:
  - pass with `base_strategy_id` -> `update_existing_task`
  - pass without an existing base task -> `create_new_task`
  - fail / not-selected / candidate-only artifacts stay in weekly review outputs and do not become library entries
  - only `active + daily pass` strategies can bridge back into `artifacts\research_workbench\_incoming`

## Scheduling

- Daily runner script:
  - `scripts\quant_research\run_openclaw_quant_research_daily_cycle_runner.ps1`
- Daily CoinAPI spot sync runner script:
  - `scripts\quant_research\run_openclaw_quant_coinapi_spot_sync_runner.ps1`
- Registration script:
  - `scripts\quant_research\register_openclaw_quant_research_task.ps1`
- Daily CoinAPI spot sync registration script:
  - `scripts\quant_research\register_openclaw_quant_coinapi_spot_sync_task.ps1`
- Daily CoinAPI spot sync schedule:
  - `03:00` Asia/Shanghai
- Default schedule:
  - `03:45` Asia/Shanghai
- Weekly runner script:
  - `scripts\quant_research\run_openclaw_quant_strategy_proposal_cycle_runner.ps1`
- Weekly registration script:
  - `scripts\quant_research\register_openclaw_quant_strategy_proposal_task.ps1`
- Weekly schedule:
  - `Monday 05:15` Asia/Shanghai

## CoinAPI Sidecar

Quant Lab can now consume a CoinAPI-backed spot OHLCV sidecar without replacing the existing Binance path.

- Quant Top100 sync command:

```powershell
python scripts\quant_research\run_quant_coinapi_spot_sync.py --as-of 2026-04-20 --mode bootstrap --refresh-catalog
```

- Default CoinAPI root:
  - `%LOCALAPPDATA%\EnhengClaw\market_history\coinapi_ohlcv`
- Required credential:
  - environment variable `CoinAPI`
- Default exchange mapping:
  - `BINANCE` spot symbols quoted in `USDT`
- Local metadata outputs:
  - `symbol_catalog.json`
  - `exchange_mapping.json`
  - per-symbol interval `manifest.json`

To run Quant Lab in the mixed lane, keep Binance as the default OHLCV root for `usdm_perp` and fallback, and pass CoinAPI as the spot-only root:

```powershell
python scripts\quant_research\run_quant_research_cycle.py --as-of 2026-04-20 --compiler-backend deterministic --ohlcv-external-root "$env:LOCALAPPDATA\EnhengClaw\market_history\binance_ohlcv" --spot-ohlcv-external-root "$env:LOCALAPPDATA\EnhengClaw\market_history\coinapi_ohlcv"
```

Notes for Phase 1:

- The CoinAPI sidecar writes the same normalized partition layout as the Binance OHLCV store, so the existing dataset builders and bridge logic keep working.
- Quant steady-state sync is `Top100 -> 1d/4h` and `Top30 -> 1h`.
- Phase 1 only replaces `spot` OHLCV. Existing Binance `usdm_perp` and derivatives sync remain the source for perp bars, funding, and open-interest data.
- CoinAPI OHLCV does not expose exchange-reported quote-volume fields in the same shape as Binance, so `quote_volume` is estimated from `volume_traded * typical_price`; manifests mark this as `estimated_from_typical_price`.
- Daily monitoring and weekly proposal runners now consume a mixed lane by default:
  - `spot`: CoinAPI root first, then Binance spot fallback
  - `usdm_perp`: Binance OHLCV root
  - `derivatives`: Binance derivatives root
- One-off A/B comparisons write isolated artifacts under `artifacts\benchmarks\quant_ohlcv_lanes\...` and do not overwrite the main quant artifacts root.

## Data Readiness Contract

Quant Lab now fails closed on hypothesis-data mismatch before an experiment can claim to be executable.

- Config source:
  - `config\quant_research\data_readiness_contract.json`
- Daily cycle summary now records:
  - `spot_provider_lane`
  - `spot_subject_coverage`
  - `cross_sectional_executable_subject_count`
  - `blocked_strategy_ids`
  - `data_gap_blockers`
- Dataset manifests now carry `data_readiness` with the same compressed evidence.

Hard gates in v1:

- Cross-sectional theses must run in the mixed spot lane and must see at least `30` executable `large_cap + mid_cap` subjects.
- If the cross-sectional subject count is below `30`, the relevant experiments are written as `invalidated` with reason `cross_sectional_spot_history_gap`.
- Single-asset spot theses require both `spot 4h` and `spot 1d` history for the target subject. Missing either interval, or failing to form non-empty `train / validation / test` plus the validation-contract walk-forward window minimum, invalidates the experiment with reason `single_asset_spot_history_gap`.
- Derivatives-required theses are fail-closed until `funding` and `open_interest` each reach `train / validation / test >= 0.8` readiness with no provider-cap or start-gap warnings. Until then they remain in the library but are not daily-executable and cannot become `pass`, `publishable`, or bridged.
- `event_drift` is not an executable research family in v1. Static `event_flag_count` and `narrative_tag_count` remain metadata only; event hypotheses stay in artifacts/review until a real temporal event tape exists.

Practical implication:

- A manual Binance-only run is no longer allowed to silently produce a `3`-name pseudo cross-sectional panel and continue as if the run were valid.
- Mixed-lane spot breadth from the local CoinAPI sidecar is now the default path for real cross-sectional testing.

## Next Data Specs

The next provider-selection step is now a concrete data-gap problem, not an infrastructure problem. Use [quant_next_data_specs.md](quant_research/01_data_foundation/quant_next_data_specs.md) as the canonical checklist for:

- derivatives history needed to reopen meta-labeling, crowding, and regime-conditioned theses
- temporal event tape needed before any event-driven family can re-enter executable discovery

## Coinglass Derivatives

Quant Lab now supports a Coinglass-backed derivatives sync path for factor repair.

- Required environment variable:
  - `CoinglassAPI`
- Operator entrypoints:

```powershell
python scripts\quant_research\run_quant_derivatives_sync_cycle.py --as-of 2026-04-23 --provider auto --mode refresh
python scripts\quant_research\run_quant_derivatives_sync_cycle.py --as-of 2026-04-23 --provider coinglass --mode bootstrap
python scripts\quant_research\run_quant_derivatives_sync_evidence.py --as-of 2026-04-22 --provider auto
```

Provider behavior:

- `--provider auto`:
  - uses Coinglass when `CoinglassAPI` is present
  - otherwise falls back to the existing Binance derivatives sync
- `--provider coinglass`:
  - fails closed if `CoinglassAPI` is missing
- `--provider binance`:
  - forces the legacy Binance-only path

Current Coinglass-backed fields written into the shared derivatives store:

- `funding_rate`
- `open_interest`
- `open_interest_value`
- `perp_close`

Why this matters:

- Binance's native open-interest history contract is capped to the latest window and cannot support long-horizon falsification.
- Coinglass fills the long-history `funding/open_interest/open_interest_value` gap directly into the current factor pipeline.
- `perp_close` is also persisted so the lab can compute `basis_proxy` even when a dedicated `usdm_perp` OHLCV lane is missing for a symbol/interval.

## Notes

- Quant Lab uses `numpy`, `pandas`, and `scikit-learn`.
- It does not replace the thesis workflow.
- Only `active + pass` alphas are exported back into `_incoming`.
