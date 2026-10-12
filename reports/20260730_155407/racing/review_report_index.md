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
- 原因：候选报告已修正主模型中子症状揉捏的问题，补充了奖池状态闭环与赔率精度等关键漏项，结构完整、证据充分，可直接输出给业务方进行需求对齐。
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
- Primary：D
- Pipeline：D
- Candidate：D
- Selected：D
- Pipeline 问题数：8
- Candidate 问题数：8
- Selected 问题数：8

## Trace 摘要
- raw：kept=6, added=2, merged=0, dropped=0
- materialized：kept=6, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：8
- 重大改写示例：单局地形段数与车型数量规则存在严重矛盾；核心赔率公式在需求与数值文档中存在根本性冲突；货币术语混用与半屏/赔率更新边界缺失；实时赔率公式中的精度处理与占位符歧义；奖池抽水机制与单局最大赔付上限（MAX_MUL）缺失；干预逻辑中的“干扰指数”与公式中的“Luck”未建立映射；奖池状态计算的滚动窗口与干预概率闭环缺失；假数据隔离、引导局结算与异常流程规则缺失
