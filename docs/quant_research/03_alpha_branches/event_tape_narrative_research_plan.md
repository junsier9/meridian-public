# Event Tape + Narrative State Research Plan

`Snapshot date: 2026-05-01`
`Status: bootstrap started; strict event-state A/B scaffold validation and fixed-set passed on 2026-05-03; statistical falsification no-go`
`Owner-side question: can M3.3 start now, and is news data missing?`

## 2026-05-03 Stage 0 Update

The first M3.3 empirical slice is now complete:

[`m3_3_event_tape_spk_stage0.md`](m3_3_event_tape_spk_stage0.md)

Key update: the existing adjudicated CryptoPanic/LLM news corpus is sufficient
for a minimal symbol-day event tape, so the lane is no longer blocked at the
bootstrap level. Full MF-16 narrative-state research is still blocked on deeper
historical social/news coverage and a frozen tag contract.

Most important result: on the canonical `v5_rw_bridge_no_overlay_h10d` parent,
`confirmed` / `real_repricing` event flags are not a valid do-not-short veto for
SP-K entered shorts. Those flagged entered shorts were better shorts in Stage 0.
The first promising separator is instead `hype` / news-chatter: SP-K entered
shorts with recent hype tags had weaker h10d returns and higher next-day squeeze
risk. Next M3.3 slice should therefore test a narrow `hype_chatter_decay_gate`,
not a broad official-event exclusion.

Follow-up result:
[`m3_3_hype_chatter_gate_stage0.md`](m3_3_hype_chatter_gate_stage0.md) tested
that narrow gate. The simple candidate veto is rejected, and the combined
candidate+selected veto is only watch-worthy. M3.3 should stay active, but the
next useful slice should search for a parent-independent event-state feature
rather than another direct SP-K news veto.

Parent-independent feature result:
[`m3_3_event_state_feature_stage0.md`](m3_3_event_state_feature_stage0.md) found
that a composite event-state short-quality score has the correct rank-IC sign
against short payoff, including inside the parent bottom-8 boundary. The
selection-layer lift is still too small for a manifest candidate because changed
entered rows remain positive-return shorts. Keep M3.3 as an active feature-seed
lane, not a promoted gate.

Strict state result:
[`m3_3_strict_event_state_stage0.md`](m3_3_strict_event_state_stage0.md) tested
the pre-registered stricter condition. `strict_q1_noise0` now produces negative
entered shorts (`-2.18%` h10d), beats exited rows by about `-1.90%`, and remains
directional under +1d delay. This upgrades M3.3 from feature seed to formal
manifest A/B candidate scaffold.

Formal scaffold result:
[`m3_3_strict_event_state_ab.json`](../../../artifacts/quant_research/factor_reports/2026-05-03-m3-3-strict-event-state-ab/m3_3_strict_event_state_ab.json)
shows that the quarantined candidate passes validation after native event-state
feature generation (`rank IC ~= 0.117`, validation Sharpe `3.90`, test Sharpe
`2.50`, walk-forward median OOS Sharpe `3.98`). Fixed-set paired comparison now
computes and passes versus the canonical parent (`+0.290` cumulative return
diff, `+0.281` Sharpe diff, bootstrap probability `0.902`). The alpha
experiment card is still no-go because fast statistical falsification fails
time shuffle, label shuffle, symbol holdout, and liquidity-bucket consistency.
The next M3.3 task is a narrower robustness-oriented v2, not another broad
event-tape variant.

Robustness v2 follow-up:
[`m3_3_robustness_v2_stage0.md`](m3_3_robustness_v2_stage0.md) tested stricter
quality thresholds, one-replacement caps, top-liquidity-only selection, and a
diagnostic symbol exclusion. The best local rule is `v2_q2_noise0`, but it still
fails the important shape: AVAX remains a negative holdout and only one
liquidity bucket contributes positive edge. This closes the threshold-tuning
branch. The next M3.3 attempt needs a richer state definition or mechanical
confirmation.

MF-01 confirmation follow-up:
[`m3_3_mf01_confirmation_stage0.md`](m3_3_mf01_confirmation_stage0.md) tested
orderbook fragility as that mechanical confirmation layer. It makes the allowed
rows cleaner (`-2.59%` h10d) but too sparse (`1.65%` changed timestamps), so the
branch remains research evidence only.

## TL;DR

Yes, we can start **now**, but only in a phased way.

- We **can** start the `event tape` side immediately with a PIT-clean,
  anti-replay, manually curated or official-source event ledger.
- We **cannot** do the full `narrative state machine` yet because the repo
  currently has **no historical news/social tape** and no configured news
  provider.
- The right bootstrap path is:
  1. build the event-tape schema and replay contract,
  2. start with high-signal official events,
  3. use it first for `real-news exclusion` and `newsless_pump short veto`,
  4. only after that add news/social history and LLM tagging.

## A. Current readiness audit

### A.1 What exists today

- Price / derivatives / on-chain adjacent lanes are live:
  `binance_ohlcv`, `binance_derivatives`, `coinglass_extended`,
  `coinapi_ohlcv`.
- The new bootstrap module now exists at
  [event_tape.py](../../../src/enhengclaw/quant_research/event_tape.py:1).
- The module already covers:
  - event schema normalization,
  - PIT replay filtering via `observed_at_utc <= as_of_utc`,
  - subject / market scope separation,
  - recent confirmed-event queries for veto / exclusion logic.

### A.2 What is missing today

- There is **no** event-tape producer in the existing research stack.
- There is **no** historical news/social provider configured in
  [.env.example](../../../.env.example).
  The environment template includes `BINANCE`, `ALCHEMY`, `CoinAPI`, but no
  `NEWSAPI`, `GNEWS`, `CryptoPanic`, `Telegram`, `X`, or Reddit source.
- `event__` and `narrative__` are still explicitly excluded in
  [feature_admission.py](../../../src/enhengclaw/quant_research/feature_admission.py:75).
- The research docs already describe this as a gap:
  - [alpha_ontology_and_factor_library.md](../00_roadmap_state/alpha_ontology_and_factor_library.md:62)
  - [MF_08_event_impulse.md](../mechanism_notes/MF_08_event_impulse.md:39)
  - [MF_16_narrative_state.md](../mechanism_notes/MF_16_narrative_state.md:38)

### A.3 Bottom line on news data

Yes: **news data is currently missing** for the full MF-16 research path.

More precisely:

- missing historical news tape,
- missing historical social tape,
- missing PIT-safe tagging pipeline,
- missing admission policy for `narrative__*`.

That blocks full narrative-state research, but it does **not** block a useful
M3.3 event-tape bootstrap.

## B. Research split: what can start now vs what is blocked

### B.1 Start now: T0/T1 event tape

Start with only events that are observable from official or auditable sources:

- exchange listing / delisting
- protocol exploit / security incident
- regulatory action
- protocol upgrade / governance milestone
- token unlock
- fixed macro events such as CPI / FOMC

This is enough to test the first two practical use cases:

- `real_news_exclusion_veto`
- `newsless_pump_short_veto`

These are the highest-ROI first applications because they directly improve the
already successful `post_pump_stall` short-replacement architecture.

### B.2 Blocked for now: MF-16 full narrative state machine

The following should be considered **blocked** until a historical
news/social tape exists:

- `narrative_entry_event`
- `narrative_persistence`
- `narrative_spread`
- `narrative_decay`
- `narrative_concentration`
- leave-one-narrative-out validation

Without PIT-clean text history, any attempt here would be too vulnerable to
backfill and hidden lookahead.

## C. Event-tape bootstrap contract

### C.1 Minimal row schema

Each event row should include:

- `event_id`
- `observed_at_utc`
- `effective_at_utc`
- `scope`
  `subject` or `market`
- `category`
- `confirmation_level`
  `official`, `confirmed`, or `narrative_only`
- `source_kind`
- `source_ref`
- `title`
- `subjects`
- `narrative_tags`
- `metadata`

This is now formalized in
[event_tape.py](../../../src/enhengclaw/quant_research/event_tape.py:1).

### C.2 Anti-replay rule

The hard rule is:

`an event may only influence an as-of timestamp if observed_at_utc <= as_of_utc`

This is the single most important control. It prevents "future-confirmed"
events from leaking into historical decisions.

### C.3 Intended first landing shape

The first production-like landing should **not** be a global base score.

It should be:

- `short replacement / veto`
- `real-news exclusion`
- event-conditioned activation gate

That matches what SP-K already taught us: sparse event alpha is strongest when
it lands at the selection layer.

## D. Immediate build order

### D.1 Stage 0: manual PIT event tape

Build a small, high-quality tape for a limited window and limited categories.

Recommended first scope:

- as-of window: last 12-18 months
- categories:
  - exchange listing / delisting
  - exploit / hack
  - regulatory action
  - macro calendar
- universe:
  - parent strategy names
  - plus the mid/tail names that most often trigger `post_pump_stall`

Success criterion:

- event rows are replay-safe,
- timestamps are auditable,
- each row is traceable to an official or stable source.

### D.2 Stage 1: attach to SP-K / parent short-leg logic

First formal research question:

`When post_pump_stall fires, does excluding names with a recent confirmed event improve short-basket economics?`

Primary metrics:

- short basket `next_5d` and `next_10d` mean
- next-day squeeze rate
- parent strategy walk-forward median OOS Sharpe
- worst-regime median OOS Sharpe

### D.3 Stage 2: add text tape and narrative tags

Only after Stage 1 is stable should we expand into:

- historical news feed
- historical social feed
- frozen tag taxonomy
- PIT-safe LLM tagging
- `narrative__*` admission policy

## E. Recommended sources by confidence tier

### E.1 Highest-confidence sources

- official exchange announcements
- official project blogs / foundation posts
- regulator press releases
- fixed macro calendars

These are best for T0 because their timestamps are easier to audit.

### E.2 Medium-confidence sources

- large crypto newswires
- curated breach / exploit trackers
- structured token-unlock calendars

Useful after the basic tape is stable.

### E.3 Lowest-confidence sources

- X / Twitter
- Telegram
- Discord
- Reddit

These are the right inputs for MF-16 later, but they should not be the first
source because PIT and replay discipline are hardest here.

## F. Recommended next experiments

### F.1 Highest priority

`real_news_exclusion_veto`

Rule sketch:

- if `post_pump_stall` is negative and
- there is **no** recent confirmed subject or market event,
- keep the short replacement active;
- otherwise veto the replacement.

### F.2 Second priority

`event_impulse_state_window`

Rule sketch:

- after a confirmed event, define a finite impulse window,
- measure whether current alpha families behave differently inside vs outside
  the window.

### F.3 Deferred until news tape exists

`narrative_entry_decay_state_machine`

This is still the highest-upside frontier lane, but it is **not yet data-ready**.

## G. Practical conclusion

We should treat M3.3 as **started**, but with a hard split:

- `event tape`: start immediately
- `narrative state machine`: blocked pending news/social history

The repo is ready to proceed with a minimal, auditable event ledger and a first
`real-news exclusion` study. It is **not** yet ready for full
`narrative__*` factor production.
