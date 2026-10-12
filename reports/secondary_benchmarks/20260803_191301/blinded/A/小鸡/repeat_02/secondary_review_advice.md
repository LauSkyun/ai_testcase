# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了倍率公式口径、筹码配置、概率算法等核心冲突，但在根因归并上存在瑕疵，将美术包装冲突混入概率冲突中，且将通用中台能力（幂等）泛化为高阻塞问题。候选稿已对核心问题进行修正与聚焦，并补充了展示概率映射与扣款时机两个高信号缺口。

- 建议等级：medium
- 是否建议候选稿直出：否
- 原因：候选稿已修正主模型的根因混合问题，剥离了低信号的美术与幂等提醒，补充了直接影响结算验收与资金安全的高信号缺口，结构完整、证据充分，可直接输出给业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：3
- candidate issue_id 修复数：3
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=5, added=2, merged=0, dropped=0
- lineage 实际落盘统计：kept=5, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- phase2 新增准入：声称 2，通过 0，拒绝 2
  - 拒绝《UI“被击中概率”展示口径与Crash算法映射缺失》：multiroot_or_root_count_invalid, primary_duplicate_root
  - 拒绝《开局扣款时机与本金结算口径缺失》：multiroot_or_root_count_invalid
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready, candidate_missing_issue_id, phase2_added_admission_rejected
- 阻断分类：protocol_blockers=candidate_missing_issue_id; quality_blockers=phase2_added_admission_rejected; readiness_blockers=normalized_candidate_not_ready

## 优点
- 准确识别了需求公式（连乘）与数值表（累计倍率）的严重口径冲突。
- 发现了下注筹码在需求、数值、UI三端的配置不一致。
- 指出了需求文档固定概率与数值文档Crash算法的根本冲突。

## 问题
- 将‘小鸡/骆驼’的美术包装冲突与‘概率算法冲突’揉在同一个finding中，违反单根因原则。
- 将‘提现幂等’等通用中台能力泛化为高阻塞安全问题，未遵循弱网/幂等默认低风险的基准原则。
- 遗漏了UI展示概率与Crash算法的映射验收缺口，以及开局扣款时机的资金流转缺口。

## 复核备注
- 主模型将‘小鸡/骆驼’的美术包装冲突与‘概率算法冲突’揉在同一个finding中，候选稿已将其剥离。美术包装不一致通常为低风险，除非影响核心规则或付费内容，建议统一术语后在美术资源制作阶段解决。
- 主模型将‘提现幂等’泛化为高阻塞安全问题。根据基准原则，弱网、断线重连、重复点击等默认按低风险处理，只有当文档明确让扣款/赔付依赖客户端时才升高。候选稿已将其降级并移入quality_notes。
- 建议数值策划在修正倍率公式时，同步提供一份包含30个格子的‘累计倍率’与‘单格倍率’对照表，避免开发在实现时再次产生歧义。
- protocol_profile=phase2
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。
- dual_pass candidate 含空 issue_id 问题项，当前仅作为对比稿，不建议默认直出。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
