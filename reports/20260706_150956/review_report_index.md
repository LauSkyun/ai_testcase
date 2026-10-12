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
- 原因：候选报告修正了主模型对公式一致性的误判，并补充了RESPIN阶段权重缺失，报告结构完整，可直接交付业务方。
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
- Pipeline 问题数：7
- Candidate 问题数：5
- Selected 问题数：5

## Trace 摘要
- raw：kept=5, added=0, merged=0, dropped=0
- materialized：kept=5, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：2
- Candidate 独有问题数：0
- 共享问题中的重大改写数：2
- Pipeline 独有示例：RESPIN次数与乘数符号权重概率未定义，影响RTP核算；RESPIN结算规则缺失最大赔付、断线恢复、自动旋转停止等边界条件
- 共享问题重大改写示例：RESPIN公式在需求与数值文档中表述不一致；基础盘面与乘数轴权重未区分全局/条件概率，RTP无法核算
