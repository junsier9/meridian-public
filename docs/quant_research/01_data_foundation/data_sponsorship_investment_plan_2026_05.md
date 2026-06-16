# EnhengClaw Quant Research Lab 数据赞助与投资计划书

`版本日期: 2026-05-08`
`面向对象: 数据赞助方 / 战略投资人 / 研究合作伙伴`
`项目状态: 研究基础设施已成型，下一阶段主要瓶颈是可回放、可审计、足够深度的数据资产`

---

## 0. 一句话主张

EnhengClaw 不是在寻找一笔“买数据”的费用，而是在寻找能把数据资产转化为可审计量化研究产能的战略赞助。

我们已经完成了一个以失败关闭为核心的数字资产量化研究系统：数据先入库、特征有来源、候选策略必须经过样本外、固定集合对照、成本压力、符号留出、流动性桶一致性、覆盖率与点时安全检查。现在，项目的下一段增长不再主要受限于建模想法，而受限于历史深度、跨场所原生校验、订单簿/期权/链上粒度和可回放事件数据。

如果获得数据赞助，资金不会进入一个不可验证的黑箱。它会进入一条有明确验收标准的研究流水线：每一类数据都先证明覆盖、时间戳、点时安全和供应商一致性，再进入预注册研究，再进入严格证伪，最后才允许纸面模拟或更高层级的实盘准备。

我们的承诺很简单：

- 不把数据覆盖改善包装成 alpha。
- 不把回测收益包装成可交易收益。
- 不让任何候选绕过证伪闸门。
- 把赞助方的数据价值转化成可复现的研究报告、数据质量反馈和潜在可部署策略资产。

---

## 1. 执行摘要

### 1.1 项目已经做到什么

EnhengClaw Quant Research Lab 已经从“想法驱动的策略实验”进化为“数据治理 + 机制假设 + 严格证伪”的研究系统。项目目前具备：

| 能力 | 当前状态 | 投资意义 |
| --- | --- | --- |
| 数据目录与来源治理 | 已建立 `market_data_inventory.md`，覆盖 Binance、CoinAPI、CoinGlass、CryptoQuant、Alchemy、TRON、Deribit 等本地缓存与派生面板 | 投资人可以知道每个结论来自哪类数据，避免黑箱 |
| 研究实验框架 | 已支持 cross-sectional daily、intraday 1h、h10d、单资产和周度 proposal 流程 | 数据进来后可以直接转化成实验，而不是重新搭平台 |
| 严格验证合同 | 已有 validation contract、fixed-set comparison、promotion gate、overlay ablation、symbol/bucket blocker attribution | 过滤过拟合，不靠单次漂亮回测做决策 |
| 当前 h10d 基线 | `v5_rw_bridge_no_overlay_h10d` 是当前 h10d canonical parent，黑箱路径信心为 `high`，但仍遵循后续严格闸门 | 项目不是零起点，已有可比较的基线资产 |
| 失败闭环文化 | 多个候选被主动关闭，例如 M3.2 sidecar、SP-K 泛确认、MF-05 预一致性场所数据、MF-07 当前形态 | 证明团队不会为了“故事”牺牲研究纪律 |
| CoinGlass full-stack foundation | 2026-05-07 已形成 foundation catalog，包含微结构、ETF、链上、期权聚合等侧车状态 | 说明数据赞助能立即落地到现有架构 |

### 1.2 当前真正瓶颈

项目已经不缺“再加一个因子”的能力，真正瓶颈是以下数据缺口：

1. **历史深度不足**
   - 1h 级别 spot、futures、orderbook、liquidation、taker flow 数据不够深时，无法判断信号是否跨市场状态稳定。

2. **跨场所原生校验不足**
   - CoinAPI 可以提供多场所覆盖，但 OKX / Bybit / Coinbase 等场所仍需要 native venue trust check，否则 MF-05 venue stress 只能作为预一致性 sidecar，不能进入 alpha rerun。

3. **订单簿和成交微结构不够细**
   - 当前 MF-01 机制有证据，但组合层传导太稀疏。要判断真实可交易性，需要更细的 L2/L3、增量 order book、depth、price impact、slippage 数据。

4. **期权曲面历史不足**
   - 当前 CoinGlass options aggregate 可以支持 market gate，但缺少完整 strike/expiry/IV/OI by strike 历史，无法证明 dealer gamma、expiry pressure、skew residual 这类高护城河机制。

5. **链上实体流和稳定币流需要更完整供应商覆盖**
   - CryptoQuant、Glassnode 或同类 on-chain provider 的历史 exchange flow、stablecoin flow、entity flow 会直接影响 MF-13 / MF-14 的可证伪性。

6. **事件 tape 需要可回放**
   - 静态 narrative tag 不足以支持事件 alpha。需要带 `event_time_utc`、`event_type`、`event_direction/weight` 的 append-only temporal event tape。

### 1.3 我们希望获得什么

优先请求是数据赞助，而非单纯现金赞助。理想赞助组合：

| 赞助类型 | 具体内容 | 直接解锁 |
| --- | --- | --- |
| API / 历史数据额度 | CoinGlass、Tardis、Amberdata、Glassnode、CryptoQuant 或同等级供应商的 API key、bulk export、rate limit、历史区间 | 覆盖、深度、订单簿、链上、期权 |
| 企业级数据试用 | 90 天到 180 天 research license，含数据字典和技术支持 | 快速形成样本外研究结论 |
| 供应商工程支持 | schema 解释、历史范围确认、rate-limit white-list、批量导出 | 降低数据接入摩擦 |
| 研究合作 | 允许将匿名化数据质量反馈、方法论报告、非敏感研究摘要返回给赞助方 | 赞助方获得真实 quant use case |
| 现金数据预算 | 用于采购不可 in-kind 覆盖的数据、计算资源和研究工程 | 补齐订单簿、期权、链上和事件 tape |

### 1.4 赞助后的可交付结果

90 天内，赞助方应看到以下可验证成果：

| 时间 | 交付物 | 验收标准 |
| --- | --- | --- |
| 第 2 周 | 数据能力矩阵和供应商接入报告 | 每个 endpoint 有 schema、历史范围、rate limit、PIT 风险、样本路径 |
| 第 4 周 | Coverage Reset Report | 覆盖率、缺失原因、供应商重叠误差、native-vs-derived provenance |
| 第 6 周 | Canonical Parent Re-baseline | h10d 基线在新数据面板下的稳定性报告 |
| 第 8 周 | 1h / on-chain / options 至少两条预注册研究 lane 的 Stage 0 结果 | 每条 lane 有 pass / fail / blocked，不留模糊状态 |
| 第 12 周 | Data Sponsorship ROI Pack | 数据使用量、研究结论、失败清单、可继续投入的高 ROI lane |

---

## 2. 我们为什么值得被赞助

### 2.1 这不是一个“靠模型堆收益”的项目

许多量化项目失败，不是因为模型不够复杂，而是因为数据边界、点时安全、过拟合、成本、交易容量和样本外一致性没有被严肃处理。EnhengClaw 的优势不是某一个漂亮策略，而是一套会主动拒绝伪 alpha 的研究制度。

项目当前有三个非常可贵的特征。

第一，**研究链路可审计**。从 raw cache 到 feature panel，再到 experiment card、fixed-set comparison、alpha registry 和 promotion gate，每一步都要求保存证据。策略不是“跑出来一个 Sharpe”，而是必须解释它用了什么数据、什么时候可见、在哪些 symbol / liquidity bucket 上成立、成本压力下是否仍然成立。

第二，**失败本身被记录为资产**。项目已经把多个诱人的方向明确关闭或降级。例如：

- 泛 funding/OI crowding 不能作为 SP-K 硬确认。
- M3.2 ETF/on-chain sidecar 当前 strict falsification 失败。
- MF-05 venue concentration sidecar 因缺少 native OKX / Bybit / Coinbase concordance 被挡在 alpha rerun 之外。
- MF-07 participant disagreement 当前 daily 和 1h pivot 形态没有保留候选。
- MF-01 orderbook confirmation 行质量更好，但组合传导太稀疏。

这些不是坏消息。对投资人而言，这是风控文化和研究纪律的证据：团队知道如何停止，知道如何把负结果转化为资源配置优势。

第三，**数据一旦补齐，系统有即时吸收能力**。项目不是拿到数据后才开始搭建框架。现在已经有 provider registry、data readiness contract、sync scripts、foundation catalog、feature builders、strict falsification runner 和 promotion guard。赞助进来的数据可以直接进入明确的验收和研究路径。

### 2.2 我们已经拥有的研究资产

#### 2.2.1 h10d canonical parent

当前 h10d 研究以 `v5_rw_bridge_no_overlay_h10d` 为 canonical parent。根据 `baseline_alpha_confidence_validation.md`：

- OOS periods: `64`
- OOS window: `2023-09-02` 到 `2026-03-30`
- baseline sum of period returns: `1.095707`
- period win fraction: `0.688`
- confidence label: `high`
- checks passed: `6/6`

这个结果不是最终部署许可，而是“我们已经有一个足够严肃的比较基线”。所有新 h10d 候选都必须打败它，而不是打败一个弱基准。

#### 2.2.2 F-cascade 机制资产

`liq_cascade_recency_score_5d` 是当前项目中最重要的机制证据之一。它来自 liquidation cascade impulse-response，对 h10d 研究尤其重要。项目在 `experiment_catalog.md` 和 `threshold_provenance.md` 中记录了：

- F-cascade 在多个候选形态中表现最强。
- h10d 相比 h5d 更匹配这类多日恢复机制。
- h10d contract 经过 sqrt-scaled 校准后，F-cascade 成为当前核心比较资产之一。

这说明项目不是纯统计挖掘，而是在寻找可解释的市场微结构与状态迁移。

#### 2.2.3 数据使用与治理资产

当前本地数据覆盖已经包括：

- Binance public spot / USDM perp OHLCV。
- CoinAPI Binance spot 和多场所 spot sidecar。
- CoinGlass derivatives / extended microstructure。
- CoinGlass ETF / on-chain / options aggregate foundation sidecars。
- CryptoQuant stablecoin / exchange flow scaffold。
- Alchemy Ethereum stablecoin raw aggregate。
- TRON stablecoin aggregate。
- Deribit DVOL 和 options chain snapshot accumulation。
- 新闻 / event-state 研究 scaffold。

更重要的是，这些数据不是散落在脚本里，而是有 inventory、schema、sync registry 和更新协议。

#### 2.2.4 研究路线图资产

当前 repo 已经形成下一阶段清晰路线：

- CoinGlass full-stack data foundation 先解决数据层。
- h10d canonical parent re-baseline 先于 challenger promotion。
- true 1h feasibility 需要 canonical OHLC path。
- M3.2 on-chain / stablecoin 需要离散边界，而不是平滑 overlay。
- M3.1 options-regime 先做 market-level gate，再考虑 dealer-gamma topology。
- MF-05 venue stress 必须先通过 native venue concordance。
- MF-01 orderbook / inventory 需要解决稀疏传导。
- 事件 tape / narrative state 需要新数据源或更强 persistence definition。

这是一条可执行路线，不是愿望清单。

---

## 3. 数据瓶颈的商业解释

### 3.1 为什么数据赞助是当前最高 ROI

在量化研究中，最危险的投入是“在错误数据上优化模型”。EnhengClaw 目前的许多候选并非因为经济逻辑彻底错误而停止，而是因为现有数据无法安全区分以下问题：

- 信号是否只是单一 symbol 贡献。
- 信号是否只在 top liquidity bucket 有效。
- 订单簿信号是否因为历史太短而看起来稀疏。
- 期权信号是否只有当前快照，没有 PIT 历史。
- 跨场所价格/成交量是否来自同一供应商重打包，而非独立原生源。
- 链上 exchange flow 是否有实体标签覆盖率和历史可回放性。
- 事件信号是否有真正 event time，而不是事后标签。

这意味着继续单纯“调模型”会迅速进入低 ROI 区域。更高 ROI 的路径是先补齐数据可证伪面板，再让严格证伪系统告诉我们哪些机制真的值得投入。

### 3.2 数据赞助对应的 alpha unlock

| 数据缺口 | 当前 blocker | 赞助后可解锁研究 |
| --- | --- | --- |
| 1h spot/futures 深历史 | true 1h research 和 cross-sectional intraday 可执行性不足 | post-pump microstructure、bid replenishment、fake liquidity、settlement squeeze |
| Native multi-venue data | MF-05 只有 pre-concordance sidecar | venue-local dislocation、cross-venue confirmation、venue volume migration |
| L2/L3 order book + trades | MF-01 机制有证据但组合传导稀疏 | depth fragility、replenishment failure、price impact-aware capacity |
| Options surface by strike/expiry | 当前 options aggregate 只能做 market gate | gamma/expiry pressure、skew residual、vol surface regime |
| On-chain entity/stablecoin flows | M3.2 sidecar 当前覆盖和语义仍有限 | stablecoin impulse、exchange flow regime、whale-to-exchange confirmation |
| Temporal event tape | event_drift 无法成为 executable family | narrative state machine、hype decay、true-news repricing exclusion |

### 3.3 为什么我们不会把数据赞助浪费在“更多噪声”

项目设有明确 stop rules：

- provider close price 与 Binance/CoinAPI 重叠严重不一致且无法解释，停止。
- pagination 无法复现完整 hourly spine，停止。
- OI derived value 与 native USD OI overlap 误差过大，停止。
- timestamp 无法确定 UTC 归一，停止。
- ETF / on-chain 数据无法 PIT lag，停止。
- 候选策略 time shuffle、label shuffle、symbol holdout、liquidity bucket consistency 失败，停止 promotion。

这些 stop rules 会把数据赞助变成纪律化研究资产，而不是把数据接入后直接堆到模型里。

---

## 4. 赞助资金和数据的使用计划

### 4.1 第一优先级：研究级数据包

我们建议把赞助资源优先投入以下数据包。

#### A. CoinGlass full-stack commercial / enterprise package

用途：

- spot OHLCV 1h / 4h / 1d 深历史。
- futures OI / funding / liquidation / taker / long-short。
- ETF flow / net asset / premium-discount。
- selected on-chain exchange / whale transfer。
- options aggregate。
- 更高 rate limit 和可能的 bulk export。

为什么优先：

- 本项目已经有 CoinGlass API 接入和 foundation catalog。
- 现有 sync scripts 可以直接扩展。
- 这能最快把数据赞助转化为 coverage reset 和 h10d re-baseline。

采购注意：

- 公开页面显示 CoinGlass 有 Standard、Professional、Enterprise 等商业层级，其中 Enterprise 可谈 custom rate limits、custom data granularity、custom history range、CSV & bulk export。
- 具体历史深度和授权条款必须以赞助/采购协议为准。

#### B. L2/L3 order book + trades historical package

候选方向：

- Tardis.dev high frequency raw tick data。
- Amberdata L1/L2 market data。
- 其他可提供 exchange-native order book snapshots、incremental updates、trades、funding、liquidations、bulk download 的供应商。

用途：

- MF-01 orderbook / inventory retest。
- 1h fake liquidity / bid replenishment / depth withdrawal。
- execution cost、slippage、capacity stress。
- market impact model 和 paper fill simulator。

为什么重要：

- 当前 orderbook sidecar 可以证明部分机制，但不足以判断真实订单簿状态、盘口撤单、流动性补给和冲击成本。
- 若项目未来需要从 research alpha 走向 paper/live readiness，L2/L3 是成本与容量评估的硬条件。

#### C. On-chain entity flow package

候选方向：

- CryptoQuant API。
- Glassnode Professional + API add-on 或机构数据合作。
- 其他覆盖 stablecoin、exchange reserves、exchange flows、whale/entity flow 的数据源。

用途：

- M3.2 stablecoin / on-chain boundary activation。
- MF-13 stablecoin plumbing。
- MF-14 on-chain reflexivity。
- ETF flow + CEX flow concordance。

为什么重要：

- 这类数据可能提供与价格、funding、OI 不同的信息维度。
- 当前 repo 已证明平滑 MF13/MF14 overlay 不够，下一步需要离散边界和 regime activation，正好需要更完整实体流数据。

#### D. Options surface historical package

用途：

- OI by strike / expiry。
- IV by strike / delta。
- 25-delta skew。
- term structure。
- max-pain PIT history。
- gamma / expiry pressure proxy。

为什么重要：

- 当前 options aggregate 只能支持 market gate。
- 真正高护城河的 options research 需要 strike/expiry surface。
- 这类数据可以成为 BTC/ETH-led market regime 的 timing layer，而不是简单 cross-sectional rank。

#### E. Temporal event tape / news intelligence package

用途：

- 带时间戳的事件分类。
- 事件方向或权重。
- 新闻源、公告源、链上异常、listing/delisting、hack、partnership、ETF/macro、treasury 等事件类型。
- append-only replay by `as_of`。

为什么重要：

- repo 已经证明静态 narrative 和简单 event veto 不够。
- 下一代 event-state alpha 需要“什么时候发生了什么”，而不是“这个币后来被贴了什么标签”。

### 4.2 预算层级建议

以下不是供应商报价，而是内部赞助结构设计。实际采购以供应商合同为准。

| 层级 | 资源形式 | 建议周期 | 目标 |
| --- | --- | --- | --- |
| Seed Data Sponsorship | 1 到 2 个 provider 的 API / historical export / trial license | 90 天 | 完成 coverage reset、h10d re-baseline、至少两条 Stage 0 lane |
| Research Acceleration Partnership | 多 provider 组合，含订单簿或链上深历史，适量工程支持 | 180 天 | 完成 1h feasibility、options/on-chain/event 至少一条 strict falsification pass or fail |
| Strategic Data Lab | 企业级 bulk data、custom rate limit、研究支持、可选现金预算 | 12 个月 | 建立可持续数据仓库、paper-trade readiness、季度研究产品和潜在策略孵化 |

### 4.3 现金预算使用原则

如果赞助包含现金，我们建议按以下优先级使用：

1. **数据采购**
   - 优先采购直接映射到 blocked hypothesis 的数据。
   - 不采购无法进入现有 contract 的“好看但无验收路径”的数据。

2. **数据工程**
   - schema normalization。
   - UTC timestamp / PIT replay。
   - provider concordance。
   - immutable snapshots。
   - bulk ingestion 和 local storage。

3. **研究工程**
   - feature builder。
   - Stage 0 evaluator。
   - falsification runner。
   - cost/capacity stress。

4. **计算与存储**
   - order book / tick data 本地压缩存储。
   - DuckDB / Parquet research warehouse。
   - deterministic replay。

5. **合规与许可管理**
   - 确保供应商 license 范围允许研究、展示、内部回测和必要的派生数据使用。

---

## 5. 赞助后的 90 天执行路线

### Phase 0: 第 0 到 2 周，供应商接入与数据合同

目标：先证明数据可用、可存、可回放、可审计。

工作项：

- 建立 provider access ledger。
- 读取 data license 和 redistribution / derived-work 限制。
- 对每个 endpoint 做 capability smoke。
- 建立 schema contract：
  - timestamp field。
  - timezone。
  - interval。
  - symbol mapping。
  - pagination。
  - max request limit。
  - missing-value semantics。
  - PIT risk。
- 建立 raw cache 路径和 normalized output。
- 禁止 secret 写入 repo。

交付物：

- `provider_capability_matrix.json`
- `provider_endpoint_samples.json`
- `data_license_summary.md`
- `provider_smoke_report.md`

验收标准：

- 每个 endpoint 至少一条 smoke 成功或明确 blocked。
- 所有 timestamp 可以 UTC 归一。
- 每个数据源被标记为：
  - `core_research_input`
  - `sidecar_context`
  - `diagnostic_only`
  - `blocked_or_short_history`

### Phase 1: 第 2 到 4 周，数据 foundation 与 coverage reset

目标：把赞助数据接入现有研究系统，并判断它是否真的解决数据瓶颈。

工作项：

- 扩展 spot 1h / futures / microstructure backfill。
- 生成 provider overlap concordance：
  - CoinGlass vs Binance。
  - CoinGlass vs CoinAPI。
  - Native OKX / Bybit / Coinbase vs CoinAPI sidecar。
- 建立 OI provenance：
  - native USD OI。
  - derived coin OI x perp close。
  - overlap error。
- 建立 options / on-chain / event sidecar PIT lag。
- 更新 `market_data_inventory.md` 和 threshold provenance。

交付物：

- `coverage_reset_report.md`
- `provider_concordance_report.md`
- `oi_value_provenance_report.md`
- `data_readiness_delta.md`

验收标准：

- strategy-scope 1h coverage 分类完整。
- 缺失原因不再是 unknown。
- 新数据进入 feature panel 前有 provenance。
- 任何不满足 PIT 的数据只能标为 sidecar 或 diagnostic。

### Phase 2: 第 4 到 8 周，canonical re-baseline 与预注册研究

目标：先确认旧基线在新数据面板下是否稳定，再开启新研究 lane。

工作项：

- 重建 `v5_rw_bridge_no_overlay_h10d` canonical parent 面板。
- 重新运行 fixed-set paired comparison。
- 重新运行 overlay ablation。
- 重新运行 promotion guard。
- 开启最多三条预注册研究 lane：
  1. true 1h microstructure feasibility。
  2. M3.2 on-chain / stablecoin discrete boundary。
  3. M3.1 options-regime exposure gate。
  4. MF-05 native venue stress。
  5. MF-01 orderbook / inventory retest。

原则：同时打开的研究 lane 不超过三条，避免过拟合式搜索。

交付物：

- `canonical_parent_full_stack_rebaseline.md`
- `intraday_1h_feasibility_report.md`
- 每条 lane 的 `stage0_card.md`
- 每条 lane 的 `strict_falsification_plan.md`

验收标准：

- canonical parent 稳定性有 clear pass / degraded / reclassify 结论。
- 每条 lane 有 pre-registered decision rule。
- 未通过 Stage 0 的 lane 不进入 manifest A/B。

### Phase 3: 第 8 到 12 周，严格证伪与赞助 ROI 报告

目标：把数据赞助转化为可投资决策。

工作项：

- 对 Stage 0 正向 lane 运行严格证伪：
  - time shuffle。
  - label shuffle。
  - delay stress。
  - cost stress。
  - symbol holdout。
  - liquidity bucket consistency。
  - fixed-set paired comparison。
  - capacity stress。
- 对失败 lane 形成关闭报告。
- 对通过 lane 形成下一阶段 paper-trade / shadow readiness 计划。
- 汇总数据赞助 ROI。

交付物：

- `strict_falsification_result.md`
- `failed_lane_postmortem.md`
- `data_sponsorship_roi_pack.md`
- `next_180_day_research_plan.md`

验收标准：

- 每个被赞助数据包都有使用记录和研究结论。
- 每个研究 lane 有 pass / fail / blocked。
- 没有“看起来不错但还没验证”的模糊结论。
- 若没有候选通过，结论仍然有效：赞助帮我们排除低质量路径，缩小下一阶段投入范围。

---

## 6. 180 天和 12 个月发展路线

### 6.1 180 天目标

| 方向 | 目标 |
| --- | --- |
| 数据仓库 | 建立 spot / futures / orderbook / options / on-chain / event 的统一 research warehouse |
| 研究纪律 | 所有新候选都经过预注册、Stage 0、strict falsification、promotion guard |
| 1h 策略 | 得出 true 1h feasibility 的硬结论：pass / fail / blocked |
| options | 至少完成一个 options regime market gate 的严格证伪 |
| on-chain | 至少完成一个 stablecoin / exchange-flow discrete boundary 的严格证伪 |
| venue stress | native venue concordance 通过后，重新评估 MF-05 |
| execution readiness | 对通过候选建立 paper fill simulator、cost model、capacity model |
| 对外输出 | 每月一份非敏感 sponsor research memo |

### 6.2 12 个月目标

12 个月内，项目希望从研究实验室走向三种可选成果之一：

1. **策略孵化**
   - 至少一个通过严格证伪、成本压力、容量约束、paper/shadow 观察的候选策略。
   - 明确适用资产池、持仓周期、换手、容量、风险限制。

2. **数据研究产品**
   - 面向数据供应商或机构客户的数字资产数据质量、微结构、链上流动性与事件状态研究报告。
   - 赞助方可获得真实 use-case feedback 和 benchmark。

3. **研究平台资产**
   - 可重复使用的数据接入、点时回放、证伪 runner、策略 promotion gate。
   - 可扩展到更多资产、更多交易所和更多研究员。

---

## 7. 投资人和赞助方的回报

### 7.1 数据赞助方的回报

数据供应商赞助本项目，可以获得以下价值：

- **真实机构级 use case**
  - 项目会用严格的 coverage、concordance、PIT、falsification 标准检验数据，而不是只做 demo。

- **产品反馈**
  - 哪些 endpoint 对 quant research 真正有用。
  - 哪些 schema / timestamp / pagination / history range 会阻碍研究。
  - 哪些数据字段最能转化成机制假设。

- **匿名化研究案例**
  - 在 license 允许范围内，形成非敏感 case study：
    - 如何从数据覆盖到策略证伪。
    - 如何评估订单簿/链上/期权数据的量化价值。
    - 数据质量如何影响研究结论。

- **潜在商业展示**
  - 如果某类数据直接解锁高质量研究结果，赞助方可以拥有一个强有力的 quant research proof point。

### 7.2 战略投资人的回报

战略投资人获得的不是一个承诺收益的黑箱策略，而是一个可逐步验收的研究资产：

- 数据接入有验收。
- 研究 lane 有关闭标准。
- 策略候选有固定基线。
- 失败会被记录并减少未来浪费。
- 成功候选会进入 paper/shadow，而不是直接跳到实盘。

投资回报来自三个可能路径：

1. **策略资产增值**
   - 若有候选通过严格证伪并在 paper/shadow 中继续稳定，可进入更正式的资金部署准备。

2. **研究 IP**
   - 形成一套数字资产数据治理、机制研究和 alpha promotion 的方法论资产。

3. **数据合作网络**
   - 与供应商形成共创关系，获取早期数据访问、试用额度或联合研究机会。

### 7.3 为什么赞助失败也是有价值的

在严格量化研究中，最昂贵的错误不是“没有发现 alpha”，而是“以为发现了 alpha”。如果 90 天赞助后结论是没有候选通过，仍然有价值：

- 我们会知道哪些数据源不足以支持对应假设。
- 我们会关闭低 ROI 研究路线。
- 我们会保留可复用数据仓库和证伪脚本。
- 我们会让下一轮投入更精准。

这是一种可审计的 downside control。

---

## 8. 风险与控制

| 风险 | 说明 | 控制方式 |
| --- | --- | --- |
| 数据许可风险 | 供应商 license 可能限制展示、派生、再分发 | 接入前写 `data_license_summary.md`，敏感数据不入公开 repo |
| 点时泄漏 | ETF、链上、事件数据有发布时间不确定性 | 默认 t+1 lag，缺 publication timestamp 不进入 decision frame |
| 供应商重打包风险 | 多场所数据可能来自同一中间源 | native venue concordance 是 MF-05 前置 gate |
| 过拟合风险 | 数据越多，搜索空间越大 | 每条 lane 预注册，限制并行搜索，严格 falsification |
| 容量与成本风险 | 回测收益可能被冲击成本吃掉 | L2/L3、slippage、trade participation rate、cost stress |
| 单一资产依赖 | 某候选可能靠少数 symbol | symbol holdout 和 liquidity bucket consistency |
| 供应商锁定 | 某 alpha 只在单一 provider 成立 | provider overlap、native-vs-derived、cross-source sanity |
| 研究叙事膨胀 | 负结果被包装成潜在成功 | fail-closed 文档，pass / fail / blocked 三态输出 |

---

## 9. 治理与汇报机制

### 9.1 周度节奏

每周交付一份 sponsor update：

- 本周接入了哪些数据。
- 哪些 endpoint pass / fail / blocked。
- 哪些研究 lane 被开启、关闭、保留。
- 有无数据质量问题需要供应商协助。
- 下周明确动作。

### 9.2 双周研究委员会节奏

每两周一次更正式的 research IC memo：

- 当前 canonical parent 状态。
- 新数据是否改变旧结论。
- Stage 0 和 strict falsification 结果。
- 是否允许某候选进入下一阶段。
- 是否停止某条 lane。

### 9.3 月度赞助 ROI 报告

每月输出：

- 数据使用统计。
- coverage delta。
- provider quality observations。
- research lane outcomes。
- blocked reasons。
- 下一月预算和数据需求。

### 9.4 赞助方可见但不泄密的材料

可分享：

- 数据质量反馈。
- endpoint-level 使用价值。
- 非敏感研究摘要。
- 方法论和流程。
- 聚合指标。

默认不分享：

- API key。
- 原始受限数据。
- 供应商 license 限制材料。
- 可直接复制交易的完整策略参数，除非合作协议另有约定。

---

## 10. 需要赞助方现在决定的事项

我们希望赞助方或投资人在第一轮对以下问题给出支持：

1. 是否可以提供 90 天 research license 或 data credits。
2. 是否支持 bulk export，而不仅是低 rate limit API。
3. 是否可以确认历史深度、字段含义、timestamp 语义和修订政策。
4. 是否允许生成非敏感数据质量反馈报告。
5. 是否希望赞助关系以以下哪种形式进行：
   - in-kind data grant。
   - strategic research partnership。
   - data + cash mixed sponsorship。
   - 可转为后续投资的研究赞助。

我们的第一轮最小请求：

- 90 天。
- 至少一个核心 provider 的 commercial / enterprise 数据能力。
- 至少覆盖 1h spot/futures 或 L2 order book / on-chain / options 中的一条主线。
- 允许本地缓存、研究回测、非敏感派生报告。

---

## 11. 对外沟通版本

可以用下面这段作为对数据供应商或投资人的开场白。

> EnhengClaw Quant Research Lab 正在建设一套数字资产量化研究系统，核心特点是数据可追溯、点时安全、预注册研究和严格证伪。我们已经完成了 Binance / CoinAPI / CoinGlass / CryptoQuant / Alchemy / Deribit 等多源数据的本地研究框架，并建立了 h10d canonical parent、fixed-set comparison、promotion gate 和 fail-closed 研究流程。
>
> 当前项目最需要的不是更多模型，而是更深、更干净、可回放的数据：1h 深历史、L2/L3 order book、native multi-venue concordance、options surface、on-chain entity flow 和 temporal event tape。我们希望通过数据赞助或战略合作，把贵方数据接入一套严谨的量化研究流水线，并在 90 天内交付覆盖率改善、数据质量反馈、严格证伪结果和非敏感研究摘要。
>
> 我们不承诺用单个数据包“跑出神奇收益”。我们承诺的是，每一份数据都会进入可审计的研究合同：先证明可用，再进入预注册假设，再经过样本外、成本、留出、流动性一致性和点时安全检查。对数据赞助方而言，这会形成一个真实、有纪律、可展示的数据价值案例。

---

## 12. 附录 A：当前 repo 内证据锚点

| 文件 | 用途 |
| --- | --- |
| `docs/quant_research/01_data_foundation/market_data_inventory.md` | 当前市场数据目录、schema、provider、sync registry |
| `docs/QUANT_RESEARCH_LAB.md` | 量化研究实验室的主入口、治理、数据 readiness contract |
| `docs/quant_research/01_data_foundation/quant_next_data_specs.md` | 下一阶段值得付费的数据规格 |
| `docs/quant_research/01_data_foundation/coinglass_full_stack_data_research_roadmap.md` | CoinGlass full-stack data + research roadmap |
| `docs/quant_research/01_data_foundation/coinglass_full_stack_foundation_sync.md` | 2026-05-07 foundation catalog 和 alpha fail-closed 状态 |
| `docs/quant_research/00_roadmap_state/baseline_alpha_confidence_validation.md` | h10d baseline confidence validation |
| `config/quant_research/active_h10d_registry.json` | 当前 h10d canonical parent 和新候选规则 |
| `config/quant_research/promotion_gate_h10d.json` | h10d promotion gate |
| `docs/quant_research/00_roadmap_state/next_stage_alpha_map.md` | 下一阶段 alpha research map |
| `docs/quant_research/00_roadmap_state/experiment_catalog.md` | 变体、权重扫描、失败集成和机制证伪目录 |

---

## 13. 附录 B：外部公开资料锚点

以下公开资料用于判断赞助数据方向是否现实可采购。价格、历史范围、授权和 endpoint 能力均需在正式采购或赞助协议前再次确认。

| 来源 | 当前计划中的用途 |
| --- | --- |
| [CoinGlass API Pricing](https://www.coinglass.com/pricing) | 商业层级、rate limit、historical range、Enterprise custom terms |
| [CoinGlass Spot Price OHLC History](https://docs.coinglass.com/reference/spot-price-ohlc-history) | spot OHLCV 1h/4h/1d backfill |
| [CoinGlass ETF Flows History](https://docs.coinglass.com/reference/etf-flows-history) | BTC/ETH ETF flow sidecar |
| [Amberdata Market Data](https://www.amberdata.io/market-data) | L1/L2 market data、order book、trades、liquidity analytics |
| [Tardis.dev](https://tardis.dev/) | high-frequency raw tick、order book snapshots/updates、trades、funding |
| [Glassnode API Docs](https://docs.glassnode.com/basic-api/api) | historical on-chain and crypto market data |
| [CryptoQuant Data API Docs](https://userguide.cryptoquant.com/api/introduction) | exchange flows、stablecoin、network、market data |

---

## 14. 最终投资判断

这个项目最值得投资的地方，不是它已经宣称找到某个永恒 alpha，而是它已经学会了如何系统性地拒绝伪 alpha。

数字资产市场的机会来自碎片化：交易所碎片化、参与者结构碎片化、链上资金流碎片化、期权和杠杆结构碎片化、事件叙事碎片化。碎片化市场里的 alpha 不会只靠一个模型出现，它需要可信数据、机制假设、严格证伪和可执行落地形态。

EnhengClaw 已经拥有后面三项的雏形：

- 机制假设库。
- 严格证伪系统。
- 策略落地闸门。

现在缺的是第一项的下一阶升级：更深、更细、更可回放的数据。

因此，本轮赞助的投资逻辑是：

> 用可采购的数据资产，放大一个已经具备研究纪律的量化系统；用 90 天可验收的流程，把“数据瓶颈”转化为“可证伪的策略机会”；用失败关闭保护下行，用严格通过捕捉真正值得继续投入的上行。

我们不请求投资人相信一个故事。我们请求投资人赞助一套能验证故事真假的机器。
