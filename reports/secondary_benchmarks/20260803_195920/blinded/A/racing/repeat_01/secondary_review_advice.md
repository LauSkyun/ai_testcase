# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率公式冲突、T变量定义歧义、假数据隔离及真假赔率映射等致命阻塞项，问题定位精准。但在扣款/冻结时机、干预逻辑边界条件等经济安全与测试验收细节上存在遗漏，部分高阻塞问题的证据引用格式略显混乱，需进一步结构化整理。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选报告已修正主模型的证据格式问题，补充了扣款时机与干预边界等关键遗漏，结构完整、证据充分、追踪清晰，可直接作为评审终稿交付业务方进行需求修订。
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
- phase2 新增准入：声称 1，通过 0，拒绝 1
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:SECURITY_BET_DEDUCTION_TIMING
  - 拒绝《下注本金扣除/冻结时机缺失，存在经济漏洞风险》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确抓住了需求文档与数值文档在赔率计算模型上的根本性冲突（资金池模式 vs 权重膨胀模式）。
- 敏锐发现了T变量在时间公式与赔率公式中的物理意义矛盾，避免了开发阶段的严重逻辑错误。
- 对假数据参与真实计算、真假赔率展示与结算映射等经济安全边界问题识别到位。

## 问题
- T_VARIABLE_CONFLICT 问题的证据引用格式混乱，包含重复和嵌套数组，不利于业务方追踪。
- 遗漏了对赌游戏核心的‘下注本金扣除/冻结时机’规则，存在经济漏洞风险。
- 干预逻辑的触发边界（如选项下注人数不满足条件时的降级处理）未做深入挖掘，影响测试验收。
- MAX_PAYOUT_RISK 未结合‘单选项限注100万’的具体规则进行量化风险分析。

## 复核备注
- 主模型在 T_VARIABLE_CONFLICT 中的证据引用存在嵌套数组和重复字符串，已在候选稿中整理为清晰的字符串列表，提升可读性。
- 主模型未识别出对赌游戏核心的‘下注本金扣除/冻结时机’规则，已在候选稿中作为高信号安全问题补充（SECURITY_BET_DEDUCTION_TIMING）。
- 干预逻辑的触发边界（如选项下注人数不满足条件时的降级处理）在主模型中未做深入挖掘，已将其吸收至 INTERVENTION_MAPPING 的现状描述中，避免问题碎片化。
- MAX_PAYOUT_RISK 已结合‘单选项限注100万’的具体规则进行量化风险分析，使资损风险更具说服力。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：SECURITY_BET_DEDUCTION_TIMING

## 不支持的问题
- 暂无

## 合并建议
- 暂无
