# Secondary 公平基线对照摘要

## 实验完整性

- 预期 Secondary 调用：10
- 已完成：0
- 失败：10
- 全部可配对：否
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
| A | 0/10 | - | -/- | - | -/- | -/- | - | -/-/- |

## 复跑稳定性

| 变体 | 游戏 | 高价值新增根因重合 | confirmed audit key 重合 | Candidate 采用一致 |
| --- | --- | ---: | ---: | ---: |

## Phase2 自动验收

- 状态：failed
- 可进入下一阶段：否
- 阻断项：phase2_calls_complete, raw_field_completeness, admitted_field_completeness, coverage_ledger_completeness, coverage_ledger_valid_rate, coverage_schema_v2_rate, coverage_evidence_packet_echo_rate, phase2_protocol_gate_pass_rate, phase2_delta_only_compliance_rate, deterministic_candidate_generation_rate, candidate_gate_pass_rate, primary_top3_retention, high_added_root_overlap
- 待人工项：human_admitted_precision, human_valid_added_count, human_high_value_added_count, human_duplicate_rate, human_unsupported, human_overstated, human_multiroot

| 检查项 | 当前值 | 门槛 | 结果 |
| --- | ---: | ---: | --- |
| phase2_calls_complete | 0/10 | 100% | 未通过 |
| fairness_invariants | True | true | 通过 |
| raw_field_completeness | - | >=0.9 | 未通过 |
| admitted_field_completeness | - | >=1.0 | 未通过 |
| coverage_ledger_completeness | - | >=1.0 | 未通过 |
| coverage_ledger_valid_rate | - | >=1.0 | 未通过 |
| coverage_schema_v2_rate | - | >=1.0 | 未通过 |
| coverage_evidence_packet_echo_rate | - | >=1.0 | 未通过 |
| phase2_protocol_gate_pass_rate | - | >=1.0 | 未通过 |
| phase2_delta_only_compliance_rate | - | >=1.0 | 未通过 |
| deterministic_candidate_generation_rate | - | >=1.0 | 未通过 |
| candidate_gate_pass_rate | - | >=0.9 | 未通过 |
| primary_top3_retention | - | >=2/3 | 未通过 |
| machine_multiroot | 0 | 0 | 通过 |
| unsupported_severity_change | 0 | 0 | 通过 |
| unsupported_blocking_change | 0 | 0 | 通过 |
| lineage_mismatch | 0 | 0 | 通过 |
| materialization_mismatch | 0 | 0 | 通过 |
| major_judgment_drift | 0 | 0 | 通过 |
| high_added_root_overlap | - | >=0.25 | 未通过 |
| human_admitted_precision | - | >=0.8 | 待人工 |
| human_valid_added_count | - | >=10 | 待人工 |
| human_high_value_added_count | - | >=5 | 待人工 |
| human_duplicate_rate | - | <=0.15 | 待人工 |
| human_unsupported | - | 0 | 待人工 |
| human_overstated | - | 0 | 待人工 |
| human_multiroot | - | 0 | 待人工 |

## 人工验收状态

当前为 `pending_human_annotation`。只有完成 `human_annotation_template.json` 后，才能计算有效新增率、重复率和高价值新增数，并决定是否切换默认 Secondary。
