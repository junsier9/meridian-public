# CryptoQuant + Alchemy M3.2 Plan

`Snapshot date: 2026-05-02`
`Owner: quant_research_maintainer`

This document defines the recommended implementation path for `stablecoin plumbing + on-chain reflexivity` using:

- `Alchemy` as the raw on-chain / PIT-oriented Ethereum transfer layer
- `CryptoQuant` as the aggregated multi-chain / exchange-flow / reflexivity layer

This is the preferred near-term path for unlocking `MF-13 stablecoin_plumbing` and `MF-14 onchain_reflexivity` without replacing the existing M3.2 bootstrap already shipped in the repository.

**Implementation status as of `2026-05-02`**:
- Phase 1 scaffold has started.
- `onchain_cryptoquant.py` and the first sync scripts are shipped.
- Live smoke / bootstrap runs now succeed for `usdt_eth`, `usdc`, `dai`, and `tusd` stablecoin supply + exchange flows, plus `BTC/ETH` reflexivity on the local `Crypto_Quant_API`.
- A parallel non-ETH raw lane is now shipped via `TronScan` public aggregates:
  - `src/enhengclaw/quant_research/onchain_stablecoin_tron.py`
  - `scripts/quant_research/provider_leaf_sync_helpers/sync_tronscan_stablecoin_tron.py`
  - current verified coverage for `USDT_TRX` is `2024-05-01` through `2026-04-30` (`730` daily rows).
- The fused `m3_2_feature_panel_1d` now unions provider date spines instead of anchoring only on Ethereum/Alchemy, so TRON flow history extends panel coverage even when `m3_2_panel_ready` is still governed by the narrower Alchemy + CryptoQuant overlap.

---

## 1. Why this two-provider stack

We should not ask one provider to do both jobs.

### 1.1 Alchemy should own the raw layer

Alchemy is best used for:

- ERC20 transfer history
- mint / burn event reconstruction
- point-in-time local ingestion logs
- custom address-label sidecars
- direct inspection of anomalous windows

This is already partially implemented in [onchain_stablecoin.py](../../../src/enhengclaw/quant_research/onchain_stablecoin.py) and the associated M3.2 scripts.

### 1.2 CryptoQuant should own the aggregate layer

CryptoQuant is best used for:

- stablecoin `supply_total / supply_circulating / supply_issued / supply_redeemed`
- exchange `reserve / inflow / netflow`
- market-wide reflexivity metrics such as exchange-flow state and SOPR-family indicators
- faster time-to-first-alpha than self-building every entity graph from raw chain data

### 1.3 Why not Alchemy-only

Alchemy-only is not enough for the full lane because it does not solve:

- multi-chain stablecoin coverage
- standardized exchange/entity clustering
- BTC/ETH reflexivity metrics like SOPR
- fast access to market-level exchange flow aggregates

---

## 2. Provider split of responsibility

| Layer | Provider | Responsibility |
| --- | --- | --- |
| Raw transfer truth | Alchemy | Ethereum ERC20 transfer, mint, burn, wallet-level diagnostics |
| Local PIT layer | Alchemy + local label snapshots | `as_of`-dated address labels and coverage audit |
| Aggregated supply / flow layer | CryptoQuant | Stablecoin supply, reserve, inflow, netflow |
| Reflexivity layer | CryptoQuant | Exchange-flow state, SOPR-family, related market stress metrics |
| Final feature engineering | Local code | Turn raw + aggregate data into MF-13 / MF-14 factors |

Rule of thumb:
- If we need `who moved what on Ethereum`, ask Alchemy.
- If we need `how much dry powder / exchange pressure exists market-wide`, ask CryptoQuant.

---

## 3. Phase plan

## 3.1 Phase 1: Wire CryptoQuant into the existing M3.2 bootstrap

### Goal

Add a second provider next to the current Alchemy pipeline without disturbing the current M3.2 files.

### Deliverables

- env resolver that accepts `Crypto_Quant_API` first and `CRYPTOQUANT_API_KEY` as alias
- new loader module:
  - `src/enhengclaw/quant_research/onchain_cryptoquant.py`
- new sync scripts:
  - `scripts/quant_research/provider_leaf_sync_helpers/sync_cryptoquant_stablecoin_history.py`
  - `scripts/quant_research/provider_leaf_sync_helpers/sync_cryptoquant_reflexivity_history.py`
- new host-side external root:
  - `%LOCALAPPDATA%\EnhengClaw\onchain_cryptoquant\`

### Data products

1. `onchain_cryptoquant/stablecoin_supply_daily.csv`
2. `onchain_cryptoquant/stablecoin_exchange_flows_daily.csv`
3. `onchain_cryptoquant/reflexivity_market_daily.csv`
4. `onchain_cryptoquant/latest_sync_summary.json`

---

## 3.2 Phase 2: Build fused M3.2 feature panel

### Goal

Join the raw Alchemy Ethereum stablecoin panel with CryptoQuant aggregate series into a single daily research panel.

### Deliverable

- new builder module:
  - `src/enhengclaw/quant_research/onchain_m3_2_features.py`
- output:
  - `artifacts/quant_research/onchain/m3_2_feature_panel_1d.csv`

### Join policy

- join on UTC day
- preserve provider-level provenance columns
- keep raw provider fields and derived feature columns separate

---

## 3.3 Phase 3: Admission and cycle research

### Goal

Turn the fused panel into real candidate factors.

### Deliverables

- `MF-13` factor report
- `MF-14` factor report
- residual-vs-`lsk3` admission report
- if successful, strategy shape test:
  - `regime gate`
  - `small-cap sleeve multiplier`
  - `short-side veto`

---

## 4. Exact data to fetch

## 4.1 Alchemy layer

Use the current Alchemy path as the Ethereum raw lane baseline.

Keep or extend:

- `USDT`
- `USDC`
- `DAI`

Current raw fields already include:

- `mint_amount`
- `burn_amount`
- `net_issuance_amount`
- `exchange_inflow_amount`
- `exchange_outflow_amount`
- `exchange_netflow_amount`
- `whale_to_exchange_amount`
- `exchange_to_whale_amount`
- `issuer_to_exchange_amount`
- `bridge_inflow_amount`
- `bridge_outflow_amount`
- `labeled_transfer_share_amount`

### Alchemy role in this plan

Alchemy is the truth layer for:

- Ethereum stablecoin issuance impulse
- entity-specific anomaly investigation
- coverage auditing
- local PIT-safe replay with explicit label snapshots

---

## 4.2 CryptoQuant stablecoin layer

Start with the following endpoint families:

### Supply / issuance

- `stablecoin/network-data/supply`

Pull at least:

- `supply_total`
- `supply_circulating`
- `supply_minted`
- `supply_burned`
- `supply_issued`
- `supply_redeemed`

### Flow intensity

- `stablecoin/network-data/tokens-transferred`
- `stablecoin/network-data/addresses-count`

### Exchange dry-powder state

- `stablecoin/exchange-flows/reserve`
- `stablecoin/exchange-flows/inflow`
- `stablecoin/exchange-flows/netflow`

Recommended initial token scope:

1. Start with the live-verified token ids on the current CryptoQuant endpoint surface:
   - `usdt_eth`
   - `usdc`
   - `dai`
   - `tusd`
2. Treat chain-specific aliases as empirical, not assumed:
   - `usdc_eth` and `dai_eth` currently return `400 invalid token`
   - token naming is mixed across chain-suffixed and non-suffixed ids
3. Then expand to the highest-impact additional stablecoin routes available on your CryptoQuant plan, with priority on:
   - non-Ethereum USDT supply routes, especially any verified `TRON` / non-ETH route
   - any chain that materially changes aggregate stablecoin liquidity

We should not assume multi-chain aggregation until the available token universe is verified from the live API.

---

## 4.3 CryptoQuant reflexivity layer

For `MF-14`, use market-level series first, not per-altcoin fantasies.

Start with:

- BTC exchange inflow / outflow / netflow
- ETH exchange inflow / outflow / netflow
- BTC or market SOPR-family metrics
- where available, short-term / long-term holder realized-profit state

Recommended interpretation:

- `exchange inflow / reserve up` for majors:
  risk-off / profit-taking pressure
- `stablecoin reserve / inflow up`:
  dry powder or volatility setup, depending on venue split
- `SOPR < 1` with improving stablecoin inflow:
  possible reflexive washout / recovery setup

---

## 5. Proposed file layout

### Host-side raw stores

- `%LOCALAPPDATA%\EnhengClaw\onchain_stablecoin_ethereum\`
- `%LOCALAPPDATA%\EnhengClaw\onchain_cryptoquant\`
- `%LOCALAPPDATA%\EnhengClaw\onchain_stablecoin_tron\`

### New local files

- `onchain_cryptoquant/stablecoin_supply_daily.csv`
- `onchain_cryptoquant/stablecoin_exchange_flows_daily.csv`
- `onchain_cryptoquant/reflexivity_market_daily.csv`
- `onchain_stablecoin_tron/daily_aggregates.csv`

### Derived panel

- `artifacts/quant_research/onchain/m3_2_feature_panel_1d.csv`

Current verified panel consequence:

- panel date coverage: `2024-05-01` -> `2026-04-30`
- decision-date coverage: `2024-05-02` -> `2026-05-01`
- `tronscan_tron_flow_days = 730`
- `m3_2_panel_ready_days = 124` still reflects the narrower Alchemy + CryptoQuant overlap rather than the full raw-lane history

---

## 6. Candidate factors to build first

Do not try to build ten factors at once. Start with five.

## 6.1 MF-13 family

### F-S1 `stablecoin_supply_impulse_7d`

Aggregate 7d growth in `supply_issued - supply_redeemed`, z-scored.

Expected use:
- regime multiplier
- small-cap risk-on sleeve activation

### F-S2 `stablecoin_exchange_dry_powder_5d`

Stablecoin reserve growth plus inflow acceleration into exchanges.

Expected use:
- market-wide risk-on gate
- candidate overlay on alt sleeves

### F-S3 `alchemy_issuer_to_exchange_impulse_3d`

Ethereum raw `issuer_to_exchange_amount` burst from Alchemy, normalized by trailing transfer volume.

Expected use:
- fast event-like supply shock detector
- complementary to slow CryptoQuant aggregates

## 6.2 MF-14 family

### F-R1 `btc_eth_exchange_pressure_spread`

BTC and ETH exchange netflow / reserve stress signal.

Expected use:
- market risk gate

### F-R2 `reflexive_stress_reversal_state`

Combine:

- weak / sub-1 SOPR regime
- falling major-asset exchange pressure
- improving stablecoin inflow / reserve backdrop

Expected use:
- post-washout regime gate

---

## 7. Landing shapes

The most likely successful landing shape is **not** a new full cross-sectional base score.

Priority order:

1. `regime gate`
2. `small-cap sleeve multiplier`
3. `short-side veto or reduced exposure`
4. only then, consider direct score integration

Why:
- these signals are mostly market-level or sleeve-level
- they are better at deciding when to lean in or back off than ranking 90 names every day

---

## 8. PIT and research safety policy

This lane must explicitly separate PIT-safe and not-fully-PIT-safe components.

### Treat as relatively PIT-safe

- Alchemy raw transfer ingestion
- local address-label snapshots with `as_of_date`
- completion markers such as `is_full_day` and `fetch_status`

### Treat as research-grade but not strict PIT

- CryptoQuant exchange-flow aggregates

Policy:

- use CryptoQuant for daily or slower research horizons
- mark its rows with provider metadata
- default to `T+1` effect in any event-like backtest using these aggregates
- do not use CryptoQuant exchange aggregates as the sole truth source for intraday causality claims

---

## 9. Implementation order inside this repo

1. Add env resolution helper for `Crypto_Quant_API` / `CRYPTOQUANT_API_KEY`
2. Add `onchain_cryptoquant.py`
3. Ship stablecoin supply sync
4. Ship stablecoin exchange-flow sync
5. Ship reflexivity sync
6. Build fused M3.2 feature panel
7. Run Stage 0 event study
8. Run `G1/G3/G6`
9. If passed, test `regime gate` first

---

## 10. Concrete next engineering task

The next coding task should be:

**wire CryptoQuant stablecoin supply + exchange-flow sync into the repo first, before any factor research.**

That means:

- provider auth resolver
- client wrapper
- dated daily CSV cache
- sync summary artifact
- minimal smoke test

Only after that should we start admission work.

### Status update: 2026-05-02 implementation checkpoint

- Phase 1 is now complete enough for research:
  - `onchain_cryptoquant.py` shipped
  - default-root CryptoQuant sync succeeded
  - fused panel builder shipped:
    - `src/enhengclaw/quant_research/onchain_m3_2_features.py`
    - `scripts/quant_research/build_m3_2_feature_panel.py`
- First fused output is live at:
  - `artifacts/quant_research/onchain/m3_2_feature_panel_1d.csv`
- First admission pass is live at:
  - `artifacts/quant_research/factor_reports/2026-05-02/m3_2_mf13_mf14_admission_report.json`
- First MF-14 regime-overlay A/B is live at:
  - `artifacts/quant_research/factor_reports/2026-05-02/mf14_regime_gate_ab_diagnostic.json`

Important reality check:

- the current live-verified CryptoQuant stablecoin token coverage in this repo is now:
  - full `supply` coverage: `usdt_eth + usdc + dai + tusd + usdt_trx + usdt_omni`
  - full `exchange-flow` coverage: `usdt_eth + usdc + dai + tusd`
- `usdt_trx` and `usdt_omni` are currently **supply-only** in the production sync because CryptoQuant's stablecoin flow sub-endpoints are not uniformly valid for those routes
- `usdc_eth` and `dai_eth` returned `400 invalid token` on the current API surface, so chain naming is not uniform
- the fused `m3_2_feature_panel_1d` now starts at `2024-05-01`, decision dates start at `2024-05-02`, and `m3_2_panel_ready` still begins with `124` ready days on the narrower Alchemy + CryptoQuant overlap
- all current MF-13 conclusions should still be read as **partial stablecoin coverage**, because the lane now has verified non-ETH USDT supply but still lacks non-ETH USDT exchange-flow completion

Current research state:

- rerunning the admission family on the broader 6-token supply set preserves and slightly strengthens the core read:
  - `MF14_sell_pressure_defensive_gate_v1` is the clearest positive-sign winner at `h5d` with `G1 = +0.0834`, `G6 = +0.0734`, `G3 = pass`
  - `MF14_capitulation_rebound_idio_gate_v1` is now also a formal positive-sign strict-pass at both `h5d` and `h10d`
  - `MF13_flow_rotation_gate_v1` and `MF13_flow_idio_gate_v1` still strict-pass with **negative empirical sign**
  - `MF13_supply_beta_gate_v1` still fails on both horizons
- the new `USDT_TRX` raw lane now produces the first positive-sign `MF-13` trigger candidates:
  - `MF13_tron_flow_impulse_defensive_beta_gate_v1`: strict-pass at `h5d` (`G1 = +0.0803`, `G6 = +0.0996`, `G3 = 1.00`, `11` active timestamps) and also strict-pass at `h10d` (`G1 = +0.0409`, `G6 = +0.0499`)
  - `MF13_tron_flow_impulse_idio_gate_v1`: strict-pass at `h5d` (`G1 = +0.0765`, `G6 = +0.1008`, `G3 = 1.00`, `11` active timestamps), but fails at `h10d`
  - `MF13_tron_speculative_heat_defensive_beta_gate_v1`: very sparse but strong strict-pass at both horizons (`h5d G1 = +0.1107 / G6 = +0.0489`, `h10d G1 = +0.2028 / G6 = +0.1078`) on only `3` active timestamps
- interpretation:
  - the first useful non-ETH `MF-13` read is not “more smooth stablecoin growth,” but **extreme `USDT_TRX` flow states acting as a triggered cross-sectional gate**
  - the cleanest early shape is `defensive beta when TRON USDT flow impulse / speculative heat is extreme`
  - the main risk has shifted from sign ambiguity to **trigger sparsity**
- converting `MF14_sell_pressure_defensive_gate_v1` and `MF14_capitulation_rebound_idio_gate_v1` into `regime gate / sleeve multiplier` overlays still does **not** improve the current `v6_h10d` baseline:
  - both overlays finish `no_material_change` on walk-forward Sharpe
  - both are directionally worse on execution-layer `test_sharpe / test_net_return`
- converting the same MF-14 states into local `cross-sectional gate` score families also does **not** improve the parent:
  - formal A/B is recorded in `artifacts/quant_research/factor_reports/2026-05-02/mf14_cross_sectional_gate_increment_diagnostic.json`
  - all three variants (`sell_beta`, `sell_mid_short`, `rebound_idio`) finish `no_material_change` on `walk_forward_median_oos_sharpe = 2.832`
  - all three lower execution-layer `test_net_return` by about `-0.0132` and `test_sharpe` by about `-0.336`
- converting the lead TRON-aware `MF-13` state into a `regime-aware gate / sleeve multiplier` also does **not** improve the current `v6_h10d` parent:
  - formal A/B is recorded in `artifacts/quant_research/factor_reports/2026-05-02/mf13_tron_regime_gate_ab_diagnostic.json`
  - `alpha_ontology_regime_gating_v2_mf13_tron_flow_impulse_v1` validation-passes but finishes `no_material_change` on `walk_forward_median_oos_sharpe = 2.832`
  - execution metrics are worse than baseline (`delta_test_net_return = -0.0132`, `delta_test_sharpe = -0.3357`, `delta_test_max_drawdown = +0.0187`)
  - interpretation: the TRON multiplier is too broad / too active to preserve the parent strategy's existing risk budget
- converting the same TRON-aware state into a local `cross-sectional gate` score family also fails to transmit the admission edge:
  - formal A/B is recorded in `artifacts/quant_research/factor_reports/2026-05-02/mf13_tron_cross_sectional_gate_increment_diagnostic.json`
  - `xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d` stops at `fast_reject_failed` with blocker `factor_evidence_lite_failed`
  - lite walk-forward metrics remain flat versus baseline (`walk_forward_median_oos_sharpe = 2.832`, `loss_window_fraction = 0.3125`), while `test_net_return` and `test_sharpe` weaken to the same degree as the regime-aware overlay
  - interpretation: this lane now has a clean non-ETH `MF-13` admission winner, but that edge still does not survive translation into the mother strategy

---

## 11. Success criteria

We should call this lane successfully unlocked only if all of the following are true:

1. CryptoQuant daily caches are reproducible and refreshable.
2. Alchemy and CryptoQuant can be joined on UTC day with explicit provenance.
3. At least one `MF-13` factor passes `G1/G3/G6`.
4. At least one `MF-13` or `MF-14` feature improves a strategy in a natural landing shape:
   - regime gate
   - sleeve multiplier
   - short-side exposure control

If the data sync works but none of the candidate factors pass admission, then the lane is data-complete but alpha-incomplete.
