# Parallel 1h Fake-Liquidity Age Sidecar Preregistration

`Snapshot date: 2026-05-07`
`Status: preregistered before strict simulator run`
`Scope: R-2 cross_sectional_intraday_1h rejected parent-interaction redesign`

## Boundary

This is a research-only redesign after the aggregate fake-liquidity parent
interaction failed strict symbol holdout. It is not h10d promotion evidence,
not live-trading evidence, and not a post-hoc symbol exclusion list.

The canonical h10d parent remains `v5_rw_bridge_no_overlay_h10d` and is not
modified.

## Pre-Registered Rule

Primary sidecar:

```text
age_30_180d_aggregate_haircut =
  capacity_haircut_candidate_flag
  AND fake_liquidity_capacity_haircut_flag
  AND 30 <= symbol_history_age_days_at_event < 180
```

Where `symbol_history_age_days_at_event` is computed from each symbol's first
local 1h row in the research frame. It is a local-history-age proxy, not a true
listing-age feed.

The simulator will compare:

- `hard_veto`: set sidecar rows to zero short exposure;
- `quarter_size`: set sidecar rows to 25% short exposure;
- `soft_multiplier`: set sidecar rows to 50% short exposure.

No individual symbol may be excluded by name. The known CoinGlass spot
concordance watchlist `SYRUP/SUN/LUNC/WIF` is not a rescue rule.

## Admission Rule

A variant can pass only if all of the following clear on the full symbol set:

- h24 gross PnL per candidate improves versus the unit-short parent;
- h24 adverse 5% squeeze tail falls;
- same-timestamp policy shuffle passes;
- same-timestamp label shuffle passes;
- symbol time-shift policy shuffle passes;
- symbol holdout consistency is at least `0.60`;
- liquidity-bucket consistency passes;
- +1h, +6h, and +24h delay robustness pass.

If the primary sidecar fails, the R-2 fake-liquidity branch remains rejected.
Split bins such as `30_90d` and `90_180d` may be reported as diagnostics only;
they are not the primary admission target in this run.
