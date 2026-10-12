# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心数值模型、结算公式与配置表之间的严重冲突，以及下注筹码三端不一致的高阻塞问题。但在问题归类时，将低风险的美术包装冲突与高阻塞的概率计算冲突合并并拔高了严重度，需通过分点梳理与定性说明进行修正。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选稿已完整保留主模型的高信号核心阻塞项，补充了coverage_ledger核验，并对混合问题进行了分点梳理与严重度定性说明，结构完整、证据充分，可直接输出。
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
- phase2 新增准入：声称 0，通过 0，拒绝 0
- coverage ledger：通过，完整率 100%
- coverage 安全归一化：filled_not_applicable_evidence:statistics_time_window

## 优点
- 准确定位了需求公式（连乘）与数值表（累计倍率）的根本口径冲突。
- 识别出Crash算法映射到离散格子的规则缺失及第30格结算边界歧义。
- 发现了下注筹码在需求、数值、UI三端的配置不一致。

## 问题
- 将低风险的美术包装冲突（小鸡/骆驼）与高阻塞的概率计算冲突合并为同一个高严重度finding，存在严重度拔高问题。
- 部分finding的现状描述揉合了多个子症状，未进行清晰的分点展开。

## 复核备注
- CORE_DIFFICULTY_CONFIG_MISMATCH 中包含了‘美术包装冲突（小鸡/骆驼）’。根据评审原则3.3，主题、角色、美术包装不一致通常为低风险，不应与高阻塞的概率计算冲突合并并拔高严重度。候选稿已在 current_state 中将其分点列出并标记为低风险，建议后续拆分或仅作为低优先级修复，不阻塞核心开发。
- 关于扣款时机：文档未显式说明‘开局扣除下注金额’，但属于博弈游戏基础常识（段落20选择筹码，段落22点击开始），不构成高阻塞。建议开发时按行业惯例处理，并在服务端增加余额校验。
- protocol_profile=phase2
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。
- dual_pass 结构提示：candidate 仍保留多根因混合问题，建议继续拆清根因或改为分点展示。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
