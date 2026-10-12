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
- lineage 原始统计：kept=8, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=8, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 2，通过 0，拒绝 2
- coverage ledger：未通过，完整率 100%
- coverage confirmed_add：funds_deduction_payout
- coverage confirmed controls：debit_timing, payout_timing
- coverage ledger 错误：coverage_control_invalid:settlement_formula_ui_config:settlement_formula:decision_primary_coverage_status_mismatch, coverage_control_invalid:settlement_formula_ui_config:ui_config_mapping:decision_primary_coverage_status_mismatch, coverage_control_invalid:max_payout_economic_boundary:relative_payout_cap:decision_primary_coverage_status_mismatch, coverage_control_invalid:max_payout_economic_boundary:pool_negative_floor:decision_primary_coverage_status_mismatch, coverage_control_invalid:max_payout_economic_boundary:single_round_payout_cap:decision_primary_coverage_status_mismatch
  - 拒绝《下注本金扣除与冻结的事务触发节点未定义》：coverage_ledger_invalid
  - 拒绝《中奖金额计入玩家钱包的入账事务节点未定义》：coverage_ledger_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 完整保留 Primary 骨架、评分和核心问题。

## 问题
- 暂无

## 复核备注
- Primary对单局最大赔付风险（MAX_PAYOUT_RISK）的判断未充分结合段落32中‘单选项单轮次最多下注100万宝石’的绝对边界限制，建议复核该上限对极端赔付风险的兜底作用。
- 资金事务链路（扣款与派奖）的节点定义缺失属于核心交易阻塞项，已作为增量确认，需优先补充。
- protocol_profile=phase2_v2_2; evidence_packet_id=0b38b9b8cda38b98a2bba023238509e609abc98c83f73391cee623706bc74b87
- phase2 准入已从 candidate 移除 rejected addition：DEBIT_TIMING_MISSING
- phase2 准入已从 candidate 移除 rejected addition：PAYOUT_TIMING_MISSING
- candidate_generation_mode=deterministic_primary_plus_admitted_delta

## 不支持的问题
- 暂无

## 合并建议
- 暂无
