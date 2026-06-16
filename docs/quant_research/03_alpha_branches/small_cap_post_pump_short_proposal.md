# Small-Cap Post-Pump Short Research Proposal

`Context-Version: 2026-05-01.2`
`Owner: quant_research_maintainer`
`Status: research-only factor family after h10d mainline correction (2026-05-03)`
`Sub-path ID: SP-K`
`Scope: event-conditional short alpha for small-cap / non-major perps`
`Authoring mode: research proposal`

---

## English TL;DR

This proposal formalizes a research path for **shorting small-cap altcoins after
anomalous price explosions** when the move looks more like **crowded reflexive
overshoot** than genuine information repricing. The hypothesis is not "price up
= short"; it is:

- detect a **pump event**
- test whether the pump is **fragile / crowded / flow-driven**
- short only when the post-event state implies **inventory exhaustion and mean
  reversion**

The proposal maps the idea to the existing ontology as a hybrid of:

- **MF-08** information shock & impulse response
- **MF-06** reflexive flow
- **MF-07** participant disagreement
- **MF-10** higher-moment fragility

The strongest analogue already validated in-repo is `F-cascade`, which captures
post-liquidation rebound after downside overshoot. SP-K is the **upside dual**:
post-pump reversal after upside overshoot, with a stricter need to separate
"fake squeeze" from "true repricing".

---

## Research update (2026-05-01)

The proposal has now advanced beyond pure idea stage. The current repo state is:

- **Stage 0 event study: PASS on the narrow mechanism.**
  In `mid_tail_ex_majors`, the strongest event family is not "pump day short"
  but **post-pump stall**. The event cohort mean forward returns are
  approximately `-1.48% / -2.99% / -4.09%` for `h3d / h5d / h10d`, with
  negative-return fractions around `64% / 65% / 70%`.
- **Admission extension: PASS at factor level.**
  `post_pump_stall_core_score_3d` is the current lead candidate. On
  `mid_tail_ex_majors`, `h5d`, it clears the intended `G1/G3/G6` bar:
  raw IC `+0.0411`, regime same-sign `1.00`, residual IC vs `lsk3` `-0.0444`.
  The `post_pump_stall_oi_score_3d` sibling also works, but does not look
  meaningfully stronger than core.
- **Cycle / walk-forward: FAIL as a standalone mid/tail base strategy.**
  After plumbing SP-K into the deterministic score stack and running the one-off
  cycle family, all three variants fast-reject on walk-forward. The issue is
  not that SP-K is directionless; the issue is that the **mid/tail lsk3 base
  score itself is a weak standalone strategy** under the current architecture.
- **Main-strategy short-overlay backtest: PASS on architecture, AT-PAR on
  portfolio metrics.**
  SP-K was then attached to the active `v6_h10d` parent strategy on
  `liquid_perp_core_20`, changing **only the short leg** and only for
  `mid_liquidity` names. Low-weight variants `w=0.05` and `w=0.10` both pass
  validation and preserve the parent headline cycle metrics exactly:
  walk-forward median OOS Sharpe `2.832`, loss-window fraction `0.3125`,
  positive-regime fraction `2/3`. The aggressive `w=0.15` version degrades the
  walk-forward median to `2.428` and is too strong.
- **Risk-managed v2 is directionally better, but still not promotable.**
  Relative to the mid/tail baseline, the clipped short-side-only variant
  (`xs_alpha_ontology_spk_post_pump_stall_v2_h5d`) improves fast-reject-lite
  walk-forward median OOS Sharpe from `-0.608` to `-0.141`, lowers
  loss-window fraction from `0.5625` to `0.5000`, and improves the worst-regime
  median OOS Sharpe from `-6.447` to `-5.899`. That is a real improvement, but
  it still remains below the promote line.
- **Trading-risk readout is manageable but not free.**
  The short basket receives funding about `70%` of the time across baseline and
  SP-K variants, which is favorable. The v2 bottom-4 construction trims the
  next-1d `>10%` squeeze fraction from `4.94%` to `4.66%`, but it also weakens
  the average next-5d short return from about `-0.96%` to `-0.83%`.
- **Overlay basket economics improve slightly, but not enough to promote.**
  Inside the active `v6_h10d` parent, the best overlay weight is currently
  `w=0.10`: the short basket next-10d mean moves from about `-0.17%` to
  `-0.19%`, the next-1d `>5%` squeeze fraction edges down from `11.83%` to
  `11.80%`, and the short basket tilts slightly further toward mid-liquidity
  post-pump-stall names. That is a real directional improvement in short
  selection, but the gain is too small to lift full-portfolio walk-forward.
- **Main-strategy short replacement / veto backtest: current winner.**
  The next iteration stopped perturbing the full score and only altered the
  short cutoff. The lead rule (`replace_mid_v1`) preserves the long leg
  entirely, replaces at most one marginal short from the bottom-6 pool, and
  only when a `mid_liquidity` name has negative `post_pump_stall` z-score.
  This version **strict-passes validation** and materially improves the parent
  cycle metrics: walk-forward median OOS Sharpe rises from `2.832` to `4.076`,
  worst-regime median OOS Sharpe improves from `-2.736` to `-1.783`, and
  loss-window fraction stays flat at `0.3125`. The short basket becomes much
  more mid-liquidity aware (`28.4%` -> `42.5%` mid-liquidity shorts) while
  improving next-10d short payoff (`-0.17%` -> `-0.28%`) and reducing next-1d
  `>5%` squeeze frequency (`11.83%` -> `11.44%`).
- **Selected-short news veto / replacement A/B: formally plumbed, but not
  promoted.**
  After wiring the news-veto columns into the core feature-set build path, we
  reran the formal A/B on top of `replace_mid_v1`. Both `ss_veto_mini` and
  `ss_veto_adjudicated` now **validation-pass** and raise walk-forward median
  OOS Sharpe from `4.076` to `4.611`, so the news layer is no longer inert at
  the portfolio level. But the improvement comes with meaningfully worse tail
  shape and weaker validation economics: loss-window fraction worsens from
  `0.3125` to `0.34375`, worst-regime median OOS Sharpe worsens from `-1.783`
  to `-2.392`, validation Sharpe drops from `2.400` to `2.121`, validation net
  return drops from `0.228` to `0.181`, and the short-basket next-10d mean
  weakens from `-0.28%` to roughly `-0.21%` / `-0.20%`.
- **Why the news layer is live but still not good enough.**
  The selected-short veto now reaches actual held shorts: `adjudicated` labels
  hit about `20.0%` of selected-short rows across `45.4%` of timestamps, while
  `mini` hits about `21.1%` / `47.3%`. Relative to `replace_mid_v1_no_news`,
  the two news-veto variants force `227` / `241` additional short-slot
  replacements. The problem is that those incremental replacements are worse
  shorts than the names they eject: adjudicated-entered names average about
  `+0.80%` over the next 10 days vs `-0.15%` for the exited names; mini-entered
  names average about `+0.78%` vs `-0.28%` for the exited names.
- **Exposure-shape rerun: `do-not-fill` fails, `reduced-exposure` is the cleanest
  news-aware shape so far.**
  We then kept the same `replace_mid_v1_no_news` short selection but stopped
  forcing replacement. `ss_do_not_fill_adjudicated` zeros the flagged selected
  short and leaves the slot empty; it is clearly worse, with
  `walk_forward_median_oos_sharpe = 2.755`, `loss_window_fraction = 0.375`, and
  only about `80%` of the original short notional retained on average.
  `ss_reduced_exposure_adjudicated` keeps the same names but halves weight on
  flagged selected shorts; it fast-reject-passes with
  `walk_forward_median_oos_sharpe = 4.711`,
  `worst_regime_median_oos_sharpe = -1.769`, and about `90%` of short notional
  retained. This is the best news-aware landing shape so far because it avoids
  the bad forced-replacement economics and preserves tails much better than
  `ss_veto_adjudicated`.
- **Why `reduced-exposure` is still not promoted over `replace_mid_v1_no_news`.**
  The reduced-exposure shape still mutes roughly `20.0%` of selected-short rows
  across `45.4%` of timestamps, but it worsens `loss_window_fraction` from
  `0.3125` to `0.34375` and weakens weighted short-basket `next_10d_mean` from
  about `-0.28%` to `-0.23%`. So the current owner-side read is:
  `reduced-exposure` is the **best news-aware landing shape**, but
  `replace_mid_v1_no_news` remains the preferred deployment until the news
  layer can improve basket quality without giving up the parent strategy's
  stability.
- **Why `mini` and `adjudicated` still tie at strategy level.**
  The stronger adjudication changes the corpus and does alter live selected
  shorts, but under the current bottom-3 construction those changes do not
  improve the replacement choices enough to separate the two variants on cycle
  or validation metrics. Current owner-side read: the limiting factor is the
  landing shape, not the lack of stronger news labels.
- **Replacement rule calibration matters.**
  A stricter sparse rule (`replace_mid_v2`, only 12 replacements total) is too
  timid and degrades walk-forward to `2.428`. A more aggressive two-slot rule
  (`replace_mid_v3`) improves basket economics but increases loss-window
  fraction to `0.3438` and did not complete full validation in the initial
  run. Current owner-side read: `replace_mid_v1` is the right shape; `v2` is
  under-active; `v3` is too aggressive.
- **Post-audit mainline correction (2026-05-03).**
  The no-news winner remains useful SP-K evidence, but it is no longer the
  canonical h10d parent because it was built on legacy `v6_h10d` and
  `regime_gating_v2`. The canonical parent is now
  `v5_rw_bridge_no_overlay_h10d`; future SP-K tests must attach there and pass
  fixed-set paired comparison plus overlay ablation before promotion.

**Current decision**:

- Promote SP-K as a **formal plumbed factor family** in code and audit docs.
- Do **not** promote SP-K as a standalone `mid/tail` long-short strategy.
- Treat the best next architecture as a **short-side overlay / gate**:
  identify post-pump-stall names inside an already healthy parent strategy or
  inside the small-cap short basket, instead of forcing SP-K to become the
  whole portfolio construction logic.
- Current overlay verdict vs the active parent is **AT-PAR, not promote**:
  keep the implementation plumbed and available, but do not yet replace the
  production candidate with an SP-K-weighted short leg.
- Current replacement / veto verdict vs the legacy parent is
  **RESEARCH-ONLY / COMPARATOR**:
  the edge clearly lives in **short-slot selection**, not in perturbing the
  full cross-sectional ranking, but the old landing shape is not the mainline
  parent after the audit repair. Re-test SP-K only on
  `v5_rw_bridge_no_overlay_h10d`.
- Current **news-veto** verdict on top of that replacement rule is
  **mechanically live but not promoted**:
  keep the LLM news corpus and the event-tape plumbing, but do not replace
  `replace_mid_v1_no_news` with the current selected-short news-veto shape.
  `do-not-fill` is too blunt, forced replacement damages tails, and
  `reduced-exposure` is promising but still gives up some basket quality and
  loss-window stability.

Primary implementation / evidence artifacts:

- `scripts/quant_research/compute_small_cap_post_pump_event_study.py`
- `scripts/quant_research/compute_small_cap_post_pump_factor_report.py`
- `scripts/quant_research/evaluate_post_pump_stall_cycle_increment.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_short_overlay.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_short_replacement.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_news_veto_ab.py`
- `scripts/quant_research/evaluate_v6_h10d_post_pump_selected_short_news_veto_ab.py`
- `artifacts/quant_research/factor_reports/2026-05-01/post_pump_stall_cycle_increment_diagnostic.json`
- `artifacts/quant_research/factor_reports/2026-05-01/v6_h10d_post_pump_short_overlay_diagnostic.json`
- `artifacts/quant_research/factor_reports/2026-05-01/v6_h10d_post_pump_short_replacement_diagnostic.json`
- `artifacts/quant_research/factor_reports/2026-05-01/v6_h10d_post_pump_news_veto_ab_diagnostic.json`
- `artifacts/quant_research/factor_reports/2026-05-01/v6_h10d_post_pump_selected_short_news_veto_ab_diagnostic.json`

---

## A. Research question

Can we build a robust cross-sectional factor that identifies **small-cap altcoin
price explosions that are likely to mean-revert over the next 3-10 days**, and
use that factor to push those names into the short book for excess return?

The target is **not** a naive reversal factor. The target is a conditional
event-state factor that answers:

1. did an abnormal upside event occur?
2. does the event look like a **fragile pump** rather than a durable repricing?
3. if yes, is the post-event decay large and stable enough to survive
   cross-sectional admission and cycle integration?

---

## B. Economic hypothesis

In smaller altcoins, short-horizon price explosions are often driven by a mix
of shallow order books, concentrated capital, forced chasing, funding/OI
crowding, social/news amplification, and dealer/inventory imbalance. These
moves can overshoot the new equilibrium because the marginal buyer at the top is
weaker than the marginal buyer earlier in the move.

Once the initial impulse fades, the market is left with an unstable inventory
stack:

- late momentum chasers own poor entry prices
- perp longs face higher funding and margin pressure
- liquidity providers widen and fade rather than support continuation
- organic follow-through demand is often insufficient

That combination creates a negative expected return window over the next
several days. The mechanism is strongest when the move is:

- **idiosyncratic** rather than market-wide
- **flow-crowded** rather than fundamentally repriced
- **volume-confirmed but follow-through-poor**
- concentrated in **non-major** names with thinner liquidity

The central asymmetry vs post-crash reversal research is important:
**downside overshoots usually mean-revert more cleanly than upside overshoots**.
Therefore SP-K must be stricter than F-cascade about conditioning. A price
explosion alone is not enough; we need evidence of **exhaustion**.

---

## C. Why this alpha might persist

- **Liquidity asymmetry**: small-cap perps have thinner books and less passive
  capital, so transient imbalance can move price much further than in majors.
- **Crowding + leverage**: post-pump long inventory is often weak-handed and
  funding-sensitive.
- **Attention bottleneck**: many pumps are narrative bursts with short
  half-lives; the market overpays for fresh attention and underestimates decay.
- **Operational friction on the short side**: borrow, funding cost, squeeze
  risk, and venue fragmentation prevent full arbitrage.
- **Conditioning difficulty**: most simple reversal models cannot reliably
  distinguish "temporary pump" from "real repricing", so the family is easy to
  test badly and easy to reject prematurely.

---

## D. Ontology mapping

SP-K is best treated as a **hybrid family** rather than forced into one lane.

| family | role in SP-K | why it matters |
| --- | --- | --- |
| **MF-08 event_impulse** | primary anchor | the pump itself is a discrete event with a decay curve |
| **MF-06 reflexive_flow** | crowding / exhaustion confirmation | price-flow amplification identifies fragile continuation |
| **MF-07 participant_disagreement** | optional confirmation | top-trader / aggregate positioning can separate smart-money fade vs crowd chase |
| **MF-10 higher_moment_fragility** | volatility / range stress confirmation | abnormal range and vol-of-vol help detect blow-off moves |
| **MF-12 state-space_regime** | optional gating | avoid running the factor in broad market-wide melt-up regimes |

Interpretation: SP-K is the **upside dual** of the validated post-cascade
downside-rebound logic, but with materially higher false-positive risk.

---

## E. Proposed factor family

The research path should test a **family** of related candidates instead of one
formula. Each candidate answers a slightly different question about post-pump
fragility.

| factor_id | candidate column name | sign | EHL (days) | tier | core idea |
| --- | --- | --- | --- | --- | --- |
| K1 | `pump_exhaustion_recency_score_5d` | `-` | 3-7 | T1 | recent abnormal pump events decay into short alpha |
| K2 | `pump_funding_oi_crowding_score_3d` | `-` | 2-5 | T1 | pump + OI expansion + positive funding = weak long inventory |
| K3 | `pump_microstructure_fragility_score_3d` | `-` | 2-5 | T1 | pump + taker imbalance + thin book / one-sided flow = fragile continuation |
| K4 | `pump_disagreement_reversal_score_5d` | `-` | 3-7 | T1 | pump + top-trader/aggregate positioning divergence = informed fade setup |
| K5 | `newsless_pump_divergence_score_5d` | `-` | 3-10 | T2 | pump without PIT-confirmed event tape follow-through = likely overreaction |
| K6 | `post_pump_stall_score_3d` | `-` | 2-4 | T1 | explosive day followed by weak continuation / failed hold = fade trigger |

### E.1 Candidate K1: `pump_exhaustion_recency_score_5d`

**Purpose**: establish the simplest event-state baseline.

Sketch:

1. detect per-asset pump events on 4h or 1d bars:
   - return z-score high
   - abnormal range high
   - quote-volume shock high
2. accumulate recent events with exponential decay over 5 days
3. assign negative sign so high recent pump intensity pushes the asset down the
   ranking

This is the direct upside analogue of `liq_cascade_recency_score_5d`, but will
likely need stronger filters because upside events are noisier.

### E.2 Candidate K2: `pump_funding_oi_crowding_score_3d`

**Purpose**: distinguish squeeze/crowding from genuine repricing.

Sketch:

`pump_event * z(open_interest_change) * max(funding_z, 0)`

Possible extensions:

- reward pumps with expanding OI and increasingly positive funding
- penalize pumps with flat OI or negative funding, which may reflect spot-led
  information repricing instead of leveraged crowding

Economic interpretation: if the pump is being financed by fresh marginal perp
longs, the post-event inventory is more fragile.

### E.3 Candidate K3: `pump_microstructure_fragility_score_3d`

**Purpose**: detect one-sided flow and post-pump book instability.

Sketch:

`pump_event * taker_buy_sell_imbalance * book_thinness_or_ask_pressure`

Possible raw ingredients:

- taker buy vs taker sell USD
- orderbook bids/asks USD or quantities
- intraday range expansion

Economic interpretation: a pump sustained by aggressive taker buying into thin
liquidity is more likely to decay once the taker impulse stops.

### E.4 Candidate K4: `pump_disagreement_reversal_score_5d`

**Purpose**: exploit participant split after the pump.

Sketch:

`pump_event * f(top_trader_long_pct, global_account_long_pct, their divergence or velocity)`

Directions to test:

- top-trader chasing less than aggregate users after the pump
- top-trader positioning decelerates while aggregate long crowding remains high

Economic interpretation: if weaker cohorts chase while stronger cohorts do not
confirm, continuation quality is poor.

### E.5 Candidate K5: `newsless_pump_divergence_score_5d`

**Purpose**: separate reflexive narrative bursts from durable repricing.

Sketch:

`pump_event * (1 - event_confirmation_score)`

`event_confirmation_score` is T2 because PIT-clean event tape is not yet in the
repo. Until then, a weak proxy can be:

- broad market non-confirmation
- no BTC/ETH or sector sympathy
- no persistent basis/funding repricing after the event

This candidate is high upside but should wait until event tape quality is good
enough.

### E.6 Candidate K6: `post_pump_stall_score_3d`

**Purpose**: detect failed continuation rather than the initial event.

Sketch:

- day 0: explosive move
- day 1 / next 1-2 bars: close fails to make meaningful new highs
- funding/OI/crowding remains elevated

Economic interpretation: the market already spent its marginal buyers, but
inventory remains expensive and fragile.

---

## F. Required primitives and current data availability

### F.1 T1 primitives already available or derivable

From the current repo and data inventory:

- `spot_open/high/low/close`, `quote_volume`
  - source: Binance / CoinAPI OHLCV
- `funding_rate`, `open_interest`, `open_interest_value`, `perp_quote_volume_usd`
  - source: derivatives sync / Coinglass-extended
- `top_trader_long_pct`, `global_account_long_pct`
  - source: Coinglass-extended
- `taker_buy_volume_usd`, `taker_sell_volume_usd`
  - source: Coinglass-extended
- `orderbook_bids_usd`, `orderbook_asks_usd`, plus quantity variants
  - source: Coinglass-extended
- existing derived helpers:
  - realized volatility family
  - abnormal range / higher-moment family
  - liquidity stress / taker imbalance dispersion

These are sufficient for K1/K2/K3/K4/K6.

### F.2 T2 primitives not yet fully ready

- PIT-clean **event tape**
  - needed for K5 and for a clean "real news vs reflexive pump" split
  - roadmap dependency: M3.3 event tape
- richer cross-venue confirmation
  - useful for separating broad repricing from venue-local squeeze behaviour

### F.3 Universe filter recommendation

This family should **not** be evaluated on the full universe without a size /
liquidity segmentation. Recommended first pass:

- exclude BTC and ETH
- optionally exclude the top 3-5 deepest names by 30d ADV
- prioritize mid / lower-liquidity perp names with stable shortability

This aligns with the existing open challenge in the research docs: the main
universe may hide alpha that is stronger in mid-cap subsets.

---

## G. Formal hypothesis and falsification

### G.1 Main hypothesis

Among non-major perp-traded altcoins, a discrete upside pump event followed by
evidence of crowding and microstructure fragility predicts **negative forward
returns over the next 3-10 days**, strong enough to survive cross-sectional
orthogonalization against the current baseline.

### G.2 Null

Post-pump reversals are either:

- not systematic after conditioning costs and crowding,
- too noisy to survive cross-sectional admission,
- or already absorbed by existing reversal / vol / flow factors.

### G.3 Falsification path

Reject the family if any of the following hold after first-pass testing:

1. **Event-study falsification**
   - conditioned pump events do not show negative mean forward abnormal return
     at `h3d`, `h5d`, or `h10d`
2. **Cross-sectional falsification**
   - the continuous-score version of the best candidate fails `G1` and also
     fails event-subset spread tests
3. **Orthogonality falsification**
   - residual IC vs `lsk3` and vs `lsk3 + F-cascade` stays below `0.02`
4. **Cycle-layer falsification**
   - after safe-weight scan, the factor produces no marginal cycle value over
     `v6_h10d`, or only improves by breaking regime protection
5. **Economic falsification**
   - post-event decay is strongest in names with neutral/benign funding and
     flat OI, implying the "crowded weak-long inventory" story is wrong

---

## H. Proposed empirical workflow

### H.1 Stage 0: event-study before factorization

Do **not** start with IC. First verify the mechanism directly.

For each candidate event definition:

1. identify pump events
2. bucket by:
   - event intensity
   - funding sign / magnitude
   - OI expansion
   - taker imbalance
   - liquidity bucket
3. measure mean and median forward returns at:
   - `h1d`
   - `h3d`
   - `h5d`
   - `h10d`

Minimum success signal:

- strongest-conditioned buckets show clearly negative forward return
- signal is stronger in non-majors than in majors
- event decay curve is monotone or at least stable across nearby horizons

### H.2 Stage 1: convert the best event rule into continuous factors

Sparse events alone do not fit the standard admission framework well. Convert
the event into a recency-decay or state variable score so it becomes a usable
cross-sectional column each day.

Recommended first order:

1. K1 baseline event-decay score
2. K2 crowding-conditioned score
3. K6 stalled-follow-through score
4. K3 microstructure fragility score
5. K4 disagreement-conditioned score

### H.3 Stage 2: admission testing

For each continuous factor:

- run standard report card
- inspect `G1`, `G3`, `G6`
- additionally inspect **event-subset spread tests** because this family is
  sparse by construction

Key comparison baselines:

- `lsk3`
- `lsk3 + F-cascade`
- `lsk3 + F-cascade + any overlapping flow/vol factor`

### H.4 Stage 3: cycle integration

If any candidate passes admission:

- start with conservative negative weight
- test at `h5d` and `h10d`
- run small weight scan, e.g. `-0.01 / -0.02 / -0.03 / -0.05`

Promotion standard should be strict because upside-event shorts can improve
average returns while badly damaging tail risk if the factor is too aggressive.

---

## I. Admission and design nuances specific to this family

### I.1 Why standard reversal tests are insufficient

Simple "past 1d return high -> future return low" is not enough. That would
almost certainly overlap with:

- `momentum_decay_5_20`
- `abnormal_range_z_60`
- `downside_upside_vol_ratio_30`
- general vol / stress factors

SP-K should only proceed if the **conditioned** version survives residual IC.

### I.2 Why event-subset evaluation is mandatory

This family is inherently sparse. A valid mechanism can look weak in full-panel
IC if the event only fires on a minority of names and days. Therefore the
research flow must preserve two evaluation layers:

- direct event-study evidence
- continuous-score cross-sectional evidence

### I.3 Why T2 event tape matters

The biggest false positive is **real information repricing**. A clean event
tape is the most powerful separator between:

- "price exploded because of reflexive squeeze / attention spike"
- "price exploded because the asset's information set genuinely changed"

Without event tape, early versions should focus on the most obviously
flow-crowded and weak-follow-through setups.

---

## J. Expected overlap risk with current active research

| current factor / family | expected overlap | comment |
| --- | --- | --- |
| `F-cascade` | medium | same event-decay logic, opposite direction; must prove non-overlap |
| `momentum_decay_5_20` | medium-high | naive pump reversal may collapse into momentum-decay |
| `liquidity_stress_qv_iv` | medium | both use abnormal flow + vol stress |
| `top_trader_velocity` / MF-07 | medium | disagreement-conditioned variants may partially reuse same information |
| MF-04 carry residuals | low | different mechanism family; useful orthogonality anchor |

The bar for promotion should therefore be **residual contribution**, not raw
mechanism plausibility.

---

## K. Risks and implementation cautions

- **True repricing risk**: some pumps are real and continue.
- **Short squeeze risk**: wrong-way tail is much uglier than long-side fade
  errors.
- **Funding drag**: the names that look best to short may be expensive to hold.
- **Capacity / execution**: small-cap alt short ideas can look strong in paper
  alpha and fail in live execution.
- **Coverage bias**: the most reflexive names may have the weakest data quality
  or partial venue coverage.

Therefore a strong paper signal is necessary but not sufficient. This family
should face a tighter implementation screen than standard long-side factors.

---

## L. Recommendation on architecture

If SP-K works, the most likely first deployment is **as a score component with
negative sign**, not as a standalone short-only strategy. That keeps it aligned
with the current cross-sectional ranking architecture:

- pumped, fragile names get pushed toward the bottom of the ranking
- the short book benefits first
- the long book simply avoids contaminated names

If the signal turns out to be too sparse for score integration but very strong
when it fires, a second path is:

- keep it outside the main score
- treat it as an event-conditional short overlay or book-level exclusion rule

That decision should come **after** event-study and cycle evidence, not before.

---

## M. Concrete next steps

### M.1 Immediate T1 path

1. build a **pump event study** on 4h and 1d data
2. test K1 / K2 / K6 first
3. compare `h3d`, `h5d`, `h10d`
4. segment by liquidity bucket and majors-vs-non-majors

### M.2 If Stage 0 passes

1. implement continuous columns for K1/K2/K6
2. run factor report cards
3. test residual IC vs `lsk3` and `v6_h10d`
4. run conservative weight scan

### M.3 If T1 path is promising but noisy

Wait for or prioritize:

- M3.3 event tape
- richer cross-venue confirmation
- explicit short-cost / funding-drag evaluation

---

## N. Pre-registered success criteria

SP-K should be considered a serious promotion candidate only if:

1. event-study shows economically meaningful negative post-pump decay in
   conditioned small-cap cohorts
2. at least one continuous-score candidate passes `G6 >= 0.02` against the
   current best baseline
3. cycle integration improves `v6_h10d` without breaking regime protection
4. the edge survives a basic implementation haircut for funding/slippage

If it fails on (2) or (3), record it as a **mechanism-real but non-additive**
result rather than forcing it into the score.

---

## Cross-references

- Mechanism families:
  - [MF_08_event_impulse.md](../mechanism_notes/MF_08_event_impulse.md)
  - [MF_03_funding_microstructure.md](../mechanism_notes/MF_03_funding_microstructure.md)
  - [MF_07_participant_disagreement.md](../mechanism_notes/MF_07_participant_disagreement.md)
  - [MF_10_higher_moment_fragility.md](../mechanism_notes/MF_10_higher_moment_fragility.md)
- Active research state:
  - [data_utilization_roadmap.md](../00_roadmap_state/data_utilization_roadmap.md)
  - [factor_audit_trail.md](../00_roadmap_state/factor_audit_trail.md)
  - [experiment_catalog.md](../00_roadmap_state/experiment_catalog.md)
- Research ontology:
  - [alpha_ontology_and_factor_library.md](../00_roadmap_state/alpha_ontology_and_factor_library.md)
- Data availability:
  - [market_data_inventory.md](../01_data_foundation/market_data_inventory.md)

---

## Change log

- `2026-05-01` - initial proposal created from user-originated research idea;
  formalized as SP-K under the existing quant_research documentation scheme.
- `2026-05-01` - selected-short news-veto A/B rerun through the core
  feature-set build path: `mini` and `adjudicated` both validation-pass and
  lift median walk-forward Sharpe to `4.611`, but worsen loss-window fraction,
  worst-regime Sharpe, validation return, and short-basket quality vs
  `replace_mid_v1_no_news`; not promoted.
- `2026-05-02` - adjudicated selected-short exposure-shape A/B added.
  `ss_do_not_fill_adjudicated` fails cleanly; `ss_reduced_exposure_adjudicated`
  is the strongest news-aware landing shape so far, but remains below
  `replace_mid_v1_no_news` on basket quality / loss-window trade-offs and is
  not promoted.
- `2026-05-02` - `replace_mid_v1_no_news` promoted to the checked-in canonical
  h10d baseline manifest at
  `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_spk_short_replace_mid_v1_h10d.json`.
