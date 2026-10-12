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
- 未通过原因：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_primary_findings, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_primary_findings,candidate_traceability_partial; readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。
- 可追踪性：partial
- readiness 是否冲突：是
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
- Candidate：D
- Selected：C
- Pipeline 问题数：10
- Candidate 问题数：9
- Selected 问题数：10

## Trace 摘要
- raw：kept=4, added=5, merged=0, dropped=0
- materialized：kept=4, added=5, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_primary_findings, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：1
- Candidate 独有问题数：0
- 共享问题中的重大改写数：6
- Pipeline 独有示例：推展机制在需求文档中未作为功能需求描述，仅动效暗示，导致功能范围不明确
- 重大改写示例：1倍乘数符号在需求文档中缺失，UI资源未定义；respin次数限制：需求文档与数值文档描述根本冲突，必须统一实现方式；风控检查与推展机制的时序冲突，可能导致推展后的高倍率绕过风控；respin中断恢复/重进的玩法专属状态规则缺失，测试无法验证；自动旋转点击停止后需等待respin完成才停止，用户可能误以为停止无效；需求文档未描述不中奖时的任何动效或反馈，可能造成体验空白
