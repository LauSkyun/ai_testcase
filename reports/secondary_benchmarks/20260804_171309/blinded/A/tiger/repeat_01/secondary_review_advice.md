# Dual Pass 副评审建议

## 总体判断
主模型首版报告整体质量较高，准确识别了核心赔率冲突、开奖兜底0赔付缺陷、奖池正常状态概率冲突、机器人机制缺失等高信号阻塞问题，维度覆盖完整，证据定位清晰。但在资金链路（扣款/派奖时机、失败补偿）、单局赔付封顶、奖池负值下限、开奖分析统计窗口正文与UI冲突、下注倒计时正文与UI冲突等方面存在漏检，且部分 kept 问题的现状描述可进一步分点展开以增强可验收性。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选稿已补齐资金链路、赔付封顶、奖池负值下限、统计窗口与倒计时 UI 冲突等高信号缺口，保留主模型全部核心 blocker 并分点展开子症状，lineage 可追踪，可直接交付业务方阅读；剩余待产品拍板项（如机器人机制最终口径、赔率最终取值）属于需求确认范畴，不阻断报告直出。
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
- phase2 新增准入：声称 6，通过 0，拒绝 6
- coverage ledger：未通过，完整率 100%
- coverage ledger 错误：coverage_entry_invalid:settlement_formula_ui_config:status_invalid, coverage_entry_invalid:settlement_formula_ui_config:primary_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:candidate_issue_ids_not_array, coverage_entry_invalid:settlement_formula_ui_config:evidence_checked_missing, coverage_entry_invalid:settlement_formula_ui_config:reason_missing, coverage_entry_invalid:trigger_state_termination:status_invalid, coverage_entry_invalid:trigger_state_termination:primary_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:candidate_issue_ids_not_array, coverage_entry_invalid:trigger_state_termination:evidence_checked_missing, coverage_entry_invalid:trigger_state_termination:reason_missing, coverage_entry_invalid:funds_deduction_payout:status_invalid, coverage_entry_invalid:funds_deduction_payout:primary_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:candidate_issue_ids_not_array, coverage_entry_invalid:funds_deduction_payout:evidence_checked_missing, coverage_entry_invalid:funds_deduction_payout:reason_missing, coverage_entry_invalid:max_payout_economic_boundary:status_invalid, coverage_entry_invalid:max_payout_economic_boundary:primary_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:candidate_issue_ids_not_array, coverage_entry_invalid:max_payout_economic_boundary:evidence_checked_missing, coverage_entry_invalid:max_payout_economic_boundary:reason_missing, coverage_entry_invalid:statistics_time_window:status_invalid, coverage_entry_invalid:statistics_time_window:primary_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:candidate_issue_ids_not_array, coverage_entry_invalid:statistics_time_window:evidence_checked_missing, coverage_entry_invalid:statistics_time_window:reason_missing, missed_finding_not_in_confirmed_add:FUNDS_DEBIT_TIMING, missed_finding_not_in_confirmed_add:FUNDS_PAYOUT_TIMING, missed_finding_not_in_confirmed_add:FUNDS_FAILURE_COMPENSATION, missed_finding_not_in_confirmed_add:ECON_POOL_NEGATIVE_FLOOR, missed_finding_not_in_confirmed_add:ECON_SINGLE_ROUND_CAP, missed_finding_not_in_confirmed_add:STAT_WINDOW_UI_TEXT, coverage_schema_version_too_old:1:required:2
  - 拒绝《玩家本金扣款节点未定义，重复投注/断线/结算退出场景的扣款幂等缺失》：multiroot_funds_debit_and_payout_combined, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《派奖到账节点未定义，奖池透支回填异常时的派奖补偿策略缺失》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《扣款/派奖失败的回滚、补偿与幂等机制完全缺失》：multiroot_funds_debit_and_payout_combined, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《奖池允许透支为负但未定义负值下限与回填失败兜底》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《单局/单选项/单用户赔付无绝对金额封顶，仅依赖 80% 奖池软兜底》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《开奖分析统计窗口正文写'最近7天'但UI截图显示'Last 30 day'，同指标窗口冲突》：coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确抓住 CLARITY_01（赔率冲突）、LOGIC_01（0赔付兜底缺陷）、LOGIC_02（正常状态概率冲突）三个高信号核心阻塞项，与共享输入证据完全吻合。
- CLARITY_02 机器人机制缺失与图22流程图形成对照，证据链完整。
- CLARITY_03 开奖分析白名单矛盾定位精准（表格1 vs 表格3）。
- SEC_01 实时计算快照时机问题属于高价值安全边界补漏。
- 维度覆盖完整，未出现跨文档误判，单文档场景处理正确。

## 问题
- 资金链路三控制面（debit_timing / payout_timing / funds_failure_compensation）完全未覆盖，文档中仅描述投入交互与结算弹窗展示，未明确扣款节点、派奖到账节点与失败回滚。
- max_payout_economic_boundary 中 single_round_payout_cap（单局赔付封顶）与 pool_negative_floor（奖池负值下限）未独立核查，仅以 80% 软兜底代替。
- statistics_time_window 中 ui_text_window_alignment 未识别：表格3写'最近7天（Last 7 days）'，图13 UI 显示'Last 30 day'，属于同指标窗口正文与UI冲突。
- 下注倒计时正文写 20s（段落/图6/图7规则），但图1/图3/图17 UI 显示 '(15)'，主模型未识别此正文与UI冲突。
- LOGIC_01 与 LOGIC_02 的 current_state 为单段混写，未按分点展开子症状，不利于开发逐项验收。
- top_blockers 中 LOGIC_02 的 why_now 混入了断线重连描述，与标题（概率冲突）不匹配，属于症状串位。

## 复核备注
- 主模型 LOGIC_02 的 why_now 混入了断线重连描述，与标题（概率冲突）不匹配，已在候选稿中修正。
- 主模型 LOGIC_01 与 LOGIC_02 的 current_state 为单段混写，已在候选稿中分点展开子症状，增强可验收性。
- 下注倒计时正文与UI冲突（20s vs 15s）已写入 quality_notes 与 image_analysis_gaps，未单独落盘为 finding，因证据强度不足以判定为高阻塞根因。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：ECON_POOL_NEGATIVE_FLOOR
- phase2 准入已从 candidate 移除 rejected addition：ECON_SINGLE_ROUND_CAP
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_DEBIT_TIMING
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_FAILURE_COMPENSATION
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_PAYOUT_TIMING
- phase2 准入已从 candidate 移除 rejected addition：STAT_WINDOW_UI_TEXT

## 不支持的问题
- 暂无

## 合并建议
- 暂无
