from __future__ import annotations

from typing import Any

from rad_review.docx_reader import ParsedDocument

from .base import sort_findings, sort_public_findings
from .duplicates import (
    add_report_entry,
    are_duplicate_findings,
    build_stable_cross_issues,
    collect_all_findings,
    collect_distinct_root_findings,
    collect_report_entries,
    compare_ngram_set,
    entry_sort_key,
    evidence_overlap,
    evidence_reference_tokens,
    findings_share_semantic_signature,
    group_entry_rank,
    merge_duplicate_findings,
    overlap_ratio,
    preferred_group_target,
    remove_report_entry,
    same_controlled_root_cause_cluster,
    shared_evidence_tokens,
    structured_signal_tokens,
)
from .pipeline import (
    dedupe_report_sections,
    findings_for_dimension,
    is_valid_finding,
    merge_canonical_finding,
    prepare_finding,
    stabilize_report as _stabilize_report,
)
from .rules import (
    finding_context_text,
    finding_signal_text,
    finding_title_text,
    finding_topic_text,
    identify_issue_id_from_text,
    is_formula_odds_conflict_cluster,
    titles_indicate_same_fake_odds_gap,
    titles_indicate_same_formula_conflict,
)
from .schema import assert_report_integrity
from .scoring import (
    blocker_priority,
    build_top_blockers,
    find_preferred_blocker_match,
    is_blocking_high,
    is_fatal_core_conflict,
    reorder_top_blockers_by_preference,
    stable_score,
    top_blocker_candidate_findings,
    top_blocker_from_finding,
)


def stabilize_report(report: dict[str, Any], documents: list[ParsedDocument]) -> dict[str, Any]:
    stabilized = _stabilize_report(report, documents)
    assert_report_integrity(stabilized)
    return stabilized


__all__ = [
    "add_report_entry",
    "are_duplicate_findings",
    "blocker_priority",
    "build_stable_cross_issues",
    "build_top_blockers",
    "collect_all_findings",
    "collect_distinct_root_findings",
    "collect_report_entries",
    "compare_ngram_set",
    "dedupe_report_sections",
    "entry_sort_key",
    "evidence_overlap",
    "evidence_reference_tokens",
    "find_preferred_blocker_match",
    "finding_context_text",
    "finding_signal_text",
    "finding_title_text",
    "finding_topic_text",
    "findings_for_dimension",
    "findings_share_semantic_signature",
    "group_entry_rank",
    "identify_issue_id_from_text",
    "is_blocking_high",
    "is_fatal_core_conflict",
    "is_formula_odds_conflict_cluster",
    "is_valid_finding",
    "merge_canonical_finding",
    "merge_duplicate_findings",
    "overlap_ratio",
    "prepare_finding",
    "preferred_group_target",
    "remove_report_entry",
    "reorder_top_blockers_by_preference",
    "same_controlled_root_cause_cluster",
    "shared_evidence_tokens",
    "sort_findings",
    "sort_public_findings",
    "stable_score",
    "stabilize_report",
    "structured_signal_tokens",
    "titles_indicate_same_fake_odds_gap",
    "titles_indicate_same_formula_conflict",
    "top_blocker_candidate_findings",
    "top_blocker_from_finding",
]
