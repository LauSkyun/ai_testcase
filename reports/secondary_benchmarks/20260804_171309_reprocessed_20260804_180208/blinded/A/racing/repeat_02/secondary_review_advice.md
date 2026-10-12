# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率公式冲突、假数据隔离、真假赔率映射等关键问题，但在结算链路的扣款时机、派奖时机和资金失败补偿方面存在明显遗漏，这些是直接影响结算实现的高信号缺口。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选报告在保留主模型核心发现的基础上，补充了结算链路的关键缺口（扣款时机、派奖时机、资金失败补偿机制），结构完整、证据充分、来源可追踪，可直接给业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=8, added=1, merged=0, dropped=0
- lineage 实际落盘统计：kept=8, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- phase2 新增准入：声称 3，通过 1，拒绝 2
- coverage ledger：通过，完整率 100%
- coverage confirmed_add：funds_deduction_payout
- coverage confirmed controls：debit_timing, payout_timing, funds_failure_compensation
- coverage 安全归一化：inferred_coverage_schema_version:2_from_complete_control_shape
  - 拒绝《派奖到账时机未明确，影响结算事务实现》：primary_duplicate_after_normalization
  - 拒绝《资金失败补偿机制未明确，包括扣款失败、派奖失败、奖池不足等场景》：evidence_position_unlocatable

## 优点
- 准确识别了T变量在开奖时间公式和赔率公式中的定义冲突
- 正确指出假数据参与实时赔率计算的风险
- 清晰识别了实际赔率与假赔率的展示与结算映射缺失
- 合理识别了干预逻辑到速度公式的映射缺口

## 问题
- 遗漏了扣款时机（debit_timing）的明确说明，影响结算事务实现
- 遗漏了派奖时机（payout_timing）的明确说明，影响结算事务实现
- 遗漏了资金失败补偿机制（funds_failure_compensation），包括扣款失败、派奖失败、奖池不足等场景的回滚与补偿逻辑

## 复核备注
- 主模型报告准确识别了核心赔率公式冲突、假数据隔离、真假赔率映射等关键问题，但在结算链路的扣款时机、派奖时机和资金失败补偿方面存在明显遗漏。
- 新增的三个finding（DEBIT_TIMING_MISSING、PAYOUT_TIMING_MISSING、FUNDS_FAILURE_COMPENSATION_MISSING）是结算链路的关键缺口，直接影响结算事务实现和资金安全。
- 根据phase2协议，funds_deduction_payout的三个control（debit_timing、payout_timing、funds_failure_compensation）具有不同的触发点、失败补偿和验收闭环，必须拆分为独立的candidate_issue_id。
- coverage_ledger已完成全部12个control的核对，其中3个为confirmed_add，4个为covered_by_primary，5个为no_issue。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：FUNDS_FAILURE_COMPENSATION_MISSING
- phase2 准入已从 candidate 移除 rejected addition：PAYOUT_TIMING_MISSING

## 不支持的问题
- 暂无

## 合并建议
- 暂无
