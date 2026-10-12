# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率冲突、开奖兜底逻辑缺陷和奖池状态偏移概率不一致等关键问题，整体结构清晰，维度划分合理。但存在个别严重度评估偏差（赔率冲突应升级为高，机器人机制缺失可降级为中等风险），且遗漏了投入扣款时机、预流失判定口径等影响结算和实现的具体细节。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选报告已修正主模型的主要偏差，升级了赔率冲突严重度，降低了机器人机制风险等级，并补充了扣款时机、预流失判定等关键遗漏，证据充分，结构完整，可直接交付业务方参考。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=10, added=3, merged=0, dropped=0
- lineage 实际落盘统计：kept=10, added=3, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- phase2 新增准入：声称 3，通过 0，拒绝 3
  - 拒绝《玩家投入扣款时机未明确，影响结算流程与充值交互》：missing_fields:candidate_issue_id,primary_dimension,current_state,risk,suggestion,severity,blocking,confidence,independent_root_cause,primary_overlap_check, primary_overlap_check_invalid, multiroot_or_root_count_invalid
  - 拒绝《预流失用户判定条件中‘有投入’口径模糊》：missing_fields:candidate_issue_id,primary_dimension,current_state,risk,suggestion,severity,blocking,confidence,independent_root_cause,primary_overlap_check, primary_overlap_check_invalid, multiroot_or_root_count_invalid, primary_duplicate_root
  - 拒绝《不抽水触发条件中最小选项投入金额为0时的边界行为未定义》：missing_fields:candidate_issue_id,primary_dimension,current_state,risk,suggestion,severity,blocking,confidence,independent_root_cause,primary_overlap_check, primary_overlap_check_invalid, multiroot_or_root_count_invalid, primary_duplicate_root
- 当前不建议默认切 candidate 的原因：phase2_added_admission_rejected
- 阻断分类：quality_blockers=phase2_added_admission_rejected

## 优点
- 精准定位了开奖兜底逻辑中‘开出0赔付’的机制缺陷，证据充分。
- 敏锐发现了奖池正常状态下偏移概率的正文与配置表冲突，直指实现阻塞。
- 全面梳理了赔率数值在UI、正文、配置表等多处不一致，覆盖了展示与结算风险。
- 测试点与异常场景覆盖较全，为后续用例设计提供了良好基础。

## 问题
- 赔率冲突问题（CLARITY_01）严重度被评为‘中’，实际应上调为‘高’，因其直接影响结算金额和玩家信任。
- 投入人数依赖机器人机制（CLARITY_02）被评为‘高’，但文档未明确要求机器人，属于设计选择待澄清，应降为‘中’。
- 遗漏了投入扣款时机这一影响结算和充值流程的关键定义。
- 遗漏了预流失用户判定中‘有投入’口径的模糊性，可能造成实现偏差。
- 未提及不抽水触发条件中最小选项投入金额为0时的边界行为。

## 复核备注
- 将CLARITY_01（赔率冲突）严重度从‘中’上调至‘高’，因其直接影响结算金额和玩家信任，应作为顶级阻塞项。
- 将CLARITY_02（机器人机制缺失）严重度从‘高’下调至‘中’，因文档未明确要求机器人，属于设计选择待澄清，非绝对阻塞。
- 新增CLARITY_04（投入扣款时机）为高优先级，缺失该定义将导致结算实现歧义。
- 新增LOGIC_04、LOGIC_05为低风险补充，用于完善边界条件。
- 更新top_blockers列表，反映上调后的赔率冲突和新增的扣款时机问题，移除机器人机制问题。
- 建议策划在后续版本中明确‘投入人数’是否包含机器人，以及不抽水触发条件中的零值处理。
- dual_pass 协议收敛提示：副模型对主模型首版报告给出负评，但 candidate_readiness=true 且候选稿结构/血缘完整，系统已按候选稿 readiness 自动收敛。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
