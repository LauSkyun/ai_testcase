---
name: game-requirement-review
description: Analyze game requirement documents, numeric design documents, PRDs, feature specs, or gameplay configuration docs before requirement review or test-case design. Use when Codex needs to find ambiguous, contradictory, missing, risky, untestable, economically unsafe, insecure, anti-cheat-sensitive, compatibility-sensitive, or poor-UX requirements in game design docs, especially when requirement and numeric documents must be reviewed together.
---

# Game Requirement Review

Use this skill to perform a strict test-perspective review of game requirement and numeric design documents.

## Workflow

1. Identify all available documents and classify them as requirement, numeric/config, or unknown.
2. Read requirement and numeric/config documents together when both exist.
3. Extract facts before judging: gameplay loop, state machine, config/formulas, settlement timing, recovery rules, UI wording, and evidence anchors.
4. Preserve evidence from paragraphs, tables, and images. If images cannot be understood, explicitly mark the gap.
5. Review the documents across all six dimensions:
   - 清晰度与完整性
   - 逻辑一致性与数值平衡
   - 可测试性与验收标准
   - 跨系统影响与兼容性
   - 安全性与反作弊
   - 用户体验与游戏性
6. For every issue, include severity, evidence, risk, suggestion, confidence, and blocking level.
7. Mark insufficient evidence as 待澄清. Do not invent rules that are not supported by the documents.
8. End with core test point suggestions covering function, exception, compatibility, security, regression, performance, and UX.

## Stability Mode

- Prefer one main analysis for daily work. Improve stability through fact-first extraction, fixed scoring rules, evidence strength, deterministic post-processing, and baseline regression rather than repeated free-form reports.
- When a second pass is needed, use an audit/checker mindset instead of producing another complete report. Simulate lead designer, programmer, numeric designer, and QA perspectives together, but only output missed high-risk findings, unsupported findings, and score calibration notes.
- Do not let the audit pass rewrite style or regenerate the whole report. It should correct or supplement the main report.
- `prompts.py` is the runtime source of analysis behavior; this skill mirrors the method for human/agent use; `AGENTS.md` only records maintenance constraints.

## Document Score

- A: Core gameplay, numeric rules, boundaries, exceptions, and acceptance criteria are clear. Only low-risk polish remains.
- B: Main flow and key numeric rules are developable. A few medium-risk gaps remain but do not block the main implementation.
- C: Main flow is understandable, but high-risk inconsistencies, missing boundaries, unclear numeric mappings, or weak acceptance criteria remain. Review and document fixes are needed before full development.
- D: Only use when core gameplay, numeric model, or settlement flow is fundamentally contradictory or not understandable, so development and QA cannot form one implementation plan. Do not assign D only because there are many high-risk findings.

Always include a one-sentence score reason.

## Baseline Review Principles

- First decide whether the main gameplay loop is understandable, then review numeric/config mappings, settlement timing, reconnect/re-enter recovery, max payout, and how client presentation maps to server results.
- Treat a report with many high-risk but fixable gaps as C when the main loop is understandable. Reserve D for root conflicts such as incompatible payout formulas, impossible state machines, or settlement chains that cannot be reconciled.
- Do not raise generic wallet, balance, compatibility, operations, analytics, logs, GM, or accounting-ledger gaps when they are covered by shared platform specs. Only raise feature-specific missing boundaries such as deduction/acquisition timing, max payout overflow, reconnect/re-enter behavior, in-progress settlement, or config changes affecting historical rounds.
- Usually mark theme, character, art package, or temporary asset-name inconsistency as 低 unless it directly changes core rules, hitbox size, paid content, required launch assets, or acceptance criteria.
- Confidence means evidence strength, not severity: 高 = directly proven by text/table/image; 中 = strongly implied by multiple fragments; 低 = risk inferred from missing information or experience.

## Quality Bar

- Prefer high-signal findings that can prevent rework, online incidents, economy loss, or untestable implementation.
- Do not fill dimensions with generic advice. If evidence is weak, mark 待澄清 and lower confidence.
- Merge duplicate root causes instead of repeating the same issue across dimensions.
- Tie titles, severity, blocking level, and score to evidence strength and gameplay impact. Do not vary the report angle just to create novel findings on repeated runs.
- For a normal feature document, aim for 8-15 meaningful findings. If there are more, group them by root cause.
- Add a planning owner to every finding: 数值策划, 系统策划 or 待定.
- Usually mark theme, character, art package, or temporary asset-name inconsistency as 低 unless it directly changes core rules, hitbox size, paid content, or required launch assets.
- Assume this middle-platform team has server-side functional logic by default and the client only presents results. Do not raise "server/client responsibility unclear" by itself; only raise it when the document says the client determines win/loss, payout, random result, odds, or when presentation cannot be reconciled with server results.
- Do not raise generic wallet, balance, compatibility, operations, analytics, logs, GM, or accounting-ledger gaps when they are covered by shared platform specs. Only raise feature-specific missing boundaries such as deduction/acquisition timing, max payout overflow, reconnect/re-enter behavior, in-progress settlement, or config changes affecting historical rounds.
- Always check game-specific risks: bet placement, deduction/acquisition timing, RTP, odds table, reconnect recovery, repeat click, cashout/settlement idempotency, max payout, re-enter behavior, and configuration changes.
- For each finding, write a clear 现状描述 before risk analysis. Explain what is conflicting, missing, or non-executable in plain language, not only evidence references.
- Make suggestions executable: propose document clauses, states, fields, formulas, boundary tables, or examples.
- Useful deep-dive angles include core terminology consistency, the timing of server result judgment after clicking Start, how client presentation maps to server results, the application layer of difficulty/probability/odds pools, final-step behavior, and whether subjective UX descriptions can become acceptance criteria.
- Always check chips/bet tiers, difficulty, probability, odds, RTP, MAX_MUL, max payout, deduction/acquisition timing, cashout/settlement, failure clearing, final-step behavior, reconnect recovery, repeated clicks/idempotency, config hot update, historical rounds, and probability/odds UI wording.
- Treat unparsed UI images or flow diagrams as an explicit quality gap.

## Severity

- 高: Blocks development or test design, risks serious online incidents, resource exploits, rollback, payment/economy damage, data corruption, or major player harm.
- 中: Causes ambiguous implementation, missed edge cases, inconsistent QA acceptance, compatibility defects, operational data gaps, or moderate UX damage.
- 低: Improves clarity, maintainability, polish, observability, or minor UX consistency without blocking core delivery.

## Confidence

- 高: Directly supported by explicit document text, table values, or image content.
- 中: Strongly implied by multiple document fragments but still needs owner confirmation.
- 低: Plausible risk raised from missing information or common game-system failure modes.

## Blocking Level

- 阻塞开发: The implementation cannot be safely designed without clarification.
- 阻塞测试用例设计: QA cannot produce reliable acceptance or boundary cases without clarification.
- 建议优化: The feature can proceed, but the document should be improved to reduce risk.

## Output

Use this structure:

```markdown
# 需求文档分析报告

## 一、总体评价
[2-3句话概括整体质量，并指出最大1-2个风险]

- **文档质量评分：** [A/B/C/D]
- **评分原因：** [一句话解释扣分点]

## 优先处理事项
- **[高/中/低] 问题标题**
  - 责任建议：[系统策划/数值策划/程序/测试/运营/待定]
  - 处理原因：[为什么评审前必须处理]

## 二、逐维度问题清单
### 【维度名称】
- **[严重程度：高/中/低] 问题一句话标题**
  - 现状描述：[当前哪里冲突、缺失或不可执行]
  - 证据来源：[文档名 / 章节、表格或图片编号 / 原文或具体场景]
  - 风险分析：[导致测试受阻、返工、线上事故或体验损害的过程]
  - 修改建议：[明确、可执行的补充或改写方向]
  - 关注角色：[系统策划/数值策划/待定]
  - 置信度：[高/中/低]
  - 阻塞级别：[阻塞开发/阻塞测试用例设计/建议优化]

## 三、核心测试点建议
- **功能验证：** [...]
- **异常操作：** [...]
- **兼容性：** [...]
- **安全专项：** [...]
- **回归影响：** [...]
- **性能与稳定性：** [...]
- **用户体验：** [...]
```
