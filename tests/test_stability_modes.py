from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rad_review.docx_reader import ParsedDocument, ParagraphBlock
from rad_review.agent import ReviewAgent
from rad_review.model_client import ModelConfig, OpenAICompatibleClient
from rad_review.prompts import DIMENSIONS, build_audit_messages
from rad_review.reporting.ingest import parse_audit_json, parse_model_json
from rad_review.reporting.modes import (
    build_report_diff_payload,
    merge_audit_report,
    merge_secondary_review_report,
)
from rad_review.reporting.normalize import normalize_report
from tests.test_report import (
    assert_cross_issues_not_misplaced,
    assert_no_empty_public_finding_fields,
    assert_top_blockers_have_matching_findings,
)
from review import build_parser, probe_text_model


def make_doc(name: str = "稳定性需求文档.docx", kind: str = "requirement") -> ParsedDocument:
    return ParsedDocument(
        path=name,
        name=name,
        kind=kind,
        paragraphs=[ParagraphBlock(index=1, text="点击开始后扣款，结算时发奖。")],
        tables=[],
        images=[],
        errors=[],
    )


def empty_report() -> dict:
    return {
        "overall_evaluation": "主流程可理解，但仍需补充边界。",
        "document_quality_score": "B",
        "score_reason": "",
        "dimensions": [{"name": dimension, "dimension_note": "", "findings": []} for dimension in DIMENSIONS],
        "cross_document_issues": [],
        "quality_notes": [],
    }


class StabilityModeTests(unittest.TestCase):
    def test_cli_accepts_review_modes(self) -> None:
        args = build_parser().parse_args(["--review-mode", "strict"])
        self.assertEqual(args.review_mode, "strict")

    def test_cli_accepts_probe_model_flag(self) -> None:
        args = build_parser().parse_args(["--probe-model"])
        self.assertTrue(args.probe_model)

    def test_probe_text_model_uses_current_ai_environment(self) -> None:
        env = {
            "AI_BASE_URL": "http://example.test",
            "AI_API_KEY": "key",
            "AI_MODEL": "probe-model",
            "AI_WIRE_API": "responses",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(OpenAICompatibleClient, "chat", return_value="OK") as mock_chat:
                result = probe_text_model(timeout=12)

        self.assertEqual(result.model, "probe-model")
        self.assertEqual(result.base_url, "http://example.test")
        self.assertEqual(result.wire_api, "responses")
        self.assertEqual(result.response, "OK")
        self.assertEqual(result.review_mode, "fast")
        self.assertEqual(len(result.checks), 1)
        self.assertEqual(result.checks[0].status, "ok")
        self.assertTrue(result.is_success)
        mock_chat.assert_called_once()

    def test_probe_text_model_uses_dual_model_environment_in_fusion_mode(self) -> None:
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
                result = probe_text_model(timeout=12, review_mode="fusion")

        self.assertEqual(result.review_mode, "fusion")
        self.assertEqual(len(result.checks), 2)
        self.assertEqual(result.checks[0].label, "primary")
        self.assertEqual(result.checks[0].model, "gpt-5.4")
        self.assertEqual(result.checks[0].wire_api, "responses")
        self.assertEqual(result.checks[0].response, "PRIMARY_OK")
        self.assertEqual(result.checks[1].label, "secondary")
        self.assertEqual(result.checks[1].model, "deepseek-v4-pro")
        self.assertEqual(result.checks[1].wire_api, "chat_completions")
        self.assertEqual(result.checks[1].response, "SECONDARY_OK")
        self.assertEqual(result.checks[0].status, "ok")
        self.assertEqual(result.checks[1].status, "ok")
        self.assertTrue(result.is_success)
        self.assertEqual(mock_chat.call_count, 2)

    def test_probe_text_model_reports_missing_default_configuration_in_result(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = probe_text_model(timeout=12)

        self.assertFalse(result.is_success)
        self.assertEqual(len(result.checks), 1)
        self.assertEqual(result.checks[0].status, "missing_config")
        self.assertIn("AI_BASE_URL", result.checks[0].error)

    def test_probe_text_model_reports_missing_secondary_configuration_in_fusion_mode(self) -> None:
        env = {
            "AI_PRIMARY_BASE_URL": "http://primary.test",
            "AI_PRIMARY_API_KEY": "primary-key",
            "AI_PRIMARY_MODEL": "gpt-5.4",
            "AI_PRIMARY_WIRE_API": "responses",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch.object(OpenAICompatibleClient, "chat", return_value="PRIMARY_OK") as mock_chat:
                result = probe_text_model(timeout=12, review_mode="fusion")

        self.assertFalse(result.is_success)
        self.assertEqual(result.checks[0].status, "ok")
        self.assertEqual(result.checks[1].status, "missing_config")
        self.assertIn("AI_SECONDARY_BASE_URL", result.checks[1].error)
        self.assertEqual(mock_chat.call_count, 1)

    def test_probe_text_model_reports_timeout_status(self) -> None:
        env = {
            "AI_BASE_URL": "http://example.test",
            "AI_API_KEY": "key",
            "AI_MODEL": "probe-model",
            "AI_WIRE_API": "responses",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(
                OpenAICompatibleClient,
                "chat",
                side_effect=RuntimeError("Model API request timed out after 12s."),
            ):
                result = probe_text_model(timeout=12)

        self.assertFalse(result.is_success)
        self.assertEqual(result.checks[0].status, "timeout")
        self.assertIn("timed out", result.checks[0].error)

    def test_model_payload_uses_zero_temperature_and_optional_seed(self) -> None:
        config = ModelConfig(
            base_url="http://example.test",
            api_key="key",
            text_model="model",
            vision_base_url="",
            vision_api_key="",
            vision_model="",
            seed=1234,
        )
        client = OpenAICompatibleClient(config)
        payload = client._responses_payload(
            "model",
            [{"role": "user", "content": "hello"}],
            temperature=0,
            seed=config.seed,
        )

        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["seed"], 1234)

    def test_anthropic_payload_converts_system_messages_and_text_content(self) -> None:
        config = ModelConfig(
            base_url="http://example.test",
            api_key="key",
            text_model="claude-proxy",
            vision_base_url="",
            vision_api_key="",
            vision_model="",
        )
        client = OpenAICompatibleClient(config)
        payload = client._anthropic_messages_payload(
            "claude-proxy",
            [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
            ],
            temperature=0,
        )

        self.assertEqual(payload["model"], "claude-proxy")
        self.assertEqual(payload["system"], "system prompt")
        self.assertEqual(payload["max_tokens"], 8192)
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["messages"][0]["content"][0]["type"], "text")
        self.assertEqual(payload["messages"][0]["content"][0]["text"], "hello")

    def test_anthropic_extract_text_reads_content_blocks(self) -> None:
        config = ModelConfig(
            base_url="http://example.test",
            api_key="key",
            text_model="claude-proxy",
            vision_base_url="",
            vision_api_key="",
            vision_model="",
        )
        client = OpenAICompatibleClient(config)
        text = client._extract_anthropic_text(
            {
                "content": [
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ]
            }
        )

        self.assertEqual(text, "first\nsecond")

    def test_audit_prompt_is_checker_not_second_report(self) -> None:
        report = empty_report()
        report["dimensions"][0]["findings"].append({"title": "已有问题", "evidence": "稳定性需求文档.docx / 段落1"})

        messages = build_audit_messages([make_doc()], report, max_context_chars=4000)
        combined = "\n".join(str(message["content"]) for message in messages)

        self.assertIn("不是重新生成报告", combined)
        self.assertIn("missed_high_risk_findings", combined)
        self.assertIn("已有问题", combined)

    def test_merge_audit_only_adds_high_confidence_corrections_and_notes(self) -> None:
        docs = [make_doc()]
        report = empty_report()
        audit = {
            "missed_high_risk_findings": [
                {
                    "primary_dimension": DIMENSIONS[0],
                    "title": "扣款与发奖时机缺少失败回滚说明",
                    "current_state": "文档只写了点击开始扣款和结算发奖，未写失败回滚。",
                    "evidence": "稳定性需求文档.docx / 段落1",
                    "risk": "异常中断时可能出现扣款与发奖状态不一致。",
                    "suggestion": "补充失败、重进、重复点击的回滚和幂等规则。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
            "unsupported_findings": [{"title": "泛化的钱包能力缺失", "reason": "当前文档未涉及玩法专属钱包边界"}],
            "score_adjustment": {"suggested_score": "C", "reason": "新增高风险缺口。"},
            "audit_notes": ["校验器只补充主报告遗漏项。"],
        }

        merged = merge_audit_report(normalize_report(report), audit, docs)
        findings = [
            finding
            for dimension in merged["dimensions"]
            for finding in dimension["findings"]
            if finding["title"] == "扣款与发奖时机缺少失败回滚说明"
        ]

        self.assertEqual(findings[0]["title"], "扣款与发奖时机缺少失败回滚说明")
        self.assertIn("strict 校验提示", "\n".join(merged["quality_notes"]))
        self.assertEqual(merged["document_quality_score"], "C")
        self.assertEqual(merged["score_reason"], "新增高风险缺口。")

    def test_strict_score_adjustment_can_override_fatal_d_to_c(self) -> None:
        docs = [make_doc("Racing需求文档.docx"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = {
            "overall_evaluation": "",
            "document_quality_score": "",
            "score_reason": "",
            "dimensions": [{"name": dimension, "dimension_note": "", "findings": []} for dimension in DIMENSIONS],
            "cross_document_issues": [
                {
                    "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                    "title": "需求文档实时赔率公式与数值文档Odds公式存在根本性冲突",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "需求和数值文档给出了无法兼容的不同赔率公式。",
                    "evidence": "Racing需求文档.docx / 段落2；Racing数值文档.docx / 段落5",
                    "risk": "赔付实现会分叉。",
                    "suggestion": "统一唯一赔率公式。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
            "quality_notes": [],
        }
        audit = {
            "missed_high_risk_findings": [],
            "unsupported_findings": [],
            "score_adjustment": {"suggested_score": "C", "reason": "主流程仍可通过补文档统一实现。"},
            "audit_notes": [],
        }

        merged = merge_audit_report(normalize_report(report), audit, docs)

        self.assertEqual(merged["document_quality_score"], "C")
        self.assertEqual(merged["score_reason"], "主流程仍可通过补文档统一实现。")
        self.assertIn("strict 校验已覆盖最终评分", "\n".join(merged["quality_notes"]))

    def test_strict_audit_keeps_main_report_when_only_rephrasing_existing_root_cause(self) -> None:
        docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
        report = {
            "overall_evaluation": "",
            "document_quality_score": "C",
            "score_reason": "main report keeps one actionable root cause",
            "dimensions": [{"name": dimension, "dimension_note": "", "findings": []} for dimension in DIMENSIONS],
            "cross_document_issues": [
                {
                    "issue_id": "CROSS_01",
                    "canonical_title": "payout formula conflict",
                    "title": "Realtime payout formula conflicts with odds formula",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "Requirement and numeric docs define different payout formulas.",
                    "evidence": "Racing spec.docx / paragraph 2; Racing numeric.docx / paragraph 5",
                    "risk": "Implementation and settlement will diverge.",
                    "suggestion": "Keep a single authoritative formula.",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
            "quality_notes": [],
        }
        audit = {
            "missed_high_risk_findings": [
                {
                    "issue_id": "CORE_01",
                    "canonical_title": "payout formula conflict",
                    "title": "Settlement formula is still split across docs",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "The same payout root cause is described with a new title.",
                    "evidence": "Racing spec.docx / paragraph 2; Racing numeric.docx / paragraph 5",
                    "risk": "Settlement still diverges.",
                    "suggestion": "Align the formula definition.",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
            "unsupported_findings": [],
            "merge_recommendations": [
                {
                    "titles": [
                        "Realtime payout formula conflicts with odds formula",
                        "Settlement formula is still split across docs",
                    ],
                    "merged_title": "Core payout formula conflict",
                    "reason": "same root cause",
                }
            ],
            "score_adjustment": {"suggested_score": "D", "reason": "audit wants to escalate the same root cause"},
            "audit_notes": [],
        }

        merged = merge_audit_report(normalize_report(report), audit, docs)

        self.assertEqual(merged["document_quality_score"], "C")
        self.assertEqual(merged["top_blockers"][0]["title"], "Realtime payout formula conflicts with odds formula")
        self.assertIn("strict 校验保留主报告评分", "\n".join(merged["quality_notes"]))

    def test_parse_audit_json_accepts_fenced_json(self) -> None:
        audit, error = parse_audit_json('```json\n{"missed_high_risk_findings": []}\n```')

        self.assertFalse(error)
        self.assertEqual(audit["missed_high_risk_findings"], [])

    def test_parse_model_json_accepts_think_wrapped_output_with_trailing_json(self) -> None:
        docs = [make_doc()]
        raw = (
            "先做分析说明，不是最终格式。\n"
            "/think>{\"overall_evaluation\":\"主流程可理解\",\"document_quality_score\":\"C\","
            "\"score_reason\":\"仍需补充关键规则\",\"dimensions\":[],\"cross_document_issues\":[],"
            "\"top_blockers\":[],\"quality_notes\":[],\"missing_information\":[],\"test_points\":{}}"
        )

        report, error = parse_model_json(raw, docs)

        self.assertFalse(error)
        self.assertEqual(report["overall_evaluation"], "主流程可理解")
        self.assertIn(report["document_quality_score"], {"A", "B", "C", "D"})

    def test_parse_audit_json_accepts_think_wrapped_output_with_trailing_json(self) -> None:
        raw = (
            "这里先输出校验草稿。\n"
            "/think>{\"missed_high_risk_findings\":[],\"unsupported_findings\":[],"
            "\"merge_recommendations\":[],\"score_adjustment\":{\"suggested_score\":\"C\",\"reason\":\"可通过补文档修复\"},"
            "\"audit_notes\":[]}"
        )

        audit, error = parse_audit_json(raw)

        self.assertFalse(error)
        self.assertEqual(audit["score_adjustment"]["suggested_score"], "C")

    def test_report_diff_payload_highlights_added_findings_and_score_change(self) -> None:
        before = empty_report()
        before["dimensions"][0]["findings"].append(
            {
                "title": "筹码映射字段命名需要补充示例",
                "risk": "测试验收口径可能不一致。",
                "severity": "中",
                "blocking": "阻塞测试用例设计",
                "primary_dimension": DIMENSIONS[0],
            }
        )
        after = json.loads(json.dumps(before, ensure_ascii=False))
        after["document_quality_score"] = "C"
        after["score_reason"] = "新增高风险缺口。"
        after["dimensions"][0]["findings"].append(
            {
                "title": "结算失败后的回滚规则缺失",
                "risk": "可能出现扣款成功但发奖失败的状态分叉。",
                "severity": "高",
                "blocking": "阻塞开发",
                "primary_dimension": DIMENSIONS[0],
            }
        )
        after["quality_notes"] = ["strict 模式新增了高风险补漏。"]

        diff = build_report_diff_payload(before, after)

        self.assertEqual(diff["score_before"], "B")
        self.assertEqual(diff["score_after"], "C")
        self.assertEqual(diff["counts"]["added"], 1)
        self.assertEqual(diff["added_findings"][0]["title"], "结算失败后的回滚规则缺失")
        self.assertIn("strict 模式新增了高风险补漏。", diff["added_quality_notes"])

    def test_strict_mode_writes_pre_audit_and_final_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "reports"
            agent = ReviewAgent(
                input_path=root,
                output_dir=output_dir,
                review_mode="strict",
                analyze_images=False,
            )
            agent.config = ModelConfig(
                base_url="http://example.test",
                api_key="key",
                text_model="model",
                vision_base_url="",
                vision_api_key="",
                vision_model="",
            )
            main_report = empty_report()
            main_report["dimensions"][0]["findings"].append(
                {
                    "title": "筹码映射字段命名需要补充示例",
                    "current_state": "主流程可理解，但配置字段示例不足。",
                    "evidence": "稳定性需求文档.docx / 段落1",
                    "risk": "测试验收口径可能不一致。",
                    "suggestion": "补充字段样例和验收示例。",
                    "severity": "中",
                    "confidence": "高",
                    "blocking": "阻塞测试用例设计",
                }
            )
            audit = {
                "missed_high_risk_findings": [
                    {
                        "primary_dimension": DIMENSIONS[0],
                        "title": "结算失败后的回滚规则缺失",
                        "current_state": "文档没有说明扣款后结算失败如何回滚。",
                        "evidence": "稳定性需求文档.docx / 段落1",
                        "risk": "可能出现扣款成功但发奖失败的状态分叉。",
                        "suggestion": "补充回滚、补偿、幂等和重进恢复规则。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
                "unsupported_findings": [],
                "score_adjustment": {"suggested_score": "C", "reason": "新增高风险问题。"},
                "audit_notes": [],
            }
            responses = iter(
                [
                    json.dumps(main_report, ensure_ascii=False),
                    json.dumps(audit, ensure_ascii=False),
                ]
            )

            agent._parse_documents = lambda assets_dir: [make_doc()]
            agent._build_review_messages = lambda docs: [{"role": "user", "content": "main"}]
            agent._build_audit_messages = lambda docs, report: [{"role": "user", "content": "audit"}]
            agent._call_text_model = lambda messages, client=None, config=None, stage="primary": next(responses)
            agent._write_latest = lambda run_dir: None

            result = agent.run(extract_only=False)
            pre_audit_json = result.json_path.parent / "review_report_pre_audit.json"
            final_json = result.json_path
            diff_json = result.json_path.parent / "review_report_diff.json"
            diff_markdown = result.json_path.parent / "review_report_diff.md"

            self.assertTrue(pre_audit_json.exists())
            self.assertTrue(final_json.exists())
            self.assertTrue(diff_json.exists())
            self.assertTrue(diff_markdown.exists())

            pre_payload = json.loads(pre_audit_json.read_text(encoding="utf-8"))
            final_payload = json.loads(final_json.read_text(encoding="utf-8"))
            diff_payload = json.loads(diff_json.read_text(encoding="utf-8"))

            self.assertEqual(pre_payload["report"]["document_quality_score"], "B")
            self.assertEqual(final_payload["report"]["document_quality_score"], "C")
            self.assertIn("review_report_pre_audit", "\n".join(final_payload["report"]["quality_notes"]))
            self.assertEqual(diff_payload["score_before"], "B")
            self.assertEqual(diff_payload["score_after"], "C")
            self.assertEqual(diff_payload["counts"]["added"], 1)


    def test_audit_prompt_requires_explicit_score_and_merge_section(self) -> None:
        report = empty_report()
        messages = build_audit_messages([make_doc()], report, max_context_chars=4000)
        combined = "\n".join(str(message["content"]) for message in messages)

        self.assertIn("merge_recommendations", combined)
        self.assertIn("A/B/C/D", combined)
        self.assertNotIn("保持不变", combined)

    def test_merge_recommendations_merge_same_root_titles(self) -> None:
        docs = [make_doc("Racing需求文档.docx"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = empty_report()
        report["dimensions"][0]["findings"].append(
            {
                "title": "数值文档区分实际赔率和假赔率，但需求文档未描述假赔率的展示机制",
                "current_state": "需求文档没有说明假赔率何时展示。",
                "evidence": "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落5",
                "risk": "展示赔率和真实赔付赔率可能不一致。",
                "suggestion": "补充假赔率展示规则。",
                "severity": "中",
                "confidence": "中",
                "blocking": "阻塞测试用例设计",
                "primary_dimension": DIMENSIONS[0],
            }
        )
        report["cross_document_issues"] = [
            {
                "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                "title": "需求文档实时赔率公式与数值文档赔率+gamma体系存在根本分歧",
                "primary_dimension": DIMENSIONS[1],
                "current_state": "需求文档和数值文档对赔率公式的定义不一致。",
                "evidence": "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落2-5",
                "risk": "开发会形成不同的赔付实现方案。",
                "suggestion": "统一赔率公式。",
                "severity": "高",
                "confidence": "高",
                "blocking": "阻塞开发",
            }
        ]
        audit = {
            "missed_high_risk_findings": [],
            "unsupported_findings": [],
            "merge_recommendations": [
                {
                    "titles": [
                        "数值文档区分实际赔率和假赔率，但需求文档未描述假赔率的展示机制",
                        "需求文档实时赔率公式与数值文档赔率+gamma体系存在根本分歧",
                    ],
                    "merged_title": "赔率公式与展示赔率/实际赔率口径存在同一根因冲突",
                    "reason": "两者都指向同一赔率实现口径缺口。",
                }
            ],
            "score_adjustment": {"suggested_score": "D", "reason": "赔率口径冲突仍是唯一 fatal 根因。"},
            "audit_notes": [],
        }

        merged = merge_audit_report(normalize_report(report), audit, docs)
        titles = [finding["title"] for finding in merged["cross_document_issues"]]
        self.assertEqual(titles, ["瀹屾垚鏃堕棿鍏紡涓璍uck闅忔満鎵板姩浠呭湪鍥剧墖涓嚭鐜帮紝闇€姹傛枃瀛楁湭鎻愬強"])
        self.assertIn("瀹屾垚鏃堕棿鍏紡渚濊禆鐨勫共鎵版寚鏁般€丩uck銆佸湴褰㈡鐜囧潎鏈畬鏁村畾涔夛紝瀵艰嚧骞查閫昏緫涓嶅彲瀹炵幇", "\n".join(merged["quality_notes"]))
        return
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0], "闇€姹傛枃妗ｅ疄鏃惰禂鐜囧叕寮忎笌鏁板€兼枃妗ｈ禂鐜?gamma浣撶郴瀛樺湪鏍规湰鍒嗘")
        self.assertIn("璧旂巼鍏紡涓庡睍绀鸿禂鐜?瀹為檯璧旂巼鍙ｅ緞瀛樺湪鍚屼竴鏍瑰洜鍐茬獊", "\n".join(merged["quality_notes"]))
        return
        self.assertEqual(titles[0], "赔率公式与展示赔率/实际赔率口径存在同一根因冲突")

    def test_merge_recommendations_can_match_issue_marker_suffix(self) -> None:
        docs = [make_doc("Racing需求文档.docx"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = empty_report()
        report["cross_document_issues"] = [
            {
                "issue_id": "CROSS-002",
                "title": "完成时间公式中Luck随机扰动仅在图片中出现，需求文字未提及",
                "primary_dimension": DIMENSIONS[0],
                "current_state": "Luck 只在图片中出现，正文没有定义。",
                "evidence": "Racing需求文档.docx / 段落36；Racing数值文档.docx / 表格3",
                "risk": "实现方无法确定 Luck 是否进入 T 公式。",
                "suggestion": "补充 Luck、干扰指数、地形概率的统一定义。",
                "severity": "高",
                "confidence": "高",
                "blocking": "阻塞开发",
            }
        ]
        audit = {
            "missed_high_risk_findings": [],
            "unsupported_findings": [],
            "merge_recommendations": [
                {
                    "titles": [
                        "干扰指数和地形概率调整无法影响完成时间T的计算（RAC-LN-002）",
                        "完成时间公式中Luck随机扰动仅在图片中出现，需求文字未提及（CROSS-002）",
                    ],
                    "merged_title": "完成时间公式依赖的干扰指数、Luck、地形概率均未完整定义，导致干预逻辑不可实现",
                    "reason": "两条都是 T 公式变量未定义的同一根因。",
                }
            ],
            "score_adjustment": {"suggested_score": "C", "reason": "问题可通过补文档修复。"},
            "audit_notes": [],
        }

        merged = merge_audit_report(normalize_report(report), audit, docs)
        titles = [finding["title"] for finding in merged["cross_document_issues"]]
        self.assertEqual(titles, ["完成时间公式依赖的干扰指数、Luck、地形概率均未完整定义，导致干预逻辑不可实现"])

def _patched_test_merge_recommendations_merge_same_root_titles(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    report = empty_report()
    report["cross_document_issues"] = [
        {
            "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
            "title": "Requirement payout formula conflicts with numeric odds formula",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "Two docs define different payout formulas.",
            "evidence": "Racing spec.docx / paragraph 28; Racing numeric.docx / paragraph 5",
            "risk": "Implementation and settlement will diverge.",
            "suggestion": "Keep one authoritative payout formula.",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]
    audit = {
        "missed_high_risk_findings": [],
        "unsupported_findings": [],
        "merge_recommendations": [
            {
                "titles": [
                    "Displayed odds and actual odds still use different wording",
                    "Requirement payout formula conflicts with numeric odds formula",
                ],
                "merged_title": "Core payout wording conflict",
                "reason": "same root cause",
            }
        ],
        "score_adjustment": {"suggested_score": "D", "reason": "same fatal root cause"},
        "audit_notes": [],
    }

    merged = merge_audit_report(normalize_report(report), audit, docs)

    self.assertEqual(
        [finding["title"] for finding in merged["cross_document_issues"]],
        ["Requirement payout formula conflicts with numeric odds formula"],
    )
    self.assertIn("Core payout wording conflict", "\n".join(merged["quality_notes"]))


def _patched_test_merge_recommendations_can_match_issue_marker_suffix(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    report = empty_report()
    report["cross_document_issues"] = [
        {
            "issue_id": "CROSS-002",
            "title": "Luck appears only in image notes and not in requirement text",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "Luck is only described in an image.",
            "evidence": "Racing spec.docx / paragraph 36; Racing numeric.docx / table 3",
            "risk": "The finish-time formula cannot be implemented consistently.",
            "suggestion": "Define Luck and related variables in text.",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]
    audit = {
        "missed_high_risk_findings": [],
        "unsupported_findings": [],
        "merge_recommendations": [
            {
                "titles": [
                    "Interference index still cannot affect finish time (RAC-LN-002)",
                    "Luck appears only in image notes and not in requirement text (CROSS-002)",
                ],
                "merged_title": "Finish-time inputs are still not fully defined",
                "reason": "same undefined variable root cause",
            }
        ],
        "score_adjustment": {"suggested_score": "C", "reason": "fixable by clarifying the docs"},
        "audit_notes": [],
    }

    merged = merge_audit_report(normalize_report(report), audit, docs)

    self.assertEqual(
        [finding["title"] for finding in merged["cross_document_issues"]],
        ["Luck appears only in image notes and not in requirement text"],
    )
    self.assertIn("Finish-time inputs are still not fully defined", "\n".join(merged["quality_notes"]))


def _patched_test_parse_model_json_preserves_model_score_and_top_blockers(self) -> None:
    raw = json.dumps(
        {
            "overall_evaluation": "model summary",
            "document_quality_score": "C",
            "score_reason": "model-owned score",
            "top_blockers": [
                {
                    "severity": "高",
                    "title": "Requirement payout formula conflicts with numeric odds formula",
                    "owner": "planner",
                    "why_now": "model priority should be preserved",
                }
            ],
            "dimensions": [
                {
                    "name": DIMENSIONS[1],
                    "dimension_note": "",
                    "findings": [
                        {
                            "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                            "title": "Requirement payout formula conflicts with numeric odds formula",
                            "primary_dimension": DIMENSIONS[1],
                            "current_state": "two docs define different formulas",
                            "evidence": "Racing spec.docx / paragraph 2; Racing numeric.docx / paragraph 5",
                            "risk": "implementation diverges",
                            "suggestion": "keep one formula",
                            "severity": "高",
                            "confidence": "高",
                            "blocking": "阻塞开发",
                        }
                    ],
                }
            ],
            "cross_document_issues": [],
            "quality_notes": [],
            "missing_information": [],
            "test_points": {},
        },
        ensure_ascii=False,
    )

    report, error = parse_model_json(raw, [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")])

    self.assertFalse(error)
    self.assertEqual(report["document_quality_score"], "C")
    self.assertEqual(report["score_reason"], "model-owned score")
    self.assertEqual(report["top_blockers"][0]["title"], "Requirement payout formula conflicts with numeric odds formula")


def _patched_test_parse_model_json_drops_low_priority_model_blockers_after_stabilization(self) -> None:
    raw = json.dumps(
        {
            "overall_evaluation": "model summary",
            "document_quality_score": "C",
            "score_reason": "model-owned score",
            "top_blockers": [
                {
                    "severity": "高",
                    "title": "关键阈值与配置占位符大量缺失",
                    "owner": "planner",
                    "why_now": "placeholder blocker should not survive as high priority",
                },
                {
                    "severity": "高",
                    "title": "客户端展示赔率与服务端权威结算边界不清",
                    "owner": "planner",
                    "why_now": "authority reminder should not survive as high priority",
                },
            ],
            "dimensions": [
                {
                    "name": DIMENSIONS[0],
                    "dimension_note": "",
                    "findings": [
                        {
                            "title": "关键阈值与配置占位符大量缺失",
                            "primary_dimension": DIMENSIONS[0],
                            "current_state": "document still uses [001] placeholders",
                            "evidence": "Racing spec.docx / paragraph 12",
                            "risk": "needs more config detail",
                            "suggestion": "fill default values",
                            "severity": "高",
                            "confidence": "高",
                            "blocking": "阻塞开发",
                        }
                    ],
                },
                {
                    "name": DIMENSIONS[1],
                    "dimension_note": "",
                    "findings": [
                        {
                            "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                            "title": "Requirement payout formula conflicts with numeric odds formula",
                            "primary_dimension": DIMENSIONS[1],
                            "current_state": "two docs define different formulas",
                            "evidence": "Racing spec.docx / paragraph 2; Racing numeric.docx / paragraph 5",
                            "risk": "implementation diverges",
                            "suggestion": "keep one formula",
                            "severity": "高",
                            "confidence": "高",
                            "blocking": "阻塞开发",
                        }
                    ],
                },
                {
                    "name": DIMENSIONS[4],
                    "dimension_note": "",
                    "findings": [
                        {
                            "title": "客户端展示赔率与服务端权威结算边界不清",
                            "primary_dimension": DIMENSIONS[4],
                            "current_state": "document does not emphasize server authority",
                            "evidence": "Racing spec.docx / paragraph 28",
                            "risk": "needs authority wording only",
                            "suggestion": "add server authority note",
                            "severity": "高",
                            "confidence": "高",
                            "blocking": "阻塞开发",
                        }
                    ],
                },
            ],
            "cross_document_issues": [],
            "quality_notes": [],
            "missing_information": [],
            "test_points": {},
        },
        ensure_ascii=False,
    )

    report, error = parse_model_json(raw, [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")])

    self.assertFalse(error)
    blocker_titles = [item["title"] for item in report["top_blockers"]]
    self.assertEqual(blocker_titles, ["Requirement payout formula conflicts with numeric odds formula"])


def _patched_test_parse_model_json_keeps_primary_formula_mapping_and_locking_blockers_distinct(self) -> None:
    raw = json.dumps(
        {
            "overall_evaluation": "model summary",
            "document_quality_score": "C",
            "score_reason": "model-owned score",
            "top_blockers": [
                {
                    "severity": "高",
                    "title": "赔率公式体系冲突与变量未定义",
                    "owner": "planner",
                    "why_now": "formula conflict should stay first",
                },
                {
                    "severity": "高",
                    "title": "干扰指数与开奖时间公式(T)的数学映射缺失",
                    "owner": "planner",
                    "why_now": "mapping gap should stay second",
                },
                {
                    "severity": "高",
                    "title": "实时赔率结算锁定机制与并发下注歧义",
                    "owner": "planner",
                    "why_now": "locking gap should stay third",
                },
                {
                    "severity": "高",
                    "title": "最大赔付(MAX_MUL)、RTP目标与奖池负数风控缺失",
                    "owner": "planner",
                    "why_now": "high risk but should remain after first three",
                },
            ],
            "dimensions": [
                {
                    "name": DIMENSIONS[0],
                    "dimension_note": "",
                    "findings": [
                        {
                            "issue_id": "CLARITY_01",
                            "title": "核心阈值与概率占位符([001]等)泛滥且无默认值/边界",
                            "primary_dimension": DIMENSIONS[0],
                            "current_state": "下注人数阈值和干扰指数区间都还是占位符。",
                            "evidence": "Racing spec.docx / paragraph 24",
                            "risk": "配置无法初始化。",
                            "suggestion": "补齐占位符默认值。",
                            "severity": "中",
                            "confidence": "高",
                            "blocking": "阻塞测试用例设计",
                        },
                        {
                            "issue_id": "CLARITY_02",
                            "title": "地形生成逻辑与隐藏地形对结算的影响未闭环",
                            "primary_dimension": DIMENSIONS[0],
                            "current_state": "隐藏地形和结算关系未说明。",
                            "evidence": "Racing spec.docx / paragraph 26",
                            "risk": "表现与结算可能不一致。",
                            "suggestion": "补充地形规则。",
                            "severity": "中",
                            "confidence": "中",
                            "blocking": "阻塞开发",
                        },
                    ],
                },
                {
                    "name": DIMENSIONS[1],
                    "dimension_note": "",
                    "findings": [
                        {
                            "issue_id": "LOGIC_01",
                            "title": "干扰指数与开奖时间公式(T)的数学映射缺失",
                            "primary_dimension": DIMENSIONS[1],
                            "current_state": "干扰指数如何作用到 T/Luck 未定义。",
                            "evidence": "Racing spec.docx / paragraph 43; Racing numeric.docx / image 3",
                            "risk": "干预链路无法实现。",
                            "suggestion": "补充映射公式。",
                            "severity": "高",
                            "confidence": "高",
                            "blocking": "阻塞开发",
                        },
                        {
                            "issue_id": "LOGIC_02",
                            "title": "实时赔率结算锁定机制与并发下注歧义",
                            "primary_dimension": DIMENSIONS[1],
                            "current_state": "未说明按下注瞬间还是开奖瞬间赔率结算。",
                            "evidence": "Racing spec.docx / paragraph 28",
                            "risk": "展示金额和结算金额可能不一致。",
                            "suggestion": "明确赔率锁定时点。",
                            "severity": "高",
                            "confidence": "高",
                            "blocking": "阻塞开发",
                        },
                        {
                            "issue_id": "LOGIC_03",
                            "title": "最大赔付(MAX_MUL)、RTP目标与奖池负数风控缺失",
                            "primary_dimension": DIMENSIONS[1],
                            "current_state": "未定义最大赔付与 RTP 目标。",
                            "evidence": "Racing spec.docx / paragraph 32",
                            "risk": "存在资损风险。",
                            "suggestion": "补充风控阈值。",
                            "severity": "高",
                            "confidence": "高",
                            "blocking": "阻塞开发",
                        },
                    ],
                },
            ],
            "cross_document_issues": [
                {
                    "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                    "title": "赔率公式体系冲突与变量未定义",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "需求与数值文档给出两套不同赔率公式，变量也未统一定义。",
                    "evidence": "Racing spec.docx / paragraph 28; Racing numeric.docx / paragraph 5",
                    "risk": "服务端结算无法统一实现。",
                    "suggestion": "统一唯一赔率公式和变量定义。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
            "quality_notes": [],
            "missing_information": [],
            "test_points": {},
        },
        ensure_ascii=False,
    )

    report, error = parse_model_json(raw, [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")])

    self.assertFalse(error)
    blocker_titles = [item["title"] for item in report["top_blockers"]]
    self.assertEqual(
        blocker_titles,
        [
            "赔率公式体系冲突与变量未定义",
            "干扰指数与开奖时间公式(T)的数学映射缺失",
            "实时赔率结算锁定机制与并发下注歧义",
        ],
    )


def _patched_test_strict_audit_treats_formula_conflict_rewording_as_duplicate(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    report = {
        "overall_evaluation": "",
        "document_quality_score": "C",
        "score_reason": "main report keeps C",
        "top_blockers": [
            {
                "severity": "高",
                "title": "赔率计算公式存在两套冲突口径",
                "owner": "数值策划",
                "why_now": "same formula root cause should stay in place",
            }
        ],
        "dimensions": [{"name": dimension, "dimension_note": "", "findings": []} for dimension in DIMENSIONS],
        "cross_document_issues": [
            {
                "issue_id": "CROSS_01",
                "canonical_title": "赔率计算公式存在两套冲突口径",
                "title": "赔率计算公式存在两套冲突口径",
                "primary_dimension": DIMENSIONS[1],
                "current_state": "两份文档定义了不同的赔率公式。",
                "evidence": "Racing spec.docx / paragraph 28 vs Racing numeric.docx / paragraph 3",
                "risk": "结算实现会分叉。",
                "suggestion": "统一唯一赔率公式。",
                "severity": "中",
                "confidence": "高",
                "blocking": "阻塞开发",
            }
        ],
        "quality_notes": [],
    }
    audit = {
        "missed_high_risk_findings": [
            {
                "issue_id": "CORE_01",
                "canonical_title": "核心结算模型互斥",
                "title": "两套赔率公式底层经济模型互斥，结算链路无法闭环",
                "primary_dimension": DIMENSIONS[1],
                "current_state": "同一组证据被换了一种更激进的写法。",
                "evidence": "Racing spec.docx / paragraph 28 vs Racing numeric.docx / paragraph 3",
                "risk": "结算实现会分叉。",
                "suggestion": "统一唯一赔率公式。",
                "severity": "高",
                "confidence": "高",
                "blocking": "阻塞开发",
            }
        ],
        "unsupported_findings": [],
        "merge_recommendations": [],
        "score_adjustment": {"suggested_score": "D", "reason": "audit rewrites the same formula conflict as fatal"},
        "audit_notes": [],
    }

    merged = merge_audit_report(normalize_report(report), audit, docs)

    self.assertEqual(merged["document_quality_score"], "C")
    self.assertEqual(merged["top_blockers"][0]["title"], "赔率计算公式存在两套冲突口径")
    self.assertIn("strict 校验保留主报告评分", "\n".join(merged["quality_notes"]))


def _patched_test_cli_accepts_fusion_review_mode(self) -> None:
    args = build_parser().parse_args(["--review-mode", "fusion"])
    self.assertEqual(args.review_mode, "fusion")


def _patched_test_model_config_from_prefixed_env(self) -> None:
    env = {
        "AI_PRIMARY_BASE_URL": "http://primary.test",
        "AI_PRIMARY_API_KEY": "primary-key",
        "AI_PRIMARY_MODEL": "gpt-5.4",
        "AI_PRIMARY_WIRE_API": "responses",
        "AI_PRIMARY_SEED": "123",
        "AI_SECONDARY_BASE_URL": "http://secondary.test",
        "AI_SECONDARY_API_KEY": "secondary-key",
        "AI_SECONDARY_MODEL": "deepseek-v4-pro",
        "AI_SECONDARY_WIRE_API": "chat_completions",
        "AI_VISION_BASE_URL": "http://vision.test",
        "AI_VISION_API_KEY": "vision-key",
        "AI_VISION_MODEL": "vision-model",
    }
    with patch.dict(os.environ, env, clear=False):
        primary = ModelConfig.from_prefixed_env("AI_PRIMARY")
        secondary = ModelConfig.from_prefixed_env("AI_SECONDARY")

    self.assertEqual(primary.base_url, "http://primary.test")
    self.assertEqual(primary.text_model, "gpt-5.4")
    self.assertEqual(primary.wire_api, "responses")
    self.assertEqual(primary.seed, 123)
    self.assertEqual(primary.vision_model, "vision-model")
    self.assertEqual(secondary.base_url, "http://secondary.test")
    self.assertEqual(secondary.text_model, "deepseek-v4-pro")
    self.assertEqual(secondary.wire_api, "chat_completions")


def _patched_test_fusion_merge_adds_unique_secondary_finding_with_source(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    primary["top_blockers"] = [
        {"severity": "高", "title": "Primary blocker", "owner": "planner", "why_now": "main risk"}
    ]
    secondary = empty_report()
    secondary["dimensions"][2]["findings"].append(
        {
            "issue_id": "COMP_RECONNECT_REENTER_MISSING",
            "title": "重连重进后的状态恢复规则缺失",
            "primary_dimension": DIMENSIONS[2],
            "current_state": "没有说明异常恢复流程。",
            "evidence": "Racing spec.docx / paragraph 12",
            "risk": "异常恢复无法稳定实现。",
            "suggestion": "补充重连重进处理规则。",
            "severity": "中",
            "confidence": "高",
            "blocking": "阻塞测试用例设计",
        }
    )

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    all_findings = [finding for finding in merged["dimensions"][3]["findings"] if finding["title"] == "重连重进后的状态恢复规则缺失"]
    self.assertEqual(len(all_findings), 1)
    self.assertEqual(all_findings[0]["finding_source_label"], "副评审补充")
    self.assertEqual(all_findings[0]["source_model"], "deepseek-v4-pro")
    self.assertEqual(merged["document_quality_score"], "C")
    self.assertEqual(summary["added_unique_findings"], 1)


def _patched_test_fusion_merge_skips_duplicate_secondary_finding(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    primary["cross_document_issues"] = [
        {
            "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
            "title": "Realtime payout formula conflicts with odds formula",
            "canonical_title": "payout formula conflict",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "two formulas are defined",
            "evidence": "Racing spec.docx / paragraph 2; Racing numeric.docx / paragraph 5",
            "risk": "settlement diverges",
            "suggestion": "keep one formula",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]
    secondary = empty_report()
    secondary["cross_document_issues"] = [
        {
            "issue_id": "CORE_01",
            "canonical_title": "payout formula conflict",
            "title": "Settlement formula is still split across docs",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "same root cause with different wording",
            "evidence": "Racing spec.docx / paragraph 2; Racing numeric.docx / paragraph 5",
            "risk": "settlement diverges",
            "suggestion": "align the formula definition",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertEqual(summary["added_unique_findings"], 0)
    self.assertEqual(len(merged["cross_document_issues"]), 1)
    self.assertEqual(merged["document_quality_score"], "C")


def _patched_test_fusion_merge_dedupes_secondary_cross_issue_with_describe_and_source_docs(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    primary["cross_document_issues"] = [
        {
            "issue_id": "CROSS_DOC_01",
            "title": "需求文档与数值文档赔率计算公式完全冲突",
            "canonical_title": "赔率计算公式双轨冲突",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "需求与数值文档分别定义了两套不同赔率公式。",
            "evidence": "Racing spec.docx / paragraph 28; Racing numeric.docx / paragraph 2-5",
            "risk": "开发无法统一结算方案。",
            "suggestion": "统一唯一赔率公式。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]
    secondary = empty_report()
    secondary["cross_document_issues"] = [
        {
            "issue_id": "CROSS-01",
            "title": "需求文档与数值文档的赔率计算体系冲突",
            "describe": "需求文档使用简单比例赔率，数值文档给出含抽水与 gamma 的另一套公式。",
            "source_docs": ["Racing spec.docx / paragraph 28", "Racing numeric.docx / paragraph 2-5"],
            "impact": "开发无法统一结算方案。",
            "suggestion": "统一唯一赔率公式。",
            "severity": "中",
            "confidence": "中",
            "blocking": "阻塞测试用例设计",
        }
    ]

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertEqual(summary["added_unique_findings"], 0)
    self.assertFalse(summary["score_downgraded"])
    self.assertEqual(merged["document_quality_score"], "C")
    self.assertEqual(len(merged["cross_document_issues"]), 1)


def _patched_test_fusion_merge_dedupes_secondary_intervention_rewrite_by_root_cluster(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    primary["top_blockers"] = [
        {"severity": "楂?", "title": "骞叉壈鎸囨暟鏈槑纭帴鍏ュ畬璧涙椂闂碩鍏紡", "owner": "planner", "why_now": "main risk"}
    ]
    primary["dimensions"][1]["findings"] = [
        {
            "issue_id": "LOGIC_01",
            "_root_cause_cluster": "intervention_mapping",
            "title": "骞叉壈鎸囨暟鏈槑纭帴鍏ュ畬璧涙椂闂碩鍏紡",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "骞叉壈鎸囨暟鏈鏄庡浣曡繘鍏?T 鍏紡",
            "evidence": "Racing spec.docx / paragraph 40",
            "risk": "寮€濂栧共棰勬棤娉曡惤鍦?",
            "suggestion": "鏄庣‘骞叉壈鎸囨暟鍦?T 鍏紡鐨勪綅缃?",
            "severity": "楂?",
            "confidence": "楂?",
            "blocking": "闃诲寮€鍙?",
        }
    ]

    secondary = empty_report()
    secondary["dimensions"][0]["findings"] = [
        {
            "issue_id": "CLR-002",
            "_root_cause_cluster": "intervention_mapping",
            "title": "骞叉壈鎸囨暟鏈笌閫熷害鎴栨椂闂村叕寮忓叧鑱旓紝寮€濂栧共棰勬棤娉曞疄鐜?",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "闇€姹傛枃妗ｅ拰鏁板€兼枃妗ｅ潎鏈鏄庡共鎵版寚鏁颁笌 T 鍏紡鐨勫叧绯?",
            "evidence": "Racing spec.docx / paragraph 40; Racing numeric.docx / image 3",
            "risk": "鎵€鏈夊共棰勯€昏緫鏃犳硶杞垚浠ｇ爜",
            "suggestion": "涓篢uck 鎴?T 鍏紡琛ュ叆骞叉壈鎸囨暟鏄犲皠",
            "severity": "楂?",
            "confidence": "楂?",
            "blocking": "闃诲寮€鍙?",
        }
    ]

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertEqual(merged["document_quality_score"], "C")
    self.assertFalse(summary["score_downgraded"])
    self.assertEqual(summary["added_unique_findings"], 0)
    self.assertEqual(summary["added_unique_high_risk_findings"], 0)
    self.assertIn("骞叉壈鎸囨暟鏈笌閫熷害鎴栨椂闂村叕寮忓叧鑱旓紝寮€濂栧共棰勬棤娉曞疄鐜?", summary["duplicate_secondary_titles"])


def _patched_test_fusion_merge_dedupes_placeholder_exception_and_fake_data_rewrites(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    primary["dimensions"][0]["findings"] = [
        {
            "issue_id": "VAR_PLACEHOLDER",
            "title": "核心变量、阈值与分布规则大量占位符未定义",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "文档中大量使用[001]、[002]、[003]作为阈值、概率和更新间隔占位符，缺少默认值、可配范围与生效时机。",
            "evidence": "Racing spec.docx / paragraph 24; Racing spec.docx / paragraph 53",
            "risk": "状态机阈值无法配置，用户分层逻辑与测试用例都无法落地。",
            "suggestion": "补齐所有占位符。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]

    secondary = empty_report()
    secondary["dimensions"][0]["findings"] = [
        {
            "issue_id": "CLARITY-005",
            "title": "用户特征判断逻辑中的[001]~[003]等关键阈值全部缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "预流失用户定义中的累计下注阈值[001]、环比下降比例[002]、每日判断次数上限[003]均为占位符，没有默认值或可配范围。",
            "evidence": "Racing spec.docx / paragraph 53; Racing spec.docx / paragraph 24",
            "risk": "用户特征判断与状态机阈值无法配置，导致用户分层逻辑无法落地。",
            "suggestion": "补充阈值默认值和可配范围。",
            "severity": "中",
            "confidence": "中",
            "blocking": "阻塞开发",
        }
    ]

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertEqual(merged["document_quality_score"], "C")
    self.assertFalse(summary["score_downgraded"])
    self.assertEqual(summary["added_unique_findings"], 0)
    self.assertEqual(summary["added_unique_high_risk_findings"], 0)
    self.assertIn("用户特征判断逻辑中的[001]~[003]等关键阈值全部缺失", summary["duplicate_secondary_titles"])


def _patched_test_fusion_merge_downgrades_only_when_three_unique_high_risk_findings_added(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    primary["top_blockers"] = [
        {"severity": "高", "title": "Primary blocker", "owner": "planner", "why_now": "main risk"}
    ]
    secondary = empty_report()
    secondary["dimensions"][0]["findings"] = [
        {
            "issue_id": "A1",
            "title": "0下注局奖池结算存在除零风险",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "可能出现收入为0。",
            "evidence": "Racing numeric.docx / paragraph 8",
            "risk": "奖池公式崩溃。",
            "suggestion": "补零值分支。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        },
        {
            "issue_id": "A2",
            "title": "开奖时间公式变量Luck定义缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "缺少Luck定义。",
            "evidence": "Racing spec.docx / paragraph 18",
            "risk": "开奖逻辑无法实现。",
            "suggestion": "补变量定义。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        },
    ]

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertEqual(merged["document_quality_score"], "C")
    self.assertFalse(summary["score_downgraded"])

    secondary["dimensions"][0]["findings"].append(
        {
            "issue_id": "A3",
            "title": "UI展示赔率与实际结算赔率未强制服务端权威对齐",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "没有定义展示赔率与实际结算赔率的强制一致关系。",
            "evidence": "Racing spec.docx / paragraph 26",
            "risk": "展示赔率与真实结算可能出现双口径。",
            "suggestion": "补服务端权威下的赔率对齐规则。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    )

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertEqual(merged["document_quality_score"], "D")
    self.assertTrue(summary["score_downgraded"])
    self.assertEqual(summary["added_unique_high_risk_findings"], 3)


def _patched_test_fusion_merge_does_not_count_generic_authority_gap_as_high_risk(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    secondary = empty_report()
    secondary["dimensions"][0]["findings"] = [
        {
            "issue_id": "A1",
            "title": "0下注局奖池结算存在除零风险",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "可能出现收入为0。",
            "evidence": "Racing numeric.docx / paragraph 8",
            "risk": "奖池公式崩溃。",
            "suggestion": "补零值分支。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        },
        {
            "issue_id": "A2",
            "title": "开奖时间公式变量Luck定义缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "缺少Luck定义。",
            "evidence": "Racing spec.docx / paragraph 18",
            "risk": "开奖逻辑无法实现。",
            "suggestion": "补变量定义。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        },
        {
            "issue_id": "A3",
            "title": "服务端权威结算与客户端展示边界缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "没有定义结算权威边界。",
            "evidence": "Racing spec.docx / paragraph 26",
            "risk": "需要补充通用边界说明。",
            "suggestion": "补服务端权威规则。",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        },
    ]

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertEqual(merged["document_quality_score"], "C")
    self.assertFalse(summary["score_downgraded"])
    self.assertEqual(summary["added_unique_findings"], 3)
    self.assertEqual(summary["added_unique_high_risk_findings"], 2)


def _patched_test_fusion_merge_rebuilds_blockers_from_stabilized_findings(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    primary = empty_report()
    primary["document_quality_score"] = "C"
    primary["score_reason"] = "primary keeps C"
    primary["top_blockers"] = [
        {"severity": "高", "title": "关键阈值与配置占位符大量缺失", "owner": "planner", "why_now": "placeholder"},
        {
            "severity": "高",
            "title": "Requirement payout formula conflicts with numeric odds formula",
            "owner": "planner",
            "why_now": "main risk",
        },
    ]
    primary["dimensions"][0]["findings"] = [
        {
            "title": "关键阈值与配置占位符大量缺失",
            "primary_dimension": DIMENSIONS[0],
            "current_state": "document still uses [001] placeholders",
            "evidence": "Racing spec.docx / paragraph 12",
            "risk": "needs more config detail",
            "suggestion": "fill default values",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]
    primary["dimensions"][1]["findings"] = [
        {
            "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
            "title": "Requirement payout formula conflicts with numeric odds formula",
            "primary_dimension": DIMENSIONS[1],
            "current_state": "two docs define different formulas",
            "evidence": "Racing spec.docx / paragraph 2; Racing numeric.docx / paragraph 5",
            "risk": "implementation diverges",
            "suggestion": "keep one formula",
            "severity": "高",
            "confidence": "高",
            "blocking": "阻塞开发",
        }
    ]
    secondary = empty_report()

    merged, summary = merge_secondary_review_report(primary, secondary, docs, "gpt-5.4", "deepseek-v4-pro")

    self.assertFalse(summary["score_downgraded"])
    self.assertEqual(
        [item["title"] for item in merged["top_blockers"]],
        ["Requirement payout formula conflicts with numeric odds formula"],
    )


def _patched_test_fusion_mode_writes_dual_model_artifacts_and_merge_summary(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output_dir = root / "reports"
        agent = ReviewAgent(
            input_path=root,
            output_dir=output_dir,
            review_mode="fusion",
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

        primary_report = empty_report()
        primary_report["document_quality_score"] = "C"
        primary_report["score_reason"] = "primary keeps C"
        primary_report["top_blockers"] = [
            {"severity": "高", "title": "Primary blocker", "owner": "planner", "why_now": "main risk"}
        ]
        secondary_report = empty_report()
        secondary_report["dimensions"][2]["findings"].append(
            {
                "issue_id": "COMP_RECONNECT_REENTER_MISSING",
                "title": "重连重进后的状态恢复规则缺失",
                "primary_dimension": DIMENSIONS[2],
                "current_state": "没有说明异常恢复流程。",
                "evidence": "Racing spec.docx / paragraph 12",
                "risk": "异常恢复无法稳定实现。",
                "suggestion": "补充重连重进处理规则。",
                "severity": "中",
                "confidence": "高",
                "blocking": "阻塞测试用例设计",
            }
        )
        responses = {
            "primary": json.dumps(primary_report, ensure_ascii=False),
            "secondary": json.dumps(secondary_report, ensure_ascii=False),
        }

        agent._parse_documents = lambda assets_dir: [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
        agent._build_review_messages = lambda docs: [{"role": "user", "content": "fusion"}]
        agent._write_latest = lambda run_dir: None

        def fake_call(messages, client=None, config=None, stage="primary"):
            return responses[stage]

        agent._call_text_model = fake_call

        result = agent.run(extract_only=False)
        artifacts_dir = result.json_path.parent / "model_artifacts"
        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        primary_raw_text = (artifacts_dir / "primary_raw_model_response.txt").read_text(encoding="utf-8")
        merged_raw_text = (artifacts_dir / "raw_model_response.txt").read_text(encoding="utf-8")

        self.assertTrue((artifacts_dir / "primary_raw_model_response.txt").exists())
        self.assertTrue((artifacts_dir / "secondary_raw_model_response.txt").exists())
        self.assertTrue((artifacts_dir / "fusion_merge_summary.json").exists())
        self.assertEqual(payload["report"]["review_mode"], "fusion")
        self.assertEqual(payload["report"]["primary_model"], "gpt-5.4")
        self.assertEqual(payload["report"]["secondary_model"], "deepseek-v4-pro")
        self.assertIn("model: gpt-5.4", primary_raw_text)
        self.assertIn("stage: primary", primary_raw_text)
        self.assertIn("model: gpt-5.4", merged_raw_text)


def _patched_test_fusion_primary_only_keeps_cross_document_issue_shape(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output_dir = root / "reports"
        agent = ReviewAgent(
            input_path=root,
            output_dir=output_dir,
            review_mode="fusion",
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

        primary_report = empty_report()
        primary_report["document_quality_score"] = "C"
        primary_report["score_reason"] = "primary keeps C"
        primary_report["cross_document_issues"] = [
            {
                "issue_title": "Cross-document payout model split",
                "doc_a": "Racing spec.docx / paragraph 28",
                "doc_b": "Racing numeric.docx / paragraph 2-5",
                "conflict_description": "Requirement and numeric docs define incompatible payout formulas.",
                "severity": "高",
                "confidence": "高",
                "blocking": "阻塞开发",
            }
        ]

        agent._parse_documents = lambda assets_dir: [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
        agent._build_review_messages = lambda docs: [{"role": "user", "content": "fusion"}]
        agent._write_latest = lambda run_dir: None

        def fake_call(messages, client=None, config=None, stage="primary"):
            if stage == "secondary":
                raise RuntimeError("secondary unavailable")
            return json.dumps(primary_report, ensure_ascii=False)

        agent._call_text_model = fake_call

        result = agent.run(extract_only=False)
        payload = json.loads(result.json_path.read_text(encoding="utf-8"))
        report = payload["report"]

        self.assertEqual(report["fusion_summary"]["status"], "primary_only")
        self.assertEqual(len(report["cross_document_issues"]), 1)
        finding = report["cross_document_issues"][0]
        self.assertEqual(finding["title"], "Cross-document payout model split")
        self.assertEqual(
            finding["current_state"],
            "Requirement and numeric docs define incompatible payout formulas.",
        )
        self.assertTrue(finding["evidence"])
        self.assertEqual(finding["evidence_scope"], "cross_document")
        self.assertEqual(
            sum(
                1
                for dimension in report["dimensions"]
                for item in dimension["findings"]
                if item["title"] == "Cross-document payout model split"
            ),
            0,
        )


def _patched_test_replay_20260604_102114_keeps_raw_cross_issue_in_final_report(self) -> None:
    artifacts_dir = Path("reports/20260604_102114/model_artifacts")
    primary_path = artifacts_dir / "primary_raw_model_response.txt"
    secondary_path = artifacts_dir / "secondary_raw_model_response.txt"
    if not primary_path.exists() or not secondary_path.exists():
        self.skipTest("20260604_102114 model artifacts are not available in this workspace")

    docs = [
        make_doc("musee游戏Racing.docx", kind="mixed"),
        make_doc("Racing数值文档.docx", kind="numeric"),
    ]
    primary_raw = primary_path.read_text(encoding="utf-8")
    secondary_raw = secondary_path.read_text(encoding="utf-8")

    primary_report, primary_error = parse_model_json(primary_raw, docs)
    secondary_report, secondary_error = parse_model_json(secondary_raw, docs)
    merged, summary = merge_secondary_review_report(
        primary_report,
        secondary_report,
        docs,
        "gpt-5.4",
        "deepseek-v4-pro",
    )

    self.assertFalse(primary_error)
    self.assertFalse(secondary_error)
    self.assertEqual(len(primary_report["cross_document_issues"]), 1)
    self.assertEqual(len(merged["cross_document_issues"]), 1)
    self.assertEqual(merged["document_quality_score"], "C")
    self.assertEqual(summary["added_unique_high_risk_findings"], 1)

    cross_issue = merged["cross_document_issues"][0]
    self.assertTrue("赔率" in cross_issue["title"])
    self.assertTrue(any(keyword in cross_issue["title"] for keyword in ("公式", "模型", "分裂", "冲突")))
    assert_no_empty_public_finding_fields(self, merged)
    assert_cross_issues_not_misplaced(self, merged, [cross_issue["title"]])
    assert_top_blockers_have_matching_findings(self, merged)
    self.assertTrue(cross_issue["current_state"])
    self.assertTrue(cross_issue["evidence"])
    self.assertTrue(cross_issue["risk"])
    self.assertEqual(cross_issue["evidence_scope"], "cross_document")
    self.assertEqual(
        sum(
            1
            for dimension in merged["dimensions"]
            for finding in dimension["findings"]
            if finding["title"] == cross_issue["title"]
        ),
        0,
    )


def _patched_test_replay_20260603_175252_primary_only_keeps_cross_issue_shape(self) -> None:
    primary_path = Path("reports/20260603_175252/model_artifacts/primary_raw_model_response.txt")
    if not primary_path.exists():
        self.skipTest("20260603_175252 primary raw model artifact is not available in this workspace")

    docs = [
        make_doc("musee游戏Racing.docx", kind="mixed"),
        make_doc("Racing数值文档.docx", kind="numeric"),
    ]
    report, error = parse_model_json(primary_path.read_text(encoding="utf-8"), docs)

    self.assertFalse(error)
    self.assertEqual(report["document_quality_score"], "C")
    self.assertEqual(len(report["cross_document_issues"]), 1)

    cross_issue = report["cross_document_issues"][0]
    self.assertTrue("赔率" in cross_issue["title"])
    self.assertTrue(any(keyword in cross_issue["title"] for keyword in ("公式", "模型", "分裂", "冲突")))
    assert_no_empty_public_finding_fields(self, report)
    assert_cross_issues_not_misplaced(self, report, [cross_issue["title"]])
    assert_top_blockers_have_matching_findings(self, report)
    self.assertEqual(cross_issue["evidence_scope"], "cross_document")


def _patched_test_replay_20260603_104134_keeps_score_c_and_core_findings_high(self) -> None:
    artifacts_dir = Path("reports/20260603_104134/model_artifacts")
    primary_path = artifacts_dir / "primary_raw_model_response.txt"
    secondary_path = artifacts_dir / "secondary_raw_model_response.txt"
    if not primary_path.exists() or not secondary_path.exists():
        self.skipTest("20260603_104134 model artifacts are not available in this workspace")

    docs = [
        make_doc("musee游戏Racing.docx", kind="mixed"),
        make_doc("Racing数值文档.docx", kind="numeric"),
    ]
    primary_report, primary_error = parse_model_json(primary_path.read_text(encoding="utf-8"), docs)
    secondary_report, secondary_error = parse_model_json(secondary_path.read_text(encoding="utf-8"), docs)
    merged, summary = merge_secondary_review_report(
        primary_report,
        secondary_report,
        docs,
        "gpt-5.4",
        "deepseek-v4-pro",
    )

    self.assertFalse(primary_error)
    self.assertFalse(secondary_error)
    self.assertEqual(primary_report["document_quality_score"], "C")
    self.assertEqual(merged["document_quality_score"], "C")
    self.assertFalse(summary["score_downgraded"])
    self.assertEqual(summary["added_unique_high_risk_findings"], 0)
    assert_no_empty_public_finding_fields(self, merged)
    assert_top_blockers_have_matching_findings(self, merged)

    all_findings = [
        finding
        for dimension in merged.get("dimensions") or []
        for finding in dimension.get("findings") or []
        if isinstance(finding, dict)
    ] + [finding for finding in merged.get("cross_document_issues") or [] if isinstance(finding, dict)]

    def assert_high_finding_contains(text: str) -> None:
        self.assertTrue(
            any(text in str(finding.get("title") or "") and finding.get("severity") == "高" for finding in all_findings),
            f"missing high severity finding containing: {text}",
        )

    assert_high_finding_contains("赔率计算公式")
    assert_high_finding_contains("Luck")
    assert_high_finding_contains("奖池状态计算公式")
    assert_high_finding_contains("单选项最大赔付")
    assert_high_finding_contains("UI展示赔率")


def _patched_test_replay_20260604_113548_promotes_dimension_formula_conflict_to_cross_section(self) -> None:
    artifacts_dir = Path("reports/20260604_113548/model_artifacts")
    primary_path = artifacts_dir / "primary_raw_model_response.txt"
    secondary_path = artifacts_dir / "secondary_raw_model_response.txt"
    if not primary_path.exists() or not secondary_path.exists():
        self.skipTest("20260604_113548 model artifacts are not available in this workspace")

    docs = [
        make_doc("musee游戏Racing.docx", kind="mixed"),
        make_doc("Racing数值文档.docx", kind="numeric"),
    ]
    primary_report, primary_error = parse_model_json(primary_path.read_text(encoding="utf-8"), docs)
    secondary_report, secondary_error = parse_model_json(secondary_path.read_text(encoding="utf-8"), docs)
    merged, summary = merge_secondary_review_report(
        primary_report,
        secondary_report,
        docs,
        "gpt-5.4",
        "deepseek-v4-pro",
    )

    self.assertFalse(primary_error)
    self.assertFalse(secondary_error)
    self.assertEqual(primary_report["document_quality_score"], "C")
    self.assertEqual(merged["document_quality_score"], "C")
    self.assertFalse(summary["score_downgraded"])
    self.assertEqual(len(primary_report["cross_document_issues"]), 1)
    self.assertEqual(len(merged["cross_document_issues"]), 1)

    cross_issue = merged["cross_document_issues"][0]
    self.assertEqual(cross_issue["title"], "赔率计算公式双轨冲突与核心变量未定义")
    self.assertEqual(cross_issue["evidence_scope"], "cross_document")
    assert_no_empty_public_finding_fields(self, merged)
    assert_cross_issues_not_misplaced(self, merged, [cross_issue["title"]])
    assert_top_blockers_have_matching_findings(self, merged)


def _patched_test_parse_model_json_recovers_metadata_prefixed_json_with_unquoted_string_value(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    raw = (
        "model: gpt-5.4\n"
        "wire_api: responses\n"
        "stage: primary\n"
        "{\n"
        '  "overall_evaluation": "main flow is understandable",\n'
        '  "document_quality_score": "C",\n'
        '  "score_reason": "key rules still need clarification",\n'
        '  "top_blockers": [],\n'
        '  "dimensions": [\n'
        "    {\n"
        f'      "name": "{DIMENSIONS[1]}",\n'
        '      "dimension_note": "",\n'
        '      "findings": [\n'
        "        {\n"
        '          "title": "Intervention priority is undefined",\n'
        f'          "primary_dimension": "{DIMENSIONS[1]}",\n'
        '          "current_state": "The same round has multiple intervention paths with no execution order.",\n'
        '          "evidence": "Racing spec.docx / paragraph 51; Racing numeric.docx / paragraph 3",\n'
        '          "risk": logic conflict may override settlement expectations,\n'
        '          "suggestion": "Define priority and stacking rules.",\n'
        '          "severity": "高",\n'
        '          "confidence": "高",\n'
        '          "blocking": "阻塞开发"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "cross_document_issues": [],\n'
        '  "missing_information": [],\n'
        '  "test_points": {},\n'
        '  "quality_notes": []\n'
        "}\n"
    )

    report, error = parse_model_json(raw, docs)

    self.assertFalse(error)
    self.assertEqual(report["document_quality_score"], "C")
    logic_findings = report["dimensions"][1]["findings"]
    self.assertEqual(len(logic_findings), 1)
    self.assertEqual(logic_findings[0]["risk"], "logic conflict may override settlement expectations")


def _patched_test_parse_model_json_recovers_duplicated_closing_quotes_in_array_items(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    raw = (
        "model: deepseek-v4-pro\n"
        "wire_api: responses\n"
        "stage: secondary\n"
        "{\n"
        '  "overall_evaluation": "main flow is understandable",\n'
        '  "document_quality_score": "C",\n'
        '  "score_reason": "core rules still need alignment",\n'
        '  "top_blockers": [],\n'
        '  "dimensions": [\n'
        "    {\n"
        f'      "name": "{DIMENSIONS[0]}",\n'
        '      "dimension_note": "",\n'
        '      "findings": []\n'
        "    }\n"
        "  ],\n"
        '  "cross_document_issues": [],\n'
        '  "missing_information": [],\n'
        '  "quality_notes": [],\n'
        '  "test_points": {\n'
        '    "功能验证": [\n'
        '      "正常下注→开奖→结算全流程",\n'
        '      "新用户/预流失干预是否按条件触发"""\n'
        "    ]\n"
        "  }\n"
        "}\n"
    )

    report, error = parse_model_json(raw, docs)

    self.assertFalse(error)
    self.assertEqual(report["document_quality_score"], "C")
    self.assertEqual(report["test_points"]["功能验证"][-1], "新用户/预流失干预是否按条件触发")


def _patched_test_parse_model_json_recovers_invalid_backslashes_in_quoted_strings(self) -> None:
    docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
    raw = (
        "model: gpt-5.4\n"
        "wire_api: responses\n"
        "stage: primary\n"
        "{\n"
        '  "overall_evaluation": "main flow is understandable",\n'
        '  "document_quality_score": "C",\n'
        '  "score_reason": "core rules still need alignment",\n'
        '  "top_blockers": [],\n'
        '  "dimensions": [\n'
        "    {\n"
        f'      "name": "{DIMENSIONS[0]}",\n'
        '      "dimension_note": "",\n'
        '      "findings": [\n'
        "        {\n"
        '          "title": "Big win thresholds are undefined",\n'
        f'          "primary_dimension": "{DIMENSIONS[0]}",\n'
        '          "current_state": "Spec only says show big win\\mega win\\super win based on multipliers.",\n'
        '          "evidence": "Racing spec.docx / paragraph 12",\n'
        '          "risk": "UI thresholds cannot be configured consistently.",\n'
        '          "suggestion": "Define exact thresholds for each win tier.",\n'
        '          "severity": "浣?",\n'
        '          "confidence": "楂?",\n'
        '          "blocking": "寤鸿浼樺寲"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "cross_document_issues": [],\n'
        '  "missing_information": [],\n'
        '  "quality_notes": [],\n'
        '  "test_points": {}\n'
        "}\n"
    )

    report, error = parse_model_json(raw, docs)

    self.assertFalse(error)
    self.assertEqual(report["document_quality_score"], "C")
    finding = report["dimensions"][0]["findings"][0]
    self.assertEqual(
        finding["current_state"],
        "Spec only says show big win\\mega win\\super win based on multipliers.",
    )


StabilityModeTests.test_merge_recommendations_merge_same_root_titles = _patched_test_merge_recommendations_merge_same_root_titles
StabilityModeTests.test_merge_recommendations_can_match_issue_marker_suffix = _patched_test_merge_recommendations_can_match_issue_marker_suffix
StabilityModeTests.test_parse_model_json_preserves_model_score_and_top_blockers = _patched_test_parse_model_json_preserves_model_score_and_top_blockers
StabilityModeTests.test_parse_model_json_drops_low_priority_model_blockers_after_stabilization = _patched_test_parse_model_json_drops_low_priority_model_blockers_after_stabilization
StabilityModeTests.test_parse_model_json_keeps_primary_formula_mapping_and_locking_blockers_distinct = _patched_test_parse_model_json_keeps_primary_formula_mapping_and_locking_blockers_distinct
StabilityModeTests.test_strict_audit_treats_formula_conflict_rewording_as_duplicate = _patched_test_strict_audit_treats_formula_conflict_rewording_as_duplicate
StabilityModeTests.test_cli_accepts_fusion_review_mode = _patched_test_cli_accepts_fusion_review_mode
StabilityModeTests.test_model_config_from_prefixed_env = _patched_test_model_config_from_prefixed_env
StabilityModeTests.test_fusion_merge_adds_unique_secondary_finding_with_source = _patched_test_fusion_merge_adds_unique_secondary_finding_with_source
StabilityModeTests.test_fusion_merge_skips_duplicate_secondary_finding = _patched_test_fusion_merge_skips_duplicate_secondary_finding
StabilityModeTests.test_fusion_merge_dedupes_secondary_cross_issue_with_describe_and_source_docs = _patched_test_fusion_merge_dedupes_secondary_cross_issue_with_describe_and_source_docs
StabilityModeTests.test_fusion_merge_dedupes_secondary_intervention_rewrite_by_root_cluster = _patched_test_fusion_merge_dedupes_secondary_intervention_rewrite_by_root_cluster
StabilityModeTests.test_fusion_merge_dedupes_placeholder_exception_and_fake_data_rewrites = _patched_test_fusion_merge_dedupes_placeholder_exception_and_fake_data_rewrites
StabilityModeTests.test_fusion_merge_downgrades_only_when_three_unique_high_risk_findings_added = _patched_test_fusion_merge_downgrades_only_when_three_unique_high_risk_findings_added
StabilityModeTests.test_fusion_merge_does_not_count_generic_authority_gap_as_high_risk = _patched_test_fusion_merge_does_not_count_generic_authority_gap_as_high_risk
StabilityModeTests.test_fusion_merge_rebuilds_blockers_from_stabilized_findings = _patched_test_fusion_merge_rebuilds_blockers_from_stabilized_findings
StabilityModeTests.test_fusion_mode_writes_dual_model_artifacts_and_merge_summary = _patched_test_fusion_mode_writes_dual_model_artifacts_and_merge_summary
StabilityModeTests.test_fusion_primary_only_keeps_cross_document_issue_shape = _patched_test_fusion_primary_only_keeps_cross_document_issue_shape
StabilityModeTests.test_replay_20260604_102114_keeps_raw_cross_issue_in_final_report = _patched_test_replay_20260604_102114_keeps_raw_cross_issue_in_final_report
StabilityModeTests.test_replay_20260603_175252_primary_only_keeps_cross_issue_shape = _patched_test_replay_20260603_175252_primary_only_keeps_cross_issue_shape
StabilityModeTests.test_replay_20260603_104134_keeps_score_c_and_core_findings_high = _patched_test_replay_20260603_104134_keeps_score_c_and_core_findings_high
StabilityModeTests.test_replay_20260604_113548_promotes_dimension_formula_conflict_to_cross_section = _patched_test_replay_20260604_113548_promotes_dimension_formula_conflict_to_cross_section
StabilityModeTests.test_parse_model_json_recovers_metadata_prefixed_json_with_unquoted_string_value = _patched_test_parse_model_json_recovers_metadata_prefixed_json_with_unquoted_string_value
StabilityModeTests.test_parse_model_json_recovers_duplicated_closing_quotes_in_array_items = _patched_test_parse_model_json_recovers_duplicated_closing_quotes_in_array_items
StabilityModeTests.test_parse_model_json_recovers_invalid_backslashes_in_quoted_strings = _patched_test_parse_model_json_recovers_invalid_backslashes_in_quoted_strings


if __name__ == "__main__":
    unittest.main()
