from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from rad_review.prompts import DIMENSIONS

from .base import normalize_compare_text
from .duplicates import finding_identity


class NormalizedFinding(TypedDict, total=False):
    issue_id: str
    canonical_title: str
    title: str
    primary_dimension: str
    evidence_scope: str
    severity: str
    confidence: str
    blocking: str
    planner_role: str
    current_state: str
    evidence: str
    risk: str
    suggestion: str
    finding_source: str
    finding_source_label: str
    source_model: str
    owner: str
    description: str
    impact: str
    issue_title: str
    raw_response: NotRequired[str]


class NormalizedDimension(TypedDict, total=False):
    name: str
    dimension_note: str
    findings: list[NormalizedFinding]


class NormalizedReport(TypedDict, total=False):
    overall_evaluation: str
    document_quality_score: str
    score_reason: str
    top_blockers: list[dict[str, Any]]
    dimensions: list[NormalizedDimension]
    cross_document_issues: list[NormalizedFinding]
    missing_information: list[str]
    test_points: dict[str, list[str]]
    quality_notes: list[str]
    image_analysis_gaps: list[str]
    review_mode: str
    primary_model: str
    secondary_model: str
    fusion_summary: dict[str, Any]
    raw_response: NotRequired[str]


class ReportDiff(TypedDict, total=False):
    score_before: str
    score_after: str
    score_reason_before: str
    score_reason_after: str
    top_blockers_before: list[str]
    top_blockers_after: list[str]
    counts: dict[str, int]
    added_findings: list[NormalizedFinding]
    removed_findings: list[NormalizedFinding]
    changed_findings: list[dict[str, Any]]
    added_quality_notes: list[str]


def iter_public_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for dimension in report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        findings.extend(
            finding for finding in dimension.get("findings") or [] if isinstance(finding, dict)
        )
    findings.extend(
        finding for finding in report.get("cross_document_issues") or [] if isinstance(finding, dict)
    )
    return findings


def validate_report_integrity(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dimensions = report.get("dimensions") or []
    if not isinstance(dimensions, list):
        return ["report.dimensions 必须是列表。"]

    normalized_dimension_names: list[str] = []
    dimension_keys: set[str] = set()
    cross_keys: set[str] = set()
    public_titles: set[str] = set()

    for index, raw_dimension in enumerate(dimensions):
        if not isinstance(raw_dimension, dict):
            errors.append(f"dimensions[{index}] 不是对象。")
            continue
        normalized_dimension_names.append(str(raw_dimension.get("name") or ""))
        for finding in raw_dimension.get("findings") or []:
            if not isinstance(finding, dict):
                errors.append(f"dimensions[{index}].findings 包含非对象条目。")
                continue
            title_key = _finding_title_key(finding)
            if title_key:
                public_titles.add(title_key)
            detail_ok = any(str(finding.get(key) or "").strip() for key in ("current_state", "evidence", "risk"))
            if _finding_has_public_title(finding) and not detail_ok:
                errors.append(f"问题《{_finding_title(finding)}》缺少可渲染公共细节字段。")
            identity = finding_identity(finding)
            if identity:
                dimension_keys.add(identity)

    if normalized_dimension_names != list(DIMENSIONS):
        errors.append("dimensions 维度集合不完整或顺序被破坏。")

    for index, finding in enumerate(report.get("cross_document_issues") or []):
        if not isinstance(finding, dict):
            errors.append(f"cross_document_issues[{index}] 不是对象。")
            continue
        title_key = _finding_title_key(finding)
        if title_key:
            public_titles.add(title_key)
        detail_ok = any(str(finding.get(key) or "").strip() for key in ("current_state", "evidence", "risk"))
        if _finding_has_public_title(finding) and not detail_ok:
            errors.append(f"跨文档问题《{_finding_title(finding)}》缺少可渲染公共细节字段。")
        identity = finding_identity(finding)
        if identity:
            cross_keys.add(identity)

    overlap = dimension_keys & cross_keys
    if overlap:
        errors.append(f"存在同时落在维度区和跨文档区的重复问题：{sorted(overlap)!r}")

    blocker_titles = {
        normalize_compare_text(str(blocker.get("title") or ""))
        for blocker in report.get("top_blockers") or []
        if isinstance(blocker, dict) and str(blocker.get("title") or "").strip()
    }
    blocker_titles.discard("")
    missing_blockers = sorted(blocker_titles - public_titles)
    if missing_blockers:
        errors.append("top_blockers 存在无法回指到最终 findings 的条目。")

    return errors


def assert_report_integrity(report: dict[str, Any]) -> None:
    errors = validate_report_integrity(report)
    if errors:
        raise ValueError("报告完整性检查失败：" + "；".join(errors))


def _finding_title(finding: dict[str, Any]) -> str:
    return str(finding.get("title") or finding.get("canonical_title") or finding.get("issue_title") or "").strip()


def _finding_has_public_title(finding: dict[str, Any]) -> bool:
    return bool(_finding_title(finding))


def _finding_title_key(finding: dict[str, Any]) -> str:
    return normalize_compare_text(_finding_title(finding))


def _finding_identity(finding: dict[str, Any]) -> str:
    return finding_identity(finding)


__all__ = [
    "NormalizedDimension",
    "NormalizedFinding",
    "NormalizedReport",
    "ReportDiff",
    "assert_report_integrity",
    "iter_public_findings",
    "validate_report_integrity",
]
