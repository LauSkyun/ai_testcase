# Dual Pass 副评审建议

## 总体判断
主模型准确识别了RESPIN核心结算公式与触发条件的跨文档冲突，以及风控规则与特殊玩法的优先级缺失等高信号阻塞项。但主问题respin_formula_conflict将5个子症状揉成一段混写，导致阅读困难；同时遗漏了推展机制在需求文档中完全缺失的跨文档缺口；部分低信号问题（如缩位展示）严重度偏高。

- 建议等级：medium
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
- lineage 原始统计：kept=4, added=1, merged=0, dropped=0
- lineage 实际落盘统计：kept=4, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- candidate 存在较大结论漂移，当前改判依据不足。
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready, candidate_missing_issue_id, candidate_major_judgment_drift
- 阻断分类：protocol_blockers=candidate_missing_issue_id; quality_blockers=candidate_major_judgment_drift; readiness_blockers=normalized_candidate_not_ready

## 优点
- 准确定位RESPIN触发条件（需求要求中奖连线 vs 数值要求123列非空）的根本冲突
- 识别出100倍风控线与RESPIN累加期望值的数学矛盾
- 证据索引完整，每个子症状都能追溯到具体段落/表格
- top_blockers聚焦核心阻塞项，未泛化扩散

## 问题
- respin_formula_conflict将触发条件、公式、风控、自动旋转、数值验证5个子症状揉成一段，违反分点展开原则
- 遗漏推展机制（数值文档段落38-40、表5）在需求文档中完全缺失的跨文档缺口
- amount_truncation严重度标为中，但实际为低信号术语冗余问题
- respin_formula_conflict在findings中标为中，但在top_blockers中标为高，严重度不一致

## 复核备注
- 主模型respin_formula_conflict将5个子症状揉成一段混写，候选稿已按分点原则重构为current_state/risk/suggestion各5点，提升可读性。
- 主模型遗漏推展机制在需求文档中完全缺失的跨文档缺口，候选稿已补充为push_mechanism_missing finding。
- 主模型amount_truncation严重度标为中，但实际为低信号术语冗余问题，候选稿已下调为低。
- 主模型respin_formula_conflict在findings中标为中但在top_blockers中标为高，严重度不一致，候选稿已统一为高。
- 建议后续进一步拆分respin_formula_conflict为5个独立finding（触发条件、结算公式、风控优先级、自动旋转、数值验证），但本轮为保持与primary骨架一致，仍保留为单一finding内分点展开。
- dual_pass candidate 含空 issue_id 问题项，当前仅作为对比稿，不建议默认直出。
- dual_pass 一致性提示：candidate 与 primary 存在较大结论漂移，但副评审未给出足够改判依据。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
