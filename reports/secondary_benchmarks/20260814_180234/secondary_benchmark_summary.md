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

## 变体汇总

| 变体 | 完成/预期 | Candidate 通过率 | 声称/准入新增 | 最低 Top3 保留率 | 原始/准入字段完整率 | Ledger 完整/合法率 | 证据包回显率 | 协议门槛/Delta-only/确定性Candidate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 10/10 | 0.0% | 0.00/0.00 | 100.0% | -/- | -/0.0% | 0.0% | 0.0%/0.0%/0.0% |

## 复跑稳定性

| 变体 | 游戏 | 高价值新增根因重合 | confirmed audit key 重合 | Candidate 采用一致 |
| --- | --- | ---: | ---: | ---: |
| A | 777 | - | - | 是 |
| A | racing | - | - | 是 |
| A | tiger | - | - | 是 |
| A | 小鸡 | - | - | 是 |
| A | 钱来了 | - | - | 是 |

## Phase3 Challenge/Correct 自动验收

- 状态：failed
- 可进入下一阶段：否
- 阻断项：human_correction_accuracy_rate
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
| human_correction_accuracy_rate | 0.7143 | >=0.9 | 未通过 |

## 人工验收状态

- 已标注新增问题：35
- 有效新增：0
- 有效新增率：-
- 高价值新增：0
- 重复新增率：-

| 变体 | 标注数 | 有效新增 | 有效率 | 高价值新增 | 重复率 | 可执行率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 0 | 0 | - | 0 | - | - |

### Phase3 人工判断

- Challenge 数：21
- Challenge 目标正确率：100.0%
- Challenge 证据可定位率：100.0%
- Challenge 有效率：100.0%
- Correction 数：14
- Correction 目标正确率：100.0%
- Correction 证据支持率：100.0%
- Correction 人工准确率：71.4%
- Correction 可安全应用率：64.3%
