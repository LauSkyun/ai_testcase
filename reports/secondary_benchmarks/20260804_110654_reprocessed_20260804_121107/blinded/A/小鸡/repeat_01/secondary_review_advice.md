# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了四组高信号核心冲突（概率模型、下注筹码、赔付公式、超级大奖边界），证据定位清晰，严重度判定合理。候选稿基本沿用主模型骨架，仅做分点展开与证据补强，未做乐观降级。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选稿已完整保留主模型四组高信号核心冲突，证据充分、来源可追踪、lineage 清晰，可直接交付业务方阅读；剩余待策划拍板项属于需求澄清范畴，不阻断报告直出。
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
- coverage ledger：未通过，完整率 100%
- coverage ledger 错误：coverage_schema_version_too_old:1:required:2
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确抓住两份文档在概率模型（固定概率 vs Crash 算法）、下注筹码（3/5/10/20 vs 100/1000）、赔付公式（连乘 vs 累计倍率）上的根本冲突
- 每个 finding 都给出了可定位的文档章节/段落/表格证据
- top_blockers 与 dimensions 内 finding 主轴一致，未出现顶层结论与细节冲突

## 问题
- SEC_01 幂等问题属于通用中台能力，按基准评审原则应降为低风险提醒，主模型给到'中'略偏高
- 小鸡/骆驼术语冲突、UI 概率展示口径等子症状揉在主问题里，建议分点展开但不拆 issue_id
- 未显式说明 MAX_MUL 与 Crash 公式如何映射到 30 个离散格子，仅在 LOGIC_03 中暗示

## 复核备注
- SEC_01 幂等问题按基准评审原则属通用中台能力，主模型给到'中'略偏高，建议后续降为低风险提醒，但本轮保留原严重度以维持与 primary 一致。
- 小鸡/骆驼术语冲突、UI 概率展示口径等子症状已揉在 CORE_DIFFICULTY_CONFIG_MISMATCH 中分点展开，未拆 issue_id。
- statistics_time_window（RTP 统计窗口、历史局配置热更对概率的影响）两份文档均未涉及，按基准评审原则属低风险通用项，不新增 finding。
- 建议数值策划补充完整的数值推导 Excel 或公式说明，便于开发复现与测试验收。
- protocol_profile=phase2
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
