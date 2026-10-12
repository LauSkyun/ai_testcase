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
- 原因：候选报告已补充中等风险遗漏，结构完整，证据充分，可直接交付业务方
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
- Pipeline 问题数：12
- Candidate 问题数：12
- Selected 问题数：12

## Trace 摘要
- raw：kept=7, added=5, merged=0, dropped=0
- materialized：kept=7, added=5, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：6
- 共享问题重大改写示例：推展机制（Push）仅在数值文档定义，需求文档缺失UI与动效说明；需求文档缺失Respin次数上限与强制结束逻辑；Respin累加公式与举例表述歧义（相加 vs 相乘，初始值处理）；风控“强制0倍”机制的客户端表现与扣款逻辑缺失；UI赔率表展示数值与数值文档配置严重冲突；未中奖时第4列高倍/Respin的视觉反馈易误导
