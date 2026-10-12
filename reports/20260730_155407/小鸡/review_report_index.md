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
- 原因：候选稿已修正主模型的严重度误判，补充了最大赔付、扣款时机等高危经济安全缺口，并将混合症状分点展开，结构完整、证据充分，可直接输出给业务方。
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
- Selected：B
- Pipeline 问题数：7
- Candidate 问题数：4
- Selected 问题数：4

## Trace 摘要
- raw：kept=4, added=0, merged=0, dropped=0
- materialized：kept=4, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：3
- Candidate 独有问题数：0
- 共享问题中的重大改写数：3
- Pipeline 独有示例：扣款时机与本金口径缺失；最大赔付（MAX_WIN）/ 封顶规则缺失；展示倍率与结算倍率的映射口径缺失
- 重大改写示例：马路封锁与车辆刷新的作用域及配置规则缺失；赔率表格数值定义缺失导致奖金公式无法实现；题材包装与主角形象跨文档/图文存在歧义
