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
- 未通过原因：quality_assessment_not_ready, candidate_readiness_not_ready, readiness_conflict, normalized_candidate_not_ready, suggestion_level_high
- 阻断分类：quality_blockers=quality_assessment_not_ready,suggestion_level_high; readiness_blockers=candidate_readiness_not_ready,readiness_conflict,normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。
- 血缘追踪状态：complete
- readiness 是否冲突：是
- candidate 是否存在结构漂移：否
- candidate 是否达到结构直出门槛：是
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突执行 override：否
- 当前是否仅被编辑判断阻断：否
- advice 与 candidate 落盘是否不一致：否
- candidate 是否发生过结构变化：是
- 结构变化是否已被 lineage 解释：是

## 产物路径
- Pipeline：review_report_pipeline.md
- Candidate：review_report_candidate.md
- Advice：secondary_review_advice.md

## 评分与问题数
- Primary：C
- Pipeline：C
- Candidate：C
- Selected：C
- Pipeline 问题数：8
- Candidate 问题数：8
- Selected 问题数：8

## Trace 摘要
- raw：kept=7, added=1, merged=0, dropped=0
- materialized：kept=7, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- block reasons：quality_assessment_not_ready, candidate_readiness_not_ready, readiness_conflict, normalized_candidate_not_ready, suggestion_level_high

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：2
- 共享问题重大改写示例：基础与RESPIN权重配置全为100，概率无差异，RTP无法控制；推展机制的客户端表现与服务端结果对齐验收缺失
