# Dual Pass 副评审建议

## 总体判断
主模型报告整体抓住了UI赔率表脱节、推展风控顺序等关键问题，但错误地将RESPIN结算公式判定为高阻塞歧义（实际公式一致），并遗漏了风控与RESPIN累加交互的重要边界，导致部分风险等级失准。

- 建议等级：medium
- 是否建议候选稿直出：否
- 原因：副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。
- 可追踪性：complete
- readiness 是否冲突：是
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=5, added=1, merged=0, dropped=0
- lineage 实际落盘统计：kept=5, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready
- 阻断分类：readiness_blockers=normalized_candidate_not_ready

## 优点
- 准确识别UI赔率表与后端配置的严重脱节，并给出高阻塞评级
- 指出推展机制与风控的执行顺序缺失
- 金额缩位展示的一致性问题定位清晰

## 问题
- 将RESPIN公式示例误判为根本歧义，实际基础投注×赔率×累加乘数值的计算逻辑在需求与数值文档中可一致实现
- 遗漏风控强制0倍与RESPIN累加过程的交互时序，该问题直接影响玩家体验和数值平衡
- RESPIN相关边界条件（如第4列出respin但123列空、快捷旋转验收）被合并到同一个高阻塞问题中，但部分子项严重性实际较低

## 复核备注
- 主模型报告将RESPIN结算公式判定为高阻塞歧义，但经复核，需求文档举例与数值文档公式在基础投注×赔率×累加乘数值的逻辑上可一致实现，已降级并修正为边界条件问题。
- 新增RESPIN_RISK_CONTROL_INTERACTION问题，捕捉风控与RESPIN累加交互的缺口，建议作为中阻塞项处理。
- 建议后续版本在数值文档中补充RTP、MAX_MUL等指标，以完善数值验收。
- 部分权重表格全为100，提醒策划在真实配置时替换为有效数值，避免误用占位符。
- dual_pass 协议提示：quality_assessment.ready_for_direct_output 与 candidate_readiness.ready_for_direct_output 不一致，已统一降为 false。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
