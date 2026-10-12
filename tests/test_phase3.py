from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from rad_review.phase3 import (
    PHASE3_V11_PROTOCOL_REVISION,
    PHASE3_V12_PROTOCOL_REVISION,
    PHASE3_V13_PROTOCOL_REVISION,
    apply_human_approved_phase3_corrections,
    evaluate_phase3_review,
    parse_phase3_review_json,
    phase3_expected_echo,
    phase3_primary_report_hash,
    write_phase3_artifacts,
)
from rad_review.prompts import DIMENSIONS, build_dual_pass_secondary_messages


def primary_report() -> dict:
    finding = {
        "issue_id": "config_mapping_conflict",
        "title": "图标命名和筹码档位跨文档不一致",
        "current_state": "需求和数值文档同时存在图标命名与筹码档位差异。",
        "evidence": "玩法需求.docx / 表格2；数值配置.xlsx / 表格1",
        "risk": "美术资源映射和下注配置需要分别修改。",
        "suggestion": "统一图标命名并统一筹码档位。",
        "planner_role": "系统策划",
        "confidence": "高",
        "severity": "高",
        "blocking": "阻塞开发",
    }
    return {
        "overall_evaluation": "主流程可理解。",
        "document_quality_score": "C",
        "score_reason": "存在高风险配置冲突。",
        "top_blockers": [
            {"severity": "高", "title": finding["title"], "owner": "系统策划", "why_now": "阻塞实现"}
        ],
        "dimensions": [
            {
                "name": name,
                "dimension_note": "",
                "findings": [copy.deepcopy(finding)] if index == 0 else [],
            }
            for index, name in enumerate(DIMENSIONS)
        ],
        "cross_document_issues": [],
        "missing_information": [],
        "test_points": {},
        "quality_notes": [],
        "image_analysis_gaps": [],
    }


def valid_phase3_payload(report: dict) -> dict:
    split_items = [
        {
            "title": "图标命名跨文档不一致",
            "decision_object": "symbol_naming",
            "current_state": "两个文档的图标命名不同。",
            "evidence": "玩法需求.docx / 表格2；数值配置.xlsx / 表格1",
            "risk": "资源映射可能错误。",
            "suggestion": "建立唯一图标命名字典。",
            "planner_role": "系统策划",
            "acceptance_criteria": "两个文档使用同一图标键。",
        },
        {
            "title": "筹码档位跨文档不一致",
            "decision_object": "chip_tiers",
            "current_state": "两个文档的筹码档位不同。",
            "evidence": "玩法需求.docx / 表格3；数值配置.xlsx / 表格4",
            "risk": "下注入口与服务端配置无法一一映射。",
            "suggestion": "冻结唯一筹码档位表。",
            "planner_role": "数值策划",
            "acceptance_criteria": "客户端和服务端档位逐项一致。",
        },
    ]
    return {
        "challenge_findings": [
            {
                "challenge_id": "CH-001",
                "target_issue_id": "config_mapping_conflict",
                "challenge_type": "multiroot",
                "challenged_claim": "图标命名与筹码档位属于同一整改闭环。",
                "evidence": "玩法需求.docx / 表格2-3；数值配置.xlsx / 表格1-4",
                "rationale": "两个对象由不同配置字段、责任人和验收用例关闭。",
                "recommended_action": "split",
                "proposed_split": split_items,
            }
        ],
        "correction_shadows": [
            {
                "correction_id": "CR-001",
                "challenge_id": "CH-001",
                "target_issue_id": "config_mapping_conflict",
                "correction_type": "split",
                "evidence": "玩法需求.docx / 表格2-3；数值配置.xlsx / 表格1-4",
                "rationale": "拆成两个可以独立分配和验收的问题。",
                "replacement_findings": copy.deepcopy(split_items),
            }
        ],
        "review_notes": ["仅输出旁路建议。", phase3_expected_echo(report)],
    }


def phase3_v11_payload(
    report: dict,
    *,
    challenge_type: str = "compatible_interpretation",
    recommended_action: str = "drop",
    disposition: str = "drop",
) -> dict:
    semantic_checks = {
        "compatible_interpretation_exists": challenge_type == "compatible_interpretation",
        "original_claim_still_valid": disposition in {"downgrade", "clarify", "narrow", "split"},
        "residual_issue_exists": disposition in {"downgrade", "clarify", "narrow", "split"},
        "protected_fields_need_human_review": disposition == "downgrade",
    }
    proposed_changes = {}
    if disposition == "downgrade":
        proposed_changes = {
            "risk": "事实问题仍成立，但影响仅为低风险提醒。",
            "suggestion": "由策划确认描述边界。",
        }
    elif disposition in {"clarify", "narrow"}:
        proposed_changes = {
            "current_state": "原文存在兼容解释，但仍有一个可定位的剩余歧义。",
            "risk": "可能造成实现口径误读。",
        }
    return {
        "challenge_findings": [
            {
                "challenge_id": "CH-001",
                "target_issue_id": "config_mapping_conflict",
                "challenge_type": challenge_type,
                "challenged_claim": "Primary 将可兼容解释定性为直接冲突。",
                "evidence": "玩法需求.docx / 表格2；数值配置.xlsx / 表格1",
                "counterevidence": "两个字段分别服务于不同配置对象。",
                "rationale": "同一实现可以同时满足两处描述。",
                "recommended_action": recommended_action,
                "proposed_split": [],
            }
        ],
        "correction_shadows": [
            {
                "correction_id": "CR-001",
                "challenge_id": "CH-001",
                "target_issue_id": "config_mapping_conflict",
                "correction_disposition": disposition,
                "source_provenance": "requirement_text",
                "evidence": "玩法需求.docx / 表格2；数值配置.xlsx / 表格1",
                "rationale": "处置动作与反证结论保持一致。",
                "residual_issue": "仍需确认配置边界" if semantic_checks["residual_issue_exists"] else "",
                "semantic_checks": semantic_checks,
                "proposed_changes": proposed_changes,
                "replacement_findings": [],
            }
        ],
        "review_notes": [
            "仅输出旁路建议。",
            phase3_expected_echo(report, protocol_revision=PHASE3_V11_PROTOCOL_REVISION),
        ],
    }


def phase3_v12_payload(report: dict, *, disposition: str = "drop") -> dict:
    recommended_action = "demote" if disposition == "downgrade" else "drop"
    challenge_type = "overstated" if disposition == "downgrade" else "compatible_interpretation"
    payload = phase3_v11_payload(
        report,
        challenge_type=challenge_type,
        recommended_action=recommended_action,
        disposition=disposition,
    )
    payload["challenge_findings"][0]["challenge_id"] = "CH-config_mapping_conflict"
    payload["correction_shadows"][0]["challenge_id"] = "CH-config_mapping_conflict"
    payload["correction_shadows"][0]["correction_id"] = "CR-config_mapping_conflict"
    payload["target_coverage_ledger"] = [
        {
            "target_issue_id": "config_mapping_conflict",
            "target_order": 1,
            "decision": "challenge",
            "challenge_type": challenge_type,
            "recommended_action": recommended_action,
            "evidence_checked": "玩法需求.docx / 表格2；数值配置.xlsx / 表格1",
            "rationale": "逐项核验后发现 Primary 定性需要纠正。",
        }
    ]
    payload["review_notes"][-1] = phase3_expected_echo(
        report, protocol_revision=PHASE3_V12_PROTOCOL_REVISION
    )
    return payload


def phase3_v13_payload(report: dict) -> dict:
    payload = phase3_v12_payload(report)
    payload["target_coverage_ledger"][0]["challenge_checks"] = {
        "duplicate": "rejected",
        "multiroot": "rejected",
        "evidence_mismatch": "rejected",
        "unsupported": "rejected",
        "compatible_interpretation": "confirmed",
        "overstated": "rejected",
    }
    payload["review_notes"][-1] = phase3_expected_echo(
        report, protocol_revision=PHASE3_V13_PROTOCOL_REVISION
    )
    return payload


class Phase3ProtocolTests(unittest.TestCase):
    def test_prompt_is_independent_advice_and_shadow_protocol(self) -> None:
        report = primary_report()
        messages = build_dual_pass_secondary_messages(
            {
                "document_labels": ["玩法需求.docx", "数值配置.xlsx"],
                "collection_summary": {},
                "document_context": "玩法需求.docx / 表格2 图标A；数值配置.xlsx / 表格1 图标B",
                "context_truncated": False,
                "public_rules": {},
            },
            report,
            protocol_profile="phase3_v1",
        )
        text = json.dumps(messages, ensure_ascii=False)
        self.assertIn("phase3_v1", text)
        self.assertIn("challenge_findings", text)
        self.assertIn("correction_shadows", text)
        self.assertIn(phase3_primary_report_hash(report), text)
        self.assertNotIn("phase2_v2_2", text)
        self.assertNotIn('"candidate_report": {', text)

    def test_valid_review_produces_traceable_advice_and_shadow_without_mutation(self) -> None:
        report = primary_report()
        before = copy.deepcopy(report)
        parsed, error = parse_phase3_review_json(json.dumps(valid_phase3_payload(report), ensure_ascii=False))
        self.assertEqual(error, "")

        challenge, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
        )

        self.assertEqual(report, before)
        self.assertTrue(challenge["protocol_gate"]["passed"])
        self.assertTrue(challenge["baseline_lock"]["passed"])
        self.assertEqual(challenge["accepted_count"], 1)
        self.assertEqual(correction["accepted_count"], 1)
        self.assertFalse(correction["accepted_corrections"][0]["applied_to_report"])
        self.assertEqual(
            correction["accepted_corrections"][0]["before"]["severity"],
            "高",
        )
        self.assertEqual(
            len(correction["accepted_corrections"][0]["after_preview"]["replacement_findings"]),
            2,
        )
        self.assertTrue(summary["protocol_gate_passed"])
        self.assertTrue(summary["baseline_lock_passed"])
        self.assertEqual(summary["challenge_keys"], ["config_mapping_conflict:multiroot:split"])

    def test_protected_score_or_blocking_change_is_rejected(self) -> None:
        report = primary_report()
        payload = valid_phase3_payload(report)
        payload["correction_shadows"][0]["replacement_findings"][0]["blocking"] = "建议优化"
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        challenge, correction, _ = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
        )

        self.assertEqual(challenge["accepted_count"], 1)
        self.assertEqual(correction["accepted_count"], 0)
        reasons = correction["rejected_corrections"][0]["validation_reasons"]
        self.assertTrue(any("protected_fields_present:blocking" in reason for reason in reasons))

    def test_unknown_target_and_bad_echo_are_hard_failures(self) -> None:
        report = primary_report()
        payload = valid_phase3_payload(report)
        payload["challenge_findings"][0]["target_issue_id"] = "UNKNOWN"
        payload["review_notes"][-1] = "protocol_profile=phase3_v1; primary_report_hash=wrong"
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        challenge, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
        )

        self.assertFalse(summary["protocol_gate_passed"])
        self.assertEqual(challenge["accepted_count"], 0)
        self.assertEqual(correction["accepted_count"], 0)
        self.assertIn("protocol_echo_missing_or_mismatched", challenge["protocol_gate"]["errors"])

    def test_forbidden_candidate_field_hard_fails_delta_only_gate(self) -> None:
        report = primary_report()
        payload = valid_phase3_payload(report)
        payload["candidate_report"] = {}
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        challenge, _, summary = evaluate_phase3_review(report, parsed, document_labels=["玩法需求.docx"])

        self.assertFalse(summary["protocol_gate_passed"])
        self.assertEqual(challenge["protocol_gate"]["forbidden_top_level_fields"], ["candidate_report"])

    def test_artifact_writer_records_before_after_without_report_rewrite(self) -> None:
        report = primary_report()
        parsed, _ = parse_phase3_review_json(json.dumps(valid_phase3_payload(report), ensure_ascii=False))
        challenge, correction, _ = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_phase3_artifacts(
                challenge,
                correction,
                root / "secondary_challenge_advice.json",
                root / "secondary_correction_shadow.json",
            )
            self.assertTrue((root / "secondary_challenge_advice.md").is_file())
            self.assertTrue((root / "secondary_correction_shadow.md").is_file())
            saved = json.loads((root / "secondary_correction_shadow.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["applied_to_report"])
            self.assertTrue(saved["baseline_lock"]["passed"])

    def test_phase3_v11_prompt_requires_explicit_correction_disposition(self) -> None:
        report = primary_report()
        messages = build_dual_pass_secondary_messages(
            {
                "document_labels": ["玩法需求.docx", "数值配置.xlsx"],
                "collection_summary": {},
                "document_context": "玩法需求.docx / 表格2 图标A；数值配置.xlsx / 表格1 图标B",
                "context_truncated": False,
                "public_rules": {},
            },
            report,
            protocol_profile="phase3_v1_1",
        )
        text = json.dumps(messages, ensure_ascii=False)
        self.assertIn("phase3_v1_1", text)
        self.assertIn("correction_disposition", text)
        self.assertIn("source_provenance", text)
        self.assertIn("semantic_checks", text)
        self.assertIn("challenged_claim", text)
        self.assertIn("drop|downgrade|clarify|narrow|split|abstain", text)
        self.assertNotIn('"candidate_report": {', text)

    def test_phase3_v11_drop_is_materialized_as_disposition_not_reworded_finding(self) -> None:
        report = primary_report()
        payload = phase3_v11_payload(report)
        parsed, error = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(error, "")

        challenge, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V11_PROTOCOL_REVISION,
        )

        self.assertEqual(challenge["accepted_count"], 1)
        self.assertEqual(correction["accepted_count"], 1)
        accepted = correction["accepted_corrections"][0]
        self.assertEqual(accepted["correction_disposition"], "drop")
        self.assertEqual(accepted["after_preview"]["disposition"], "drop")
        self.assertNotIn("severity", accepted["after_preview"])
        self.assertNotIn("blocking", accepted["after_preview"])
        self.assertEqual(summary["correction_disposition_counts"], {"drop": 1})

    def test_phase3_v11_rejects_correction_that_conflicts_with_challenge_action(self) -> None:
        report = primary_report()
        payload = phase3_v11_payload(report, recommended_action="drop", disposition="clarify")
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        _, correction, _ = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V11_PROTOCOL_REVISION,
        )

        self.assertEqual(correction["accepted_count"], 0)
        self.assertIn(
            "challenge_action_disposition_mismatch:drop->clarify",
            correction["rejected_corrections"][0]["validation_reasons"],
        )

    def test_phase3_v11_compatible_interpretation_cannot_be_repackaged_as_clarification(self) -> None:
        report = primary_report()
        payload = phase3_v11_payload(report, recommended_action="clarify", disposition="clarify")
        payload["correction_shadows"][0]["semantic_checks"]["original_claim_still_valid"] = False
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        _, correction, _ = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V11_PROTOCOL_REVISION,
        )

        self.assertEqual(correction["accepted_count"], 0)
        self.assertIn(
            "compatible_interpretation_requires_drop_or_abstain",
            correction["rejected_corrections"][0]["validation_reasons"],
        )
        self.assertIn(
            "clarify_requires_original_claim_still_valid",
            correction["rejected_corrections"][0]["validation_reasons"],
        )

    def test_phase3_v11_downgrade_requires_risk_rewrite_and_human_protected_field_review(self) -> None:
        report = primary_report()
        payload = phase3_v11_payload(
            report,
            challenge_type="overstated",
            recommended_action="demote",
            disposition="downgrade",
        )
        payload["correction_shadows"][0]["proposed_changes"].pop("risk")
        payload["correction_shadows"][0]["semantic_checks"]["protected_fields_need_human_review"] = False
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        _, correction, _ = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V11_PROTOCOL_REVISION,
        )

        reasons = correction["rejected_corrections"][0]["validation_reasons"]
        self.assertIn("downgrade_requires_risk_rewrite", reasons)
        self.assertIn("downgrade_requires_protected_fields_human_review", reasons)

    def test_phase3_v11_reference_or_competitor_evidence_cannot_invent_product_correction(self) -> None:
        report = primary_report()
        payload = phase3_v11_payload(report, recommended_action="clarify", disposition="clarify")
        payload["correction_shadows"][0]["source_provenance"] = "reference_or_competitor"
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        _, correction, _ = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V11_PROTOCOL_REVISION,
        )

        self.assertIn(
            "reference_source_cannot_drive_product_rewrite",
            correction["rejected_corrections"][0]["validation_reasons"],
        )

    def test_phase3_v11_abstain_is_recorded_without_entering_human_correction_queue(self) -> None:
        report = primary_report()
        payload = phase3_v11_payload(report, recommended_action="drop", disposition="abstain")
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        _, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V11_PROTOCOL_REVISION,
        )

        self.assertEqual(correction["accepted_count"], 0)
        self.assertEqual(correction["abstained_count"], 1)
        self.assertEqual(summary["correction_abstained_count"], 1)

    def test_phase3_v12_prompt_contains_fixed_target_inventory_and_ledger(self) -> None:
        report = primary_report()
        messages = build_dual_pass_secondary_messages(
            {
                "document_labels": ["玩法需求.docx", "数值配置.xlsx"],
                "collection_summary": {},
                "document_context": "玩法需求.docx / 表格2；数值配置.xlsx / 表格1",
                "context_truncated": False,
                "public_rules": {},
            },
            report,
            protocol_profile="phase3_v1_2",
        )
        text = json.dumps(messages, ensure_ascii=False)
        self.assertIn("phase3_v1_2", text)
        self.assertIn("target_coverage_ledger", text)
        self.assertIn("config_mapping_conflict", text)
        self.assertIn("人工确认后", text)

    def test_phase3_v12_requires_complete_ordered_target_coverage_ledger(self) -> None:
        report = primary_report()
        payload = phase3_v12_payload(report)
        payload["target_coverage_ledger"] = []
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        challenge, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V12_PROTOCOL_REVISION,
        )

        self.assertFalse(summary["protocol_gate_passed"])
        self.assertFalse(summary["target_coverage_ledger_valid"])
        self.assertEqual(challenge["accepted_count"], 0)
        self.assertEqual(correction["accepted_count"], 0)
        self.assertTrue(any("target_coverage_count_mismatch" in item for item in summary["target_coverage_ledger_errors"]))

    def test_phase3_v12_human_approved_drop_rebuilds_score_reason_and_top_blockers(self) -> None:
        report = primary_report()
        parsed, _ = parse_phase3_review_json(
            json.dumps(phase3_v12_payload(report), ensure_ascii=False)
        )
        _, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V12_PROTOCOL_REVISION,
        )
        self.assertTrue(summary["target_coverage_ledger_valid"])

        revised, audit = apply_human_approved_phase3_corrections(
            report, correction["accepted_corrections"]
        )

        self.assertEqual(revised["document_quality_score"], "A")
        self.assertEqual(revised["top_blockers"], [])
        self.assertIn("未发现会阻塞开发", revised["score_reason"])
        self.assertEqual(
            audit["score_recalculation"]["risk_counts_before"]["high_or_block_dev_count"], 1
        )
        self.assertEqual(
            audit["score_recalculation"]["risk_counts_after"]["high_or_block_dev_count"], 0
        )

    def test_phase3_v12_human_approved_downgrade_changes_signals_before_scoring(self) -> None:
        report = primary_report()
        parsed, _ = parse_phase3_review_json(
            json.dumps(phase3_v12_payload(report, disposition="downgrade"), ensure_ascii=False)
        )
        _, correction, _ = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V12_PROTOCOL_REVISION,
        )

        revised, audit = apply_human_approved_phase3_corrections(
            report, correction["accepted_corrections"]
        )
        finding = revised["dimensions"][0]["findings"][0]
        self.assertEqual(finding["severity"], "中")
        self.assertEqual(finding["blocking"], "阻塞测试用例设计")
        self.assertEqual(revised["document_quality_score"], "B")
        self.assertTrue(audit["score_recalculation"]["score_changed"])

    def test_phase3_v13_prompt_requires_exhaustive_checks_and_fixed_matrix(self) -> None:
        report = primary_report()
        messages = build_dual_pass_secondary_messages(
            {
                "document_labels": ["玩法需求.docx", "数值配置.xlsx"],
                "collection_summary": {},
                "document_context": "玩法需求.docx / 表格2；数值配置.xlsx / 表格1",
                "context_truncated": False,
                "public_rules": {},
            },
            report,
            protocol_profile="phase3_v1_3",
        )
        text = json.dumps(messages, ensure_ascii=False)
        self.assertIn("phase3_v1_3", text)
        self.assertIn("challenge_checks", text)
        self.assertIn("duplicate > multiroot > evidence_mismatch", text)
        self.assertIn("compatible_interpretation=drop", text)
        self.assertIn("confirmed|rejected|uncertain", text)

    def test_phase3_v13_accepts_matrix_derived_challenge(self) -> None:
        report = primary_report()
        parsed, error = parse_phase3_review_json(
            json.dumps(phase3_v13_payload(report), ensure_ascii=False)
        )
        self.assertEqual(error, "")

        challenge, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V13_PROTOCOL_REVISION,
        )

        self.assertTrue(summary["protocol_gate_passed"])
        self.assertTrue(summary["challenge_checks_complete"])
        self.assertTrue(summary["challenge_checks_valid"])
        self.assertEqual(summary["challenge_target_keys"], ["config_mapping_conflict"])
        self.assertEqual(len(summary["challenge_check_keys"]), 6)
        self.assertEqual(challenge["accepted_count"], 1)
        self.assertEqual(correction["accepted_count"], 1)

    def test_phase3_v13_rejects_decision_or_priority_not_derived_from_checks(self) -> None:
        report = primary_report()
        payload = phase3_v13_payload(report)
        payload["target_coverage_ledger"][0]["challenge_checks"]["duplicate"] = "confirmed"
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        challenge, correction, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V13_PROTOCOL_REVISION,
        )

        self.assertFalse(summary["protocol_gate_passed"])
        self.assertFalse(summary["challenge_checks_valid"])
        self.assertEqual(challenge["accepted_count"], 0)
        self.assertEqual(correction["accepted_count"], 0)
        self.assertTrue(
            any("challenge_priority_mismatch" in item for item in summary["challenge_matrix_errors"])
        )

    def test_phase3_v13_rejects_incomplete_challenge_checks(self) -> None:
        report = primary_report()
        payload = phase3_v13_payload(report)
        payload["target_coverage_ledger"][0]["challenge_checks"].pop("overstated")
        parsed, _ = parse_phase3_review_json(json.dumps(payload, ensure_ascii=False))

        _, _, summary = evaluate_phase3_review(
            report,
            parsed,
            document_labels=["玩法需求.docx", "数值配置.xlsx"],
            protocol_revision=PHASE3_V13_PROTOCOL_REVISION,
        )

        self.assertFalse(summary["protocol_gate_passed"])
        self.assertFalse(summary["challenge_checks_complete"])
        self.assertTrue(any("challenge_checks_missing" in item for item in summary["challenge_matrix_errors"]))


if __name__ == "__main__":
    unittest.main()
