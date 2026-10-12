# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了开奖兜底0赔付缺陷、机器人机制缺失、奖池正常状态概率冲突三大核心阻塞项，证据定位清晰、严重度判定合理。但遗漏了两处UI截图与正文在时间范围上的直接矛盾（游戏记录3日vs30日、开奖分析7天vs30天），且LOGIC_02将概率冲突与断线重连规则混写于同一finding，建议拆分关注点。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选报告已补充两处UI-正文时间范围矛盾的高信号遗漏项，并保留主模型全部核心阻塞项，证据充分、结构完整、lineage可追踪，可直接交付业务方阅读。
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
- phase2 新增准入：声称 2，通过 0，拒绝 2
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:CLARITY_04, missed_finding_not_in_confirmed_add:CLARITY_05
  - 拒绝《游戏记录展示范围在正文与UI截图中存在直接矛盾（3日 vs 30日）》：missing_fields:audit_key,root_causes,fact_check, multiroot_or_root_count_invalid, fact_check_invalid, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《开奖分析时间范围在正文与UI截图中存在直接矛盾（7天 vs 30天）》：missing_fields:audit_key,root_causes,fact_check, multiroot_or_root_count_invalid, fact_check_invalid, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别开奖兜底逻辑会开出0赔付选项的机制缺陷，证据链完整（段落57/68/108 + 段落73）
- 正确发现图22机器人流程图与正文需求脱节，指出阈值依赖人数但缺乏机器人机制支撑
- 精准定位奖池正常状态偏移概率在正文(60%)与配置表(20%)的数值冲突
- 证据引用规范，均定位到具体段落、表格或图片编号

## 问题
- 遗漏游戏记录展示范围矛盾：正文表格3写'近3日'，但图6/图8 UI截图写'last 30 days'
- 遗漏开奖分析时间范围矛盾：正文表格3写'最近7天'，但图13 UI截图写'Last 30 day'
- LOGIC_02将概率冲突与断线重连规则混写于同一finding的current_state/risk/suggestion，建议拆分关注点或在描述中分点说明

## 复核备注
- 主模型LOGIC_02将'奖池正常状态概率冲突'与'断线重连规则缺失'混写于同一finding的current_state/risk/suggestion，建议后续拆分为两个独立finding：一个聚焦数值冲突（已保留为LOGIC_02），另一个聚焦断线重连专属规则（建议作为新增finding后续补充）。
- 候选稿新增CLARITY_04和CLARITY_05两个finding，均基于正文与UI截图的直接数值矛盾，证据充分、根因独立，符合高信号补漏标准。
- 建议后续补充断线重连与局内状态恢复的专属规则作为独立finding，当前仅保留在missing_information中。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：CLARITY_04
- phase2 准入已从 candidate 移除 rejected addition：CLARITY_05
- dual_pass 结构提示：candidate 仍保留多根因混合问题，建议继续拆清根因或改为分点展示。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
