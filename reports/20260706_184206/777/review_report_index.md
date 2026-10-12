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
- 未通过原因：quality_assessment_not_ready, candidate_readiness_not_ready, readiness_conflict, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; quality_blockers=quality_assessment_not_ready; readiness_blockers=candidate_readiness_not_ready,readiness_conflict,normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。
- 血缘追踪状态：partial
- readiness 是否冲突：是
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
- Candidate：C
- Selected：C
- Pipeline 问题数：6
- Candidate 问题数：6
- Selected 问题数：6

## Trace 摘要
- raw：kept=4, added=0, merged=1, dropped=0
- materialized：kept=4, added=0, merged=1, dropped=0
- added 落盘状态：none
- merged 落盘状态：complete
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：quality_assessment_not_ready, candidate_readiness_not_ready, readiness_conflict, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：4
- 共享问题重大改写示例：“组合结果为空白”指代不明导致结算逻辑歧义；推展机制的“倍数>5倍”指代不明且与风控存在潜在冲突；金额缩位展示的“向下取整”与“直接截断”需统一验收口径；需求文档“连成一线”表述易导致玩家与程序理解偏差
