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
- lineage 原始统计：kept=6, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=6, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 3，通过 0，拒绝 3
- coverage ledger：未通过，完整率 83%
- coverage confirmed_add：funds_deduction_payout, max_payout_economic_boundary
- coverage confirmed controls：debit_timing, payout_timing, pool_negative_floor
- coverage ledger 错误：coverage_audit_key_order_invalid, coverage_entry_invalid:index_4:audit_key_invalid, coverage_entry_invalid:index_4:controls_not_array
  - 拒绝《玩家本金扣除/冻结的事务触发节点缺失》：coverage_ledger_invalid
  - 拒绝《中奖金额计入玩家钱包的事务触发节点缺失》：coverage_ledger_invalid
  - 拒绝《奖池为负时的透支下限与熔断条件缺失》：coverage_ledger_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 完整保留 Primary 骨架、评分和核心问题。

## 问题
- 暂无

## 复核备注
- funds_failure_compensation 因无明确中台引用证据，按规则降级为 advice_only，建议补充资金事务失败的回滚与补偿机制。
- single_round_payout_cap 因存在最高投注额与最高赔率乘积的数学有限边界，按规则降级为 advice_only，建议明确多符号叠加时的单局绝对赔付封顶。
- protocol_profile=phase2_v2_2; evidence_packet_id=92560100b340b430f324d6c196130cd53ba7ba72b8f9c66692a70632f5d48ade
- phase2 准入已从 candidate 移除 rejected addition：ECON-01
- phase2 准入已从 candidate 移除 rejected addition：FUND-01
- phase2 准入已从 candidate 移除 rejected addition：FUND-02
- candidate_generation_mode=deterministic_primary_plus_admitted_delta

## 不支持的问题
- 暂无

## 合并建议
- 暂无
