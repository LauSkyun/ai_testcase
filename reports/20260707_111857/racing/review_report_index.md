# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.4
- 副模型：deepseek-v4-pro
- 默认最终报告来源：pipeline
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_pipeline.md

## 推荐门槛
- 推荐状态：fallback_pipeline
- 未通过原因：quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_missing_issue_id, candidate_traceability_partial
- 阻断分类：protocol_blockers=candidate_missing_issue_id; traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; quality_blockers=quality_assessment_not_ready; readiness_blockers=candidate_readiness_not_ready,normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 血缘追踪状态：partial
- readiness 是否冲突：否
- candidate 是否存在结构漂移：是
- candidate 是否达到结构直出门槛：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突执行 override：否
- 当前是否仅被编辑判断阻断：否
- advice 与 candidate 落盘是否不一致：否
- candidate 是否发生过结构变化：是
- 结构变化是否已被 lineage 解释：否

## 产物路径
- Pipeline：review_report_pipeline.md
- Candidate：review_report_candidate.md
- Advice：secondary_review_advice.md

## 评分与问题数
- Primary：C
- Pipeline：C
- Candidate：D
- Selected：C
- Pipeline 问题数：7
- Candidate 问题数：8
- Selected 问题数：7

## Trace 摘要
- raw：kept=6, added=0, merged=0, dropped=0
- materialized：kept=6, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_missing_issue_id, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：1
- 共享问题中的重大改写数：2
- Candidate 独有示例：核心赔率计算公式在需求与数值文档中存在严重冲突
- 共享问题重大改写示例：开奖干预逻辑优先级与参数映射歧义；“假赔率”机制的UI展示与真实结算映射缺失
