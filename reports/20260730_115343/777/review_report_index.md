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
- 未通过原因：normalized_candidate_not_ready, advice_candidate_structure_mismatch, candidate_materialized_missed_without_added, candidate_major_judgment_drift
- 阻断分类：protocol_blockers=advice_candidate_structure_mismatch; traceability_blockers=candidate_materialized_missed_without_added; quality_blockers=candidate_major_judgment_drift; readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：candidate_lineage 对 candidate 结构的说明与最终落盘结果不一致，当前候选稿不可作为默认最终输出。
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
- advice 与 candidate 落盘是否一致：否
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
- Pipeline 问题数：7
- Candidate 问题数：7
- Selected 问题数：7

## Trace 摘要
- raw：kept=6, added=1, merged=0, dropped=0
- materialized：kept=6, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- block reasons：normalized_candidate_not_ready, advice_candidate_structure_mismatch, candidate_materialized_missed_without_added, candidate_major_judgment_drift

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：2
- 重大改写示例：RESPIN乘数符号1倍配置及公式定义在两文档中不一致；需求文档缺失推展机制、风控机制、卷轴方案选择和RESPIN乘数表，与数值文档不一致
