# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了跨文档在概率模型、筹码配置、倍率公式上的核心冲突，但在根因归并上存在瑕疵（将美术包装冲突混入概率问题），且遗漏了开局扣款时机这一高信号经济边界问题。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选报告已修正主模型的根因归并错误，补充了扣款时机等关键经济边界，结构完整、证据充分，可直接输出给业务方阅读。
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
- phase2 新增准入：声称 2，通过 0，拒绝 2
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:CLARITY_ART_CONFLICT, missed_finding_not_in_confirmed_add:ECONOMY_DEDUCT_TIMING
  - 拒绝《核心角色与题材包装冲突（小鸡 vs 骆驼）》：missing_fields:audit_key, primary_duplicate_declared_nearest, coverage_ledger_invalid, coverage_confirmed_add_link_missing
  - 拒绝《开局扣款与本金结算口径未明确》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确抓住了需求与数值文档在Crash算法、筹码配置、倍率连乘/累计上的直接冲突。
- 对数值表难度3、4的最终值与“倍盘”命名数量级差异的识别非常敏锐，直接指出了数值推导错误。

## 问题
- 将“小鸡/骆驼”的美术包装冲突错误归并到概率计算问题中，导致根因不纯，影响问题定位。
- 遗漏了开局扣款时机与本金结算口径的明确说明，这是博弈游戏的核心经济边界。
- 部分finding的current_state揉合了多个子症状，未按规范分点展开。

## 复核备注
- 主模型将“小鸡/骆驼”的美术包装冲突混入“难度系统概率计算逻辑冲突”，已在候选稿中剥离为独立的 CLARITY_ART_CONFLICT 问题。
- 主模型遗漏了开局扣款时机与本金结算口径的明确说明，已在候选稿中补充为 ECONOMY_DEDUCT_TIMING 问题。
- 建议数值策划重新校验难度3和难度4的赔率推导公式，确保第30关的最终累计倍率与“103倍盘”、“176倍盘”的命名定义严格对齐。
- 建议明确UI上“被击中概率”的计算公式，并补充测试验收用例，确保UI展示值与服务端底层概率严格一致。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：CLARITY_ART_CONFLICT
- phase2 准入已从 candidate 移除 rejected addition：ECONOMY_DEDUCT_TIMING
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
