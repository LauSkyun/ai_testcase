# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.4
- 副模型：gpt-5.4
- 默认最终报告来源：pipeline
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_pipeline.md

## 推荐门槛
- 推荐状态：fallback_pipeline
- 未通过原因：normalized_candidate_not_ready, candidate_missing_issue_id, candidate_major_judgment_drift
- 阻断分类：protocol_blockers=candidate_missing_issue_id; quality_blockers=candidate_major_judgment_drift; readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：candidate 与 primary 存在较大结论漂移，但副评审未给出足够改判依据，当前不建议默认直出。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
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
- Candidate：B
- Selected：C
- Pipeline 问题数：5
- Candidate 问题数：6
- Selected 问题数：5

## Trace 摘要
- raw：kept=4, added=1, merged=0, dropped=0
- materialized：kept=4, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- block reasons：normalized_candidate_not_ready, candidate_missing_issue_id, candidate_major_judgment_drift

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：3
- 重大改写示例：推展机制在需求文档中完全缺失；缩位展示的'向下取整'与'直接截断'表述冗余；RESPIN触发条件、结算公式、风控优先级、自动旋转、数值验证五重冲突
