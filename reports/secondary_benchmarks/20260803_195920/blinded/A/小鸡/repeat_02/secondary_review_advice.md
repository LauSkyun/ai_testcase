# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了文档中核心的数值模型、结算公式与配置表冲突，但在问题归类上存在将不同根因（如概率算法与美术包装）混合的情况，且将通用中台能力（幂等性）误判为玩法专属高优问题。候选稿已对此进行结构化修正与补漏。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选稿已修正主模型中混合症状的表述，补充了核心经济边界缺口，并移除了无玩法专属证据的通用幂等问题，结构完整、证据充分，可直接输出。
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
- phase2 新增准入：声称 1，通过 0，拒绝 1
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:LOGIC_BET_DEDUCTION_TIMING
  - 拒绝《扣款时机与失败结算本金口径缺失》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确抓住了倍率公式连乘与累计倍率表的口径冲突
- 识别了下注筹码在需求、数值、UI三端的配置不一致
- 发现了通关超级大奖与第30格结算的边界歧义

## 问题
- 将概率算法冲突、美术包装冲突、UI概率展示混合在同一个finding中，未分点展开
- 将通用幂等性/防重复点击作为中风险finding，缺乏玩法专属边界缺失的证据
- 遗漏了开局扣款时机与失败结算本金口径这一核心经济边界问题

## 复核备注
- 幂等性、弱网、断线重连等属于通用中台能力，当前文档无玩法专属边界缺失证据，已将其从 findings 移除并记为低风险提醒。
- 题材包装（小鸡与骆驼混用）与概率算法冲突虽同属清晰度问题，但根因不同，已在 CORE_DIFFICULTY_CONFIG_MISMATCH 中分点展开说明，未拆分为独立 issue_id。
- 数值文档中难度3和难度4的表格数据与‘倍盘’命名存在数量级差异，需核实是否为配置错误。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：LOGIC_BET_DEDUCTION_TIMING
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
