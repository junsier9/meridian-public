# Research Cycle Snapshot

## Metadata

- `object_id`:
- `cycle_id`:
- `cycle_date`:
- `asset`:
- `scope`: `spot+perp`
- `thesis_status_before`: `watch | active thesis | invalidated`

## Skill Snapshot Sources

- `info-flow`:
- `CEX / CoinMarketCap / CoinAnk`:
- `onchain-tools / Nansen / Dune`:
- `security / audit`:

## Observation

One short paragraph describing the current market state and why this thesis is worth attention.

## Evidence

List the strongest supporting facts from the current snapshot.

## Risk

List invalidation conditions, opposing evidence, or reasons the thesis might fail.

## Next Step

State the single highest-value question or evidence gap for the next cycle.

## Pain Log Check

- `gap_category`: `ohlcv_history | onchain_timeseries | structured_news_archive | other | none`
- `blocking`: `true | false`
- `missing_question`:
- `notes`:
- `candidate_api_type`: `market_history_api | onchain_data_api | news_archive_api | none`

## Suggested Commands

```powershell
python examples\governed_agent_ingress_demo.py market_observer `
  --artifacts-root artifacts\research_workbench\<object_id> `
  --object-id <object_id> `
  --subject <asset> `
  --scope spot+perp `
  --observation-text "<observation>" `
  --compiler-backend deterministic
```

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
