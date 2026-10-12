# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.6-sol
- 副模型：gpt-5.6-sol
- Secondary 协议：phase2
- Secondary 协议修订：phase2_v2_2
- Candidate 生成方式：deterministic_primary_plus_admitted_delta
- 证据包回显：通过
- Delta-only 输出：通过
- 默认最终报告来源：candidate
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_candidate.md

## 推荐门槛
- 推荐状态：recommended
- 未通过原因：无
- phase2 新增准入：通过 2 / 声称 2，拒绝 0
- coverage ledger：通过，完整率 100%
- coverage confirmed_add：funds_deduction_payout, max_payout_economic_boundary
- coverage confirmed controls：payout_timing, pool_negative_floor
- coverage 安全归一化：normalized_same_control_status:settlement_formula_ui_config:settlement_formula:covered_by_primary->covered_by_primary, normalized_same_control_status:settlement_formula_ui_config:ui_config_mapping:covered_by_primary->covered_by_primary, normalized_same_control_status:funds_deduction_payout:debit_timing:covered_by_primary->covered_by_primary
- Primary Top 3 门槛：通过
- Candidate 评分锁定 Primary：是
- Candidate 直出建议：是
- 原因：Candidate 由系统确定性生成，不依赖模型自评。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- candidate 是否达到结构直出门槛：是
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- 当前是否仅被编辑性判断阻断：否
- advice 与 candidate 落盘是否一致：是
- 是否存在无依据的高信号问题降级：否
- candidate 是否存在过度收缩：否

## 产物路径
- Pipeline：review_report_pipeline.md
- Candidate：review_report_candidate.md
- Advice：secondary_review_advice.md

## 评分与问题数
- Primary：C
- Pipeline：C
- Candidate：C
- Selected：C
- Pipeline 问题数：11
- Candidate 问题数：11
- Selected 问题数：11

## Trace 摘要
- raw：kept=9, added=2, merged=0, dropped=0
- materialized：kept=9, added=2, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：0
