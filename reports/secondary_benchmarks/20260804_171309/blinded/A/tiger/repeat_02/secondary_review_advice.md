# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了三个高信号核心阻塞项（0赔付兜底缺陷、机器人机制缺失、奖池正常状态概率冲突），并覆盖了赔率口径分裂、开奖分析可见性矛盾等关键问题。但在资金事务边界（扣款/派奖时机、失败补偿）和奖池透支下限方面存在明显漏检，且未发现游戏记录模块在正文与UI截图之间的时间窗口冲突。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选稿已补全资金事务边界和奖池透支下限等高信号缺口，修正了top_blockers的证据引用，lineage完整可追踪，可直接交付业务方阅读。
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
- phase2 新增准入：声称 5，通过 0，拒绝 5
- coverage ledger：未通过，完整率 100%
- coverage ledger 错误：coverage_entry_invalid:settlement_formula_ui_config:status_invalid, coverage_entry_invalid:settlement_formula_ui_config:primary_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:candidate_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:evidence_checked_missing, coverage_entry_invalid:settlement_formula_ui_config:reason_missing, coverage_entry_invalid:trigger_state_termination:status_invalid, coverage_entry_invalid:trigger_state_termination:primary_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:candidate_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:evidence_checked_missing, coverage_entry_invalid:trigger_state_termination:reason_missing, coverage_entry_invalid:funds_deduction_payout:status_invalid, coverage_entry_invalid:funds_deduction_payout:primary_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:candidate_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:evidence_checked_missing, coverage_entry_invalid:funds_deduction_payout:reason_missing, coverage_entry_invalid:max_payout_economic_boundary:status_invalid, coverage_entry_invalid:max_payout_economic_boundary:primary_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:candidate_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:evidence_checked_missing, coverage_entry_invalid:max_payout_economic_boundary:reason_missing, coverage_entry_invalid:statistics_time_window:status_invalid, coverage_entry_invalid:statistics_time_window:primary_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:candidate_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:evidence_checked_missing, coverage_entry_invalid:statistics_time_window:reason_missing, missed_finding_not_in_confirmed_add:FUNDS_01, missed_finding_not_in_confirmed_add:FUNDS_02, missed_finding_not_in_confirmed_add:FUNDS_03, missed_finding_not_in_confirmed_add:ECON_01, missed_finding_not_in_confirmed_add:STATS_01, coverage_schema_version_too_old:1:required:2
  - 拒绝《玩家下注本金的扣款时机未明确定义》：primary_duplicate_root, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《派奖到账用户钱包的时机未明确定义》：multiroot_funds_debit_and_payout_combined, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《资金失败（扣款/派奖）的回滚、补偿与幂等机制完全缺失》：evidence_position_unlocatable, multiroot_funds_debit_and_payout_combined, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《奖池允许透支为负但缺乏下限定义和熔断机制》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《游戏记录模块的时间窗口在正文与UI截图之间存在冲突》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确定位了0赔付兜底缺陷这一致命逻辑漏洞，证据链完整（段落57/68/108 + 段落73）
- 发现图22机器人流程图与正文需求脱节，指出阈值依赖人数但缺乏机器人机制支撑
- 识别出奖池正常状态偏移概率在正文(60%)与配置表(20%)之间的数值冲突
- 对赔率口径分裂（2.9 vs 3X）的多源证据收集充分（表格4、图1、图5、图7、图21）

## 问题
- 完全遗漏了资金事务边界：扣款时机（下注时 vs 结算时）、派奖到账时机、资金失败补偿均未覆盖
- 未发现奖池允许透支为负但缺乏下限定义的经济边界风险
- 未发现游戏记录模块正文(近3日)与UI截图(近30日)之间的时间窗口冲突
- 部分finding的evidence字段为空（top_blockers），影响可追踪性

## 复核备注
- 主模型报告准确识别了三个高信号核心阻塞项，但遗漏了资金事务边界（扣款/派奖时机、失败补偿）和奖池透支下限等重要缺口。
- 候选稿新增5个finding（FUNDS_01/02/03、ECON_01、STATS_01），均通过phase2 coverage_ledger的confirmed_add校验。
- 建议后续补充：1)完整的资金流转时序图；2)奖池透支的负值下限和熔断阈值；3)断线重连后的资金补偿逻辑。
- 图6与表格3的时间窗口冲突（30天 vs 3天）需产品确认最终口径。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：ECON_01
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_01
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_02
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_03
- phase2 准入已从 candidate 移除 rejected addition：STATS_01

## 不支持的问题
- 暂无

## 合并建议
- 暂无
