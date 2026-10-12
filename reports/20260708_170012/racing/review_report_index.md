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
- Pipeline 问题数：6
- Candidate 问题数：7
- Selected 问题数：6

## Trace 摘要
- raw：kept=5, added=1, merged=0, dropped=0
- materialized：kept=5, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：1
- 共享问题中的重大改写数：5
- Candidate 独有示例：假数据注入对实时赔率计算的污染风险
- 重大改写示例：奖池状态计算公式存在分母为0的致命缺陷及阈值占位符；开奖时间T的动态计算与固定5S动画表现存在冲突；“干扰指数”与“Luck(随机扰动)”的映射关系缺失；新用户/流失用户干预与奖池干预的优先级与风控冲突；引导局（蒙层引导）经济隔离规则完全缺失
