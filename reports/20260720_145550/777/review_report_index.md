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
- 原因：主模型报告准确识别了核心问题，但严重度评估需要调整，多个子症状需要分点整理，建议经本次复核修正后再输出最终报告。
- 可追踪性：complete
- readiness 是否冲突：否
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
- Candidate：B
- Selected：C
- Pipeline 问题数：6
- Candidate 问题数：5
- Selected 问题数：6

## Trace 摘要
- raw：kept=5, added=0, merged=0, dropped=0
- materialized：kept=5, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- block reasons：normalized_candidate_not_ready

## 差异摘要
- Pipeline 独有问题数：1
- Candidate 独有问题数：0
- 共享问题中的重大改写数：3
- Pipeline 独有示例：RESPIN累加公式的表述歧义与示例错误
- 重大改写示例：基础盘面组合符号判定优先级与边界模糊；两份文档对“空白”符号的指代存在歧义；RESPIN累加公式与风控规则存在致命冲突
