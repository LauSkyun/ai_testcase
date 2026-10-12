# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心UI冲突、奖池结算漏洞和异常流程缺失等高信号问题，但将低风险配置占位符混入高严重度问题，并遗漏了开奖分析统计范围这一UI冲突。整体结构清晰，证据充分，经少量修正后可直接输出。

- 建议等级：low
- 是否建议候选稿直出：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 可追踪性：partial
- readiness 是否冲突：否
- candidate 是否有结构漂移：是
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
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; readiness_blockers=normalized_candidate_not_ready

## 优点
- 抓住了文档中多处UI与配置的致命冲突，有明确的证据定位
- 奖池结算链路的漏洞分析深入，指出了套利风险
- 问题分维度呈现，测试点和缺失信息列表实用

## 问题
- 将奖池收益率统计口径的占位符问题作为高严重度UI冲突的一部分，混淆了风险等级
- 遗漏了开奖分析模块胜率统计范围（7天 vs 30天）的UI冲突

## 复核备注
- 移除了原UI冲突问题中关于奖池收益率统计口径占位符的描述，将其降级为quality_notes中的低风险提醒，避免混淆严重度。
- 补充了开奖分析统计范围（7天 vs 30天）的UI冲突，并吸收到原有的UI冲突问题中。
- 调整了top_blockers标题以反映新增的统计范围冲突。
- dual_pass trace 提示：candidate_lineage 不为空，但未完整覆盖 primary/candidate 的问题血缘；当前候选稿暂不建议默认直出。
- dual_pass trace 提示：candidate 存在未被 lineage 覆盖的问题映射，需补齐 kept/added/merged/dropped 后再考虑默认直出。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
