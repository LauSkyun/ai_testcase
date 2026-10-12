# 阶段一公平基线验收报告

## 1. 验收结论

阶段一实验执行合格，但模型切换验收不合格。

- 20/20 次 Secondary 外部回放完成，失败 0 次，全部可配对。
- 冻结输入、Primary 原始输出、Primary 报告和 Secondary 消息的 hash 一致；实验中 Primary 调用 0 次、视觉调用 0 次，公平性校验通过。
- 揭盲结果：Variant A = DeepSeek `deepseek-v4-pro`；Variant B = Qwen `gpt-5.6-sol`。
- 盲评阶段已先独立固化“B 优于 A，但两者均不能默认切换”，揭盲后对应结论为：Qwen Secondary 明显优于 DeepSeek Secondary。
- 当前不应把生产环境切换为 `Qwen Primary + DeepSeek Secondary`；继续保持 `Qwen Primary + Qwen Secondary`。

阶段一解决了“公平比较”的问题，也证明当前 DeepSeek Secondary 不是更优方向。它的有效新增少、幻觉和泛化问题多、重复率更高，且稳定性未达标。

## 2. 实验范围与公平性

| 项目 | 结果 |
|---|---:|
| 冻结来源批次 | `reports/20260731_105856` |
| 游戏数 | 5 |
| Secondary 数 | 2 |
| 每款每模型复跑 | 2 次 |
| 计划调用 | 20 |
| 成功调用 | 20 |
| 失败调用 | 0 |
| Primary 调用 | 0 |
| 视觉调用 | 0 |
| 全部配对 | 是 |
| 公平性不变量 | 全部通过 |

本次仅改变 Secondary 供应商；同款游戏的共享输入、Primary 原始响应、Primary 消息、解析后的 Primary 报告和 Secondary 消息全部保持一致。

## 3. 揭盲结果

| 盲测 Variant | 供应商 | 模型 |
|---|---|---|
| A | DeepSeek | `deepseek-v4-pro` |
| B | Qwen | `gpt-5.6-sol` |

揭盲前结论保存在 `blind_evaluation_conclusion.json/.md`，避免先知道厂商再调整评价。

## 4. 质量对比

| 指标 | Qwen Secondary | DeepSeek Secondary | 更优 |
|---|---:|---:|---|
| 人工标注新增数 | 18 | 13 | — |
| 有效新增数 | 10 | 2 | Qwen |
| 有效新增率 | 55.56% | 15.38% | Qwen |
| 高价值有效新增 | 5 | 0 | Qwen |
| 重复新增率 | 16.67% | 23.08% | Qwen |
| 证据不足数 | 6 | 11 | Qwen |
| 严重度夸大数 | 2 | 2 | 持平 |
| 人工确认多根因数 | 1 | 1 | 持平 |
| Candidate 门槛通过率 | 90% | 80% | Qwen |
| Candidate 默认采用率 | 90% | 80% | Qwen |
| Primary Top Blocker 平均保留率 | 80.00% | 73.33% | Qwen |
| 字段完整率 | 57.14% | 51.43% | Qwen |
| lineage mismatch | 1 | 1 | 持平 |
| materialization mismatch | 1 | 1 | 持平 |
| major judgment drift | 0 | 0 | 持平 |

Qwen 的优势不只是“多报问题”：它产出的 10 个有效新增中有 5 个达到高价值，而 DeepSeek 的 13 个新增里只有 2 个有效，且没有高价值有效新增。DeepSeek 常见问题是脱离当前文档生成通用项，例如弱网、热更、教程、最小选项为零等；部分判断与原文直接冲突。

Qwen 同样尚未达到生产自动合并标准：仍有 6 个证据不足新增、16.67% 重复率，以及跨复跑新增根因不稳定的问题。

## 5. 十项切换门槛审计

| # | 门槛 | Qwen | DeepSeek |
|---:|---|---|---|
| 1 | 有效新增率 ≥ 80% | 失败：55.56% | 失败：15.38% |
| 2 | 异模型稳定增加高价值问题或显著降低重复 | 参照组 | 失败：高价值 0，重复率更高 |
| 3 | 重复新增率 ≤ 15% | 失败：16.67% | 失败：23.08% |
| 4 | 无依据严重度升降级 = 0 | 结构检测通过；人工仍发现 2 个夸大新增 | 结构检测通过；人工仍发现 2 个夸大新增 |
| 5 | 多根因 finding = 0 | 失败：1 | 失败：1 |
| 6 | Primary Top 3 平均保留率 ≥ 2/3 | 通过：80%；但单次最低 33.33% | 通过：73.33%；但单次最低 33.33% |
| 7 | Candidate 门槛通过率 ≥ 90% | 通过：90% | 失败：80% |
| 8 | 高价值新增复跑重合率 ≥ 60% | 失败：可计算项为 0% | 失败：可计算项为 0% |
| 9 | lineage/materialization mismatch、drift 均为 0 | 失败：1/1/0 | 失败：1/1/0 |
| 10 | Secondary 失败 100% 回退 pipeline | 代码路径已实现；本批未触发外部失败 | 代码路径已实现；本批未触发外部失败 |

DeepSeek 未达到切换要求；Qwen 虽整体明显领先，也未达到“Secondary 新增可无人工直接合并”的要求。因此当前可以继续使用 Qwen + Qwen 作为更优基线，但 Candidate 必须继续受门槛约束，不能放宽自动采用规则。

## 6. 可用性判断

- Qwen + Qwen：可继续作为当前生产基线使用；使用条件是保留 pipeline 回退和 Candidate 结构门槛。尚不适合把所有 Secondary 新增无条件自动并入最终报告。
- Qwen + DeepSeek：当前不达到默认可使用标准，不建议修改活动环境。若继续研究，只能作为 advice-only 实验支路。
- 回放工具：达到阶段一可用标准。支持冻结 Primary、公平盲测、20 次配对、人工标注、保存响应重处理和汇总复算。

## 7. 落实方案与下一阶段方向

1. 保持活动环境为 Qwen Primary + Qwen Secondary；命名供应商配置保留，仅用于公平回放，不需要修改当前模型组合。
2. DeepSeek 暂时降为 advice-only：只能提出 `add/challenge/correct` 建议，不直接控制 Candidate 或总评分。
3. 强制每个新增项提供 `evidence`、`independent_root_cause`、`primary_overlap_check`、`severity_basis`；缺任一字段即拒绝物化。
4. 将人工发现的三类问题前移为代码门槛：证据不足、与 Primary 重复、多根因合并。
5. 收紧后复用本次冻结 Primary 再跑 20 次，避免 Primary 波动污染前后对比。
6. 只有 20 次复验全部达到十项门槛，才进入每模型 3 次、共 30 次的正式验收；正式验收通过后才讨论切换默认 Secondary。

## 8. 验收决定

- 阶段一公平基线能力：通过。
- 20 次外部模型回放：通过。
- Qwen Secondary 相对 DeepSeek Secondary 的质量结论：Qwen 明显更优。
- DeepSeek 默认 Secondary：不通过。
- 修改活动环境为 Qwen + DeepSeek：不批准。
- 下一步：进入阶段二协议收紧；生产配置保持 Qwen + Qwen。
