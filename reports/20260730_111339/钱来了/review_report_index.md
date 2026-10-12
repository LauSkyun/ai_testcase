# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：deepseek-v4-pro
- 副模型：deepseek-v4-pro
- 默认最终报告来源：pipeline
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_pipeline.md

## 推荐门槛
- 推荐状态：fallback_pipeline
- 未通过原因：normalized_candidate_not_ready, advice_candidate_structure_mismatch, candidate_absorbed_missed_materialized_separately
- 阻断分类：protocol_blockers=advice_candidate_structure_mismatch,candidate_absorbed_missed_materialized_separately; readiness_blockers=normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：candidate_lineage 对 candidate 结构的说明与最终落盘结果不一致，当前候选稿不可作为默认最终输出。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- candidate 是否达到结构直出门槛：否
- primary issue_id 修复数：4
- candidate issue_id 修复数：4
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- 当前是否仅被编辑性判断阻断：否
- advice 与 candidate 落盘是否一致：否
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
- Selected：C
- Pipeline 问题数：10
- Candidate 问题数：10
- Selected 问题数：10

## Trace 摘要
- raw：kept=8, added=2, merged=0, dropped=0
- materialized：kept=8, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- block reasons：normalized_candidate_not_ready, advice_candidate_structure_mismatch, candidate_absorbed_missed_materialized_separately

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：8
- 重大改写示例：RESPIN触发条件与风控倍数规则冲突；免费旋转符号触发时的基础奖金计算公式未明确；免费旋转续杯规则中出现“夺宝符号”与“免费旋转符号”不一致；大奖档位、重进恢复及记录规则缺失；银行符号与乘数1的对应关系不明确；购买免费游戏的价格系数与配置表序号未定义；抽奖按钮重复点击防重与幂等性未说明；普通游戏旋转过程中退出重进的处理方式未定义
