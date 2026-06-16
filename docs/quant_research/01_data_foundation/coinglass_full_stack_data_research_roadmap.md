# CoinGlass Full-Stack Data + Research Roadmap

`Snapshot date: 2026-05-04`
`Owner: quant_research_maintainer`
`Status: priority roadmap / R-1 through R-8 gates updated 2026-05-09; ETF/on-chain sidecars filled; foundation catalog linked`

This roadmap corrects the earlier narrow interpretation of CoinGlass as only a
derivatives-sidecar provider. The current verified view is broader: CoinGlass
can be used as a local full-stack market-data source for spot, futures,
microstructure, ETF, selected on-chain flows, options aggregates, and vendor
indicators.

The roadmap has two layers:

1. **Data layer**: fill CoinGlass-related local data in a strict, ordered,
   provenance-preserving way.
2. **Research layer**: restart prior conclusions that were data-limited or
   frequency-limited, then update the next-alpha priority queue under the new
   data surface.

The governing principle is fail-closed: no research conclusion is promoted only
because a richer provider exists. Every re-opened lane must pass the existing
validation, falsification, cost, holdout, and capacity contracts.

Default data catalog:

- `docs/quant_research/01_data_foundation/coinglass_full_stack_foundation_sync.md`
- JSON catalog:
  `artifacts/quant_research/coinglass/coinglass_full_stack_foundation_sync.json`

Before opening any new CoinGlass-backed research lane, check the catalog first.
If a required entry is missing or marked `quarantined`, refresh
`scripts/quant_research/sync_coinglass_full_stack_foundation.py` before adding
lane-specific one-off data pulls.

---

## 1. Current verified CoinGlass capability

### 1.1 Official API surface checked

| area | relevant endpoint family | research value | immediate interpretation |
| --- | --- | --- | --- |
| Spot OHLCV | `/api/spot/price/history` | 1h spot history with OHLC and locally observed `volume_usd` | directly useful for the 1h spot-history blocker |
| Spot taker / CVD / footprint | `/api/spot/taker-buy-sell-volume/history`, `/api/spot/cvd/history`, `/api/spot/volume/footprint-history` | spot flow and order-flow state | useful after core OHLCV; some endpoints may have shorter history |
| Futures price / OI / funding / taker | `/api/futures/price/history`, `/api/futures/open-interest/history`, `/api/futures/funding-rate/history`, taker history | existing derivatives lane plus repair source | already partly implemented; needs USD-OI fallback and broader provenance |
| Liquidation / orderbook / participant state | existing `coinglass_extended` family | MF-01, MF-06, MF-07, MF-12 | already local but underused; re-test only after coverage audit |
| ETF | `/api/etf/bitcoin/*`, `/api/etf/ethereum/*` | ETF flow, net assets, premium/discount, price | new market-state layer for MF-12 / MF-15 / M3.2 |
| On-chain | `/api/exchange/assets`, `/api/exchange/chain/tx/list`, `/api/chain/v2/whale-transfer` | CEX wallet state, ERC-20 exchange transfers, whale transfers | useful supplement to CryptoQuant/Alchemy, not a full Glassnode substitute |
| Options | `/api/option/exchange-oi-history`, `/api/option/exchange-vol-history`, `/api/option/max-pain`, `/api/index/option-vs-futures-oi-ratio` | market-level options regime and expiry pressure | can accelerate an options-regime slice; not yet enough for full dealer-gamma topology |
| Indicators | `/api/index/pi-cycle-indicator`, `/api/bull-market-peak-indicator`, futures indicator endpoints | diagnostics / regime context | quarantine from score promotion unless recomputed PIT-safe locally |

### 1.2 Local smoke result on 2026-05-04

The current local `CoinglassAPI` credential resolved successfully and returned
data for spot, ETF, on-chain, and options endpoints. Do not write the key to
repo. The observed account level was `PROFESSIONAL`; the local smoke indicated
the credential was not expired at the time of testing.

Important observed facts:

- `spot/price/history` returned `open`, `high`, `low`, `close`, `time`,
  `volume_usd`.
- For Binance spot 1h, major symbols such as `ENAUSDT`, `FETUSDT`, `WLDUSDT`
  were available at least 720 days back.
- `PENGUUSDT`, `TRUMPUSDT`, `XPLUSDT`, `ASTERUSDT`, and `KITEUSDT` had enough
  observed spot history to satisfy a 180-day gate.
- `NIGHTUSDT` did not have enough observed spot history; no provider should
  fabricate pre-listing history.
- BTC ETF flows, IBIT ETF history/net-assets, ETH ETF flows, exchange wallet
  assets, whale transfers, ERC-20 exchange transfers, option OI, and option
  volume all returned structured payloads.

### 1.3 Source anchors for future verification

Use these official CoinGlass pages when rechecking this roadmap:

- Pricing / historical range:
  `https://www.coinglass.com/pricing`
- Spot OHLC history:
  `https://docs.coinglass.com/reference/spot-price-ohlc-history`
- Spot taker buy/sell history:
  `https://docs.coinglass.com/reference/spot-taker-buysell-ratio-history`
- ETF flow history:
  `https://docs.coinglass.com/reference/etf-flows-history`
- ETF history:
  `https://docs.coinglass.com/reference/etf-history`
- Ethereum ETF flow history:
  `https://docs.coinglass.com/reference/ethereum-etf-flows-history`
- Exchange assets:
  `https://docs.coinglass.com/reference/exchange-assets`
- Exchange on-chain transfers:
  `https://docs.coinglass.com/reference/exchange-onchain-transfers`
- Whale transfer:
  `https://docs.coinglass.com/reference/whale-transfer`
- Option exchange OI history:
  `https://docs.coinglass.com/reference/exchange-open-interest-history`
- Option exchange volume history:
  `https://docs.coinglass.com/reference/exchange-volume-history`
- Option max pain:
  `https://docs.coinglass.com/reference/option-max-pain`

---

## 2. Data-layer roadmap

### CG-0. Capability matrix and contracts

**Goal**: make the provider surface explicit before backfilling large local
caches.

Deliverables:

- `artifacts/quant_research/provider_smoke/coinglass_capability_matrix.json`
- `artifacts/quant_research/provider_smoke/coinglass_endpoint_samples.json`
- a small no-secret report with:
  - endpoint path
  - plan availability
  - observed response keys
  - native timestamp field and timezone
  - history window observed
  - pagination model
  - max result limit
  - PIT risk notes

Acceptance gates:

- no secret material in artifacts
- all timestamps normalized to UTC
- every endpoint classified as one of:
  - `core_research_input`
  - `sidecar_context`
  - `diagnostic_only`
  - `blocked_or_short_history`
- at least one smoke request for each endpoint family used in this roadmap

Priority: **P0**.
Reason: prevents expensive backfills from writing incompatible schemas.

2026-05-07 foundation-catalog update:

- total foundation entrypoint:
  `scripts/quant_research/sync_coinglass_full_stack_foundation.py`
- default human-readable catalog:
  `docs/quant_research/01_data_foundation/coinglass_full_stack_foundation_sync.md`
- default machine-readable catalog:
  `artifacts/quant_research/coinglass/coinglass_full_stack_foundation_sync.json`
- current decision:
  `foundation_catalog_ready = True`; `alpha_rerun_allowed = False`
- use rule:
  this catalog is now the first stop for roadmap execution. It answers
  availability, PIT/quarantine status, and local artifact paths; it does not
  replace strict falsification.

### CG-1. Spot 1h OHLCV full backfill

**Goal**: solve the immediate 1h spot-history blocker and make CoinGlass a
first-class spot source alongside Binance and CoinAPI.

Proposed raw cache:

```text
%LOCALAPPDATA%\EnhengClaw\market_history\coinglass_spot_ohlcv\spot\<SYMBOL>\<INTERVAL>\<YYYY-MM>.csv.gz
```

Proposed normalized schema should match the existing OHLCV contract where
possible:

```text
exchange, market_type, symbol, interval, open_time_ms, close_time_ms,
open, high, low, close, volume, quote_volume, trade_count,
taker_buy_base_volume, taker_buy_quote_volume, source
```

Mapping:

- `exchange = Binance` for the first implementation.
- `market_type = spot`.
- `quote_volume = volume_usd`.
- `volume`, `trade_count`, `taker_buy_*` remain null unless a confirmed
  CoinGlass endpoint supplies equivalent fields.
- `source = coinglass_spot_price_history`.

Backfill scope:

1. all subjects in the current cross-sectional research universe;
2. current strategy-scope symbols first (`top_liquidity`, `mid_liquidity`,
   executable perp);
3. then long-tail/full 99-symbol panel;
4. intervals: `1h` first, then `1d` only if needed for concordance and
   backfill speed.

Validation gates:

- no duplicate `(symbol, interval, open_time_ms)` rows
- monotonic hourly spine per symbol
- `>= 95%` hourly completeness over the observable post-listing window
- overlap close-price concordance against Binance/CoinAPI where available
- volume sanity: non-negative `quote_volume`; missing volume is explicit null,
  not zero-filled
- listing-age aware coverage: new symbols can fail history length honestly, but
  old symbols must not fail due to provider pagination

Research gates unlocked:

- rebuild `cross-sectional-intraday-1h`
- re-run minimum executable history coverage
- restart the true 1h strategy feasibility question

Priority: **P0 highest**.
Reason: it attacks the current blocker directly and is the cheapest unlock.

### CG-2. Futures core repair and OI-value provenance

**Goal**: repair false coverage failures caused by short `unit=usd` OI history
when `unit=coin` OI and perp price are available.

Current issue:

- CoinGlass futures OI in `unit=coin` can be much longer than `unit=usd`.
- The current dataset gate depends on `open_interest_value > 0`.
- For symbols such as `ASTERUSDT`, `TRUMPUSDT`, `FFUSDT`, `KAIAUSDT`, and
  `SKYUSDT`, `open_interest` and `perp_close` were observed far enough back,
  while `open_interest_value` was much shorter.

Implementation:

```text
if open_interest_value is null/zero
and open_interest > 0
and perp_close > 0:
    open_interest_value = open_interest * perp_close
    open_interest_value_source = derived_coin_oi_x_perp_close
else:
    open_interest_value_source = coinglass_usd_oi
```

Acceptance gates:

- derived value count is manifest-visible
- derived-vs-native overlap error is measured on rows where both exist
- no derived value is used without a provenance flag
- research reports can filter native-only vs derived-inclusive variants

Additional repair:

- add executable-perp alias handling for Binance multiplier contracts such as
  `1000PEPEUSDT`, `1000SHIBUSDT`, `1000BONKUSDT`, `1000FLOKIUSDT`,
  `1000LUNCUSDT`
- record multiplier mapping explicitly so price/volume/OI units are not mixed

Priority: **P0** after CG-1.
Reason: likely moves full-panel coverage over the current minimum threshold and
prevents false negatives in data eligibility.

### CG-3. Extended 1h microstructure refresh

**Goal**: bring existing Coinglass extended data into a single audited
microstructure panel.

Inputs:

- liquidation history
- orderbook ask/bid history
- taker buy/sell volume
- global account long/short ratio
- top-trader position ratio
- spot taker/CVD where available
- spot footprint only as short-history sidecar unless history proves sufficient

Derived panels:

```text
artifacts/quant_research/coinglass/microstructure_panel_1h.csv.gz
artifacts/quant_research/coinglass/microstructure_panel_1d.csv.gz
```

Core fields:

- liquidation imbalance and intensity
- orderbook imbalance and depth fragility
- taker imbalance / CVD proxy
- top-vs-global disagreement
- participant-pivot timing
- flow-vs-price absorption

Acceptance gates:

- per-column coverage table by symbol, liquidity bucket, and date
- raw 1h to 1d aggregation method fixed and documented
- no promotion from columns with sparse activation unless the landing shape is
  explicitly a sparse event rule

Priority: **P1**.
Reason: this is not the first data blocker, but it is the fastest route to
better MF-01/MF-06/MF-07 re-tests once the base panel is clean.

### CG-4. ETF daily state sidecar

**Goal**: add ETF flow and ETF balance-sheet state as a market-wide regime
sidecar.

Inputs:

- BTC ETF flow history
- ETH ETF flow history
- ETF net assets
- premium/discount
- ETF price history where useful

Proposed output:

```text
artifacts/quant_research/coinglass/etf_flow_panel_1d.csv.gz
```

Core features:

- `btc_etf_flow_usd_1d`
- `btc_etf_flow_usd_3d_sum`
- `btc_etf_flow_usd_10d_sum`
- `btc_etf_flow_z_60d`
- `eth_etf_flow_usd_1d`
- `etf_flow_regime_label`
- `etf_premium_discount_z`
- `days_since_large_etf_inflow`
- `days_since_large_etf_outflow`

PIT rule:

- ETF flow should be lagged at least one decision bar unless the exact
  publication timestamp is recorded.
- Default daily research should use `t-1` ETF flow for `t` decision.

Priority: **P1**.
Reason: directly supports MF-12 state persistence, MF-15 settlement/rebalance
friction, and M3.2 boundary activation without contaminating symbol-level
features.

2026-05-07 execution update:

- PIT ETF sidecar exists at
  `artifacts/quant_research/coinglass/etf_daily_state_1d.csv.gz`.
- The live sync wrote `598` decision-date rows from `2024-01-12` to
  `2026-05-07`.
- Inputs included BTC ETF flow, ETH ETF flow, and IBIT history/net-assets.
- The sidecar uses `source_date + 1 day`; it is data-layer context only until
  wired into a pre-registered transition and falsification pass.

### CG-5. On-chain exchange / whale sidecar

**Goal**: add a CoinGlass on-chain supplement to existing CryptoQuant, Alchemy,
and TronScan M3.2 work.

Inputs:

- exchange wallet assets
- ERC-20 exchange chain transfer list
- whale transfer feed

Proposed outputs:

```text
artifacts/quant_research/coinglass/exchange_assets_snapshot.csv.gz
artifacts/quant_research/coinglass/exchange_transfers_erc20_1d.csv.gz
artifacts/quant_research/coinglass/whale_transfers_1d.csv.gz
```

Core features:

- CEX stablecoin inflow / outflow intensity
- whale transfer count / notional by chain and asset
- exchange asset balance shock
- ETF-flow plus CEX-flow concordance
- stablecoin impulse confirmation for M3.2 sparse boundary rules

Important limitation:

- this is not a complete SOPR/LTH/UTXO-level on-chain provider
- use as flow/event confirmation and regime context, not as a replacement for
  CryptoQuant/Glassnode-style holder-state research

Priority: **P1/P2**.
Reason: high value for M3.2, but its PIT and coverage properties must be
audited more carefully than spot/futures.

2026-05-07 execution update:

- PIT exchange-transfer sidecar exists at
  `artifacts/quant_research/coinglass/exchange_transfers_1d.csv.gz`.
- PIT whale-transfer sidecar exists at
  `artifacts/quant_research/coinglass/whale_transfers_1d.csv.gz`.
- Combined context exists at
  `artifacts/quant_research/coinglass/participant_context_1d.csv.gz`.
- Live sync report:
  `artifacts/quant_research/factor_reports/2026-05-07-coinglass-etf-onchain-participant-sidecars/coinglass_etf_onchain_participant_sidecars.json`.
- Exchange transfer history is a paginated latest-event feed because local
  probes showed start/end filters are ignored. Raw `transfer_type` codes are
  retained and not promoted as semantic inflow/outflow labels.
- Whale transfer history used millisecond start/end windows with adaptive
  splitting; final warnings were empty.

### CG-6. Options aggregate sidecar

**Goal**: accelerate an options-regime slice without pretending we already have
full dealer-gamma topology.

Inputs:

- option exchange OI history
- option exchange volume history
- option max pain
- option-vs-futures OI ratio

Proposed output:

```text
artifacts/quant_research/coinglass/options_regime_panel_1d.csv.gz
```

Core features:

- BTC/ETH options OI regime
- option volume shock
- option-vs-futures OI ratio regime
- distance to max-pain
- expiry-week pressure state

Blocked until proven:

- full strike/expiry/IV surface
- dealer gamma topology
- 25-delta skew family

Priority: **P2**.
Reason: useful for market-wide regime gates now, but the highest-moat options
research still requires finer surface data or a paid surface source.

### CG-7. Vendor indicator quarantine

**Goal**: ingest indicator endpoints only as diagnostics or market-state
metadata unless they can be independently recomputed PIT-safe.

Examples:

- Pi Cycle
- Bull Market Peak indicators
- vendor RSI/EMA/ATR endpoints

Rules:

- do not put vendor-calculated indicators directly into alpha score manifests
- do not use any endpoint whose calculation window or revision policy is opaque
  as a promotion-grade feature
- allowed uses:
  - sanity dashboards
  - regime labels for exploratory slicing
  - documentation of broad-market context

Priority: **P3**.
Reason: low engineering cost, but high overfitting and lookahead risk.

---

## 3. Research restart roadmap

### R-0. Coverage reset before alpha claims

After CG-1 and CG-2, rebuild:

- full 99-symbol 1h dataset
- strategy-scope 1h dataset
- daily h10d canonical dataset
- feature manifests with provider coverage sidecars

Required report:

```text
artifacts/quant_research/reports/coinglass_coverage_reset_2026-05-04.md
```

Report fields:

- full-panel coverage before/after
- strategy-scope coverage before/after
- symbol-level failure reasons:
  - true listing too short
  - missing spot
  - missing executable perp
  - alias/multiplier unresolved
  - derivatives field missing
  - provider conflict
- native-vs-derived OI value counts
- CoinGlass-vs-CoinAPI/Binance overlap error

No alpha work should be promoted until this report exists.

### R-1. Re-baseline `v5_rw_bridge_no_overlay_h10d`

**Why restart**: it is the canonical h10d parent. A richer data panel changes
coverage, execution eligibility, and possibly liquidity/capacity estimates.

Actions:

1. rebuild the daily feature panel with the cleaned data spine
2. re-run canonical parent metrics
3. re-run fixed-set paired comparison baselines
4. re-run promotion guard and overlay-ablation sidecars
5. compare old-vs-new parent performance by:
   - timestamp overlap
   - full new sample
   - native-only OI
   - derived-inclusive OI
   - top/mid liquidity buckets
   - symbol holdouts

Decision rule:

- if canonical parent metrics materially change, freeze all old challenger
  conclusions as `pre_coinglass_full_stack_comparator`
- if metrics are stable, preserve the parent and only re-open data-sensitive
  challengers

Priority: **P0 research**.

2026-05-07 execution update:

- Frozen reset strict re-run remains `fail_closed_frozen_reset_strict_validation`.
- Alpha-card semantics are corrected: missing statistical falsification tests
  are now `not_measured_fail_closed`, not measured cost/delay failures.
- The new symbol/bucket strict gate fails the original parent on
  `top_bucket_only` and `symbol_holdout_dependency` with TRX as the measured
  hard-fail holdout subject.
- The last narrow diagnostic did **not** fail: `top_liquidity_ex_trx` produced
  positive OOS metrics and passed leave-one-symbol-out inside that subset.
- Therefore the parent is still not promotable, but a residual
  `top_liquidity_ex_trx` sublane is quarantined for a separate candidate
  validation. It must not inherit the parent promotion status.

2026-05-07 R-1a execution update:

- `top_liquidity_ex_trx` is now a standalone quarantined candidate:
  `r1a_top_liquidity_ex_trx_h10d`.
- Candidate manifest:
  `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_r1a_top_liquidity_ex_trx_h10d.json`.
- Strict run root:
  `artifacts/quant_research/coinglass/r1a_top_liquidity_ex_trx_strict_2026-05-04_2026-05-07_01`.
- Fast reject passed on the frozen reset matrix:
  validation net return / Sharpe `0.4046422811` / `2.7583358069`;
  test net return / Sharpe `0.2453822837` / `2.6736234949`.
- Complete statistical falsification did **not** clear:
  `time_shuffle_failed`, `label_shuffle_failed`, `delay_stress_failed`,
  `cost_stress_failed`, `symbol_holdout_failed`, and
  `liquidity_bucket_consistency_failed`.
- Strict result: `strict_validation_passed = false`,
  `strict_survivor_count = 0`, `credible_research_evidence = false`.
- Decision: keep R-1a quarantined / fail-closed. Do not optimize this residual
  sublane without a new mechanism reason.

### R-2. True `cross_sectional_intraday_1h` strategy feasibility

**Why restart**: prior true 1h strategy work was blocked by history length and
coverage, not by a clean alpha rejection.

Actions:

1. define 1h decision calendar and label contract
2. test horizons:
   - `h24h`
   - `h48h`
   - `h72h`
   - `h5d`
   - `h10d` as bridge to the existing parent
3. rebuild 1h features without leaking future daily aggregates
4. run baseline 1h long-short rank strategy
5. run capacity / turnover / max-trade-participation stress before any Sharpe
   interpretation

Mandatory fail-closed gates:

- turnover does not make capacity impossible under existing participation
  limits
- alpha survives 1h time shuffle
- alpha survives symbol holdout
- alpha is not only a vendor timestamp or listing-age artifact
- slippage/cost stress does not erase edge

Priority: **P0/P1 research** after R-1.

2026-05-07 execution update:

- Opened the parallel 1h Stage 0 lane in
  `docs/quant_research/04_parallel_1h/parallel_1h_alpha_mining_roadmap.md`.
- Completed the first-three Stage 0 set under
  `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/`.
- `low_float_squeeze_trap_stage0_1h`: `fail`; shuffle, symbol holdout, and
  delay robustness failed.
- `post_squeeze_exit_short_stage0_1h`: `fail`; shuffle, symbol holdout,
  liquidity-bucket consistency, and delay robustness failed.
- `fake_liquidity_capacity_haircut_stage0_1h`: `pass` as a quarantined
  risk-control / participation-cap candidate; h24 short-return delta is
  `-0.007236` for haircut rows versus controls, with 6,260 haircut rows from
  28,142 post-pump candidates.
- Atomic decomposition report:
  `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_atomic_decomposition_1h.json`.
  Only the aggregate haircut state survives; standalone `volume_oi`,
  `book_thinness`, `taker_book_dislocation`, `thin_capacity`, and
  `slippage_proxy_extreme` components fail strict component admission.
- Aggregate-only parent-interaction simulator report:
  `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_aggregate_parent_interaction_1h.json`.
  `hard_veto`, `quarter_size`, and `soft_multiplier` all improve aggregate h24
  PnL and reduce adverse tails, but all fail strict admission on symbol holdout
  consistency (`0.5694 < 0.60`).
- Symbol/provider sensitivity report:
  `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_parent_symbol_provider_sensitivity_1h.json`.
  Excluding the known CoinGlass spot-concordance watchlist only moves hard-veto
  symbol holdout from `0.5694` to `0.5714`, and provider-watchlist-only
  improvement is negative (`-0.001260`), so the failure is broader symbol
  instability rather than a simple suspect-provider-symbol artifact.
- Pre-registered age-sidecar redesign:
  `docs/quant_research/04_parallel_1h/parallel_1h_fake_liquidity_age_sidecar_preregistration.md`
  and
  `artifacts/quant_research/factor_reports/2026-05-07-parallel-1h-alpha-stage0/fake_liquidity_age_30_180d_sidecar_1h.json`.
  The primary `30_180d` local-history-age sidecar improves aggregate h24 PnL
  and passes symbol holdout (`0.6806`), but it fails same-timestamp shuffle and
  +24h delay robustness, so it is rejected.
- Boundary: this is not h10d promotion evidence and not live-trading evidence.
  Atomic decomposition, aggregate-only parent simulation, symbol/provider
  sensitivity, and the preregistered age-sidecar redesign are complete. The
  fake-liquidity branch remains rejected unless a new exogenous venue/provider
  sidecar is added.

### R-3. M3.2 boundary activation with ETF/on-chain confirmation

**Why restart**: current M3.2 smooth overlays failed, but discrete boundary
activation was Stage0-positive. CoinGlass adds ETF, exchange-flow, and whale
state that can either confirm or falsify the sparse boundary interpretation.

Carry forward only the Stage0-positive sparse rules:

- `tron_impulse_short_high_beta_rs`
- `tron_heat_short_high_rs`
- `rebound_long_idio`
- `sell_pressure_short_high_beta_rs`

New confirmations to test:

- ETF inflow/outflow regime
- CEX stablecoin transfer impulse
- whale transfer impulse
- ETF-flow plus perp-basis stress
- stablecoin flow plus short-boundary selection quality

Required falsification:

- delay test
- time shuffle
- label shuffle
- symbol holdout
- liquidity-bucket consistency
- native-only vs CoinGlass-augmented sidecar comparison

Priority: **P1 research**.
Reason: this is the current best repo-native next lane and the new CoinGlass
surface directly improves its mechanism test.

2026-05-07 R-3 execution update:

- strict hard-gate card:
  `docs/quant_research/03_alpha_branches/m3_2_full_stack_boundary_falsification.md`.
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-07-m3-2-boundary-activation-falsification-iter1-all/m3_2_boundary_activation_falsification.json`.
- result: `cleared_variants = []`; all four Stage0-positive variants are
  rejected for direct manifest A/B.
- deterministic blockers:
  - `tron_impulse_short_high_beta_rs`: delay and liquidity-bucket consistency.
  - `tron_heat_short_high_rs`: delay, symbol holdout, and liquidity-bucket
    consistency.
  - `rebound_long_idio`: liquidity-bucket consistency.
  - `sell_pressure_short_high_beta_rs`: liquidity-bucket consistency.
- operational note: the default 80-iteration monolithic runner was stopped
  after `3292` CPU seconds without a JSON artifact. That run is not interpreted.
  Since every variant already fails a deterministic hard gate, full random-tail
  completion is not required for rejection. Any future random-tail rerun should
  first make the executor resumable or exact-fast with per-label partial
  artifacts.
- Decision: stop the current direct M3.2 boundary branch. Reopen only with a
  new exogenous ETF/on-chain sidecar that changes the activation definition and
  clears deterministic hard gates before random-tail spend.

2026-05-07 R-3b ETF/on-chain sidecar integration update:

- sidecar hard-gate card:
  `docs/quant_research/03_alpha_branches/m3_2_etf_onchain_sidecar_falsification.md`.
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-07-m3-2-etf-onchain-sidecar-falsification/m3_2_etf_onchain_sidecar_falsification.json`.
- carried forward only the four direct Stage0-positive M3.2 labels and rebuilt
  their activation states with pre-registered CoinGlass ETF/on-chain
  confirmations.
- Stage 0 positives:
  - `tron_impulse_short_high_beta_rs__cg_etf_10d_inflow_confirm`
  - `tron_heat_short_high_rs__cg_etf_10d_outflow_confirm`
  - `rebound_long_idio__cg_etf_10d_outflow_confirm`
- strict result: `strict_cleared_variants = []`;
  `alpha_rerun_allowed = False`; `manifest_ab_allowed = False`.
- deterministic blockers:
  - `tron_impulse_short_high_beta_rs__cg_etf_10d_inflow_confirm`: delay and
    liquidity-bucket consistency.
  - `tron_heat_short_high_rs__cg_etf_10d_outflow_confirm`: delay and symbol
    holdout.
  - `rebound_long_idio__cg_etf_10d_outflow_confirm`: liquidity-bucket
    consistency.
  - `sell_pressure_short_high_beta_rs__cg_participant_risk_off_confirm`:
    Stage 0 not positive because active timestamps are only `4`.
- Decision: close this R-3 sidecar reopening. Do not run another M3.2
  confirmation filter unless the mechanism definition changes materially.

### R-4. SP-K canonical-parent revalidation

**Why restart**: SP-K remains useful mechanism evidence, but the promotable
question must attach to `v5_rw_bridge_no_overlay_h10d`, not legacy `v6_h10d`.
CoinGlass can improve the short-slot replacement context with better spot,
perp, taker, liquidation, and participant data.

Allowed landing shapes:

- short-slot replacement
- short veto
- reduced short exposure
- do-not-short state

Rejected landing shapes to avoid repeating:

- broad smooth score overlay
- generic funding/OI confirmation gate
- naive news veto

New confirmation candidates:

- post-pump plus taker exhaustion
- post-pump plus liquidation max-pain distance
- post-pump plus spot-vs-perp flow divergence
- post-pump plus ETF/on-chain market-wide risk-on state

Priority: **P1/P2 research**.
Reason: high practical relevance, but only after parent re-baseline and data
coverage reset.

2026-05-07 R-4 execution update:

- stage0 card:
  `docs/quant_research/03_alpha_branches/spk_non_kline_confirmation_stage0.md`.
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-07-spk-non-kline-confirmation-stage0/spk_non_kline_confirmation_stage0.json`.
- tested first non-kline confirmation battery on the canonical parent:
  funding/OI crowding, liquidation cascade exhaustion, taker/orderbook
  exhaustion, top-trader fade / retail chase, and ready-gated stablecoin stress.
- result: `kept_for_strict_falsification = []`.
- main blockers:
  - funding/OI and top-trader filters reduce activity but weaken entered shorts
    versus raw SP-K and worsen short-basket quality.
  - liquidation confirmation is directionally closest, but its selected short
    basket remains weaker than raw SP-K.
  - taker/orderbook exhaustion has too few replacements (`37`) and a worse
    next-day squeeze profile.
  - ready-gated stablecoin confirmation has zero eligible replacements in this
    landing shape.
- Decision: stop generic non-kline confirmation overlays for SP-K. Reopen R-4
  only with a narrower pre-registered landing shape; otherwise move to R-5/R-6.

### R-5. MF-05 sub-day venue stress re-open

**Why restart**: current 1d cross-venue close-price dispersion failed in the
wrong direction. That does not close the full MF-05 mechanism; it closes the
coarse daily landing shape.

New data requirement:

- venue-local 1h spot price and volume
- venue-local futures price/OI/funding where supported
- venue-local taker or CVD if supported

New feature shapes:

- intraday venue dislocation impulse
- Binance-vs-OKX/Bybit venue volume migration
- spot-perp venue-local basis stress
- dislocation decay after large liquidation or ETF-flow day

Decision rule:

- old 1d MF-05 remains a closed comparator
- re-open only if 1h venue-local state exists with enough coverage and shows
  directional event timing

Priority: **P2 research**.

2026-05-07 R-5 execution update:

- data-gate card:
  `docs/quant_research/03_alpha_branches/mf05_venue_local_data_gate.md`.
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-07-mf05-venue-local-data-gate/mf05_venue_local_data_gate.json`.
- input sidecar:
  `artifacts/quant_research/sidecars/venue_concentration_1h/venue_concentration_1h_sidecar.csv.gz`.
- result: `alpha_rerun_allowed = False`; `mf05_stage0_allowed = False`.
- sidecar coverage is useful but not admissible: `135,116` rows, `30`
  subjects, `30.84%` multi-venue rows, `26.40%` three-plus venue rows, and all
  rows still marked `pre_concordance` / `not_started`.
- Binance CoinAPI-vs-native sanity check passed for 1h close/volume
  (`quote_volume_abs_pct_diff_median ~= 0.0009`, p95 `~0.0850`), so the blocker
  is not Binance.
- hard blocker: no independent native OKX / Bybit / Coinbase local concordance
  source exists. The OKX / Bybit / Coinbase rows are sidecar input sources from
  CoinAPI, not native venue-trust checks.
- Decision: do not run MF-05 alpha validation or h10d sidecar admission from
  this sidecar yet. Keep the sidecar as a data unlock only; move the roadmap to
  R-6 unless native multi-venue concordance is added.

### R-6. MF-01 orderbook / inventory re-test

**Why restart**: MF-01 orderbook fragility was mechanism-positive but too sparse
as a confirmation layer. CoinGlass can add cleaner spot flow, orderbook,
liquidation, taker, and footprint context.

New feature shapes:

- depth fragility plus taker-flow persistence
- orderbook imbalance velocity
- liquidation pressure plus depth withdrawal
- spot footprint exhaustion after pump/cascade
- do-not-short veto for fragile upside squeeze conditions

Acceptance gates:

- non-sparse transmission, or explicitly sparse event landing
- cost-aware implementation
- symbol-holdout stability
- does not only select the same rows as F-cascade

Priority: **P2 research**.

2026-05-07 R-6 execution update:

- stage0 card:
  `docs/quant_research/03_alpha_branches/mf01_orderbook_inventory_r6_retest.md`.
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-07-mf01-orderbook-inventory-stage0/m3_3_mf01_confirmation_stage0.json`.
- result: do not open manifest A/B for the MF-01 orderbook / inventory landing
  shape.
- event-only `q2_event_only_max3` is the only Stage0-pass variant (`237`
  entered rows, `14` subjects, `19.95%` changed timestamps, `+0.052%` edge vs
  parent).
- MF-01-confirmed variants are row-quality-positive but too sparse: all three
  MF-01 confirmation modes collapse to the same `18` entered rows, `5`
  subjects, `1.65%` changed timestamps, and only `+0.002%` edge vs parent.
- Decision: keep MF-01 as mechanism evidence only. Do not spend the next
  roadmap slot on another broad bottom-boundary MF-01 replacement unless the
  variant is pre-registered to solve breadth, cost, symbol-holdout, and
  liquidity-bucket consistency.

### R-7. MF-07 participant disagreement 2.0

**Why restart**: daily MF-07 and raw 1h participant-pivot forms failed. A richer
participant stack can test the mechanism more honestly.

New participant stack:

- top-trader long/short
- global account long/short
- taker buy/sell
- CEX transfer direction
- whale transfer direction
- ETF flow regime for BTC/ETH-led market state

Feature shapes:

- top-vs-global disagreement plus whale confirmation
- taker-vs-position divergence
- smart-money fade vs retail chase proxy
- disagreement decay after liquidation/event shocks

Priority: **P2/P3 research**.
Reason: interesting, but current local forms already failed; do not let this
jump ahead of M3.2, 1h feasibility, or canonical re-baseline.

2026-05-07 R-7 execution update:

- gate card:
  `docs/quant_research/03_alpha_branches/mf07_participant_stack_r7_gate.md`.
- primary gate report:
  `artifacts/quant_research/factor_reports/2026-05-07-r7-mf07-participant-stack-gate/mf07_participant_stack_r7_gate.json`.
- fresh daily participant-disagreement report:
  `artifacts/quant_research/factor_reports/2026-05-07-r7-mf07-participant-disagreement-spk-stage0/mf07_participant_disagreement_spk_stage0.json`.
- fresh sub-day participant-pivot report:
  `artifacts/quant_research/factor_reports/2026-05-07-r7-mf07-subday-participant-pivot-stage0/mf07_subday_participant_pivot_stage0.json`.
- result: `alpha_rerun_allowed = False`; `manifest_ab_allowed = False`.
- current-form rejection: daily top/global MF-07 kept `0` variants; sub-day
  participant-pivot MF-07 kept `0` variants. The best daily veto is too sparse
  (`0.91%` changed timestamps), and the best sub-day veto is weak and sparse
  (`+0.000144` edge vs raw SP-K, `3.02%` changed timestamps).
- full-stack blocker update: PIT ETF, exchange-transfer, and whale-transfer
  sidecars now exist, but they are not integrated into the current daily
  feature panel. Stablecoin exchange/whale context is only `17.36%` covered in
  the current daily feature panel, and ETF flow columns are still absent.
- Decision: stop R-7 in the current roadmap cycle. Reopen only after the PIT
  ETF/on-chain participant sidecars are integrated into a new pre-registered
  transition definition that beats raw SP-K on the canonical parent.

2026-05-09 R-7b ETF/on-chain transition update:

- transition falsification card:
  `docs/quant_research/03_alpha_branches/mf07_etf_onchain_transition_falsification.md`
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-09-r7-mf07-etf-onchain-transition-falsification/mf07_etf_onchain_transition_falsification.json`
- integrated the PIT CoinGlass `participant_context_1d` sidecar into six
  pre-registered MF-07 transition variants. Exchange-transfer activity remains
  quarantined; only ETF and whale fields are used directionally.
- result: `stage0_survivors = []`; `strict_cleared_variants = []`;
  `alpha_rerun_allowed = False`; `manifest_ab_allowed = False`.
- confirm-style transitions were active but degraded raw SP-K
  (`edge_vs_spk_raw` from `-0.001033` to `-0.001407`).
- veto-style transitions had the right sign but stayed at-par or too sparse:
  best edge was `+0.000333` with only `3.11%` changed timestamps.
- Decision: close the current MF-07 participant-stack reopening. Do not add an
  MF-07 ETF/on-chain transition to the parent overlay without a materially new
  mechanism.

### R-8. M3.1 options-regime slice

**Why restart**: Deribit free historical path was too slow for full options
surface. CoinGlass option aggregates can unlock a narrower market-level regime
slice now.

Immediate scope:

- option OI regime
- option volume shock
- options/futures OI ratio
- distance to max pain
- expiry-week pressure state

Defer:

- dealer gamma by strike
- 25-delta skew
- full IV term surface
- strike concentration topology

Priority: **P2 research**.
Reason: high moat, but current confirmed CoinGlass option endpoints support
regime gates more clearly than full dealer-gamma topology.

2026-05-07 execution update:

- R-8 Stage0/data-gate card:
  `docs/quant_research/03_alpha_branches/m3_1_options_regime_r8_stage0.md`
- Primary report:
  `artifacts/quant_research/factor_reports/2026-05-07-m3-1-options-regime-stage0/m3_1_options_regime_stage0.json`
- Generated market-level sidecar:
  `artifacts/quant_research/coinglass/options_regime_panel_1d.csv.gz`
- Result: `r8_high_option_volume_shock_flag` is kept only as a quarantined
  market-gate candidate. It has train/test-consistent short-veto direction
  (`+0.0411` train edge, `+0.0289` test edge), but it is not a cross-sectional
  rank factor and cannot open manifest A/B.
- Hard blockers: BTC/ETH option OI has no parent-date historical coverage in
  the current panel, max-pain is only a current snapshot, and aggregate options
  features require a pre-registered exposure-gate falsification before any
  parent overlay.

2026-05-09 R-8b strict falsification update:

- short-veto hard-gate card:
  `docs/quant_research/03_alpha_branches/m3_1_options_volume_shock_veto_falsification.md`
- primary artifact:
  `artifacts/quant_research/factor_reports/2026-05-09-m3-1-options-volume-shock-veto-falsification/m3_1_options_volume_shock_veto_falsification.json`
- tested only the quarantined Stage 0 survivor:
  `r8_high_option_volume_shock_flag`
- observed parent-short diagnostic remained strong:
  `153` active dates, active-minus-inactive next-10d short-basket return
  `+0.0366`.
- strict passes: +1d delay, contiguous era split, symbol holdout, active-date
  time shuffle, return-date shuffle.
- strict blocker: liquidity-bucket consistency fails because `tail_liquidity`
  has eligible sample and negative edge (`-0.0199`), even though
  `top_liquidity` and `mid_liquidity` pass.
- Decision: keep as quarantined mechanism evidence only;
  `alpha_rerun_allowed = False`; `manifest_ab_allowed = False`.

---

## 4. Updated research priority after CoinGlass expansion

| rank | lane | status before CoinGlass expansion | new priority | why |
| ---: | --- | --- | --- | --- |
| 0 | CG-1/CG-2 data foundation | not a research lane | mandatory | without this, all reopened results are polluted |
| 1 | `v5_rw_bridge_no_overlay_h10d` re-baseline | original parent fail-closed; residual top-liq/ex-TRX quarantined | P0 complete for parent, P0 diagnostic for residual sublane | every challenger depends on this reference, but the parent cannot be promoted |
| 2 | true `cross_sectional_intraday_1h` feasibility | first-three Stage 0, atomic decomposition, parent simulator, symbol/provider sensitivity, and preregistered age-sidecar redesign completed; fake-liquidity branch rejected | stop fake-liquidity branch unless a new exogenous venue/provider sidecar is added; no bridge | Binance derivatives close is the return reference; CoinGlass spot remains quarantined, standalone atoms fail, provider-watchlist exclusion does not rescue holdout, aggregate variants fail strict parent admission, and age-sidecar redesign fails shuffle/delay |
| 3 | M3.2 sparse boundary activation | direct hard-gate failed, and R-3b ETF/on-chain sidecar reopening also failed | close current M3.2 branch; no manifest A/B | direct variants and pre-registered CoinGlass sidecar variants all fail deterministic strict blockers before any random-tail or A/B spend |
| 4 | SP-K canonical-parent short replacement | first non-kline confirmation battery completed; no variant kept | stop generic confirmation branch; reopen only with narrower pre-registered landing shape | funding/OI, liquidation, taker/orderbook, participant, and stablecoin filters do not beat raw SP-K on combined Stage 0 checks |
| 5 | MF-05 sub-day venue stress | 1h venue sidecar built, but data gate blocks alpha rerun | blocked until native OKX/Bybit/Coinbase concordance exists | Binance sanity passes, but the venue-concentration sidecar is still pre-concordance and all non-Binance venue rows lack native trust checks |
| 6 | MF-01 orderbook/inventory | R-6 retest complete; confirmation improves row quality but is too sparse | stop current landing shape; mechanism evidence only | MF-01-confirmed variants collapse to 18 entered rows / 5 subjects and do not transmit parent-level edge |
| 7 | M3.1 options-regime | R-8 market-level sidecar, Stage0/data gate, and R-8b strict veto falsification complete | keep volume-shock gate quarantined; no manifest A/B | option-volume shock passes delay/holdout/shuffle checks but fails liquidity-bucket consistency on tail-liquidity exposure, while OI/max-pain remain non-PIT-historical |
| 8 | MF-07 participant disagreement 2.0 | R-7 gate and R-7b ETF/on-chain transition test complete | close current MF-07 branch; no manifest A/B | daily top/global, 1h pivot, and PIT ETF/whale transition forms all have zero Stage 0 survivors |
| 9 | vendor indicators | not in repo | P3 | diagnostic only unless PIT recomputed |

---

## 5. Concrete local implementation sequence

### Day 0 / first execution block

1. Write `coinglass_capability_matrix` smoke script.
2. Add `coinglass_spot_ohlcv` provider module.
3. Backfill Binance spot `1h` for the current strategy scope.
4. Validate close/volume overlap against existing Binance/CoinAPI data.
5. Rebuild the `cross-sectional-intraday-1h` dataset.
6. Produce `coinglass_coverage_reset_2026-05-04.md`.

Exit condition:

- strategy-scope coverage passes
- remaining failures are classified by true cause
- no alpha experiment is interpreted yet

### Day 1 / second execution block

1. Extend backfill to the full research universe.
2. Implement OI-value derivation with provenance.
3. Add Binance multiplier perp alias mapping.
4. Rebuild full 1h and daily datasets.
5. Re-run canonical h10d parent metrics.
6. Fix any experiment runner failure exposed by the rebuilt panel.

Exit condition:

- canonical parent re-baseline report exists
- native-only vs derived-inclusive comparison exists
- all old data-blocked conclusions are reclassified

### Day 2 / third execution block

1. Add ETF daily sidecar.
2. Add CoinGlass on-chain exchange/whale sidecar.
3. Add options aggregate sidecar.
4. Re-run M3.2 sparse boundary falsification with the new sidecars.
5. Open only one research A/B if falsification survives.

2026-05-07 checkpoint:

- Direct M3.2 sparse boundary falsification now has a hard-gate card and fails.
- The ETF/on-chain sidecar data layer exists and the narrow pre-registered
  R-3b integration/falsification pass is complete.
- R-3b result: `strict_cleared_variants = []`; close current M3.2 branch and
  move roadmap execution to downstream lanes rather than another M3.2
  confirmation rerun.

Exit condition:

- M3.2 has both direct-boundary and ETF/on-chain-sidecar strict falsification
  cards
- no smooth MF13/MF14 overlay is reintroduced without new evidence

### Day 3+ / research expansion block

1. True 1h strategy feasibility.
2. SP-K canonical-parent revalidation.
3. MF-05 sub-day venue stress.
4. MF-01 orderbook/inventory re-test.
5. M3.1 options-regime slice.
6. MF-07 participant stack only after the above.

Exit condition:

- each lane has an explicit pass/fail report
- failures stay as comparator evidence
- only strict-pass candidates proceed to manifest A/B

2026-05-07 checkpoint:

- true 1h feasibility: first-battery completed; fake-liquidity branch rejected.
- SP-K canonical-parent revalidation: first non-kline confirmation battery
  completed; no variant kept for strict falsification.
- MF-05 venue-local stress: 1h sidecar exists but data gate blocks alpha rerun
  until native OKX/Bybit/Coinbase concordance exists.
- MF-01 orderbook/inventory: R-6 retest complete; confirmation improves row
  quality but is too sparse for manifest A/B.
- M3.1 options-regime: R-8 sidecar and Stage0/data gate complete; volume-shock
  short-veto strict falsification now exists and fails liquidity-bucket
  consistency; keep it as mechanism evidence only.
- MF-07 participant disagreement 2.0: R-7 gate complete; daily top/global and
  sub-day pivot forms have zero kept variants. R-7b now integrates PIT
  ETF/whale sidecars into pre-registered transition definitions, but still has
  zero Stage 0 survivors.
- Next executable lane should not be another M3.2 or R-8 confirmation rerun.
  It should also not be another current-form MF-07 rerun. Move to a genuinely
  new pre-registered mechanism or stop the CoinGlass reopening cycle and update
  the broader alpha priority map.

2026-05-09 closure checkpoint:

- final priority update:
  `docs/quant_research/03_alpha_branches/research_priority_update_full_stack.md`
- decision: the current CoinGlass reopening cycle is frozen. CoinGlass remains
  a reusable catalog and sidecar source, but no R-1 through R-8 reopening lane
  produced a strict survivor, manifest A/B candidate, or live candidate.
- main roadmap position: past the CoinGlass `Day 3+ / research expansion
  block`; next work should be native venue concordance if the goal is data
  trust, or a new pre-registered 1h mechanism if the goal is alpha search.

---

## 6. Non-negotiable safeguards

1. **Provider provenance is mandatory**
   Every row and derived feature must expose source and, where relevant,
   native-vs-derived field provenance.

2. **No silent forward fill across listing boundaries**
   Missing pre-listing history is a true failure, not a data-engineering gap.

3. **ETF and on-chain features require PIT lagging**
   If publication timestamp is unknown, daily features must be lagged before
   entering a decision frame.

4. **Vendor indicators are quarantined**
   They can describe regimes but should not become promotion-grade alpha unless
   recomputed locally with auditable PIT inputs.

5. **Coverage improvement is not alpha evidence**
   A panel can become executable and still contain no promotable alpha.

6. **Old conclusions are not automatically invalidated**
   They are reclassified:
   - `confirmed_under_full_stack_data`
   - `weakened_under_full_stack_data`
   - `reopened_due_to_data_blocker`
   - `closed_comparator_only`

7. **The canonical parent remains the comparison anchor**
   `v5_rw_bridge_no_overlay_h10d` remains the h10d parent unless the rebuilt
   canonical re-baseline itself fails governance.

---

## 7. Required reports and artifacts

| artifact | purpose | required before |
| --- | --- | --- |
| `coinglass_capability_matrix.json` | endpoint availability and schema truth | any bulk backfill |
| `coinglass_spot_backfill_summary.json` | spot coverage and provider overlap | dataset rebuild |
| `coinglass_coverage_reset_2026-05-04.md` | before/after coverage and failure classification | alpha re-runs |
| `coinglass_oi_value_provenance_report.md` | native vs derived OI audit | daily h10d re-baseline |
| `canonical_parent_full_stack_rebaseline.md` | new canonical parent metrics | challenger re-tests |
| `m3_2_full_stack_boundary_falsification.md` | sparse on-chain/ETF boundary validity | any M3.2 A/B |
| `m3_2_etf_onchain_sidecar_falsification.md` | pre-registered CoinGlass ETF/on-chain sidecar reopening for M3.2 | any M3.2 sidecar A/B |
| `m3_1_options_volume_shock_veto_falsification.md` | pre-registered options volume-shock short-veto validity | any M3.1 options exposure gate |
| `mf07_etf_onchain_transition_falsification.md` | pre-registered MF-07 ETF/whale participant-transition validity | any MF-07 participant transition |
| `intraday_1h_feasibility_report.md` | true 1h turnover/cost/alpha feasibility | any 1h manifest |
| [`research_priority_update_full_stack.md`](../03_alpha_branches/research_priority_update_full_stack.md) | final updated priority after data fill | roadmap refresh |

---

## 8. Stop rules

Stop data fill and do not continue to research if:

- CoinGlass close prices disagree materially with Binance/CoinAPI on overlap
  without a documented symbol or venue reason.
- pagination cannot reproduce a complete hourly spine for old listings.
- OI-value derivation diverges materially from native USD OI on overlap.
- provider timestamps cannot be normalized deterministically.
- ETF/on-chain data cannot be lagged PIT-safely.

Stop research promotion if:

- time shuffle, label shuffle, or symbol holdout fails
- liquidity-bucket consistency fails
- symbol/bucket blocker attribution returns `top_bucket_only`
- symbol/bucket blocker attribution returns `symbol_holdout_dependency`
- the edge only appears in derived-OI rows and vanishes in native-only rows
- turnover/cost stress erases the result
- fixed-set paired comparison against `v5_rw_bridge_no_overlay_h10d` is weak

---

## 9. Bottom line

The highest-priority path is not to immediately add more alpha factors. It is:

1. make CoinGlass spot/futures coverage canonical enough to remove the 1h data
   blocker;
2. re-baseline the canonical h10d parent under the new data surface;
3. keep the original h10d parent fail-closed unless the quarantined
   `top_liquidity_ex_trx` residual sublane passes as a new candidate;
4. restart the true 1h strategy feasibility test only on a canonical OHLC path;
5. re-open only the research lanes whose prior failure was plausibly data-shape
   related:
   - M3.2 sparse boundary activation
   - SP-K canonical-parent short replacement
   - MF-05 sub-day venue stress
   - MF-01 orderbook/inventory
   - M3.1 options-regime

This turns the next phase from "can we get enough data?" into "which mechanisms
survive strict falsification under a complete, provenance-audited market-data
surface?"
