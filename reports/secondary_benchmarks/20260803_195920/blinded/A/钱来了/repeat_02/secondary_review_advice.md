# Dual Pass 副评审建议

## 总体判断
主模型报告整体质量较好，准确识别了核心机制（RESPIN、推展）的底层逻辑矛盾、风控口径冲突、以及数值配置重复等关键问题。但在结算公式冲突的严重度判断上偏保守（实际为术语歧义而非根本冲突），且遗漏了需求文档中明显的复制粘贴错误（1x3盘面不可能出现4个及以上符号）。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选报告已修正主模型的严重度判断偏差，补充了遗漏的高信号核心问题，结构完整、证据充分、来源可追踪，可直接给业务方阅读
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=6, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=6, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 1，通过 0，拒绝 1
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:LOGIC_04
  - 拒绝《免费续杯触发条件与盘面结构冲突》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别了RESPIN底层数据生成规则与触发条件的矛盾
- 发现了乘数符号ID=0表演权重替换逻辑的表述不清问题
- 识别了风控基数与封顶规则的口径冲突
- 发现了免费续杯概率配置缺失的问题

## 问题
- CROSS_01（结算公式口径分裂）严重度判断偏高，实际为术语歧义而非根本冲突
- 遗漏了需求文档3.5.1中'4个及以上夺宝符号'与1x3盘面结构的直接冲突
- 部分finding的证据引用可以更精确到具体段落/表格

## 复核备注
- CROSS_01 从高风险调整为中风险，因为公式在正确解释下是一致的（中奖金额 = 乘数符号 × (基础投注 × 符号赔率) = 100 × (投注 × 10) = 1000 × 投注），主要问题是术语和符号定义不够清晰，可能导致实现错误，但并非根本性冲突。
- 新增 LOGIC_04，因为需求文档 3.5.1 中存在从其他游戏复制粘贴的错误描述（'4个及以上夺宝符号'），与 1x3 盘面结构直接冲突，primary 未覆盖此独立根因。
- top_blockers 更新为当前三个高严重度问题，移除已降级的 CROSS_01，新增 LOGIC_04。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：LOGIC_04

## 不支持的问题
- 暂无

## 合并建议
- 暂无
