from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rad_review.model_client import OpenAICompatibleClient
from rad_review.prompts import DIMENSIONS
from rad_review.secondary_benchmark import (
    build_phase2_acceptance_summary,
    build_phase3_acceptance_summary,
    finalize_secondary_benchmark_annotations,
    reprocess_saved_secondary_responses,
    render_benchmark_markdown,
    root_key,
    run_secondary_benchmark,
    set_overlap,
)
from review import build_parser


def load_internal_summary(run_dir: Path) -> dict:
    return json.loads(
        (run_dir / "_private" / "secondary_benchmark_internal.json").read_text(encoding="utf-8")
    )


def call_artifacts_dir(run_dir: Path, call: dict) -> Path:
    private_output_dir = str(call.get("private_output_dir") or "").strip()
    if private_output_dir:
        return run_dir / private_output_dir / "model_artifacts"
    return run_dir / str(call.get("output_dir") or "") / "model_artifacts"


def empty_report() -> dict:
    return {
        "overall_evaluation": "主流程可理解，但仍需补充边界。",
        "document_quality_score": "B",
        "score_reason": "主流程基本可落地。",
        "top_blockers": [],
        "dimensions": [{"name": name, "dimension_note": "", "findings": []} for name in DIMENSIONS],
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
    }


def secondary_response() -> str:
    return json.dumps(
        {
            "quality_assessment": {
                "summary": "可浏览，但不建议直接替换。",
                "suggestion_level": "medium",
                "ready_for_direct_output": False,
            },
            "candidate_readiness": {
                "ready_for_direct_output": False,
                "reason": "测试回放。",
            },
            "missed_findings": [],
            "unsupported_findings": [],
            "merge_recommendations": [],
            "candidate_lineage": {"kept": [], "added": [], "merged": [], "dropped": []},
            "candidate_report": empty_report(),
            "review_notes": [],
        },
        ensure_ascii=False,
    )


def secondary_response_with_incomplete_addition() -> str:
    payload = json.loads(secondary_response())
    payload["missed_findings"] = [
        {
            "candidate_issue_id": "ADDED_1",
            "title": "通用弱网规则缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "文档没有描述弱网。",
            "evidence": "",
        }
    ]
    return json.dumps(payload, ensure_ascii=False)


def make_source(root: Path) -> Path:
    game = root / "source" / "game_one"
    artifacts = game / "model_artifacts"
    artifacts.mkdir(parents=True)
    shared_input = {
        "document_labels": ["game_one.docx"],
        "collection_summary": "1 document",
        "document_context": "[game_one.docx]\n点击开始后扣费并结算。",
        "context_truncated": False,
        "public_rules": [],
    }
    (artifacts / "shared_review_input.json").write_text(
        json.dumps(shared_input, ensure_ascii=False), encoding="utf-8"
    )
    (artifacts / "primary_review_messages.json").write_text(
        json.dumps([{"role": "user", "content": "frozen"}], ensure_ascii=False), encoding="utf-8"
    )
    (artifacts / "primary_raw_model_response.txt").write_text(
        json.dumps(empty_report(), ensure_ascii=False), encoding="utf-8"
    )
    (artifacts / "run_metadata.json").write_text(
        json.dumps({"review_mode": "dual_pass", "primary_text_model": "primary-model"}), encoding="utf-8"
    )
    (game / "review_report_pipeline.json").write_text(
        json.dumps(
            {
                "report": empty_report(),
                "documents": [
                    {
                        "name": "game_one.docx",
                        "kind": "requirement",
                        "paragraph_count": 1,
                        "table_count": 0,
                        "image_count": 0,
                        "errors": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root / "source"


class SecondaryBenchmarkTests(unittest.TestCase):
    def test_cli_accepts_phase3_v1_directional_profile(self) -> None:
        args = build_parser().parse_args(
            [
                "--secondary-replay-from",
                "reports/source",
                "--secondary-provider",
                "qwen",
                "--secondary-profile",
                "phase3_v1",
            ]
        )
        self.assertEqual(args.secondary_profile, ["phase3_v1"])

    def test_cli_accepts_phase3_v11_correction_convergence_profile(self) -> None:
        args = build_parser().parse_args(
            [
                "--secondary-replay-from",
                "reports/source",
                "--secondary-provider",
                "qwen",
                "--secondary-profile",
                "phase3_v1_1",
            ]
        )
        self.assertEqual(args.secondary_profile, ["phase3_v1_1"])

    def test_cli_accepts_phase3_v12_stability_and_scoring_profile(self) -> None:
        args = build_parser().parse_args(
            [
                "--secondary-replay-from",
                "reports/source",
                "--secondary-provider",
                "qwen",
                "--secondary-profile",
                "phase3_v1_2",
            ]
        )
        self.assertEqual(args.secondary_profile, ["phase3_v1_2"])

    def test_cli_accepts_phase3_v13_challenge_stabilization_profile(self) -> None:
        args = build_parser().parse_args(
            [
                "--secondary-replay-from",
                "reports/source",
                "--secondary-provider",
                "qwen",
                "--secondary-profile",
                "phase3_v1_3",
            ]
        )
        self.assertEqual(args.secondary_profile, ["phase3_v1_3"])

    def test_phase3_v11_replay_materializes_drop_disposition_without_candidate_or_report_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            game_dir = source / "game_one"
            artifacts = game_dir / "model_artifacts"
            report = empty_report()
            finding = {
                "issue_id": "CLOSED_CONFLICT",
                "title": "两个分支概率被误判为冲突",
                "current_state": "命中和不命中分支分别配置0.1与0.05。",
                "evidence": "game_one.docx / 段落1",
                "risk": "程序无法确定配置。",
                "suggestion": "统一概率。",
                "planner_role": "数值策划",
                "confidence": "高",
                "severity": "高",
                "blocking": "阻塞开发",
            }
            report["dimensions"][0]["findings"] = [finding]
            artifacts.joinpath("primary_raw_model_response.txt").write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            game_dir.joinpath("review_report_pipeline.json").write_text(
                json.dumps(
                    {
                        "report": report,
                        "documents": [{"name": "game_one.docx", "kind": "requirement"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
            }

            def phase3_v11_response(messages, **kwargs) -> str:
                del kwargs
                text = json.dumps(messages, ensure_ascii=False)
                match = re.search(r"primary_report_hash=([0-9a-f]{64})", text)
                self.assertIsNotNone(match)
                return json.dumps(
                    {
                        "challenge_findings": [
                            {
                                "challenge_id": "CH-001",
                                "target_issue_id": "CLOSED_CONFLICT",
                                "challenge_type": "compatible_interpretation",
                                "challenged_claim": "两个分支概率直接冲突。",
                                "evidence": "game_one.docx / 段落1",
                                "counterevidence": "两个概率分别属于命中与不命中分支。",
                                "rationale": "分支互斥，不要求取值相同。",
                                "recommended_action": "drop",
                                "proposed_split": [],
                            }
                        ],
                        "correction_shadows": [
                            {
                                "correction_id": "CR-001",
                                "challenge_id": "CH-001",
                                "target_issue_id": "CLOSED_CONFLICT",
                                "correction_disposition": "drop",
                                "source_provenance": "requirement_text",
                                "evidence": "game_one.docx / 段落1",
                                "rationale": "原问题已被分支上下文闭环。",
                                "residual_issue": "",
                                "semantic_checks": {
                                    "compatible_interpretation_exists": True,
                                    "original_claim_still_valid": False,
                                    "residual_issue_exists": False,
                                    "protected_fields_need_human_review": False,
                                },
                                "proposed_changes": {},
                                "replacement_findings": [],
                            }
                        ],
                        "review_notes": [
                            f"protocol_profile=phase3_v1_1; primary_report_hash={match.group(1)}"
                        ],
                    },
                    ensure_ascii=False,
                )

            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(OpenAICompatibleClient, "chat", side_effect=phase3_v11_response),
            ):
                result = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                    protocol_profiles=["phase3_v1_1"],
                )

            self.assertTrue(result.is_complete)
            summary = load_internal_summary(result.run_dir)
            self.assertEqual(summary["phase3_acceptance"]["status"], "pending_human_annotation")
            self.assertTrue(all(call["phase3_protocol_gate_passed"] for call in summary["calls"]))
            self.assertTrue(all(call["phase3_correction_disposition_counts"] == {"drop": 1} for call in summary["calls"]))
            for call in summary["calls"]:
                call_artifacts = call_artifacts_dir(result.run_dir, call)
                shadow = json.loads(
                    (call_artifacts / "secondary_correction_shadow.json").read_text(encoding="utf-8")
                )
                preview = shadow["accepted_corrections"][0]["after_preview"]
                self.assertEqual(preview["disposition"], "drop")
                self.assertNotIn("severity", preview)
                self.assertNotIn("blocking", preview)
                self.assertFalse((call_artifacts / "review_report_candidate.json").exists())
            public_items = json.loads(result.annotation_json_path.read_text(encoding="utf-8"))["items"]
            corrections = [item for item in public_items if item["change_type"] == "correction"]
            self.assertTrue(all(item["correction_disposition"] == "drop" for item in corrections))
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(OpenAICompatibleClient, "chat", side_effect=AssertionError("must not call model")),
            ):
                reprocessed = reprocess_saved_secondary_responses(result.run_dir)
            reprocessed_summary = load_internal_summary(reprocessed.run_dir)
            self.assertTrue(reprocessed.is_complete)
            self.assertTrue(
                all(call["processing_profile"] == "phase3_v1_1" for call in reprocessed_summary["calls"])
            )
            self.assertTrue(
                all(call["phase3_correction_disposition_counts"] == {"drop": 1} for call in reprocessed_summary["calls"])
            )

    def test_phase3_v12_finalize_applies_human_approved_drop_and_recalculates_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            game_dir = source / "game_one"
            artifacts = game_dir / "model_artifacts"
            report = empty_report()
            finding = {
                "issue_id": "FALSE_HIGH_RISK",
                "title": "互斥分支被误判为直接冲突",
                "current_state": "两个互斥分支分别配置不同概率。",
                "evidence": "game_one.docx / 段落1",
                "risk": "被误判为无法实现。",
                "suggestion": "删除误判。",
                "planner_role": "数值策划",
                "confidence": "高",
                "severity": "高",
                "blocking": "阻塞开发",
            }
            report["document_quality_score"] = "C"
            report["score_reason"] = "存在高风险冲突。"
            report["dimensions"][0]["findings"] = [finding]
            report["top_blockers"] = [
                {"severity": "高", "title": finding["title"], "owner": "数值策划", "why_now": finding["risk"]}
            ]
            artifacts.joinpath("primary_raw_model_response.txt").write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            game_dir.joinpath("review_report_pipeline.json").write_text(
                json.dumps(
                    {"report": report, "documents": [{"name": "game_one.docx", "kind": "requirement"}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
            }

            def phase3_v12_response(messages, **kwargs) -> str:
                del kwargs
                text = json.dumps(messages, ensure_ascii=False)
                match = re.search(r"primary_report_hash=([0-9a-f]{64})", text)
                self.assertIsNotNone(match)
                return json.dumps(
                    {
                        "target_coverage_ledger": [
                            {
                                "target_issue_id": "FALSE_HIGH_RISK",
                                "target_order": 1,
                                "decision": "challenge",
                                "challenge_type": "compatible_interpretation",
                                "recommended_action": "drop",
                                "evidence_checked": "game_one.docx / 段落1",
                                "rationale": "互斥分支可同时成立。",
                            }
                        ],
                        "challenge_findings": [
                            {
                                "challenge_id": "CH-FALSE_HIGH_RISK",
                                "target_issue_id": "FALSE_HIGH_RISK",
                                "challenge_type": "compatible_interpretation",
                                "challenged_claim": "两个互斥分支无法并存。",
                                "evidence": "game_one.docx / 段落1",
                                "counterevidence": "分支互斥。",
                                "rationale": "不同分支允许不同概率。",
                                "recommended_action": "drop",
                                "proposed_split": [],
                            }
                        ],
                        "correction_shadows": [
                            {
                                "correction_id": "CR-FALSE_HIGH_RISK",
                                "challenge_id": "CH-FALSE_HIGH_RISK",
                                "target_issue_id": "FALSE_HIGH_RISK",
                                "correction_disposition": "drop",
                                "source_provenance": "requirement_text",
                                "evidence": "game_one.docx / 段落1",
                                "rationale": "原高风险判断不成立。",
                                "residual_issue": "",
                                "semantic_checks": {
                                    "compatible_interpretation_exists": True,
                                    "original_claim_still_valid": False,
                                    "residual_issue_exists": False,
                                    "protected_fields_need_human_review": False,
                                },
                                "proposed_changes": {},
                                "replacement_findings": [],
                            }
                        ],
                        "review_notes": [
                            f"protocol_profile=phase3_v1_2; primary_report_hash={match.group(1)}"
                        ],
                    },
                    ensure_ascii=False,
                )

            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(OpenAICompatibleClient, "chat", side_effect=phase3_v12_response),
            ):
                result = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                    protocol_profiles=["phase3_v1_2"],
                )

            template = json.loads(result.annotation_json_path.read_text(encoding="utf-8"))
            for item in template["items"]:
                for field in (
                    ("target_correct", "valid", "evidence_locatable", "actionable", "should_split")
                    if item["change_type"] == "challenge"
                    else ("target_correct", "accurate", "supported", "safe_to_apply")
                ):
                    item[field] = False if field == "should_split" else True
            result.annotation_json_path.write_text(
                json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            finalized = finalize_secondary_benchmark_annotations(result.run_dir)
            finalized_summary = json.loads(finalized.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(finalized_summary["phase3_acceptance"]["status"], "passed")
            self.assertEqual(finalized_summary["phase3_human_application"]["applied_correction_count"], 2)
            self.assertEqual(finalized_summary["phase3_human_application"]["score_change_count"], 2)
            for call in load_internal_summary(result.run_dir)["calls"]:
                approved_path = call_artifacts_dir(result.run_dir, call) / "review_report_human_approved.json"
                self.assertTrue(approved_path.is_file())
                approved = json.loads(approved_path.read_text(encoding="utf-8"))["report"]
                self.assertEqual(approved["document_quality_score"], "A")
                self.assertEqual(approved["top_blockers"], [])

    def test_phase3_replay_writes_private_advice_shadow_and_keeps_primary_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            game_dir = source / "game_one"
            artifacts = game_dir / "model_artifacts"
            report = empty_report()
            finding = {
                "issue_id": "CONFIG_MIXED",
                "title": "图标命名与筹码档位被合成一个问题",
                "current_state": "两个独立配置对象混在一条 finding。",
                "evidence": "game_one.docx / 段落1",
                "risk": "无法独立分配和验收。",
                "suggestion": "拆成两个 finding。",
                "planner_role": "系统策划",
                "confidence": "高",
                "severity": "高",
                "blocking": "阻塞开发",
            }
            report["dimensions"][0]["findings"] = [finding]
            report["top_blockers"] = [
                {"severity": "高", "title": finding["title"], "owner": "系统策划", "why_now": "阻塞实现"}
            ]
            artifacts.joinpath("primary_raw_model_response.txt").write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            game_dir.joinpath("review_report_pipeline.json").write_text(
                json.dumps(
                    {
                        "report": report,
                        "documents": [
                            {
                                "name": "game_one.docx",
                                "kind": "requirement",
                                "paragraph_count": 1,
                                "table_count": 0,
                                "image_count": 0,
                                "errors": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
            }

            def phase3_response(messages, **kwargs) -> str:
                del kwargs
                text = json.dumps(messages, ensure_ascii=False)
                match = re.search(r"primary_report_hash=([0-9a-f]{64})", text)
                self.assertIsNotNone(match)
                split_items = [
                    {
                        "title": "图标命名不一致",
                        "decision_object": "symbol_naming",
                        "current_state": "图标名未统一。",
                        "evidence": "game_one.docx / 段落1",
                        "risk": "资源映射错误。",
                        "suggestion": "统一图标键。",
                        "planner_role": "系统策划",
                        "acceptance_criteria": "图标键唯一。",
                    },
                    {
                        "title": "筹码档位不一致",
                        "decision_object": "chip_tiers",
                        "current_state": "筹码档位未统一。",
                        "evidence": "game_one.docx / 段落1",
                        "risk": "下注配置错误。",
                        "suggestion": "统一档位表。",
                        "planner_role": "数值策划",
                        "acceptance_criteria": "档位逐项一致。",
                    },
                ]
                return json.dumps(
                    {
                        "challenge_findings": [
                            {
                                "challenge_id": "CH-001",
                                "target_issue_id": "CONFIG_MIXED",
                                "challenge_type": "multiroot",
                                "challenged_claim": "两个配置对象可以共用一个关闭闭环。",
                                "evidence": "game_one.docx / 段落1",
                                "rationale": "对象、责任人与验收标准不同。",
                                "recommended_action": "split",
                                "proposed_split": split_items,
                            }
                        ],
                        "correction_shadows": [
                            {
                                "correction_id": "CR-001",
                                "challenge_id": "CH-001",
                                "target_issue_id": "CONFIG_MIXED",
                                "correction_type": "split",
                                "evidence": "game_one.docx / 段落1",
                                "rationale": "形成两个独立关闭闭环。",
                                "proposed_changes": {},
                                "replacement_findings": split_items,
                            }
                        ],
                        "review_notes": [
                            f"protocol_profile=phase3_v1; primary_report_hash={match.group(1)}"
                        ],
                    },
                    ensure_ascii=False,
                )

            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(OpenAICompatibleClient, "chat", side_effect=phase3_response),
            ):
                result = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                    protocol_profiles=["phase3_v1"],
                )

            self.assertTrue(result.is_complete)
            summary = load_internal_summary(result.run_dir)
            self.assertEqual(summary["phase3_acceptance"]["status"], "pending_human_annotation")
            self.assertTrue(all(item["phase3_protocol_gate_passed"] for item in summary["calls"]))
            self.assertTrue(all(item["phase3_baseline_lock_passed"] for item in summary["calls"]))
            self.assertTrue(all(item["selected_report_owner"] == "primary_locked" for item in summary["calls"]))
            frozen_report = json.loads(
                (
                    result.run_dir
                    / "_private"
                    / "frozen_inputs"
                    / "game_one"
                    / "model_artifacts"
                    / "frozen_primary_report.json"
                ).read_text(encoding="utf-8")
            )
            for call in summary["calls"]:
                call_artifacts = call_artifacts_dir(result.run_dir, call)
                self.assertTrue((call_artifacts / "secondary_challenge_advice.json").is_file())
                self.assertTrue((call_artifacts / "secondary_correction_shadow.json").is_file())
                self.assertFalse((call_artifacts / "review_report_candidate.json").exists())
                saved_report = json.loads((call_artifacts / "review_report.json").read_text(encoding="utf-8"))["report"]
                self.assertEqual(saved_report["document_quality_score"], frozen_report["document_quality_score"])
                self.assertEqual(saved_report["score_reason"], frozen_report["score_reason"])
                self.assertEqual(saved_report["top_blockers"], frozen_report["top_blockers"])
            annotations = json.loads(
                (result.run_dir / "_private" / "human_annotation_internal.json").read_text(encoding="utf-8")
            )["items"]
            self.assertEqual({item["change_type"] for item in annotations}, {"challenge", "correction"})
            self.assertTrue(all(item.get("applied_to_report") is False for item in annotations if item["change_type"] == "correction"))
            public_template_path = result.run_dir / "human_annotation_template.json"
            public_template = json.loads(public_template_path.read_text(encoding="utf-8"))
            for item in public_template["items"]:
                if item["change_type"] == "challenge":
                    for field in ("target_correct", "valid", "evidence_locatable", "actionable", "should_split"):
                        item[field] = True
                else:
                    for field in ("target_correct", "accurate", "supported", "safe_to_apply"):
                        item[field] = True
            public_template_path.write_text(
                json.dumps(public_template, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            finalized = finalize_secondary_benchmark_annotations(result.run_dir)
            self.assertEqual(finalized.annotated_item_count, 4)
            finalized_summary = json.loads(finalized.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(finalized_summary["phase3_acceptance"]["status"], "passed")
            self.assertTrue(finalized_summary["phase3_acceptance"]["eligible_for_next_stage"])
            with (
                patch.dict(os.environ, env, clear=False),
                patch.object(OpenAICompatibleClient, "chat", side_effect=AssertionError("must not call model")),
            ):
                reprocessed = reprocess_saved_secondary_responses(result.run_dir)
            self.assertTrue(reprocessed.is_complete)
            reprocessed_summary = load_internal_summary(reprocessed.run_dir)
            self.assertTrue(all(item.get("reprocessed_saved_raw") for item in reprocessed_summary["calls"]))
            self.assertTrue(all(item.get("phase3_baseline_lock_passed") for item in reprocessed_summary["calls"]))

    def test_phase3_acceptance_requires_human_precision_after_machine_locks_pass(self) -> None:
        summary = {
            "calls": [
                {
                    "variant_id": "A",
                    "protocol_profile": "phase3_v1",
                    "processing_profile": "phase3_v1",
                    "status": "completed",
                    "phase3_protocol_gate_passed": True,
                    "phase3_baseline_lock_passed": True,
                    "selected_report_owner": "primary_locked",
                    "materialized_added_count": 0,
                    "unsupported_severity_change_count": 0,
                    "unsupported_blocking_change_count": 0,
                }
                for _ in range(10)
            ],
            "fairness_invariants": {"passed": True},
            "human_metrics": {"status": "pending_human_annotation"},
        }
        pending = build_phase3_acceptance_summary(summary)
        self.assertEqual(pending["status"], "pending_human_annotation")
        self.assertTrue(pending["checks"]["baseline_lock_pass_rate"]["passed"])

        summary["human_metrics"] = {
            "status": "completed",
            "phase3": {
                "challenge_count": 10,
                "challenge_target_correct_rate": 1.0,
                "challenge_evidence_locatable_rate": 1.0,
                "challenge_precision": 0.8,
                "correction_count": 10,
                "correction_target_correct_rate": 1.0,
                "correction_supported_rate": 1.0,
                "correction_accuracy_rate": 0.9,
            },
        }
        passed = build_phase3_acceptance_summary(summary)
        self.assertEqual(passed["status"], "passed")
        self.assertTrue(passed["eligible_for_next_stage"])

    def test_phase3_v12_acceptance_requires_ledger_and_repeat_stability(self) -> None:
        summary = {
            "calls": [
                {
                    "variant_id": "A",
                    "game": f"game_{index // 2}",
                    "repeat": index % 2 + 1,
                    "protocol_profile": "phase3_v1_2",
                    "processing_profile": "phase3_v1_2",
                    "status": "completed",
                    "phase3_protocol_gate_passed": True,
                    "phase3_baseline_lock_passed": True,
                    "phase3_target_coverage_ledger_complete": True,
                    "phase3_target_coverage_ledger_valid": True,
                    "selected_report_owner": "primary_locked",
                    "materialized_added_count": 0,
                }
                for index in range(10)
            ],
            "fairness_invariants": {"passed": True},
            "stability_comparison": [
                {
                    "variant_id": "A",
                    "game": f"game_{index}",
                    "phase3_target_decision_overlap": 0.8,
                    "phase3_challenge_overlap": 0.5,
                    "phase3_correction_overlap": 0.5,
                }
                for index in range(5)
            ],
            "human_metrics": {
                "status": "completed",
                "phase3": {
                    "challenge_count": 10,
                    "challenge_target_correct_rate": 1.0,
                    "challenge_evidence_locatable_rate": 1.0,
                    "challenge_precision": 1.0,
                    "correction_count": 10,
                    "correction_target_correct_rate": 1.0,
                    "correction_supported_rate": 1.0,
                    "correction_accuracy_rate": 1.0,
                },
            },
        }

        passed = build_phase3_acceptance_summary(summary)
        self.assertEqual(passed["status"], "passed")
        self.assertTrue(passed["checks"]["target_coverage_ledger_valid_rate"]["passed"])
        self.assertTrue(passed["checks"]["target_decision_overlap"]["passed"])

        summary["stability_comparison"][0]["phase3_target_decision_overlap"] = 0.0
        failed = build_phase3_acceptance_summary(summary)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("target_decision_overlap", failed["blocking_reasons"])

    def test_phase3_v13_acceptance_requires_complete_matrix_and_check_stability(self) -> None:
        summary = {
            "calls": [
                {
                    "variant_id": "A",
                    "game": f"game_{index // 2}",
                    "repeat": index % 2 + 1,
                    "protocol_profile": "phase3_v1_3",
                    "processing_profile": "phase3_v1_3",
                    "status": "completed",
                    "phase3_protocol_gate_passed": True,
                    "phase3_baseline_lock_passed": True,
                    "phase3_target_coverage_ledger_complete": True,
                    "phase3_target_coverage_ledger_valid": True,
                    "phase3_challenge_checks_complete": True,
                    "phase3_challenge_checks_valid": True,
                    "selected_report_owner": "primary_locked",
                    "materialized_added_count": 0,
                }
                for index in range(10)
            ],
            "fairness_invariants": {"passed": True},
            "stability_comparison": [
                {
                    "variant_id": "A",
                    "game": f"game_{index}",
                    "phase3_target_decision_overlap": 0.8,
                    "phase3_challenge_overlap": 0.5,
                    "phase3_correction_overlap": 0.5,
                    "phase3_challenge_target_overlap": 0.5,
                    "phase3_challenge_check_overlap": 0.8,
                }
                for index in range(5)
            ],
            "human_metrics": {
                "status": "completed",
                "phase3": {
                    "challenge_count": 10,
                    "challenge_target_correct_rate": 1.0,
                    "challenge_evidence_locatable_rate": 1.0,
                    "challenge_precision": 1.0,
                    "correction_count": 10,
                    "correction_target_correct_rate": 1.0,
                    "correction_supported_rate": 1.0,
                    "correction_accuracy_rate": 1.0,
                },
            },
        }

        passed = build_phase3_acceptance_summary(summary)
        self.assertEqual(passed["status"], "passed")
        self.assertTrue(passed["checks"]["challenge_checks_complete_rate"]["passed"])
        self.assertTrue(passed["checks"]["challenge_check_overlap"]["passed"])

        summary["calls"][0]["phase3_challenge_checks_valid"] = False
        summary["stability_comparison"][0]["phase3_challenge_check_overlap"] = 0.0
        failed = build_phase3_acceptance_summary(summary)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("challenge_checks_valid_rate", failed["blocking_reasons"])
        self.assertIn("challenge_check_overlap", failed["blocking_reasons"])

    def test_phase3_markdown_does_not_label_challenge_items_as_added_findings(self) -> None:
        markdown = render_benchmark_markdown(
            {
                "completion": {},
                "fairness_invariants": {},
                "phase3_acceptance": {"applicable": True, "checks": {}},
                "variant_metrics": [
                    {
                        "variant_id": "A",
                        "completed_calls": 2,
                        "expected_calls": 2,
                        "phase3_protocol_gate_pass_rate": 1.0,
                        "phase3_baseline_lock_pass_rate": 1.0,
                        "average_phase3_challenge_accepted_count": 1.5,
                        "average_phase3_correction_accepted_count": 0.5,
                        "average_phase3_correction_abstained_count": 0.0,
                        "minimum_primary_top_blocker_retention": 1.0,
                    }
                ],
                "stability_comparison": [
                    {
                        "variant_id": "A",
                        "game": "demo",
                        "phase3_challenge_overlap": 0.5,
                        "phase3_correction_overlap": 1.0,
                        "top_blocker_overlap": 1.0,
                    }
                ],
                "human_metrics": {
                    "status": "completed",
                    "annotated_item_count": 4,
                    "variants": [{"variant_id": "A", "annotated_added_finding_count": 0}],
                    "phase3": {
                        "challenge_count": 3,
                        "correction_count": 1,
                        "challenge_precision": 1.0,
                        "correction_accuracy_rate": 1.0,
                    },
                },
            }
        )

        self.assertIn("已标注 Phase3 审核项：4", markdown)
        self.assertIn("## Phase3 变体汇总", markdown)
        self.assertIn("## Phase3 复跑稳定性", markdown)
        self.assertIn("| A | demo | - | - | - | 50.0% | 100.0% | 100.0% |", markdown)
        self.assertNotIn("已标注新增问题：4", markdown)
        self.assertNotIn("| A | 0 | 0 |", markdown)
        self.assertNotIn("Candidate 通过率", markdown)

    def test_phase2_acceptance_gate_requires_machine_human_and_stability_thresholds(self) -> None:
        summary = {
            "calls": [
                {"variant_id": "A", "protocol_profile": "phase2", "processing_profile": "phase2", "status": "completed"}
                for _ in range(10)
            ],
            "fairness_invariants": {"passed": True},
            "variant_metrics": [
                {
                    "variant_id": "A",
                    "average_field_completeness": 0.95,
                    "average_admitted_field_completeness": 1.0,
                    "average_coverage_ledger_completeness": 1.0,
                    "coverage_ledger_valid_rate": 1.0,
                    "coverage_schema_v2_rate": 1.0,
                    "candidate_gate_pass_rate": 0.9,
                    "minimum_primary_top_blocker_retention": 0.6667,
                    "multiroot_finding_count": 0,
                    "preserved_primary_multiroot_finding_count": 0,
                    "unsupported_severity_change_count": 0,
                    "unsupported_blocking_change_count": 0,
                    "lineage_mismatch_count": 0,
                    "materialization_mismatch_count": 0,
                    "major_judgment_drift_count": 0,
                }
            ],
            "stability_comparison": [
                {"variant_id": "A", "game": f"game_{index}", "high_added_root_overlap": value}
                for index, value in enumerate((1.0, 0.25, 0.0, 0.0, 0.0), start=1)
            ],
            "human_metrics": {
                "status": "completed",
                "variants": [
                    {
                        "variant_id": "A",
                        "admitted_added_finding_count": 10,
                        "admitted_valid_added_finding_count": 10,
                        "admitted_high_value_added_count": 5,
                        "admitted_duplicate_add_rate": 0.1,
                        "admitted_unsupported_count": 0,
                        "admitted_overstated_count": 0,
                        "admitted_multiroot_count": 0,
                    }
                ],
            },
        }

        acceptance = build_phase2_acceptance_summary(summary)

        self.assertEqual(acceptance["status"], "passed")
        self.assertTrue(acceptance["eligible_for_next_stage"])
        self.assertEqual(acceptance["checks"]["high_added_root_overlap"]["observed"], 0.25)
        self.assertEqual(acceptance["checks"]["high_added_root_overlap"]["target"], ">=0.25")

        for call in summary["calls"]:
            call["coverage_protocol_revision"] = "phase2_v2_1"
        summary["variant_metrics"][0]["coverage_evidence_packet_echo_rate"] = 1.0
        v21_passed = build_phase2_acceptance_summary(summary)
        self.assertTrue(v21_passed["checks"]["coverage_evidence_packet_echo_rate"]["passed"])

        for call in summary["calls"]:
            call["coverage_protocol_revision"] = "phase2_v2_2"
        summary["variant_metrics"][0].update(
            {
                "phase2_protocol_gate_pass_rate": 1.0,
                "phase2_delta_only_compliance_rate": 1.0,
                "deterministic_candidate_generation_rate": 1.0,
            }
        )
        v22_passed = build_phase2_acceptance_summary(summary)
        self.assertTrue(v22_passed["eligible_for_next_stage"])
        summary["variant_metrics"][0]["phase2_delta_only_compliance_rate"] = 0.9
        v22_failed = build_phase2_acceptance_summary(summary)
        self.assertIn("phase2_delta_only_compliance_rate", v22_failed["blocking_reasons"])
        summary["variant_metrics"][0]["phase2_delta_only_compliance_rate"] = 1.0

        summary["variant_metrics"][0]["coverage_evidence_packet_echo_rate"] = 0.9
        v21_failed = build_phase2_acceptance_summary(summary)
        self.assertEqual(v21_failed["status"], "failed")
        self.assertIn("coverage_evidence_packet_echo_rate", v21_failed["blocking_reasons"])
        summary["variant_metrics"][0]["coverage_evidence_packet_echo_rate"] = 1.0

        summary["variant_metrics"][0]["coverage_ledger_valid_rate"] = 0.9
        failed = build_phase2_acceptance_summary(summary)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("coverage_ledger_valid_rate", failed["blocking_reasons"])

        summary["variant_metrics"][0]["coverage_ledger_valid_rate"] = 1.0
        summary["human_metrics"] = {"status": "pending_human_annotation"}
        pending = build_phase2_acceptance_summary(summary)
        self.assertEqual(pending["status"], "pending_human_annotation")
        self.assertIn("human_admitted_precision", pending["pending_reasons"])

    def test_stability_keys_ignore_temporary_missed_ids_and_empty_overlap_is_not_applicable(self) -> None:
        left = {"issue_id": "MISSED_01", "title": "结算规则缺失"}
        same_root = {"issue_id": "MISSED_99", "title": "结算规则缺失"}
        different_root = {"issue_id": "MISSED_01", "title": "断线恢复规则缺失"}

        self.assertEqual(root_key(left), root_key(same_root))
        self.assertNotEqual(root_key(left), root_key(different_root))
        self.assertIsNone(set_overlap([set(), set()]))

    def test_phase2_stability_key_uses_fixed_control_identity(self) -> None:
        first = {
            "issue_id": "FUNDS_01",
            "audit_key": "funds_deduction_payout",
            "control_key": "debit_timing",
            "title": "玩家本金扣款节点未定义",
        }
        second = {
            "issue_id": "DEBIT_TIMING_MISSING",
            "audit_key": "funds_deduction_payout",
            "control_key": "debit_timing",
            "title": "下注扣款时机未明确",
        }

        self.assertEqual(root_key(first), root_key(second))

    def test_cli_accepts_secondary_replay_arguments(self) -> None:
        args = build_parser().parse_args(
            [
                "--secondary-replay-from",
                "reports/source",
                "--secondary-provider",
                "qwen",
                "--secondary-provider",
                "deepseek",
                "--secondary-repeats",
                "3",
            ]
        )
        self.assertEqual(args.secondary_replay_from, "reports/source")
        self.assertEqual(args.secondary_provider, ["qwen", "deepseek"])
        self.assertEqual(args.secondary_repeats, 3)

    def test_cli_accepts_same_provider_protocol_profile_ab(self) -> None:
        args = build_parser().parse_args(
            [
                "--secondary-replay-from",
                "reports/source",
                "--secondary-provider",
                "qwen",
                "--secondary-profile",
                "baseline",
                "--secondary-profile",
                "phase2",
                "--secondary-reprocess-profile",
                "phase2",
            ]
        )
        self.assertEqual(args.secondary_provider, ["qwen"])
        self.assertEqual(args.secondary_profile, ["baseline", "phase2"])
        self.assertEqual(args.secondary_reprocess_profile, "phase2")

    def test_same_qwen_protocol_profiles_change_only_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(OpenAICompatibleClient, "chat", return_value=secondary_response()) as mock_chat,
            ):
                result = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                    protocol_profiles=["baseline", "phase2"],
                )

            self.assertTrue(result.is_complete)
            self.assertEqual(mock_chat.call_count, 4)
            summary = load_internal_summary(result.run_dir)
            self.assertEqual(summary["design"]["comparison_axis"], "protocol_profile")
            self.assertTrue(summary["fairness_invariants"]["passed"])
            self.assertTrue(summary["fairness_invariants"]["only_protocol_profile_varies"])
            self.assertTrue(summary["fairness_invariants"]["only_intended_variable_varies"])
            self.assertEqual(len({item["provider_config_hash"] for item in summary["calls"]}), 1)
            hashes_by_variant = {
                variant: {item["secondary_message_hash"] for item in summary["calls"] if item["variant_id"] == variant}
                for variant in ("A", "B")
            }
            self.assertTrue(all(len(values) == 1 for values in hashes_by_variant.values()))
            self.assertNotEqual(hashes_by_variant["A"], hashes_by_variant["B"])

            mapping = json.loads((result.run_dir / "_private" / "provider_mapping.json").read_text(encoding="utf-8"))
            self.assertEqual({item["requested_provider"] for item in mapping["variants"]}, {"qwen"})
            self.assertEqual({item["protocol_profile"] for item in mapping["variants"]}, {"baseline", "phase2"})
            public_fragments: list[str] = []
            for path in result.run_dir.rglob("*"):
                if not path.is_file() or "_private" in path.parts:
                    continue
                try:
                    public_fragments.append(path.read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    continue
            public_batch_text = "\n".join(public_fragments).lower()
            for marker in (
                "protocol_profile",
                "processing_profile",
                "phase2_variant_ids",
                "phase2_v2_2",
                "evidence_packet_id",
                "qwen-model",
            ):
                self.assertNotIn(marker, public_batch_text, marker)

    def test_phase2_evidence_packet_id_is_echoed_and_measured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
            }

            def echo_evidence_packet(messages, **kwargs) -> str:
                del kwargs
                prompt_text = json.dumps(messages, ensure_ascii=False)
                match = re.search(r"evidence_packet_id=([0-9a-f]{64})", prompt_text)
                self.assertIsNotNone(match)
                payload = json.loads(secondary_response())
                payload.pop("candidate_report", None)
                payload.pop("candidate_lineage", None)
                payload.pop("candidate_readiness", None)
                payload["review_notes"] = [
                    f"protocol_profile=phase2_v2_2; evidence_packet_id={match.group(1)}"
                ]
                return json.dumps(payload, ensure_ascii=False)

            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(OpenAICompatibleClient, "chat", side_effect=echo_evidence_packet),
            ):
                result = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                    protocol_profiles=["phase2"],
                )

            summary = load_internal_summary(result.run_dir)
            self.assertTrue(result.is_complete)
            self.assertTrue(all(item["coverage_evidence_packet_echoed"] for item in summary["calls"]))
            self.assertEqual(summary["variant_metrics"][0]["coverage_evidence_packet_echo_rate"], 1.0)
            self.assertEqual(summary["variant_metrics"][0]["phase2_delta_only_compliance_rate"], 1.0)
            self.assertEqual(summary["variant_metrics"][0]["deterministic_candidate_generation_rate"], 1.0)
            self.assertEqual(
                {item["coverage_protocol_revision"] for item in summary["calls"]},
                {"phase2_v2_2"},
            )
            for item in summary["calls"]:
                packet_path = call_artifacts_dir(result.run_dir, item) / "phase2_control_evidence_packet.json"
                packet = json.loads(packet_path.read_text(encoding="utf-8"))
                self.assertEqual(packet["evidence_packet_id"], item["coverage_evidence_packet_id"])
                self.assertEqual(len(packet["cards"]), 12)

    def test_frozen_primary_benchmark_pairs_every_secondary_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
                "AI_PROVIDER_DEEPSEEK_BASE_URL": "http://deepseek.test",
                "AI_PROVIDER_DEEPSEEK_API_KEY": "deepseek-key",
                "AI_PROVIDER_DEEPSEEK_MODEL": "deepseek-model",
                "AI_PROVIDER_DEEPSEEK_WIRE_API": "responses",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: values.reverse()),
                patch.object(OpenAICompatibleClient, "chat", return_value=secondary_response()) as mock_chat,
            ):
                result = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen", "deepseek"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                )

            self.assertTrue(result.is_complete)
            self.assertEqual(result.expected_calls, 4)
            self.assertEqual(result.completed_calls, 4)
            self.assertEqual(mock_chat.call_count, 4)

            summary = load_internal_summary(result.run_dir)
            self.assertEqual(summary["design"]["primary_calls"], 0)
            self.assertEqual(summary["design"]["vision_calls"], 0)
            self.assertTrue(summary["completion"]["all_calls_paired"])
            self.assertTrue(summary["fairness_invariants"]["passed"])
            self.assertTrue(summary["fairness_invariants"]["only_secondary_provider_varies"])
            self.assertEqual({item["variant_id"] for item in summary["calls"]}, {"A", "B"})
            self.assertEqual(len({item["primary_report_hash"] for item in summary["calls"]}), 1)
            self.assertEqual(len({item["secondary_message_hash"] for item in summary["calls"]}), 1)

            public_text = result.summary_json_path.read_text(encoding="utf-8").lower()
            self.assertNotIn("qwen-model", public_text)
            self.assertNotIn("deepseek-model", public_text)
            self.assertNotIn("protocol_profile", public_text)
            self.assertNotIn("processing_profile", public_text)
            self.assertNotIn("phase2_variant_ids", public_text)
            self.assertFalse(
                (result.run_dir / "blinded" / "A" / "game_one" / "repeat_01" / "model_artifacts").exists()
            )
            mapping = json.loads((result.run_dir / "_private" / "provider_mapping.json").read_text(encoding="utf-8"))
            self.assertEqual([item["requested_provider"] for item in mapping["variants"]], ["deepseek", "qwen"])
            self.assertEqual([item["variant_id"] for item in mapping["variants"]], ["A", "B"])
            self.assertTrue(
                (
                    result.run_dir
                    / "_private"
                    / "frozen_inputs"
                    / "game_one"
                    / "model_artifacts"
                    / "frozen_primary_report.json"
                ).is_file()
            )
            self.assertTrue((result.run_dir / "human_annotation_template.json").is_file())

    def test_phase_one_requires_two_repeats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            with self.assertRaisesRegex(ValueError, "at least 2"):
                run_secondary_benchmark(source, root / "reports", ["qwen", "deepseek"], repeats=1)

    def test_reprocess_saved_responses_rebuilds_batch_without_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
                "AI_PROVIDER_DEEPSEEK_BASE_URL": "http://deepseek.test",
                "AI_PROVIDER_DEEPSEEK_API_KEY": "deepseek-key",
                "AI_PROVIDER_DEEPSEEK_MODEL": "deepseek-model",
                "AI_PROVIDER_DEEPSEEK_WIRE_API": "responses",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(
                    OpenAICompatibleClient,
                    "chat",
                    side_effect=["not json", secondary_response(), secondary_response(), secondary_response()],
                ),
            ):
                initial = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen", "deepseek"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                )

            self.assertEqual(initial.completed_calls, 3)
            initial_summary = load_internal_summary(initial.run_dir)
            failed_call = next(
                item
                for item in initial_summary["calls"]
                if item["variant_id"] == "A" and item["game"] == "game_one" and item["repeat"] == 1
            )
            failed_raw = call_artifacts_dir(initial.run_dir, failed_call) / "secondary_raw_model_response.txt"
            failed_raw.write_text(secondary_response(), encoding="utf-8")
            source_summary_before = initial.summary_json_path.read_text(encoding="utf-8")

            with patch.dict(os.environ, env, clear=False):
                with patch.object(OpenAICompatibleClient, "chat", side_effect=AssertionError("must not call model")):
                    resumed = reprocess_saved_secondary_responses(initial.run_dir)

            self.assertTrue(resumed.is_complete)
            self.assertNotEqual(resumed.run_dir, initial.run_dir)
            self.assertEqual(initial.summary_json_path.read_text(encoding="utf-8"), source_summary_before)
            self.assertTrue((resumed.run_dir / "reprocess_manifest.json").is_file())
            summary = load_internal_summary(resumed.run_dir)
            repaired = next(
                item
                for item in summary["calls"]
                if item["variant_id"] == "A" and item["game"] == "game_one" and item["repeat"] == 1
            )
            self.assertTrue(repaired["reprocessed_saved_raw"])
            self.assertEqual(repaired["attempt_count"], 0)
            self.assertTrue(all(item["reprocessed_saved_raw"] for item in summary["calls"]))

    def test_reprocess_phase2_profile_applies_admission_without_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
                "AI_PROVIDER_DEEPSEEK_BASE_URL": "http://deepseek.test",
                "AI_PROVIDER_DEEPSEEK_API_KEY": "deepseek-key",
                "AI_PROVIDER_DEEPSEEK_MODEL": "deepseek-model",
                "AI_PROVIDER_DEEPSEEK_WIRE_API": "responses",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(OpenAICompatibleClient, "chat", return_value=secondary_response_with_incomplete_addition()),
            ):
                initial = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                    protocol_profiles=["phase2"],
                )

            with patch.dict(os.environ, env, clear=False):
                with (
                    patch.object(OpenAICompatibleClient, "chat", side_effect=AssertionError("must not call model")),
                    patch(
                        "rad_review.secondary_benchmark.build_phase2_control_evidence_packet",
                        side_effect=AssertionError("must reuse saved evidence packet"),
                    ),
                ):
                    reprocessed = reprocess_saved_secondary_responses(initial.run_dir, processing_profile="phase2")

            self.assertTrue(reprocessed.is_complete)
            summary = load_internal_summary(reprocessed.run_dir)
            self.assertEqual(summary["design"]["reprocessed_with_profile"], "phase2")
            self.assertTrue(all(item["processing_profile"] == "phase2" for item in summary["calls"]))
            self.assertTrue(
                all(
                    item["candidate_generation_mode"]
                    == "deterministic_primary_plus_admitted_delta"
                    for item in summary["calls"]
                )
            )
            self.assertTrue(all(item["rejected_added_count"] == 1 for item in summary["calls"]))
            self.assertTrue(all(item["materialized_added_count"] == 0 for item in summary["calls"]))
            template = json.loads(
                (reprocessed.run_dir / "_private" / "human_annotation_internal.json").read_text(encoding="utf-8")
            )
            self.assertTrue(all(item["added_admission_status"] == "rejected" for item in template["items"]))
            self.assertTrue(all("root_cause_count" in item for item in template["items"]))
            self.assertTrue(all("root_causes" in item for item in template["items"]))
            self.assertTrue(all("audit_key" in item for item in template["items"]))
            for item in summary["calls"]:
                source_packet = call_artifacts_dir(initial.run_dir, item) / "phase2_control_evidence_packet.json"
                derived_packet = call_artifacts_dir(reprocessed.run_dir, item) / "phase2_control_evidence_packet.json"
                self.assertEqual(
                    json.loads(derived_packet.read_text(encoding="utf-8"))["evidence_packet_id"],
                    json.loads(source_packet.read_text(encoding="utf-8"))["evidence_packet_id"],
                )

    def test_reprocess_preserves_legacy_phase2_prompt_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_source(root)
            env = {
                "AI_PROVIDER_QWEN_BASE_URL": "http://qwen.test",
                "AI_PROVIDER_QWEN_API_KEY": "qwen-key",
                "AI_PROVIDER_QWEN_MODEL": "qwen-model",
                "AI_PROVIDER_QWEN_WIRE_API": "responses",
            }
            with (
                patch.dict(os.environ, env, clear=False),
                patch("rad_review.secondary_benchmark.secrets.SystemRandom.shuffle", side_effect=lambda values: None),
                patch.object(OpenAICompatibleClient, "chat", return_value=secondary_response()),
            ):
                initial = run_secondary_benchmark(
                    source,
                    root / "reports",
                    ["qwen"],
                    repeats=2,
                    timeout=10,
                    model_retries=0,
                    protocol_profiles=["phase2"],
                )

            legacy_messages = [{"role": "system", "content": "phase2 legacy frozen prompt"}]
            for repeat_index in (1, 2):
                initial_summary = load_internal_summary(initial.run_dir)
                saved_call = next(
                    item
                    for item in initial_summary["calls"]
                    if item["variant_id"] == "A" and item["game"] == "game_one" and item["repeat"] == repeat_index
                )
                messages_path = call_artifacts_dir(initial.run_dir, saved_call) / "secondary_review_messages.json"
                messages_path.write_text(json.dumps(legacy_messages, ensure_ascii=False), encoding="utf-8")

            with patch.dict(os.environ, env, clear=False):
                with patch.object(OpenAICompatibleClient, "chat", side_effect=AssertionError("must not call model")):
                    reprocessed = reprocess_saved_secondary_responses(initial.run_dir)

            summary = load_internal_summary(reprocessed.run_dir)
            self.assertEqual(
                {item["coverage_protocol_revision"] for item in summary["calls"]},
                {"phase2_legacy"},
            )
            self.assertEqual(
                summary["phase2_acceptance"]["checks"]["coverage_evidence_packet_echo_rate"]["observed"],
                "legacy_not_required",
            )
            for item in summary["calls"]:
                artifacts = call_artifacts_dir(reprocessed.run_dir, item)
                self.assertEqual(
                    json.loads((artifacts / "secondary_review_messages.json").read_text(encoding="utf-8")),
                    legacy_messages,
                )
                self.assertFalse((artifacts / "phase2_control_evidence_packet.json").exists())

    def test_annotation_finalization_requires_complete_blind_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            benchmark = Path(tmp)
            summary = {
                "design": {"expected_secondary_calls": 4, "primary_calls": 0, "vision_calls": 0},
                "completion": {"completed_secondary_calls": 4, "failed_secondary_calls": 0, "all_calls_paired": True},
                "fairness_invariants": {"passed": True, "only_secondary_provider_varies": True},
                "blinding": {"annotation_status": "pending_human_review"},
                "variant_metrics": [],
            }
            item = {
                "annotation_id": "A-game-R01-A001",
                "variant_id": "A",
                "game": "game",
                "repeat": 1,
                "title": "结算规则缺失",
                "severity": "高",
                "blocking": "阻塞开发",
                "added_admission_status": "admitted",
            }
            for field in ("valid", "duplicate", "unsupported", "overstated", "understated", "multiroot", "actionable"):
                item[field] = None
            (benchmark / "secondary_benchmark_summary.json").write_text(
                json.dumps(summary, ensure_ascii=False), encoding="utf-8"
            )
            template_path = benchmark / "human_annotation_template.json"
            template_path.write_text(json.dumps({"items": [item]}, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Human annotation is incomplete"):
                finalize_secondary_benchmark_annotations(benchmark)

            item.update(
                {
                    "valid": True,
                    "duplicate": False,
                    "unsupported": False,
                    "overstated": False,
                    "understated": False,
                    "multiroot": False,
                    "actionable": True,
                }
            )
            template_path.write_text(json.dumps({"items": [item]}, ensure_ascii=False), encoding="utf-8")
            result = finalize_secondary_benchmark_annotations(benchmark)

            self.assertEqual(result.annotated_item_count, 1)
            results = json.loads(result.results_path.read_text(encoding="utf-8"))
            self.assertEqual(results["metrics"]["valid_added_finding_count"], 1)
            self.assertEqual(results["metrics"]["high_value_added_count"], 1)
            self.assertEqual(results["metrics"]["duplicate_add_rate"], 0.0)
            self.assertEqual(results["metrics"]["admitted_added_finding_precision"], 1.0)
            self.assertEqual(results["metrics"]["admitted_high_value_added_count"], 1)
            self.assertEqual(results["metrics"]["valid_recall_after_admission"], 1.0)

    def test_annotation_finalization_rejects_incomplete_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            benchmark = Path(tmp)
            (benchmark / "secondary_benchmark_summary.json").write_text(
                json.dumps(
                    {
                        "design": {"expected_secondary_calls": 20},
                        "completion": {
                            "completed_secondary_calls": 0,
                            "failed_secondary_calls": 20,
                            "all_calls_paired": False,
                        },
                        "fairness_invariants": {"passed": True, "only_secondary_provider_varies": True},
                    }
                ),
                encoding="utf-8",
            )
            (benchmark / "human_annotation_template.json").write_text(
                json.dumps({"items": []}), encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "all Secondary calls are paired: 0/20"):
                finalize_secondary_benchmark_annotations(benchmark)

    def test_annotation_finalization_accepts_separate_decision_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            benchmark = Path(tmp)
            (benchmark / "secondary_benchmark_summary.json").write_text(
                json.dumps(
                    {
                        "design": {"expected_secondary_calls": 1},
                        "completion": {"completed_secondary_calls": 1, "failed_secondary_calls": 0, "all_calls_paired": True},
                        "fairness_invariants": {"passed": True, "only_secondary_provider_varies": True},
                        "blinding": {"annotation_status": "pending_human_review"},
                        "variant_metrics": [],
                    }
                ),
                encoding="utf-8",
            )
            template_item = {"annotation_id": "A-game-R01-A001", "variant_id": "A", "severity": "中"}
            for field in ("valid", "duplicate", "unsupported", "overstated", "understated", "multiroot", "actionable"):
                template_item[field] = None
            (benchmark / "human_annotation_template.json").write_text(
                json.dumps({"items": [template_item]}), encoding="utf-8"
            )
            decision = {
                "annotation_id": "A-game-R01-A001",
                "valid": True,
                "duplicate": False,
                "unsupported": False,
                "overstated": False,
                "understated": False,
                "multiroot": False,
                "actionable": True,
                "reviewer_notes": "blind review",
            }
            (benchmark / "human_annotation_decisions.json").write_text(
                json.dumps({"items": [decision]}), encoding="utf-8"
            )

            result = finalize_secondary_benchmark_annotations(benchmark)
            payload = json.loads(result.results_path.read_text(encoding="utf-8"))

            self.assertEqual(payload["decision_source"], "human_annotation_decisions.json")
            self.assertEqual(payload["items"][0]["reviewer_notes"], "blind review")


if __name__ == "__main__":
    unittest.main()
