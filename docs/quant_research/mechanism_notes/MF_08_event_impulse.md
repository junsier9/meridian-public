# MF-08: Information shock & impulse response

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: draft`
`Source family: docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md §B`
`Tier: T1 (vol / OI / funding shocks); T2 (curated event tape with
PIT-clean replay protection)`

---

## Economic story

Discrete events — FOMC announcements, CPI prints, exchange hacks, large
liquidation cascades, regulatory actions, listing announcements — produce
sharp impulses in price, vol, OI, and funding. The impulse-response window
is *not* random: post-cascade vol stays elevated for 3–7 days, post-funding-
sign-flip leverage cycle takes 5–10 days to rebuild, post-shock liquidity
is degraded for ~7 days. Continuous-factor models smooth this out — they
treat the elevated vol as "high vol regime" rather than "5 days into a
shock decay". The *time-since-shock* is itself a factor.

A second pattern: shock co-occurrence. When ≥ 3 names experience a 3σ
return move on the same day, the shock is *systemic* rather than
idiosyncratic, and the post-shock decay differs (cross-sectional dispersion
collapses for a week, then re-builds). Universe-wide shock counters work
better as regime-gating variables than as score components.

A third pattern: the LLM-tagged event tape itself, gated through a strict
PIT-clean replay protection layer, lets us separate "the price moved 5%
on event X" from "the price moved 5%". The first kind is conditionally
predictable; the second is closer to the unconditional vol distribution.

## Why this alpha persists

- **Modelling cost**: continuous factors are easier to fit; building a
  proper event-state-machine factor requires new tooling (state variable
  definitions, decay curves, anti-replay checks).
- **Data scarcity for clean event tape**: a curated, PIT-validated, anti-
  replay event tape is a several-month engineering project. Most teams use
  raw news feeds and have lookahead bias.
- **Threshold calibration**: 3σ vs 4σ vs liquidation $-amount thresholds
  produce materially different shock counts, and the right threshold is
  empirical, not theoretical.

## Required primitives

- `realized_volatility_20`, `return_1`, `funding_rate`, `open_interest` —
  in panel; sufficient for F46 / F47 / F48 / F49 / F50.
- `coinglass_liquidation_imbalance_24h`, `coinglass_liq_intraday_concentration_24h`
  — in panel; needed for liquidation-cascade subset of F50.
- `event__macro_release`, `event__hack`, `event__listing` — **[T2] not in
  panel**; gated on M3.3 (Day 61–90) curated event tape build-out.
- LLM-tag `narrative__*` series — **[T3] not in panel**; gated on M3.3+.

**Admission caveat**: `event__` and `narrative__` are currently in
`FEATURE_ADMISSION_EXPLICITLY_EXCLUDED_PREFIXES` (see
`feature_admission.py`). The doc memo §A.3 line 62 inaccurately states
they are "allowed". Before any event-tape factor can enter a manifest, the
admission policy needs an explicit allowlist update with PIT-clean replay
audit (a stronger gate than the W1.2 prefix extension).

## Candidate factors

| factor_id | column name | sign | EHL (days) | tier | implementation status |
|---|---|---|---|---|---|
| F46 | `vol_shock_impulse_phase` (TBD) | − (post-shock 3-7d compressed) | 5–10 | T1 | not implemented |
| F47 | `funding_flip_decay_phase` (TBD) | cond (post-flip 5d trend) | 4–7 | T1 | not implemented |
| F48 | `oi_shock_decay` (TBD) | cond | 4–7 | T1 | not implemented |
| F49 | `shock_co_occurrence_index` (TBD) | universe-wide regime gate | 3–7 | T1 | not implemented |
| F50 | `event_cluster_persistence` (TBD) | − (multiple shocks = unstable) | 7–14 | T1 | not implemented |

§E.6 (PIT macro/event tape with anti-replay) and §E.12 (liquidation cascade
impulse-response) are the corresponding frontier directions; §E.6 is the
hardest engineering item in the 90-day plan.

## Expected sign and half-life

F46 (vol-shock decay) is the cleanest negative-sign factor: post-shock,
returns are dampened. F49 / F50 act as universe-wide regime modifiers
rather than as score components.

## Regime where strongest

Post-shock windows (3-7 days after a 3σ vol move). Cascade aftermath is
the highest-conviction sub-window. Shock co-occurrence is most informative
in pre-systemic-stress windows where dispersion is rising.

## Failure modes

- Threshold calibration drift — the 3σ definition of "shock" is sensitive
  to the rolling vol window choice. A regime where realised vol structurally
  shifts (e.g. ETF approval, major exchange listing of futures) breaks the
  threshold.
- Sparse-event sample bias — same caveat as MF-06's F20.
- Event-tape data quality risks: backfilled timestamps, multi-event
  collisions, PIT-incompliance.

## Falsification path

- Per-factor: rolling 60d residual IC stays below 0.02 for 90 days → retire.
- Family-level placebo test (§E.6 frontier): construct a synthetic event
  tape with random dates of equal frequency. If the placebo IC is within 1σ
  of the real-event IC → the event-tape factors are not actually conditional
  on event presence; reject family.
- Liquidation cascade post-event 24h abnormal return t-stat < 2.5σ → reject
  §E.12.

## Implementation status

- in `features.py`: none.
- admitted via `feature_admission.py`: none. Note: `event__*` /
  `narrative__*` are *explicitly excluded* and need a deliberate policy
  update before MF-08 / MF-16 factors can enter manifests.
- present in any active manifest: none.
- report-carded: none.

Next action: W3.1 (Day 14–30) — implement F46 / F47 / F48 / F49 on the
existing daily panel (no new data; just `days_since_last_X_shock`-style
event-decay variables). Then negotiate the `event__` admission policy
update with the PIT-clean replay protection. F50 and the §E.6 / §E.12
extensions are M3.3+ work.

## Cross-references

- Alpha ontology memo §B (MF-08 row), §D (Family MF-08 table), §E.6 (PIT
  event tape), §E.12 (liquidation cascade).
- `feature_admission.py` — current `event__` / `narrative__` exclusion
  policy.

---

## Change log

- `2026-04-29` — initial note created from §B / §D / §E content (W1.5);
  flagged the doc-vs-code admission status discrepancy.
