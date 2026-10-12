# Dual Pass 副评审建议

## 总体判断
Candidate 由 Primary 与已准入增量确定性生成。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：Candidate 由系统确定性生成，不依赖模型自评。
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
- coverage ledger：未通过，完整率 100%
- coverage confirmed_add：funds_deduction_payout
- coverage confirmed controls：debit_timing
- coverage ledger 错误：coverage_control_invalid:statistics_time_window:ui_text_window_alignment:primary_control_mismatch:CLARITY_03
  - 拒绝《下注本金扣除时机未定义》：coverage_ledger_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 完整保留 Primary 骨架、评分和核心问题。

## 问题
- 暂无

## 复核备注
- funds_failure_compensation 因无证据证明公共流程缺失或冲突，降级为 advice_only，不进入 confirmed_add。
- single_round_payout_cap 因已有 MAX_MUL 形成有限赔付边界，无直接证据证明相对边界失效，降级为 advice_only。
- pool_negative_floor 和 same_metric_window 因玩法类型不适用，标注为 not_applicable。
- protocol_profile=phase2_v2_2; evidence_packet_id=f8e6d4bbfaa6b16e968171fefa3632afe6f37ff74d2ceb2732cf235a06cbfbd5
- phase2 准入已从 candidate 移除 rejected addition：DEBIT_01
- candidate_generation_mode=deterministic_primary_plus_admitted_delta

## 不支持的问题
- 暂无

## 合并建议
- 暂无
