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
- 原因：主模型报告整体质量高，问题识别准确，结构完整。上述issues均为可修正的严重度/归属偏差，不影响报告核心价值。候选稿已修正这些偏差，可直接交付业务方。
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
- Pipeline 问题数：9
- Candidate 问题数：8
- Selected 问题数：8

## Trace 摘要
- raw：kept=7, added=1, merged=0, dropped=0
- materialized：kept=7, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：1
- Candidate 独有问题数：0
- 共享问题中的重大改写数：3
- Pipeline 独有示例：后台配置热更对历史统计窗口（奖池状态、人群判定）的生效规则缺失
- 共享问题重大改写示例：核心视觉术语、赔率与筹码档位在文档与UI图中严重冲突；开奖兜底逻辑的“实时奖池”计算口径与透支上限缺失；断线重连、弱网及重复点击等核心异常流程规则完全缺失
