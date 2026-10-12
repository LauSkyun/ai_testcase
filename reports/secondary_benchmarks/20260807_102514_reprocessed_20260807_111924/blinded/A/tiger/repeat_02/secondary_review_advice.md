# Dual Pass 副评审建议

## 总体判断
Candidate 由 Primary 与已准入增量确定性生成。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：Candidate 由系统确定性生成，不依赖模型自评。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=10, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=10, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 2，通过 0，拒绝 2
- coverage ledger：未通过，完整率 80%
- coverage ledger 错误：coverage_audit_key_order_invalid, coverage_entry_invalid:settlement_formula_ui_config:status_invalid, coverage_entry_invalid:settlement_formula_ui_config:primary_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:candidate_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:evidence_checked_missing, coverage_entry_invalid:settlement_formula_ui_config:reason_missing, coverage_entry_invalid:trigger_state_termination:status_invalid, coverage_entry_invalid:trigger_state_termination:primary_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:candidate_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:evidence_checked_missing, coverage_entry_invalid:trigger_state_termination:reason_missing, coverage_entry_invalid:funds_deduction_payout:status_invalid, coverage_entry_invalid:funds_deduction_payout:primary_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:candidate_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:evidence_checked_missing, coverage_entry_invalid:funds_deduction_payout:reason_missing, coverage_entry_invalid:max_payout_economic_boundary:status_invalid, coverage_entry_invalid:max_payout_economic_boundary:primary_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:candidate_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:evidence_checked_missing, coverage_entry_invalid:max_payout_economic_boundary:reason_missing, coverage_entry_invalid:index_4:audit_key_invalid, coverage_entry_invalid:index_4:status_invalid, coverage_entry_invalid:index_4:primary_issue_ids_not_array, coverage_entry_invalid:index_4:candidate_issue_ids_not_array, coverage_entry_invalid:index_4:evidence_checked_missing, coverage_entry_invalid:index_4:reason_missing, missed_finding_not_in_confirmed_add:MAX_PAYOUT_01, missed_finding_not_in_confirmed_add:STATISTICS_01, coverage_schema_version_too_old:1:required:2
  - 拒绝《奖池允许透支为负但未定义透支下限与熔断条件》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《开奖分析时间窗口在正文与UI截图中不一致（7天 vs 30天）》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 完整保留 Primary 骨架、评分和核心问题。

## 问题
- 暂无

## 复核备注
- 主模型报告整体质量良好，准确识别了核心高信号问题，但遗漏了奖池透支下限与开奖分析时间窗口两个独立根因。
- 建议补充玩家本金实际扣除时机（下注时还是结算时）的显式说明，虽然TEST_02覆盖了边界行为，但扣款时机本身未明确。
- 建议确认资金事务失败回滚是否由平台中台统一处理，本玩法是否有特殊需求。
- protocol_profile=phase2_v2_1; evidence_packet_id=b4a6e1c32c61dd26379c4d03e435f3e135d8de14131c463c80393bdd956b09c9
- phase2 准入已从 candidate 移除 rejected addition：MAX_PAYOUT_01
- phase2 准入已从 candidate 移除 rejected addition：STATISTICS_01
- candidate_generation_mode=deterministic_primary_plus_admitted_delta

## 不支持的问题
- 暂无

## 合并建议
- 暂无
