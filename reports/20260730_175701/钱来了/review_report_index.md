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
- 原因：候选报告已修正主模型遗漏的规则错误，增强了核心finding的分点描述，证据充分且可追踪，结构完整，可直接输出给业务方阅读。
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
- raw：kept=7, added=1, merged=0, dropped=0
- materialized：kept=7, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：5
- 重大改写示例：购买免费游戏的价格系数与指定金额缺失具体数值；2000倍赢奖上限与100倍风控截断的致命冲突；RESPIN触发概率'必定'与'0.1/0.05'的矛盾及多表冲突；免费符号触发时的基础奖金结算公式缺失；免费续杯规则中'4个及以上符号'与3轴盘面结构矛盾
