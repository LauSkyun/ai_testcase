from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .base import BLOCKING_RANK, CONFIDENCE_RANK, SEVERITY_RANK, finding_priority, merge_scope, merge_text, normalize_compare_text, normalized_max, public_finding, sort_findings, sort_public_findings
from .rules import (
    build_cross_issue_evidence,
    build_root_cause_key,
    finding_context_text,
    finding_root_key,
    finding_title_text,
    finding_topic_text,
    identify_root_cause_cluster,
    titles_indicate_same_fake_odds_gap,
    titles_indicate_same_formula_conflict,
)


def collect_report_entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for dimension_index, dimension in enumerate(report.get("dimensions") or []):
        for finding_index, finding in enumerate(dimension.get("findings") or []):
            if isinstance(finding, dict):
                entries.append({"location": "dimension", "dimension_index": dimension_index, "finding_index": finding_index, "dimension_name": dimension.get("name", ""), "finding": finding})
    for finding_index, finding in enumerate(report.get("cross_document_issues") or []):
        if isinstance(finding, dict):
            entries.append({"location": "cross_document", "finding_index": finding_index, "dimension_name": str(finding.get("primary_dimension") or ""), "finding": finding})
    return entries


def evidence_reference_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    lowered = text.lower()
    for doc_name in re.findall(r"[\w\-\u4e00-\u9fff.]+\.(?:docx|md|pdf|txt|xlsx?)", lowered):
        normalized = normalize_compare_text(doc_name)
        if normalized:
            tokens.add(normalized)
        stem = normalize_compare_text(Path(doc_name).stem)
        if stem:
            tokens.add(stem)
    for alias in ("需求文档", "数值文档", "requirement", "numeric", "spec", "docx", "markdown"):
        if alias in lowered:
            tokens.add(normalize_compare_text(alias))
    return {token for token in tokens if token}


def evidence_locator_tokens(text: str) -> set[str]:
    lowered = str(text or "").lower()
    tokens: set[str] = set()
    patterns = (
        r"(?:段落|paragraph)\s*\d+(?:\s*[-~至]\s*\d+)?",
        r"(?:表格|table)\s*\d+(?:\s*[-~至]\s*\d+)?",
        r"(?:图片|image)\s*\d+(?:\s*[-~至]\s*\d+)?",
        r"(?:章节|section)\s*[:：]?\s*[^；;,，\n]{1,48}",
    )
    for pattern in patterns:
        for match in re.findall(pattern, lowered):
            normalized = normalize_compare_text(match)
            if normalized:
                tokens.add(normalized)
    return tokens


def shared_evidence_tokens(left: str, right: str) -> set[str]:
    return evidence_reference_tokens(left) & evidence_reference_tokens(right)


def evidence_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_evidence = str(left.get("evidence") or "")
    right_evidence = str(right.get("evidence") or "")
    if not left_evidence or not right_evidence:
        return False
    left_norm = normalize_compare_text(left_evidence)
    right_norm = normalize_compare_text(right_evidence)
    return left_norm in right_norm or right_norm in left_norm or bool(shared_evidence_tokens(left_evidence, right_evidence))


def granular_evidence_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_evidence = str(left.get("evidence") or "")
    right_evidence = str(right.get("evidence") or "")
    if not left_evidence or not right_evidence:
        return False
    left_norm = normalize_compare_text(left_evidence)
    right_norm = normalize_compare_text(right_evidence)
    if left_norm in right_norm or right_norm in left_norm:
        return True
    shared_docs = shared_evidence_tokens(left_evidence, right_evidence)
    shared_locations = evidence_locator_tokens(left_evidence) & evidence_locator_tokens(right_evidence)
    return bool(shared_docs and shared_locations)


def compare_ngram_set(text: str) -> set[str]:
    normalized = normalize_compare_text(text)
    if len(normalized) < 2:
        return set()
    tokens: set[str] = set()
    for size in (2, 3):
        if len(normalized) < size:
            continue
        for index in range(len(normalized) - size + 1):
            tokens.add(normalized[index : index + size])
    return tokens


def structured_signal_tokens(text: str) -> set[str]:
    lowered = text.lower()
    return {token for token in re.findall(r"\[[0-9]{3,}\]|[a-z][a-z0-9_]{1,}", lowered) if len(token) >= 2}


ATOMIC_DECISION_OBJECT_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bonus_probability", ("触发概率", "额外开奖概率", "额外奖励概率")),
    ("symbol_naming", ("符号名", "符号名称", "符号字段", "资源命名", "李子", "番茄", "苹果")),
    ("chip_tiers", ("筹码挡位", "筹码档位", "筹码配置", "投注挡位", "投注档位")),
    ("countdown_interaction", ("倒计时阶段", "下注截止", "投注截止", "toast反馈", "交互反馈")),
    ("debit_timing", ("扣款时机", "本金扣除", "冻结本金", "扣款节点")),
    ("payout_timing", ("派奖时机", "奖励到账", "派奖到账", "入账节点")),
    ("funds_compensation", ("资金失败补偿", "补发", "事务回滚", "资金重试")),
    ("pool_negative_floor", ("奖池负值", "透支下限", "负值下限")),
    ("single_round_cap", ("单局最大赔付", "单局赔付封顶", "绝对赔付上限")),
    ("fake_data_isolation", ("假人数", "假金额", "展示数据", "显示数据", "虚拟数据")),
)


def finding_atomic_decision_objects(finding: dict[str, Any]) -> set[str]:
    text = " ".join(
        str(finding.get(field) or "").lower()
        for field in ("canonical_title", "title", "current_state", "suggestion")
    )
    return {
        key
        for key, terms in ATOMIC_DECISION_OBJECT_TERMS
        if any(term.lower() in text for term in terms)
    }


def overlap_ratio(left: set[str], right: set[str], shared: set[str] | None = None) -> float:
    if not left or not right:
        return 0.0
    shared = shared if shared is not None else left & right
    return len(shared) / max(1, min(len(left), len(right)))


def findings_share_semantic_signature(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title_tokens = compare_ngram_set(finding_title_text(left))
    right_title_tokens = compare_ngram_set(finding_title_text(right))
    left_context_tokens = compare_ngram_set(finding_context_text(left))
    right_context_tokens = compare_ngram_set(finding_context_text(right))
    left_structured_tokens = structured_signal_tokens(finding_topic_text(left))
    right_structured_tokens = structured_signal_tokens(finding_topic_text(right))
    shared_title = left_title_tokens & right_title_tokens
    shared_context = left_context_tokens & right_context_tokens
    shared_structured = left_structured_tokens & right_structured_tokens
    title_overlap = overlap_ratio(left_title_tokens, right_title_tokens, shared_title)
    context_overlap = overlap_ratio(left_context_tokens, right_context_tokens, shared_context)
    evidence_related = evidence_overlap(left, right)
    if evidence_related and len(shared_title) >= 10 and title_overlap >= 0.25:
        return True
    if evidence_related and len(shared_structured) >= 2 and len(shared_context) >= 8 and context_overlap >= 0.08:
        return True
    if evidence_related and len(shared_title) >= 3 and len(shared_context) >= 16 and context_overlap >= 0.11:
        return True
    if len(shared_title) >= 6 and len(shared_context) >= 18 and title_overlap >= 0.10 and context_overlap >= 0.14:
        return True
    return False


def same_controlled_root_cause_cluster(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = finding_root_key(left)
    right_key = finding_root_key(right)
    if not left_key or left_key != right_key:
        return False
    if left_key == "cluster:formula_odds_conflict":
        return titles_indicate_same_formula_conflict(left, right)
    if left_key == "cluster:display_real_data_isolation":
        return "fake_data_isolation" in finding_atomic_decision_objects(left) and "fake_data_isolation" in finding_atomic_decision_objects(right)
    return left_key in {
        "cluster:intervention_mapping",
        "cluster:placeholder_configuration",
    }


def strong_canonical_issue_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = finding_root_key(left)
    right_key = finding_root_key(right)
    if not left_key or left_key != right_key or not left_key.startswith("issue:"):
        return False
    issue_id = left_key.removeprefix("issue:")
    left_text = finding_topic_text(left).lower()
    right_text = finding_topic_text(right).lower()
    if issue_id == "CORE_BET_CONFIG_MISMATCH":
        config_terms = ("筹码", "档位", "挡位", "投注额", "下注金额", "额度", "上限", "配置")
        return any(term in left_text for term in config_terms) and any(term in right_text for term in config_terms)
    if issue_id == "COMP_RECONNECT_REENTER_MISSING":
        recovery_terms = ("断线", "重连", "重进", "恢复", "退出", "杀进程")
        return any(term in left_text for term in recovery_terms) and any(term in right_text for term in recovery_terms)
    return True


def same_inferred_canonical_issue(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return strong_canonical_issue_match(left, right)


def classify_duplicate_findings(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_issue_id = str(left.get("issue_id") or "").strip()
    right_issue_id = str(right.get("issue_id") or "").strip()
    distinct_explicit_ids = bool(left_issue_id and right_issue_id and left_issue_id != right_issue_id)
    left_objects = finding_atomic_decision_objects(left)
    right_objects = finding_atomic_decision_objects(right)
    if left_objects and right_objects and left_objects != right_objects:
        return {
            "duplicate": False,
            "reason": "different_atomic_decision_objects",
            "confidence": "high",
            "possible_duplicate": bool(left_objects & right_objects),
            "distinct_explicit_issue_ids": distinct_explicit_ids,
            "left_decision_objects": sorted(left_objects),
            "right_decision_objects": sorted(right_objects),
        }
    if left_issue_id and right_issue_id and left_issue_id == right_issue_id:
        return {"duplicate": True, "reason": "same_explicit_issue_id", "confidence": "high", "possible_duplicate": False}
    if same_controlled_root_cause_cluster(left, right):
        return {"duplicate": True, "reason": "same_controlled_root_cluster", "confidence": "high", "possible_duplicate": False}
    left_canonical = normalize_compare_text(str(left.get("canonical_title") or ""))
    right_canonical = normalize_compare_text(str(right.get("canonical_title") or ""))
    if left_canonical and right_canonical and left_canonical == right_canonical:
        return {"duplicate": True, "reason": "same_canonical_title", "confidence": "high", "possible_duplicate": False}
    left_title = normalize_compare_text(str(left.get("title") or ""))
    right_title = normalize_compare_text(str(right.get("title") or ""))
    if left_title and right_title and left_title == right_title and evidence_overlap(left, right):
        return {"duplicate": True, "reason": "same_title_with_related_evidence", "confidence": "high", "possible_duplicate": False}
    if evidence_overlap(left, right) and titles_indicate_same_formula_conflict(left, right):
        return {"duplicate": True, "reason": "controlled_formula_conflict", "confidence": "high", "possible_duplicate": False}
    if evidence_overlap(left, right) and titles_indicate_same_fake_odds_gap(left, right):
        return {"duplicate": True, "reason": "controlled_fake_odds_gap", "confidence": "high", "possible_duplicate": False}
    if same_inferred_canonical_issue(left, right) and (
        granular_evidence_overlap(left, right)
        or finding_root_key(left) == "issue:COMP_RECONNECT_REENTER_MISSING"
    ):
        return {"duplicate": True, "reason": "same_strong_canonical_issue", "confidence": "high", "possible_duplicate": False}
    semantic_match = findings_share_semantic_signature(left, right)
    if semantic_match:
        return {
            "duplicate": False,
            "reason": "weak_semantic_similarity_requires_review",
            "confidence": "low",
            "possible_duplicate": True,
            "distinct_explicit_issue_ids": distinct_explicit_ids,
        }
    return {
        "duplicate": False,
        "reason": "distinct_atomic_findings",
        "confidence": "high" if distinct_explicit_ids else "medium",
        "possible_duplicate": False,
        "distinct_explicit_issue_ids": distinct_explicit_ids,
    }


def are_duplicate_findings(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(classify_duplicate_findings(left, right).get("duplicate"))


def merge_duplicate_findings(group: list[dict[str, Any]]) -> dict[str, Any]:
    best_entry = preferred_group_target(group)
    merged = dict(best_entry["finding"])
    for entry in group:
        if entry is best_entry:
            continue
        finding = entry["finding"]
        merged["severity"] = normalized_max("severity", [merged.get("severity"), finding.get("severity")])
        merged["confidence"] = normalized_max("confidence", [merged.get("confidence"), finding.get("confidence")])
        merged["blocking"] = normalized_max("blocking", [merged.get("blocking"), finding.get("blocking")])
        merged["evidence_scope"] = merge_scope(str(merged.get("evidence_scope") or ""), str(finding.get("evidence_scope") or ""))
        merged["evidence"] = merge_text(str(merged.get("evidence") or ""), str(finding.get("evidence") or ""))
        if not str(merged.get("issue_id") or "").strip():
            merged["issue_id"] = str(finding.get("issue_id") or "")
        if not str(merged.get("canonical_title") or "").strip():
            merged["canonical_title"] = str(finding.get("canonical_title") or "")
        if finding_priority(finding) > finding_priority(merged):
            merged["title"] = str(finding.get("title") or merged.get("title") or "")
            merged["planner_role"] = str(finding.get("planner_role") or merged.get("planner_role") or "")
            merged["primary_dimension"] = str(finding.get("primary_dimension") or merged.get("primary_dimension") or "")
        if not str(merged.get("_root_cause_cluster") or "").strip():
            merged["_root_cause_cluster"] = str(finding.get("_root_cause_cluster") or identify_root_cause_cluster(finding))
        if not str(merged.get("_root_cause_key") or "").strip():
            merged["_root_cause_key"] = str(finding.get("_root_cause_key") or build_root_cause_key(finding))
    merged["_root_cause_key"] = str(merged.get("_root_cause_key") or build_root_cause_key(merged))
    return merged


def preferred_group_target(group: list[dict[str, Any]]) -> dict[str, Any]:
    return max(group, key=group_entry_rank)


def group_entry_rank(entry: dict[str, Any]) -> tuple[int, int, int, int, int]:
    finding = entry["finding"]
    return (
        1 if str(finding.get("evidence_scope") or "") == "cross_document" or entry["location"] == "cross_document" else 0,
        SEVERITY_RANK.get(str(finding.get("severity") or ""), 0),
        BLOCKING_RANK.get(str(finding.get("blocking") or ""), 0),
        CONFIDENCE_RANK.get(str(finding.get("confidence") or ""), 0),
        len(str(finding.get("evidence") or "")),
    )


def entry_sort_key(entry: dict[str, Any]) -> tuple[int, int, int]:
    return (1 if entry["location"] == "cross_document" else 0, int(entry.get("dimension_index", -1)), int(entry.get("finding_index", -1)))


def remove_report_entry(report: dict[str, Any], entry: dict[str, Any]) -> None:
    if entry["location"] == "cross_document":
        findings = report.get("cross_document_issues") or []
        del findings[entry["finding_index"]]
        report["cross_document_issues"] = findings
        return
    dimensions = report.get("dimensions") or []
    findings = dimensions[entry["dimension_index"]].get("findings") or []
    del findings[entry["finding_index"]]
    dimensions[entry["dimension_index"]]["findings"] = findings


def add_report_entry(report: dict[str, Any], target: dict[str, Any], finding: dict[str, Any]) -> None:
    public = public_finding(finding)
    if target["location"] == "cross_document" or str(public.get("evidence_scope") or "") == "cross_document":
        report.setdefault("cross_document_issues", []).append(public)
        return
    dimensions = report.get("dimensions") or []
    dimensions[target["dimension_index"]].setdefault("findings", []).append(public)


def collect_all_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for dimension in report.get("dimensions") or []:
        for finding in dimension.get("findings") or []:
            if isinstance(finding, dict):
                findings.append(finding)
    for finding in report.get("cross_document_issues") or []:
        if isinstance(finding, dict):
            findings.append(finding)
    return findings


def collect_distinct_root_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    distinct: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in collect_all_findings(report):
        key = finding_root_key(finding) or str(finding.get("issue_id") or finding.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        distinct.append(finding)
    return distinct


def build_stable_cross_issues(canonical_hits: dict[str, dict[str, Any]], unmatched_cross_issues: list[dict[str, Any]], document_count: int) -> list[dict[str, Any]]:
    if document_count < 2:
        return []
    cross_issues = [finding for finding in canonical_hits.values() if finding.get("evidence_scope") == "cross_document"]
    cross_issues.extend(unmatched_cross_issues)
    return [public_finding(finding) for finding in sort_findings(cross_issues)]


def finding_identity(finding: dict[str, Any]) -> str:
    issue_id = str(finding.get("issue_id") or "").strip()
    title = str(finding.get("title") or finding.get("canonical_title") or "").strip()
    evidence = str(finding.get("evidence") or "").strip()
    dimension = str(finding.get("primary_dimension") or "").strip()
    if issue_id:
        return f"{dimension}|{issue_id}"
    if title:
        return f"{dimension}|{title}"
    return f"{dimension}|{evidence}"


def finding_snapshot(finding: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(finding.get("severity") or ""),
        str(finding.get("blocking") or ""),
        str(finding.get("title") or ""),
        str(finding.get("risk") or ""),
        str(finding.get("suggestion") or ""),
    )


def index_findings(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for finding in collect_all_findings(report):
        key = finding_identity(finding)
        if key not in indexed:
            indexed[key] = finding
    return indexed
