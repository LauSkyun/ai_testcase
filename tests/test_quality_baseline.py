from __future__ import annotations

import json
import unittest
from pathlib import Path

from rad_review.docx_reader import ParsedDocument, ParagraphBlock
from rad_review.prompts import DIMENSIONS
from rad_review.reporting.normalize import normalize_report
from rad_review.reporting.stabilize import stabilize_report


BASELINE_PATH = Path("quality_baselines/chicken_manual_baseline.json")


def make_doc(name: str, kind: str = "mixed") -> ParsedDocument:
    return ParsedDocument(
        path=name,
        name=name,
        kind=kind,
        paragraphs=[ParagraphBlock(index=1, text="小鸡玩法基准文档")],
        tables=[],
        images=[],
        errors=[],
    )


class QualityBaselineTests(unittest.TestCase):
    def test_chicken_baseline_is_machine_readable(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(baseline["expected_score"], "C")
        self.assertGreaterEqual(len(baseline["required_issue_categories"]), 5)
        self.assertIn("forbidden_false_positive_patterns", baseline)

    def test_chicken_baseline_style_scores_c_without_drift_to_d(self) -> None:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        docs = [make_doc("小鸡需求文档.docx"), make_doc("小鸡数值文档.docx", kind="numeric")]
        report = {
            "overall_evaluation": "",
            "document_quality_score": "",
            "score_reason": "",
            "dimensions": [{"name": dimension, "dimension_note": "", "findings": []} for dimension in DIMENSIONS],
            "cross_document_issues": [],
        }
        titles = [
            "术语、步数、格子和关卡单位需要统一",
            "筹码、难度、倍率配置映射缺少正式表",
            "扣款、结算、发奖和提现时机需要补齐",
            "断线重进后的局内状态恢复规则缺失",
            "最大赔付边界需要明确到配置字段",
        ]
        for title in titles:
            report["dimensions"][0]["findings"].append(
                {
                    "title": title,
                    "current_state": "主流程可理解，但该边界缺少可执行说明。",
                    "evidence": "小鸡需求文档.docx / 段落1；小鸡数值文档.docx / 表格1",
                    "risk": "开发和测试需要补文档后才能完整覆盖。",
                    "suggestion": "补充字段、状态和验收例子。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            )

        stabilized = stabilize_report(normalize_report(report), docs)
        self.assertEqual(stabilized["document_quality_score"], baseline["expected_score"])
        self.assertEqual(sum(len(dimension["findings"]) for dimension in stabilized["dimensions"]), 5)


if __name__ == "__main__":
    unittest.main()
