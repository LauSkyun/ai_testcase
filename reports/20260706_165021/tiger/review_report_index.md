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
- 原因：候选报告已修正主模型报告的少量描述错误，并补充了4个关键遗漏项，整体结构完整、证据明确、建议可执行，可直接交给业务方。
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
- Candidate：C
- Selected：C
- Pipeline 问题数：11
- Candidate 问题数：11
- Selected 问题数：11

## Trace 摘要
- raw：kept=7, added=4, merged=0, dropped=0
- materialized：kept=7, added=4, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：7
- 共享问题重大改写示例：游戏术语、赔率展示及统计时间维度在正文与UI截图中严重冲突；亏损大R累计亏损金额正文与配置表冲突；档位配置数值在文档多处严重冲突；特殊人群判定次数重置规则存在矛盾；结算净赢金额定义不清，影响排行榜与展示；核心结算兜底逻辑中“实时总奖池”定义及计算口径缺失；特殊人群保护策略的判定边界条件（局数/时长不足）缺失
