# Dual Pass 副评审建议

## 总体判断
主模型首版报告整体结构完整，准确识别了开奖兜底0赔付缺陷、奖池正常状态概率冲突、核心赔率多处矛盾、机器人机制缺失等高信号核心问题，top_blockers 聚焦合理，C 评分与证据强度匹配。但存在两处可改进点：(1) CLARITY_01（核心赔率冲突）直接决定结算金额与展示一致性，主模型仅判中风险偏保守，应升至高风险；(2) LOGIC_02 将'概率数值冲突'与'断线重连缺失'两个不同根因揉在同一条 finding 中，违反单根因原则，需在现状描述中分点展开或拆分归属维度。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选稿已修正 CLARITY_01 严重度、拆分 LOGIC_02 子症状并补充术语/时间范围口径冲突，结构完整、证据可追踪、lineage 清晰，可直接交付业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=10, added=2, merged=0, dropped=0
- lineage 实际落盘统计：kept=10, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- phase2 新增准入：声称 2，通过 0，拒绝 2
  - 拒绝《正文强制术语'spend'与 UI/规则/配置中大量'投入/bet'并存，存在术语冲突》：missing_fields:candidate_issue_id,current_state,blocking,confidence,independent_root_cause,primary_overlap_check, primary_overlap_check_invalid, multiroot_or_root_count_invalid
  - 拒绝《开奖分析与游戏记录的'时间范围'在正文与 UI 截图间存在矛盾》：missing_fields:candidate_issue_id,current_state,blocking,confidence,independent_root_cause,primary_overlap_check, primary_overlap_check_invalid, multiroot_or_root_count_invalid
- 当前不建议默认切 candidate 的原因：phase2_added_admission_rejected
- 阻断分类：quality_blockers=phase2_added_admission_rejected

## 优点
- 暂无

## 问题
- CLARITY_01 核心赔率冲突直接决定结算与展示，判中风险偏保守，应升至高风险并进入 top_blockers。
- LOGIC_02 混合了'奖池正常概率冲突'与'断线重连缺失'两个不同根因，违反单根因原则。
- 未识别 spend/投入 术语冲突、开奖分析与游戏记录时间范围在正文与 UI 截图间的矛盾等中信号问题。

## 复核备注
- CLARITY_01 由中风险升至高风险，理由：赔率直接决定结算金额与客户端展示，多处冲突将导致结算与展示不一致，属核心结算链路冲突。
- LOGIC_02 保留原 issue_id，在 current_state 中分点展开两个子症状：(1) 奖池正常状态概率正文 60% vs 配置表 20% 冲突；(2) 20s+5s+5s 短轮次制下断线重连专属规则缺失。
- 新增 CLARITY_04（术语冲突）与 CLARITY_05（时间范围矛盾），均基于共享输入中的明确证据（段落19、表格3、表格6、图1/图3/图6/图13/图18）。
- 主模型 top_blockers 原为 3 项，候选稿补充 CLARITY_01 为第 4 项高风险 blocker，与 overall_evaluation 和 score_reason 保持一致。
- 断线重连规则缺失虽属通用能力缺口，但因短轮次制（20s+5s+5s）下状态机切换频繁，且文档未明确任何恢复规则，故保留在 LOGIC_02 中作为子症状，不单独升维。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
