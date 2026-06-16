# Research Track Position (2026-04-22)

## Current evidence

截至 `2026-04-22`，项目已经有三条比主观判断更硬的事实。

第一，cross-sectional 通道在 overlap 修复后和 positive control 检验下仍然是可信的。`2026-04-20` 与 `2026-04-21` 的 `strong_oracle` 都能通过，说明 ranking、walk-forward、split integrity 与评估链路本身没有被这轮 single-asset 修复动坏。当前 canonical 历史里可直接信任的 cross-sectional 结论是 `30` 条，状态全部为 `fail`。

第二，single-asset 通道此前的主要问题不是“没有 alpha”，而是评估层存在 `score -> position -> PnL` 的会计对齐错误。修复后，single-asset `strong_oracle` 在两个日期上都转为 `raw_positive=true`，这说明当前 single-asset pipeline 至少已经能识别“方向已知正确”的正控制，不再处于 `broken` 状态。

第三，single-asset 通道修复之后，对历史 canonical single-asset 的窄 rerun 结果是：`58` 条里 `0 pass / 54 fail / 4 quarantined`。这四条 quarantined 不是“潜在通过”，而是仍然需要 leakage audit 的异常样本。因此，到目前为止，项目仍然没有一条可 promote 的候选。

## Interpretation

这组数字的意义比单纯的 `0/88` 更清楚。

`0/88` 不再是一个混杂了 phantom pass、overlap 污染和 single-asset 执行 bug 的模糊结论。现在它可以被拆开读：

- `30` 条 cross-sectional：结论可信，当前就是没有通过样本。
- `58` 条 single-asset：pipeline 已从 `broken` 修到至少 `marginal/healthy`，但修复后的 fresh rerun 仍然没有产出 pass；当前结果是 `54 fail + 4 quarantined`。

这意味着“项目当前没有可 promote alpha”已经从一个半可信判断，升级成了一个基本可信的研究事实。它不再只是“我还没找到”，而是“在现有两族信号、现有样本和现有 gate 下，确实还没有找到”。

## Track position

我的当前立场是：

1. 不再把 crypto cross-sectional 当作主研究产出赛道，而把它降级为 **benchmark lane**。它仍然有价值，因为它是目前 oracle 明确证明健康的通道，适合拿来验证 pipeline 的 ranking/selection 逻辑是否工作，但它不应继续吞掉主要的研究时间预算。
2. single-asset 仍然值得继续做，但前提已经变化。现在继续做 single-asset，不是因为它已经显示出 alpha，而是因为它刚刚完成从 `broken` 到 `usable` 的修复，且从个人研究者的资源约束看，single-asset 比 broad cross-sectional 更可能承载真实 edge。
3. 下一阶段的研究主线应该转向 **small-universe single-asset / derivatives-aware**，而不是再扩一批 OHLCV cross-sectional 变种。更具体地说，后续优先级应当是：先用 oracle-healthy 的 single-asset 通道测试新的信号家族，再决定是否继续留在 crypto 赛道本身。

## Decision rule going forward

我给自己的下一道门不是“再打磨 governance”，而是下面这个研究门：

- 如果在 single-asset 通道上新增 `1-2` 个非当前同质化的信号家族后，结果仍然是 `0/N pass`，并且 positive control 继续保持健康，那么我应当正式把“crypto broad cross-sectional / generic 4h single-asset”降级为次要方向，开始评估是否迁移到更适合个人研究者的赛道。
- 如果 single-asset 新信号里首次出现 `pass` 或持续出现需要 quarantine 的高 Sharpe 样本，那就说明这条通道至少值得继续深挖，下一步就该把重心从赛道争论切到独立 leakage audit 与现实可执行性评估。

当前结论很简单：框架已经足够诚实，可以告诉我“这里没有 alpha”；但它还没有告诉我“这个市场值得继续打”。接下来需要的是研究选择，不是治理升级。
