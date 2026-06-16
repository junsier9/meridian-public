# MF-15: Settlement & arbitrage friction

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1 (intraday); T2 (ETF rebalance calendar)`

---

## Economic story

Several flows in crypto markets are **scheduled** rather than discretionary:

1. **8h funding settlement** at 00:00 / 08:00 / 16:00 UTC. Holders who do
   not want to pay (or want to collect) reposition in the hour before each
   settlement. The intraday hour-of-day return distribution near the
   settlement boundary is therefore systematically different from the
   distribution at random hours — a hour-of-day premium that does not
   exist in spot equity markets.
2. **Weekly Friday options expiry on Deribit** (08:00 UTC). The 3 days
   before and 1 day after Friday show consistent spot patterns driven by
   dealer hedge-unwind around the expiry strikes.
3. **Monthly last-Friday Deribit expiry** — same mechanism, larger size.
4. **BTC ETF rebalance windows**. The major US BTC ETFs publish daily
   creation / redemption flows with a 1-business-day lag; the *pattern* of
   flows around month-end and quarter-end is structural.

All four sub-mechanisms share a property: the flow is **rule-driven**. The
participant cannot opt out without breaching a contract or committee
mandate. The flow's existence is therefore not adversarially-arbitraged in
the way speculation flow is — the most we can do is *anticipate* and
position for the residual price impact.

## Why this alpha persists

- **Cannot be traded away**: the originating flow is the dealer / ETF
  market-maker / margin-system itself. Even if every speculator could
  predict the flow perfectly, the flow happens regardless.
- **Sub-day data resolution requirement**: most factor pipelines aggregate
  to daily bars and lose the hour-of-day premium entirely. Implementing
  any of the intraday factors (F66) requires running on 1h or 4h bars.
- **Calendar maintenance**: ETF rebalance windows (F68) require keeping a
  PIT-clean ETF flow calendar, which is an external dependency.

## Required primitives

- `timestamp_ms` — already in panel.
- 1h or 4h bars — **partial**: the 4h cross-sectional intraday bundle
  exists (`build_cross_sectional_intraday_feature_bundle`) but the daily
  cross-sectional bundle aggregates them away.
- ETF flow calendar — **[T2] not ingested**.

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F66 | `funding_settlement_proximity` (TBD) | cond × interaction with `|funding|` | <1 (intraday) | T1 (intraday) | not implemented; daily-bar pipeline cannot use it |
| F67 | `weekly_expiry_proximity` (TBD) | universe-wide gate | 1–3 | T1 | not implemented |
| F68 | `etf_rebalance_window` (TBD) | cond × interaction with OI | 1–5 | **T2** | not implemented |

§E.10 (settlement-cycle hour-of-day premium) is the corresponding frontier
direction.

## Expected sign and half-life

F66 / F68 are conditional and require interaction terms with funding /
OI to produce non-zero IC. F67 is a universe-wide gate (BTC/ETH expiry
windows affect the entire universe symmetrically and are best used to
modulate position size, not direct alpha).

Half-life is short across the family (hours to a few days) — these are
*event-window* factors.

## Regime where strongest

F66: every 8h, all the time, bounded by the settlement clock. Strongest at
high-funding regimes where the cashflow per settlement is large.
F67: weekly Friday window, all the time. Magnitude scales with weekly
options OI level.
F68: monthly month-end and quarter-end windows. Magnitude scales with ETF
AUM.

## Failure modes

- Daily-bar aggregation eliminates F66 entirely — the factor is only
  meaningful at sub-day cadence. The current daily pipeline cannot host
  it; it lives in the intraday pipeline.
- Calendar maintenance: ETF rebalance dates change with corporate
  actions; keeping the calendar PIT-clean is an ongoing chore.
- Holiday weeks (e.g. US Thanksgiving) where dealer activity is dispersed
  and the F67 expiry window pattern weakens.

## Falsification path

- F66 hour-of-day mean-return diff t-stat near settlement vs random hours
  < 2 → reject (§E.10 frontier line).
- F67 distribution of expiry-week vs non-expiry-week 5d returns: KS-test
  p > 0.05 → reject.
- F68 1-day-lag IC < 0.05 → reject (§E.18 frontier line covers ETF flow
  more broadly).

## Implementation status

- in `features.py`: none of F66 / F67 / F68 in either daily or intraday
  bundle. The intraday bundle has hooks (`build_cross_sectional_intraday_
  feature_bundle`) that could host F66; it is not exercised because the
  current strategy stack runs on daily bars.
- admitted via `feature_admission.py`: none.
- present in any active manifest: none.
- report-carded: none.

Next action: F67 is the **single highest-ROI** deliverable in the family
(works on daily data, requires only `timestamp_ms`; depends only on the
weekly Friday calendar). Implement and report-card it; if it survives
W1.3-style admission, fold into v_alpha_v2 manifest as a regime-gating
multiplier per §G.3 / W3.5. F66 and F68 wait on intraday-bar adoption
and ETF calendar respectively.

## Cross-references

- Alpha ontology memo §B (MF-15 row), §D (Family MF-15 table), §E.10
  (settlement-cycle hour-of-day premium), §E.18 (ETF-flow-aware basis).
- `build_cross_sectional_intraday_feature_bundle` — the intraday entry
  point that would host F66.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5).
