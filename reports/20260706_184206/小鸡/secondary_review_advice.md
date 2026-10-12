# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心数值模型冲突（赔率表定义）和通关奖励缺失，但将下注筹码示例不一致误判为严重冲突，且遗漏了扣款时机、最大赔付、RTP映射等关键问题。

- 建议等级：medium
- 是否建议直接采用候选成稿：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 血缘追踪状态：partial
- readiness 是否冲突：否
- candidate 是否存在结构漂移：是
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突执行 override：否
- advice 与 candidate 落盘是否不一致：是
- candidate 是否发生过结构变化：是
- 结构变化是否已被 lineage 解释：否
- lineage 原始统计：kept=6, added=5, merged=0, dropped=0
- lineage 实际落盘统计：kept=6, added=3, merged=0, dropped=0
- added 问题落盘状态：partial
- 未落盘的 added issue_id：CLARITY_05, LOGIC_04
- 声称 added 但未落盘：CLARITY_05, LOGIC_04
- 当前不建议默认切 candidate 的原因：quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, advice_candidate_structure_mismatch, candidate_added_not_materialized, candidate_traceability_partial
- 阻断分类：protocol_blockers=advice_candidate_structure_mismatch,candidate_added_not_materialized; traceability_blockers=candidate_lineage_coverage_incomplete,candidate_traceability_partial; quality_blockers=quality_assessment_not_ready; readiness_blockers=candidate_readiness_not_ready,normalized_candidate_not_ready

## 优点
- 准确指出了赔率表定义歧义和通关奖励缺失，识别了异常流程缺失。

## 问题
- 将数值文档的下注示例与需求文档的筹码示例差异视为严重冲突，实际为示例不一致，可降级；
- 概率模型冲突可降级为需统一说明，并拆分处理；
- 遗漏了扣款时机、最大赔付/封顶、RTP与难度映射等关键规则。

## 复核备注
- 将CROSS_01严重度从高调整为低，因为数值文档已明确为示例，样本不一致不构成阻塞；
- CROSS_02被拆分，概率模型部分并入新建的LOGIC_04，角色形象部分并入CLARITY_05；
- 新增了扣款时机（CLARITY_04）、最大赔付（LOGIC_02）、RTP映射（LOGIC_03）等缺失项；
- CLARITY_01中的术语不统一问题已合并到LOGIC_04中处理，不再单独列出；
- top_blockers调整为赔率表歧义、通关大奖缺失、最大赔付缺失，其他原阻塞项已降级或拆分。
- dual_pass trace 提示：candidate_lineage 不为空，但未完整覆盖 primary/candidate 的问题血缘；当前候选稿暂不建议默认直出。
- dual_pass 补漏落盘提示：candidate_lineage.added 中声明的新增问题未完整落入最终 candidate。
- dual_pass 协议提示：部分 lineage.added 声称的新问题未实际落盘到最终 candidate。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
