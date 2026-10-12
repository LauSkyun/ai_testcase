from __future__ import annotations

import hashlib
import json
from textwrap import dedent

from rad_review.docx_reader import ParsedDocument, build_collection_summary


DIMENSIONS = [
    "清晰度与完整性",
    "逻辑一致性与数值平衡",
    "可测试性与验收标准",
    "跨系统影响与兼容性",
    "安全性与反作弊",
    "用户体验与游戏性",
]


ROLE_PROMPT = dedent(
    """
    你是一名资深游戏测试与需求评审专家。
    你的目标是在开发前，基于当前输入文档中的明确证据，识别需求中的模糊、矛盾、缺失和风险。
    只能把文档里能证明的内容写进报告；无法确认时，明确写“待澄清”，不要把猜测包装成事实。
    """
).strip()


REVIEW_RULES = dedent(
    """
    请严格从以下六个维度审查文档，并给出可执行的修订建议：
    1. 清晰度与完整性：术语、入口、流程、状态、按钮、配置、公式、边界条件是否清楚。
    2. 逻辑一致性与数值平衡：玩法规则、状态流转、奖励公式、概率、倍率、数值口径是否一致。
    3. 可测试性与验收标准：主流程、异常流程、弱网、重复点击、并发、回退、重进等是否有明确验收口径。
    4. 跨系统影响与兼容性：仅关注本玩法直接新增的恢复、热更、历史局处理、界面层级等专属规则。
    5. 安全性与反作弊：随机结果、扣款、派奖、幂等、防篡改和服务端权威边界是否清楚。
    6. 用户体验与游戏性：新手理解、失败反馈、引导、节奏、按钮可理解性与信息反馈是否合理。
    """
).strip()


BASELINE_REVIEW_PRINCIPLES = dedent(
    """
    基准评审原则：
    - 先判断主玩法循环是否能跑通，再检查数值/配置映射、结算时机、异常恢复、最大赔付、服务端结果与客户端表现映射。
    - 不要把通用中台能力泛化成高危问题；钱包、日志、埋点、运营后台、通用兼容等如果已有平台规范，只有在本文缺少玩法专属边界时才列问题。
    - 配置默认值、占位符、可配范围、接口字段蓝图、配置表示例缺失，如果没有直接造成公式冲突、结算歧义或主流程无法编译，默认按低风险处理，不要轻易给高严重度。
    - 弱网、断线重连、重进恢复、配置热更、历史局、服务端权威性说明等，默认按低风险处理；只有当文档已经明确让胜负、赔率、扣款、赔付依赖客户端，或这些规则与核心结算链路直接冲突时，才允许升高严重度。
    - 主题、角色、美术包装、临时资源名不一致通常为低风险；只有影响核心规则、碰撞范围、付费内容、上线资源或验收口径时才提高严重程度。
    - 优先输出 8-15 个高信号根因。相同根因合并，不要为了填满维度重复输出。
    - 置信度表示证据强度，不表示严重程度；文档直接证明为高，多处暗示为中，经验推断为低。
    """
).strip()


PLACEHOLDER_CONFIGURATION_POLICY = dedent(
    """
    占位符与配置值专项口径（优先级高于通用缺失项检查）：
    - `[001]`、TBD、待配置、待填写、示例值、默认值、概率/倍率/阈值/上下限等具体配置值未填，视为团队约定的正常配置流程，不是需求风险。
    - 不得仅因这类占位符或具体配置值未给出而生成 finding、Top Blocker、缺失信息、质量备注、测试点或扣分；即使字段名称包含“最大赔付”“最小赔付”“概率”“倍率”等，也不得把“尚未填具体值”包装成实现阻塞或高风险。
    - 只有当前文档的明确证据能证明两条已给规则/公式互相冲突、结算口径矛盾、出现除零/死锁，或主流程在不依赖具体配置值的情况下仍不可执行时，才报告那个实际冲突；标题、风险与建议必须针对实际冲突，不得再以“占位符未填”作为根因。
    """
).strip()


SPECIAL_CHECKLIST = dedent(
    """
    必查专项：
    - 筹码、难度、概率、赔率、RTP、MAX_MUL、最大赔付之间是否有可验收映射。
    - 开局扣款、局内累计、获得、提现、失败清零、通关奖励、最后一步行为是否清楚。
    - 重进/断线恢复、重复点击/幂等、结算中退出、配置热更与历史局处理是否有玩法专属规则。
    - UI 展示的概率、赔率、倍率、排行榜、结果弹窗是否能和真实结算或服务端结果对齐。
    - 如果服务端已默认负责功能逻辑，不要单独输出“服务端/客户端责任不清”；只在文档暗示客户端决定胜负、随机、赔率、赔付，或表现无法对齐服务端结果时提出。
    """
).strip()


STABILITY_PROTOCOL = dedent(
    """
    稳定输出要求：
    - 同一根因只输出一次，不要在多个维度重复刷屏。
    - 只有当前输入里真的存在两份及以上文档，且证据明确分别来自不同文档时，才输出 cross_document_issues。
    - 单文档场景不要假设一定存在独立数值文档；如果同一文档同时包含需求和数值信息，按单文档分析。
    - 不要引用历史项目、旧案例、其他游戏名称、未在当前上下文出现的术语。
    - 每条问题都必须带证据来源，格式优先使用“文档名 / 章节、段落、表格或图片编号”。
    - 如果证据只对应当前输入中的一份文档，就不要把该问题写进 cross_document_issues。
    """
).strip()


FACT_FIRST_PROTOCOL = dedent(
    """
    稳定化分析流程（必须按顺序执行，但最终只输出 JSON）：
    1. 先抽取事实，不要先下结论：主玩法循环、状态机/局内阶段、配置与公式、结算/扣款/发奖时机、异常恢复、UI 展示口径、证据索引。
    2. 每个问题都必须从上述事实缺口或事实冲突推导出来，不要因为“常见平台能力”自动生成高危问题。
    3. 问题标题、严重程度、阻塞级别要绑定证据强度：证据越弱，置信度越低；严重程度只看对玩法实现、数值结算、测试验收的实际影响。
    3.1 配置具体值/范围/默认值/占位符缺失，如果不直接阻断公式求值或结算链路，严重程度默认低。
    3.2 弱网、断线重连、热更、历史局、服务端权威性说明，默认只记低风险提醒，不要默认高风险。
    3.3 新手引导、教程演示、教学局说明默认只记低风险；即使涉及玩法口径冲突，严重程度最高也只到中风险，不要直接记高风险。
    4. 相同根因只输出一次，优先输出 8-15 个高信号根因；不要为了覆盖维度而拆成多个近似问题。
    5. 如果无法找到文档名、章节、段落、表格或图片编号作为证据，该 finding 通常只能作为待澄清信息，不能作为高置信高风险问题。
    """
).strip()


SCORE_RUBRIC = dedent(
    """
    评分规则：
    - A：核心玩法、数值、边界和验收标准完整清晰，可直接进入开发和测试设计。
    - B：主流程和关键数值基本可落地，仅有少量中低风险补充项；如果不存在 fatal 冲突，且高风险问题少于 3 个，也可以评为 B。
    - C：主流程可理解，但存在较多高风险缺口、关键边界缺失或验收标准不足，需要补充后再完整开工。
    - D：仅用于核心玩法、数值模型或结算链路互相矛盾到无法形成一致实现方案，或存在会造成严重经济/结算事故的根本冲突。
    - 问题数量多但主流程可理解、补文档后能推进的情况，优先评为 C，不要仅因高风险项数量多评为 D。
    - 必须输出一句评分原因，说明扣分点。
    """
).strip()


OUTPUT_QUALITY_BAR = dedent(
    """
    输出质量要求：
    - 优先输出会阻塞开发、测试设计、结算正确性、安全性或用户理解的高信号问题。
    - 每条问题都要形成“现状描述 -> 证据 -> 风险 -> 修改建议”的闭环。
    - 如果某维度没有明显问题，对应 findings 为空，并在 dimension_note 写“未发现明显问题”。
    - 图片未解析或超限时，必须在 image_analysis_gaps 或 quality_notes 中说明风险。
    - 建议要可落地，优先提出文档条款、状态表、字段、公式、边界表或示例，而不是只写“补充说明”。
    """
).strip()


ROOT_CAUSE_PROMPT_RULES = dedent(
    """
    根因归并要求：
    - 同一实现阻塞如果只是不同表述、不同侧面、不同证据来源，不要拆成多个问题。
    - 先判断它们是不是同一根因的多个症状，再决定是否单列。
    - 一条 finding 只能对应一个可独立关闭单元：一个决策对象、一个主要根因、一个主修复动作和一个验收闭环。
    - “同一根因只输出一次”不等于把同一维度、同一文档或同一业务主题全部合并；概率、符号名、筹码挡位、流程交互等对象不同就必须拆分。
    - 即使多个问题共同出现在同一张表或同一次跨文档审计中，只要需要分别修改配置字段、分别分配责任人或分别设计验收用例，就必须输出为独立 finding。
    - cross_document_issues 也必须保持原子化，禁止用“多处配置不一致”汇总概率、命名、金额、流程等多个可独立修复的问题。
    - 建议可以包含完成同一整改目标所需的多个步骤；如果其中任一步可以独立上线或独立验收，应拆成另一个 finding。
    - 赔率公式冲突、展示赔率/实际赔率口径分裂、假赔率机制缺失、赔率公式占位符，如果本质上指向同一实现阻塞，应合并为一个主问题。
    - 干扰指数、Luck、T 公式、地形概率之间如果是在说同一套干预映射缺口，应合并为一个主问题。
    - 假人数/假金额展示与真实结算、奖池计量的数据源隔离问题，如果本质一致，应合并为一个主问题。
    """
).strip()


STRICT_AUDIT_SCHEMA_INSTRUCTION = dedent(
    """
    只输出合法 JSON，不要输出 Markdown。你不是重新生成报告，而是作为综合校验器检查主报告。
    {
      "missed_high_risk_findings": [
        {
          "issue_id": "可选归类键",
          "canonical_title": "可选标准标签",
          "primary_dimension": "问题所属维度",
          "evidence_scope": "document/cross_document/table/image",
          "severity": "高/中/低",
          "title": "贴近具体问题的展示标题",
          "current_state": "现状描述",
          "evidence": "必须带文档名 / 章节、段落、表格或图片编号",
          "risk": "为什么会影响实现、数值、结算或测试",
          "suggestion": "补充或修正文档建议",
          "planner_role": "系统策划/数值策划/服务端/客户端/测试/运营",
          "confidence": "高/中/低",
          "blocking": "阻塞开发/阻塞测试用例设计/建议优化"
        }
      ],
      "unsupported_findings": [
        {
          "title": "主报告中不成立、重复拆分或证据不足的问题标题",
          "reason": "为什么证据不支持，或为什么它其实属于另一条根因"
        }
      ],
      "merge_recommendations": [
        {
          "titles": ["应合并的问题标题A", "应合并的问题标题B"],
          "merged_title": "合并后的主标题建议",
          "reason": "为什么它们其实是同一根因的多个症状"
        }
      ],
      "score_adjustment": {
        "suggested_score": "A/B/C/D",
        "reason": "最终 strict 报告应落到该评分的原因；如果仍是 D，必须明确说明是哪一个单一核心根因独立触发 fatal，以及当前评分是否被同根因重复计数放大"
      },
      "audit_notes": []
    }
    校验视角合并模拟主策划、程序、数值、测试四方：只补充遗漏的高风险根因、指出不该成立的问题、指出应该合并的同根因问题，并判断评分是否明显偏高或偏低。
    不要输出另一份完整报告，不要重写已有风格；没有高置信修正时返回空数组，但 score_adjustment 仍必须给出最终评分。
    """
).strip()


JSON_SCHEMA_INSTRUCTION = dedent(
    """
    只返回一个合法 JSON 对象，不要使用 Markdown 代码块。字段结构如下：
    {
      "overall_evaluation": "2-3句总体评价",
      "document_quality_score": "A/B/C/D",
      "score_reason": "一句话评分原因",
      "top_blockers": [
        {
          "severity": "高/中/低",
          "title": "最优先问题",
          "owner": "系统策划/数值策划/程序/测试/运营/待定",
          "why_now": "为什么现在必须处理"
        }
      ],
      "dimensions": [
        {
          "name": "清晰度与完整性",
          "dimension_note": "无问题时写未发现明显问题",
          "findings": [
            {
              "issue_id": "可选归类标签；无法匹配时可为空字符串",
              "canonical_title": "可选标准标题；用于内部归类，不要求与 title 完全一致",
              "primary_dimension": "所属主维度",
              "evidence_scope": "document/cross_document/table/image",
              "severity": "高/中/低",
              "title": "报告实际展示标题，优先写最贴近当前问题的一句话标题",
              "current_state": "现状描述",
              "evidence": "证据来源，优先写成“文档名 / 章节、段落、表格或图片编号”",
              "risk": "风险分析",
              "suggestion": "修改建议",
              "planner_role": "系统策划/数值策划/程序/测试/待定",
              "confidence": "高/中/低",
              "blocking": "阻塞开发/阻塞测试用例设计/建议优化"
            }
          ]
        }
      ],
      "cross_document_issues": [],
      "missing_information": [],
      "test_points": {
        "功能验证": [],
        "异常操作": [],
        "兼容性": [],
        "安全专项": [],
        "回归影响": [],
        "性能与稳定性": [],
        "用户体验": []
      },
      "quality_notes": [],
      "image_analysis_gaps": []
    }
    dimensions 必须包含六个维度，顺序与上文一致。
    title 是最终展示标题；issue_id 和 canonical_title 仅作为辅助归类信息，不要为了匹配固定标题而牺牲问题描述准确性。
    """
).strip()


IMAGE_PROMPT = dedent(
    """
    请作为游戏需求评审助手，提取这张文档图片中明确可见的信息。
    只描述图片里能看到的 UI、流程、状态、按钮、提示、公式、配置或数值。
    如果有文字看不清，明确说明不可读区域，不要猜测图片外的信息。
    输出 3-8 条中文要点。
    """
).strip()


def build_review_messages(documents: list[ParsedDocument], max_context_chars: int) -> list[dict[str, str]]:
    context = build_document_context(documents)
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n\n[上下文因长度限制被截断，请优先基于已给证据分析，并在缺失信息中提示可能遗漏。]"
    document_labels = [f"{doc.name} ({doc.kind})" for doc in documents]
    current_document_constraints = "\n".join(
        [
            "当前文档约束：",
            f"- 本次输入文档：{', '.join(document_labels) or '无'}",
            "- 只能基于本次输入文档内容输出，不得引用此前项目、历史案例或其他游戏需求。",
            "- 如果当前上下文里没有某个玩法名词、角色名、旧项目名或规则，不要主动补写到报告里。",
            "- 只有在本次确实输入了两份及以上文档，且证据同时来自不同文档时，才输出跨文档一致性问题。",
            "- 如果证据里不能明确标出至少两个当前输入文档名，就不要输出 cross_document_issues。",
            "- 单文档场景不要假设一定存在独立数值文档；若同一文档同时包含规则和数值信息，可直接按单文档分析。",
        ]
    )
    user_prompt = "\n\n".join(
        [
            "请分析以下游戏需求/数值文档内容。",
            current_document_constraints,
            "集合摘要：",
            json.dumps(build_collection_summary(documents), ensure_ascii=False, indent=2),
            "文档内容：",
            context,
            JSON_SCHEMA_INSTRUCTION,
        ]
    )
    return [
        {"role": "system", "content": ROLE_PROMPT},
        {
            "role": "user",
            "content": REVIEW_RULES
            + "\n\n"
            + BASELINE_REVIEW_PRINCIPLES
            + "\n\n"
            + PLACEHOLDER_CONFIGURATION_POLICY
            + "\n\n"
            + SPECIAL_CHECKLIST
            + "\n\n"
            + FACT_FIRST_PROTOCOL
            + "\n\n"
            + ROOT_CAUSE_PROMPT_RULES
            + "\n\n"
            + STABILITY_PROTOCOL
            + "\n\n"
            + SCORE_RUBRIC
            + "\n\n"
            + OUTPUT_QUALITY_BAR
            + "\n\n"
            + user_prompt,
        },
    ]


AUDIT_SCHEMA_INSTRUCTION = dedent(
    """
    只输出合法 JSON，不要输出 Markdown。你不是重新生成报告，而是作为综合校验器检查主报告。
    {
      "missed_high_risk_findings": [
        {
          "issue_id": "可选归类键",
          "canonical_title": "可选标准标签",
          "primary_dimension": "问题所属维度",
          "evidence_scope": "document/cross_document/table/image",
          "severity": "高/中/低",
          "title": "贴近具体问题的展示标题",
          "current_state": "现状描述",
          "evidence": "必须带文档名 / 章节、段落、表格或图片编号",
          "risk": "为什么会影响实现、数值、结算或测试",
          "suggestion": "补充或修正建议",
          "planner_role": "系统策划/数值策划/服务端/客户端/测试/运营",
          "confidence": "高/中/低",
          "blocking": "阻塞开发/阻塞测试用例设计/建议优化"
        }
      ],
      "unsupported_findings": [
        {
          "title": "主报告中不成立或证据不足的问题标题",
          "reason": "为什么证据不支持"
        }
      ],
      "score_adjustment": {
        "suggested_score": "A/B/C/D/保持不变",
        "reason": "只在评分明显过高或过低时填写"
      },
      "audit_notes": []
    }
    校验视角合并模拟主策划、程序、数值、测试四方：只补充遗漏的高风险根因、指出不该成立的问题、判断评分是否明显偏移。
    不要输出另一份完整报告；不要重写已有风格；没有高置信修正时返回空数组。
    """
).strip()


def build_audit_messages(
    documents: list[ParsedDocument],
    report: dict[str, object],
    max_context_chars: int,
) -> list[dict[str, str]]:
    context = build_document_context(documents)
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n\n[上下文过长，已截断；只基于当前可见内容校验。]"
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    user_prompt = "\n\n".join(
        [
            "请基于当前输入文档和主报告做一次轻量校验。",
            "当前输入文档摘要：",
            json.dumps(build_collection_summary(documents), ensure_ascii=False, indent=2),
            "当前输入文档上下文：",
            context,
            "主报告 JSON：",
            report_json,
            STRICT_AUDIT_SCHEMA_INSTRUCTION,
        ]
    )
    return [
        {"role": "system", "content": "你是游戏需求评审的综合校验器，合并主策划、程序、数值、测试视角，只做高置信修正。"},
        {
            "role": "user",
            "content": FACT_FIRST_PROTOCOL
            + "\n\n"
            + PLACEHOLDER_CONFIGURATION_POLICY
            + "\n\n"
            + ROOT_CAUSE_PROMPT_RULES
            + "\n\n"
            + SCORE_RUBRIC
            + "\n\n"
            + user_prompt,
        },
    ]


def build_document_context(documents: list[ParsedDocument]) -> str:
    chunks: list[str] = []
    for doc in documents:
        chunks.append(f"# 文档：{doc.name}（类型：{doc.kind}）")
        chunks.append("## 正文段落")
        for paragraph in doc.paragraphs:
            heading = " > ".join(paragraph.heading_path)
            prefix = f"[段落{paragraph.index}]"
            if heading:
                prefix += f"[章节：{heading}]"
            chunks.append(f"{prefix} {paragraph.text}")
        chunks.append("## 表格")
        if doc.tables:
            for table in doc.tables:
                heading = " > ".join(table.heading_path) or "未识别章节"
                chunks.append(f"### 表格{table.index}（章节：{heading}）")
                chunks.append(table.markdown)
        else:
            chunks.append("无表格。")
        chunks.append("## 图片解析")
        if doc.images:
            for image in doc.images:
                label = f"图片{image.index}（{image.source_name}）"
                if image.analysis:
                    chunks.append(f"- {label}: {image.analysis}")
                elif image.error:
                    chunks.append(f"- {label}: 图片解析失败：{image.error}")
                else:
                    chunks.append(f"- {label}: 已提取但未解析。")
        else:
            chunks.append("无图片。")
    return "\n".join(chunks)


DUAL_PASS_SCHEMA_INSTRUCTION = dedent(
    """
    只返回一个合法 JSON 对象，不要使用 Markdown 代码块。顶层字段必须包含：
    {
      "quality_assessment": {
        "summary": "对主模型报告质量的总体评价",
        "strengths": ["主模型报告做得好的点"],
        "issues": ["主模型报告仍存在的问题"],
        "suggestion_level": "low/medium/high",
        "ready_for_direct_output": true,
        "reason": "为什么建议或不建议直接采用候选成稿"
      },
      "coverage_ledger": [],
      "missed_findings": [],
      "unsupported_findings": [],
      "merge_recommendations": [],
      "candidate_lineage": {
        "kept": [],
        "added": [],
        "merged": [],
        "dropped": []
      },
      "candidate_report": {
        "overall_evaluation": "2-3句总体评价",
        "document_quality_score": "A/B/C/D",
        "score_reason": "一句话评分原因",
        "top_blockers": [],
        "dimensions": [],
        "cross_document_issues": [],
        "missing_information": [],
        "test_points": {},
        "quality_notes": [],
        "image_analysis_gaps": []
      },
      "candidate_readiness": {
        "ready_for_direct_output": true,
        "reason": "候选报告是否可直接输出及原因"
      },
      "review_notes": []
    }
    missed_findings / unsupported_findings / merge_recommendations 的结构沿用综合校验器语义。
    只要 candidate_report 非空，就必须返回 candidate_lineage；即使候选稿与主模型几乎一致，也必须在 kept 中显式标记沿用关系。
    candidate_report 必须完整复用标准报告结构，且只基于共享输入与主模型报告中的事实修正后生成。
    """
).strip()


DUAL_PASS_LINEAGE_RULES = dedent(
    """
    候选稿生成附加规则：
    1. 先判断 quality_assessment.ready_for_direct_output，并把它作为 readiness 的唯一事实源；若无法确定，统一返回 false。
    2. 再将同一个布尔值原样复制到 candidate_readiness.ready_for_direct_output；不得出现一个 true、一个 false。
    3. quality_assessment.reason 与 candidate_readiness.reason 也必须保持同一句理由；先写前者，再把相同文本原样复制到后者，不得改写。
    4. 输出前自检：如果两个 readiness 的布尔值或 reason 不完全一致，先改成完全一致后再输出 JSON。
    5. 这里的 ready_for_direct_output 只表示“这份候选报告本身是否已达到可直接给业务 / 产品 / 研发阅读的输出质量”，不表示“文档里的所有需求问题都已被产品确认解决”。
    6. 文档内仍存在待策划确认、待产品拍板、待研发实现澄清的问题，本身不是阻断报告直出的理由；只有当候选报告本身存在结构、证据、追踪、命名、严重失真或不可交付问题时，才把 ready_for_direct_output 设为 false。
    7. quality_assessment 可以批评主模型首版报告的缺点，但 quality_assessment.ready_for_direct_output 回答的仍然是“候选稿在你修正后是否建议直接输出”；如果 primary 有问题但 candidate 已修正到可交付，两个 readiness 都应返回 true。
    8. 若 candidate finding 与 primary finding 为同一根因，优先复用 primary 的 issue_id 与主标题，不要仅为润色而重建整套 issue_id。
    9. 只要 candidate_report 非空，就不允许省略 candidate_lineage，也不允许只改结构不写 lineage。
    10. 若 candidate finding 与 primary finding 为同一问题，即使只补证据、修标题、改描述或补建议，也必须写入 candidate_lineage.kept。
    11. 若某个 missed finding 被吸收到 kept 问题中，必须写入对应 kept 项的 absorbed_missed_issue_ids；不要一边声称已吸收，一边又把它作为独立问题落盘。
    12. 删除主模型问题时，必须写入 unsupported_findings 或 candidate_lineage.dropped。
    13. 只有当最终 candidate_report 里确实 materialize 出新的合并后问题时，才允许写 candidate_lineage.merged；如果你只是建议“后续可以拆分 / 合并 / 改写”，但最终 candidate 仍沿用原问题骨架，就把建议写进 review_notes，不要伪造 merged。
    14. 新增候选问题时，必须写入 missed_findings 或 candidate_lineage.added；如果 missed finding 在 candidate 中仍以独立问题存在，就不能只声称“已吸收”。
    15. 每个 primary finding 都必须有去向：要么被 kept，要么被 merged，要么被 dropped；不允许静默消失。
    16. 每个 candidate finding 都必须能被 kept、added 或 merged 解释；不允许只改了候选结构却不给 lineage。
    17. 如果你无法说明 candidate 每个问题来自 primary 的哪一项，就不要重构 candidate；要么保持接近 primary 的保守版本，要么把两个 readiness 都返回 false。
    18. 如果你声称 dropped / merged / renamed 了某个问题，但最终 candidate_report 里并没有真实 materialize 出对应结构，就不要输出这条 lineage；此时应回退为 kept 或保留 primary 原骨架。
    19. candidate_lineage 顶层结构固定为 kept / added / merged / dropped 四个数组；若某一类为空，返回空数组。
    20. kept 项至少包含 candidate_issue_id 与 primary_issue_ids；若吸收了 missed finding，还要补 absorbed_missed_issue_ids。
    21. added 项至少包含 candidate_issue_id、source_missed_issue_ids、reason。
    22. merged 项至少包含 candidate_issue_id、primary_issue_ids、reason，且 candidate_issue_id 必须真实存在于最终 candidate_report 中。
    23. dropped 项至少包含 primary_issue_id、disposition、reason，可选 target_candidate_issue_id。
    24. 若你对同一个 primary finding 只是下调严重程度、把“根本冲突”改判为“表述歧义 / 术语歧义 / 规则不清”，也必须沿用同一个 issue_id，并在 review_notes 中明确写出改判原因。
    25. 如果 candidate 已达到可直接输出标准，suggestion_level 只能返回 low 或 medium，不得返回 high；若 suggestion_level 仍为 high，则两个 readiness 都必须返回 false。
    26. suggestion_level = high 的唯一含义是“候选稿仍存在实质性交付缺口”，不能只因为主模型首版质量差、还存在待产品拍板问题、或还可以继续润色，就把 suggestion_level 设为 high。
    27. 只有以下缺陷才能把 ready_for_direct_output 设为 false：候选稿仍漏掉高信号核心问题；证据不足或关键引用错误；lineage/来源不可追踪；问题命名、维度归属、严重度失真到会误导业务。
    28. 以下情况不能单独阻断直出：仍有待产品拍板的需求问题；还可以继续优化的表述；低置信度补充提醒；只是想把报告写得更漂亮。
    29. 除非共享输入中的明确证据已经证伪主模型某条高信号 finding，否则不要静默把它替换成另一组不同焦点的问题；若要降级、改判或移除，必须在 unsupported_findings、candidate_lineage.dropped 或 review_notes 中显式说明原因。
    30. kept finding 不允许擅自改成子编号 issue_id，例如把 LOGIC_01 改成 LOGIC_01_02；若只是把一个主问题拆成多条症状，必须继续保留原 issue_id，并把子症状写进同一 finding 的分点现状描述。
    31. 如果你明确判断主模型某条 finding 属于误判、已被修正、并非冲突、公式其实一致，或应该降级为可兼容实现下的歧义，就必须同步改写 candidate_report 中该 finding 的标题、现状、风险、严重度，以及 overall_evaluation、score_reason、top_blockers；不要一边说“已修正”，一边在 candidate 顶层继续保留旧 blocker。
    32. 如果你无法把上述“误判已修正/已降级”的结论同步落实到 candidate_report 全文，就把两个 readiness 都返回 false，而不是输出一份自相矛盾的 candidate。
    33. 若你下调的是 primary 的高信号核心问题，必须给出共享输入中的可兼容实现依据；若没有这个依据，就保持 primary 判断，不要做乐观改判。
    34. 高信号核心问题的降级必须比普通补漏更谨慎；不能只因为 candidate 想更简洁、更好看，就删除或弱化这些问题。
    """
).strip()


DUAL_PASS_CONSERVATIVE_CANDIDATE_RULES = dedent(
    """
    dual_pass 候选成稿约束：
    1. 候选报告优先复用主模型的 issue_id、title 和 primary_dimension，尽量保持主模型的问题结构、顺序和分组。
    2. 非必要不要拆分主模型问题，也不要把多个主模型问题重写成一个全新汇总问题。
    3. 如果只是补证据、修描述、补建议或修正标题，直接沿用主模型问题骨架，并写入 candidate_lineage.kept。
    4. 只有在确认主模型明显漏项时才允许新增 finding，并同时写入 missed_findings 或 candidate_lineage.added。
    5. 本期禁止输出非空 cross_document_issues，所有问题都必须回到 dimensions[*].findings，并沿用原维度。
    6. candidate_lineage 以 kept 作为默认主路径；added 只记录真正补漏；merged / dropped 非必要不要使用。
    7. 若你无法提供完整 lineage，就不要大幅改写 candidate 结构；优先输出接近 primary 的保守版本。
    8. 如果 candidate 不是你愿意直接给业务方看的最终稿，就先把 quality_assessment.ready_for_direct_output 设为 false，再把同样的布尔值和同样的 reason 原样复制给 candidate_readiness；不要一个 true 一个 false，也不要两个 reason 不一致。
    9. ready_for_direct_output 的判断口径是“报告是否已经结构完整、证据充分、来源可追踪、可直接给业务方阅读”，不是“文档里的产品疑问是否已经全部有最终答案”。
    10. 如果你只是识别到某个 primary 问题里混合了多个子症状，但本轮并没有真的把它拆成多个 candidate finding 并补全 lineage，就继续保留原主问题，改为在现状描述里分点展开，不要伪造 split / merged 关系。
    11. 如果你只是建议后续进一步拆分、合并或编辑，也写在 review_notes，不要把“编辑建议”伪装成已经完成的 candidate 结构调整。
    12. 在补漏时优先检查这些高频缺口：展示赔率与结算赔付口径、假数据是否参与真实计算、教程 / 引导局是否污染真实数据、时间窗口是否一致、扣款时机与本金口径、最大赔付 / 封顶、术语冲突、状态机触发顺序。
    13. 只有当两份文档明确要求两种互相排斥、无法由同一套实现同时满足的规则时，才允许使用“根本冲突”“高阻塞”“fatal”之类定性。
    14. 如果两份文档在数学结果上可以由同一实现满足，只是公式写法、术语、UI文案或解释口径容易让人误解，应优先判定为“表述歧义 / 术语歧义 / 说明不清”，不要轻易升级为“根本冲突”。
    15. 对 kept finding 的改写要保守：优先修证据、修标题、修建议、修严重程度；除非有明确事实冲突，否则不要把主模型的“可解释歧义”重写成新的“高阻塞根因”，也不要把主模型的“高阻塞根因”轻率降成低风险提示。
    16. 若主模型问题本质上属于“根本冲突 / 同一实现无法同时满足”，除非你能给出明确降级依据，否则不要把它降成中低风险或非阻塞问题。
    17. 补漏优先级固定为：先补直接影响结算结果、中奖金额、赔率口径、公式实现的问题；再补触发条件、状态机顺序、断线恢复、扣费时机的问题；再补直接影响测试验收或线上经济安全的数据源/隔离问题；最后才补通用产品缺口与低置信度提醒。
    18. 低置信度、泛化 checklist 式提醒不能单独作为 ready_for_direct_output = false 的依据；如果高优先级缺口已经足够构成主结论，不要为了“更全面”继续补很多低信号问题。
    19. 低信号 checklist 式提醒默认只允许写入 review_notes；除非共享输入里有非常具体、可定位、会直接阻塞实现或结算的证据，否则不要把它们写入 missed_findings，也不要据此新增 candidate finding。
    20. 若一个补漏点没有明确的文档、表格或图片证据，只能写入 review_notes，不能写入 missed_findings，也不能据此新增 candidate finding。
    21. 只有在两份文档明确要求互斥实现、同一套实现无法同时满足时，才允许使用“根本冲突 / 致命矛盾 / 高阻塞”这类定性。
    22. 若存在可兼容实现，只是公式写法、术语解释、样例口径或 UI 文案容易误解，应优先判为“表述歧义 / 术语歧义 / 规则说明不清”；若要把主模型的高阻塞根因降级，必须同时给出“可兼容实现的明确说明”和“为何当前仍保留或调整严重度”的依据。
    23. 若你确实把主模型的高阻塞问题降级为歧义或说明不清，必须同步重写 candidate_report 的 overall_evaluation、score_reason 与 top_blockers，使其与新结论一致，不要残留已被你否定的旧顶层结论。
    24. 若 kept 问题仍沿用主模型骨架，就必须继续使用原 issue_id；不要为了内部追踪方便，把 kept 问题重命名为 LOGIC_01_02、LOGIC_01_A 这类派生编号。
    25. 如果你只是想表达“主问题里还有 3 个子症状”，请在 current_state 中做编号分点，不要新建子 issue_id，也不要把这些子症状抬成新的 top_blockers。
    26. 如果 primary 已经识别出高信号核心问题，candidate 默认应保留该问题主轴，只允许补证据、补边界、补建议或在有充分依据时谨慎降级。
    27. candidate 不得通过删除高信号边界问题来换取更高评分；若只是想让报告更清爽，应优先做分点整理，而不是直接删减问题。
    """
).strip()


SECONDARY_PROTOCOL_PROFILES = (
    "baseline",
    "phase2",
    "phase3_v1",
    "phase3_v1_1",
    "phase3_v1_2",
    "phase3_v1_3",
)
PHASE2_PROTOCOL_REVISION = "phase2_v2_2"
PHASE3_PROTOCOL_REVISION = "phase3_v1"
PHASE3_V11_PROTOCOL_REVISION = "phase3_v1_1"
PHASE3_V12_PROTOCOL_REVISION = "phase3_v1_2"
PHASE3_V13_PROTOCOL_REVISION = "phase3_v1_3"

PHASE2_COVERAGE_AUDIT_KEYS = (
    "settlement_formula_ui_config",
    "trigger_state_termination",
    "funds_deduction_payout",
    "max_payout_economic_boundary",
    "statistics_time_window",
)

PHASE2_COVERAGE_CONTROL_KEYS = {
    "settlement_formula_ui_config": (
        "settlement_formula",
        "ui_config_mapping",
    ),
    "trigger_state_termination": (
        "trigger_entry",
        "termination_priority",
    ),
    "funds_deduction_payout": (
        "debit_timing",
        "payout_timing",
        "funds_failure_compensation",
    ),
    "max_payout_economic_boundary": (
        "relative_payout_cap",
        "pool_negative_floor",
        "single_round_payout_cap",
    ),
    "statistics_time_window": (
        "same_metric_window",
        "ui_text_window_alignment",
    ),
}


PHASE2_CONTROL_EVIDENCE_SPECS = {
    "settlement_formula": {
        "definition": "实际用于服务端结算的公式、变量、计算顺序与最终金额口径",
        "terms": ("结算公式", "奖金计算", "赔率公式", "赔付公式", "计算公式", "倍率", "赔率", "奖金"),
        "do_not_merge_with": ("ui_config_mapping", "relative_payout_cap", "single_round_payout_cap"),
    },
    "ui_config_mapping": {
        "definition": "UI、正文、配置表与实际结算字段之间的同对象映射",
        "terms": ("UI", "界面", "截图", "配置表", "后台配置", "展示", "映射", "字段", "符号"),
        "do_not_merge_with": ("settlement_formula", "ui_text_window_alignment"),
    },
    "trigger_entry": {
        "definition": "玩法、奖励、重转或特殊状态的唯一触发入口和前置条件",
        "terms": ("触发条件", "触发", "入口", "点击开始", "进入", "前置条件", "满足条件"),
        "do_not_merge_with": ("termination_priority",),
    },
    "termination_priority": {
        "definition": "状态结束条件、最大次数、提前终止以及冲突分支优先级",
        "terms": ("终止", "结束", "停止", "优先", "先后", "最大次数", "次数", "最后一步", "通关"),
        "do_not_merge_with": ("trigger_entry",),
    },
    "debit_timing": {
        "definition": "玩家本金实际冻结或扣除的产品触发节点",
        "terms": (
            "扣款",
            "扣费",
            "扣除",
            "冻结",
            "消耗对应",
            "本金",
            "下注余额",
            "余额不足",
            "收银台",
            "下注",
            "投注",
        ),
        "anchors": ("扣款", "扣费", "扣除", "冻结", "消耗对应", "本金", "下注余额", "余额不足", "收银台"),
        "do_not_merge_with": ("payout_timing", "funds_failure_compensation"),
    },
    "payout_timing": {
        "definition": "中奖金额计入玩家钱包或可用余额的产品节点",
        "terms": ("派奖", "到账", "返奖", "余额增加", "中奖金额", "奖励金额", "赢分", "结算弹窗"),
        "do_not_merge_with": ("debit_timing", "funds_failure_compensation"),
    },
    "funds_failure_compensation": {
        "definition": "资金事务失败后的回滚、补发、重试与幂等，不包含奖池经济边界",
        "terms": ("回滚", "补偿", "补发", "重试", "幂等", "异常", "断线", "重连", "失败", "中台"),
        "anchors": ("回滚", "补偿", "补发", "重试", "幂等", "断线", "重连", "中台", "扣款失败", "派奖失败"),
        "do_not_merge_with": ("debit_timing", "payout_timing", "pool_negative_floor"),
    },
    "relative_payout_cap": {
        "definition": "MAX_MUL、倍率上限、强制0倍等相对投注额的赔付边界",
        "terms": (
            "MAX_MUL",
            "倍率上限",
            "最大倍率",
            "强制0倍",
            "0 倍",
            "超过100倍",
            "100 ≤ 倍数",
            "倍数区间",
            "封顶倍率",
            "赔率上限",
            "实时赔率",
            "赔率公式",
            "对应赔率",
            "返奖倍数",
            "赔率倍数",
        ),
        "do_not_merge_with": ("pool_negative_floor", "single_round_payout_cap"),
    },
    "pool_negative_floor": {
        "definition": "奖池允许为负时的透支下限、回填边界与熔断条件",
        "terms": ("奖池", "负数", "负值", "透支", "回填", "下限", "熔断"),
        "do_not_merge_with": ("relative_payout_cap", "single_round_payout_cap", "funds_failure_compensation"),
    },
    "single_round_payout_cap": {
        "definition": "单局、单次、单用户或单选项的绝对赔付金额封顶",
        "terms": (
            "最大赔付",
            "单局赔付",
            "单次赔付",
            "赔付金额上限",
            "金额封顶",
            "MAX_PAYOUT",
            "MAX_MUL",
            "倍率上限",
            "最大倍率",
            "80%",
        ),
        "do_not_merge_with": ("relative_payout_cap", "pool_negative_floor", "settlement_formula"),
    },
    "same_metric_window": {
        "definition": "同一统计对象、同一指标、同一用途下的时间窗口一致性",
        "terms": ("时间窗口", "统计范围", "最近", "今日", "昨日", "小时", "自然日", "胜率", "平均赔率"),
        "do_not_merge_with": ("ui_text_window_alignment",),
    },
    "ui_text_window_alignment": {
        "definition": "同一统计指标在正文与UI截图中的窗口值一致性",
        "terms": ("Last 30", "Last 7", "近3日", "最近7天", "最近30天", "游戏记录", "开奖分析", "UI", "截图"),
        "do_not_merge_with": ("same_metric_window",),
    },
}


PHASE2_V22_DECISION_ORDER = (
    "1_applicability:先判断当前文档是否涉及该control；确实不涉及才可not_applicable",
    "2_source_state:逐条核对证据卡和共享正文，固定判为explicit/partial/missing/conflict之一",
    "3_counterevidence:主动查找能推翻缺失或冲突判断的原文、公共模块引用、等价上限或兼容解释",
    "4_primary_coverage:只有Primary正文实际覆盖同一control时才可same_control；一旦为same_control，status和final必须都是covered_by_primary",
    "5_status:explicit且无冲突=no_issue；partial或有兼容解释=advice_only；missing/conflict且无反证并未被Primary覆盖=confirmed_add",
    "6_materialize:confirmed_add必须生成且只生成一个绑定同audit_key+control_key的单根因finding",
)


DUAL_PASS_PHASE2_DELTA_RULES = dedent(
    """
    phase2 结构化补漏与反证协议（优先级高于此前候选稿写作规则）：
    1. 你的核心身份是“差异审查者”，不是第二份报告的自由改写者。先逐项核对 primary findings，再决定 keep / add / challenge / correct。
    2. candidate_report 必须以 primary report 为骨架；默认完整保留 primary 的 issue_id、问题顺序、维度、评分和 Top Blocker，只物化通过下述协议的增量。
    3. document_quality_score 与 score_reason 必须原样沿用 primary；任何改分意见只能写入 review_notes。
    4. 每个 missed_findings 项都必须完整包含：candidate_issue_id、audit_key、control_key、title、primary_dimension、current_state、evidence、risk、suggestion、severity、blocking、confidence、independent_root_cause、root_causes、primary_overlap_check、severity_basis、root_cause_count、fact_check。audit_key + control_key 必须唯一对应 coverage_ledger 中一个 confirmed_add control。
    5. evidence 必须写出当前输入中的完整文档名，并定位到章节、段落、表格或图片；不得只写“需求文档”“数值文档”或泛化经验。
    6. primary_overlap_check 固定为对象：nearest_primary_issue_id、overlap、reason。提出新增时 overlap 必须为 false，并说明为什么最近的 primary finding 没有覆盖该独立根因。
    7. independent_root_cause 必须只描述一个根因；root_causes 必须是只含一个元素的数组；root_cause_count 必须为 1。若标题或建议同时需要不同责任人、不同修复方案或不同验收闭环，不得强行声称为一个根因，应拆分后分别自检。
    8. high、block_dev、block_test 项必须提供 severity_basis，明确指出会造成的实现阻塞、结算错误、资损或无法验收后果；没有依据就降为 review_notes。
    9. 如果原文明示了某条规则，不得把它输出为“缺失/未明确”；只能检查该规则内部是否矛盾或与其他证据冲突。
    10. 与 primary 同根因时只能放入 candidate_lineage.kept 或 correct/challenge 建议，不得放入 missed_findings 或 candidate_lineage.added。
    11. 通用弱网、热更、教程、幂等、安全 checklist 只有在当前文档存在直接、可定位证据时才允许新增；否则只写 review_notes。
    12. 低置信度项只能进入 review_notes。允许 missed_findings 返回空数组，不要为了显得全面而凑数。
    13. 每个新增项必须填写 fact_check：claim_type 只能是 direct_conflict/value_mismatch/missing_rule/mapping_gap/boundary_gap；source_rule_presence_checked=true；compatible_interpretation_checked=true；compatible_interpretation_exists=true/false；conclusion 只能在确认成立时写 confirmed；reason 写出核验结论。missing_rule 还必须填写 searched_locations（至少一个可定位章节/段落/表格/图片）。value_mismatch 还必须填写 same_subject_and_scope=true，并证明比较的是同一对象、同一前提和同一执行阶段；不同规则有意使用不同统计口径不算冲突。
    14. candidate 的 Primary Top 3 至少保留 2 个同根因问题；不得通过删除核心问题换取更高评分或更简洁的报告。
    15. 只有两条规则在同一前提和同一执行阶段下互斥、无法由“提前结束 + 最大次数兜底”“默认值 + 边界覆盖”等组合同时满足时，fact_check 才能写 direct_conflict/confirmed。只要存在合理兼容解释，就令 compatible_interpretation_exists=true，并把该项降为 challenge/review_notes，禁止进入 missed_findings。
    16. 对“缺失”类判断，必须先核对原文是否已给出上限、阈值、默认值、公共模块引用或等价约束。不得把“已存在但适用范围不清”改写成“完全缺失”；后者只能写成 boundary_gap 或规则适用范围待澄清。
    17. 固定按以下顺序扫描 Primary 未覆盖面，并按同一顺序输出所有 confirmed 高/中置信增量：①结算、赔率、公式和UI/配置数值冲突；②触发条件、状态机终止与先后顺序；③扣款、发奖、数据隔离和经济边界；④其他可直接验收的规则缺口。不要在重复回放中随机挑选其中一部分。
    18. candidate_issue_id 使用稳定语义 ID，优先采用“维度_缺陷类型_证据主体”，不得使用本轮序号或随措辞变化的临时编号；输出按上述扫描顺序和证据在文档中的出现顺序排序。
    19. 输出前逐项自检字段完整性、证据定位、事实反证、兼容解释、Primary 重复、单根因、严重度依据；任一不满足时从 missed_findings 和 candidate_lineage.added 删除，并改写为 review_notes。
    20. 顶层 coverage_schema_version 必须为 2。必须先逐项完成 coverage_ledger 的全部固定 controls，再据此生成 missed_findings；五个 audit_key 及其 controls 的数量和顺序都不可变。每个 control 包含 status（covered_by_primary/confirmed_add/advice_only/no_issue/not_applicable）、primary_issue_ids、candidate_issue_ids、evidence_checked、reason；数组字段即使为空也必须返回 []。
    21. control 中 status=confirmed_add 的 candidate_issue_ids 必须逐一出现在 missed_findings，且对应 finding.audit_key + control_key 必须完全一致；missed_findings 中的每个 candidate_issue_id 也必须且只能回指一个 confirmed_add control。非 confirmed_add control 的 candidate_issue_ids 必须为空；每个 control 最多生成一个 candidate_issue_id。
    22. 对每个 control 都要给出明确结论，不允许只挑最显眼的一两个方向：Primary 已覆盖同一控制面才用 covered_by_primary；发现成立且通过全部自检用 confirmed_add；证据不足或存在兼容解释用 advice_only；完成核对后未发现问题用 no_issue；当前文档确实不涉及才用 not_applicable。相同共享输入与 Primary 下，除非证据判断改变，否则不得随机改变 status。
    23. funds_deduction_payout 可以对应多个独立新增，但“扣款事务”和“派奖事务”具有不同触发点、失败补偿和验收闭环，若两者都缺失必须拆成两个 candidate_issue_id，不得合成一个根因。
    24. max_payout_economic_boundary 中“奖池透支/负值下限”和“单局最大赔付封顶”是两个独立控制面；若两者都成立必须拆分，不得用一个 root_cause_count=1 的 finding 同时承载。
    25. statistics_time_window 只有在统计对象、指标、用户群、业务用途和执行阶段一致时才允许判 value_mismatch。车辆胜率/平均赔率与用户下注金额榜属于不同对象或指标，即使窗口分别为30天和今日/本周也不是冲突。
    26. 若原文已有倍率上限、MAX_MUL、强制0倍或等价封顶，默认视为已有相对赔付边界；除非能证明该边界未进入实际结算或与公式直接冲突，否则不得新增“最大赔付完全缺失”，只能写 advice_only 说明绝对金额口径可补充。
    27. not_applicable 也必须在 evidence_checked 写出实际检查过的完整文档名和“全文/具体章节”；covered_by_primary 的 candidate_issue_ids 必须为 []，即使 candidate 保留了同 ID 问题，也只能把 Primary ID 写入 primary_issue_ids。
    28. covered_by_primary 必须引用真实存在且正文明确涉及同一 control 的 Primary issue_id。例如 debit_timing 不能引用只讨论假数据隔离、零赔付选项或开奖快照的 Primary 问题；pool_negative_floor 不能引用只讨论单局封顶的 Primary 问题。无法证明同控制面时只能继续核对并选择 confirmed_add/advice_only/no_issue。
    29. 固定 controls 的含义如下：settlement_formula=实际结算公式；ui_config_mapping=UI/配置到结算的映射；trigger_entry=触发入口条件；termination_priority=终止、优先级与先后顺序；debit_timing=玩家本金扣款节点；payout_timing=派奖到账节点；funds_failure_compensation=资金失败回滚、补偿与幂等；relative_payout_cap=MAX_MUL/倍率类相对上限；pool_negative_floor=奖池透支下限；single_round_payout_cap=单局/单次金额封顶；same_metric_window=同对象同指标统计窗口；ui_text_window_alignment=同指标正文与UI窗口一致性。
    """
).strip()


DUAL_PASS_PHASE2_V22_EVIDENCE_RULES = dedent(
    """
    phase2_v2_2 固定证据卡判定规则：
    1. 你现在是“结构化补漏与反证审查者”，不是候选稿重写者。必须按 evidence_packet.cards 的固定顺序逐卡完成判定，禁止先挑选 missed_findings 再倒推 ledger。
    2. source_evidence_candidates 是确定性证据索引，不是结论，也不替代共享输入正文。每张卡必须用它定位原文，并继续检查全文中的等价规则和反证；不得只凭关键词确认问题。
    3. primary_candidates_to_verify 只是待核对候选。只有 Primary finding 的正文实际覆盖相同 control，才能写 covered_by_primary；标题都含“结算/下注/时机”不等于同一控制面。
    4. 每张卡都固定按 decision_order 执行，并在 reason 中依次写明：source_state=<explicit|partial|missing|conflict>；counterevidence=<有|无及摘要>；primary_coverage=<same_control|not_covered>；final=<status>。不得省略任一步。枚举值后不要追加括号说明；说明只放 counterevidence。primary_coverage=same_control 时 status 和 final 必须写 covered_by_primary，不能写 no_issue 或 advice_only。
    5. 资金 control 必须有明确事务动作才可判 explicit：“点击后从玩家余额扣除/冻结本金”或“点击后消耗对应货币”可覆盖 debit_timing，“结算后玩家余额增加/钱包入账”可覆盖 payout_timing；仅有点击下注、选择档位、展示下注数值、唤起收银台、中奖弹窗或返奖数值展示都不足以证明资金事务节点。
    6. 原文引用既有中台、公共模块或统一处理流程时，source_state 至少为 partial；没有证据证明公共流程缺失或冲突时，只能 advice_only，不得 confirmed_add 为“完全缺失”。
    7. relative_payout_cap、pool_negative_floor、single_round_payout_cap 必须独立判定。已有 MAX_MUL、倍率上限或强制0倍时，不得仅因未出现 MAX_PAYOUT 字样就确认单局绝对金额封顶缺失；必须证明现有边界无法形成有限赔付或不参与实际结算。
    8. control 的 title、independent_root_cause、current_state、risk 和 suggestion 都不得越过 do_not_merge_with。debit_timing 不承载幂等/断线恢复，funds_failure_compensation 不承载奖池下限/熔断，single_round_payout_cap 不承载公式或数值表错误。
    9. 同一 evidence_packet_id 下，证据未变化时必须得到同一 source_state 和 status。输出前重新遍历12张卡，确认没有因篇幅或输出结构随机漏掉 confirmed_add。
    10. `[001]`、TBD、待配置、待填写、示例值以及概率/倍率/阈值/上下限等具体配置值未填，属于正常配置流程。若证据只证明“具体值尚未填写”，对应 control 只能是 no_issue（Primary 已覆盖同一实际问题时仍按 covered_by_primary），不得写 advice_only、confirmed_add 或 review_notes；只有明确的规则/公式冲突、结算矛盾、除零或死锁才按实际冲突处理。
    """
).strip()


DUAL_PASS_PHASE2_V22_DELTA_ONLY_RULES = dedent(
    """
    phase2_v2_2 delta-only 协议（覆盖此前所有 candidate 写作要求）：
    1. 你只输出结构化复核差量，不生成 candidate_report，不生成 candidate_lineage，也不重写 Primary 的评分、Top Blocker 或正文。最终 Candidate 由系统基于 Primary 与通过准入的 missed_findings 确定性生成。
    2. 唯一主任务是按固定顺序完成12个 control，并输出 coverage_ledger、missed_findings、unsupported_findings、merge_recommendations、quality_assessment 和 review_notes。
    3. 必须先完整填完12个 control，再一次性输出所有 confirmed_add；不得因为候选稿篇幅、报告结构或只挑重点而省略已确认问题。
    4. debit_timing 只有在原文明确说明从玩家余额/钱包扣除或冻结本金的事务节点时才算 explicit；仅写“选择档位、点击下注、下注对应数值、唤起收银台”不等于已定义余额扣款时机。
    5. payout_timing 只有在原文明确说明玩家余额/钱包入账或增加的节点时才算 explicit；仅展示中奖弹窗、返奖数值或排行榜返奖不等于已定义钱包到账时机。
    6. funds_failure_compensation 在存在真实支付、钱包扣款或提现事务时，必须核对失败回滚、补发、重试与幂等；只有原文明示平台/中台统一承接且无玩法特殊冲突时才能 advice_only。
    7. covered_by_primary 必须逐字核对 Primary finding 是否涉及相同 control。中奖金额格式、零赔付选项、开奖兜底或公式错误不得覆盖 payout_timing / single_round_payout_cap 等不同控制面。
    8. 已有 MAX_MUL、倍率上限或等价有限边界时，single_round_payout_cap 不得仅凭“可能配置极高下注额”确认缺失；没有直接证据证明相对边界失效时只能 advice_only。
    9. 每个 control 的 reason 固定写为 source_state=...; counterevidence=...; primary_coverage=...; final=...，并保证 primary_issue_ids、candidate_issue_ids、evidence_checked 始终为数组。source_state、primary_coverage 和 final 的枚举值后不得追加括号说明；primary_coverage=same_control 时 status=covered_by_primary 且 final=covered_by_primary。
    10. 输出前按原顺序重新遍历12个 control，校验 audit_key、control_key、字段、证据、映射和 missed_findings 双向关系；不得改变固定 JSON 包装形式。
    11. 每个 missed_findings 必须完整包含 candidate_issue_id、audit_key、control_key、title、primary_dimension、current_state、evidence、risk、suggestion、severity、blocking、confidence、independent_root_cause、root_causes、primary_overlap_check、severity_basis、root_cause_count、fact_check。
    12. evidence 必须使用完整文档名并定位章节、段落、表格或图片；independent_root_cause 只允许一个根因，root_causes 只能有一个元素，root_cause_count 必须为1。
    13. primary_overlap_check 固定包含 nearest_primary_issue_id、overlap、reason；confirmed_add 的 overlap 必须为 false，并说明最近 Primary finding 未覆盖相同根因。
    14. fact_check.claim_type 只能是 direct_conflict/value_mismatch/missing_rule/mapping_gap/boundary_gap；必须完成原文规则、兼容解释和 searched_locations 核验，只有 conclusion=confirmed 才能进入 missed_findings。
    15. high、block_dev、block_test 必须给出 severity_basis；低置信度、存在合理兼容解释、证据不能定位或与 Primary 同根因的项目只能写入 review_notes。
    16. confirmed_add 的 candidate_issue_ids 必须与 missed_findings 按 candidate_issue_id + audit_key + control_key 双向一一对应；非 confirmed_add 的 candidate_issue_ids 必须为 []，每个 control 最多一个新增。
    17. 扣款、派奖、资金失败补偿、奖池负值下限、单局金额封顶必须分别作为独立 control 和独立根因，不得混写；统计冲突必须证明是同对象、同指标、同用途和同执行阶段。
    18. not_applicable 也必须在 evidence_checked 写出实际检查的完整文档名与全文/章节范围；允许 missed_findings 为空，不得为了数量凑项。
    """
).strip()


DUAL_PASS_PHASE2_COMPACT_BASELINE = dedent(
    """
    phase2_v2_2 复核基线：
    1. 只基于本次共享输入和冻结 Primary，按十二个固定 control 逐项抽取事实、反证与 Primary 覆盖关系。
    2. 没有问题数量目标；允许零新增，禁止为了全面感、维度覆盖或固定数量生成低信号 finding。
    3. 通用平台能力、经验 checklist 和当前文档未出现的规则只能写 review_notes，不得据此 confirmed_add。
    4. 每个新增必须有完整文档名与章节/段落/表格/图片定位，并形成现状、证据、风险、建议的单根因闭环。
    5. 相同根因只输出一次；置信度表示证据强度，严重度和 blocking 只由实现、结算、测试或资损影响决定。
    6. 先完成全部 control 的事实判断，再生成 missed_findings；不得先挑结论、不得评分、不得重写报告。
    7. 占位符、待配置项、示例值或具体配置数值未填不是风险，不得形成新增、建议、质量备注或评分依据；只审查文档直接证明的实际规则冲突。
    """
).strip()


DUAL_PASS_PHASE3_V1_BASELINE = dedent(
    """
    phase3_v1 质疑与影子纠错基线：
    1. 只基于共享输入和冻结 Primary；不得引入外部经验补漏，不得重新生成完整报告。
    2. challenge 只质疑 Primary 已存在 finding 的证据、定性、重复性或原子性；每项必须绑定真实 target_issue_id。
    3. 相同决策对象、根因、修复动作和验收闭环的重复表述可以建议合并证据；对象、配置字段、责任人、修复动作或验收闭环任一不同，必须建议拆分。
    4. multiroot challenge 必须给出至少两个 proposed_split，每个拆分项只处理一个 decision_object，并具备独立证据、风险、建议、责任人与验收标准。
    5. correct 只生成 shadow 建议；系统会补齐真实 before，并保存 after_preview，但不会写回 Primary、Pipeline 或 Candidate。
    6. 禁止输出或建议修改 overall_evaluation、document_quality_score、score_reason、top_blockers、severity、blocking。
    7. 允许零 challenge、零 correct；没有可定位证据时不要输出。
    8. challenge/correct 的 ID、目标、证据、动作和理由必须稳定、可追踪、可复跑和可人工判断。
    """
).strip()


DUAL_PASS_PHASE3_V1_SCHEMA = dedent(
    """
    只返回一个合法 JSON 对象，不要使用 Markdown 代码块。顶层只允许 challenge_findings、correction_shadows、review_notes：
    {
      "challenge_findings": [
        {
          "challenge_id": "CH-稳定编号",
          "target_issue_id": "Primary中真实存在的issue_id",
          "challenge_type": "unsupported|overstated|duplicate|multiroot|compatible_interpretation|evidence_mismatch",
          "challenged_claim": "被质疑的具体判断",
          "evidence": "完整文档名 / 章节、段落、表格或图片定位",
          "counterevidence": "可选反证；没有则空字符串",
          "rationale": "质疑成立的原因",
          "recommended_action": "keep|split|clarify|demote|drop|merge_evidence",
          "proposed_split": [
            {
              "title": "单一问题标题",
              "decision_object": "稳定且唯一的决策对象键",
              "current_state": "单一对象现状",
              "evidence": "完整文档名 / 可定位位置",
              "risk": "该对象的独立风险",
              "suggestion": "只关闭该对象的修改建议",
              "planner_role": "唯一主要责任角色",
              "acceptance_criteria": "独立可关闭的验收标准"
            }
          ]
        }
      ],
      "correction_shadows": [
        {
          "correction_id": "CR-稳定编号",
          "challenge_id": "已输出且同目标的challenge_id",
          "target_issue_id": "Primary中真实存在的issue_id",
          "correction_type": "split|clarify|narrow_claim|evidence_fix|wording",
          "evidence": "完整文档名 / 章节、段落、表格或图片定位",
          "rationale": "为什么该影子修正更准确",
          "proposed_changes": {
            "title": "可选",
            "current_state": "可选",
            "evidence": "可选",
            "risk": "可选",
            "suggestion": "可选",
            "planner_role": "可选",
            "confidence": "可选",
            "acceptance_criteria": "可选"
          },
          "replacement_findings": []
        }
      ],
      "review_notes": []
    }
    correction_type=split 时必须返回至少两个 replacement_findings，结构与 proposed_split 单项完全相同，并把 proposed_changes 设为 {}。
    非 split correction 必须返回非空 proposed_changes，并把 replacement_findings 设为 []。
    不得返回 candidate_report、candidate_lineage、candidate_readiness、quality_assessment、coverage_ledger、missed_findings 或任何其他顶层字段。
    proposed_split、replacement_findings、proposed_changes 的任意层级都不得出现 severity、blocking、overall_evaluation、document_quality_score、score_reason、top_blockers。
    """
).strip()


DUAL_PASS_PHASE3_V11_BASELINE = dedent(
    f"""
    {DUAL_PASS_PHASE3_V1_BASELINE}

    phase3_v1_1 Correction 处置收敛规则（Challenge 规则保持 phase3_v1 不变）：
    1. 先完成 challenge，再决定是否存在安全的 correction；不要为了每条 challenge 都有 after 而强行改写。允许 correction_shadows 为空。
    2. correction_disposition 必须先于正文改写确定，只能是 drop、downgrade、clarify、narrow、split、abstain。
    3. recommended_action=drop 只能对应 drop/abstain；demote 只能对应 downgrade/drop/abstain；split 只能对应 split/abstain；keep 只能对应 abstain。处置与 Challenge 不一致时不要输出修正。
    4. compatible_interpretation 已证明原判断不成立且没有剩余问题时必须 drop；禁止把已闭环、已解释清楚或分支本来不同的问题重新包装成“轻微歧义”。
    5. downgrade 必须重写 risk，使影响与降级结论一致；不得只改标题或 current_state 后继续沿用高风险措辞。severity/blocking 仍是保护字段，只能令 protected_fields_need_human_review=true，禁止输出具体修改值。
    6. drop 只表达“人工确认后移除该 finding”，proposed_changes 必须为 {{}}，replacement_findings 必须为 []，不得留下新的 after finding。
    7. clarify/narrow 只有在 residual_issue_exists=true 且 residual_issue 能明确描述一个仍成立、可定位、可关闭的问题时才允许；否则 drop 或 abstain。
    8. 竞品截图、参考图、示例图不能推导当前产品真实存在机器人、降级策略、资源分期或其他机制；source_provenance=reference_or_competitor/unknown 时只允许 drop、downgrade 或 abstain。
    9. abstain 表示证据不足以生成安全修正；proposed_changes={{}}、replacement_findings=[]，系统只保留 Challenge，不进入人工 Correction 队列。
    10. semantic_checks 四个布尔值必须基于证据真实填写，不得为了通过协议而倒推答案。
    """
).strip()


DUAL_PASS_PHASE3_V11_SCHEMA = dedent(
    """
    只返回一个合法 JSON 对象，不要使用 Markdown 代码块。顶层仍只允许 challenge_findings、correction_shadows、review_notes。
    challenge_findings 的字段、顺序与 phase3_v1 完全相同；为避免引用歧义，完整结构与 correction_shadows 一并列出：
    {
      "challenge_findings": [
        {
          "challenge_id": "CH-稳定编号",
          "target_issue_id": "Primary中真实存在的issue_id",
          "challenge_type": "unsupported|overstated|duplicate|multiroot|compatible_interpretation|evidence_mismatch",
          "challenged_claim": "被质疑的具体判断",
          "evidence": "完整文档名 / 章节、段落、表格或图片定位",
          "counterevidence": "可选反证；没有则空字符串",
          "rationale": "质疑成立的原因",
          "recommended_action": "keep|split|clarify|demote|drop|merge_evidence",
          "proposed_split": [
            {
              "title": "单一问题标题",
              "decision_object": "稳定且唯一的决策对象键",
              "current_state": "单一对象现状",
              "evidence": "完整文档名 / 可定位位置",
              "risk": "该对象的独立风险",
              "suggestion": "只关闭该对象的修改建议",
              "planner_role": "唯一主要责任角色",
              "acceptance_criteria": "独立可关闭的验收标准"
            }
          ]
        }
      ],
      "correction_shadows": [
        {
          "correction_id": "CR-稳定编号",
          "challenge_id": "已输出且同目标的challenge_id",
          "target_issue_id": "Primary中真实存在的issue_id",
          "correction_disposition": "drop|downgrade|clarify|narrow|split|abstain",
          "source_provenance": "requirement_text|numeric_config|product_screenshot|reference_or_competitor|mixed|unknown",
          "evidence": "完整文档名 / 章节、段落、表格或图片定位",
          "rationale": "为什么该处置与 Challenge 事实结论一致",
          "residual_issue": "仍成立的单一剩余问题；drop/abstain 时必须为空字符串",
          "semantic_checks": {
            "compatible_interpretation_exists": false,
            "original_claim_still_valid": true,
            "residual_issue_exists": true,
            "protected_fields_need_human_review": false
          },
          "proposed_changes": {
            "title": "可选",
            "current_state": "可选",
            "evidence": "可选",
            "risk": "可选",
            "suggestion": "可选",
            "planner_role": "可选",
            "confidence": "可选",
            "acceptance_criteria": "可选"
          },
          "replacement_findings": []
        }
      ],
      "review_notes": []
    }
    drop/abstain：proposed_changes={}、replacement_findings=[]、residual_issue=""、residual_issue_exists=false。
    downgrade：proposed_changes 至少包含重写后的 risk，protected_fields_need_human_review=true，不得出现 severity/blocking。
    clarify/narrow：proposed_changes 非空，residual_issue 非空，residual_issue_exists=true。
    split：replacement_findings 至少两个且满足 phase3_v1 原子拆分字段，proposed_changes={}，residual_issue_exists=true。
    每个 correction 只允许示例中列出的字段；不得返回 correction_type 或其他兼容旧字段。
    任意层级都不得出现 severity、blocking、overall_evaluation、document_quality_score、score_reason、top_blockers。
    """
).strip()


DUAL_PASS_PHASE3_V12_BASELINE = dedent(
    f"""
    {DUAL_PASS_PHASE3_V11_BASELINE}

    phase3_v1_2 固定目标覆盖与稳定性规则：
    1. 必须严格按系统提供的 target inventory 顺序逐项检查每个 Primary finding，不得只挑本轮最显眼的问题。
    2. target_coverage_ledger 必须与 inventory 数量、target_order、target_issue_id 完全一致，每个目标恰好一行。
    3. decision 只能是 pass、challenge、abstain：pass 表示证据支持原 finding；challenge 表示存在可定位反证并输出唯一匹配 challenge；abstain 表示证据不足，既不确认也不质疑。
    4. decision=challenge 时 challenge_type、recommended_action 必须与 challenge_findings 中同 target 的唯一对象完全一致；pass/abstain 时两字段必须为空字符串，且不得输出该 target 的 challenge/correction。
    5. evidence_checked 必须写出实际核对的完整文档名和章节、段落、表格或图片；rationale 必须说明为什么选择当前 decision。
    6. challenge_id 固定使用 CH-<target_issue_id>，correction_id 固定使用 CR-<target_issue_id>；同一冻结输入复跑不得改用临时序号。
    7. 先完成全部 ledger，再从 decision=challenge 的目标生成 challenge，最后才决定是否生成 correction；不得从 correction 反推 ledger。
    8. 模型仍不得输出评分、评分理由、Top 3、severity 或 blocking。只有 correction 通过机器准入和人工确认后，系统才按最终 findings 确定性重算这些字段。
    """
).strip()


DUAL_PASS_PHASE3_V12_SCHEMA = dedent(
    """
    只返回一个合法 JSON 对象，不要使用 Markdown 代码块。顶层只允许 target_coverage_ledger、challenge_findings、correction_shadows、review_notes：
    {
      "target_coverage_ledger": [
        {
          "target_issue_id": "与固定inventory当前行完全一致",
          "target_order": 1,
          "decision": "pass|challenge|abstain",
          "challenge_type": "challenge时填写；否则空字符串",
          "recommended_action": "challenge时填写；否则空字符串",
          "evidence_checked": "完整文档名 / 章节、段落、表格或图片定位",
          "rationale": "逐项核验结论"
        }
      ],
      "challenge_findings": [
        {
          "challenge_id": "CH-<target_issue_id>",
          "target_issue_id": "Primary中真实存在且ledger decision=challenge的issue_id",
          "challenge_type": "unsupported|overstated|duplicate|multiroot|compatible_interpretation|evidence_mismatch",
          "challenged_claim": "被质疑的具体判断",
          "evidence": "完整文档名 / 可定位位置",
          "counterevidence": "可选反证；没有则空字符串",
          "rationale": "质疑成立的原因",
          "recommended_action": "keep|split|clarify|demote|drop|merge_evidence",
          "proposed_split": []
        }
      ],
      "correction_shadows": [
        {
          "correction_id": "CR-<target_issue_id>",
          "challenge_id": "同目标challenge_id",
          "target_issue_id": "同目标issue_id",
          "correction_disposition": "drop|downgrade|clarify|narrow|split|abstain",
          "source_provenance": "requirement_text|numeric_config|product_screenshot|reference_or_competitor|mixed|unknown",
          "evidence": "完整文档名 / 可定位位置",
          "rationale": "处置依据",
          "residual_issue": "drop/abstain为空；其他处置写单一剩余问题",
          "semantic_checks": {
            "compatible_interpretation_exists": false,
            "original_claim_still_valid": true,
            "residual_issue_exists": true,
            "protected_fields_need_human_review": false
          },
          "proposed_changes": {},
          "replacement_findings": []
        }
      ],
      "review_notes": []
    }
    multiroot/split 的 proposed_split 与 replacement_findings 每项仍必须包含 title、decision_object、current_state、evidence、risk、suggestion、planner_role、acceptance_criteria。
    drop/abstain：proposed_changes={}、replacement_findings=[]、residual_issue=""、residual_issue_exists=false。
    downgrade：proposed_changes 至少重写 risk，protected_fields_need_human_review=true；不得输出具体 severity/blocking。
    clarify/narrow：proposed_changes 非空，residual_issue 非空，residual_issue_exists=true。
    split：replacement_findings 至少两个，proposed_changes={}，residual_issue_exists=true。
    任意层级不得出现 overall_evaluation、document_quality_score、score_reason、top_blockers、severity、blocking。
    """
).strip()


DUAL_PASS_PHASE3_V13_BASELINE = dedent(
    f"""
    {DUAL_PASS_PHASE3_V12_BASELINE}

    phase3_v1_3 Challenge 稳定化规则（V1.2 Correction、人工应用与评分规则保持冻结）：
    1. 每个 target 必须在 challenge_checks 中依次判断 duplicate、multiroot、evidence_mismatch、unsupported、compatible_interpretation、overstated 六类信号；状态只能是 confirmed、rejected、uncertain。
    2. 六类检查必须全部填写，不得在看到一个显眼问题后跳过其他类型，也不得根据是否想输出 correction 倒推状态。
    3. 最终 decision 由固定矩阵决定：至少一项 confirmed 时必须 challenge；没有 confirmed 但至少一项 uncertain 时必须 abstain；全部 rejected 时必须 pass。
    4. 多项 confirmed 时必须按固定优先级选择唯一 challenge_type：duplicate > multiroot > evidence_mismatch > unsupported > compatible_interpretation > overstated。
    5. recommended_action 由 challenge_type 固定映射，不允许自由选择：duplicate=merge_evidence；multiroot=split；evidence_mismatch=clarify；unsupported=drop；compatible_interpretation=drop；overstated=demote。
    6. challenge_checks 是对同一份冻结证据的穷举事实检查，不是置信度评分。无法确认也无法排除时填 uncertain，禁止为了减少输出而填 rejected。
    7. challenge/correction 的目标、证据与准入规则沿用 V1.2；模型仍不得修改或输出评分、评分理由、Top 3、severity、blocking。
    """
).strip()


DUAL_PASS_PHASE3_V13_SCHEMA = dedent(
    """
    只返回一个合法 JSON 对象，不要使用 Markdown 代码块。顶层只允许 target_coverage_ledger、challenge_findings、correction_shadows、review_notes：
    {
      "target_coverage_ledger": [
        {
          "target_issue_id": "与固定inventory当前行完全一致",
          "target_order": 1,
          "decision": "pass|challenge|abstain",
          "challenge_type": "由challenge_checks和固定优先级确定；非challenge时为空字符串",
          "recommended_action": "由challenge_type固定映射；非challenge时为空字符串",
          "challenge_checks": {
            "duplicate": "confirmed|rejected|uncertain",
            "multiroot": "confirmed|rejected|uncertain",
            "evidence_mismatch": "confirmed|rejected|uncertain",
            "unsupported": "confirmed|rejected|uncertain",
            "compatible_interpretation": "confirmed|rejected|uncertain",
            "overstated": "confirmed|rejected|uncertain"
          },
          "evidence_checked": "完整文档名 / 章节、段落、表格或图片定位",
          "rationale": "说明六类检查结果和固定矩阵如何得到最终decision"
        }
      ],
      "challenge_findings": [
        {
          "challenge_id": "CH-<target_issue_id>",
          "target_issue_id": "ledger decision=challenge的真实issue_id",
          "challenge_type": "固定优先级选出的唯一类型",
          "challenged_claim": "被质疑的具体判断",
          "evidence": "完整文档名 / 可定位位置",
          "counterevidence": "可选反证；没有则空字符串",
          "rationale": "质疑成立的原因",
          "recommended_action": "固定映射得到的动作",
          "proposed_split": []
        }
      ],
      "correction_shadows": [
        {
          "correction_id": "CR-<target_issue_id>",
          "challenge_id": "同目标challenge_id",
          "target_issue_id": "同目标issue_id",
          "correction_disposition": "drop|downgrade|clarify|narrow|split|abstain",
          "source_provenance": "requirement_text|numeric_config|product_screenshot|reference_or_competitor|mixed|unknown",
          "evidence": "完整文档名 / 可定位位置",
          "rationale": "处置依据",
          "residual_issue": "drop/abstain为空；其他处置写单一剩余问题",
          "semantic_checks": {
            "compatible_interpretation_exists": false,
            "original_claim_still_valid": true,
            "residual_issue_exists": true,
            "protected_fields_need_human_review": false
          },
          "proposed_changes": {},
          "replacement_findings": []
        }
      ],
      "review_notes": []
    }
    multiroot/split 的 proposed_split 与 replacement_findings 每项仍必须包含 title、decision_object、current_state、evidence、risk、suggestion、planner_role、acceptance_criteria。
    drop/abstain：proposed_changes={}、replacement_findings=[]、residual_issue=""、residual_issue_exists=false。
    downgrade：proposed_changes 至少重写 risk，protected_fields_need_human_review=true；不得输出具体 severity/blocking。
    clarify/narrow：proposed_changes 非空，residual_issue 非空，residual_issue_exists=true。
    split：replacement_findings 至少两个，proposed_changes={}，residual_issue_exists=true。
    任意层级不得出现 overall_evaluation、document_quality_score、score_reason、top_blockers、severity、blocking。
    """
).strip()


DUAL_PASS_PHASE2_DELTA_ONLY_SCHEMA = dedent(
    """
    只返回一个 JSON 对象，不要 Markdown 代码块，不要解释文字。顶层只允许：
    {
      "quality_assessment": {
        "summary": "对Primary覆盖质量的简述",
        "strengths": ["..."],
        "issues": ["..."],
        "suggestion_level": "low|medium|high",
        "ready_for_direct_output": false,
        "reason": "仅评价Primary，不评价系统生成的Candidate"
      },
      "coverage_schema_version": 2,
      "coverage_ledger": [],
      "missed_findings": [],
      "unsupported_findings": [],
      "merge_recommendations": [],
      "review_notes": []
    }
    不得返回 candidate_report、candidate_lineage 或 candidate_readiness；这些字段由系统确定性生成。
    """
).strip()


DUAL_PASS_PHASE2_MISSED_FINDING_SCHEMA = dedent(
    """
    phase2_v2_2 missed_findings 唯一对象模板（字段名和 JSON 类型必须原样保持，替换示例值；没有合格新增时返回 []）：
    {
      "candidate_issue_id": "稳定语义ID",
      "audit_key": "五个固定audit_key之一",
      "control_key": "十二个固定control_key之一",
      "title": "单一根因标题",
      "primary_dimension": "六个原始维度之一",
      "current_state": "当前文档中的具体缺口",
      "evidence": "完整文档名 / 章节、段落、表格或图片定位",
      "risk": "具体实现、结算、测试或资损后果",
      "suggestion": "可执行且可验收的修订方案",
      "severity": "high|medium|low",
      "blocking": "block_dev|block_test|advisory",
      "confidence": "high|medium",
      "independent_root_cause": "唯一独立根因",
      "root_causes": ["与independent_root_cause一致的唯一根因"],
      "root_cause_count": 1,
      "primary_overlap_check": {
        "nearest_primary_issue_id": "真实存在的最近Primary issue_id；若Primary为空则写NONE",
        "overlap": false,
        "reason": "为什么最近Primary问题没有覆盖同一根因"
      },
      "severity_basis": "high/block_dev/block_test的事实依据；其他级别也返回说明字符串",
      "fact_check": {
        "claim_type": "direct_conflict|value_mismatch|missing_rule|mapping_gap|boundary_gap",
        "source_rule_presence_checked": true,
        "compatible_interpretation_checked": true,
        "compatible_interpretation_exists": false,
        "conclusion": "confirmed",
        "reason": "事实核验与反证结论",
        "searched_locations": ["完整文档名 / 已检查章节、段落、表格、图片或全文"],
        "same_subject_and_scope": false
      }
    }
    searched_locations 永远是字符串数组，不得返回单个字符串；value_mismatch 时 same_subject_and_scope 必须为 true，其他 claim_type 保持 false。所有布尔值必须是 JSON true/false，不得用字符串。
    """
).strip()


DUAL_PASS_PHASE2_COVERAGE_TEMPLATE = dedent(
    """
    phase2 coverage_ledger V2 固定 JSON 骨架（audit_key、control_key、数量和顺序必须原样保留，只替换 status、ID、证据与理由）：
    "coverage_schema_version": 2,
    "coverage_ledger": [
      {"audit_key":"settlement_formula_ui_config","controls":[
        {"control_key":"settlement_formula","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"},
        {"control_key":"ui_config_mapping","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"}
      ]},
      {"audit_key":"trigger_state_termination","controls":[
        {"control_key":"trigger_entry","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"},
        {"control_key":"termination_priority","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"}
      ]},
      {"audit_key":"funds_deduction_payout","controls":[
        {"control_key":"debit_timing","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"},
        {"control_key":"payout_timing","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"},
        {"control_key":"funds_failure_compensation","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"}
      ]},
      {"audit_key":"max_payout_economic_boundary","controls":[
        {"control_key":"relative_payout_cap","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"},
        {"control_key":"pool_negative_floor","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"},
        {"control_key":"single_round_payout_cap","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"}
      ]},
      {"audit_key":"statistics_time_window","controls":[
        {"control_key":"same_metric_window","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"},
        {"control_key":"ui_text_window_alignment","status":"no_issue","primary_issue_ids":[],"candidate_issue_ids":[],"evidence_checked":["完整文档名 / 定位"],"reason":"核对结论"}
      ]}
    ]
    先填完全部12个 control 再生成 missed_findings；不得新增、删除、改名或换序，不得把示例中的 no_issue 当作默认答案。not_applicable 也不得把 evidence_checked 留空；非 confirmed_add 的 candidate_issue_ids 永远为 []。
    """
).strip()


def normalize_secondary_protocol_profile(value: str | None) -> str:
    profile = str(value or "phase2").strip().lower()
    if profile not in SECONDARY_PROTOCOL_PROFILES:
        raise ValueError(
            f"Unsupported Secondary protocol profile: {value!r}. "
            f"Expected one of: {', '.join(SECONDARY_PROTOCOL_PROFILES)}."
        )
    return profile


def _phase2_context_evidence_candidates(document_context: str) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    document_name = "当前输入"
    section_name = "全文"
    for index, raw_line in enumerate(str(document_context or "").splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# 文档："):
            document_name = line.removeprefix("# 文档：").split("（类型：", 1)[0].strip() or document_name
            section_name = "全文"
            continue
        if line.startswith("## ") or line.startswith("### "):
            section_name = line.lstrip("# ").strip() or section_name
            continue
        if line.startswith("[段落"):
            locator = line.split("]", 1)[0] + "]"
        elif line.startswith("- 图片"):
            locator = line.split("：", 1)[0].lstrip("- ").strip()
        else:
            locator = section_name
        compact_line = " ".join(line.split())
        if len(compact_line) > 280:
            compact_line = compact_line[:277] + "..."
        candidates.append((index, f"{document_name} / {locator}: {compact_line}"))
    return candidates


def _phase2_rank_evidence(
    candidates: list[tuple[int, str]],
    terms: tuple[str, ...],
    *,
    anchor_terms: tuple[str, ...] = (),
    limit: int = 2,
) -> list[str]:
    ranked: list[tuple[int, int, str]] = []
    normalized_terms = [(term, term.lower()) for term in terms]
    for index, candidate in candidates:
        lowered = candidate.lower()
        if anchor_terms and not any(str(anchor).lower() in lowered for anchor in anchor_terms):
            continue
        hits = [original for original, lowered_term in normalized_terms if lowered_term in lowered]
        if not hits:
            continue
        score = sum(max(1, len(hit)) for hit in hits)
        ranked.append((-score, index, candidate))
    selected = sorted(ranked)[:limit]
    return [candidate for _, _, candidate in sorted(selected, key=lambda item: item[1])]


def _phase2_primary_findings(primary_report: dict[str, object]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for dimension in primary_report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        for finding in dimension.get("findings") or []:
            if isinstance(finding, dict):
                key = (
                    str(finding.get("issue_id") or "").strip(),
                    str(finding.get("title") or finding.get("canonical_title") or "").strip(),
                )
                if key not in seen:
                    seen.add(key)
                    findings.append(finding)
    for finding in primary_report.get("cross_document_issues") or []:
        if not isinstance(finding, dict):
            continue
        key = (
            str(finding.get("issue_id") or "").strip(),
            str(finding.get("title") or finding.get("canonical_title") or "").strip(),
        )
        if key not in seen:
            seen.add(key)
            findings.append(finding)
    return findings


def _phase2_primary_candidates(
    findings: list[dict[str, object]],
    terms: tuple[str, ...],
    *,
    limit: int = 2,
) -> list[dict[str, str]]:
    ranked: list[tuple[int, int, dict[str, str]]] = []
    normalized_terms = [(term, term.lower()) for term in terms]
    for index, finding in enumerate(findings):
        text = "\n".join(
            str(finding.get(field) or "")
            for field in ("title", "canonical_title", "current_state", "risk", "suggestion")
        ).lower()
        hits = [original for original, lowered_term in normalized_terms if lowered_term in text]
        if not hits:
            continue
        ranked.append(
            (
                -sum(max(1, len(hit)) for hit in hits),
                index,
                {
                    "issue_id": str(finding.get("issue_id") or "").strip(),
                    "title": str(finding.get("title") or finding.get("canonical_title") or "").strip(),
                },
            )
        )
    return [candidate for _, _, candidate in sorted(ranked)[:limit]]


def build_phase2_control_evidence_packet(
    shared_input: dict[str, object],
    primary_report: dict[str, object],
    protocol_revision: str = PHASE2_PROTOCOL_REVISION,
) -> dict[str, object]:
    """Build a compact deterministic evidence index for all fixed phase2 controls."""
    context_candidates = _phase2_context_evidence_candidates(
        str(shared_input.get("document_context") or "")
    )
    primary_findings = _phase2_primary_findings(primary_report)
    cards: list[dict[str, object]] = []
    for audit_key in PHASE2_COVERAGE_AUDIT_KEYS:
        for control_key in PHASE2_COVERAGE_CONTROL_KEYS[audit_key]:
            spec = PHASE2_CONTROL_EVIDENCE_SPECS[control_key]
            terms = tuple(str(term) for term in spec["terms"])
            cards.append(
                {
                    "audit_key": audit_key,
                    "control_key": control_key,
                    "definition": str(spec["definition"]),
                    "source_evidence_candidates": _phase2_rank_evidence(
                        context_candidates,
                        terms,
                        anchor_terms=tuple(str(term) for term in spec.get("anchors", ())),
                    ),
                    "primary_candidates_to_verify": _phase2_primary_candidates(
                        primary_findings,
                        terms,
                    ),
                    "do_not_merge_with": list(spec["do_not_merge_with"]),
                }
            )
    packet_body: dict[str, object] = {
        "protocol_revision": str(protocol_revision or PHASE2_PROTOCOL_REVISION),
        "decision_order": list(PHASE2_V22_DECISION_ORDER),
        "cards": cards,
    }
    canonical = json.dumps(packet_body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "evidence_packet_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        **packet_body,
    }


def build_shared_review_input(documents: list[ParsedDocument], max_context_chars: int) -> dict[str, object]:
    context = build_document_context(documents)
    context_truncated = False
    if len(context) > max_context_chars:
        context = context[:max_context_chars] + "\n\n[上下文因长度限制被截断，请优先基于已给证据分析，并在缺失信息中提示可能遗漏。]"
        context_truncated = True
    return {
        "document_labels": [f"{doc.name} ({doc.kind})" for doc in documents],
        "collection_summary": build_collection_summary(documents),
        "document_context": context,
        "context_truncated": context_truncated,
        "public_rules": {
            "review_rules": REVIEW_RULES,
            "baseline_review_principles": BASELINE_REVIEW_PRINCIPLES,
            "placeholder_configuration_policy": PLACEHOLDER_CONFIGURATION_POLICY,
            "special_checklist": SPECIAL_CHECKLIST,
            "stability_protocol": STABILITY_PROTOCOL,
            "fact_first_protocol": FACT_FIRST_PROTOCOL,
            "score_rubric": SCORE_RUBRIC,
            "output_quality_bar": OUTPUT_QUALITY_BAR,
            "root_cause_prompt_rules": ROOT_CAUSE_PROMPT_RULES,
        },
    }


def _build_current_document_constraints(document_labels: list[str]) -> str:
    return "\n".join(
        [
            "当前文档约束：",
            f"- 本次输入文档：{', '.join(document_labels) or '无'}",
            "- 只能基于本次输入文档内容输出，不得引用此前项目、历史案例或其他游戏需求。",
            "- 如果当前上下文里没有某个玩法名词、角色名、旧项目名或规则，不要主动补写到报告里。",
            "- 只有在本次确实输入了两份及以上文档，且证据同时来自不同文档时，才输出跨文档一致性问题。",
            "- 如果证据里不能明确标出至少两个当前输入文档名，就不要输出 cross_document_issues。",
            "- 单文档场景不要假设一定存在独立数值文档；若同一文档同时包含规则和数值信息，可直接按单文档分析。",
        ]
    )


def _compose_shared_review_baseline(
    public_rules: dict[str, object],
    *,
    include_placeholder_configuration_policy: bool = False,
) -> str:
    parts = [
        str(public_rules.get("review_rules") or REVIEW_RULES),
        str(public_rules.get("baseline_review_principles") or BASELINE_REVIEW_PRINCIPLES),
    ]
    if include_placeholder_configuration_policy:
        parts.append(
            str(
                public_rules.get("placeholder_configuration_policy")
                or PLACEHOLDER_CONFIGURATION_POLICY
            )
        )
    parts.extend(
        [
            str(public_rules.get("special_checklist") or SPECIAL_CHECKLIST),
            str(public_rules.get("fact_first_protocol") or FACT_FIRST_PROTOCOL),
            str(public_rules.get("root_cause_prompt_rules") or ROOT_CAUSE_PROMPT_RULES),
            str(public_rules.get("stability_protocol") or STABILITY_PROTOCOL),
            str(public_rules.get("score_rubric") or SCORE_RUBRIC),
            str(public_rules.get("output_quality_bar") or OUTPUT_QUALITY_BAR),
        ]
    )
    return "\n\n".join(parts)


def _compose_phase2_delta_baseline(public_rules: dict[str, object]) -> str:
    """Return a compact delta-only baseline without Primary report-writing or quantity targets."""
    _ = public_rules
    return DUAL_PASS_PHASE2_COMPACT_BASELINE


def build_primary_review_messages(shared_input: dict[str, object]) -> list[dict[str, str]]:
    document_labels = [str(item) for item in shared_input.get("document_labels") or []]
    user_prompt = "\n\n".join(
        [
            "请分析以下游戏需求/数值文档内容。",
            _build_current_document_constraints(document_labels),
            "集合摘要：",
            json.dumps(shared_input.get("collection_summary") or {}, ensure_ascii=False, indent=2),
            "文档内容：",
            str(shared_input.get("document_context") or ""),
            JSON_SCHEMA_INSTRUCTION,
        ]
    )
    public_rules = shared_input.get("public_rules") or {}
    baseline_rules = _compose_shared_review_baseline(
        public_rules,
        include_placeholder_configuration_policy=True,
    )
    return [
        {"role": "system", "content": ROLE_PROMPT},
        {
            "role": "user",
            "content": baseline_rules + "\n\n" + user_prompt,
        },
    ]


def _build_phase3_target_inventory(primary_report: dict[str, object]) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    order = 0
    for dimension in primary_report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        for finding in dimension.get("findings") or []:
            if not isinstance(finding, dict) or not str(finding.get("issue_id") or "").strip():
                continue
            order += 1
            inventory.append(
                {
                    "target_order": order,
                    "target_issue_id": str(finding.get("issue_id") or "").strip(),
                    "title": str(finding.get("title") or finding.get("canonical_title") or "").strip(),
                    "dimension": str(dimension.get("name") or finding.get("primary_dimension") or "").strip(),
                    "severity": str(finding.get("severity") or "").strip(),
                    "blocking": str(finding.get("blocking") or "").strip(),
                    "evidence": str(finding.get("evidence") or "").strip(),
                }
            )
    for finding in primary_report.get("cross_document_issues") or []:
        if not isinstance(finding, dict) or not str(finding.get("issue_id") or "").strip():
            continue
        order += 1
        inventory.append(
            {
                "target_order": order,
                "target_issue_id": str(finding.get("issue_id") or "").strip(),
                "title": str(finding.get("title") or finding.get("canonical_title") or "").strip(),
                "dimension": str(finding.get("primary_dimension") or "").strip(),
                "severity": str(finding.get("severity") or "").strip(),
                "blocking": str(finding.get("blocking") or "").strip(),
                "evidence": str(finding.get("evidence") or "").strip(),
            }
        )
    return inventory


def build_dual_pass_secondary_messages(
    shared_input: dict[str, object],
    primary_report: dict[str, object],
    protocol_profile: str = "phase2",
) -> list[dict[str, str]]:
    protocol_profile = normalize_secondary_protocol_profile(protocol_profile)
    public_rules = shared_input.get("public_rules") or {}
    if protocol_profile == "phase2":
        baseline_rules = _compose_phase2_delta_baseline(public_rules)
    elif protocol_profile == "phase3_v1":
        baseline_rules = DUAL_PASS_PHASE3_V1_BASELINE
    elif protocol_profile == "phase3_v1_1":
        baseline_rules = DUAL_PASS_PHASE3_V11_BASELINE
    elif protocol_profile == "phase3_v1_2":
        baseline_rules = DUAL_PASS_PHASE3_V12_BASELINE
    elif protocol_profile == "phase3_v1_3":
        baseline_rules = DUAL_PASS_PHASE3_V13_BASELINE
    else:
        baseline_rules = _compose_shared_review_baseline(public_rules)
    document_labels = [str(item) for item in shared_input.get("document_labels") or []]
    secondary_focus_rules = dedent(
        """
        dual_pass 本轮附加收敛规则：
        1. 除非共享输入里的证据已经明确证伪，否则不要把 primary 已发现的高信号核心 finding 静默替换成另一组更泛化、更 checklist 化的问题。
        2. 如果同时存在“强信号核心阻塞项”和“低信号泛化提醒项”，优先保留前者；后者默认写入 review_notes，不要挤占 missed_findings 的主结论位。
        3. candidate 的 top_blockers 应尽量保持与 primary 同一组高信号焦点；除非有明确证据推翻，否则不要在不同 rerun 间频繁更换主阻塞问题。
        4. 若 kept 问题已经吸收多个子症状，请在 current_state、risk、suggestion 中分点写清楚，不要揉成一段混写；也不要再把同组子症状额外独立落成新问题。
        5. 如果你下调了 primary 的高信号主问题，必须同时给出 shared input 中的 compatible implementation basis；否则保留 primary 判断。
        6. 如果你下调了高信号主问题，必须同步改写 candidate_report 的 overall_evaluation、score_reason、top_blockers，使其与新结论一致。
        7. Do not make candidate look better merely by deleting high-signal boundary issues. Prefer preserve-and-clarify over optimistic shrinkage.
        8. If one kept finding absorbs multiple sub-symptoms, current_state, risk, and suggestion must use numbered bullets such as 1. 2. 3.
        """
    ).strip()
    user_prompt_parts = [
            "请基于同一份共享输入，对主模型首版报告做复核。",
            "你的职责只有三件事：",
            "1. 评估主模型报告的合理性、完整性和表述质量。",
            "2. 补充主模型遗漏的问题。",
            "3. 生成一份候选最终报告。",
            _build_current_document_constraints(document_labels),
            "共享输入摘要：",
            json.dumps(
                {
                    "document_labels": shared_input.get("document_labels") or [],
                    "collection_summary": shared_input.get("collection_summary") or {},
                    "context_truncated": bool(shared_input.get("context_truncated")),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "共享输入正文：",
            str(shared_input.get("document_context") or ""),
            "主模型首版报告 JSON：",
            json.dumps(primary_report, ensure_ascii=False, indent=2),
            DUAL_PASS_CONSERVATIVE_CANDIDATE_RULES,
            DUAL_PASS_LINEAGE_RULES,
            secondary_focus_rules,
        ]
    if protocol_profile == "phase2":
        evidence_packet = build_phase2_control_evidence_packet(shared_input, primary_report)
        user_prompt_parts = [
            "请基于同一份共享输入，对主模型首版报告做结构化补漏与反证审查。",
            "你的职责只有两件事：",
            "1. 按固定12个 control 评估 Primary 是否已经覆盖。",
            "2. 输出 Primary 真正遗漏且证据成立的结构化增量。",
            _build_current_document_constraints(document_labels),
            "共享输入摘要：",
            json.dumps(
                {
                    "document_labels": shared_input.get("document_labels") or [],
                    "collection_summary": shared_input.get("collection_summary") or {},
                    "context_truncated": bool(shared_input.get("context_truncated")),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "共享输入正文：",
            str(shared_input.get("document_context") or ""),
            "主模型首版报告 JSON：",
            json.dumps(primary_report, ensure_ascii=False, indent=2),
            DUAL_PASS_PHASE2_V22_EVIDENCE_RULES,
            DUAL_PASS_PHASE2_V22_DELTA_ONLY_RULES,
            "phase2_v2_2 固定证据卡 JSON：",
            json.dumps(evidence_packet, ensure_ascii=False, separators=(",", ":")),
            DUAL_PASS_PHASE2_COVERAGE_TEMPLATE,
            DUAL_PASS_PHASE2_MISSED_FINDING_SCHEMA,
            (
                "协议标识：phase2_v2_2。请在 review_notes 最后一项原样写入 "
                f"protocol_profile=phase2_v2_2; evidence_packet_id={evidence_packet['evidence_packet_id']}。"
            ),
            DUAL_PASS_PHASE2_DELTA_ONLY_SCHEMA,
        ]
    elif protocol_profile in {"phase3_v1", "phase3_v1_1", "phase3_v1_2", "phase3_v1_3"}:
        primary_report_canonical = json.dumps(
            primary_report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        primary_report_hash = hashlib.sha256(primary_report_canonical.encode("utf-8")).hexdigest()
        user_prompt_parts = [
            "请对冻结 Primary 中已经存在的问题执行质疑与影子纠错，不要补漏，不要重写报告。",
            _build_current_document_constraints(document_labels),
            "共享输入摘要：",
            json.dumps(
                {
                    "document_labels": shared_input.get("document_labels") or [],
                    "collection_summary": shared_input.get("collection_summary") or {},
                    "context_truncated": bool(shared_input.get("context_truncated")),
                },
                ensure_ascii=False,
                indent=2,
            ),
            "共享输入正文：",
            str(shared_input.get("document_context") or ""),
            "冻结 Primary 报告 JSON：",
            json.dumps(primary_report, ensure_ascii=False, indent=2),
            *(
                [
                    f"{protocol_profile} 固定 Primary target inventory JSON：",
                    json.dumps(_build_phase3_target_inventory(primary_report), ensure_ascii=False, indent=2),
                ]
                if protocol_profile in {"phase3_v1_2", "phase3_v1_3"}
                else []
            ),
            (
                DUAL_PASS_PHASE3_V13_BASELINE
                if protocol_profile == "phase3_v1_3"
                else DUAL_PASS_PHASE3_V12_BASELINE
                if protocol_profile == "phase3_v1_2"
                else DUAL_PASS_PHASE3_V11_BASELINE
                if protocol_profile == "phase3_v1_1"
                else DUAL_PASS_PHASE3_V1_BASELINE
            ),
            (
                DUAL_PASS_PHASE3_V13_SCHEMA
                if protocol_profile == "phase3_v1_3"
                else DUAL_PASS_PHASE3_V12_SCHEMA
                if protocol_profile == "phase3_v1_2"
                else DUAL_PASS_PHASE3_V11_SCHEMA
                if protocol_profile == "phase3_v1_1"
                else DUAL_PASS_PHASE3_V1_SCHEMA
            ),
            (
                f"协议标识：{protocol_profile}。请在 review_notes 最后一项原样写入 "
                f"protocol_profile={protocol_profile}; primary_report_hash={primary_report_hash}。"
            ),
        ]
    else:
        user_prompt_parts.append(DUAL_PASS_SCHEMA_INSTRUCTION)
    user_prompt = "\n\n".join(user_prompt_parts)
    return [
        {
            "role": "system",
            "content": (
                "你是游戏需求评审的结构化补漏与反证审查者，必须按固定 control 证据卡复核主模型首版报告，"
                "禁止自由重写报告或引入外部背景。"
                if protocol_profile == "phase2"
                else (
                    "你是游戏需求报告的质疑与影子纠错审查者，只能输出可追踪的 challenge/correct 旁路建议，"
                    "禁止修改评分、blocking、评分理由、Top 3 或生成候选报告。"
                    if protocol_profile in {"phase3_v1", "phase3_v1_1", "phase3_v1_2", "phase3_v1_3"}
                    else "你是游戏需求评审的复核编辑，必须基于共享输入事实复核主模型首版报告，禁止引入外部背景。"
                )
            ),
        },
        {
            "role": "user",
            "content": baseline_rules + "\n\n" + user_prompt,
        },
    ]
