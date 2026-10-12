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
- 未通过原因：normalized_candidate_not_ready
- 阻断分类：readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。
- 可追踪性：complete
- readiness 是否冲突：是
- candidate 是否有结构漂移：否
- candidate 是否达到结构直出门槛：是
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
- Pipeline 问题数：4
- Candidate 问题数：4
- Selected 问题数：4

## Trace 摘要
- raw：kept=4, added=0, merged=0, dropped=0
- materialized：kept=4, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- block reasons：normalized_candidate_not_ready

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：4
- 重大改写示例：第4列（特殊轴）的盘面结构与中奖连线规则描述冲突；推展机制的触发条件与表现逻辑不清晰；风控规则（>=100倍强制0倍）与RESPIN玩法的潜在致命冲突；UI缩位展示“直接截断”可能引发金额误解
