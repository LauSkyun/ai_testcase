from __future__ import annotations

import re
from typing import Any

from rad_review.docx_reader import ParsedDocument
from rad_review.prompts import DIMENSIONS

from .base import CANONICAL_BY_ID, NO_FINDINGS_NOTE, finding_priority, merge_scope, merge_text, normalized_max, public_finding, sort_findings, sort_public_findings
from .duplicates import ATOMIC_DECISION_OBJECT_TERMS, add_report_entry, are_duplicate_findings, build_stable_cross_issues, classify_duplicate_findings, collect_distinct_root_findings, collect_report_entries, entry_sort_key, finding_atomic_decision_objects, merge_duplicate_findings, preferred_group_target, remove_report_entry
from .rules import (
    build_cross_issue_evidence,
    build_document_aliases,
    build_root_cause_key,
    explicit_canonical_issue_id,
    finding_mentions_multiple_documents,
    finding_root_key,
    finding_text,
    identify_issue_id,
    identify_root_cause_cluster,
    infer_evidence_scope,
    is_ignorable_placeholder_or_config_value_gap,
    normalize_dimension_name,
    normalize_report,
    normalize_unmatched_finding,
    resolve_dimension,
    should_promote_dimension_finding_to_cross_document,
)
from .scoring import build_top_blockers, is_blocking_high, stable_score
from .base import PLACEHOLDER_EVIDENCE_MARKERS


def is_valid_finding(finding: Any, source_dimension: str, document_count: int) -> bool:
    if not isinstance(finding, dict):
        return False
    evidence = str(finding.get("evidence") or "")
    text = finding_text(finding)
    if not text.strip():
        return False
    if any(marker in evidence for marker in PLACEHOLDER_EVIDENCE_MARKERS):
        return False
    if is_ignorable_placeholder_or_config_value_gap(finding):
        return False
    if source_dimension == "cross_document" and document_count < 2:
        return False
    if str(finding.get("evidence_scope") or "") == "cross_document" and document_count < 2:
        return False
    return True


def _filter_ignorable_placeholder_content(value: Any) -> Any:
    if isinstance(value, str):
        probe = {"title": value, "current_state": value}
        return None if is_ignorable_placeholder_or_config_value_gap(probe) else value
    if isinstance(value, list):
        filtered: list[Any] = []
        for item in value:
            cleaned = _filter_ignorable_placeholder_content(item)
            if cleaned is not None:
                filtered.append(cleaned)
        return filtered
    if isinstance(value, dict):
        if is_ignorable_placeholder_or_config_value_gap(value):
            return None
        return {
            key: cleaned
            for key, item in value.items()
            if (cleaned := _filter_ignorable_placeholder_content(item)) is not None
        }
    return value


def suppress_ignorable_placeholder_content(report: dict[str, Any]) -> None:
    for field in ("missing_information", "quality_notes", "image_analysis_gaps", "test_points"):
        cleaned = _filter_ignorable_placeholder_content(report.get(field))
        if cleaned is not None:
            report[field] = cleaned


def prepare_finding(finding: dict[str, Any], dimension_name: str, order: int, evidence_scope: str | None = None) -> dict[str, Any]:
    normalized = normalize_unmatched_finding(finding, dimension_name)
    normalized["_order"] = order
    normalized["_title_rank"] = finding_priority(normalized)
    normalized["evidence_scope"] = evidence_scope or infer_evidence_scope(normalized, dimension_name)
    normalized["_root_cause_cluster"] = identify_root_cause_cluster(normalized)
    normalized["_root_cause_key"] = build_root_cause_key(normalized)
    return normalized


def merge_canonical_finding(canonical_hits: dict[str, dict[str, Any]], issue_id: str, finding: dict[str, Any], source_dimension: str) -> None:
    issue = CANONICAL_BY_ID[issue_id]
    existing = canonical_hits.get(issue_id)
    evidence = str(finding.get("evidence") or "").strip()
    evidence_scope = infer_evidence_scope(finding, source_dimension)
    incoming_title_rank = finding_priority(finding)
    incoming_title = str(finding.get("title") or finding.get("canonical_title") or issue["title"]).strip()
    if existing is None:
        canonical_hits[issue_id] = {
            "issue_id": issue_id,
            "canonical_title": issue["title"],
            "primary_dimension": issue["dimension"],
            "evidence_scope": evidence_scope,
            "severity": normalized_max("severity", [finding.get("severity")]),
            "title": incoming_title or issue["title"],
            "current_state": str(finding.get("current_state") or ""),
            "evidence": evidence,
            "risk": str(finding.get("risk") or ""),
            "suggestion": str(finding.get("suggestion") or ""),
            "planner_role": finding.get("planner_role") or finding.get("owner") or issue["owner"],
            "confidence": normalized_max("confidence", [finding.get("confidence")]),
            "blocking": normalized_max("blocking", [finding.get("blocking")]),
            "finding_source": str(finding.get("finding_source") or ""),
            "finding_source_label": str(finding.get("finding_source_label") or ""),
            "source_model": str(finding.get("source_model") or ""),
            "_order": int(finding.get("_order", 0)),
            "_title_rank": incoming_title_rank,
            "_root_cause_cluster": str(finding.get("_root_cause_cluster") or identify_root_cause_cluster(finding)),
            "_root_cause_key": str(finding.get("_root_cause_key") or build_root_cause_key(finding)),
        }
        return
    existing["severity"] = normalized_max("severity", [existing.get("severity"), finding.get("severity")])
    existing["confidence"] = normalized_max("confidence", [existing.get("confidence"), finding.get("confidence")])
    existing["blocking"] = normalized_max("blocking", [existing.get("blocking"), finding.get("blocking")])
    existing["evidence_scope"] = merge_scope(str(existing.get("evidence_scope") or ""), evidence_scope)
    existing["planner_role"] = finding.get("planner_role") or finding.get("owner") or existing.get("planner_role") or issue["owner"]
    existing["_order"] = min(int(existing.get("_order", 0)), int(finding.get("_order", 0)))
    if not str(existing.get("finding_source") or "").strip():
        existing["finding_source"] = str(finding.get("finding_source") or "")
    if not str(existing.get("finding_source_label") or "").strip():
        existing["finding_source_label"] = str(finding.get("finding_source_label") or "")
    if not str(existing.get("source_model") or "").strip():
        existing["source_model"] = str(finding.get("source_model") or "")
    if incoming_title and incoming_title_rank > existing.get("_title_rank", (0, 0, 0)):
        existing["title"] = incoming_title
        existing["_title_rank"] = incoming_title_rank
    if evidence:
        existing["evidence"] = merge_text(str(existing.get("evidence") or ""), evidence)
    for key in ("current_state", "risk", "suggestion"):
        incoming = str(finding.get(key) or "").strip()
        if incoming:
            existing[key] = incoming
    if not str(existing.get("_root_cause_cluster") or "").strip():
        existing["_root_cause_cluster"] = str(finding.get("_root_cause_cluster") or identify_root_cause_cluster(finding))
    existing["_root_cause_key"] = str(existing.get("_root_cause_key") or finding.get("_root_cause_key") or build_root_cause_key(existing))


def findings_for_dimension(canonical_hits: dict[str, dict[str, Any]], dimension_name: str) -> list[dict[str, Any]]:
    return [finding for finding in canonical_hits.values() if finding.get("primary_dimension") == dimension_name]


def dedupe_report_sections(report: dict[str, Any]) -> None:
    entries = collect_report_entries(report)
    if len(entries) < 2:
        report["dedupe_diagnostics"] = {
            "auto_merge_count": 0,
            "auto_merge_rejected_count": 0,
            "possible_duplicate_pair_count": 0,
            "distinct_issue_id_merge_blocked_count": 0,
            "decisions": [],
        }
        return
    consumed: set[int] = set()
    removals: list[dict[str, int]] = []
    additions: list[tuple[dict[str, int], dict[str, Any]]] = []
    decisions: list[dict[str, Any]] = []
    possible_duplicate_pair_count = 0
    distinct_issue_id_merge_blocked_count = 0
    for index, entry in enumerate(entries):
        if index in consumed:
            continue
        group = [entry]
        consumed.add(index)
        for candidate_index in range(index + 1, len(entries)):
            if candidate_index in consumed:
                continue
            candidate = entries[candidate_index]
            decision = classify_duplicate_findings(entry["finding"], candidate["finding"])
            if decision.get("possible_duplicate"):
                possible_duplicate_pair_count += 1
                if decision.get("distinct_explicit_issue_ids"):
                    distinct_issue_id_merge_blocked_count += 1
                decisions.append(
                    {
                        "action": "kept_separate",
                        "reason": decision.get("reason"),
                        "left_issue_id": str(entry["finding"].get("issue_id") or ""),
                        "right_issue_id": str(candidate["finding"].get("issue_id") or ""),
                        "left_title": str(entry["finding"].get("title") or ""),
                        "right_title": str(candidate["finding"].get("title") or ""),
                    }
                )
            if decision.get("duplicate"):
                group.append(candidate)
                consumed.add(candidate_index)
                decisions.append(
                    {
                        "action": "merged",
                        "reason": decision.get("reason"),
                        "left_issue_id": str(entry["finding"].get("issue_id") or ""),
                        "right_issue_id": str(candidate["finding"].get("issue_id") or ""),
                        "left_title": str(entry["finding"].get("title") or ""),
                        "right_title": str(candidate["finding"].get("title") or ""),
                    }
                )
        if len(group) <= 1:
            continue
        merged_finding = merge_duplicate_findings(group)
        target = preferred_group_target(group)
        additions.append((target, merged_finding))
        removals.extend(group)
    if removals:
        for entry in sorted(removals, key=entry_sort_key, reverse=True):
            remove_report_entry(report, entry)
        for target, finding in additions:
            add_report_entry(report, target, finding)
    for dimension in report.get("dimensions") or []:
        findings = dimension.get("findings") or []
        dimension["findings"] = sort_public_findings(findings)
        dimension["dimension_note"] = "" if dimension["findings"] else NO_FINDINGS_NOTE
    report["cross_document_issues"] = sort_public_findings(report.get("cross_document_issues") or [])
    report["dedupe_diagnostics"] = {
        "auto_merge_count": len(additions),
        "auto_merge_rejected_count": possible_duplicate_pair_count,
        "possible_duplicate_pair_count": possible_duplicate_pair_count,
        "distinct_issue_id_merge_blocked_count": distinct_issue_id_merge_blocked_count,
        "decisions": decisions,
    }


ATOMIC_OBJECT_LABELS = {
    "bonus_probability": "额外奖励触发概率",
    "symbol_naming": "符号命名",
    "chip_tiers": "筹码档位配置",
    "countdown_interaction": "倒计时交互与下注截止",
    "debit_timing": "本金扣款时机",
    "payout_timing": "派奖到账时机",
    "funds_compensation": "资金失败补偿",
    "pool_negative_floor": "奖池负值下限",
    "single_round_cap": "单局最大赔付封顶",
    "fake_data_isolation": "展示数据与真实数据隔离",
}

ATOMIC_OBJECT_OWNERS = {
    "bonus_probability": "数值策划",
    "symbol_naming": "系统策划",
    "chip_tiers": "数值策划",
    "countdown_interaction": "系统策划",
    "debit_timing": "服务端",
    "payout_timing": "服务端",
    "funds_compensation": "服务端",
    "pool_negative_floor": "数值策划",
    "single_round_cap": "数值策划",
    "fake_data_isolation": "服务端",
}


def _atomic_text_fragments(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    text = re.sub(r"(?<!^)(?=\d+\s*[.、)])", "\n", text)
    coarse = re.split(r"[\n；;。]+", text)
    fragments: list[str] = []
    for part in coarse:
        part = re.sub(r"^\s*\d+\s*[.、)]\s*", "", part).strip(" ，,：:")
        if not part:
            continue
        detected = finding_atomic_decision_objects({"current_state": part})
        if len(detected) <= 1:
            fragments.append(part)
            continue
        for subpart in re.split(r"[，,]+|(?:和|及|与)", part):
            subpart = subpart.strip(" ，,：:")
            if subpart:
                fragments.append(subpart)
    return fragments


def _atomic_fragments_by_object(value: Any) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for fragment in _atomic_text_fragments(value):
        objects = finding_atomic_decision_objects({"current_state": fragment})
        if len(objects) != 1:
            continue
        decision_object = next(iter(objects))
        result.setdefault(decision_object, []).append(fragment)
    return result


def _atomic_issue_id(base_issue_id: str, decision_object: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base_issue_id).strip("_") or "ATOMIC_FINDING"
    suffix = re.sub(r"[^A-Za-z0-9_]+", "_", decision_object).strip("_").upper()
    return f"{base}__{suffix}"


def split_finding_into_atomic_units(finding: dict[str, Any]) -> list[dict[str, Any]]:
    objects = sorted(finding_atomic_decision_objects(finding))
    if len(objects) < 2:
        return []
    state_map = _atomic_fragments_by_object(finding.get("current_state"))
    if any(not state_map.get(decision_object) for decision_object in objects):
        return []
    suggestion_map = _atomic_fragments_by_object(finding.get("suggestion"))
    base_issue_id = str(finding.get("issue_id") or "ATOMIC_FINDING")
    evidence = str(finding.get("evidence") or "").strip()
    split_findings: list[dict[str, Any]] = []
    for decision_object in objects:
        label = ATOMIC_OBJECT_LABELS.get(decision_object, decision_object)
        current_state = "；".join(state_map[decision_object])
        suggestion_parts = suggestion_map.get(decision_object) or []
        suggestion = "；".join(suggestion_parts).strip()
        if not suggestion:
            suggestion = f"单独确认并冻结{label}的唯一口径，补充对应责任人与可独立关闭的验收标准。"
        atomic = dict(finding)
        atomic.update(
            {
                "issue_id": _atomic_issue_id(base_issue_id, decision_object),
                "canonical_title": f"{label}口径需独立确认",
                "title": f"{label}口径不一致或未形成唯一规则",
                "current_state": current_state,
                "evidence": evidence,
                "risk": f"{label}无法形成唯一实现口径，会导致对应配置、实现或验收无法独立关闭。",
                "suggestion": suggestion,
                "planner_role": ATOMIC_OBJECT_OWNERS.get(
                    decision_object,
                    str(finding.get("planner_role") or "待定"),
                ),
                "atomicity_decision_object": decision_object,
                "atomicity_split_from_issue_id": base_issue_id,
            }
        )
        split_findings.append(atomic)
    return split_findings


def _replace_report_entry(
    report: dict[str, Any],
    entry: dict[str, Any],
    replacements: list[dict[str, Any]],
) -> None:
    if entry.get("location") == "dimension":
        dimension = (report.get("dimensions") or [])[int(entry.get("dimension_index") or 0)]
        findings = dimension.get("findings") or []
    else:
        findings = report.get("cross_document_issues") or []
    index = int(entry.get("finding_index") or 0)
    findings[index : index + 1] = replacements


def enforce_finding_atomicity(report: dict[str, Any]) -> None:
    existing_diagnostics = (
        report.get("atomicity_transform_diagnostics")
        if isinstance(report.get("atomicity_transform_diagnostics"), dict)
        else {}
    )
    actions: list[dict[str, Any]] = list(existing_diagnostics.get("actions") or [])
    split_source_count = int(existing_diagnostics.get("split_source_count") or 0)
    split_finding_count = int(existing_diagnostics.get("split_finding_count") or 0)
    suppressed_count = int(existing_diagnostics.get("suppressed_fully_covered_umbrella_count") or 0)

    entries_before_split = collect_report_entries(report)
    narrower_umbrella_removals: list[dict[str, Any]] = []
    for entry in entries_before_split:
        finding = entry.get("finding") if isinstance(entry.get("finding"), dict) else {}
        objects = sorted(finding_atomic_decision_objects(finding))
        if len(objects) < 2:
            continue
        covered_by: dict[str, list[str]] = {}
        for decision_object in objects:
            for candidate in entries_before_split:
                if candidate is entry:
                    continue
                candidate_finding = (
                    candidate.get("finding") if isinstance(candidate.get("finding"), dict) else {}
                )
                candidate_objects = finding_atomic_decision_objects(candidate_finding)
                if decision_object not in candidate_objects or len(candidate_objects) >= len(objects):
                    continue
                covered_by.setdefault(decision_object, []).append(
                    str(candidate_finding.get("issue_id") or "")
                )
        if not all(covered_by.get(item) for item in objects):
            continue
        narrower_umbrella_removals.append(entry)
        suppressed_count += 1
        actions.append(
            {
                "action": "suppressed_umbrella_covered_by_narrower_findings",
                "source_issue_id": str(finding.get("issue_id") or ""),
                "source_title": str(finding.get("title") or finding.get("canonical_title") or ""),
                "decision_objects": objects,
                "covered_by_issue_ids": sorted(
                    {issue_id for values in covered_by.values() for issue_id in values if issue_id}
                ),
                "source_snapshot": public_finding(finding),
            }
        )
    for entry in sorted(narrower_umbrella_removals, key=entry_sort_key, reverse=True):
        _replace_report_entry(report, entry, [])

    first_pass: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for entry in collect_report_entries(report):
        finding = entry.get("finding") if isinstance(entry.get("finding"), dict) else {}
        if len(finding_atomic_decision_objects(finding)) < 2:
            continue
        replacements = split_finding_into_atomic_units(finding)
        if replacements:
            first_pass.append((entry, replacements))
    for entry, replacements in sorted(first_pass, key=lambda item: entry_sort_key(item[0]), reverse=True):
        source = entry.get("finding") or {}
        _replace_report_entry(report, entry, replacements)
        split_source_count += 1
        split_finding_count += len(replacements)
        actions.append(
            {
                "action": "split",
                "source_issue_id": str(source.get("issue_id") or ""),
                "source_title": str(source.get("title") or source.get("canonical_title") or ""),
                "decision_objects": sorted(finding_atomic_decision_objects(source)),
                "result_issue_ids": [str(item.get("issue_id") or "") for item in replacements],
            }
        )

    entries = collect_report_entries(report)
    atomic_coverage: dict[str, list[str]] = {}
    for entry in entries:
        finding = entry.get("finding") if isinstance(entry.get("finding"), dict) else {}
        objects = finding_atomic_decision_objects(finding)
        if len(objects) == 1:
            atomic_coverage.setdefault(next(iter(objects)), []).append(str(finding.get("issue_id") or ""))
    umbrella_removals: list[dict[str, Any]] = []
    for entry in entries:
        finding = entry.get("finding") if isinstance(entry.get("finding"), dict) else {}
        objects = sorted(finding_atomic_decision_objects(finding))
        if len(objects) < 2 or not all(atomic_coverage.get(item) for item in objects):
            continue
        umbrella_removals.append(entry)
        suppressed_count += 1
        actions.append(
            {
                "action": "suppressed_fully_covered_umbrella",
                "source_issue_id": str(finding.get("issue_id") or ""),
                "source_title": str(finding.get("title") or finding.get("canonical_title") or ""),
                "decision_objects": objects,
                "covered_by_issue_ids": sorted(
                    {
                        issue_id
                        for decision_object in objects
                        for issue_id in atomic_coverage.get(decision_object) or []
                        if issue_id
                    }
                ),
                "source_snapshot": public_finding(finding),
            }
        )
    for entry in sorted(umbrella_removals, key=entry_sort_key, reverse=True):
        _replace_report_entry(report, entry, [])

    unresolved_entries: list[dict[str, Any]] = []
    for entry in collect_report_entries(report):
        finding = entry.get("finding") if isinstance(entry.get("finding"), dict) else {}
        if len(finding_atomic_decision_objects(finding)) >= 2:
            unresolved_entries.append(entry)
    review_queue = list(report.get("finding_atomicity_review_queue") or [])
    for entry in sorted(unresolved_entries, key=entry_sort_key, reverse=True):
        finding = entry.get("finding") or {}
        review_queue.append(
            {
                "reason": "multiple_decision_objects_could_not_be_safely_split",
                "decision_objects": sorted(finding_atomic_decision_objects(finding)),
                "source_finding": public_finding(finding),
            }
        )
        actions.append(
            {
                "action": "quarantined_for_atomicity_review",
                "source_issue_id": str(finding.get("issue_id") or ""),
                "source_title": str(finding.get("title") or finding.get("canonical_title") or ""),
                "decision_objects": sorted(finding_atomic_decision_objects(finding)),
            }
        )
        _replace_report_entry(report, entry, [])
    if review_queue:
        report["finding_atomicity_review_queue"] = review_queue
        notes = list(report.get("quality_notes") or [])
        note = f"有 {len(review_queue)} 条多决策对象问题无法安全自动拆分，已移入 finding_atomicity_review_queue，未进入默认 finding。"
        if note not in notes:
            notes.append(note)
        report["quality_notes"] = notes
    report["atomicity_transform_diagnostics"] = {
        "split_source_count": split_source_count,
        "split_finding_count": split_finding_count,
        "suppressed_fully_covered_umbrella_count": suppressed_count,
        "quarantined_count": int(existing_diagnostics.get("quarantined_count") or 0)
        + len(unresolved_entries),
        "actions": actions,
    }


def attach_finding_atomicity_diagnostics(report: dict[str, Any]) -> None:
    suspects: list[dict[str, Any]] = []
    for entry in collect_report_entries(report):
        finding = entry.get("finding")
        if not isinstance(finding, dict):
            continue
        decision_objects = sorted(finding_atomic_decision_objects(finding))
        if len(decision_objects) < 2:
            continue
        suspects.append(
            {
                "issue_id": str(finding.get("issue_id") or ""),
                "title": str(finding.get("title") or finding.get("canonical_title") or ""),
                "decision_objects": decision_objects,
                "reason": "finding_contains_multiple_independently_closeable_decision_objects",
            }
        )
    report["finding_atomicity_status"] = "pass" if not suspects else "suspect"
    report["finding_atomicity_suspect_count"] = len(suspects)
    report["finding_atomicity_suspects"] = suspects


def stabilize_report(report: dict[str, Any], documents: list[ParsedDocument]) -> dict[str, Any]:
    if report.get("document_quality_score") == "未评定":
        return normalize_report(report)
    normalized = normalize_report(report)
    enforce_finding_atomicity(normalized)
    raw_dimension_finding_presence = {
        normalize_dimension_name(dimension.get("name"), fallback=DIMENSIONS[0]): bool(dimension.get("findings"))
        for dimension in normalized.get("dimensions", [])
        if isinstance(dimension, dict)
    }
    document_count = len(documents)
    document_aliases = build_document_aliases(documents)
    canonical_hits: dict[str, dict[str, Any]] = {}
    unmatched_by_dimension = {dimension: [] for dimension in DIMENSIONS}
    unmatched_cross_issues: list[dict[str, Any]] = []
    finding_order = 0
    for dimension in normalized.get("dimensions", []):
        dimension_name = normalize_dimension_name(dimension.get("name"), fallback=DIMENSIONS[0])
        for raw_finding in dimension.get("findings") or []:
            if not is_valid_finding(raw_finding, dimension_name, document_count):
                continue
            finding = prepare_finding(raw_finding, dimension_name, finding_order)
            finding_order += 1
            issue_id = identify_issue_id(finding)
            canonical_issue_id = explicit_canonical_issue_id(finding)
            if should_promote_dimension_finding_to_cross_document(finding, document_aliases, document_count):
                finding["evidence_scope"] = "cross_document"
                if canonical_issue_id:
                    merge_canonical_finding(canonical_hits, canonical_issue_id, finding, "cross_document")
                else:
                    unmatched_cross_issues.append(finding)
                continue
            if canonical_issue_id:
                merge_canonical_finding(canonical_hits, canonical_issue_id, finding, dimension_name)
            else:
                unmatched_by_dimension[dimension_name].append(finding)
    if document_count >= 2:
        for raw_finding in normalized.get("cross_document_issues") or []:
            if not is_valid_finding(raw_finding, "cross_document", document_count):
                continue
            issue_id = identify_issue_id(raw_finding if isinstance(raw_finding, dict) else {})
            canonical_issue_id = explicit_canonical_issue_id(raw_finding if isinstance(raw_finding, dict) else {})
            strict_cross = finding_mentions_multiple_documents(raw_finding, document_aliases)
            target_dimension = resolve_dimension(raw_finding, issue_id)
            target_scope = "cross_document" if strict_cross else "document"
            finding = prepare_finding(raw_finding, target_dimension, finding_order, evidence_scope=target_scope)
            finding_order += 1
            if strict_cross:
                if canonical_issue_id:
                    merge_canonical_finding(canonical_hits, canonical_issue_id, finding, "cross_document")
                else:
                    unmatched_cross_issues.append(finding)
            elif canonical_issue_id:
                merge_canonical_finding(canonical_hits, canonical_issue_id, finding, target_dimension)
            else:
                unmatched_by_dimension[target_dimension].append(finding)
    stable_dimensions: list[dict[str, Any]] = []
    for dimension_name in DIMENSIONS:
        findings = list(findings_for_dimension(canonical_hits, dimension_name))
        findings.extend(unmatched_by_dimension.get(dimension_name, []))
        findings = sort_findings(findings)
        if findings:
            dimension_note = ""
        elif raw_dimension_finding_presence.get(dimension_name):
            dimension_note = "没有高风险问题"
        else:
            dimension_note = NO_FINDINGS_NOTE
        stable_dimensions.append(
            {
                "name": dimension_name,
                "dimension_note": dimension_note,
                "findings": [public_finding(finding) for finding in findings],
            }
        )
    normalized["dimensions"] = stable_dimensions
    normalized["cross_document_issues"] = build_stable_cross_issues(canonical_hits, unmatched_cross_issues, document_count)
    suppress_ignorable_placeholder_content(normalized)
    enforce_finding_atomicity(normalized)
    dedupe_report_sections(normalized)
    attach_finding_atomicity_diagnostics(normalized)
    for dimension in normalized.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        dimension_name = normalize_dimension_name(dimension.get("name"), fallback=DIMENSIONS[0])
        findings = list(dimension.get("findings") or [])
        if findings:
            dimension["dimension_note"] = ""
        elif raw_dimension_finding_presence.get(dimension_name):
            dimension["dimension_note"] = "没有高风险问题"
        else:
            dimension["dimension_note"] = NO_FINDINGS_NOTE
    normalized["top_blockers"] = build_top_blockers(normalized)
    normalized["document_quality_score"], normalized["score_reason"] = stable_score(normalized)
    normalized["quality_notes"] = list(normalized.get("quality_notes") or [])
    return normalized
