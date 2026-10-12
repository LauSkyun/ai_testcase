# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：deepseek-v4-pro
- 副模型：deepseek-v4-pro
- 默认最终报告来源：pipeline
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_pipeline.md

## 推荐门槛
- 推荐状态：fallback_pipeline
- 未通过原因：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_major_judgment_drift, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; quality_blockers=candidate_major_judgment_drift; readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 可追踪性：partial
- readiness 是否冲突：否
- candidate 是否有结构漂移：是
- candidate 是否达到结构直出门槛：否
- primary issue_id 修复数：2
- candidate issue_id 修复数：2
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
- Primary：D
- Pipeline：D
- Candidate：B
- Selected：D
- Pipeline 问题数：9
- Candidate 问题数：9
- Selected 问题数：9

## Trace 摘要
- raw：kept=8, added=0, merged=1, dropped=0
- materialized：kept=8, added=0, merged=1, dropped=0
- added 落盘状态：none
- merged 落盘状态：complete
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_major_judgment_drift, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：5
- 重大改写示例：难度与概率、倍率池的映射关系混乱，超级大奖规则缺失；失败判定机制在需求文档与数值文档间表述不一致，且扣款时机、本金处理等规则缺失；开始、提现按钮缺乏防重复点击机制，无幂等说明；提现过程中退出或异常关闭的处理规则缺失；未定义配置热更时对进行中游戏的影响，以及历史局数据存储
