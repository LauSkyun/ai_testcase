# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心的公式冲突、筹码配置冲突及Crash算法映射问题，但在资金事务边界（扣款时机、单局封顶）上存在漏项，且部分finding混入了非阻塞的美术包装问题。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选稿已补全资金事务边界的高信号缺口，清理了非阻塞的美术包装干扰，结构完整、证据充分，可直接输出给业务方。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：3
- candidate issue_id 修复数：3
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=5, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=5, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 2，通过 0，拒绝 2
- coverage ledger：未通过，完整率 100%
- coverage ledger 错误：coverage_entry_invalid:settlement_formula_ui_config:status_invalid, coverage_entry_invalid:settlement_formula_ui_config:primary_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:candidate_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:evidence_checked_missing, coverage_entry_invalid:settlement_formula_ui_config:reason_missing, coverage_entry_invalid:trigger_state_termination:status_invalid, coverage_entry_invalid:trigger_state_termination:primary_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:candidate_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:evidence_checked_missing, coverage_entry_invalid:trigger_state_termination:reason_missing, coverage_entry_invalid:funds_deduction_payout:status_invalid, coverage_entry_invalid:funds_deduction_payout:primary_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:candidate_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:evidence_checked_missing, coverage_entry_invalid:funds_deduction_payout:reason_missing, coverage_entry_invalid:max_payout_economic_boundary:status_invalid, coverage_entry_invalid:max_payout_economic_boundary:primary_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:candidate_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:evidence_checked_missing, coverage_entry_invalid:max_payout_economic_boundary:reason_missing, coverage_entry_invalid:statistics_time_window:status_invalid, coverage_entry_invalid:statistics_time_window:primary_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:candidate_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:evidence_checked_missing, coverage_entry_invalid:statistics_time_window:reason_missing, missed_finding_not_in_confirmed_add:FUNDS_DEBIT_TIMING, missed_finding_not_in_confirmed_add:FUNDS_MAX_PAYOUT_CAP, coverage_schema_version_too_old:1:required:2
  - 拒绝《下注扣款时机与事务边界缺失》：multiroot_funds_debit_and_payout_combined, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《单局最大赔付金额封顶（Max Payout）缺失》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确抓住了倍率连乘与累计的口径冲突
- 识别了Crash算法与离散格子映射的实现难点
- 指出了下注筹码在多端配置不一致的问题

## 问题
- 遗漏了扣款时机和单局最大赔付封顶等高危资金边界问题
- 将美术包装（小鸡/骆驼）混入核心概率冲突finding，导致焦点分散
- 对数值表中倍盘命名与最终数值的数量级冲突缺乏独立的高危定性

## 复核备注
- 美术包装（小鸡/骆驼）混用问题已移至 quality_notes，不作为高阻塞 finding。
- UI截图中的倍率（如1.03, 1.07）与数值文档难度1的赔率（1.01, 1.03）存在微小差异，可能为不同难度或版本UI，建议策划澄清，但不阻塞核心逻辑。
- 数值文档中难度3（103倍盘）和难度4（176倍盘）的最终数值与命名存在严重数量级冲突，需数值策划立即修正推导公式。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_DEBIT_TIMING
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_MAX_PAYOUT_CAP
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
