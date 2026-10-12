from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any, Iterable

from rad_review.docx_reader import ParsedDocument
from rad_review.prompts import (
    DIMENSIONS,
    PHASE2_COVERAGE_AUDIT_KEYS,
    PHASE2_COVERAGE_CONTROL_KEYS,
)

from .base import (
    BLOCKING_RANK,
    CONFIDENCE_RANK,
    NO_FINDINGS_NOTE,
    SEVERITY_RANK,
    dedupe_text_list,
    normalize_compare_text,
)
from .duplicates import (
    finding_atomic_decision_objects,
    finding_identity as _finding_identity_impl,
    finding_snapshot as _finding_snapshot_impl,
    index_findings as _index_findings_impl,
)
from .normalize import normalize_dimension_name, normalize_report, normalize_unmatched_finding, public_finding
from .rules import build_root_cause_key, is_fusion_high_risk_candidate
from .schema import assert_report_integrity
from .stabilize import (
    add_report_entry,
    are_duplicate_findings,
    collect_all_findings,
    collect_report_entries,
    entry_sort_key,
    is_blocking_high,
    merge_duplicate_findings,
    preferred_group_target,
    remove_report_entry,
    reorder_top_blockers_by_preference,
    sort_public_findings,
    stable_score,
    stabilize_report,
    top_blocker_from_finding,
)


def build_report_diff_payload(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_findings = index_findings(before)
    after_findings = index_findings(after)

    added_keys = [key for key in after_findings if key not in before_findings]
    removed_keys = [key for key in before_findings if key not in after_findings]
    changed_keys = [
        key
        for key in after_findings
        if key in before_findings and finding_snapshot(before_findings[key]) != finding_snapshot(after_findings[key])
    ]

    before_notes = dedupe_text_list(list(before.get("quality_notes") or []))
    after_notes = dedupe_text_list(list(after.get("quality_notes") or []))
    added_notes = [note for note in after_notes if note not in before_notes]

    return {
        "score_before": str(before.get("document_quality_score") or ""),
        "score_after": str(after.get("document_quality_score") or ""),
        "score_reason_before": str(before.get("score_reason") or ""),
        "score_reason_after": str(after.get("score_reason") or ""),
        "top_blockers_before": [blocker.get("title") for blocker in before.get("top_blockers") or [] if isinstance(blocker, dict)],
        "top_blockers_after": [blocker.get("title") for blocker in after.get("top_blockers") or [] if isinstance(blocker, dict)],
        "counts": {
            "before": len(before_findings),
            "after": len(after_findings),
            "added": len(added_keys),
            "removed": len(removed_keys),
            "changed": len(changed_keys),
        },
        "added_findings": [public_finding(after_findings[key]) for key in added_keys],
        "removed_findings": [public_finding(before_findings[key]) for key in removed_keys],
        "changed_findings": [
            {
                "key": key,
                "before": public_finding(before_findings[key]),
                "after": public_finding(after_findings[key]),
            }
            for key in changed_keys
        ],
        "added_quality_notes": added_notes,
    }


def merge_audit_report(
    report: dict[str, Any],
    audit: dict[str, Any],
    documents: list[ParsedDocument],
) -> dict[str, Any]:
    def collect_existing_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
        return list(collect_all_findings(payload))

    def score_rank(value: str) -> int:
        return {"A": 1, "B": 2, "C": 3, "D": 4}.get(value, 99)

    original_score = str(report.get("document_quality_score") or "").strip()
    original_score_reason = str(report.get("score_reason") or "").strip()
    original_top_blockers = list(report.get("top_blockers") or [])
    merged = normalize_report(report)
    existing_dimensions = {dimension.get("name"): dimension for dimension in merged.get("dimensions", []) if isinstance(dimension, dict)}
    existing_findings = collect_existing_findings(merged)
    added_high_risk_count = 0

    for raw_finding in audit.get("missed_high_risk_findings") or []:
        if not isinstance(raw_finding, dict):
            continue
        if any(are_duplicate_findings(raw_finding, existing) for existing in existing_findings):
            merged["quality_notes"] = dedupe_text_list(
                list(merged.get("quality_notes") or [])
                + ["strict 校验提示：忽略了一条与主报告已有根因高度重合的遗漏项，保留主报告原有表述。"]
            )
            continue
        dimension_name = normalize_dimension_name(raw_finding.get("primary_dimension"), fallback=DIMENSIONS[0])
        dimension = existing_dimensions.get(dimension_name)
        if dimension is None:
            dimension = {"name": dimension_name, "dimension_note": "", "findings": []}
            merged["dimensions"].append(dimension)
            existing_dimensions[dimension_name] = dimension
        dimension.setdefault("findings", []).append(raw_finding)
        existing_findings.append(raw_finding)
        if is_blocking_high(raw_finding) or str(raw_finding.get("severity") or "") == "高":
            added_high_risk_count += 1

    notes = list(merged.get("quality_notes") or [])
    for item in audit.get("unsupported_findings") or []:
        if not isinstance(item, dict):
            continue
        primary_issue_id = str(item.get("primary_issue_id") or item.get("target_primary_issue_id") or "").strip()
        resolved_primary = primary_findings_by_issue_id.get(primary_issue_id) if primary_issue_id else None
        title = str(
            item.get("title")
            or item.get("canonical_title")
            or (resolved_primary or {}).get("title")
            or (resolved_primary or {}).get("canonical_title")
            or primary_issue_id
            or "unknown finding"
        ).strip()
        reason = str(item.get("reason") or "missing evidence").strip()
        notes.append(f"strict 校验提示：主报告中的《{title}》可能证据不足，原因：{reason}")

    for item in audit.get("merge_recommendations") or []:
        if not isinstance(item, dict):
            continue
        titles = [str(title).strip() for title in item.get("titles") or [] if str(title).strip()]
        if len(titles) < 2:
            continue
        merged_title = str(item.get("merged_title") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if merged_title:
            notes.append(f"strict 校验备注：建议将《{' / '.join(titles)}》合并为《{merged_title}》。{reason}".strip())
        elif reason:
            notes.append(f"strict 校验备注：建议合并《{' / '.join(titles)}》，原因：{reason}".strip())

    score_adjustment = audit.get("score_adjustment")
    suggested_score = ""
    suggested_score_reason = ""
    if isinstance(score_adjustment, dict):
        suggested_score = str(score_adjustment.get("suggested_score") or "").strip()
        reason = str(score_adjustment.get("reason") or "").strip()
        if suggested_score in {"A", "B", "C", "D"}:
            suggested_score_reason = reason
            notes.append(f"strict 校验评分提示：建议评分 {suggested_score}。{reason}".strip())

    for note in audit.get("audit_notes") or []:
        if str(note).strip():
            notes.append(f"strict 校验备注：{note}")
    merged["quality_notes"] = dedupe_text_list(notes)

    stabilized = stabilize_report(merged, documents)
    stabilized["top_blockers"] = reorder_top_blockers_by_preference(stabilized, original_top_blockers)
    baseline_score = original_score or str(merged.get("document_quality_score") or "").strip()
    baseline_score_reason = original_score_reason or str(merged.get("score_reason") or "").strip()
    if baseline_score in {"A", "B", "C", "D"}:
        stabilized["document_quality_score"] = baseline_score
        if baseline_score_reason:
            stabilized["score_reason"] = baseline_score_reason
    elif not suggested_score:
        stabilized["document_quality_score"], stabilized["score_reason"] = stable_score(stabilized)

    if suggested_score:
        previous_score = str(stabilized.get("document_quality_score") or "")
        allow_override = score_rank(suggested_score) <= score_rank(previous_score) or added_high_risk_count > 0
        if allow_override:
            stabilized["document_quality_score"] = suggested_score
            if suggested_score_reason:
                stabilized["score_reason"] = suggested_score_reason
            if previous_score and previous_score != suggested_score:
                stabilized["quality_notes"] = dedupe_text_list(
                    list(stabilized.get("quality_notes") or [])
                    + [f"strict 校验已覆盖最终评分：{previous_score} -> {suggested_score}"]
                )
        else:
            stabilized["quality_notes"] = dedupe_text_list(
                list(stabilized.get("quality_notes") or [])
                + [
                    f"strict 校验保留主报告评分：{previous_score}",
                    f"建议评分 {suggested_score} 未采纳，因为没有新增唯一高风险根因。",
                ]
            )

    assert_report_integrity(stabilized)
    return stabilized


def confidence_rank_value(value: Any) -> int:
    return CONFIDENCE_RANK.get(str(value or ""), 0)


def downgrade_score_once(score: str) -> str:
    score = str(score or "").strip().upper()
    mapping = {"A": "B", "B": "C", "C": "D", "D": "D"}
    return mapping.get(score, score or "C")


def build_blocker_from_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return top_blocker_from_finding(finding)


def merge_secondary_blockers(
    primary_blockers: list[dict[str, Any]],
    secondary_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = [dict(blocker) for blocker in primary_blockers]
    seen = {
        normalize_compare_text(str(blocker.get("title") or ""))
        for blocker in merged
        if str(blocker.get("title") or "").strip()
    }
    for finding in secondary_findings:
        blocker = build_blocker_from_finding(finding)
        title_key = normalize_compare_text(str(blocker.get("title") or ""))
        if title_key and title_key in seen:
            continue
        if title_key:
            seen.add(title_key)
        merged.append(blocker)
    return merged[:3]


def demote_dual_pass_cross_document_issues(
    report: dict[str, Any],
    note: str = "dual_pass 当前已暂时停用跨文档一致性分区，相关问题已回归原维度展示",
) -> dict[str, Any]:
    normalized = normalize_report(json.loads(json.dumps(report, ensure_ascii=False)))
    dimensions = normalized.setdefault("dimensions", [])
    dimensions_by_name = {
        normalize_dimension_name(dimension.get("name"), fallback=DIMENSIONS[0]): dimension
        for dimension in dimensions
        if isinstance(dimension, dict)
    }

    for raw_finding in normalized.get("cross_document_issues") or []:
        if not isinstance(raw_finding, dict):
            continue
        dimension_name = normalize_dimension_name(raw_finding.get("primary_dimension"), fallback=DIMENSIONS[0])
        finding = normalize_unmatched_finding(dict(raw_finding), dimension_name)
        finding["evidence_scope"] = "document"
        dimension = dimensions_by_name.get(dimension_name)
        if dimension is None:
            dimension = {"name": dimension_name, "dimension_note": "", "findings": []}
            dimensions.append(dimension)
            dimensions_by_name[dimension_name] = dimension
        dimension.setdefault("findings", []).append(finding)
        dimension["dimension_note"] = ""

    normalized["cross_document_issues"] = []
    notes = [str(item).strip() for item in (normalized.get("quality_notes") or []) if str(item).strip()]
    note_key = normalize_compare_text(note)
    notes = [item for item in notes if normalize_compare_text(item) != note_key]
    notes.append(note)
    normalized["quality_notes"] = dedupe_text_list(notes)
    return normalized


def _dual_pass_raw_issue_id(raw_finding: dict[str, Any] | None) -> str:
    raw = raw_finding if isinstance(raw_finding, dict) else {}
    return str(
        raw.get("issue_id")
        or raw.get("candidate_issue_id")
        or raw.get("missed_issue_id")
        or raw.get("missed_id")
        or raw.get("primary_issue_id")
        or raw.get("source_missed_issue_id")
        or raw.get("source_issue_id")
        or raw.get("id")
        or ""
    ).strip()


def _dual_pass_numbered_text(texts: list[str]) -> str:
    normalized_texts = [str(text).strip().rstrip("；;") for text in texts if str(text).strip()]
    unique_texts = dedupe_text_list(normalized_texts)
    if not unique_texts:
        return ""
    if len(unique_texts) == 1:
        return unique_texts[0]
    return "；".join(f"{index}、{text}" for index, text in enumerate(unique_texts, start=1))


def _dual_pass_extract_candidate_issue_ids_from_text(text: str, candidate_issue_ids: set[str]) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return []
    return dedupe_text_list([candidate_issue_id for candidate_issue_id in candidate_issue_ids if candidate_issue_id in content])


def _dual_pass_absorb_secondary_findings_into_primary(
    target: dict[str, Any],
    source_findings: list[dict[str, Any]],
) -> None:
    if not isinstance(target, dict):
        return
    current_states = [str(source.get("current_state") or source.get("description") or "").strip() for source in source_findings]
    risks = [str(source.get("risk") or source.get("impact") or "").strip() for source in source_findings]
    suggestions = [str(source.get("suggestion") or "").strip() for source in source_findings]
    evidences = [str(source.get("evidence") or "").strip() for source in source_findings]

    merged_current_state = _dual_pass_numbered_text(current_states)
    merged_risk = _dual_pass_numbered_text(risks)
    merged_suggestion = _dual_pass_numbered_text(suggestions)
    merged_evidence = "；".join(dedupe_text_list(evidences))

    if merged_current_state:
        target["current_state"] = merged_current_state
    if merged_risk:
        target["risk"] = merged_risk
    if merged_suggestion:
        target["suggestion"] = merged_suggestion
    if merged_evidence:
        target["evidence"] = merged_evidence
    _ensure_finding_has_title(target)


def _apply_dual_pass_absorbed_splits(
    report: dict[str, Any],
    candidate_report: dict[str, Any] | None,
    candidate_lineage: dict[str, Any] | None,
) -> tuple[set[str], set[str]]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    candidate = candidate_report if isinstance(candidate_report, dict) else {}
    primary_by_issue_id: dict[str, dict[str, Any]] = {}
    candidate_by_issue_id: dict[str, dict[str, Any]] = {}

    for entry in collect_report_entries(report):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id and issue_id not in primary_by_issue_id:
            primary_by_issue_id[issue_id] = finding
    for entry in collect_report_entries(candidate):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id and issue_id not in candidate_by_issue_id:
            candidate_by_issue_id[issue_id] = finding

    candidate_issue_ids = list(candidate_by_issue_id)
    suppressed_candidate_issue_ids: set[str] = set()
    absorbed_primary_issue_ids: set[str] = set()

    for item in lineage.get("dropped") or []:
        if not isinstance(item, dict):
            continue
        primary_issue_id = str(item.get("primary_issue_id") or "").strip()
        target = primary_by_issue_id.get(primary_issue_id)
        if target is None:
            continue

        explicit_target_ids = [
            str(value).strip()
            for value in list(item.get("target_candidate_issue_ids") or []) + [item.get("target_candidate_issue_id")]
            if str(value or "").strip()
        ]
        split_issue_ids = explicit_target_ids + _dual_pass_extract_candidate_issue_ids_from_text(
            f"{item.get('disposition') or ''} {item.get('reason') or ''}",
            candidate_issue_ids,
        )
        if not split_issue_ids:
            for added_item in lineage.get("added") or []:
                if not isinstance(added_item, dict):
                    continue
                candidate_issue_id = str(added_item.get("candidate_issue_id") or "").strip()
                if not candidate_issue_id:
                    continue
                source_missed_issue_ids = [
                    str(value).strip() for value in (added_item.get("source_missed_issue_ids") or []) if str(value).strip()
                ]
                reason = str(added_item.get("reason") or "").strip()
                if source_missed_issue_ids:
                    continue
                if primary_issue_id and primary_issue_id in reason:
                    split_issue_ids.append(candidate_issue_id)
                    continue
                if "拆自" in reason or "拆分" in reason:
                    split_issue_ids.append(candidate_issue_id)

        split_issue_ids = dedupe_text_list(split_issue_ids)
        split_findings = [candidate_by_issue_id[candidate_issue_id] for candidate_issue_id in split_issue_ids if candidate_issue_id in candidate_by_issue_id]
        if not split_findings:
            continue
        if len(split_findings) > 1:
            # Multiple materialized split findings are independently closeable
            # units. Reabsorbing them would recreate the multi-element Primary
            # finding that the candidate explicitly split.
            continue
        target_objects = finding_atomic_decision_objects(target)
        source_objects = finding_atomic_decision_objects(split_findings[0])
        if target_objects and source_objects and target_objects != source_objects:
            continue
        _dual_pass_absorb_secondary_findings_into_primary(target, split_findings)
        suppressed_candidate_issue_ids.update(split_issue_ids)
        absorbed_primary_issue_ids.add(primary_issue_id)

    return suppressed_candidate_issue_ids, absorbed_primary_issue_ids


def _dedupe_dual_pass_report_collisions(report: dict[str, Any]) -> None:
    collision_groups: dict[str, list[dict[str, Any]]] = {}
    for entry in collect_report_entries(report):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id:
            collision_groups.setdefault(f"issue:{issue_id}", []).append(entry)
            continue
        title = normalize_compare_text(str(finding.get("title") or finding.get("canonical_title") or "").strip())
        if title:
            collision_groups.setdefault(f"title:{title}", []).append(entry)

    groups = [entries for entries in collision_groups.values() if len(entries) >= 2]
    for entries in sorted(groups, key=lambda current_entries: entry_sort_key(preferred_group_target(current_entries)), reverse=True):
        merged_finding = merge_duplicate_findings(entries)
        target = preferred_group_target(entries)
        for entry in sorted(entries, key=entry_sort_key, reverse=True):
            remove_report_entry(report, entry)
        add_report_entry(report, target, merged_finding)

    for dimension in report.get("dimensions") or []:
        findings = dimension.get("findings") or []
        dimension["findings"] = sort_public_findings(findings)
        dimension["dimension_note"] = "" if dimension["findings"] else NO_FINDINGS_NOTE
    report["cross_document_issues"] = sort_public_findings(report.get("cross_document_issues") or [])


def _dual_pass_numbered_text(texts: list[str]) -> str:
    normalized_texts = [str(text).strip().rstrip("\uff1b;") for text in texts if str(text).strip()]
    unique_texts = dedupe_text_list(normalized_texts)
    if not unique_texts:
        return ""
    if len(unique_texts) == 1:
        return unique_texts[0]
    return "\uff1b".join(f"{index}\u3001{text}" for index, text in enumerate(unique_texts, start=1))


def _dual_pass_split_multisymptom_text(text: Any) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return []
    parts = [segment.strip() for segment in re.split(r"(?:\r?\n)+|[；;]+", content) if segment.strip()]
    return dedupe_text_list(parts)


def _dual_pass_is_numbered_text(text: Any) -> bool:
    parts = _dual_pass_split_multisymptom_text(text)
    if len(parts) < 2:
        return False
    return all(re.match(r"^\d+[、.．]\s*", part) for part in parts)


def _dual_pass_format_multisymptom_text(text: Any) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    if _dual_pass_is_numbered_text(content):
        return content
    parts = _dual_pass_split_multisymptom_text(content)
    if len(parts) < 2:
        return content
    return _dual_pass_numbered_text(parts)


DUAL_PASS_MULTISYMPTOM_LIMITS = {
    "current_state": 5,
    "risk": 5,
    "suggestion": 5,
}

DUAL_PASS_MULTISYMPTOM_FIELD_LABELS = {
    "current_state": "现状描述",
    "risk": "风险分析",
    "suggestion": "修改建议",
}


def _dual_pass_trim_multisymptom_field(finding: dict[str, Any], field: str, max_parts: int) -> str:
    parts = _dual_pass_split_multisymptom_text(finding.get(field))
    if len(parts) <= max_parts:
        formatted = _dual_pass_format_multisymptom_text(finding.get(field))
        if formatted:
            finding[field] = formatted
        return ""
    finding[field] = _dual_pass_numbered_text(parts[:max_parts])
    title = str(finding.get("title") or finding.get("canonical_title") or finding.get("issue_id") or "未命名问题").strip()
    label = DUAL_PASS_MULTISYMPTOM_FIELD_LABELS.get(field, field)
    overflow_count = len(parts) - max_parts
    return (
        f"dual_pass 收敛提示：问题《{title}》的{label}原有 {len(parts)} 条分点，"
        f"最终报告先保留前 {max_parts} 条，其余 {overflow_count} 条保留在原始调试工件中。"
    )


def _format_dual_pass_multisymptom_finding(finding: dict[str, Any]) -> list[str]:
    if not isinstance(finding, dict):
        return []
    notes: list[str] = []
    for field in ("current_state", "risk", "suggestion"):
        max_parts = DUAL_PASS_MULTISYMPTOM_LIMITS.get(field, 5)
        note = _dual_pass_trim_multisymptom_field(finding, field, max_parts)
        if note:
            notes.append(note)
    return notes


def _format_dual_pass_multisymptom_report(report: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_report(json.loads(json.dumps(report, ensure_ascii=False)))
    notes = list(normalized.get("quality_notes") or [])
    for finding in collect_all_findings(normalized):
        if isinstance(finding, dict):
            notes.extend(_format_dual_pass_multisymptom_finding(finding))
    normalized["quality_notes"] = dedupe_text_list(notes)
    return normalized


def _dual_pass_absorb_secondary_findings_into_primary(
    target: dict[str, Any],
    source_findings: list[dict[str, Any]],
) -> None:
    if not isinstance(target, dict):
        return
    current_states = [str(source.get("current_state") or source.get("description") or "").strip() for source in source_findings]
    risks = [str(source.get("risk") or source.get("impact") or "").strip() for source in source_findings]
    suggestions = [str(source.get("suggestion") or "").strip() for source in source_findings]
    evidences = [str(source.get("evidence") or "").strip() for source in source_findings]

    merged_current_state = _dual_pass_numbered_text(current_states)
    merged_risk = _dual_pass_numbered_text(risks)
    merged_suggestion = _dual_pass_numbered_text(suggestions)
    merged_evidence = "\uff1b".join(dedupe_text_list(evidences))

    if merged_current_state:
        target["current_state"] = merged_current_state
    if merged_risk:
        target["risk"] = merged_risk
    if merged_suggestion:
        target["suggestion"] = merged_suggestion
    if merged_evidence:
        target["evidence"] = merged_evidence
    _ensure_finding_has_title(target)


def _should_skip_absorbed_split_note(note: str, absorbed_primary_issue_ids: set[str]) -> bool:
    clean_note = str(note or "").strip()
    if not clean_note or not absorbed_primary_issue_ids:
        return False
    if "拆分" not in clean_note and "已拆分为" not in clean_note:
        return False
    return any(primary_issue_id and primary_issue_id in clean_note for primary_issue_id in absorbed_primary_issue_ids)


def _is_absorbed_primary_quality_note(note: str, absorbed_primary_issue_ids: set[str]) -> bool:
    clean_note = str(note or "").strip()
    if not clean_note or not absorbed_primary_issue_ids:
        return False
    if "dual_pass candidate" not in clean_note and "dual_pass 已将" not in clean_note:
        return False
    return any(primary_issue_id and primary_issue_id in clean_note for primary_issue_id in absorbed_primary_issue_ids)


def _build_dual_pass_absorbed_primary_notes(prefix: str, absorbed_primary_issue_ids: set[str]) -> list[str]:
    scope = "candidate" if prefix == "candidate" else "pipeline"
    return [
        f"dual_pass {scope} 已将“{primary_issue_id}”的拆分补充点吸收到主问题中，不再额外输出独立补充问题。"
        for primary_issue_id in sorted(absorbed_primary_issue_ids)
    ]


def _dual_pass_extract_candidate_issue_ids_from_text(
    text: str,
    candidate_issue_ids: Iterable[str],
) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return []
    return dedupe_text_list(
        [candidate_issue_id for candidate_issue_id in candidate_issue_ids if candidate_issue_id and candidate_issue_id in content]
    )


def _dual_pass_secondary_origin_id(finding: dict[str, Any] | None) -> str:
    current = finding if isinstance(finding, dict) else {}
    return str(
        current.get("source_missed_issue_id")
        or current.get("source_issue_id")
        or current.get("missed_issue_id")
        or current.get("missed_id")
        or current.get("source_primary_issue_id")
        or ""
    ).strip()


def _dual_pass_normalized_title_signature(title: Any) -> str:
    normalized = normalize_compare_text(str(title or ""))
    return normalized.translate(str.maketrans("", "", "\"'“”‘’`:`："))


def _build_dual_pass_finding_origin_key(finding: dict[str, Any]) -> str:
    issue_id = str(finding.get("issue_id") or "").strip()
    dimension = normalize_dimension_name(finding.get("primary_dimension"), fallback=DIMENSIONS[0])
    if str(finding.get("finding_source") or "").strip() == "secondary_reviewer":
        origin_id = _dual_pass_secondary_origin_id(finding)
        if origin_id:
            return f"secondary-origin:{origin_id}"
        title_signature = _dual_pass_normalized_title_signature(
            finding.get("title") or finding.get("canonical_title") or issue_id
        )
        if title_signature:
            return f"secondary-title:{dimension}:{title_signature}"
    if issue_id:
        return f"primary-issue:{issue_id}"
    title_signature = _dual_pass_normalized_title_signature(finding.get("title") or finding.get("canonical_title") or "")
    if title_signature:
        return f"primary-title:{dimension}:{title_signature}"
    return f"fallback:{dimension}:{len(str(finding))}"


def _index_dual_pass_findings_for_comparison(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for finding in collect_all_findings(report):
        if not isinstance(finding, dict):
            continue
        key = _build_dual_pass_finding_origin_key(finding)
        indexed.setdefault(key, finding)
    return indexed


def _dual_pass_absorbed_missed_ids_by_kept_candidate(candidate_lineage: dict[str, Any] | None) -> dict[str, list[str]]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    absorbed_by_candidate: dict[str, list[str]] = {}
    for item in lineage.get("kept") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if not candidate_issue_id:
            continue
        absorbed_ids = [
            str(value).strip()
            for value in (item.get("absorbed_missed_issue_ids") or [])
            if str(value).strip()
        ]
        if absorbed_ids:
            absorbed_by_candidate[candidate_issue_id] = dedupe_text_list(absorbed_ids)
    return absorbed_by_candidate


def _dual_pass_build_secondary_origin_to_issue_ids(candidate_report: dict[str, Any] | None) -> dict[str, set[str]]:
    origin_to_issue_ids: dict[str, set[str]] = {}
    for finding in collect_all_findings(candidate_report or {}):
        if not isinstance(finding, dict):
            continue
        origin_id = _dual_pass_secondary_origin_id(finding)
        issue_id = str(finding.get("issue_id") or "").strip()
        if not origin_id or not issue_id:
            continue
        origin_to_issue_ids.setdefault(origin_id, set()).add(issue_id)
    return origin_to_issue_ids


def _dual_pass_build_candidate_issue_id_set(candidate_report: dict[str, Any] | None) -> set[str]:
    return {
        str(finding.get("issue_id") or "").strip()
        for finding in collect_all_findings(candidate_report or {})
        if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    }


def _dual_pass_advice_consistency_diagnostics(
    candidate_report: dict[str, Any] | None,
    candidate_lineage: dict[str, Any] | None,
    missed_findings: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    candidate_issue_ids = _dual_pass_build_candidate_issue_id_set(candidate_report)
    secondary_origin_to_issue_ids = _dual_pass_build_secondary_origin_to_issue_ids(candidate_report)
    absorbed_by_candidate = _dual_pass_absorbed_missed_ids_by_kept_candidate(lineage)
    absorbed_missed_ids = {
        missed_issue_id
        for missed_ids in absorbed_by_candidate.values()
        for missed_issue_id in missed_ids
        if missed_issue_id
    }
    added_items = [item for item in (lineage.get("added") or []) if isinstance(item, dict)]
    added_source_ids = {
        str(source_id).strip()
        for item in added_items
        for source_id in (item.get("source_missed_issue_ids") or [])
        if str(source_id).strip()
    }
    claimed_added_but_not_materialized: list[str] = []
    for item in added_items:
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if not candidate_issue_id:
            continue
        source_ids = {
            str(source_id).strip() for source_id in (item.get("source_missed_issue_ids") or []) if str(source_id).strip()
        }
        if candidate_issue_id in candidate_issue_ids or source_ids.intersection(candidate_issue_ids):
            continue
        claimed_added_but_not_materialized.append(candidate_issue_id)

    claimed_absorbed_but_materialized_separately: list[str] = []
    materialized_missed_without_added: list[str] = []
    for raw_finding in missed_findings or []:
        if not isinstance(raw_finding, dict):
            continue
        missed_issue_id = _dual_pass_raw_issue_id(raw_finding)
        if not missed_issue_id:
            continue
        independent_issue_ids = secondary_origin_to_issue_ids.get(missed_issue_id, set())
        if missed_issue_id in absorbed_missed_ids and independent_issue_ids:
            claimed_absorbed_but_materialized_separately.append(missed_issue_id)
        if independent_issue_ids and missed_issue_id not in added_source_ids and missed_issue_id not in absorbed_missed_ids:
            materialized_missed_without_added.append(missed_issue_id)

    advice_candidate_structure_mismatch = bool(
        claimed_absorbed_but_materialized_separately
        or claimed_added_but_not_materialized
        or materialized_missed_without_added
    )
    return {
        "advice_candidate_structure_mismatch": advice_candidate_structure_mismatch,
        "advice_claimed_absorbed_but_materialized_separately": dedupe_text_list(
            claimed_absorbed_but_materialized_separately
        ),
        "advice_claimed_added_but_not_materialized": dedupe_text_list(claimed_added_but_not_materialized),
        "materialized_missed_without_added": dedupe_text_list(materialized_missed_without_added),
        "absorbed_missed_issue_ids": sorted(absorbed_missed_ids),
    }


def _dual_pass_candidate_top_blocker_titles(report: dict[str, Any] | None) -> list[str]:
    blockers = []
    for item in (report or {}).get("top_blockers") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title:
            blockers.append(title)
    return dedupe_text_list(blockers)


def _dual_pass_collect_review_texts(review: dict[str, Any] | None) -> list[str]:
    source = review if isinstance(review, dict) else {}
    assessment = source.get("quality_assessment") if isinstance(source.get("quality_assessment"), dict) else {}
    texts: list[str] = []
    for value in (
        assessment.get("summary"),
        assessment.get("reason"),
    ):
        text = str(value or "").strip()
        if text:
            texts.append(text)
    for group in (
        assessment.get("issues") or [],
        source.get("review_notes") or [],
    ):
        for value in group:
            text = str(value or "").strip()
            if text:
                texts.append(text)
    for item in source.get("unsupported_findings") or []:
        if not isinstance(item, dict):
            continue
        for value in (item.get("title"), item.get("reason")):
            text = str(value or "").strip()
            if text:
                texts.append(text)
    return texts


def _dual_pass_text_mentions_finding(text: str, finding: dict[str, Any]) -> bool:
    current_text = str(text or "").strip()
    if not current_text:
        return False
    issue_id = str(finding.get("issue_id") or "").strip()
    if issue_id and issue_id in current_text:
        return True
    for key in ("title", "canonical_title"):
        title = str(finding.get(key) or "").strip()
        if not title:
            continue
        if title in current_text:
            return True
        normalized_title = normalize_compare_text(title)
        normalized_text = normalize_compare_text(current_text)
        if normalized_title and len(normalized_title) >= 4 and normalized_title in normalized_text:
            return True
    return False


def _dual_pass_find_candidate_finding_for_primary(
    primary_issue_id: str,
    candidate_report: dict[str, Any] | None,
    candidate_lineage: dict[str, Any] | None,
) -> dict[str, Any] | None:
    candidate_by_issue_id = {
        str(finding.get("issue_id") or "").strip(): finding
        for finding in collect_all_findings(candidate_report or {})
        if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    }
    if primary_issue_id in candidate_by_issue_id:
        return candidate_by_issue_id[primary_issue_id]
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    for item in lineage.get("kept") or []:
        if not isinstance(item, dict):
            continue
        primary_issue_ids = {str(value).strip() for value in (item.get("primary_issue_ids") or []) if str(value).strip()}
        if primary_issue_id not in primary_issue_ids:
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if candidate_issue_id and candidate_issue_id in candidate_by_issue_id:
            return candidate_by_issue_id[candidate_issue_id]
    return None


def _dual_pass_candidate_consistency_diagnostics(
    primary_report: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
    candidate_lineage: dict[str, Any] | None,
    secondary_review: dict[str, Any] | None,
) -> dict[str, Any]:
    primary = primary_report if isinstance(primary_report, dict) else {}
    candidate = candidate_report if isinstance(candidate_report, dict) else {}
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    review = secondary_review if isinstance(secondary_review, dict) else {}
    review_texts = _dual_pass_collect_review_texts(review)
    normalized_review_texts = [normalize_compare_text(text) for text in review_texts if normalize_compare_text(text)]
    compatible_terms = ("鍙吋瀹炵幇", "琛ㄨ堪姝т箟", "鏈姝т箟", "璇存槑涓嶆竻", "宸蹭慨姝?", "鏀瑰垽", "闄嶇骇")
    negation_terms = ("璇垽", "涓嶆垚绔?", "宸蹭慨姝?", "骞堕潪鍐茬獊", "涓嶆槸鍐茬獊", "鍏紡涓€鑷?", "琛ㄨ堪涓€鑷?", "搴斿垹闄?", "宸查檷绾?", "鍙吋瀹炵幇")
    conflict_terms = ("鍐茬獊", "涓嶄竴鑷?", "鑷村懡", "fatal", "楂橀樆濉?", "鏃犳硶鍚屾椂婊¤冻", "闃诲")
    candidate_top_blockers = _dual_pass_candidate_top_blocker_titles(candidate)
    candidate_blocker_keys = {normalize_compare_text(title) for title in candidate_top_blockers if normalize_compare_text(title)}
    candidate_finding_keys = {
        normalize_compare_text(str(finding.get("title") or finding.get("canonical_title") or "").strip())
        for finding in collect_all_findings(candidate)
        if isinstance(finding, dict)
    }
    primary_top_blockers = _dual_pass_candidate_top_blocker_titles(primary)
    primary_blocker_keys = {normalize_compare_text(title) for title in primary_top_blockers if normalize_compare_text(title)}

    def is_high_signal_finding(finding: dict[str, Any]) -> bool:
        title_key = normalize_compare_text(str(finding.get("title") or finding.get("canonical_title") or "").strip())
        severity = str(finding.get("severity") or "").strip().lower()
        blocking = str(finding.get("blocking") or "").strip().lower()
        return (
            title_key in primary_blocker_keys
            or severity == "high"
            or blocking in {"block_dev", "block_release"}
            or is_blocking_high(finding)
        )

    def finding_strength_rank(finding: dict[str, Any]) -> tuple[int, int]:
        severity = str(finding.get("severity") or "").strip().lower()
        blocking = str(finding.get("blocking") or "").strip().lower()
        return (SEVERITY_RANK.get(severity, 0), BLOCKING_RANK.get(blocking, 0))

    def candidate_finding_softened(primary_finding: dict[str, Any], candidate_finding: dict[str, Any]) -> bool:
        primary_strength = finding_strength_rank(primary_finding)
        candidate_strength = finding_strength_rank(candidate_finding)
        candidate_title = str(candidate_finding.get("title") or candidate_finding.get("canonical_title") or "").strip()
        candidate_title_key = normalize_compare_text(candidate_title)
        candidate_text = normalize_compare_text(
            " ".join(
                str(candidate_finding.get(field) or "").strip()
                for field in ("title", "canonical_title", "current_state", "risk", "suggestion")
            )
        )
        return (
            candidate_strength < primary_strength
            or (candidate_title_key and candidate_title_key not in candidate_blocker_keys)
            or not any(term in candidate_text for term in conflict_terms)
        )

    kept_issue_id_splits: list[str] = []
    for item in lineage.get("kept") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        primary_issue_ids = [str(value).strip() for value in (item.get("primary_issue_ids") or []) if str(value).strip()]
        if not candidate_issue_id or not primary_issue_ids or candidate_issue_id in primary_issue_ids:
            continue
        if any(
            candidate_issue_id.startswith(f"{primary_issue_id}_")
            or candidate_issue_id.startswith(f"{primary_issue_id}-")
            for primary_issue_id in primary_issue_ids
        ):
            kept_issue_id_splits.append(candidate_issue_id)

    negated_primary_issue_ids: list[str] = []
    negated_primary_titles: list[str] = []
    unsupported_high_signal_demotion_issue_ids: list[str] = []
    unsupported_high_signal_demotion_titles: list[str] = []
    for finding in collect_all_findings(primary):
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        if not issue_id:
            continue
        matched_texts = [text for text in review_texts if _dual_pass_text_mentions_finding(text, finding)]
        if not matched_texts:
            continue
        normalized_text = normalize_compare_text(" ".join(matched_texts))
        if not any(term in normalized_text for term in negation_terms):
            continue
        candidate_finding = _dual_pass_find_candidate_finding_for_primary(issue_id, candidate, lineage)
        if not candidate_finding:
            continue
        candidate_text = normalize_compare_text(
            " ".join(
                str(candidate_finding.get(field) or "").strip()
                for field in ("title", "canonical_title", "current_state", "risk", "suggestion")
            )
        )
        blocker_title = str(candidate_finding.get("title") or candidate_finding.get("canonical_title") or "").strip()
        blocker_key = normalize_compare_text(blocker_title)
        if any(term in candidate_text for term in conflict_terms) or (blocker_key and blocker_key in candidate_blocker_keys):
            negated_primary_issue_ids.append(issue_id)
            if blocker_title:
                negated_primary_titles.append(blocker_title)
        matched_texts_normalized = [normalize_compare_text(text) for text in matched_texts if normalize_compare_text(text)]
        has_supporting_rationale = any(
            any(term in text for term in compatible_terms) for text in matched_texts_normalized
        )
        if (
            is_high_signal_finding(finding)
            and candidate_finding_softened(finding, candidate_finding)
            and not has_supporting_rationale
        ):
            unsupported_high_signal_demotion_issue_ids.append(issue_id)
            unsupported_high_signal_demotion_titles.append(
                str(candidate_finding.get("title") or candidate_finding.get("canonical_title") or issue_id).strip()
            )

    invalid_top_blocker_titles = [
        title
        for title in candidate_top_blockers
        if normalize_compare_text(title) not in candidate_finding_keys
    ]
    negated_blocker_titles = [
        title for title in candidate_top_blockers if normalize_compare_text(title) in {normalize_compare_text(value) for value in negated_primary_titles}
    ]
    candidate_blocker_conclusion_mismatch = bool(invalid_top_blocker_titles or negated_blocker_titles)

    score_rank = {"A": 1, "B": 2, "C": 3, "D": 4}
    primary_score = str(primary.get("document_quality_score") or "").strip().upper()
    candidate_score = str(candidate.get("document_quality_score") or "").strip().upper()
    primary_rank = score_rank.get(primary_score, 99)
    candidate_rank = score_rank.get(candidate_score, 99)
    blocker_overlap = primary_blocker_keys.intersection(candidate_blocker_keys)
    rationale_present = any(any(term in text for term in compatible_terms) for text in normalized_review_texts)
    score_improved = candidate_rank < primary_rank
    score_delta = abs(primary_rank - candidate_rank) if primary_rank < 99 and candidate_rank < 99 else 0
    primary_finding_count = len([finding for finding in collect_all_findings(primary) if isinstance(finding, dict)])
    candidate_finding_count = len([finding for finding in collect_all_findings(candidate) if isinstance(finding, dict)])
    materially_changed_count = len(
        [
            key
            for key in index_findings(primary)
            if key in index_findings(candidate)
            and finding_snapshot(index_findings(primary)[key]) != finding_snapshot(index_findings(candidate)[key])
        ]
    )
    candidate_major_judgment_drift = (
        not candidate_blocker_conclusion_mismatch
        and (
            (score_delta >= 2 and not rationale_present)
            or (score_improved and primary_blocker_keys and candidate_blocker_keys and not blocker_overlap and not rationale_present)
            or (
                bool(unsupported_high_signal_demotion_issue_ids)
                and score_improved
                and not rationale_present
            )
        )
    )
    candidate_overcompressed = (
        candidate_finding_count > 0
        and primary_finding_count - candidate_finding_count >= 2
        and materially_changed_count >= 2
        and (
            score_improved
            or not blocker_overlap
            or bool(unsupported_high_signal_demotion_issue_ids)
        )
    )
    candidate_overcompressed_reason = ""
    if candidate_overcompressed:
        candidate_overcompressed_reason = (
            f"candidate 问题数从 {primary_finding_count} 收缩到 {candidate_finding_count}，"
            f"且共享问题发生 {materially_changed_count} 处重大改写。"
        )

    return {
        "candidate_issue_id_split_detected": bool(kept_issue_id_splits),
        "candidate_issue_id_split_issue_ids": dedupe_text_list(kept_issue_id_splits),
        "candidate_negated_primary_finding_still_materialized": bool(negated_primary_issue_ids),
        "candidate_negated_primary_issue_ids": dedupe_text_list(negated_primary_issue_ids),
        "candidate_negated_primary_titles": dedupe_text_list(negated_primary_titles),
        "candidate_blocker_conclusion_mismatch": candidate_blocker_conclusion_mismatch,
        "candidate_blocker_conclusion_mismatch_titles": dedupe_text_list(
            invalid_top_blocker_titles + negated_blocker_titles
        ),
        "candidate_high_signal_demotion_without_support": bool(unsupported_high_signal_demotion_issue_ids),
        "candidate_high_signal_demotion_issue_ids": dedupe_text_list(unsupported_high_signal_demotion_issue_ids),
        "candidate_high_signal_demotion_titles": dedupe_text_list(unsupported_high_signal_demotion_titles),
        "candidate_overcompressed": candidate_overcompressed,
        "candidate_overcompressed_reason": candidate_overcompressed_reason,
        "candidate_major_judgment_drift": candidate_major_judgment_drift,
    }


def _dual_pass_is_strong_root_conflict(raw_finding: dict[str, Any] | None) -> bool:
    raw = raw_finding if isinstance(raw_finding, dict) else {}
    text = " ".join(
        str(raw.get(key) or "").strip()
        for key in (
            "title",
            "canonical_title",
            "issue_title",
            "reason",
            "description",
            "current_state",
            "conflict_description",
            "risk",
            "impact",
        )
    )
    normalized = normalize_compare_text(text)
    strong_conflict_terms = (
        "根本冲突",
        "无法同时实现",
        "无法由同一套代码实现",
        "互相冲突",
        "同一版本无法同时满足",
        "实现口径冲突",
        "规则冲突",
        "配置冲突",
    )
    return any(normalize_compare_text(term) in normalized for term in strong_conflict_terms)


def _build_dual_pass_candidate_overall_evaluation(report: dict[str, Any]) -> str:
    blocker_titles = [
        str(item.get("title") or "").strip()
        for item in (report.get("top_blockers") or [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    blocker_text = "、".join(blocker_titles[:3])
    score = str(report.get("document_quality_score") or "").strip()

    if score == "D":
        if blocker_text:
            return f"文档当前仍存在{blocker_text}等关键阻塞问题，规则尚不足以支撑开发与测试形成一致方案，建议先补充对齐后再推进。"
        return "文档当前仍存在关键阻塞问题，规则尚不足以支撑开发与测试形成一致方案，建议先补充对齐后再推进。"
    if score == "C":
        if blocker_text:
            return f"文档主流程可理解，但仍存在{blocker_text}等高风险问题，建议补充对齐后再推进开发与测试。"
        return "文档主流程可理解，但仍存在高风险规则缺口，建议补充对齐后再推进开发与测试。"
    if score == "B":
        if blocker_text:
            return f"文档主流程基本可落地，当前主要剩余{blocker_text}等少量关键问题，补齐后即可推进完整开发与测试。"
        return "文档主流程基本可落地，当前仅剩少量关键问题，补齐后即可推进完整开发与测试。"
    if score == "A":
        return "文档当前整体较为完整，未发现会阻塞开发与测试落地的关键问题。"
    if blocker_text:
        return f"文档当前仍存在{blocker_text}等待确认问题，建议补充对齐后再推进。"
    return "文档当前仍存在待确认问题，建议补充对齐后再推进。"


def build_conservative_dual_pass_candidate_report(
    primary_report: dict[str, Any],
    candidate_report: dict[str, Any],
    candidate_lineage: dict[str, Any] | None,
    missed_findings: list[dict[str, Any]] | None,
    secondary_model: str = "",
) -> dict[str, Any]:
    aligned = normalize_report(json.loads(json.dumps(primary_report, ensure_ascii=False)))
    candidate = normalize_report(json.loads(json.dumps(candidate_report, ensure_ascii=False)))
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}

    primary_by_issue_id: dict[str, dict[str, Any]] = {}
    candidate_by_issue_id: dict[str, dict[str, Any]] = {}
    for entry in collect_report_entries(aligned):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        _ensure_finding_has_title(finding)
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id and issue_id not in primary_by_issue_id:
            primary_by_issue_id[issue_id] = finding
    for entry in collect_report_entries(candidate):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        _ensure_finding_has_title(finding)
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id and issue_id not in candidate_by_issue_id:
            candidate_by_issue_id[issue_id] = finding

    suppressed_candidate_issue_ids, absorbed_primary_issue_ids = _apply_dual_pass_absorbed_splits(
        aligned,
        candidate,
        lineage,
    )

    def overlay_candidate_details(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key in (
            "title",
            "canonical_title",
            "current_state",
            "evidence",
            "risk",
            "suggestion",
            "severity",
            "blocking",
            "planner_role",
            "confidence",
            "owner",
            "description",
            "impact",
            "issue_title",
            "finding_source",
            "finding_source_label",
            "source_model",
        ):
            value = source.get(key)
            if str(value or "").strip():
                target[key] = value
        if not str(target.get("issue_id") or "").strip() and str(source.get("issue_id") or "").strip():
            target["issue_id"] = source.get("issue_id")
        if not str(target.get("primary_dimension") or "").strip() and str(source.get("primary_dimension") or "").strip():
            target["primary_dimension"] = source.get("primary_dimension")
        _ensure_finding_has_title(target)

    def has_exact_issue_id(issue_id: str) -> bool:
        normalized_issue_id = str(issue_id or "").strip()
        if not normalized_issue_id:
            return False
        return any(str(current.get("issue_id") or "").strip() == normalized_issue_id for current in existing_findings)

    def has_renderable_public_details(finding: dict[str, Any]) -> bool:
        return any(str(finding.get(key) or "").strip() for key in ("current_state", "evidence", "risk"))

    kept_fallback_candidates: list[dict[str, Any]] = []
    for item in lineage.get("kept") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        primary_issue_ids = [str(value).strip() for value in (item.get("primary_issue_ids") or []) if str(value).strip()]
        source = candidate_by_issue_id.get(candidate_issue_id)
        if not source or not primary_issue_ids:
            continue
        matched = False
        for primary_issue_id in primary_issue_ids:
            target = primary_by_issue_id.get(primary_issue_id)
            if target is not None:
                overlay_candidate_details(target, source)
                matched = True
                break
        if not matched:
            kept_fallback_candidates.append(source)

    existing_findings = list(collect_all_findings(aligned))
    missed_by_issue_id: dict[str, dict[str, Any]] = {}
    candidate_issue_id_to_source_missed_ids: dict[str, list[str]] = {}
    consumed_missed_title_signatures: set[str] = set()
    consumed_missed_issue_ids: set[str] = set()
    absorbed_missed_ids_by_candidate = _dual_pass_absorbed_missed_ids_by_kept_candidate(lineage)
    absorbed_missed_issue_ids = {
        missed_issue_id
        for missed_ids in absorbed_missed_ids_by_candidate.values()
        for missed_issue_id in missed_ids
        if missed_issue_id
    }
    for raw_finding in missed_findings or []:
        if not isinstance(raw_finding, dict):
            continue
        raw_issue_ids = {
            _dual_pass_raw_issue_id(raw_finding),
            str(raw_finding.get("missed_issue_id") or "").strip(),
            str(raw_finding.get("missed_id") or "").strip(),
            str(raw_finding.get("primary_issue_id") or "").strip(),
        }
        for raw_issue_id in raw_issue_ids:
            if raw_issue_id and raw_issue_id not in missed_by_issue_id:
                missed_by_issue_id[raw_issue_id] = raw_finding
    for item in lineage.get("added") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        source_missed_issue_ids = [
            str(value).strip() for value in (item.get("source_missed_issue_ids") or []) if str(value).strip()
        ]
        if candidate_issue_id:
            candidate_issue_id_to_source_missed_ids[candidate_issue_id] = source_missed_issue_ids
        consumed_missed_issue_ids.update(source_missed_issue_ids)
    consumed_missed_issue_ids.update(absorbed_missed_issue_ids)

    addition_candidates: list[dict[str, Any]] = []
    addition_candidates.extend(kept_fallback_candidates)
    for item in lineage.get("added") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if candidate_issue_id and candidate_issue_id in suppressed_candidate_issue_ids:
            continue
        source = candidate_by_issue_id.get(candidate_issue_id)
        raw_finding = missed_by_issue_id.get(candidate_issue_id)
        if raw_finding is None:
            for source_missed_issue_id in candidate_issue_id_to_source_missed_ids.get(candidate_issue_id) or []:
                raw_finding = missed_by_issue_id.get(source_missed_issue_id)
                if raw_finding is not None:
                    break
        normalized = build_dual_pass_secondary_finding(
            raw_finding or {},
            secondary_model=secondary_model,
            candidate_finding=source,
            fallback_dimension=(source or raw_finding or {}).get("primary_dimension")
            or (source or raw_finding or {}).get("dimension")
            or DIMENSIONS[0],
            preferred_issue_id=candidate_issue_id,
        )
        if normalized:
            addition_candidates.append(normalized)
    for raw_finding in missed_findings or []:
        if isinstance(raw_finding, dict):
            raw_issue_id = _dual_pass_raw_issue_id(raw_finding)
            if raw_issue_id and raw_issue_id in consumed_missed_issue_ids:
                title_signature = _dual_pass_normalized_title_signature(
                    raw_finding.get("title") or raw_finding.get("canonical_title") or raw_finding.get("issue_title") or ""
                )
                if title_signature:
                    consumed_missed_title_signatures.add(title_signature)
                continue
            normalized = build_dual_pass_secondary_finding(raw_finding, secondary_model=secondary_model)
            if normalized and has_renderable_public_details(normalized):
                addition_candidates.append(normalized)

    for raw_finding in addition_candidates:
        dimension_name = normalize_dimension_name(raw_finding.get("primary_dimension"), fallback=DIMENSIONS[0])
        finding = normalize_unmatched_finding(dict(raw_finding), dimension_name)
        _ensure_finding_has_title(finding)
        if has_exact_issue_id(str(finding.get("issue_id") or "")):
            continue
        append_secondary_finding(aligned, finding, disable_cross_document=True)
        existing_findings.append(finding)

    lineage_candidate_issue_ids = {
        str(item.get("candidate_issue_id") or "").strip()
        for key in ("kept", "added", "merged")
        for item in (lineage.get(key) or [])
        if isinstance(item, dict) and str(item.get("candidate_issue_id") or "").strip()
    }
    for entry in collect_report_entries(candidate):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        candidate_issue_id = str(finding.get("issue_id") or "").strip()
        origin_issue_id = _dual_pass_secondary_origin_id(finding)
        if candidate_issue_id and candidate_issue_id in suppressed_candidate_issue_ids:
            continue
        if candidate_issue_id and candidate_issue_id in lineage_candidate_issue_ids:
            continue
        if origin_issue_id and origin_issue_id in absorbed_missed_issue_ids:
            continue
        title_signature = _dual_pass_normalized_title_signature(
            finding.get("title") or finding.get("canonical_title") or ""
        )
        if not candidate_issue_id and title_signature and title_signature in consumed_missed_title_signatures:
            continue
        if candidate_issue_id and has_exact_issue_id(candidate_issue_id):
            continue
        normalized_finding = normalize_unmatched_finding(
            dict(finding),
            normalize_dimension_name(finding.get("primary_dimension"), fallback=DIMENSIONS[0]),
        )
        _ensure_finding_has_title(normalized_finding)
        append_secondary_finding(aligned, normalized_finding, disable_cross_document=True)
        existing_findings.append(normalized_finding)

    dropped_notes: list[str] = []
    aligned_issue_ids = {
        str(finding.get("issue_id") or "").strip()
        for finding in collect_all_findings(aligned)
        if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    }
    for item in lineage.get("dropped") or []:
        if not isinstance(item, dict):
            continue
        primary_issue_id = str(item.get("primary_issue_id") or "").strip()
        if primary_issue_id in absorbed_primary_issue_ids:
            continue
        if primary_issue_id in aligned_issue_ids:
            continue
        disposition = str(item.get("disposition") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if primary_issue_id:
            note = f"dual_pass candidate 血缘备注：主模型问题《{primary_issue_id}》被标记为 dropped"
            if disposition:
                note = f"{note}（{disposition}）"
            if reason:
                note = f"{note}，原因：{reason}"
            dropped_notes.append(note)
    if dropped_notes:
        aligned["quality_notes"] = dedupe_text_list(list(aligned.get("quality_notes") or []) + dropped_notes)

    if absorbed_primary_issue_ids:
        aligned["quality_notes"] = dedupe_text_list(
            [
                note
                for note in list(aligned.get("quality_notes") or [])
                if not _is_absorbed_primary_quality_note(note, absorbed_primary_issue_ids)
            ]
            + _build_dual_pass_absorbed_primary_notes("candidate", absorbed_primary_issue_ids)
        )

    for key in ("missing_information", "test_points", "image_analysis_gaps"):
        if candidate.get(key):
            aligned[key] = candidate.get(key)
    if candidate.get("quality_notes"):
        aligned["quality_notes"] = dedupe_text_list(
            list(aligned.get("quality_notes") or []) + list(candidate.get("quality_notes") or [])
        )
    for finding in collect_all_findings(aligned):
        if isinstance(finding, dict):
            _ensure_finding_has_title(finding)
    preferred_top_blockers = [dict(item) for item in (candidate.get("top_blockers") or []) if isinstance(item, dict)] or [
        dict(item) for item in (aligned.get("top_blockers") or []) if isinstance(item, dict)
    ]
    _dedupe_dual_pass_report_collisions(aligned)
    aligned = _format_dual_pass_multisymptom_report(aligned)
    aligned["top_blockers"] = reorder_top_blockers_by_preference(aligned, preferred_top_blockers)
    aligned["document_quality_score"], aligned["score_reason"] = stable_score(aligned)
    aligned["overall_evaluation"] = _build_dual_pass_candidate_overall_evaluation(aligned)
    assert_report_integrity(aligned)
    return aligned


def build_dual_pass_secondary_finding(
    raw_finding: dict[str, Any] | None,
    *,
    secondary_model: str = "",
    candidate_finding: dict[str, Any] | None = None,
    fallback_dimension: str = DIMENSIONS[0],
    preferred_issue_id: str = "",
) -> dict[str, Any]:
    raw = raw_finding if isinstance(raw_finding, dict) else {}
    candidate = candidate_finding if isinstance(candidate_finding, dict) else {}
    combined: dict[str, Any] = json.loads(json.dumps(candidate, ensure_ascii=False)) if candidate else {}

    raw_issue_id = _dual_pass_raw_issue_id(raw)
    raw_title = str(raw.get("title") or raw.get("canonical_title") or raw.get("issue_title") or "").strip()
    raw_dimension = raw.get("primary_dimension") or raw.get("dimension") or fallback_dimension
    raw_reason = raw.get("reason")
    raw_current_state = (
        raw.get("current_state") or raw.get("description") or raw.get("describe") or raw.get("conflict_description") or raw_reason
    )
    raw_risk = raw.get("risk") or raw.get("impact") or raw_reason
    strong_root_conflict = _dual_pass_is_strong_root_conflict(raw)

    if raw_issue_id and not str(combined.get("issue_id") or "").strip():
        combined["issue_id"] = raw_issue_id
    if preferred_issue_id and not str(candidate.get("issue_id") or "").strip():
        combined["issue_id"] = preferred_issue_id
    if raw_title and not str(combined.get("title") or "").strip():
        combined["title"] = raw_title
    if raw_title and not str(combined.get("canonical_title") or "").strip():
        combined["canonical_title"] = raw_title
    if raw_dimension and not str(combined.get("primary_dimension") or "").strip():
        combined["primary_dimension"] = raw_dimension
    if raw_current_state and not str(combined.get("current_state") or "").strip():
        combined["current_state"] = raw_current_state
    if raw.get("evidence") and not str(combined.get("evidence") or "").strip():
        combined["evidence"] = raw.get("evidence")
    if raw_risk and not str(combined.get("risk") or "").strip():
        combined["risk"] = raw_risk
    if raw.get("suggestion") and not str(combined.get("suggestion") or "").strip():
        combined["suggestion"] = raw.get("suggestion")
    if raw.get("planner_role") and not str(combined.get("planner_role") or "").strip():
        combined["planner_role"] = raw.get("planner_role")
    if raw.get("owner") and not str(combined.get("owner") or "").strip():
        combined["owner"] = raw.get("owner")
    if raw.get("severity") and not str(combined.get("severity") or "").strip():
        combined["severity"] = raw.get("severity")
    if raw.get("confidence") and not str(combined.get("confidence") or "").strip():
        combined["confidence"] = raw.get("confidence")
    if raw.get("blocking") and not str(combined.get("blocking") or "").strip():
        combined["blocking"] = raw.get("blocking")
    if raw.get("evidence_scope") and not str(combined.get("evidence_scope") or "").strip():
        combined["evidence_scope"] = raw.get("evidence_scope")
    if raw.get("description") and not str(combined.get("description") or "").strip():
        combined["description"] = raw.get("description")
    if raw.get("impact") and not str(combined.get("impact") or "").strip():
        combined["impact"] = raw.get("impact")
    if raw_issue_id and not str(combined.get("source_missed_issue_id") or "").strip():
        combined["source_missed_issue_id"] = raw_issue_id
    if raw_issue_id and not str(combined.get("source_issue_id") or "").strip():
        combined["source_issue_id"] = raw_issue_id

    dimension_name = normalize_dimension_name(combined.get("primary_dimension") or raw_dimension, fallback=DIMENSIONS[0])
    normalized = normalize_unmatched_finding(combined, dimension_name)
    candidate_title = str(candidate.get("title") or candidate.get("canonical_title") or "").strip()
    if candidate_title and normalize_compare_text(str(normalized.get("title") or "")) in {
        normalize_compare_text("未命名问题"),
        normalize_compare_text("未命名"),
        normalize_compare_text("unknown finding"),
    }:
        normalized["title"] = candidate_title
        if not str(normalized.get("canonical_title") or "").strip():
            normalized["canonical_title"] = candidate_title
    if strong_root_conflict:
        if SEVERITY_RANK.get(str(normalized.get("severity") or "").strip(), 0) < SEVERITY_RANK["高"]:
            normalized["severity"] = "高"
        if BLOCKING_RANK.get(str(normalized.get("blocking") or "").strip(), 0) < BLOCKING_RANK["阻塞开发"]:
            normalized["blocking"] = "阻塞开发"
    for phase2_field in ("audit_key", "control_key"):
        if str(raw.get(phase2_field) or "").strip():
            normalized[phase2_field] = str(raw.get(phase2_field) or "").strip()
    _ensure_finding_has_title(normalized)
    normalized["finding_source"] = "secondary_reviewer"
    normalized["finding_source_label"] = "副评审补充"
    normalized["source_model"] = secondary_model
    return normalized


def append_secondary_finding(
    report: dict[str, Any],
    finding: dict[str, Any],
    *,
    disable_cross_document: bool = False,
) -> None:
    public = public_finding(finding)
    dimension_name = normalize_dimension_name(public.get("primary_dimension"), fallback=DIMENSIONS[0])
    if str(public.get("evidence_scope") or "") == "cross_document" and not disable_cross_document:
        report.setdefault("cross_document_issues", []).append(public)
        return
    if disable_cross_document:
        public["evidence_scope"] = "document"
    dimensions = report.setdefault("dimensions", [])
    for dimension in dimensions:
        if normalize_dimension_name(dimension.get("name"), fallback=DIMENSIONS[0]) == dimension_name:
            dimension.setdefault("findings", []).append(public)
            dimension["dimension_note"] = ""
            return
    dimensions.append({"name": dimension_name, "dimension_note": "", "findings": [public]})


PHASE2_ADDED_REQUIRED_FIELDS = (
    "candidate_issue_id",
    "audit_key",
    "title",
    "primary_dimension",
    "current_state",
    "evidence",
    "risk",
    "suggestion",
    "severity",
    "blocking",
    "confidence",
    "independent_root_cause",
    "root_causes",
    "primary_overlap_check",
    "fact_check",
)

PHASE2_FACT_CHECK_TYPES = {
    "direct_conflict",
    "value_mismatch",
    "missing_rule",
    "mapping_gap",
    "boundary_gap",
}

PHASE2_COVERAGE_STATUSES = {
    "covered_by_primary",
    "confirmed_add",
    "advice_only",
    "no_issue",
    "not_applicable",
}

PHASE2_BROAD_ROOT_KEYS = {
    "issue:TEST_ACCEPTANCE_CRITERIA_MISSING",
    "issue:COMP_RECONNECT_REENTER_MISSING",
    "issue:UX_FAILURE_GUIDANCE_MISSING",
    "issue:CORE_BET_CONFIG_MISMATCH",
    "issue:CORE_DIFFICULTY_CONFIG_MISMATCH",
}


def _evaluate_phase2_coverage_ledger_v1(
    secondary_review: dict[str, Any] | None,
    shared_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the fixed phase-two audit ledger and its bidirectional finding links."""
    review = secondary_review if isinstance(secondary_review, dict) else {}
    raw_ledger = review.get("coverage_ledger")
    ledger = [item for item in raw_ledger if isinstance(item, dict)] if isinstance(raw_ledger, list) else []
    missed = [item for item in review.get("missed_findings") or [] if isinstance(item, dict)]
    expected_keys = list(PHASE2_COVERAGE_AUDIT_KEYS)
    observed_keys = [str(item.get("audit_key") or "").strip() for item in ledger]
    errors: list[str] = []
    protocol_repairs: list[str] = []
    if len(ledger) != len(expected_keys):
        errors.append(f"coverage_entry_count_invalid:{len(ledger)}")
    if observed_keys != expected_keys:
        errors.append("coverage_audit_key_order_invalid")
    if len(set(key for key in observed_keys if key)) != len([key for key in observed_keys if key]):
        errors.append("coverage_audit_key_duplicate")

    normalized_entries: list[dict[str, Any]] = []
    confirmed_occurrences: dict[str, list[str]] = {}
    for index, item in enumerate(ledger):
        audit_key = str(item.get("audit_key") or "").strip()
        status = str(item.get("status") or "").strip().lower()
        primary_values = item.get("primary_issue_ids")
        candidate_values = item.get("candidate_issue_ids")
        primary_ids = (
            dedupe_text_list([str(value).strip() for value in primary_values if str(value).strip()])
            if isinstance(primary_values, list)
            else []
        )
        candidate_ids = (
            dedupe_text_list([str(value).strip() for value in candidate_values if str(value).strip()])
            if isinstance(candidate_values, list)
            else []
        )
        evidence_checked = item.get("evidence_checked")
        if (
            status == "covered_by_primary"
            and candidate_ids
            and primary_ids
            and set(candidate_ids).issubset(set(primary_ids))
        ):
            protocol_repairs.append(
                f"cleared_redundant_candidate_ids:{audit_key}:{','.join(candidate_ids)}"
            )
            candidate_ids = []
        if status == "not_applicable" and not _phase2_field_present(evidence_checked):
            document_names = _phase2_document_names(shared_input)
            if document_names:
                evidence_checked = [f"{name} / 全文" for name in document_names]
                protocol_repairs.append(f"filled_not_applicable_evidence:{audit_key}")
        entry_errors: list[str] = []
        if audit_key not in PHASE2_COVERAGE_AUDIT_KEYS:
            entry_errors.append("audit_key_invalid")
        if status not in PHASE2_COVERAGE_STATUSES:
            entry_errors.append("status_invalid")
        if not isinstance(primary_values, list):
            entry_errors.append("primary_issue_ids_not_array")
        if not isinstance(candidate_values, list):
            entry_errors.append("candidate_issue_ids_not_array")
        if not _phase2_field_present(evidence_checked):
            entry_errors.append("evidence_checked_missing")
        if not str(item.get("reason") or "").strip():
            entry_errors.append("reason_missing")
        if status == "confirmed_add" and not candidate_ids:
            entry_errors.append("confirmed_add_candidate_ids_empty")
        if status != "confirmed_add" and candidate_ids:
            entry_errors.append("non_confirmed_candidate_ids_present")
        if status == "covered_by_primary" and not primary_ids:
            entry_errors.append("covered_by_primary_issue_ids_empty")
        for candidate_id in candidate_ids if status == "confirmed_add" else []:
            confirmed_occurrences.setdefault(candidate_id, []).append(audit_key)
        if entry_errors:
            label = audit_key or f"index_{index}"
            errors.extend(f"coverage_entry_invalid:{label}:{reason}" for reason in entry_errors)
        normalized_entries.append(
            {
                "audit_key": audit_key,
                "status": status,
                "primary_issue_ids": primary_ids,
                "candidate_issue_ids": candidate_ids,
                "evidence_checked": evidence_checked,
                "reason": str(item.get("reason") or "").strip(),
                "errors": entry_errors,
            }
        )

    missed_ids: list[str] = []
    finding_audit_keys: dict[str, str] = {}
    for index, finding in enumerate(missed):
        candidate_id = _dual_pass_raw_issue_id(finding)
        audit_key = str(finding.get("audit_key") or "").strip()
        if not candidate_id:
            errors.append(f"missed_finding_candidate_issue_id_missing:{index}")
            continue
        missed_ids.append(candidate_id)
        finding_audit_keys[candidate_id] = audit_key
        mapped_keys = confirmed_occurrences.get(candidate_id, [])
        if not mapped_keys:
            errors.append(f"missed_finding_not_in_confirmed_add:{candidate_id}")
        elif len(mapped_keys) != 1:
            errors.append(f"missed_finding_mapped_multiple_times:{candidate_id}")
        elif audit_key != mapped_keys[0]:
            errors.append(f"missed_finding_audit_key_mismatch:{candidate_id}")
    if len(set(missed_ids)) != len(missed_ids):
        errors.append("missed_finding_candidate_issue_id_duplicate")

    confirmed_ids = set(confirmed_occurrences)
    missed_id_set = set(missed_ids)
    orphan_confirmed_ids = sorted(confirmed_ids - missed_id_set)
    unmapped_missed_ids = sorted(missed_id_set - confirmed_ids)
    duplicate_confirmed_ids = sorted(
        candidate_id for candidate_id, keys in confirmed_occurrences.items() if len(keys) != 1
    )
    for candidate_id in orphan_confirmed_ids:
        errors.append(f"confirmed_add_without_missed_finding:{candidate_id}")

    errors = dedupe_text_list(errors)
    completeness = round(
        len(set(observed_keys).intersection(expected_keys)) / len(expected_keys), 4
    ) if expected_keys else 1.0
    return {
        "schema_version": 1,
        "passed": not errors,
        "completeness": completeness,
        "expected_audit_keys": expected_keys,
        "observed_audit_keys": observed_keys,
        "confirmed_audit_keys": [
            item["audit_key"] for item in normalized_entries if item["status"] == "confirmed_add"
        ],
        "candidate_to_audit_key": {
            candidate_id: keys[0]
            for candidate_id, keys in confirmed_occurrences.items()
            if len(keys) == 1
        },
        "finding_audit_keys": finding_audit_keys,
        "unmapped_missed_issue_ids": unmapped_missed_ids,
        "orphan_confirmed_issue_ids": orphan_confirmed_ids,
        "duplicate_confirmed_issue_ids": duplicate_confirmed_ids,
        "protocol_repairs": protocol_repairs,
        "errors": errors,
        "entries": normalized_entries,
    }


def _phase2_primary_matches_control(control_key: str, finding: dict[str, Any]) -> bool:
    text = "\n".join(
        str(finding.get(field) or "")
        for field in ("title", "canonical_title", "current_state", "evidence", "risk", "suggestion")
    ).lower()
    keyword_groups: dict[str, tuple[tuple[str, ...], ...]] = {
        "settlement_formula": (("公式", "计算", "赔付", "结算"),),
        "ui_config_mapping": (("ui", "界面", "展示", "配置", "映射", "口径", "定义", "符号", "公式"),),
        "trigger_entry": (("触发", "进入", "入口", "条件"),),
        "termination_priority": (("终止", "结束", "优先", "顺序", "状态", "触发条件", "次数", "边界", "结算", "逻辑"),),
        "debit_timing": (("扣款", "扣除", "本金", "余额"),),
        "payout_timing": (("派奖", "发奖", "到账", "奖励发放", "结算时机"),),
        "funds_failure_compensation": (("失败", "回滚", "补偿", "幂等", "重试", "弱网"),),
        "relative_payout_cap": (("max_mul", "倍率上限", "最大倍率", "100倍", "封顶", "倍率", "倍数", "赔率", "最高赔付"),),
        "pool_negative_floor": (("奖池",), ("负", "透支", "下限")),
        "single_round_payout_cap": (("最大赔付", "最高赔付", "赔付上限", "单局赔付", "单次赔付", "封顶"),),
        "same_metric_window": (("统计", "窗口", "时间范围", "天", "今日", "本周"),),
        "ui_text_window_alignment": (("ui", "界面", "截图", "正文", "展示"), ("天", "今日", "本周", "时间")),
    }
    groups = keyword_groups.get(control_key) or ()
    return bool(groups) and all(any(keyword in text for keyword in group) for group in groups)


def _phase2_aggregate_control_status(statuses: list[str]) -> str:
    for status in ("confirmed_add", "advice_only", "covered_by_primary", "no_issue", "not_applicable"):
        if status in statuses:
            return status
    return ""


def _phase2_v22_decision_reason_errors(reason: str, status: str) -> list[str]:
    """Validate the deterministic four-step decision trace required by phase2 V2.2."""
    text = str(reason or "").strip()
    markers = ("source_state=", "counterevidence=", "primary_coverage=", "final=")
    positions = [text.find(marker) for marker in markers]
    errors: list[str] = []
    if any(position < 0 for position in positions):
        return ["decision_trace_incomplete"]
    if positions != sorted(positions):
        errors.append("decision_trace_order_invalid")
    source_match = re.search(r"source_state\s*=\s*(explicit|partial|missing|conflict)\b", text, re.I)
    if not source_match:
        errors.append("decision_source_state_invalid")
    primary_match = re.search(r"primary_coverage\s*=\s*(same_control|not_covered)\b", text, re.I)
    if not primary_match:
        errors.append("decision_primary_coverage_invalid")
    else:
        primary_state = primary_match.group(1).strip().lower()
        if status == "covered_by_primary" and primary_state != "same_control":
            errors.append("decision_primary_coverage_status_mismatch")
        elif status != "covered_by_primary" and primary_state != "not_covered":
            errors.append("decision_primary_coverage_status_mismatch")
    counter_match = re.search(r"counterevidence=([^;；]+)", text, re.I)
    if not counter_match or not counter_match.group(1).strip():
        errors.append("decision_counterevidence_missing")
    final_match = re.search(r"final\s*=\s*([a-z_]+)\b", text, re.I)
    if not final_match:
        errors.append("decision_final_missing")
    elif final_match.group(1).strip().lower() != str(status or "").strip().lower():
        errors.append("decision_final_status_mismatch")
    return dedupe_text_list(errors)


def evaluate_phase2_protocol_gate(
    secondary_review: dict[str, Any] | None,
    protocol_revision: str,
    evidence_packet_id: str,
) -> dict[str, Any]:
    """Validate protocol identity and the V2.2 delta-only response contract."""
    review = secondary_review if isinstance(secondary_review, dict) else {}
    revision = str(protocol_revision or "").strip()
    packet_id = str(evidence_packet_id or "").strip()
    echo_required = revision.startswith("phase2_v2_") and bool(packet_id)
    expected_echo = (
        f"protocol_profile={revision}; evidence_packet_id={packet_id}"
        if echo_required
        else ""
    )
    notes = [str(item).strip() for item in review.get("review_notes") or [] if str(item).strip()]
    echo_matched = (not echo_required) or (bool(notes) and notes[-1] == expected_echo)
    delta_only_required = revision == "phase2_v2_2"
    provided_fields = review.get("_provided_top_level_fields")
    supplied_field_names = (
        {str(field) for field in provided_fields}
        if isinstance(provided_fields, list)
        else set(review)
    )
    forbidden_fields = [
        field
        for field in ("candidate_report", "candidate_lineage", "candidate_readiness")
        if field in supplied_field_names
    ]
    delta_only_allowed_fields = {
        "quality_assessment",
        "coverage_schema_version",
        "coverage_ledger",
        "missed_findings",
        "unsupported_findings",
        "merge_recommendations",
        "review_notes",
    }
    unexpected_fields = sorted(supplied_field_names - delta_only_allowed_fields) if delta_only_required else []
    delta_only_compliant = (not delta_only_required) or not unexpected_fields
    errors: list[str] = []
    if not echo_matched:
        errors.append("phase2_protocol_echo_missing_or_mismatch")
    if not delta_only_compliant:
        errors.append("phase2_delta_only_unexpected_fields_present:" + ",".join(unexpected_fields))
    return {
        "required": echo_required or delta_only_required,
        "protocol_revision": revision,
        "evidence_packet_id": packet_id,
        "expected_echo": expected_echo,
        "echo_required": echo_required,
        "echo_matched": echo_matched,
        "delta_only_required": delta_only_required,
        "delta_only_compliant": delta_only_compliant,
        "forbidden_fields_present": forbidden_fields,
        "unexpected_fields_present": unexpected_fields,
        "passed": not errors,
        "errors": errors,
    }


def _evaluate_phase2_coverage_ledger_v2(
    secondary_review: dict[str, Any] | None,
    shared_input: dict[str, Any] | None,
    primary_report: dict[str, Any] | None,
    protocol_revision: str = "",
) -> dict[str, Any]:
    review = secondary_review if isinstance(secondary_review, dict) else {}
    raw_ledger = review.get("coverage_ledger")
    ledger = [item for item in raw_ledger if isinstance(item, dict)] if isinstance(raw_ledger, list) else []
    missed = [item for item in review.get("missed_findings") or [] if isinstance(item, dict)]
    expected_audit_keys = list(PHASE2_COVERAGE_AUDIT_KEYS)
    observed_audit_keys = [str(item.get("audit_key") or "").strip() for item in ledger]
    expected_control_count = sum(len(values) for values in PHASE2_COVERAGE_CONTROL_KEYS.values())
    observed_valid_control_count = 0
    errors: list[str] = []
    protocol_repairs: list[str] = []
    normalized_entries: list[dict[str, Any]] = []
    confirmed_occurrences: dict[str, list[tuple[str, str]]] = {}
    primary_by_id = {
        str(item.get("issue_id") or "").strip(): item
        for item in collect_all_findings(primary_report or {})
        if isinstance(item, dict) and str(item.get("issue_id") or "").strip()
    }

    if len(ledger) != len(expected_audit_keys):
        errors.append(f"coverage_entry_count_invalid:{len(ledger)}")
    if observed_audit_keys != expected_audit_keys:
        errors.append("coverage_audit_key_order_invalid")
    if len(set(key for key in observed_audit_keys if key)) != len([key for key in observed_audit_keys if key]):
        errors.append("coverage_audit_key_duplicate")

    for audit_index, item in enumerate(ledger):
        audit_key = str(item.get("audit_key") or "").strip()
        expected_controls = list(PHASE2_COVERAGE_CONTROL_KEYS.get(audit_key) or ())
        raw_controls = item.get("controls")
        controls = [value for value in raw_controls if isinstance(value, dict)] if isinstance(raw_controls, list) else []
        observed_controls = [str(value.get("control_key") or "").strip() for value in controls]
        audit_errors: list[str] = []
        if audit_key not in PHASE2_COVERAGE_CONTROL_KEYS:
            audit_errors.append("audit_key_invalid")
        if not isinstance(raw_controls, list):
            audit_errors.append("controls_not_array")
        if len(controls) != len(expected_controls):
            audit_errors.append(f"control_count_invalid:{len(controls)}")
        if observed_controls != expected_controls:
            audit_errors.append("control_key_order_invalid")

        normalized_controls: list[dict[str, Any]] = []
        for control_index, control in enumerate(controls):
            control_key = str(control.get("control_key") or "").strip()
            status = str(control.get("status") or "").strip().lower()
            reason = str(control.get("reason") or "").strip()
            primary_values = control.get("primary_issue_ids")
            candidate_values = control.get("candidate_issue_ids")
            primary_ids = (
                dedupe_text_list([str(value).strip() for value in primary_values if str(value).strip()])
                if isinstance(primary_values, list)
                else []
            )
            candidate_ids = (
                dedupe_text_list([str(value).strip() for value in candidate_values if str(value).strip()])
                if isinstance(candidate_values, list)
                else []
            )
            if protocol_revision == "phase2_v2_2" and status == "not_applicable":
                if re.search(r"source_state\s*=\s*not_applicable\b", reason, re.I):
                    reason = re.sub(
                        r"(source_state\s*=\s*)not_applicable\b",
                        r"\1missing",
                        reason,
                        count=1,
                        flags=re.I,
                    )
                    protocol_repairs.append(
                        f"normalized_not_applicable_source_state:{audit_key}:{control_key}:not_applicable->missing"
                    )
                if re.search(r"primary_coverage\s*=\s*not_applicable\b", reason, re.I):
                    reason = re.sub(
                        r"(primary_coverage\s*=\s*)not_applicable\b",
                        r"\1not_covered",
                        reason,
                        count=1,
                        flags=re.I,
                    )
                    protocol_repairs.append(
                        f"normalized_not_applicable_primary_coverage:{audit_key}:{control_key}:"
                        "not_applicable->not_covered"
                    )
            if protocol_revision == "phase2_v2_2" and status in {
                "no_issue",
                "advice_only",
                "covered_by_primary",
            }:
                primary_state_match = re.search(
                    r"primary_coverage\s*=\s*(same_control|not_covered)\b",
                    reason,
                    re.I,
                )
                valid_primary_ids = [
                    primary_id
                    for primary_id in primary_ids
                    if primary_id in primary_by_id
                    and _phase2_primary_matches_control(control_key, primary_by_id[primary_id])
                ]
                invalid_primary_ids = [primary_id for primary_id in primary_ids if primary_id not in valid_primary_ids]
                same_control_mapping_is_valid = bool(valid_primary_ids)
                if invalid_primary_ids and not candidate_ids:
                    primary_ids = valid_primary_ids
                    protocol_repairs.append(
                        f"cleared_invalid_nonmaterializing_primary_reference:{audit_key}:{control_key}:"
                        f"{','.join(invalid_primary_ids)}"
                    )
                if (
                    primary_state_match
                    and primary_state_match.group(1).lower() == "same_control"
                    and not candidate_ids
                    and same_control_mapping_is_valid
                ):
                    original_status = status
                    status = "covered_by_primary"
                    reason = re.sub(
                        rf"(final\s*=\s*){re.escape(original_status)}\b",
                        r"\1covered_by_primary",
                        reason,
                        count=1,
                        flags=re.I,
                    )
                    protocol_repairs.append(
                        f"normalized_same_control_status:{audit_key}:{control_key}:"
                        f"{original_status}->covered_by_primary"
                    )
                elif (
                    primary_state_match
                    and primary_state_match.group(1).lower() == "same_control"
                    and not candidate_ids
                    and not same_control_mapping_is_valid
                ):
                    primary_ids = []
                    reason = re.sub(
                        r"(primary_coverage\s*=\s*)same_control(?:\([^;；]*\))?",
                        r"\1not_covered",
                        reason,
                        count=1,
                        flags=re.I,
                    )
                    if status == "covered_by_primary":
                        source_state_match = re.search(
                            r"source_state\s*=\s*(explicit|partial|missing|conflict)\b",
                            reason,
                            re.I,
                        )
                        replacement_status = (
                            "no_issue"
                            if source_state_match and source_state_match.group(1).lower() == "explicit"
                            else "advice_only"
                        )
                        reason = re.sub(
                            r"(final\s*=\s*)covered_by_primary\b",
                            rf"\g<1>{replacement_status}",
                            reason,
                            count=1,
                            flags=re.I,
                        )
                        protocol_repairs.append(
                            f"normalized_invalid_covered_status:{audit_key}:{control_key}:"
                            f"covered_by_primary->{replacement_status}"
                        )
                        status = replacement_status
            evidence_checked = control.get("evidence_checked")
            if (
                status == "covered_by_primary"
                and candidate_ids
                and primary_ids
                and set(candidate_ids).issubset(set(primary_ids))
            ):
                protocol_repairs.append(
                    f"cleared_redundant_candidate_ids:{audit_key}:{control_key}:{','.join(candidate_ids)}"
                )
                candidate_ids = []
            if status == "not_applicable" and not _phase2_field_present(evidence_checked):
                document_names = _phase2_document_names(shared_input)
                if document_names:
                    evidence_checked = [f"{name} / 全文" for name in document_names]
                    protocol_repairs.append(
                        f"filled_not_applicable_evidence:{audit_key}:{control_key}"
                    )

            control_errors: list[str] = []
            if control_key not in expected_controls:
                control_errors.append("control_key_invalid")
            else:
                observed_valid_control_count += 1
            if status not in PHASE2_COVERAGE_STATUSES:
                control_errors.append("status_invalid")
            if not isinstance(primary_values, list):
                control_errors.append("primary_issue_ids_not_array")
            if not isinstance(candidate_values, list):
                control_errors.append("candidate_issue_ids_not_array")
            if not _phase2_field_present(evidence_checked):
                control_errors.append("evidence_checked_missing")
            if not reason:
                control_errors.append("reason_missing")
            elif protocol_revision == "phase2_v2_2":
                control_errors.extend(_phase2_v22_decision_reason_errors(reason, status))
            if status == "confirmed_add" and not candidate_ids:
                control_errors.append("confirmed_add_candidate_ids_empty")
            if status == "confirmed_add" and len(candidate_ids) > 1:
                control_errors.append("confirmed_add_multiple_candidate_ids")
            if status != "confirmed_add" and candidate_ids:
                control_errors.append("non_confirmed_candidate_ids_present")
            if status == "covered_by_primary" and not primary_ids:
                control_errors.append("covered_by_primary_issue_ids_empty")
            if status == "covered_by_primary" and primary_by_id:
                for primary_id in primary_ids:
                    primary_finding = primary_by_id.get(primary_id)
                    if primary_finding is None:
                        control_errors.append(f"primary_issue_id_unknown:{primary_id}")
                    elif not _phase2_primary_matches_control(control_key, primary_finding):
                        control_errors.append(f"primary_control_mismatch:{primary_id}")
            for candidate_id in candidate_ids if status == "confirmed_add" else []:
                confirmed_occurrences.setdefault(candidate_id, []).append((audit_key, control_key))
            if control_errors:
                label = control_key or f"index_{control_index}"
                errors.extend(
                    f"coverage_control_invalid:{audit_key or f'index_{audit_index}'}:{label}:{reason}"
                    for reason in control_errors
                )
            normalized_controls.append(
                {
                    "control_key": control_key,
                    "status": status,
                    "primary_issue_ids": primary_ids,
                    "candidate_issue_ids": candidate_ids,
                    "evidence_checked": evidence_checked,
                    "reason": reason,
                    "errors": control_errors,
                }
            )
        if audit_errors:
            label = audit_key or f"index_{audit_index}"
            errors.extend(f"coverage_entry_invalid:{label}:{reason}" for reason in audit_errors)
        statuses = [value["status"] for value in normalized_controls if value["status"]]
        normalized_entries.append(
            {
                "audit_key": audit_key,
                "status": _phase2_aggregate_control_status(statuses),
                "primary_issue_ids": dedupe_text_list(
                    [primary_id for value in normalized_controls for primary_id in value["primary_issue_ids"]]
                ),
                "candidate_issue_ids": dedupe_text_list(
                    [candidate_id for value in normalized_controls for candidate_id in value["candidate_issue_ids"]]
                ),
                "evidence_checked": dedupe_text_list(
                    [
                        str(evidence).strip()
                        for value in normalized_controls
                        for evidence in (value["evidence_checked"] or [])
                        if str(evidence).strip()
                    ]
                ),
                "reason": "；".join(
                    value["reason"] for value in normalized_controls if value["reason"]
                ),
                "controls": normalized_controls,
                "errors": audit_errors,
            }
        )

    missed_ids: list[str] = []
    finding_audit_keys: dict[str, str] = {}
    finding_control_keys: dict[str, str] = {}
    for index, finding in enumerate(missed):
        candidate_id = _dual_pass_raw_issue_id(finding)
        audit_key = str(finding.get("audit_key") or "").strip()
        control_key = str(finding.get("control_key") or "").strip()
        if not candidate_id:
            errors.append(f"missed_finding_candidate_issue_id_missing:{index}")
            continue
        missed_ids.append(candidate_id)
        finding_audit_keys[candidate_id] = audit_key
        finding_control_keys[candidate_id] = control_key
        mapped_controls = confirmed_occurrences.get(candidate_id, [])
        if not mapped_controls:
            errors.append(f"missed_finding_not_in_confirmed_add:{candidate_id}")
        elif len(mapped_controls) != 1:
            errors.append(f"missed_finding_mapped_multiple_times:{candidate_id}")
        elif (audit_key, control_key) != mapped_controls[0]:
            errors.append(f"missed_finding_control_mismatch:{candidate_id}")
    if len(set(missed_ids)) != len(missed_ids):
        errors.append("missed_finding_candidate_issue_id_duplicate")

    confirmed_ids = set(confirmed_occurrences)
    missed_id_set = set(missed_ids)
    orphan_confirmed_ids = sorted(confirmed_ids - missed_id_set)
    unmapped_missed_ids = sorted(missed_id_set - confirmed_ids)
    duplicate_confirmed_ids = sorted(
        candidate_id for candidate_id, values in confirmed_occurrences.items() if len(values) != 1
    )
    for candidate_id in orphan_confirmed_ids:
        errors.append(f"confirmed_add_without_missed_finding:{candidate_id}")

    errors = dedupe_text_list(errors)
    completeness = round(observed_valid_control_count / expected_control_count, 4) if expected_control_count else 1.0
    return {
        "schema_version": 2,
        "passed": not errors,
        "completeness": completeness,
        "expected_audit_keys": expected_audit_keys,
        "observed_audit_keys": observed_audit_keys,
        "expected_control_keys": {
            key: list(values) for key, values in PHASE2_COVERAGE_CONTROL_KEYS.items()
        },
        "confirmed_audit_keys": dedupe_text_list(
            [audit_key for values in confirmed_occurrences.values() for audit_key, _ in values]
        ),
        "confirmed_control_keys": dedupe_text_list(
            [control_key for values in confirmed_occurrences.values() for _, control_key in values]
        ),
        "candidate_to_audit_key": {
            candidate_id: values[0][0]
            for candidate_id, values in confirmed_occurrences.items()
            if len(values) == 1
        },
        "candidate_to_control_key": {
            candidate_id: values[0][1]
            for candidate_id, values in confirmed_occurrences.items()
            if len(values) == 1
        },
        "finding_audit_keys": finding_audit_keys,
        "finding_control_keys": finding_control_keys,
        "unmapped_missed_issue_ids": unmapped_missed_ids,
        "orphan_confirmed_issue_ids": orphan_confirmed_ids,
        "duplicate_confirmed_issue_ids": duplicate_confirmed_ids,
        "protocol_repairs": protocol_repairs,
        "errors": errors,
        "entries": normalized_entries,
    }


def evaluate_phase2_coverage_ledger(
    secondary_review: dict[str, Any] | None,
    shared_input: dict[str, Any] | None = None,
    primary_report: dict[str, Any] | None = None,
    required_schema_version: int | None = None,
    protocol_revision: str = "",
) -> dict[str, Any]:
    """Validate the active phase-two coverage ledger schema."""
    review = secondary_review if isinstance(secondary_review, dict) else {}
    raw_schema_version = review.get("coverage_schema_version")
    declared_schema_version = (
        _phase2_positive_int(raw_schema_version)
        if raw_schema_version is not None and str(raw_schema_version).strip()
        else None
    )
    raw_ledger = review.get("coverage_ledger")
    ledger = [item for item in raw_ledger if isinstance(item, dict)] if isinstance(raw_ledger, list) else []
    observed_audits = [str(item.get("audit_key") or "").strip() for item in ledger]
    v2_shape_complete = (
        observed_audits == list(PHASE2_COVERAGE_AUDIT_KEYS)
        and all(
            [
                str(control.get("control_key") or "").strip()
                for control in (item.get("controls") if isinstance(item.get("controls"), list) else [])
                if isinstance(control, dict)
            ]
            == list(PHASE2_COVERAGE_CONTROL_KEYS.get(str(item.get("audit_key") or "").strip()) or ())
            for item in ledger
        )
    )
    schema_version_inferred = declared_schema_version is None and v2_shape_complete
    schema_version = declared_schema_version or (2 if schema_version_inferred else 1)
    if schema_version >= 2:
        result = _evaluate_phase2_coverage_ledger_v2(
            review,
            shared_input,
            primary_report,
            protocol_revision=protocol_revision,
        )
    else:
        result = _evaluate_phase2_coverage_ledger_v1(review, shared_input)
    if schema_version_inferred:
        result["schema_version_inferred"] = True
        result["protocol_repairs"] = dedupe_text_list(
            ["inferred_coverage_schema_version:2_from_complete_control_shape"]
            + list(result.get("protocol_repairs") or [])
        )
    else:
        result["schema_version_inferred"] = False
    if required_schema_version is not None and schema_version < required_schema_version:
        result["errors"] = dedupe_text_list(
            list(result.get("errors") or [])
            + [f"coverage_schema_version_too_old:{schema_version}:required:{required_schema_version}"]
        )
        result["passed"] = False
    return result


def phase2_findings_are_duplicate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_issue_id = str(left.get("issue_id") or left.get("candidate_issue_id") or "").strip()
    right_issue_id = str(right.get("issue_id") or right.get("candidate_issue_id") or "").strip()
    if left_issue_id and right_issue_id and left_issue_id == right_issue_id:
        return True
    left_audit_key = str(left.get("audit_key") or "").strip()
    right_audit_key = str(right.get("audit_key") or "").strip()
    left_control_key = str(left.get("control_key") or "").strip()
    right_control_key = str(right.get("control_key") or "").strip()
    if (
        left_audit_key
        and left_audit_key == right_audit_key
        and left_control_key
        and right_control_key
        and left_control_key != right_control_key
    ):
        return False
    left_root = build_root_cause_key(left)
    right_root = build_root_cause_key(right)
    if left_root and left_root == right_root:
        if left_root not in PHASE2_BROAD_ROOT_KEYS:
            return True
        if left_root == "issue:CORE_DIFFICULTY_CONFIG_MISMATCH":
            left_domain = str(left.get("title") or left.get("canonical_title") or "")
            right_domain = str(right.get("title") or right.get("canonical_title") or "")
            if "概率" in left_domain and "概率" in right_domain:
                return True
    left_title = normalize_compare_text(str(left.get("title") or left.get("canonical_title") or ""))
    right_title = normalize_compare_text(str(right.get("title") or right.get("canonical_title") or ""))
    if not left_title or not right_title:
        return False
    if left_title == right_title:
        return True
    return SequenceMatcher(None, left_title, right_title).ratio() >= 0.82


def evaluate_dual_pass_added_admission(
    raw_finding: dict[str, Any],
    primary_report: dict[str, Any],
    shared_input: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply phase-two hard gates before a Secondary addition can enter the pipeline."""
    raw, evidence_alias_resolved = _phase2_resolve_evidence_aliases(raw_finding, shared_input)
    reasons: list[str] = []
    missing_fields = [
        field for field in PHASE2_ADDED_REQUIRED_FIELDS if not _phase2_field_present(raw.get(field))
    ]
    if missing_fields:
        reasons.append("missing_fields:" + ",".join(missing_fields))

    evidence = str(raw.get("evidence") or "").strip()
    document_names = _phase2_document_names(shared_input)
    if evidence and document_names and not any(name in evidence for name in document_names):
        reasons.append("evidence_document_unlocatable")
    if evidence and not re.search(
        r"(?:全文|章节|段落|表格|图片|第\s*\d+\s*[章节段表图]|\b\d+(?:\.\d+)+\b)",
        evidence,
        re.I,
    ):
        reasons.append("evidence_position_unlocatable")

    overlap_check = raw.get("primary_overlap_check")
    if not isinstance(overlap_check, dict):
        reasons.append("primary_overlap_check_invalid")
    else:
        nearest_id = str(overlap_check.get("nearest_primary_issue_id") or "").strip()
        overlap = overlap_check.get("overlap")
        overlap_reason = str(overlap_check.get("reason") or "").strip()
        if not nearest_id or overlap is not False or not overlap_reason:
            reasons.append("primary_overlap_check_incomplete")

    root_cause_count = _phase2_positive_int(raw.get("root_cause_count"))
    root_causes = raw.get("root_causes")
    if root_cause_count != 1 or not isinstance(root_causes, list) or len(root_causes) != 1:
        reasons.append("multiroot_or_root_count_invalid")
    if raw.get("multiroot") is True:
        reasons.append("multiroot_declared")

    severity = str(raw.get("severity") or "").strip().lower()
    blocking = str(raw.get("blocking") or "").strip().lower()
    high_signal = severity in {"high", "高"} or blocking in {
        "block_dev",
        "block_test",
        "阻塞开发",
        "阻塞测试用例设计",
    }
    if high_signal and not str(raw.get("severity_basis") or "").strip():
        reasons.append("severity_basis_missing")
    confidence = str(raw.get("confidence") or "").strip().lower()
    if confidence in {"low", "低"}:
        reasons.append("confidence_low")

    fact_check = raw.get("fact_check")
    if not isinstance(fact_check, dict):
        reasons.append("fact_check_invalid")
    else:
        claim_type = str(fact_check.get("claim_type") or "").strip().lower()
        conclusion = str(fact_check.get("conclusion") or "").strip().lower()
        fact_reason = str(fact_check.get("reason") or "").strip()
        if claim_type not in PHASE2_FACT_CHECK_TYPES:
            reasons.append("fact_check_claim_type_invalid")
        if fact_check.get("source_rule_presence_checked") is not True:
            reasons.append("fact_check_source_rule_not_checked")
        if fact_check.get("compatible_interpretation_checked") is not True:
            reasons.append("fact_check_compatible_interpretation_not_checked")
        if conclusion != "confirmed" or not fact_reason:
            reasons.append("fact_check_not_confirmed")
        if claim_type == "direct_conflict" and fact_check.get("compatible_interpretation_exists") is not False:
            reasons.append("direct_conflict_has_compatible_interpretation")
        if claim_type == "missing_rule":
            searched_locations = fact_check.get("searched_locations")
            if not isinstance(searched_locations, list) or not any(
                str(location or "").strip() for location in searched_locations
            ):
                reasons.append("missing_rule_search_scope_unlocatable")

    title = str(raw.get("title") or raw.get("canonical_title") or "").strip()
    current_state = str(raw.get("current_state") or raw.get("description") or "").strip()
    audit_key = str(raw.get("audit_key") or "").strip()
    control_key = str(raw.get("control_key") or "").strip()
    missing_claim = any(marker in title for marker in ("缺失", "未明确", "未说明", "未显式", "未定义", "没有定义"))
    explicit_rule_text = current_state
    for negated_marker in (
        "未明确说明",
        "未明确规定",
        "未明确",
        "并未明确说明",
        "没有明确说明",
        "没有明确规定",
    ):
        explicit_rule_text = explicit_rule_text.replace(negated_marker, "")
    explicit_rule = any(
        marker in explicit_rule_text
        for marker in ("明确说明", "明确规定", "已明确", "已经规定", "严格优先", "原文明确", "文档明确")
    )
    if missing_claim and explicit_rule:
        reasons.append("source_rule_already_explicit")
    if (
        missing_claim
        and control_key == "debit_timing"
        and "点击" in current_state
        and any(marker in current_state for marker in ("消耗对应的货币", "消耗对应货币", "扣除对应"))
    ):
        reasons.append("source_rule_already_explicit")
    if (
        missing_claim
        and control_key == "payout_timing"
        and "余额增加" in current_state
        and any(marker in current_state for marker in ("弹窗消失", "回到投入阶段"))
    ):
        reasons.append("source_rule_already_explicit")
    if (
        missing_claim
        and control_key == "funds_failure_compensation"
        and any(marker in current_state for marker in ("复用中台", "统一处理流程"))
    ):
        reasons.append("existing_platform_process_requires_advice_only")

    normalized = build_dual_pass_secondary_finding(raw, secondary_model="phase2_admission")
    primary_findings = [item for item in collect_all_findings(primary_report) if isinstance(item, dict)]
    raw_issue_id = _dual_pass_raw_issue_id(raw)
    broad_duplicate_matches = [
        {
            "issue_id": str(item.get("issue_id") or "").strip(),
            "title": str(item.get("title") or item.get("canonical_title") or "").strip(),
        }
        for item in primary_findings
        if (raw_issue_id and str(item.get("issue_id") or "").strip() == raw_issue_id)
        or are_duplicate_findings(normalized, item)
    ]
    duplicate_matches = [
        {
            "issue_id": str(item.get("issue_id") or "").strip(),
            "title": str(item.get("title") or item.get("canonical_title") or "").strip(),
        }
        for item in primary_findings
        if phase2_findings_are_duplicate(normalized, item)
    ]
    if raw_issue_id and any(str(item.get("issue_id") or "").strip() == raw_issue_id for item in primary_findings):
        reasons.append("primary_duplicate_issue_id")
    elif duplicate_matches:
        reasons.append("primary_duplicate_root")
    elif isinstance(overlap_check, dict):
        nearest_id = str(overlap_check.get("nearest_primary_issue_id") or "").strip()
        nearest_primary = next(
            (item for item in primary_findings if str(item.get("issue_id") or "").strip() == nearest_id),
            None,
        )
        overlap_reason_text = str(overlap_check.get("reason") or "")
        scope_expansion_claim = any(marker in overlap_reason_text for marker in ("更上层", "更完整", "更全面"))
        if nearest_primary and (
            scope_expansion_claim or _phase2_title_covered_by_primary_text(raw, nearest_primary)
        ):
            reasons.append("primary_duplicate_declared_nearest")

    fact_reason_text = str((fact_check or {}).get("reason") or "") if isinstance(fact_check, dict) else ""
    if fact_check and fact_check.get("compatible_interpretation_exists") is True and (
        any(marker in title for marker in ("疑问", "是否必要", "必要性"))
        or any(marker in fact_reason_text for marker in ("可能存在", "需要澄清", "疑问"))
    ):
        reasons.append("fact_check_inconclusive_compatible_interpretation")
    ambiguity_text = title + "\n" + current_state
    diagnostic_text = "\n".join(
        str(raw.get(field) or "")
        for field in ("title", "current_state", "risk", "suggestion", "independent_root_cause")
    )
    root_claim_text = "\n".join(
        str(raw.get(field) or "") for field in ("title", "independent_root_cause")
    )
    if (
        audit_key == "funds_deduction_payout"
        and control_key not in {"debit_timing", "payout_timing", "funds_failure_compensation"}
        and any(marker in root_claim_text for marker in ("扣款", "本金扣除", "本金扣款"))
        and any(marker in root_claim_text for marker in ("派奖", "发奖", "奖励到账"))
    ):
        reasons.append("multiroot_funds_debit_and_payout_combined")
    if control_key == "debit_timing" and "幂等" in root_claim_text:
        reasons.append("control_scope_drift_debit_timing_and_idempotency")
    if (
        control_key == "funds_failure_compensation"
        and "奖池透支" in diagnostic_text
        and any(marker in diagnostic_text for marker in ("回填", "熔断", "负值下限"))
    ):
        reasons.append("control_scope_drift_funds_failure_and_pool_boundary")
    if (
        control_key == "single_round_payout_cap"
        and "数值表" in root_claim_text
        and any(marker in root_claim_text for marker in ("冲突", "错误", "数量级"))
    ):
        reasons.append("control_scope_drift_payout_cap_and_formula_error")
    if (
        audit_key == "max_payout_economic_boundary"
        and any(marker in diagnostic_text for marker in ("负值下限", "负数下限", "透支下限"))
        and any(marker in diagnostic_text for marker in ("单局最大赔付", "单次最大赔付", "单局赔付封顶"))
    ):
        reasons.append("multiroot_pool_floor_and_payout_cap_combined")
    if (
        audit_key == "statistics_time_window"
        and isinstance(fact_check, dict)
        and str(fact_check.get("claim_type") or "").strip().lower() == "value_mismatch"
        and "下注金额" in diagnostic_text
        and any(marker in diagnostic_text for marker in ("胜率", "平均赔率"))
    ):
        reasons.append("statistics_subject_or_metric_mismatch")
    if (
        audit_key == "max_payout_economic_boundary"
        and "倍率上限" in diagnostic_text
        and any(marker in diagnostic_text for marker in ("最大赔付", "赔付金额上限"))
    ):
        reasons.append("existing_multiplier_boundary_requires_advice_only")
    if (
        fact_check
        and str(fact_check.get("claim_type") or "").strip().lower() in {"direct_conflict", "value_mismatch"}
        and fact_check.get("compatible_interpretation_exists") is False
        and (
        ("未明确" in ambiguity_text and "还是" in ambiguity_text)
        or ("若指" in ambiguity_text and "则" in ambiguity_text)
        )
    ):
        reasons.append("fact_check_compatible_interpretation_contradiction")
    if (
        isinstance(fact_check, dict)
        and str(fact_check.get("claim_type") or "").strip().lower() == "value_mismatch"
        and any(marker in title for marker in ("统计口径", "人数口径", "去重"))
        and fact_check.get("same_subject_and_scope") is not True
    ):
        reasons.append("value_mismatch_same_scope_unverified")

    reasons = dedupe_text_list(reasons)
    return {
        "candidate_issue_id": raw_issue_id,
        "title": title or str(normalized.get("title") or "未命名问题"),
        "status": "admitted" if not reasons else "rejected",
        "reasons": reasons,
        "missing_fields": missing_fields,
        "primary_duplicate_matches": duplicate_matches,
        "broad_primary_duplicate_matches": broad_duplicate_matches,
        "evidence_alias_resolved": evidence_alias_resolved,
        "normalized_evidence": str(raw.get("evidence") or ""),
    }


def _phase2_field_present(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _phase2_title_covered_by_primary_text(
    raw_finding: dict[str, Any],
    primary_finding: dict[str, Any],
) -> bool:
    title = normalize_compare_text(str(raw_finding.get("title") or raw_finding.get("canonical_title") or ""))
    primary_text = normalize_compare_text(
        " ".join(
            str(primary_finding.get(field) or "")
            for field in ("title", "canonical_title", "current_state", "evidence", "risk", "suggestion")
        )
    )
    if len(title) < 6 or not primary_text:
        return False
    title_bigrams = {title[index : index + 2] for index in range(len(title) - 1)}
    if len(title_bigrams) < 4:
        return False
    covered = sum(bigram in primary_text for bigram in title_bigrams)
    return covered / len(title_bigrams) >= 0.6


def _phase2_positive_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _phase2_document_names(shared_input: dict[str, Any] | None) -> list[str]:
    names: list[str] = []
    for label in (shared_input or {}).get("document_labels") or []:
        name = re.sub(r"\s+\([^()]*\)\s*$", "", str(label), flags=re.I).strip()
        if name:
            names.append(name)
    return dedupe_text_list(names)


def _phase2_resolve_evidence_aliases(
    raw_finding: dict[str, Any] | None,
    shared_input: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    raw = json.loads(json.dumps(raw_finding, ensure_ascii=False)) if isinstance(raw_finding, dict) else {}
    evidence = str(raw.get("evidence") or "")
    labels_by_kind: dict[str, list[str]] = {"requirement": [], "numeric": []}
    for label in (shared_input or {}).get("document_labels") or []:
        match = re.match(r"^(.*?)\s+\((requirement|numeric)\)\s*$", str(label), re.I)
        if match:
            labels_by_kind[match.group(2).lower()].append(match.group(1).strip())
    replacements = (
        (r"(?<![\w.])需求文档(?=\s*/)", "requirement"),
        (r"(?<![\w.])数值文档(?=\s*/)", "numeric"),
    )
    resolved = evidence
    for pattern, kind in replacements:
        names = dedupe_text_list(labels_by_kind[kind])
        if len(names) == 1:
            resolved = re.sub(pattern, names[0], resolved)
    if resolved != evidence:
        raw["evidence"] = resolved
        return raw, True
    return raw, False


def sanitize_dual_pass_phase2_candidate_review(
    primary_report: dict[str, Any],
    secondary_review: dict[str, Any],
    phase2_admission: dict[str, Any] | None,
    shared_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Remove rejected Secondary additions before constructing the phase-two candidate."""
    review = json.loads(json.dumps(secondary_review, ensure_ascii=False))
    missed = [
        _phase2_resolve_evidence_aliases(item, shared_input)[0]
        for item in review.get("missed_findings") or []
        if isinstance(item, dict)
    ]
    review["missed_findings"] = missed
    results = [item for item in (phase2_admission or {}).get("results") or [] if isinstance(item, dict)]
    if not results:
        return review

    admitted_missed: list[dict[str, Any]] = []
    admitted_source_ids: set[str] = set()
    rejected_source_ids: set[str] = set()
    for index, raw in enumerate(missed):
        result = results[index] if index < len(results) else {}
        source_id = _dual_pass_raw_issue_id(raw)
        if result.get("status") == "admitted":
            admitted_missed.append(raw)
            if source_id:
                admitted_source_ids.add(source_id)
        elif source_id:
            rejected_source_ids.add(source_id)
    review["missed_findings"] = admitted_missed

    lineage = review.get("candidate_lineage") if isinstance(review.get("candidate_lineage"), dict) else {}
    sanitized_lineage = json.loads(json.dumps(lineage, ensure_ascii=False)) if lineage else {
        "kept": [], "added": [], "merged": [], "dropped": []
    }
    admitted_candidate_ids: set[str] = set()
    sanitized_added: list[dict[str, Any]] = []
    for item in sanitized_lineage.get("added") or []:
        if not isinstance(item, dict):
            continue
        candidate_id = str(item.get("candidate_issue_id") or "").strip()
        source_ids = {
            str(value).strip()
            for value in item.get("source_missed_issue_ids") or []
            if str(value).strip()
        }
        linked_ids = source_ids or ({candidate_id} if candidate_id else set())
        if linked_ids and linked_ids.issubset(admitted_source_ids):
            sanitized_added.append(item)
            if candidate_id:
                admitted_candidate_ids.add(candidate_id)
    sanitized_lineage["added"] = sanitized_added
    for item in sanitized_lineage.get("kept") or []:
        if isinstance(item, dict) and isinstance(item.get("absorbed_missed_issue_ids"), list):
            item["absorbed_missed_issue_ids"] = [
                value
                for value in item.get("absorbed_missed_issue_ids") or []
                if str(value).strip() in admitted_source_ids
            ]
    review["candidate_lineage"] = sanitized_lineage

    primary_ids = {
        str(item.get("issue_id") or "").strip()
        for item in collect_all_findings(primary_report)
        if isinstance(item, dict) and str(item.get("issue_id") or "").strip()
    }
    lineage_candidate_ids = {
        str(item.get("candidate_issue_id") or "").strip()
        for key in ("kept", "merged")
        for item in sanitized_lineage.get(key) or []
        if isinstance(item, dict) and str(item.get("candidate_issue_id") or "").strip()
    }
    allowed_candidate_ids = primary_ids | admitted_source_ids | admitted_candidate_ids | lineage_candidate_ids
    candidate = review.get("candidate_report")
    if isinstance(candidate, dict):
        for dimension in candidate.get("dimensions") or []:
            if isinstance(dimension, dict):
                dimension["findings"] = [
                    finding
                    for finding in dimension.get("findings") or []
                    if isinstance(finding, dict)
                    and str(finding.get("issue_id") or "").strip() in allowed_candidate_ids
                ]
        candidate["cross_document_issues"] = [
            finding
            for finding in candidate.get("cross_document_issues") or []
            if isinstance(finding, dict)
            and str(finding.get("issue_id") or "").strip() in allowed_candidate_ids
        ]
        candidate["top_blockers"] = [
            blocker
            for blocker in candidate.get("top_blockers") or []
            if not isinstance(blocker, dict)
            or not str(blocker.get("issue_id") or "").strip()
            or str(blocker.get("issue_id") or "").strip() in allowed_candidate_ids
        ]
        for finding in collect_all_findings(candidate):
            if isinstance(finding, dict):
                normalized_finding, _ = _phase2_resolve_evidence_aliases(finding, shared_input)
                finding["evidence"] = normalized_finding.get("evidence") or finding.get("evidence") or ""
    review["review_notes"] = dedupe_text_list(
        list(review.get("review_notes") or [])
        + [f"phase2 准入已从 candidate 移除 rejected addition：{issue_id}" for issue_id in sorted(rejected_source_ids)]
    )
    return review


def build_deterministic_phase2_candidate(
    primary_report: dict[str, Any],
    pipeline_report: dict[str, Any],
    sanitized_secondary_review: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the phase2 candidate from Primary plus admitted delta, never from model-authored report prose."""
    candidate = json.loads(json.dumps(pipeline_report, ensure_ascii=False))
    review = json.loads(json.dumps(sanitized_secondary_review, ensure_ascii=False))
    primary_ids = [
        str(item.get("issue_id") or "").strip()
        for item in collect_all_findings(primary_report)
        if isinstance(item, dict) and str(item.get("issue_id") or "").strip()
    ]
    admitted_missed = [
        item for item in review.get("missed_findings") or [] if isinstance(item, dict)
    ]
    added_ids = dedupe_text_list(
        [_dual_pass_raw_issue_id(item) for item in admitted_missed if _dual_pass_raw_issue_id(item)]
    )
    review["candidate_lineage"] = {
        "kept": [
            {
                "candidate_issue_id": issue_id,
                "primary_issue_ids": [issue_id],
                "absorbed_missed_issue_ids": [],
            }
            for issue_id in dedupe_text_list(primary_ids)
        ],
        "added": [
            {
                "candidate_issue_id": issue_id,
                "source_missed_issue_ids": [issue_id],
                "reason": "通过 phase2 确定性准入后由系统物化。",
            }
            for issue_id in added_ids
        ],
        "merged": [],
        "dropped": [],
    }
    raw_assessment = review.get("quality_assessment")
    if isinstance(raw_assessment, dict):
        review["primary_quality_assessment"] = raw_assessment
    review["quality_assessment"] = {
        "summary": "Candidate 由 Primary 与已准入增量确定性生成。",
        "strengths": ["完整保留 Primary 骨架、评分和核心问题。"],
        "issues": [],
        "suggestion_level": "low",
        "ready_for_direct_output": True,
        "reason": "系统已完成结构化准入、物化和追踪校验。",
    }
    review["candidate_readiness"] = {
        "ready_for_direct_output": True,
        "reason": "Candidate 由系统确定性生成，不依赖模型自评。",
    }
    review["candidate_report"] = {}
    review["candidate_generation_mode"] = "deterministic_primary_plus_admitted_delta"
    review["review_notes"] = dedupe_text_list(
        list(review.get("review_notes") or [])
        + ["candidate_generation_mode=deterministic_primary_plus_admitted_delta"]
    )
    return candidate, review


def lock_dual_pass_candidate_score_to_primary(
    primary_report: dict[str, Any],
    candidate_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(candidate_report, dict):
        return candidate_report
    candidate_report["document_quality_score"] = str(primary_report.get("document_quality_score") or "")
    candidate_report["score_reason"] = str(primary_report.get("score_reason") or "")
    return candidate_report


def lock_dual_pass_candidate_top_blockers_to_primary(
    primary_report: dict[str, Any],
    candidate_report: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(candidate_report, dict):
        return candidate_report
    candidate_findings = [item for item in collect_all_findings(candidate_report) if isinstance(item, dict)]
    primary_top3: list[dict[str, Any]] = []
    for primary_blocker in [item for item in primary_report.get("top_blockers") or [] if isinstance(item, dict)][:3]:
        primary_issue_id = str(primary_blocker.get("issue_id") or "").strip()
        match = next(
            (
                finding
                for finding in candidate_findings
                if (
                    str(finding.get("issue_id") or "").strip() == primary_issue_id
                    if primary_issue_id
                    else phase2_findings_are_duplicate(primary_blocker, finding)
                )
            ),
            None,
        )
        if match is None:
            continue
        blocker = json.loads(json.dumps(primary_blocker, ensure_ascii=False))
        for field in ("issue_id", "title", "canonical_title", "severity", "blocking"):
            if str(match.get(field) or "").strip():
                blocker[field] = match.get(field)
        primary_top3.append(blocker)
    remaining = [
        json.loads(json.dumps(item, ensure_ascii=False))
        for item in candidate_report.get("top_blockers") or []
        if isinstance(item, dict)
        and not any(phase2_findings_are_duplicate(item, primary_item) for primary_item in primary_top3)
    ]
    candidate_report["top_blockers"] = (primary_top3 + remaining)[: max(3, len(primary_top3))]
    return candidate_report


def merge_secondary_review_report(
    primary_report: dict[str, Any],
    secondary_report: dict[str, Any],
    documents: list[ParsedDocument],
    primary_model: str,
    secondary_model: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged = normalize_report(json.loads(json.dumps(primary_report, ensure_ascii=False)))
    secondary = normalize_report(json.loads(json.dumps(secondary_report, ensure_ascii=False)))

    primary_score = str(merged.get("document_quality_score") or "").strip() or "C"
    primary_score_reason = str(merged.get("score_reason") or "").strip()
    primary_overall = str(merged.get("overall_evaluation") or "").strip()
    primary_top_blockers = [dict(item) for item in (merged.get("top_blockers") or []) if isinstance(item, dict)]

    existing_findings = list(collect_all_findings(merged))
    added_unique: list[dict[str, Any]] = []
    added_high_risk: list[dict[str, Any]] = []
    skipped_low_confidence: list[str] = []
    duplicate_secondary_titles: list[str] = []

    for entry in collect_report_entries(secondary):
        raw_finding = entry.get("finding")
        if not isinstance(raw_finding, dict):
            continue
        dimension_name = normalize_dimension_name(
            raw_finding.get("primary_dimension") or entry.get("dimension_name"),
            fallback=DIMENSIONS[0],
        )
        finding = normalize_unmatched_finding(dict(raw_finding), dimension_name)
        if entry.get("location") == "cross_document":
            finding["evidence_scope"] = "cross_document"
        if confidence_rank_value(finding.get("confidence")) < CONFIDENCE_RANK["中"]:
            skipped_low_confidence.append(str(finding.get("title") or finding.get("canonical_title") or "未命名问题"))
            continue
        if any(are_duplicate_findings(finding, current) for current in existing_findings):
            duplicate_secondary_titles.append(str(finding.get("title") or finding.get("canonical_title") or "未命名问题"))
            continue
        if any(are_duplicate_findings(finding, current) for current in added_unique):
            duplicate_secondary_titles.append(str(finding.get("title") or finding.get("canonical_title") or "未命名问题"))
            continue

        finding["finding_source"] = "secondary_model"
        finding["finding_source_label"] = "副评审补充"
        finding["source_model"] = secondary_model
        added_unique.append(finding)
        existing_findings.append(finding)
        if is_fusion_high_risk_candidate(finding):
            added_high_risk.append(finding)
        append_secondary_finding(merged, finding)

    merged = stabilize_report(merged, documents)

    downgraded = len(added_high_risk) >= 3
    final_score = primary_score
    final_reason = primary_score_reason
    if downgraded:
        final_score = downgrade_score_once(primary_score)
        reason_prefix = primary_score_reason or "主评审报告已作为评分基线。"
        final_reason = (
            f"{reason_prefix} 副评审新增 {len(added_high_risk)} 个唯一高风险问题，"
            f"因此最终评分由 {primary_score} 下调为 {final_score}。"
        )
    else:
        final_reason = primary_score_reason or "最终评分沿用主评审报告。"

    merged["top_blockers"] = reorder_top_blockers_by_preference(merged, primary_top_blockers)
    merged["document_quality_score"] = final_score
    merged["score_reason"] = final_reason
    merged["overall_evaluation"] = primary_overall or merged.get("overall_evaluation") or ""
    merged["review_mode"] = "fusion"
    merged["primary_model"] = primary_model
    merged["secondary_model"] = secondary_model

    quality_notes = list(merged.get("quality_notes") or [])
    quality_notes.append(
        f"fusion 模式采用主评审模型 {primary_model} 作为主评分基线，副评审模型 {secondary_model} 仅补充唯一问题。"
    )
    quality_notes.append(
        f"副评审共补充 {len(added_unique)} 个唯一问题，其中高风险问题 {len(added_high_risk)} 个。"
    )
    if skipped_low_confidence:
        quality_notes.append(f"副评审有 {len(skipped_low_confidence)} 个低置信度问题未并入最终报告。")
    if downgraded:
        quality_notes.append(
            f"副评审新增唯一高风险问题达到 {len(added_high_risk)} 个，最终评分由 {primary_score} 调整为 {final_score}。"
        )
    else:
        quality_notes.append(f"最终评分保留主评审结果：{primary_score}。")
    merged["quality_notes"] = quality_notes

    fusion_summary = {
        "status": "merged",
        "primary_model": primary_model,
        "secondary_model": secondary_model,
        "primary_score": primary_score,
        "final_score": final_score,
        "score_downgraded": downgraded,
        "primary_finding_count": len(collect_all_findings(primary_report)),
        "secondary_finding_count": len(collect_all_findings(secondary_report)),
        "added_unique_findings": len(added_unique),
        "added_unique_high_risk_findings": len(added_high_risk),
        "duplicate_secondary_titles": duplicate_secondary_titles,
        "skipped_low_confidence_titles": skipped_low_confidence,
    }
    merged["fusion_summary"] = fusion_summary
    assert_report_integrity(merged)
    return merged, fusion_summary


def merge_dual_pass_review_report(
    primary_report: dict[str, Any],
    secondary_review: dict[str, Any],
    documents: list[ParsedDocument],
    secondary_model: str,
    *,
    shared_input: dict[str, Any] | None = None,
    enforce_phase2_admission: bool = False,
    phase2_protocol_gate: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _ = documents
    merged = normalize_report(json.loads(json.dumps(primary_report, ensure_ascii=False)))
    original_score = str(merged.get("document_quality_score") or "").strip()
    original_score_reason = str(merged.get("score_reason") or "").strip()
    original_top_blockers = [dict(item) for item in (merged.get("top_blockers") or []) if isinstance(item, dict)]

    existing_findings = list(collect_all_findings(merged))
    added_findings = 0
    duplicate_titles: list[str] = []
    admission_results: list[dict[str, Any]] = []
    coverage_ledger_evaluation = (
        evaluate_phase2_coverage_ledger(
            secondary_review,
            shared_input,
            primary_report,
            required_schema_version=2,
            protocol_revision=str((phase2_protocol_gate or {}).get("protocol_revision") or ""),
        )
        if enforce_phase2_admission
        else {"passed": True, "completeness": 1.0, "errors": []}
    )
    protocol_gate_evaluation = dict(phase2_protocol_gate or {})
    if enforce_phase2_admission and protocol_gate_evaluation:
        coverage_ledger_evaluation["protocol_gate"] = protocol_gate_evaluation
        if protocol_gate_evaluation.get("passed") is not True:
            coverage_ledger_evaluation["errors"] = dedupe_text_list(
                list(coverage_ledger_evaluation.get("errors") or [])
                + [
                    f"phase2_protocol_gate:{error}"
                    for error in protocol_gate_evaluation.get("errors") or ["failed"]
                ]
            )
            coverage_ledger_evaluation["passed"] = False
    candidate_report = secondary_review.get("candidate_report") if isinstance(secondary_review.get("candidate_report"), dict) else {}
    candidate_findings_by_issue_id: dict[str, dict[str, Any]] = {}
    primary_findings_by_issue_id: dict[str, dict[str, Any]] = {}
    for entry in collect_report_entries(candidate_report):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id and issue_id not in candidate_findings_by_issue_id:
            candidate_findings_by_issue_id[issue_id] = finding
    for entry in collect_report_entries(merged):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id and issue_id not in primary_findings_by_issue_id:
            primary_findings_by_issue_id[issue_id] = finding

    suppressed_candidate_issue_ids, absorbed_primary_issue_ids = _apply_dual_pass_absorbed_splits(
        merged,
        candidate_report,
        secondary_review.get("candidate_lineage") if isinstance(secondary_review.get("candidate_lineage"), dict) else {},
    )

    for raw_finding in secondary_review.get("missed_findings") or []:
        if not isinstance(raw_finding, dict):
            continue
        effective_raw_finding = raw_finding
        if enforce_phase2_admission:
            effective_raw_finding, _ = _phase2_resolve_evidence_aliases(raw_finding, shared_input)
            admission = evaluate_dual_pass_added_admission(effective_raw_finding, primary_report, shared_input)
            issue_id = _dual_pass_raw_issue_id(effective_raw_finding)
            mapped_audit_key = str(
                (coverage_ledger_evaluation.get("candidate_to_audit_key") or {}).get(issue_id) or ""
            ).strip()
            declared_audit_key = str(effective_raw_finding.get("audit_key") or "").strip()
            mapped_control_key = str(
                (coverage_ledger_evaluation.get("candidate_to_control_key") or {}).get(issue_id) or ""
            ).strip()
            declared_control_key = str(effective_raw_finding.get("control_key") or "").strip()
            coverage_reasons: list[str] = []
            if coverage_ledger_evaluation.get("passed") is not True:
                coverage_reasons.append("coverage_ledger_invalid")
            if issue_id and not mapped_audit_key:
                coverage_reasons.append("coverage_confirmed_add_link_missing")
            elif issue_id and declared_audit_key != mapped_audit_key:
                coverage_reasons.append("coverage_audit_key_mismatch")
            if coverage_ledger_evaluation.get("schema_version") == 2:
                if issue_id and not mapped_control_key:
                    coverage_reasons.append("coverage_confirmed_control_link_missing")
                elif issue_id and declared_control_key != mapped_control_key:
                    coverage_reasons.append("coverage_control_key_mismatch")
            if issue_id in set(coverage_ledger_evaluation.get("duplicate_confirmed_issue_ids") or []):
                coverage_reasons.append("coverage_candidate_mapped_multiple_times")
            if coverage_reasons:
                admission["status"] = "rejected"
                admission["reasons"] = dedupe_text_list(
                    list(admission.get("reasons") or []) + coverage_reasons
                )
            admission["coverage_audit_key"] = mapped_audit_key or declared_audit_key
            admission["coverage_control_key"] = mapped_control_key or declared_control_key
            admission_results.append(admission)
            if admission.get("status") != "admitted":
                continue
        issue_id = _dual_pass_raw_issue_id(effective_raw_finding)
        if issue_id and issue_id in suppressed_candidate_issue_ids:
            continue
        finding = build_dual_pass_secondary_finding(
            effective_raw_finding,
            secondary_model=secondary_model,
            candidate_finding=candidate_findings_by_issue_id.get(issue_id),
            fallback_dimension=effective_raw_finding.get("primary_dimension")
            or effective_raw_finding.get("dimension")
            or DIMENSIONS[0],
        )
        duplicate_check = phase2_findings_are_duplicate if enforce_phase2_admission else are_duplicate_findings
        if (issue_id and any(str(current.get("issue_id") or "").strip() == issue_id for current in existing_findings)) or any(
            duplicate_check(finding, current) for current in existing_findings
        ):
            duplicate_titles.append(str(finding.get("title") or finding.get("canonical_title") or "未命名问题"))
            if enforce_phase2_admission:
                for admission in reversed(admission_results):
                    if admission.get("candidate_issue_id") == issue_id or admission.get("title") == str(
                        finding.get("title") or finding.get("canonical_title") or ""
                    ):
                        admission["status"] = "rejected"
                        admission["reasons"] = dedupe_text_list(
                            list(admission.get("reasons") or []) + ["primary_duplicate_after_normalization"]
                        )
                        break
            continue
        append_secondary_finding(merged, finding, disable_cross_document=True)
        existing_findings.append(finding)
        if issue_id:
            primary_findings_by_issue_id.setdefault(issue_id, finding)
        added_findings += 1

    notes = list(merged.get("quality_notes") or [])
    for admission in admission_results:
        if admission.get("status") == "admitted":
            continue
        title = str(admission.get("title") or admission.get("candidate_issue_id") or "未命名问题")
        reasons = ", ".join(str(item) for item in admission.get("reasons") or []) or "phase2_admission_failed"
        notes.append(f"dual_pass phase2 准入拒绝：《{title}》未进入最终报告，原因：{reasons}")
    for item in secondary_review.get("unsupported_findings") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "unknown finding").strip()
        reason = str(item.get("reason") or "missing evidence").strip()
        notes.append(f"dual_pass 复核提示：主报告中的《{title}》可能证据不足，原因：{reason}")
    for item in secondary_review.get("merge_recommendations") or []:
        if not isinstance(item, dict):
            continue
        titles = [str(title).strip() for title in item.get("titles") or [] if str(title).strip()]
        if len(titles) < 2:
            continue
        merged_title = str(item.get("merged_title") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if merged_title:
            notes.append(f"dual_pass 复核备注：建议将《{' / '.join(titles)}》合并为《{merged_title}》。{reason}".strip())
        elif reason:
            notes.append(f"dual_pass 复核备注：建议合并《{' / '.join(titles)}》，原因：{reason}".strip())
    for note in secondary_review.get("review_notes") or []:
        clean_note = str(note).strip()
        if not clean_note:
            continue
        if _should_skip_absorbed_split_note(clean_note, absorbed_primary_issue_ids):
            continue
        notes.append(f"dual_pass 复核备注：{clean_note}")
    if absorbed_primary_issue_ids:
        notes.extend(_build_dual_pass_absorbed_primary_notes("pipeline", absorbed_primary_issue_ids))
    merged["quality_notes"] = dedupe_text_list(notes)

    merged["top_blockers"] = reorder_top_blockers_by_preference(merged, original_top_blockers)
    if original_score in {"A", "B", "C", "D"}:
        merged["document_quality_score"] = original_score
        if original_score_reason:
            merged["score_reason"] = original_score_reason
    else:
        merged["document_quality_score"], merged["score_reason"] = stable_score(merged)

    _dedupe_dual_pass_report_collisions(merged)
    merged = _format_dual_pass_multisymptom_report(merged)

    summary = {
        "added_findings": added_findings,
        "absorbed_split_findings": len(suppressed_candidate_issue_ids),
        "absorbed_primary_findings": len(absorbed_primary_issue_ids),
        "duplicate_titles": duplicate_titles,
        "unsupported_findings": len(secondary_review.get("unsupported_findings") or []),
        "merge_recommendations": len(secondary_review.get("merge_recommendations") or []),
        "phase2_admission": {
            "enabled": enforce_phase2_admission,
            "claimed_count": len(admission_results) if enforce_phase2_admission else len(
                [item for item in secondary_review.get("missed_findings") or [] if isinstance(item, dict)]
            ),
            "admitted_count": sum(item.get("status") == "admitted" for item in admission_results),
            "rejected_count": sum(item.get("status") == "rejected" for item in admission_results),
            "all_passed": not enforce_phase2_admission
            or (
                coverage_ledger_evaluation.get("passed") is True
                and all(item.get("status") == "admitted" for item in admission_results)
            ),
            "results": admission_results,
            "coverage_ledger": coverage_ledger_evaluation,
            "protocol_gate": protocol_gate_evaluation,
        },
    }
    assert_report_integrity(merged)
    return merged, summary


def build_dual_pass_comparison_summary(pipeline_report: dict[str, Any], candidate_report: dict[str, Any]) -> dict[str, Any]:
    pipeline_findings = _index_dual_pass_findings_for_comparison(pipeline_report)
    candidate_findings = _index_dual_pass_findings_for_comparison(candidate_report)
    pipeline_only_keys = [key for key in pipeline_findings if key not in candidate_findings]
    candidate_only_keys = [key for key in candidate_findings if key not in pipeline_findings]
    materially_changed_examples: list[dict[str, Any]] = []
    for shared_key in [key for key in pipeline_findings if key in candidate_findings]:
        pipeline_finding = public_finding(pipeline_findings[shared_key])
        candidate_finding = public_finding(candidate_findings[shared_key])
        change_kinds = _dual_pass_shared_finding_change_kinds(pipeline_finding, candidate_finding)
        if not change_kinds:
            continue
        materially_changed_examples.append(
            {
                "compare_key": shared_key,
                "issue_id": str(candidate_finding.get("issue_id") or pipeline_finding.get("issue_id") or "").strip(),
                "title": str(
                    candidate_finding.get("title")
                    or candidate_finding.get("canonical_title")
                    or pipeline_finding.get("title")
                    or pipeline_finding.get("canonical_title")
                    or "unknown finding"
                ).strip(),
                "change_kinds": change_kinds,
            }
        )
    return {
        "pipeline_only_count": len(pipeline_only_keys),
        "candidate_only_count": len(candidate_only_keys),
        "pipeline_only_titles": [
            str(public_finding(pipeline_findings[key]).get("title") or "未命名问题") for key in pipeline_only_keys[:10]
        ],
        "candidate_only_titles": [
            str(public_finding(candidate_findings[key]).get("title") or "未命名问题") for key in candidate_only_keys[:10]
        ],
        "materially_changed_count": len(materially_changed_examples),
        "materially_changed_titles": [str(item.get("title") or "") for item in materially_changed_examples[:10]],
        "materially_changed_examples": materially_changed_examples[:10],
    }


def build_dual_pass_lineage_counts(candidate_lineage: dict[str, Any]) -> dict[str, int]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    return {
        "kept": len([item for item in lineage.get("kept") or [] if isinstance(item, dict)]),
        "added": len([item for item in lineage.get("added") or [] if isinstance(item, dict)]),
        "merged": len([item for item in lineage.get("merged") or [] if isinstance(item, dict)]),
        "dropped": len([item for item in lineage.get("dropped") or [] if isinstance(item, dict)]),
    }


def _dual_pass_issue_id_set(report: dict[str, Any] | None) -> set[str]:
    return {
        str(finding.get("issue_id") or "").strip()
        for finding in collect_all_findings(report or {})
        if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    }


def _is_untitled_finding_title(value: Any) -> bool:
    normalized_title = normalize_compare_text(str(value or "").strip())
    return normalized_title in {
        "",
        normalize_compare_text("未命名问题"),
        normalize_compare_text("未命名"),
        normalize_compare_text("unknown finding"),
    }


def _build_title_fallback(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    if len(text) <= 40:
        return text
    return text[:40].rstrip() + "..."


def _ensure_finding_has_title(finding: dict[str, Any]) -> None:
    if not isinstance(finding, dict):
        return
    if not _is_untitled_finding_title(finding.get("title")):
        if not str(finding.get("canonical_title") or "").strip():
            finding["canonical_title"] = str(finding.get("title") or "").strip()
        return
    for key in ("canonical_title", "description", "current_state", "risk", "evidence"):
        fallback = _build_title_fallback(finding.get(key))
        if fallback:
            finding["title"] = fallback
            if not str(finding.get("canonical_title") or "").strip():
                finding["canonical_title"] = fallback
            return


def collect_dual_pass_untitled_finding_issue_ids(report: dict[str, Any] | None) -> list[str]:
    untitled: list[str] = []
    for finding in collect_all_findings(report or {}):
        if not isinstance(finding, dict):
            continue
        if not _is_untitled_finding_title(finding.get("title")):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        untitled.append(issue_id or "untitled_finding")
    return untitled


def collect_dual_pass_missing_issue_id_finding_titles(report: dict[str, Any] | None) -> list[str]:
    missing_titles: list[str] = []
    for finding in collect_all_findings(report or {}):
        if not isinstance(finding, dict):
            continue
        if str(finding.get("issue_id") or "").strip():
            continue
        title = str(finding.get("title") or finding.get("canonical_title") or "").strip()
        missing_titles.append(title or "untitled_finding")
    return missing_titles


def build_dual_pass_materialized_lineage_counts(
    candidate_lineage: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
) -> dict[str, int]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    candidate_findings = [finding for finding in collect_all_findings(candidate_report or {}) if isinstance(finding, dict)]
    issue_ids = {str(finding.get("issue_id") or "").strip() for finding in candidate_findings if str(finding.get("issue_id") or "").strip()}

    counts = {"kept": 0, "added": 0, "merged": 0, "dropped": 0}
    for item in lineage.get("kept") or []:
        if not isinstance(item, dict):
            continue
        primary_ids = {str(value).strip() for value in (item.get("primary_issue_ids") or []) if str(value).strip()}
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if (candidate_issue_id and candidate_issue_id in issue_ids) or primary_ids.intersection(issue_ids):
            counts["kept"] += 1
    for item in lineage.get("added") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        source_ids = {str(value).strip() for value in (item.get("source_missed_issue_ids") or []) if str(value).strip()}
        if (candidate_issue_id and candidate_issue_id in issue_ids) or source_ids.intersection(issue_ids):
            counts["added"] += 1
    for item in lineage.get("merged") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if candidate_issue_id and candidate_issue_id in issue_ids:
            counts["merged"] += 1
    for item in lineage.get("dropped") or []:
        if not isinstance(item, dict):
            continue
        primary_issue_id = str(item.get("primary_issue_id") or "").strip()
        if primary_issue_id and primary_issue_id not in issue_ids:
            counts["dropped"] += 1
    return counts


def evaluate_dual_pass_added_materialization_status(
    candidate_lineage: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
) -> dict[str, Any]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    added_items = [item for item in (lineage.get("added") or []) if isinstance(item, dict)]
    materialized_counts = build_dual_pass_materialized_lineage_counts(lineage, candidate_report)
    total_added = len(added_items)
    materialized_added = materialized_counts.get("added", 0)
    issue_ids = {
        str(finding.get("issue_id") or "").strip()
        for finding in collect_all_findings(candidate_report or {})
        if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    }
    missing_ids = [
        str(item.get("candidate_issue_id") or "").strip()
        for item in added_items
        if str(item.get("candidate_issue_id") or "").strip()
        and str(item.get("candidate_issue_id") or "").strip() not in issue_ids
        and not {
            str(value).strip() for value in (item.get("source_missed_issue_ids") or []) if str(value).strip()
        }.intersection(issue_ids)
    ]
    if total_added == 0:
        status = "none"
    elif materialized_added >= total_added:
        status = "complete"
    elif materialized_added > 0:
        status = "partial"
    else:
        status = "missing"
    return {
        "status": status,
        "total_added": total_added,
        "materialized_added": materialized_added,
        "missing_candidate_issue_ids": missing_ids,
    }


def evaluate_dual_pass_merged_materialization_status(
    candidate_lineage: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
) -> dict[str, Any]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    merged_items = [item for item in (lineage.get("merged") or []) if isinstance(item, dict)]
    total_merged = len(merged_items)
    issue_ids = {
        str(finding.get("issue_id") or "").strip()
        for finding in collect_all_findings(candidate_report or {})
        if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    }
    materialized_ids = [
        str(item.get("candidate_issue_id") or "").strip()
        for item in merged_items
        if str(item.get("candidate_issue_id") or "").strip() in issue_ids
    ]
    missing_ids = [
        str(item.get("candidate_issue_id") or "").strip()
        for item in merged_items
        if str(item.get("candidate_issue_id") or "").strip()
        and str(item.get("candidate_issue_id") or "").strip() not in issue_ids
    ]
    materialized_merged = len(materialized_ids)
    if total_merged == 0:
        status = "none"
    elif materialized_merged >= total_merged:
        status = "complete"
    elif materialized_merged > 0:
        status = "partial"
    else:
        status = "missing"
    return {
        "status": status,
        "total_merged": total_merged,
        "materialized_merged": materialized_merged,
        "materialized_candidate_issue_ids": dedupe_text_list(materialized_ids),
        "missing_candidate_issue_ids": dedupe_text_list(missing_ids),
    }


def _dual_pass_auto_keep_lineage_items(
    primary_report: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
    covered_primary_issue_ids: set[str],
    covered_candidate_issue_ids: set[str],
) -> list[dict[str, Any]]:
    primary_candidates = [
        finding
        for finding in collect_all_findings(primary_report or {})
        if isinstance(finding, dict)
        and str(finding.get("issue_id") or "").strip()
        and str(finding.get("issue_id") or "").strip() not in covered_primary_issue_ids
    ]
    candidate_candidates = [
        finding
        for finding in collect_all_findings(candidate_report or {})
        if isinstance(finding, dict)
        and str(finding.get("issue_id") or "").strip()
        and str(finding.get("issue_id") or "").strip() not in covered_candidate_issue_ids
    ]
    if not primary_candidates or not candidate_candidates:
        return []

    def finding_dimension(finding: dict[str, Any]) -> str:
        return normalize_dimension_name(finding.get("primary_dimension"), fallback=DIMENSIONS[0])

    def title_key(finding: dict[str, Any]) -> str:
        return normalize_compare_text(str(finding.get("title") or finding.get("canonical_title") or "").strip())

    primary_by_root: dict[tuple[str, str], list[dict[str, Any]]] = {}
    candidate_by_root: dict[tuple[str, str], list[dict[str, Any]]] = {}
    primary_by_title: dict[tuple[str, str], list[dict[str, Any]]] = {}
    candidate_by_title: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for finding in primary_candidates:
        root_key = build_root_cause_key(finding)
        dimension = finding_dimension(finding)
        if root_key:
            primary_by_root.setdefault((dimension, root_key), []).append(finding)
        current_title_key = title_key(finding)
        if current_title_key:
            primary_by_title.setdefault((dimension, current_title_key), []).append(finding)
    for finding in candidate_candidates:
        root_key = build_root_cause_key(finding)
        dimension = finding_dimension(finding)
        if root_key:
            candidate_by_root.setdefault((dimension, root_key), []).append(finding)
        current_title_key = title_key(finding)
        if current_title_key:
            candidate_by_title.setdefault((dimension, current_title_key), []).append(finding)

    auto_kept_items: list[dict[str, Any]] = []
    used_primary_ids: set[str] = set()
    used_candidate_ids: set[str] = set()

    def append_unique_pairs(
        primary_map: dict[tuple[str, str], list[dict[str, Any]]],
        candidate_map: dict[tuple[str, str], list[dict[str, Any]]],
        match_kind: str,
    ) -> None:
        for key, primary_items in primary_map.items():
            candidate_items = candidate_map.get(key) or []
            if len(primary_items) != 1 or len(candidate_items) != 1:
                continue
            primary_finding = primary_items[0]
            candidate_finding = candidate_items[0]
            primary_issue_id = str(primary_finding.get("issue_id") or "").strip()
            candidate_issue_id = str(candidate_finding.get("issue_id") or "").strip()
            if (
                not primary_issue_id
                or not candidate_issue_id
                or primary_issue_id in used_primary_ids
                or candidate_issue_id in used_candidate_ids
            ):
                continue
            auto_kept_items.append(
                {
                    "candidate_issue_id": candidate_issue_id,
                    "primary_issue_ids": [primary_issue_id],
                    "auto_healed": True,
                    "auto_match_kind": match_kind,
                }
            )
            used_primary_ids.add(primary_issue_id)
            used_candidate_ids.add(candidate_issue_id)

    append_unique_pairs(primary_by_root, candidate_by_root, "root_key")
    append_unique_pairs(primary_by_title, candidate_by_title, "title")
    return auto_kept_items


def _dual_pass_collect_multiroot_kept_titles(
    primary_report: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
    assessment_issues: list[str] | None,
    review_notes: list[str] | None,
) -> list[str]:
    source_texts = [str(item).strip() for item in (assessment_issues or []) if str(item).strip()]
    source_texts.extend(str(item).strip() for item in (review_notes or []) if str(item).strip())
    if not source_texts:
        return []
    keywords = ("多个不同根因", "混杂", "混在一个条目", "未按根因拆分", "建议进一步拆分", "建议后续拆分")
    matched_titles: list[str] = []
    findings = list(collect_all_findings(candidate_report or {})) + list(collect_all_findings(primary_report or {}))
    seen_signatures: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        issue_id = str(finding.get("issue_id") or "").strip()
        title = str(finding.get("title") or finding.get("canonical_title") or "").strip()
        signature = f"{issue_id}::{title}"
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        for text in source_texts:
            if not any(keyword in text for keyword in keywords):
                continue
            if issue_id and issue_id in text:
                matched_titles.append(title or issue_id)
                break
            if title and title in text:
                matched_titles.append(title)
                break
            if title:
                short_title = re.sub(r"[“”\"'（）()]", "", title)
                if len(short_title) >= 4 and short_title in text:
                    matched_titles.append(title)
                    break
    return dedupe_text_list(matched_titles)


def _dual_pass_structure_sequence(report: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    findings = [finding for finding in collect_all_findings(report or {}) if isinstance(finding, dict)]
    title_sequence: list[str] = []
    dimension_sequence: list[str] = []
    for finding in findings:
        title = str(finding.get("title") or finding.get("canonical_title") or "").strip()
        title_sequence.append(normalize_compare_text(title or "未命名问题"))
        dimension_sequence.append(normalize_dimension_name(finding.get("primary_dimension"), fallback=DIMENSIONS[0]))
    return findings, title_sequence, dimension_sequence


def _dual_pass_normalize_comparable_text(value: Any) -> str:
    parts = _dual_pass_split_multisymptom_text(value)
    if parts:
        normalized_parts = [re.sub(r"^\d+[、.．]\s*", "", str(part).strip()) for part in parts if str(part).strip()]
        return normalize_compare_text("；".join(normalized_parts))
    return normalize_compare_text(str(value or "").strip())


def _dual_pass_shared_finding_change_kinds(
    pipeline_finding: dict[str, Any],
    candidate_finding: dict[str, Any],
) -> list[str]:
    change_kinds: list[str] = []
    if _dual_pass_normalize_comparable_text(
        pipeline_finding.get("title") or pipeline_finding.get("canonical_title")
    ) != _dual_pass_normalize_comparable_text(candidate_finding.get("title") or candidate_finding.get("canonical_title")):
        change_kinds.append("title_changed")
    if normalize_dimension_name(pipeline_finding.get("primary_dimension"), fallback=DIMENSIONS[0]) != normalize_dimension_name(
        candidate_finding.get("primary_dimension"),
        fallback=DIMENSIONS[0],
    ):
        change_kinds.append("dimension_changed")
    if str(pipeline_finding.get("severity") or "").strip() != str(candidate_finding.get("severity") or "").strip():
        change_kinds.append("severity_changed")
    if str(pipeline_finding.get("blocking") or "").strip() != str(candidate_finding.get("blocking") or "").strip():
        change_kinds.append("blocking_changed")
    for field in ("current_state", "risk", "suggestion"):
        if _dual_pass_normalize_comparable_text(pipeline_finding.get(field)) != _dual_pass_normalize_comparable_text(
            candidate_finding.get(field)
        ):
            change_kinds.append(f"{field}_changed")
    return change_kinds


def build_dual_pass_traceability_diagnostics(
    primary_report: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
    candidate_lineage: dict[str, Any] | None,
) -> dict[str, Any]:
    lineage_counts = build_dual_pass_lineage_counts(candidate_lineage or {})
    lineage_total = sum(max(int(value or 0), 0) for value in lineage_counts.values())
    primary_issue_id_repair_count = int((primary_report or {}).get("_issue_id_repair_count") or 0)
    candidate_issue_id_repair_count = int((candidate_report or {}).get("_issue_id_repair_count") or 0)
    if not candidate_report:
        return {
            "traceability_status": "unavailable",
            "candidate_structure_drift": False,
            "count_changed": False,
            "title_set_changed": False,
            "order_changed": False,
            "dimension_changed": False,
            "lineage_counts": lineage_counts,
            "lineage_coverage_complete": False,
            "unmapped_primary_issue_ids": [],
            "unmapped_candidate_issue_ids": [],
            "invalid_primary_lineage_ids": [],
            "invalid_candidate_lineage_ids": [],
            "duplicate_primary_lineage_ids": [],
            "duplicate_candidate_lineage_ids": [],
            "primary_issue_id_repair_count": primary_issue_id_repair_count,
            "candidate_issue_id_repair_count": candidate_issue_id_repair_count,
            "lineage_auto_healed": False,
            "lineage_auto_mapped_primary_issue_ids": [],
            "lineage_auto_mapped_candidate_issue_ids": [],
            "trace_warning": "",
        }

    primary_findings, primary_title_sequence, primary_dimension_sequence = _dual_pass_structure_sequence(primary_report)
    candidate_findings, candidate_title_sequence, candidate_dimension_sequence = _dual_pass_structure_sequence(candidate_report)
    count_changed = len(primary_findings) != len(candidate_findings)
    title_set_changed = set(primary_title_sequence) != set(candidate_title_sequence)
    order_changed = primary_title_sequence != candidate_title_sequence
    dimension_changed = primary_dimension_sequence != candidate_dimension_sequence
    raw_structure_change = count_changed or title_set_changed or order_changed or dimension_changed

    primary_issue_ids = _dual_pass_issue_id_set(primary_report)
    candidate_issue_ids = _dual_pass_issue_id_set(candidate_report)
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    covered_primary_issue_ids: set[str] = set()
    covered_candidate_issue_ids: set[str] = set()
    invalid_primary_lineage_ids: set[str] = set()
    invalid_candidate_lineage_ids: set[str] = set()
    duplicate_primary_lineage_ids: set[str] = set()
    duplicate_candidate_lineage_ids: set[str] = set()
    primary_reference_counts: dict[str, int] = {}
    candidate_reference_counts: dict[str, int] = {}

    def mark_primary_issue(issue_id: str) -> None:
        normalized_issue_id = str(issue_id or "").strip()
        if not normalized_issue_id:
            return
        primary_reference_counts[normalized_issue_id] = primary_reference_counts.get(normalized_issue_id, 0) + 1
        if normalized_issue_id in primary_reference_counts and primary_reference_counts[normalized_issue_id] > 1:
            duplicate_primary_lineage_ids.add(normalized_issue_id)
        if normalized_issue_id in primary_issue_ids:
            covered_primary_issue_ids.add(normalized_issue_id)
        else:
            invalid_primary_lineage_ids.add(normalized_issue_id)

    def mark_candidate_issue(issue_id: str) -> None:
        normalized_issue_id = str(issue_id or "").strip()
        if not normalized_issue_id:
            return
        candidate_reference_counts[normalized_issue_id] = candidate_reference_counts.get(normalized_issue_id, 0) + 1
        if normalized_issue_id in candidate_reference_counts and candidate_reference_counts[normalized_issue_id] > 1:
            duplicate_candidate_lineage_ids.add(normalized_issue_id)
        if normalized_issue_id in candidate_issue_ids:
            covered_candidate_issue_ids.add(normalized_issue_id)
        else:
            invalid_candidate_lineage_ids.add(normalized_issue_id)

    for item in lineage.get("kept") or []:
        if not isinstance(item, dict):
            continue
        mark_candidate_issue(item.get("candidate_issue_id"))
        for issue_id in item.get("primary_issue_ids") or []:
            mark_primary_issue(issue_id)
    for item in lineage.get("added") or []:
        if not isinstance(item, dict):
            continue
        mark_candidate_issue(item.get("candidate_issue_id"))
    for item in lineage.get("merged") or []:
        if not isinstance(item, dict):
            continue
        mark_candidate_issue(item.get("candidate_issue_id"))
        for issue_id in item.get("primary_issue_ids") or []:
            mark_primary_issue(issue_id)
    for item in lineage.get("dropped") or []:
        if not isinstance(item, dict):
            continue
        mark_primary_issue(item.get("primary_issue_id"))

    auto_mapped_primary_issue_ids = sorted(
        {
            str(value).strip()
            for item in (lineage.get("kept") or [])
            if isinstance(item, dict) and item.get("auto_healed")
            for value in (item.get("primary_issue_ids") or [])
            if str(value).strip()
        }
    )
    auto_mapped_candidate_issue_ids = sorted(
        {
            str(item.get("candidate_issue_id") or "").strip()
            for item in (lineage.get("kept") or [])
            if isinstance(item, dict) and item.get("auto_healed") and str(item.get("candidate_issue_id") or "").strip()
        }
    )
    lineage_auto_healed = bool(auto_mapped_primary_issue_ids or auto_mapped_candidate_issue_ids)

    unmapped_primary_issue_ids = sorted(primary_issue_ids - covered_primary_issue_ids)
    unmapped_candidate_issue_ids = sorted(candidate_issue_ids - covered_candidate_issue_ids)
    lineage_coverage_complete = (
        bool(candidate_report)
        and bool(primary_issue_ids or candidate_issue_ids)
        and not unmapped_primary_issue_ids
        and not unmapped_candidate_issue_ids
        and not invalid_primary_lineage_ids
        and not invalid_candidate_lineage_ids
    )

    structure_change_explained_by_lineage = (
        raw_structure_change
        and lineage_total > 0
        and lineage_coverage_complete
        and not invalid_primary_lineage_ids
        and not invalid_candidate_lineage_ids
        and not duplicate_primary_lineage_ids
        and not duplicate_candidate_lineage_ids
    )
    structure_drift = raw_structure_change and not structure_change_explained_by_lineage

    if lineage_total > 0 and lineage_coverage_complete:
        traceability_status = "complete"
        trace_warning = ""
    elif lineage_total > 0:
        traceability_status = "partial"
        trace_warning = "candidate_lineage present but does not fully cover primary/candidate findings"
    elif structure_drift:
        traceability_status = "missing"
        trace_warning = "candidate_lineage missing or empty; candidate changed structure without traceability"
    else:
        traceability_status = "minimal"
        trace_warning = "candidate_lineage missing or empty; candidate stayed near primary structure"

    return {
        "traceability_status": traceability_status,
        "candidate_structure_drift": structure_drift,
        "raw_structure_change": raw_structure_change,
        "structure_change_explained_by_lineage": structure_change_explained_by_lineage,
        "count_changed": count_changed,
        "title_set_changed": title_set_changed,
        "order_changed": order_changed,
        "dimension_changed": dimension_changed,
        "lineage_counts": lineage_counts,
        "lineage_coverage_complete": lineage_coverage_complete,
        "unmapped_primary_issue_ids": unmapped_primary_issue_ids,
        "unmapped_candidate_issue_ids": unmapped_candidate_issue_ids,
        "invalid_primary_lineage_ids": sorted(invalid_primary_lineage_ids),
        "invalid_candidate_lineage_ids": sorted(invalid_candidate_lineage_ids),
        "duplicate_primary_lineage_ids": sorted(duplicate_primary_lineage_ids),
        "duplicate_candidate_lineage_ids": sorted(duplicate_candidate_lineage_ids),
        "primary_issue_id_repair_count": primary_issue_id_repair_count,
        "candidate_issue_id_repair_count": candidate_issue_id_repair_count,
        "lineage_auto_healed": lineage_auto_healed,
        "lineage_auto_mapped_primary_issue_ids": auto_mapped_primary_issue_ids,
        "lineage_auto_mapped_candidate_issue_ids": auto_mapped_candidate_issue_ids,
        "trace_warning": trace_warning,
    }


def _dual_pass_reason_targets_primary_report(text: str) -> bool:
    normalized = normalize_compare_text(text or "")
    if not normalized:
        return False
    mentions_primary = any(token in normalized for token in ("主模型", "首版报告", "primary report", "primary"))
    mentions_candidate = any(token in normalized for token in ("候选稿", "candidate", "直出", "可交付"))
    return mentions_primary and not mentions_candidate


def _dual_pass_absorbed_added_by_kept_candidate(
    candidate_lineage: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
) -> tuple[dict[str, list[str]], set[str]]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    candidate_issue_ids = _dual_pass_build_candidate_issue_id_set(candidate_report)
    added_items = [item for item in (lineage.get("added") or []) if isinstance(item, dict)]
    added_candidate_ids = {
        str(item.get("candidate_issue_id") or "").strip()
        for item in added_items
        if str(item.get("candidate_issue_id") or "").strip()
    }
    added_by_candidate_issue_id = {
        str(item.get("candidate_issue_id") or "").strip(): item
        for item in added_items
        if str(item.get("candidate_issue_id") or "").strip()
    }
    absorbed_by_kept_candidate: dict[str, list[str]] = {}
    absorbed_added_candidate_ids: set[str] = set()

    for item in lineage.get("dropped") or []:
        if not isinstance(item, dict):
            continue
        primary_issue_id = str(item.get("primary_issue_id") or "").strip()
        explicit_target_ids = [
            str(value).strip()
            for value in list(item.get("target_candidate_issue_ids") or []) + [item.get("target_candidate_issue_id")]
            if str(value or "").strip()
        ]
        extracted_target_ids = _dual_pass_extract_candidate_issue_ids_from_text(
            f"{item.get('disposition') or ''} {item.get('reason') or ''}",
            added_candidate_ids,
        )
        target_candidate_issue_ids = dedupe_text_list(explicit_target_ids + extracted_target_ids)
        if not target_candidate_issue_ids:
            continue
        absorbed_source_missed_issue_ids: list[str] = []
        for target_candidate_issue_id in target_candidate_issue_ids:
            added_item = added_by_candidate_issue_id.get(target_candidate_issue_id)
            if not added_item:
                continue
            source_missed_issue_ids = [
                str(value).strip()
                for value in (added_item.get("source_missed_issue_ids") or [])
                if str(value).strip()
            ]
            if not source_missed_issue_ids:
                continue
            absorbed_added_candidate_ids.add(target_candidate_issue_id)
            absorbed_source_missed_issue_ids.extend(source_missed_issue_ids)

        if not absorbed_source_missed_issue_ids:
            continue

        preferred_kept_candidate_issue_id = next(
            (candidate_issue_id for candidate_issue_id in target_candidate_issue_ids if candidate_issue_id in candidate_issue_ids),
            "",
        )
        if not preferred_kept_candidate_issue_id and primary_issue_id in candidate_issue_ids:
            preferred_kept_candidate_issue_id = primary_issue_id
        if not preferred_kept_candidate_issue_id:
            continue

        absorbed_by_kept_candidate[preferred_kept_candidate_issue_id] = dedupe_text_list(
            list(absorbed_by_kept_candidate.get(preferred_kept_candidate_issue_id) or [])
            + absorbed_source_missed_issue_ids
        )

    return absorbed_by_kept_candidate, absorbed_added_candidate_ids


def reconcile_dual_pass_lineage_to_candidate_report(
    primary_report: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
    candidate_lineage: dict[str, Any] | None,
    missed_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    lineage = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    primary = primary_report if isinstance(primary_report, dict) else {}
    candidate = candidate_report if isinstance(candidate_report, dict) else {}

    primary_findings = [
        finding for finding in collect_all_findings(primary) if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    ]
    candidate_findings = [
        finding for finding in collect_all_findings(candidate) if isinstance(finding, dict) and str(finding.get("issue_id") or "").strip()
    ]
    primary_issue_ids = {str(finding.get("issue_id") or "").strip() for finding in primary_findings}
    candidate_issue_ids = {str(finding.get("issue_id") or "").strip() for finding in candidate_findings}

    absorbed_added_by_kept_candidate, absorbed_added_candidate_ids = _dual_pass_absorbed_added_by_kept_candidate(
        lineage,
        candidate,
    )
    reconciled: dict[str, list[dict[str, Any]]] = {"kept": [], "added": [], "merged": [], "dropped": []}
    kept_keys: set[tuple[str, tuple[str, ...]]] = set()
    kept_primary_ids: set[str] = set()
    covered_candidate_ids: set[str] = set()

    for item in lineage.get("kept") or []:
        if not isinstance(item, dict):
            continue
        raw_primary_issue_ids = [str(value).strip() for value in (item.get("primary_issue_ids") or []) if str(value).strip()]
        primary_issue_ids_for_item = [
            issue_id for issue_id in raw_primary_issue_ids if not primary_issue_ids or issue_id in primary_issue_ids
        ]
        if not primary_issue_ids_for_item:
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if candidate_issue_id not in candidate_issue_ids:
            candidate_issue_id = next((issue_id for issue_id in primary_issue_ids_for_item if issue_id in candidate_issue_ids), "")
        if not candidate_issue_id:
            continue
        key = (candidate_issue_id, tuple(sorted(dict.fromkeys(primary_issue_ids_for_item))))
        if key in kept_keys:
            continue
        normalized_item = dict(item)
        normalized_item["candidate_issue_id"] = candidate_issue_id
        normalized_item["primary_issue_ids"] = list(dict.fromkeys(primary_issue_ids_for_item))
        absorbed_missed_issue_ids = dedupe_text_list(
            [
                str(value).strip()
                for value in list(item.get("absorbed_missed_issue_ids") or [])
                + list(absorbed_added_by_kept_candidate.get(candidate_issue_id) or [])
                if str(value).strip()
            ]
        )
        if absorbed_missed_issue_ids:
            normalized_item["absorbed_missed_issue_ids"] = absorbed_missed_issue_ids
        reconciled["kept"].append(normalized_item)
        kept_keys.add(key)
        covered_candidate_ids.add(candidate_issue_id)
        kept_primary_ids.update(primary_issue_ids_for_item)

    for item in lineage.get("added") or []:
        if not isinstance(item, dict):
            continue
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if candidate_issue_id and candidate_issue_id in absorbed_added_candidate_ids:
            continue
        reconciled["added"].append(dict(item))
        if candidate_issue_id:
            covered_candidate_ids.add(candidate_issue_id)

    for item in lineage.get("merged") or []:
        if not isinstance(item, dict):
            continue
        reconciled["merged"].append(dict(item))
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        primary_issue_ids_for_item = [
            str(value).strip()
            for value in (item.get("primary_issue_ids") or [])
            if str(value).strip() and (not primary_issue_ids or str(value).strip() in primary_issue_ids)
        ]
        if candidate_issue_id:
            covered_candidate_ids.add(candidate_issue_id)
        kept_primary_ids.update(primary_issue_ids_for_item)

    for item in lineage.get("dropped") or []:
        if not isinstance(item, dict):
            continue
        primary_issue_id = str(item.get("primary_issue_id") or "").strip()
        if not primary_issue_id or primary_issue_id in candidate_issue_ids:
            continue
        if primary_issue_ids and primary_issue_id not in primary_issue_ids:
            continue
        reconciled["dropped"].append(dict(item))
        kept_primary_ids.add(primary_issue_id)

    implicit_kept_issue_ids = sorted((primary_issue_ids & candidate_issue_ids) - kept_primary_ids - covered_candidate_ids)
    for issue_id in implicit_kept_issue_ids:
        key = (issue_id, (issue_id,))
        if key in kept_keys:
            continue
        implicit_kept_item: dict[str, Any] = {"candidate_issue_id": issue_id, "primary_issue_ids": [issue_id]}
        absorbed_missed_issue_ids = dedupe_text_list(
            [str(value).strip() for value in (absorbed_added_by_kept_candidate.get(issue_id) or []) if str(value).strip()]
        )
        if absorbed_missed_issue_ids:
            implicit_kept_item["absorbed_missed_issue_ids"] = absorbed_missed_issue_ids
        reconciled["kept"].append(implicit_kept_item)
        kept_keys.add(key)
        covered_candidate_ids.add(issue_id)
        kept_primary_ids.add(issue_id)

    for item in _dual_pass_auto_keep_lineage_items(primary, candidate, kept_primary_ids, covered_candidate_ids):
        primary_issue_ids_for_item = [
            str(value).strip() for value in (item.get("primary_issue_ids") or []) if str(value).strip()
        ]
        candidate_issue_id = str(item.get("candidate_issue_id") or "").strip()
        if not candidate_issue_id or not primary_issue_ids_for_item:
            continue
        key = (candidate_issue_id, tuple(sorted(dict.fromkeys(primary_issue_ids_for_item))))
        if key in kept_keys:
            continue
        reconciled["kept"].append(dict(item))
        kept_keys.add(key)
        covered_candidate_ids.add(candidate_issue_id)
        kept_primary_ids.update(primary_issue_ids_for_item)

    return reconciled


def normalize_dual_pass_advice_payload(
    primary_report: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
    secondary_review: dict[str, Any] | None,
) -> dict[str, Any]:
    review = secondary_review if isinstance(secondary_review, dict) else {}
    candidate_lineage = reconcile_dual_pass_lineage_to_candidate_report(
        primary_report,
        candidate_report,
        review.get("candidate_lineage") if isinstance(review.get("candidate_lineage"), dict) else {},
        review.get("missed_findings") if isinstance(review.get("missed_findings"), list) else [],
    )
    assessment = dict(review.get("quality_assessment") or {})
    readiness = dict(review.get("candidate_readiness") or {})
    strengths = assessment.get("strengths")
    issues = assessment.get("issues")
    review_notes = review.get("review_notes")
    normalized_notes = [str(item).strip() for item in (review_notes if isinstance(review_notes, list) else []) if str(item).strip()]
    assessment["strengths"] = [str(item).strip() for item in (strengths if isinstance(strengths, list) else []) if str(item).strip()]
    assessment["issues"] = [str(item).strip() for item in (issues if isinstance(issues, list) else []) if str(item).strip()]

    qa_ready = assessment.get("ready_for_direct_output") is True
    candidate_ready = readiness.get("ready_for_direct_output") is True
    raw_readiness_conflict = qa_ready != candidate_ready

    diagnostics = build_dual_pass_traceability_diagnostics(
        primary_report,
        candidate_report,
        candidate_lineage,
    )
    advice_consistency = _dual_pass_advice_consistency_diagnostics(
        candidate_report,
        candidate_lineage,
        review.get("missed_findings") or [],
    )
    lineage_materialization = evaluate_dual_pass_added_materialization_status(
        candidate_lineage,
        candidate_report,
    )
    merged_materialization = evaluate_dual_pass_merged_materialization_status(
        candidate_lineage,
        candidate_report,
    )
    candidate_consistency = _dual_pass_candidate_consistency_diagnostics(
        primary_report,
        candidate_report,
        candidate_lineage,
        review,
    )
    if diagnostics["traceability_status"] == "missing":
        normalized_notes.append(
            "dual_pass trace 提示：candidate_lineage 为空，且 candidate 相比 primary 存在明显结构变化；当前候选稿可读但不可追踪。"
        )
    elif diagnostics["traceability_status"] == "minimal":
        normalized_notes.append(
            "dual_pass trace 提示：candidate_lineage 为空，但 candidate 与 primary 基本同构；当前候选稿仅保留为可浏览版本，不建议默认直出。"
        )
    elif diagnostics["traceability_status"] == "partial":
        normalized_notes.append(
            "dual_pass trace 提示：candidate_lineage 不为空，但未完整覆盖 primary/candidate 的问题血缘；当前候选稿暂不建议默认直出。"
        )
    if diagnostics["unmapped_primary_issue_ids"] or diagnostics["unmapped_candidate_issue_ids"]:
        normalized_notes.append(
            "dual_pass trace 提示：candidate 存在未被 lineage 覆盖的问题映射，需补齐 kept/added/merged/dropped 后再考虑默认直出。"
        )
    if diagnostics["primary_issue_id_repair_count"] or diagnostics["candidate_issue_id_repair_count"]:
        normalized_notes.append(
            "dual_pass 协议提示：系统已对缺失 issue_id 的 finding 做稳定修复，并按修复后的 issue_id 参与 lineage 与 candidate 门槛判断。"
        )
    if diagnostics["lineage_auto_healed"]:
        normalized_notes.append(
            "dual_pass trace 提示：部分 kept 映射由系统按同维度同根因或同标题关系自动补齐，当前已纳入 traceability 判断。"
        )
    if lineage_materialization["status"] in {"partial", "missing"}:
        normalized_notes.append(
            "dual_pass 补漏落盘提示：candidate_lineage.added 中声明的新增问题未完整落入最终 candidate。"
        )
    if merged_materialization["status"] in {"partial", "missing"}:
        normalized_notes.append(
            "dual_pass 合并落盘提示：candidate_lineage.merged 中声明的合并问题未完整落入最终 candidate。"
        )
    absorbed_but_separate = advice_consistency["advice_claimed_absorbed_but_materialized_separately"]
    added_but_missing = advice_consistency["advice_claimed_added_but_not_materialized"]
    materialized_without_added = advice_consistency["materialized_missed_without_added"]
    if absorbed_but_separate:
        normalized_notes.append(
            "dual_pass 协议提示：部分 missed finding 被 lineage 声称已吸收进 kept 问题，但在最终 candidate 中仍以独立问题落盘。"
        )
    if added_but_missing:
        normalized_notes.append(
            "dual_pass 协议提示：部分 lineage.added 声称的新问题未实际落盘到最终 candidate。"
        )
    if materialized_without_added:
        normalized_notes.append(
            "dual_pass 协议提示：部分 missed finding 已在 candidate 中独立落盘，但 lineage.added/kept 未解释其来源。"
        )
    untitled_finding_issue_ids = collect_dual_pass_untitled_finding_issue_ids(candidate_report)
    missing_issue_id_finding_titles = collect_dual_pass_missing_issue_id_finding_titles(candidate_report)
    multiroot_kept_titles = _dual_pass_collect_multiroot_kept_titles(
        primary_report,
        candidate_report,
        assessment.get("issues") or [],
        normalized_notes,
    )
    if missing_issue_id_finding_titles:
        normalized_notes.append("dual_pass candidate 含空 issue_id 问题项，当前仅作为对比稿，不建议默认直出。")
    if multiroot_kept_titles:
        normalized_notes.append(
            "dual_pass 结构提示：candidate 仍保留多根因混合问题，建议继续拆清根因或改为分点展示。"
        )
    if candidate_consistency["candidate_issue_id_split_detected"]:
        normalized_notes.append(
            "dual_pass 一致性提示：candidate 对 kept 问题出现了子编号式 issue_id 拆分，当前不建议默认直出。"
        )
    if candidate_consistency["candidate_negated_primary_finding_still_materialized"]:
        normalized_notes.append(
            "dual_pass 一致性提示：副评审已否定或降级的 primary 高信号问题，仍被 candidate 以原冲突结论落盘。"
        )
    if candidate_consistency["candidate_blocker_conclusion_mismatch"]:
        normalized_notes.append(
            "dual_pass 一致性提示：candidate 的 top_blockers 与实际 findings 结论不同步，需先修正总评与阻塞项。"
        )
    if candidate_consistency["candidate_major_judgment_drift"]:
        normalized_notes.append(
            "dual_pass 一致性提示：candidate 与 primary 存在较大结论漂移，但副评审未给出足够改判依据。"
        )
    if candidate_consistency["candidate_high_signal_demotion_without_support"]:
        normalized_notes.append(
            "dual_pass 一致性提示：candidate 下调了 primary 的高信号核心问题，但副评审未给出明确可兼容实现或反证依据。"
        )
    if candidate_consistency["candidate_overcompressed"]:
        normalized_notes.append(
            "dual_pass 结构提示：candidate 相比 primary 出现明显收缩，且伴随多处共享问题改写，当前不建议默认直出。"
        )

    readiness_conflict_auto_resolved = False
    if raw_readiness_conflict:
        primary_target_reason = str(assessment.get("reason") or "").strip()
        assessment_context = primary_target_reason or "\n".join(
            [
                str(assessment.get("summary") or "").strip(),
                *assessment["issues"],
            ]
        ).strip()
        candidate_structural_green = (
            diagnostics["traceability_status"] == "complete"
            and diagnostics["lineage_coverage_complete"]
            and lineage_materialization["status"] in {"none", "complete"}
            and merged_materialization["status"] in {"none", "complete"}
            and not advice_consistency["advice_candidate_structure_mismatch"]
            and not candidate_consistency["candidate_issue_id_split_detected"]
            and not candidate_consistency["candidate_negated_primary_finding_still_materialized"]
            and not candidate_consistency["candidate_blocker_conclusion_mismatch"]
            and not candidate_consistency["candidate_major_judgment_drift"]
            and not untitled_finding_issue_ids
            and not missing_issue_id_finding_titles
        )
        if (
            not qa_ready
            and candidate_ready
            and candidate_structural_green
            and str(assessment.get("suggestion_level") or "").strip().lower() != "high"
            and _dual_pass_reason_targets_primary_report(assessment_context)
        ):
            readiness_conflict_auto_resolved = True
            assessment["ready_for_direct_output"] = True
            readiness["ready_for_direct_output"] = True
            healed_reason = str(readiness.get("reason") or assessment.get("reason") or "").strip()
            if healed_reason:
                assessment["reason"] = healed_reason
                readiness["reason"] = healed_reason
            normalized_notes.append(
                "dual_pass 协议收敛提示：副模型对主模型首版报告给出负评，但 candidate_readiness=true 且候选稿结构/血缘完整，系统已按候选稿 readiness 自动收敛。"
            )
        else:
            assessment["ready_for_direct_output"] = False
            readiness["ready_for_direct_output"] = False
            conflict_reason = "副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。"
            assessment["reason"] = conflict_reason
            readiness["reason"] = conflict_reason
            normalized_notes.append(
                "dual_pass 协议提示：quality_assessment.ready_for_direct_output 与 candidate_readiness.ready_for_direct_output 不一致，已统一降为 false。"
            )

    qa_ready = assessment.get("ready_for_direct_output") is True
    candidate_ready = readiness.get("ready_for_direct_output") is True
    readiness_conflict = raw_readiness_conflict and not readiness_conflict_auto_resolved
    candidate_structurally_ready = (
        diagnostics["traceability_status"] == "complete"
        and diagnostics["lineage_coverage_complete"]
        and lineage_materialization["status"] in {"none", "complete"}
        and merged_materialization["status"] in {"none", "complete"}
        and not advice_consistency["advice_candidate_structure_mismatch"]
        and not candidate_consistency["candidate_issue_id_split_detected"]
        and not candidate_consistency["candidate_negated_primary_finding_still_materialized"]
        and not candidate_consistency["candidate_blocker_conclusion_mismatch"]
        and not candidate_consistency["candidate_major_judgment_drift"]
        and not untitled_finding_issue_ids
        and not missing_issue_id_finding_titles
    )
    normalized_ready = (
        qa_ready
        and candidate_ready
        and not readiness_conflict
        and candidate_structurally_ready
    )
    normalized_ready_reason = str(readiness.get("reason") or assessment.get("reason") or "").strip()
    if readiness_conflict:
        normalized_ready_reason = "副模型 readiness 标记冲突，系统已统一降为 false；当前候选稿仅保留为可比较版本，不建议默认直出。"
    elif diagnostics["traceability_status"] == "missing":
        normalized_ready_reason = "candidate 相比 primary 存在明显结构变化，但缺少可用 lineage，当前候选稿不可追踪，不建议默认直出。"
    elif diagnostics["traceability_status"] == "minimal":
        normalized_ready_reason = "candidate 与 primary 基本同构，但 lineage 缺失，仅保留为可浏览版本，不建议默认直出。"
    elif diagnostics["traceability_status"] == "partial":
        normalized_ready_reason = "candidate_lineage 未完整覆盖 primary/candidate 的问题血缘，当前候选稿暂不建议默认直出。"
    elif not diagnostics["lineage_coverage_complete"]:
        normalized_ready_reason = "candidate 的 lineage 覆盖不完整，仍存在未映射问题，不建议默认直出。"
    elif lineage_materialization["status"] in {"partial", "missing"}:
        normalized_ready_reason = "candidate_lineage.added 中声明的新增问题未完整落入最终 candidate，不建议默认直出。"
    elif merged_materialization["status"] in {"partial", "missing"}:
        normalized_ready_reason = "candidate_lineage.merged 中声明的合并问题未完整落入最终 candidate，不建议默认直出。"
    elif advice_consistency["advice_candidate_structure_mismatch"]:
        normalized_ready_reason = "candidate_lineage 对 candidate 结构的说明与最终落盘结果不一致，当前候选稿不可作为默认最终输出。"
    elif candidate_consistency["candidate_issue_id_split_detected"]:
        normalized_ready_reason = "candidate 对 kept 问题做了子编号 issue_id 拆分，来源不可稳定追踪，当前不建议默认直出。"
    elif candidate_consistency["candidate_negated_primary_finding_still_materialized"]:
        normalized_ready_reason = "副评审已否定或降级的 primary 高信号问题，仍被 candidate 以原结论落盘，当前不建议默认直出。"
    elif candidate_consistency["candidate_blocker_conclusion_mismatch"]:
        normalized_ready_reason = "candidate 的 top_blockers 与实际 findings 结论不同步，当前不建议默认直出。"
    elif candidate_consistency["candidate_major_judgment_drift"]:
        normalized_ready_reason = "candidate 与 primary 存在较大结论漂移，但副评审未给出足够改判依据，当前不建议默认直出。"
    elif untitled_finding_issue_ids:
        normalized_ready_reason = "candidate 仍存在未命名问题，当前候选稿不建议默认直出。"
    if not normalized_ready_reason and missing_issue_id_finding_titles:
        normalized_ready_reason = "candidate 瀛樺湪空 issue_id 的问题项，当前候选稿不建议默认直出。"
    if not normalized_ready:
        assessment["ready_for_direct_output"] = False
        readiness["ready_for_direct_output"] = False
        if normalized_ready_reason:
            assessment["reason"] = normalized_ready_reason
            readiness["reason"] = normalized_ready_reason
    else:
        assessment["ready_for_direct_output"] = True
        readiness["ready_for_direct_output"] = True
        if normalized_ready_reason:
            assessment["reason"] = normalized_ready_reason
            readiness["reason"] = normalized_ready_reason

    return {
        "candidate_generation_mode": str(review.get("candidate_generation_mode") or "model_authored"),
        "primary_quality_assessment": review.get("primary_quality_assessment") or {},
        "quality_assessment": assessment,
        "candidate_readiness": readiness,
        "review_notes": dedupe_text_list(normalized_notes),
        "unsupported_findings": review.get("unsupported_findings") or [],
        "merge_recommendations": review.get("merge_recommendations") or [],
        "missed_findings": review.get("missed_findings") or [],
        "candidate_lineage": candidate_lineage,
        "advice_candidate_structure_mismatch": advice_consistency["advice_candidate_structure_mismatch"],
        "advice_claimed_absorbed_but_materialized_separately": absorbed_but_separate,
        "advice_claimed_added_but_not_materialized": added_but_missing,
        "materialized_missed_without_added": materialized_without_added,
        "absorbed_missed_issue_ids": advice_consistency["absorbed_missed_issue_ids"],
        "lineage_counts": diagnostics["lineage_counts"],
        "lineage_counts_raw": diagnostics["lineage_counts"],
        "lineage_counts_materialized": build_dual_pass_materialized_lineage_counts(
            candidate_lineage,
            candidate_report,
        ),
        "raw_readiness_conflict": raw_readiness_conflict,
        "readiness_conflict_auto_resolved": readiness_conflict_auto_resolved,
        "traceability_status": diagnostics["traceability_status"],
        "candidate_structure_drift": diagnostics["candidate_structure_drift"],
        "raw_structure_change": diagnostics["raw_structure_change"],
        "structure_change_explained_by_lineage": diagnostics["structure_change_explained_by_lineage"],
        "readiness_conflict": readiness_conflict,
        "trace_warning": diagnostics["trace_warning"],
        "lineage_coverage_complete": diagnostics["lineage_coverage_complete"],
        "unmapped_primary_issue_ids": diagnostics["unmapped_primary_issue_ids"],
        "unmapped_candidate_issue_ids": diagnostics["unmapped_candidate_issue_ids"],
        "invalid_primary_lineage_ids": diagnostics["invalid_primary_lineage_ids"],
        "invalid_candidate_lineage_ids": diagnostics["invalid_candidate_lineage_ids"],
        "duplicate_primary_lineage_ids": diagnostics["duplicate_primary_lineage_ids"],
        "duplicate_candidate_lineage_ids": diagnostics["duplicate_candidate_lineage_ids"],
        "primary_issue_id_repair_count": diagnostics["primary_issue_id_repair_count"],
        "candidate_issue_id_repair_count": diagnostics["candidate_issue_id_repair_count"],
        "lineage_auto_healed": diagnostics["lineage_auto_healed"],
        "lineage_auto_mapped_primary_issue_ids": diagnostics["lineage_auto_mapped_primary_issue_ids"],
        "lineage_auto_mapped_candidate_issue_ids": diagnostics["lineage_auto_mapped_candidate_issue_ids"],
        "candidate_added_materialization_status": lineage_materialization["status"],
        "candidate_added_materialization_missing_ids": lineage_materialization["missing_candidate_issue_ids"],
        "candidate_merged_materialization_status": merged_materialization["status"],
        "candidate_merged_materialization_missing_ids": merged_materialization["missing_candidate_issue_ids"],
        "candidate_issue_id_split_detected": candidate_consistency["candidate_issue_id_split_detected"],
        "candidate_issue_id_split_issue_ids": candidate_consistency["candidate_issue_id_split_issue_ids"],
        "candidate_negated_primary_finding_still_materialized": candidate_consistency[
            "candidate_negated_primary_finding_still_materialized"
        ],
        "candidate_negated_primary_issue_ids": candidate_consistency["candidate_negated_primary_issue_ids"],
        "candidate_negated_primary_titles": candidate_consistency["candidate_negated_primary_titles"],
        "candidate_blocker_conclusion_mismatch": candidate_consistency["candidate_blocker_conclusion_mismatch"],
        "candidate_blocker_conclusion_mismatch_titles": candidate_consistency[
            "candidate_blocker_conclusion_mismatch_titles"
        ],
        "candidate_high_signal_demotion_without_support": candidate_consistency[
            "candidate_high_signal_demotion_without_support"
        ],
        "candidate_high_signal_demotion_issue_ids": candidate_consistency[
            "candidate_high_signal_demotion_issue_ids"
        ],
        "candidate_high_signal_demotion_titles": candidate_consistency[
            "candidate_high_signal_demotion_titles"
        ],
        "candidate_overcompressed": candidate_consistency["candidate_overcompressed"],
        "candidate_overcompressed_reason": candidate_consistency["candidate_overcompressed_reason"],
        "candidate_major_judgment_drift": candidate_consistency["candidate_major_judgment_drift"],
        "candidate_structurally_ready": candidate_structurally_ready,
        "candidate_contains_multiroot_kept_findings": bool(multiroot_kept_titles),
        "candidate_multiroot_kept_titles": multiroot_kept_titles,
        "untitled_finding_issue_ids": untitled_finding_issue_ids,
        "missing_issue_id_finding_titles": missing_issue_id_finding_titles,
        "normalized_candidate_ready_for_direct_output": normalized_ready,
        "normalized_candidate_ready_reason": normalized_ready_reason,
    }


def _dual_pass_top3_retention(
    primary_report: dict[str, Any],
    candidate_report: dict[str, Any] | None,
) -> float | None:
    primary_blockers = [item for item in primary_report.get("top_blockers") or [] if isinstance(item, dict)][:3]
    candidate_blockers = [item for item in (candidate_report or {}).get("top_blockers") or [] if isinstance(item, dict)]
    if not primary_blockers:
        return None
    retained = 0
    for primary_blocker in primary_blockers:
        primary_issue_id = str(primary_blocker.get("issue_id") or "").strip()
        primary_root = build_root_cause_key(primary_blocker)
        primary_title = normalize_compare_text(
            str(primary_blocker.get("title") or primary_blocker.get("canonical_title") or "")
        )
        matched = False
        for candidate_blocker in candidate_blockers:
            candidate_issue_id = str(candidate_blocker.get("issue_id") or "").strip()
            candidate_root = build_root_cause_key(candidate_blocker)
            candidate_title = normalize_compare_text(
                str(candidate_blocker.get("title") or candidate_blocker.get("canonical_title") or "")
            )
            if primary_issue_id and candidate_issue_id == primary_issue_id:
                matched = True
            elif primary_title and candidate_title == primary_title:
                matched = True
            elif primary_root and candidate_root == primary_root:
                matched = True
            elif are_duplicate_findings(primary_blocker, candidate_blocker):
                matched = True
            if matched:
                break
        retained += int(matched)
    return round(retained / len(primary_blockers), 4)


def evaluate_dual_pass_candidate_selection(
    primary_report: dict[str, Any] | None,
    candidate_report: dict[str, Any] | None,
    advice_payload: dict[str, Any] | None,
    lineage_counts: dict[str, int] | None,
    warning: str,
    phase2_admission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary = primary_report if isinstance(primary_report, dict) else {}
    advice = advice_payload if isinstance(advice_payload, dict) else {}
    lineage = lineage_counts if isinstance(lineage_counts, dict) else {}
    assessment = advice.get("quality_assessment") if isinstance(advice.get("quality_assessment"), dict) else {}
    readiness = advice.get("candidate_readiness") if isinstance(advice.get("candidate_readiness"), dict) else {}
    phase2 = phase2_admission if isinstance(phase2_admission, dict) else {}
    phase2_enabled = phase2.get("enabled") is True
    phase2_candidate_inputs_sanitized = phase2.get("candidate_inputs_sanitized") is True
    phase2_coverage_ledger = (
        phase2.get("coverage_ledger") if isinstance(phase2.get("coverage_ledger"), dict) else {}
    )
    phase2_protocol_gate = (
        phase2.get("protocol_gate") if isinstance(phase2.get("protocol_gate"), dict) else {}
    )
    phase2_protocol_gate_passed = (
        not phase2_enabled
        or not phase2_protocol_gate
        or phase2_protocol_gate.get("passed") is True
    )
    phase2_coverage_ledger_passed = (
        not phase2_enabled or phase2_coverage_ledger.get("passed") is True
    )
    phase2_all_additions_admitted = (
        not phase2_enabled
        or phase2.get("all_passed") is True
        or phase2_candidate_inputs_sanitized
    )
    primary_top3_retention = _dual_pass_top3_retention(primary, candidate_report)
    primary_top3_retained = primary_top3_retention is None or primary_top3_retention >= (2 / 3)
    candidate_score_locked = (
        not phase2_enabled
        or (
            isinstance(candidate_report, dict)
            and str(candidate_report.get("document_quality_score") or "")
            == str(primary.get("document_quality_score") or "")
            and str(candidate_report.get("score_reason") or "") == str(primary.get("score_reason") or "")
        )
    )

    qa_ready = assessment.get("ready_for_direct_output") is True
    candidate_ready = readiness.get("ready_for_direct_output") is True
    raw_readiness_conflict = bool(advice.get("raw_readiness_conflict"))
    readiness_conflict_auto_resolved = bool(advice.get("readiness_conflict_auto_resolved"))
    suggestion_level = str(assessment.get("suggestion_level") or "").strip().lower()
    candidate_cross_document_empty = not bool((candidate_report or {}).get("cross_document_issues") or [])
    diagnostics = build_dual_pass_traceability_diagnostics(primary, candidate_report, advice.get("candidate_lineage") or {})
    traceability_status = str(advice.get("traceability_status") or diagnostics.get("traceability_status") or "unavailable")
    readiness_conflict = bool(advice.get("readiness_conflict"))
    candidate_structure_drift = bool(advice.get("candidate_structure_drift")) or bool(
        diagnostics.get("candidate_structure_drift")
    )
    traceability_consistent = traceability_status in {"complete", "minimal", "partial"}
    traceability_ready_for_default_output = traceability_status == "complete"
    lineage_coverage_complete = bool(advice.get("lineage_coverage_complete"))
    unmapped_primary_issue_ids = [
        str(value).strip() for value in (advice.get("unmapped_primary_issue_ids") or []) if str(value).strip()
    ]
    unmapped_candidate_issue_ids = [
        str(value).strip() for value in (advice.get("unmapped_candidate_issue_ids") or []) if str(value).strip()
    ]
    untitled_finding_issue_ids = [
        str(value).strip() for value in (advice.get("untitled_finding_issue_ids") or []) if str(value).strip()
    ]
    missing_issue_id_finding_titles = [
        str(value).strip() for value in (advice.get("missing_issue_id_finding_titles") or []) if str(value).strip()
    ]
    merged_materialization_status = str(advice.get("candidate_merged_materialization_status") or "none").strip().lower()
    merged_materialization_missing_ids = [
        str(value).strip()
        for value in (advice.get("candidate_merged_materialization_missing_ids") or [])
        if str(value).strip()
    ]
    candidate_structurally_ready = bool(advice.get("candidate_structurally_ready"))
    absorbed_but_separate = [
        str(value).strip()
        for value in (advice.get("advice_claimed_absorbed_but_materialized_separately") or [])
        if str(value).strip()
    ]
    added_but_missing = [
        str(value).strip()
        for value in (advice.get("advice_claimed_added_but_not_materialized") or [])
        if str(value).strip()
    ]
    materialized_without_added = [
        str(value).strip()
        for value in (advice.get("materialized_missed_without_added") or [])
        if str(value).strip()
    ]
    candidate_issue_id_split_issue_ids = [
        str(value).strip()
        for value in (advice.get("candidate_issue_id_split_issue_ids") or [])
        if str(value).strip()
    ]
    candidate_negated_primary_issue_ids = [
        str(value).strip()
        for value in (advice.get("candidate_negated_primary_issue_ids") or [])
        if str(value).strip()
    ]
    candidate_negated_primary_titles = [
        str(value).strip()
        for value in (advice.get("candidate_negated_primary_titles") or [])
        if str(value).strip()
    ]
    candidate_blocker_conclusion_mismatch_titles = [
        str(value).strip()
        for value in (advice.get("candidate_blocker_conclusion_mismatch_titles") or [])
        if str(value).strip()
    ]
    advice_structure_mismatch = bool(advice.get("advice_candidate_structure_mismatch")) or bool(
        absorbed_but_separate or added_but_missing or materialized_without_added
    )
    candidate_issue_id_split_detected = bool(advice.get("candidate_issue_id_split_detected")) or bool(
        candidate_issue_id_split_issue_ids
    )
    candidate_negated_primary_finding_still_materialized = bool(
        advice.get("candidate_negated_primary_finding_still_materialized")
    ) or bool(candidate_negated_primary_issue_ids)
    candidate_blocker_conclusion_mismatch = bool(advice.get("candidate_blocker_conclusion_mismatch")) or bool(
        candidate_blocker_conclusion_mismatch_titles
    )
    candidate_high_signal_demotion_without_support = bool(
        advice.get("candidate_high_signal_demotion_without_support")
    )
    candidate_high_signal_demotion_issue_ids = [
        str(value).strip()
        for value in (advice.get("candidate_high_signal_demotion_issue_ids") or [])
        if str(value).strip()
    ]
    candidate_high_signal_demotion_titles = [
        str(value).strip()
        for value in (advice.get("candidate_high_signal_demotion_titles") or [])
        if str(value).strip()
    ]
    candidate_overcompressed = bool(advice.get("candidate_overcompressed"))
    candidate_overcompressed_reason = str(advice.get("candidate_overcompressed_reason") or "").strip()
    candidate_major_judgment_drift = bool(advice.get("candidate_major_judgment_drift"))
    normalized_candidate_ready = bool(advice.get("normalized_candidate_ready_for_direct_output"))
    normalized_candidate_ready_reason = str(advice.get("normalized_candidate_ready_reason") or "").strip()
    primary_issue_id_repair_count = int(advice.get("primary_issue_id_repair_count") or diagnostics.get("primary_issue_id_repair_count") or 0)
    candidate_issue_id_repair_count = int(
        advice.get("candidate_issue_id_repair_count") or diagnostics.get("candidate_issue_id_repair_count") or 0
    )
    lineage_auto_healed = bool(advice.get("lineage_auto_healed") or diagnostics.get("lineage_auto_healed"))
    lineage_auto_mapped_primary_issue_ids = [
        str(value).strip()
        for value in (
            advice.get("lineage_auto_mapped_primary_issue_ids")
            or diagnostics.get("lineage_auto_mapped_primary_issue_ids")
            or []
        )
        if str(value).strip()
    ]
    lineage_auto_mapped_candidate_issue_ids = [
        str(value).strip()
        for value in (
            advice.get("lineage_auto_mapped_candidate_issue_ids")
            or diagnostics.get("lineage_auto_mapped_candidate_issue_ids")
            or []
        )
        if str(value).strip()
    ]
    suggestion_level_conflict = (
        suggestion_level == "high" and qa_ready and candidate_ready and normalized_candidate_ready
    )
    suggestion_level_override_applied = (
        suggestion_level_conflict and candidate_structurally_ready and traceability_status == "complete"
    )

    gate_results = {
        "candidate_report_valid": bool(candidate_report),
        "warning_free": not str(warning or "").strip(),
        "quality_assessment_ready": qa_ready,
        "candidate_readiness_ready": candidate_ready,
        "raw_readiness_conflict": raw_readiness_conflict,
        "readiness_conflict_auto_resolved": readiness_conflict_auto_resolved,
        "readiness_consistent": not readiness_conflict,
        "normalized_candidate_ready": normalized_candidate_ready,
        "primary_issue_id_repair_count": primary_issue_id_repair_count,
        "candidate_issue_id_repair_count": candidate_issue_id_repair_count,
        "lineage_auto_healed": lineage_auto_healed,
        "lineage_auto_mapped_primary_issue_ids": lineage_auto_mapped_primary_issue_ids,
        "lineage_auto_mapped_candidate_issue_ids": lineage_auto_mapped_candidate_issue_ids,
        "suggestion_level_allowed": suggestion_level != "high" or suggestion_level_override_applied,
        "suggestion_level_conflict": suggestion_level_conflict,
        "suggestion_level_override_applied": suggestion_level_override_applied,
        "cross_document_section_empty": candidate_cross_document_empty,
        "traceability_consistent": traceability_consistent,
        "traceability_ready_for_default_output": traceability_ready_for_default_output,
        "traceability_status": traceability_status,
        "candidate_structurally_ready": candidate_structurally_ready,
        "candidate_structure_drift": candidate_structure_drift,
        "raw_structure_change": bool(advice.get("raw_structure_change")) or bool(diagnostics.get("raw_structure_change")),
        "structure_change_explained_by_lineage": bool(advice.get("structure_change_explained_by_lineage"))
        or bool(diagnostics.get("structure_change_explained_by_lineage")),
        "lineage_coverage_complete": lineage_coverage_complete,
        "untitled_findings_absent": not untitled_finding_issue_ids,
        "issue_ids_complete": not missing_issue_id_finding_titles,
        "unmapped_primary_findings_absent": not unmapped_primary_issue_ids,
        "unmapped_candidate_findings_absent": not unmapped_candidate_issue_ids,
        "advice_candidate_structure_mismatch_absent": not advice_structure_mismatch,
        "advice_claimed_absorbed_but_materialized_separately_absent": not absorbed_but_separate,
        "advice_claimed_added_but_not_materialized_absent": not added_but_missing,
        "materialized_missed_without_added_absent": not materialized_without_added,
        "candidate_merged_materialization_complete": merged_materialization_status in {"none", "complete"},
        "candidate_issue_id_split_absent": not candidate_issue_id_split_detected,
        "candidate_negated_primary_finding_absent": not candidate_negated_primary_finding_still_materialized,
        "candidate_blocker_conclusion_consistent": not candidate_blocker_conclusion_mismatch,
        "candidate_high_signal_demotion_supported": not candidate_high_signal_demotion_without_support,
        "candidate_not_overcompressed": not candidate_overcompressed,
        "candidate_major_judgment_drift_absent": not candidate_major_judgment_drift,
        "phase2_admission_enabled": phase2_enabled,
        "phase2_candidate_inputs_sanitized": phase2_candidate_inputs_sanitized,
        "phase2_protocol_gate_passed": phase2_protocol_gate_passed,
        "phase2_protocol_gate": phase2_protocol_gate,
        "phase2_coverage_ledger_passed": phase2_coverage_ledger_passed,
        "phase2_coverage_ledger_completeness": phase2_coverage_ledger.get("completeness"),
        "phase2_coverage_ledger_errors": phase2_coverage_ledger.get("errors") or [],
        "phase2_all_additions_admitted": phase2_all_additions_admitted,
        "phase2_admitted_count": int(phase2.get("admitted_count") or 0),
        "phase2_rejected_count": int(phase2.get("rejected_count") or 0),
        "primary_top3_retention": primary_top3_retention,
        "primary_top3_retention_gate_passed": primary_top3_retained,
        "candidate_score_locked_to_primary": candidate_score_locked,
    }
    gate_failure_reasons: list[str] = []
    if not gate_results["candidate_report_valid"]:
        gate_failure_reasons.append("candidate_report_unavailable")
    if not gate_results["warning_free"]:
        gate_failure_reasons.append("warning_present")
    if not gate_results["normalized_candidate_ready"]:
        gate_failure_reasons.append("normalized_candidate_not_ready")
    if not gate_results["suggestion_level_allowed"]:
        gate_failure_reasons.append("suggestion_level_high")
    if not gate_results["cross_document_section_empty"]:
        gate_failure_reasons.append("candidate_cross_document_not_empty")
    if not gate_results["lineage_coverage_complete"]:
        gate_failure_reasons.append("candidate_lineage_coverage_incomplete")
    if not gate_results["unmapped_primary_findings_absent"]:
        gate_failure_reasons.append("candidate_unmapped_primary_findings")
    if not gate_results["unmapped_candidate_findings_absent"]:
        gate_failure_reasons.append("candidate_unmapped_candidate_findings")
    if not gate_results["untitled_findings_absent"]:
        gate_failure_reasons.append("candidate_contains_untitled_finding")
    if not gate_results["issue_ids_complete"]:
        gate_failure_reasons.append("candidate_missing_issue_id")
    if not gate_results["advice_candidate_structure_mismatch_absent"]:
        gate_failure_reasons.append("advice_candidate_structure_mismatch")
    if not gate_results["advice_claimed_absorbed_but_materialized_separately_absent"]:
        gate_failure_reasons.append("candidate_absorbed_missed_materialized_separately")
    if not gate_results["advice_claimed_added_but_not_materialized_absent"]:
        gate_failure_reasons.append("candidate_added_not_materialized")
    if not gate_results["materialized_missed_without_added_absent"]:
        gate_failure_reasons.append("candidate_materialized_missed_without_added")
    if not gate_results["candidate_merged_materialization_complete"]:
        gate_failure_reasons.append("candidate_merged_not_materialized")
    if not gate_results["candidate_issue_id_split_absent"]:
        gate_failure_reasons.append("candidate_issue_id_split_detected")
    if not gate_results["candidate_negated_primary_finding_absent"]:
        gate_failure_reasons.append("candidate_negated_primary_finding_still_materialized")
    if not gate_results["candidate_blocker_conclusion_consistent"]:
        gate_failure_reasons.append("candidate_blocker_conclusion_mismatch")
    if not gate_results["candidate_high_signal_demotion_supported"]:
        gate_failure_reasons.append("candidate_high_signal_demotion_without_support")
    if not gate_results["candidate_not_overcompressed"]:
        gate_failure_reasons.append("candidate_overcompressed")
    if not gate_results["candidate_major_judgment_drift_absent"]:
        gate_failure_reasons.append("candidate_major_judgment_drift")
    if not gate_results["phase2_all_additions_admitted"]:
        gate_failure_reasons.append("phase2_added_admission_rejected")
    if not gate_results["phase2_protocol_gate_passed"]:
        gate_failure_reasons.append("phase2_protocol_gate_invalid")
    if not gate_results["phase2_coverage_ledger_passed"]:
        gate_failure_reasons.append("phase2_coverage_ledger_invalid")
    if not gate_results["primary_top3_retention_gate_passed"]:
        gate_failure_reasons.append("candidate_primary_top3_retention_below_two_thirds")
    if not gate_results["candidate_score_locked_to_primary"]:
        gate_failure_reasons.append("candidate_score_not_locked_to_primary")
    if traceability_status == "missing":
        gate_failure_reasons.append("candidate_traceability_missing")
    elif traceability_status == "minimal":
        gate_failure_reasons.append("candidate_traceability_minimal")
    elif traceability_status == "partial":
        gate_failure_reasons.append("candidate_traceability_partial")

    failure_category_map = {
        "candidate_report_unavailable": "protocol_blockers",
        "warning_present": "quality_blockers",
        "normalized_candidate_not_ready": "readiness_blockers",
        "suggestion_level_high": "quality_blockers",
        "candidate_cross_document_not_empty": "protocol_blockers",
        "candidate_lineage_coverage_incomplete": "traceability_blockers",
        "candidate_unmapped_primary_findings": "traceability_blockers",
        "candidate_unmapped_candidate_findings": "traceability_blockers",
        "candidate_contains_untitled_finding": "quality_blockers",
        "candidate_missing_issue_id": "protocol_blockers",
        "advice_candidate_structure_mismatch": "protocol_blockers",
        "candidate_absorbed_missed_materialized_separately": "protocol_blockers",
        "candidate_added_not_materialized": "protocol_blockers",
        "candidate_merged_not_materialized": "protocol_blockers",
        "candidate_issue_id_split_detected": "protocol_blockers",
        "candidate_negated_primary_finding_still_materialized": "quality_blockers",
        "candidate_blocker_conclusion_mismatch": "quality_blockers",
        "candidate_high_signal_demotion_without_support": "quality_blockers",
        "candidate_overcompressed": "quality_blockers",
        "candidate_major_judgment_drift": "quality_blockers",
        "candidate_materialized_missed_without_added": "traceability_blockers",
        "candidate_traceability_missing": "traceability_blockers",
        "candidate_traceability_minimal": "traceability_blockers",
        "candidate_traceability_partial": "traceability_blockers",
        "phase2_added_admission_rejected": "quality_blockers",
        "phase2_protocol_gate_invalid": "protocol_blockers",
        "phase2_coverage_ledger_invalid": "protocol_blockers",
        "candidate_primary_top3_retention_below_two_thirds": "quality_blockers",
        "candidate_score_not_locked_to_primary": "protocol_blockers",
    }
    gate_failure_categories = {
        "protocol_blockers": [],
        "traceability_blockers": [],
        "quality_blockers": [],
        "readiness_blockers": [],
    }
    for reason in gate_failure_reasons:
        category = failure_category_map.get(reason)
        if category:
            gate_failure_categories[category].append(reason)
    gate_failure_categories = {
        key: dedupe_text_list(values) for key, values in gate_failure_categories.items() if values
    }
    editorial_only_reasons = {"suggestion_level_high"}
    candidate_blocked_only_by_editorial_judgment = (
        gate_results["candidate_report_valid"]
        and gate_results["candidate_structurally_ready"]
        and not suggestion_level_override_applied
        and bool(gate_failure_reasons)
        and all(reason in editorial_only_reasons for reason in gate_failure_reasons)
        and not gate_failure_categories.get("protocol_blockers")
        and not gate_failure_categories.get("traceability_blockers")
        and not gate_failure_categories.get("readiness_blockers")
    )

    if gate_results["candidate_report_valid"] and not gate_failure_reasons:
        selected_report_owner = "candidate"
        recommendation_status = "recommended"
    elif gate_results["candidate_report_valid"]:
        selected_report_owner = "pipeline"
        recommendation_status = "fallback_pipeline"
    else:
        selected_report_owner = "pipeline"
        recommendation_status = "candidate_unavailable"

    return {
        "selected_report_owner": selected_report_owner,
        "candidate_recommendation_status": recommendation_status,
        "candidate_gate_results": gate_results,
        "candidate_gate_failure_reasons": gate_failure_reasons,
        "candidate_gate_failure_categories": gate_failure_categories,
        "candidate_ready_reason": normalized_candidate_ready_reason,
        "candidate_blocked_only_by_editorial_judgment": candidate_blocked_only_by_editorial_judgment,
        "primary_issue_id_repair_count": primary_issue_id_repair_count,
        "candidate_issue_id_repair_count": candidate_issue_id_repair_count,
        "lineage_auto_healed": lineage_auto_healed,
        "lineage_auto_mapped_primary_issue_ids": lineage_auto_mapped_primary_issue_ids,
        "lineage_auto_mapped_candidate_issue_ids": lineage_auto_mapped_candidate_issue_ids,
        "suggestion_level_conflict": suggestion_level_conflict,
        "suggestion_level_override_applied": suggestion_level_override_applied,
        "candidate_merged_materialization_status": merged_materialization_status,
        "candidate_merged_materialization_missing_ids": merged_materialization_missing_ids,
        "candidate_issue_id_split_detected": candidate_issue_id_split_detected,
        "candidate_issue_id_split_issue_ids": candidate_issue_id_split_issue_ids,
        "candidate_negated_primary_finding_still_materialized": candidate_negated_primary_finding_still_materialized,
        "candidate_negated_primary_issue_ids": candidate_negated_primary_issue_ids,
        "candidate_negated_primary_titles": candidate_negated_primary_titles,
        "candidate_blocker_conclusion_mismatch": candidate_blocker_conclusion_mismatch,
        "candidate_blocker_conclusion_mismatch_titles": candidate_blocker_conclusion_mismatch_titles,
        "candidate_high_signal_demotion_without_support": candidate_high_signal_demotion_without_support,
        "candidate_high_signal_demotion_issue_ids": candidate_high_signal_demotion_issue_ids,
        "candidate_high_signal_demotion_titles": candidate_high_signal_demotion_titles,
        "candidate_overcompressed": candidate_overcompressed,
        "candidate_overcompressed_reason": candidate_overcompressed_reason,
        "phase2_admission": phase2,
        "primary_top3_retention": primary_top3_retention,
        "primary_top3_retention_gate_passed": primary_top3_retained,
        "candidate_score_locked_to_primary": candidate_score_locked,
        "candidate_major_judgment_drift": candidate_major_judgment_drift,
        "candidate_structurally_ready": candidate_structurally_ready,
    }


def apply_merge_recommendations(report: dict[str, Any], recommendations: list[dict[str, Any]]) -> None:
    if not recommendations:
        return

    for item in recommendations:
        raw_titles = [str(title).strip() for title in item.get("titles") or [] if str(title).strip()]
        if not raw_titles:
            continue
        titles = set(raw_titles)
        normalized_titles = {normalize_merge_recommendation_title(title) for title in raw_titles}
        issue_markers = {
            marker
            for marker in (extract_merge_recommendation_issue_marker(title) for title in raw_titles)
            if marker
        }
        entries: list[dict[str, Any]] = []
        for entry in collect_report_entries(report):
            finding = entry["finding"]
            title = str(finding.get("title") or "").strip()
            canonical_title = str(finding.get("canonical_title") or "").strip()
            normalized_candidates = {
                normalize_merge_recommendation_title(title),
                normalize_merge_recommendation_title(canonical_title),
            }
            issue_id = str(finding.get("issue_id") or "").strip().upper()
            if (
                title in titles
                or canonical_title in titles
                or normalized_candidates.intersection(normalized_titles)
                or (issue_id and issue_id in issue_markers)
            ):
                entries.append(entry)
        if not entries:
            continue

        merged_title = str(item.get("merged_title") or "").strip()
        if len(entries) == 1:
            if merged_title:
                entries[0]["finding"]["title"] = merged_title
            continue

        merged_finding = merge_duplicate_findings(entries)
        if merged_title:
            merged_finding["title"] = merged_title
        target = preferred_group_target(entries)
        for entry in sorted(entries, key=entry_sort_key, reverse=True):
            remove_report_entry(report, entry)
        add_report_entry(report, target, merged_finding)

    for dimension in report.get("dimensions") or []:
        findings = dimension.get("findings") or []
        dimension["findings"] = sort_public_findings(findings)
        dimension["dimension_note"] = "" if dimension["findings"] else NO_FINDINGS_NOTE
    report["cross_document_issues"] = sort_public_findings(report.get("cross_document_issues") or [])


def normalize_merge_recommendation_title(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return re.sub(r"\s*[（(][A-Z0-9_-]+[)）]\s*$", "", text, flags=re.IGNORECASE)


def extract_merge_recommendation_issue_marker(value: str) -> str:
    match = re.search(r"[（(]([A-Z0-9_-]+)[)）]\s*$", str(value or "").strip(), flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def index_findings(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _index_findings_impl(report)


def finding_identity(finding: dict[str, Any]) -> str:
    return _finding_identity_impl(finding)


def finding_snapshot(finding: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return _finding_snapshot_impl(finding)


__all__ = [
    "append_secondary_finding",
    "apply_merge_recommendations",
    "build_blocker_from_finding",
    "build_dual_pass_lineage_counts",
    "build_dual_pass_materialized_lineage_counts",
    "build_dual_pass_secondary_finding",
    "build_dual_pass_traceability_diagnostics",
    "evaluate_dual_pass_candidate_selection",
    "evaluate_dual_pass_added_admission",
    "evaluate_phase2_protocol_gate",
    "evaluate_phase2_coverage_ledger",
    "build_deterministic_phase2_candidate",
    "lock_dual_pass_candidate_score_to_primary",
    "build_report_diff_payload",
    "build_dual_pass_comparison_summary",
    "build_conservative_dual_pass_candidate_report",
    "confidence_rank_value",
    "collect_dual_pass_missing_issue_id_finding_titles",
    "demote_dual_pass_cross_document_issues",
    "merge_dual_pass_review_report",
    "downgrade_score_once",
    "extract_merge_recommendation_issue_marker",
    "finding_identity",
    "finding_snapshot",
    "index_findings",
    "merge_audit_report",
    "merge_secondary_blockers",
    "merge_secondary_review_report",
    "normalize_merge_recommendation_title",
    "normalize_dual_pass_advice_payload",
]
