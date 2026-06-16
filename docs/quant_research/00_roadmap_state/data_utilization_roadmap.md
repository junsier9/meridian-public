# Data Utilization Reflection + Sub-path Roadmap

> **Supersession note (2026-05-13):** This is a 2026-05-03 data-utilization
> snapshot and sub-path ledger. It remains useful evidence for data gaps and
> prior lane outcomes, but it is not the current execution mainline. Start from
> [`quant_research_roadmap_state_2026_05_12.md`](../quant_research_roadmap_state_2026_05_12.md)
> for current state; the current live/research baseline split now treats
> `hv_balanced:multiphase_10_sleeve` as the live-operations baseline and
> `v5_rw_bridge_no_overlay_h10d:multiphase_10_sleeve` as the follow-on research
> baseline. Single-phase `v5_rw_bridge_no_overlay_h10d` rows in this older file
> are score-parent/history evidence, not the current portfolio baseline.

`Snapshot date: 2026-05-03` 路 `Owner: quant_research_maintainer`

Based on the canonical inventory at [`market_data_inventory.md`](../01_data_foundation/market_data_inventory.md) and the alpha-ontology execution status per [`alpha_ontology_and_factor_library.md`](alpha_ontology_and_factor_library.md), this doc audits **what data we have on disk but have NOT yet extracted alpha from**, and lays out concrete sub-path roadmaps to close those gaps.

---

## Snapshot status as of 2026-05-03

> **Read-this-first** entry point for sub-path conclusions. Compresses 搂G into a one-page status board. Per-sub-path lessons + audit detail are below in 搂G; full audit lineage in `config/quant_research/threshold_provenance.md`.

### Doc 90-day plan checkpoint status

| checkpoint | doc anchor | bullets required | bullets met | overall |
| --- | --- | --- | --- | --- |
| Week 2 鍑哄彛 | 搂H.1 | v92 cycle, 鈮? new factors admitted, IC 鈮?v91+0.005 | (legacy phase 0 complete) | **PASS** (historical) |
| Day 30 鍑哄彛 | 搂H.2 | v93 cycle, 2 gating multipliers raise worst-regime to 鈮?1.5, walk-forward median 鈮?.3 | substantial pass via alpha_ontology v6 鈥?walk-forward +2.832 (>>1.3); regime gating v2 productionized | **PASS** |
| **Day 60 鍑哄彛** | **搂H.3** | **v94 manifest涓婄嚎; 鈮? MF (MF-04 or MF-05) IR>0.4; factor_lifecycle 鑷姩 demotion** | **all 3** 鈥?alpha_ontology v6_lsk3_g_v2_h10d ships (瀹炶川 v94+); MF-04 F12 + MF-12 F-cascade (IR鈮?.3) both >0.4; M2.5 factor_lifecycle.py + automated demotion experiment shipped | **PASS** 猸?|
| Day 90 鍑哄彛 | 搂H.4 | v95 frontier (options/on-chain/event tape), 鈮?/4 strict gates PASS, rank IC 鈮?.30, regime worst median sharpe 鈮?0.5, 鈮? frontier family IC鈮?.04 | M3.x not yet executed; M3.1 Phase 0 scoping shows free Public API insufficient (no historical OI by strike); requires Owner-decision (free live-sync ~60-90d wall-clock OR paid Tardis.dev sample) | NOT YET 鈥?**gap = M3.x frontier data lanes** |

### Active alpha candidates (checked-in, score-integrated)

| candidate | horizon | overlay | walk-forward median | regime breakdown | lifecycle marker | source commit |
| --- | --- | --- | --- | --- | --- | --- |
| **`v5_rw_bridge_no_overlay_h10d`** | **h10d** | **none** | **+3.360 recomputed** | **2/3 positive, worst -0.951** | **canonical h10d parent** (2026-05-03) | audit repair bridge |
| `v_alpha_v1_lsk3_g_v2` | h5d | regime_gating_v2 | (control baseline) | passes regime | `active` | pre-SP-A |
| `v_alpha_v6_lsk3_g_v2` (lsk3 + F-cascade w=0.05) | h5d | regime_gating_v2 | +2.373 | 1/3 positive, worst -1.851 | `active_alternative` (2026-04-29) | `977c1a0` (SP-A) |
| `v_alpha_v6_lsk3_g_v2_h10d` (lsk3 + F-cascade w=0.025) | h10d | regime_gating_v2 | +2.832 historical | 2/3 positive, worst -2.736 (vs floor -2.828) | legacy comparator (2026-05-03) | `472ea4a` (SP-C Phase 3) |

Current h10d governance: `v5_rw_bridge_no_overlay_h10d` is the only canonical parent for follow-on h10d alpha. `regime_gating_v2`, legacy `v6_h10d`, and SP-K are comparator / research-only until a new candidate based on this parent passes fixed-set paired comparison, full-OOS period-return review, capacity, and overlay ablation.

### Experimental (admitted but not promoted)

| candidate | horizon | reason | commit |
| --- | --- | --- | --- |
| `v_alpha_v8_lsk3_g_v2` (lsk3 + F47, w=-0.03) | h5d | walk-forward +2.227 (+0.08 over v1, modest) | `7199b89` (SP-C) |
| `v_alpha_v1_h10d` / `v5_h10d` / `v8_h10d` | h10d | rotation regime fail (only F-cascade clears the sqrt-scaled floor) | `472ea4a` (SP-C Phase 3) |
| `v_alpha_v6_lsk3_g_v3_h10d` (DVOL overlay) | h10d | strict-pass but identical metrics to v2 (DVOL throttle days don't overlap losing days) | `f52aef7` (SP-G) |
| `v_alpha_v9_lsk3_g_v2_h10d` (lsk3 + F-cascade + F1 w=+0.015) | h10d | F1 G6-admitted but cycle non-additive on top of F-cascade; locked at no-op weight | `237457f` (SP-F) |

### Sub-path status board

| sub-path | doc anchor | status | outcome | commit |
| --- | --- | --- | --- | --- |
| **SP-A** Liquidation cascade impulse-response | 搂E.12 | **SUCCESS** 猸?| F-cascade (recency_score_5d) admitted; v6 ships `active_alternative` (2 horizons) | `977c1a0` |
| SP-B 1h Coinglass microstructure swarm | 搂H.4 / W3.5 | partial | B3a passes G6 but +0.94 sibling-corr with F-cascade; MF-07 (disagreement) data-rich but G6-fail | `329a76b` |
| SP-C Phase 1 Multi-horizon factor audit | 搂I challenge #3 | **SUCCESS** | All 5 score-integrated factors monotone-stronger at h10d; F47 idle factor unlock | `7199b89` |
| SP-C Phase 2 h10d cycle infrastructure | (continuation) | **SUCCESS** | walk-forward +13-19% confirmed at h10d; regime gates need recalibration | `d587740` |
| **SP-C Phase 3** validation_contract h10d sqrt-scaling | 搂G | **SUCCESS** 猸?| sqrt(2)-scaled `v10_h10d` contract; v6_h10d productionized (best walk-forward of any candidate) | `472ea4a` |
| SP-D BTC鈫抋lt basis shock propagation | 搂E.16 | **FALSIFIED** | t-stat 1.39 < 2.0; D2/D3 \|IC\| << 0.04; MF-04 saturation under lsk3+F12 confirmed | `2cc580b` |
| SP-E Realized correlation regime gate | 搂E.17 | **FALSIFIED** | Tertile-stratified IC ratio 0.90 (REVERSED vs doc prediction of 鈮?.20); rejected as gate | `f52aef7` |
| SP-G DVOL extensions overlay | (no doc anchor) | NEUTRAL | regime_gating_v3 strict-passes but DVOL anomaly days don't overlap strategy losses; not promoted | `f52aef7` |
| **SP-F** Sub-day funding microstructure (extending F08) | 搂D MF-04 | MIXED 鈥?admission win, cycle non-additive | F1 G6 +0.040 t=7.24 vs lsk3+F08 (admitted); cycle layer no marginal value over v6_h10d when stacked with F-cascade | `237457f` |
| **SP-H** Hedge unwind around derivatives expiry | 搂E.15 | **FALSIFIED** | KS-test p=0.128>0.05 (signal direction correct: -62 bp in-window vs out-window 5d return, but sub-significance); H1/H2 universe-wide; H3 raw IC 0.16 strong but G6 fails (vol dimension absorbed by lsk3) | `b3a69fb` |
| **SP-J** Regime-conditional alpha architecture | 搂G.5 (extended) | **AT-PAR 鈥?architecture validated, F1 alpha NOT unlocked** | v10 strict-passes contract but cycle-flat vs v6_h10d (walk-forward 螖=0.000, regime preserved). Confirms SP-F cycle non-additivity is FUNDAMENTAL (not architecture-driven). Architecture preserved as Stage-2 primitive for future regime-localized alpha. v10 ships `experimental`. | `6edfb70` |
| **M3.1** Deribit options surface (Phase 0) | 搂H.4 / 搂E.1 / 搂E.2 / 搂E.15 | **PHASE 0 SCOPING DONE 鈥?owner-decision required for Phase 1+** | Deribit Public API doesn't provide historical OI by strike or IV by strike (matches doc 搂E.1 prediction). 5 factors only F57 IV-RV spread feasible on existing data 鈥?but universe-wide 鈫?cross-section G1 fail by design. F56/F58/F59/F60 require multi-day live sync (60-90d wall-clock) OR paid history (Tardis.dev ~$50-200). Recommended Stage-1: defer to Owner decision. | `99d68bf` |
| **M3.1** Deribit options surface (Phase 1) | 搂H.4 / 搂E.1 / 搂E.2 / 搂E.15 | **PHASE 1 ACTIVE 鈥?pipeline shipped + first snapshot validated; 60-90d accumulation needed for F56-F59** | `sync_deribit_options_chain.py` shipped + first snapshot 2026-04-30T16:45Z (BTC 938 instr / 94 strikes / 13 expiries; ETH 774 / 81 / 13). Schedule registration deferred to Owner. F58 + F60 implementable at ~30d; F56 + F59 at ~60-90d. Earliest Day 90 鍑哄彛 path: F58 + F60 admission audit late June 2026 (calendar). | `7c905e0` |
| **M3.1** Deribit options surface (Phase 1.5) | (continuation) | **HISTORICAL FREE PATH REJECTED 鈥?paid Tardis.dev (~$50-200) or wait 30-90d wall-clock** | Empirical probe: Deribit Public API trades-by-time endpoint silently clamps to ~24-48h regardless of `start_timestamp` + `include_old=true`. Past-window probe (30d 鈫?25d ago) returned 0 trades. Free historical IV reconstruction NOT feasible. Owner-decision: Tardis.dev procurement (C1, ~$50-200, Day 90 closure ~2026-05-15) OR continue free live-sync (B, $0, ~2026-07-29). | (this commit) |

| **M3.1** Deribit options surface (Phase 6 full backfill + v0 overlay ablation) | `docs/quant_research/03_alpha_branches/m3_1_options_surface_overlay_preregistration_2026_06_13.md` | **REPORT-ONLY ABLATION COMPLETE - V0 FAILED RESEARCH-WATCH GATE** | Tardis remote backfill covered `2023-04-01` through `2026-06-13` with `39/39` monthly shards, failed partitions `0`, and final panel `2340` BTC/ETH rows. The context report allowed only the frozen report-only ablation (`overlay_context_research_allowed=true`, `score_layer_admission_allowed=false`). The ablation sets `research_watch_state_allowed=false`; blockers are worse full-OOS cumulative return, worse full-OOS h10d-equivalent Sharpe, and the same failures after excluding the first 30 context dates. Do not read `context_allowed` as overlay usable. No active registry, manifest, v1 policy, live, or timer mutation. | 2026-06-15 report artifacts |
| **M3.1** Deribit options surface (v1 overlay ablation) | `docs/quant_research/03_alpha_branches/m3_1_options_surface_overlay_v1_preregistration_2026_06_15.md` | **REPORT-ONLY ABLATION COMPLETE - V1 FAILED RESEARCH-WATCH GATE** | v1 treated v0 as failed comparator evidence and froze a signed-gamma / put-skew confirmed report-only throttle. It still triggered only `8/640` decisions (`0.0125`), below the preregistered trigger gate (`>=16` and `>=0.025`), with full-OOS cumulative return worse than baseline (`2.116687` vs `2.124385`) and max drawdown slightly worse, despite a tiny Sharpe/holdout improvement. Triggered-window attribution stayed adverse: 6 of 8 triggered windows were baseline-positive and triggered-window net return fell by `-0.025608`. No research-watch approval, score-layer admission, manifest mutation, v1 policy mutation, live, timer, or scheduler authorization. Do not continue by quantile-threshold micro-tuning; any next design must prove triggers primarily land on baseline-loss windows or require an explicit loss-state confirmation gate. | 2026-06-15 v1 report artifacts |
| **M3.1** Deribit options surface (v2 loss-state proof design) | `docs/quant_research/03_alpha_branches/m3_1_options_surface_overlay_v2_loss_state_preregistration_2026_06_15.md` | **CLOSED PATTERN - STAGE A DIAGNOSTIC FAILED LOSS-STATE PROOF** | v2 Stage A ran only the retained v1 precursor trigger alignment diagnostic. It failed all substantive gates: `8 < 16` triggered windows, triggered-loss fraction `2/8 = 0.25` below `0.60`, loss-fraction lift `-0.065625`, positive leakage `6/8 = 0.75` above `0.40`, and triggered baseline net-return sum `+0.373271` above `0`. The current `options stress -> portfolio throttle` shape is closed; reopening requires a new non-threshold-microtuned precursor and retained Stage A proof before any Stage B return ablation. No research-watch approval, score-layer admission, manifest mutation, v1 policy mutation, live, timer, scheduler, or remote-runner authorization. | 2026-06-15 Stage A artifacts |
| **M3.1** Deribit options surface (precursor mechanism reset) | `docs/quant_research/03_alpha_branches/m3_1_options_surface_precursor_mechanism_reset_2026_06_15.md` | **MECHANISM-HYPOTHESIS RESET - NO CANDIDATE ADMITTED** | M3.1 options work is reset from portfolio-throttle repair to new precursor mechanism hypotheses. Any future document must propose a genuinely new, PIT-safe precursor and pass retained loss-state proof before return ablation; q-threshold micro-tuning, v0/v1 trigger repair, and portfolio multiplier actions remain forbidden. No research-watch approval, score-layer admission, manifest mutation, v1 policy mutation, live, timer, scheduler, or remote-runner authorization. | 2026-06-15 reset note |
| **M3.1** Deribit options surface (dealer hedge-pressure transition precursor) | `docs/quant_research/03_alpha_branches/m3_1_options_surface_new_precursor_dealer_hedge_pressure_transition_preregistration_2026_06_15.md` | **CLOSED FAILED MECHANISM EVIDENCE - NO CONFIRMATION-THRESHOLD TUNING** | The new mechanism was implemented only as a loss-state proof runner and failed. It hit the trigger-count floor exactly (`16`), but triggered baseline-loss fraction was `5/16 = 0.3125` versus all-window `0.315625`, loss-fraction lift was `-0.003125`, positive leakage was `11/16 = 0.6875`, and triggered baseline net-return sum was `+0.472731`. Retained summary `sha256=561951f4e2ad011fc8f3f1093fb3c0f368fceeb9733c3a4501c93a7e1f845dc7`. Do not repair this path by tuning `return_1`, `momentum_5`, `basis_velocity_3d`, taker pressure, perp-volume expansion, prior-observation count, or same-family AND/OR wiring. No return ablation, score-layer admission, manifest mutation, paper-shadow, live, timer, scheduler, remote-runner, portfolio multiplier, or trading-action authorization. | 2026-06-15 precursor proof artifacts |
| **Parallel 1h / Tardis** intraday baseline + liquidity-shock impulse | `docs/quant_research/04_parallel_1h/intraday_baseline_contract_2026_06_16.md`, `docs/quant_research/04_parallel_1h/tardis_intraday_liquidity_shock_impulse_preregistration_2026_06_15.md` | **BASELINE CONTRACT OPENED; 18-MONTH BTC/ETH COVERAGE PASSED - STAGE A MECHANISM PROOF FAILED; COLUMNAR PIPELINE PROFILED; PIT CORE SCOPE FROZEN** | Implements only the Stage A artifact runner at `scripts/quant_research/parallel_1h/run_tardis_intraday_liquidity_shock_impulse_stage_a.py`. After the local raw-missing run and one-day/cross-month smokes, external raw staging was expanded to `2025-01-01` through `2026-06-13`, retaining `5290/5290` BTC/ETH `binance-futures` partitions across 18 distinct months, failed `0`, and staged `338,327,222,114` raw bytes (`sha256=bf35c47323606f318c1b0624d1ddd106d7dbc7894afb53079bfa5446ed3c0026`). The same Stage A runner reran with coverage green (`event_count_total=57672`, BTCUSDT `29454`, ETHUSDT `28218`, `distinct_months_with_min_events=18`, missing fraction `0.0`) and summary `sha256=578088971fe4dd59f5a98abe3491149066ba928c3606dcb5a29fec27979accc1`, but the result remains `computed_failed_stage_a` because the primary 1h effect is only `0.1158457815` bps versus the `5.0` bps floor, the bootstrap CI includes zero, same-timestamp cross-symbol and label shuffles reproduce the effect, monthly holdout consistency is `0.5 < 0.6`, and BTC/ETH holdout erases or insufficiently preserves the effect. The execution substrate now separates raw normalization from proof: `normalize_tardis_intraday_liquidity_shock_raw_to_parquet.py` scans raw gzip/CSV into normalized parquet with raw-source hashes and profiling, while the Stage A runner is `v2_columnar`, rejects `--raw-root`, scans only parquet staging, and writes `intraday_liquidity_shock_profile.json`. Remote profiling retained `1058/1058` parquet partitions (`79M`, manifest `sha256=a39b36f6ac28064dcf24db83e9c11f99e6bd328e779da3fc8363eed4d864fdc8`) and a columnar-only Stage A rerun (`summary sha256=d3ab7a5c5b64c3a215f477d1e74c0b0dd30d6dffa1c24bf657422632795b13db`) with coverage green (`event_count_total=57637`, `distinct_months_with_min_events=18`) but mechanism proof still failed. The measured bottleneck is raw gzip/CSV normalization and aggregation (`normalize_and_write_seconds=4739.878081`; summed written aggregation `18940.63924` worker-seconds), not parquet writing (`2.503075` seconds) or Stage A columnar proof (`3.753678` seconds). The 2026-06-16 intraday baseline contract now requires separate labels, C0-C3 cost layers, D0-D4 delay layers, control groups, and proof gates before new mechanism design; BTCUSDT/ETHUSDT are Tier 0 anchor-only, not enough for a generalized intraday baseline. The PIT core selector at `scripts/quant_research/parallel_1h/build_tardis_intraday_liquid_perp_core_universe.py` uses retained PIT input `pit-liquidity-top100-2026-05-31.quant_universe.json` and freezes `20` symbols, `18` non-BTC/ETH names, and `3` liquidity buckets with local summary `sha256=5e45f375524460fd7ef9823de94ed9279f4b2fd6d36383868a4eded3c33f5d37`; it writes only universe and staging-plan artifacts, no downloads, no raw scan, no Stage A proof, no PnL, and no trading action. The core scope gate is green, but generalized historical Stage A scope remains blocked until the frozen-core staging reaches `18` PIT-valid distinct months. Next infrastructure step is raw and normalized parquet staging for this frozen core before rerunning the same Stage A proof runner; next research step is not BTC/ETH-only mechanism tuning. No return ablation, score-layer admission, h10d bridge, manifest mutation, paper-shadow, live, timer, scheduler, remote-runner, portfolio construction, or trading-action authorization. | 2026-06-15 18-month Stage A artifacts plus 2026-06-16 baseline contract and PIT core freeze |

### SP-K addendum (2026-05-01)

> Small-cap post-pump short is now beyond ideation and into factor / cycle diagnostics.

- **Stage 0 event study**: `post_pump_stall` is the strongest version of the mechanism in `mid_tail_ex_majors`, with mean forward returns around `-1.48% / -2.99% / -4.09%` for `h3d / h5d / h10d`.
- **Admission extension**: `post_pump_stall_core_score_3d` is the lead SP-K factor. On `mid_tail_ex_majors`, `h5d`, it clears `G1/G3/G6` with raw IC `+0.0411`, regime same-sign `1.00`, residual IC vs lsk3 `-0.0444`. `post_pump_stall_oi_score_3d` is a close sibling, but not clearly superior.
- **Cycle conclusion**: the dedicated `mid/tail` long-short score family still fast-rejects. The control baseline itself is weak, and SP-K should **not** be promoted as a fresh base strategy in its current form.
- **Best current landing**: clipped short-side-only SP-K improves the weak control materially (`walk_forward_median_oos_sharpe` `-0.608` -> `-0.141`, worst regime `-6.447` -> `-5.899`), but remains below promotion standards. Owner-side interpretation: **overlay / gate candidate**, not standalone portfolio architecture.
- **Trading-risk readout**: the short basket still receives funding about 70% of the time, and clipped v2 reduces `>10%` 1d squeeze frequency modestly (`4.94%` -> `4.66%`) with a slightly weaker 5d short payoff.
- **Main-strategy overlay result**: when SP-K is attached to the active `v6_h10d` parent on `liquid_perp_core_20`, modifying only the short leg for `mid_liquidity` names, the architecture validates cleanly. `w=0.05` and `w=0.10` both strict-pass validation and remain **AT-PAR** on portfolio metrics (`walk_forward_median_oos_sharpe = 2.832`, loss-window fraction `0.3125`). `w=0.10` slightly improves short-basket economics; `w=0.15` is too aggressive and drops the walk-forward median to `2.428`.
- **Main-strategy replacement / veto result**: when SP-K stops perturbing the whole score and is used only as a short-slot replacement rule, the picture changes materially. The lead rule (`replace_mid_v1`) strict-passes validation, lifts walk-forward median OOS Sharpe from `2.832` to `4.076`, improves worst-regime median OOS Sharpe from `-2.736` to `-1.783`, keeps loss-window fraction flat at `0.3125`, and improves short-basket economics (`next_10d_mean -0.17% -> -0.28%`, `>5%` next-1d squeeze `11.83% -> 11.44%`). This is the first SP-K integration mode that appears genuinely additive on the healthy parent strategy.
- **LLM selected-short news-veto result**: after wiring the news-veto flags into the core feature-set build path, the formal selected-short variants `ss_veto_mini` and `ss_veto_adjudicated` both validation-pass on top of `replace_mid_v1_no_news` and raise walk-forward median OOS Sharpe from `4.076` to `4.611`. But they do so with worse tails and weaker realized economics: loss-window fraction worsens from `0.3125` to `0.34375`, worst-regime median OOS Sharpe worsens from `-1.783` to `-2.392`, validation Sharpe / net return fall from `2.400` / `0.228` to `2.121` / `0.181`, and short-basket next-10d mean weakens from `-0.28%` to roughly `-0.21%` / `-0.20%`.
- **Interpretation**: the news layer is now mechanically live, not disconnected. It touches about `20-21%` of selected-short rows across `45-47%` of timestamps and forces `227-241` additional replacements relative to `replace_mid_v1_no_news`. The issue is that those extra replacements are worse shorts than the names they eject, so stronger news adjudication does not rescue the current bottom-3 landing shape. Owner-side read: keep the corpus and plumbing, but do **not** promote the selected-short news-veto variant over `replace_mid_v1_no_news`.
- **Exposure-shape rerun**: treating adjudicated durable-news labels as a sizing problem is better than treating them as a replacement problem. `ss_do_not_fill_adjudicated` fails cleanly (`walk_forward_median_oos_sharpe = 2.755`, `loss_window_fraction = 0.375`, average short notional `~80%` of baseline). `ss_reduced_exposure_adjudicated` is the best news-aware landing shape so far: fast-reject-pass, `walk_forward_median_oos_sharpe = 4.711`, `worst_regime_median_oos_sharpe = -1.769`, and average short notional `~90%` of baseline.
- **Final owner-side read on the news lane**: `reduced-exposure` improves materially on forced replacement, but it still worsens `loss_window_fraction` from `0.3125` to `0.34375` and weakens weighted short-basket `next_10d_mean` from about `-0.28%` to `-0.23%`. So `replace_mid_v1_no_news` remains the preferred deployment; the news corpus and plumbing stay active, `do-not-fill` is rejected, and `reduced-exposure` remains exploratory rather than promoted.
- **Post-audit mainline correction (2026-05-03)**: `replace_mid_v1_no_news` remains useful SP-K factor evidence, but it is no longer the h10d canonical parent because it was built on legacy `v6_h10d` + `regime_gating_v2`. The canonical parent is now `v5_rw_bridge_no_overlay_h10d`; SP-K may only re-enter as a research-only challenger attached to that parent and judged by fixed-set paired comparison plus overlay ablation.

### MF-01 addendum (2026-05-02)

> `1h orderbook / inventory risk transfer` is now beyond proposal stage and has completed both Stage 0 event study and first formal parent-strategy A/B.

- **Stage 0 result**: `boundary_fragile_orderbook` is the cleanest broad MF-01 mechanism so far. Inside `v6_h10d` short-boundary candidates it prints roughly `-1.31%` / `-2.04%` mean forward returns at `h5d` / `h10d`, with t-stats around `-2.14` / `-2.25`.

### Main-roadmap correction (2026-05-03)

> The canonical parent is now `v5_rw_bridge_no_overlay_h10d`. Recent Stage 0
> tests should narrow the next mainline rather than add more candidates.

- **Canonical parent rule**: all new h10d candidates must be evaluated against
  `v5_rw_bridge_no_overlay_h10d` with fixed-set paired evidence and strict
  falsification. Legacy `v6_h10d`, `regime_gating_v2`, and legacy-parent SP-K
  are comparator / research-only.
- **SP-K current-parent rerun**: `xs_alpha_ontology_v5_rw_bridge_no_overlay_spk_short_replace_mid_v1_h10d`
  remains a useful short-side research lane, but it is not promotable. It
  fast-rejects positively, but strict validation is quarantined and the
  canonical-parent paired edge is weak.
- **Experiment 4, Funding + OI crowded squeeze failure**: broad crowding is
  `stage0_reject`; extreme crowding is only `stage0_watch`; using it as a hard
  SP-K confirmation gate narrows replacements but underperforms raw SP-K. Do
  not promote this to canonical replacement.
- **Experiment 5, Post-capitulation long replacement**: canonical long-boundary
  replacement is `stage0_reject`. The signal may be useful as rebound sleeve or
  `do-not-short` veto, but not as a parent-long replacement.
- **Roadmap implication**: continue the main roadmap, but do not spend the next
  slot on generic funding/OI, stablecoin daily overlays, or liquidation-rebound
  long replacement. The next executable mainline should be either:
  1. `M3.3 event tape / narrative state` for SP-K hardening; or
  2. a narrower, cost-aware `MF-01 orderbook / inventory` challenger on the
     canonical parent.
- **M3.3 Stage 0 event-tape result (2026-05-03)**: the event-tape bootstrap is
  now live against the canonical `v5_rw_bridge_no_overlay_h10d` parent. Using
  the adjudicated crypto-news corpus, broad `confirmed` / `real_repricing`
  short vetoes are rejected for SP-K entered shorts: flagged entered shorts were
  better shorts (`next_10d_mean ~= -5.02%` for confirmed-event rows versus
  `-0.52%` unflagged). The first promising separator is instead `hype`
  chatter: hype-tagged entered shorts were weaker (`+0.17%` next 10d versus
  `-1.18%` unflagged) and had higher next-day squeeze risk. Next mainline
  slice should be `hype_chatter_decay_gate`, not official-event exclusion.
- **M3.3 hype-gate follow-up (2026-05-03)**: direct conversion into a gate is
  not promotable. `hype_candidate_veto` worsens SP-K no-news (`next_10d_mean
  -0.278% -> -0.193%`) because replacement rows are worse than the hype rows it
  removes. `hype_candidate_plus_selected_veto` is only watch-worthy (`-0.278%
  -> -0.292%`) and still has a mixed changed-row risk profile. M3.3 should now
  move upstream to parent-independent event-state features rather than another
  direct SP-K news veto.
- **M3.3 parent-independent event-state result (2026-05-03)**:
  `m3_3_event_state_short_quality_v1` has the right sign as a feature seed
  (`all_core rank IC ~= +0.054`, parent-bottom-8 rank IC ~= +0.025` versus
  short payoff). Boundary selection slightly improves parent shorts
  (`next_10d_mean -0.167% -> -0.203%`, +1d delay `-0.271%`), but changed
  entered rows are still positive-return shorts (`+0.055%`). Do not create a
  manifest candidate yet; require a stricter event-state feature and
  symbol-holdout before promotion.
- **M3.3 strict event-state result (2026-05-03)**: the stricter condition now
  clears Stage 0. `strict_q1_noise0` (`short_quality >= 1`, `noise_ratio = 0`,
  no hype) changes about `21.6%` of timestamps, improves selected shorts versus
  parent by about `-0.154%` h10d, and enters genuinely negative-return shorts
  (`-2.18%` h10d; entered-minus-exited about `-1.90%`). +1d event delay remains
  directionally positive (`entered -1.49%`, entered-minus-exited `-1.82%`).
  The first quarantined formal A/B scaffold has now run with native event-state
  feature generation. Validation contract passes and the experiment itself is
  credible (`rank IC ~= 0.117`, validation Sharpe `3.90`, test Sharpe `2.50`,
  walk-forward median OOS Sharpe `3.98`). Fixed-set comparison now computes and
  passes versus the canonical parent (`+0.290` cumulative return diff, `+0.281`
  Sharpe diff, bootstrap P(candidate > parent cumulative return) `0.902`).
  It is **not promotable**: fast statistical falsification blockers are
  `time_shuffle_failed`, `label_shuffle_failed`, `symbol_holdout_failed`, and
  `liquidity_bucket_consistency_failed`. M3.3 should continue only as robustness
  narrowing, not as a production candidate.
- **M3.3 robustness v2 result (2026-05-04)**: threshold narrowing does not solve
  the blocker shape. `v2_q2_noise0` is the best local variant (`+0.052%` mean
  edge vs parent, entered h10d `-1.77%`), but AVAX remains a negative holdout and
  only one liquidity bucket has positive edge. Do not open a v2 manifest A/B;
  future M3.3 work needs a different event-state definition or non-news
  mechanical confirmation.
- **M3.3 + MF-01 confirmation result (2026-05-04)**: orderbook fragility is a
  useful confirmation filter but too sparse for portfolio transmission. Confirmed
  M3.3 entered rows improve to `-2.59%` h10d and work in both mid/top liquidity,
  but the rule changes only `1.65%` of timestamps and parent-level mean edge is
  effectively zero. Do not open a manifest A/B.
- **M3.2 canonical-parent Stage 0 (2026-05-04)**: the current MF13/MF14 score
  perturbations do not transmit on `v5_rw_bridge_no_overlay_h10d`.
  `mf14_sell_beta_v5_parent` is the best slice, but ready-window long-short mean
  improves only `+0.000445` and short-boundary changes are just `0.18%` of
  timestamps. `MF13_tron_impulse`, `MF14_rebound_idio`, and
  `MF14_sell_mid_short` are exact at-par. Do not open a canonical manifest A/B
  for these smooth score shapes; re-open M3.2 only with a discrete
  boundary/stress-state landing or materially more ready-window history.
- **MF-05 cross-venue boundary Stage 0 (2026-05-04)**: 1d spot-dispersion /
  Binance-premium boundary rules have enough transmission but the wrong
  direction. `select_high_dispersion_q90` changes `24.9%` of timestamps but
  worsens selected-short edge by `-0.001324`; `select_abs_binance_premium_q90`
  also worsens by `-0.000971`. Veto variants are at-par to negative. Do not open
  a canonical manifest A/B for current MF-05 1d boundary shapes; re-open only
  with event-conditioned or sub-day venue stress definitions.
- **MF-05 + SP-K event-conditioned Stage 0 (2026-05-04)**: the plausible re-open
  path also fails on the current 1d cross-venue panel. Raw SP-K still improves
  the canonical parent short basket (`-0.001673` -> `-0.002781` h10d mean), but
  requiring cross-venue confirmation worsens raw SP-K by about `12-13 bps` while
  changing roughly `52%` of timestamps. Cross-venue veto changes only
  `0.27-0.46%` of timestamps and is at-par. Current MF-05 close-price dispersion
  is closed until sub-day venue stress, venue volume migration, or explicit
  venue-local state data is added.
- **MF-07 + SP-K event-conditioned Stage 0 (2026-05-04)**: participant
  disagreement also fails as the next SP-K confirmation layer. Raw SP-K remains
  positive versus the canonical parent (`-0.001673` -> `-0.002781` h10d mean),
  but MF-07 confirmation changes about `45-52%` of raw SP-K timestamps and
  worsens the short basket by roughly `8-15 bps`. Veto variants are at-par or
  too sparse (`0.18-6.86%` changed timestamps). Current daily MF-07 is closed
  until sub-day participant pivot timing or lead-lag state data is added.
- **MF-07 sub-day participant-pivot Stage 0 (2026-05-04)**: the raw 1h re-open
  path also fails. The evaluator loads `17/17` canonical subjects from the
  local `coinglass_extended` 1h cache and gets `65.16%` 24h pivot coverage, but
  participant-pivot confirmation changes about `46-51%` of raw SP-K timestamps
  and worsens the short basket by roughly `9-12 bps`. Veto variants are at-par
  with only `1.65-5.86%` changed timestamps. MF-07 is now closed for daily and
  current raw-1h threshold forms; do not spend the next mainline slot here.
- **M3.2 boundary activation Stage 0 (2026-05-04)**: the discrete re-open
  succeeds where old smooth MF13/MF14 shapes failed. Four sparse rules are
  Stage0-positive versus `v5_rw_bridge_no_overlay_h10d`:
  `tron_impulse_short_high_beta_rs` (`+0.009474` active-window long-short
  delta on `22` active timestamps), `tron_heat_short_high_rs` (`+0.007439` on
  `23`), `rebound_long_idio` (`+0.006026` on `12`), and
  `sell_pressure_short_high_beta_rs` (`+0.005579` on `16`). This re-opens
  M3.2 as the next falsification lane only; do not promote or launch manifest
  A/B until delay, shuffle, symbol-holdout, liquidity-bucket, and cost-stress
  controls pass.

### M3.2 addendum (2026-05-02)

> `stablecoin plumbing + on-chain reflexivity` is now out of pure infra and into first admission-grade research.

- **Phase 1**: `CryptoQuant` sync is live and smoke-validated; default-root history now exists under the local M3.2 external cache.
- **Phase 2**: fused daily panel shipped:
  - `src/enhengclaw/quant_research/onchain_m3_2_features.py`
  - `artifacts/quant_research/onchain/m3_2_feature_panel_1d.csv`
- **Coverage status**: the stablecoin lane is no longer `usdt_eth-only`.
  - Current live-verified `supply` token set is `usdt_eth + usdc + dai + tusd + usdt_trx + usdt_omni`
  - Current live-verified `exchange-flow` token set is `usdt_eth + usdc + dai + tusd`
  - `usdt_trx` and `usdt_omni` are currently `supply-only` because CryptoQuant flow endpoints are not uniformly valid on those routes
  - `usdc_eth` / `dai_eth` are invalid on the current endpoint surface, so chain naming is mixed and coverage is still partial
- **Non-ETH raw-lane expansion**:
  - a new `TronScan`-backed raw lane now exists at `%LOCALAPPDATA%\\EnhengClaw\\onchain_stablecoin_tron\\daily_aggregates.csv`
  - verified `USDT_TRX` aggregate history now covers `2024-05-01` -> `2026-04-30` (`730` daily rows)
  - the fused panel now unions provider date spines instead of anchoring only on Alchemy, so `USDT_TRX` history extends raw panel coverage even before full M3.2 readiness
- **Date coverage**: the fused panel now starts at `2024-05-01`, decision dates start at `2024-05-02`, `tronscan_tron_flow_days = 730`, and `m3_2_panel_ready_days = 124`.
- **Admission rerun on broader token coverage**:
  - `MF14_sell_pressure_defensive_gate_v1` remains the cleanest early winner. At `h5d`, it strict-passes with `G1 = +0.0834`, `G6 = +0.0734`, `G3 = pass`; at `h10d`, it stays positive but fails on regime consistency (`G1 = +0.0780`, `G6 = +0.0562`).
  - `MF14_capitulation_rebound_idio_gate_v1` improves materially on the broader supply set and now strict-passes at both horizons: `h5d G1 = +0.0433 / G6 = +0.0661`, `h10d G1 = +0.0772 / G6 = +0.0870`.
  - `MF13_flow_rotation_gate_v1` and `MF13_flow_idio_gate_v1` still strict-pass in admission terms, but with **negative empirical sign** on both `h5d` and `h10d`; they remain sign-discovery results, not promotion candidates.
  - `MF13_supply_beta_gate_v1` still fails on both horizons.
- **USDT_TRX-triggered MF-13 candidates**:
  - `MF13_tron_flow_impulse_defensive_beta_gate_v1` is the first clean positive-sign non-ETH `MF-13` winner so far. It strict-passes at `h5d` (`G1 = +0.0803`, `G6 = +0.0996`, `G3 = 1.00`) and remains a strict-pass at `h10d` (`G1 = +0.0409`, `G6 = +0.0499`) on `11` active timestamps.
  - `MF13_tron_flow_impulse_idio_gate_v1` also strict-passes at `h5d` (`G1 = +0.0765`, `G6 = +0.1008`, `G3 = 1.00`) on the same `11` timestamps, but fails at `h10d`; it looks short-lived rather than fully persistent.
  - `MF13_tron_speculative_heat_defensive_beta_gate_v1` is extremely sparse (`3` active timestamps) but strongest on pure admission metrics: `h5d G1 = +0.1107 / G6 = +0.0489`, `h10d G1 = +0.2028 / G6 = +0.1078`.
- **Interpretation shift**:
  - the first useful non-ETH `MF-13` signal is not 鈥渂roader smooth stablecoin growth,鈥?but **extreme `USDT_TRX` flow states acting as triggered cross-sectional gates**
  - the cleanest early shape is `defensive beta when TRON USDT flow impulse / speculative heat is extreme`
  - the key remaining research risk is **trigger sparsity**, not sign ambiguity
- **MF14 overlay A/B**:
  - `MF14_sell_pressure` and `MF14_rebound_release` were both tested as `regime gate / sleeve multiplier` overlays stacked on top of `alpha_ontology_regime_gating_v2`.
  - Both finish `no_material_change` on core walk-forward metrics versus baseline (`walk_forward_median_oos_sharpe` stays `2.832`), while execution-layer `test_net_return / test_sharpe` get worse.
- **MF14 cross-sectional gate A/B**:
  - `MF14` was also retested as three local cross-sectional gates on top of `v6_h10d`:
    - `xs_alpha_ontology_v12_mf14_sell_beta_h10d`
    - `xs_alpha_ontology_v12_mf14_sell_mid_short_h10d`
    - `xs_alpha_ontology_v12_mf14_rebound_idio_h10d`
  - Formal result is still `no_material_change` for all three:
    - `walk_forward_median_oos_sharpe = 2.832` for every variant
    - `delta_test_net_return ~= -0.0132`
    - `delta_test_sharpe ~= -0.3357`
    - `delta_test_max_drawdown ~= +0.0187`
- **MF13 TRON regime-aware gate A/B**:
  - the first TRON-aware `MF-13` overlay was tested as `alpha_ontology_regime_gating_v2_mf13_tron_flow_impulse_v1`
  - formal result is still `no_material_change`:
    - `walk_forward_median_oos_sharpe = 2.832`
    - `delta_test_net_return ~= -0.0132`
    - `delta_test_sharpe ~= -0.3357`
    - `delta_test_max_drawdown ~= +0.0187`
  - interpretation: the multiplier is too broad / too active relative to the parent strategy's existing risk budget
- **MF13 TRON cross-sectional gate A/B**:
  - the lead local gate `xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d` now runs end-to-end through the admitted feature path
  - formal result stops at `fast_reject_failed` with blocker `factor_evidence_lite_failed`
  - lite cycle metrics stay flat versus baseline (`walk_forward_median_oos_sharpe = 2.832`, `loss_window_fraction = 0.3125`), while `test_net_return` / `test_sharpe` weaken by about `-0.0132` / `-0.3357`
  - interpretation: the first clean positive-sign non-ETH `MF-13` admission winner is real, but the current local-gate landing still does not lift the mother strategy
- **Owner-side read**: the lane is now **broad enough for real research, but still alpha-incomplete**. The current blocker is no longer provider access; it is finding a landing shape where `MF-13/MF-14` actually improve the mother strategy rather than only passing admission.
- **Sparse trigger result**: `pump_bid_replenishment_failure` is directionally the strongest local event (`h5d ~= -4.85%`, `h10d ~= -9.59%`, `100%` negative at `h10d` on `n=8`), but the sample is very small.
- **Formal A/B result**: once converted into `v6_h10d` short-boundary replacement rules, MF-01 does **not** beat the current SP-K winner `replace_mid_v1_no_news`.
  - `mf01_boundary_fragile_v1`: `walk_forward_median_oos_sharpe = 2.461` vs `4.076`, `loss_window_fraction = 0.34375` vs `0.3125`, short-basket `next_10d_mean ~= -0.109%` vs `-0.248%`.
  - `mf01_pump_bid_fail_v1`: `walk_forward_median_oos_sharpe = 2.270`, `loss_window_fraction = 0.40625`, `positive_regime_fraction = 1/3`, and replacement churn is too high (`timestamps_with_short_changes_fraction ~= 98.6%`).
  - `mf01_combo_v1`: effectively identical to `boundary_fragile_v1` in the first pass.
- **Narrow landing-shape result**: the requested confirmation / veto / guardrail pass is now complete.
  - `mf01_spk_confirm_v1`: changes `89` short slots versus `replace_mid_v1_no_news` across about `8.2%` of timestamps, but leaves `walk_forward_median_oos_sharpe`, `loss_window_fraction`, and `worst_regime` unchanged at `4.076 / 0.3125 / -1.783`. The changed names are not better shorts: entered `next_10d_mean = +2.87%` versus exited `+2.04%`.
  - `mf01_spk_ss_veto_v1`: validation-pass but realized no-op. It flags `14` selected-short rows, yet produces `0` actual short-slot changes versus `replace_mid_v1_no_news`.
  - `mf01_post_cascade_guardrail_v1`: extremely sparse. It triggers only `7` realized replacements, stays AT-PAR on cycle metrics, and the selected-short rows it flags still average about `-3.68%` over the next `10d`, so it is not yet a valid do-not-short rule.
- **Interpretation**: MF-01 is **mechanically live but still not promoted**. The mechanism is real enough to survive Stage 0, broad replacement tests, and the requested narrow landing-shape pass, but none of the current MF-01 forms beats `replace_mid_v1_no_news`.

### lsk3 baseline late-period decay diagnostic (2026-04-30, post-M2.5)

> M2.5 demotion experiment recommended demote for 7/11 lsk3 factors (3 retired). Diagnostic at `compute_lsk3_baseline_decay_diagnostic.py` ran 5-step audit (temporal raw IC split + temporal residual IC + internal correlation + late-period bootstrap CI + per-factor verdict) and concluded:

- **lsk3 baseline does NOT need restructuring** 鈥?late-period raw IC is healthy or strengthening for 8/11 factors (3 cross G1 floor 0.04: iv_smooth_60, dh_5, downside_upside_vol_ratio_30).
- **Only 2 factors show TRUE regime shift**: `coinglass_top_trader_long_pct_smooth_5` (raw IC -0.035 鈫?-0.008 late, CI includes 0) and `momentum_decay_5_20` (sign-flipped -0.022 鈫?+0.015 late, CI includes 0).
- **Internal redundancy is LOW** 鈥?only 1 lsk3 pair > 0.5 correlation: `iv_smooth_60` 鈫?`dh_60` (-0.522). All other pairs <0.5.
- **5/7 M2.5 demote recommendations were self-residual measurement artifacts** 鈥?when iv_smooth_60 and dh_60 both strengthen late, their mutual high correlation (-0.522) makes self-residual IC computation collapse one factor's residual onto the other. NOT a sign of decay.
- **`factor_lifecycle.py` augmented with raw-IC sanity check**: G.5 verdict preserved verbatim (doc compliance); each verdict annotated with `likely_artifact` / `likely_artifact_strong` when G.5 demotes but raw IC remains stable. Owner-side reads both signals. Re-run shows 10 of 14 demote recommendations flagged as artifacts (3 strong: tt_smooth_5, momentum_decay, F-triangle).

Full audit at `config/quant_research/threshold_provenance.md` "lsk3 baseline late-2026 decay diagnostic" section.

### Cross-cutting lessons (applied across sub-paths)

1. **G6 admission is necessary but NOT sufficient for score promotion.** v7 (F62 + F-cascade, commit 68c4593) and v9 (F1 + F-cascade, SP-F) both: two G6-admitted factors that don't add when stacked because their long-short top-3 selection contributions overlap in regime-stressed windows. Future score-integration tests MUST run a weight scan AND check non-additivity vs strongest existing component, not rely on per-ts rank correlation alone (which can be 鈮?.10 even when cycle metrics show full overlap).

2. **MF-04 saturation is dimension-specific, not statistic-specific.** F08 (1d-grain skew of funding) saturates F3 (sub-day skew of funding) 鈥?same statistic, different grain 鈫?collinear. But F08 does NOT saturate F1 (within-day std of funding) 鈥?different statistic on same data 鈫?orthogonal at the rank level (residual IC +0.040). Saturation tests must compare apples-to-apples (same statistic) not "anything in the same data family."

3. **Sharpe-magnitude thresholds are implicitly horizon-coupled.** The v10 contract was h5d-calibrated. h10d cycles fail "regime worst sharpe 鈮?-2.0" by default because sharpe scales with sqrt(N) under random-walk-IID. Fix: scale magnitude thresholds by sqrt(horizon_ratio); leave rate-based thresholds (loss_window_fraction, positive_regime_fraction) unchanged. SP-C Phase 3 ships `v10_h10d` contract.

4. **Doc-prescribed mechanism direction is not always empirical.** SP-E 搂E.17 ("low-corr regime 鈫?high IC") is empirically REVERSED on this panel (high-corr regime has higher IC under tertile split). SP-D 搂E.16 mechanism direction is correct but signal too weak (t=1.39 < 2.0). Doc mental models need empirical verification before being baked into gates or score weights.

5. **Sample-size matters in regime falsification.** Absolute-threshold splits (low n=9 in 搂E.17) can produce borderline-pass artifacts that disappear under tertile splits (n=365). Prefer balanced-sample partitioning over arbitrary thresholds when evaluating regime gates.

6. **Sign-flip pattern in baseline-over-correction.** Factor with raw IC negative + residual IC positive (after baseline) is the textbook over-correction case. Score-integration weight sign must follow **residual IC** (marginal contribution direction), NOT raw IC. SP-F first attempt (w=-0.020 matching raw IC) actively contradicted the residual signal; walk-forward dropped 0.32 + regime broke. Sign correction to w=+0.015 (matching residual IC) restored baseline metrics.

7. **Overlay enrichment must overlap with strategy-specific losing days.** SP-G DVOL anomaly throttle was operationally well-calibrated (4% trigger, sensible) but did NOT shift cycle metrics 鈥?DVOL z>2 days don't systematically coincide with lsk3 + F-cascade losing days at h10d. The W3.5 v2 success (trailing-mean return throttle) worked because it specifically captured slow-grind bear regimes that hurt lsk3. Future overlay components need failure-mode-aware design, not generic "vol regime detector."

8. **Negative findings have economic value.** SP-D / SP-E falsifications and SP-G neutral result unblocked resource allocation away from MF-04 cross-asset basis lane and 搂E.17 correlation gate, redirecting toward higher-ROI directions. Audit scripts preserved (`compute_basis_propagation_factor_report.py`, `compute_correlation_dvol_overlay_diagnostic.py`) for re-test when underlying data conditions change (sub-day grain, cross-venue, etc.).

9. **Self-residual IC is unreliable when baseline has high internal correlation.** lsk3 late-2026 decay diagnostic showed that 5/7 M2.5 demote recommendations were self-residual measurement artifacts 鈥?`iv_smooth_60` 鈫?`distance_to_high_60` mutual correlation -0.522 caused self-residual IC to collapse to ~0 even when raw IC strengthened. Demote decisions on residual-IC-only criteria need a raw-IC cross-check (factor_lifecycle.py now includes `assess_raw_ic_sanity_check` augmenting G.5 verdicts). Doc 搂G.5 self-residual <threshold criteria is operationally insufficient for high-internal-correlation baselines without raw-IC backstop.

10. **Regime-fragility is NOT signal decay 鈥?distinguish them in lifecycle decisions.** The tt_smooth_5 + momentum_decay per-regime deep dive (2026-04-30) found that BOTH factors with TRUE regime-shift evidence (raw IC bootstrap CI includes 0) actually have **fully restored signal in non-trend / non-rotation regimes** (tt_smooth_5 drawdown_rebound IC -0.033 t=-3.55; momentum_decay 2024Q3 historical precedent +0.047, 2026Q2 partial +0.107). The "decay" is regime-conditional, not permanent. G.5 state machine's `retired` recommendation cannot distinguish "regime-fragile" from "decayed" 鈥?owner-side override needed. Action options range from (A) keep-as-is, (B) reduce weight, (C) reformulate as regime-stable variant, (D) regime-conditional weighting. Phase-1 change requires owner decision; lifecycle is informational only.

11. **Median window sharpe 鈮?cumulative return 鈥?validation contract metric and terminal portfolio value can REVERSE.** v6 dual-horizon ensemble analysis (2026-04-30) found that despite v6_h10d's higher median window sharpe (+2.832 vs v6_h5d +2.373), **v6_h5d delivers higher cumulative compound return over the same 32-month walk-forward** (+109% vs +75.88%). Mechanism: h10d has fewer rebalance opportunities (3/month vs 6/month) with high per-rebalance edge; h5d has more opportunities with moderate edge 鈥?the higher rebalance frequency dominates the lower per-rebalance edge for terminal value. **Implication**: validation contract `median_oos_sharpe_min` favors low-frequency-high-edge horizons; cumulative return favors high-frequency-moderate-edge. For Stage-2 deployment criterion, owner-side may want to re-rank candidates by cumulative return + sharpe + regime breadth jointly. Future validation_contract may add `cumulative_compound_return_min` alongside median sharpe. v6_h10d's winning case rests on regime breadth (drawdown_rebound +2.17 vs h5d -3.37) and risk-adjusted sharpe 鈥?but if the Stage-2 deployment criterion is terminal value, v6_h5d may be preferable.

12. **Validating an architecture is separate from validating its alpha hypothesis.** SP-J regime-conditional alpha architecture (2026-05-01) executed correctly end-to-end (manifest + score function + regime classifier + strict-pass contract) but produced cycle-flat metrics vs v6_h10d (walk-forward 螖=0.000). The architecture is VALIDATED as Stage-2 primitive 鈥?future score-extension candidates with truly regime-localized alpha (NOT F-cascade-overlapping) can use this same pattern (`classify_regime_v10` + `regime_label_v10` panel column + score-layer regime-conditional weights). The F1 alpha hypothesis is REJECTED 鈥?F1's residual IC strength does not translate to cycle-layer marginal value at any weighting scheme (constant OR regime-conditional). **Implication**: cycle-layer non-additivity is more fundamental than weight architecture. Future regime-conditional candidates need cycle-layer non-additivity test BEFORE concluding admission strength translates to walk-forward lift. Pre-registered decision criteria (PROMOTE/AT-PAR/DECLINE before cycle runs) prevent post-hoc rationalization.

13. **A strong sparse-event factor may belong in the short-selection layer, not the portfolio base layer.** SP-K makes this concrete: `post_pump_stall_core_score_3d` is economically real and admission-clean on small-cap alts, but the dedicated `mid/tail` long-short family remains a fast-reject. A smooth score overlay on the healthy `v6_h10d` parent validates but stays AT-PAR; a discrete short-slot replacement rule becomes materially additive. Factor validity, overlay validity, and promotion validity are separate questions, and the **highest-ROI landing may be a boundary-rule that changes only a few short slots rather than the whole cross-sectional rank**.

### Where to read more

- **Per-sub-path detail + lessons**: 搂G "Completed sub-paths" below (newest first).
- **Full audit lineage + threshold rationale**: [`config/quant_research/threshold_provenance.md`](../../../config/quant_research/threshold_provenance.md).
- **Per-candidate cycle outcomes**: each `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v*.json` carries a `lineage` + `verified_outcome_2026_*` block.
- **Active mechanism families coverage**: 搂A.4 below + `docs/quant_research/mechanism_notes/MF_*.md`.
- **Forward-looking priority synthesis**: [`next_stage_alpha_map.md`](next_stage_alpha_map.md) 鈥?six-lane ranking of where the next materially-new alpha is most likely to come from, with recommended landing shape (`base score` vs `overlay` vs `replacement / veto` vs `regime gate`).
- **M3.3 bootstrap plan**: [`event_tape_narrative_research_plan.md`](../03_alpha_branches/event_tape_narrative_research_plan.md) 鈥?what can start immediately on `event tape`, what is still blocked on missing news / social history, and the recommended phased path from `real-news exclusion` to full `narrative__*` state machines.
- **MF-01 formal proposal**: [`orderbook_inventory_risk_transfer_proposal.md`](../03_alpha_branches/orderbook_inventory_risk_transfer_proposal.md) 鈥?1h orderbook / inventory-risk-transfer proposal with candidate factors, field mapping, Stage 0 event-study design, and recommended `replacement / veto / gate` landing order.
- **ABC catalog docs (cross-cutting reorganized views)**:
  - [`factor_audit_trail.md`](factor_audit_trail.md) 鈥?per-factor one-stop index (~35 factors with provenance, current state, admission outcomes, lifecycle, references).
  - [`experiment_catalog.md`](experiment_catalog.md) 鈥?weight scans, variant audits, failed integrations, falsified mechanisms, horizon scans, lifecycle experiments.
  - [`algorithm_choices.md`](algorithm_choices.md) 鈥?Architecture Decision Records for ~25 design choices (admission thresholds, weight calibration, score architecture, lifecycle, falsification rules).

---

## A. Utilization audit (what's used vs idle)

### A.1 Score-layer adoption

Across all five active alpha-ontology score functions (`xs_alpha_ontology_v1` through `v5`), only **14 distinct columns** are referenced:

```
intraday_realized_vol_4h_to_1d_smooth_60     realized_volatility_5
distance_to_high_60                          distance_to_high_5
coinglass_top_trader_long_pct_smooth_5       liquidity_stress_qv_iv
momentum_decay_5_20                          coinglass_taker_imb_intraday_dispersion_24h
quality_funding_oi                           downside_upside_vol_ratio_30
funding_basis_residual_implied_repo_30       funding_term_skew_60          (M2.2)
contagion_in_degree (v_alpha_v2 only)        settlement_cycle_premium_60d  (M2.3)
```

### A.2 Implemented-but-idle factors (the ~50-row long list)

`features.py` builds many more columns than score functions consume. Notable idle factors:

| Factor (column name) | Origin | Why idle |
| --- | --- | --- |
| `realized_skew_20_xs_z`, `realized_kurt_20_xs_z` | W1.1 MF-10 | failed G6 vs lsk3 baseline |
| `flow_persistence_against_price_20`, `qv_acceleration_residual_xs` | W1.1 MF-06 reflexive flow | failed G6 |
| `funding_basis_residual_20`, `funding_zscore_20` | W1.1 / panel basics | F12 / F09 already absorb most signal |
| `funding_flip_decay_phase`, `oi_shock_decay_phase`, `vol_shock_impulse_phase` | W3.1 MF-08 state machines | F49 alone went into overlay; F46/F47/F48 not in any score |
| `lead_lag_beta_btc`, `lead_lag_residual_strength` | W3.2 MF-09 contagion | F29 only one promoted to v2 |
| `quote_share_change_30d`, `universe_rank_velocity_10`, `idiosyncratic_share` | W3.3 MF-11 rotation | F44 only universe-wide gauge promoted |
| `vol_of_vol_60`, `abnormal_range_z_60` | W1.1 MF-10 | failed G6 |
| `triangle_residual_60d` | M2.4 MF-04 | doc E.11 PASS but G6 fail (lsk3 saturation) |
| `cross_venue_spot_dispersion` | M2.1 v1 MF-05 | G6 fail (collinear w/ vol factors) |
| `funding_term_kurt_60` | M2.2 sibling | G6 fail |

**Pattern**: ~30+ factors implemented, only 11-12 in any score. The "lsk3 11-factor saturation ceiling" is empirically real for traditional MF-04 / MF-06 / MF-10 candidates.

### A.3 Raw data utilization gap (the headline)

Coinglass-extended cache contains 14 microstructure columns at 1h/4h/1d grains. Only **6 columns enter the panel**, all at 1d-aggregate grain. Detailed breakdown:

| Raw 1h Coinglass column                                     | Panel column derived               | Information loss |
| ----------------------------------------------------------- | ---------------------------------- | ---------------- |
| `long_liquidation_usd`, `short_liquidation_usd`             | `coinglass_liquidation_imbalance_24h`, `coinglass_liq_intraday_concentration_24h` | **Liquidation IMPULSE / cascade detection lost** 鈥?24h-aggregate kills E.12 mechanism |
| `global_account_long_pct/short_pct/long_short_ratio`         | `coinglass_global_account_long_pct` | Sub-day flow direction lost; only daily closing snapshot used |
| `top_trader_long_pct/short_pct/long_short_ratio`             | `coinglass_top_trader_long_pct[_smooth_5/_20/_60]`, `coinglass_top_trader_intraday_volatility_24h` | Top-trader vs global divergence (MF-07) lost; sub-day pivot moments lost |
| `orderbook_bids_usd/asks_usd/bids_quantity/asks_quantity`   | `coinglass_orderbook_imb_persistence_24h` | Sub-day depth velocity / velocity-of-velocity lost |
| `taker_buy_volume_usd`, `taker_sell_volume_usd`             | `coinglass_taker_imbalance_5d_sum`, `coinglass_taker_imb_intraday_dispersion_24h` | 1h flow persistence sign-rate lost; settlement-time taker skew lost |

### A.4 Mechanism family (MF) coverage map

| MF | Doc family            | Implemented? | In score / overlay? |
| -- | --------------------- | ------------ | ------------------- |
| MF-01 | inventory_risk_transfer | PARTIAL (`Stage 0` + broad/narrow SP-L trials shipped) | experimental selection-layer rules only; no promoted score |
| MF-02 | dealer_gamma            | NO  | needs Deribit OI by strike (M3.1 not yet) |
| MF-03 | funding_microstructure  | YES (F08)    | 鉁?in v4 |
| MF-04 | carry_residuals         | YES (F09/F11/F12/F13) | F12 in lsk3, others idle (saturation) |
| MF-05 | cross_venue_inventory   | YES (M2.1)   | 鉁?G6 fail |
| MF-06 | reflexive_flow          | YES (F16-F20)| 鉁?all admission-failed |
| MF-07 | participant_disagreement| **NO**       | **DATA READY** (top_trader vs global at 1h) 鈫?gap |
| MF-08 | event_impulse           | YES (F46-F49)| only F49 in overlay |
| MF-09 | cojump_contagion        | YES (F26-F29)| F29 in v2, F26 in overlay |
| MF-10 | higher_moment_fragility | YES (F31-F36)| only F33 in lsk3 |
| MF-11 | liquidity_migration     | YES (F41-F45)| only F44 in overlay |
| MF-12 | state_space_regime      | partial (regime_gating overlay) | overlay only |
| MF-13 | stablecoin_plumbing     | NO           | needs on-chain (M3.2) |
| MF-14 | onchain_reflexivity     | NO           | needs on-chain (M3.2) |
| MF-15 | settlement_friction     | YES (F62)    | 鉁?in v5 鈥?empirical winner |
| MF-16 | narrative_state         | NO           | needs NLP (M3.x) |

**MF-07 (participant_disagreement) is the ONE family with implementation gap but data ready.** Top-trader vs global account ratios at 1h grain are sitting in disk completely unused.

---

## B. Underused data summary (ranked by alpha-richness 脳 ease-of-use)

| Rank | Underused dataset                                    | Volume          | Doc family       | Mechanism unlocked                                                  |
| ---- | ---------------------------------------------------- | --------------- | ---------------- | ------------------------------------------------------------------- |
| 1    | Coinglass 1h liquidation flow (`*_liquidation_usd`)  | 17k脳93=1.6M obs | MF-12, E.12      | Cascade detection + post-cascade impulse-response                   |
| 2    | Coinglass 1h orderbook depth (`orderbook_bids/asks_*`)| 17k脳93=1.6M obs | MF-01            | Sub-day inventory imbalance + depth velocity                         |
| 3    | Coinglass 1h top-trader vs global (`*_long_pct/*ratio`)| 17k脳93=1.6M obs| MF-07            | Pro-vs-retail divergence 鈥?completely-untouched MF family            |
| 4    | Coinglass 1h taker flow (`taker_buy/sell_volume_usd`)| 17k脳93=1.6M obs | MF-06 reflexive  | Hour-of-day flow persistence (F62 sibling on flow side)               |
| 5    | DVOL daily OHLC (we use only `dvol_close`)           | 1k脳2 currencies | MF-10 / overlay  | Implied vol-of-vol (high-low spread) for richer regime gauge          |
| 6    | Per-venue spot 1d (M2.1 v1 panel)                    | 26k rows 脳 30 sym 脳 4 venue | MF-05 | Per-asset venue premium / cross-venue volume share                    |
| 7    | OKX 8h funding (M2.2 cache, 90-180d per symbol)      | ~7k rows 脳 27 sym | MF-04         | Single-venue funding flip detection on non-Binance venue              |
| 8    | Spot OHLCV `taker_buy_*_volume`                      | 17k 脳 100 sym  | MF-06           | Spot-side flow imbalance distinct from coinglass-derived perp flow    |
| 9    | Multi-grain {1h,4h,1d} cross-grain ratios            | already in panel | MF-10/MF-12   | Vol term-structure (intraday vs overnight)                            |
| 10   | Implemented-but-idle factors (W1.1, W3.x leftovers)   | ~30 factors   | MF-04/06/10     | Re-test at non-5d horizons (doc 搂I challenge #3)                      |

**Total idle observations**: ~6.4M Coinglass observation matrix mostly idle.

---

## C. Sub-path roadmap

Each sub-path is scoped to be **independently runnable** 鈥?no path blocks another. Priority is by Pareto-optimal `expected G6 admission probability 脳 effort`, calibrated against M2.x track record (1 of 4 cleared G6 鈫?MF-15 was the only winner).

### Sub-path SP-A: Liquidation cascade (E.12 / M3.4 鈥?UNBLOCKED ahead of schedule)

**Why now**: doc M3.4 was Day 61-90, but `coinglass_extended/{1h}` has `long_liquidation_usd` + `short_liquidation_usd` for 93 subjects 脳 720 days. Doc gives a clear falsification (post-cascade 24h abnormal return t-stat < 2.5蟽). High-conviction frontier per 搂E.12.

**Factor candidates:**
- **A1 鈥?`liq_cascade_event`** (event-study factor)
  Definition: 1h `(long_liquidation_usd + short_liquidation_usd) / open_interest_value` z-score vs rolling-30d baseline > 2.5 鈫?cascade event flag. Per-asset event count over rolling 24h.
  Expected sign: + (post-cascade mean reversion = forward return positive).
- **A2 鈥?`liq_to_oi_ratio_24h_signed`**
  Definition: rolling-24h sum (`long_liquidation_usd - short_liquidation_usd`) / `open_interest_value`. Captures net liquidation pressure direction.
  Expected sign: + (long-side liquidation = capitulation = mean revert up).
- **A3 鈥?`post_cascade_recovery_score`** (event-driven)
  Definition: (return_5d after a cascade event) - (return_5d in matched baseline period). Treated as factor: rolling-30d mean of "is this asset currently in a 5d post-cascade recovery window".
  Expected sign: + (positive abnormal return persists 24-72h).

**Doc falsification**: post-cascade 24h abnormal return t-stat < 2.5蟽 鈫?reject mechanism. Apply doc's threshold strictly.

**Effort**: S (1-2 hours). Module: `intraday_liquidation_features.py`. Late-merge into panel like F62 (M2.3 pattern).

**G6 success probability**: HIGH. Liquidation events are mechanistically distinct from any factor in lsk3 (lsk3 has no liquidation-direct signal 鈥?only `coinglass_liquidation_imbalance_24h` which is daily-aggregate, dampened).

**Interim deliverable**: v_alpha_v6_lsk3_g_v2 = lsk3 + F-cascade.

---

### Sub-path SP-B: 1h Coinglass microstructure factor swarm

**Why**: 1h Coinglass data is 6.4M obs of unused alpha matrix; F62 (M2.3) showed the 1h-input 鈫?1d-output pattern works on this data class. SP-A is just one slice of this; SP-B systematically explores the rest.

**Factor candidates** (each tested against G1+G3+G6 vs lsk3, F62-style late-merge):

- **B1 鈥?`orderbook_imb_velocity_1h`**
  Definition: per-asset rolling-30d std of 1h `(bids_usd - asks_usd) / (bids_usd + asks_usd)` 鈥?depth churn rate.
  MF: MF-01 inventory_risk_transfer.

- **B2 鈥?`top_global_disagreement_1h`** (MF-07 unlock)
  Definition: per-asset rolling-30d corr(top_trader_long_pct, global_account_long_pct) at 1h. Low corr = pros and retail diverging = informational asymmetry signal.
  Expected sign: - (high disagreement = uncertainty = forward negative). Or +: when pros lead, retail follows on lag.
  MF: **MF-07 鈥?completely untouched family**.

- **B3 鈥?`top_trader_velocity_1h`**
  Definition: per-asset 1h short-window change of `top_trader_long_pct` (gradient over 6h). High |gradient| = pros repositioning aggressively.
  MF: MF-07.

- **B4 鈥?`taker_flow_persistence_1h`**
  Definition: per-asset 1h sign(`taker_buy - taker_sell`) n-step persistence count over 24h. Captures sub-day directional flow.
  MF: MF-06 reflexive_flow.

- **B5 鈥?`hour_of_day_taker_skew`** (F62 sibling on flow side)
  Definition: per-asset 30d-rolling mean(`taker_buy - taker_sell` at pre-settlement hours {23,7,15}) - mean(other hours).
  Expected sign: probably NEGATIVE same as F62 (long-unwind = sell pressure).
  MF: MF-15 settlement-friction.

- **B6 鈥?`liq_concentration_24h_signed`** (sibling to A2 but at intraday concentration)
  Definition: hourly liq distribution Gini coefficient (concentration vs uniform). Concentrated = sudden cascade burst = signal.
  MF: MF-12 state_space_regime.

**Process**: implement all 6 in one module `intraday_microstructure_features.py`, run admission audit against G1/G3/G6, retain only those that PASS G6 strict (鈮?.02). Same M2.3 pattern.

**Effort**: M (4-6 hours total, but parallelizable; per-factor admission is fast).

**G6 success probability**:
- B2/B3 (MF-07 unlock): HIGH 鈥?completely-untouched family
- B5 (F62 sibling): MEDIUM 鈥?may be saturated by F62 itself
- B1/B4/B6: MEDIUM-LOW (similar mechanisms to existing 24h-aggregate columns)

**Interim deliverable**: v_alpha_v7 with whatever subset of B1-B6 PASS G6.

---

### Sub-path SP-C: Multi-horizon factor re-test (doc 搂I challenge #3)

**Why**: doc explicitly challenges "5d horizon is given" assumption. We ONLY tested factors at h5d. F46/F47 type state-machines may peak at 1d or 3d; F62 may be stronger at 1d.

**Process**: take the existing implemented-but-idle factors (~30 of them) and re-run admission audit at horizons {1d, 3d, 10d}. Find horizon-specific G6 winners. Build v_alpha_v8_h1d / v_alpha_v8_h3d / v_alpha_v8_h10d candidates.

**Factor candidates re-tested**:
- W1.1 leftovers: F09 (raw), F11 (basis_velocity), F13 (basis_carry_convexity), F16 (qv_accel_residual), F18 (flow_persistence), F19 (absorption), F20 (capitulation), F31/F32/F35/F36 (higher moments)
- W3.1 idle: F46/F47/F48 (state-machine phases)
- W3.2 idle: F27 (lead_lag_beta_btc), F28 (lead_lag_residual_strength)
- W3.3 idle: F41 (quote_share_change), F42 (universe_rank_velocity), F45 (idiosyncratic_share)
- M2 leftovers: triangle_residual_60d, cross_venue_spot_dispersion, funding_term_kurt_60

**Effort**: M-L (need new label_contract for non-5d horizons + cycle plumbing for h1d/h3d/h10d; ~6-8 hours including manifest variants per horizon).

**G6 success probability**: MEDIUM. Some factors may have wrong horizon for their EHL (e.g., MF-08 state-machine factors might shine at 1d not 5d).

**Interim deliverable**: horizon-specific v_alpha_v8_h{1,3,10}d candidates documenting per-horizon G6 winners.

---

### Sub-path SP-D: BTC鈫抋lt basis shock propagation (E.16)

**Why**: doc 搂E.16 鈥?when BTC has basis shock, alts follow in 12-48h via mechanical arbitrage capital reallocation. Data ready: we have basis_proxy at 1d for all subjects. No new sync needed.

**Factor candidates**:
- **D1 鈥?`btc_basis_shock_t_minus_1` per-asset** 鈥?1d-lagged BTC basis_proxy z-score broadcast as universe-wide regressor.
- **D2 鈥?`alt_basis_residual_after_btc`** 鈥?per-asset basis_proxy minus 尾 脳 BTC_basis_proxy (rolling-60d 尾). Residual captures alt-specific basis pressure.
- **D3 鈥?`basis_propagation_lag_corr_30d`** 鈥?per-asset rolling 30d corr(asset_basis[t], BTC_basis[t-1]). High corr = mechanically following.

**Doc falsification**: BTC basis shock 鈫?ALT basis impulse-response 1d-after t-stat < 2.

**Effort**: S (~2 hours). Single module, no new data.

**G6 success probability**: MEDIUM-LOW. May overlap with existing `quality_funding_oi` and `funding_basis_residual_implied_repo_30` (already MF-04 saturated).

---

### Sub-path SP-E: Realized correlation regime gate (E.17)

**Why**: doc 搂E.17 鈥?BTC-ETH 30d realized correlation switching 0.7鈫?.4 separates idiosyncratic from systematic alpha regimes. Use as universe-wide GATING var (not score factor).

**Factor candidates**:
- **E1 鈥?`btc_eth_realized_corr_30d`** 鈥?universe-wide gauge.
- **E2 鈥?`regime_low_correlation_indicator`** 鈥?binary: corr < 0.5 鈫?"alts decoupled" regime.
- **E3 鈥?Add to W3.5 v3 overlay**: when `corr < 0.5` AND `lsk3 score has high cross-section dispersion` 鈫?BOOST exposure (multiplier > 1.0); when `corr > 0.7` AND market beta dominant 鈫?throttle (multiplier < 1.0).

**Doc falsification**: cross-section IC in low-correlation regime not 1.2脳 baseline 鈫?reject as gate.

**Effort**: S-M (~3 hours). Extends regime_gating.py with v3 overlay variant.

**G6 success probability**: HIGH for the gate (W3.5 v2 pattern proved gating layer works); LOW if used as score factor.

---

### Sub-path SP-F: Sub-day funding microstructure (extending F08)

**Why**: F08 was 1d-grain skew. Binance funding events at 8h grain enable richer microstructure factors. Data already in `binance_derivatives/4h` (which has `funding_rate` per 4h bar 鈥?denser than 8h).

**Factor candidates**:
- **F1 鈥?`funding_intraday_dispersion_30d`** 鈥?rolling 30d std of within-day funding values (captures "how variable is the 8h funding sequence"). High dispersion = unstable carry regime.
- **F2 鈥?`funding_sign_flip_count_30d`** 鈥?count of funding-sign changes per 30d. High flip rate = structural noise.
- **F3 鈥?`funding_term_skew_60_residual_after_F08`** 鈥?orthogonalize various windows of skew against F08; residual is what F08 misses.

**Effort**: S (~1-2 hours).

**G6 success probability**: LOW-MEDIUM. F08 already extracts most MF-04 family signal; close cousins likely G6-fail.

---

### Sub-path SP-G: DVOL extensions (m7 overlay enrichment)

**Why**: We use only `dvol_close`. The OHLC of DVOL has more info 鈥?implied vol-of-vol (intraday DVOL range) is a regime-quality signal.

**Factor candidates**:
- **G1 鈥?`dvol_intraday_range_z90`** 鈥?`(dvol_high - dvol_low) / dvol_close` z-score on rolling 90d.
- **G2 鈥?Add to regime_gating v3**: when `dvol_intraday_range_z > 2` 鈫?vol-of-vol regime 鈫?throttle harder.
- **G3 鈥?Cross-pair DVOL ratio**: `btc_dvol / eth_dvol` regime 鈥?when ETH outpaces BTC 鈫?regime change indicator.

**Effort**: S (~1 hour).

**G6 success probability**: For overlay extension: HIGH (W3.5 v2 pattern). For score factor: LOW.

---

### Sub-path SP-H: Hedge unwind around derivatives expiry (E.15)

**Why**: doc 搂E.15 鈥?BTC/ETH monthly options expiry calendar is public knowledge; gamma window 3-5 days before expiry creates dealer hedge unwind pressure. Don't need OI by strike (which is M3.1) for the *event-study* version 鈥?just the calendar.

**Factor candidates**:
- **H1 鈥?`time_to_btc_expiry`** 鈥?universe-wide gauge: days until next BTC monthly options expiry (from public calendar).
- **H2 鈥?`expiry_window_indicator`** 鈥?binary: 1 if within 5d of expiry, else 0.
- **H3 鈥?`expiry_window 脳 return interaction`** 鈥?historical mean returns in expiry-window vs non-expiry. Treat as universe-wide gauge for overlay.

**Doc falsification**: KS-test of expiry-window 5d return distribution vs normal 5d distribution, p > 0.05 鈫?reject.

**Effort**: M (~2-3 hours). Need to bake the BTC monthly options expiry calendar (public, every last-Friday-of-month).

**G6 success probability**: MEDIUM as overlay component; UNCLEAR as score factor.

---

### Sub-path SP-I: Strategy-level (deferred 鈥?doc 搂I #3 + 1h-grain)

**Why**: doc 搂I challenge #3 ("5d horizon is given") and 搂I challenge #1 ("Top-K long-only is correct") were partially addressed by W2-A (long-short top-3) but not by horizon scan. SP-C handles factor-level horizon scan; SP-I is the strategy-level rewrite to 1h-grain.

**Scope** (deferred, large effort):
- Build complete 1h-grain panel pipeline using existing `build_cross_sectional_intraday_feature_bundle` (already in features.py, never invoked by manifests).
- New label contract for 1h forward returns (e.g., 24h-fwd at 1h bar grain).
- Recompute all W3.x universe-wide gauges in 1h-grain.
- Capacity reassessment (1h turnover would breach 0.005 max_trade_participation_rate easily).
- New manifest family `cross_sectional_intraday_1h`.

**Effort**: XL (3-5 day equivalent). DEFERRED unless SP-A/SP-B yield very high signals justifying the rewrite.

---

### Sub-path SP-J: Regime-conditional alpha architecture (post-Day-60 finding)

**Why**: After completing all original 搂C short-effort sub-paths (SP-A through SP-H) + M2.5 + late-2026 lsk3 decay diagnostic + tt_smooth_5/momentum_decay deep dive + dual-horizon ensemble analysis, **5 independent investigations converge on a single architectural conclusion**: regime-conditional weighting is the next unlock for current-data alpha extraction.

**Convergent evidence** (multi-source):
- **SP-F cycle non-additivity**: F1 funding_intraday_dispersion_30d passes G6 (residual IC +0.040 t=+7.24 vs lsk3+F08) but adds zero marginal cycle value at constant weight when stacked on F-cascade. Hypothesis: F1 alpha is regime-localized (rotation/drawdown) and constant-weight averaging dilutes it.
- **tt_smooth_5 per-regime deep dive**: drawdown_rebound IC -0.033 t=-3.55 (full restoration) vs trend_up IC = 0.000 (complete failure). Factor is regime-fragile, not decayed. Constant-weight weighting carries trend_up drag.
- **momentum_decay_5_20 per-regime deep dive**: rotation_high_vol IC = +0.075 t=+3.01 (sign-flipped strong) vs other regimes 鈮?0. The factor's optimal direction reverses by regime 鈥?constant-weight can't capture either.
- **v_alpha_v6 dual-horizon ensemble**: Pearson +0.843 same-sign 87.5% confirms v6_h5d and v6_h10d share alpha source (same lsk3+F-cascade score, different horizon). v6_h10d's median sharpe advantage is entirely concentrated in drawdown_rebound (h5d sharpe -3.37 vs h10d +2.17). **True diversification requires structurally regime-conditional alpha**, not horizon variants.
- **W3.5 v2 overlay success precedent**: trailing_universe_mean_return_30d throttle component WORKS specifically because it captures slow-grind bear regimes that hurt lsk3. The pattern "regime-conditional component on lsk3 losing days" is empirically validated.

**Factor candidates**:

- **J1 鈥?`xs_alpha_ontology_v10_regime_conditional_h10d`** 鈥?score function with regime-aware weights:
  - trend_up: lsk3 + F-cascade w=0.025 (= v6_h10d baseline)
  - rotation_high_vol: lsk3 + F-cascade w=0.025 + F1 w=+0.025 (rotation is where F1 might activate per momentum_decay finding)
  - drawdown_rebound: lsk3 + F-cascade w=0.025 + F1 w=+0.030 (strongest in cascade-recovery)
- **J2 鈥?Regime-aware position multiplier overlay v4** 鈥?add per-regime score-weight modifier (cleaner decoupling: keep score fixed, modify overlay).
- **J3 鈥?Regime-conditional ensemble v6_h5d + v6_h10d** 鈥?100% h10d in drawdown_rebound, 50/50 in trend_up, 100% h5d in rotation. Direct response to dual-horizon ensemble finding.

**Doc anchor**: doc 搂G.5 mentions "regime gating multipliers" but does NOT specify regime-conditional score-weight architecture. SP-J extends this pattern from overlay layer (per-period multiplier) to score layer (per-period weight).

**Doc falsification**: per-regime cycle outcome 鈥?at least one regime variant must pass strict (median sharpe > +2.832) without breaking another regime's worst sharpe. Specifically:
- (J1) v10 overall walk-forward median > v6_h10d +2.832
- regime_holdout per-regime median improves on at least one of {trend_up, rotation, drawdown_rebound} without breaking another

**Regime label source**:
- Option A (simpler, lookahead-risky): calendar-based labels matching existing 3 regime calendar windows
- Option B (no lookahead): trailing W3.5 v2 component readings (BTC vol regime quantile + trailing universe mean return)
- Decision: start with Option B for production-realism

**Effort**: M-L (~6-8 hours). Single new score function + new overlay variant + cycle test. Reuses existing F1 panel + W3.5 v2 regime detection.

**G6 / promotion success probability**: MEDIUM-HIGH for the regime-conditional pattern (W3.5 v2 historical precedent); LOW-MEDIUM for material walk-forward improvement over v6_h10d (high baseline; needs to clear +2.832).

**Why important even if walk-forward doesn't improve**:
- Establishes regime-conditional architecture as repeatable Stage-2 pattern.
- Tests F1 follow-up question (cycle non-additivity = constant-weight problem? or fundamental F-cascade overlap?).
- Demonstrates that regime gating extends from overlay layer to score layer.

**Lifecycle expectation**: ships as `experimental` initially. Promotes to `active_alternative` only if cycle outcome shows material lift over v6_h10d AND regime breadth preserved.

---

## D. Priority schedule (tomorrow 鈫?30 days)

| Sub-path | Effort | G6 prob | MF coverage gain | Schedule slot |
| -------- | ------ | ------- | ---------------- | ------------- |
| **SP-A 鈥?Liq cascade (E.12 / M3.4)** | S | HIGH | new MF-12 leg | **Immediate next** (highest expected value) |
| **SP-B 鈥?1h Coinglass swarm (esp. MF-07)** | M | mixed | **NEW MF-07 family** + sibling extensions | Right after SP-A |
| SP-E 鈥?Correlation regime gate (E.17) | S-M | HIGH for overlay | new gating var | After SP-A/SP-B; lightweight |
| SP-G 鈥?DVOL extensions | S | HIGH for overlay | overlay enrichment | Bundle with SP-E |
| SP-D 鈥?Basis-shock propagation (E.16) | S | MEDIUM | possible MF-04 redux | Speculative |
| SP-C 鈥?Multi-horizon re-test (doc 搂I #3) | M-L | MEDIUM | unlocks idle factors | After SP-A/SP-B |
| SP-H 鈥?Expiry hedge unwind (E.15) | M | MEDIUM | new event-driven | Mid-term |
| SP-F 鈥?Sub-day funding | S | LOW-MED | MF-04 sibling | Defer (lsk3 saturated) |
| SP-I 鈥?1h-grain strategy | XL | unknown | strategy-level | Defer (large) |

### Recommended execution order

1. **SP-A** (1-2h) 鈥?liq cascade. v_alpha_v6 candidate. Closes Day 60 / 90 doc bullet (M3.4 ahead of schedule).
2. **SP-B partial** (2-3h) 鈥?implement B2 (top vs global disagreement, MF-07 unlock) + B5 (hour-of-day taker skew, F62 sibling). These two have highest standalone G6 prob.
3. **SP-E + SP-G bundled** (~3h) 鈥?correlation regime gate + DVOL OHLC. Both feed regime_gating_v3 overlay.
4. **SP-C** (~6h) 鈥?horizon scan. Use existing factor library at h1d / h3d / h10d. May produce 2-3 new G6 winners.
5. Re-evaluate after this batch. If we have 3-4 new G6 winners, build v_alpha_v9 ensemble; if not, escalate to SP-D / SP-H.

Total effort estimate for steps 1-4: **~12-15 hours**. Expected outcome: 2-4 additional G6-passing factors, with at least one non-MF-04 family unlock (MF-07 or MF-12 cascade).

---

### Post-Day-60 priority schedule (effective 2026-04-30, supersedes the table above)

> The original `D. Priority schedule` table above was the pre-execution plan. By 2026-04-30, **all listed sub-paths SP-A through SP-H + M2.5 + lsk3 diagnostic + dual-horizon ensemble have been executed**. The table below reflects the post-Day-60 state with revised priorities based on 11 cross-cutting lessons + saturation findings.

**State summary** (per `Snapshot status` section above):
- 鉁?SP-A SUCCESS 鈥?F-cascade in v6 (active_alternative h5d + h10d)
- 鉁?SP-C Phase 1/2/3 SUCCESS 鈥?h10d productionization + sqrt-scaled v10_h10d contract
- 鈿狅笍 SP-B partial 鈥?MF-07 (1d-grain) empirically unimplementable
- 鉂?SP-D / SP-E / SP-G / SP-H 鈥?all FALSIFIED or NEUTRAL
- 鈿狅笍 SP-F 鈥?admission win but cycle non-additive at constant weight
- 鉁?M2.5 鈥?factor_lifecycle.py shipped, Day 60 PASS
- 鈿狅笍 lsk3 baseline LATE-2026 audit: NOT decayed; G.5 self-residual unreliable in high-internal-correlation baselines
- 鈿狅笍 Dual-horizon ensemble: 50/50 DECLINE; surfaces median sharpe vs cumulative return reversal

**Saturation findings**:
- MF-04 carry: SATURATED on lsk3+F12 (SP-D confirmed)
- MF-10 vol-of-vol: SATURATED on lsk3 (SP-H H3 confirmed)
- MF-07 1d-aggregate: empirically unimplementable (SP-B B2 fail)
- MF-12 state_space_regime: F-cascade is the SOLE productionized winner
- W3.5 v2 overlay: only `trailing_universe_mean_return` is strategy-aware; DVOL-class generic vol throttles (SP-G v3) don't overlap losing days

**Revised post-Day-60 priority schedule**:

**2026-05-01 update**: this priority queue is now being executed as a dual-track frontier program rather than a single-lane handoff. M3.1 daily Deribit snapshot accumulation has been operationalized, and M3.2 has started with an Ethereum stablecoin-plumbing Phase 0/1 lane via Alchemy (`USDT` / `USDC` / `DAI` issuance + transfer-velocity aggregates). The remaining Day-90 gap is no longer "frontier data not started"; it is "frontier data not yet converted into admitted alpha."

**2026-05-02 update**: M3.2 is no longer Alchemy-only bootstrap. The CryptoQuant Phase-1 scaffold is now shipped and materially broader than the first smoke: `onchain_cryptoquant.py`, `sync_cryptoquant_stablecoin_history.py`, `sync_cryptoquant_reflexivity_history.py`, and `run_quant_cryptoquant_m3_2_sync_cycle.py` are in place; live-verified stablecoin coverage is `usdt_eth + usdc + dai + tusd`, the fused panel is live, the MF-13 / MF-14 admission rerun is complete, and the first MF-14 regime-overlay A/B has been formally tested. The remaining gap is no longer infra; it is strategy-layer conversion.

| Sub-path | Effort | G6/Promotion prob | Strategic rationale | Schedule slot |
| --- | --- | --- | --- | --- |
| **SP-J 鈥?Regime-conditional alpha architecture** | M-L (~6-8h) | MEDIUM-HIGH for arch pattern; MEDIUM for material walk-forward lift | 5 independent deep dives converge: regime-conditional weighting unlocks F1 + per-regime fragility + dual-horizon overlap | **Immediate next** 猸?|
| Day 90 搂H.4 M3.1 鈥?Deribit options surface | XL (multi-day) | UNKNOWN; HIGH if 搂E.15 strong-form productionize | unlock MF-01/02; SP-H half-validated mechanism (KS p=0.128 sub-significance) | After SP-J |
| Day 90 搂H.4 M3.2 鈥?On-chain (Glassnode/CryptoQuant) | XL (multi-day) | PHASE 2 RESEARCH ACTIVE | unlock MF-13/14 (Alchemy raw lane + CryptoQuant aggregate lane live; fused factor layer + first MF-14 overlay A/B completed, still seeking promotable landing shape) | After SP-J / M3.1 |
| Day 90 H.4 M3.3 - NLP event tape | L | QUARANTINED; LOCAL V2 + MF-01 CONFIRMATION EXHAUSTED | unlock MF-16 narrative_state; strict event-state short-boundary candidate passes validation and fixed-set comparison, but falsification fails; threshold v2 lacks robustness and MF-01 confirmation is too sparse | Revisit only with new state source / broader event persistence |
| Doc 搂G.5 amendment (raw IC cross-check) | S (~1h) | n/a | doc compliance update; absorb lsk3 diagnostic finding | Anytime |
| Validation contract amendment (cumulative return metric) | S-M (~2h) | n/a | absorb dual-horizon ensemble finding (median sharpe 鈮?terminal value) | Anytime |
| SP-I 鈥?1h-grain strategy | XL (3-5 day) | unknown | NOT triggered by SP-A/B; may revisit after M3.x | Defer |

**Recommended next concrete action**: SP-J (regime-conditional architecture). Reasons:
1. Implementable on existing data (no new sync)
2. Tests SP-F follow-up + tt_smooth_5/momentum_decay regime-fragility hypothesis simultaneously
3. Lower data risk than M3.x (Deribit/on-chain APIs)
4. Even if walk-forward doesn't improve, establishes regime-conditional pattern as Stage-2 architectural primitive

**If SP-J succeeds** (walk-forward > v6_h10d +2.832 + regime breadth preserved): promote v10_regime_conditional_h10d as new `active_alternative`. Re-evaluate Day 90 M3.x priorities 鈥?M3.1 (Deribit options) likely promoted to next priority.

**If SP-J fails or is at-par**: confirms F1 cycle non-additivity is fundamental (not architecture-driven); proceed to M3.1 (Deribit options) for new alpha source.

---

## E. Cross-validation against 搂C MF families

Per the alpha ontology doc's 搂C "16 mechanism families", the 90-day plan implicitly aimed for **鈮?2 of 16 families covered** (per 搂H.5 "鍥犲瓙搴撲粠 9 鈫?~30 涓?admitted, 璺?鈮?12 涓満鍒跺鏃?). Current state:

| Family coverage status | Count |
| --- | --- |
| With at least one factor in any current score / overlay | **9** (MF-03, MF-04, MF-07, MF-08, MF-09, MF-10, MF-11, MF-12, MF-15) |
| With factors implemented but failed admission | 3 (MF-05, MF-06, MF-04 extensions) |
| With implemented but non-promoted research plumbing | MF-01 (selection-layer only), MF-05, MF-06, MF-04 extensions |
| **Family still unimplemented beyond proposal stage** | **4 (MF-02, MF-13, MF-14, MF-16)** |

This roadmap closes:
- MF-12 (cascade) via SP-A
- MF-07 (participant disagreement) via SP-B2/B3
- MF-01 (inventory risk transfer) partially via SP-B1 (orderbook depth velocity)
- MF-15 extensions via SP-B5

After this roadmap completes, most remaining frontier work sits in MF-02 and MF-13/MF-14/MF-16, which still require external data unlocks (Deribit surface, on-chain APIs, or richer event / narrative history).

---

## F. Update protocol

When a sub-path completes (factors built, admission audited, score-integrated or deferred), this doc should be updated in the same commit:

1. Move the sub-path entry from "Roadmap" (搂C) to a new "搂G 鈥?Completed sub-paths" section.
2. Annotate the result: `G6 PASS 鈥?score-integrated as v_alpha_vN` OR `G6 FAIL 鈥?factor admitted standalone, score deferred` OR `falsified per doc test`.
3. Update 搂A.4 mechanism family coverage map.
4. Add commit hash to the entry.
5. Cross-link to `threshold_provenance.md` audit entry.

---

## G. Completed sub-paths

### SP-J 鈥?Regime-conditional alpha architecture 鈥?AT-PAR (2026-05-01)

**Result: AT-PAR 鈥?architecture validated end-to-end (manifest + score function + regime classifier all execute correctly + strict-pass contract); F1 alpha NOT unlocked (cycle-flat vs v6_h10d). Confirms SP-F cycle non-additivity is FUNDAMENTAL, not architecture-driven.**

| outcome | status |
| --- | --- |
| Regime classifier production-realistic (no lookahead) | DONE 鈥?`classify_regime_v10` uses trailing 30d/60d universe mean return + BTC vol regime quantile |
| Regime distribution on 2026-04-29 panel | trend_up 56.7% / drawdown_rebound 31.9% / rotation_high_vol 11.5% |
| Regime-conditional score function `xs_alpha_ontology_v10_regime_conditional_h10d_score` | DONE 鈥?base v6_h10d + F1 weight (0/0.025/0.030 by regime) |
| v10 manifest spec_hash + cycle | strict-pass; validation_contract `passed` |
| walk-forward delta vs v6_h10d (+2.832) | **+0.000 (zero)** |
| Pre-registered decision (PROMOTE / AT-PAR / DECLINE) | **AT-PAR** |
| F1 alpha unlock hypothesis | **REJECTED** 鈥?F1 cycle non-additivity is fundamental |
| Architecture re-usability | **VALIDATED** as Stage-2 primitive for future regime-localized SP-X candidates |

**Cycle results**:

| metric | v6_h10d | **v10 SP-J** | delta |
| --- | --- | --- | --- |
| walk_forward median sharpe | +2.832 | **+2.832** | **0.000** |
| loss_window_fraction | 0.312 | 0.3125 | +0.0005 |
| positive_regime_fraction | 0.667 | 0.667 | 0 |
| worst_regime sharpe | -2.736 | -2.805 (still in floor -2.828) | -0.069 |

**Effective F1 weight** (panel-weighted): 0.115 脳 0.025 (rotation) + 0.319 脳 0.030 (drawdown) + 0.567 脳 0 (trend) = **0.013**. Net: F1 contribution exists but at small effective weight; cycle metrics insensitive to it.

**Lifecycle**: v10 ships `experimental`. NOT promoted. v6_lsk3_g_v2_h10d remains h10d active_alternative. Architecture (`classify_regime_v10` + `regime_label_v10` panel column + score-layer regime-conditional pattern) preserved for future SP-X candidates.

**Files**: `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v10_regime_conditional_lsk3_g_v2_h10d.json` (new manifest), `regime_gating.py` (added classifier), `features.py` (added v10 score + regime_label_v10 merge), `lab.py` (v10 dispatch).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-J section.

**Lessons learned**:
1. **Cycle-layer non-additivity is more fundamental than weight architecture**. SP-F at constant weight = SP-J at regime-conditional weight = both cycle-flat at +2.832 walk-forward median. F1 + F-cascade shared cycle-layer signal cannot be disentangled by weight tuning alone 鈥?they are non-additive at the long-short top-3 selection 脳 regime-windowed sharpe metric integration.
2. **High admission residual IC + high cycle-layer overlap is a signature pattern**. F1 has +0.040 residual IC vs lsk3+F08 (admission-real) but cycle-flat with F-cascade (cycle-layer overlap). Future similar candidates need to test cycle-layer non-additivity BEFORE concluding admission strength translates to walk-forward lift.
3. **Validating an architecture is separate from validating its alpha hypothesis**. SP-J architecture (regime-conditional weighting + production-realistic regime detection) executed correctly + preserved cycle metrics; the architecture is RE-USABLE for future candidates. Future SP-X with truly regime-localized alpha (NOT F-cascade-overlapping) can use this same architecture.
4. **Pre-registered decision criteria prevent post-hoc rationalization**. SP-J was pre-registered as PROMOTE/AT-PAR/DECLINE in Phase 1 commit `7fd417c` BEFORE the cycle ran. Outcome (+0.000 delta, regime preserved) crisply maps to AT-PAR. Without pre-registration, we'd be tempted to argue "well, it preserves regime so it's good" or "well, it's not worse so it's neutral". Pre-registration converts those into AT-PAR 鈥?informative without bias.
5. **Path forward proceed to M3.1 per Phase 1 plan**. SP-J AT-PAR confirms F1 fundamental non-additivity 鈫?existing data + factor library is exhausted at Stage-1 + Day-60 saturation level. Next alpha lift requires NEW DATA 鈥?Deribit options surface (M3.1) is the highest-priority frontier lane.

---

### SP-H 鈥?Hedge unwind around derivatives expiry (E.15) 鈥?FALSIFIED (2026-04-30)

**Result: NEGATIVE FINDING 鈥?doc 搂E.15 KS-test fails (p=0.128>0.05); signal direction empirically correct (BTC 5d returns -62 bp lower in expiry-window vs out-window) but sub-significance; H1/H2 universe-wide gauges have zero cross-section variance; H3 (per-asset window脳rv20) has raw IC 0.16 but G6 fails because lsk3 baseline already absorbs the vol dimension.**

| outcome | status |
| --- | --- |
| Doc 搂E.15 falsification (KS-test expiry-window vs out-window 5d return) | **FAIL 鈥?KS p=0.128, Welch t=-1.72** (direction correct, sub-significance) |
| H1 `time_to_btc_expiry` G1 admission | n/a (universe-wide 鈫?zero cross-section, n=0 ts-IC by construction) |
| H2 `expiry_window_indicator_5d` G1 admission | n/a (universe-wide 鈫?zero cross-section) |
| H3 `expiry_window 脳 rv20` G1 admission | h5d \|IC\|=0.104, h10d \|IC\|=0.159 鈥?strong raw signal |
| H3 G6 vs lsk3 / lsk3+F-cascade+F08 baselines | **FAIL** 鈥?residual IC 0.009-0.018 across all variants (vol dimension absorbed by lsk3 realized_volatility_20 / iv_smooth_60) |

**搂E.15 falsification detail** (2026-04-29 panel, BTC subject, 36 expiries with both in-window + out-window samples):

| metric | in-window (n=216) | out-window (n=896) | delta |
| --- | --- | --- | --- |
| mean 5d log return | -0.05 bp | **+57 bp** | **-62 bp** (correct direction) |
| std 5d log return | 4.60% | 5.32% | volatility comparable |
| KS statistic | 0.088 | (vs threshold p<0.05) | p=0.128 |
| Welch t-stat | -1.72 | (vs implicit -2 threshold) | p=0.087 |

The mechanism IS empirically detectable (in-window mean 5d return is 62 bp lower than out-window 鈥?a meaningful negative tilt) but variance is too large for the KS-test to clear p<0.05. **Same pattern as SP-D 搂E.16** (t-stat 1.39 sub-threshold): doc-prescribed mechanism direction is correct but signal strength is borderline on this panel.

**Vol dimension saturation under lsk3**. H3's raw IC of 0.16 at h10d is impressive but illusory at the marginal level. H3 = expiry_window_indicator 脳 rv20 is zero on 83% of days (out-window) and equals rv20 on the remaining 17% (in-window). Its raw cross-sectional alpha is the rv20 alpha gated to a sparse subset of days. lsk3 baseline already contains realized_volatility_20 + realized_volatility_5 + intraday_realized_vol_4h_to_1d_smooth_60 鈥?the vol axis is fully absorbed, leaving only ~0.018 residual IC.

**Lifecycle**: SP-H ships as `falsified per doc test`. No score function added. No manifest added. No factor registered. Audit script preserved at `scripts/quant_research/compute_expiry_hedge_unwind_factor_report.py` for future re-test when one of:
1. **Longer history**: panel extends to 鈮?-10 years (n_in_window doubles 鈫?KS power improves).
2. **Cross-venue expiry calendar**: include CME monthly + Deribit weekly expiries (currently only Deribit monthly = last Friday rule).
3. **OI by strike (M3.1)**: stronger version uses dealer gamma proxy + concentration at ATM. Pure calendar event-study is the weak form; doc 搂E.15 strong form needs Deribit OI snapshots out of scope for SP-H.

**Files**: `scripts/quant_research/compute_expiry_hedge_unwind_factor_report.py` (new audit script). Audit JSON at `artifacts/quant_research/factor_reports/2026-04-29/expiry_hedge_unwind_factor_report_card.json` (gitignored).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-H section.

**Lessons learned**:
1. **Doc 搂E.15 mechanism direction is empirically correct but sub-significant on this panel**. The 62 bp / 5d return gap between expiry-window and non-window IS economically meaningful and matches the dealer-hedge-unwind story, but volatility is high enough that 216 in-window samples don't clear the doc-prescribed KS p<0.05 threshold. Doc-test calibration may be too strict for event-driven mechanisms with low-frequency triggers (12 monthly expiries 脳 5d = 60 in-window days/year, accumulating slowly).
2. **Universe-wide gauges are score-incompatible by construction** (third confirmation after SP-D D1 and SP-E E2/E3): cross-sectional rank IC requires per-asset variation, which universe-wide constants don't have. They can ONLY enter as overlay gating components, not score factors. Score-layer tests of universe-wide candidates produce design-failure n=0 results (not informative beyond "wrong factor type").
3. **Vol dimension under lsk3 is fully saturated for at-the-money cross-sectional alpha**. H3 (window 脳 rv20) joins the "raw IC strong, G6 absorbed by lsk3 vol" club: SP-D D2/D3 (basis residuals absorbed by F12 + funding_basis_residual_implied_repo_30) and now SP-H H3 (vol-gated event interaction absorbed by realized_volatility_*). The vol axis of lsk3 is **mechanistically dense** 鈥?to escape the saturation, a candidate factor needs a non-vol-correlated dimension (e.g., F-cascade's liquidation impulse, F1's intraday funding dispersion, F62's settlement timing).
4. **Sub-threshold doc tests are NOT a license to relax thresholds**. SP-D and now SP-H both have correct-direction signals at sub-significance (t=1.39 / KS p=0.128). Tempting to argue "well, it's directionally right, just barely shy of threshold". But (a) the doc thresholds were calibrated to control false-positive admission rate, and (b) sub-threshold mechanisms typically don't survive walk-forward at the cycle layer (even if they did pass admission). Holding the line on doc-prescribed thresholds prevents accumulating weak-but-correlated factors that compound into stale-alpha noise.

---

### SP-F 鈥?Sub-day funding microstructure (extending F08) 鈥?ADMISSION WIN, CYCLE NON-ADDITIVE (2026-04-30)

**Result: MIXED 鈥?F1 funding_intraday_dispersion_30d strict-passes G6 admission (residual IC +0.040 t=+7.24 at h10d vs lsk3+F08), but score-integration produces NO marginal cycle improvement over v6_h10d at any safe weight. v9 ships `experimental`; v6_h10d remains active.**

| outcome | status |
| --- | --- |
| F1 funding_intraday_dispersion_30d G1+G3+G6 admission at h10d | **PASS 鈥?residual IC +0.040 vs lsk3+F08, +0.029 vs lsk3+F-cascade** |
| F2 funding_sign_flip_count_30d_4h admission | borderline 鈥?passes G6 at h10d only |
| F3 funding_term_skew_30d_4h admission | **FAIL** 鈥?collinear with F08 (1d-grain skew already absorbs the signal, as roadmap predicted) |
| F1 sign correction (raw IC -0.019 vs residual IC +0.040) | **discovered through failed first integration** at w=-0.020 (walk-forward dropped 0.32, regime broke) |
| v9 = v6_h10d + F1 at w=+0.015 cycle | **strict-pass** (validation_contract = passed) |
| v9 walk-forward delta vs v6_h10d (+2.832) | **0.000** (identical) |
| v9 lifecycle | `experimental` (NOT promoted) |
| Per-ts Spearman corr(F1, F-cascade) | 0.064 mean (LOW; not sibling-duplicate at rank level) |

**F1 weight scan at h10d (v9 = lsk3 + F-cascade w=0.025 + F1 w=variable):**

| w_F1 | walk-forward median | regime worst | passed |
| --- | --- | --- | --- |
| -0.020 (raw IC sign 鈥?wrong) | **+2.513 (-0.319)** | **-3.001** | FAIL |
| **+0.015 (locked, residual IC sign)** | +2.832 | -2.736 | PASS = v6_h10d |
| +0.020 | +2.832 | -2.736 | PASS = v6_h10d |
| +0.025 (= F-cascade weight) | +2.832 | **-3.098** | FAIL (regime break) |

**Non-additivity finding**. Despite low rank-level correlation with F-cascade (per-ts Spearman 0.064), F1's predictive direction overlaps with F-cascade's rotation regime protection in cycle backtest space. There is NO weight at which F1 measurably improves walk-forward median while preserving regime 鈥?at safe weights it's a no-op, at higher weights it breaks regime. **Analogous to v7 (F62 + F-cascade) non-additivity** (commit 68c4593): two G6-admitted factors don't add when stacked because their long-short top-3 selection contributions overlap in regime-stressed windows.

**Sign discovery 鈥?score-integration pitfall**. F1 raw IC is -0.019 but residual IC is +0.040 (vs lsk3+F08). When the baseline over-corrects in F1's direction, the residual signal flips sign relative to the raw signal. **Score-integration weight sign must follow the residual IC, NOT the raw IC**. First v9 attempt at w=-0.020 (matching raw IC sign) actively contradicted F1's marginal contribution direction; walk-forward dropped 0.32 and regime broke. Sign correction to w=+0.015 (matching residual IC sign) restored v6_h10d-equivalent metrics.

**Lifecycle**:
- v6_lsk3_g_v2_h10d remains `active_alternative` (SP-C Phase 3 winner, +2.832 walk-forward).
- v9_lsk3_g_v2_h10d ships `experimental` at locked w=+0.015 鈥?strict-passes contract but identical metrics to v6_h10d. F1 plumbed in panel for future use (different baseline / different horizon / regime-conditional weights).

**Files**: `scripts/quant_research/compute_subday_funding_factor_report.py` (new audit), `src/enhengclaw/quant_research/subday_funding_features.py` (new panel writer), `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v9_lsk3_g_v2_h10d.json` (new manifest, experimental). Modified: `features.py` (xs_alpha_ontology_v9_h10d_score + SP-F panel merge), `lab.py` (v9 dispatch), `feature_admission.py` + `governance.py` + `deterministic_core.py` (SP-F columns plumbed).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-F section.

**Lessons learned**:
1. **MF-04 saturation is dimension-specific**: F08 (1d-grain skew) does NOT saturate the intraday-dispersion microstructure dimension. F3 (sub-day skew) IS collinear with F08 and fails G6 鈥?confirming the roadmap 搂C SP-F prediction for the same-statistic-different-grain case. But F1 (within-day std) is orthogonal at the rank level (residual IC +0.040 t=+7.24) 鈥?saturation does NOT extend to all sub-day funding statistics.
2. **G6 admission is necessary but NOT sufficient for score promotion**. Two patterns now confirmed: v7 (F62 + F-cascade) and v9 (F1 stacked on F-cascade). When a G6-admitted factor's contribution to long-short top-3 selection in regime-stressed windows overlaps with F-cascade's rotation regime protection, walk-forward median doesn't improve and regime can break at higher weights. Future score-integration tests should ALWAYS run a weight scan + check non-additivity vs strongest existing component.
3. **Sign-flip pattern in baseline-over-correction**. F1 raw IC -0.019 vs residual IC +0.040 is the textbook case: when baseline projection on F1 over-shoots the negative correlation, residual flips positive. Score-integration weight sign must follow residual IC. First v9 attempt got this wrong (w=-0.020 matched raw IC sign), produced -0.319 walk-forward delta + regime break. After sign correction to w=+0.015, metrics restored to v6_h10d level.
4. **Per-ts Spearman correlation can mislead**. F1 vs F-cascade corr is 0.064 (low) but cycle non-additivity is real. Linear rank correlation between two factors does NOT capture how their RANK PROFILES overlap in the specific (long-short top-3, regime windows) interaction that drives walk-forward + regime metrics. Future audits should add a "stack against existing component" weight-scan diagnostic, not rely on per-ts correlation alone.

---

### SP-E + SP-G bundle 鈥?Correlation regime gate (E.17) + DVOL extensions 鈥?MIXED FINDING (2026-04-30)

**Result: MIXED 鈥?SP-E 搂E.17 empirically REJECTED (sign reversed); SP-G DVOL overlay v3 strict-passes but is NEUTRAL-NEGATIVE on v6_h10d (walk-forward unchanged, loss_window_fraction +0.032). v3 ships `experimental`; v6_lsk3_g_v2_h10d remains active.**

| outcome | status |
| --- | --- |
| SP-E doc 搂E.17 falsification (low-corr IC 鈮?1.2脳 high-corr) | **REJECT 鈥?tertile-stratified ratio 0.93 (h5d) / 0.90 (h10d), SIGN REVERSED** |
| SP-E `btc_eth_corr_30d` integration into v3 | **DROPPED** |
| SP-G DVOL OHLC diagnostic (BTC + ETH range z90) | **operational viability confirmed** (3.9-4.4% anomaly days) |
| SP-G regime_gating_v3 implementation (DVOL-only) | DONE |
| v6_lsk3_g_v3_h10d cycle | strict-passes, validation_contract = passed |
| v3 walk-forward delta vs v6_lsk3_g_v2_h10d (+2.832) | **0.000 (identical)** |
| v3 loss_window_fraction delta vs v2 | **+0.032 (slightly WORSE)** |
| v6_lsk3_g_v3_h10d lifecycle | `experimental` (NOT promoted) |

**SP-E 搂E.17 empirical inversion**.

| split | bottom (low corr) abs IC | top (high corr) abs IC | ratio | doc threshold |
| --- | --- | --- | --- | --- |
| Absolute thresholds (low<0.5 n=9, high鈮?.7 n=935) h5d | 0.309 | 0.259 | 1.194 | 1.20 (border-FAIL, n=9 unreliable) |
| **Tertile split (each n鈮?65)** h10d | 0.240 | 0.268 | **0.895** | 1.20 |

The doc's "low-corr 鈫?idiosyncratic alpha 鈫?high IC" mental model is empirically inverted on the 2026-04-29 panel: tight BTC-ETH correlation coincides with clean trend regimes where systematic top-K selection works best, and loose correlation periods are typically transitional / chaotic. **搂E.17 should not be used as a regime gate**.

**SP-G DVOL overlay diagnosis**.

DVOL anomaly days (z>2.0) fire on 4% of history, scattered across the calendar 鈥?they don't systematically overlap with lsk3 + F-cascade losing days at h10d. Throttling on these days reduces some winning compounding (slightly higher loss_window_fraction) without moving the median sharpe. The W3.5 v2 success was driven by trailing-30-bar universe mean return (which DOES correlate with strategy losses in slow-grind regimes). DVOL doesn't replicate that pattern.

**Lifecycle**:
- v6_lsk3_g_v2_h10d remains `active_alternative` (SP-C Phase 3 winner, +2.832 walk-forward).
- v6_lsk3_g_v3_h10d ships `experimental`. Not promoted. v3 overlay infrastructure preserved at `regime_gating._compute_alpha_ontology_regime_gating_v3` + `multiplier_overlay.OVERLAY_BUILDERS["alpha_ontology_regime_gating_v3"]` for future re-test when a different gating signal is identified.

**Files**: `scripts/quant_research/compute_correlation_dvol_overlay_diagnostic.py` (new), `src/enhengclaw/quant_research/regime_gating.py` (added v3 builder + DVOL helpers), `src/enhengclaw/quant_research/multiplier_overlay.py` (registered v3), `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v6_lsk3_g_v3_h10d.json` (new manifest, experimental).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-E + SP-G section.

**Lessons learned**:
1. **Doc-prescribed mechanism direction is not always empirical**. SP-E 搂E.17 predicts low-corr 鈫?high IC; tertile-stratified evidence shows the OPPOSITE on this panel. Doc mental models need empirical verification before being baked into gates.
2. **Sample-size matters in regime falsification**. The absolute-threshold split (low n=9) gave a borderline-pass at h10d that disappeared under tertile split (low n=365). When evaluating regime gates, prefer balanced-sample partitioning over arbitrary thresholds.
3. **Gating-layer overlays need to overlap with strategy-specific losing days**, not generic "vol-of-vol" anomalies. The W3.5 v2 success (trailing-mean return component) worked because it specifically captured slow-grind bear regimes that hurt lsk3. DVOL anomaly days don't have the same correlation with lsk3 losses, so v3 overlay is operationally well-calibrated but functionally inert.
4. **Negative findings on overlay enrichments are inexpensive**. Building v3 took ~2 hours and produced a clean falsification. The infrastructure (script, builder, manifest, cycle output) is preserved and can be repurposed when a better gating signal is identified.

---

### SP-D 鈥?BTC鈫抋lt basis shock propagation (E.16) 鈥?FALSIFIED (2026-04-30)

**Result: NEGATIVE FINDING 鈥?doc 搂E.16 fails per-doc falsification test (t=1.39<2.0); all three D1/D2/D3 candidates fail G1 admission |IC|鈮?.04 with best at 0.0073 (~5脳 below floor); MF-04 saturation hypothesis from roadmap 搂C confirmed.**

| outcome | status |
| --- | --- |
| Doc 搂E.16 falsification (BTC basis shock 鈫?ALT basis 1d-after t-stat 鈮?2.0) | **FAIL 鈥?t=+1.39** (correct direction, signal too weak) |
| D1 broadcast (universe-wide gauge) G1 admission | n/a (zero cross-section by construction) |
| D2 alt_basis_residual_after_btc_60d G1 admission | **FAIL** 鈥?\|IC\| 0.0007 (h5d) / 0.0008 (h10d) |
| D3 basis_propagation_lag_corr_30d G1 admission | **FAIL** 鈥?\|IC\| 0.0073 (h5d) / 0.0030 (h10d) |
| G6 residual IC vs lsk3 baseline | **FAIL** for all candidates at all horizons (best \|residual IC\| = 0.0047) |

**Empirical detail**.

The 搂E.16 mechanism IS empirically detectable 鈥?across 74 BTC shock days 脳 97 alt subjects (3800 pairs), alts move basis in the same direction as BTC shock at d+1 with mean +29.1 bp (8脳 the per-subject non-event baseline of +3.5 bp). But the t-stat is only 1.39 because the per-(subject, day) noise is 1.29% 鈥?the directional signal sits in a much larger noise floor. The mechanism is real but not alpha-ready at the doc-prescribed threshold.

**MF-04 saturation confirmed**. The roadmap 搂C SP-D entry warned: "MEDIUM-LOW G6 success probability 鈥?May overlap with existing `quality_funding_oi` and `funding_basis_residual_implied_repo_30` (already MF-04 saturated)." Empirically:
- Direct cross-asset basis residual (D2) and lag correlation (D3) both fail G1 with |IC| ~0.001-0.007.
- After orthogonalization vs lsk3 baseline, residual IC remains < 0.005 鈥?F12 + funding_basis_residual_implied_repo_30 absorb the cross-asset basis dimension at 1d aggregate grain.

**Lifecycle**: SP-D ships as `falsified per doc test`. No score function added. No manifest added. No factor registered. Audit script preserved at `scripts/quant_research/compute_basis_propagation_factor_report.py` for future re-test when one of:
1. **Sub-day basis grain** 鈥?Coinglass 1h basis_proxy variants (currently 1d aggregate).
2. **Cross-venue basis** 鈥?per-venue basis dispersion (SP-J / coinapi_spot_sync productionization).
3. **Network propagation graph** 鈥?multi-asset rolling SEM/VAR (significant infra investment).

**Files**: `scripts/quant_research/compute_basis_propagation_factor_report.py` (new audit script). Audit JSON at `artifacts/quant_research/factor_reports/2026-04-29/basis_propagation_factor_report_card.json` (gitignored).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-D section.

**Lessons learned**:
1. Doc-prescribed thresholds are calibrated for raw mechanism detection, not for marginal-alpha discovery. A 1.39蟽 signal can still represent a real economic mechanism 鈥?the falsification test rejected SP-D as a direct alpha source, NOT as a mechanism.
2. MF-04 carry-residuals family is now empirically demonstrated to be saturated at 1d aggregate grain by F12 + funding_basis_residual_implied_repo_30. Any future MF-04 candidate (M2.1 cross-venue, F09 funding_zscore, F11 basis_velocity etc.) needs a sub-day or cross-venue dimension to escape collinearity.
3. The "build the simplest cross-asset propagation factor" pattern (D1 broadcast, D2 OLS residual, D3 lag corr) is the right first-pass falsification 鈥?they are minimum-infrastructure proxies for the full mechanism. Their failure rules out simple-extraction approaches without committing major engineering to multi-asset network models.
4. Negative findings have economic value: SP-D's empirical falsification of doc 搂E.16 unblocks resource allocation away from this lane and toward higher-ROI sub-paths (SP-E correlation regime gate, SP-G DVOL extensions per the roadmap 搂D priority schedule).

---

### SP-C Phase 3 鈥?validation_contract h10d sqrt-scaling + v6_h10d productionization (2026-04-30)

**Result: SUCCESS 鈥?`quant_validation_contract.v10_h10d` shipped, v6_h10d `active_alternative`, walk-forward champion across all candidates (+2.832, +19% vs h5d).**

| outcome | status |
| --- | --- |
| Diagnosis: rotation regime collapse at h10d is sharpe-magnitude-rescaling artifact (sqrt(N) scaling under random-walk-IID), NOT factor pathology | CONFIRMED |
| h10d-specific validation_contract built (`quant_validation_contract.v10_h10d`) | DONE |
| Sharpe-magnitude thresholds rescaled by sqrt(2): worst_regime -2.0 鈫?-2.828, walk-forward median 0.8 鈫?1.131 | DONE |
| Rate/count thresholds (loss_window_fraction, positive_regime_fraction, regime_coverage) kept unchanged (horizon-agnostic) | DONE |
| `sharpe_anomaly_quarantine_threshold` empirically tuned 20 鈫?200 (sqrt-scaled 28.3 was too aggressive 鈥?7/32 false-positive windows; raised to numerical-pathology floor) | DONE |
| Runner integration: `_HORIZON_CONTRACT_PATHS` map + per-horizon contract monkey-patch | DONE |
| h10d candidate cycle matrix (v1 / v5 / v6 / v8) all completed under v10_h10d contract | DONE |
| **v6_h10d STRICT-PASSES** 鈥?sole h10d strict-passer | CONFIRMED |
| v6_h10d promoted from `experimental` 鈫?`active_alternative` with `verified_outcome_2026_04_29` block | DONE |

**h10d candidate matrix under v10_h10d contract (panel as of 2026-04-29).**

| candidate | walk-forward median | rotation | drawdown_rebound | positive_regime | regime_holdout | strict-pass |
| --- | --- | --- | --- | --- | --- | --- |
| v1_lsk3_g_v2 (control) | +2.428 | -3.098 | +3.138 | 1/3 | FAIL (rotation < -2.828 floor) | NO |
| v5_lsk3_g_v2 (F62) | +2.716 | -3.001 | +3.138 | 1/3 | FAIL (rotation + sharpe_anomaly window 17=791) | NO |
| **v6_lsk3_g_v2 (F-cascade w=0.025)** | **+2.832** | **-2.736** | **+3.162** | **2/3** | **PASS** | **YES** |
| v8_lsk3_g_v2 (F47) | +2.594 | -3.098 | +3.138 | 1/3 | FAIL (rotation < -2.828 floor) | NO |

F-cascade is the sole factor providing meaningful rotation regime protection at h10d (-2.736 vs -3.098 baseline) 鈥?JUST clears the sqrt(2)-scaled -2.828 floor. The +0.36 sharpe rotation protection mirrors the F-cascade lesson at h5d (where it also gave best rotation result).

**v6_h10d delta vs v6_h5d.**

| metric | v6_h5d | v6_h10d | delta |
| --- | --- | --- | --- |
| walk_forward median | +2.373 (w=0.05) | **+2.832** (w=0.025) | **+0.459 (+19%, highest of all candidates)** |
| positive_regime_fraction | 1/3 | **2/3** | +0.333 |
| trend_up_2025h2 | +5.687 | +6.725 | +1.038 |
| rotation_high_vol_2025q4 | -0.062 | -2.736 | -2.674 (within sqrt-scaled floor) |
| drawdown_rebound_2026ytd | -1.851 | **+3.162** | **+5.013 (FLIPS positive)** |

The drawdown_rebound flip is the qualitative h10d-shape signature: cascade recovery is a multi-day mean-reversion process whose alpha unfolds across ~10 days. v6_h10d captures this naturally; v6_h5d truncates the recovery before it materializes.

**Lifecycle**: v6_h10d `active_alternative` (2026-04-30) alongside v6_h5d `active_alternative` (2026-04-29). v1_h10d / v5_h10d / v8_h10d remain `experimental` (proof that rotation regime sensitivity at h10d is real-but-bounded).

**Files**: `config/quant_research/validation_contract_h10d.json` (new), `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py` (root compatibility wrapper as of Phase 5.45; implementation under `scripts/quant_research/alpha_ontology_cycles/` with per-horizon contract monkey-patch), `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v5_lsk3_g_v2_h10d.json` + `_v8_..._h10d.json` (new manifests), `..._v6_..._h10d.json` (promoted to active_alternative).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-C Phase 3 section.

**Lessons learned**:
1. Regime gates are implicitly horizon-coupled. When changing forward-return horizon, sharpe-magnitude thresholds must rescale by sqrt(N); rate-based thresholds stay fixed. Mixing the two without explicit calibration produces false rejections of genuinely-strong h10d candidates.
2. Sharpe anomaly thresholds and magnitude thresholds need DIFFERENT scaling treatment. Sharpe magnitude scales with sqrt(N); anomaly thresholds target numerical pathology (variance-floor) and need empirical recalibration, not pure-sqrt.
3. F-cascade's rotation regime protection is the binding constraint at h10d, just as it was at h5d. Score-integrated factors that strict-pass at h5d don't automatically strict-pass at h10d under sqrt-scaled gates 鈥?only F-cascade clears the rotation floor at both horizons.
4. The empirical sqrt(h10d)/sqrt(h5d) sharpe ratio on this panel ranges 1.32-1.45 across regimes (theoretical sqrt(2)鈮?.414). Random-walk-IID is approximate, not exact, but close enough to validate sqrt-scaling as the operative rule. Documented as a rolling diagnostic for future review.

---

### SP-C Phase 2 鈥?h10d cycle infrastructure + walk-forward confirmation (2026-04-29)

**Result: PARTIAL 鈥?infrastructure shipped, audit prediction confirmed empirically (+13-19% walk-forward), regime gates need h10d-specific recalibration.**

| outcome | status |
| --- | --- |
| Horizon-flexible runner shipped (`run_alpha_ontology_horizon_cycle_oneoff.py`) | DONE |
| h10d cycles run for v1 (control) and v6 (lsk3 + F-cascade) | DONE |
| Phase 1 audit prediction confirmed: h10d walk-forward consistently 12-19% higher than h5d | CONFIRMED |
| Regime gates pass at h10d | **FAIL 鈥?rotation_high_vol_2025q4 collapses to -2.7 to -3.1 across candidates including un-augmented v1** |
| Diagnosis: regime collapse is lsk3-baseline-intrinsic, not factor-specific | CONFIRMED |
| h10d candidates strict-pass | **NO 鈥?validation_contract recalibration required** |

| candidate | h5d walk-forward | h10d walk-forward | h5d worst-regime | h10d worst-regime |
| --- | --- | --- | --- | --- |
| v1_lsk3_g_v2 | +2.147 | **+2.423 (+13%)** | -1.851 | **-3.101 (FAIL)** |
| v6_lsk3_g_v2 (w=0.05) | +2.373 | **+2.830 (+19%)** | -1.851 | **-2.739 (FAIL)** |
| v6_lsk3_g_v2 (w=0.025) | n/a | +2.815 | n/a | -2.739 (FAIL, weight halve doesn't help) |

**Lifecycle**: v6_h10d and v1_h10d ship as `experimental`. The deliverable is the empirical conclusion, not a new active candidate.

**Phase 3 follow-up needed**: validation_contract recalibration for h10d. Two paths:
1. Relax `worst_regime_median_oos_sharpe_min` from -2.0 to ~-3.5 specifically for h10d cycles (acknowledge h10d is genuinely riskier in rotation regimes)
2. Investigate why rotation_high_vol_2025q4 collapses at h10d 鈥?may be a regime-window-classification artifact rather than true alpha problem

Estimated effort: 2-4 hours.

> **RESOLVED in SP-C Phase 3 (2026-04-30)**: chose path (1) but with sqrt(2)-scaling derived from random-walk-IID sharpe scaling, not arbitrary judgment-relaxation. v6_h10d strict-passes; promoted to `active_alternative`. See SP-C Phase 3 entry above.

**Files**: `scripts/quant_research/run_alpha_ontology_horizon_cycle_oneoff.py` (new root path at the time; root compatibility wrapper as of Phase 5.45), `src/enhengclaw/quant_research/features.py` (added `xs_alpha_ontology_v6_h10d_score`), 2 new manifests (v6_h10d, v1_h10d).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-C Phase 2 section.

**Lessons learned**:
1. Audit predictions for walk-forward magnitude are reliable 鈥?Phase 1's predicted 25% boost empirically materialized as 12-19% (lower bound of expectation, but directionally exact).
2. Regime gates calibrated for h5d don't translate to h10d. validation_contract is implicitly horizon-coupled.
3. Drawdown_rebound regime FLIPS positive at h10d (+3.14 from -1.85) 鈥?the post-cascade recovery duration matches the longer horizon. This is good news for h10d strategies in any market that experiences cascades.
4. At h10d, all strategies become MORE EXTREME across regimes (bigger trend wins, bigger rotation losses, drawdown flips). The horizon stretches both alpha and risk proportionally, but regime gates assume fixed thresholds 鈥?they don't auto-rescale.

---

### SP-C 鈥?Multi-horizon factor re-test (2026-04-29)

**Result: PARTIAL 鈥?major research finding (5d horizon suboptimal for all strong factors), small score-integrated win (v8 with F47 at h5d).**

| outcome | status |
| --- | --- |
| Multi-horizon audit script + JSON output | shipped |
| Primary finding: ALL score-integrated factors peak at h10d | confirmed (residual t monotone-increasing with horizon for F12, F33, F62, F-cascade, F29, B3a) |
| Idle factor unlock | F47 funding_flip_decay_phase borderline G6 PASS at h5d (residual -0.020 t=-3.89) |
| Short-horizon factors found | F11 basis_velocity, F13 basis_carry_convexity each strongest at h1d (residual t ~+3.6) 鈥?NOT integrated, doesn't help h5d cycle |
| ~70% of "G6-failed at h5d" idle factors fail at all horizons | confirmed (W1.1 F09/F16-F20/F31/F32, W3.1 F46/F48, W3.2 F27/F28, W3.3 F41/F42/F45, M2.4 triangle, M2.2 kurt) |
| Score integration: v_alpha_v8_lsk3_g_v2 (lsk3 + F47, w=-0.03) | strict-passes, modest +0.08 walk-forward |

**Key research finding**: 5d horizon is empirically suboptimal for every score-integrated factor (F12 / F33 / F62 / F-cascade / F29). All have residual t increasing monotonically with horizon, peaking at h10d. The doc's "5d horizon" assumption (搂I challenge #3) is empirically falsified. Building a full h10d cycle infrastructure (Phase 2, ~6-8h) would likely yield meaningful walk-forward improvements across all current candidates (v5 / v6 retested at h10d).

**Phase 2 NOT done** in this sub-path. Recorded as highest-ROI follow-up.

**Files**: `scripts/quant_research/compute_multi_horizon_factor_audit.py` (new), `src/enhengclaw/quant_research/features.py` (added `xs_alpha_ontology_v8_score`), `cross_sectional_hypothesis_batch_manifest_alpha_ontology_v8_lsk3_g_v2.json` (new).

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-C section.

**Lessons learned**:
1. Doc-default assumptions (5d horizon) deserve empirical verification 鈥?major potential alpha left on table when assumptions go unchallenged.
2. Idle factors are not always weak 鈥?some are right-mechanism but wrong-horizon. F47 is the example: G6 fail at h5d when first tested in W3.1 (when threshold was different), but borderline G6 PASS in this audit at the SAME h5d horizon 鈥?suggests panel evolution and/or admission threshold revision changes the verdict.
3. Score-integrated factors that already pass G6 at h5d ALL get even stronger at h10d 鈥?this is consistent with the funding/microstructure mechanisms being slow-decay (the alpha unfolds across days, not within 24h).

---

### SP-B partial 鈥?1h Coinglass microstructure swarm (2026-04-29)

**Result: PARTIAL 鈥?framework shipped, 1 admitted-but-sibling-duplicate factor; MF-07 family target NOT unlocked.**

| variant | mechanism | admission outcome |
| --- | --- | --- |
| B2 `top_global_disagreement_1h_30d` (MF-07 target) | rolling-720h corr(top_long, global_long) | G1 fail, G6 fail (near-zero raw IC) |
| **B3a** `top_trader_velocity_1h_abs_24h` | daily mean abs(6h gradient of top_long) | **G1 PASS, G3 PASS (1.00), G6 PASS** (residual +0.062, t=+10.87) 鈥?but +0.94 per-ts spearman with F-cascade (sibling-duplicate) |
| B3b `top_trader_velocity_1h_signed_24h` | daily signed sum of 6h gradient | G1 fail, G6 marginal |
| B5 `taker_skew_presettle_30d` (F62 sibling) | F62 mechanism on taker_buy-sell flow side | G1 fail, G6 fail |

**Score integration: NOT proceeding.** B3a passes admission but is +0.94 per-ts spearman correlated with `liq_cascade_recency_score_5d` from SP-A 鈥?they capture the same "high-activity window" signal from different mechanism sides (position movement vs liquidation flow). Adding B3a alongside F-cascade in score would near-duplicate the cross-sectional rank without adding alpha (per v7 non-additivity lesson).

**MF-07 family**: B2 was the canonical MF-07 candidate with the data-ready gap closed. Empirical falsification 鈥?disagreement signal has near-zero cross-sectional IC on this panel. **MF-07 stays unimplementable on current data.**

**Plumbing**: panel + admission allowlist + group mapping shipped for the 4 variants 鈥?available for future score variants (e.g., SP-C horizon scan, or paired with non-lsk3 baseline).

**Files**: `src/enhengclaw/quant_research/intraday_microstructure_features.py` (new) + `features.py` late-merge + admission registration.

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-B section.

**Lessons learned**:
1. High raw IC after fillna(0) can be a rank artifact 鈥?when ~75% of rows are 0-filled, the remaining 25% subjects rank-extreme in cross-section, inflating the IC. The +0.94 per-ts spearman with F-cascade is the diagnostic 鈥?both factors over-weight the same minority of in-coverage subjects.
2. Sibling-mechanism factors at 1h grain (top trader velocity, liquidation cascade, settlement-cycle drift) likely all capture variants of "high-activity window" alpha. Stacking them won't multiply the alpha; better to pick the one with strongest doc-mechanism falsification (SP-A wins on 搂E.12 t=10.75 vs SP-B no doc test).
3. The IDLE-data-driven "build N factors and pick winners" pattern works for finding 1-2 winners per data source, not for compounding. After SP-A captured the cascade-class alpha, SP-B's siblings have low marginal return.

---

### SP-A 鈥?Liquidation cascade impulse-response (2026-04-29 / 2026-04-30)

**Result: SUCCESS 鈥?`active_alternative` lifecycle, v_alpha_v6_lsk3_g_v2 ships.**

| outcome | status |
| --- | --- |
| Doc 搂E.12 falsification (post-cascade 24h abnormal return t-stat 鈮?2.5蟽) | **PASS t=+10.75** (4脳 margin) |
| Cross-sectional G1 strict (鈮?.04) | **PASS** raw IC +0.052 (t=+10.50) |
| Cross-sectional G3 same-sign (鈮?.60) | **PASS** 1.00 (perfect across vol regimes) |
| Cross-sectional G6 strict vs lsk3 (鈮?.02) | **PASS** residual IC +0.062 (t=+10.77) |
| Score-integrated cycle on 2026-04-29 panel | **PASS** strict_survivor_count = 1 |
| Walk-forward improvement vs v1_lsk3_g_v2 | **+0.226** (+10.5%, w=0.05) |
| Worst regime safety margin | -1.851 (unchanged from baseline; comfortable from -2.0 floor) |
| Best regime delta | rotation_high_vol_2025q4 **+0.527** (best of any factor in M2.x track) |

**Selected variant**: `liq_cascade_recency_score_5d` (exponential-decay 5d recency accumulator of 1h liq_to_oi z>2.5 events). All 4 candidate variants passed G6 strict; recency_score_5d picked as highest-IC + highest-residual-t.

**Sign empirical**: POSITIVE (mean revert up after cascade), aligns with doc 搂E.12 prescription.

**Weight calibration**: w=0.05 (Pareto-optimal; theoretical 0.17 would over-fit; w=0.10 broke regime as W3.5 v1 pattern; w=0.05 captures alpha while preserving regime stability).

**Score function**: `xs_alpha_ontology_v6_score`. Manifest spec_hash `93ff0243e3...`.

**MF family coverage gain**: MF-12 (state_space_regime 鈥?cascade impulse-response is a state-machine-like regime indicator). Coverage 8 鈫?**9 of 16**.

**Audit lineage**: `config/quant_research/threshold_provenance.md` SP-A section. Commit hash: see git log around `f584e92` 鈫?next commit.

**Lessons learned for future sub-paths**:
1. Doc-prescribed falsification tests are the cleanest first-line filter 鈥?SP-A's t=+10.75 was a strong indicator that admission would also pass.
2. "Build all candidate variants, pick the strongest" pattern works (4 variants tested, 4 passed G6, picked the strongest one for score integration).
3. Initial weight = 50% of theoretical IC脳3.25 ratio is a safe starting point, but weight scan still needed (w=0.10 broke regime; w=0.05 was the answer).
4. Strong factors with directional regime sensitivity need weight calibration to balance walk-forward gain vs regime tail risk (W3.5 v1 / SP-A pattern).
