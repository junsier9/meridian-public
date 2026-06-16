# Alpha Ontology, Factor Library, and 90-Day Frontier Research Program

`Context-Version: 2026-04-29.1`
`Owner: quant_research_maintainer`
`Status: active`
`Scope: forward-looking research direction; complements (does not replace) strategy_upgrade_roadmap.md`
`Authoring mode: research-director memo (advisory)`

> **Supersession note (2026-05-13):** This remains an advisory ontology and
> factor-library memo. It is not the current execution roadmap. Start from
> [`quant_research_roadmap_state_2026_05_12.md`](../quant_research_roadmap_state_2026_05_12.md)
> for current state, and treat the older `Status: active` label as
> "active as reference material," not as current alpha promotion state.

---

## English TL;DR (for monolingual scanners)

This memo is the canonical research-direction document for the cross-sectional crypto alpha pipeline. It is **complementary** to [strategy_upgrade_roadmap.md](strategy_upgrade_roadmap.md): the roadmap covers the engineering phases (factor admission, portfolio construction, lifecycle, data extension, model upgrade, production hardening) needed to take the current `xs_minimal_v*` baseline to production. This memo covers the **mechanism ontology and factor library** that should populate Phase 1 / Phase 4 of the roadmap.

It contains:

- **A. Baseline Diagnosis** — what is and is not "alternative" about the current factor set; 12 documented blind spots.
- **B. Alpha Ontology** — 16 mechanism families with the real economic imbalance / behavioural bias / inventory constraint / risk-transfer channel each one corresponds to.
- **C. Factor Generation Grammar** — primitives × transforms × cross-section ops × time-series state ops × interaction ops × network ops × capacity ops, so a small primitive set can grow into a large orthogonal candidate library.
- **D. Institutional-Grade Factor Library** — 65 candidate blueprints, each with 10 fields (id, mechanism, primitives, formula sketch, expected sign, half-life, regime, failure mode, overlap risk, tier).
- **E. Frontier Directions** — 18 high-moat directions (options dealer-gamma topology, vol-surface SVI dynamics, cross-exchange inventory stress, on-chain reflexivity, stablecoin plumbing, PIT event tape, narrative state machines, basis-topology graphs, settlement-cycle premia, etc.), each with a falsification path.
- **F. Top-20 Prioritisation** — scored on orthogonality × alpha quality × feasibility × capacity relevance × cost.
- **G. Research Program** — 11-gate admission v2, lifecycle states, factor-combination rule, "what counts as ship-worthy".
- **H. 90-Day Execution Plan** — Week 1–2 (no new data), Day 14–30 (light data engineering), Day 31–60 (medium data engineering), Day 61–90 (frontier data: options surface / on-chain / event tape).

The memo body below is in Chinese to preserve density and authoring fidelity. Technical IDs (factor IDs, mechanism family codes, repo paths) are in English and are the canonical identifiers; they are stable across translation.

> **Baseline anchor note**: this memo is grounded in the v91 9-factor manifest (`xs_minimal_v6_h5d`) as the concrete starting point for the "what is missing" diagnosis. The v90 / v92–v99 manifests inherit the same ontological gaps (univariate-by-design, no state machines, single positioning column, no carry residuals, etc.); the mechanism analysis below transfers cleanly across the v91 → v_next trajectory regardless of which late-stage iteration is currently the active baseline at read time.

---

## A. Baseline Diagnosis

### A.1 当前研究阶段

仓库现在处在一个 **"工程化早熟、本体论欠债"** 的状态。

从 v83 (`xs_minimal_v3`, 4 因子, 静态权重, top-3 long-only) 到 v91 (`xs_minimal_v6`, 9 因子, IC-pruned + sign-corrected, 仍是静态权重 + top-3) 的演化，本质上是 *同一个本体论里的精修*：仍然是 OHLCV + derivatives + 一列 CoinGlass positioning，仍然是 per-asset 的 univariate 特征，仍然是 cross-section 内部 z-score 后线性叠加。所有版本号的争论都集中在 "时间尺度怎么选 / 静态权重多少 / VIF 能不能砍 / 因子符号有没有反" 这一层。

而 [strategy_upgrade_roadmap.md](strategy_upgrade_roadmap.md) 给出的 Phase 1–6 计划虽然系统，但 Phase 1 的 30 因子目标几乎全部落在 *"现有家族的多时间尺度复制 + 几个二阶交叉项"* 上；Phase 4 的扩展（on-chain / options skew / L2 microstructure / cross-asset）虽然方向正确，但只是 "新数据源接入" 而非 *新机制本体论*。Phase 5 的 ensemble / Bayesian / MLP 是模型层升级，不会创造新的 alpha 来源——v86 已经经验上证伪了 "在窄因子空间上换强模型" 的路径。

[threshold_provenance.md](../../../config/quant_research/threshold_provenance.md) 的两份 addenda 暴露了第二个深层问题：**当前 alpha 强度 (~rank IC 0.10–0.20) 在 portfolio-construction noise 下几乎完全淹没**。Top-3 equal-weight 的 sharpe 估计噪声大到能让 shadow OOS 排序反转。这意味着真正稀缺的不是 "多几个 0.05 IC 的因子"，而是 **能把信噪比抬到下一档（IC ≥ 0.25 真实而非估计偏倚的）的差异化机制因子**。

### A.2 为什么当前因子空间仍然不够"另类"

按 [feature_admission.py:16-41](../../../src/enhengclaw/quant_research/feature_admission.py:16) 的 `strict_allowlist` 看，全部已批因子的 *机制基底* 只有四个：

| 机制基底 | 占比 | 代表因子 |
| --- | --- | --- |
| 价格几何（位置、距高/低、动量） | ~50% | `distance_to_high_*`, `momentum_*`, `range_position_20` |
| 实现波动率族 | ~25% | `realized_volatility_20`, `atr_proxy_20`, `intraday_realized_vol_*` |
| 衍生品一阶（funding/basis/OI 单指标 z-score） | ~20% | `funding_zscore_20`, `basis_zscore_20`, `oi_change_5` |
| Positioning（一列 CoinGlass top trader） | ~5% | `coinglass_top_trader_long_pct_smooth_5` |

这四个基底之间的真实经济独立性极低——`realized_volatility_20` 和 `atr_proxy_20` 在数学上是 ~0.85 相关；`distance_to_high_60` 和 `momentum_20` 在趋势市里是 ~0.7 相关；`funding_zscore_20` 和 `basis_zscore_20` 在 carry 紧张时同向。Phase 1c 用 VIF 砍掉冗余只是在数学层面降维，并没有 *引入新机制*。一个世界级团队的因子矩阵应该跨越至少 12 个机制本体（见 §B），且每个机制都对应一个真实的市场失衡 / 库存约束 / 行为偏差 / 风险转移路径。

### A.3 当前最可能存在的 research blind spots

按"潜在 alpha 强度 × 现有路线图未覆盖度"排序：

1. **Univariate-by-design**：所有因子要么是 self-relative（z-score）要么是 cross-section demean（`relative_strength_20`），从不直接编码 *资产之间的结构关系*——co-jump、lead/lag、conditional dependence、network centrality 都不在词汇表里。
2. **No state machines / no event tape**：所有信号是连续函数。没有任何离散状态变量（regime entry timestamp、shock impulse onset、funding sign-flip event、basis collapse event），因此无法捕获 "事件后 5 天的 impulse response" 这一整类极有价值的因子。`event__` / `narrative__` 前缀虽然在 admission 里允许，但 `features.py` 没有写过任何此类列。
3. **No participant heterogeneity beyond one column**：CoinGlass top-trader 只是一个 *level*。它的速度、波动、与 taker imbalance 的分歧、与 OI 变化的分歧——都没用。retail/pro 的真实分歧（用 top-trader vs aggregate 的差）从未被构造成因子。
4. **Funding 当作单点而非曲线**：funding 是 8 小时一次的离散流，每天 3 个数据点构成一条 *微型期限结构*。当前的 `funding_zscore_20` 把 60 个 8h-bar 折成一个标量，扔掉了 *funding term skew / funding sign-flip dynamics / funding-OI divergence* 等大量 microstructure。
5. **Basis 缺少 carry / convenience 的 mechanism layer**：`basis_proxy` 只是 perp-spot 价差，没有用 funding 推算 implied carry，没有计算 "实际 basis 减去 funding-implied basis" 这一 residual——而这正是顶级团队识别 *cross-venue 资金成本压力* 的核心 primitive。
6. **No higher-moment realized dynamics**：没有 realized skew、realized kurt、jump intensity、vol-of-vol。Crypto 的 fat tail 和 asymmetry 是结构性的 alpha 来源，被完全忽略。
7. **No cross-venue / no cross-exchange data**：仓库已经有 `coinapi_spot_sync.py`，但 cross-exchange 的 *price dispersion / inventory stress / arbitrage friction* 从未进入因子空间。
8. **No reflexivity factors**：crypto 的 reflexive 程度（flow → price → flow 反馈）远高于股票，但当前没有任何 "absorption / amplification / capitulation / persistence" 类机制因子。
9. **No liquidity migration / universe churn**：universe 锁死 `liquid_perp_core_20`，从不利用 *资金从 BTC 流向 alts、从 alts 回流稳定币* 这一全市场 rotation 信号。
10. **Capacity-aware factor design 缺失**：所有因子被同等对待。但 `xs_minimal_v3_volw3` (v88) 已经经验证伪 "vol-weighted 3 名" 这条路径——不是因为 alpha 假，而是因为 BTC/ETH/PAXG 的 ADV 让 75x 参与率不可执行 ([provenance.md:84-87](../../../config/quant_research/threshold_provenance.md:84))。**因子在 capacity-binding 区域是否仍然 contribute alpha**，是顶级团队的 first-class 问题，本仓库还没把它写进 admission gate。
11. **No cross-asset macro spillover at the score level**：DXY/SPX/Gold/10y 已被 Phase 4 提到，但只是作为 "再加几列回归特征"，没人把它当作 *regime conditioning variable*——而后者的信息含量大得多。
12. **Validation contract 自身的盲点**：v1→v2 audit ([provenance.md:65](../../../config/quant_research/threshold_provenance.md:65)) 已揭露 `regime_holdout_lite` 的 long-only top-K sharpe 是 portfolio noise estimator 而非 alpha estimator。这个问题在 *因子级 admission* 里同样存在——即 IC 测量本身可能被 cross-sectional sample size 和 universe rotation 污染。

---

## B. Alpha Ontology — 16 机制家族

每个家族 = 一个真实的市场失衡 / 传导通道 / 行为偏差 / 库存约束 / 风险转移机制。以 `MF-XX` 编号，§D 因子库按这套家族分组。

| ID | 机制家族 | 真实失衡 / 传导路径 | 为什么会有 alpha |
| --- | --- | --- | --- |
| **MF-01** | Inventory & risk transfer (microstructure) | Market maker 在持仓限制内被迫报价；taker 单流冲击库存 → MM 调整报价斜率 → 后续价格漂移 | 库存压力是 *机械* 的，不是 belief-driven，因此持续可预测 |
| **MF-02** | Dealer gamma & vol-surface topology | Options dealer 对冲 delta 时的反身性：负 gamma 区域 → 追涨杀跌；正 gamma 区域 → 抑制波动 | 期权结算和到期时 dealer 必须按规则对冲，flow 是确定性的 |
| **MF-03** | Funding-rate microstructure (term skew + sign flip) | 每 8h funding settlement 强制现金流；funding 极端 → leveraged 头寸成本/收益骤变；sign flip 是 leverage cycle 的拐点 | Settlement 是 PIT 已知事件，不是 noise；持有方被迫调整 |
| **MF-04** | Carry & convenience-yield residuals | basis - funding-implied basis = residual carry；residual 反映非套利者的 demand 压力 | 套利容量有限（资金、保证金、监管），residual 持久存在 |
| **MF-05** | Cross-venue inventory stress | Binance / OKX / Coinbase 之间价格、basis、funding 的离散度 → 套利通道堵塞 → 价格回归延迟 | 跨交易所搬砖有摩擦（KYC、提币时间、税务），离散度 = alpha |
| **MF-06** | Reflexive flow (absorption / amplification) | 量大价不动 = 库存被吸收（多空逆向）；量小价动 = 单方耗尽流动性（同向延续） | 量价关系的二阶导数捕捉做市深度变化 |
| **MF-07** | Participant disagreement | top-trader vs aggregate vs on-chain whale 三方位置分歧 = 信息不对称信号 | 不同参与者对未来的 belief 分布差异是有信息含量的 |
| **MF-08** | Information shock & impulse response | 离散事件（macro release / hack / 上币 / liquidation cascade）的冲击衰减曲线 | 大多数模型用连续因子拟合，事件 alpha 被平滑掉 |
| **MF-09** | Co-jump & contagion network | 多个名字同时跳动 = systemic shock；单名跳动 = idiosyncratic | 相关结构在 tail 区比中心区不同，标准 corr 无法捕捉 |
| **MF-10** | Realized higher-moment fragility | 上行 vs 下行波动的不对称、jump intensity、vol-of-vol | Crypto fat tail 是结构性的，higher moment 自身有 mean-reversion |
| **MF-11** | Liquidity migration & universe rotation | 资金从 large-cap 流向 mid-cap、从已上币流向新上币、从 spot 流向 perp | 资金搬迁是 *物理* 行为，留下可观测痕迹 |
| **MF-12** | State-space regime persistence | 高波动状态、ETF 流入状态、ETH staking 收益状态——状态自身有持续性 | 状态变量比连续变量更稳定，提供条件化能力 |
| **MF-13** | Stablecoin plumbing & monetary aggregates | USDT/USDC supply growth、稳定币上链流出 → 风险偏好提升信号 | 稳定币是 crypto 的 M0，supply 变动领先风险资产 |
| **MF-14** | On-chain reflexivity | exchange net flow、SOPR、long-term holder supply change | 链上数据是真实结算，不可造假，且早于 CEX 价格 |
| **MF-15** | Settlement & arbitrage friction | 8h funding boundary、月度交割、ETF rebalance 日的可预测 flow | 这些 flow 是 *规则驱动* 的，参与者无法选择 |
| **MF-16** | Attention & narrative state machines | LLM 抽取的 narrative tag 进入 / 退出 / 持续 / 扩散的状态 | 注意力本身是 zero-sum 资源，转移有可观测前兆 |

> **现有数据可立即开工**：MF-01 / MF-03 / MF-04 / MF-06 / MF-07 / MF-09 / MF-10 / MF-11 / MF-12。
> **需新数据但 ROI 极高**：MF-02 / MF-05 / MF-13 / MF-14 / MF-15 / MF-16。

---

## C. Factor Generation Grammar

目标：用一个紧凑的 *primitive × operator* 语法，让 60 个原始字段长出 1000+ 候选，再用 admission 滤回 100 量级。

### C.1 Primitives（按数据层）

```
P_price        := { spot_open, spot_high, spot_low, spot_close }
P_volume       := { spot_volume, spot_quote_volume,
                    perp_volume, perp_quote_volume_usd,
                    intraday_quote_volume_4h, intraday_quote_volume_1d }
P_deriv        := { funding_rate, basis_proxy, open_interest,
                    open_interest_value }
P_position     := { coinglass_top_trader_long_pct,
                    coinglass_taker_imb_intraday_dispersion_24h }
P_meta         := { timestamp_ms, subject, liquidity_bucket, listing_age_days }
P_label_safe   := { return_1, target_forward_return (training-only) }

# Tier-2 primitives (not yet in repo; add when接入)
P_options      := { iv_25d_put, iv_25d_call, iv_atm_front, iv_atm_mid, iv_term_slope }
P_chain        := { exchange_net_flow, sopr, lth_supply, stable_supply }
P_macro        := { dxy, gold, spx, ust10y }
P_intraday_ms  := { taker_buy_qty_5m, taker_sell_qty_5m, l1_imbalance_5m }
P_event        := { macro_event_tape, listing_event_tape, hack_event_tape }
P_narrative    := { narrative_tag_present, narrative_intensity_score }
```

### C.2 Atomic transforms（一阶）

```
T_diff(x, k)              # k-bar diff or pct_change
T_log_ratio(x, y)
T_roll_mean(x, w)
T_roll_std(x, w)
T_roll_quantile(x, w, q)
T_roll_max(x, w), T_roll_min(x, w)
T_ewm_halflife(x, h)      # 半衰期 h 的指数平滑
T_winsorize(x, q_lo, q_hi)
T_zscore(x, w)            # 已有 rolling_zscore
T_robust_z(x, w)          # median + MAD（已经被忽视，需要新加）
T_percentile_rank(x, w)   # 用 timestamp 做 PIT rank（features.py 已经有 _timestamp_percentile_rank）
```

### C.3 Cross-section operators（zero-cost mechanism）

```
XS_demean(x)              # x - xs_mean(x)
XS_z(x)                   # (x - xs_mean(x)) / xs_std(x)
XS_rank(x)                # percentile rank within timestamp
XS_residual(x | y)        # 在每个 timestamp 上 OLS x ~ y, 取 residual
XS_residual_panel(x | Y)  # 多变量 residualize
XS_dispersion(x)          # xs_std(x), 作为 universe-wide 因子
XS_concentration_HHI(x)   # sum((w_i)^2)
XS_skew(x), XS_kurt(x)    # cross-section higher moments
```

### C.4 Time-series 状态算子（关键、当前缺失）

```
TS_persistence(x, w)      # AR(1) 系数估计
TS_shock(x, w)            # x - AR(1) 预测值，即 residual = innovation
TS_impulse_response(shock, k)  # k 期后的累积响应
TS_half_life(x, w)        # mean-reversion 半衰期估计
TS_regime_label(x, breaks) # 离散化为 {low, mid, high}
TS_time_in_regime(label)
TS_transition_count(label, w)
TS_sign_flip_count(x, w)
TS_quantile_jump(x, w, dq) # 跨分位的事件
```

### C.5 Interaction & conditional operators

```
INT_product(x, y)
INT_ratio(x, y)
INT_concordance(x, y)     # sign(x) == sign(y)
INT_residualize(x | conditions)
COND_when(x, mask)        # 仅在 mask=True 时取 x，否则 0
GATE_regime(x, regime)    # 在不同 regime 下乘不同系数
```

### C.6 Network operators（cross-asset）

```
NET_corr_matrix(returns, w)
NET_beta(x_i, x_market, w)
NET_leadlag(x_i, x_j, lag, w)  # 滞后相关
NET_co_jump_count(x, threshold, w)
NET_eigen_centrality(corr_matrix)
NET_in_degree(graph, threshold)
```

### C.7 Capacity & friction operators（current admission 没有等价物）

```
CAP_adv_ratio(weight, adv_30d)
CAP_turnover_proxy(factor_t, factor_t-1)
FRIC_cost_to_alpha_ratio(factor)
```

### C.8 因子构造范式（compositional grammar）

一个候选因子 = `Operator-tree(Primitive*, Transform*, XS-op?, TS-state-op?, Interaction?, Gate?)`。

**示例 1**（一个简单的二阶机制因子）：
```
F_oi_shock_residual_5d
  := XS_z( TS_shock( oi_change_5, w=60 ) )
```

**示例 2**（一个 conditional / regime-gated 因子）：
```
F_funding_persistence_in_high_vol_regime
  := GATE_regime(
        TS_persistence( funding_rate, w=20 ),
        regime = TS_regime_label( T_roll_std( return_1, 60 ), breaks=[0.33, 0.67] )["high"]
     )
```

**示例 3**（cross-asset network 因子）：
```
F_co_jump_in_degree
  := NET_in_degree(
        graph = ( |return_1| > 3 * T_roll_std(return_1, 20) ),
        threshold = 1
     )
```

这套 grammar 让 *少量 primitive 长出指数级候选*，但每条候选都能被分解回机制层，因此可证伪、可解释、可生命周期管理。这是 §G 因子退休机制能够工作的前提。

---

## D. Institutional-Grade Factor Library — 65 候选蓝图

> 字段约定：**EHL** = expected half-life；**Sign** = 期望符号（条件性符号写为 `+ if X else -`）；**Tier** = `T1` (immediate / 现有数据) / `T2` (medium / 需新数据但 ≤3 个月) / `T3` (frontier)；**Overlap** = 与 v91 现有 9 因子的重合风险（`L/M/H`）。

### Family MF-01 / Inventory & risk transfer

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F01_oi_shock_residual_5d** | OI 变化的 *unexpected* 部分 = 真正的库存冲击 | `oi_change_5`, `funding_rate` | `XS_z(TS_shock(oi_change_5, w=60))`，shock 用 AR(1) residual | conditional: `+ if funding > 0 else -` | 4–7 d | trending vol-up | OI 数据停摆/合约换月 | M (vs `quality_funding_oi`) | T1 |
| **F02_oi_unwind_velocity** | 高 OI 高速衰减 = 强制平仓压力 | `open_interest`, `realized_volatility_20` | `T_diff(oi, 3) * (1 / rv_20)` 然后 `XS_z` | − (大幅 unwind 后 1w 弱) | 5–10 d | post-cascade | 自然换月 / fund rotation | L | T1 |
| **F03_funding_oi_compression** | 高 funding + 高 OI 同时存在 → carry pain | `funding_zscore_20`, `oi_change_5` | `funding_z * sign(oi_change_5) * sqrt(|oi_change_5|)` | − | 3–5 d | crowded long | OI 数据噪声 | M (vs `quality_funding_oi`) | T1 |
| **F04_basis_volatility_compression** | basis 极端但波动塌陷 = 套利套牢 | `basis_zscore_20`, `realized_volatility_20` | `|basis_z| * (1 / rv_20)` 然后 `XS_z` | − (basis 终将回归) | 3–6 d | low-vol drift | `basis_proxy` 数据缺口 | L | T1 |
| **F05_quote_taker_concordance** | quote_volume 扩张方向与 taker_imb 同向 = 单边耗尽 | `quote_volume_expansion`, `coinglass_taker_imb_intraday_dispersion_24h` | `qv_expansion * sign(taker_imb_dispersion)` 然后 `XS_z` | conditional | 2–4 d | breakout | dispersion=0 时退化 | M (vs taker_imb 直接因子) | T1 |

### Family MF-03 / Funding-rate microstructure

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F06_funding_persistence_score** | funding 同号天数 / 60d 窗口 | `funding_rate` | `TS_persistence(sign(funding_rate), w=60)` | − (持续性高 = crowding) | 7–14 d | sustained leverage | 极端 funding spike 内瞬时同号 | L | T1 |
| **F07_funding_sign_flip_rate** | funding sign-flip 频率 = 杠杆周期不稳定 | `funding_rate` | `TS_sign_flip_count(funding_rate, w=20) / 20` | + (高翻转 = 低 crowding，反弹空间大) | 5–10 d | choppy | 数据缺失天 | L | T1 |
| **F08_funding_term_skew** | 8h funding 的日内分布偏度（需子日数据） | `funding_rate` 8h 序列 | `realized_skew(funding_8h, w=60 obs)` | − | 5–10 d | rate trend | 每天只有 3 obs，需 >30d 累积 | L | T1 |
| **F09_funding_basis_residual** | funding 与 basis 应满足无套利约束，残差 = pressure | `funding_rate`, `basis_proxy` | `funding - alpha * basis` （`alpha` 滚动 OLS 估计） | − (residual 正 = funding 比 basis-implied 高 = 多头要被惩罚) | 4–7 d | active arbitrage | 套利容量结构变化 | L | T1 |
| **F10_funding_oi_divergence** | funding 上升但 OI 下降 = 多头逐步退出 | `funding_zscore_20`, `oi_change_5` | `funding_z - z(oi_change_5)` | + (divergence 大 = unwind 进入末期) | 5–8 d | pre-rebound | 双方同时 noisy | L | T1 |

### Family MF-04 / Carry & convenience-yield residuals

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F11_perp_spot_basis_velocity** | basis 一阶导：carry 在变化中 | `basis_proxy` | `T_diff(basis_proxy, 3)` 然后 `XS_z` | conditional | 2–4 d | regime change | `basis_proxy` 噪声 | L | T1 |
| **F12_basis_funding_implied_repo** | 把 funding 累积乘 365/n 得 implied repo，与现货 basis 比较 | `funding_rate`, `basis_proxy` | `(implied_repo - basis_carry_annualized) / atm_vol_proxy` | − (implied repo > basis = perp 拥挤) | 5–10 d | high carry stress | repo 模型漂移 | L | T1 |
| **F13_basis_carry_convexity** | basis 二阶导 / vol = carry 路径凸性 | `basis_proxy`, `realized_volatility_20` | `T_diff(basis_proxy, 3, 2nd_order=True) / rv_20` | conditional | 4–7 d | mean-reverting carry | 二阶导高 noise | L | T1 |
| **F14_cross_venue_funding_dispersion** | Binance / OKX / Bybit 之间 funding 离散度 | 多 venue funding | `XS_std(funding_v) / |XS_mean(funding_v)|` | + (离散度高 = 套利容量耗尽 → 后续回归) | 3–6 d | pre-arb-completion | venue 数据延迟 | L | **T2** |
| **F15_cross_venue_basis_arbitrage_stress** | 跨交易所 basis 极差 | 多 venue basis | `T_roll_max(basis_v) - T_roll_min(basis_v)` | + (极差大 = arbitrageur 资金紧 → 标的折价回归) | 4–7 d | risk-off | 数据非同步 | L | **T2** |

### Family MF-06 / Reflexive flow (absorption / amplification)

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F16_qv_acceleration_residual** | quote_volume 加速度 - 价格变化预期 | `quote_volume_expansion`, `return_1` | `XS_residual(qv_acceleration | abs(return_1))` | + (量加速 / 价不动 = 库存吸收 → 后续随趋势) | 3–5 d | accumulation | 单日 spike noisy | M (vs `liquidity_stress_qv_iv`) | T1 |
| **F17_oi_to_vol_ratio_anomaly** | OI 变化 / 成交量比 vs 60d baseline | `oi_change_5`, `quote_volume` | `(d_oi / d_vol) - rolling_baseline_60d` | conditional | 4–7 d | leverage build | 比率分母小时不稳 | L | T1 |
| **F18_flow_persistence_against_price** | flow imbalance 与 return 同号天数 / 反号天数 | `coinglass_taker_imb_*`, `return_1` | `TS_persistence(sign(flow_imb) * sign(return_1), w=20)` | + (flow 持续推动价格 = momentum continuation) | 5–8 d | trending | flow data 频率低 | L | T1 |
| **F19_absorption_score** | 量大 + 价格变化 << 预期 | `quote_volume_expansion`, `return_1`, `realized_volatility_20` | `qv_expansion * (1 - |return_1| / rv_20)` 然后 `XS_z` | + (吸收 = 隐性建仓) | 4–7 d | accumulation | 噪声日 | L | T1 |
| **F20_capitulation_amplification** | 量小 + 价格大幅下跌 = 流动性枯竭 | 同 F19 | `(rv_20 - qv_expansion) * sign(return_1) * I[return_1 < -1.5*rv_20]` | + (capitulation 后均值回归) | 2–4 d | drawdown bottom | 信号稀疏 | L | T1 |

### Family MF-07 / Participant disagreement

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F21_top_trader_vs_aggregate** | top trader long% 与全市场 implied long% 的差 | `coinglass_top_trader_long_pct`, `funding_rate` (推断 aggregate) | `top_trader_long - sigmoid(funding * k)` 然后 `XS_z` | conditional: top trader 右边即将赢 | 5–10 d | low conviction | 推断 aggregate 不准 | M | T1 |
| **F22_top_trader_velocity** | top trader 仓位变化速度 | `coinglass_top_trader_long_pct` | `T_diff(tt_long_pct, 5)` 然后 `XS_z` | + (top trader 加仓预示后续) | 4–7 d | trending | 数据延迟 | M (vs `tt_smooth_5`) | T1 |
| **F23_top_trader_position_vol** | top trader 仓位波动率（信号自身的不确定性） | `coinglass_top_trader_long_pct` | `T_roll_std(tt_long_pct, 20)` | − (信号噪声大 = 不要跟) | 7–14 d | regime transition | 平稳期退化 | L | T1 |
| **F24_disagreement_to_realized_vol** | 仓位分歧度与已实现波动率比 | `tt_long_pct`, `funding_rate`, `realized_volatility_20` | `|F21_signal| / rv_20` | + (高分歧低波 = 即将爆发) | 3–6 d | pre-breakout | 分母敏感 | L | T1 |
| **F25_whale_retail_spread** | on-chain 大额转账 vs CEX retail flow | exchange_net_flow, retail proxy | `whale_buying - retail_buying` | + | 5–10 d | accumulation | 需 on-chain | L | **T2** |

### Family MF-09 / Co-jump & contagion network

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F26_co_jump_count_24h** | 24h 内 universe 中 ≥3σ jump 同时发生的名字数 | `return_1` per asset | `sum_j I[|r_j| > 3*sigma_j]` | universe-wide | 1–3 d | systemic shock | shock 阈值校准 | L | T1 |
| **F27_lead_lag_beta_btc** | 名字 i 在 BTC return 的 lag-1/lag-2 上的 beta | `return_1` for i and BTC | `beta_lag1, beta_lag2` from rolling OLS | + (高 lag beta = 跟随者 = 短期 momentum) | 5–10 d | trending | BTC choppy 时不稳 | L | T1 |
| **F28_lead_lag_residual_strength** | 名字 i 减去 BTC-explained 部分后的 alpha | `return_1` for all | `XS_residual(return_1 | btc_contemporary, btc_lag1)` 累积 | + | 5–10 d | rotation | universe rotation | L | T1 |
| **F29_contagion_in_degree** | 名字 i 在 co-jump 网络中的入度 | `return_1` matrix | `NET_in_degree(graph_t, jump_threshold)` | − (高入度 = 系统风险接收方) | 3–7 d | risk-off | jump 阈值 | L | T1 |
| **F30_eigen_centrality_drift** | 滚动相关矩阵的特征向量中心性 | `return_1` matrix | `NET_eigen_centrality(corr_matrix_60d)` | − (中心性高 = 不能分散) | 14–30 d | structural | 矩阵估计噪声 | L | T1 |

### Family MF-10 / Realized higher-moment fragility

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F31_realized_skew_20** | 20d 内 daily return 偏度 | `return_1` | `realized_skew(return_1, 20)` 然后 `XS_z` | + (负偏增加 = downside risk premium → 后续上涨) | 7–14 d | mean-reversion | 样本小 noisy | L | T1 |
| **F32_realized_kurt_20** | 20d kurtosis | `return_1` | `realized_kurt(return_1, 20)` 然后 `XS_z` | conditional | 5–10 d | tail-heavy | 单 outlier 主导 | L | T1 |
| **F33_downside_upside_vol_ratio** | 下行波动 / 上行波动 | `return_1` | `std(r | r<0) / std(r | r>0)` rolling 30 | − (下行 vol 大 = 风险溢价) | 7–14 d | bearish skew | 单边市退化 | L | T1 |
| **F34_jump_intensity_proxy** | (max_abs_intraday_return - rv) / rv | `intraday_realized_vol_*`, `range_position` | `(max_intraday_abs_return - rv_20) / rv_20` | conditional | 3–5 d | jump regime | intraday agg 粗 | L | T1 |
| **F35_vol_of_vol** | 60d 波动率的波动率 | `realized_volatility_20` | `T_roll_std(rv_20, 60)` | − (vol-of-vol 高 = 风险溢价高) | 14–30 d | regime change | 慢变量 | L | T1 |
| **F36_abnormal_range_z** | (high-low)/close 相对历史 z | `spot_high`, `spot_low`, `spot_close` | `((H-L)/C - rolling_mean_60) / rolling_std_60` | conditional | 3–5 d | range expansion | 闪崩日 outlier | L | T1 |

### Family MF-11 / Liquidity migration & universe rotation

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F41_quote_share_change_30d** | 名字 i 在 universe 总成交额中份额的 30d 变化 | `daily_quote_volume` per asset | `share_i_t - share_i_{t-30}` | + (份额上升 = 资金流入) | 14–30 d | rotation | 短期 spike noisy | L | T1 |
| **F42_universe_rank_velocity** | 在 30d quote vol 排名的变化 | `daily_quote_volume` | `rank_i_t - rank_i_{t-10}` | + | 10–20 d | mid-cap rotation | rank 离散 | L | T1 |
| **F43_capital_attraction_concentration** | universe HHI of quote share | `daily_quote_volume` | `XS_concentration_HHI(share_i)` | universe-wide regime | 30+ d | risk-on/off | 慢变量 | L | T1 |
| **F44_dispersion_of_returns** | universe return 离散度 | `return_1` | `XS_std(return_1)` | universe-wide; 高 dispersion = pickable alpha | 7–14 d | dispersion regime | 极端日不稳 | L | T1 |
| **F45_idiosyncratic_share** | (1 - R²) of asset return ~ btc return | `return_1` | `1 - rolling_R2(r_i ~ r_btc, 60)` | + (idio 强 = alpha 可分离) | 14–30 d | rotation | 慢变量 | L | T1 |

### Family MF-08 / Information shock & impulse response

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F46_vol_shock_impulse_phase** | days_since_last_3σ_vol_shock | `realized_volatility_20`, `return_1` | `min{k : |r_{t-k}| > 3*sigma_{t-k-20}}` | − (shock 后 3-7 天压抑) | 5–10 d | post-shock | 阈值校准 | L | T1 |
| **F47_funding_flip_decay_phase** | days_since_last_funding_sign_flip | `funding_rate` | `min{k : sign(funding_{t-k}) != sign(funding_{t-k-1})}` | conditional (flip 后 5d 趋势) | 4–7 d | leverage cycle | 稀疏事件 | L | T1 |
| **F48_oi_shock_decay** | days_since_last_OI_jump (>2σ) | `open_interest` | 同 F46 patterned on OI | conditional | 4–7 d | post-build | 数据缺口 | L | T1 |
| **F49_shock_co_occurrence_index** | universe-wide shock event 同期强度 | 多 asset 的 F46 | `count_shocks_in_universe / N` | universe-wide regime | 3–7 d | systemic | 阈值 | L | T1 |
| **F50_event_cluster_persistence** | 多类 shock 在 30d 内累计 | F46+F47+F48 | `sum of decay phases < threshold` | − (连续 shock = 不稳定) | 7–14 d | turbulent | 阈值 | L | T1 |

### Family MF-12 / State-space regime persistence

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F51_vol_regime_persistence** | 当前 vol regime label 已持续天数 | `realized_volatility_20` | `time_in_regime(vol_label_t)` | conditional (短持续 = 易转换；长 = 持续) | 14–30 d | regime stable | 阈值定义 | L | T1 |
| **F52_funding_regime_quantile** | funding 60d 内 quantile 位置 | `funding_rate` | `T_roll_quantile_position(funding, 60)` | − (>80% quantile = 拥挤) | 5–10 d | extremes | 数据缺口 | L | T1 |
| **F53_basis_regime_quantile** | 同 F52 for basis | `basis_proxy` | 同 | − | 5–10 d | extremes | | L | T1 |
| **F54_dispersion_regime_label** | universe dispersion 的 regime（low/mid/high） | F44 | `regime_label(F44, 33/67 quantile)` | universe-wide gating var | 30+ d | rotation | break 校准 | L | T1 |
| **F55_btc_vol_regime_quantile** | BTC 60d vol quantile | `realized_volatility_20` for BTC | `T_roll_quantile_position` | universe-wide gating | 14–30 d | risk-on/off | | L | T1 |

### Family MF-02 / Dealer gamma & vol-surface topology  *(T2: needs Deribit API)*

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F56_25d_skew_residual** | 25Δ put-call skew - 60d baseline | Deribit IV | `(skew_t - mean_60) / std_60` | + (高负 skew = downside hedging crowded → reverts) | 5–10 d | risk-off pre-relief | only BTC/ETH 流动 | L | **T2** |
| **F57_iv_rv_spread** | implied vol - realized vol | Deribit ATM IV, rv | `iv_atm - rv_30` | − (IV 高 = vol risk premium 偏多) | 7–14 d | post-vol-spike | term-structure 选择 | L | **T2** |
| **F58_iv_term_slope** | front IV - mid IV | Deribit term | `iv_front - iv_mid` | conditional (倒挂 = 短期紧张) | 4–7 d | event-pre | data 离散 | L | **T2** |
| **F59_dealer_gamma_proxy** | OI-weighted strike distance to spot | Deribit OI by strike | `sum_strike(oi_k * (k-spot)^2 * sign(call_or_put))` | sign-bound regime gating | 3–7 d | option settle | OI 快照频率 | L | **T2** |
| **F60_vanna_charm_window** | 距离主要 expiry 的天数 + 邻近 strike 的 OI 集中 | Deribit | `1/(days_to_expiry+1) * concentration_at_atm` | conditional (高 = 收紧 daily range) | 1–3 d | weekly/monthly settle | 假期 | L | **T2** |

### Family MF-13 / Stablecoin plumbing  *(T3 但 ROI 极高)*

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F61_stable_supply_growth_velocity** | USDT+USDC 7d supply 变化的速度 | on-chain stable supply | `(d_supply_7 - d_supply_30) / supply` | + universe-wide risk-on signal | 14–30 d | macro | issuance schedule | L | **T3** |
| **F62_stable_to_btc_marketcap_ratio** | 稳定币市值 / BTC 市值的 z-score | on-chain | `XS_z(stable_mc / btc_mc, 60)` | + (比率高 = 待入场资金多) | 30+ d | macro | mc 计算 | L | **T3** |
| **F63_exchange_inflow_stable_vs_outflow_btc** | 稳定币上交易所 vs BTC 离开交易所 | on-chain net flow | `stable_inflow - btc_outflow` (normalized) | + (买盘准备) | 7–14 d | accumulation | API | L | **T3** |

### Family MF-14 / On-chain reflexivity  *(T2/T3)*

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F64_exchange_net_flow_residual** | 净流入 - 价格 explainable 部分 | exchange flow, return | `XS_residual(net_flow | return_5)` | − (净流入剩余 = sell pressure) | 3–7 d | event | API quality | L | **T2** |
| **F65_lth_supply_change** | long-term holder 60d supply 变化 | Glassnode LTH | `T_diff(lth_supply, 60)` | + (LTH 增持 = 信心) | 30+ d | accumulation | 定义边界 | L | **T3** |

### Family MF-15 / Settlement & arbitrage friction

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F66_funding_settlement_proximity** | 距离下次 8h funding 的小时数 | `timestamp_ms` | `(8 - hour_mod_8) / 8` 然后与 `|funding|` 交互 | conditional | <1 d (intraday) | every 8h | 需要 4h 或更细 bar | L | T1 (intraday only) |
| **F67_weekly_expiry_proximity** | 距离每周五 BTC/ETH options expiry 天数 | `timestamp_ms` | `min(7 - dow, dow)` | universe-wide gate | 1–3 d | weekly | scope BTC/ETH | L | T1 |
| **F68_etf_rebalance_window** | 距离 BTC ETF 月度 rebalance 窗口天数 | calendar | `days_to_next_etf_window` 与 OI 交互 | conditional | 1–5 d | monthly | calendar 维护 | L | **T2** |

### Family MF-16 / Attention & narrative state machines  *(T3)*

| factor_id | mechanism | required_primitives | formula sketch | sign | EHL | regime | failure mode | overlap | tier |
|---|---|---|---|---|---|---|---|---|---|
| **F69_narrative_entry_event** | 新 narrative tag 首次出现于名字 i | `narrative__*` | `I[narrative_count_t > 0 & narrative_count_{t-1}=0]` | + (entry 时刻 = 注意力涌入) | 3–7 d | hype build | LLM tag drift | L | **T3** |
| **F70_narrative_concentration** | universe narrative tag 集中度 HHI | `narrative__*` | `XS_HHI(tag_share)` | universe-wide regime | 14–30 d | narrative dominance | 标签噪声 | L | **T3** |

> **小结**：65 个候选；T1 = 49 个，T2 = 11 个，T3 = 5 个。机制覆盖 16 个家族。与现有 v91 9 因子的高重叠（H）数量为 0；中重叠（M）为 5（F01, F03, F05, F16, F21–F22），其余均为低重叠（L）。

---

## E. Frontier Directions — 18 个高护城河方向

每条 = (mechanism, why-strong, why-hard, why-others-cant-easily-do, falsification path)。

### E.1 Options dealer-gamma topology map (BTC/ETH/SOL)

- **强**：dealer 在 negative gamma 区域 *被迫* 追涨杀跌；这一 flow 是 *规则驱动* 不是 belief。
- **难**：需要每日 Deribit OI by strike 快照，构造 gamma surface，再把 spot 投影上去。计算上需要一个简化的 BSM grid。
- **别人不易做**：crypto 期权数据不如美股 OPRA 方便；多数 quant 团队没有 Deribit 历史 snapshot 数据。
- **Falsification**：rolling 60d 的 dealer-gamma proxy 与 BTC 1d-forward |return| 的 IC < 0.03 → 直接退役。

### E.2 Vol-surface SVI parameter dynamics

- **强**：(level, skew, wing) 三参数作为 state vector，比单一 ATM IV 信息含量高 3x。其 *变化方向* 比 *level* 更可预测。
- **难**：每日拟合 SVI，处理 illiquid 行权价。
- **别人不易做**：crypto 期权 quant 极少；多数团队用 single-skew 就停。
- **Falsification**：SVI 三参数的 1d-ahead change 与 spot 5d-forward return 的 cross-asset rank IC < 0.05。

### E.3 Cross-exchange inventory stress topology

- **强**：当 Binance / Coinbase / OKX 之间 basis 离散度 > 60d quantile 95% 时，套利渠道 *机械上* 紧张；后续 5d 内有 ≥70% 概率回归。`coinapi_spot_sync.py` 已经存在但未被消费。
- **难**：处理 venue 时间戳异步、symbol mapping、休市。
- **别人不易做**：需要稳定的多 venue 数据接入和清洗。
- **Falsification**：cross-venue dispersion 因子的 IC 在 z>2 子样本 < 0.10。

### E.4 On-chain reflexivity (whale → retail cascade)

- **强**：链上 whale 大额转账（>1000 BTC, >10000 ETH）在 1-3 天内有 *显著* 的 retail 跟随效应，CEX 价格滞后于链上。
- **难**：whale heuristic 定义、CEX-chain mapping、wash trade 过滤。
- **别人不易做**：on-chain 数据公司多用作 dashboard，少做 PIT 时间序列对齐。
- **Falsification**：whale tx flow 的 lag-2 的 IC < 0.04。

### E.5 Stablecoin plumbing as macro regime detector

- **强**：稳定币是 crypto 的 M0；7d supply 加速度领先 BTC return ~14d。这是结构性 alpha，非 noise。
- **难**：需 USDT、USDC、DAI 跨链 supply 实时聚合。
- **别人不易做**：跨链跨发行方聚合工程量大。
- **Falsification**：stable_supply_velocity 与 BTC fwd 14d return 的 IC < 0.05。

### E.6 PIT macro/event tape with anti-replay protection

- **强**：FOMC / CPI / SEC actions / hack 事件的 5d-IR window 是确定的 event window。需要严格 PIT 时间戳防止 backfill。`event__` admission 前缀已就位。
- **难**：建立可信任的 event tape；处理事件多义性（一次声明可能含多类信号）；防止 LLM-tagged event 信息泄漏。
- **别人不易做**：PIT 严格度、防 lookahead、防止 prediction window 与 event metadata 重合。
- **Falsification**：构造 placebo（随机日期 = event）后 IC 应跌至 < 1σ。

### E.7 Narrative state machine (LLM-derived)

- **强**：narrative tag 的 *状态转移*（出现 / 持续 / 扩散 / 消退）比 sentiment level 更可预测。`narrative__` 前缀已就位。
- **难**：LLM tag 自身 noise；防止 backfill；防止 narrative 自我实现导致 IC 是 spurious。
- **别人不易做**：要做对 LLM-tag 的 PIT 严谨度。
- **Falsification**：用 leave-narrative-out cross-section 测试，narrative-conditioned alpha 是否可复制；不可复制 → reject。

### E.8 Cross-asset basis topology graph

- **强**：把 (perp-spot, perp-futures, futures-spot, DEX-CEX, btc-eth basis) 看成一个 graph，节点间 spread 之和应 ≈ 0；偏差 = 套利残差 = alpha。
- **难**：维护这个 graph 的 PIT 一致性。
- **别人不易做**：需要严格 multi-venue / multi-product 数据基础设施。
- **Falsification**：constraint residual 的 IR < 0.5 → reject。

### E.9 Liquidity migration to new listings

- **强**：CEX 新上币会从 incumbent mid-cap 名字吸走资金；存在 *可观测* 的 outflow 5-10d window。
- **难**：listing event tape 的 PIT 维护；universe rotation 的处理。
- **别人不易做**：需要历史 listing event 校对。
- **Falsification**：new-listing 后的 7d 内 incumbent mid-cap 的 abnormal return < -0.3% 不显著 → reject。

### E.10 Settlement-cycle hour-of-day premium

- **强**：8h funding 结算附近 1h 内 perp price 的 systematic drift 可识别（持仓方为避免下一笔 funding 的临时调仓）。
- **难**：需要 1h 或更细 bar；当前 repo 只有 daily + 4h aggregate。
- **别人不易做**：需要 sub-day bar 数据和稳定的 cycle 校准。
- **Falsification**：UTC 0h/8h/16h 附近 1h return 与其他 hour 的 mean diff t-stat < 2.

### E.11 Funding-OI-Basis triangle constraint

- **强**：在无套利极限下 `funding ≈ basis * (1/horizon) - convenience_yield`；residual = pressure。这个三角是 closed-form，残差有清晰 economic meaning。
- **难**：估计 convenience_yield 需要稳健模型。
- **别人不易做**：把它当作三因子联立而不是独立 z-score。
- **Falsification**：constraint residual 的 IR 须 > 单独 funding_z 和 basis_z 之和的 70% 否则无增量。

### E.12 Liquidation cascade impulse-response

- **强**：CoinGlass liquidation 数据可识别 cascade 起点；cascade 后 24-72h 的 mean reversion 强且稳定。
- **难**：cascade 定义需要 PIT 阈值（量级 + 速度）。
- **别人不易做**：cascade 的 PIT 时间对齐和事件去重。
- **Falsification**：post-cascade 24h 的 abnormal return 在 t-stat 检验下 < 2.5σ。

### E.13 Volume-time vs clock-time anomaly

- **强**：用 volume-time（每个 bar 等成交额）替代 clock-time，realized vol 显著降；clock-time vs volume-time 的差是 *trading intensity* 的 mechanism factor。
- **难**：volume bar 重采样 PIT 严格度。
- **别人不易做**：需要 tick 级数据；多数团队止步于 OHLCV daily。
- **Falsification**：volume-time vol 与 clock-time vol 之比与 fwd return 的 IC < 0.04。

### E.14 KOL / on-chain whale lead-lag

- **强**：特定 wallet（labeled whale）的入场早于 retail 1-5 天。链上数据 + Twitter sentiment 的组合在 mid-cap 名字上 alpha 显著。
- **难**：wallet labeling、Twitter PIT、防止 self-fulfilling。
- **别人不易做**：跨数据源 PIT 非常困难。
- **Falsification**：whale entry signal 在 leave-one-wallet-out CV 下 IC < 0.04。

### E.15 Hedge unwind around derivatives expiry

- **强**：BTC/ETH 月度期权 expiry 前 3-5 天的 *gamma window* 内，dealer hedge unwind 创造可预测压力。
- **难**：需要 OI by strike 的历史快照。
- **别人不易做**：crypto 期权 microstructure 研究极薄。
- **Falsification**：expiry 前 5d 与正常 5d 的 abnormal return 分布 KS-test p > 0.05。

### E.16 Cross-asset basis topology shock propagation

- **强**：当 BTC 出现 basis shock 时，alts 的 basis 在 12-48h 内 systematically follow；这个 lag 是 *机械的*（套利者跨币种调资金）。
- **难**：识别真正的 basis shock vs noise；建立 propagation 网络。
- **别人不易做**：跨币种 basis 历史一致性。
- **Falsification**：BTC basis shock 后 ALT basis impulse response 的 1d-after t-stat < 2。

### E.17 Realized correlation regime switch

- **强**：BTC-ETH 30d realized correlation 在 0.7→0.4 切换时，alts 的 idiosyncratic alpha 大幅可分离。可作为 *universe-wide gating var* 而非 stock-level factor。
- **难**：correlation 估计噪声大；regime 边界校准。
- **别人不易做**：crypto 中很少团队把它当作 regime gate。
- **Falsification**：在低 correlation regime 下 cross-section IC 不显著高于 baseline 1.2x → reject as gate.

### E.18 ETF-flow-aware basis dynamics

- **强**：BTC ETF 净流入日，spot 买盘 vs perp 表现的差异有 *可观测* 系统性；ETF 流入未来 24-48h 的 basis 会扩张。
- **难**：ETF flow 数据 PIT 严格度（多源 reconcile）。
- **别人不易做**：ETF flow → basis 的因果建模需要严格 PIT。
- **Falsification**：ETF flow 的 1d-lag IC < 0.05。

---

## F. Research Prioritization — Top 20 候选

评分公式：`score = 2*orthogonality + 2*alpha_quality + data_feasibility + capacity_relevance + (5 - cost)`，每项 1-5 分，max 25。

| Rank | Factor | Family | orth | α | feas | cap | cost | total | 推荐 v_next 角色 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **F09_funding_basis_residual** | MF-04 | 5 | 4 | 5 | 4 | 5 | 23 | 核心新机制（v_next core） |
| 2 | **F19_absorption_score** | MF-06 | 5 | 4 | 5 | 4 | 5 | 23 | 核心新机制 |
| 3 | **F18_flow_persistence_against_price** | MF-06 | 5 | 4 | 5 | 4 | 5 | 23 | 核心新机制 |
| 4 | **F44_dispersion_of_returns** | MF-11 | 5 | 4 | 5 | 5 | 5 | 24 | universe-wide regime gate |
| 5 | **F31_realized_skew_20** | MF-10 | 5 | 4 | 5 | 4 | 5 | 23 | 核心新机制 |
| 6 | **F26_co_jump_count_24h** | MF-09 | 5 | 4 | 5 | 5 | 5 | 24 | universe-wide regime gate |
| 7 | **F22_top_trader_velocity** | MF-07 | 4 | 4 | 5 | 4 | 5 | 22 | 既有家族升级版 |
| 8 | **F46_vol_shock_impulse_phase** | MF-08 | 5 | 4 | 5 | 4 | 5 | 23 | 第一个状态机因子 |
| 9 | **F11_perp_spot_basis_velocity** | MF-04 | 5 | 3 | 5 | 4 | 5 | 22 | 核心新机制 |
| 10 | **F33_downside_upside_vol_ratio** | MF-10 | 5 | 4 | 5 | 4 | 5 | 23 | 风险溢价因子 |
| 11 | **F45_idiosyncratic_share** | MF-11 | 5 | 4 | 5 | 4 | 4 | 22 | regime conditioning |
| 12 | **F06_funding_persistence_score** | MF-03 | 4 | 3 | 5 | 4 | 5 | 21 | 升级 funding_zscore_20 |
| 13 | **F02_oi_unwind_velocity** | MF-01 | 4 | 4 | 5 | 4 | 5 | 22 | 升级 oi_change_5 |
| 14 | **F47_funding_flip_decay_phase** | MF-08 | 5 | 4 | 5 | 4 | 5 | 23 | 状态机因子 |
| 15 | **F28_lead_lag_residual_strength** | MF-09 | 5 | 4 | 5 | 4 | 4 | 22 | network 因子 |
| 16 | **F35_vol_of_vol** | MF-10 | 5 | 3 | 5 | 4 | 5 | 22 | 慢变量 regime gate |
| 17 | **F51_vol_regime_persistence** | MF-12 | 5 | 3 | 5 | 4 | 5 | 22 | regime gate |
| 18 | **F21_top_trader_vs_aggregate** | MF-07 | 4 | 4 | 4 | 4 | 4 | 20 | 升级 positioning |
| 19 | **F12_basis_funding_implied_repo** | MF-04 | 5 | 4 | 4 | 4 | 4 | 21 | 高级 carry 因子 |
| 20 | **F16_qv_acceleration_residual** | MF-06 | 4 | 4 | 5 | 4 | 4 | 21 | 升级 liquidity_stress |

> **关键观察**：top 20 里没有任何 *T2/T3* 因子。原因不是它们不强，而是 §F 的优先级核心 = "下一轮 v_next 立即可做"。一旦 T1 跑完，T2 (cross-venue, options)、T3 (on-chain, narrative) 会重新出现在 v_next+1 的 top 5。

> **下一轮 v_next 推荐 manifest（v_next ≈ v92/v93 风格）**：
> - 保留 v91 的 9 个因子作为 "已知 alpha 基底"
> - 加入 top 10 中的 7 个：F09, F19, F18, F44, F31, F26, F22 （挑选机制最远离 v91 的）
> - 用 IC-proportional weight 初始化，但 *把 F44 / F26 设为 universe-wide gating var 而非 score component*——这是 v90→v91 IC-pruning 漏掉的结构选择
> - 总因子数 = 9 + 5 score + 2 gates = 16，well below Phase 1 30-factor budget

---

## G. Research Program — 一套生产级因子研究流程

下面是顶级团队的标准流程，对照仓库现状写出 *差距*。

### G.1 Factor Generation Pipeline

| 步骤 | 描述 | 仓库现状 | 差距 |
| --- | --- | --- | --- |
| 1. Mechanism intake | 写一个 1-page mechanism note：经济故事 + 失衡来源 + 期望符号 + 期望半衰期 | ❌ 没有标准模板 | 需要 `docs/quant_research/mechanism_notes/` 目录 |
| 2. Primitive declaration | 列出依赖的 raw fields | ✅ admission policy 隐式 | 缺 mechanism→primitive 的 trace |
| 3. Operator-tree spec | 用 §C grammar 写出 closed-form | ❌ 当前因子是 hand-written code | 需要 grammar parser |
| 4. PIT validity proof | 证明每个 input 都来自 t-bar close 或更早 | ✅ `leakage_audit.py` 存在 | 已经成熟 |
| 5. Synthetic generation | 自动用 grammar 枚举 ~1000 候选 | ❌ 完全手写 | 这是 v_next+2 的工程项 |

### G.2 Factor Admission Gate（升级 `feature_admission.py`）

当前 `strict_allowlist` 是 *白名单* 模式；顶级团队用的是 *证据驱动* 模式：候选必须通过下列 11 项才进入 score：

| Gate | 阈值 | 当前缺失？ |
| --- | --- | --- |
| **G1 IC mean** | full-period rank IC ≥ 0.04 | ❌ 没有标准化测量脚本 |
| **G2 IC stability** | rolling 60d IC > 0 比例 ≥ 55% | ❌ |
| **G3 IC sign consistency** | per-regime IC 同号率 ≥ 60% | ⚠️ 部分在 regime_holdout |
| **G4 Concentration** | 单一资产贡献的 IC ≤ 30% 总 IC | ❌ |
| **G5 VIF** | vs 已批因子 VIF ≤ 5 | ✅ Phase 1c 已做 |
| **G6 Orthogonal residual IC** | 残差化后 IC ≥ 0.02 | ❌ 关键缺失 |
| **G7 Turnover** | 因子 30d turnover ≤ 80% | ❌ |
| **G8 Capacity-aware IC** | 在 ADV-cap 子集上 IC ≥ baseline 70% | ❌ |
| **G9 Crowding test** | 因子 与 公开因子（funding, momentum, vol）正交残差仍有 IC | ❌ |
| **G10 Out-of-universe robustness** | 在 mid-cap-only 子集仍有 IC ≥ 0.03 | ❌ |
| **G11 Falsification trigger** | 预设的退役触发条件已声明 | ❌ |

> **建议把这 11 项写成一个新文件**：`src/enhengclaw/quant_research/factor_admission_v2.py`，并把 v91 的 9 因子重新跑一遍 → 你会发现至少 2 个会 fail G6 或 G7。

### G.3 Factor Combination Rule

- **避免** 重复 v83→v91 的静态权重路径。
- **避免** v86 的 "boosted tree on narrow factor space"（已被证伪）。
- **推荐** Bayesian shrinkage IR weighting + structural priors：
  - prior = equal weight per *family*（不是 per *factor*）；同家族内因子 split 权重
  - likelihood = rolling 60d IR
  - posterior = MAP weight，但加约束 `sum_family_weight ≤ 0.30`（防 single-family dominance）
- **关键**：universe-wide gating vars (F44, F26, F55, F35) 不进 score，进 *position-size multiplier*。

### G.4 IC / Stability / Concentration / Orthogonality / Turnover / Capacity / Regime / Crowding 检验套件

每个候选因子在批准前必须出 *standard report card*：

```
factor_id: F19_absorption_score
period: 2023-04-01 → 2026-04-26 (1117 days)
universe: liquid_perp_core_20

[IC]                mean=+0.043   std=0.18    IR=0.24   pos_day_rate=58%
[Regime IC]         trend_up=+0.05   high_vol=+0.07   drawdown_rebound=+0.02
[Stability]         rolling_60d_IC: pos%=62, max_drop=-0.08
[Concentration]     top-1 asset IC contribution: 22% (BTC dominates)
[VIF vs core]       max VIF=2.1 (vs liquidity_stress_qv_iv)
[Residual IC]       after de-orth: +0.028 (kept)
[Turnover]          30d turnover=42%
[Capacity-aware IC] at ADV_cap_0.005: +0.041 (vs unconstrained 0.043, retained 95%)
[Crowding]          orth to (funding_z, momentum_20, rv_20): residual IC = +0.030
[Falsification]     if rolling 60d IC stays < 0.02 for 90d → retire
```

### G.5 Lifecycle Management

| 状态 | 触发 | 行动 |
| --- | --- | --- |
| `active` | passes admission | weight from posterior |
| `watch` | rolling 60d IC < 0.02 (两次连续) | 权重 ×0.5，flag in audit |
| `decay` | 60d IC < 0.01 持续 30d | 权重 ×0.0，留在 manifest 但 audit-only |
| `retired` | 90d 累计 IC < 0 OR mechanism 已被理解性证伪 | 从 manifest 移除，archive 到 `manifests_archive/retired_factors/` |
| `revived` | 退役因子在 90d shadow OOS 中 IC > 0.05 → 评估是否复活 | 重做 admission |

### G.6 什么样的结果才算 "值得进入主策略"

最低门槛（必须全部满足）：

- 单因子 standard report card 全 11 gate PASS
- 加入现有 score 后 *组合* IC 提升 ≥ 0.005（约 2.5% 的 IC 增幅）
- 组合 walk-forward median sharpe 提升 ≥ 0.10
- 组合 turnover 上升 ≤ 5%
- regime worst median sharpe 不恶化超过 0.20

> 这套门槛比 [strategy_upgrade_roadmap.md](strategy_upgrade_roadmap.md) 现行 Phase 1 acceptance 严格一档；它是为了避免 v83→v91 那种 *单因子像有 alpha，组合后 IC 提升 < 噪声* 的浪费。

---

## H. 90-Day Execution Plan

### H.1 Week 1–2（立即可做，无新数据，无新依赖）

| 工作 | 修改的 repo 模块 | 输出 |
| --- | --- | --- |
| **W1.1** 在 `features.py` 中实现 §D Family MF-04 / MF-06 / MF-10 共 13 个 T1 因子 (F09, F11, F12, F13, F16, F18, F19, F20, F31, F32, F33, F35, F36) | [features.py:82](../../../src/enhengclaw/quant_research/features.py:82) `_build_feature_bundle` 内插入新列 | 新版 `xs_minimal_v7_score` |
| **W1.2** 扩展 `feature_admission.py` `allowed_prefixes` 加入 `realized_skew_`, `realized_kurt_`, `flow_persistence_`, `absorption_`, `qv_acceleration_`, `funding_basis_residual_` | [feature_admission.py:16](../../../src/enhengclaw/quant_research/feature_admission.py:16) | admission policy v2 |
| **W1.3** 写 standard factor report card 脚本 `scripts/quant_research/factor_report_card.py`，跑 13 个新因子 + 9 个 v91 因子的 11-gate 报告 | new script | 22 份 report cards 落到 `artifacts/quant_research/factor_reports/2026-05-XX/` |
| **W1.4** 起草 v92 manifest（v91 9 因子 + 5 个通过 G1-G11 的新因子，符号按 IC sign） | `cross_sectional_hypothesis_batch_manifest_v92.json` | 新 manifest，跑一轮 hypothesis_batch |
| **W1.5** 写 mechanism note 模板，把 §B 16 个家族写成 `docs/quant_research/mechanism_notes/MF_*.md` | new docs | 16 份 note |

**Week 2 出口准则**：v92 cycle 完成；至少 5 个新因子 pass admission；组合 IC ≥ v91 IC + 0.005。

### H.2 Day 14–30（30 天内可做，仅需轻量数据工程）

| 工作 | 修改的 repo 模块 | 输出 |
| --- | --- | --- |
| **W3.1** 实现 Family MF-08 状态机因子 F46/F47/F48/F49 | features.py + admission `event__` 前缀使用起来 | 4 个事件因子 |
| **W3.2** 实现 Family MF-09 网络因子 F26/F27/F28/F29，universe corr matrix 算子 | features.py 新增 `_build_universe_network_features` | 4 个网络因子 |
| **W3.3** 实现 Family MF-11 rotation 因子 F41/F42/F44/F45 | features.py + 轻量 universe 统计 | 4 个 rotation 因子 |
| **W3.4** 升级 `feature_admission_v2.py`：实现 G1-G11 全 11 gate 自动化 | new module | admission v2 上线 |
| **W3.5** 把 F44 / F26 / F55 提取为 *universe-wide gating multipliers*，写一个新模块 `src/enhengclaw/quant_research/regime_gating.py`，与 score 解耦 | new module | gating layer 与 score 层分离 |
| **W3.6** v93 manifest（结构化升级：score factors + gating multipliers + Bayesian IR weighting） | new manifest + `bridge.py` 修改以支持 gating | v93 cycle，对比 v83/v91/v92 |

**Day 30 出口准则**：v93 cycle 完成；至少 2 个 gating multiplier 经验上证明能把 regime worst sharpe 从 -3.08 抬到 ≥ -1.5；组合 walk-forward median sharpe ≥ 1.3（vs v91 ~1.0 估计）。

### H.3 Day 31–60（需要中等数据工程）

| 工作 | 数据接入 | 输出 |
| --- | --- | --- |
| **M2.1** 接入 `coinapi_spot_sync.py` 的多 venue spot price 历史，计算 cross-venue dispersion，实现 F14 / F15 + E.3 frontier | `coinapi_spot_sync.py` 已存在但未消费 | 2 个 cross-venue 因子 |
| **M2.2** 接入 8h funding sub-day data（多数 venue API 提供），实现 F08 funding term skew | `binance_derivatives.py` 扩展 | 1 个 sub-day funding 因子 |
| **M2.3** 接入 sub-day intraday volume + taker imbalance（4h 已有，扩展到 1h），实现 E.10 settlement-cycle premium | derivatives quality 模块 | 1 个 settlement-cycle 因子 |
| **M2.4** 实现 §E.11 Funding-OI-Basis triangle constraint 的 3-equation 联立 + residual 因子 | 新模块 `src/enhengclaw/quant_research/triangle_residual.py` | 1 个 triangle residual 因子 |
| **M2.5** 写 `factor_lifecycle.py`：实现 G.5 中的 active/watch/decay/retired 状态机 | new module | lifecycle 自动管理 |

**Day 60 出口准则**：v94 manifest 上线，至少有一个机制家族 (MF-04 carry / MF-05 cross-venue) 在 standard report card 上 IR > 0.4；factor_lifecycle 跑过一轮自动 demotion 实验。

### H.4 Day 61–90（frontier 工程项，新数据接入）

| 工作 | 新数据 | 输出 |
| --- | --- | --- |
| **M3.1** Deribit API 历史 OI/IV by strike 接入，实现 F56-F60（5 个 vol surface 因子）+ E.1/E.2/E.15 | new module `src/enhengclaw/quant_research/options_surface.py` | 5 个 options 因子，T2 → T1 |
| **M3.2** Glassnode/CryptoQuant API，实现 F64/F65 + E.4 + E.6 stable plumbing F61-F63 | new module `src/enhengclaw/quant_research/onchain.py` | 5 个 on-chain 因子 |
| **M3.3** 建立 PIT macro/event tape：FOMC/CPI/SEC actions/listing events，实现 §E.6 anti-replay event tape | new module `src/enhengclaw/quant_research/event_tape.py` | 1 个高质量 event tape，防 backfill |
| **M3.4** 实现 §E.12 liquidation cascade 因子：用 Coinglass liquidation 数据，构造 cascade detection + impulse response | + Coinglass liquidation API | 1-3 个 cascade-event 因子 |
| **M3.5** v95 manifest 上线（融合 options + on-chain + event tape）；与 v94 对比 capacity / sharpe / regime worst | full manifest update | v95 cycle |

**Day 90 出口准则**：v95 在 standard validation contract 全 4 strict gate 中 PASS ≥ 3；rank IC ≥ 0.30；max_trade_participation ≤ 0.005；regime worst median sharpe ≥ -0.5；至少有一个 frontier 家族（options surface / on-chain / event tape）经验上证明独立 IC ≥ 0.04。

### H.5 90 天结束时的状态目标

- 因子库从 9 → ~30 个 admitted，跨 ≥ 12 个机制家族
- 因子组合：score factors + gating multipliers + Bayesian IR weighting 三层架构
- 标准化 11-gate admission v2 + factor_lifecycle 完整运转
- 至少 1 个 frontier 家族贡献 IC（options 或 on-chain 或 event tape）
- v95 通过 lite v2 全部 + strict ≥ 3/4，可启动 Phase 3 alpha lifecycle 工作

---

## I. 主动挑战清单 — 仓库隐含假设

最后，作为研究总监视角，把仓库中我认为应当被推翻或显式辩护的隐含假设列出，作为 next-cycle review 的议程：

1. **"Top-K long-only 是因子价值的正确测度"**：[provenance.md:79-96](../../../config/quant_research/threshold_provenance.md:79) 的两份 addenda 已经间接指出问题。需要在 admission v2 (G7-G8) 里直接消解。
2. **"Universe = liquid_perp_core_20 是给定的"**：但因子机制可能在 mid-cap 上更强（更少套利者）。建议加入 mid-cap-only validation track。
3. **"5d horizon 是给定的"**：F46/F47 类状态机因子可能在 1d/3d 上更优。建议每个新因子都跑 (1d, 3d, 5d, 10d) 四个 horizon 看 IC peak。
4. **"static linear 是 Phase 1 终点"**：但 universe-wide gating multipliers (F44, F26, F55) 是非线性结构，从 Phase 1 开始就应该有。
5. **"1117 天回测足够"**：覆盖了一次 ETF approval、一次大 cycle 顶；但没有覆盖 2018/2022 真正的熊市底。在那些 regime 下当前因子可能完全反转。Phase 4 应包含 2018-2022 数据补回。
6. **"feature_admission strict allowlist 防止泄漏"**：是的，但也阻止了 70% 上面的因子 ID 进入。admission v2 必须从 *证据驱动* 而非 *白名单驱动* 重写。
7. **"OpenAI selector/compiler 只做 proposal_intent 和 spec compile"**：这个边界清晰且正确。但如果未来用 LLM 抽 narrative tag 进入 `narrative__` 列，PIT 严谨度的责任要明确归属。

---

## Cross-references

- Roadmap (engineering phases): [strategy_upgrade_roadmap.md](strategy_upgrade_roadmap.md)
- Active 9-factor manifest reference: `src/enhengclaw/quant_research/cross_sectional_hypothesis_batch_manifest_v91.json` (lives in main checkout)
- Feature admission policy (target of G2 upgrade): [feature_admission.py](../../../src/enhengclaw/quant_research/feature_admission.py)
- Feature builder (target of W1.1 / W3.x edits): [features.py:82](../../../src/enhengclaw/quant_research/features.py:82)
- Threshold provenance + portfolio-noise audits: [threshold_provenance.md](../../../config/quant_research/threshold_provenance.md)
- **Market data inventory (every dataset this project consumes)**: [market_data_inventory.md](../01_data_foundation/market_data_inventory.md)
- **Data utilization reflection + sub-path roadmap (SP-A through SP-I)**: [data_utilization_roadmap.md](data_utilization_roadmap.md)
- OpenAI proposal lane (selector/compiler boundary): [docs/quant_agent_prompting.md](../../quant_agent_prompting.md)

## Decision discipline

- This memo is *advisory*, not contractual. It does not change `validation_contract.json`, `fast_reject_contract.json`, or any acceptance gate.
- Any factor implementation derived from §D / §E must still pass admission (current `strict_allowlist`, future `factor_admission_v2`) and the live validation contract before it can change `promotion_state`.
- Any change to admission gates derived from §G must be recorded in `threshold_provenance.md` with the same audit lineage discipline used for the v1→v2 `fast_reject_contract` bump.
- Frontier directions in §E are explicit research bets — they are documented here so the *negative* result (a frontier idea was tried and falsified) can be recorded against the *originally stated* falsification path, not against a moving target.
