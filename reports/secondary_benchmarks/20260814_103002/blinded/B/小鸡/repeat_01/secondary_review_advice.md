# Dual Pass 副评审建议

## 总体判断
主模型报告准确识别了倍率公式、筹码配置、概率算法等核心冲突，但部分 finding 存在症状堆砌（如将美术冲突与概率冲突混为一谈），且遗漏了资金链路中关键的扣款时机问题。

- 建议等级：low
- 是否建议候选稿直出：是
- 原因：候选报告已修正主模型的结构臃肿问题，补充了资金链路的高信号缺口，证据充分，维度归属合理，可直接输出给业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：3
- candidate issue_id 修复数：3
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=5, added=1, merged=0, dropped=0
- lineage 实际落盘统计：kept=5, added=1, merged=0, dropped=0
- added 落盘状态：complete
- merged 落盘状态：none

## 优点
- 准确抓住了连乘公式与累计倍率表的根本冲突
- 识别了固定概率与Crash算法的互斥问题
- 发现了筹码配置在三端的不一致

## 问题
- CORE_DIFFICULTY_CONFIG_MISMATCH 混合了概率、UI、美术三个不同维度的症状，焦点模糊
- 遗漏了开局扣款时机这一高信号资金安全问题
- 可测试性、跨系统等维度直接判空，未对断线恢复等博弈游戏核心验收点做最低限度提醒

## 复核备注
- 建议后续将 CORE_DIFFICULTY_CONFIG_MISMATCH 中的“美术包装冲突（小鸡 vs 骆驼）”拆分为独立的资源制作阻塞问题，以便美术团队单独跟进。
- 难度4（176倍盘）第30关数值高达6627万倍，疑似配置错误或公式推导溢出，需数值策划重点核查。
- 弱网、断线重连、历史局处理等通用中台能力，若已有平台规范，本文档无需赘述，但需确保核心结算链路不依赖客户端状态。
- dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。

## 不支持的问题
- 暂无

## 合并建议
- 暂无
