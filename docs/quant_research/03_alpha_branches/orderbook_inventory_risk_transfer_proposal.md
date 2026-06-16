# Orderbook / Inventory Risk Transfer Research Proposal

`Context-Version: 2026-05-02.2`
`Owner: quant_research_maintainer`
`Status: stage-0 first pass complete`
`Sub-path ID: SP-L`
`Scope: 1h orderbook-driven inventory-risk-transfer alpha for short-side selection`
`Authoring mode: research proposal`

---

## English TL;DR

This proposal formalizes a research path for extracting alpha from **1h
orderbook depth and inventory-transfer states** already present in the
CoinGlass extended cache.

The target is **not** "another daily factor". The core question is:

- when a price impulse happens, does the book **replenish** or **fail**?
- does orderbook behavior tell us **which short to keep**, **which short to
  veto**, or **which post-cascade rebound not to fade**?

The proposal treats MF-01 as a **selection-layer mechanism**:

- best initial landing: `short replacement`
- second landing: `do-not-short veto`
- third landing: event-conditioned `gate`
- lowest-priority landing: smooth full-score overlay

This ranking follows the strongest lesson from `SP-K`: sparse, local, mechanical
alpha often becomes real only when it touches the **selection boundary**, not
when it is smoothed into the whole cross-sectional score.

---

## Research update (2026-05-02)

This lane is now high-priority because the repo has already learned three
important things:

- **The data is ready.**
  The 1h CoinGlass extended cache already contains `orderbook_bids_usd`,
  `orderbook_asks_usd`, `orderbook_bids_quantity`, `orderbook_asks_quantity`,
  `taker_buy_volume_usd`, `taker_sell_volume_usd`, and positioning fields for
  the top-liquidity universe:
  [market_data_inventory.md](../01_data_foundation/market_data_inventory.md)
- **MF-01 is still materially under-explored.**
  The daily panel already carries one orderbook-derived feature,
  `coinglass_orderbook_imb_persistence_24h`, but there has been no formal
  MF-01 admission or cycle path yet. `SP-B` only sketched `B1` and mostly
  explored MF-07 / MF-15 siblings:
  [data_utilization_roadmap.md](../00_roadmap_state/data_utilization_roadmap.md)
- **The best current architecture is selection-layer, not full-score.**
  `SP-K` showed that a sparse event-family can be weak as a standalone score,
  flat as a smooth overlay, and genuinely additive as a short-slot replacement
  rule:
  [small_cap_post_pump_short_proposal.md](small_cap_post_pump_short_proposal.md)

So the right way to attack MF-01 is:

1. start from **boundary decisions**,
2. condition on **post-pump / post-squeeze / post-cascade states**,
3. test whether book replenishment or thinness changes **which short should be
   held**.

Current owner-side read:

- **Highest ready-to-build lane** among next-stage alpha candidates:
  [next_stage_alpha_map.md](../00_roadmap_state/next_stage_alpha_map.md)
- **Not** the right lane for a fresh unconditional base score on day one.
- Very likely the right lane for:
  - `selected-short replacement`
  - `do-not-short veto`
  - post-event `gate`

**Stage 0 first-pass result (2026-05-02)**:

- **`boundary_fragile_orderbook` is the cleanest broad signal so far.**
  Inside the current `v6_h10d` short-boundary candidates, names flagged by weak
  replenishment or persistent ask pressure show mean forward returns of roughly
  `-0.42% / -1.31% / -2.04%` for `h3d / h5d / h10d`, with `h5d` / `h10d`
  t-stats around `-2.14 / -2.25`. This is the best evidence so far that MF-01
  belongs first in **short-slot replacement**, not in a fresh global score.
- **`pump_bid_replenishment_failure` is sparse but high-conviction.**
  On all core-20 names it is only a small sample, but inside
  `boundary_candidates` it prints about `-4.85%` at `h5d` and `-9.59%` at
  `h10d` (`n=8`), with `100%` negative-rate at `h10d`. The same pattern also
  looks strong inside current bottom-3 shorts, which suggests this rule is a
  promising candidate for a higher-conviction but sparse replacement trigger.
- **`pump_ask_pressure_persistence` is directionally right but still too sparse.**
  It shows the expected negative sign across `h3d / h5d / h10d`, but only
  `n=10` events in the first pass. It should stay as a confirmation branch, not
  the lead lane.
- **`selected_short_supportive_replenishment` is NOT yet a valid veto.**
  The naive "bid-heavy / replenished book means do-not-short" story is
  currently falsified in the active bottom-3 short book. Those names still show
  negative forward returns on average, so supportive replenishment by itself is
  not enough to justify a veto.
- **`cascade_bid_absorption_rebound` is mixed.**
  At the broad core-20 level it looks like a short-horizon rebound-risk state
  (`h3d` / `h5d` positive on average), but it does not survive cleanly inside
  the currently selected short book and flips weak or negative by `h10d`. This
  is not yet a promotable selected-short veto rule.

Primary implementation / evidence context:

- `src/enhengclaw/quant_research/coinglass_extended.py`
- `src/enhengclaw/quant_research/lab.py`
- `src/enhengclaw/quant_research/intraday_microstructure_features.py`
- `scripts/quant_research/alpha_branch_reports/compute_orderbook_inventory_event_study.py`
- `artifacts/quant_research/factor_reports/2026-05-02/orderbook_inventory_event_study.json`
- `artifacts/quant_research/factor_reports/2026-05-02/orderbook_inventory_event_rows.csv`
- `artifacts/quant_research/factor_reports/2026-05-02/orderbook_inventory_daily_state.csv`
- `docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md`
- `docs/quant_research/00_roadmap_state/data_utilization_roadmap.md`
- `docs/quant_research/00_roadmap_state/next_stage_alpha_map.md`

**Formal A/B result on the active parent (2026-05-02)**:

- **MF-01 is now mechanically live on `v6_h10d`, but the first replacement rules are not additive.**
  Three formal variants were tested on the active parent:
  `mf01_boundary_fragile_v1`, `mf01_pump_bid_fail_v1`, `mf01_combo_v1`.
- **`boundary_fragile` and `combo` both underperform the current SP-K boundary winner.**
  Relative to `replace_mid_v1_no_news`, both land at
  `walk_forward_median_oos_sharpe = 2.461` versus `4.076`,
  worsen `loss_window_fraction` from `0.3125` to `0.34375`,
  and weaken short-basket `next_10d_mean` from about `-0.248%` to `-0.109%`.
  In this first pass the combo rule is effectively the same rule as the broad
  `boundary_fragile_orderbook` replacement.
- **`pump_bid_replenishment_failure` is too sparse and too churny in broad replacement form.**
  It changes shorts on about `98.6%` of timestamps, but degrades the basket:
  `walk_forward_median_oos_sharpe = 2.270`,
  `loss_window_fraction = 0.40625`,
  `positive_regime_fraction = 1/3`,
  and short-basket `next_10d_mean` weakens to roughly `-0.009%`.
- **Owner-side interpretation.**
  Stage 0 successfully identified a real mechanism, but the first T1 landing
  shape is still wrong. The correct recording is:
  **signal discovered, replacement architecture not promoted**.

**Formal narrow-shape A/B result on the active parent (2026-05-02)**:

- **`mf01_spk_confirm_v1` is real, but non-additive.**
  This version uses MF-01 only as an SP-K confirmation gate on top of
  `replace_mid_v1_no_news`. It is not a no-op: it changes `89` short slots
  versus the SP-K winner across about `8.2%` of timestamps. But the cycle
  result stays flat at `walk_forward_median_oos_sharpe = 4.076`,
  `loss_window_fraction = 0.3125`, and
  `worst_regime_median_oos_sharpe = -1.783`. The changed names are not better
  shorts: entered replacements show `next_10d_mean = +2.87%` versus
  `+2.04%` for the names they eject.
- **`mf01_spk_ss_veto_v1` is an exact no-op under the current short-boundary construction.**
  The veto flag does hit already-selected shorts (`14` rows, about `1.28%` of
  timestamps), but no better eligible replacement is found inside the current
  pool, so realized short-slot changes versus `replace_mid_v1_no_news` are
  exactly `0`.
- **`mf01_post_cascade_guardrail_v1` is too sparse and still not a usable do-not-short rule.**
  It triggers only `7` realized short replacements (about `0.64%` of
  timestamps) and leaves the portfolio metrics unchanged versus
  `replace_mid_v1_no_news`. More importantly, the selected-short rows it flags
  still average about `-3.68%` over the next `10d`, so the present guardrail is
  not yet identifying the wrong shorts to remove.
- **Owner-side interpretation.**
  MF-01 microstructure state is now fully plumbed through the active parent and
  has survived both broad and narrow landing-shape tests. But none of the
  narrow forms beats `replace_mid_v1_no_news`. The correct recording is:
  **mechanism real, plumbing retained, narrow landing shapes still not promoted**.

---

## A. Research question

Can we build robust, event-conditioned MF-01 features from **1h orderbook depth
and replenishment behavior** that improve short-side selection beyond the
current `v6_h10d` parent strategy?

The target is not a generic statement like "ask-heavy book means down". The
target is a more operational question:

1. after a price impulse, is inventory being **absorbed** or **transferred**?
2. does the book show **bid replenishment** or **ask persistence**?
3. can that state improve:
   - which marginal short is selected,
   - which short should be vetoed,
   - or which post-cascade name should not be faded?

---

## B. Economic hypothesis

MF-01 is built on a mechanical market-making story:

- takers push inventory onto market makers,
- market makers reprice quotes to manage inventory and risk,
- displayed depth then either **replenishes** or **stays one-sided**,
- that state contains information about near-future price drift or reversal.

There are two especially important cases.

### B.1 Fragile upside case

After an upside impulse:

- taker buying lifts price,
- displayed bids fail to replenish,
- asks remain heavy or quickly rebuild above spot,
- the book stays thin relative to the recent flow impulse.

That is a **fragile pump** setup. The marginal buyer has already spent capital,
but the book has not normalized. Expected outcome: weaker continuation and
higher odds of mean reversion over the next few days.

### B.2 Supportive downside case

After a downside impulse or liquidation event:

- bids replenish aggressively,
- ask pressure fades,
- book imbalance normalizes faster than price,
- taker sell pressure decays.

That is a **do-not-short / rebound-risk** setup. The information is not "buy
everything"; it is "do not keep the wrong short".

This is why MF-01 should first be treated as a **selection-layer mechanism**,
not a broad rank-everything factor.

---

## C. Why this alpha might persist

- **Mechanical inventory transfer**:
  orderbook adjustments are constrained by market-maker balance-sheet risk, not
  just discretionary belief.
- **Shallow alt books**:
  even modest flow can create persistent depth asymmetry in crypto perps.
- **Execution friction**:
  many participants cannot instantly arbitrage or size into thin books without
  moving price further.
- **State dependence**:
  most models see price and volume, but not whether the book is refilling or
  staying empty after the impulse.
- **Better local use than global use**:
  if the signal only matters at the selection boundary, many broad IC tests will
  underestimate it unless the landing shape is chosen correctly.

---

## D. Ontology mapping

MF-01 is the anchor family, but the practical research path is hybrid.

| family | role in SP-L | why it matters |
| --- | --- | --- |
| **MF-01 inventory_risk_transfer** | primary anchor | direct mapping from book replenishment / one-sided depth to future drift |
| **MF-06 reflexive_flow** | flow confirmation | taker imbalance helps identify whether depth stress is flow-driven |
| **MF-08 event_impulse** | conditioning | the same book state means different things after a pump vs after a cascade |
| **MF-10 higher_moment_fragility** | volatility context | thin-book risk is strongest when range expansion is already elevated |
| **MF-12 state_space_regime** | optional gate | book effects may behave differently in broad stress or rebound regimes |

Interpretation:

- MF-01 supplies the **microstructure state**,
- MF-08 tells us **when to care**,
- MF-06 helps tell us **why the book is stressed**.

---

## E. Proposed factor family

This should be tested as a family, not as one formula.

| factor_id | candidate column name | sign | EHL (days) | tier | core idea |
| --- | --- | --- | --- | --- | --- |
| L1 | `orderbook_imb_velocity_1h_30d` | conditional | 3-7 | T1 | persistent churn in hourly imbalance proxies unstable inventory transfer |
| L2 | `post_pump_bid_replenishment_failure_24h` | `-` | 2-5 | T1 | after upside impulse, bids do not refill even as price stalls |
| L3 | `post_pump_ask_pressure_persistence_24h` | `-` | 2-5 | T1 | ask-heavy book remains after pump, signaling weak continuation quality |
| L4 | `thin_book_taker_exhaustion_24h` | `-` | 3-7 | T1 | aggressive taker buying into thin depth leaves fragile upside inventory |
| L5 | `post_cascade_bid_absorption_rebound_24h` | `+` | 1-5 | T1 | after downside shock, bids refill faster than price, raising rebound risk |
| L6 | `inventory_transfer_gap_24h` | conditional | 2-5 | T1 | book re-prices more than spot or flow would imply, revealing hidden inventory stress |

### E.1 Candidate L1: `orderbook_imb_velocity_1h_30d`

**Purpose**: establish the broad MF-01 baseline already foreshadowed by `SP-B`.

Sketch:

1. compute hourly orderbook imbalance:
   `ob_imb_1h = (bids_usd - asks_usd) / (bids_usd + asks_usd)`
2. compute rolling instability or churn over a 30d window:
   `rolling_std(ob_imb_1h, 720h)` or a closely related velocity measure
3. aggregate to daily-grain state and cross-sectionally z-score

Interpretation:

- high churn can mean inventory is being repeatedly transferred and repriced,
- but the direction is state-dependent,
- so this is more a **conditioning state** than a standalone signed factor.

### E.2 Candidate L2: `post_pump_bid_replenishment_failure_24h`

**Purpose**: identify fragile upside states for short selection.

Sketch:

1. detect an upside impulse:
   strong return / range / taker-buy imbalance / pump-state trigger
2. measure whether bids refill over the next 6-24h:
   compare post-event bid depth vs pre-event bid depth or rolling baseline
3. assign more-negative score when bid replenishment is weak

Interpretation:

- buyers pushed price up,
- but new passive demand did not refill underneath,
- continuation quality is poor.

### E.3 Candidate L3: `post_pump_ask_pressure_persistence_24h`

**Purpose**: detect upside exhaustion via continued ask dominance.

Sketch:

1. compute share of post-event hours where:
   - `asks_usd > bids_usd`, or
   - `ob_imb_1h < 0`
2. optionally weight by how thin the total displayed depth is
3. use higher persistence as a more-negative short score

Interpretation:

- displayed supply remains stronger than displayed demand even after the pump,
- suggesting the move was not cleanly reabsorbed.

### E.4 Candidate L4: `thin_book_taker_exhaustion_24h`

**Purpose**: tie book thinness directly to flow intensity.

Sketch:

`taker_imbulse / displayed_depth`

Possible implementation:

- numerator:
  post-event taker-buy imbalance or cumulative taker-buy USD
- denominator:
  mean or minimum displayed depth over the same window

Interpretation:

- aggressive takers got a lot done against not much depth,
- which often leaves weak-handed inventory after the initial impulse fades.

### E.5 Candidate L5: `post_cascade_bid_absorption_rebound_24h`

**Purpose**: use MF-01 as a **do-not-short / rebound-risk** state.

Sketch:

1. detect downside shock or liquidation state
2. measure whether bids replenish quickly and persistently in the next 6-24h
3. assign positive score, or use as a veto against keeping the short

Interpretation:

- the market has already transferred inventory,
- fresh passive demand is showing up,
- fading that name from the short side becomes dangerous.

### E.6 Candidate L6: `inventory_transfer_gap_24h`

**Purpose**: detect mismatch between book state and realized price adjustment.

Sketch:

- build a simple expected price-pressure model from:
  - return impulse,
  - taker imbalance,
  - recent volatility,
  - displayed depth
- use the residual between observed depth state and price state as the signal

Interpretation:

- if the book remains stressed even after price has moved, more adjustment may
  still be pending,
- if the book normalizes before price does, the move may already be exhausted.

---

## F. Existing field mapping

### F.1 Direct-ready 1h primitives

These are already available in the 1h CoinGlass extended cache:

| field | source | immediate use |
| --- | --- | --- |
| `orderbook_bids_usd` | `coinglass_extended 1h` | displayed bid depth |
| `orderbook_asks_usd` | `coinglass_extended 1h` | displayed ask depth |
| `orderbook_bids_quantity` | `coinglass_extended 1h` | size depth alternative |
| `orderbook_asks_quantity` | `coinglass_extended 1h` | size depth alternative |
| `taker_buy_volume_usd` | `coinglass_extended 1h` | flow impulse |
| `taker_sell_volume_usd` | `coinglass_extended 1h` | flow impulse |
| `top_trader_long_pct` | `coinglass_extended 1h` | participant confirmation |
| `global_account_long_pct` | `coinglass_extended 1h` | participant confirmation |
| `long_liquidation_usd` | `coinglass_extended 1h` | downside shock state |
| `short_liquidation_usd` | `coinglass_extended 1h` | squeeze / upside stress state |

### F.2 Existing daily-grain derived features already in the panel

These are already built in `lab.py` and available to the daily panel:

| field | current definition | relevance |
| --- | --- | --- |
| `coinglass_orderbook_imb_persistence_24h` | lag-1 autocorr of hourly orderbook imbalance over the UTC day | first MF-01 proxy |
| `coinglass_taker_imb_intraday_dispersion_24h` | std of hourly taker imbalance | flow instability |
| `coinglass_liq_intraday_concentration_24h` | max 1h liquidation share of daily total | event concentration |
| `coinglass_top_trader_intraday_volatility_24h` | std of top-trader long% within day | participant instability |
| `coinglass_liquidation_imbalance_24h` | daily liquidation imbalance | downside / squeeze conditioning |
| `coinglass_taker_imbalance_5d_sum` | rolling sum of daily taker imbalance | flow context |

### F.3 New T1 derived columns to add

These are not yet standardized in the panel, but can be built immediately from
existing 1h raw data:

| proposed field | formula sketch | used by |
| --- | --- | --- |
| `ob_imb_1h` | `(bids_usd - asks_usd) / (bids_usd + asks_usd)` | L1-L6 |
| `ob_depth_usd_total_1h` | `bids_usd + asks_usd` | L2-L4 |
| `ob_depth_qty_total_1h` | `bids_qty + asks_qty` | L2-L4 |
| `ob_depth_usd_z_30d` | z-score of hourly displayed depth vs trailing baseline | L2-L4 |
| `bid_replenishment_ratio_6h` | post-event bid depth / pre-event bid depth | L2, L5 |
| `bid_replenishment_ratio_24h` | post-event bid depth / pre-event bid depth | L2, L5 |
| `ask_pressure_hours_share_24h` | share of hours with ask-heavy book after event | L3 |
| `thin_book_taker_impact_24h` | taker flow impulse / mean displayed depth | L4 |
| `ob_imb_velocity_6h` | change in imbalance over 6h | L1, L6 |
| `ob_depth_velocity_6h` | change in total depth over 6h | L1, L2, L6 |

### F.4 Companion conditioning fields

These are already available elsewhere in the repo and should be used for event
conditioning:

- `return_1`, `range_position`, `distance_to_high_5`
- `perp_quote_volume_usd`
- `open_interest`, `oi_change_5`
- `funding_rate`, `funding_zscore_20`
- `coinglass_liquidation_imbalance_24h`
- `coinglass_taker_imbalance_5d_sum`
- `post_pump_stall_core_score_3d` as an optional downstream trigger

---

## G. Stage 0 event-study design

Do **not** start with broad IC. Start with conditioned event studies.

### G.1 Stage 0-A: post-pump thin-book fragility

**Question**:
after upside impulses, do names with weak bid replenishment or persistent ask
pressure produce more negative `3d / 5d / 10d` forward returns?

**Universe**:

- first pass: `liquid_perp_core_20`
- second pass: `top_liquidity_ex_majors`
- third pass only if coverage is acceptable: `mid_liquidity`

**Event definition**:

- daily pump or post-pump-stall candidate
- optionally require elevated taker-buy or positive short-liquidation stress

**Buckets**:

- strong vs weak bid replenishment
- high vs low ask-pressure persistence
- high vs low thin-book-taker impact

**Primary readouts**:

- mean / median forward log return at `h1d / h3d / h5d / h10d`
- negative-return fraction
- next-day squeeze fraction for the short leg

### G.2 Stage 0-B: selected-short boundary conditioning

**Question**:
inside the current `v6_h10d` short boundary, does MF-01 identify which marginal
short should be replaced?

**Design**:

1. take the baseline bottom-6 short candidate pool,
2. compare names with:
   - weak replenishment / ask persistence
   - supportive replenishment / rebound risk
3. measure whether the weak-replenishment bucket has more negative forward
   returns than the supportive bucket

**Why this is critical**:

- this is the most realistic first landing,
- and it directly matches the architecture already validated by `SP-K`.

### G.3 Stage 0-C: post-cascade bid absorption

**Question**:
after downside liquidation or large downside impulses, does strong bid
replenishment warn us not to keep the short?

**Design**:

1. detect downside-shock days using liquidation or return thresholds,
2. split on post-event bid replenishment,
3. test whether strong replenishment predicts positive `3d / 5d / 10d`
   returns or higher short squeeze risk.

**Why this matters**:

- this may become a cleaner `do-not-short veto` than an outright return factor.

### G.4 Minimum success signal

The family deserves Stage 1 factorization only if at least one of these is
true:

1. post-pump weak-replenishment cohorts show clearly worse forward returns than
   strong-replenishment cohorts;
2. baseline short-boundary names with adverse MF-01 state are materially better
   shorts than the names with supportive-replenishment state;
3. post-cascade supportive-replenishment cohorts show higher rebound risk,
   creating a usable short veto.

---

## H. Falsification path

Reject or de-prioritize the lane if:

1. **Event-study falsification**
   conditioned cohorts do not show stable forward-return separation;
2. **Boundary falsification**
   MF-01 does not improve bottom-6 / bottom-3 short candidate quality;
3. **Orthogonality falsification**
   any continuous factor is fully absorbed by existing
   `coinglass_taker_imbalance_5d_sum`, `coinglass_liquidation_imbalance_24h`,
   or `SP-K` state variables;
4. **Cycle falsification**
   replacement or veto variants improve median Sharpe but reliably worsen short
   basket quality and regime tails;
5. **Mechanism falsification**
   upside thin-book states do not behave differently from supportive
   replenishment states after controlling for flow intensity.

---

## I. Best landing shape

### I.1 First-choice landing: `short replacement`

This is the highest-priority landing.

Pattern:

- start from the current healthy parent strategy,
- inspect the marginal short candidate pool,
- prefer names whose post-event book state looks **fragile**,
- replace names whose post-event book state looks **supportive**.

Why this is first:

- it matches the successful `replace_mid_v1` lesson,
- it minimizes the risk of forcing a local alpha into a global score.

### I.2 Second-choice landing: `do-not-short veto`

This is especially relevant for:

- post-cascade bid replenishment,
- names with fast book normalization after downside stress,
- names where ask pressure disappears too quickly to justify a fresh short.

Why this is second:

- MF-01 may be better at avoiding the wrong short than at identifying the very
  best short.

### I.3 Third-choice landing: event-conditioned `gate`

Examples:

- only activate SP-K short replacement when book thinness confirms fragility,
- or suppress shorting when rebound-risk book states appear after liquidation.

Why this is third:

- gates are powerful, but usually need a better-understood core selector first.

### I.4 Lowest-priority landing: smooth full-score overlay

This is explicitly the least preferred first implementation.

Why:

- MF-01 is likely sparse and local,
- the repo already has strong evidence that smoothing local signals into the
  full score often produces `AT-PAR` or misleading gains.

---

## J. Concrete next steps

### J.1 Immediate T1 path

Completed on `2026-05-02`:

1. built the daily MF-01 state panel from CoinGlass 1h orderbook / taker-flow data
2. ran `Stage 0-A / B / C` event studies
3. converted the lead Stage 0 rules into formal `v6_h10d` short-boundary
   replacement scorers and ran cycle-level A/B diagnostics

### J.2 If Stage 0 passes

Completed:

1. `boundary_fragile_orderbook_score`
2. `pump_bid_replenishment_failure_score`
3. `mf01_short_boundary_combo_score`

Outcome:

- the columns and scorers are now wired into the deterministic `v6_h10d` path,
- but the first replacement forms are **non-additive** relative to the current
  SP-K short-boundary winner,
- so MF-01 should **not** move to smooth-overlay or broad score-admission work yet.

### J.3 Immediate next iteration

Do **not** try a smooth score perturbation yet. The requested narrow-shape pass
has now been completed:

1. `SP-K confirmation gate` tested as `mf01_spk_confirm_v1`
2. `selected-short veto` tested as `mf01_spk_ss_veto_v1`
3. `post-cascade rebound guardrail` tested as `mf01_post_cascade_guardrail_v1`

Current owner-side read:

1. keep the MF-01 columns and scorers in the research stack,
2. keep `replace_mid_v1_no_news` as the preferred live short-boundary shape,
3. do **not** advance MF-01 to smooth-overlay or broad score-admission work,
4. only revisit MF-01 if a future event-conditioned architecture can make the
   veto actually touch the realized short book in a beneficial way.

---

## K. Pre-registered success criteria

SP-L should be considered a serious promotion candidate only if:

1. at least one MF-01 event cohort shows stable and economically meaningful
   forward-return separation,
2. the short-boundary study shows better candidate quality under the intended
   replacement / veto rule,
3. the first formal replacement or veto backtest improves short-basket
   economics,
4. and it does **not** worsen regime tails beyond the benefit.

If it only improves median walk-forward but worsens basket quality and tails, it
should be recorded as **mechanically live but not promoted**, exactly as we now
do for the current selected-short news-veto architecture.

---

## Cross-references

- Mechanism families:
  - [alpha_ontology_and_factor_library.md](../00_roadmap_state/alpha_ontology_and_factor_library.md)
  - [mechanism_notes/MF_08_event_impulse.md](../mechanism_notes/MF_08_event_impulse.md)
- Active research state:
  - [data_utilization_roadmap.md](../00_roadmap_state/data_utilization_roadmap.md)
  - [factor_audit_trail.md](../00_roadmap_state/factor_audit_trail.md)
  - [next_stage_alpha_map.md](../00_roadmap_state/next_stage_alpha_map.md)
- Related architecture lessons:
  - [small_cap_post_pump_short_proposal.md](small_cap_post_pump_short_proposal.md)
- Data availability:
  - [market_data_inventory.md](../01_data_foundation/market_data_inventory.md)

---

## Change log

- `2026-05-02` - initial proposal created for MF-01 / SP-L, formalizing the
  1h orderbook and inventory-risk-transfer research path with candidate factor
  definitions, field mapping, Stage 0 event-study design, and preferred landing
  shapes.
- `2026-05-02` - Stage 0 completed and first formal `v6_h10d` A/B finished.
  `boundary_fragile_orderbook` and the combo rule validate mechanically but are
  non-additive versus the current SP-K short-boundary winner; the sparse
  `pump_bid_replenishment_failure` trigger is directionally real but too churny
  in broad replacement form.
- `2026-05-02` - requested narrow landing-shape pass completed on top of
  `replace_mid_v1_no_news`. `mf01_spk_confirm_v1` changes `89` short slots but
  does not improve cycle metrics, `mf01_spk_ss_veto_v1` is a realized no-op,
  and `mf01_post_cascade_guardrail_v1` is too sparse and not yet a valid
  do-not-short rule.
