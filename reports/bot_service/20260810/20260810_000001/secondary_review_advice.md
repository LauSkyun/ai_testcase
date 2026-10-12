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
- phase2 新增准入：声称 1，通过 0，拒绝 1
- coverage ledger：未通过，完整率 100%
- coverage confirmed_add：funds_deduction_payout
- coverage confirmed controls：payout_timing
- coverage ledger 错误：coverage_control_invalid:max_payout_economic_boundary:pool_negative_floor:primary_control_mismatch:NUM-CTRL-01
  - 拒绝《中奖金额计入玩家钱包的产品节点未定义》：coverage_ledger_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 完整保留 Primary 骨架、评分和核心问题。

## 问题
- 暂无

## 复核备注
- settlement_formula 控制面：表格3-6示例已隐含收回金额=投注金额×赔率的计算逻辑，但服务端结算公式、变量与计算顺序未显式定义，建议补充结算接口字段说明。
- termination_priority 控制面：表格7已定义8阶段顺序流程，但各阶段提前终止、冲突分支优先级未显式说明，建议补充状态机异常分支处理。
- funds_failure_compensation 控制面：两份文档均未提及资金事务失败后的回滚、补发、重试与幂等规则，假设由平台/中台统一承接，建议补充玩法侧与中台的对接说明。
- single_round_payout_cap 控制面：相对倍率上限x8与最高投注额10,000,000已形成隐含封顶（80,000,000），但未显式定义单局绝对赔付金额封顶，建议补充配置项。
- protocol_profile=phase2_v2_2; evidence_packet_id=f9f1fc8f8b12491799a4deb117996911f3ee11f7083c51d5261b2160ff2d4558
- phase2 准入已从 candidate 移除 rejected addition：REQ-FUNDS-01
- candidate_generation_mode=deterministic_primary_plus_admitted_delta

## 不支持的问题
- 暂无

## 合并建议
- 暂无
