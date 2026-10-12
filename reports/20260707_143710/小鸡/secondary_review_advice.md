# Dual Pass 副评审建议

## 总体判断
主模型报告结构清晰，识别了跨文档映射断裂、胜负判定边界、UI概率展示、异常恢复等关键问题，但遗漏了核心结算公式歧义，且对胜负判定冲突的严重度标注在维度中与top_blockers矛盾，需修正补充。

- 建议等级：high
- 是否建议候选稿直出：否
- 原因：candidate 与 primary 存在较大结论漂移，但副评审未给出足够改判依据，当前不建议默认直出。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=7, added=1, merged=0, dropped=0
- lineage 实际落盘统计：kept=7, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- candidate 存在较大结论漂移，当前改判依据不足。
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready, suggestion_level_high, candidate_major_judgment_drift
- 阻断分类：quality_blockers=suggestion_level_high,candidate_major_judgment_drift; readiness_blockers=normalized_candidate_not_ready

## 优点
- 覆盖了结算、异常恢复、UI展示、安全性等多个维度，问题定位较全面
- 提供了可测试的验收点和缺失信息清单，有助于后续测试设计
- 指出了需求文档与数值文档在难度、倍率、概率上的不一致，并给出了统一建议

## 问题
- 遗漏了总奖金计算公式中倍率定义（单格倍率连乘 vs 累积倍率）的歧义，将直接阻塞结算实现
- 安全性与反作弊维度中胜负判定边界冲突的严重度标注为“低”，与top_blockers中的“高”矛盾，且实际应属高阻塞
- 未深入分析数值文档中倍率表（表格2）的数学性质与需求文档公式的兼容性

## 复核备注
- 新增finding 'formula_ambiguity' 解决总奖金公式歧义，该问题为高阻塞，主模型遗漏。
- 将 'client_server_boundary' 的严重度从低提升为高，并统一top_blockers，修正了主模型报告中的矛盾。
- 在 'cross_doc_mapping' 中明确指出了超级大奖缺失，并强化了建议。
- 所有kept finding均沿用主模型issue_id，未做拆分或合并。
- candidate_report 整体结构保持与主模型一致，仅在必要处补充和修正。
- dual_pass 一致性提示：candidate 与 primary 存在较大结论漂移，但副评审未给出足够改判依据。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
