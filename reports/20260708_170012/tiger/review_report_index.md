# Dual Pass 索引

## 运行结果
- 状态：primary_only
- 主模型：gpt-5.4
- 副模型：deepseek-v4-pro
- 默认最终报告来源：pipeline
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_pipeline.md

## 推荐门槛
- 推荐状态：candidate_unavailable
- 未通过原因：candidate_report_unavailable
- 阻断分类：protocol_blockers=candidate_report_unavailable
- Candidate 直出建议：否
- 可追踪性：unavailable
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- candidate 是否达到结构直出门槛：否
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
- Candidate：未生成
- Advice：未生成

## 评分与问题数
- Primary：C
- Pipeline：C
- Candidate：未提供
- Selected：C
- Pipeline 问题数：9
- Candidate 问题数：0
- Selected 问题数：9

## Trace 摘要
- raw：kept=0, added=0, merged=0, dropped=0
- materialized：kept=0, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- block reasons：candidate_report_unavailable

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：0

## Warning
- 副评审调用失败，本次仅保留 pipeline 版：Model API request timed out after 600s. Try increasing --timeout or lowering --max-context-chars.
