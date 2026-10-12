# Dual Pass 副评审建议

## 总体判断
主模型报告整体质量良好，准确识别了核心赔率冲突、机器人机制缺失、开奖兜底0赔付缺陷等高信号问题。但遗漏了奖池透支下限与熔断条件缺失、开奖分析时间窗口正文与UI不一致两个独立根因问题，需补充后方可完整交付。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选报告已补充奖池透支下限与开奖分析时间窗口两个独立根因问题，结构完整、证据充分、来源可追踪，可直接给业务方阅读
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
- 准确识别了核心赔率在正文、配置表与UI中的多处冲突（CLARITY_01）
- 发现了开奖兜底逻辑中0赔付选项的机制缺陷（LOGIC_01）
- 指出了机器人机制缺失导致人数阈值无法触发的问题（CLARITY_02）
- 识别了奖池正常状态偏移概率在正文与配置表中的数值冲突（LOGIC_02）

## 问题
- 遗漏了奖池允许透支为负但未定义下限与熔断条件的经济边界缺口
- 未发现开奖分析时间窗口在正文（7天）与UI截图（30天）中的不一致

## 复核备注
- 主模型报告整体质量良好，准确识别了核心高信号问题，但遗漏了奖池透支下限与开奖分析时间窗口两个独立根因。
- 建议补充玩家本金实际扣除时机（下注时还是结算时）的显式说明，虽然TEST_02覆盖了边界行为，但扣款时机本身未明确。
- 建议确认资金事务失败回滚是否由平台中台统一处理，本玩法是否有特殊需求。
- protocol_profile=phase2_v2_1; evidence_packet_id=b4a6e1c32c61dd26379c4d03e435f3e135d8de14131c463c80393bdd956b09c9
- phase2 准入已从 candidate 移除 rejected addition：MAX_PAYOUT_01
- phase2 准入已从 candidate 移除 rejected addition：STATISTICS_01

## 不支持的问题
- 暂无

## 合并建议
- 暂无
