# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.4
- 副模型：deepseek-v4-pro
- 默认最终报告来源：candidate
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_candidate.md

## 推荐门槛
- 推荐状态：recommended
- 未通过原因：无
- Candidate 直出建议：是
- 原因：候选报告已修正主要误判，补充了关键细节，结构完整，证据充分，可直接交付业务方。
- 血缘追踪状态：complete
- readiness 是否冲突：否
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
- Candidate：B
- Selected：B
- Pipeline 问题数：5
- Candidate 问题数：5
- Selected 问题数：5

## Trace 摘要
- raw：kept=5, added=0, merged=0, dropped=0
- materialized：kept=5, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：5
- 共享问题重大改写示例：基础盘面空白与乘数空白的赔付逻辑在两份文档中严重冲突；排行榜与中奖记录的统计维度与数据来源未定义；推展机制的结算归属与风控规则存在潜在冲突；基础盘面“表演权重”的抽样与映射规则缺失；自动/快捷旋转在RESPIN长序列下的状态流转缺失
