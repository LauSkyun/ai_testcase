# Dual Pass 索引

## 运行结果
- 状态：complete
- 主模型：deepseek-v4-pro
- 副模型：deepseek-v4-pro
- 默认最终报告来源：candidate
- 默认最终报告路径：review_report.md
- 实际来源副本：review_report_candidate.md

## 推荐门槛
- 推荐状态：recommended
- 未通过原因：无
- Candidate 直出建议：是
- 原因：候选报告已修正主模型部分过高的严重度，补充了遗漏的关键不一致和边界条件，整体结构清晰、证据充分，可直接交付业务方阅读和跟进。
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
- Primary：D
- Pipeline：D
- Candidate：C
- Selected：C
- Pipeline 问题数：14
- Candidate 问题数：14
- Selected 问题数：14

## Trace 摘要
- raw：kept=11, added=3, merged=0, dropped=0
- materialized：kept=11, added=3, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 差异摘要
- Pipeline 独有问题数：0
- Candidate 独有问题数：0
- 共享问题中的重大改写数：10
- 重大改写示例：UI 原型图/文字描述与后台配置表中的赔率数值存在多处不一致；未定义每局游戏完整的金钱流转链路（扣款、累入、提现、清零）；用户个人赔付公式、奖池变动公式缺失，且奖池正常状态开奖偏移概率正文与表格冲突；“投入人数”的定义模糊，影响开奖逻辑判定；Repeat 按钮在余额不足以覆盖全部上一局投入时的处理未定义；开奖分析/游戏记录的文字描述与UI原型中的时间范围不一致；排行榜分数计算未说明是否扣除投入成本；缺少筹码、难度、概率、赔率、RTP、MAX_MUL、最大赔付之间的可验收映射；缺失异常流程、弱网、断线重连、并发等场景的验收标准，但多数为通用平台能力；未声明服务端为开奖随机结果、赔率、扣款、赔付的最终权威方
