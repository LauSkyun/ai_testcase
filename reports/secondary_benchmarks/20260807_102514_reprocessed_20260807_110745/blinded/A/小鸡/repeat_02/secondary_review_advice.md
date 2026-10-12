# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心数值模型、结算公式与配置表之间的严重冲突，以及角色包装与UI表现的割裂问题。但在资金事务控制面（扣款时机、失败补偿、绝对赔付封顶）存在明显漏项，需补充后方可作为最终交付物。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选稿已修正主模型结构，补充了资金事务与赔付边界的高信号缺口，证据充分，可直接输出给业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：3
- candidate issue_id 修复数：3
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=5, added=3, merged=0, dropped=0
- lineage 实际落盘统计：kept=5, added=3, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- phase2 新增准入：声称 3，通过 3，拒绝 0
- coverage ledger：通过，完整率 100%
- coverage confirmed_add：funds_deduction_payout, max_payout_economic_boundary
- coverage confirmed controls：debit_timing, funds_failure_compensation, single_round_payout_cap
- coverage 安全归一化：inferred_coverage_schema_version:2_from_complete_control_shape

## 优点
- 准确定位了需求公式（连乘）与数值表（累计倍率）的根本冲突。
- 识别了下注筹码在需求、数值、UI三端的配置不一致。
- 指出了Crash算法映射到离散格子的逻辑歧义。

## 问题
- 遗漏了本金扣除时机与失败‘清零’口径的歧义，可能导致资金流水对账失败。
- 未覆盖资金事务失败（如提现超时、扣款失败）的回滚与补偿机制。
- 未识别出缺乏单局绝对赔付金额封顶（MAX_PAYOUT）的重大资损风险。

## 复核备注
- 建议数值策划重新校验难度3和难度4的赔率推导公式，确保第30关的最终累计倍率与‘103倍盘’、‘176倍盘’的命名定义严格对齐。
- 建议明确最终核心角色（小鸡或骆驼），若保留小鸡需重写世界观与场景包装；若使用骆驼需重新设计UI资源与游戏标题。
- 建议补充‘被击中概率’的实时计算公式（如：当前格撞车概率 = 1 - (下一格爆炸倍数期望 / 当前格爆炸倍数期望)），并在UI上增加‘风险预警’视觉反馈。
- protocol_profile=phase2_v2_1; evidence_packet_id=200944b053334df973ab4939a58772f8b5d4f8dd144d90f3719d89035a7d2ce2
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
