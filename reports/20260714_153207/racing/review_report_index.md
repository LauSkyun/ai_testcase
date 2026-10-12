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
- 未通过原因：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 可追踪性：partial
- readiness 是否冲突：否
- candidate 是否有结构漂移：是
- candidate 是否达到结构直出门槛：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- 当前是否仅被编辑性判断阻断：否
- advice 与 candidate 落盘是否一致：是
- 是否存在无依据的高信号问题降级：否
- candidate 是否存在过度收缩：否

## 产物路径
- Pipeline：review_report_pipeline.md
- Candidate：review_report_candidate.md
- Advice：secondary_review_advice.md

## 评分与问题数
- Primary：C
- Pipeline：C
- Candidate：C
- Selected：C
- Pipeline 问题数：11
- Candidate 问题数：11
- Selected 问题数：11

## Trace 摘要
- raw：kept=10, added=0, merged=1, dropped=0
- materialized：kept=10, added=0, merged=1, dropped=0
- added 落盘状态：none
- merged 落盘状态：complete
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：3
- 重大改写示例：假数据注入对赔率计算的污染及口径分裂；赔率结算公式双轨制冲突导致结算链路无法实现；开奖时间T与固定5s动画的映射缺失
