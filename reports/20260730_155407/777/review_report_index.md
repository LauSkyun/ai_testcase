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
- 原因：候选报告已修正主模型对赔付优先级的误判，澄清了RESPIN公式的术语歧义，并补充了交互状态冲突、扣款幂等及最大赔付上限等高信号遗漏项，结构完整、证据充分，可直接输出给业务方。
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
- Candidate 问题数：8
- Selected 问题数：8

## Trace 摘要
- raw：kept=5, added=3, merged=0, dropped=0
- materialized：kept=5, added=3, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：5
- 重大改写示例：RESPIN触发条件冲突、风控与表现不一致及术语歧义；空白符号赔付逻辑与基础奖金定义存在直接矛盾；“推展机制”触发条件与表演逻辑混淆；特殊倍率回推/下拉效果的触发概率缺失；金额缩位展示的“直接截断”精度歧义
