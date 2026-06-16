# External OpenClaw Scheduled Research Deployment

This is the canonical scheduler-safe path when you want to:

- use one upstream market scan to select `1-3` research-worthy assets from the open market
- use external OpenClaw plus Skills to produce one normalized research snapshot per selected asset
- compile each research cycle through the shipped OpenClaw adapters with a live OpenAI backend
- retain every cycle under the thesis workbench
- avoid real-time provider ingestion, 24h shadow, and the formal OpenClaw deployment gate

This workflow is intentionally:

- `research-only`
- `one-shot`
- `permit-backed`
- `trust-root validated`
- `live compiler` first
- `pool-summary aware`
- `api-reminder gated`

It is not:

- a 24h monitoring path
- a streaming runtime
- a formal OpenClaw deployment decision path
- a seconds-level freshness system

## 1. Operating Model

The scheduler now runs as a simple two-layer system:

1. one upstream market scan
2. one downstream thesis-cycle consumer

The market scan is a pure selector:

```powershell
python scripts\openclaw\run_openclaw_research_scan.py --market-scan <MarketScanJsonPath>
```

The cycle consumer stays the thesis/workbench writer:

```powershell
python scripts\openclaw\run_openclaw_research_cycle.py --snapshot <SnapshotJsonPath>
```

Each market scan does exactly this:

1. load one normalized open-market scan generated upstream by external OpenClaw + Skills
2. exclude stablecoins and pegged assets
3. map candidates into `large_cap / mid_cap / small_cap` by market-cap rank
4. assign one stable `strategy_profile` per candidate:
   - `conservative`
   - `balanced`
   - `aggressive`
5. prioritize missing bucket coverage first
6. emit at most `3` normalized cycle snapshots into `artifacts\research_workbench\_incoming`

Each research cycle then does exactly this:

1. load one normalized snapshot generated upstream by external OpenClaw + Skills
2. provision one fresh external execution permit under the research-specific external root
3. map lane env from `OPENCLAW` or existing dedicated `ENHENGCLAW_<LANE>_*` overrides
4. create the thesis object on first sight through `market_observer`
5. continue the same thesis through:
   - `evidence_agent`
   - `risk_signal_agent`
   - `research_synthesizer`
   - `research_lead`
6. append pain-log evidence and update the workbench-level API-gap and pool summaries

Default scheduler assumption:

- market scan runs twice daily in `Asia/Shanghai`
- cycle consumer continues hourly and only consumes `_incoming`

This path is one-shot and works with:

- Linux `cron`
- Windows Task Scheduler

## 2. Market-Scan Contract

The upstream market-scan file must be one JSON file with:

- `scan_id`
- `scan_date`
- `generated_at_utc` (optional)
- `candidates` as a non-empty array

Each candidate must provide:

- `subject`
- `spot_symbol` (optional)
- `usdm_symbol` (optional)
- `market_cap_rank`
- `scope` (optional; defaults to `spot+perp`)
- `structure_clarity_score`
- `liquidity_score`
- `catalyst_score`
- `risk_boundary_score`
- `volatility_score`
- `observation`
- `evidence`
- `risk`
- `next_step`
- `is_stablecoin` (optional; defaults to `false`)
- `is_pegged_asset` (optional; defaults to `false`)

Optional per-candidate pain log:

- `gap_category`
- `blocking`
- `missing_question`
- `notes`

Tracked template:

- `docs\templates\market_research\openclaw_research_market_scan_template.json`

The fixed bucket rule is:

- `large_cap = rank 1-20`
- `mid_cap = rank 21-100`
- `small_cap = rank 101-300`

The fixed selection rule is:

- fill missing `large_cap / mid_cap / small_cap` coverage first
- then rank remaining candidates by structure, liquidity, catalyst, and risk-boundary quality
- emit at most `3` snapshots per scan
- keep each thesis at no more than `2` cycles per day

## 3. Snapshot Contract

The scheduler-facing snapshot must be one JSON file with:

- `cycle_id`
- `cycle_date`
- `object_id`
- `subject`
- `scope` (optional; defaults to `spot+perp`)
- `strategy_profile`
- `asset_bucket`
- `observation`
- `evidence`
- `risk`
- `next_step`

Optional:

- `pain_log`
- `market_symbols`
- `history_coverage`
- `ohlcv_context_ref`

`pain_log` fields:

- `gap_category`
- `blocking`
- `missing_question`
- `notes`

Tracked template:

- `docs\templates\market_research\openclaw_research_snapshot_template.json`

Allowed snapshot metadata values:

- `strategy_profile = conservative | balanced | aggressive`
- `asset_bucket = large_cap | mid_cap | small_cap`

The repo treats `strategy_profile` and `asset_bucket` as thesis-stable metadata in v1.
If a thesis genuinely changes category, open a new `object_id` instead of reclassifying in place.

The repo-side wrappers do not scrape websites or call Skills directly. External OpenClaw + Skills must produce the normalized market scan and the normalized cycle snapshots before the scheduled consumer runs.

When `spot_symbol` / `usdm_symbol` are omitted, the repo tries `<subject>USDT` against the local Binance symbol catalog and records the result into:

- `market_symbols`
- `history_coverage`
- `ohlcv_context_ref`

Each selected scan candidate writes an OHLCV context bundle before it lands in `_incoming`, and each cycle retains:

- `ohlcv_context.json`
- `ohlcv_context.md`

## 4. Commands

Provision the research-specific external inputs directly:

```powershell
python scripts\openclaw\provision_openclaw_research_inputs.py
```

Run one upstream market scan:

```powershell
python scripts\openclaw\run_openclaw_research_scan.py `
  --market-scan <MarketScanJsonPath> `
  --workbench-root artifacts\research_workbench
```

Sync research-only Binance OHLCV history:

```powershell
python scripts\market_data\sync_binance_ohlcv.py `
  --mode refresh `
  --markets "spot,usdm_perp" `
  --intervals "1h,4h,1d" `
  --workbench-root artifacts\research_workbench
```

For first-time backfill on new symbols:

```powershell
python scripts\market_data\sync_binance_ohlcv.py `
  --mode bootstrap `
  --markets "spot,usdm_perp" `
  --intervals "1h,4h,1d" `
  --symbols ETHUSDT SUIUSDT JTOUSDT
```

Run one research cycle:

```powershell
python scripts\openclaw\run_openclaw_research_cycle.py `
  --snapshot <SnapshotJsonPath> `
  --workbench-root artifacts\research_workbench `
  --compiler-backend live
```

Optional knobs:

- `--external-root <path>`
- `--trust-root-dir <path>`
- `--expires-after-hours <N>`
- `--compiler-backend deterministic`
- `--incoming-root <path>` on the scan side
- `--max-snapshots <N>` on the scan side

Default assumptions:

- `OPENCLAW` is enough in a clean session
- `scope` defaults to `spot+perp`
- thesis root is `artifacts\research_workbench\<object_id>`
- market scans emit no more than `3` snapshots per run
- Binance OHLCV sync is research-only and stays outside the realtime shadow stack

## 5. Object, Cycle, And Pool Retention

Each thesis lives under:

- `artifacts\research_workbench\<object_id>`

Each thesis also keeps:

- `thesis_profile.json`
- `pain_log.csv`

Each cycle lives under:

- `artifacts\research_workbench\<object_id>\cycles\<cycle_id>`

Each cycle retains:

- `snapshot.normalized.json`
- one `*.request.json` per attempted lane
- one `*.response.json` per attempted lane
- one `*.stdout.log` per attempted lane
- one `*.stderr.log` per attempted lane
- `cycle_summary.json`

The workbench root keeps:

- `api_gap_summary.json`
- `api_gap_summary.md`
- `research_pool_summary.json`
- `research_pool_summary.md`

The market-scan side keeps:

- `artifacts\research_workbench\_scan_runs\<scan_id>\scan_summary.json`

The wrapper is create-on-first-sight:

- if the thesis object does not yet exist, it runs `market_observer`
- if it already exists, it skips `market_observer`

`market_observer` remains the only create-new OpenClaw lane. The other research lanes remain resume-only.

Later-cycle `observation` text is still retained and is folded into the generated `research_synthesizer` request text, but it is not used to recreate the object.

## 6. API Reminder And Pool Summary Behavior

Allowed pain categories:

- `ohlcv_history`
- `onchain_timeseries`
- `structured_news_archive`
- `other`

Automatic reminders stay advisory and never fail the cycle.

A reminder triggers only when one category reaches at least one threshold:

- `>= 3` thesis objects
- `>= 5` research cycles
- `>= 2` blocking thesis objects

Category-to-API mapping:

- `ohlcv_history` -> `行情历史 API`
- `onchain_timeseries` -> `链上数据 API`
- `structured_news_archive` -> `资讯归档 API`

If multiple categories cross threshold, choose:

1. highest total frequency
2. then higher blocking count
3. then add only one API class next

The pool summary is also where v1 classification is meant to be observed:

- thesis count
- `strategy_profile` distribution
- `asset_bucket` distribution
- pain-gap counts grouped by profile and bucket
- missing coverage, such as no current `small_cap` thesis

If Skills are no longer enough for research-grade strategy, this is the signal to add one external historical-data API rather than jumping straight to a real-time pipeline.

## 7. Explicit Separation

This path must remain separate from:

- `python scripts\verify\run_openclaw_deployment_readiness.py`
- `python scripts\verify\run_real_24h_shadow_bundle.py`

It also remains separate from the manual deterministic workflow in:

- `docs\MINIMAL_MARKET_RESEARCH_WORKFLOW.md`

Recommended progression:

1. manual deterministic workbench
2. scheduled external OpenClaw market scans plus hourly thesis consumers
3. external historical-data API only if the reminder thresholds justify it
4. real-time data layer only if seconds-level freshness becomes necessary
