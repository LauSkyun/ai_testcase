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

| 变体 | 完成/预期 | 协议门槛 | 基线锁定 | 平均 Challenge | 平均 Correction | 平均 abstain | Top3 保留 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 10/10 | 100.0% | 100.0% | 1.80 | 1.50 | 0.10 | 100.0% |

## Phase3 复跑稳定性

| 变体 | 游戏 | Challenge 重合 | Correction 重合 | Top blocker 重合 |
| --- | --- | ---: | ---: | ---: |
| A | 777 | 0.0% | 0.0% | 100.0% |
| A | racing | 0.0% | - | 100.0% |
| A | tiger | 0.0% | 0.0% | 100.0% |
| A | 小鸡 | 0.0% | 25.0% | 100.0% |
| A | 钱来了 | 0.0% | 0.0% | 100.0% |

## Phase3 Challenge/Correct 自动验收

- 状态：passed
- 可进入下一阶段：是
- 阻断项：无
- 待人工项：无

| 检查项 | 当前值 | 门槛 | 结果 |
| --- | ---: | ---: | --- |
| phase3_calls_complete | 10/10 | 100% | 通过 |
| fairness_invariants | True | true | 通过 |
| protocol_gate_pass_rate | 1.0 | >=1.0 | 通过 |
| baseline_lock_pass_rate | 1.0 | >=1.0 | 通过 |
| direct_materialization_rate | 0.0 | 0 | 通过 |
| protected_field_change_count | 0 | 0 | 通过 |
| human_challenge_target_correct_rate | 1.0 | >=1.0 | 通过 |
| human_challenge_evidence_locatable_rate | 1.0 | >=1.0 | 通过 |
| human_challenge_precision | 1.0 | >=0.8 | 通过 |
| human_correction_target_correct_rate | 1.0 | >=1.0 | 通过 |
| human_correction_supported_rate | 1.0 | >=1.0 | 通过 |
| human_correction_accuracy_rate | 1.0 | >=0.9 | 通过 |

## 人工验收状态

- 已标注 Phase3 审核项：33

### Phase3 人工判断

- Challenge 数：18
- Challenge 目标正确率：100.0%
- Challenge 证据可定位率：100.0%
- Challenge 有效率：100.0%
- Correction 数：15
- Correction 目标正确率：100.0%
- Correction 证据支持率：100.0%
- Correction 人工准确率：100.0%
- Correction 可安全应用率：100.0%
