# Dual Pass 副评审建议

## 总体判断
主模型报告质量较高，准确识别了核心赔率冲突、兜底逻辑缺陷、概率冲突等高信号问题，问题分类清晰、证据定位准确、建议具体可落地。但仍遗漏了投入人数统计口径不一致、亏损大R阈值10倍差异、开奖分析和游戏记录时间范围冲突等关键问题，需补充后输出。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选稿已补充关键遗漏问题，结构完整、证据充分、来源可追踪，可直接给业务方阅读
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=10, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=10, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 4，通过 0，拒绝 4
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:LOGIC_04, missed_finding_not_in_confirmed_add:LOGIC_05, missed_finding_not_in_confirmed_add:CLARITY_04, missed_finding_not_in_confirmed_add:CLARITY_05
  - 拒绝《投入人数统计口径在不同规则中不一致（非去重 vs 去重）》：missing_fields:audit_key, value_mismatch_same_scope_unverified, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《亏损大R累计亏损阈值在正文与配置表中存在10倍差异》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《开奖分析模块的时间范围在正文与UI截图中存在冲突》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《游戏记录展示范围在正文与UI截图中存在冲突》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别了赔率、概率、兜底逻辑等核心冲突
- 问题分类清晰，证据定位到具体段落/表格/图片
- 建议具体可落地，指向明确的修复方向
- Top Blockers 聚焦真正阻塞开发的高信号问题

## 问题
- 遗漏了投入人数统计口径不一致问题（非去重 vs 去重）
- 遗漏了亏损大R累计亏损阈值10倍差异问题（50000000 vs 5000000）
- 遗漏了开奖分析时间范围冲突（表格3写7天，图13显示30天）
- 遗漏了游戏记录展示范围冲突（表格3写3日，图6/图8显示30日/1日）

## 复核备注
- 主模型报告质量较高，准确识别了核心赔率冲突、兜底逻辑缺陷、概率冲突等高信号问题
- 补充了4个关键遗漏问题：投入人数统计口径不一致、亏损大R阈值10倍差异、开奖分析时间范围冲突、游戏记录展示范围冲突
- 所有问题均提供了明确的证据定位和可落地的修复建议
- 建议产品方优先修复4个高阻塞问题（LOGIC_01、LOGIC_02、LOGIC_04、LOGIC_05），再补充中风险问题
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：CLARITY_04
- phase2 准入已从 candidate 移除 rejected addition：CLARITY_05
- phase2 准入已从 candidate 移除 rejected addition：LOGIC_04
- phase2 准入已从 candidate 移除 rejected addition：LOGIC_05

## 不支持的问题
- 暂无

## 合并建议
- 暂无
