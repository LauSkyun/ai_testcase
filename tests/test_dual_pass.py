from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rad_review.agent import ReviewAgent
from rad_review.docx_reader import ParagraphBlock, ParsedDocument
from rad_review.model_client import ModelConfig, OpenAICompatibleClient
from rad_review.run_logger import RunLogger
from rad_review.prompts import (
    BASELINE_REVIEW_PRINCIPLES,
    DIMENSIONS,
    FACT_FIRST_PROTOCOL,
    OUTPUT_QUALITY_BAR,
    REVIEW_RULES,
    ROOT_CAUSE_PROMPT_RULES,
    SCORE_RUBRIC,
    SPECIAL_CHECKLIST,
    STABILITY_PROTOCOL,
    build_dual_pass_secondary_messages,
    build_phase2_control_evidence_packet,
    build_primary_review_messages,
    build_shared_review_input,
)
from rad_review.reporting.ingest import parse_candidate_model_json, parse_dual_pass_review_json
from rad_review.reporting.modes import (
    build_conservative_dual_pass_candidate_report,
    build_deterministic_phase2_candidate,
    build_dual_pass_secondary_finding,
    demote_dual_pass_cross_document_issues,
    evaluate_dual_pass_added_admission,
    evaluate_dual_pass_candidate_selection,
    evaluate_phase2_protocol_gate,
    evaluate_phase2_coverage_ledger,
    lock_dual_pass_candidate_score_to_primary,
    lock_dual_pass_candidate_top_blockers_to_primary,
    merge_dual_pass_review_report,
    normalize_dual_pass_advice_payload,
    phase2_findings_are_duplicate,
    sanitize_dual_pass_phase2_candidate_review,
)
from rad_review.reporting.render import (
    render_dual_pass_advice_markdown,
    render_dual_pass_index_markdown,
    write_report_files,
)
from review import build_parser, probe_text_model


def make_doc(name: str = "稳定性需求文档.docx", kind: str = "requirement") -> ParsedDocument:
    return ParsedDocument(
        path=name,
        name=name,
        kind=kind,
        paragraphs=[ParagraphBlock(index=1, text="点击开始后扣费，结算时派奖。")],
        tables=[],
        images=[],
        errors=[],
    )


def empty_report(score: str = "B") -> dict:
    return {
        "overall_evaluation": "主流程可理解，但仍需补充边界。",
        "document_quality_score": score,
        "score_reason": "主流程基本可落地。",
        "dimensions": [{"name": dimension, "dimension_note": "", "findings": []} for dimension in DIMENSIONS],
        "cross_document_issues": [],
        "missing_information": [],
        "test_points": {
            "功能验证": [],
            "异常操作": [],
            "兼容性": [],
            "安全专项": [],
            "回归影响": [],
            "性能与稳定性": [],
            "用户体验": [],
        },
        "quality_notes": [],
        "image_analysis_gaps": [],
        "top_blockers": [],
    }


def finding(
    issue_id: str,
    title: str,
    dimension: str | None = None,
    severity: str = "high",
    blocking: str = "block_dev",
) -> dict:
    return {
        "issue_id": issue_id,
        "title": title,
        "canonical_title": title,
        "primary_dimension": dimension or DIMENSIONS[0],
        "current_state": "state",
        "evidence": "doc / p1",
        "risk": "risk",
        "suggestion": "suggestion",
        "severity": severity,
        "confidence": "high",
        "blocking": blocking,
    }


def phase2_coverage_ledger(
    confirmed: dict[str, list[str]] | None = None,
    covered: dict[str, list[str]] | None = None,
) -> list[dict]:
    confirmed = confirmed or {}
    covered = covered or {}
    keys = (
        "settlement_formula_ui_config",
        "trigger_state_termination",
        "funds_deduction_payout",
        "max_payout_economic_boundary",
        "statistics_time_window",
    )
    result = []
    for key in keys:
        candidate_ids = confirmed.get(key, [])
        primary_ids = covered.get(key, [])
        status = "confirmed_add" if candidate_ids else "covered_by_primary" if primary_ids else "no_issue"
        result.append(
            {
                "audit_key": key,
                "status": status,
                "primary_issue_ids": primary_ids,
                "candidate_issue_ids": candidate_ids,
                "evidence_checked": ["玩法需求.docx / 段落10"],
                "reason": "已按固定方向完成核对。",
            }
        )
    return result


def phase2_v2_coverage_ledger(
    confirmed: dict[str, list[str]] | None = None,
    covered: dict[str, list[str]] | None = None,
) -> list[dict]:
    confirmed = confirmed or {}
    covered = covered or {}
    controls = {
        "settlement_formula_ui_config": ("settlement_formula", "ui_config_mapping"),
        "trigger_state_termination": ("trigger_entry", "termination_priority"),
        "funds_deduction_payout": ("debit_timing", "payout_timing", "funds_failure_compensation"),
        "max_payout_economic_boundary": (
            "relative_payout_cap",
            "pool_negative_floor",
            "single_round_payout_cap",
        ),
        "statistics_time_window": ("same_metric_window", "ui_text_window_alignment"),
    }
    result = []
    for audit_key, control_keys in controls.items():
        control_items = []
        for control_key in control_keys:
            candidate_ids = confirmed.get(control_key, [])
            primary_ids = covered.get(control_key, [])
            status = "confirmed_add" if candidate_ids else "covered_by_primary" if primary_ids else "no_issue"
            primary_coverage = "same_control" if primary_ids else "not_covered"
            control_items.append(
                {
                    "control_key": control_key,
                    "status": status,
                    "primary_issue_ids": primary_ids,
                    "candidate_issue_ids": candidate_ids,
                    "evidence_checked": ["玩法需求.docx / 段落10"],
                    "reason": (
                        f"source_state=explicit; counterevidence=无; "
                        f"primary_coverage={primary_coverage}; final={status}"
                    ),
                }
            )
        result.append({"audit_key": audit_key, "controls": control_items})
    return result


class DualPassTests(unittest.TestCase):
    def test_phase2_candidate_is_deterministically_built_from_pipeline_delta(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [finding("PRIMARY_1", "主报告问题")]
        pipeline = json.loads(json.dumps(primary, ensure_ascii=False))
        pipeline["dimensions"][0]["findings"].append(finding("ADD_1", "副评审准入新增"))
        secondary = {
            "quality_assessment": {"summary": "仅评价Primary", "ready_for_direct_output": False},
            "missed_findings": [{"candidate_issue_id": "ADD_1"}],
            "candidate_report": {"overall_evaluation": "模型自由重写内容不得使用"},
            "candidate_lineage": {"kept": [], "added": [], "merged": [], "dropped": []},
            "review_notes": [],
        }

        candidate, normalized_review = build_deterministic_phase2_candidate(
            primary,
            pipeline,
            secondary,
        )

        self.assertEqual(candidate, pipeline)
        self.assertEqual(
            normalized_review["candidate_generation_mode"],
            "deterministic_primary_plus_admitted_delta",
        )
        advice = normalize_dual_pass_advice_payload(primary, candidate, normalized_review)
        self.assertEqual(
            advice["candidate_generation_mode"],
            "deterministic_primary_plus_admitted_delta",
        )
        self.assertEqual(normalized_review["candidate_report"], {})
        self.assertTrue(normalized_review["quality_assessment"]["ready_for_direct_output"])
        self.assertEqual(
            normalized_review["candidate_lineage"]["kept"][0]["candidate_issue_id"],
            "PRIMARY_1",
        )
        self.assertEqual(
            normalized_review["candidate_lineage"]["added"][0]["candidate_issue_id"],
            "ADD_1",
        )

    def test_phase2_v22_protocol_gate_rejects_model_candidate_fields_and_bad_echo(self) -> None:
        review = {
            "review_notes": ["protocol_profile=phase2_v2_2; evidence_packet_id=wrong"],
            "candidate_report": {},
            "candidate_lineage": {},
        }
        gate = evaluate_phase2_protocol_gate(review, "phase2_v2_2", "a" * 64)

        self.assertFalse(gate["passed"])
        self.assertFalse(gate["echo_matched"])
        self.assertFalse(gate["delta_only_compliant"])
        self.assertEqual(gate["forbidden_fields_present"], ["candidate_report", "candidate_lineage"])

        exact_echo = f"protocol_profile=phase2_v2_2; evidence_packet_id={'a' * 64}"
        not_last = evaluate_phase2_protocol_gate(
            {"review_notes": [exact_echo, "尾部多余备注"]},
            "phase2_v2_2",
            "a" * 64,
        )
        self.assertFalse(not_last["echo_matched"])
        passed = evaluate_phase2_protocol_gate(
            {"review_notes": ["审查完成", exact_echo]},
            "phase2_v2_2",
            "a" * 64,
        )
        self.assertTrue(passed["passed"])

    def test_phase2_v22_ledger_requires_four_step_decision_trace(self) -> None:
        review = {
            "coverage_schema_version": 2,
            "coverage_ledger": phase2_v2_coverage_ledger(),
            "missed_findings": [],
        }
        review["coverage_ledger"][0]["controls"][0]["reason"] = "仅给出普通结论"

        result = evaluate_phase2_coverage_ledger(
            review,
            protocol_revision="phase2_v2_2",
        )

        self.assertFalse(result["passed"])
        self.assertIn(
            "coverage_control_invalid:settlement_formula_ui_config:settlement_formula:decision_trace_incomplete",
            result["errors"],
        )

    def test_phase2_v22_repairs_same_control_status_and_accepts_explanatory_suffixes(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [
            finding("PRIMARY_FORMULA", "结算公式存在加法与乘法冲突")
        ]
        ledger = phase2_v2_coverage_ledger()
        control = ledger[0]["controls"][0]
        control.update(
            {
                "status": "no_issue",
                "primary_issue_ids": ["PRIMARY_FORMULA"],
                "reason": (
                    "source_state=conflict(加法与乘法歧义); counterevidence=无; "
                    "primary_coverage=same_control(PRIMARY_FORMULA); final=no_issue。Primary 已覆盖。"
                ),
            }
        )
        review = {
            "coverage_schema_version": 2,
            "coverage_ledger": ledger,
            "missed_findings": [],
        }

        result = evaluate_phase2_coverage_ledger(
            review,
            primary_report=primary,
            protocol_revision="phase2_v2_2",
        )

        self.assertTrue(result["passed"])
        normalized = result["entries"][0]["controls"][0]
        self.assertEqual(normalized["status"], "covered_by_primary")
        self.assertIn("final=covered_by_primary", normalized["reason"])
        self.assertIn(
            "normalized_same_control_status:settlement_formula_ui_config:settlement_formula:"
            "no_issue->covered_by_primary",
            result["protocol_repairs"],
        )

    def test_phase2_v22_clears_invalid_primary_reference_only_for_nonmaterializing_control(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [
            finding("PRIMARY_FUNDS", "提现与结算幂等边界缺失")
        ]
        ledger = phase2_v2_coverage_ledger()
        control = ledger[1]["controls"][0]
        control.update(
            {
                "status": "no_issue",
                "primary_issue_ids": ["PRIMARY_FUNDS"],
                "reason": (
                    "source_state=partial; counterevidence=无; "
                    "primary_coverage=same_control; final=no_issue"
                ),
            }
        )
        review = {
            "coverage_schema_version": 2,
            "coverage_ledger": ledger,
            "missed_findings": [],
        }

        result = evaluate_phase2_coverage_ledger(
            review,
            primary_report=primary,
            protocol_revision="phase2_v2_2",
        )

        self.assertTrue(result["passed"])
        normalized = result["entries"][1]["controls"][0]
        self.assertEqual(normalized["status"], "no_issue")
        self.assertEqual(normalized["primary_issue_ids"], [])
        self.assertIn("primary_coverage=not_covered", normalized["reason"])
        self.assertIn(
            "cleared_invalid_nonmaterializing_primary_reference:"
            "trigger_state_termination:trigger_entry:PRIMARY_FUNDS",
            result["protocol_repairs"],
        )

    def test_phase2_v22_repairs_invalid_covered_reference_without_changing_additions(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [
            finding("PRIMARY_UNRELATED", "开奖快照时机未定义")
        ]
        ledger = phase2_v2_coverage_ledger()
        control = ledger[3]["controls"][2]
        control.update(
            {
                "status": "covered_by_primary",
                "primary_issue_ids": ["PRIMARY_UNRELATED"],
                "reason": (
                    "source_state=explicit; counterevidence=无; "
                    "primary_coverage=same_control; final=covered_by_primary"
                ),
            }
        )
        review = {"coverage_schema_version": 2, "coverage_ledger": ledger, "missed_findings": []}

        result = evaluate_phase2_coverage_ledger(
            review,
            primary_report=primary,
            protocol_revision="phase2_v2_2",
        )

        self.assertTrue(result["passed"])
        normalized = result["entries"][3]["controls"][2]
        self.assertEqual(normalized["status"], "no_issue")
        self.assertEqual(normalized["primary_issue_ids"], [])
        self.assertIn("primary_coverage=not_covered", normalized["reason"])
        self.assertIn("final=no_issue", normalized["reason"])
        self.assertIn(
            "normalized_invalid_covered_status:max_payout_economic_boundary:"
            "single_round_payout_cap:covered_by_primary->no_issue",
            result["protocol_repairs"],
        )

    def test_phase2_v22_filters_only_invalid_primary_reference_from_covered_control(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [
            finding("PRIMARY_CAP", "最高赔付失控，需要校验单局经济边界"),
            finding("PRIMARY_UNRELATED", "开奖快照时机未定义"),
        ]
        ledger = phase2_v2_coverage_ledger()
        control = ledger[3]["controls"][2]
        control.update(
            {
                "status": "covered_by_primary",
                "primary_issue_ids": ["PRIMARY_CAP", "PRIMARY_UNRELATED"],
                "reason": (
                    "source_state=explicit; counterevidence=无; "
                    "primary_coverage=same_control; final=covered_by_primary"
                ),
            }
        )
        review = {"coverage_schema_version": 2, "coverage_ledger": ledger, "missed_findings": []}

        result = evaluate_phase2_coverage_ledger(
            review,
            primary_report=primary,
            protocol_revision="phase2_v2_2",
        )

        self.assertTrue(result["passed"])
        normalized = result["entries"][3]["controls"][2]
        self.assertEqual(normalized["status"], "covered_by_primary")
        self.assertEqual(normalized["primary_issue_ids"], ["PRIMARY_CAP"])
        self.assertIn(
            "cleared_invalid_nonmaterializing_primary_reference:max_payout_economic_boundary:"
            "single_round_payout_cap:PRIMARY_UNRELATED",
            result["protocol_repairs"],
        )

    def test_phase2_v22_normalizes_not_applicable_decision_enums(self) -> None:
        ledger = phase2_v2_coverage_ledger()
        control = ledger[3]["controls"][1]
        control.update(
            {
                "status": "not_applicable",
                "reason": (
                    "source_state=not_applicable; counterevidence=无; "
                    "primary_coverage=not_applicable; final=not_applicable"
                ),
            }
        )
        review = {"coverage_schema_version": 2, "coverage_ledger": ledger, "missed_findings": []}

        result = evaluate_phase2_coverage_ledger(review, protocol_revision="phase2_v2_2")

        self.assertTrue(result["passed"])
        normalized = result["entries"][3]["controls"][1]
        self.assertIn("source_state=missing", normalized["reason"])
        self.assertIn("primary_coverage=not_covered", normalized["reason"])
        self.assertIn(
            "normalized_not_applicable_source_state:max_payout_economic_boundary:"
            "pool_negative_floor:not_applicable->missing",
            result["protocol_repairs"],
        )

    def test_phase2_added_admission_requires_complete_locatable_independent_evidence(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [finding("PRIMARY_1", "下注档位缺失")]
        shared_input = {
            "document_labels": ["玩法需求.docx (requirement)"],
            "document_context": "[玩法需求.docx][段落10] 奖池收益率以累计收入为分母。",
        }
        added = {
            "candidate_issue_id": "ADDED_1",
            "audit_key": "settlement_formula_ui_config",
            "control_key": "settlement_formula",
            "title": "奖池收益率公式缺少除零边界",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "累计收入为0时公式分母为0，文档未定义处理规则。",
            "evidence": "玩法需求.docx / 段落10",
            "risk": "服务端计算可能失败，奖池状态无法判定。",
            "suggestion": "数值策划定义累计收入为0时的状态和返回值，并补充验收示例。",
            "severity": "中",
            "blocking": "阻塞测试用例设计",
            "confidence": "高",
            "independent_root_cause": "奖池收益率公式的分母零值边界未定义。",
            "primary_overlap_check": {
                "nearest_primary_issue_id": "PRIMARY_1",
                "overlap": False,
                "reason": "Primary 仅讨论下注档位，不涉及奖池计算。",
            },
            "severity_basis": "未定义零值行为会导致公式不可执行，无法设计边界测试。",
            "root_cause_count": 1,
            "root_causes": ["奖池收益率公式的分母零值边界未定义。"],
            "fact_check": {
                "claim_type": "boundary_gap",
                "source_rule_presence_checked": True,
                "compatible_interpretation_checked": True,
                "compatible_interpretation_exists": False,
                "conclusion": "confirmed",
                "reason": "段落10给出公式口径，但没有累计收入为0时的计算规则。",
            },
        }

        admitted = evaluate_dual_pass_added_admission(added, primary, shared_input)
        self.assertEqual(admitted["status"], "admitted")
        self.assertEqual(admitted["reasons"], [])

        secondary_review = {
            "coverage_schema_version": 2,
            "coverage_ledger": phase2_v2_coverage_ledger(
                {"settlement_formula": ["ADDED_1"]}
            ),
            "missed_findings": [added],
            "unsupported_findings": [],
            "merge_recommendations": [],
            "review_notes": [],
            "candidate_lineage": {"kept": [], "added": [], "merged": [], "dropped": []},
            "candidate_report": empty_report("C"),
        }
        pipeline, summary = merge_dual_pass_review_report(
            primary,
            secondary_review,
            [make_doc("玩法需求.docx")],
            "qwen",
            shared_input=shared_input,
            enforce_phase2_admission=True,
        )
        self.assertEqual(summary["added_findings"], 1)
        self.assertTrue(summary["phase2_admission"]["coverage_ledger"]["passed"])
        self.assertEqual(summary["phase2_admission"]["admitted_count"], 1)
        self.assertEqual(sum(len(item.get("findings") or []) for item in pipeline["dimensions"]), 2)

        protocol_gate = evaluate_phase2_protocol_gate(
            secondary_review,
            "phase2_v2_2",
            "a" * 64,
        )
        blocked_pipeline, blocked_summary = merge_dual_pass_review_report(
            primary,
            secondary_review,
            [make_doc("玩法需求.docx")],
            "qwen",
            shared_input=shared_input,
            enforce_phase2_admission=True,
            phase2_protocol_gate=protocol_gate,
        )
        self.assertEqual(blocked_summary["added_findings"], 0)
        self.assertFalse(blocked_summary["phase2_admission"]["protocol_gate"]["passed"])
        self.assertFalse(blocked_summary["phase2_admission"]["coverage_ledger"]["passed"])
        self.assertEqual(
            sum(len(item.get("findings") or []) for item in blocked_pipeline["dimensions"]),
            1,
        )

        missing = dict(added)
        missing["evidence"] = ""
        rejected = evaluate_dual_pass_added_admission(missing, primary, shared_input)
        self.assertEqual(rejected["status"], "rejected")
        self.assertTrue(any(reason.startswith("missing_fields") for reason in rejected["reasons"]))

    def test_phase2_added_admission_rejects_primary_duplicate_and_explicit_rule_claimed_missing(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [finding("PRIMARY_1", "RESPIN优先级规则缺失")]
        shared_input = {"document_labels": ["玩法需求.docx (requirement)"]}
        added = {
            "candidate_issue_id": "ADDED_1",
            "audit_key": "trigger_state_termination",
            "title": "RESPIN优先级规则缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "原文明确规定RESPIN严格优先，但仍未说明优先级。",
            "evidence": "玩法需求.docx / 段落37",
            "risk": "实现分支不一致。",
            "suggestion": "补充优先级。",
            "severity": "中",
            "blocking": "建议优化",
            "confidence": "高",
            "independent_root_cause": "优先级未定义。",
            "primary_overlap_check": {
                "nearest_primary_issue_id": "PRIMARY_1",
                "overlap": False,
                "reason": "声称不同。",
            },
            "severity_basis": "",
            "root_cause_count": 1,
            "root_causes": ["优先级未定义。"],
            "fact_check": {
                "claim_type": "missing_rule",
                "source_rule_presence_checked": True,
                "compatible_interpretation_checked": True,
                "compatible_interpretation_exists": False,
                "conclusion": "confirmed",
                "reason": "声称规则缺失。",
                "searched_locations": ["玩法需求.docx / 段落37"],
            },
        }

        rejected = evaluate_dual_pass_added_admission(added, primary, shared_input)
        self.assertEqual(rejected["status"], "rejected")
        self.assertIn("source_rule_already_explicit", rejected["reasons"])
        self.assertTrue(any(reason.startswith("primary_duplicate") for reason in rejected["reasons"]))

        negated = dict(added)
        negated.update(
            {
                "candidate_issue_id": "PAYOUT_TIMING_MISSING",
                "audit_key": "funds_deduction_payout",
                "control_key": "payout_timing",
                "title": "派奖到账时机未明确",
                "current_state": "文档未明确说明中奖金额何时计入玩家钱包。",
                "evidence": "玩法需求.docx / 全文",
                "independent_root_cause": "派奖到账时机未定义。",
                "root_causes": ["派奖到账时机未定义。"],
                "primary_overlap_check": {
                    "nearest_primary_issue_id": "PRIMARY_1",
                    "overlap": False,
                    "reason": "Primary仅讨论RESPIN优先级，未覆盖派奖到账。",
                },
                "fact_check": {
                    "claim_type": "missing_rule",
                    "source_rule_presence_checked": True,
                    "compatible_interpretation_checked": True,
                    "compatible_interpretation_exists": False,
                    "conclusion": "confirmed",
                    "reason": "全文未找到派奖到账节点。",
                    "searched_locations": ["玩法需求.docx / 全文"],
                },
            }
        )
        admitted = evaluate_dual_pass_added_admission(negated, primary, shared_input)
        self.assertEqual(admitted["status"], "admitted")
        self.assertNotIn("source_rule_already_explicit", admitted["reasons"])
        self.assertNotIn("evidence_position_unlocatable", admitted["reasons"])

    def test_phase2_added_admission_rejects_unconfirmed_or_compatible_conflict(self) -> None:
        primary = empty_report("C")
        shared_input = {"document_labels": ["玩法需求.docx (requirement)"]}
        added = {
            "candidate_issue_id": "STATE_END_CONFLICT",
            "audit_key": "trigger_state_termination",
            "title": "结束条件冲突",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "段落10写随机为空提前结束，段落20写达到上限后强制为空。",
            "evidence": "玩法需求.docx / 段落10、20",
            "risk": "实现口径可能分歧。",
            "suggestion": "明确提前结束和最大次数兜底的优先级。",
            "severity": "中",
            "blocking": "阻塞测试用例设计",
            "confidence": "高",
            "independent_root_cause": "状态机结束条件说明不清。",
            "root_causes": ["状态机结束条件说明不清。"],
            "root_cause_count": 1,
            "primary_overlap_check": {
                "nearest_primary_issue_id": "PRIMARY_1",
                "overlap": False,
                "reason": "Primary 未讨论结束条件。",
            },
            "severity_basis": "需要确定终止测试路径。",
            "fact_check": {
                "claim_type": "direct_conflict",
                "source_rule_presence_checked": True,
                "compatible_interpretation_checked": True,
                "compatible_interpretation_exists": True,
                "conclusion": "confirmed",
                "reason": "可以解释为提前结束加最大次数兜底。",
            },
        }

        rejected = evaluate_dual_pass_added_admission(added, primary, shared_input)

        self.assertEqual(rejected["status"], "rejected")
        self.assertIn("direct_conflict_has_compatible_interpretation", rejected["reasons"])

    def test_phase2_candidate_sanitizer_removes_rejected_addition(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [finding("PRIMARY_1", "主问题")]
        candidate = empty_report("C")
        candidate["dimensions"][0]["findings"] = [
            finding("PRIMARY_1", "主问题"),
            finding("ADD_OK", "有效补漏"),
            finding("ADD_BAD", "证据不足补漏"),
        ]
        secondary = {
            "missed_findings": [
                {"candidate_issue_id": "ADD_OK", "title": "有效补漏"},
                {"candidate_issue_id": "ADD_BAD", "title": "证据不足补漏"},
            ],
            "candidate_lineage": {
                "kept": [{"candidate_issue_id": "PRIMARY_1", "primary_issue_ids": ["PRIMARY_1"]}],
                "added": [
                    {"candidate_issue_id": "ADD_OK", "source_missed_issue_ids": ["ADD_OK"]},
                    {"candidate_issue_id": "ADD_BAD", "source_missed_issue_ids": ["ADD_BAD"]},
                ],
                "merged": [],
                "dropped": [],
            },
            "candidate_report": candidate,
            "review_notes": [],
        }
        admission = {
            "results": [
                {"candidate_issue_id": "ADD_OK", "status": "admitted"},
                {"candidate_issue_id": "ADD_BAD", "status": "rejected"},
            ]
        }

        sanitized = sanitize_dual_pass_phase2_candidate_review(primary, secondary, admission)

        self.assertEqual([item["candidate_issue_id"] for item in sanitized["missed_findings"]], ["ADD_OK"])
        candidate_ids = {
            item["issue_id"]
            for dimension in sanitized["candidate_report"]["dimensions"]
            for item in dimension.get("findings") or []
        }
        self.assertEqual(candidate_ids, {"PRIMARY_1", "ADD_OK"})
        self.assertEqual(
            [item["candidate_issue_id"] for item in sanitized["candidate_lineage"]["added"]],
            ["ADD_OK"],
        )

    def test_phase2_coverage_ledger_rejects_order_and_bidirectional_mapping_drift(self) -> None:
        ledger = phase2_coverage_ledger({"trigger_state_termination": ["ADD_A", "ORPHAN"]})
        ledger[0], ledger[1] = ledger[1], ledger[0]
        review = {
            "coverage_ledger": ledger,
            "missed_findings": [
                {
                    "candidate_issue_id": "ADD_A",
                    "audit_key": "settlement_formula_ui_config",
                },
                {
                    "candidate_issue_id": "UNMAPPED",
                    "audit_key": "funds_deduction_payout",
                },
            ],
        }

        evaluation = evaluate_phase2_coverage_ledger(review)

        self.assertFalse(evaluation["passed"])
        self.assertIn("coverage_audit_key_order_invalid", evaluation["errors"])
        self.assertIn("missed_finding_audit_key_mismatch:ADD_A", evaluation["errors"])
        self.assertIn("missed_finding_not_in_confirmed_add:UNMAPPED", evaluation["errors"])
        self.assertIn("confirmed_add_without_missed_finding:ORPHAN", evaluation["errors"])

    def test_phase2_coverage_ledger_requires_all_five_entries_and_array_fields(self) -> None:
        ledger = phase2_coverage_ledger()
        ledger.pop()
        ledger[0]["candidate_issue_ids"] = "ADD_A"
        review = {"coverage_ledger": ledger, "missed_findings": []}

        evaluation = evaluate_phase2_coverage_ledger(review)

        self.assertFalse(evaluation["passed"])
        self.assertEqual(evaluation["completeness"], 0.8)
        self.assertTrue(any(error.startswith("coverage_entry_count_invalid") for error in evaluation["errors"]))
        self.assertTrue(any("candidate_issue_ids_not_array" in error for error in evaluation["errors"]))

    def test_phase2_coverage_ledger_repairs_safe_protocol_drift(self) -> None:
        ledger = phase2_coverage_ledger(covered={"settlement_formula_ui_config": ["PRIMARY_1"]})
        ledger[0]["candidate_issue_ids"] = ["PRIMARY_1"]
        ledger[-1]["status"] = "not_applicable"
        ledger[-1]["evidence_checked"] = []
        review = {"coverage_ledger": ledger, "missed_findings": []}
        shared = {"document_labels": ["玩法需求.docx (requirement)", "玩法数值.docx (numeric)"]}

        evaluation = evaluate_phase2_coverage_ledger(review, shared)

        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["entries"][0]["candidate_issue_ids"], [])
        self.assertEqual(
            evaluation["entries"][-1]["evidence_checked"],
            ["玩法需求.docx / 全文", "玩法数值.docx / 全文"],
        )
        self.assertEqual(len(evaluation["protocol_repairs"]), 2)

    def test_phase2_v2_coverage_ledger_maps_finding_to_unique_control(self) -> None:
        review = {
            "coverage_schema_version": 2,
            "coverage_ledger": phase2_v2_coverage_ledger(
                confirmed={"debit_timing": ["FUNDS_DEBIT_TIMING"]}
            ),
            "missed_findings": [
                {
                    "candidate_issue_id": "FUNDS_DEBIT_TIMING",
                    "audit_key": "funds_deduction_payout",
                    "control_key": "debit_timing",
                }
            ],
        }

        evaluation = evaluate_phase2_coverage_ledger(review)

        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["schema_version"], 2)
        self.assertEqual(evaluation["completeness"], 1.0)
        self.assertEqual(
            evaluation["candidate_to_control_key"]["FUNDS_DEBIT_TIMING"],
            "debit_timing",
        )
        self.assertEqual(evaluation["confirmed_control_keys"], ["debit_timing"])

    def test_phase2_v2_schema_is_safely_inferred_from_complete_control_shape(self) -> None:
        review = {
            "coverage_ledger": phase2_v2_coverage_ledger(),
            "missed_findings": [],
        }

        evaluation = evaluate_phase2_coverage_ledger(
            review,
            required_schema_version=2,
        )

        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["schema_version"], 2)
        self.assertTrue(evaluation["schema_version_inferred"])
        self.assertIn(
            "inferred_coverage_schema_version:2_from_complete_control_shape",
            evaluation["protocol_repairs"],
        )

    def test_phase2_v2_rejects_primary_mapping_from_different_control_surface(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [
            finding("DATA_ISOLATION", "假数据不得参与真实排行榜与奖池统计")
        ]
        review = {
            "coverage_schema_version": 2,
            "coverage_ledger": phase2_v2_coverage_ledger(
                covered={"debit_timing": ["DATA_ISOLATION"]}
            ),
            "missed_findings": [],
        }

        evaluation = evaluate_phase2_coverage_ledger(review, None, primary)

        self.assertFalse(evaluation["passed"])
        self.assertTrue(any("primary_control_mismatch:DATA_ISOLATION" in error for error in evaluation["errors"]))

    def test_phase2_v2_rejects_wrong_or_missing_control_link(self) -> None:
        review = {
            "coverage_schema_version": 2,
            "coverage_ledger": phase2_v2_coverage_ledger(
                confirmed={"debit_timing": ["FUNDS_DEBIT_TIMING"]}
            ),
            "missed_findings": [
                {
                    "candidate_issue_id": "FUNDS_DEBIT_TIMING",
                    "audit_key": "funds_deduction_payout",
                    "control_key": "payout_timing",
                }
            ],
        }

        evaluation = evaluate_phase2_coverage_ledger(review)

        self.assertFalse(evaluation["passed"])
        self.assertIn("missed_finding_control_mismatch:FUNDS_DEBIT_TIMING", evaluation["errors"])

    def test_phase2_admission_rejects_observed_false_positive_patterns(self) -> None:
        primary = empty_report("C")
        shared = {"document_labels": ["玩法需求.docx (requirement)"]}

        def base_added(issue_id: str, audit_key: str, title: str, state: str) -> dict:
            return {
                "candidate_issue_id": issue_id,
                "audit_key": audit_key,
                "title": title,
                "primary_dimension": DIMENSIONS[1],
                "current_state": state,
                "evidence": "玩法需求.docx / 段落10",
                "risk": "会导致结算或验收口径不明确。",
                "suggestion": "补充独立规则并分别验收。",
                "severity": "高",
                "blocking": "阻塞开发",
                "confidence": "高",
                "independent_root_cause": title,
                "root_causes": [title],
                "root_cause_count": 1,
                "primary_overlap_check": {
                    "nearest_primary_issue_id": "PRIMARY_1",
                    "overlap": False,
                    "reason": "Primary未覆盖该规则。",
                },
                "severity_basis": "可能造成结算错误。",
                "fact_check": {
                    "claim_type": "boundary_gap",
                    "source_rule_presence_checked": True,
                    "compatible_interpretation_checked": True,
                    "compatible_interpretation_exists": False,
                    "conclusion": "confirmed",
                    "reason": "已核对原文。",
                    "searched_locations": ["玩法需求.docx / 段落10"],
                },
            }

        funds = base_added(
            "FUNDS_BOTH",
            "funds_deduction_payout",
            "扣款与派奖时机均未明确",
            "未定义本金扣款节点，也未定义派奖到账节点。",
        )
        stats = base_added(
            "STATS_SCOPE",
            "statistics_time_window",
            "胜率与下注金额榜时间窗口不同",
            "胜率使用30天，用户下注金额榜使用今日。",
        )
        stats["fact_check"]["claim_type"] = "value_mismatch"
        stats["fact_check"]["same_subject_and_scope"] = True
        boundary = base_added(
            "BOUNDARY_RELATIVE",
            "max_payout_economic_boundary",
            "未明确最大赔付金额上限",
            "文档仅定义100倍倍率上限，仍缺少绝对赔付金额上限。",
        )

        funds_result = evaluate_dual_pass_added_admission(funds, primary, shared)
        stats_result = evaluate_dual_pass_added_admission(stats, primary, shared)
        boundary_result = evaluate_dual_pass_added_admission(boundary, primary, shared)

        self.assertIn("multiroot_funds_debit_and_payout_combined", funds_result["reasons"])
        self.assertIn("statistics_subject_or_metric_mismatch", stats_result["reasons"])
        self.assertIn("existing_multiplier_boundary_requires_advice_only", boundary_result["reasons"])

        split_cases = [
            base_added(
                "FUNDS_DEBIT_ONLY",
                "funds_deduction_payout",
                "玩家本金扣款节点未定义",
                "下注流程未定义玩家本金实际扣款节点。",
            ),
            base_added(
                "FUNDS_PAYOUT_ONLY",
                "funds_deduction_payout",
                "派奖到账节点未定义",
                "开奖流程未定义奖励实际到账节点。",
            ),
            base_added(
                "FUNDS_FAILURE_COMPENSATION",
                "funds_deduction_payout",
                "扣款与派奖失败补偿机制未定义",
                "文档未定义扣款失败回滚和派奖失败补发机制。",
            ),
            base_added(
                "POOL_NEGATIVE_FLOOR",
                "max_payout_economic_boundary",
                "奖池透支下限未定义",
                "文档允许奖池为负，但未定义负值下限。",
            ),
            base_added(
                "SINGLE_ROUND_CAP",
                "max_payout_economic_boundary",
                "单局赔付金额封顶未定义",
                "文档未定义单局最大赔付金额。",
            ),
        ]
        split_cases[0]["control_key"] = "debit_timing"
        split_cases[1]["control_key"] = "payout_timing"
        split_cases[2]["control_key"] = "funds_failure_compensation"
        split_cases[3]["control_key"] = "pool_negative_floor"
        split_cases[4]["control_key"] = "single_round_payout_cap"

        self.assertTrue(
            all(
                evaluate_dual_pass_added_admission(item, primary, shared)["status"] == "admitted"
                for item in split_cases
            )
        )

        explicit_debit = dict(split_cases[0])
        explicit_debit["current_state"] = "文档写明点击投注按钮后消耗对应的货币进行开奖。"
        self.assertIn(
            "source_rule_already_explicit",
            evaluate_dual_pass_added_admission(explicit_debit, primary, shared)["reasons"],
        )

        explicit_payout = dict(split_cases[1])
        explicit_payout["current_state"] = "结束弹窗消失回到投入阶段时，余额增加对应数值。"
        self.assertIn(
            "source_rule_already_explicit",
            evaluate_dual_pass_added_admission(explicit_payout, primary, shared)["reasons"],
        )

        platform_compensation = dict(split_cases[2])
        platform_compensation["current_state"] = "文档仅写复用中台统一处理流程，未展开具体补偿策略。"
        self.assertIn(
            "existing_platform_process_requires_advice_only",
            evaluate_dual_pass_added_admission(platform_compensation, primary, shared)["reasons"],
        )

        mixed_debit = dict(split_cases[0])
        mixed_debit["independent_root_cause"] = "玩家本金扣款节点与幂等机制均未定义。"
        self.assertIn(
            "control_scope_drift_debit_timing_and_idempotency",
            evaluate_dual_pass_added_admission(mixed_debit, primary, shared)["reasons"],
        )

        mixed_compensation = dict(split_cases[2])
        mixed_compensation["current_state"] = "资金失败补偿缺失，奖池透支回填失败时也没有熔断。"
        self.assertIn(
            "control_scope_drift_funds_failure_and_pool_boundary",
            evaluate_dual_pass_added_admission(mixed_compensation, primary, shared)["reasons"],
        )

        mixed_cap = dict(split_cases[4])
        mixed_cap["independent_root_cause"] = "单局封顶缺失且数值表存在数量级错误。"
        self.assertIn(
            "control_scope_drift_payout_cap_and_formula_error",
            evaluate_dual_pass_added_admission(mixed_cap, primary, shared)["reasons"],
        )

        relative_boundary_cap = dict(split_cases[4])
        relative_boundary_cap["current_state"] = "文档已有100倍倍率上限，但未定义最大赔付金额上限。"
        self.assertIn(
            "existing_multiplier_boundary_requires_advice_only",
            evaluate_dual_pass_added_admission(relative_boundary_cap, primary, shared)["reasons"],
        )

    def test_phase2_duplicate_gate_keeps_distinct_time_window_modules(self) -> None:
        statistics = {"issue_id": "A", "title": "开奖分析模块的时间范围在正文与UI截图中存在冲突"}
        records = {"issue_id": "B", "title": "游戏记录展示范围在正文与UI截图中存在冲突"}

        self.assertFalse(phase2_findings_are_duplicate(statistics, records))

    def test_phase2_duplicate_gate_keeps_distinct_funds_controls(self) -> None:
        debit = {
            "issue_id": "FUNDS_DEBIT",
            "audit_key": "funds_deduction_payout",
            "control_key": "debit_timing",
            "title": "玩家本金扣款时机未明确",
        }
        payout = {
            "issue_id": "FUNDS_PAYOUT",
            "audit_key": "funds_deduction_payout",
            "control_key": "payout_timing",
            "title": "派奖到账时机未明确",
        }
        broad_primary = {"issue_id": "SEC_01", "title": "开奖兜底实时计算的判定时机未定义"}

        self.assertFalse(phase2_findings_are_duplicate(debit, payout))
        self.assertFalse(phase2_findings_are_duplicate(debit, broad_primary))

    def test_phase2_admission_resolves_unique_requirement_document_alias(self) -> None:
        primary = empty_report("C")
        added = {
            "candidate_issue_id": "FREE_SPIN_TRIGGER",
            "audit_key": "trigger_state_termination",
            "title": "免费续杯触发条件与盘面结构冲突",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "1x3盘面不可能出现4个以上符号。",
            "evidence": "需求文档 / 3.5.1 基础设定（段落183）",
            "risk": "触发条件无法实现。",
            "suggestion": "统一为左右匹配时触发。",
            "severity": "高",
            "blocking": "阻塞开发",
            "confidence": "高",
            "independent_root_cause": "续杯触发条件超过盘面容量。",
            "root_causes": ["续杯触发条件超过盘面容量。"],
            "root_cause_count": 1,
            "primary_overlap_check": {"nearest_primary_issue_id": "CROSS_03", "overlap": False, "reason": "不同根因。"},
            "severity_basis": "规则在当前盘面不可执行。",
            "fact_check": {
                "claim_type": "direct_conflict",
                "source_rule_presence_checked": True,
                "compatible_interpretation_checked": True,
                "compatible_interpretation_exists": False,
                "conclusion": "confirmed",
                "reason": "最多只有3个符号位。",
            },
        }
        shared = {
            "document_labels": ["钱来了需求文档.docx (requirement)", "钱来了数值文档.docx (numeric)"]
        }

        result = evaluate_dual_pass_added_admission(added, primary, shared)

        self.assertEqual(result["status"], "admitted")
        self.assertTrue(result["evidence_alias_resolved"])
        self.assertIn("钱来了需求文档.docx", result["normalized_evidence"])

    def test_phase2_top_blocker_lock_preserves_primary_top3(self) -> None:
        primary = empty_report("C")
        primary["top_blockers"] = [
            {"issue_id": f"P{i}", "title": f"Primary {i}", "severity": "高", "owner": "程序", "why_now": "阻塞"}
            for i in range(1, 4)
        ]
        candidate = empty_report("C")
        candidate["dimensions"][0]["findings"] = [
            finding(f"P{i}", f"Primary {i}") for i in range(1, 4)
        ]
        candidate["top_blockers"] = [{"issue_id": "C1", "title": "Candidate", "severity": "高"}]

        locked = lock_dual_pass_candidate_top_blockers_to_primary(primary, candidate)

        self.assertEqual([item["issue_id"] for item in locked["top_blockers"]], ["P1", "P2", "P3"])

    def test_phase2_merge_keeps_rejected_addition_out_of_pipeline(self) -> None:
        primary = empty_report("C")
        rejected_added = {
            "candidate_issue_id": "ADDED_1",
            "title": "通用弱网规则缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "未描述。",
            "evidence": "",
        }
        secondary_review = {
            "missed_findings": [rejected_added],
            "unsupported_findings": [],
            "merge_recommendations": [],
            "review_notes": [],
            "candidate_lineage": {"kept": [], "added": [], "merged": [], "dropped": []},
            "candidate_report": empty_report("A"),
        }

        pipeline, summary = merge_dual_pass_review_report(
            primary,
            secondary_review,
            [make_doc("玩法需求.docx")],
            "qwen",
            shared_input={"document_labels": ["玩法需求.docx (requirement)"]},
            enforce_phase2_admission=True,
        )

        self.assertEqual(summary["added_findings"], 0)
        self.assertEqual(summary["phase2_admission"]["rejected_count"], 1)
        self.assertEqual(sum(len(item.get("findings") or []) for item in pipeline["dimensions"]), 0)
        self.assertTrue(any("phase2 准入拒绝" in note for note in pipeline["quality_notes"]))

    def test_phase2_selection_locks_score_and_blocks_top3_loss(self) -> None:
        primary = empty_report("C")
        primary["score_reason"] = "primary score"
        primary["top_blockers"] = [
            {"issue_id": f"P{index}", "title": f"核心问题{index}", "severity": "高", "owner": "程序", "why_now": "阻塞"}
            for index in range(1, 4)
        ]
        candidate = empty_report("A")
        candidate["score_reason"] = "candidate score"
        candidate["top_blockers"] = [dict(primary["top_blockers"][0])]
        candidate = lock_dual_pass_candidate_score_to_primary(primary, candidate)
        advice = {
            "quality_assessment": {"ready_for_direct_output": True, "suggestion_level": "low"},
            "candidate_readiness": {"ready_for_direct_output": True},
            "normalized_candidate_ready_for_direct_output": True,
            "candidate_structurally_ready": True,
            "traceability_status": "complete",
            "lineage_coverage_complete": True,
        }
        selection = evaluate_dual_pass_candidate_selection(
            primary,
            candidate,
            advice,
            {},
            "",
            phase2_admission={
                "enabled": True,
                "all_passed": True,
                "admitted_count": 0,
                "rejected_count": 0,
                "coverage_ledger": {"passed": True, "completeness": 1.0, "errors": []},
            },
        )

        self.assertEqual(candidate["document_quality_score"], "C")
        self.assertEqual(candidate["score_reason"], "primary score")
        self.assertFalse(selection["primary_top3_retention_gate_passed"])
        self.assertIn("candidate_primary_top3_retention_below_two_thirds", selection["candidate_gate_failure_reasons"])

    def test_phase2_selection_falls_back_when_coverage_ledger_is_invalid(self) -> None:
        primary = empty_report("C")
        candidate = lock_dual_pass_candidate_score_to_primary(primary, empty_report("A"))
        advice = {
            "quality_assessment": {"ready_for_direct_output": True, "suggestion_level": "low"},
            "candidate_readiness": {"ready_for_direct_output": True},
            "normalized_candidate_ready_for_direct_output": True,
            "candidate_structurally_ready": True,
            "traceability_status": "complete",
            "lineage_coverage_complete": True,
        }

        selection = evaluate_dual_pass_candidate_selection(
            primary,
            candidate,
            advice,
            {},
            "",
            phase2_admission={
                "enabled": True,
                "all_passed": False,
                "candidate_inputs_sanitized": True,
                "coverage_ledger": {
                    "passed": False,
                    "completeness": 0.8,
                    "errors": ["coverage_audit_key_order_invalid"],
                },
            },
        )

        self.assertEqual(selection["selected_report_owner"], "pipeline")
        self.assertIn("phase2_coverage_ledger_invalid", selection["candidate_gate_failure_reasons"])
        self.assertFalse(selection["candidate_gate_results"]["phase2_coverage_ledger_passed"])
    def test_cli_accepts_dual_pass_review_mode(self) -> None:
        args = build_parser().parse_args(["--review-mode", "dual_pass"])
        self.assertEqual(args.review_mode, "dual_pass")
        self.assertEqual(args.model_retries, 3)

        custom_args = build_parser().parse_args(["--review-mode", "dual_pass", "--model-retries", "5"])
        self.assertEqual(custom_args.model_retries, 5)

    def test_text_model_retries_transient_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = ReviewAgent(
                input_path=root,
                output_dir=root / "reports",
                analyze_images=False,
                model_retries=3,
            )
            agent.logger = RunLogger(root / "run.log", echo=False)
            client = OpenAICompatibleClient(agent.config, timeout=30)

            with (
                patch.object(
                    client,
                    "chat",
                    side_effect=[
                        RuntimeError("Model API HTTP 502: upstream request failed"),
                        RuntimeError("Model API HTTP 503: temporarily unavailable"),
                        "OK",
                    ],
                ) as mock_chat,
                patch("rad_review.agent.time.sleep") as mock_sleep,
            ):
                response = agent._call_text_model([{"role": "user", "content": "test"}], client=client)

        self.assertEqual(response, "OK")
        self.assertEqual(mock_chat.call_count, 3)
        self.assertEqual([item.args[0] for item in mock_sleep.call_args_list], [2, 4])

    def test_text_model_raises_after_configured_retries_are_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = ReviewAgent(
                input_path=root,
                output_dir=root / "reports",
                analyze_images=False,
                model_retries=3,
            )
            agent.logger = RunLogger(root / "run.log", echo=False)
            client = OpenAICompatibleClient(agent.config, timeout=30)

            with (
                patch.object(
                    client,
                    "chat",
                    side_effect=RuntimeError("Model API HTTP 502: upstream request failed"),
                ) as mock_chat,
                patch("rad_review.agent.time.sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "primary text model failed after 4 attempt.*HTTP 502"):
                    agent._call_text_model([{"role": "user", "content": "test"}], client=client)

        self.assertEqual(mock_chat.call_count, 4)

    def test_probe_text_model_uses_dual_model_environment_in_dual_pass_mode(self) -> None:
        env = {
            "AI_PRIMARY_BASE_URL": "http://primary.test",
            "AI_PRIMARY_API_KEY": "primary-key",
            "AI_PRIMARY_MODEL": "gpt-5.4",
            "AI_PRIMARY_WIRE_API": "responses",
            "AI_SECONDARY_BASE_URL": "http://secondary.test",
            "AI_SECONDARY_API_KEY": "secondary-key",
            "AI_SECONDARY_MODEL": "deepseek-v4-pro",
            "AI_SECONDARY_WIRE_API": "chat_completions",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(OpenAICompatibleClient, "chat", side_effect=["PRIMARY_OK", "SECONDARY_OK"]) as mock_chat:
                result = probe_text_model(timeout=12, review_mode="dual_pass")

        self.assertEqual(result.review_mode, "dual_pass")
        self.assertEqual([check.label for check in result.checks], ["primary", "secondary"])
        self.assertEqual(mock_chat.call_count, 2)

    def test_shared_review_input_is_reused_by_primary_and_secondary_messages(self) -> None:
        docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
        shared_input = build_shared_review_input(docs, max_context_chars=4000)
        primary_messages = build_primary_review_messages(shared_input)
        secondary_messages = build_dual_pass_secondary_messages(shared_input, empty_report())

        self.assertIn("Racing spec.docx", json.dumps(shared_input, ensure_ascii=False))
        self.assertIn("Racing spec.docx", json.dumps(primary_messages, ensure_ascii=False))
        self.assertIn("Racing spec.docx", json.dumps(secondary_messages, ensure_ascii=False))
        self.assertNotEqual(primary_messages, secondary_messages)

    def test_phase2_secondary_prompt_is_delta_reviewer_and_baseline_is_frozen(self) -> None:
        docs = [make_doc("玩法需求.docx")]
        shared_input = build_shared_review_input(docs, max_context_chars=4000)
        primary = empty_report("C")

        baseline = build_dual_pass_secondary_messages(shared_input, primary, protocol_profile="baseline")
        phase2 = build_dual_pass_secondary_messages(shared_input, primary, protocol_profile="phase2")
        baseline_text = json.dumps(baseline, ensure_ascii=False)
        phase2_text = json.dumps(phase2, ensure_ascii=False)
        phase2_content = phase2[1]["content"]

        self.assertNotIn("phase2 结构化补漏与反证协议", baseline_text)
        self.assertNotIn("phase2_v2_1", baseline_text)
        self.assertNotIn("phase2_v2_2", baseline_text)
        self.assertIn("phase2_v2_2 delta-only 协议", phase2_text)
        self.assertIn("评分规则：", baseline_text)
        self.assertIn("必查专项：", baseline_text)
        self.assertNotIn("评分规则：", phase2_text)
        self.assertNotIn("必查专项：", phase2_text)
        self.assertNotIn("优先输出 8-15", phase2_text)
        self.assertNotIn("优先输出8-15", phase2_text)
        self.assertIn("没有问题数量目标", phase2_text)
        self.assertIn("允许零新增", phase2_text)
        self.assertIn("结构化补漏与反证审查者", phase2_text)
        self.assertIn("phase2_v2_2 固定证据卡", phase2_text)
        self.assertIn("evidence_packet_id", phase2_text)
        self.assertIn("source_state=", phase2_text)
        self.assertIn("不生成 candidate_report", phase2_text)
        self.assertNotIn("候选稿生成附加规则", phase2_text)
        self.assertNotIn("dual_pass 候选成稿约束", phase2_text)
        self.assertNotIn("生成一份候选最终报告", phase2_text)
        self.assertIn("Candidate 由系统", phase2_text)
        self.assertIn("primary_overlap_check", phase2_text)
        self.assertIn("fact_check", phase2_text)
        self.assertIn("missed_findings 唯一对象模板", phase2_text)
        self.assertIn('"searched_locations": [', phase2_content)
        self.assertIn("searched_locations 永远是字符串数组", phase2_text)
        self.assertIn('"root_cause_count": 1', phase2_content)
        self.assertIn('"same_subject_and_scope": false', phase2_content)
        self.assertIn("不得因为候选稿篇幅", phase2_text)
        self.assertIn("coverage_ledger", phase2_text)
        self.assertIn("coverage_ledger V2 固定 JSON 骨架", phase2_text)
        self.assertIn("coverage_schema_version", phase2_text)
        self.assertIn("debit_timing", phase2_text)
        self.assertIn("点击后消耗对应货币", phase2_text)
        self.assertIn("唤起收银台", phase2_text)
        self.assertIn("pool_negative_floor", phase2_text)
        self.assertIn("same_metric_window", phase2_text)
        self.assertIn("settlement_formula_ui_config", phase2_text)
        self.assertNotEqual(baseline, phase2)

    def test_phase2_control_evidence_packet_is_deterministic_and_complete(self) -> None:
        shared_input = build_shared_review_input([make_doc("资金需求.docx")], max_context_chars=4000)
        primary = empty_report("C")
        primary["dimensions"][0]["findings"] = [
            finding("PRIMARY_FUNDS", "派奖到账节点未定义")
        ]

        first = build_phase2_control_evidence_packet(shared_input, primary)
        second = build_phase2_control_evidence_packet(shared_input, primary)

        self.assertEqual(first, second)
        self.assertEqual(first["protocol_revision"], "phase2_v2_2")
        self.assertEqual(len(first["evidence_packet_id"]), 64)
        self.assertEqual(len(first["cards"]), 12)
        self.assertEqual(
            [card["control_key"] for card in first["cards"]],
            [
                "settlement_formula",
                "ui_config_mapping",
                "trigger_entry",
                "termination_priority",
                "debit_timing",
                "payout_timing",
                "funds_failure_compensation",
                "relative_payout_cap",
                "pool_negative_floor",
                "single_round_payout_cap",
                "same_metric_window",
                "ui_text_window_alignment",
            ],
        )
        debit_card = next(card for card in first["cards"] if card["control_key"] == "debit_timing")
        payout_card = next(card for card in first["cards"] if card["control_key"] == "payout_timing")
        self.assertTrue(any("资金需求.docx" in value for value in debit_card["source_evidence_candidates"]))
        self.assertTrue(
            any("PRIMARY_FUNDS" == value["issue_id"] for value in payout_card["primary_candidates_to_verify"])
        )

    def test_dual_pass_secondary_messages_reuse_primary_baseline_rules(self) -> None:
        shared_input = build_shared_review_input([make_doc("Racing spec.docx")], max_context_chars=4000)
        content = "\n".join(
            str(item.get("content") or "")
            for item in build_dual_pass_secondary_messages(
                shared_input,
                empty_report(),
                protocol_profile="baseline",
            )
        )

        for block in (
            REVIEW_RULES,
            BASELINE_REVIEW_PRINCIPLES,
            SPECIAL_CHECKLIST,
            FACT_FIRST_PROTOCOL,
            ROOT_CAUSE_PROMPT_RULES,
            STABILITY_PROTOCOL,
            SCORE_RUBRIC,
            OUTPUT_QUALITY_BAR,
        ):
            self.assertIn(block, content)

    def test_dual_pass_secondary_messages_include_secondary_focus_rules(self) -> None:
        shared_input = build_shared_review_input([make_doc("Racing spec.docx")], max_context_chars=4000)
        content = "\n".join(
            str(item.get("content") or "") for item in build_dual_pass_secondary_messages(shared_input, empty_report())
        )

        self.assertIn("结构化补漏与反证审查者", content)
        self.assertIn("missed_findings", content)
        self.assertIn("review_notes", content)
        self.assertIn("coverage_ledger", content)
        self.assertIn("不生成 candidate_report", content)
        self.assertIn("最终 Candidate 由系统", content)
        self.assertIn("不得返回 candidate_report", content)

    def test_parse_dual_pass_review_json_normalizes_optional_sections(self) -> None:
        payload, error = parse_dual_pass_review_json('{"quality_assessment":{"summary":"ok"},"candidate_report":{}}')

        self.assertFalse(error)
        self.assertEqual(payload["quality_assessment"]["summary"], "ok")
        self.assertEqual(payload["missed_findings"], [])
        self.assertEqual(payload["review_notes"], [])
        self.assertEqual(payload["candidate_lineage"]["kept"], [])

    def test_parse_dual_pass_review_json_repairs_unclosed_key_before_array(self) -> None:
        payload, error = parse_dual_pass_review_json(
            '{\n'
            '  "quality_assessment": {\n'
            '    "summary": "ok",\n'
            '    "strengths [\n'
            '    ], "issues": ["one"]\n'
            '  },\n'
            '  "candidate_report": {}\n'
            '}'
        )

        self.assertFalse(error)
        self.assertEqual(payload["quality_assessment"]["strengths"], [])
        self.assertEqual(payload["quality_assessment"]["issues"], ["one"])

    def test_parse_dual_pass_review_json_repairs_unescaped_inner_quotes(self) -> None:
        payload, error = parse_dual_pass_review_json(
            '{"quality_assessment":{"summary":"OMS控制"购买免费游戏的价格系数"但未定义公式"},'
            '"candidate_report":{},"review_notes":[]}'
        )

        self.assertFalse(error)
        self.assertEqual(
            payload["quality_assessment"]["summary"],
            'OMS控制"购买免费游戏的价格系数"但未定义公式',
        )

    def test_parse_candidate_model_json_preserves_candidate_findings_before_stabilization(self) -> None:
        candidate_report = empty_report()
        candidate_report["dimensions"][0]["findings"] = [
            finding("LOGIC_1", "候选问题A"),
            finding("LOGIC_1", "候选问题B"),
        ]

        parsed, error = parse_candidate_model_json(json.dumps(candidate_report, ensure_ascii=False))

        self.assertFalse(error)
        self.assertEqual(len(parsed["dimensions"][0]["findings"]), 2)

    def test_demote_dual_pass_cross_document_issues_moves_findings_back_to_dimensions(self) -> None:
        report = empty_report()
        report["cross_document_issues"] = [
            {
                **finding("CROSS_1", "cross finding", DIMENSIONS[1]),
                "evidence_scope": "cross_document",
                "evidence": "doc-a / p1; doc-b / p2",
            }
        ]

        demoted = demote_dual_pass_cross_document_issues(report)

        self.assertEqual(demoted["cross_document_issues"], [])
        self.assertEqual(len(demoted["dimensions"][1]["findings"]), 1)
        self.assertEqual(demoted["dimensions"][1]["findings"][0]["evidence_scope"], "document")

    def test_build_conservative_dual_pass_candidate_report_materializes_kept_corrections_and_added_source(self) -> None:
        primary = empty_report()
        primary["dimensions"][0]["findings"] = [finding("PRIMARY_1", "primary finding")]
        primary["dimensions"][1]["findings"] = [finding("PRIMARY_2", "second primary finding", DIMENSIONS[1], "medium")]
        primary["top_blockers"] = [{"title": "primary finding", "severity": "high", "owner": "程序", "why_now": "why"}]

        candidate = empty_report()
        candidate["dimensions"][0]["findings"] = [
            {**finding("CAND_KEEP", "rewritten kept finding"), "current_state": "candidate state"},
            {**finding("CAND_ADD", "candidate added finding", severity="medium", blocking="block_testcase")},
        ]

        aligned = build_conservative_dual_pass_candidate_report(
            primary,
            candidate,
            {
                "kept": [{"candidate_issue_id": "CAND_KEEP", "primary_issue_ids": ["PRIMARY_1"]}],
                "added": [{"candidate_issue_id": "CAND_ADD", "source_missed_issue_ids": [], "reason": "missed"}],
                "merged": [],
                "dropped": [],
            },
            [],
            "deepseek-v4-pro",
        )

        titles = [item["title"] for dimension in aligned["dimensions"] for item in dimension.get("findings", [])]
        self.assertIn("rewritten kept finding", titles)
        self.assertIn("second primary finding", titles)
        self.assertIn("candidate added finding", titles)
        added_finding = next(
            item for item in aligned["dimensions"][0]["findings"] if item.get("title") == "candidate added finding"
        )
        self.assertEqual(added_finding["finding_source"], "secondary_reviewer")
        self.assertEqual(added_finding["source_model"], "deepseek-v4-pro")

    def test_build_conservative_dual_pass_candidate_report_materializes_judgment_demotion(self) -> None:
        primary = empty_report("C")
        primary["dimensions"][1]["findings"] = [
            finding("LOGIC_03", "取整规则导致高危赔付风险", DIMENSIONS[1], "高", "阻塞开发")
        ]
        candidate = empty_report("B")
        candidate["dimensions"][1]["findings"] = [
            {
                **finding("LOGIC_03", "取整精度口径仍需明确", DIMENSIONS[1], "中", "阻塞测试用例设计"),
                "risk": "仅可能造成最小货币单位上的计算差异。",
            }
        ]

        aligned = build_conservative_dual_pass_candidate_report(
            primary,
            candidate,
            {
                "kept": [{"candidate_issue_id": "LOGIC_03", "primary_issue_ids": ["LOGIC_03"]}],
                "added": [],
                "merged": [],
                "dropped": [],
            },
            [],
            "deepseek-v4-pro",
        )

        materialized = aligned["dimensions"][1]["findings"][0]
        self.assertEqual(materialized["title"], "取整精度口径仍需明确")
        self.assertEqual(materialized["severity"], "中")
        self.assertEqual(materialized["blocking"], "阻塞测试用例设计")
        self.assertEqual(materialized["risk"], "仅可能造成最小货币单位上的计算差异。")

    def test_build_dual_pass_secondary_finding_uses_candidate_details_and_marks_source(self) -> None:
        result = build_dual_pass_secondary_finding(
            {"missed_issue_id": "MISS_1", "dimension": DIMENSIONS[0], "description": "raw state", "severity": "high"},
            secondary_model="deepseek-v4-pro",
            candidate_finding={
                **finding("MISS_1", "candidate title"),
                "current_state": "candidate state",
                "risk": "candidate risk",
            },
        )

        self.assertEqual(result["issue_id"], "MISS_1")
        self.assertEqual(result["title"], "candidate title")
        self.assertEqual(result["current_state"], "candidate state")
        self.assertEqual(result["finding_source"], "secondary_reviewer")
        self.assertEqual(result["source_model"], "deepseek-v4-pro")

    def test_normalize_dual_pass_advice_payload_marks_lineage_auto_heal_and_issue_id_repairs(self) -> None:
        primary = empty_report()
        primary["_issue_id_repair_count"] = 1
        primary["dimensions"][0]["findings"] = [finding("PRIMARY_1", "shared title issue")]
        candidate = empty_report()
        candidate["_issue_id_repair_count"] = 1
        candidate["dimensions"][0]["findings"] = [finding("CAND_1", "shared title issue")]

        payload = normalize_dual_pass_advice_payload(
            primary,
            candidate,
            {
                "quality_assessment": {"ready_for_direct_output": True, "suggestion_level": "low"},
                "candidate_readiness": {"ready_for_direct_output": True},
                "candidate_lineage": {"kept": [], "added": [], "merged": [], "dropped": []},
                "review_notes": [],
            },
        )

        self.assertTrue(payload["lineage_auto_healed"])
        self.assertEqual(payload["lineage_auto_mapped_primary_issue_ids"], ["PRIMARY_1"])
        self.assertEqual(payload["lineage_auto_mapped_candidate_issue_ids"], ["CAND_1"])
        self.assertEqual(payload["primary_issue_id_repair_count"], 1)
        self.assertEqual(payload["candidate_issue_id_repair_count"], 1)
        self.assertEqual(payload["traceability_status"], "complete")

    def test_normalize_dual_pass_advice_payload_blocks_kept_issue_id_split(self) -> None:
        primary = empty_report()
        candidate = empty_report()
        primary["dimensions"][0]["findings"] = [finding("LOGIC_01", "primary finding")]
        candidate["dimensions"][0]["findings"] = [finding("LOGIC_01_02", "primary finding")]

        payload = normalize_dual_pass_advice_payload(
            primary,
            candidate,
            {
                "quality_assessment": {"summary": "ok", "ready_for_direct_output": True, "suggestion_level": "low"},
                "candidate_readiness": {"ready_for_direct_output": True},
                "candidate_lineage": {
                    "kept": [{"candidate_issue_id": "LOGIC_01_02", "primary_issue_ids": ["LOGIC_01"]}],
                    "added": [],
                    "merged": [],
                    "dropped": [],
                },
                "review_notes": [],
            },
        )

        self.assertTrue(payload["candidate_issue_id_split_detected"])
        self.assertFalse(payload["normalized_candidate_ready_for_direct_output"])

    def test_evaluate_dual_pass_candidate_selection_allows_suggestion_override(self) -> None:
        primary = empty_report()
        candidate = empty_report()
        candidate["dimensions"][0]["findings"] = [finding("PRIMARY_1", "primary finding")]

        result = evaluate_dual_pass_candidate_selection(
            primary,
            candidate,
            {
                "quality_assessment": {"ready_for_direct_output": True, "suggestion_level": "high"},
                "candidate_readiness": {"ready_for_direct_output": True},
                "candidate_lineage": {
                    "kept": [{"candidate_issue_id": "PRIMARY_1", "primary_issue_ids": ["PRIMARY_1"]}],
                    "added": [],
                    "merged": [],
                    "dropped": [],
                },
                "traceability_status": "complete",
                "candidate_structure_drift": False,
                "lineage_coverage_complete": True,
                "normalized_candidate_ready_for_direct_output": True,
                "candidate_added_materialization_status": "none",
                "candidate_merged_materialization_status": "none",
                "candidate_structurally_ready": True,
                "unmapped_primary_issue_ids": [],
                "unmapped_candidate_issue_ids": [],
                "untitled_finding_issue_ids": [],
                "missing_issue_id_finding_titles": [],
                "advice_candidate_structure_mismatch": False,
            },
            {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
            "",
        )

        self.assertEqual(result["selected_report_owner"], "candidate")
        self.assertNotIn("suggestion_level_high", result["candidate_gate_failure_reasons"])
        self.assertTrue(result["suggestion_level_conflict"])
        self.assertTrue(result["suggestion_level_override_applied"])

    def test_evaluate_dual_pass_candidate_selection_uses_normalized_readiness_as_gate(self) -> None:
        candidate = empty_report()
        candidate["dimensions"][0]["findings"] = [finding("PRIMARY_1", "primary finding")]

        result = evaluate_dual_pass_candidate_selection(
            empty_report(),
            candidate,
            {
                "quality_assessment": {"ready_for_direct_output": False, "suggestion_level": "low"},
                "candidate_readiness": {"ready_for_direct_output": False},
                "candidate_lineage": {
                    "kept": [{"candidate_issue_id": "PRIMARY_1", "primary_issue_ids": ["PRIMARY_1"]}],
                    "added": [],
                    "merged": [],
                    "dropped": [],
                },
                "traceability_status": "complete",
                "candidate_structure_drift": False,
                "lineage_coverage_complete": True,
                "normalized_candidate_ready_for_direct_output": True,
                "normalized_candidate_ready_reason": "normalized ready",
                "candidate_added_materialization_status": "none",
                "candidate_merged_materialization_status": "none",
                "candidate_structurally_ready": True,
                "unmapped_primary_issue_ids": [],
                "unmapped_candidate_issue_ids": [],
                "untitled_finding_issue_ids": [],
                "missing_issue_id_finding_titles": [],
                "advice_candidate_structure_mismatch": False,
            },
            {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
            "",
        )

        self.assertEqual(result["selected_report_owner"], "candidate")
        self.assertNotIn("normalized_candidate_not_ready", result["candidate_gate_failure_reasons"])
        self.assertNotIn("readiness_conflict", result["candidate_gate_failure_reasons"])

    def test_evaluate_dual_pass_candidate_selection_blocks_unsupported_high_signal_demotion(self) -> None:
        candidate = empty_report("B")
        candidate["dimensions"][0]["findings"] = [finding("PRIMARY_1", "primary finding", severity="medium")]

        result = evaluate_dual_pass_candidate_selection(
            empty_report("C"),
            candidate,
            {
                "quality_assessment": {"ready_for_direct_output": True, "suggestion_level": "medium"},
                "candidate_readiness": {"ready_for_direct_output": True},
                "candidate_lineage": {
                    "kept": [{"candidate_issue_id": "PRIMARY_1", "primary_issue_ids": ["PRIMARY_1"]}],
                    "added": [],
                    "merged": [],
                    "dropped": [],
                },
                "traceability_status": "complete",
                "candidate_structure_drift": False,
                "lineage_coverage_complete": True,
                "normalized_candidate_ready_for_direct_output": True,
                "candidate_added_materialization_status": "none",
                "candidate_merged_materialization_status": "none",
                "candidate_structurally_ready": True,
                "unmapped_primary_issue_ids": [],
                "unmapped_candidate_issue_ids": [],
                "untitled_finding_issue_ids": [],
                "missing_issue_id_finding_titles": [],
                "advice_candidate_structure_mismatch": False,
                "candidate_high_signal_demotion_without_support": True,
                "candidate_high_signal_demotion_issue_ids": ["PRIMARY_1"],
                "candidate_high_signal_demotion_titles": ["primary finding"],
            },
            {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
            "",
        )

        self.assertEqual(result["selected_report_owner"], "pipeline")
        self.assertIn("candidate_high_signal_demotion_without_support", result["candidate_gate_failure_reasons"])

    def test_evaluate_dual_pass_candidate_selection_blocks_overcompressed_candidate(self) -> None:
        candidate = empty_report("B")
        candidate["dimensions"][0]["findings"] = [finding("PRIMARY_1", "primary finding")]

        result = evaluate_dual_pass_candidate_selection(
            empty_report("C"),
            candidate,
            {
                "quality_assessment": {"ready_for_direct_output": True, "suggestion_level": "medium"},
                "candidate_readiness": {"ready_for_direct_output": True},
                "candidate_lineage": {
                    "kept": [{"candidate_issue_id": "PRIMARY_1", "primary_issue_ids": ["PRIMARY_1"]}],
                    "added": [],
                    "merged": [],
                    "dropped": [],
                },
                "traceability_status": "complete",
                "candidate_structure_drift": False,
                "lineage_coverage_complete": True,
                "normalized_candidate_ready_for_direct_output": True,
                "candidate_added_materialization_status": "none",
                "candidate_merged_materialization_status": "none",
                "candidate_structurally_ready": True,
                "unmapped_primary_issue_ids": [],
                "unmapped_candidate_issue_ids": [],
                "untitled_finding_issue_ids": [],
                "missing_issue_id_finding_titles": [],
                "advice_candidate_structure_mismatch": False,
                "candidate_overcompressed": True,
                "candidate_overcompressed_reason": "candidate 问题数收缩过快",
            },
            {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
            "",
        )

        self.assertEqual(result["selected_report_owner"], "pipeline")
        self.assertIn("candidate_overcompressed", result["candidate_gate_failure_reasons"])

    def test_render_dual_pass_markdown_includes_new_diagnostics(self) -> None:
        advice_markdown = render_dual_pass_advice_markdown(
            {
                "quality_assessment": {"summary": "ok", "suggestion_level": "high", "ready_for_direct_output": True},
                "traceability_status": "complete",
                "readiness_conflict": False,
                "candidate_structure_drift": False,
                "advice_candidate_structure_mismatch": False,
                "suggestion_level_conflict": True,
                "suggestion_level_override_applied": True,
                "primary_issue_id_repair_count": 1,
                "candidate_issue_id_repair_count": 2,
                "lineage_auto_healed": True,
                "lineage_auto_mapped_primary_issue_ids": ["PRIMARY_1"],
                "lineage_auto_mapped_candidate_issue_ids": ["CAND_1"],
                "candidate_added_materialization_status": "none",
                "candidate_merged_materialization_status": "none",
                "candidate_issue_id_split_detected": True,
                "candidate_issue_id_split_issue_ids": ["LOGIC_01_02"],
                "candidate_negated_primary_finding_still_materialized": True,
                "candidate_negated_primary_titles": ["赔率公式冲突"],
                "candidate_high_signal_demotion_without_support": True,
                "candidate_high_signal_demotion_titles": ["RESPIN 结算公式"],
                "candidate_overcompressed": True,
                "candidate_overcompressed_reason": "candidate 问题数收缩过快",
                "lineage_counts": {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
                "lineage_counts_raw": {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
                "lineage_counts_materialized": {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
                "review_notes": [],
                "unsupported_findings": [],
                "merge_recommendations": [],
                "candidate_block_reasons": [],
                "candidate_block_reason_categories": {},
                "phase2_admission": {
                    "enabled": True,
                    "claimed_count": 0,
                    "admitted_count": 0,
                    "rejected_count": 0,
                    "coverage_ledger": {"passed": True, "completeness": 1.0, "confirmed_audit_keys": [], "errors": []},
                },
            }
        )
        index_markdown = render_dual_pass_index_markdown(
            {
                "status": "complete",
                "primary_model": "gpt-5.4",
                "secondary_model": "deepseek-v4-pro",
                "selected_report_owner": "candidate",
                "selected_report_path": "review_report.md",
                "selected_source_report_path": "review_report_candidate.md",
                "candidate_recommendation_status": "recommended",
                "candidate_gate_failure_reasons": [],
                "candidate_gate_failure_categories": {},
                "candidate_ready_for_direct_output": True,
                "candidate_ready_reason": "ready",
                "traceability_status": "complete",
                "readiness_conflict": False,
                "candidate_structure_drift": False,
                "candidate_structurally_ready": True,
                "candidate_blocked_only_by_editorial_judgment": False,
                "advice_candidate_structure_mismatch": False,
                "suggestion_level_conflict": True,
                "suggestion_level_override_applied": True,
                "candidate_high_signal_demotion_without_support": True,
                "candidate_high_signal_demotion_titles": ["RESPIN 结算公式"],
                "candidate_overcompressed": True,
                "candidate_overcompressed_reason": "candidate 问题数收缩过快",
                "primary_issue_id_repair_count": 1,
                "candidate_issue_id_repair_count": 2,
                "lineage_auto_healed": True,
                "lineage_auto_mapped_primary_issue_ids": ["PRIMARY_1"],
                "lineage_auto_mapped_candidate_issue_ids": ["CAND_1"],
                "pipeline_report_path": "review_report_pipeline.md",
                "candidate_report_path": "review_report_candidate.md",
                "advice_path": "secondary_review_advice.md",
                "primary_score": "C",
                "pipeline_score": "C",
                "candidate_score": "C",
                "selected_score": "C",
                "pipeline_finding_count": 1,
                "candidate_finding_count": 1,
                "selected_finding_count": 1,
                "lineage_counts": {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
                "lineage_counts_raw": {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
                "lineage_counts_materialized": {"kept": 1, "added": 0, "merged": 0, "dropped": 0},
                "candidate_added_materialization_status": "none",
                "candidate_merged_materialization_status": "none",
                "comparison_summary": {"pipeline_only_count": 0, "candidate_only_count": 0, "materially_changed_count": 0},
                "phase2_admission": {
                    "enabled": True,
                    "claimed_count": 0,
                    "admitted_count": 0,
                    "rejected_count": 0,
                    "coverage_ledger": {"passed": True, "completeness": 1.0, "confirmed_audit_keys": [], "errors": []},
                },
            }
        )

        self.assertIn("issue_id 修复数", advice_markdown)
        self.assertIn("自动补齐的 primary issue_id", advice_markdown)
        self.assertIn("kept 子编号 issue_id", advice_markdown)
        self.assertIn("默认最终报告来源", index_markdown)
        self.assertIn("Candidate 直出建议", index_markdown)
        self.assertIn("自动补齐的 candidate issue_id", index_markdown)
        self.assertIn("高信号核心问题", advice_markdown)
        self.assertIn("过度收缩", advice_markdown)
        self.assertIn("高信号问题降级", index_markdown)
        self.assertIn("过度收缩", index_markdown)
        self.assertIn("coverage ledger：通过，完整率 100%", advice_markdown)
        self.assertIn("coverage ledger：通过，完整率 100%", index_markdown)

    def test_write_report_files_strip_internal_issue_id_repair_fields(self) -> None:
        report = empty_report()
        report["_issue_id_repair_count"] = 2
        report["_issue_id_repairs"] = [{"issue_id": "A"}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            markdown_path = root / "report.md"
            json_path = root / "report.json"
            write_report_files(report, [make_doc()], markdown_path, json_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertNotIn("_issue_id_repair_count", payload["report"])
        self.assertNotIn("_issue_id_repairs", payload["report"])

    def test_dual_pass_mode_writes_pipeline_candidate_advice_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "reports"
            agent = ReviewAgent(
                input_path=root,
                output_dir=output_dir,
                review_mode="dual_pass",
                analyze_images=False,
            )
            agent.config = ModelConfig(
                base_url="http://primary.test",
                api_key="key",
                text_model="gpt-5.4",
                vision_base_url="",
                vision_api_key="",
                vision_model="",
            )
            agent.secondary_config = ModelConfig(
                base_url="http://secondary.test",
                api_key="key2",
                text_model="deepseek-v4-pro",
                vision_base_url="",
                vision_api_key="",
                vision_model="",
            )
            agent.secondary_client = OpenAICompatibleClient(agent.secondary_config, timeout=600)
            agent._parse_documents = lambda assets_dir: [make_doc("Racing spec.docx")]
            agent._write_latest = lambda run_dir: None

            primary_report = empty_report("C")
            primary_report["dimensions"][0]["findings"] = [finding("PRIMARY_1", "触发入口条件缺失")]
            primary_report["top_blockers"] = [{"title": "触发入口条件缺失", "severity": "high", "owner": "程序", "why_now": "why"}]

            candidate_report = empty_report("C")
            candidate_report["dimensions"][0]["findings"] = [
                finding("PRIMARY_1", "触发入口条件缺失", severity="中", blocking="阻塞测试用例设计")
            ]
            candidate_report["top_blockers"] = [{"title": "触发入口条件缺失", "severity": "high", "owner": "程序", "why_now": "why"}]

            secondary_review = {
                "quality_assessment": {
                    "summary": "候选稿可直接输出。",
                    "strengths": [],
                    "issues": [],
                    "suggestion_level": "low",
                    "ready_for_direct_output": True,
                    "reason": "candidate ready",
                },
                "coverage_schema_version": 2,
                "coverage_ledger": phase2_v2_coverage_ledger(covered={"trigger_entry": ["PRIMARY_1"]}),
                "missed_findings": [],
                "unsupported_findings": [],
                "merge_recommendations": [],
                "review_notes": [],
            }

            def fake_call(messages: list[dict[str, str]], client=None, config=None, stage: str = "primary") -> str:
                if stage == "primary":
                    return json.dumps(primary_report, ensure_ascii=False)
                if stage == "secondary":
                    prompt_text = json.dumps(messages, ensure_ascii=False)
                    packet_match = re.search(r"evidence_packet_id=([0-9a-f]{64})", prompt_text)
                    self.assertIsNotNone(packet_match)
                    payload = json.loads(json.dumps(secondary_review, ensure_ascii=False))
                    payload["review_notes"] = [
                        f"protocol_profile=phase2_v2_2; evidence_packet_id={packet_match.group(1)}"
                    ]
                    return json.dumps(payload, ensure_ascii=False)
                raise AssertionError(stage)

            agent._call_text_model = fake_call  # type: ignore[method-assign]
            result = agent.run()

            run_dir = Path(result.markdown_path).parent
            self.assertTrue((run_dir / "review_report.md").exists())
            self.assertTrue((run_dir / "review_report_pipeline.md").exists())
            self.assertTrue((run_dir / "review_report_candidate.md").exists())
            self.assertTrue((run_dir / "review_report_index.md").exists())
            self.assertTrue((run_dir / "secondary_review_advice.md").exists())

            index_payload = json.loads((run_dir / "review_report_index.json").read_text(encoding="utf-8"))
            self.assertEqual(index_payload["selected_report_owner"], "candidate")
            self.assertEqual(index_payload["candidate_recommendation_status"], "recommended")
            self.assertEqual(
                index_payload["candidate_generation_mode"],
                "deterministic_primary_plus_admitted_delta",
            )
            packet = json.loads(
                (run_dir / "model_artifacts" / "phase2_control_evidence_packet.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                (run_dir / "model_artifacts" / "dual_pass_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(packet["protocol_revision"], "phase2_v2_2")
            self.assertTrue(summary["coverage_evidence_packet_echoed"])
            self.assertTrue(summary["phase2_delta_only_compliant"])
            self.assertTrue(summary["phase2_protocol_gate"]["passed"])

    def test_dual_pass_secondary_failure_falls_back_to_primary_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = ReviewAgent(
                input_path=root,
                output_dir=root / "reports",
                review_mode="dual_pass",
                analyze_images=False,
                model_retries=3,
            )
            agent.config = ModelConfig(
                base_url="http://primary.test",
                api_key="key",
                text_model="qwen-primary",
                vision_base_url="",
                vision_api_key="",
                vision_model="",
            )
            agent.secondary_config = ModelConfig(
                base_url="http://secondary.test",
                api_key="key2",
                text_model="qwen-secondary",
                vision_base_url="",
                vision_api_key="",
                vision_model="",
            )
            agent.secondary_client = OpenAICompatibleClient(agent.secondary_config, timeout=600)
            agent._parse_documents = lambda assets_dir: [make_doc("玩法需求.docx")]
            agent._write_latest = lambda run_dir: None
            primary_report = empty_report("C")
            primary_report["dimensions"][0]["findings"] = [finding("PRIMARY_1", "核心结算规则不完整")]
            primary_report["top_blockers"] = [
                {"issue_id": "PRIMARY_1", "title": "核心结算规则不完整", "severity": "高", "owner": "程序", "why_now": "阻塞"}
            ]

            def fake_call(messages: list[dict[str, str]], client=None, config=None, stage: str = "primary") -> str:
                if stage == "primary":
                    return json.dumps(primary_report, ensure_ascii=False)
                raise RuntimeError("secondary failed after 4 attempt(s): Model API HTTP 502")

            agent._call_text_model = fake_call  # type: ignore[method-assign]
            result = agent.run()
            run_dir = Path(result.markdown_path).parent
            final_payload = json.loads((run_dir / "review_report.json").read_text(encoding="utf-8"))["report"]
            pipeline_payload = json.loads((run_dir / "review_report_pipeline.json").read_text(encoding="utf-8"))["report"]
            summary = json.loads((run_dir / "model_artifacts" / "dual_pass_summary.json").read_text(encoding="utf-8"))

            self.assertIn("副评审调用失败", result.warning)
            self.assertEqual(final_payload, pipeline_payload)
            self.assertFalse((run_dir / "review_report_candidate.json").exists())
            self.assertEqual(summary["status"], "primary_only")
            self.assertEqual(summary["secondary_protocol_profile"], "phase2")

    def test_dual_pass_timeout_and_invalid_json_fall_back_to_primary_pipeline(self) -> None:
        cases = {
            "timeout": TimeoutError("secondary timed out"),
            "invalid_json": "not-json-and-not-repairable",
        }
        for case_name, secondary_outcome in cases.items():
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                agent = ReviewAgent(
                    input_path=root,
                    output_dir=root / "reports",
                    review_mode="dual_pass",
                    analyze_images=False,
                )
                agent.config = ModelConfig(
                    base_url="http://primary.test",
                    api_key="key",
                    text_model="qwen-primary",
                    vision_base_url="",
                    vision_api_key="",
                    vision_model="",
                )
                agent.secondary_config = ModelConfig(
                    base_url="http://secondary.test",
                    api_key="key2",
                    text_model="qwen-secondary",
                    vision_base_url="",
                    vision_api_key="",
                    vision_model="",
                )
                agent.secondary_client = OpenAICompatibleClient(agent.secondary_config, timeout=600)
                agent._parse_documents = lambda assets_dir: [make_doc("玩法需求.docx")]
                agent._write_latest = lambda run_dir: None
                primary_report = empty_report("C")

                def fake_call(messages: list[dict[str, str]], client=None, config=None, stage: str = "primary") -> str:
                    if stage == "primary":
                        return json.dumps(primary_report, ensure_ascii=False)
                    if isinstance(secondary_outcome, Exception):
                        raise secondary_outcome
                    return secondary_outcome

                agent._call_text_model = fake_call  # type: ignore[method-assign]
                result = agent.run()
                run_dir = Path(result.markdown_path).parent
                final_payload = json.loads((run_dir / "review_report.json").read_text(encoding="utf-8"))["report"]
                pipeline_payload = json.loads((run_dir / "review_report_pipeline.json").read_text(encoding="utf-8"))["report"]

                self.assertEqual(final_payload, pipeline_payload)
                self.assertFalse((run_dir / "review_report_candidate.json").exists())
                self.assertTrue(result.warning)


if __name__ == "__main__":
    unittest.main()
