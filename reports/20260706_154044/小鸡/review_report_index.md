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
- 原因：候选报告已修正主模型报告的不足，证据充分，结构清晰，可直接供业务方阅读。
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
- raw：kept=7, added=0, merged=0, dropped=0
- materialized：kept=7, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：5
- 共享问题重大改写示例：下注筹码预设档位与数值示例存在直接冲突；难度档位定义、格子数与核心算法在两份文档中完全割裂；UI“被击中概率”展示与Crash底层算法的条件概率映射缺失；局内“抉择阶段”与“前进动画阶段”的防抖与超时规则缺失；提现与继续的服务端权威结算边界及幂等性模糊
