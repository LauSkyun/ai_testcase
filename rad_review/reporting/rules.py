from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from rad_review.docx_reader import ParsedDocument
from rad_review.prompts import DIMENSIONS

from .base import (
    CANONICAL_BY_ID,
    LOW_SEVERITY_BLOCKING,
    MEDIUM_SEVERITY_BLOCKING,
    NO_AI_ANALYSIS_NOTE,
    NO_FINDINGS_NOTE,
    ROOT_CAUSE_CLUSTERS,
    BLOCKING_RANK,
    PLACEHOLDER_EVIDENCE_MARKERS,
    normalized_max,
    finding_priority,
    has_any,
    merge_scope,
    merge_text,
    normalize_compare_text,
)


def normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    report.setdefault("overall_evaluation", "")
    report.setdefault("document_quality_score", "")
    report.setdefault("score_reason", "")
    report.setdefault("top_blockers", [])
    report.setdefault("dimensions", [])
    existing = {item.get("name"): item for item in report["dimensions"] if isinstance(item, dict)}
    normalized_dimensions: list[dict[str, Any]] = []
    for dimension in DIMENSIONS:
        item = existing.get(dimension, {"name": dimension, "dimension_note": NO_FINDINGS_NOTE, "findings": []})
        item.setdefault("dimension_note", NO_FINDINGS_NOTE if not item.get("findings") else "")
        item.setdefault("findings", [])
        normalized_dimensions.append(item)
    report["dimensions"] = normalized_dimensions
    report.setdefault("cross_document_issues", [])
    report.setdefault("missing_information", [])
    report.setdefault("test_points", {})
    report.setdefault("quality_notes", [])
    report.setdefault("image_analysis_gaps", [])
    return report


ISSUE_ID_PREFIX_BY_DIMENSION = {
    "清晰度与完整性": "CLARITY",
    "逻辑一致性与数值平衡": "LOGIC",
    "可测试性与验收标准": "TEST",
    "跨系统影响与兼容性": "COMP",
    "安全性与反作弊": "SEC",
    "用户体验与游戏性": "UX",
    "cross_document": "CROSS",
}


def _stable_issue_id_prefix(source_dimension: str) -> str:
    return ISSUE_ID_PREFIX_BY_DIMENSION.get(source_dimension, "ISSUE")


def _stable_issue_id_seed_text(finding: dict[str, Any]) -> str:
    parts = [
        str(finding.get("canonical_title") or "").strip(),
        str(finding.get("title") or "").strip(),
        str(finding.get("issue_title") or "").strip(),
        str(finding.get("current_state") or finding.get("description") or "").strip(),
        str(finding.get("evidence") or "").strip(),
    ]
    normalized = normalize_compare_text(" ".join(part for part in parts if part))
    if normalized:
        return normalized
    fallback = " ".join(part for part in parts if part).strip()
    return fallback or "missing_issue_id"


def build_stable_synthetic_issue_id(finding: dict[str, Any], source_dimension: str) -> str:
    prefix = _stable_issue_id_prefix(source_dimension)
    digest = hashlib.sha1(_stable_issue_id_seed_text(finding).encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}_GEN_{digest}"


def repair_missing_issue_ids(report: dict[str, Any], *, prefer_canonical: bool = True) -> tuple[dict[str, Any], list[dict[str, str]]]:
    normalized_report = normalize_report(report)
    repairs: list[dict[str, str]] = []
    seen_issue_ids: set[str] = set()

    def visit(finding: Any, source_dimension: str) -> None:
        if not isinstance(finding, dict):
            return
        finding["issue_id"] = str(finding.get("issue_id") or "").strip()
        if not str(finding.get("canonical_title") or "").strip():
            fallback_title = str(finding.get("title") or finding.get("issue_title") or "").strip()
            if fallback_title:
                finding["canonical_title"] = fallback_title
        if finding["issue_id"]:
            seen_issue_ids.add(finding["issue_id"])
            return

        repaired_issue_id = ""
        repair_kind = ""
        if prefer_canonical:
            repaired_issue_id = inferred_canonical_issue_id(finding)
            if repaired_issue_id:
                repair_kind = "canonical"
                canonical = CANONICAL_BY_ID.get(repaired_issue_id) or {}
                if canonical and not str(finding.get("canonical_title") or "").strip():
                    finding["canonical_title"] = str(canonical.get("title") or "").strip()
        if not repaired_issue_id:
            repaired_issue_id = build_stable_synthetic_issue_id(finding, source_dimension)
            repair_kind = "synthetic"
        if repaired_issue_id in seen_issue_ids:
            suffix = hashlib.sha1(
                f"{repaired_issue_id}|{str(finding.get('risk') or '').strip()}|{str(finding.get('suggestion') or '').strip()}".encode(
                    "utf-8"
                )
            ).hexdigest()[:4].upper()
            repaired_issue_id = f"{repaired_issue_id}_{suffix}"
        finding["issue_id"] = repaired_issue_id
        seen_issue_ids.add(repaired_issue_id)
        repairs.append(
            {
                "title": str(finding.get("title") or finding.get("canonical_title") or "未命名问题").strip(),
                "issue_id": repaired_issue_id,
                "repair_kind": repair_kind,
                "source_dimension": source_dimension,
            }
        )

    for dimension in normalized_report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        dimension_name = normalize_dimension_name(dimension.get("name"), fallback=DIMENSIONS[0])
        for finding in dimension.get("findings") or []:
            visit(finding, dimension_name)
    for finding in normalized_report.get("cross_document_issues") or []:
        visit(finding, "cross_document")
    return normalized_report, repairs


def finding_policy_text(finding: dict[str, Any]) -> str:
    fields = ("issue_id", "canonical_title", "title", "current_state", "evidence", "risk", "suggestion", "planner_role")
    return " ".join(str(finding.get(field) or "").lower() for field in fields)


def finding_signal_text(finding: dict[str, Any]) -> str:
    fields = ["issue_id", "canonical_title", "title", "issue_title", "current_state", "description", "risk", "suggestion", "blocking"]
    return " ".join(str(finding.get(field) or "").lower() for field in fields)


def finding_text(finding: dict[str, Any]) -> str:
    fields = [
        "issue_id",
        "canonical_title",
        "title",
        "issue_title",
        "current_state",
        "description",
        "evidence",
        "doc1",
        "doc2",
        "risk",
        "suggestion",
        "blocking",
    ]
    return " ".join(str(finding.get(field) or "").lower() for field in fields)


def finding_title_text(finding: dict[str, Any]) -> str:
    return " ".join(str(finding.get(field) or "") for field in ("canonical_title", "title", "issue_title"))


def finding_topic_text(finding: dict[str, Any]) -> str:
    return " ".join(str(finding.get(field) or "") for field in ("canonical_title", "title", "issue_title", "current_state", "description", "risk"))


def finding_context_text(finding: dict[str, Any]) -> str:
    return " ".join(str(finding.get(field) or "") for field in ("current_state", "description", "risk"))


def build_cross_issue_evidence(finding: Any) -> str:
    if not isinstance(finding, dict):
        return ""
    evidence = str(finding.get("evidence") or "").strip()
    if evidence:
        return evidence
    affected_docs = finding.get("affected_docs")
    if isinstance(affected_docs, list):
        parts = [str(item).strip() for item in affected_docs if str(item).strip()]
        if parts:
            return "；".join(parts)
    parts: list[str] = []
    for key in ("doc1", "doc2", "doc_a", "doc_b", "doc1_evidence", "doc2_evidence"):
        value = str(finding.get(key) or "").strip()
        if value:
            parts.append(value)
    return "；".join(parts)


def explicit_canonical_issue_id(finding: Any) -> str:
    if not isinstance(finding, dict):
        return ""
    issue_id = str(finding.get("issue_id") or "").strip()
    return issue_id if issue_id in CANONICAL_BY_ID else ""


def inferred_canonical_issue_id(finding: Any) -> str:
    if not isinstance(finding, dict):
        return ""
    explicit = explicit_canonical_issue_id(finding)
    if explicit:
        return explicit
    text = " ".join(
        str(finding.get(field) or "")
        for field in ("canonical_title", "title", "issue_title", "current_state")
    ).lower()
    inferred = identify_issue_id_from_text(text)
    return inferred if inferred in CANONICAL_BY_ID else ""


def identify_issue_id_from_text(text: str) -> str:
    if has_any(text, "断线", "重连", "重进", "恢复", "后台", "杀进程"):
        return "COMP_RECONNECT_REENTER_MISSING"
    if has_any(text, "热更", "配置变更", "历史局", "进行中局", "配置版本"):
        return "COMP_CONFIG_HOT_UPDATE_MISSING"
    if "提现" in text and has_any(text, "幂等", "重放", "重复", "序列号", "接口"):
        return "SEC_CASHOUT_IDEMPOTENCY_MISSING"
    if has_any(text, "失败", "新手", "引导", "再来一局", "流失"):
        return "UX_FAILURE_GUIDANCE_MISSING"
    if has_any(text, "最大赔付", "赔付上限", "熔断", "风控阈值"):
        return "LOGIC_MAX_PAYOUT_MISSING"
    if has_any(text, "篡改", "权威", "反作弊", "随机结果", "服务端判定", "客户端上报"):
        return "SEC_SERVER_AUTHORITY_MISSING"
    if has_any(text, "验收", "量化", "边界条件", "无法验证", "测试不可执行"):
        return "TEST_ACCEPTANCE_CRITERIA_MISSING"
    if has_any(text, "重复点击", "并发", "快点", "快速点击", "重复提交") or ("按钮" in text and has_any(text, "锁定", "互斥")):
        return "TEST_CONCURRENT_OPERATION_MISSING"
    if has_any(text, "马路", "格子", "关卡") and has_any(text, "数量", "定义", "术语", "单位", "30"):
        return "CORE_TERMINOLOGY_UNIT_COUNT"
    if has_any(text, "下注", "筹码", "下注金额", "档位"):
        return "CORE_BET_CONFIG_MISMATCH"
    if has_any(text, "超级大奖", "通关", "大奖") and has_any(text, "缺失", "没有", "规则", "奖励", "触发"):
        return "CORE_JACKPOT_RULE_MISSING"
    if has_any(text, "难度", "倍率池", "配置表", "赔率表", "ui") and has_any(text, "不一致", "冲突", "不明", "映射", "含义"):
        return "CORE_DIFFICULTY_CONFIG_MISMATCH"
    if has_any(text, "碰撞", "被撞", "爆炸", "crash") and has_any(text, "冲突", "矛盾", "模型", "判定"):
        return "LOGIC_COLLISION_MODEL_CONFLICT"
    if has_any(text, "rtp", "概率") and has_any(text, "映射", "缺失", "对应", "配置"):
        return "LOGIC_RTP_PROBABILITY_MAPPING_MISSING"
    if has_any(text, "假赔率", "实际赔率", "展示赔率") and not has_any(text, "公式", "gamma", "max("):
        return ""
    if has_any(text, "奖金", "赔率", "连乘", "累乘", "公式", "赔付", "倍率") and has_any(text, "冲突", "矛盾", "口径", "不匹配"):
        return "LOGIC_PAYOUT_FORMULA_CONFLICT"
    return ""


def identify_issue_id(finding: dict[str, Any]) -> str:
    provided = str(finding.get("issue_id") or "").strip()
    if provided:
        return provided
    title_text = " ".join(str(finding.get(field) or "").lower() for field in ("canonical_title", "title"))
    current_text = str(finding.get("current_state") or "").lower()
    return identify_issue_id_from_text(title_text) or identify_issue_id_from_text(current_text)


def is_formula_odds_conflict_cluster(finding: dict[str, Any]) -> bool:
    issue_id = str(finding.get("issue_id") or "").strip()
    if issue_id == "LOGIC_PAYOUT_FORMULA_CONFLICT":
        return True
    title_text = " ".join(str(finding.get(field) or "").lower() for field in ("canonical_title", "title", "issue_title", "current_state"))
    formula_terms = ("赔率公式", "结算公式", "赔付公式", "赔率体系", "赔率计算", "odds", "gamma", "抽水")
    conflict_terms = ("冲突", "矛盾", "分歧", "不一致", "未统一", "根本分歧", "未澄清", "两套", "多版本")
    display_terms = ("假赔率", "实际赔率", "展示赔率")
    return (has_any(title_text, *formula_terms) and has_any(title_text, *conflict_terms)) or (
        has_any(title_text, *display_terms) and has_any(title_text, *conflict_terms) and has_any(title_text, "公式", "赔率")
    )


def is_intervention_mapping_cluster(finding: dict[str, Any]) -> bool:
    title_text = " ".join(str(finding.get(field) or "").lower() for field in ("canonical_title", "title", "issue_title", "current_state"))
    interference_terms = ("干扰指数", "随机扰动", "奖池干预")
    target_terms = ("luck", "开奖时间公式", "t公式", "t=", "t)", "t）")
    mapping_terms = ("映射", "对应", "联系", "未建立", "未定义", "未说明", "缺失")
    return has_any(title_text, *interference_terms) and has_any(title_text, *target_terms) and has_any(title_text, *mapping_terms)


def identify_root_cause_cluster(finding: dict[str, Any]) -> str:
    text = finding_text(finding)
    issue_id = str(finding.get("issue_id") or "").strip()
    if is_formula_odds_conflict_cluster(finding):
        return "formula_odds_conflict"
    if is_intervention_mapping_cluster(finding):
        return "intervention_mapping"
    for cluster in ROOT_CAUSE_CLUSTERS:
        cluster_issue_ids = cluster["issue_ids"]
        if issue_id and issue_id in cluster_issue_ids:
            return str(cluster["key"])
        if has_any(text, *cluster["must"]) and has_any(text, *cluster["signal"]):
            return str(cluster["key"])
    return ""


def build_root_cause_key(finding: dict[str, Any]) -> str:
    cluster = str(finding.get("_root_cause_cluster") or identify_root_cause_cluster(finding)).strip()
    if cluster:
        return f"cluster:{cluster}"
    inferred_issue_id = inferred_canonical_issue_id(finding)
    if inferred_issue_id:
        return f"issue:{inferred_issue_id}"
    issue_id = str(finding.get("issue_id") or "").strip()
    if issue_id:
        return f"issue:{issue_id}"
    canonical = normalize_compare_text(str(finding.get("canonical_title") or ""))
    if canonical:
        return f"canonical:{canonical}"
    title = normalize_compare_text(str(finding.get("title") or ""))
    return f"title:{title}" if title else ""


def finding_root_key(finding: dict[str, Any]) -> str:
    return str(finding.get("_root_cause_key") or build_root_cause_key(finding)).strip()


def titles_indicate_same_fake_odds_gap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = " ".join(str(left.get(key) or "").lower() for key in ("title", "canonical_title", "issue_title"))
    right_title = " ".join(str(right.get(key) or "").lower() for key in ("title", "canonical_title", "issue_title"))
    fake_terms = ("假赔率", "实际赔率", "展示赔率")
    return has_any(left_title, *fake_terms) and has_any(right_title, *fake_terms)


def titles_indicate_same_formula_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = " ".join(str(left.get(key) or "").lower() for key in ("title", "canonical_title", "issue_title"))
    right_title = " ".join(str(right.get(key) or "").lower() for key in ("title", "canonical_title", "issue_title"))
    # `odds` is a generic formula term, not evidence that a finding is about the
    # separate fake/display-odds decision object.
    fake_terms = ("假赔率", "实际赔率", "展示赔率")
    left_fake = has_any(left_title, *fake_terms)
    right_fake = has_any(right_title, *fake_terms)
    if left_fake != right_fake:
        return False
    formula_terms = ("odds", "gamma", "公式", "赔率")
    conflict_terms = ("矛盾", "冲突", "分歧", "不一致", "无法实现", "互斥", "无法闭环")
    return has_any(left_title, *formula_terms) and has_any(right_title, *formula_terms) and has_any(left_title, *conflict_terms) and has_any(right_title, *conflict_terms)


def is_core_execution_or_economic_gap(finding: dict[str, Any]) -> bool:
    text = finding_policy_text(finding)
    issue_id = str(finding.get("issue_id") or "").strip()
    if issue_id in {"LOGIC_PAYOUT_FORMULA_CONFLICT", "LOGIC_MAX_PAYOUT_MISSING", "LOGIC_RTP_PROBABILITY_MAPPING_MISSING", "LOGIC_COLLISION_MODEL_CONFLICT"}:
        return True
    if has_any(text, "赔率公式", "结算公式", "最终结算公式", "开奖时间公式", "rtp", "gamma", "luck", "干扰指数", "最大赔付", "赔付上限", "max_mul", "熔断", "资金损", "无限赔付", "开奖结果不可控"):
        return True
    if has_any(text, "奖池") and has_any(text, "除零", "分母为", "收入为", "负值"):
        return True
    if has_any(text, "展示赔率", "ui展示赔率", "客户端展示赔率", "假赔率") and has_any(text, "实际赔率", "实际结算", "真实赔付", "最终结算"):
        return True
    if has_any(text, "下注接口", "幂等", "防重", "重复扣款") and has_any(text, "赔付", "资金", "下注", "结算"):
        return True
    return False


def is_resilience_or_authority_gap(finding: dict[str, Any]) -> bool:
    if is_core_execution_or_economic_gap(finding):
        return False
    text = finding_policy_text(finding)
    issue_id = str(finding.get("issue_id") or "").strip()
    if issue_id in {"COMP_RECONNECT_REENTER_MISSING", "COMP_CONFIG_HOT_UPDATE_MISSING", "SEC_SERVER_AUTHORITY_MISSING"}:
        return True
    return has_any(text, "弱网", "断线", "重连", "重进", "热更", "历史局", "服务端权威", "防篡改")


def is_config_placeholder_detail_gap(finding: dict[str, Any]) -> bool:
    if is_core_execution_or_economic_gap(finding):
        return False
    text = finding_policy_text(finding)
    if not has_any(text, "占位符", "默认值", "可配范围", "取值范围", "范围", "字段清单", "配置表蓝图", "配置蓝图", "配置表示例", "配置表结构", "后台配置", "具体值", "示例值", "接口字段"):
        return False
    if not has_any(text, "缺失", "未给出", "未说明", "未定义", "未提供", "缺少", "占位"):
        return False
    if has_any(text, "冲突", "矛盾", "不一致", "无法实现", "无法落地", "结算", "赔付", "开奖链路", "主流程无法", "核心公式", "口径分裂"):
        return False
    return True


def is_ignorable_placeholder_or_config_value_gap(finding: dict[str, Any]) -> bool:
    """Return True when a finding only complains about an unfilled configuration value."""
    source_text = " ".join(
        str(finding.get(field) or "").lower()
        for field in (
            "canonical_title",
            "title",
            "issue_title",
            "current_state",
            "description",
            "evidence",
        )
    )
    explicit_placeholder = has_any(
        source_text,
        "占位符",
        "占位值",
        "待配置",
        "待填写",
        "待填充",
        "tbd",
        "todo",
    ) or bool(re.search(r"\[\s*\d{2,}\s*\]", source_text))
    config_value_detail = has_any(
        source_text,
        "配置值",
        "具体值",
        "具体数值",
        "示例值",
        "默认值",
        "可配范围",
        "取值范围",
        "数值待定",
        "数值未定",
    ) and has_any(
        source_text,
        "配置",
        "参数",
        "概率",
        "倍率",
        "阈值",
        "上限",
        "下限",
        "最大赔付",
        "最小赔付",
        "赔付极值",
    )
    if not (explicit_placeholder or config_value_detail):
        return False
    if not has_any(
        source_text,
        "缺失",
        "未给出",
        "未说明",
        "未定义",
        "未提供",
        "缺少",
        "未填",
        "待配置",
        "待填写",
        "待定",
        "tbd",
        "todo",
        "占位",
        "无具体",
        "无法确认",
    ):
        return False
    # Keep a real, document-proven contradiction even when one side happens to use a placeholder.
    if has_any(
        source_text,
        "冲突",
        "矛盾",
        "不一致",
        "互斥",
        "双轨",
        "两套公式",
        "多版本公式",
        "口径分裂",
        "前后不一",
        "除零",
        "分母为0",
        "分母为 0",
        "死锁",
        "公式错误",
    ):
        return False
    return True


def is_fusion_high_risk_candidate(finding: dict[str, Any]) -> bool:
    return str(finding.get("severity") or "") == "高"


def is_onboarding_or_guide_gap(finding: dict[str, Any]) -> bool:
    text = " ".join(
        str(finding.get(field) or "").lower()
        for field in ("issue_id", "canonical_title", "title", "issue_title", "current_state")
    )
    issue_id = str(finding.get("issue_id") or "").strip().upper()
    if issue_id.startswith("GUIDE") or issue_id.startswith("TUTORIAL") or issue_id.startswith("ONBOARD"):
        return True
    return has_any(text, "新手", "引导", "教程", "教学关", "guide", "tutorial", "onboarding")


def is_core_guide_conflict(finding: dict[str, Any]) -> bool:
    text = finding_policy_text(finding)
    return has_any(text, "赔率", "公式", "结算", "赔付", "扣款", "冲突", "矛盾", "不一致", "开奖")


def apply_severity_policy(finding: dict[str, Any]) -> None:
    if is_onboarding_or_guide_gap(finding):
        if is_core_guide_conflict(finding):
            finding["severity"] = "中"
            finding["blocking"] = MEDIUM_SEVERITY_BLOCKING
        else:
            finding["severity"] = "低"
            finding["blocking"] = LOW_SEVERITY_BLOCKING
        return
    if is_core_execution_or_economic_gap(finding):
        return
    if is_resilience_or_authority_gap(finding) or is_config_placeholder_detail_gap(finding):
        finding["severity"] = "低"
        finding["blocking"] = LOW_SEVERITY_BLOCKING


def normalize_unmatched_finding(finding: dict[str, Any], dimension_name: str) -> dict[str, Any]:
    normalized = dict(finding)
    if not normalized.get("description") and normalized.get("describe"):
        normalized["description"] = normalized.get("describe")
    if not normalized.get("description") and normalized.get("conflict_description"):
        normalized["description"] = normalized.get("conflict_description")
    if not normalized.get("description"):
        doc_evidence = build_cross_issue_evidence(normalized)
        if normalized.get("doc1_evidence") and normalized.get("doc2_evidence") and doc_evidence:
            normalized["description"] = doc_evidence
    if not normalized.get("risk") and normalized.get("impact"):
        normalized["risk"] = normalized.get("impact")
    if not normalized.get("affected_docs") and normalized.get("source_docs"):
        normalized["affected_docs"] = normalized.get("source_docs")
    if not normalized.get("title") and normalized.get("issue_title"):
        normalized["title"] = normalized.get("issue_title")
    normalized.setdefault("issue_id", "")
    normalized.setdefault("canonical_title", normalized.get("title") or normalized.get("issue_title") or "")
    normalized.setdefault("primary_dimension", dimension_name)
    normalized.setdefault("title", normalized.get("canonical_title") or "未命名问题")
    normalized.setdefault("evidence_scope", "document")
    normalized["severity"] = normalized_max("severity", [normalized.get("severity")])
    normalized["confidence"] = normalized_max("confidence", [normalized.get("confidence")])
    normalized["blocking"] = normalized_max("blocking", [normalized.get("blocking")])
    normalized.setdefault("planner_role", normalized.get("owner") or "待定")
    normalized.setdefault("current_state", normalized.get("description") or "")
    normalized.setdefault("evidence", build_cross_issue_evidence(normalized))
    normalized.setdefault("risk", "")
    normalized.setdefault("suggestion", "")
    title = str(normalized.get("title") or normalized.get("canonical_title") or "未命名问题").strip()
    if not str(normalized.get("current_state") or "").strip():
        normalized["current_state"] = (
            str(normalized.get("evidence") or "").strip()
            or f"文档中存在“{title}”相关规则缺口，当前缺少可直接落地的完整说明。"
        )
    if not str(normalized.get("evidence") or "").strip():
        normalized["evidence"] = "模型未提供可核验的原文定位，采用该结论前需回查需求文档。"
    if not str(normalized.get("risk") or "").strip():
        normalized["risk"] = f"该问题可能导致开发、配置或测试对“{title}”采用不一致口径。"
    if not str(normalized.get("suggestion") or "").strip():
        normalized["suggestion"] = f"补充“{title}”的唯一规则、边界条件与验收口径。"
    apply_severity_policy(normalized)
    return normalized


def build_document_aliases(documents: list[ParsedDocument]) -> list[set[str]]:
    aliases: list[set[str]] = []
    requirement_indexes = [index for index, doc in enumerate(documents) if doc.kind in {"requirement", "mixed"}]
    numeric_indexes = [index for index, doc in enumerate(documents) if doc.kind == "numeric"]
    token_groups: list[set[str]] = []
    for doc in documents:
        alias_group = {doc.name.lower(), Path(doc.name).stem.lower()}
        aliases.append({alias for alias in alias_group if alias})
        tokens = {
            token
            for token in re.findall(r"[a-z0-9]{3,}", f"{doc.name.lower()} {Path(doc.name).stem.lower()}")
            if token not in {"doc", "docx"}
        }
        token_groups.append(tokens)
    token_counts: dict[str, int] = {}
    for tokens in token_groups:
        for token in tokens:
            token_counts[token] = token_counts.get(token, 0) + 1
    for index, tokens in enumerate(token_groups):
        aliases[index].update({token for token in tokens if token_counts.get(token, 0) == 1})
    if len(requirement_indexes) == 1:
        aliases[requirement_indexes[0]].update({"需求文档", "需求"})
    if len(numeric_indexes) == 1:
        aliases[numeric_indexes[0]].update({"数值文档", "数值"})
    return aliases


def mentioned_document_indexes(text: str, document_aliases: list[set[str]]) -> set[int]:
    lowered = text.lower()
    matches: set[int] = set()
    for index, alias_group in enumerate(document_aliases):
        if any(alias in lowered for alias in alias_group):
            matches.add(index)
    return matches


def evidence_mentions_multiple_documents(evidence: str, document_aliases: list[set[str]]) -> bool:
    return len(mentioned_document_indexes(evidence, document_aliases)) >= 2


def finding_mentions_multiple_documents(finding: Any, document_aliases: list[set[str]]) -> bool:
    if not isinstance(finding, dict):
        return False
    doc1 = str(finding.get("doc1") or "").strip()
    doc2 = str(finding.get("doc2") or "").strip()
    if doc1 and doc2:
        doc1_matches = mentioned_document_indexes(doc1, document_aliases)
        doc2_matches = mentioned_document_indexes(doc2, document_aliases)
        if doc1_matches and doc2_matches and len(doc1_matches | doc2_matches) >= 2:
            return True
    return evidence_mentions_multiple_documents(build_cross_issue_evidence(finding), document_aliases)


def should_promote_dimension_finding_to_cross_document(finding: dict[str, Any], document_aliases: list[set[str]], document_count: int) -> bool:
    if document_count < 2:
        return False
    if not finding_mentions_multiple_documents(finding, document_aliases):
        return False
    return is_formula_odds_conflict_cluster(finding)


def infer_evidence_scope(finding: dict[str, Any], source_dimension: str) -> str:
    if source_dimension == "cross_document":
        return "cross_document"
    explicit = str(finding.get("evidence_scope") or "").strip()
    if explicit in {"document", "table", "image", "cross_document"}:
        return explicit
    text = finding_text(finding)
    if "图片" in text:
        return "image"
    if "表格" in text:
        return "table"
    return "document"


def resolve_dimension(finding: dict[str, Any], issue_id: str, fallback: str = DIMENSIONS[0]) -> str:
    primary_dimension = normalize_dimension_name(finding.get("primary_dimension"), fallback="")
    if primary_dimension in DIMENSIONS:
        return primary_dimension
    if issue_id in CANONICAL_BY_ID:
        return CANONICAL_BY_ID[issue_id]["dimension"]
    return normalize_dimension_name(fallback, fallback=DIMENSIONS[0])


def normalize_dimension_name(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text in DIMENSIONS else fallback


def fallback_report(reason: str, raw_response: str = "") -> dict[str, Any]:
    return normalize_report(
        {
            "overall_evaluation": f"未完成 AI 评审：{reason}",
            "document_quality_score": "未评定",
            "score_reason": reason,
            "top_blockers": [],
            "dimensions": [{"name": dimension, "dimension_note": NO_AI_ANALYSIS_NOTE, "findings": []} for dimension in DIMENSIONS],
            "cross_document_issues": [],
            "missing_information": [reason],
            "test_points": {
                "功能验证": [],
                "异常操作": [],
                "兼容性": [],
                "安全专项": [],
                "回归影响": [],
                "性能与稳定性": [],
                "用户体验": [],
            },
            "quality_notes": [reason],
            "image_analysis_gaps": [],
            "raw_response": raw_response,
        }
    )
