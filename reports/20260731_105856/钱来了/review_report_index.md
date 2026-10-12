# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.6-sol
- 副模型：gpt-5.6-sol
- 默认最终报告来源：candidate
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_candidate.md

## 推荐门槛
- 推荐状态：recommended
- 未通过原因：无
- Candidate 直出建议：是
- 原因：候选报告已修正主模型的证据引用缺口、补充了关键数值概念区分、并在kept finding中分点展开子症状，结构完整、证据可追踪、严重度判定合理，可直接输出给业务方阅读。
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
- Pipeline 问题数：8
- Candidate 问题数：6
- Selected 问题数：6

## Trace 摘要
- raw：kept=6, added=0, merged=0, dropped=0
- materialized：kept=6, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：2
- Candidate 独有问题数：0
- 共享问题中的重大改写数：6
- Pipeline 独有示例：RESPIN与推展的优先级互斥规则未在需求文档中同步说明；数值文档表格3中'表演权重'与'出现权重'两列的定义区分缺失
- 重大改写示例：推展机制的'上下'方向与1x3盘面结构冲突；中奖金额计算公式与符号定义术语歧义；乘数符号ID=0的表演权重替换逻辑表述不清；底层数据生成规则与RESPIN触发条件矛盾；风控倍数基数与免费游戏封顶规则冲突；免费游戏续杯概率与购买规则配置缺失
