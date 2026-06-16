# Provider Sidecar H10D Preregistration

`Snapshot date: 2026-05-17`
`Branch id: provider_sidecar_h10d`
`Status: pre-registered research branch; no live config change`
`Control: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget`

---

## Decision

Open a new provider-sidecar h10d research branch while keeping the current
`hv_balanced` live-pipeline candidate frozen as the control.

2026-06-02 baseline clarification:

- `hv_balanced:multiphase_10_sleeve` remains the live-operations control for
  this provider-sidecar branch because it is the documented remote live strategy
  lineage.
- General follow-on h10d research should attach to
  `v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve` by default: the score
  parent is `v5_rw_bridge_no_overlay_h10d`, while the portfolio construction
  baseline is 10-phase equal-sleeve.
- `v5_binance_pit_top_mid_h10d_pruned3_hv_tail_only_soft_budget` is a passed
  Binance-only PIT challenger, not the current remote live config and not the
  default follow-on research baseline.

This branch exists to answer one narrow question:

```text
Can PIT-safe provider sidecars improve the current Binance PIT h10d candidate,
first as a risk overlay and only later as a full alpha rescore?
```

It does not authorize live trading, does not mutate any live configuration, and
does not replace the current frozen control.

---

## Frozen Control

Control config:

```text
config/quant_research/binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget.json
```

Control report:

```text
docs/quant_research/02_binance_pit_h10d/binance_canonical_h10d_validation_2026_05_12_hv_balanced_soft_budget.md
```

Control metrics:

| metric | value |
| --- | ---: |
| base net return | 3.241191 |
| base Sharpe | 1.270 |
| base max DD | 0.279320 |
| stress net return | 3.202118 |
| stress Sharpe | 1.263 |
| stress max DD | 0.279618 |
| rebalance count | 183 |
| stratified repeated holdout | 13 / 16 positive folds |

Current live-pipeline rule:

```text
Do not edit live_trading configs or current Binance execution candidates for
this research branch.
```

---

## Provider Priority

First provider:

```text
CoinGlass
```

Reason:

- it is closest to the old canonical h10d parent sidecar layer;
- local catalogs already include participant, taker, liquidation, orderbook,
  OI, funding, ETF, on-chain, and options surfaces;
- the old canonical h10d parent had meaningful learned exposure to
  `coinglass_top_trader_long_pct_smooth_5`, `quality_funding_oi`,
  `coinglass_taker_imb_intraday_dispersion_24h`, and
  `funding_basis_residual_implied_repo_30`.

Provider sidecars remain sidecars. Binance OHLCV remains the canonical price
truth unless a separate concordance decision explicitly changes that.

---

## Source Boundaries

Allowed in Phase 0 / Phase 1:

- Binance OHLCV price and execution frame from the frozen control.
- Closed strategy equity only for existing drawdown throttle comparison.
- CoinGlass sidecar state if it has provider timestamp, local provenance, and
  explicit point-in-time availability handling.

Not allowed:

- CoinGlass spot price as canonical OHLC.
- Opaque vendor indicators as score inputs.
- Future-filled sidecar rows.
- Latest-event feeds without a conservative PIT lag.
- Any provider signal in live trading before this branch has a separate paper
  approval packet.

---

## Phase 0 - Provider Smoke And Coverage Reset

Goal:

```text
Prove the current provider data can support a PIT h10d sidecar test before any
new portfolio metric is computed.
```

Inputs to inspect first:

- `docs/quant_research/01_data_foundation/coinglass_full_stack_foundation_sync.md`
- `docs/quant_research/01_data_foundation/provider_api_registry.md`
- `docs/quant_research/01_data_foundation/market_data_inventory.md`

Required checks:

| check | requirement |
| --- | --- |
| provider auth | key presence only; never print secrets |
| endpoint availability | current smoke for top trader, taker, OI, funding, liquidation, orderbook |
| history window | report exact first and last timestamps by endpoint and interval |
| overlap window | compute overlap with `hv_balanced` rebalance timestamps |
| symbol coverage | split current live fixed-20 coverage from PIT rolling top20 coverage |
| PIT policy | define `available_at` for every sidecar family |
| quarantine status | block any latest-event or opaque feed from score use |

Fail-closed blockers:

- no explicit timestamp or no defensible `available_at`;
- provider history shorter than the intended test window without an overlap-only
  declaration;
- sidecar rows cannot be joined by symbol/date without forward-looking fill;
- coverage differs materially between top-liquidity and mid-liquidity buckets
  and cannot be stratified.

Expected artifact root:

```text
artifacts/quant_research/provider_sidecar_h10d/phase0_coverage_YYYYMMDD/
```

---

## Phase 1 - Risk Overlay Before Alpha Rescore

Phase 1 only changes short-side risk multipliers. It does not change the
five-factor `hv_balanced` score.

Candidate overlay families:

| overlay | sidecar state | landing shape |
| --- | --- | --- |
| `provider_crowded_long_short_brake_v1` | top-trader long share, global long share, OI growth, positive funding | reduce selected short weight |
| `provider_taker_followthrough_veto_v1` | taker buy pressure without price follow-through, or taker sell impulse exhaustion | veto or halve fragile shorts |
| `provider_liquidity_fragility_brake_v1` | orderbook bid/ask imbalance, liquidation concentration, poor depth context | reduce short exposure in squeeze-prone names |
| `provider_funding_oi_squeeze_veto_v1` | extreme funding/OI crowding on names near highs | do-not-short veto or severe multiplier |

Allowed multiplier values:

```text
1.00, 0.50, 0.25, 0.00
```

Primary objective:

```text
Reduce max drawdown and adverse short-tail risk versus hv_balanced on the same
overlap window, without creating a new fragile return source.
```

Promotion-style comparison gates:

| gate | minimum expectation |
| --- | --- |
| paired sample | same timestamps and symbols as overlap-window control |
| base max DD | must improve versus overlap-window control |
| Sharpe | must not degrade materially; target improvement over control |
| net return | should retain at least 90% of overlap-window control unless DD reduction is large |
| stress scenario | positive net return and no DD blow-up |
| stratified holdout | no bucket or symbol-family collapse |
| capacity | max trade participation remains under existing cap |
| cost sensitivity | 2x cost stress remains positive |

Stop rules:

- If an overlay only improves one liquidity bucket while hurting the other, stop.
- If the edge appears only after threshold tuning, quarantine it.
- If an overlay increases DD while raising net return, do not use it as the
  first provider-sidecar bridge.
- If provider coverage begins after a major regime and cannot be broadened,
  label the result `overlap_only_diagnostic`.

---

## Phase 2 - Old-Style 12-Factor Rescore

Only start Phase 2 after Phase 0 is clean and Phase 1 has either passed or
produced a clearly useful diagnostic.

Phase 2 asks whether a PIT-safe version of the old canonical h10d factor stack
can be rebuilt on the Binance PIT universe:

- train-window cross-sectional Spearman IC;
- IR conversion;
- signed absolute IR weight normalization;
- no future label leakage;
- same cost, funding, capacity, holdout, and liquidity-bucket gates as the
  Binance PIT h10d line.

The old canonical parent is a comparison target, not an automatic formula to
copy. Any new 12-factor score must beat `hv_balanced` on a paired Binance PIT
comparison before it can become more than a research branch.

---

## Required Output Tables

Every Phase 1/Phase 2 run must publish at least:

| table | purpose |
| --- | --- |
| `control_vs_candidate_metrics.csv` | base/stress return, Sharpe, DD, turnover, participation |
| `paired_period_returns.csv` | per-rebalance control and candidate returns |
| `sidecar_coverage_by_symbol.csv` | coverage by symbol and sidecar family |
| `sidecar_coverage_by_liquidity_bucket.csv` | top/mid bucket coverage split |
| `overlay_trigger_audit.csv` | when and why multipliers fired |
| `short_tail_adverse_excursion.csv` | short-side adverse move diagnostics |
| `falsification_summary.json` | gate-by-gate pass/fail status |

---

## Next Executable Step

Build the Phase 0 coverage/smoke report only.

Do not run threshold search, score rescore, or live-candidate edits until the
Phase 0 report explicitly says:

```text
provider_sidecar_h10d_phase0_ready = true
```

If Phase 0 is not ready, the correct result is a hard blocked status with the
missing provider families, history windows, and PIT blockers listed explicitly.
