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

| 变体 | 完成/预期 | Candidate 通过率 | 声称/准入新增 | 最低 Top3 保留率 | 原始/准入字段完整率 | Ledger 完整/合法率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 10/10 | 0.0% | 0.50/0.00 | 100.0% | 100.0%/- | 100.0%/0.0% |

## 复跑稳定性

| 变体 | 游戏 | 高价值新增根因重合 | confirmed audit key 重合 | Candidate 采用一致 |
| --- | --- | ---: | ---: | ---: |
| A | 777 | - | 0.0% | 是 |
| A | racing | - | 0.0% | 是 |
| A | tiger | - | 0.0% | 是 |
| A | 小鸡 | - | - | 是 |
| A | 钱来了 | - | - | 是 |

## Phase2 自动验收

- 状态：failed
- 可进入下一阶段：否
- 阻断项：admitted_field_completeness, coverage_ledger_valid_rate, coverage_schema_v2_rate, candidate_gate_pass_rate, high_added_root_overlap, human_admitted_precision, human_valid_added_count, human_high_value_added_count, human_duplicate_rate
- 待人工项：无

| 检查项 | 当前值 | 门槛 | 结果 |
| --- | ---: | ---: | --- |
| phase2_calls_complete | 10/10 | 100% | 通过 |
| fairness_invariants | True | true | 通过 |
| raw_field_completeness | 1.0 | >=0.9 | 通过 |
| admitted_field_completeness | - | >=1.0 | 未通过 |
| coverage_ledger_completeness | 1.0 | >=1.0 | 通过 |
| coverage_ledger_valid_rate | 0.0 | >=1.0 | 未通过 |
| coverage_schema_v2_rate | 0.0 | >=1.0 | 未通过 |
| candidate_gate_pass_rate | 0.0 | >=0.9 | 未通过 |
| primary_top3_retention | 1.0 | >=2/3 | 通过 |
| machine_multiroot | 0 | 0 | 通过 |
| unsupported_severity_change | 0 | 0 | 通过 |
| unsupported_blocking_change | 0 | 0 | 通过 |
| lineage_mismatch | 0 | 0 | 通过 |
| materialization_mismatch | 0 | 0 | 通过 |
| major_judgment_drift | 0 | 0 | 通过 |
| high_added_root_overlap | - | >=0.6 | 未通过 |
| human_admitted_precision | - | >=0.8 | 未通过 |
| human_valid_added_count | 0 | >=10 | 未通过 |
| human_high_value_added_count | 0 | >=5 | 未通过 |
| human_duplicate_rate | - | <=0.15 | 未通过 |
| human_unsupported | 0 | 0 | 通过 |
| human_overstated | 0 | 0 | 通过 |
| human_multiroot | 0 | 0 | 通过 |

## 人工验收状态

- 已标注新增问题：5
- 有效新增：3
- 有效新增率：60.0%
- 高价值新增：3
- 重复新增率：0.0%

| 变体 | 标注数 | 有效新增 | 有效率 | 高价值新增 | 重复率 | 可执行率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 5 | 3 | 60.0% | 3 | 0.0% | 100.0% |
