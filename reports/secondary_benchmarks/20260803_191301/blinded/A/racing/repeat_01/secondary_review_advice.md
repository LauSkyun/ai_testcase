# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率公式冲突、假数据隔离、真假赔率映射、干预逻辑落地等关键阻塞项，问题结构清晰、证据定位准确、严重度判定合理。候选稿基本沿用主模型骨架，仅补充一条关于下注扣款时机的高信号缺口。

- 建议等级：low
- 是否建议候选稿直出：否
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
- lineage 原始统计：kept=8, added=1, merged=0, dropped=0
- lineage 实际落盘统计：kept=8, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- phase2 新增准入：声称 1，通过 1，拒绝 0
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready, candidate_missing_issue_id
- 阻断分类：protocol_blockers=candidate_missing_issue_id; readiness_blockers=normalized_candidate_not_ready

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
- dual_pass candidate 含空 issue_id 问题项，当前仅作为对比稿，不建议默认直出。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
