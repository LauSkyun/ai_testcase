# Secondary 公平基线对照摘要

## 实验完整性

- 预期 Secondary 调用：10
- 已完成：10
- 失败：0
- 全部可配对：是
- Primary 调用：0
- 视觉调用：0
- 公平性不变量：通过
- 对照变量：single_profile
- 仅预定变量不同：是

## 盲测说明

公开产物仅显示 Variant A / B。完成人工标注前不要打开 `_private/provider_mapping.json`。

## Phase3 变体汇总

| 变体 | 完成/预期 | 协议门槛 | 基线锁定 | 目标账本完整/合法 | 平均 Challenge | 平均 Correction | 平均 abstain | Top3 保留 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 10/10 | 100.0% | 100.0% | 100.0%/100.0% | 1.50 | 1.10 | 0.00 | 100.0% |

## Phase3 复跑稳定性

| 变体 | 游戏 | 目标决策重合 | Challenge 重合 | Correction 重合 | Top blocker 重合 |
| --- | --- | ---: | ---: | ---: | ---: |
| A | 777 | 100.0% | 66.7% | 100.0% | 100.0% |
| A | racing | 100.0% | - | - | 100.0% |
| A | tiger | 100.0% | - | - | 100.0% |
| A | 小鸡 | 81.8% | 0.0% | - | 100.0% |
| A | 钱来了 | 60.0% | 0.0% | 0.0% | 100.0% |

## Phase3 Challenge/Correct 自动验收

- 状态：failed
- 可进入下一阶段：否
- 阻断项：challenge_overlap
- 待人工项：无

| 检查项 | 当前值 | 门槛 | 结果 |
| --- | ---: | ---: | --- |
| phase3_calls_complete | 10/10 | 100% | 通过 |
| fairness_invariants | True | true | 通过 |
| protocol_gate_pass_rate | 1.0 | >=1.0 | 通过 |
| baseline_lock_pass_rate | 1.0 | >=1.0 | 通过 |
| direct_materialization_rate | 0.0 | 0 | 通过 |
| protected_field_change_count | 0 | 0 | 通过 |
| target_coverage_ledger_complete_rate | 1.0 | >=1.0 | 通过 |
| target_coverage_ledger_valid_rate | 1.0 | >=1.0 | 通过 |
| target_decision_overlap | 0.8836 | >=0.8 | 通过 |
| challenge_overlap | 0.2222 | >=0.5 | 未通过 |
| correction_overlap | 0.5 | >=0.5 | 通过 |
| human_challenge_target_correct_rate | 1.0 | >=1.0 | 通过 |
| human_challenge_evidence_locatable_rate | 1.0 | >=1.0 | 通过 |
| human_challenge_precision | 1.0 | >=0.8 | 通过 |
| human_correction_target_correct_rate | 1.0 | >=1.0 | 通过 |
| human_correction_supported_rate | 1.0 | >=1.0 | 通过 |
| human_correction_accuracy_rate | 1.0 | >=0.9 | 通过 |

## 人工验收状态

- 已标注 Phase3 审核项：26

### Phase3 人工判断

- Challenge 数：15
- Challenge 目标正确率：100.0%
- Challenge 证据可定位率：100.0%
- Challenge 有效率：100.0%
- Correction 数：11
- Correction 目标正确率：100.0%
- Correction 证据支持率：100.0%
- Correction 人工准确率：100.0%
- Correction 可安全应用率：100.0%
- 已确定性应用 Correction：11
- 评分发生变化的报告：2

### V1.2 人工确认后评分重算

| 变体 | 游戏 | 复跑 | 应用修正 | 高风险前/后 | 评分前/后 |
| --- | --- | ---: | ---: | ---: | ---: |
| A | 777 | 1 | 5 | 4/2 | C/B |
| A | 777 | 2 | 5 | 4/2 | C/B |
| A | 钱来了 | 2 | 1 | 7/6 | C/C |
