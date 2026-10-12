# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率公式冲突、T变量定义歧义、假数据隔离、真假赔率映射、干预逻辑映射缺口和最大赔付兜底缺失等高信号问题，整体方向正确。但部分finding存在明显重复表述（同一问题在current_state、risk、suggestion中多次复述），且遗漏了扣款时机、派奖时机、资金失败补偿、赔率倍率上限等直接影响结算正确性和经济安全的独立控制面。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选报告已修正主模型的重复表述问题，补充了4个直接影响结算正确性和经济安全的独立控制面缺口，结构完整、证据充分、来源可追踪，可直接给业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=8, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=8, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 4，通过 0，拒绝 4
- coverage ledger：未通过，完整率 100%
- coverage ledger 错误：coverage_entry_invalid:settlement_formula_ui_config:status_invalid, coverage_entry_invalid:settlement_formula_ui_config:primary_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:candidate_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:evidence_checked_missing, coverage_entry_invalid:settlement_formula_ui_config:reason_missing, coverage_entry_invalid:trigger_state_termination:status_invalid, coverage_entry_invalid:trigger_state_termination:primary_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:candidate_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:evidence_checked_missing, coverage_entry_invalid:trigger_state_termination:reason_missing, coverage_entry_invalid:funds_deduction_payout:status_invalid, coverage_entry_invalid:funds_deduction_payout:primary_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:candidate_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:evidence_checked_missing, coverage_entry_invalid:funds_deduction_payout:reason_missing, coverage_entry_invalid:max_payout_economic_boundary:status_invalid, coverage_entry_invalid:max_payout_economic_boundary:primary_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:candidate_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:evidence_checked_missing, coverage_entry_invalid:max_payout_economic_boundary:reason_missing, coverage_entry_invalid:statistics_time_window:status_invalid, coverage_entry_invalid:statistics_time_window:primary_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:candidate_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:evidence_checked_missing, coverage_entry_invalid:statistics_time_window:reason_missing, missed_finding_not_in_confirmed_add:FUNDS_DEBIT_TIMING, missed_finding_not_in_confirmed_add:FUNDS_PAYOUT_TIMING, missed_finding_not_in_confirmed_add:FUNDS_FAILURE_COMPENSATION, missed_finding_not_in_confirmed_add:ODDS_RELATIVE_PAYOUT_CAP, coverage_schema_version_too_old:1:required:2
  - 拒绝《下注扣款时机未明确，存在重复扣款或漏扣风险》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《派奖到账时机未明确，影响用户体验与信任》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《资金失败回滚与补偿机制未明确，存在资损风险》：evidence_position_unlocatable, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《赔率倍率上限未定义，存在极端赔付风险》：primary_duplicate_declared_nearest, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别了需求文档与数值文档之间赔率公式的根本性冲突（资金池比例公式 vs 权重膨胀公式）
- 准确识别了T变量在开奖时间公式与赔率公式中的定义冲突
- 正确识别了假数据参与赔率计算的数据源隔离风险
- 正确识别了真假赔率展示与结算映射缺失的客诉风险
- 正确识别了干预逻辑缺乏到速度公式映射的实现阻塞
- 正确识别了奖池负数时缺乏最大赔付兜底的资损风险

## 问题
- T_VARIABLE_CONFLICT和FAKE_ODDS_MAPPING的current_state、risk、suggestion存在大量重复表述，同一问题被复述3-5次
- 遗漏了扣款时机（debit_timing）这一关键资金控制面
- 遗漏了派奖时机（payout_timing）这一关键资金控制面
- 遗漏了资金失败回滚与补偿机制（funds_failure_compensation）
- 遗漏了赔率倍率上限（relative_payout_cap）这一独立于绝对金额封顶的经济边界
- MAX_PAYOUT_RISK同时承载了奖池负数下限和单局金额封顶两个控制面，但未拆分

## 复核备注
- 主模型T_VARIABLE_CONFLICT和FAKE_ODDS_MAPPING存在明显重复表述，已在候选报告中精简为分点描述。
- 主模型遗漏了扣款时机、派奖时机、资金失败补偿、赔率倍率上限等4个关键资金控制面，已在候选报告中补充。
- 建议后续将MAX_PAYOUT_RISK拆分为pool_negative_floor和single_round_payout_cap两个独立问题，但当前保留原结构以维持与primary的一致性。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_DEBIT_TIMING
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_FAILURE_COMPENSATION
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_PAYOUT_TIMING
- phase2 准入已从 candidate 移除 rejected addition：ODDS_RELATIVE_PAYOUT_CAP

## 不支持的问题
- 暂无

## 合并建议
- 暂无
