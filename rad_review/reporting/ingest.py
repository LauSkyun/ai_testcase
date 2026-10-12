from __future__ import annotations

import json
import re
import string
from typing import Any

from rad_review.docx_reader import ParsedDocument

from .normalize import fallback_report, normalize_report, repair_missing_issue_ids
from .schema import assert_report_integrity, validate_report_integrity
from .stabilize import build_top_blockers, dedupe_report_sections, reorder_top_blockers_by_preference, stabilize_report


def extract_json_payload(content: str) -> str:
    cleaned = content.strip()
    if not cleaned:
        return cleaned

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced_match:
        return fenced_match.group(1).strip()

    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    candidates = iter_json_object_candidates(cleaned)
    if candidates:
        return candidates[-1]

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if 0 <= first_brace < last_brace:
        return cleaned[first_brace : last_brace + 1].strip()
    return cleaned


def iter_json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    stack = 0
    start_index: int | None = None
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if stack == 0:
                start_index = index
            stack += 1
            continue
        if char == "}" and stack > 0:
            stack -= 1
            if stack == 0 and start_index is not None:
                candidate = text[start_index : index + 1].strip()
                if looks_like_json_object(candidate):
                    candidates.append(candidate)
                start_index = None
    return candidates


def looks_like_json_object(candidate: str) -> bool:
    if not candidate.startswith("{") or not candidate.endswith("}"):
        return False
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict)


def escape_invalid_json_backslashes(text: str) -> tuple[str, bool]:
    repaired: list[str] = []
    changed = False
    in_string = False
    index = 0
    valid_escape_chars = {'"', "\\", "/", "b", "f", "n", "r", "t"}
    hex_chars = set(string.hexdigits)

    while index < len(text):
        char = text[index]

        if not in_string:
            repaired.append(char)
            if char == '"':
                in_string = True
            index += 1
            continue

        if char == '"':
            repaired.append(char)
            in_string = False
            index += 1
            continue

        if char != "\\":
            repaired.append(char)
            index += 1
            continue

        if index + 1 >= len(text):
            repaired.append("\\\\")
            changed = True
            index += 1
            continue

        next_char = text[index + 1]
        if next_char in valid_escape_chars:
            repaired.append(char)
            repaired.append(next_char)
            index += 2
            continue

        if next_char == "u":
            unicode_digits = text[index + 2 : index + 6]
            if len(unicode_digits) == 4 and all(digit in hex_chars for digit in unicode_digits):
                repaired.append(char)
                repaired.append(next_char)
                repaired.extend(unicode_digits)
                index += 6
                continue

        repaired.append("\\\\")
        changed = True
        index += 1

    return "".join(repaired), changed


def escape_unescaped_json_string_quotes(text: str) -> tuple[str, bool]:
    """Escape model-emitted inner quotes while preserving actual JSON delimiters."""
    repaired: list[str] = []
    changed = False
    in_string = False
    escape = False
    for index, char in enumerate(text):
        if not in_string:
            repaired.append(char)
            if char == '"':
                in_string = True
            continue
        if escape:
            repaired.append(char)
            escape = False
            continue
        if char == "\\":
            repaired.append(char)
            escape = True
            continue
        if char != '"':
            repaired.append(char)
            continue
        lookahead = index + 1
        while lookahead < len(text) and text[lookahead].isspace():
            lookahead += 1
        next_char = text[lookahead] if lookahead < len(text) else ""
        if not next_char or next_char in {",", ":", "}", "]"}:
            repaired.append(char)
            in_string = False
        else:
            repaired.append('\\"')
            changed = True
    return "".join(repaired), changed


def repair_json_like_payload(text: str) -> str:
    repaired_lines: list[str] = []
    changed = False
    line_pattern = re.compile(r'^(\s*"[^"]+"\s*:\s*)(.+?)(\s*,?\s*)$')
    literal_pattern = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")

    for line in text.splitlines():
        match = line_pattern.match(line)
        if not match:
            repaired_lines.append(line)
            continue

        prefix, raw_value, suffix = match.groups()
        value = raw_value.strip()
        if value.startswith('"') and not value.endswith('"'):
            repaired_lines.append(f"{prefix}{json.dumps(value[1:], ensure_ascii=False)}{suffix}")
            changed = True
            continue
        if (
            not value
            or value.startswith(('"', "{", "["))
            or value in {"true", "false", "null"}
            or literal_pattern.fullmatch(value)
        ):
            repaired_lines.append(line)
            continue

        repaired_lines.append(f"{prefix}{json.dumps(value, ensure_ascii=False)}{suffix}")
        changed = True

    if not changed:
        repaired = text
    else:
        repaired = "\n".join(repaired_lines)
        if text.endswith("\n"):
            repaired += "\n"

    # Long model responses occasionally omit the closing quote and colon from
    # an object key immediately before an array/object value, for example:
    # `"strengths [` on its own line. Repair only this tightly-scoped shape.
    repaired = re.sub(
        r'(?m)^(\s*)"([A-Za-z_][A-Za-z0-9_]*)\s*([\[{])\s*$',
        r'\1"\2": \3',
        repaired,
    )

    # Collapse duplicated closing quotes before detecting true inner quotes.
    repaired = re.sub(r'(?<!\\)"{3,}(?=\s*[,}\]])', '"', repaired)

    repaired, _ = escape_unescaped_json_string_quotes(repaired)
    repaired, _ = escape_invalid_json_backslashes(repaired)

    # Models sometimes duplicate the closing quote of a string item, for example:
    # `"some item"""` before a comma or closing bracket.
    repaired = re.sub(r'(?<!\\)"{3,}(?=\s*[,}\]])', '"', repaired)

    # Tolerate trailing commas in JSON-like arrays/objects.
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def load_json_with_repairs(content: str) -> tuple[dict[str, Any], str]:
    cleaned = extract_json_payload(content)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        repaired = repair_json_like_payload(cleaned)
        if repaired == cleaned:
            return {}, str(exc)
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            return {}, str(exc)
    return parsed if isinstance(parsed, dict) else {}, ""


def parse_model_json(content: str, documents: list[ParsedDocument] | None = None) -> tuple[dict[str, Any], str]:
    report, error = load_json_with_repairs(content)
    if error:
        return fallback_report(f"模型返回不是合法 JSON：{error}", raw_response=content), error

    report, issue_id_repairs = repair_missing_issue_ids(normalize_report(report))
    model_score = str(report.get("document_quality_score") or "").strip()
    model_score_reason = str(report.get("score_reason") or "").strip()
    model_top_blockers = list(report.get("top_blockers") or [])
    stabilized = stabilize_report(report, documents or [])
    if model_score in {"A", "B", "C", "D"}:
        stabilized["document_quality_score"] = model_score
    if model_score_reason:
        stabilized["score_reason"] = model_score_reason
    dedupe_report_sections(stabilized)
    if model_top_blockers:
        stabilized["top_blockers"] = reorder_top_blockers_by_preference(stabilized, model_top_blockers)
    else:
        stabilized["top_blockers"] = build_top_blockers(stabilized)
    if issue_id_repairs:
        stabilized["_issue_id_repair_count"] = len(issue_id_repairs)
        stabilized["_issue_id_repairs"] = issue_id_repairs
    assert_report_integrity(stabilized)
    return stabilized, ""


def parse_candidate_model_json(content: str, documents: list[ParsedDocument] | None = None) -> tuple[dict[str, Any], str]:
    report, error = load_json_with_repairs(content)
    if error:
        return {}, error

    candidate, issue_id_repairs = repair_missing_issue_ids(normalize_report(report))
    if not candidate.get("top_blockers"):
        candidate["top_blockers"] = build_top_blockers(candidate)

    errors = validate_report_integrity(candidate)
    if errors and any("top_blockers" in item for item in errors):
        candidate["top_blockers"] = build_top_blockers(candidate)
        errors = validate_report_integrity(candidate)

    if errors:
        return {}, "；".join(errors)
    if issue_id_repairs:
        candidate["_issue_id_repair_count"] = len(issue_id_repairs)
        candidate["_issue_id_repairs"] = issue_id_repairs
    return candidate, ""


def parse_audit_json(content: str) -> tuple[dict[str, Any], str]:
    return load_json_with_repairs(content)


def parse_dual_pass_review_json(content: str) -> tuple[dict[str, Any], str]:
    payload, error = load_json_with_repairs(content)
    if error:
        return {}, error
    normalized = dict(payload)
    normalized["_provided_top_level_fields"] = sorted(str(key) for key in payload)
    if not isinstance(normalized.get("quality_assessment"), dict):
        normalized["quality_assessment"] = {}
    coverage_ledger = normalized.get("coverage_ledger")
    normalized["coverage_ledger"] = [
        item for item in (coverage_ledger if isinstance(coverage_ledger, list) else []) if isinstance(item, dict)
    ]
    missed_findings = normalized.get("missed_findings")
    normalized["missed_findings"] = [
        item for item in (missed_findings if isinstance(missed_findings, list) else []) if isinstance(item, dict)
    ]

    unsupported_findings = normalized.get("unsupported_findings")
    normalized["unsupported_findings"] = []
    for item in unsupported_findings if isinstance(unsupported_findings, list) else []:
        if isinstance(item, dict):
            normalized["unsupported_findings"].append(item)
        elif str(item).strip():
            normalized["unsupported_findings"].append({"title": str(item).strip(), "reason": ""})

    merge_recommendations = normalized.get("merge_recommendations")
    normalized["merge_recommendations"] = []
    for item in merge_recommendations if isinstance(merge_recommendations, list) else []:
        if isinstance(item, dict):
            normalized["merge_recommendations"].append(item)
        elif str(item).strip():
            normalized["merge_recommendations"].append({"titles": [], "merged_title": "", "reason": str(item).strip()})

    review_notes = normalized.get("review_notes")
    normalized["review_notes"] = [
        str(item).strip() for item in (review_notes if isinstance(review_notes, list) else []) if str(item).strip()
    ]
    candidate_lineage = normalized.get("candidate_lineage")
    normalized["candidate_lineage"] = candidate_lineage if isinstance(candidate_lineage, dict) else {}
    for key in ("kept", "added", "merged", "dropped"):
        value = normalized["candidate_lineage"].get(key)
        normalized["candidate_lineage"][key] = [
            item for item in (value if isinstance(value, list) else []) if isinstance(item, dict)
        ]
    if not isinstance(normalized.get("candidate_report"), dict):
        normalized["candidate_report"] = {}
    if not isinstance(normalized.get("candidate_readiness"), dict):
        normalized["candidate_readiness"] = {}
    return normalized, ""


__all__ = [
    "extract_json_payload",
    "iter_json_object_candidates",
    "load_json_with_repairs",
    "looks_like_json_object",
    "parse_audit_json",
    "parse_candidate_model_json",
    "parse_dual_pass_review_json",
    "parse_model_json",
    "repair_json_like_payload",
]
