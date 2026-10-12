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
- 原因：候选报告已修正误判、补充关键细节，结构完整、证据充分，可直接作为业务方评审的交付件。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- candidate 是否达到结构直出门槛：是
- primary issue_id 修复数：2
- candidate issue_id 修复数：2
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
- Selected：D
- Pipeline 问题数：8
- Candidate 问题数：8
- Selected 问题数：8

## Trace 摘要
- raw：kept=8, added=0, merged=0, dropped=0
- materialized：kept=8, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：8
- 重大改写示例：核心物理公式变量定义混乱（T是输入还是输出）；车型与地形的联合概率分布规则模糊；新手引导局的经济流转与数值来源未定义；取整规则歧义导致赔付精度与RTP风险；赔率计算、展示（假赔率）与真实结算的映射冲突；奖池状态公式的除零风险与干预边界盲区；开奖判定机制与干预逻辑的因果断裂导致无法设计验收用例；下注并发控制与上限校验的服务端权威边界未说明
