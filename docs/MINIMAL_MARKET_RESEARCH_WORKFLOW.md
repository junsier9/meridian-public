# Minimal Market Research Workflow

This workflow is the canonical low-friction way to do market research in this repo without depending on real-time provider ingestion, the 24h shadow bundle, or the OpenClaw deployment boundary.

It exists for one purpose:

- let operators use existing Skills to gather market snapshots
- turn those snapshots into one reusable thesis object
- keep research evidence inside the repo's existing governed object flow
- leave a clean upgrade path to `live` compilers or real-time pipelines later

This workflow is intentionally:

- `hybrid`
- `swing thesis` oriented
- `manual snapshot` driven
- `deterministic backend` first
- `pain-log gated` for future API expansion

## 1. When To Use This Workflow

Use this workflow when you want to:

- research a token, narrative, sector, or setup
- track a thesis across multiple sessions
- keep evidence, risks, and next steps attached to one object
- avoid real-time transport/operator complexity while research is still human-driven

Do not treat this workflow as:

- a 24h monitoring pipeline
- a real-time alerting system
- an execution or auto-trading path
- an OpenClaw deployment path

## 2. Inputs

Each research cycle starts from one manual snapshot assembled from existing Skills.

Recommended sources:

- `info-flow`: news, X, project updates, narrative changes
- `CEX / CoinMarketCap / CoinAnk`: price, volume, ranking, funding, market structure
- `onchain-tools / Nansen / Dune`: wallet behavior, flows, protocol activity, smart money
- `security / audit`: token risk, address risk, contract warnings, abnormal signals

Each cycle should compress the snapshot into four short texts:

- `observation`: what the market currently looks like
- `evidence`: the strongest supporting facts
- `risk`: invalidation conditions or opposing evidence
- `next_step`: what must be checked next

Do not dump raw webpages or long tool output into repo artifacts.

## 3. Object Model

Use one fixed `object_id` per thesis.

Recommended format:

- `<asset>-<theme>-<yyyymmdd>`

Example:

- `sol-breakout-20260419`

Use one fixed artifact root per thesis:

- `artifacts\research_workbench\<object_id>`

For the multi-asset pilot, also assign two stable v1 metadata labels per thesis:

- `strategy_profile = conservative | balanced | aggressive`
- `asset_bucket = large_cap | mid_cap | small_cap`

Treat both as thesis-stable metadata in v1.
If a thesis genuinely needs to change profile or bucket, open a new `object_id` instead of reclassifying in place.

Reuse the same:

- `object_id`
- `artifacts-root`

for the full life of the thesis.

Recommended watchlist size:

- `5-10` names on the standing watchlist
- `1-3` active thesis objects per cycle

Recommended pilot size:

- target `8` thesis objects
- minimum `5`
- at least `2` cycles per thesis
- at least `16` total cycles before deciding whether a new API is needed

For the open-market pilot, bucket coverage should also include:

- at least one `large_cap` thesis
- at least one `mid_cap` thesis
- at least one `small_cap` thesis

Default scope for crypto research:

- `spot+perp`

## 4. Minimal Slice Chain

The minimal research chain uses only five existing slices:

1. `market_observer`
2. `evidence_agent`
3. `risk_signal_agent`
4. `research_synthesizer`
5. `research_lead`

This chain is enough to:

- create a thesis object
- add support
- add invalidation
- summarize current conviction
- define the next research action

Leave these out of v1:

- `validation_agent`
- `risk_governance_agent`

Add them only when a thesis is close to publication, external communication, or stricter review.

## 5. Canonical Commands

All commands below intentionally use:

- `examples\governed_agent_ingress_demo.py`
- `--compiler-backend deterministic`

That keeps the workflow independent from real-time pipelines and model env configuration.

### Create the thesis object

```powershell
python examples\governed_agent_ingress_demo.py market_observer `
  --artifacts-root artifacts\research_workbench\<object_id> `
  --object-id <object_id> `
  --subject <asset> `
  --scope spot+perp `
  --observation-text "<observation>" `
  --compiler-backend deterministic
```

### Add supporting evidence

```powershell
python examples\governed_agent_ingress_demo.py evidence_agent `
  --artifacts-root artifacts\research_workbench\<object_id> `
  --object-id <object_id> `
  --subject <asset> `
  --scope spot+perp `
  --evidence-text "<evidence>" `
  --compiler-backend deterministic `
  --skip-seed
```

### Add invalidation or opposing risk

```powershell
python examples\governed_agent_ingress_demo.py risk_signal_agent `
  --artifacts-root artifacts\research_workbench\<object_id> `
  --object-id <object_id> `
  --subject <asset> `
  --scope spot+perp `
  --risk-text "<risk>" `
  --compiler-backend deterministic `
  --skip-seed
```

### Update the current synthesis

```powershell
python examples\governed_agent_ingress_demo.py research_synthesizer `
  --artifacts-root artifacts\research_workbench\<object_id> `
  --object-id <object_id> `
  --subject <asset> `
  --scope spot+perp `
  --synthesis-text "<current synthesis>" `
  --compiler-backend deterministic `
  --skip-seed
```

### Set the next research action

```powershell
python examples\governed_agent_ingress_demo.py research_lead `
  --artifacts-root artifacts\research_workbench\<object_id> `
  --object-id <object_id> `
  --subject <asset> `
  --scope spot+perp `
  --directive-text "<next step>" `
  --compiler-backend deterministic `
  --skip-seed
```

## 6. Default Research Cadence

For `swing thesis` work:

- active market regime: `1-2` cycles per day
- normal regime: `3` cycles per week

Each cycle should do exactly this:

1. pull one manual snapshot from Skills
2. compress it into `observation / evidence / risk / next_step`
3. write those texts into the existing thesis object
4. inspect the resulting synthesis and next step

Use these tracked templates during the pilot:

- `docs\templates\market_research\watchlist_template.csv`
- `docs\templates\market_research\cycle_snapshot_template.md`
- `docs\templates\market_research\pain_log_template.csv`

## 7. Thesis Status Convention

Do not add a new status system yet.

Use these three human conventions inside the text you write to the object:

- `watch`
- `active thesis`
- `invalidated`

Recommended meaning:

- `watch`: still observing, no strong direction yet
- `active thesis`: direction exists, still needs follow-up evidence
- `invalidated`: the risk case triggered; stop allocating further research budget

In v1, express status through:

- `risk_signal_agent` text
- `research_lead` text

instead of introducing new code or schema.

## 8. Pain Log And API Trigger Rules

Each completed cycle must log whether a real data gap appeared.

Allowed gap categories:

- `ohlcv_history`
- `onchain_timeseries`
- `structured_news_archive`
- `other`

Each pain-log row should record at least:

- `object_id`
- `cycle_date`
- `cycle_id`
- `gap_category`
- `blocking`
- `missing_question`
- `notes`
- `candidate_api_type`

Count a gap only when it genuinely blocked or degraded thesis judgment.
Do not count optional curiosity or "nice to have" data.

API expansion is allowed only when at least one of these thresholds is met:

- the same gap category appears in `>= 3` thesis objects
- the same gap category appears in `>= 5` research cycles
- the same gap category causes `>= 2` thesis objects to remain undecided instead of reaching `active thesis` or `invalidated`

Map pain categories to future API classes like this:

- `ohlcv_history` -> market history API
- `onchain_timeseries` -> onchain data API
- `structured_news_archive` -> structured news/archive API

If more than one category reaches threshold:

1. choose the category with the highest total frequency
2. break ties by higher blocking count
3. add only one API class in the next phase

## 9. Pilot Execution Rules

The pilot should use:

- one standing watchlist of `8` names or one equivalent open-market shortlist per scan
- `1-3` active thesis objects per cycle
- the same `object_id` and artifact root reused for every follow-up cycle

If you use the scheduled external scan path, the intended v1 order is:

1. run one open-market scan upstream
2. let it emit at most `3` classified snapshots
3. let the hourly consumer write those snapshots into thesis/workbench
4. review pool coverage before adding more inputs

The pilot is complete only after:

- at least `5` thesis objects exist
- target `8` thesis objects have been attempted
- each completed thesis has at least `2` cycles
- total completed cycles are at least `16`

At the end of the pilot, answer only these decision questions:

- is OHLCV history the most frequent real blocker?
- is onchain time-series the most frequent real blocker?
- is structured news archive the most frequent real blocker?

If none reaches threshold, continue using Skills only.
If one reaches threshold, add only that one API class next.

## 10. Acceptance Criteria

This workflow is working when:

- you can create one thesis object for one asset
- you can reuse the same `object_id` in later sessions
- you can add evidence, risk, synthesis, and next step without real-time ingestion
- each cycle leaves object-based artifacts under `artifacts\research_workbench\<object_id>\...`
- one full cycle takes roughly `15-20` minutes
- the pilot leaves one pain log with enough evidence to justify either "no API needed yet" or "one specific API class should be added next"

## 11. Explicit Non-Goals

This workflow does not require:

- `scripts\verify\run_real_24h_shadow_bundle.py`
- `scripts\verify\run_openclaw_deployment_readiness.py`
- real-time provider soak or shadow pipelines
- external execution permits
- read-only trust-root setup
- `ENHENGCLAW_<LANE>_*` live model env vars

## 12. Upgrade Path

When the research process becomes stable, upgrade in two steps only:

1. `deterministic -> live`
2. manual snapshots -> scheduled or real-time inputs

Keep the same:

- `object_id`
- artifact root
- five-slice chain

so research history remains continuous.

For the scheduled external OpenClaw version of step 2, use:

- `docs\EXTERNAL_OPENCLAW_RESEARCH_DEPLOYMENT.md`
- `docs\templates\market_research\openclaw_research_snapshot_template.json`
- `docs\templates\market_research\openclaw_research_market_scan_template.json`
