# Quant Provider / API Registry

`Snapshot date: 2026-05-02`
`Owner: quant_research_maintainer`

This file is the canonical registry for every external data/API provider that quant research depends on, may depend on next, or has already been provisioned locally.

Use this file for three jobs:

1. Track the canonical env-var name for each provider.
2. Track which research lane or script actually consumes the provider.
3. Track whether the provider is active, optional, reserved, or only locally provisioned.

Secrets must never be written here. Only record names, scopes, status, plan requirements, and usage notes.

---

## 1. Local verification snapshot

Checked on `2026-05-02` from the current Codex shell host.

| Env var | Process scope | User scope | Machine scope | Read |
| --- | --- | --- | --- | --- |
| `ALCHEMY_API_KEY` | present | present | missing | Available to current shell and current M3.2 scripts. |
| `Crypto_Quant_API` | missing | present | missing | Provisioned at User scope. The new CryptoQuant loader now also supports Windows User-scope fallback, so research sync can still resolve it even if the current process was started before the env var appeared. |
| `CRYPTOQUANT_API_KEY` | missing | missing | missing | Alias not provisioned. |
| `TRONSCAN_API_KEY` | missing | missing | missing | Optional only. Current `USDT_TRX` aggregate sync works against public `TronScan` endpoints without it. |
| `TRON_PRO_API_KEY` | missing | missing | missing | Optional alias only. Not required by the current raw-lane implementation. |

Interpretation:
- `Crypto_Quant_API` is not missing from Windows entirely; it is already written to the User environment.
- The current Codex process still does not expose it in plain `Process` scope, but the new M3.2 CryptoQuant resolver can read the Windows User environment directly on this host.
- `Tardis_api_key` was owner-reported on `2026-06-13` after this snapshot; its current usable status is decided by the M3.1 Tardis Deribit options Phase 0 probe report, not by the older `2026-05-02` snapshot table.

---

## 2. Canonical provider inventory

| Provider | Canonical env var(s) | Auth type / plan | Current role | Current status | Primary scripts / consumers | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Binance public | none | public | Core spot/perp OHLCV lane | active | `scripts/market_data/sync_binance_ohlcv.py` | `BINANCE_API_KEY` is optional and only improves rate limits. |
| Binance optional auth | `BINANCE_API_KEY` | free exchange API key | Higher-rate public market sync | active | `sync_binance_ohlcv.py` | Not required for baseline research syncs. |
| CoinAPI | `CoinAPI` | paid or free tier | Multi-venue spot OHLCV and M2.1 cross-venue probes | active | `scripts/market_data/sync_coinapi_ohlcv.py`, `scripts/quant_research/sync_coinapi_multi_venue_spot.py` | Local naming is intentionally `CoinAPI`. |
| Coinglass | `CoinglassAPI` | paid | Derivatives panel, liquidation, orderbook, taker flow, top-trader metrics | active | `scripts/quant_research/sync_binance_derivatives_history.py` | Powers most 1h microstructure and liquidation research lanes. |
| OKX public | none | public | 8h funding history | active | `scripts/quant_research/provider_leaf_sync_helpers/sync_okx_funding_history.py` | Current funding-history lane does not need private auth. Root CLI wrapper remains at `scripts/quant_research/sync_okx_funding_history.py`. |
| OKX private | `OKX_API` | exchange API key | Reserved / future authenticated OKX endpoints | optional | none in active quant path | Kept for future deeper venue work. |
| Alchemy | `ALCHEMY_API_KEY` | paid | M3.2 Ethereum stablecoin bootstrap, Transfers API, fallback EVM RPC | active | `scripts/quant_research/sync_alchemy_stablecoin_ethereum.py`, `backfill_stablecoin_history.py` | Current on-chain lane is Ethereum-only and label-limited. |
| Provider-neutral Ethereum RPC | `ETH_RPC_URL` | provider-specific | Optional raw `eth_getLogs` backfill path | optional | `backfill_stablecoin_history.py` | Use when Alchemy Transfers is incomplete or when changing node provider. |
| Deribit public | none | public | DVOL and options-chain snapshots | active | `sync_deribit_dvol_history.py`, `sync_deribit_options_chain.py` | Current lane is public only; historical OI-by-strike still limited. |
| Tardis.dev | `Tardis_api_key` | Professional all exchanges yearly | M3.1 Deribit historical `options_chain` coverage/schema gate and F56-F60 feature panel | phase-0 probe wired; builder gated by green report | `scripts/quant_research/probe_tardis_deribit_options_surface.py`, `scripts/quant_research/build_tardis_deribit_options_surface_features.py` | Read-only CSV dataset probe and gated builder; both stream bounded `OPTIONS.csv.gz`, retain no raw vendor rows, and require the Phase 0 report to set `m3_1_tardis_options_surface_phase0_ready=true` and `feature_builder_allowed=true` before the feature panel can be built. The builder supports date ranges and computes F57 with a 30d RV join from canonical spot OHLCV; manifest/admission audit is report-only and does not mutate active manifests. |
| OpenAI | `OPENAI_API_KEY` | paid API | LLM news/event structuring for quant research | active | `process_cryptonewsdataset_llm.py`, `review_cryptonewsdataset_strong_model.py` | Used for research enrichment, not raw market data. |
| CryptoQuant | `Crypto_Quant_API` | `Professional` or `Premium` | Target M3.2 aggregated on-chain layer for MF-13 / MF-14 | phase-1 scaffold shipped, live-smoke validated | `src/enhengclaw/quant_research/onchain_cryptoquant.py`, `scripts/quant_research/provider_leaf_sync_helpers/sync_cryptoquant_stablecoin_history.py`, `scripts/quant_research/provider_leaf_sync_helpers/sync_cryptoquant_reflexivity_history.py`, `scripts/quant_research/run_quant_cryptoquant_m3_2_sync_cycle.py` | Best near-term source for stablecoin supply / reserve / inflow / netflow. Official docs note some exchange-flow data is not strict PIT. Root CLI wrappers remain at the old sync helper paths. |
| CryptoQuant alias | `CRYPTOQUANT_API_KEY` | `Professional` or `Premium` | Optional future alias for cleaner provider naming | reserved | none yet | Not currently provisioned. |
| TronScan public aggregates | none | public | Non-ETH raw stablecoin flow lane, currently `USDT_TRX` | active | `src/enhengclaw/quant_research/onchain_stablecoin_tron.py`, `scripts/quant_research/provider_leaf_sync_helpers/sync_tronscan_stablecoin_tron.py` | Provides verifiable daily aggregate flow fields (`transfer_count`, `amount_usd`, `active_address_count`, `holders`) from `TronScan` public endpoints. Root CLI wrapper remains at `scripts/quant_research/sync_tronscan_stablecoin_tron.py`. |
| TronScan optional auth | `TRONSCAN_API_KEY`, `TRON_PRO_API_KEY` | optional platform key | Higher-rate / future protected endpoints for TRON on-chain research | optional | `onchain_stablecoin_tron.py` | Current public aggregate endpoints do not require auth, but the loader accepts these headers if later provisioned. |
| Glassnode | none yet | paid | Alternative / complementary M3.2 PIT-oriented on-chain layer | candidate | none yet | Strong PIT research value; not yet provisioned. |
| Dune | none yet | free + paid API | Multi-chain stablecoin detail, balances, labels, Tron coverage | candidate | none yet | Best customizable engineering layer if we choose self-built on-chain aggregates. |
| DefiLlama | none yet | public + premium | Stablecoin macro overlays and chain allocation | candidate | none yet | Good cheap regime layer, not enough alone for entity-labeled exchange flow. |
| Nansen | none yet | paid | High-quality address/entity labeling | candidate | none yet | Best used as label enrichment, not as sole research feed. |

---

## 3. Recommended env-var conventions

Use the following names when adding or documenting credentials:

| Category | Preferred naming rule | Current examples |
| --- | --- | --- |
| Existing legacy providers | Keep the already-established local name for backward compatibility. | `CoinAPI`, `CoinglassAPI`, `OKX_API` |
| New provider tokens with existing local setup | Prefer the already-provisioned local name first; aliases are optional. | `Crypto_Quant_API` first, `CRYPTOQUANT_API_KEY` optional; `Tardis_api_key` for Tardis.dev |
| Generic runtime/model providers | Use explicit uppercase names. | `OPENAI_API_KEY`, `ALCHEMY_API_KEY`, `ETH_RPC_URL` |

Practical rule:
- When future CryptoQuant code is added, it should ideally accept both `Crypto_Quant_API` and `CRYPTOQUANT_API_KEY`, with `Crypto_Quant_API` checked first so existing local setup works unchanged.

---

## 4. Current lane-to-provider mapping

| Research lane | Minimum provider set | Why |
| --- | --- | --- |
| `M1/M2` spot + perp cross-sectional baseline | Binance public, Coinglass, CoinAPI | Core market history and derivatives panel. |
| `M2.2` OKX funding probe | OKX public | Non-Binance funding regime comparison. |
| `M3.1` Deribit surface | Tardis.dev `options_chain` plus Deribit public legacy snapshots | Tardis.dev is the new Phase 0 coverage/schema gate for historical F56-F60 construction; Deribit public remains a legacy/free snapshot accumulation path. |
| `M3.2` stablecoin plumbing bootstrap | Alchemy, local label snapshots | Current Ethereum-only Phase 0/1 implementation. |
| `MF-13 stablecoin_plumbing` production candidate | CryptoQuant or Dune + Alchemy | Need more than raw Ethereum transfers: multi-chain supply + exchange/entity flows. |
| `MF-14 onchain_reflexivity` production candidate | CryptoQuant or Glassnode, optionally Dune | Need SOPR / holder-state / exchange-flow style metrics beyond current local bootstrap. |
| `M3.3 event tape / narrative` | OpenAI + historical news corpora | Used for structured labeling, not market data sync itself. |

---

## 5. Immediate recommendations for the on-chain expansion

If we pursue `stablecoin plumbing + on-chain reflexivity` next:

1. Keep `ALCHEMY_API_KEY` as the raw-Ethereum backstop.
2. Use `Crypto_Quant_API` as the first aggregated M3.2 provider to wire.
3. Keep the `TronScan` aggregate lane for non-ETH `USDT_TRX` flow verification.
4. Do not treat CryptoQuant as the only PIT truth source.
5. If deeper customization or Tron/issuer-level routing becomes the bottleneck, add Dune next.

Why:
- Alchemy solves raw transfer access, but not cross-chain entity labeling.
- CryptoQuant is the fastest route to usable `stablecoin supply / reserve / inflow / netflow`.
- Dune is the best second leg if we decide to own the aggregation logic.

Detailed implementation plan:
- [cryptoquant_alchemy_m3_2_plan.md](cryptoquant_alchemy_m3_2_plan.md)

---

## 6. Operator validation snippet

Use this PowerShell snippet to re-check scopes without printing secrets:

```powershell
$names = 'Crypto_Quant_API','CRYPTOQUANT_API_KEY','Tardis_api_key','ALCHEMY_API_KEY','CoinAPI','CoinglassAPI','OPENAI_API_KEY'
foreach ($scope in 'Process','User','Machine') {
  Write-Output "[$scope]"
  foreach ($n in $names) {
    $v = [Environment]::GetEnvironmentVariable($n, $scope)
    if ([string]::IsNullOrEmpty($v)) {
      Write-Output "$n=<missing>"
    } else {
      Write-Output "$n=present len=$($v.Length)"
    }
  }
}
```

---

## 7. Update protocol

Whenever a provider is added, renamed, or promoted from candidate to active:

1. Update this file.
2. Update [market_data_inventory.md](market_data_inventory.md).
3. Update [.env.example](../../../.env.example) if the provider requires a new env var.
4. If code is added, document the exact loader script or module here.
5. If the provider is not PIT-safe, state that explicitly in the Notes column.

This file is the canonical home for provider/API management; `market_data_inventory.md` remains the canonical home for datasets and caches.
