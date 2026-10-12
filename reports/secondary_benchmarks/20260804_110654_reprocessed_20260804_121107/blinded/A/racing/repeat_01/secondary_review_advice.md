# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了核心赔率公式冲突、T变量定义歧义、假数据隔离缺失、真假赔率映射缺失等高信号阻塞项，问题定位精准、证据引用完整、严重度判定合理。但在结算时机、统计时间窗口一致性方面存在漏项，且部分finding的current_state存在重复表述可进一步精炼。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选稿已修正主模型重复表述问题，补充了结算时机与统计时间窗口两个高信号漏项，lineage追踪完整，可直接输出给业务方阅读。
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
- phase2 新增准入：声称 2，通过 0，拒绝 2
- coverage ledger：未通过，完整率 100%
- coverage confirmed_add：funds_deduction_payout, statistics_time_window
- coverage ledger 错误：coverage_schema_version_too_old:1:required:2
  - 拒绝《下注扣款时机与派奖时机未明确定义，结算链路存在缺口》：multiroot_funds_debit_and_payout_combined, coverage_ledger_invalid
  - 拒绝《统计模块时间窗口不一致：胜率/赔率使用30天，榜单使用今日/本周》：statistics_subject_or_metric_mismatch, coverage_ledger_invalid
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别T变量在需求文档（耗时）与数值文档（赔率分子）之间的根本性定义冲突
- 正确指出假人数/假金额可能参与实时赔率计算的数据源隔离风险
- 清晰区分'实际赔率'与'假赔率'在展示与结算之间的映射缺失
- 干预逻辑到速度公式的映射缺口定位准确
- 占位符问题按评审原则正确降级为低风险

## 问题
- T_VARIABLE_CONFLICT的current_state存在5处重复表述，未做分点整理
- 遗漏结算时机（扣款/发奖时间点）的明确性缺口
- 遗漏统计时间窗口（30天 vs 今日/本周）在不同模块间的不一致
- FAKE_ODDS_MAPPING与DATA_ISOLATION存在部分根因重叠但未做合并说明

## 复核备注
- T_VARIABLE_CONFLICT的current_state已做分点整理，消除主模型报告中的5处重复表述
- 新增LOGIC_FUNDS_01覆盖结算链路中扣款与派奖时间节点的明确性缺口
- 新增DATA_STATS_01覆盖不同统计模块时间窗口不一致的问题
- DATA_ISOLATION与FAKE_ODDS_MAPPING虽存在部分根因重叠（均涉及假数据处理），但前者关注计算数据源隔离，后者关注展示与结算映射，属于不同环节，保持独立
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：DATA_STATS_01
- phase2 准入已从 candidate 移除 rejected addition：LOGIC_FUNDS_01

## 不支持的问题
- 暂无

## 合并建议
- 暂无
