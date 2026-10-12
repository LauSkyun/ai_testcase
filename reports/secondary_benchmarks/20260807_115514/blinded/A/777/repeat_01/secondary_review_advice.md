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
- lineage 原始统计：kept=9, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=9, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 0，通过 0，拒绝 0
- coverage ledger：未通过，完整率 100%
- coverage ledger 错误：coverage_control_invalid:settlement_formula_ui_config:settlement_formula:decision_source_state_invalid, coverage_control_invalid:settlement_formula_ui_config:settlement_formula:decision_primary_coverage_invalid, coverage_control_invalid:settlement_formula_ui_config:ui_config_mapping:decision_source_state_invalid, coverage_control_invalid:settlement_formula_ui_config:ui_config_mapping:decision_primary_coverage_invalid, coverage_control_invalid:trigger_state_termination:trigger_entry:decision_source_state_invalid, coverage_control_invalid:trigger_state_termination:trigger_entry:decision_primary_coverage_invalid, coverage_control_invalid:trigger_state_termination:termination_priority:decision_source_state_invalid, coverage_control_invalid:trigger_state_termination:termination_priority:decision_primary_coverage_invalid, coverage_control_invalid:funds_deduction_payout:debit_timing:decision_source_state_invalid, coverage_control_invalid:funds_deduction_payout:payout_timing:decision_source_state_invalid, coverage_control_invalid:funds_deduction_payout:funds_failure_compensation:decision_source_state_invalid, coverage_control_invalid:max_payout_economic_boundary:relative_payout_cap:decision_source_state_invalid, coverage_control_invalid:max_payout_economic_boundary:relative_payout_cap:decision_primary_coverage_invalid, coverage_control_invalid:max_payout_economic_boundary:pool_negative_floor:decision_source_state_invalid, coverage_control_invalid:max_payout_economic_boundary:single_round_payout_cap:decision_source_state_invalid, coverage_control_invalid:statistics_time_window:same_metric_window:decision_source_state_invalid, coverage_control_invalid:statistics_time_window:ui_text_window_alignment:decision_source_state_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 完整保留 Primary 骨架、评分和核心问题。

## 问题
- 暂无

## 复核备注
- payout_timing 原文仅描述‘获得奖励金额’与‘展示中奖金额’，未明确钱包入账/余额增加的事务节点，建议补充结算后资金到账的明确说明。
- funds_failure_compensation 原文引用中台统一处理流程，建议确认中台流程是否完全覆盖RESPIN状态下的断线恢复与资金回滚。
- single_round_payout_cap 原文存在100倍强制0倍的相对上限，建议评估在极高下注额下是否需要补充绝对金额封顶。
- protocol_profile=phase2_v2_2; evidence_packet_id=8e0da672cf5b111a8037b391519192483e42dc166a2ebcef5c045cef81585f02
- candidate_generation_mode=deterministic_primary_plus_admitted_delta

## 不支持的问题
- 暂无

## 合并建议
- 暂无
