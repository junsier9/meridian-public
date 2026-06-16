# Parallel 1h Alpha Mining Roadmap

`Snapshot date: 2026-05-07`
`Owner: quant_research_maintainer`
`Status: first-three Stage 0, fake-liquidity repair tests, first-batch fresh mechanical-flow Stage 0, trust-masked venue-concentration sidecar, trust-masked venue Stage 0 evaluator, and native exchange-flow availability audit completed; no admitted 1h alpha; h10d promotion state untouched`
`Scope: parallel 1h manipulation-state / mechanical-flow alpha discovery`

---

## Research Thesis

The repo has repeatedly learned that sparse mechanical information is more
useful at the selection layer than as another smooth global score. The 1h lane
therefore starts from event/state variables that can change whether a short is
allowed, delayed, resized, or capacity-haircut, not from `score += w * factor`.

The first research problem is the post-pump short trap:

- before squeeze completion, a high-return small/mid token can still be in a
  short-harvesting phase;
- after OI collapse, funding normalization, taker fade, and book flip, the same
  token can become a delayed short candidate;
- fake volume and venue concentration should reduce capacity before they are
  treated as alpha.

Default prior: every candidate is wrong until the local Stage 0 report survives
shuffle, holdout, delay, liquidity-bucket, funding, slippage, and capacity
stress.

---

## Boundary With Existing h10d Mainline

- The canonical h10d parent remains `v5_rw_bridge_no_overlay_h10d`.
- This 1h lane is parallel research infrastructure. It does not mutate h10d
  manifests, promotion cards, `run_quant_h10d_promotion_guard.py`, or any
  current `fixed_set_comparison` status.
- h10d evidence is allowed only as mechanism inspiration: SP-K showed that
  post-pump shorts need selection-layer logic; M3.2 showed that sparse boundary
  activation can beat smooth perturbation in Stage 0.
- A 1h candidate can later become an h10d sidecar only after it has its own
  1h evidence card and after the h10d promotion gate explicitly accepts the
  bridge. No implicit promotion transfer is allowed.

---

## Available 1h Data Inventory

Local data that is immediately usable for Stage 0:

| data family | local source | grain | current use in this lane |
| --- | --- | --- | --- |
| Perp close / quote volume / OI / funding | `%LOCALAPPDATA%/EnhengClaw/market_history/binance_derivatives/<SYM>USDT/1h` | 1h | forward returns, OI acceleration/collapse, funding drag, capacity proxy |
| Liquidations | `%LOCALAPPDATA%/EnhengClaw/market_history/coinglass_extended/<SYM>USDT/1h` | 1h | squeeze completion, liquidation cooldown, adverse short risk |
| Orderbook bids / asks | same `coinglass_extended` cache | 1h | bid support, ask thinning, book flip, depth failure |
| Taker buy / sell volume | same `coinglass_extended` cache | 1h | taker-buy dominance, taker fade, sell confirmation |
| Global vs top-trader positioning | same `coinglass_extended` cache | 1h | retail chase vs top-trader fade context |
| Spot OHLCV | Binance direct and CoinGlass spot cache | 1h | optional confirmation only; CoinGlass spot remains quarantined for strict provider concordance |
| On-chain stablecoin / exchange flow | CryptoQuant / Alchemy daily caches | daily today | context only; not enough for native 1h CEX-inflow state yet |
| Listing / low-float / unlock metadata | not local | event sidecar needed | blocker for true low-float labels; liquidity bucket is only a proxy |

Repo facts that constrain interpretation:

- `market_data_inventory.md` records 1h `coinglass_extended` fields for
  liquidation, long/short account ratios, top-trader ratios, orderbook depth,
  and taker flow.
- `data_utilization_roadmap.md` says much of the 1h Coinglass matrix is
  underused, especially liquidation, orderbook, taker flow, and participant
  disagreement.
- CoinGlass spot coverage is not provider trust. The 2026-05-04 coverage reset
  passed coverage but strict Binance OHLC concordance failed for many symbols.

---

## Data Quality Blockers

| blocker | severity | required handling |
| --- | --- | --- |
| CoinGlass spot OHLC strict concordance failed | hard blocker for spot-trust claims | use Binance derivatives close for first 1h perp Stage 0; keep spot as quarantined confirmation until concordance passes |
| True circulating float / unlock schedule not local | blocker for literal low-float claims | use `liquidity_bucket` and volume/OI only as proxies; label output as `low_float_proxy` |
| Venue OI / volume concentration not verified locally | blocker for venue HHI candidates | keep `venue_concentration` candidates in implementation-plan status until provider endpoint is verified |
| CEX inflow is daily/partial today, not native 1h | blocker for first-class `cex_inflow_bait_vs_exit` | run only after an aligned PIT exchange-flow sidecar exists; require +1h/+6h/+24h delay tests |
| OI value provenance can differ by provider | high | record OI source/provenance; run native-vs-derived sensitivity before promotion |
| 1h bars near the live tail may be incomplete | medium | exclude newest incomplete bars in production runs; Stage 0 reports must state coverage window |

---

## Ranked Candidate Alpha / State Variables

Ranking score is qualitative: expected edge, data availability, and live
feasibility. Every candidate is fail-closed until the Stage 0 matrix passes.

| rank | candidate | expected edge | data | live | feature definition | entry / exit / use shape | invalidates_if |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | `low_float_squeeze_trap` | high | high | high | recent 6h/24h pump + OI acceleration + deep negative funding + bid support or taker-buy dominance + no OI collapse | do-not-short / reduce short; do not replace into this name | flagged shorts are not worse than controls at h1-h72, or delay tests erase effect |
| 2 | `post_squeeze_exit_short` | high | high | high | prior trap/squeeze + OI collapse/deceleration + funding normalization + taker-buy fade + bid replenishment failure | delayed short entry after trap clears | not stronger than raw post-pump stall, or +1h/+6h/+24h delay fails |
| 3 | `fake_liquidity_capacity_haircut` | medium-high | medium | high | 24h volume/OI extreme, thin OI, abnormal taker/book structure, venue concentration when available | haircut ADV, max participation, and short eligibility | capacity haircut does not reduce adverse tails or destroys most alpha |
| 4 | `cex_inflow_bait_vs_exit` | high | low-medium | medium | CEX inflow spike split by OI/funding/taker/book confirmation | classify inflow as bait or true exit before short | inflow-only performs the same as confirmed-exit split, or PIT delay fails |
| 5 | `oi_accel_negative_funding_veto` | medium | high | high | OI 6h/24h acceleration with funding below rolling q20 | short-veto component inside trap | works only on one symbol or one liquidity bucket |
| 6 | `taker_buy_with_flat_price_absorption` | medium | high | high | taker-buy dominance while price stalls after pump | do-not-short until taker buy fades | no adverse squeeze difference over h1-h24 |
| 7 | `post_pump_bid_replenishment_failure` | medium | high | high | bid/ask ratio flips down after bid support phase | delayed short enable | book flip is stale or not PIT stable |
| 8 | `short_liquidation_completion_cooldown` | medium | high | high | short-liquidation spike then liquidation intensity decays | wait for cooldown before short | cooldown does not reduce h1/h3 adverse squeeze |
| 9 | `funding_normalization_after_deep_negative` | medium | high | high | funding exits extreme-negative quantile after trap | delayed short enable / size restore | funding drag remains worse than control |
| 10 | `top_trader_fade_retail_chase_veto` | medium | high | medium | global accounts add longs while top traders reduce longs | short timing / reduce exposure | current MF-07-style pivots remain at-par under 1h horizon |
| 11 | `venue_local_pump_nonconfirmation` | medium | low | medium | price/volume pump appears on one venue without broad confirmation | event confirmation filter | venue-local 1h state is not available or daily proxy repeats prior failure |
| 12 | `spot_perp_divergence_repricing_guard` | medium | medium | medium | perp pump not confirmed by trusted spot return / volume | do-not-short if spot confirms real repricing; short if perp-only stress exhausts | CoinGlass spot remains untrusted and Binance spot coverage is insufficient |
| 13 | `liquidation_cluster_aftershock_veto` | medium | high | high | multiple liquidation bursts within 24h after pump | no new short during aftershock window | aftershock count is just volatility proxy and label shuffle passes |
| 14 | `volume_oi_brushing_risk` | medium | high | high | 24h volume/OI ratio extreme, especially with low OI and high taker churn | capacity haircut / kill-switch input | not associated with worse capacity/slippage proxy |
| 15 | `depth_velocity_collapse_exit` | medium | high | medium | orderbook bid depth change turns sharply negative after trap | delayed entry | depth fields have poor coverage or stale vendor updates |
| 16 | `funding_settlement_squeeze_window` | medium-low | high | high | trap state near 0/8/16 UTC funding settlement | intraday order timing / avoid crowded shorts | no hour-of-day concentration or cost dominates edge |
| 17 | `low_liquidity_hour_kill_switch` | medium-low | high | high | event occurs in bottom liquidity hours for symbol | no market order / reduce participation | removes too many good events or no slippage proxy improvement |
| 18 | `oi_value_provenance_quarantine` | risk control | medium | high | native OI value and derived OI value disagree materially | provider trust veto, not alpha | no provenance sidecar or mismatch not material |

---

## Stage 0 Validation Matrix

Each first-round report must include these fields:

```text
research_id
data_sources_and_coverage
feature_definitions
event_count_by_symbol
event_count_by_liquidity_bucket
forward_return_table_h1_h3_h6_h12_h24_h48_h72
selected_short_changed_rows or equivalent strategy interaction
funding_drag_summary
slippage_or_capacity_proxy
shuffle_tests
symbol_holdout
liquidity_bucket_consistency
delay_robustness
pass_fail_decision
next_landing_shape
```

Minimum Stage 0 pass conditions:

- event count is large enough for at least two liquidity buckets;
- flagged rows materially differ from the control cohort in the expected
  direction at the candidate's natural horizon;
- effect survives same-timestamp feature shuffle and a symbol time-shift
  shuffle;
- no single symbol contributes more than 30% of positive evidence;
- symbol holdout remains directionally consistent;
- delay robustness survives +1h, +6h, and +24h for event/external-state
  features;
- funding drag and slippage/capacity proxy do not reverse the conclusion.

---

## Falsification Matrix

| test | fail-closed condition |
| --- | --- |
| Time shuffle | randomly time-shifted state equals or beats observed edge |
| Label shuffle | shuffled forward returns reproduce observed effect |
| Same-timestamp feature shuffle | cross-sectional randomization of the flag reproduces edge |
| Symbol holdout | removing any one high-event symbol flips the conclusion, or fewer than 60% of eligible symbols have the expected sign |
| Liquidity bucket consistency | effect exists only in one bucket without an execution reason |
| Delay robustness | +1h, +6h, or +24h entry delay erases the sign for event/on-chain/news features |
| Cost / funding stress | doubled cost, negative funding drag, or realistic slippage proxy makes edge non-positive |
| Provider sensitivity | CoinGlass-only result disappears on trusted Binance/perp reference or when suspect symbols are quarantined |
| Capacity stress | max participation or OI participation breaches ADR-G1-like limits |
| Tail-bar audit | newest incomplete bars drive the result |

---

## Live Trading Feasibility Checklist

Before a 1h candidate can leave research-only status:

- capacity: report trade capacity at 0.5% hourly volume and 2% OI;
- turnover: expected trades per day, symbol churn, and average holding period;
- funding: expected funding PnL by horizon and fraction of short windows paying
  funding;
- slippage: at least a volume/volatility proxy, later orderbook depth impact;
- max participation: per-symbol max participation and hard reject list;
- order type: whether signal requires market, limit, post-only, or TWAP;
- latency: whether +1h delay still works;
- rate limits: provider polling cadence and fallback data path;
- kill switch: stale data, missing OI, suspect provider concordance, funding
  spike, volume/OI brushing, and book-thinness triggers;
- failure modes: squeeze continuation, fake liquidity, funding bleed, venue
  dislocation, listing halt/delist, API outage, and crowded unwind.

---

## First Three Recommended Stage 0 Experiments

1. `low_float_squeeze_trap_stage0_1h`
   - Use local 1h derivatives + CoinGlass extended data.
   - Treat liquidity bucket as a proxy for float until real float/unlock
     metadata exists.
   - Landing shape: selected-short do-not-short / reduce-short equivalent.

2. `post_squeeze_exit_short_stage0_1h`
   - Reuse the trap state, then test OI collapse + funding normalization +
     taker/book reversal as delayed short entry.
   - Landing shape: delayed entry, not immediate short.

3. `fake_liquidity_capacity_haircut_stage0_1h`
   - Measure whether volume/OI and depth/taker anomalies identify overstated
     executable liquidity.
   - Landing shape: capacity haircut, participation cap, and kill-switch input.

`cex_inflow_bait_vs_exit` is high-value but should wait until a native PIT
exchange-flow sidecar is aligned to the 1h decision grid.

---

## Current First-Slice Decision

Implement the first evaluator as a standalone Stage 0 script that:

- reads raw 1h local caches directly;
- writes a JSON report under `artifacts/quant_research/factor_reports/`;
- does not modify manifests or h10d promotion state;
- reports `blocked` if data coverage is insufficient, otherwise `pass` only if
  all falsification gates clear.

---

## Stage 0 Execution Log

Status as of 2026-05-07:

| research_id | report | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- | --- |
| `low_float_squeeze_trap_stage0_1h` | `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/low_float_squeeze_trap_stage0_1h.json` | `fail` | 28,142 post-pump short candidates; 3,130 trap rows; h24 short-return delta `-0.002409`; liquidity buckets consistent | same-timestamp shuffle, symbol holdout, and +24h delay robustness failed |
| `post_squeeze_exit_short_stage0_1h` | `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/post_squeeze_exit_short_stage0_1h.json` | `fail` | 280,706 prior trap/squeeze candidates; 14,925 confirmed-exit rows; h24 short-return delta `-0.001234` | shuffle, symbol holdout, liquidity-bucket consistency, and delay robustness failed |
| `fake_liquidity_capacity_haircut_stage0_1h` | `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_capacity_haircut_stage0_1h.json` | `pass` | 28,142 post-pump short candidates; 6,260 haircut rows; h24 short-return delta `-0.007236`; adverse tail higher on haircut rows; 200-iteration feature/label/time-shift shuffles pass; symbol holdout consistency `0.6338`; mid/tail buckets and +1h/+6h/+24h delay pass | no candidate-state Stage 0 blocker; still quarantined because parent-interaction admission later failed and no h10d bridge is accepted |

Current interpretation: `fake_liquidity_capacity_haircut` is the only survivor
of the first-three Stage 0 set, and only as a quarantined 1h risk-control /
participation-cap candidate. It is not a live strategy and it does not transfer
to the h10d parent.

### Atomic Decomposition Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_atomic_decomposition_1h.json`

Strict component rule: an atomic component survives only if capacity diagnostic,
200-iteration shuffle tests, symbol holdout, liquidity-bucket consistency, and
+1h/+6h/+24h delay all pass.

| component | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `aggregate_haircut` | `pass` | 6,260 rows; h24 short-return delta `-0.007236`; shuffle, holdout, bucket, and delay pass | no Stage 0 blocker, but remains quarantined until parent interaction is simulated |
| `volume_oi_brushing_extreme` | `fail` | 6,676 rows; h24 delta `-0.006950`; shuffle, bucket, and delay pass | symbol holdout consistency `0.5714`, below the `0.60` gate |
| `book_thinness` | `fail` | 20,389 rows; h24 delta `-0.005553`; holdout, bucket, and delay pass | same-timestamp feature/label shuffle reproduce too much of the effect |
| `taker_book_dislocation` | `fail` | 13,975 rows; h24 delta `-0.005443`; shuffle, bucket, and delay pass | symbol holdout consistency `0.5844`, below the `0.60` gate |
| `thin_capacity` | `fail` | 7,395 rows; h24 delta `+0.000645` | wrong sign and fails capacity, shuffle, holdout, bucket, and delay |
| `slippage_proxy_extreme` | `fail` | 5,375 rows; h24 delta `+0.003128` | wrong sign and fails capacity, shuffle, holdout, bucket, and delay |

Decomposition conclusion: the current evidence is interaction-shaped, not
atomic. Do not use `volume_oi`, `book_thinness`, `taker_book_dislocation`,
`thin_capacity`, or `slippage_proxy_extreme` as standalone gates. The next
research move is a quarantined 1h parent-interaction simulator using only the
aggregate haircut state, with hard-veto, quarter-size, and soft-multiplier
variants compared under capacity and turnover stress.

### Parent Interaction Simulator Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_aggregate_parent_interaction_1h.json`

Parent definition: every `capacity_haircut_candidate_flag` row is a unit short
candidate; the aggregate fake-liquidity state is allowed only to resize or veto
those rows. This is a quarantined simulator, not a live portfolio.

| variant | conclusion | h24 gross pnl delta | h24 adverse 5pct tail delta | capacity / turnover impact | fail-closed reason |
| --- | --- | ---: | ---: | --- | --- |
| `hard_veto` | `fail` | `+0.001274` | `-0.008488` | mean exposure `0.7775`; exposure units/day `30.73`; capacity/day `$708k` | symbol holdout consistency `0.5694`, below the `0.60` gate |
| `quarter_size` | `fail` | `+0.000956` | `-0.005941` | mean exposure `0.8331`; exposure units/day `32.93`; capacity/day `$776k` | symbol holdout consistency `0.5694`, below the `0.60` gate |
| `soft_multiplier` | `fail` | `+0.000637` | `-0.003713` | mean exposure `0.8887`; exposure units/day `35.13`; capacity/day `$844k` | symbol holdout consistency `0.5694`, below the `0.60` gate |

Baseline parent at h24 is weak: gross PnL per candidate `-0.000100`, adverse
5pct squeeze tail `0.1780`, exposure units/day `39.53`, capacity/day `$979k`.
All three policies improve the aggregate h24 PnL, reduce adverse tails, pass
policy shuffle, pass liquidity-bucket consistency, and pass delay robustness.
They still fail strict admission because the improvement is not symbol-holdout
stable enough. Decision: no parent-interaction admission, no h10d bridge, and
no live use. The next allowed work is symbol/bucket attribution plus venue
concentration/provider sensitivity, or a redesigned aggregate state with a
fresh strict simulator run.

### Requested Atom Decomposition Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_capacity_haircut_atoms_stage0_1h.json`

This run decomposes the user-requested atomic rules:
`thin_book_vs_flow`, `taker_churn_without_direction`,
`volume_oi_brushing`, `high_slippage_proxy`, and
`kill_switch_score_gte4`. Overall conclusion: `fail`; no standalone atom is
admitted.

| atom | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `volume_oi_brushing` | `fail` | 6,676 rows; h24 short delta `-0.006950`; adverse-tail delta `+0.040378`; shuffle, bucket, and delay pass | symbol holdout consistency `0.5075`, below the `0.60` gate |
| `thin_book_vs_flow` | `fail` | 17,625 rows; h24 short delta `-0.006555`; adverse-tail delta `+0.051400`; bucket and delay pass | same-timestamp shuffle fails and symbol holdout consistency is `0.5676` |
| `kill_switch_score_gte4` | `fail` | 5,653 rows; h24 short delta `-0.005431`; adverse-tail delta `+0.035576`; bucket and delay pass | same-timestamp shuffle fails and symbol holdout consistency is `0.5652` |
| `taker_churn_without_direction` | `fail` | 16,947 rows; h24 short delta `-0.000090`; adverse-tail delta `+0.011244` | shuffle, symbol holdout, bucket consistency, and delay robustness fail |
| `high_slippage_proxy` | `fail` | 5,375 rows; h24 short delta `+0.003128`; adverse-tail delta `-0.013947` | wrong primary direction and all falsification gates fail |

Interpretation: `volume_oi_brushing` is the nearest retry candidate, but it is
not admissible as a standalone gate. The evidence remains interaction-shaped:
single components either fail holdout or are reproduced by same-timestamp
randomization.

### Symbol / Provider Sensitivity Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_parent_symbol_provider_sensitivity_1h.json`

This audit explains the rejected aggregate parent-interaction simulator. It is
not an admission rerun and cannot rescue the rule by post-hoc symbol exclusion.

| scenario | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `all` hard-veto parent interaction | `fail` | 28,142 candidates; 6,260 aggregate haircut rows; h24 improvement `+0.001274`; bucket pass | symbol holdout consistency `0.5694`, below the `0.60` gate |
| `exclude_provider_watchlist` | `fail` | removing `SYRUP/SUN/LUNC/WIF` raises h24 improvement to `+0.001328` | holdout only improves to `0.5714`, still below gate |
| `provider_watchlist_only` | `fail` | 580 candidate rows; h24 improvement `-0.001260` | watchlist is not the only root cause and is not itself tradable |
| `complete_core_provider_fields` | `fail` | 28,141 rows; h24 improvement `+0.001274` | missing core fields are not driving the rejection |
| tail-bar exclusions | `fail` | excluding last 24h/72h/168h keeps positive improvement | holdout remains `0.5694`; not a live-tail artifact |

Top negative hard-veto contributors are `CFX`, `2Z`, `WAL`, `PYTH`, and `INJ`.
Top positive contributors are `SAND`, `DASH`, `XTZ`, `DEXE`, and `CAKE`.
Bucket-level attribution does not isolate the failure: `mid_liquidity` has
positive symbol fraction `0.5190` and `tail_liquidity` has `0.5179`.
Listing-age split suggests `30_90d` and `90_180d` bins pass holdout, while
`180_365d`, `gte_365d`, and `lt_30d` fail. This is attribution only: the next
valid research step must pre-register any age-gated redesign before rerunning
the strict simulator.

### Pre-Registered Age Sidecar Redesign

Preregistration:
`docs/quant_research/04_parallel_1h/parallel_1h_fake_liquidity_age_sidecar_preregistration.md`

Strict simulator report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_age_30_180d_sidecar_1h.json`

Primary rule:

```text
capacity_haircut_candidate_flag
AND fake_liquidity_capacity_haircut_flag
AND 30 <= local symbol history age days < 180
```

No symbol-name exclusion is allowed; `SYRUP/SUN/LUNC/WIF` is not used as a
rescue rule. Split bins are diagnostics only.

| sidecar | variant | conclusion | h24 pnl delta | h24 adverse 5pct tail delta | key gates |
| --- | --- | --- | ---: | ---: | --- |
| `age_30_180d` | `hard_veto` | `fail` | `+0.000690` | `-0.003692` | holdout `0.6806` passes; same-timestamp shuffle and +24h delay fail |
| `age_30_180d` | `quarter_size` | `fail` | `+0.000517` | `-0.002734` | holdout `0.6806` passes; same-timestamp shuffle and +24h delay fail |
| `age_30_180d` | `soft_multiplier` | `fail` | `+0.000345` | `-0.001799` | holdout `0.6806` passes; same-timestamp shuffle and +24h delay fail |
| `diagnostic_age_30_90d` | best hard-veto | `fail` | `+0.000305` | `-0.001571` | diagnostic only; shuffle and delay fail |
| `diagnostic_age_90_180d` | best hard-veto | `fail` | `+0.000385` | `-0.002031` | diagnostic only; holdout `0.5833`, shuffle, and delay fail |

Decision: the pre-registered age sidecar fixes the previous symbol-holdout
blocker but fails the stricter causal tests. Same-timestamp policy/label
shuffle reproduces too much of the improvement, and +24h delay turns the
primary hard-veto improvement negative. The R-2 fake-liquidity branch remains
rejected. Do not bridge, do not use live, and do not keep iterating on
post-hoc symbol or age filters without a new exogenous venue/provider sidecar.

### Age-Gated Parent Interaction Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_age_gated_parent_interaction_1h.json`

Pre-registered redesign: keep all parent candidates and all symbols, but only
apply the aggregate fake-liquidity policy when
`30 <= symbol_history_age_days_at_signal < 180`. The age proxy is measured from
the first local 1h bar, not a trusted listing timestamp, so even a pass would
remain quarantined.

| variant | conclusion | h24 gross pnl delta | h24 adverse 5pct tail delta | pass evidence | fail-closed reason |
| --- | --- | ---: | ---: | --- | --- |
| `hard_veto` | `fail` | `+0.000690` | `-0.003692` | symbol holdout passes (`0.6806`) and buckets pass | same-timestamp policy/label shuffle fail; +24h delay flips improvement to `-0.000458` |
| `quarter_size` | `fail` | `+0.000517` | `-0.002734` | symbol holdout passes (`0.6806`) and buckets pass | same-timestamp policy/label shuffle fail; +24h delay flips improvement to `-0.000343` |
| `soft_multiplier` | `fail` | `+0.000345` | `-0.001799` | symbol holdout passes (`0.6806`) and buckets pass | same-timestamp policy/label shuffle fail; +24h delay flips improvement to `-0.000229` |

The age gate retains 1,389 of 6,260 raw aggregate haircut rows (`22.19%`).
It repairs symbol holdout but fails policy uniqueness and delay robustness.
Decision: `fail`; no age-gated rescue, no parent-interaction admission, no h10d
bridge, and no live use.

### Short-Liquidation Completion Cooldown Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/short_liquidation_completion_cooldown_stage0_1h.json`

This is the first fresh Stage 1B mechanical-flow experiment after closing the
fake-liquidity rescue loop. The rule marks post-pump short candidates as
`do-not-short / delayed-entry cooldown` when short-liquidation pressure is
elevated but exhaustion is not confirmed.

| rule | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `short_liquidation_completion_cooldown_stage0_1h` | `fail` | 28,142 post-pump candidates; 12,953 cooldown rows; h24 short-return delta `-0.003995`; adverse squeeze >5% delta `+0.032327`; shuffle, bucket consistency, and +1h/+6h/+24h delay robustness pass | symbol holdout consistency is `0.5867`, below the `0.60` hard gate |

Diagnostic detail: the top event contributors are `PENDLE`, `LDO`, `ETHFI`,
`RENDER`, `JASMY`, `THETA`, `INJ`, `ZEC`, `JTO`, and `CFX`, but the largest
single symbol share is only `2.96%`. The failure is therefore not a single-name
concentration bug; it is a cross-symbol stability miss. Decision: no parent
interaction, no h10d bridge, and no live use. Keep the mechanism as evidence
that active short-liquidation pressure is dangerous for post-pump shorts, but
advance the executable queue to `funding_settlement_squeeze_window_stage0_1h`.

### Funding-Settlement Squeeze Window Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/funding_settlement_squeeze_window_stage0_1h.json`

This is the second fresh Stage 1B mechanical-flow experiment. The rule marks
post-pump short candidates as near-settlement `do-not-short / reduce-short`
rows when UTC 0/8/16 funding-settlement timing coincides with deep negative
funding that has not normalized and OI/flow still supports squeeze risk.

| rule | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `funding_settlement_squeeze_window_stage0_1h` | `fail` | 28,142 post-pump candidates; 1,537 window rows; h24 short-return delta `-0.006522`; adverse squeeze >5% delta `+0.034684`; symbol holdout `0.65625` passes; mid/tail buckets pass | same-timestamp feature/label shuffles fail and +24h delay flips the delta to `+0.002580` |

Diagnostic detail: settlement-hour label shuffle and symbol time-shift shuffle
pass, but same-timestamp shuffles reproduce too much of the effect. This means
the signal is not cleanly unique versus contemporaneous cross-sectional state.
Delay robustness also fails: +1h and +6h stay negative, but +24h reverses.
Funding drag is materially worse on the flagged rows in the local units
(`h24` mean short funding estimate `-0.583483` versus control `+0.013166`),
so funding provider semantics must be audited before any later live-sizing use.
Decision: no parent interaction, no h10d bridge, and no live use. Keep this as
timing/carry-risk evidence only; advance the executable queue to
`top_trader_fade_retail_chase_veto_stage0_1h`.

### Top-Trader Fade / Retail Chase Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/top_trader_fade_retail_chase_veto_stage0_1h.json`

This is the third fresh Stage 1B mechanical-flow experiment. The initial
diagnostic showed that `global account chase + top-trader fade/nonconfirmation`
behaves more like a delayed short-entry / size-restore state than a veto state,
so the primary Stage 0 test required a positive short-return delta. The aligned
top-trader-and-retail chase state is retained only as a diagnostic veto side.

| rule | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `top_trader_fade_retail_chase_veto_stage0_1h` | `fail` | 28,142 post-pump candidates; 1,060 top-trader-fade/retail-chase entry rows; h24 short-return delta `+0.004192`; adverse squeeze >5% delta `-0.025865`; symbol holdout `0.6667` passes; mid/tail buckets pass; +1h/+6h/+24h delay robustness passes | same-timestamp feature/label shuffles fail; shuffled means are near or above observed |

Diagnostic detail: symbol time-shift shuffle passes, but same-timestamp feature
shuffle has observed upper-tail quantile `0.585` and same-timestamp label
shuffle has `0.625`. The signal therefore is not unique enough versus
contemporaneous cross-sectional account/taker state. Decision: no parent
interaction, no h10d bridge, and no live use. Keep this as an account-ratio
timing diagnostic only. Advance the executable queue to
`post_pump_bid_replenishment_failure_stage0_1h`.

### Post-Pump Bid Replenishment Failure Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/post_pump_bid_replenishment_failure_stage0_1h.json`

This is the fourth fresh Stage 1B mechanical-flow experiment. The rule tested a
delayed short-entry selector: after a post-pump candidate first had bid/taker
support, short entry is allowed only when book pressure deteriorates, price
fails to make a shifted prior-6h high, and a seven-component bid-replenishment
failure score is at least 5. All rolling thresholds and prior-window features
are shifted one bar.

| rule | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `post_pump_bid_replenishment_failure_stage0_1h` | `fail` | 28,142 post-pump candidates; 4,534 entry rows; h24 short-return delta `-0.002014`; adverse squeeze >5% delta `+0.016274`; event counts are broad enough across mid/tail buckets | primary direction is negative; shuffle, symbol holdout, liquidity-bucket consistency, and +1h/+6h/+24h delay robustness all fail |

Diagnostic detail: the rule is not data-count blocked. It has 3,161 mid-liquidity
and 1,373 tail-liquidity events across 76 symbols, but both buckets have
negative h24 short-return deltas and higher adverse-squeeze fractions. Delay
robustness is also directionally wrong: +1h delta `-0.002061`, +6h delta
`-0.001469`, and +24h delta `-0.005158`. Funding drag is materially worse on
flagged rows (`h24` mean short funding estimate `-0.075149` versus control
`-0.008718`). Capacity/slippage proxies do not rescue the result: entry rows
show slightly lower proxy slippage, but the return and funding evidence reject
the delayed-entry use shape. Decision: no parent interaction, no h10d bridge,
and no live use. Keep only the negative lesson: naive bid-replenishment failure
may still be a squeeze-continuation risk state.

### Funding Normalization After Deep Negative Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/funding_normalization_after_deep_negative_stage0_1h.json`

This is the fifth fresh Stage 1B mechanical-flow experiment. The rule tested a
delayed short-entry / size-restore selector: after a post-pump candidate has
recent deep-negative funding and prior squeeze pressure, short entry is allowed
only when funding exits the deep-negative state and OI/taker/book pressure has
partly cleared. All rolling thresholds and prior-window features are shifted
one bar.

| rule | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `funding_normalization_after_deep_negative_stage0_1h` | `fail` | 28,142 post-pump candidates; 1,984 entry rows; h24 short-return delta `+0.005606`; adverse squeeze >5% delta `-0.033174`; symbol holdout passes at `0.6061`; mid/tail buckets both positive | same-timestamp feature and label shuffles reproduce stronger deltas; +24h delay flips the edge |

Diagnostic detail: this is the closest fresh mechanical-flow result so far,
but it still fails the repo's admission contract. Same-timestamp feature
shuffle has observed upper-tail quantile `0.925`; same-timestamp label shuffle
has `0.945`, so contemporaneous cross-sectional state explains too much of the
effect. Delay robustness passes at +1h (`+0.004914`) and +6h (`+0.005058`) but
fails at +24h (`-0.000377`). Funding carry is favorable on flagged rows (`h24`
mean short funding estimate `+0.055044` versus control `-0.025069`), and
slippage proxy is slightly lower, but capacity is thinner (`p10` capacity
`1971` versus control `3259`). Decision: no parent interaction, no h10d bridge,
and no live use. Retain this only as a funding-timing diagnostic unless a fresh,
pre-registered causal confirmation can beat same-timestamp shuffles and +24h
delay.

### Liquidation Cluster Aftershock Veto Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/liquidation_cluster_aftershock_veto_stage0_1h.json`

This is the sixth fresh Stage 1B mechanical-flow experiment. The rule tested a
state-duration veto: after a post-pump candidate, repeated short-liquidation
bursts over the trailing 24h mark an aftershock window where new shorts should
be blocked unless liquidation pressure has clearly cooled. Current-bar
liquidation fields are used only as closed-bar inputs; rolling thresholds are
shifted one bar.

| rule | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `liquidation_cluster_aftershock_veto_stage0_1h` | `fail` | 28,142 post-pump candidates; 18,779 veto rows; h24 veto short-return delta `-0.007259`; adverse squeeze >5% delta `+0.039684`; symbol holdout passes at `0.6000`; mid/tail buckets and +1h/+6h/+24h delay all pass | same-timestamp feature and label shuffles reproduce the effect |

Diagnostic detail: the aftershock state is a strong risk descriptor but not an
admitted independent veto. Same-timestamp feature shuffle has observed
lower-tail quantile `0.635`; same-timestamp label shuffle has `0.605`. In plain
terms, the rule is mostly capturing the contemporaneous cross-sectional danger
state already visible at that timestamp, not a unique causal selector. The
symbol time-shift shuffle passes and the delayed deltas remain negative
(+1h `-0.006207`, +6h `-0.004187`, +24h `-0.002068`), but the same-timestamp
failure is a hard gate. Funding drag is worse on veto rows (`h24` mean short
funding estimate `-0.034546` versus control `+0.010915`). Capacity and slippage
proxies do not block the result, but they do not rescue a shuffle failure.
Decision: no parent interaction, no h10d bridge, and no live use. Retain this
only as liquidation-risk diagnostic evidence.

### Low-Liquidity Hour Kill Switch Update

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/low_liquidity_hour_kill_switch_stage0_1h.json`

This is the seventh fresh Stage 1B mechanical-flow experiment. The rule tested
an execution-risk kill switch for post-pump short candidates that arrive during
symbol-specific low-liquidity hours. All low-volume, low-capacity, and
high-slippage thresholds are point-in-time rolling features shifted one bar.

| rule | conclusion | key evidence | fail-closed reason |
| --- | --- | --- | --- |
| `low_liquidity_hour_kill_switch_stage0_1h` | `fail` | 28,142 post-pump candidates; 3,276 kill-switch rows; capacity p10 is thinner (`1278` versus control `3654`), but h24 short-return delta is `+0.007367` and adverse squeeze >5% delta is `-0.047489` | the flagged rows are not worse shorts, have lower adverse squeeze risk, have lower slippage proxy, and fail shuffle, symbol holdout, bucket, and delay gates |

Diagnostic detail: this result is useful because it rejects a tempting but too
blunt execution rule. The flagged rows do have lower capacity
(`capacity_proxy_usd` median ratio `0.369` and p10 ratio `0.350` versus
control), but lower capacity does not translate into worse forward short
outcomes or worse slippage proxy in this sample. The kill-switch rows have h24
mean short return `+0.006411` versus control `-0.000957`, and the >5% adverse
forward move rate is lower (`0.1360` versus `0.1835`). +1h, +6h, and +24h
delays keep the same non-veto direction, so delay robustness fails for a
kill-switch thesis. Symbol holdout passes in only `11/65` usable symbols
(`0.1692`). Decision: no parent interaction, no h10d bridge, and no live use.
Retain only as a reminder that capacity-thin rows are not automatically
do-not-short rows.

### Stage 0 Progress Snapshot

As of 2026-05-07, the parallel 1h lane has completed the first three planned
experiments, five fake-liquidity follow-on falsification/repair runs, and seven
fresh mechanical-flow Stage 0 runs.

| area | status | current meaning |
| --- | --- | --- |
| first-three experiments | `3/3 complete` | `low_float_squeeze_trap` fail; `post_squeeze_exit_short` fail; aggregate `fake_liquidity_capacity_haircut` passes only as quarantined state evidence |
| standalone atoms | `complete / fail` | requested atoms do not admit; `volume_oi_brushing` is closest but fails symbol holdout |
| parent interaction | `complete / fail` | aggregate hard-veto/quarter/soft policies improve average h24 metrics but fail strict symbol holdout |
| symbol/provider sensitivity | `complete / fail` | provider watchlist, missing core fields, and live-tail bars do not explain away the rejection |
| age-gated rescue | `complete / fail` | age gate fixes symbol holdout but fails shuffle and +24h delay robustness |
| fresh mechanical-flow Stage 0 | `7 complete / fail` | `short_liquidation_completion_cooldown` fails symbol holdout at `0.5867 < 0.60`; `funding_settlement_squeeze_window` fails shuffle and +24h delay; `top_trader_fade_retail_chase` fails same-timestamp shuffles; `post_pump_bid_replenishment_failure` has negative primary direction and fails all hard gates; `funding_normalization_after_deep_negative` is directionally promising but fails same-timestamp shuffles and +24h delay; `liquidation_cluster_aftershock_veto` passes holdout/bucket/delay but fails same-timestamp shuffles; `low_liquidity_hour_kill_switch` has thinner capacity but the wrong veto direction and fails all hard gates |
| h10d bridge / live trading | `not allowed` | no 1h rule has promotion rights; h10d canonical parent remains untouched |

Net state: the 1h lane has produced useful mechanism hypotheses
(`fake_liquidity_capacity_haircut` and
`short_liquidation_completion_cooldown`) and one timing/carry-risk diagnostic
(`funding_settlement_squeeze_window`) plus one account-ratio timing diagnostic
(`top_trader_fade_retail_chase`) plus one negative bid-failure diagnostic
(`post_pump_bid_replenishment_failure`) plus one promising but non-admitted
funding-normalization diagnostic
(`funding_normalization_after_deep_negative`) plus one liquidation-risk
diagnostic (`liquidation_cluster_aftershock_veto`) plus one rejected capacity
thinness diagnostic (`low_liquidity_hour_kill_switch`) but zero admitted parent
interactions and zero live-trading candidates. Further work should not keep
rescuing failed states unless a new, pre-registered data source or a fresh
mechanical-flow candidate changes the information set.

---

## Forward Roadmap After Current Stage 0 Evidence

The next stages should treat the completed 1h work as a falsification base, not
as a search space to rescue. The current evidence says that post-pump small-cap
short risk is real, but the available aggregate fake-liquidity rule is not yet a
causal or tradable selector. The roadmap therefore splits future work into:

1. evidence freeze and branch triage,
2. data unlocks that can change the information set,
3. fresh mechanical-flow Stage 0 experiments,
4. parent-interaction simulators only for survivors,
5. h10d bridge and live-readiness gates only after independent 1h proof.

### Stage Progress And Gates

| stage | objective | allowed work | entry criteria | exit criteria | fail-closed stop |
| --- | --- | --- | --- | --- | --- |
| `Stage 0.5` evidence freeze | Convert completed reports into a stable decision ledger | Evidence index, report schema cleanup, no new alpha fitting | Existing reports exist and are reproducible from local scripts | Each branch has `pass/fail/blocked`, report path, decisive failed gate, and next action | Any missing report field or irreproducible run remains `blocked` |
| `Stage 1A` data sidecar unlocks | Add exogenous information that can change fake-liquidity and inflow hypotheses | Venue concentration, native PIT exchange-flow, listing/float/unlock sidecar, provider concordance checks | Data path and timestamp semantics are explicit | Sidecar has coverage, missingness, latency, concordance, and no-leakage report | Coverage without concordance does not unlock research |
| `Stage 1B` fresh mechanical-flow Stage 0 | Test new state variables that do not depend on the rejected aggregate rule | New evaluators for liquidation completion, funding-settlement squeeze, taker/top-trader fade, bid replenishment failure, funding normalization, liquidation aftershock, low-liquidity kill switch | Candidate is pre-registered with feature definitions and delays | Full Stage 0 report with shuffles, holdout, buckets, delay robustness, costs, funding, and capacity proxy | Any candidate failing primary direction, shuffle, symbol holdout, liquidity buckets, or delays is rejected |
| `Stage 1C` parent interaction | Test selector/veto/exposure policies for Stage 0 survivors only | Hard veto, reduce-short, delayed entry, cooldown, capacity haircut; no smooth overlay | Candidate passed independent Stage 0 and has enough selected rows | Parent interaction improves net h24/h48 metrics, adverse tail, turnover/cost drag, and passes falsification | Average uplift without causal uniqueness or delay robustness is rejected |
| `Stage 2` out-of-sample falsification | Prove the rule is not a timestamp/symbol artifact | Walk-forward, symbol-family holdout, liquidity-bucket holdout, label/time shuffle, cost/funding/slippage stress | Parent interaction passed Stage 1C | Survivor is stable across time, symbols, liquidity, and execution stress | One hard gate failure blocks bridge |
| `Stage 3` h10d bridge | Compare against h10d canonical parent without mutating its promotion state | Read-only bridge card, sidecar manifest, promotion-guard dry run | 1h rule passed Stage 2 | h10d comparison shows incremental value without canonical-state mutation | Any contamination of h10d canonical promotion state invalidates the run |
| `Stage 4` paper/live readiness | Decide whether the 1h lane is executable under API constraints | Paper simulator, kill switch, rate-limit budget, order type feasibility, participation caps, monitoring | Stage 3 bridge passed and live data path is timestamp-safe | Paper/live checklist passes with bounded turnover, capacity, slippage, funding drag, and failure modes | Missing live observability or kill switch blocks deployment |

### Stage 0.5 Evidence Freeze

Status: `complete`.

This stage created a machine-readable and human-readable ledger of the
completed 1h reports. This is not a new alpha run; it prevents accidental
promotion drift and prevents later work from reusing rejected variants as if
they were still open.

Required ledger rows:

| research_id | current decision | decisive blocker | allowed next action |
| --- | --- | --- | --- |
| `low_float_squeeze_trap_stage0_1h` | `fail` | trap state did not survive strict falsification and delay requirements | closed unless a new exogenous short-squeeze completion feature is introduced |
| `post_squeeze_exit_short_stage0_1h` | `fail` | delayed entry confirmation did not provide robust parent-worthy edge | closed; use only as source of candidate diagnostics |
| `fake_liquidity_capacity_haircut_stage0_1h` | `quarantined_state_evidence` | aggregate rule passed state-level evidence but failed parent interaction and repair tests | data-unlock retry only |
| `fake_liquidity_capacity_haircut_atoms_stage0_1h` | `fail` | requested standalone atoms failed holdout/shuffle/direction gates | closed; `volume_oi_brushing` can be retried only with venue/provider sidecar |
| `fake_liquidity_age_gated_parent_interaction_1h` | `fail` | age gate fixed holdout but failed same-timestamp shuffle and +24h delay | closed; no age-only rescue |
| `short_liquidation_completion_cooldown_stage0_1h` | `fail` | cooldown state passes shuffle, buckets, and delay but misses symbol-holdout gate | closed for admission; proceed to funding-settlement mechanical-flow test |
| `funding_settlement_squeeze_window_stage0_1h` | `fail` | window state passes symbol holdout, bucket consistency, settlement-hour shuffle, and symbol time-shift shuffle | closed for admission; same-timestamp shuffles and +24h delay fail |
| `top_trader_fade_retail_chase_veto_stage0_1h` | `fail` | account-ratio timing state passes symbol holdout, buckets, delay, and symbol time-shift shuffle | closed for admission; same-timestamp feature/label shuffles fail |
| `post_pump_bid_replenishment_failure_stage0_1h` | `fail` | sample size is broad enough, but h24 short-return delta is negative and adverse squeeze is higher | closed for admission; shuffle, symbol holdout, buckets, and delays all fail |
| `funding_normalization_after_deep_negative_stage0_1h` | `fail` | h24 direction, adverse-tail, symbol holdout, and liquidity buckets pass | closed for admission; same-timestamp shuffles and +24h delay fail |
| `liquidation_cluster_aftershock_veto_stage0_1h` | `fail` | h24 veto direction, adverse-tail, symbol holdout, liquidity buckets, and delays pass | closed for admission; same-timestamp shuffles reproduce the effect |
| `low_liquidity_hour_kill_switch_stage0_1h` | `fail` | low-capacity rows are real, but h24 direction and adverse-tail evidence are opposite the kill-switch thesis | closed for admission; shuffle, symbol holdout, buckets, and delays all fail |

Exit artifact:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/parallel_1h_stage0_decision_ledger.json`

Human-readable artifact:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/parallel_1h_stage0_decision_ledger.md`

Ledger summary:

| item | value |
| --- | --- |
| ledger rows | `18` |
| missing reports | `0` |
| admitted alpha count | `0` |
| admitted parent interaction count | `0` |
| live candidate count | `0` |
| h10d bridge allowed count | `0` |
| live use allowed count | `0` |
| decision counts | `fail=14`, `blocked_by_data=1`, `fail_explanatory_audit=1`, `quarantined_state_evidence=2` |
| overall decision | `fail` |

Stage 0.5 decision: freeze the current 1h lane as `zero_admitted_alpha`.
All completed states are either failed or quarantined as mechanism evidence.
The next work must be data-sidecar unlocking or a fresh pre-registered
mechanical-flow candidate, not post-hoc rescue.

### Stage 1A Data Sidecar Unlocks

These are data-enabling tasks, not alpha admissions. They should be implemented
before any fake-liquidity retry or `cex_inflow_bait_vs_exit` rerun.

| sidecar | unlocks | minimum fields | validation requirements | decision if unavailable |
| --- | --- | --- | --- | --- |
| `venue_concentration_1h` | real versus fake liquidity, capacity haircut, participation caps | per-symbol venue volume share, top venue share, venue count, venue missingness | coverage by symbol/hour, provider concordance where possible, closed-bar timestamps | fake-liquidity retry remains blocked |
| `native_exchange_flow_1h` | `cex_inflow_bait_vs_exit`, exchange-exit confirmation | exchange inflow/outflow, netflow, source provider, observed timestamp, delay applied | +1h/+6h/+24h delay robustness, provider/source claim boundary | CEX inflow candidate remains blocked |
| `listing_age_float_unlock_sidecar` | low-float squeeze and age diagnostics | trusted listing timestamp, circulating float proxy, unlock/event flags, source timestamp | source-vs-repo boundary, no backfilled future events, missingness report | age-only local-history proxy cannot be promoted |
| `spot_perp_concordance_1h` | spot/perp divergence and fake-volume checks | trusted spot OHLCV, perp OHLCV, basis, spread/mismatch flags | strict OHLC concordance against trusted baseline, not only coverage | spot-driven alpha remains blocked |
| `slippage_capacity_proxy_1h` | live sizing and kill-switch thresholds | depth proxy, volume/OI, taker flow, spread proxy, max participation, stress participation | bucket stability and tail stress reporting | no exposure-size promotion allowed |

Stage 1A pass does not mean an alpha is valid. It only changes branch status
from `blocked_by_data` to `ready_for_stage0`.

### Stage 1A Venue Concentration Discovery Update

Audit report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/venue_concentration_1h_sidecar_discovery.json`

Markdown summary:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/venue_concentration_1h_sidecar_discovery.md`

Initial decision: `blocked_by_data`; local non-Binance CoinAPI roots were daily
only. This was a data-side block, not an alpha pass/fail. The h10d canonical
parent was not modified.

Provider fill update on 2026-05-07:

```text
python scripts/quant_research/sync_coinapi_multi_venue_spot.py --exchanges OKEX,BYBITSPOT,COINBASE --intervals 1h --mode bootstrap
```

The fill completed without provider-level errors or `missing_at_sync` rows:
OKEX 29 symbols, BYBITSPOT 25 symbols, and COINBASE 10 symbols. The local 1h
range is `2026-03-08 04:00:00 UTC` through `2026-05-07 03:00:00 UTC`.

Updated audit decision: `pass_data_unlock`, `ready_for_stage0_builder`.

| source | 1h coverage observed after fill | venue / field evidence | decision |
| --- | --- | --- | --- |
| `coinapi_binance_spot` | 100 symbols, 713 1h partitions | Binance spot quote volume | usable venue leg |
| `coinapi_coinbase_spot` | 10 symbols, 30 1h partitions | Coinbase spot quote volume | usable venue leg for listed majors |
| `coinapi_okex_spot` | 29 symbols, 87 1h partitions | OKEX spot quote volume | usable venue leg |
| `coinapi_bybitspot_spot` | 25 symbols, 75 1h partitions | BybitSpot quote volume | usable venue leg |
| `coinglass_extended` | 93 symbols, 1,928 1h partitions | derivatives extended fields, not multi-venue volume | not used for venue share |
| `coinglass_spot_ohlcv` | 99 symbols, 689 1h partitions | Binance-only spot; strict concordance remains separate | coverage does not equal trust |

Sidecar build report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/venue_concentration_1h_sidecar_build_report.json`

Sidecar output:
`artifacts/quant_research/sidecars/venue_concentration_1h/venue_concentration_1h_sidecar.csv.gz`

Sidecar fields include `observed_venue_count`,
`missing_listed_venue_count`, `top_venue_quote_volume_share`,
`venue_share_hhi`, per-venue quote-volume shares, and
`non_binance_quote_volume_share`. Build summary: 30 subjects, 135,116
symbol-hour rows, with observed-venue-count distribution `{1: 93445, 2: 5997,
3: 22202, 4: 13472}`.

Operational conclusion: provider coverage has been filled enough to build the
1h venue-concentration sidecar, but the sidecar is explicitly
`pre_concordance`. No fake-liquidity retry or alpha rerun is allowed until
native exchange concordance validates a sample of Binance/OKX/Bybit/Coinbase
1h quote-volume bars.

Native venue-volume concordance update:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/venue_volume_native_concordance_1h.json`

Detailed comparison rows:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/venue_volume_native_concordance_1h_details.csv.gz`

Run shape: 5 symbols (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`,
`DOGEUSDT`), 24 closed hourly bars, with a +24h tail exclusion. The final
comparison window was `2026-05-04 19:00:00 UTC` through
`2026-05-05 18:00:00 UTC`.

Decision: `fail`. API access itself was not blocked, but strict native
concordance failed for 12 of 20 venue/symbol pairs. Alpha rerun remains
disabled.

| venue | result | evidence | implication |
| --- | --- | --- | --- |
| `OKEX` | pass 5/5 | close p95 `0`; base-volume p95 <= `0.000974`; actual quote p95 <= `0.002263` | OKEX CoinAPI 1h spot leg is usable for a trusted sidecar candidate |
| `BYBITSPOT` | mixed 3/5 | base-volume and close pass; `SOLUSDT` and `DOGEUSDT` fail max actual-quote outlier thresholds (`0.1074`, `0.1269`) | Bybit leg needs outlier audit before trusted use |
| `BINANCE` via CoinAPI | fail 0/5 | close roughly matches, but base-volume p95 is `0.2097` to `0.2804` | do not use CoinAPI Binance leg for trusted venue concentration; prefer direct Binance cache/API |
| `COINBASE` via CoinAPI | fail 0/5 | public Coinbase candle API has no native quote turnover; base-volume and close mismatch, with missing XRP/DOGE rows | exclude Coinbase from trusted venue concentration until source/product mapping is resolved |

Trust-masked venue-concentration sidecar update:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/trust_masked_venue_concentration_1h_build_report.json`

Markdown summary:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/trust_masked_venue_concentration_1h_build_report.md`

Sidecar output:
`artifacts/quant_research/sidecars/trust_masked_venue_concentration_1h/trust_masked_venue_concentration_1h.csv.gz`

Implementation:
`scripts/quant_research/build_parallel_1h_trust_masked_venue_concentration_sidecar.py`

Trust mask:

| leg | decision | reason |
| --- | --- | --- |
| `binance_direct` | include | uses direct Binance cache/API lineage from `%LOCALAPPDATA%/EnhengClaw/market_history/binance_ohlcv/spot`; CoinAPI Binance volume is excluded |
| `okex` | include | OKEX native concordance passed the sampled 5/5 symbols |
| `bybitspot` | partial include | only sampled-pass subjects `BTC`, `ETH`, and `XRP` enter the sidecar; `SOL` and `DOGE` are outlier-fail; all unsampled subjects fail closed |
| `coinbase` | exclude | native audit lacks quote turnover and failed strict concordance/product mapping checks |

Build summary: 30 subjects, 131,106 symbol-hour rows, trusted venue row counts
`{'binance_direct': 129624, 'okex': 41760, 'bybitspot': 4320}`, and trusted
observed-venue-count distribution `{1: 90715, 2: 36185, 3: 4206}`.

Bybit outlier attribution: `DOGEUSDT` and `SOLUSDT` both failed the strict max
actual-quote error threshold at `2026-05-05 16:00:00 UTC`, with max errors
`0.126856` and `0.107449` respectively. Those symbols are excluded from the
trusted Bybit leg.

Decision: `pass_data_sidecar_build` with
`provider_concordance_status = partial_pass_trust_masked`. This is not alpha
validation. `alpha_rerun_allowed = false`, `fake_liquidity_retry_allowed =
false`, and h10d promotion state remains untouched. The next allowed landing
shape is a pre-registered Stage 0 evaluator that consumes the trust-masked
fields as selector/exposure/capacity inputs and reruns the full falsification
matrix.

Trust-masked venue Stage 0 retry:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/trust_masked_venue_concentration_fake_liquidity_stage0_1h.json`

Implementation:
`scripts/quant_research/evaluate_parallel_1h_trust_masked_venue_concentration_fake_liquidity_stage0.py`

Pre-registered rule shape:

```text
post_pump_short_candidate_flag
AND trust_masked sidecar has >=2 observed trusted venues
AND (top trusted venue share high OR trusted venue HHI high OR trusted non-Binance dominance)
AND (volume/OI brushing OR high slippage proxy OR kill_switch_score >= 4)
```

Single-venue rows are treated as coverage context, not concentration evidence.
Bybit trust status is recorded as context, not as a standalone alpha rule.

Initial top30 run summary:

| metric | value |
| --- | ---: |
| research frame rows | 1,376,910 |
| loaded subjects | 93 |
| trust-masked sidecar rows | 131,106 |
| sidecar subjects | 30 |
| matched research rows | 120,205 |
| matched row fraction | 8.73% |
| raw post-pump candidates | 28,142 |
| post-pump candidates with any trust sidecar match | 416 |
| post-pump candidates with >=2 observed trusted venues | 74 |
| pre-registered event rows | 0 |

Initial decision was `blocked`, not `fail`, because the top30 sidecar had no
admissible event sample. The largest missing post-pump candidate contributors
were outside the sidecar, led by `PENDLE`, `RENDER`, `ETHFI`, `LDO`, `JTO`,
`JASMY`, `PYTH`, `STRK`, `CFX`, and `INJ`.

Coverage-repair execution:

| batch | added subjects | venue sync notes |
| --- | --- | --- |
| 1 | `PENDLE`, `RENDER`, `ETHFI`, `LDO`, `JTO`, `JASMY`, `PYTH`, `STRK`, `CFX`, `INJ` | OKEX missing `JASMYUSDT`; BYBITSPOT missing `CFXUSDT` |
| 2 | `THETA`, `JUP`, `MORPHO`, `ZRO`, `STX`, `GRT`, `IOTA`, `QNT`, `ENS`, `RUNE` | OKEX missing `QNTUSDT` and `RUNEUSDT`; BYBITSPOT missing `IOTAUSDT` |
| 3 | `VET`, `SEI`, `DEXE`, `AXS`, `COMP`, `TIA`, `ALGO`, `MANA`, `S`, `ICP` | OKEX missing `DEXEUSDT` and `VETUSDT`; BYBITSPOT missing `DEXEUSDT` |

Final trust-masked sidecar summary after repair: 60 subjects, 259,918
symbol-hour rows, trusted venue row counts `{'binance_direct': 257044,
'okex': 77760, 'bybitspot': 4320}`, and trusted observed-venue-count
distribution `{1: 185064, 2: 70648, 3: 4206}`. This repaired coverage, but did
not broaden Bybit trust: Bybit remains included only for sampled-pass `BTC`,
`ETH`, and `XRP`; all new unsampled Bybit subjects fail closed. OKEX inclusion
remains trusted-by-sample, not universal proof of provider quality.

Final Stage 0 rerun summary after coverage repair:

| metric | value |
| --- | ---: |
| capacity haircut candidate rows | 683 |
| pre-registered event rows | 32 |
| event rows by liquidity bucket | `mid_liquidity`: 24; `tail_liquidity`: 8 |
| h24 short-return delta | `-0.004179` |
| capacity diagnostic | `pass` |
| shuffle tests | `fail` |
| symbol holdout | `fail` |
| liquidity bucket consistency | `fail` |
| delay robustness | `fail` |

Component attribution inside the 32 final event rows: high-slippage proxy
appeared on 19 rows, kill-switch score>=4 on 10 rows, non-Binance dominance on
19 rows, top-share/high-HHI on 14 rows each, and volume/OI brushing on 15 rows.

Decision: `fail`, not `blocked`. The minimum event sample cleared after the
60-subject repair, and the capacity diagnostic correctly identified weaker
execution/capacity rows, but the rule failed same-timestamp shuffles, symbol
holdout, liquidity-bucket consistency, and +6h/+24h delay robustness. It is
closed for admission. Further work in this family must be either data
foundation / wider native concordance, or a fresh pre-registered state; no
h10d bridge or live use is allowed.

### Stage 1A Native Exchange Flow Availability Audit

Report:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/native_exchange_flow_1h_availability_audit.json`

Markdown summary:
`artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/native_exchange_flow_1h_availability_audit.md`

Implementation:
`scripts/quant_research/audit_parallel_1h_native_exchange_flow_sidecar.py`

Purpose: decide whether `cex_inflow_bait_vs_exit_stage0_1h` can move from
`blocked_by_data` to Stage 0. This is a data-sidecar audit, not alpha
validation.

Minimum sidecar requirement:

```text
PIT 1h timestamp / observed timestamp
AND per-symbol or per-asset scope
AND exchange inflow, outflow, and netflow fields
AND provider/source provenance
AND delay-ready semantics for +1h/+6h/+24h robustness tests
```

Audit summary:

| source | rows | grid | flow fields | ready | key blocker |
| --- | ---: | --- | --- | --- | --- |
| `cryptoquant_stablecoin_exchange_flows_daily` | 4,380 | daily | yes | no | stablecoin token macro flow, not native 1h symbol flow |
| `cryptoquant_reflexivity_exchange_flows_daily` | 2,190 | daily | yes | no | BTC/ETH only and daily |
| `alchemy_stablecoin_ethereum_daily_aggregates` | 405 | daily | partial | no | daily aggregate, not symbol-level 1h |
| `alchemy_stablecoin_tron_daily_aggregates` | 730 | daily | no | no | no exchange-flow fields |
| `coinglass_exchange_transfers_1d` | 31 | daily | partial | no | daily aggregate and raw direction semantics unverified |
| `coinglass_whale_transfers_1d` | 181 | daily | partial | no | daily whale aggregate |
| `coinglass_microstructure_panel_1h` | 1,359,148 | 1h | no | no | liquidation/orderbook/taker fields only |
| `coinglass_participant_panel_1h` | 1,359,148 | 1h | no | no | account/taker fields only |

CryptoQuant hourly provider probe was attempted for BTC, ETH, `usdt_eth`, SOL,
and PENDLE exchange inflow over a two-day window. All sampled probes returned
HTTP 403, so provider coverage is not available under the current entitlement
or endpoint policy. This is a source-capability claim only; it is not evidence
for or against alpha.

Decision: `blocked`. There is no local native PIT 1h exchange inflow/outflow
sidecar, no symbol-level altcoin exchange-flow coverage for the post-pump
universe, and the sampled provider-hourly path is inaccessible. Therefore
`cex_inflow_bait_vs_exit_stage0_1h` remains blocked and cannot run Stage 0.
No h10d bridge or live use is allowed.

### Stage 1B Recommended Fresh Stage 0 Experiments

The next executable priority should move away from the rejected aggregate
fake-liquidity rescue path and toward mechanical-flow states that are supported
by current 1h data.

| priority | research_id | thesis | feature definition | use shape | invalidates_if |
| --- | --- | --- | --- | --- | --- |
| 1 | `short_liquidation_completion_cooldown_stage0_1h` | After a pump, shorting before liquidation pressure completes is dangerous; entry should wait for liquidation exhaustion plus flow reversal | post-pump candidate, elevated recent liquidation notional, liquidation notional falling from local max, taker sell recovery or book pressure reversal, no renewed OI expansion | do-not-short / delayed short entry cooldown | same-timestamp shuffle passes as well as real rule, +6h/+24h delay kills effect, or only tail-liquidity bucket works |
| 2 | `funding_settlement_squeeze_window_stage0_1h` | Funding windows can mechanically extend squeeze risk and distort short carry | funding rate extreme, funding normalization slope, hours-to-funding or funding-settlement bucket, OI expansion/collapse state | veto/reduce-short near squeeze-prone settlement windows; delayed short after normalization | edge disappears after funding drag, is concentrated in one exchange/provider, or fails settlement-time shuffle |
| 3 | `top_trader_fade_retail_chase_veto_stage0_1h` | Retail/taker chase without informed positioning support can mark trap continuation or exhaustion states | taker buy imbalance, long/short account or top-trader account divergence where available, OI change, price extension | state-machine veto or delayed entry depending on top-trader direction | account-ratio coverage is sparse/untrusted, symbol holdout fails, or provider watchlist drives effect |
| 4 | `post_pump_bid_replenishment_failure_stage0_1h` | A short is safer after bids fail to replenish following liquidation/taker reversal | book pressure deterioration, taker buy exhaustion, price unable to make new highs, falling OI | delayed short entry confirmation | book proxy is too incomplete, effect is only same-bar, or slippage proxy worsens more than return improves |
| 5 | `funding_normalization_after_deep_negative_stage0_1h` | Deep-negative funding may stop being squeeze fuel only after funding normalizes and OI/taker/book pressure clears | prior deep-negative funding, funding rebound/normalization, OI not expanding, taker/book pressure cleared | delayed short entry / size restore | same-timestamp state explains the effect, +24h delay fails, or funding carry/capacity stress removes edge |
| 6 | `liquidation_cluster_aftershock_veto_stage0_1h` | Repeated short-liquidation bursts after pump can mark continuing squeeze aftershocks | trailing 24h short-liquidation burst count, recent burst pressure, no confirmed cooling, OI/taker/book pressure | do-not-short / reduce-short veto | same-timestamp state explains the effect or repeated bursts are only a generic volatility proxy |
| 7 | `low_liquidity_hour_kill_switch_stage0_1h` | Capacity-thin symbol-hours may require market-order kill switch or reduced participation | symbol-specific rolling low volume, low capacity proxy, low same-hour historical liquidity, high slippage proxy | no-market-order / reduce-short participation / hard kill switch | flagged rows are not worse shorts, adverse-tail risk is lower, or slippage proxy does not worsen |
| 8 | `venue_concentration_fake_volume_stage0_1h` | Concentrated venue volume can make apparent liquidity non-executable | venue concentration sidecar, abnormal volume/OI, low venue count, high top-venue share | capacity haircut / participation cap / kill switch | current trust-masked fake-liquidity rule failed after coverage repair; any retry needs a fresh pre-registered state and wider native concordance |
| 9 | `cex_inflow_bait_vs_exit_stage0_1h` | Exchange inflow after a pump may be either short bait or confirmed distribution depending on flow and book/taker state | native exchange inflow sidecar, delayed observed timestamp, OI, funding, taker/book reversal | delayed entry or veto | blocked until native PIT exchange-flow sidecar exists and passes delay tests |

First batch status:

1. `short_liquidation_completion_cooldown_stage0_1h`: `fail`
2. `funding_settlement_squeeze_window_stage0_1h`: `fail`
3. `top_trader_fade_retail_chase_veto_stage0_1h`: `fail`
4. `post_pump_bid_replenishment_failure_stage0_1h`: `fail`
5. `funding_normalization_after_deep_negative_stage0_1h`: `fail`
6. `liquidation_cluster_aftershock_veto_stage0_1h`: `fail`
7. `low_liquidity_hour_kill_switch_stage0_1h`: `fail`

These are preferred because they can be tested with current liquidation,
funding, OI, taker, and book/orderbook-derived 1h fields without depending on a
new trusted venue or exchange-flow sidecar. All seven have now been tested and
closed for admission.

### Stage 1C Parent-Interaction Contract

Only candidates that pass Stage 1B may enter parent interaction. The simulator
must report both standalone event evidence and changed parent rows.

Required policy variants:

| policy | intended shape | must report |
| --- | --- | --- |
| `hard_veto` | remove selected short entries entirely | changed rows, skipped notional, gross/net PnL delta, adverse-tail delta |
| `reduce_short_25pct` | keep signal but reduce exposure | size-adjusted PnL delta, capacity relief, funding drag change |
| `delayed_entry_1h_6h_24h` | wait for confirmation after trap/squeeze state | entry count retained, missed winners, avoided losers, delay robustness |
| `cooldown_until_state_clear` | block new shorts while state remains active | average cooldown hours, turnover change, opportunity cost |
| `capacity_haircut` | reduce max participation under poor execution state | max participation, volume/OI stress, slippage proxy, fill feasibility |

Admission requires improvement in net returns and adverse-tail risk after
funding, slippage proxy, and turnover cost. A candidate that only improves gross
return but increases tail loss, funding drag, or turnover is rejected.

### Stage 2 Falsification Matrix

Every Stage 1C survivor must pass the following before any h10d bridge:

| gate | required test | fail condition |
| --- | --- | --- |
| time robustness | walk-forward splits and contiguous time holdout | one favorable window explains the edge |
| symbol robustness | symbol holdout, market-cap/age family holdout, provider-watchlist exclusion | positive fraction below gate or exclusion flips result |
| liquidity robustness | head/mid/tail bucket consistency | only tail bucket works or head bucket is harmed |
| causality robustness | same-timestamp policy shuffle, time shuffle, label shuffle | shuffled policy reproduces the effect |
| delay robustness | +1h/+6h/+24h signal delays | edge depends on same-bar information |
| execution stress | fees, funding, slippage proxy, participation caps | net edge disappears or capacity is non-tradable |
| provider sensitivity | coverage versus concordance separation | coverage passes but trusted-field concordance fails |

All gates are hard gates. The default decision is `fail`; optimization is not a
substitute for falsification.

### Stage 3 H10D Bridge Boundary

The 1h lane stays parallel to the h10d canonical parent until a candidate has
passed Stage 2. Bridge work must be read-only with respect to the current h10d
promotion state.

Allowed bridge artifact:
`artifacts/quant_research/factor_reports/<run_id>/<research_id>_h10d_bridge_card.json`

Required fields:

| field | requirement |
| --- | --- |
| `h10d_parent_id` | record current canonical parent for comparison only |
| `one_hour_rule_id` | record exact 1h rule and code hash |
| `bridge_mode` | `read_only_sidecar`, never canonical mutation |
| `changed_parent_rows` | rows where 1h selector/veto would have changed h10d exposure |
| `incremental_metrics` | gross/net return, adverse tail, turnover, funding, slippage proxy |
| `falsification_status` | pass/fail for Stage 2 matrix |
| `promotion_state_mutation` | must be `false` |

If the bridge shows no incremental value, or if it requires changing h10d
canonical promotion state to look good, the candidate is rejected.

### Stage 4 Paper And Live Feasibility Gate

No 1h rule can be used in API/live trading until the live feasibility checklist
passes independently of research PnL.

Required checklist:

| area | minimum requirement |
| --- | --- |
| capacity | max participation per symbol/hour, volume/OI cap, venue concentration cap |
| turnover | expected entries/exits per day, cooldown behavior, churn under flat markets |
| funding drag | realized and stressed funding cost by bucket and signal state |
| slippage | book/depth proxy, stress multiplier, tail-liquidity haircut |
| order type | market/limit/post-only feasibility, timeout and partial-fill handling |
| rate limits | provider/API call budget, retry policy, stale-data handling |
| kill switch | stale data, provider mismatch, spread/depth shock, funding spike, venue outage |
| monitoring | live signal log, decision replay, rejected-order log, position reconciliation |
| failure modes | squeeze continuation, delisting/news halt, provider outage, symbol mapping error |

Passing Stage 4 means the rule is operationally testable in paper/live mode; it
does not retroactively prove alpha.

### Updated Recommendation

Current lane decision: `fail` for promotion, `fail` for fake-liquidity alpha
retry after coverage repair, `pass_data_sidecar_build` for
`trust_masked_venue_concentration_1h`, `fail` for
`trust_masked_venue_concentration_fake_liquidity_stage0_1h`, `fail` for
`short_liquidation_completion_cooldown_stage0_1h`, `fail` for
`funding_settlement_squeeze_window_stage0_1h`, `fail` for
`top_trader_fade_retail_chase_veto_stage0_1h`, `fail` for
`post_pump_bid_replenishment_failure_stage0_1h`, `fail` for
`funding_normalization_after_deep_negative_stage0_1h`, `fail` for
`liquidation_cluster_aftershock_veto_stage0_1h`, `fail` for
`low_liquidity_hour_kill_switch_stage0_1h`, `blocked` for
`native_exchange_flow_1h_availability_audit`, and `complete` for Stage 0.5
decision-ledger consolidation. There are still zero admitted 1h alphas and
zero parent-interaction candidates.

Recommended next execution order:

1. Do not continue the exact
   `trust_masked_venue_concentration_fake_liquidity_stage0_1h` rule for alpha
   admission. It cleared the minimum sample after repair and then failed the
   falsification matrix.
2. Run a wider Bybit native concordance sample before broad Bybit inclusion,
   only as data foundation work.
   Current Bybit trust is limited to sampled-pass `BTC`, `ETH`, and `XRP`;
   all unsampled subjects remain fail-closed.
3. Keep `cex_inflow_bait_vs_exit_stage0_1h` blocked until provider entitlement
   or an alternate source can deliver native PIT 1h exchange inflow/outflow
   with delay-ready semantics.
4. If continuing with current local 1h data, pre-register a new current-data
   candidate before coding it. The next preferred local-data shape is
   `depth_velocity_collapse_exit_stage0_1h`: a delayed-entry confirmation that
   requires bid-depth deterioration plus taker/price failure after the pump.
   It must be explicitly distinguished from the already failed
   `post_pump_bid_replenishment_failure_stage0_1h`; otherwise it should not be
   run.
5. If venue-concentration research continues, define a new pre-registered
   state before running it. Do not relax thresholds post hoc around the failed
   32-event sample.
