# Secondary 公平基线对照摘要

## 实验完整性

- 预期 Secondary 调用：20
- 已完成：20
- 失败：0
- 全部可配对：是
- Primary 调用：0
- 视觉调用：0
- 公平性不变量：通过
- 对照变量：protocol_profile
- 仅预定变量不同：是

## 盲测说明

公开产物仅显示 Variant A / B。完成人工标注前不要打开 `_private/provider_mapping.json`。

## 变体汇总

| 变体 | 完成/预期 | Candidate 通过率 | 声称/准入新增 | 最低 Top3 保留率 | 原始/准入字段完整率 | Ledger 完整/合法率 | 证据包回显率 | 协议门槛/Delta-only/确定性Candidate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 10/10 | 100.0% | 1.70/1.50 | 66.7% | 100.0%/100.0% | 100.0%/100.0% | 100.0% | 100.0%/100.0%/100.0% |
| B | 10/10 | 70.0% | 1.90/1.90 | 66.7% | 36.5%/36.5% | 100.0%/100.0% | 100.0% | 100.0%/100.0%/0.0% |

## 复跑稳定性

| 变体 | 游戏 | 高价值新增根因重合 | confirmed audit key 重合 | Candidate 采用一致 |
| --- | --- | ---: | ---: | ---: |
| A | 777 | - | - | 是 |
| A | racing | 100.0% | 100.0% | 是 |
| A | tiger | 0.0% | 33.3% | 是 |
| A | 小鸡 | 50.0% | 100.0% | 是 |
| A | 钱来了 | 0.0% | 0.0% | 是 |
| B | 777 | 0.0% | - | 否 |
| B | racing | 0.0% | - | 是 |
| B | tiger | 0.0% | - | 否 |
| B | 小鸡 | 0.0% | - | 是 |
| B | 钱来了 | - | - | 否 |

## Phase2 自动验收

- 状态：passed
- 可进入下一阶段：是
- 阻断项：无
- 待人工项：无

| 检查项 | 当前值 | 门槛 | 结果 |
| --- | ---: | ---: | --- |
| phase2_calls_complete | 10/10 | 100% | 通过 |
| fairness_invariants | True | true | 通过 |
| raw_field_completeness | 1.0 | >=0.9 | 通过 |
| admitted_field_completeness | 1.0 | >=1.0 | 通过 |
| coverage_ledger_completeness | 1.0 | >=1.0 | 通过 |
| coverage_ledger_valid_rate | 1.0 | >=1.0 | 通过 |
| coverage_schema_v2_rate | 1.0 | >=1.0 | 通过 |
| coverage_evidence_packet_echo_rate | 1.0 | >=1.0 | 通过 |
| phase2_protocol_gate_pass_rate | 1.0 | >=1.0 | 通过 |
| phase2_delta_only_compliance_rate | 1.0 | >=1.0 | 通过 |
| deterministic_candidate_generation_rate | 1.0 | >=1.0 | 通过 |
| candidate_gate_pass_rate | 1.0 | >=0.9 | 通过 |
| primary_top3_retention | 0.6667 | >=2/3 | 通过 |
| machine_multiroot | 0 | 0 | 通过 |
| unsupported_severity_change | 0 | 0 | 通过 |
| unsupported_blocking_change | 0 | 0 | 通过 |
| lineage_mismatch | 0 | 0 | 通过 |
| materialization_mismatch | 0 | 0 | 通过 |
| major_judgment_drift | 0 | 0 | 通过 |
| high_added_root_overlap | 0.375 | >=0.25 | 通过 |
| human_admitted_precision | 1.0 | >=0.8 | 通过 |
| human_valid_added_count | 15 | >=10 | 通过 |
| human_high_value_added_count | 12 | >=5 | 通过 |
| human_duplicate_rate | 0.0 | <=0.15 | 通过 |
| human_unsupported | 0 | 0 | 通过 |
| human_overstated | 0 | 0 | 通过 |
| human_multiroot | 0 | 0 | 通过 |

## 人工验收状态

- 已标注新增问题：36
- 有效新增：27
- 有效新增率：75.0%
- 高价值新增：19
- 重复新增率：11.1%

| 变体 | 标注数 | 有效新增 | 有效率 | 高价值新增 | 重复率 | 可执行率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 17 | 17 | 100.0% | 14 | 0.0% | 100.0% |
| B | 19 | 10 | 52.6% | 5 | 21.1% | 0.0% |
