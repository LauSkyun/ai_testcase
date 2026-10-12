from __future__ import annotations

from rad_review.reporting.ingest import parse_audit_json, parse_model_json
from rad_review.reporting.modes import build_report_diff_payload, merge_audit_report, merge_secondary_review_report
from rad_review.reporting.normalize import (
    fallback_report,
    normalize_compare_text,
    normalize_report,
    normalize_unmatched_finding,
    repair_missing_issue_ids,
)
from rad_review.reporting.render import render_markdown, write_report_diff_files, write_report_files
from rad_review.reporting.stabilize import are_duplicate_findings, stabilize_report

__all__ = [
    "are_duplicate_findings",
    "build_report_diff_payload",
    "fallback_report",
    "merge_audit_report",
    "merge_secondary_review_report",
    "normalize_compare_text",
    "normalize_report",
    "normalize_unmatched_finding",
    "repair_missing_issue_ids",
    "parse_audit_json",
    "parse_model_json",
    "render_markdown",
    "stabilize_report",
    "write_report_diff_files",
    "write_report_files",
]
