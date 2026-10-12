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
- 原因：候选报告已补充Respin结束条件冲突、推展机制需求缺失等关键遗漏，并修正了主模型的问题描述，现在证据充分、结构完整，可直接交付业务方阅读。
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
- Pipeline 问题数：7
- Candidate 问题数：6
- Selected 问题数：6

## Trace 摘要
- raw：kept=5, added=1, merged=0, dropped=0
- materialized：kept=5, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：1
- Candidate 独有问题数：0
- 共享问题中的重大改写数：4
- Pipeline 独有示例：Respin结束条件：需求要求“直到空”与数值文档“次数达标后强制空”不一致
- 重大改写示例：Respin触发条件跨文档表述冲突；需求文档未定义推展机制的触发条件、概率及服务端流程，仅描述动效；第4列“出现权重”与“表演权重”的作用域与切换条件模糊；基础符号权重导致的中奖率异常及RTP/MAX_MUL缺失
