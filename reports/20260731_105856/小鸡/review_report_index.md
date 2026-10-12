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
- 原因：候选稿已修正主模型的描述混乱问题，分点澄清了核心冲突，并补全了开局扣款时机这一高信号安全边界，结构完整、证据充分，可直接交付业务方阅读与推进修正。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- candidate 是否达到结构直出门槛：是
- primary issue_id 修复数：3
- candidate issue_id 修复数：3
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
- Pipeline 问题数：6
- Candidate 问题数：6
- Selected 问题数：6

## Trace 摘要
- raw：kept=5, added=1, merged=0, dropped=0
- materialized：kept=5, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：4
- 重大改写示例：难度系统概率计算逻辑与角色包装冲突；下注筹码数值配置冲突；倍率计算公式与数值表口径严重冲突；通关‘超级大奖’与第30格结算的边界歧义
