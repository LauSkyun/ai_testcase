from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rad_review.prompts import DIMENSIONS
from rad_review.reporting.normalize import NO_FINDINGS_NOTE, normalize_report
from rad_review.reporting.render import write_report_files
from rad_review.reporting.schema import validate_report_integrity
from tests.test_report import make_doc, make_report


class ReportIntegrityTests(unittest.TestCase):
    def test_validate_report_integrity_flags_cross_section_duplicates(self) -> None:
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "title": "同一根因被写进单维度",
                        "current_state": "维度区版本",
                        "evidence": "spec.docx / 段落1",
                        "risk": "会让读者误判问题数量。",
                    }
                ]
            },
            cross_document_issues=[
                {
                    "title": "同一根因被写进单维度",
                    "current_state": "跨文档区版本",
                    "evidence": "spec.docx / 段落1；numeric.docx / 段落2",
                    "risk": "同一问题会被重复渲染。",
                }
            ],
        )

        errors = validate_report_integrity(normalize_report(report))

        self.assertTrue(errors)
        self.assertIn("重复问题", "".join(errors))

    def test_validate_report_integrity_reuses_pipeline_identity_rules(self) -> None:
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "title": "同名但不同维度的问题",
                        "primary_dimension": DIMENSIONS[0],
                        "current_state": "维度区版本",
                        "evidence": "spec.docx / 段落1",
                        "risk": "如果 identity 规则不一致，这里会误报重复。",
                    }
                ]
            },
            cross_document_issues=[
                {
                    "title": "同名但不同维度的问题",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "跨文档区版本",
                    "evidence": "spec.docx / 段落8；numeric.docx / 段落2",
                    "risk": "应由主管线的 identity 规则决定是否视为同一问题。",
                }
            ],
        )

        errors = validate_report_integrity(normalize_report(report))

        self.assertNotIn("重复问题", "".join(errors))

    def test_write_report_files_sanitizes_dimension_note_without_mutating_core_findings(self) -> None:
        docs = [make_doc("spec.docx")]
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "title": "下注边界缺少上限",
                        "current_state": "文档没写最大下注值。",
                        "evidence": "spec.docx / 段落3",
                        "risk": "客户端和服务端可能做出不同限制。",
                    }
                ]
            }
        )
        report["dimensions"][1]["dimension_note"] = "閺堫亜褰傞悳鐗堟閺勯箖妫舵０?"
        original_title = report["dimensions"][0]["findings"][0]["title"]
        original_note = report["dimensions"][1]["dimension_note"]

        with tempfile.TemporaryDirectory() as temp_dir:
            markdown_path = Path(temp_dir) / "review_report.md"
            json_path = Path(temp_dir) / "review_report.json"
            write_report_files(report, docs, markdown_path, json_path)
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(report["dimensions"][0]["findings"][0]["title"], original_title)
        self.assertEqual(report["dimensions"][1]["dimension_note"], original_note)
        self.assertEqual(payload["report"]["dimensions"][1]["dimension_note"], NO_FINDINGS_NOTE)
        self.assertEqual(payload["report"]["dimensions"][0]["findings"][0]["title"], original_title)

    def test_write_report_files_rejects_orphan_top_blocker(self) -> None:
        docs = [make_doc("spec.docx")]
        report = make_report()
        report["top_blockers"] = [{"title": "报告里不存在的阻塞项", "severity": "高"}]

        with tempfile.TemporaryDirectory() as temp_dir:
            markdown_path = Path(temp_dir) / "review_report.md"
            json_path = Path(temp_dir) / "review_report.json"
            with self.assertRaisesRegex(ValueError, "完整性检查失败"):
                write_report_files(report, docs, markdown_path, json_path)


if __name__ == "__main__":
    unittest.main()
