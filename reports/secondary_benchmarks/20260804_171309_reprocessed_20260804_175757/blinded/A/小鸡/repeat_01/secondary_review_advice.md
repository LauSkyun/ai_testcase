# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心数值模型、结算公式与配置表之间的严重冲突，问题定位精准，证据充分。但在扣款/派奖时机、单局封顶等经济边界方面存在少量补充空间，且部分 finding 混合了多个子症状未分点展开。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选稿已修正主模型问题结构，补充了经济边界控制面核对，可直接输出给业务方阅读
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：3
- candidate issue_id 修复数：3
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=5, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=5, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 0，通过 0，拒绝 0
- coverage ledger：未通过，完整率 100%
- coverage ledger 错误：coverage_control_invalid:trigger_state_termination:termination_priority:primary_control_mismatch:LOGIC_03
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别倍率公式与数值表口径冲突（LOGIC_PAYOUT_FORMULA_CONFLICT）
- 准确识别下注筹码三端配置不一致（CORE_BET_CONFIG_MISMATCH）
- 准确识别难度概率计算逻辑冲突（CORE_DIFFICULTY_CONFIG_MISMATCH）
- 准确识别第30格超级大奖边界歧义（LOGIC_03）
- 问题证据定位清晰，引用了具体段落、表格和图片

## 问题
- CORE_DIFFICULTY_CONFIG_MISMATCH 混合了多个子症状（概率冲突、角色命名、UI展示、风险感知），未分点展开
- 未覆盖扣款时机、派奖时机、单局绝对封顶等经济边界控制面
- 部分 finding 的 finding_source、source_model 字段为空

## 复核备注
- 建议补充扣款时机说明：明确是在'点击开始'时扣款还是'选择筹码'时预扣
- 建议补充派奖时机说明：明确真实支付场景下的到账时机与失败回滚机制
- 建议补充单局绝对金额封顶：MAX_MUL提供相对上限，但需定义单局最大赔付金额
- CORE_DIFFICULTY_CONFIG_MISMATCH 已分点展开多个子症状，建议后续可考虑拆分为独立问题
- protocol_profile=phase2
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
