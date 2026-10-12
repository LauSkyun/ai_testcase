# Dual Pass 副评审建议

## 总体判断
主模型报告准确捕捉了核心数值公式冲突、下注筹码跨文档冲突、关卡数与难度定义缺失等关键阻塞问题，并指出了碰撞权威隐患和异常恢复缺失。但报告存在少量问题内部混合了多个根因（如数值冲突中混入美术资源问题），且遗漏了扣款时机、本金处理、初始提现规则、并发操作防护等重要边界条件。整体结构可用，但需修正后成为可直接交付的最终报告。

- 建议等级：medium
- 是否建议候选稿直出：否
- 原因：副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。
- 可追踪性：complete
- readiness 是否冲突：是
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=6, added=2, merged=0, dropped=0
- lineage 实际落盘统计：kept=6, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none
- 当前不建议默认切 candidate 的原因：normalized_candidate_not_ready
- 阻断分类：readiness_blockers=normalized_candidate_not_ready

## 优点
- 准确识别了爆炸倍数公式与赔率表的数量级冲突，直击数值模型核心矛盾
- 抓住了跨文档下注筹码、难度定义不一致的关键配置冲突
- 指出了碰撞判定客户端权威的安全隐患，以及提现幂等与断线重连规则缺失
- 测试点和缺失信息列表具有较好的覆盖度

## 问题
- NM-01 中混入了美术资源不一致问题，导致价值冲突表述不聚焦
- CL-01 中同时包含了下注筹码冲突，与 NM-03 重复，建议拆分
- 遗漏了扣款时机、本金口径、初始提现规则等影响结算的边界条件
- 遗漏了并发操作（快速连续点击开始/提现）的防护规则
- UI 展示概率与真实概率的映射关系未作为独立问题提出，仅隐含在 SC-01 中

## 复核备注
- 主模型 NM-01 中混入了美术资源不一致问题，候选稿已将其分离，美术资源问题降级为低风险写入 quality_notes，不影响整体阻塞评估。
- 主模型 CL-01 中重复出现了下注筹码冲突，候选稿已将其全部归入 NM-03，避免重复。
- 新增了扣款时机与本金处理规则（CL-02）和并发操作防护规则（TS-02），建议策划在下一版需求中补充。
- 新手引导内容缺失（仅‘如何玩?’按钮无具体引导）为低风险，可在后续迭代中完善，未作为独立 finding 输出。
- 建议后续进一步拆分 SC-01 中的概率映射问题，如需要更明确的合规审计，可单独作为一条问题。
- dual_pass 协议提示：quality_assessment.ready_for_direct_output 与 candidate_readiness.ready_for_direct_output 不一致，已统一降为 false。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
