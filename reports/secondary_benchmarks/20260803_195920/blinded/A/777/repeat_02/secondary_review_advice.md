# Dual Pass 副评审建议

## 总体判断
主模型报告整体结构完整，准确识别了风控与RESPIN冲突、累加算法歧义、盘面生成规则混乱等核心高阻塞问题。但存在部分误判（如推展机制、自动旋转交互），且遗漏了RESPIN最大赔付上限（MAX_MUL）这一关键经济边界缺口。

- 建议等级：medium
- 是否建议候选稿直出：是
- 原因：候选报告已修正主模型的误判，补充了MAX_MUL高信号缺口，结构完整、证据充分、来源可追踪，可直接给业务方阅读。
- 可追踪性：complete
- readiness 是否冲突：否
- candidate 是否有结构漂移：否
- primary issue_id 修复数：0
- candidate issue_id 修复数：0
- lineage 是否自动补齐：否
- suggestion_level 是否与 readiness 冲突：否
- 是否已对 suggestion_level 冲突做 override：否
- advice 与 candidate 落盘是否一致：是
- lineage 原始统计：kept=9, added=0, merged=0, dropped=0
- lineage 实际落盘统计：kept=9, added=0, merged=0, dropped=0
- added 落盘状态：none
- merged 落盘状态：none
- phase2 新增准入：声称 1，通过 0，拒绝 1
- coverage ledger：未通过，完整率 0%
- coverage ledger 错误：coverage_entry_count_invalid:0, coverage_audit_key_order_invalid, missed_finding_not_in_confirmed_add:LOGIC_MAX_MUL_01
  - 拒绝《RESPIN玩法最大赔付上限（MAX_MUL）缺失，且与风控规则边界不清》：missing_fields:audit_key, coverage_ledger_invalid, coverage_confirmed_add_link_missing
- 当前不建议默认切 candidate 的原因：phase2_coverage_ledger_invalid
- 阻断分类：protocol_blockers=phase2_coverage_ledger_invalid

## 优点
- 准确识别了风控规则与RESPIN触发条件的致命逻辑冲突。
- 敏锐捕捉到RESPIN累加算法在术语和举例上的歧义风险。
- 指出基础符号盘面生成规则的描述混乱问题。

## 问题
- 误判推展机制为自相矛盾，未识别出文档已明确其为表现激励。
- 误判自动旋转/快捷旋转交互规则缺失，实际文档已有明确说明。
- 遗漏了RESPIN玩法缺乏最大赔付上限（MAX_MUL）兜底的高信号经济边界问题。

## 复核备注
- 建议将“推展机制”在需求文档中明确标注为“纯客户端表现激励，严禁修改服务端结算数据”，以降低客户端开发误解风险。
- 建议明确RESPIN每次重转的乘数值是否为独立随机抽取，虽不阻塞主流程，但有助于测试设计极端用例。
- 建议统一需求文档与数值文档中关于“基础投注奖金”与“基础投注金额”的术语，避免举例中的笔误引发歧义。
- protocol_profile=phase2
- phase2 准入已从 candidate 移除 rejected addition：LOGIC_MAX_MUL_01

## 不支持的问题
- 暂无

## 合并建议
- 暂无
