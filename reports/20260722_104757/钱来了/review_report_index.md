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
- 原因：候选报告已修正误判并补充关键遗漏，结构完整、证据充分、来源可追踪，可直接交付业务方用于澄清与修复。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- candidate 是否达到结构直出门槛：是
- primary issue_id 修复数：3
- candidate issue_id 修复数：3
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
- Candidate：D
- Selected：D
- Pipeline 问题数：9
- Candidate 问题数：9
- Selected 问题数：9

## Trace 摘要
- raw：kept=6, added=3, merged=0, dropped=0
- materialized：kept=6, added=3, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：5
- 重大改写示例：基础盘面生成逻辑与中奖判定条件根本冲突；核心数值上限与风控规则根本冲突；购买免费游戏（Feature Buy）核心规则与数值缺失；RESPIN发生几率存在两份冲突的配置表；推展与重转的互斥关系及客户端表演逻辑描述存在歧义
