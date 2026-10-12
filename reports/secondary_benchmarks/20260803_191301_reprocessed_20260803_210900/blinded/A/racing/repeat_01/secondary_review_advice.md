# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率公式冲突、假数据隔离、真假赔率映射、干预逻辑落地等关键阻塞项，问题结构清晰、证据定位准确、严重度判定合理。候选稿基本沿用主模型骨架，仅补充一条关于下注扣款时机的高信号缺口。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选稿已修正主模型重复表述、补全扣款时机缺口，结构完整、证据可追踪、lineage 清晰，可直接交付业务方阅读。
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
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:BET_DEDUCTION_TIMING
  - 拒绝《下注扣款时机与余额校验节点未明确，影响并发安全与幂等验收》：missing_fields:audit_key,root_causes,fact_check, multiroot_or_root_count_invalid, fact_check_invalid, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确抓住T变量在开奖时间公式与赔率公式中的语义冲突，并给出跨文档证据
- 将假数据参与赔率计算、真假赔率展示与结算映射、干预指数到速度公式的映射等核心阻塞项识别到位
- 对占位符、新手引导、音频混合等问题按评审原则做了合理降级
- lineage 结构完整，kept/added 划分清晰，未擅自删除高信号问题

## 问题
- T_VARIABLE_CONFLICT 的 current_state 与 risk 存在多处重复表述，可精简为分点展开
- 遗漏了下注扣款时机这一直接影响并发安全与幂等验收的高信号缺口
- top_blockers 中第 1、2 条的 why_now 字段存在拼接痕迹，可读性略差

## 复核备注
- 主模型 T_VARIABLE_CONFLICT 的 current_state 存在多处重复表述（如“变量定义歧义导致赔率公式无法正确编码”出现两次），候选稿已精简为分点展开，提升可读性。
- 主模型 top_blockers 中第 1、2 条的 why_now 字段存在拼接痕迹（如“；该问题可能导致开发、配置或测试对...”重复出现），候选稿已精简为单句核心风险。
- 候选稿新增 BET_DEDUCTION_TIMING 问题，补充下注扣款时机与余额校验节点这一高信号缺口，该问题直接影响并发安全与幂等验收。
- 根据 phase2 协议，候选稿完整保留主模型的 issue_id、问题顺序、维度、评分和 Top Blocker，仅物化增量。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：BET_DEDUCTION_TIMING

## 不支持的问题
- 暂无

## 合并建议
- 暂无
