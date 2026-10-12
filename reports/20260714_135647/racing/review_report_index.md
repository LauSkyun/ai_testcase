# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：gpt-5.4
- 副模型：deepseek-v4-pro
- 默认最终报告来源：candidate
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_candidate.md

## 推荐门槛
- 推荐状态：recommended
- 未通过原因：无
- Candidate 直出建议：是
- 原因：候选报告已补充Luck定义、引导局数据隔离、假赔率生成规则等关键遗漏，主流程阻塞项保持高优先级，整体可直接交付业务方。
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
- Pipeline 问题数：12
- Candidate 问题数：10
- Selected 问题数：10

## Trace 摘要
- raw：kept=9, added=1, merged=0, dropped=0
- materialized：kept=9, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：2
- Candidate 独有问题数：0
- 共享问题中的重大改写数：4
- Pipeline 独有示例：假赔率生成规则缺失；引导局数据隔离规则缺失
- 重大改写示例：赔率计算核心公式存在两套冲突逻辑；半屏模式下的音频通道与UI层级验收标准缺失；“假赔率/假数据”的展示与结算边界未定义；新手引导倒计时与跳过机制缺失
