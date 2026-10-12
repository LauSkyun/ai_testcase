from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from rad_review.reporting.duplicates import collect_report_entries
from rad_review.reporting.ingest import load_json_with_repairs
from rad_review.reporting.scoring import build_top_blockers, is_blocking_high, is_fatal_core_conflict, stable_score


PHASE3_V1_PROTOCOL_REVISION = "phase3_v1"
PHASE3_V11_PROTOCOL_REVISION = "phase3_v1_1"
PHASE3_V12_PROTOCOL_REVISION = "phase3_v1_2"
PHASE3_V13_PROTOCOL_REVISION = "phase3_v1_3"
PHASE3_PROTOCOL_REVISIONS = {
    PHASE3_V1_PROTOCOL_REVISION,
    PHASE3_V11_PROTOCOL_REVISION,
    PHASE3_V12_PROTOCOL_REVISION,
    PHASE3_V13_PROTOCOL_REVISION,
}
# Historical callers continue to default to the frozen V1 protocol.
PHASE3_PROTOCOL_REVISION = PHASE3_V1_PROTOCOL_REVISION
PHASE3_ALLOWED_TOP_LEVEL_FIELDS = {
    "challenge_findings",
    "correction_shadows",
    "review_notes",
}
PHASE3_V12_ALLOWED_TOP_LEVEL_FIELDS = PHASE3_ALLOWED_TOP_LEVEL_FIELDS | {"target_coverage_ledger"}
PHASE3_V12_LEDGER_DECISIONS = {"pass", "challenge", "abstain"}
PHASE3_V12_LEDGER_FIELDS = {
    "target_issue_id",
    "target_order",
    "decision",
    "challenge_type",
    "recommended_action",
    "evidence_checked",
    "rationale",
}
PHASE3_V13_LEDGER_FIELDS = PHASE3_V12_LEDGER_FIELDS | {"challenge_checks"}
PHASE3_V13_CHECK_STATUSES = {"confirmed", "rejected", "uncertain"}
# Stable priority removes free choice when more than one challenge basis is plausible.
PHASE3_V13_CHALLENGE_PRIORITY = (
    "duplicate",
    "multiroot",
    "evidence_mismatch",
    "unsupported",
    "compatible_interpretation",
    "overstated",
)
PHASE3_V13_ACTION_BY_TYPE = {
    "duplicate": "merge_evidence",
    "multiroot": "split",
    "evidence_mismatch": "clarify",
    "unsupported": "drop",
    "compatible_interpretation": "drop",
    "overstated": "demote",
}
PHASE3_CHALLENGE_TYPES = {
    "unsupported",
    "overstated",
    "duplicate",
    "multiroot",
    "compatible_interpretation",
    "evidence_mismatch",
}
PHASE3_CHALLENGE_ACTIONS = {
    "keep",
    "split",
    "clarify",
    "demote",
    "drop",
    "merge_evidence",
}
PHASE3_CORRECTION_TYPES = {
    "split",
    "clarify",
    "narrow_claim",
    "evidence_fix",
    "wording",
}
PHASE3_V11_CORRECTION_DISPOSITIONS = {
    "drop",
    "downgrade",
    "clarify",
    "narrow",
    "split",
    "abstain",
}
PHASE3_V11_SOURCE_PROVENANCE = {
    "requirement_text",
    "numeric_config",
    "product_screenshot",
    "reference_or_competitor",
    "mixed",
    "unknown",
}
PHASE3_V11_SEMANTIC_CHECK_FIELDS = (
    "compatible_interpretation_exists",
    "original_claim_still_valid",
    "residual_issue_exists",
    "protected_fields_need_human_review",
)
PHASE3_V11_ALLOWED_CORRECTION_FIELDS = {
    "correction_id",
    "challenge_id",
    "target_issue_id",
    "correction_disposition",
    "source_provenance",
    "evidence",
    "rationale",
    "residual_issue",
    "semantic_checks",
    "proposed_changes",
    "replacement_findings",
}
PHASE3_V11_ACTION_DISPOSITIONS = {
    "keep": {"abstain"},
    "split": {"split", "abstain"},
    "clarify": {"clarify", "narrow", "downgrade", "drop", "abstain"},
    "demote": {"downgrade", "drop", "abstain"},
    "drop": {"drop", "abstain"},
    "merge_evidence": {"clarify", "narrow", "drop", "abstain"},
}
PHASE3_EDITABLE_FINDING_FIELDS = {
    "title",
    "current_state",
    "evidence",
    "risk",
    "suggestion",
    "planner_role",
    "confidence",
    "acceptance_criteria",
}
PHASE3_PROTECTED_FIELDS = {
    "overall_evaluation",
    "document_quality_score",
    "score_reason",
    "top_blockers",
    "severity",
    "blocking",
}
PHASE3_SPLIT_REQUIRED_FIELDS = (
    "title",
    "decision_object",
    "current_state",
    "evidence",
    "risk",
    "suggestion",
    "planner_role",
    "acceptance_criteria",
)


def hash_json_payload(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def phase3_primary_report_hash(primary_report: dict[str, Any]) -> str:
    return hash_json_payload(primary_report)


def phase3_expected_echo(
    primary_report: dict[str, Any],
    *,
    protocol_revision: str = PHASE3_PROTOCOL_REVISION,
) -> str:
    if protocol_revision not in PHASE3_PROTOCOL_REVISIONS:
        raise ValueError(f"Unsupported phase3 protocol revision: {protocol_revision}")
    return (
        f"protocol_profile={protocol_revision}; "
        f"primary_report_hash={phase3_primary_report_hash(primary_report)}"
    )


def parse_phase3_review_json(content: str) -> tuple[dict[str, Any], str]:
    payload, error = load_json_with_repairs(content)
    if error:
        return {}, error
    normalized = dict(payload)
    normalized["_provided_top_level_fields"] = sorted(str(key) for key in payload)
    for field in ("challenge_findings", "correction_shadows"):
        value = payload.get(field)
        normalized[field] = [item for item in (value if isinstance(value, list) else []) if isinstance(item, dict)]
    ledger = payload.get("target_coverage_ledger")
    normalized["target_coverage_ledger"] = [
        item for item in (ledger if isinstance(ledger, list) else []) if isinstance(item, dict)
    ]
    notes = payload.get("review_notes")
    normalized["review_notes"] = [
        str(item).strip()
        for item in (notes if isinstance(notes, list) else [])
        if str(item).strip()
    ]
    return normalized, ""


def _primary_finding_index(primary_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for entry in collect_report_entries(primary_report):
        finding = entry.get("finding") if isinstance(entry.get("finding"), dict) else {}
        issue_id = str(finding.get("issue_id") or "").strip()
        if issue_id:
            index[issue_id] = copy.deepcopy(finding)
    return index


def build_phase3_target_inventory(primary_report: dict[str, Any]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for entry in collect_report_entries(primary_report):
        finding = entry.get("finding") if isinstance(entry.get("finding"), dict) else {}
        issue_id = _text(finding.get("issue_id"))
        if not issue_id:
            continue
        order = len(inventory) + 1
        inventory.append(
            {
                "target_order": order,
                "target_issue_id": issue_id,
                "title": _text(finding.get("title") or finding.get("canonical_title")),
                "dimension": _text(entry.get("dimension_name") or finding.get("primary_dimension")),
                "severity": _text(finding.get("severity")),
                "blocking": _text(finding.get("blocking")),
                "evidence": _text(finding.get("evidence")),
            }
        )
    return inventory


def _protected_snapshot(primary_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_evaluation": copy.deepcopy(primary_report.get("overall_evaluation")),
        "document_quality_score": copy.deepcopy(primary_report.get("document_quality_score")),
        "score_reason": copy.deepcopy(primary_report.get("score_reason")),
        "top_blockers": copy.deepcopy(primary_report.get("top_blockers") or []),
        "finding_signals": [
            {
                "issue_id": str(entry["finding"].get("issue_id") or ""),
                "severity": str(entry["finding"].get("severity") or ""),
                "blocking": str(entry["finding"].get("blocking") or ""),
            }
            for entry in collect_report_entries(primary_report)
        ],
    }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has_locatable_evidence(value: Any, document_labels: list[str]) -> bool:
    text = _text(value)
    lowered = text.lower()
    if not text:
        return False
    if any(str(label).strip() and str(label).strip().lower() in lowered for label in document_labels):
        return True
    return bool(
        re.search(
            r"(?:段落|表格|图片|章节|全文|paragraph|table|image|section)\s*[:：#]?\s*[\w\u4e00-\u9fff.-]*",
            text,
            re.IGNORECASE,
        )
        or re.search(r"[\w\-\u4e00-\u9fff.]+\.(?:docx|md|pdf|txt|xlsx?)", text, re.IGNORECASE)
    )


def _contains_protected_key(value: Any) -> list[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in PHASE3_PROTECTED_FIELDS:
                found.add(str(key))
            found.update(_contains_protected_key(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_contains_protected_key(item))
    return sorted(found)


def _evaluate_v12_target_coverage_ledger(
    primary_report: dict[str, Any],
    raw_ledger: list[dict[str, Any]],
    raw_challenges: list[dict[str, Any]],
    document_labels: list[str],
    *,
    protocol_revision: str = PHASE3_V12_PROTOCOL_REVISION,
) -> dict[str, Any]:
    inventory = build_phase3_target_inventory(primary_report)
    expected_ids = [str(item["target_issue_id"]) for item in inventory]
    challenge_by_target: dict[str, list[dict[str, Any]]] = {}
    for challenge in raw_challenges:
        challenge_by_target.setdefault(_text(challenge.get("target_issue_id")), []).append(challenge)

    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    valid_challenge_check_count = 0
    if len(raw_ledger) != len(inventory):
        errors.append(f"target_coverage_count_mismatch:{len(raw_ledger)}/{len(inventory)}")
    for index, item in enumerate(raw_ledger, start=1):
        row = copy.deepcopy(item)
        target_issue_id = _text(item.get("target_issue_id"))
        decision = _text(item.get("decision")).lower()
        challenge_type = _text(item.get("challenge_type")).lower()
        action = _text(item.get("recommended_action")).lower()
        allowed_fields = (
            PHASE3_V13_LEDGER_FIELDS
            if protocol_revision == PHASE3_V13_PROTOCOL_REVISION
            else PHASE3_V12_LEDGER_FIELDS
        )
        unexpected = sorted(set(str(key) for key in item) - allowed_fields)
        if unexpected:
            errors.append(f"target_{index}_unexpected_fields:{','.join(unexpected)}")
        if target_issue_id in seen_ids:
            errors.append(f"target_{index}_duplicate_issue_id:{target_issue_id}")
        seen_ids.add(target_issue_id)
        expected_id = expected_ids[index - 1] if index <= len(expected_ids) else ""
        if target_issue_id != expected_id:
            errors.append(f"target_{index}_order_mismatch:{target_issue_id or '<missing>'}!={expected_id or '<none>'}")
        if item.get("target_order") != index:
            errors.append(f"target_{index}_invalid_target_order")
        if decision not in PHASE3_V12_LEDGER_DECISIONS:
            errors.append(f"target_{index}_invalid_decision")
        if not _text(item.get("rationale")):
            errors.append(f"target_{index}_missing_rationale")
        if not _text(item.get("evidence_checked")):
            errors.append(f"target_{index}_missing_evidence_checked")
        if protocol_revision == PHASE3_V13_PROTOCOL_REVISION:
            raw_checks = item.get("challenge_checks")
            checks = raw_checks if isinstance(raw_checks, dict) else {}
            missing_checks = [key for key in PHASE3_V13_CHALLENGE_PRIORITY if key not in checks]
            unexpected_checks = sorted(set(str(key) for key in checks) - set(PHASE3_V13_CHALLENGE_PRIORITY))
            if not isinstance(raw_checks, dict):
                errors.append(f"target_{index}_challenge_checks_not_object")
            if missing_checks:
                errors.append(f"target_{index}_challenge_checks_missing:{','.join(missing_checks)}")
            if unexpected_checks:
                errors.append(f"target_{index}_challenge_checks_unexpected:{','.join(unexpected_checks)}")
            normalized_checks: dict[str, str] = {}
            for key in PHASE3_V13_CHALLENGE_PRIORITY:
                status = _text(checks.get(key)).lower()
                normalized_checks[key] = status
                if status not in PHASE3_V13_CHECK_STATUSES:
                    errors.append(f"target_{index}_challenge_check_invalid:{key}")
                else:
                    valid_challenge_check_count += 1
            confirmed = [key for key in PHASE3_V13_CHALLENGE_PRIORITY if normalized_checks.get(key) == "confirmed"]
            uncertain = [key for key in PHASE3_V13_CHALLENGE_PRIORITY if normalized_checks.get(key) == "uncertain"]
            expected_decision = "challenge" if confirmed else "abstain" if uncertain else "pass"
            if decision != expected_decision:
                errors.append(f"target_{index}_decision_matrix_mismatch:{decision or '<missing>'}!={expected_decision}")
            if confirmed:
                expected_type = confirmed[0]
                expected_action = PHASE3_V13_ACTION_BY_TYPE[expected_type]
                if challenge_type != expected_type:
                    errors.append(
                        f"target_{index}_challenge_priority_mismatch:{challenge_type or '<missing>'}!={expected_type}"
                    )
                if action != expected_action:
                    errors.append(
                        f"target_{index}_challenge_action_mismatch:{action or '<missing>'}!={expected_action}"
                    )
            row["challenge_checks"] = normalized_checks
        linked = challenge_by_target.get(target_issue_id) or []
        if decision == "challenge":
            if challenge_type not in PHASE3_CHALLENGE_TYPES:
                errors.append(f"target_{index}_invalid_challenge_type")
            if action not in PHASE3_CHALLENGE_ACTIONS:
                errors.append(f"target_{index}_invalid_recommended_action")
            if not _has_locatable_evidence(item.get("evidence_checked"), document_labels):
                errors.append(f"target_{index}_evidence_not_locatable")
            if len(linked) != 1:
                errors.append(f"target_{index}_requires_exactly_one_challenge")
            elif (
                _text(linked[0].get("challenge_type")).lower() != challenge_type
                or _text(linked[0].get("recommended_action")).lower() != action
            ):
                errors.append(f"target_{index}_challenge_payload_mismatch")
        else:
            if challenge_type or action:
                errors.append(f"target_{index}_{decision or 'invalid'}_must_clear_challenge_fields")
            if linked:
                errors.append(f"target_{index}_{decision or 'invalid'}_must_not_emit_challenge")
        row["decision"] = decision
        row["challenge_type"] = challenge_type
        row["recommended_action"] = action
        normalized.append(row)

    unknown_challenge_targets = sorted(set(challenge_by_target) - set(expected_ids))
    if unknown_challenge_targets:
        errors.append("challenge_targets_not_in_inventory:" + ",".join(unknown_challenge_targets))
    matched_ids = {
        _text(item.get("target_issue_id"))
        for index, item in enumerate(raw_ledger, start=1)
        if index <= len(expected_ids) and _text(item.get("target_issue_id")) == expected_ids[index - 1]
    }
    completeness = round(len(matched_ids) / len(expected_ids), 4) if expected_ids else 1.0
    expected_challenge_check_count = (
        len(expected_ids) * len(PHASE3_V13_CHALLENGE_PRIORITY)
        if protocol_revision == PHASE3_V13_PROTOCOL_REVISION
        else 0
    )
    challenge_matrix_error_markers = (
        "challenge_checks",
        "challenge_check_invalid",
        "decision_matrix_mismatch",
        "challenge_priority_mismatch",
        "challenge_action_mismatch",
        "challenge_payload_mismatch",
    )
    challenge_matrix_errors = [
        error for error in errors if any(marker in error for marker in challenge_matrix_error_markers)
    ]
    return {
        "schema_version": 1,
        "expected_count": len(expected_ids),
        "actual_count": len(raw_ledger),
        "completeness": completeness,
        "valid": not errors,
        "errors": errors,
        "inventory": inventory,
        "entries": normalized,
        "decision_keys": sorted(
            f"{_text(item.get('target_issue_id'))}:{_text(item.get('decision')).lower()}"
            for item in normalized
            if _text(item.get("target_issue_id")) and _text(item.get("decision"))
        ),
        "challenge_check_keys": sorted(
            f"{_text(item.get('target_issue_id'))}:{key}:{_text((item.get('challenge_checks') or {}).get(key)).lower()}"
            for item in normalized
            for key in PHASE3_V13_CHALLENGE_PRIORITY
            if protocol_revision == PHASE3_V13_PROTOCOL_REVISION
            and _text(item.get("target_issue_id"))
            and _text((item.get("challenge_checks") or {}).get(key))
        ),
        "challenge_checks_required": protocol_revision == PHASE3_V13_PROTOCOL_REVISION,
        "challenge_checks_completeness": (
            round(valid_challenge_check_count / expected_challenge_check_count, 4)
            if expected_challenge_check_count
            else 1.0
            if protocol_revision == PHASE3_V13_PROTOCOL_REVISION
            else None
        ),
        "challenge_checks_valid": (
            not challenge_matrix_errors
            if protocol_revision == PHASE3_V13_PROTOCOL_REVISION
            else None
        ),
        "challenge_matrix_errors": challenge_matrix_errors,
    }


def _validate_split_items(items: Any, document_labels: list[str]) -> list[str]:
    if not isinstance(items, list) or len(items) < 2:
        return ["split_requires_at_least_two_replacements"]
    errors: list[str] = []
    objects: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"split_{index}_not_object")
            continue
        for field in PHASE3_SPLIT_REQUIRED_FIELDS:
            if not _text(item.get(field)):
                errors.append(f"split_{index}_missing_{field}")
        decision_object = _text(item.get("decision_object")).lower()
        if decision_object:
            objects.append(decision_object)
        if not _has_locatable_evidence(item.get("evidence"), document_labels):
            errors.append(f"split_{index}_evidence_not_locatable")
        protected = _contains_protected_key(item)
        if protected:
            errors.append(f"split_{index}_protected_fields:{','.join(protected)}")
    if len(objects) != len(set(objects)):
        errors.append("split_decision_objects_not_unique")
    return errors


def _evaluate_challenges(
    primary_index: dict[str, dict[str, Any]],
    raw_items: list[dict[str, Any]],
    document_labels: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in raw_items:
        normalized = copy.deepcopy(item)
        challenge_id = _text(item.get("challenge_id"))
        target_issue_id = _text(item.get("target_issue_id"))
        challenge_type = _text(item.get("challenge_type")).lower()
        action = _text(item.get("recommended_action")).lower()
        reasons: list[str] = []
        if not challenge_id:
            reasons.append("missing_challenge_id")
        elif challenge_id in seen_ids:
            reasons.append("duplicate_challenge_id")
        else:
            seen_ids.add(challenge_id)
        if target_issue_id not in primary_index:
            reasons.append("target_issue_id_not_found")
        if challenge_type not in PHASE3_CHALLENGE_TYPES:
            reasons.append("invalid_challenge_type")
        if action not in PHASE3_CHALLENGE_ACTIONS:
            reasons.append("invalid_recommended_action")
        for field in ("challenged_claim", "evidence", "rationale"):
            if not _text(item.get(field)):
                reasons.append(f"missing_{field}")
        if not _has_locatable_evidence(item.get("evidence"), document_labels):
            reasons.append("evidence_not_locatable")
        if challenge_type == "multiroot" and action != "split":
            reasons.append("multiroot_must_recommend_split")
        if action == "split":
            reasons.extend(_validate_split_items(item.get("proposed_split"), document_labels))
        elif item.get("proposed_split") not in (None, []):
            reasons.append("proposed_split_requires_split_action")
        protected = _contains_protected_key(item)
        if protected:
            reasons.append(f"protected_fields_present:{','.join(protected)}")
        normalized["target_title"] = _text(primary_index.get(target_issue_id, {}).get("title"))
        normalized["validation_status"] = "accepted" if not reasons else "rejected"
        normalized["validation_reasons"] = reasons
        (accepted if not reasons else rejected).append(normalized)
    return accepted, rejected


def _build_after_preview(
    before: dict[str, Any],
    correction: dict[str, Any],
) -> dict[str, Any]:
    correction_type = _text(correction.get("correction_type")).lower()
    if correction_type == "split":
        return {"replacement_findings": copy.deepcopy(correction.get("replacement_findings") or [])}
    preview = copy.deepcopy(before)
    changes = correction.get("proposed_changes") if isinstance(correction.get("proposed_changes"), dict) else {}
    for field, value in changes.items():
        if field in PHASE3_EDITABLE_FINDING_FIELDS:
            preview[field] = copy.deepcopy(value)
    return preview


def _build_v11_after_preview(
    before: dict[str, Any],
    correction: dict[str, Any],
) -> dict[str, Any]:
    disposition = _text(correction.get("correction_disposition")).lower()
    if disposition == "drop":
        return {
            "disposition": "drop",
            "target_issue_id": _text(correction.get("target_issue_id")),
            "outcome": "remove_finding_after_human_approval",
            "protected_fields_locked": True,
        }
    if disposition == "split":
        return {
            "disposition": "split",
            "replacement_findings": copy.deepcopy(correction.get("replacement_findings") or []),
            "protected_fields_locked": True,
        }
    preview = {
        key: copy.deepcopy(value)
        for key, value in before.items()
        if key in PHASE3_EDITABLE_FINDING_FIELDS or key in {"issue_id", "canonical_title", "primary_dimension", "evidence_scope"}
    }
    changes = correction.get("proposed_changes") if isinstance(correction.get("proposed_changes"), dict) else {}
    for field, value in changes.items():
        if field in PHASE3_EDITABLE_FINDING_FIELDS:
            preview[field] = copy.deepcopy(value)
    return {
        "disposition": disposition,
        "editable_finding_preview": preview,
        "protected_fields_locked": True,
        "protected_fields_note": "severity/blocking remain unchanged until separate human approval",
    }


def _evaluate_corrections(
    primary_index: dict[str, dict[str, Any]],
    accepted_challenges: list[dict[str, Any]],
    raw_items: list[dict[str, Any]],
    document_labels: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    challenge_index = {
        _text(item.get("challenge_id")): item
        for item in accepted_challenges
        if _text(item.get("challenge_id"))
    }
    seen_ids: set[str] = set()
    for item in raw_items:
        normalized = copy.deepcopy(item)
        correction_id = _text(item.get("correction_id"))
        challenge_id = _text(item.get("challenge_id"))
        target_issue_id = _text(item.get("target_issue_id"))
        correction_type = _text(item.get("correction_type")).lower()
        reasons: list[str] = []
        if not correction_id:
            reasons.append("missing_correction_id")
        elif correction_id in seen_ids:
            reasons.append("duplicate_correction_id")
        else:
            seen_ids.add(correction_id)
        challenge = challenge_index.get(challenge_id)
        if challenge is None:
            reasons.append("accepted_challenge_not_found")
        elif _text(challenge.get("target_issue_id")) != target_issue_id:
            reasons.append("challenge_target_mismatch")
        if target_issue_id not in primary_index:
            reasons.append("target_issue_id_not_found")
        if correction_type not in PHASE3_CORRECTION_TYPES:
            reasons.append("invalid_correction_type")
        for field in ("evidence", "rationale"):
            if not _text(item.get(field)):
                reasons.append(f"missing_{field}")
        if not _has_locatable_evidence(item.get("evidence"), document_labels):
            reasons.append("evidence_not_locatable")
        protected = _contains_protected_key(item)
        if protected:
            reasons.append(f"protected_fields_present:{','.join(protected)}")
        if correction_type == "split":
            reasons.extend(_validate_split_items(item.get("replacement_findings"), document_labels))
            if item.get("proposed_changes") not in (None, {}):
                reasons.append("split_must_not_use_proposed_changes")
        else:
            changes = item.get("proposed_changes")
            if not isinstance(changes, dict) or not changes:
                reasons.append("missing_proposed_changes")
            else:
                unexpected = sorted(set(str(key) for key in changes) - PHASE3_EDITABLE_FINDING_FIELDS)
                if unexpected:
                    reasons.append(f"unsupported_proposed_changes:{','.join(unexpected)}")
            if item.get("replacement_findings") not in (None, []):
                reasons.append("replacement_findings_requires_split")
        before = copy.deepcopy(primary_index.get(target_issue_id) or {})
        normalized["before"] = before
        normalized["after_preview"] = _build_after_preview(before, normalized)
        normalized["applied_to_report"] = False
        normalized["validation_status"] = "accepted" if not reasons else "rejected"
        normalized["validation_reasons"] = reasons
        (accepted if not reasons else rejected).append(normalized)
    return accepted, rejected


def _evaluate_corrections_v11(
    primary_index: dict[str, dict[str, Any]],
    accepted_challenges: list[dict[str, Any]],
    raw_items: list[dict[str, Any]],
    document_labels: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    abstained: list[dict[str, Any]] = []
    challenge_index = {
        _text(item.get("challenge_id")): item
        for item in accepted_challenges
        if _text(item.get("challenge_id"))
    }
    seen_ids: set[str] = set()
    for item in raw_items:
        normalized = copy.deepcopy(item)
        correction_id = _text(item.get("correction_id"))
        challenge_id = _text(item.get("challenge_id"))
        target_issue_id = _text(item.get("target_issue_id"))
        disposition = _text(item.get("correction_disposition")).lower()
        source_provenance = _text(item.get("source_provenance")).lower()
        reasons: list[str] = []
        if not correction_id:
            reasons.append("missing_correction_id")
        elif correction_id in seen_ids:
            reasons.append("duplicate_correction_id")
        else:
            seen_ids.add(correction_id)
        unexpected_fields = sorted(set(str(key) for key in item) - PHASE3_V11_ALLOWED_CORRECTION_FIELDS)
        if unexpected_fields:
            reasons.append(f"unexpected_correction_fields:{','.join(unexpected_fields)}")
        challenge = challenge_index.get(challenge_id)
        if challenge is None:
            reasons.append("accepted_challenge_not_found")
        elif _text(challenge.get("target_issue_id")) != target_issue_id:
            reasons.append("challenge_target_mismatch")
        if target_issue_id not in primary_index:
            reasons.append("target_issue_id_not_found")
        if disposition not in PHASE3_V11_CORRECTION_DISPOSITIONS:
            reasons.append("invalid_correction_disposition")
        if source_provenance not in PHASE3_V11_SOURCE_PROVENANCE:
            reasons.append("invalid_source_provenance")
        for field in ("evidence", "rationale"):
            if not _text(item.get(field)):
                reasons.append(f"missing_{field}")
        if not _has_locatable_evidence(item.get("evidence"), document_labels):
            reasons.append("evidence_not_locatable")
        protected = _contains_protected_key(item)
        if protected:
            reasons.append(f"protected_fields_present:{','.join(protected)}")

        semantic_checks = item.get("semantic_checks")
        if not isinstance(semantic_checks, dict):
            semantic_checks = {}
            reasons.append("missing_semantic_checks")
        for field in PHASE3_V11_SEMANTIC_CHECK_FIELDS:
            if not isinstance(semantic_checks.get(field), bool):
                reasons.append(f"semantic_check_not_boolean:{field}")

        proposed_changes = item.get("proposed_changes")
        if not isinstance(proposed_changes, dict):
            proposed_changes = {}
            reasons.append("proposed_changes_not_object")
        unexpected_changes = sorted(set(str(key) for key in proposed_changes) - PHASE3_EDITABLE_FINDING_FIELDS)
        if unexpected_changes:
            reasons.append(f"unsupported_proposed_changes:{','.join(unexpected_changes)}")
        replacement_findings = item.get("replacement_findings")
        if not isinstance(replacement_findings, list):
            replacement_findings = []
            reasons.append("replacement_findings_not_array")

        action = _text((challenge or {}).get("recommended_action")).lower()
        allowed_dispositions = PHASE3_V11_ACTION_DISPOSITIONS.get(action, set())
        if disposition in PHASE3_V11_CORRECTION_DISPOSITIONS and disposition not in allowed_dispositions:
            reasons.append(f"challenge_action_disposition_mismatch:{action}->{disposition}")

        challenge_type = _text((challenge or {}).get("challenge_type")).lower()
        compatible_exists = semantic_checks.get("compatible_interpretation_exists") is True
        original_claim_valid = semantic_checks.get("original_claim_still_valid") is True
        residual_issue_exists = semantic_checks.get("residual_issue_exists") is True
        protected_review = semantic_checks.get("protected_fields_need_human_review") is True
        if challenge_type == "compatible_interpretation" and not compatible_exists:
            reasons.append("compatible_challenge_requires_compatible_interpretation")
        if (
            challenge_type == "compatible_interpretation"
            and compatible_exists
            and not original_claim_valid
            and disposition not in {"drop", "abstain"}
        ):
            reasons.append("compatible_interpretation_requires_drop_or_abstain")
        if disposition in {"downgrade", "clarify", "narrow", "split"} and not original_claim_valid:
            reasons.append(f"{disposition}_requires_original_claim_still_valid")
        if source_provenance in {"reference_or_competitor", "unknown"} and disposition not in {
            "drop",
            "downgrade",
            "abstain",
        }:
            reasons.append("reference_source_cannot_drive_product_rewrite")

        if disposition in {"drop", "abstain"}:
            if proposed_changes:
                reasons.append(f"{disposition}_must_not_use_proposed_changes")
            if replacement_findings:
                reasons.append(f"{disposition}_must_not_use_replacement_findings")
            if residual_issue_exists:
                reasons.append(f"{disposition}_requires_no_residual_issue")
        elif disposition == "split":
            reasons.extend(_validate_split_items(replacement_findings, document_labels))
            if proposed_changes:
                reasons.append("split_must_not_use_proposed_changes")
            if not residual_issue_exists:
                reasons.append("split_requires_residual_issue")
        elif disposition in {"clarify", "narrow", "downgrade"}:
            if not proposed_changes:
                reasons.append("missing_proposed_changes")
            if replacement_findings:
                reasons.append("replacement_findings_requires_split")
            if not residual_issue_exists or not _text(item.get("residual_issue")):
                reasons.append(f"{disposition}_requires_residual_issue")
        if disposition == "downgrade":
            if not _text(proposed_changes.get("risk")):
                reasons.append("downgrade_requires_risk_rewrite")
            if not protected_review:
                reasons.append("downgrade_requires_protected_fields_human_review")
        elif protected_review and disposition != "abstain":
            reasons.append("protected_fields_human_review_only_for_downgrade")

        before = copy.deepcopy(primary_index.get(target_issue_id) or {})
        normalized["correction_type"] = disposition
        normalized["before"] = before
        normalized["after_preview"] = (
            {} if disposition == "abstain" else _build_v11_after_preview(before, normalized)
        )
        normalized["applied_to_report"] = False
        if reasons:
            normalized["validation_status"] = "rejected"
            normalized["validation_reasons"] = reasons
            rejected.append(normalized)
        elif disposition == "abstain":
            normalized["validation_status"] = "abstained"
            normalized["validation_reasons"] = []
            abstained.append(normalized)
        else:
            normalized["validation_status"] = "accepted"
            normalized["validation_reasons"] = []
            accepted.append(normalized)
    return accepted, rejected, abstained


def evaluate_phase3_review(
    primary_report: dict[str, Any],
    review: dict[str, Any],
    *,
    document_labels: list[str] | None = None,
    protocol_revision: str = PHASE3_PROTOCOL_REVISION,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if protocol_revision not in PHASE3_PROTOCOL_REVISIONS:
        raise ValueError(f"Unsupported phase3 protocol revision: {protocol_revision}")
    labels = [str(item).strip() for item in (document_labels or []) if str(item).strip()]
    report_before = copy.deepcopy(primary_report)
    report_hash = phase3_primary_report_hash(report_before)
    protected_before = _protected_snapshot(report_before)
    protected_hash = hash_json_payload(protected_before)
    provided_fields = {
        str(item)
        for item in review.get("_provided_top_level_fields") or review.keys()
        if not str(item).startswith("_")
    }
    ledger_protocol = protocol_revision in {
        PHASE3_V12_PROTOCOL_REVISION,
        PHASE3_V13_PROTOCOL_REVISION,
    }
    allowed_top_level_fields = (
        PHASE3_V12_ALLOWED_TOP_LEVEL_FIELDS
        if ledger_protocol
        else PHASE3_ALLOWED_TOP_LEVEL_FIELDS
    )
    forbidden_fields = sorted(provided_fields - allowed_top_level_fields)
    notes = [str(item).strip() for item in review.get("review_notes") or [] if str(item).strip()]
    expected_echo = phase3_expected_echo(report_before, protocol_revision=protocol_revision)
    echo_matched = bool(notes) and notes[-1] == expected_echo
    protocol_errors: list[str] = []
    if forbidden_fields:
        protocol_errors.append("forbidden_top_level_fields:" + ",".join(forbidden_fields))
    if not echo_matched:
        protocol_errors.append("protocol_echo_missing_or_mismatched")
    raw_challenges = [item for item in review.get("challenge_findings") or [] if isinstance(item, dict)]
    target_coverage_ledger = (
        _evaluate_v12_target_coverage_ledger(
            report_before,
            [item for item in review.get("target_coverage_ledger") or [] if isinstance(item, dict)],
            raw_challenges,
            labels,
            protocol_revision=protocol_revision,
        )
        if ledger_protocol
        else {
            "schema_version": 0,
            "expected_count": 0,
            "actual_count": 0,
            "completeness": None,
            "valid": True,
            "errors": [],
            "inventory": [],
            "entries": [],
            "decision_keys": [],
            "challenge_check_keys": [],
            "challenge_checks_required": False,
            "challenge_checks_completeness": None,
            "challenge_checks_valid": None,
            "challenge_matrix_errors": [],
        }
    )
    if ledger_protocol and not target_coverage_ledger["valid"]:
        protocol_errors.extend(
            f"target_coverage_ledger:{error}" for error in target_coverage_ledger.get("errors") or []
        )
    primary_index = _primary_finding_index(report_before)
    if protocol_errors:
        accepted_challenges: list[dict[str, Any]] = []
        rejected_challenges = [
            {**copy.deepcopy(item), "validation_status": "rejected", "validation_reasons": list(protocol_errors)}
            for item in review.get("challenge_findings") or []
            if isinstance(item, dict)
        ]
        accepted_corrections: list[dict[str, Any]] = []
        abstained_corrections: list[dict[str, Any]] = []
        rejected_corrections = [
            {**copy.deepcopy(item), "validation_status": "rejected", "validation_reasons": list(protocol_errors)}
            for item in review.get("correction_shadows") or []
            if isinstance(item, dict)
        ]
    else:
        accepted_challenges, rejected_challenges = _evaluate_challenges(
            primary_index,
            raw_challenges,
            labels,
        )
        raw_corrections = [item for item in review.get("correction_shadows") or [] if isinstance(item, dict)]
        if protocol_revision in {
            PHASE3_V11_PROTOCOL_REVISION,
            PHASE3_V12_PROTOCOL_REVISION,
            PHASE3_V13_PROTOCOL_REVISION,
        }:
            accepted_corrections, rejected_corrections, abstained_corrections = _evaluate_corrections_v11(
                primary_index,
                accepted_challenges,
                raw_corrections,
                labels,
            )
        else:
            accepted_corrections, rejected_corrections = _evaluate_corrections(
                primary_index,
                accepted_challenges,
                raw_corrections,
                labels,
            )
            abstained_corrections = []
    protected_after = _protected_snapshot(primary_report)
    report_after_hash = phase3_primary_report_hash(primary_report)
    baseline_lock = {
        "primary_report_hash_before": report_hash,
        "primary_report_hash_after": report_after_hash,
        "protected_fields_hash_before": protected_hash,
        "protected_fields_hash_after": hash_json_payload(protected_after),
        "primary_report_unchanged": report_hash == report_after_hash,
        "protected_fields_unchanged": protected_before == protected_after,
        "score_locked": report_before.get("document_quality_score") == primary_report.get("document_quality_score"),
        "score_reason_locked": report_before.get("score_reason") == primary_report.get("score_reason"),
        "top_blockers_locked": report_before.get("top_blockers") == primary_report.get("top_blockers"),
        "severity_blocking_locked": protected_before.get("finding_signals") == protected_after.get("finding_signals"),
    }
    baseline_lock["passed"] = all(
        baseline_lock[key] is True
        for key in (
            "primary_report_unchanged",
            "protected_fields_unchanged",
            "score_locked",
            "score_reason_locked",
            "top_blockers_locked",
            "severity_blocking_locked",
        )
    )
    protocol_gate = {
        "required": True,
        "protocol_revision": protocol_revision,
        "expected_primary_report_hash": report_hash,
        "expected_echo": expected_echo,
        "echo_matched": echo_matched,
        "forbidden_top_level_fields": forbidden_fields,
        "errors": protocol_errors,
        "passed": not protocol_errors,
    }
    challenge_advice = {
        "protocol_revision": protocol_revision,
        "mode": "advice_only",
        "applied_to_report": False,
        "primary_report_hash": report_hash,
        "protocol_gate": protocol_gate,
        "baseline_lock": baseline_lock,
        "accepted_count": len(accepted_challenges),
        "rejected_count": len(rejected_challenges),
        "accepted_challenges": accepted_challenges,
        "rejected_challenges": rejected_challenges,
        "target_coverage_ledger": target_coverage_ledger,
        "review_notes": notes[:-1] if echo_matched else notes,
    }
    correction_shadow = {
        "protocol_revision": protocol_revision,
        "mode": "shadow_only",
        "applied_to_report": False,
        "primary_report_hash": report_hash,
        "protocol_gate": protocol_gate,
        "baseline_lock": baseline_lock,
        "accepted_count": len(accepted_corrections),
        "rejected_count": len(rejected_corrections),
        "abstained_count": len(abstained_corrections),
        "accepted_corrections": accepted_corrections,
        "rejected_corrections": rejected_corrections,
        "abstained_corrections": abstained_corrections,
    }
    summary = {
        "protocol_revision": protocol_revision,
        "protocol_gate_passed": protocol_gate["passed"],
        "baseline_lock_passed": baseline_lock["passed"],
        "primary_report_hash": report_hash,
        "challenge_claimed_count": len(review.get("challenge_findings") or []),
        "challenge_accepted_count": len(accepted_challenges),
        "challenge_rejected_count": len(rejected_challenges),
        "correction_claimed_count": len(review.get("correction_shadows") or []),
        "correction_accepted_count": len(accepted_corrections),
        "correction_rejected_count": len(rejected_corrections),
        "correction_abstained_count": len(abstained_corrections),
        "correction_disposition_counts": dict(
            sorted(
                Counter(
                    _text(item.get("correction_disposition") or item.get("correction_type")).lower()
                    for item in accepted_corrections
                    if _text(item.get("correction_disposition") or item.get("correction_type"))
                ).items()
            )
        ),
        "challenge_keys": sorted(
            {
                f"{_text(item.get('target_issue_id'))}:{_text(item.get('challenge_type')).lower()}:{_text(item.get('recommended_action')).lower()}"
                for item in accepted_challenges
            }
        ),
        "correction_keys": sorted(
            {
                f"{_text(item.get('target_issue_id'))}:{_text(item.get('correction_disposition') or item.get('correction_type')).lower()}"
                for item in accepted_corrections
            }
        ),
        "target_coverage_ledger_complete": target_coverage_ledger.get("completeness") == 1.0,
        "target_coverage_ledger_completeness": target_coverage_ledger.get("completeness"),
        "target_coverage_ledger_valid": bool(target_coverage_ledger.get("valid")),
        "target_coverage_ledger_errors": target_coverage_ledger.get("errors") or [],
        "target_decision_keys": target_coverage_ledger.get("decision_keys") or [],
        "challenge_check_keys": target_coverage_ledger.get("challenge_check_keys") or [],
        "challenge_checks_complete": target_coverage_ledger.get("challenge_checks_completeness") == 1.0,
        "challenge_checks_completeness": target_coverage_ledger.get("challenge_checks_completeness"),
        "challenge_checks_valid": target_coverage_ledger.get("challenge_checks_valid"),
        "challenge_matrix_errors": target_coverage_ledger.get("challenge_matrix_errors") or [],
        "challenge_target_keys": sorted(
            {
                _text(item.get("target_issue_id"))
                for item in accepted_challenges
                if _text(item.get("target_issue_id"))
            }
        ),
    }
    return challenge_advice, correction_shadow, summary


def _report_finding_container(
    report: dict[str, Any], target_issue_id: str
) -> tuple[list[dict[str, Any]], int] | None:
    for dimension in report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        findings = dimension.get("findings")
        if not isinstance(findings, list):
            continue
        for index, finding in enumerate(findings):
            if isinstance(finding, dict) and _text(finding.get("issue_id")) == target_issue_id:
                return findings, index
    findings = report.get("cross_document_issues")
    if isinstance(findings, list):
        for index, finding in enumerate(findings):
            if isinstance(finding, dict) and _text(finding.get("issue_id")) == target_issue_id:
                return findings, index
    return None


def _downgrade_signal(value: Any, mapping: dict[str, str]) -> str:
    text = _text(value)
    return mapping.get(text, text)


def _report_risk_counts(report: dict[str, Any]) -> dict[str, int]:
    findings = [entry["finding"] for entry in collect_report_entries(report)]
    return {
        "finding_count": len(findings),
        "high_or_block_dev_count": sum(is_blocking_high(item) for item in findings),
        "fatal_core_conflict_count": sum(is_fatal_core_conflict(item) for item in findings),
        "medium_count": sum(_text(item.get("severity")) == "中" for item in findings),
    }


def apply_human_approved_phase3_corrections(
    primary_report: dict[str, Any],
    corrections: list[dict[str, Any]],
    *,
    protocol_revision: str = PHASE3_V12_PROTOCOL_REVISION,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply already machine-admitted and human-approved ledger-protocol corrections deterministically."""
    if protocol_revision not in {PHASE3_V12_PROTOCOL_REVISION, PHASE3_V13_PROTOCOL_REVISION}:
        raise ValueError(f"Human-approved phase3 application is unsupported for: {protocol_revision}")
    report = copy.deepcopy(primary_report)
    score_before = _text(report.get("document_quality_score"))
    reason_before = _text(report.get("score_reason"))
    blockers_before = copy.deepcopy(report.get("top_blockers") or [])
    risks_before = _report_risk_counts(report)
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    severity_downgrade = {"高": "中", "中": "低", "低": "低", "high": "medium", "medium": "low", "low": "low"}
    blocking_downgrade = {
        "阻塞开发": "阻塞测试用例设计",
        "阻塞测试用例设计": "建议优化",
        "建议优化": "建议优化",
        "block_dev": "block_test",
        "block_test": "advice",
        "advice": "advice",
    }

    for correction in corrections:
        target_issue_id = _text(correction.get("target_issue_id"))
        disposition = _text(correction.get("correction_disposition") or correction.get("correction_type")).lower()
        if not target_issue_id or target_issue_id in seen_targets:
            skipped.append({"target_issue_id": target_issue_id, "reason": "missing_or_duplicate_target"})
            continue
        seen_targets.add(target_issue_id)
        located = _report_finding_container(report, target_issue_id)
        if located is None:
            skipped.append({"target_issue_id": target_issue_id, "reason": "target_not_found"})
            continue
        container, index = located
        before = copy.deepcopy(container[index])
        preview = correction.get("after_preview") if isinstance(correction.get("after_preview"), dict) else {}
        after_severity = _text(before.get("severity"))
        if disposition == "drop":
            container.pop(index)
            after_severity = "removed"
        elif disposition == "split":
            replacements = preview.get("replacement_findings") if isinstance(preview, dict) else []
            if not isinstance(replacements, list) or len(replacements) < 2:
                skipped.append({"target_issue_id": target_issue_id, "reason": "invalid_split_preview"})
                continue
            materialized: list[dict[str, Any]] = []
            for replacement_index, replacement in enumerate(replacements, start=1):
                if not isinstance(replacement, dict):
                    continue
                finding = copy.deepcopy(before)
                for field in PHASE3_EDITABLE_FINDING_FIELDS:
                    if field in replacement:
                        finding[field] = copy.deepcopy(replacement[field])
                finding["issue_id"] = f"{target_issue_id}__S{replacement_index:02d}"
                finding["canonical_title"] = _text(finding.get("title"))
                materialized.append(finding)
            if len(materialized) < 2:
                skipped.append({"target_issue_id": target_issue_id, "reason": "invalid_split_materialization"})
                continue
            container[index : index + 1] = materialized
            after_severity = "inherited_per_split"
        elif disposition in {"downgrade", "clarify", "narrow"}:
            editable_preview = preview.get("editable_finding_preview") if isinstance(preview, dict) else {}
            if not isinstance(editable_preview, dict):
                editable_preview = {}
            updated = copy.deepcopy(before)
            for field in PHASE3_EDITABLE_FINDING_FIELDS:
                if field in editable_preview:
                    updated[field] = copy.deepcopy(editable_preview[field])
            if disposition == "downgrade":
                updated["severity"] = _downgrade_signal(updated.get("severity"), severity_downgrade)
                updated["blocking"] = _downgrade_signal(updated.get("blocking"), blocking_downgrade)
            container[index] = updated
            after_severity = _text(updated.get("severity"))
        else:
            skipped.append({"target_issue_id": target_issue_id, "reason": f"unsupported_disposition:{disposition}"})
            continue
        applied.append(
            {
                "correction_id": _text(correction.get("correction_id")),
                "target_issue_id": target_issue_id,
                "disposition": disposition,
                "severity_before": _text(before.get("severity")),
                "severity_after": after_severity,
                "blocking_before": _text(before.get("blocking")),
            }
        )

    report["top_blockers"] = build_top_blockers(report)
    score_after, reason_after = stable_score(report)
    report["document_quality_score"] = score_after
    report["score_reason"] = reason_after
    if applied:
        report["overall_evaluation"] = f"经二审人工确认并应用纠错后，{reason_after}"
    risks_after = _report_risk_counts(report)
    summary = {
        "application_mode": f"human_approved_deterministic_{protocol_revision}",
        "applied": bool(applied),
        "applied_correction_count": len(applied),
        "skipped_correction_count": len(skipped),
        "applied_corrections": applied,
        "skipped_corrections": skipped,
        "score_recalculation": {
            "owner": "system_deterministic_scoring",
            "trigger": "after_human_approved_corrections",
            "score_before": score_before,
            "score_after": score_after,
            "score_changed": score_before != score_after,
            "score_reason_before": reason_before,
            "score_reason_after": reason_after,
            "risk_counts_before": risks_before,
            "risk_counts_after": risks_after,
            "top_blockers_before": blockers_before,
            "top_blockers_after": copy.deepcopy(report.get("top_blockers") or []),
        },
    }
    return report, summary


def render_phase3_challenge_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 3 Challenge 建议（Advice Only）",
        "",
        "本工件只提供质疑和拆分建议，不修改正式报告。",
        "",
        f"- 协议门槛：{'通过' if (payload.get('protocol_gate') or {}).get('passed') else '失败'}",
        f"- Primary 基线锁：{'通过' if (payload.get('baseline_lock') or {}).get('passed') else '失败'}",
        f"- 接受：{payload.get('accepted_count', 0)}",
        f"- 拒绝：{payload.get('rejected_count', 0)}",
        "",
        "## 已准入质疑",
    ]
    accepted = payload.get("accepted_challenges") or []
    if not accepted:
        lines.append("- 暂无")
    for item in accepted:
        lines.extend(
            [
                f"### {item.get('challenge_id') or '未编号'} · {item.get('target_title') or item.get('target_issue_id')}",
                "",
                f"- 类型：{item.get('challenge_type')}",
                f"- 建议动作：{item.get('recommended_action')}",
                f"- 被质疑判断：{item.get('challenged_claim')}",
                f"- 证据：{item.get('evidence')}",
                f"- 理由：{item.get('rationale')}",
                "",
            ]
        )
    if payload.get("rejected_challenges"):
        lines.append("## 未准入质疑")
        for item in payload.get("rejected_challenges") or []:
            lines.append(
                f"- {item.get('challenge_id') or '未编号'}：{', '.join(str(reason) for reason in item.get('validation_reasons') or [])}"
            )
    return "\n".join(lines).strip() + "\n"


def render_phase3_correction_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase 3 Correct 影子建议（Shadow Only）",
        "",
        "本工件只保存 before/after 预览，不写回正式报告。",
        "",
        f"- Primary 基线锁：{'通过' if (payload.get('baseline_lock') or {}).get('passed') else '失败'}",
        f"- 接受：{payload.get('accepted_count', 0)}",
        f"- 拒绝：{payload.get('rejected_count', 0)}",
        f"- 主动放弃：{payload.get('abstained_count', 0)}",
        "",
        "## 已准入影子修正",
    ]
    accepted = payload.get("accepted_corrections") or []
    if not accepted:
        lines.append("- 暂无")
    for item in accepted:
        lines.extend(
            [
                f"### {item.get('correction_id') or '未编号'} · {item.get('target_issue_id') or '未知目标'}",
                "",
                f"- 处置：{item.get('correction_disposition') or item.get('correction_type')}",
                f"- 证据：{item.get('evidence')}",
                f"- 理由：{item.get('rationale')}",
                f"- 已写回正式报告：{'是' if item.get('applied_to_report') else '否'}",
                "",
            ]
        )
    if payload.get("rejected_corrections"):
        lines.append("## 未准入影子修正")
        for item in payload.get("rejected_corrections") or []:
            lines.append(
                f"- {item.get('correction_id') or '未编号'}：{', '.join(str(reason) for reason in item.get('validation_reasons') or [])}"
            )
    if payload.get("abstained_corrections"):
        lines.append("## 主动放弃的修正")
        for item in payload.get("abstained_corrections") or []:
            lines.append(f"- {item.get('correction_id') or '未编号'}：保留 Challenge，不生成影子修正")
    return "\n".join(lines).strip() + "\n"


def write_phase3_artifacts(
    challenge_advice: dict[str, Any],
    correction_shadow: dict[str, Any],
    challenge_json_path: Path,
    correction_json_path: Path,
) -> None:
    challenge_json_path.parent.mkdir(parents=True, exist_ok=True)
    correction_json_path.parent.mkdir(parents=True, exist_ok=True)
    challenge_json_path.write_text(json.dumps(challenge_advice, ensure_ascii=False, indent=2), encoding="utf-8")
    correction_json_path.write_text(json.dumps(correction_shadow, ensure_ascii=False, indent=2), encoding="utf-8")
    challenge_json_path.with_suffix(".md").write_text(
        render_phase3_challenge_markdown(challenge_advice), encoding="utf-8"
    )
    correction_json_path.with_suffix(".md").write_text(
        render_phase3_correction_markdown(correction_shadow), encoding="utf-8"
    )


__all__ = [
    "PHASE3_PROTOCOL_REVISION",
    "PHASE3_PROTOCOL_REVISIONS",
    "PHASE3_V1_PROTOCOL_REVISION",
    "PHASE3_V11_PROTOCOL_REVISION",
    "PHASE3_V12_PROTOCOL_REVISION",
    "PHASE3_V13_PROTOCOL_REVISION",
    "apply_human_approved_phase3_corrections",
    "build_phase3_target_inventory",
    "evaluate_phase3_review",
    "hash_json_payload",
    "parse_phase3_review_json",
    "phase3_expected_echo",
    "phase3_primary_report_hash",
    "render_phase3_challenge_markdown",
    "render_phase3_correction_markdown",
    "write_phase3_artifacts",
]
