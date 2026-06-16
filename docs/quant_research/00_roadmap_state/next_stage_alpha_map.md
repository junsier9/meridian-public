# Next-Stage Alpha Map

`Snapshot date: 2026-05-01`
`Owner: quant_research_maintainer`
`Status: advisory`
`Scope: where the next materially-new alpha is most likely to come from`

---

## 2026-05-03 Roadmap Correction

The canonical h10d parent is now `v5_rw_bridge_no_overlay_h10d`. Any new
candidate must be judged against this parent, not against legacy `v6_h10d` or
`regime_gating_v2` variants.

Recent Stage 0 / fixed-set work changes the roadmap in three ways:

- `SP-K` remains useful research evidence, but the current canonical-parent
  `spk_short_replace_mid_v1` challenger is not promotable. It fast-rejects
  positively, but strict falsification fails and its paired edge versus
  `v5_rw_bridge_no_overlay_h10d` is too thin.
- Experiment 4, `Funding + OI crowded squeeze failure`, is `P1-watch`, not a
  mainline replacement candidate. Broad crowding fails Stage 0, and extreme
  crowding works only weakly. As a hard confirmation gate on SP-K it narrows
  replacements but underperforms raw SP-K.
- Experiment 5, `Post-capitulation long replacement`, is rejected for canonical
  long-boundary replacement. It should be reframed as a possible rebound sleeve
  or `do-not-short` veto rather than a parent-long replacement.

Immediate mainline after this correction:

1. **M3.3 event tape / narrative state for canonical short-boundary hardening**.
   The lane has progressed past direct SP-K vetoes into a strict event-state
   replacement scaffold. Fast-reject evidence passes, but full strict validation
   is blocked until event-state columns are native in the validation feature
   frame.
2. **MF-01 narrow orderbook / inventory hardening on the canonical parent**.
   The prior MF-01 candidate is research-useful but not promotable; the next
   version must be narrower, cost-aware, and symbol-holdout-stable.
3. **Stablecoin / on-chain only as regime context or sleeve activation**.
   Current daily overlays are incremental-negative at strategy layer, so this
   is not the next direct score/replacement mainline.

Do not spend the next mainline slot on generic funding/OI variants, generic
long replacement after liquidation, or another smooth score overlay.

---

## 2026-05-04 Roadmap Correction

M3.3 is now locally exhausted for the current event-tape representation. The
strict state candidate passed validation/fixed-set scaffolding, but failed
statistical falsification; threshold v2 and MF-01 confirmation did not repair
symbol-holdout / liquidity-bucket fragility.

M3.2 has also been rechecked against the canonical parent:
[`m3_2_canonical_parent_stage0.md`](../03_alpha_branches/m3_2_canonical_parent_stage0.md). The old
MF13/MF14 landing shapes were mostly exact at-par on
`v5_rw_bridge_no_overlay_h10d`; the best slice, `mf14_sell_beta_v5_parent`,
improved ready-window long-short mean by only `+0.000445` and changed just
`0.18%` of short-boundary timestamps. This is below the Stage 0 threshold and
does not justify a manifest A/B.

The discrete M3.2 boundary activation re-open has now run:
[`m3_2_boundary_activation_stage0.md`](../03_alpha_branches/m3_2_boundary_activation_stage0.md).
Unlike the old smooth-score shapes, four sparse boundary rules are
Stage0-positive: `tron_impulse_short_high_beta_rs`,
`tron_heat_short_high_rs`, `rebound_long_idio`, and
`sell_pressure_short_high_beta_rs`. Active-window edge ranges from about
`+56` to `+95` bps on `12-23` active timestamps. This is not promotion
evidence yet; it is the next falsification queue.

Immediate mainline after this correction:

1. **Do not continue M3.3 threshold/MF-01-confirmation tuning** unless a new
   event-state source or broader persistence definition is introduced.
2. **M3.2 discrete boundary activation is now the active next lane**. The
   smooth MF13/MF14 score shapes stay rejected, but the four Stage0-positive
   sparse rules should move directly into delay / shuffle / holdout / cost
   falsification before any manifest A/B.
3. **Do not open M3.2 MF13/MF14 smooth-score manifest A/B** on the current
   evidence. Carry forward only the discrete boundary rules listed above.
4. **MF-05 cross-venue also fails in its current 1d boundary form**:
   [`mf05_cross_venue_boundary_stage0.md`](../03_alpha_branches/mf05_cross_venue_boundary_stage0.md).
   It has enough boundary transmission (`~18-25%` changed timestamps), but the
   direction is wrong. Selecting high dispersion / premium shorts replaces good
   shorts with worse shorts, while vetoing them is at-par to negative.
5. **Event-conditioned MF-05 + SP-K also fails**:
   [`mf05_cross_venue_spk_stage0.md`](../03_alpha_branches/mf05_cross_venue_spk_stage0.md).
   Cross-venue confirmation changes about `52%` of raw SP-K timestamps but
   worsens the SP-K short basket by roughly `12-13 bps`; cross-venue veto
   changes only `0.27-0.46%` of timestamps and is at-par. The current 1d
   close-price MF-05 route is closed.
6. **Event-conditioned MF-07 + SP-K also fails**:
   [`mf07_participant_disagreement_spk_stage0.md`](../03_alpha_branches/mf07_participant_disagreement_spk_stage0.md).
   Participant-disagreement confirmation changes about `45-52%` of raw SP-K
   timestamps but worsens the SP-K short basket by roughly `8-15 bps`; veto
   variants are at-par or too sparse. The current daily MF-07 route is closed.
7. **Sub-day MF-07 participant pivots also fail**:
   [`mf07_subday_participant_pivot_stage0.md`](../03_alpha_branches/mf07_subday_participant_pivot_stage0.md).
   Raw 1h participant-pivot confirmation changes about `46-51%` of raw SP-K
   timestamps and worsens the SP-K short basket by roughly `9-12 bps`; veto
   variants are at-par and change only `1.65-5.86%` of timestamps.
8. **Next executable alpha search should move to a different information
   source or landing shape**, not another inherited smooth overlay. Highest
   priority is now M3.2 boundary falsification, then an options-surface slice
   once enough snapshots exist, or sub-day venue stress only if raw venue-local
   state data is available.

### 2026-05-04 CoinGlass full-stack data upgrade

The CoinGlass API surface is broader than the currently implemented local
provider path. It can potentially fill spot 1h OHLCV, repair futures OI-value
coverage with provenance, add ETF flow/state, add selected on-chain exchange /
whale flow sidecars, and accelerate an options-regime slice. The implementation
roadmap is now tracked separately in
[`coinglass_full_stack_data_research_roadmap.md`](../01_data_foundation/coinglass_full_stack_data_research_roadmap.md).

Priority implication: before opening another smooth score overlay, first execute
the CoinGlass data foundation, re-baseline `v5_rw_bridge_no_overlay_h10d`, then
restart only data-sensitive lanes: true `cross_sectional_intraday_1h`, M3.2
sparse boundary activation, canonical-parent SP-K replacement, sub-day MF-05,
narrow MF-01, and a market-level M3.1 options-regime slice.

### 2026-05-05 Crime-pump manipulation-state note

The external "Crime Pump Playbook" thread has been converted into a local
research note:
[`crime_pump_playbook_alpha_research_note.md`](../03_alpha_branches/crime_pump_playbook_alpha_research_note.md).
The actionable repo lesson is that `post-pump short` should be represented as a
staged manipulation-state problem, not a single reversal factor. The first
research products should be `squeeze_trap` short veto / exposure reduction,
`post_squeeze_exit` delayed entry, fake-liquidity capacity haircut, and
CEX-inflow bait-vs-exit separation.

### 2026-05-07 Parallel 1h alpha-mining lane

The manipulation-state lesson is now opened as a separate 1h research mainline:
[`parallel_1h_alpha_mining_roadmap.md`](../04_parallel_1h/parallel_1h_alpha_mining_roadmap.md).
This lane is explicitly parallel to the h10d canonical parent. It starts with
local 1h mechanical-flow Stage 0 evidence (`low_float_squeeze_trap`,
`post_squeeze_exit_short`, capacity haircut) and must not mutate h10d promotion
state unless a later bridge is explicitly validated.

### 2026-05-08 Data sponsorship investment plan

The current bottleneck is now packaged for external data sponsors and strategic
investors in
[`data_sponsorship_investment_plan_2026_05.md`](../01_data_foundation/data_sponsorship_investment_plan_2026_05.md).
Use it as the outward-facing narrative for why the next phase needs deeper,
cleaner, replayable data before more alpha search. The plan preserves the same
repo rule used here: data fill, provider concordance, and research
revalidation stay separate, and no data sponsorship result becomes alpha
evidence without strict falsification.

### 2026-05-09 CoinGlass full-stack closure

The CoinGlass data-foundation and data-sensitive reopening cycle is now frozen
in
[`research_priority_update_full_stack.md`](../03_alpha_branches/research_priority_update_full_stack.md).

Main roadmap position: the project is past the CoinGlass `Day 3+ / research
expansion block`. The foundation catalog exists, R-1 through R-8 have current
pass/fail/blocked statuses, and no CoinGlass-backed reopening has produced a
strict survivor, manifest A/B candidate, or live candidate.

Priority implication:

- do not reopen M3.2, R-8, MF-07, or generic SP-K non-kline confirmation by
  tuning thresholds;
- use CoinGlass as a reusable catalog and sidecar source, not the active
  alpha-search frontier;
- next data-side work should target native venue concordance for OKX / Bybit /
  Coinbase if the goal is to unblock MF-05 or venue-concentration research;
- next alpha-side work should be a new pre-registered 1h mechanism, with
  `depth_velocity_collapse_exit_stage0_1h` as the preferred current-data shape
  only if it is explicitly distinct from the already failed bid-replenishment
  rule.

### 2026-05-12 Roadmap state consolidation and Binance PIT turn

The full `docs/quant_research` folder has been reconciled in
[`quant_research_roadmap_state_2026_05_12.md`](../quant_research_roadmap_state_2026_05_12.md).
Use that file as the first read when the roadmap feels split across too many
branches.

Current position: the CoinGlass/R-lane closure above still stands, and the
parallel 1h lane remains separate with no admitted h10d bridge. The active
validation frontier has moved to the Binance-only PIT h10d line. The latest
passed research challenger is
`v5_binance_pit_top_mid_h10d_pruned3_hv_tail_only_soft_budget`, with CoinGlass,
OI, liquidation, orderbook, top-trader, taker, funding, and basis columns still
excluded from core alpha.

Next clean step: build a promotion-readiness packet for the Binance-only PIT
candidate before reopening CoinGlass sidecars, native venue work, or a new 1h
mechanism.

### 2026-05-17 Provider-sidecar h10d control branch

A new pre-registered branch has been opened:
[`provider_sidecar_h10d_preregistration_2026_05_17.md`](../03_alpha_branches/provider_sidecar_h10d_preregistration_2026_05_17.md).

This branch keeps `hv_balanced` frozen as the live-pipeline control and does
not modify live configs. It reopens provider sidecars only under a stricter
shape than the earlier CoinGlass R-lane cycle:

1. Phase 0 proves current provider coverage, timestamp, and PIT availability.
2. Phase 1 tests provider-driven short-side risk overlays against the frozen
   `hv_balanced` control.
3. Phase 2 can only then attempt an old-style 12-factor h10d rescore.

The branch is not a live candidate. Its first allowed action is a coverage and
smoke report, not threshold search or alpha promotion.

---

## TL;DR

The next alpha lift is unlikely to come from more day-frequency
`funding/basis/vol` variants or another round of smooth score overlays.

The strongest new evidence in-repo now points to a different pattern:

- sparse-event alpha is real
- smooth score perturbation often stays `AT-PAR`
- **selection-layer rules** can be materially additive

`post_pump_stall` made this concrete. As a standalone small-cap score family it
was weak; as a smooth overlay on `v6_h10d` it was flat; as a **short-slot
replacement / veto rule** it became genuinely additive. That changes how the
next frontier should be ranked.

After the 2026-05-04 exhaustion passes, the highest-probability next alpha
lanes are now:

1. on-chain / stablecoin boundary activation
2. options surface / dealer-gamma topology
3. new event-state sources or broader event persistence
4. sub-day venue stress if raw venue-local state data exists
5. narrower orderbook / inventory confirmation with non-sparse transmission
6. MF-05 / MF-07 daily and participant-pivot routes only as closed comparators

The common thread is not "more factors". It is:

- **new state variables**
- **mechanical flow channels**
- **better strategy landing shape** (`veto`, `replacement`, `gate`) rather than
  defaulting every signal into a global base score

---

## A. Ranking Table

| rank | field | why it is promising now | best landing shape | data readiness | estimated effort | current owner-side view |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **MF-13 + MF-14 stablecoin / on-chain boundary** | best remaining broad liquidity state variables beyond price + perp microstructure | discrete boundary gate, sleeve activation, macro veto | medium | M-L | Stage0-positive; falsification next |
| 2 | **MF-02 options surface / dealer gamma** | deterministic flow and expiry mechanics, especially for market-wide rhythm | market-wide overlay, expiry gate, BTC/ETH-led modulation | medium-low now, improves with history | L | high moat, slower payoff |
| 3 | **new M3.3 event-state source** | existing event-state thresholds passed validation but failed falsification; a new state source may still separate real repricing | `short replacement / veto`, event-state activation | low today | M-L | revisit only with new information |
| 4 | **sub-day venue stress** | daily MF-05 failed, but raw venue-local dislocation may still carry timing information if available | venue-local event gate, confirmation/veto | unknown | M | only if raw venue state exists |
| 5 | **narrow MF-01 orderbook / inventory confirmation** | mechanism is live but prior confirmation was too sparse | do-not-short veto, post-squeeze selector | high | M | needs non-sparse transmission |
| 6 | **MF-05 / MF-07 closed comparators** | current daily and participant-pivot confirmation/veto forms are falsified or at-par | comparator only | high | S | do not spend next mainline here |

---

## B. Why These Six

### 1. M3.3 Event Tape + Narrative State Machines

**Why this field ranks first**

- The repo explicitly identifies "no state machines / no event tape" as a
  structural blind spot:
  [alpha_ontology_and_factor_library.md](alpha_ontology_and_factor_library.md:62)
- `SP-K` already showed the biggest false positive is **real repricing vs fake
  pump**:
  [small_cap_post_pump_short_proposal.md](../03_alpha_branches/small_cap_post_pump_short_proposal.md:505)
- This is the cleanest way to increase hit rate without turning the whole
  strategy into a different base score.

**What alpha would likely look like**

- `newsless_pump_short_veto`
- `event_confirmed_repricing_exclusion`
- `narrative_entry_decay_state_machine`
- `fresh_attention_burst_then_stall`

**Best landing shape**

- `short replacement / veto`
- `hype_chatter_decay_gate` on SP-K entered shorts
- event-conditioned activation, not continuous score perturbation

**Fast falsification path**

1. Build a PIT event tape with minimal categories: listing / hack / partnership
   / governance / macro / ETF / treasury.
2. Split current `SP-K` pump cohorts into:
   - event-confirmed
   - unconfirmed / narrative-only
3. Test whether the short alpha remains concentrated in the unconfirmed bucket.

**2026-05-03 Stage 0 result**

The first executable event-tape slice has been run:
[`m3_3_event_tape_spk_stage0.md`](../03_alpha_branches/m3_3_event_tape_spk_stage0.md). It found that
confirmed / real-repricing flags are not the SP-K entered-short false-positive
bucket on the canonical parent. Event-confirmed entered shorts were better
shorts, while `hype`-tagged entered shorts were weaker and had higher next-day
squeeze risk. The next implementation should therefore be a narrow hype decay
gate, not an official-event veto.

The hype-gate follow-up has also run:
[`m3_3_hype_chatter_gate_stage0.md`](../03_alpha_branches/m3_3_hype_chatter_gate_stage0.md). The
simple candidate veto is rejected; the combined candidate+selected veto is only
watch-worthy. M3.3 remains high value, but the next slice should search for a
parent-independent event-state feature instead of another direct SP-K news veto.

That parent-independent feature slice has now run:
[`m3_3_event_state_feature_stage0.md`](../03_alpha_branches/m3_3_event_state_feature_stage0.md).
`m3_3_event_state_short_quality_v1` has the right IC sign versus short payoff
and works directionally in the parent bottom-8 boundary, but the realized
selection lift is too thin for promotion. M3.3 should remain ranked high as a
feature-seed lane, while the next implementation should be a stricter state
feature with symbol-holdout and delay gates before any manifest candidate.

The stricter state-feature slice has now run:
[`m3_3_strict_event_state_stage0.md`](../03_alpha_branches/m3_3_strict_event_state_stage0.md).
`strict_q1_noise0` clears the prior failure condition: entered rows are negative
shorts, the entered-minus-exited spread is large, and +1d delay remains
directional. The quarantined manifest A/B scaffold has also run. Fast-reject
evidence passes (`rank IC ~= 0.117`, validation Sharpe `3.90`, test Sharpe
`2.50`, walk-forward median OOS Sharpe `3.98`), and the validation contract now
passes after native event-state feature generation. The fixed-set comparison
also computes and passes versus the canonical parent (`+0.290` cumulative return
diff, `+0.281` Sharpe diff, bootstrap P(candidate > parent cumulative return)
`0.902`). The alpha experiment card is still no-go because fast statistical
falsification fails time shuffle, label shuffle, symbol holdout, and
liquidity-bucket consistency. M3.3 remains valuable, but the next slice should
be a narrower robustness-oriented v2, not a production candidate.

The robustness-oriented v2 diagnostic has now run:
[`m3_3_robustness_v2_stage0.md`](../03_alpha_branches/m3_3_robustness_v2_stage0.md). Raising the
quality threshold to `2.0` is the best local variant, but it still leaves AVAX as
a negative symbol holdout and only one liquidity bucket with positive edge.
Threshold tuning is therefore exhausted for now; the next M3.3 attempt needs a
new state definition or a mechanical confirmation layer, not another strictness
scan.

The first mechanical-confirmation attempt has now run:
[`m3_3_mf01_confirmation_stage0.md`](../03_alpha_branches/m3_3_mf01_confirmation_stage0.md). MF-01
orderbook fragility improves the allowed entered-row quality (`-2.59%` h10d),
but the rule touches only `1.65%` of timestamps and has effectively zero
parent-level edge. That keeps M3.3 in quarantine: useful mechanism evidence,
insufficient portfolio transmission.

**Why it fits the new lesson**

- This is exactly the kind of information that should change **which short you
  select**, not necessarily the full long-short ranking.

---

### 2. MF-01 1h Orderbook / Inventory Risk Transfer

**Why this field ranks second**

- It is the best **data-ready** lane still underused:
  [data_utilization_roadmap.md](data_utilization_roadmap.md:202)
- The mechanism is mechanical, not belief-driven:
  [alpha_ontology_and_factor_library.md](alpha_ontology_and_factor_library.md:82)
- It naturally matches the now-validated `selection-layer` architecture.

**What alpha would likely look like**

- `post_pump_orderbook_thinness_veto`
- `depth_velocity_collapse_after_squeeze`
- `ask_pressure_without_follow_through`
- `taker-through-thin-book exhaustion`

**Best landing shape**

- `short replacement`
- `do-not-short veto`
- post-cascade or post-pump event selector

**Fast falsification path**

1. Restrict to current `v6_h10d` short-boundary names.
2. Test whether names with:
   - weak bid replenishment
   - rising ask imbalance
   - thin-book persistence after price impulse
   have more negative `5d / 10d` forward returns.
3. Evaluate only as short-slot replacement, not as a full score family.

**Why it fits the new lesson**

- It is likely a **few-slot alpha**, not a whole-book alpha.

---

### 3. MF-13 + MF-14 Stablecoin Plumbing / On-Chain Reflexivity

**Why this field ranks third**

- This is the first new macro-liquidity state layer already entering the repo:
  [market_data_inventory.md](../01_data_foundation/market_data_inventory.md:85)
- The core economic story is strong:
  stablecoins are crypto's broad `M0`, and exchange / whale plumbing can lead
  risk appetite.
- Unlike more `funding/basis` tweaks, this is genuinely orthogonal information.

**What alpha would likely look like**

- `stablecoin_issuance_velocity_regime`
- `stablecoin_exchange_inflow_impulse`
- `whale_to_exchange_stable_flow`
- `exchange_net_flow_residual`

**Best landing shape**

- market-wide `regime gate`
- small-cap sleeve activation / deactivation
- portfolio-level overlay before single-name ranking

**Fast falsification path**

1. Test universe-level forward returns against:
   - 7d issuance acceleration
   - exchange inflow / outflow imbalance
   - whale-to-exchange stable flow
2. Then test whether `SP-K`-style small-cap short alpha is stronger only when
   stablecoin liquidity impulse is weak or fading.

**Important nuance**

- This lane is more likely to create **market-state alpha** than a clean
  cross-sectional factor on day one.

---

### 4. MF-02 Options Surface / Dealer-Gamma Topology

**Why this field ranks fourth**

- It is still one of the highest-moat lanes in the ontology:
  [alpha_ontology_and_factor_library.md](alpha_ontology_and_factor_library.md:341)
- The pipeline now exists, but history is still shallow:
  [data_utilization_roadmap.md](data_utilization_roadmap.md:57)
- Dealer hedging flow is mechanical and often governs the market-wide rhythm
  that other cross-sectional signals live inside.

**What alpha would likely look like**

- `iv_term_slope_stress_gate`
- `25d_skew_residual_relief`
- `expiry_gamma_window`
- `vanna_charm_concentration_window`

**Best landing shape**

- market-wide overlay
- expiry window gate
- BTC/ETH-led modulation on alt sleeves

**Fast falsification path**

1. Use currently accumulating Deribit chain snapshots.
2. First test market-wide regimes around:
   - front-vs-mid IV slope
   - skew residual
   - expiry concentration windows
3. Only after that try to let those states modulate `v6_h10d` or the small-cap
   short sleeve.

**Important nuance**

- This is less likely to directly create a per-name rank winner and more likely
  to create a strong **timing layer**.

---

### 5. MF-05 Cross-Venue Confirmation / Inventory Stress

**Why this field ranks fifth**

- The shallow daily version already failed once, but that does **not** kill the
  deeper mechanism:
  [factor_audit_trail.md](factor_audit_trail.md:278)
- The economic logic is still strong:
  broad repricing and venue-local squeezes should not look the same across
  Binance / OKX / Coinbase / Bybit.
- This is especially relevant for the exact problem `SP-K` is trying to solve.

**What alpha would likely look like**

- `venue_local_pump_non_confirmation`
- `cross_venue_price_premium_stress`
- `cross_venue_volume_share_migration`
- `spot_confirmation_breadth`

**Best landing shape**

- event confirmation filter
- `do-not-short if repricing is broad`
- venue-local stress veto

**Fast falsification path**

1. Take small-cap pumps and classify them into:
   - broad cross-venue confirmation
   - weak / venue-local confirmation
2. Measure whether only the weak-confirmation bucket mean-reverts reliably.

**Important nuance**

- The likely mistake would be to rebuild another generic daily dispersion factor.
- The likely win is to make it **event-conditional**.

---

### 6. Sub-Day Participant-Pivot Transitions

**Why this field still stays on the map**

- The canonical plain-vanilla MF-07 candidate failed:
  [data_utilization_roadmap.md](data_utilization_roadmap.md:901)
- The SP-K-conditioned daily MF-07 re-open also failed:
  [`mf07_participant_disagreement_spk_stage0.md`](../03_alpha_branches/mf07_participant_disagreement_spk_stage0.md).
- The raw 1h participant-pivot re-open also failed:
  [`mf07_subday_participant_pivot_stage0.md`](../03_alpha_branches/mf07_subday_participant_pivot_stage0.md).
- MF-07 remains on the map only as a closed comparator unless a materially new
  participant-state definition appears.

**What alpha would likely look like**

- `pump_plus_top_global_divergence`
- `cascade_plus_top_trader_velocity`
- `failed_follow_through_plus_participant_split`
- `pro_not_confirming_retail_chase`

**Best landing shape**

- sub-day transition gate
- replacement-layer timing signal
- not a standalone score family

**Fast falsification path**

1. Build raw 1h participant-pivot states around pump / cascade timestamps.
2. Test whether top-trader movement leads global-account catch-up or refusal.
3. Require non-trivial turnover and symbol-holdout stability before any
   manifest candidate.

**Important nuance**

- This is the weakest of the six as a standalone lane.
- Daily conditioning has now failed; only transition timing remains plausible.

---

## C. Recommended Priority Order

### Immediate build order

1. **MF-13 / MF-14 on-chain boundary**
   Because it is the best remaining candidate for a genuinely new market-state
   layer, but it needs a discrete boundary / activation shape.
2. **MF-02 options surface**
   Because this is the cleanest remaining new flow channel once enough
   snapshots exist or paid history is procured.
3. **New M3.3 event-state source**
   Only if the event representation changes materially.

### Second wave

4. **Sub-day venue stress**
   Only if raw venue-local state exists; do not reuse the daily close-price
   MF-05 panel.
5. **MF-05 cross-venue confirmation**
   Only as sub-day venue stress, venue volume migration, or venue-local state.
6. **MF-07 participant disagreement**
   Closed for daily and current raw 1h threshold forms.

---

## D. Recommended Research Shapes

The six fields should not all be expressed the same way.

| field | best initial expression |
| --- | --- |
| event tape / narrative | short veto, true-news exclusion, event activation |
| orderbook / inventory | short-slot replacement, do-not-short veto |
| stablecoin / on-chain | market regime gate, sleeve activation |
| options surface | market-wide overlay, expiry gate |
| cross-venue stress | sub-day venue stress / event-state filter |
| participant disagreement | closed comparator unless state definition changes |

This is the core design lesson from `SP-K`:

- if the mechanism is sparse and local, start with `replacement / veto`
- if the mechanism is broad and slow, start with `overlay / gate`
- only promote to base score if it proves additive at full portfolio scale

---

## E. What Not To Prioritize

These are the lowest-ROI next steps:

- another smooth `+/- w * factor_z` overlay on the full score
- more day-frequency `funding / basis / OI` variants from the same data family
- more unconditional or threshold-style MF-07 attempts on the full panel
- another round of model upgrades on the same narrow factor space

The repo already has strong evidence that those paths are saturated or
non-additive:

- [data_utilization_roadmap.md](data_utilization_roadmap.md:595)
- [factor_audit_trail.md](factor_audit_trail.md:174)

---

## F. Operational Conclusion

If the goal is **the next truly new alpha**, the most likely answer is:

- not "more of the same factors"
- not "stronger model on the same factors"
- but **new state information + better portfolio landing**

The single best meta-bet is:

> the next winner will probably look like a **selection-layer or gating rule**
> driven by event-conditioned microstructure or new macro-liquidity state,
> rather than a new globally-smoothed base score.

That is the main lesson the repo has earned so far.
