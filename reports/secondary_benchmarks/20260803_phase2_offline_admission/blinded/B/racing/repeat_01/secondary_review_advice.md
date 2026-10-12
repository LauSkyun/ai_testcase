# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心结算链路中的公式冲突、变量定义歧义以及数据源隔离缺失等高信号阻塞问题，整体方向正确。但部分finding的current_state和risk存在明显的文本重复拼接，且将‘假数据隔离’与‘真假赔率映射’拆分为两个独立问题，未遵循相同根因合并原则。候选稿已修复文本冗余，合并了数据源隔离相关问题，并规范了证据引用与严重度定级。

- 建议等级：low
- 是否建议候选稿直出：否
- 原因：candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。
- 可追踪性：partial
- readiness 是否冲突：否
- candidate 是否有结构漂移：是
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=6, added=0, merged=1, dropped=0
- lineage 实际落盘统计：kept=6, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：missing
- 未落盘的 merged issue_id：DATA_SOURCE_ISOLATION
- phase2 新增准入：声称 0，通过 0，拒绝 0
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, candidate_unmapped_candidate_findings, candidate_merged_not_materialized, candidate_traceability_partial
- 阻断分类：protocol_blockers=candidate_merged_not_materialized; traceability_blockers=candidate_lineage_coverage_incomplete,candidate_unmapped_candidate_findings,candidate_traceability_partial; readiness_blockers=normalized_candidate_not_ready

## 优点
- 准确抓住了赔率公式跨文档冲突和T变量定义矛盾这一致命阻塞项。
- 识别出干预逻辑缺乏到速度公式的具体映射，切中控盘玩法的实现痛点。
- 对占位符、新手引导、音频混合等问题进行了合理的风险降级，符合评审原则。

## 问题
- T_VARIABLE_CONFLICT的current_state和risk存在大量重复拼接的模板化文本，阅读体验差。
- 将‘假人数/金额参与计算’与‘真假赔率展示结算映射’拆分为两个高优问题，本质上同属‘展示数据与结算数据的数据源隔离规则缺失’，应合并。
- top_blockers中的why_now字段同样存在重复拼接问题，未提炼核心结论。

## 复核备注
- 主模型首版报告中 T_VARIABLE_CONFLICT 的 current_state 和 risk 存在大量重复拼接的模板化文本，候选稿已将其重构为分点描述，提升可读性。
- 主模型将 DATA_ISOLATION 和 FAKE_ODDS_MAPPING 拆分为两个高优问题，候选稿已根据‘相同根因合并’原则将其合并为 DATA_SOURCE_ISOLATION，并在 lineage 中记录了 merged 和 dropped 关系。
- 主模型 top_blockers 中的 why_now 字段同样存在重复拼接，候选稿已精简为核心结论。
- 建议后续进一步补充 gamma 公式中 α、β 参数的配置范围，以完善极端资金比例下的膨胀效果验证。
- dual_pass trace 提示：candidate_lineage 不为空，但未完整覆盖 primary/candidate 的问题血缘；当前候选稿暂不建议默认直出。
- dual_pass trace 提示：candidate 存在未被 lineage 覆盖的问题映射，需补齐 kept/added/merged/dropped 后再考虑默认直出。
- dual_pass 合并落盘提示：candidate_lineage.merged 中声明的合并问题未完整落入最终 candidate。

## 不支持的问题
- 暂无

## 合并建议
- ：两者本质上均指向‘客户端展示/氛围数据’与‘服务端真实结算数据’的边界不清。假人数/假金额参与计算会导致赔率失真，假赔率展示与实际结算不符会导致客诉，统一合并为‘展示数据与结算数据的数据源隔离规则缺失’更符合根因归并原则。
