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
- 未通过原因：quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; quality_blockers=quality_assessment_not_ready; readiness_blockers=candidate_readiness_not_ready,normalized_candidate_not_ready
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
- Pipeline 问题数：10
- Candidate 问题数：11
- Selected 问题数：10

## Trace 摘要
- raw：kept=5, added=5, merged=0, dropped=0
- materialized：kept=5, added=5, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：1
- 共享问题中的重大改写数：7
- Candidate 独有示例：历史局配置热更处理规则缺失
- 共享问题重大改写示例：扣款时机未明确；按钮状态变化（开始/继续）未明确；重复点击幂等性与并发控制缺失；异常流程（弱网、重复点击、并发）验收标准缺失；服务端权威性未明确声明；跨文档难度档位映射与概率/倍率数据冲突；通关条件、格子总数与‘超级大奖’规则缺失/冲突
