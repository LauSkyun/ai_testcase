# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.6-sol
- 副模型：gpt-5.6-sol
- 默认最终报告来源：pipeline
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_pipeline.md

## 推荐门槛
- 推荐状态：fallback_pipeline
- 未通过原因：normalized_candidate_not_ready
- 阻断分类：readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：候选报告需要移除低信号问题、补充遗漏的高信号问题，并修正对游戏设计的误判后才能直接输出
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
- Candidate：C
- Selected：C
- Pipeline 问题数：10
- Candidate 问题数：10
- Selected 问题数：10

## Trace 摘要
- raw：kept=7, added=3, merged=0, dropped=0
- materialized：kept=7, added=3, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- block reasons：normalized_candidate_not_ready

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：7
- 重大改写示例：Repeat按钮复用多选项投入的逻辑未定义；亏损大R的'最近{3}局'定义边界不清；奖池不抽水触发条件的时间口径不一致；兜底赔付逻辑歧义可能导致奖池无底线透支；投入阶段时长在流程图与UI截图中严重冲突；机器人是否计入核心策略的'投入人数'口径未定义；后台广播'可见占比'配置定义模糊，无法落地
