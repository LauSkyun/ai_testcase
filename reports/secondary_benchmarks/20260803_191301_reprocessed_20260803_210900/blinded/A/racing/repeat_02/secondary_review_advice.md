# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率公式冲突、T变量定义歧义、假数据隔离缺失、真假赔率映射缺失等高信号阻塞项，维度覆盖完整，严重度判定合理。主要问题是个别finding的证据引用存在重复拼接、T变量冲突的现状描述存在多段近义重复，影响可读性但不影响结论正确性。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选稿已修正证据重复与描述冗余问题，核心高信号阻塞项保留完整，lineage 可追踪，可直接交付业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=8, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=8, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 0，通过 0，拒绝 0
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别出需求文档与数值文档在赔率公式上的根本性冲突（资金池模型 vs 权重膨胀模型），并正确判定为高阻塞。
- 正确识别T变量在开奖时间公式与赔率公式中的物理意义冲突，且未轻率降级为表述歧义。
- 假数据隔离、真假赔率映射、奖池负数兜底等边界问题定位准确，证据可追溯。
- 对占位符缺失、新手引导隔离、音频混合等问题按规则合理降级，未泛化高危。

## 问题
- T_VARIABLE_CONFLICT 的 current_state 与 risk 字段存在多段近义重复（如两次描述T定义冲突、两次描述两套公式不同），需合并精简。
- 部分 finding 的 evidence 字段出现数组拼接重复（如 ['musee游戏Racing.docx / 3.3下注部分 段落28', 'Racing数值文档.docx / 图片1'] 重复出现），需去重。
- FAKE_ODDS_MAPPING 与 DATA_ISOLATION 在'假数据/假赔率'主题上存在一定关联，但根因不同（一个是数据源隔离，一个是展示与结算映射），主模型分列合理，无需合并。

## 复核备注
- T_VARIABLE_CONFLICT 的 current_state 原文存在多段近义重复（如两次描述T定义冲突、两次描述两套公式不同），候选稿已合并为3个分点：1.T物理意义冲突 2.赔率公式模型冲突 3.取整规则矛盾。
- 部分 finding 的 evidence 字段原文存在数组拼接重复，候选稿已去重并统一为字符串格式。
- DATA_ISOLATION 与 FAKE_ODDS_MAPPING 虽主题相关，但根因不同（前者是数据源隔离，后者是展示与结算映射），分列合理，无需合并。
- 主模型对高信号核心问题的严重度判定准确，未做乐观降级，候选稿全部保留。
- protocol_profile=phase2

## 不支持的问题
- 暂无

## 合并建议
- 暂无
