# Dual Pass 副评审建议

## 总体判断
主模型报告抓住了核心冲突（数值模型不一致、最大赔付缺失、超级大奖规则缺失），并指出了部分边界条件缺失，整体结构清晰，证据定位较准确。但报告将一些可拆分的症状合并为同一问题，且对下注筹码冲突的严重度评估略高，同时在可测试性、服务端权威性等维度存在少量遗漏，建议补充低风险提醒。

- 建议等级：low
- 是否建议直接采用候选成稿：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 血缘追踪状态：partial
- readiness 是否冲突：否
- candidate 是否存在结构漂移：是
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突执行 override：否
- advice 与 candidate 落盘是否不一致：否
- candidate 是否发生过结构变化：是
- 结构变化是否已被 lineage 解释：否
- lineage 原始统计：kept=5, added=5, merged=0, dropped=0
- lineage 实际落盘统计：kept=5, added=5, merged=0, dropped=0
- added 问题落盘状态：complete
- 当前不建议默认切 candidate 的原因：quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; quality_blockers=quality_assessment_not_ready; readiness_blockers=candidate_readiness_not_ready,normalized_candidate_not_ready

## 优点
- 准确识别了数值文档中Crash算法与30步累乘表的根本冲突，以及MAX_PAYOUT缺失的经济风险
- 证据引用具体（文档名/章节/表格），问题描述与风险分析有闭环
- 维度覆盖较全面，测试点设计针对性强

## 问题
- 将下注筹码配置不一致（示例冲突）与难度数据冲突合并为同一高阻塞问题，但下注部分风险可降级
- 遗漏了扣款时机、按钮状态变化、幂等性说明、服务端权威性声明等边界条件，但均为低风险
- 可测试性维度未指出异常流程验收标准缺失，与测试点设计不完全匹配
- 部分描述（如“UI展示概率”与结算口径冲突）被合并进同一个大问题，可能导致读者忽略其独立影响

## 复核备注
- 保留主模型的问题骨架，仅对部分描述进行微调，并将下注筹码冲突的风险描述融入原问题中，未单独拆分。
- 补充了5个低风险遗漏点，均通过candidate_lineage.added记录，并追溯到missed_findings。
- 在可测试性维度新增了异常流程验收标准缺失问题，以匹配主模型测试点设计。
- 修正了主模型在‘逻辑一致性与数值平衡’维度中‘UI展示概率’子问题的描述，使其更明确地归属到用户体验风险，但仍在同一大问题内。
- 未对主模型的三项高阻塞问题进行降级，因为根本冲突依然存在且证据充分。
- candidate_report的评分保持C，因核心问题未解决，但补充了低风险提醒后，报告已可直接交付。
- dual_pass trace 提示：candidate_lineage 不为空，但未完整覆盖 primary/candidate 的问题血缘；当前候选稿暂不建议默认直出。
- dual_pass trace 提示：candidate 存在未被 lineage 覆盖的问题映射，需补齐 kept/added/merged/dropped 后再考虑默认直出。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
