# Dual Pass 副评审建议

## 总体判断
主模型报告抓住了核心矛盾，问题排序合理，证据引用充分，但在跨文档问题合并、假数据隔离等关键缺失上仍有不足，且存在跨文档问题未归入维度的问题。

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
- lineage 原始统计：kept=8, added=1, merged=0, dropped=1
- lineage 实际落盘统计：kept=8, added=1, merged=0, dropped=1
- added 问题落盘状态：complete
- 当前不建议默认切 candidate 的原因：warning_present, quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_traceability_partial; quality_blockers=warning_present,quality_assessment_not_ready; readiness_blockers=candidate_readiness_not_ready,normalized_candidate_not_ready

## 优点
- 准确识别了赔率公式双轨制冲突、干预逻辑优先级矛盾、数值变量缺失等关键阻塞点
- 证据引用具体，段落与图片编号清晰
- 严重度分级合理，高风险问题均与结算链路直接相关

## 问题
- 未将跨文档赔率冲突归入维度，导致重复和结构瑕疵
- 遗漏了假数据（人数/金额）可能参与真实赔率计算的隔离风险
- 引导局资金属性未明确，仅关注强制交互，未覆盖资产真实性风险
- 开奖时间计算中总时间与分段L的关系未澄清

## 复核备注
- 主模型报告中的 cross_document_issues 已合并至清晰度与完整性维度下的“赔率体系冲突”问题，避免重复。
- 新增了“假数据隔离缺失”问题，归属安全性与反作弊，以覆盖数据源隔离风险。
- 在“数值变量缺失”中补充了开奖总时间计算方式未明确的说明。
- 在“引导误扣款”中增加了引导局资金属性未明确的描述。
- 所有 kept finding 均保持原 issue_id，仅做了最小化修改，未破坏主模型问题骨架。
- dual_pass trace 提示：candidate_lineage 不为空，但未完整覆盖 primary/candidate 的问题血缘；当前候选稿暂不建议默认直出。

## 不支持的问题
- 暂无

## 合并建议
- ：两者本质为同一赔率冲突问题，应合并为一个维度内的finding，避免重复。
