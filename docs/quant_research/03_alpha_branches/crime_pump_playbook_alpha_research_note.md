# Crime Pump Playbook Alpha Research Note

`Snapshot date: 2026-05-05`
`Owner: quant_research_maintainer`
`Status: external-article interpretation / ready for Stage 0 design`
`Source topic: low-float manipulation, short-squeeze pumps, pump-and-dump, orderbook accumulation`

This note converts the external article / thread commonly titled **"The Crime
Pump Playbook"** into repo-native alpha research hypotheses. It is not a claim
that the external cases are independently proven by this repo. It is a
mechanism translation: what the source describes, which parts are testable with
our data, and how those ideas should change SP-K, MF-01, MF-05, MF-07, M3.2,
and the CoinGlass full-stack roadmap.

The key conclusion is:

> `post-pump short` is not a single-stage reversal factor. It is a staged
> manipulation-state problem. The first research product should be a
> **short-side veto / exposure reduction / delayed-entry state machine**, not a
> broad smooth score overlay.

---

## 1. Source anchors

Use these external links to re-check the original claims. Do not quote them as
repo-verified truth without an independent data replay.

| source | link | use in this note |
| --- | --- | --- |
| Original X post | `https://x.com/tradinghoex/status/2050231770289713490` | original thread source |
| Rattibha mirror | `https://en.rattibha.com/thread/2050231770289713490` | readable mirror of the thread |
| Odaily English article | `https://www.odaily.news/en/post/5210591` | article-form translation and summary |
| Odaily Chinese/Thai path mirror | `https://www.odaily.news/th/post/5210591` | alternate article page observed during lookup |

Primary source claims used:

- two manipulation playbooks:
  - `MYX`: short-squeeze pump after a deliberate trap phase
  - `COAI`: faster low-float pump-and-dump
- common setup:
  - low initial circulating supply / high locked supply
  - BNB Chain / Binance Alpha / futures-listing pipeline
  - AI or narrative packaging
  - coordinated wallet accumulation
  - leverage venue where liquidation cascades can be harvested
- derivatives warning signs:
  - OI acceleration
  - deep negative funding during a "looks topped" consolidation
  - abnormal volume/OI ratio, with the article using `>20x` as a danger zone
  - venue-level OI/volume concentration
- microstructure warning signs:
  - ask-side depth thinning
  - persistent bid dominance or bid/ask ratio creep
  - taker-buy dominance
  - repeated order placement/cancellation patterns
- on-chain warning signs:
  - coordinated wallets funded from the same source
  - large wallet-to-exchange flows that can be true exit or short-bait

Interpretation rule:

- Treat the exact thresholds from the article as **priors**, not as constants.
- Re-estimate thresholds inside our own universe, timestamp grid, liquidity
  buckets, and execution assumptions.

---

## 2. What changes for the repo

### 2.1 SP-K must become stage-aware

Current SP-K framing is already stricter than "pump up = short": it targets
post-pump stall / exhaustion. This article adds an important veto:

> a pump can look overextended and still be in the short-harvesting phase.

Implication:

- do not blindly short a low-float pump while:
  - OI is still accelerating,
  - funding is deeply negative,
  - short liquidations are not yet exhausted,
  - orderbook still shows accumulation / bid support,
  - on-chain CEX inflow is not confirmed by spot sell pressure.

Preferred landing shapes:

- `do_not_short_squeeze_trap`
- `reduced_short_exposure_squeeze_trap`
- `delayed_post_pump_short_after_oi_collapse`
- `post_squeeze_exit_short`

Avoid:

- broad SP-K score overlay
- immediate short-on-pump rules
- CEX-inflow-only dump triggers

### 2.2 MF-01 orderbook / inventory gets a sharper question

The useful MF-01 question is not just whether the book is fragile. It is:

> is the book showing controlled accumulation before a short squeeze, or failed
> replenishment after the pump has already exhausted?

This creates two opposite regimes:

| regime | book behavior | short implication |
| --- | --- | --- |
| accumulation / trap | ask depth thins, bids replenish, bid/ask ratio creeps upward, taker buy pressure persists | do not short yet |
| exit / exhaustion | bid replenishment fails, ask pressure persists, taker buy fades, OI collapses | short can be allowed |

Candidate features:

- `ask_depth_thinning_1h`
- `bid_ask_ratio_creep_7d`
- `persistent_positive_orderbook_imbalance`
- `taker_buy_dominance_with_flat_price`
- `post_pump_bid_replenishment_failure`
- `post_squeeze_book_flip`

### 2.3 Fake liquidity should affect capacity and eligibility

The article's volume/OI and venue-concentration points are most useful as
execution realism, not as direct alpha.

Candidate risk fields:

- `vol_oi_brushing_risk`
- `venue_oi_concentration_z`
- `venue_volume_concentration_hhi`
- `fake_liquidity_score`
- `capacity_haircut_fake_liquidity`

Use:

- haircut ADV and quote-volume capacity
- lower max allowed participation
- exclude symbols from short replacement when observed liquidity is likely
  inflated
- separate native capacity from fake-liquidity-adjusted capacity in reports

### 2.4 On-chain CEX inflow needs a state context

The article explicitly warns that wallet-to-exchange transfers can be short
bait before the final exit.

Repo implication:

- `cex_inflow` alone should not be a dump signal
- combine it with:
  - OI collapse or OI deceleration
  - funding normalization
  - taker-sell dominance
  - bid replenishment failure
  - liquidation cascade completion

Candidate features:

- `cex_inflow_bait_state`
- `cex_inflow_confirmed_exit_state`
- `cex_inflow_with_oi_collapse`
- `cex_inflow_without_spot_sell_pressure`

### 2.5 Narrative and listing pipeline become event-state metadata

The article's BNB Chain / Binance Alpha / AI-narrative setup is not a clean
price factor by itself. It is event metadata that can condition short risk.

Useful event flags:

- `binance_alpha_listed_recently`
- `futures_listed_recently`
- `leverage_enabled_recently`
- `ai_narrative_tag`
- `bnb_chain_contract_present`
- `multi_chain_deployment`
- `low_float_high_locked_supply`
- `unlock_event_near_pump`

These belong in M3.3-style event-state plumbing and SP-K conditional gates, not
in an unconditional score.

---

## 3. Proposed manipulation state machine

### State 0: precondition / manipulability

Definition:

- low circulating supply or high locked supply
- recently launched or recently listed
- narrative cover exists
- leverage venue exists or is imminent
- spot liquidity is thin relative to FDV / market cap

Research use:

- qualify the symbol for special handling
- do not trade solely from this state

### State 1: stealth accumulation

Definition:

- price and OI not yet extreme
- ask-side depth thinning
- bids replenish near market
- bid/ask ratio creeps toward balance or positive dominance
- taker buy flow persists without a proportional price response
- coordinated wallet inflow / repeated funding-source pattern if available

Research use:

- do-not-short state
- potential watchlist for future squeeze-risk

### State 2: lure-shorts / trap consolidation

Definition:

- recent abnormal pump
- price consolidates rather than collapses
- funding turns deeply negative
- OI keeps rising or stays high
- shorts appear crowded
- narrative says "obvious short"

Research use:

- veto SP-K shorts
- reduce short exposure
- test short-squeeze forward risk at `h24h/h48h/h72h`

### State 3: squeeze / forced buyback

Definition:

- price breaks above consolidation
- short liquidations spike
- OI and volume spike
- funding remains stressed or flips violently
- taker buy dominance persists

Research use:

- no new shorts
- possible squeeze-risk sleeve only if execution/cost is realistic
- mainly used to learn exit timing, not immediate alpha promotion

### State 4: baited CEX inflow

Definition:

- large wallet-to-exchange flow appears
- OI/funding/orderbook still show squeeze-risk
- price has not confirmed real distribution

Research use:

- do not treat CEX inflow as enough to short
- require confirmation before SP-K entry

### State 5: true exit / post-squeeze exhaustion

Definition:

- OI collapses or decelerates
- funding normalizes or stops being deeply negative
- taker buy pressure fades
- bid replenishment fails
- ask pressure persists
- CEX inflow has sell-pressure confirmation

Research use:

- allow post-pump short
- short replacement / delayed entry
- reduced-exposure veto removed

---

## 4. Stage 0 research design

### Stage 0A: `low_float_squeeze_trap_stage0`

Question:

> When SP-K or the parent strategy wants to short a post-pump low-float name,
> does a squeeze-trap state predict worse short outcomes over the next 24-72h?

Universe:

- current executable perp universe
- mid-liquidity and tail-liquidity symbols first
- exclude true no-history names until CoinGlass spot/perp coverage is fixed

Candidate label:

```text
squeeze_trap =
    recent_pump
    and OI_acceleration_positive
    and funding_extremely_negative
    and (orderbook_bid_support or taker_buy_dominance)
    and not OI_collapse_confirmed
```

Primary outcomes:

- next `24h/48h/72h` short return
- next `1d` `>5%` and `>10%` adverse squeeze frequency
- short liquidation intensity after entry
- change in parent selected-short basket quality

Pass condition:

- flagged selected shorts have materially worse short payoff or higher adverse
  squeeze rate than unflagged selected shorts
- effect survives symbol holdout and liquidity-bucket split
- no single symbol accounts for the result

Preferred landing if pass:

- selected-short exposure reduction
- selected-short veto only if replacement rows are better
- delayed short entry after exit confirmation

### Stage 0B: `post_squeeze_exit_short_stage0`

Question:

> After a squeeze state, does OI collapse plus orderbook/taker reversal identify
> the real short window better than raw post-pump stall?

Candidate label:

```text
post_squeeze_exit =
    prior_squeeze_state
    and OI_collapse_or_deceleration
    and funding_normalization
    and taker_buy_fade
    and bid_replenishment_failure
```

Primary outcomes:

- next `3d/5d/10d` forward return
- SP-K selected-short improvement
- parent boundary replacement edge

Pass condition:

- stronger than raw `post_pump_stall`
- still works under +1d delay
- survives cost and funding drag

### Stage 0C: `fake_liquidity_capacity_haircut`

Question:

> Does extreme volume/OI or venue concentration identify names where the
> current capacity model overstates executable liquidity?

Candidate fields:

```text
vol_oi_ratio = perp_quote_volume_usd / open_interest_value
venue_volume_hhi = sum(venue_volume_share^2)
venue_oi_hhi = sum(venue_oi_share^2)
fake_liquidity_score = z(vol_oi_ratio) + z(venue_volume_hhi) + z(venue_oi_hhi)
```

Primary outcomes:

- realized slippage proxy
- next-day adverse move after selected short
- sensitivity of max trade participation
- headline strategy performance before/after haircut

Pass condition:

- haircut improves adverse-tail profile without destroying alpha
- capacity report changes are material and interpretable

### Stage 0D: `cex_inflow_bait_vs_exit`

Question:

> Is wallet-to-exchange flow a dump signal only after derivatives and
> microstructure confirm the exit state?

Candidate labels:

```text
cex_inflow_bait =
    cex_inflow_spike
    and not OI_collapse
    and (funding_deep_negative or taker_buy_dominance)

cex_inflow_confirmed_exit =
    cex_inflow_spike
    and OI_collapse
    and taker_sell_dominance
    and bid_replenishment_failure
```

Pass condition:

- bait state has worse immediate short outcomes
- confirmed-exit state has better `h3d/h5d/h10d` short outcomes

---

## 5. Required data and current provider mapping

| data need | current / planned source | local status |
| --- | --- | --- |
| 1h spot OHLCV and volume | CoinGlass spot or CoinAPI/Binance | CoinGlass provider planned in `coinglass_full_stack_data_research_roadmap.md` |
| perp OI / funding / volume | CoinGlass futures | partially implemented |
| liquidation intensity | CoinGlass extended | implemented |
| orderbook bids/asks | CoinGlass extended | implemented, needs coverage audit |
| taker buy/sell | CoinGlass extended and possibly spot taker endpoints | implemented for futures side; spot planned |
| venue OI / volume concentration | CoinGlass / CoinAnk-style venue breakdown if API available | not yet verified in local provider |
| CEX inflow/outflow | CoinGlass on-chain, CryptoQuant, Alchemy labels | partial / planned |
| low float / unlock schedule | CoinMarketCap, CoinGecko, TokenUnlocks, project metadata | not yet local; should start as event sidecar |
| listing / leverage enable dates | Binance Alpha, Binance Futures, Aster/Bybit listing metadata, news/event tape | not yet local; M3.3 sidecar candidate |
| wallet coordination | Arkham/Bubblemaps-style cluster data | not local; use as manual labels unless API exists |

---

## 6. Validation and falsification rules

A manipulation-state candidate is not promotable unless it passes:

- time-shuffle falsification
- label-shuffle falsification
- symbol holdout
- liquidity-bucket consistency
- +1d delay robustness for any signal relying on external publication timing
- native-only vs derived-data sensitivity, especially for OI value
- cost and funding drag stress
- max trade participation and capacity haircut review
- replacement-row economics if used as a veto/replacement

Specific veto for overfitting:

- do not tune thresholds to MYX/COAI case dates
- do not use BNB/AI tags as alpha alone
- do not call CEX inflow a dump signal without derivatives confirmation
- do not promote vendor/social claims before local replay
- do not open a manifest A/B until Stage 0 says the landing shape is correct

---

## 7. Report template

Every Stage 0 report spawned from this note should include:

```text
research_id
source_claims_used
data_sources_and_coverage
feature_definitions
event_count_by_symbol
event_count_by_liquidity_bucket
forward_return_table_h24h_h48h_h72h_h3d_h5d_h10d
adverse_squeeze_frequency
selected_short_changed_rows
entered_vs_exited_short_economics
funding_drag_summary
capacity_haircut_summary
shuffle_tests
symbol_holdout
liquidity_bucket_consistency
pass_fail_decision
next_landing_shape
```

---

## 8. Updated local priority

This note does not replace the CoinGlass full-stack roadmap. It depends on it.

Recommended order:

1. execute CoinGlass spot/futures coverage reset
2. re-baseline `v5_rw_bridge_no_overlay_h10d`
3. run `low_float_squeeze_trap_stage0`
4. run `post_squeeze_exit_short_stage0`
5. add `fake_liquidity_capacity_haircut` to capacity reports
6. only then test SP-K canonical-parent replacement/veto variants with the new
   state columns

Priority ranking among active research lanes:

| rank | lane | reason |
| ---: | --- | --- |
| 1 | `low_float_squeeze_trap_stage0` | directly fixes SP-K's highest-risk false positive |
| 2 | `post_squeeze_exit_short_stage0` | converts "do not short yet" into delayed short entry |
| 3 | `fake_liquidity_capacity_haircut` | protects execution realism from brushed volume/OI |
| 4 | `cex_inflow_bait_vs_exit` | prevents on-chain flow from becoming a false dump trigger |
| 5 | richer wallet-cluster / listing-pipeline labels | valuable but currently less local-data-ready |

---

## 9. Bottom line

The source's strongest contribution is not a new single factor. It is a warning
that the same observable event, "small token pumped hard", can mean opposite
things depending on stage:

- before squeeze completion: shorting can be the crowded trade being harvested
- after OI/liquidation/orderbook exhaustion: shorting can become the right
  post-pump decay trade

Therefore the next SP-K-family research should be a **manipulation state
machine** with explicit veto, exposure reduction, and delayed-entry states.
This fits the repo's current lesson: sparse mechanical information should first
touch the selection boundary, not the whole cross-sectional score.
