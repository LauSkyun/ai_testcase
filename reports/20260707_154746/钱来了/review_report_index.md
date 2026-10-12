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
- 原因：候选报告已修正主模型误判的定性，保留核心阻塞项，补全遗漏的推展触发条件问题，证据充分、来源可追踪，可直接交付业务方。建议值medium仅因仍有待产品拍板的阈值、口径澄清，但不影响报告本身作为工作文档的交付质量。
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
- raw：kept=8, added=2, merged=0, dropped=0
- materialized：kept=8, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：6
- 重大改写示例：购买免费游戏（Feature Buy）的核心规则与公式缺失；“银行符号”在数值配置表中的映射缺失；RESPIN机制的盘面生成逻辑与触发条件存在根本矛盾；免费旋转符号的基础赔付乘数缺失导致结算公式断裂；风控强制0倍规则与免费游戏2000倍封顶规则存在数值冲突；异常流程在特色机制动画中的恢复口径缺失
