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
- 原因：候选报告已修正主模型对公式冲突的误判，并补充了关键缺失项，可直接交付。
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
- Candidate：D
- Selected：D
- Pipeline 问题数：7
- Candidate 问题数：7
- Selected 问题数：7

## Trace 摘要
- raw：kept=5, added=2, merged=0, dropped=0
- materialized：kept=5, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：4
- 共享问题重大改写示例：购买免费游戏（Feature Buy）核心规则与结算链路缺失；Respin（重转）触发条件、概率配置与表现逻辑在两份文档中互相矛盾；中奖金额计算公式表述歧义，符号值与投注额的乘数关系不明确；风控阈值（100倍）与游戏上限（2000倍/x100倍率）存在直接冲突，导致核心高爆玩法失效
