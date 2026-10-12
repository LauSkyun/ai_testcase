# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.4
- 副模型：deepseek-v4-pro
- 默认最终报告来源：pipeline
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_pipeline.md

## 推荐门槛
- 推荐状态：fallback_pipeline
- 未通过原因：warning_present, quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_traceability_partial
- 阻断分类：traceability_blockers=candidate_lineage_coverage_incomplete,candidate_traceability_partial; quality_blockers=warning_present,quality_assessment_not_ready; readiness_blockers=candidate_readiness_not_ready,normalized_candidate_not_ready
- Candidate 直出建议：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 血缘追踪状态：partial
- readiness 是否冲突：否
- candidate 是否存在结构漂移：是
- candidate 是否达到结构直出门槛：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突执行 override：否
- 当前是否仅被编辑判断阻断：否
- advice 与 candidate 落盘是否不一致：否
- candidate 是否发生过结构变化：是
- 结构变化是否已被 lineage 解释：否

## 产物路径
- Pipeline：review_report_pipeline.md
- Candidate：review_report_candidate.md
- Advice：secondary_review_advice.md

## 评分与问题数
- Primary：未评定
- Pipeline：B
- Candidate：D
- Selected：B
- Pipeline 问题数：2
- Candidate 问题数：9
- Selected 问题数：2

## Trace 摘要
- raw：kept=8, added=1, merged=0, dropped=1
- materialized：kept=8, added=1, merged=0, dropped=1
- added 落盘状态：complete
- merged 落盘状态：none
- trace warning：candidate_lineage present but does not fully cover primary/candidate findings
- block reasons：warning_present, quality_assessment_not_ready, candidate_readiness_not_ready, normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_traceability_partial

## 差异摘要
- Pipeline 独有问题数：1
- Candidate 独有问题数：8
- 共享问题中的重大改写数：1
- Pipeline 独有示例：引导局是否使用真实资金未明确，存在误扣真实资产风险
- Candidate 独有示例：核心数值公式变量定义缺失及“干扰指数”映射不明；赔率计算双轨制冲突及“假赔率”展示结算口径风险；多重开奖干预逻辑优先级未定义及“待补充”状态逻辑矛盾；奖池状态计算公式存在分母为零的异常风险；新手引导强制交互缺乏跳过机制，且资金属性未明确，存在误扣款风险；半屏模式下开奖动画与结果弹窗的UI适配规则缺失；单局最大赔付上限与奖池负数兜底机制缺失；统计板块无数据时的默认展示值与实际概率模型脱节
- 共享问题重大改写示例：假数据（人数/金额）与真实赔率计算的数据源隔离未明确

## Warning
- 主评审模型返回 JSON 解析失败，已保留原始响应：Expecting ',' delimiter: line 242 column 2 (char 8881)；副评审调用失败，本次仅保留 pipeline 版：Object of type set is not JSON serializable
