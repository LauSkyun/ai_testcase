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
- lineage 原始统计：kept=10, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=10, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 2，通过 0，拒绝 2
- coverage ledger：未通过，完整率 100%
- coverage confirmed_add：max_payout_economic_boundary, statistics_time_window
- coverage confirmed controls：pool_negative_floor, ui_text_window_alignment
- coverage 安全归一化：inferred_coverage_schema_version:2_from_complete_control_shape
- coverage ledger 错误：coverage_control_invalid:max_payout_economic_boundary:single_round_payout_cap:primary_control_mismatch:LOGIC_01
  - 拒绝《奖池透支下限、回填边界与熔断条件未定义》：coverage_ledger_invalid
  - 拒绝《开奖分析时间窗口正文（7天）与UI截图（30天）不一致》：coverage_ledger_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 完整保留 Primary 骨架、评分和核心问题。

## 问题
- 暂无

## 复核备注
- LOGIC_02混合了概率冲突与断线重连两个独立根因，建议后续拆分为独立问题以便追踪。
- SEC_01严重度从低提升至中，因'实时计算'快照时机直接影响结算正确性与并发安全。
- 新增MAX_PAYOUT_01覆盖奖池透支下限边界缺口，与LOGIC_01的单局封顶问题控制面不同。
- 新增STATISTICS_01覆盖开奖分析时间窗口正文与UI不一致问题，与CLARITY_01的赔率冲突问题对象不同。
- protocol_profile=phase2_v2_1; evidence_packet_id=b4a6e1c32c61dd26379c4d03e435f3e135d8de14131c463c80393bdd956b09c9
- phase2 准入已从 candidate 移除 rejected addition：MAX_PAYOUT_01
- phase2 准入已从 candidate 移除 rejected addition：STATISTICS_01
- candidate_generation_mode=deterministic_primary_plus_admitted_delta
- dual_pass 结构提示：candidate 仍保留多根因混合问题，建议继续拆清根因或改为分点展示。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
