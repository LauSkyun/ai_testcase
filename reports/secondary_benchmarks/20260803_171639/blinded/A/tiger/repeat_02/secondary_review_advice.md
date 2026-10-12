# Dual Pass 副评审建议

## 总体判断
主模型报告总体结构完整，抓住了赔率冲突、兜底逻辑缺陷、机器人机制缺失等核心问题，方向正确。但报告在问题归并、证据引用、严重度判定上存在若干可优化项：部分问题可合并为同一根因，部分风险描述与证据链不完全匹配，且遗漏了少量关键边界问题。

- 建议等级：medium
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
- advice 与 candidate 落盘是否一致：否
- lineage 原始统计：kept=10, added=4, merged=0, dropped=0
- lineage 实际落盘统计：kept=10, added=3, merged=0, dropped=0
- added 落盘状态：partial
- merged 落盘状态：none
- 未落盘的 added issue_id：CLARITY_04
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready, candidate_lineage_coverage_incomplete, advice_candidate_structure_mismatch, candidate_added_not_materialized, candidate_traceability_partial
- 阻断分类：protocol_blockers=advice_candidate_structure_mismatch,candidate_added_not_materialized; traceability_blockers=candidate_lineage_coverage_incomplete,candidate_traceability_partial; readiness_blockers=normalized_candidate_not_ready

## 优点
- 准确识别了赔率/倍数在正文、配置表、UI截图中的多处矛盾
- 发现了开奖兜底逻辑中「开出0赔付选项」的机制缺陷
- 指出了开奖阈值强依赖投入人数但缺失机器人机制的架构风险
- 报告结构清晰，维度覆盖全面，测试要点具备可执行性

## 问题
- 将 '奖池正常状态偏移概率冲突' 与 '断线重连缺失' 揉在同一个finding中，混淆了根因
- 将 '赔率展示冲突' 与 '规则说明冲突' 作为两个独立问题处理，实际可合并为同一赔率口径问题
- 遗漏了 '不抽水触发条件' 中的公式与判定顺序冲突
- 遗漏了 '结算弹窗重复拉起' 的幂等风险
- 部分证据引用未精确到段落编号或表格编号
- 对 '假人数/假金额' 展示与真实结算的数据源隔离问题未做专项检查
- top_blockers 中包含了非阻塞性问题（如断线重连），应聚焦真正阻塞开发的核心项

## 复核备注
- 主模型将LOGIC_02与断线重连缺失混写在同一finding中，已拆分为独立的LOGIC_02（数值冲突）与TEST_01（断线重连缺失）
- 主模型将CLARITY_01（赔率冲突）与断线重连缺失混写在同一finding中，已拆分为独立的CLARITY_04（赔率冲突）与TEST_01（断线重连缺失）
- 补充了MISS_01「不抽水触发条件逻辑冲突」为新增LOGIC_04，属高信号遗漏
- 补充了MISS_02「结算弹窗幂等风险」为新增TEST_03
- 补充了MISS_03「假金额展示与真实结算数据源隔离」为新增UX_02
- top_blockers已更新为CLARITY_04、LOGIC_01、LOGIC_04、CLARITY_02，移除原CLARITY_01和LOGIC_02
- 表格5中亏损大R累计亏损初始值5000000与正文段落85的50000000存在数量级差异，已在quality_notes中标注
- 建议后续评审中关注：奖池透支上限、最大赔付封顶、新手引导局是否污染真实统计数据等边界
- dual_pass trace 提示：candidate_lineage 不为空，但未完整覆盖 primary/candidate 的问题血缘；当前候选稿暂不建议默认直出。
- dual_pass 补漏落盘提示：candidate_lineage.added 中声明的新增问题未完整落入最终 candidate。
- dual_pass 协议提示：部分 lineage.added 声称的新问题未实际落盘到最终 candidate。

## 不支持的问题
- 暂无

## 合并建议
- ：根因不同，应保持独立
