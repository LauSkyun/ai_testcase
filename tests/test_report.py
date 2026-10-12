from __future__ import annotations

import unittest

from rad_review.docx_reader import ParsedDocument, ParagraphBlock
from rad_review.prompts import DIMENSIONS
from rad_review.reporting.normalize import (
    normalize_compare_text,
    normalize_report,
    normalize_unmatched_finding,
    repair_missing_issue_ids,
)
from rad_review.reporting.render import render_markdown
from rad_review.reporting.stabilize import are_duplicate_findings, stabilize_report


def make_doc(name: str, text: str = "正文内容", kind: str = "mixed") -> ParsedDocument:
    return ParsedDocument(
        path=name,
        name=name,
        kind=kind,
        paragraphs=[ParagraphBlock(index=1, text=text)],
        tables=[],
        images=[],
        errors=[],
    )


def make_report(
    findings_by_dimension: dict[str, list[dict]] | None = None,
    cross_document_issues: list[dict] | None = None,
) -> dict:
    findings_by_dimension = findings_by_dimension or {}
    return {
        "overall_evaluation": "",
        "document_quality_score": "",
        "score_reason": "",
        "dimensions": [
            {
                "name": dimension,
                "dimension_note": "",
                "findings": list(findings_by_dimension.get(dimension, [])),
            }
            for dimension in DIMENSIONS
        ],
        "cross_document_issues": list(cross_document_issues or []),
    }


def iter_public_findings(report: dict) -> list[dict]:
    findings: list[dict] = []
    for dimension in report.get("dimensions") or []:
        findings.extend(finding for finding in dimension.get("findings") or [] if isinstance(finding, dict))
    findings.extend(finding for finding in report.get("cross_document_issues") or [] if isinstance(finding, dict))
    return findings


def assert_no_empty_public_finding_fields(testcase: unittest.TestCase, report: dict) -> None:
    for finding in iter_public_findings(report):
        title = str(finding.get("title") or finding.get("canonical_title") or "").strip()
        if not title:
            continue
        testcase.assertTrue(
            any(str(finding.get(key) or "").strip() for key in ("current_state", "evidence", "risk")),
            f"finding has no public detail fields: {title}",
        )


def assert_cross_issues_not_misplaced(testcase: unittest.TestCase, report: dict, expected_titles: list[str]) -> None:
    cross_titles = {
        normalize_compare_text(str(finding.get("title") or finding.get("canonical_title") or ""))
        for finding in report.get("cross_document_issues") or []
        if isinstance(finding, dict)
    }
    dimension_titles = {
        normalize_compare_text(str(finding.get("title") or finding.get("canonical_title") or ""))
        for dimension in report.get("dimensions") or []
        for finding in dimension.get("findings") or []
        if isinstance(finding, dict)
    }
    for title in expected_titles:
        normalized = normalize_compare_text(title)
        testcase.assertIn(normalized, cross_titles)
        testcase.assertNotIn(normalized, dimension_titles)


def assert_top_blockers_have_matching_findings(testcase: unittest.TestCase, report: dict) -> None:
    finding_titles = {
        normalize_compare_text(str(finding.get(key) or ""))
        for finding in iter_public_findings(report)
        for key in ("title", "canonical_title")
        if str(finding.get(key) or "").strip()
    }
    for blocker in report.get("top_blockers") or []:
        title = normalize_compare_text(str(blocker.get("title") or ""))
        if title:
            testcase.assertIn(title, finding_titles)


class ReportNormalizationTests(unittest.TestCase):
    def test_distinct_atomic_findings_are_not_merged_by_broad_semantic_overlap(self) -> None:
        docs = [
            make_doc("LUCKY77 转盘投注游戏设计方案.md", kind="requirement"),
            make_doc("LUCKT 77 数值文档.md", kind="numeric"),
        ]
        report = make_report(
            {
                DIMENSIONS[1]: [
                    {
                        "issue_id": "bonus_prob_conflict",
                        "canonical_title": "额外奖励触发概率跨文档冲突",
                        "title": "额外奖励触发概率跨文档严重冲突（55% vs 29%）",
                        "current_state": "需求文档写明额外奖励触发概率为55%，数值文档配置为29%。",
                        "evidence": "LUCKY77 转盘投注游戏设计方案.md / 段落29；LUCKT 77 数值文档.md / 表格5",
                        "risk": "额外奖励概率不一致会导致RTP偏离。",
                        "suggestion": "统一额外奖励触发概率，并明确固定值或动态映射。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                    {
                        "issue_id": "config_mapping_conflict",
                        "canonical_title": "基础配置跨文档冲突",
                        "title": "符号名称与筹码挡位配置不一致",
                        "current_state": "符号名称使用李子/番茄两种口径，筹码挡位分别为4档和6档。",
                        "evidence": "LUCKY77 转盘投注游戏设计方案.md / 表格2、表格8；LUCKT 77 数值文档.md / 表格2、表格8",
                        "risk": "资源映射和投注配置无法形成唯一实现。",
                        "suggestion": "分别统一符号字段和筹码挡位配置。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                ],
                DIMENSIONS[5]: [
                    {
                        "issue_id": "countdown_interaction",
                        "canonical_title": "倒计时阶段交互反馈与下注截止逻辑不明确",
                        "title": "倒计时阶段交互反馈与下注截止逻辑不明确",
                        "current_state": "倒计时阶段是否允许继续下注以及点击反馈未定义。",
                        "evidence": "LUCKY77 转盘投注游戏设计方案.md / 表格7",
                        "risk": "玩家无法确认倒计时期间的下注是否成功。",
                        "suggestion": "单独明确倒计时开始后的下注截止与Toast反馈。",
                        "severity": "中",
                        "confidence": "高",
                        "blocking": "阻塞测试用例设计",
                    }
                ],
            },
            cross_document_issues=[
                {
                    "issue_id": "broad_config_conflict",
                    "canonical_title": "基础配置跨文档多处不一致",
                    "title": "概率、符号名称与筹码挡位存在多处跨文档冲突",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "1. 额外奖励概率为55%和29%。2. 符号名为李子和番茄。3. 筹码挡位为4档和6档。",
                    "evidence": "LUCKY77 转盘投注游戏设计方案.md / 表格2、表格8；LUCKT 77 数值文档.md / 表格2、表格5、表格8",
                    "risk": "多个配置项无法对齐。",
                    "suggestion": "分别统一概率、符号名称和筹码挡位。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        findings = {finding["issue_id"]: finding for finding in iter_public_findings(stabilized)}

        self.assertIn("bonus_prob_conflict", findings)
        self.assertIn("config_mapping_conflict__SYMBOL_NAMING", findings)
        self.assertIn("config_mapping_conflict__CHIP_TIERS", findings)
        self.assertIn("countdown_interaction", findings)
        self.assertNotIn("broad_config_conflict", findings)
        bonus = findings["bonus_prob_conflict"]
        bonus_text = " ".join(str(bonus.get(field) or "") for field in ("current_state", "risk", "suggestion"))
        self.assertNotIn("筹码", bonus_text)
        self.assertNotIn("倒计时", bonus_text)
        self.assertNotIn("番茄", bonus_text)
        symbol = findings["config_mapping_conflict__SYMBOL_NAMING"]
        chip = findings["config_mapping_conflict__CHIP_TIERS"]
        self.assertNotIn("筹码", " ".join(str(symbol.get(field) or "") for field in ("title", "current_state", "risk", "suggestion")))
        self.assertNotIn("符号", " ".join(str(chip.get(field) or "") for field in ("title", "current_state", "risk", "suggestion")))
        self.assertEqual(stabilized["finding_atomicity_status"], "pass")
        self.assertEqual(stabilized["finding_atomicity_suspect_count"], 0)
        transforms = stabilized["atomicity_transform_diagnostics"]
        self.assertGreaterEqual(transforms["split_source_count"], 1)
        self.assertGreaterEqual(transforms["suppressed_fully_covered_umbrella_count"], 1)

    def test_unresolvable_multiroot_finding_is_quarantined_from_default_report(self) -> None:
        docs = [make_doc("混合需求.docx", kind="requirement")]
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "issue_id": "mixed_unstructured",
                        "title": "符号名称和筹码档位存在混合问题",
                        "current_state": "当前配置整体无法确认，原文没有按对象分别描述。",
                        "evidence": "混合需求.docx / 段落1",
                        "risk": "多个配置对象无法关闭。",
                        "suggestion": "需要重新核对符号名称和筹码档位。",
                        "severity": "高",
                        "confidence": "中",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        finding_ids = {finding["issue_id"] for finding in iter_public_findings(stabilized)}
        self.assertNotIn("mixed_unstructured", finding_ids)
        self.assertEqual(stabilized["finding_atomicity_status"], "pass")
        self.assertEqual(len(stabilized["finding_atomicity_review_queue"]), 1)
        self.assertEqual(
            stabilized["finding_atomicity_review_queue"][0]["source_finding"]["issue_id"],
            "mixed_unstructured",
        )
        self.assertEqual(stabilized["atomicity_transform_diagnostics"]["quarantined_count"], 1)
        markdown = render_markdown(stabilized, docs)
        self.assertIn("原子化待人工拆分队列", markdown)
        self.assertIn("符号名称和筹码档位存在混合问题", markdown)
        self.assertIn("不计入正式 Finding", markdown)

    def test_same_atomic_issue_merges_evidence_without_stacking_detail_blocks(self) -> None:
        docs = [
            make_doc("LUCKY77 转盘投注游戏设计方案.md", kind="requirement"),
            make_doc("LUCKT 77 数值文档.md", kind="numeric"),
        ]
        report = make_report(
            {
                DIMENSIONS[1]: [
                    {
                        "issue_id": "bonus_prob_conflict",
                        "title": "额外奖励触发概率冲突",
                        "current_state": "需求文档为55%，数值配置为29%。",
                        "evidence": "LUCKY77 转盘投注游戏设计方案.md / 段落29",
                        "risk": "RTP计算口径不一致。",
                        "suggestion": "统一额外奖励概率。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                    {
                        "issue_id": "bonus_prob_conflict",
                        "title": "额外奖励概率55%与29%不一致",
                        "current_state": "同一额外奖励概率在数值表中配置为29%，在需求正文中写为55%。",
                        "evidence": "LUCKT 77 数值文档.md / 表格5",
                        "risk": "服务端无法选择唯一触发概率。",
                        "suggestion": "确认唯一概率字段及其配置来源。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        findings = [finding for finding in iter_public_findings(stabilized) if finding.get("issue_id") == "bonus_prob_conflict"]

        self.assertEqual(len(findings), 1)
        merged = findings[0]
        self.assertIn("段落29", merged["evidence"])
        self.assertIn("表格5", merged["evidence"])
        self.assertNotIn("；", merged["current_state"])
        self.assertNotIn("；", merged["risk"])
        self.assertNotIn("；", merged["suggestion"])

    def test_normalize_unmatched_finding_fills_all_public_detail_fields(self) -> None:
        finding = normalize_unmatched_finding(
            {
                "issue_id": "DETAIL_1",
                "title": "规则边界缺失",
                "severity": "中",
                "confidence": "高",
                "blocking": "阻塞测试用例设计",
                "planner_role": "系统策划",
            },
            DIMENSIONS[0],
        )

        for field in ("current_state", "evidence", "risk", "suggestion"):
            self.assertTrue(str(finding.get(field) or "").strip(), field)

    def test_repair_missing_issue_ids_prefers_canonical_issue_id(self) -> None:
        report = make_report(
            {
                DIMENSIONS[1]: [
                    {
                        "title": "核心赔率计算公式在需求与数值文档中存在严重冲突",
                        "current_state": "需求与数值文档给出了两套不一致的赔率计算逻辑。",
                        "evidence": "Racing spec.docx / paragraph 28; Racing numeric.docx / paragraph 3",
                        "risk": "开发无法形成唯一结算方案。",
                        "suggestion": "统一唯一赔率公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )

        repaired, repairs = repair_missing_issue_ids(report)
        finding = repaired["dimensions"][1]["findings"][0]

        self.assertEqual(finding["issue_id"], "LOGIC_PAYOUT_FORMULA_CONFLICT")
        self.assertEqual(len(repairs), 1)
        self.assertEqual(repairs[0]["repair_kind"], "canonical")

    def test_repair_missing_issue_ids_builds_stable_synthetic_id(self) -> None:
        raw_finding = {
            "title": "排行榜入口视觉层级缺少说明",
            "current_state": "文档未说明排行榜入口在主界面与弹窗之间的层级关系。",
            "evidence": "777 spec.docx / paragraph 26",
            "risk": "前端实现可能出现遮挡。",
            "suggestion": "补充入口层级和遮挡规则。",
            "severity": "中",
            "confidence": "中",
            "blocking": "阻塞测试用例设计",
        }

        repaired_a, repairs_a = repair_missing_issue_ids(make_report({DIMENSIONS[3]: [dict(raw_finding)]}))
        repaired_b, repairs_b = repair_missing_issue_ids(make_report({DIMENSIONS[3]: [dict(raw_finding)]}))
        issue_id_a = repaired_a["dimensions"][3]["findings"][0]["issue_id"]
        issue_id_b = repaired_b["dimensions"][3]["findings"][0]["issue_id"]

        self.assertEqual(issue_id_a, issue_id_b)
        self.assertTrue(issue_id_a.startswith("COMP_GEN_"))
        self.assertEqual(repairs_a[0]["repair_kind"], "synthetic")
        self.assertEqual(repairs_b[0]["repair_kind"], "synthetic")

    def test_report_integrity_helpers_accept_stabilized_report(self) -> None:
        docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
        report = make_report(
            {
                DIMENSIONS[1]: [
                    {
                        "title": "Critical payout cap is missing",
                        "current_state": "The requirement allows negative pool values without a payout cap.",
                        "evidence": "Racing spec.docx / paragraph 37",
                        "risk": "Extreme payouts can drain the pool.",
                        "suggestion": "Define a max payout and pool fuse.",
                        "severity": "楂?",
                        "confidence": "楂?",
                        "blocking": "闃诲寮€鍙?",
                    }
                ]
            },
            cross_document_issues=[
                {
                    "title": "Cross-document settlement mismatch",
                    "doc1_evidence": "Racing spec.docx / paragraph 28",
                    "doc2_evidence": "Racing numeric.docx / paragraph 3",
                    "impact": "The two formulas cannot both be settlement rules.",
                    "severity": "楂?",
                    "confidence": "楂?",
                    "blocking": "闃诲寮€鍙?",
                }
            ],
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        assert_no_empty_public_finding_fields(self, stabilized)
        assert_cross_issues_not_misplaced(self, stabilized, ["Cross-document settlement mismatch"])
        assert_top_blockers_have_matching_findings(self, stabilized)

    def test_legacy_term_like_text_is_not_filtered(self) -> None:
        docs = [make_doc("赛车需求.docx", "这里没有历史项目词，但需求确实在讨论玩法问题。")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "title": "小鸡玩法下注口径说明不完整",
                        "current_state": "文档只写了玩法名，没有说明下注上限。",
                        "evidence": "赛车需求.docx / 段落1",
                        "risk": "开发无法确定边界。",
                        "suggestion": "补充下注上限和口径。",
                        "severity": "中",
                        "confidence": "高",
                        "blocking": "阻塞测试用例设计",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        findings = stabilized["dimensions"][0]["findings"]

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["title"], "小鸡玩法下注口径说明不完整")

    def test_canonical_issue_keeps_model_title_for_display(self) -> None:
        docs = [make_doc("赛车需求.docx")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "issue_id": "CORE_BET_CONFIG_MISMATCH",
                        "title": "下注公式与赔率口径对不上",
                        "current_state": "文档里的下注口径前后不一致。",
                        "evidence": "赛车需求.docx / 段落2",
                        "risk": "会直接影响赔付实现。",
                        "suggestion": "统一下注公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        finding = stabilized["dimensions"][0]["findings"][0]

        self.assertEqual(finding["title"], "下注公式与赔率口径对不上")
        self.assertEqual(finding["canonical_title"], "下注金额或档位配置口径不一致")

    def test_single_document_cross_document_section_is_cleared(self) -> None:
        docs = [make_doc("赛车需求.docx")]
        report = make_report(
            cross_document_issues=[
                {
                    "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                    "title": "赔率公式跨文档冲突",
                    "primary_dimension": "逻辑一致性与数值平衡",
                    "current_state": "模型误把单文档问题写成跨文档。",
                    "evidence": "赛车需求.docx / 段落3",
                    "risk": "会误导读者判断输入结构。",
                    "suggestion": "按单文档问题处理。",
                    "severity": "中",
                    "confidence": "高",
                    "blocking": "阻塞测试用例设计",
                }
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(stabilized["cross_document_issues"], [])

    def test_raw_cross_issue_shape_is_preserved(self) -> None:
        docs = [make_doc("musee游戏Racing.docx"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            cross_document_issues=[
                {
                    "issue_title": "赔率公式相互矛盾",
                    "doc1": "musee游戏Racing.docx 段落28：实时赔率=合计下注/本选项下注×[001]%",
                    "doc2": "Racing数值文档.docx 段落2-5：odds=max(T×(1-x)/W, 1.02)×γ",
                    "description": "两个文档给出的赔率算法完全不同。",
                    "severity": "高",
                }
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(len(stabilized["cross_document_issues"]), 1)
        finding = stabilized["cross_document_issues"][0]
        self.assertEqual(finding["title"], "赔率公式相互矛盾")
        self.assertEqual(finding["current_state"], "两个文档给出的赔率算法完全不同。")
        self.assertIn("musee游戏Racing.docx", finding["evidence"])
        self.assertIn("Racing数值文档.docx", finding["evidence"])
        self.assertEqual(finding["evidence_scope"], "cross_document")

    def test_cross_issue_with_doc_a_doc_b_is_kept_in_cross_document_section(self) -> None:
        docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
        report = make_report(
            cross_document_issues=[
                {
                    "issue_title": "跨文档赔率模型冲突",
                    "doc_a": "Racing spec.docx / paragraph 28",
                    "doc_b": "Racing numeric.docx / paragraph 2-5",
                    "conflict_description": "Requirement and numeric docs define incompatible payout models.",
                    "severity": "高",
                }
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(len(stabilized["cross_document_issues"]), 1)
        finding = stabilized["cross_document_issues"][0]
        self.assertEqual(finding["title"], "跨文档赔率模型冲突")
        self.assertEqual(
            finding["current_state"],
            "Requirement and numeric docs define incompatible payout models.",
        )
        self.assertTrue(finding["evidence"])
        self.assertEqual(finding["evidence_scope"], "cross_document")
        self.assertEqual(
            sum(
                1
                for dimension in stabilized["dimensions"]
                for item in dimension["findings"]
                if item["title"] == "跨文档赔率模型冲突"
            ),
            0,
        )

    def test_normalize_unmatched_finding_maps_describe_source_docs_and_impact(self) -> None:
        finding = normalize_unmatched_finding(
            {
                "issue_id": "CROSS-001",
                "title": "需求文档与数值文档的赔率计算体系冲突",
                "describe": "需求和数值文档给出了不同的赔率计算体系。",
                "source_docs": ["Racing需求文档.docx / 段落28", "Racing数值文档.docx / 段落2-5"],
                "impact": "开发无法统一结算方案。",
                "suggestion": "统一唯一赔率公式。",
            },
            DIMENSIONS[0],
        )

        self.assertEqual(finding["current_state"], "需求和数值文档给出了不同的赔率计算体系。")
        self.assertEqual(finding["risk"], "开发无法统一结算方案。")
        self.assertEqual(finding["evidence"], "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落2-5")

    def test_normalize_unmatched_finding_maps_doc_a_doc_b_and_conflict_description(self) -> None:
        finding = normalize_unmatched_finding(
            {
                "issue_title": "跨文档赔率公式冲突",
                "doc_a": "Racing spec.docx / paragraph 28",
                "doc_b": "Racing numeric.docx / paragraph 2-5",
                "conflict_description": "Requirement and numeric docs define different payout formulas.",
                "severity": "高",
            },
            DIMENSIONS[1],
        )

        self.assertEqual(finding["title"], "跨文档赔率公式冲突")
        self.assertEqual(finding["current_state"], "Requirement and numeric docs define different payout formulas.")
        self.assertIn("Racing spec.docx / paragraph 28", finding["evidence"])
        self.assertIn("Racing numeric.docx / paragraph 2-5", finding["evidence"])

    def test_normalize_unmatched_finding_maps_doc_evidence_and_impact(self) -> None:
        finding = normalize_unmatched_finding(
            {
                "title": "Cross-document payout model split",
                "doc1_evidence": "Racing spec.docx / paragraph 28",
                "doc2_evidence": "Racing numeric.docx / paragraph 3",
                "impact": "The two formulas cannot both be implemented as settlement rules.",
                "severity": "高",
            },
            DIMENSIONS[1],
        )

        self.assertIn("Racing spec.docx / paragraph 28", finding["current_state"])
        self.assertIn("Racing numeric.docx / paragraph 3", finding["current_state"])
        self.assertIn("Racing spec.docx / paragraph 28", finding["evidence"])
        self.assertIn("Racing numeric.docx / paragraph 3", finding["evidence"])
        self.assertEqual(finding["risk"], "The two formulas cannot both be implemented as settlement rules.")

    def test_cross_issue_with_doc_evidence_is_kept_in_cross_document_section(self) -> None:
        docs = [make_doc("Racing spec.docx"), make_doc("Racing numeric.docx", kind="numeric")]
        report = make_report(
            cross_document_issues=[
                {
                    "title": "Cross-document payout model split",
                    "doc1_evidence": "Racing spec.docx / paragraph 28",
                    "doc2_evidence": "Racing numeric.docx / paragraph 3",
                    "impact": "The two formulas cannot both be implemented as settlement rules.",
                    "severity": "高",
                }
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(len(stabilized["cross_document_issues"]), 1)
        finding = stabilized["cross_document_issues"][0]
        self.assertEqual(finding["title"], "Cross-document payout model split")
        self.assertEqual(finding["evidence_scope"], "cross_document")
        self.assertIn("Racing spec.docx / paragraph 28", finding["evidence"])
        self.assertIn("Racing numeric.docx / paragraph 3", finding["evidence"])
        self.assertEqual(finding["risk"], "The two formulas cannot both be implemented as settlement rules.")
        self.assertEqual(
            sum(
                1
                for dimension in stabilized["dimensions"]
                for item in dimension["findings"]
                if item["title"] == "Cross-document payout model split"
            ),
            0,
        )

    def test_cross_document_issue_with_one_document_reference_is_downgraded(self) -> None:
        docs = [make_doc("需求文档A.docx"), make_doc("数值文档B.docx")]
        report = make_report(
            cross_document_issues=[
                {
                    "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                    "title": "赔率公式口径冲突",
                    "primary_dimension": "逻辑一致性与数值平衡",
                    "current_state": "模型声称跨文档，但证据只引用了一份文档。",
                    "evidence": "需求文档A.docx / 段落3",
                    "risk": "会制造虚假的跨文档结论。",
                    "suggestion": "先按普通逻辑问题归档。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        logic_findings = stabilized["dimensions"][1]["findings"]

        self.assertEqual(stabilized["cross_document_issues"], [])
        self.assertEqual(len(logic_findings), 1)
        self.assertEqual(logic_findings[0]["title"], "赔率公式口径冲突")
        self.assertEqual(logic_findings[0]["evidence_scope"], "document")

    def test_formula_and_fake_odds_display_gaps_remain_separate_atomic_findings(self) -> None:
        primary = normalize_unmatched_finding(
            {
                "issue_id": "CROSS_DOC_01",
                "_root_cause_cluster": "formula_odds_conflict",
                "title": "Requirement and numeric docs use conflicting odds formulas",
                "current_state": "Two documents define incompatible payout formulas.",
                "evidence": "Racing spec.docx / paragraph 28; Racing numeric.docx / paragraph 3",
                "risk": "Implementation cannot choose one payout path.",
                "suggestion": "Keep a single payout formula.",
                "severity": "楂?",
                "confidence": "楂?",
                "blocking": "闃诲寮€鍙?",
            },
            DIMENSIONS[1],
        )
        secondary = normalize_unmatched_finding(
            {
                "issue_id": "CLR-001",
                "_root_cause_cluster": "formula_odds_conflict",
                "title": "Odds formula conflict and fake odds concept are not aligned",
                "current_state": "Requirement and numeric docs describe two odds systems.",
                "evidence": "Racing spec.docx / paragraph 28; Racing numeric.docx / paragraph 3",
                "risk": "Displayed odds and settlement odds can diverge.",
                "suggestion": "Treat fake odds as display-only and keep one real payout formula.",
                "severity": "楂?",
                "confidence": "楂?",
                "blocking": "闃诲寮€鍙?",
            },
            DIMENSIONS[0],
        )

        self.assertFalse(are_duplicate_findings(primary, secondary))

    def test_placeholder_root_cause_cluster_counts_as_duplicate(self) -> None:
        primary = normalize_unmatched_finding(
            {
                "issue_id": "VAR_PLACEHOLDER",
                "title": "核心变量、阈值与分布规则大量占位符未定义",
                "current_state": "文档中大量使用[001]、[002]、[003]作为阈值、概率和更新间隔占位符，缺少默认值、可配范围与生效时机。",
                "evidence": "Racing spec.docx / paragraph 24; Racing spec.docx / paragraph 53",
                "risk": "状态机阈值无法配置，用户分层逻辑与测试用例都无法落地。",
                "suggestion": "补齐所有占位符。",
                "severity": "高",
                "confidence": "高",
                "blocking": "阻塞开发",
            },
            DIMENSIONS[0],
        )
        secondary = normalize_unmatched_finding(
            {
                "issue_id": "CLARITY-005",
                "title": "用户特征判断逻辑中的[001]~[003]等关键阈值全部缺失",
                "current_state": "预流失用户定义中的累计下注阈值[001]、环比下降比例[002]、每日判断次数上限[003]均为占位符，没有默认值或可配范围。",
                "evidence": "Racing spec.docx / paragraph 53; Racing spec.docx / paragraph 24",
                "risk": "用户特征判断与状态机阈值无法配置，导致用户分层逻辑无法落地。",
                "suggestion": "补充阈值默认值和可配范围。",
                "severity": "中",
                "confidence": "中",
                "blocking": "阻塞开发",
            },
            DIMENSIONS[0],
        )

        self.assertTrue(are_duplicate_findings(primary, secondary))

    def test_exception_recovery_root_cause_cluster_counts_as_duplicate(self) -> None:
        primary = normalize_unmatched_finding(
            {
                "issue_id": "EXCEPTION_FLOW",
                "title": "异常流程与断线重连恢复规则完全缺失",
                "current_state": "文档仅描述正常下注、开奖、弹窗流程，未定义下注阶段断线重连、结算中退出、重复点击下注和倒计时不同步等异常场景处理规则。",
                "evidence": "Racing spec.docx / paragraph 7; Racing spec.docx / paragraph 42",
                "risk": "异常流程无法验收，容易出现重复扣款、状态卡死与结算不同步。",
                "suggestion": "补状态机恢复表。",
                "severity": "中",
                "confidence": "高",
                "blocking": "阻塞测试用例设计",
            },
            DIMENSIONS[2],
        )
        secondary = normalize_unmatched_finding(
            {
                "issue_id": "TEST-001",
                "title": "重进恢复、断线重连、下注阶段退出、开奖阶段崩溃等异常场景完全未定义",
                "current_state": "文档未提及重进恢复、断线重连、下注阶段退出、开奖阶段崩溃后的恢复策略，也未说明是否保留原轮下注状态和结算结果。",
                "evidence": "Racing spec.docx / paragraph 7; Racing spec.docx / paragraph 42",
                "risk": "上线后容易出现状态卡死、重复扣款与结算结果不同步，异常场景无法验收。",
                "suggestion": "补充异常恢复规则。",
                "severity": "低",
                "confidence": "中",
                "blocking": "建议优化",
            },
            DIMENSIONS[2],
        )

        self.assertTrue(are_duplicate_findings(primary, secondary))

    def test_reconnect_alias_issue_ids_count_as_duplicate_without_forcing_public_issue_id(self) -> None:
        primary = normalize_unmatched_finding(
            {
                "issue_id": "exception_recovery",
                "title": "异常流程(重进/断线/热更)缺失专属规则",
                "current_state": "文档未提及下注中、开奖中、结算中退出或断线重连时的状态恢复、筹码退还或结果同步规则。",
                "evidence": "musee游戏Racing.docx / 全文",
                "risk": "缺失会导致测试用例覆盖不全，线上可能出现状态卡死或重复扣款。",
                "suggestion": "补充玩法专属的断线重连状态机表。",
                "severity": "中",
                "confidence": "中",
                "blocking": "阻塞测试用例设计",
            },
            DIMENSIONS[2],
        )
        secondary = normalize_unmatched_finding(
            {
                "issue_id": "RECONNECT_HANDLING",
                "title": "未说明玩家在游戏中断线、退出或重进时的状态恢复规则",
                "current_state": "文档没有描述用户在倒计时、下注后、开奖阶段等不同阶段断开连接或重进游戏时的恢复逻辑。",
                "evidence": "全文档缺失",
                "risk": "可能导致玩家下注丢失、重复扣款或无法看到结果。",
                "suggestion": "补充各阶段的断线重连与重进恢复方案。",
                "severity": "中",
                "confidence": "中",
                "blocking": "阻塞测试用例设计",
            },
            DIMENSIONS[2],
        )

        self.assertTrue(are_duplicate_findings(primary, secondary))
        self.assertEqual(primary["issue_id"], "exception_recovery")
        self.assertEqual(secondary["issue_id"], "RECONNECT_HANDLING")

    def test_fake_data_isolation_root_cause_cluster_counts_as_duplicate(self) -> None:
        primary = normalize_unmatched_finding(
            {
                "issue_id": "FAKE_DATA_SYNC",
                "title": "虚拟数据（假人数/金额）与真实结算数据的同步与隔离边界不清",
                "current_state": "假人数/金额每1秒更新并乘系数展示，但未明确实时赔率计算中的合计下注是否包含假数据，以及假数据是否参与奖池注入或扣除。",
                "evidence": "Racing spec.docx / paragraph 22; Racing spec.docx / paragraph 23",
                "risk": "假数据一旦混入赔率计算、奖池或真实赔付链路，会直接造成真实结算失真。",
                "suggestion": "明确假数据仅用于展示。",
                "severity": "中",
                "confidence": "中",
                "blocking": "阻塞测试用例设计",
            },
            DIMENSIONS[3],
        )
        secondary = normalize_unmatched_finding(
            {
                "issue_id": "SEC-002",
                "title": "客户端展示的假人数和假金额乘系数，但需求未要求服务端隔离来源，可能错用于计算真实赔率",
                "current_state": "客户端展示层使用乘系数后的假人数和假金额，但服务端未声明实时赔率、奖池和真实结算只使用真实下注数据，存在来源混用风险。",
                "evidence": "Racing spec.docx / paragraph 22-23; Racing spec.docx / paragraph 22",
                "risk": "如果服务端误将展示层假值用于赔率计算、奖池或赔付，会直接产生真实结算错误。",
                "suggestion": "声明服务端只使用真实下注数据。",
                "severity": "中",
                "confidence": "中",
                "blocking": "阻塞测试用例设计",
            },
            DIMENSIONS[4],
        )

        self.assertTrue(are_duplicate_findings(primary, secondary))

    def test_same_issue_merges_and_keeps_first_high_signal_title(self) -> None:
        docs = [make_doc("赛车需求.docx")]
        report = make_report(
            {
                "逻辑一致性与数值平衡": [
                    {
                        "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                        "title": "赔率描述略有歧义",
                        "current_state": "第一处描述偏模糊。",
                        "evidence": "赛车需求.docx / 段落4",
                        "risk": "测试理解可能不一致。",
                        "suggestion": "补一句说明。",
                        "severity": "低",
                        "confidence": "中",
                        "blocking": "建议优化",
                    },
                    {
                        "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                        "title": "高风险赔率赔付公式冲突",
                        "current_state": "第二处显示两个赔付公式互相冲突。",
                        "evidence": "赛车需求.docx / 段落7",
                        "risk": "会直接导致错误赔付。",
                        "suggestion": "统一最终赔付公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        finding = stabilized["dimensions"][1]["findings"][0]

        self.assertEqual(finding["title"], "高风险赔率赔付公式冲突")
        self.assertEqual(finding["severity"], "高")
        self.assertEqual(finding["blocking"], "阻塞开发")
        self.assertIn("赛车需求.docx / 段落4", finding["evidence"])
        self.assertIn("赛车需求.docx / 段落7", finding["evidence"])

    def test_empty_issue_ids_do_not_auto_canonical_merge_raw_findings(self) -> None:
        docs = [make_doc("musee游戏Racing.docx"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "title": "关键配置字段大量使用占位符[001]等，无法进入开发与测试",
                        "current_state": "文档中多处使用[001]、[002]等占位符。",
                        "evidence": "musee游戏Racing.docx / 段落22",
                        "risk": "无法进入开发和测试。",
                        "suggestion": "补齐全部配置值。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
                "逻辑一致性与数值平衡": [
                    {
                        "issue_id": "odds_formula_conflict",
                        "title": "需求文档的实时赔率公式与数值文档的Odds公式矛盾，无法实现",
                        "current_state": "需求写实时赔率，数值文档写Odds=max(T×(1-x)/W, 1.02)×γ。",
                        "evidence": "musee游戏Racing.docx / 段落28；Racing数值文档.docx / 段落2-5",
                        "risk": "无法实现一致的赔率逻辑。",
                        "suggestion": "统一赔率公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                    {
                        "title": "假赔率概念仅在数值文档出现，需求未定义，展示与结算口径分裂",
                        "current_state": "需求文档没有假赔率定义。",
                        "evidence": "Racing数值文档.docx / 段落5；musee游戏Racing.docx / 段落16",
                        "risk": "展示赔率与真实结算可能口径不一致。",
                        "suggestion": "补充假赔率定义及适用边界。",
                        "severity": "中",
                        "confidence": "高",
                        "blocking": "阻塞测试用例设计",
                    },
                    {
                        "title": "干扰指数、Luck随机扰动与gamma系数关系未定义，开奖结果无法落地",
                        "current_state": "Luck 和 gamma 的关系没有统一定义。",
                        "evidence": "musee游戏Racing.docx / 段落36；Racing数值文档.docx / 段落4",
                        "risk": "开奖结果无法稳定落地。",
                        "suggestion": "定义干扰指数、Luck、gamma 的映射关系。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                ],
                "安全性与反作弊": [
                    {
                        "title": "假人数/假金额的数据源是否隔离于真实赔率计算和奖池统计未明确",
                        "current_state": "假数据和真实赔率、奖池是否共用数据源未定义。",
                        "evidence": "musee游戏Racing.docx / 段落22-28",
                        "risk": "可能污染真实赔率和奖池统计。",
                        "suggestion": "定义假数据与真实数据的隔离边界。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
            },
            cross_document_issues=[
                {
                    "issue_title": "赔率公式相互矛盾",
                    "doc1": "musee游戏Racing.docx 段落28：实时赔率=合计下注/本选项下注×[001]%",
                    "doc2": "Racing数值文档.docx 段落2-5：odds=max(T×(1-x)/W, 1.02)×γ",
                    "description": "两个文档给出的赔率算法完全不同，且数值文档引入假赔率，未在需求文档体现。",
                    "severity": "高",
                }
            ],
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        clarity_titles = [finding["title"] for finding in stabilized["dimensions"][0]["findings"]]
        logic_titles = [finding["title"] for finding in stabilized["dimensions"][1]["findings"]]
        security_titles = [finding["title"] for finding in stabilized["dimensions"][4]["findings"]]
        cross_titles = [finding["title"] for finding in stabilized["cross_document_issues"]]

        self.assertEqual(clarity_titles, [])
        self.assertIn(
            "假赔率概念仅在数值文档出现，需求未定义，展示与结算口径分裂",
            logic_titles,
            stabilized.get("dedupe_diagnostics"),
        )
        self.assertIn("干扰指数、Luck随机扰动与gamma系数关系未定义，开奖结果无法落地", logic_titles)
        self.assertEqual(security_titles, ["假人数/假金额的数据源是否隔离于真实赔率计算和奖池统计未明确"])
        self.assertEqual(
            cross_titles,
            ["需求文档的实时赔率公式与数值文档的Odds公式矛盾，无法实现"],
            stabilized.get("dedupe_diagnostics"),
        )

    def test_two_high_fixable_findings_after_policy_downgrade_can_score_b(self) -> None:
        docs = [make_doc("小鸡需求文档.docx"), make_doc("小鸡数值文档.docx", kind="numeric")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "title": "格子、马路、关卡的核心概念混用",
                        "current_state": "主流程可理解，但挑战单位需要统一。",
                        "evidence": "需求文档 / 段落1；数值文档 / 段落3",
                        "risk": "开发和测试会按不同步数理解。",
                        "suggestion": "补充术语和状态表。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                    {
                        "title": "筹码配置跨文档不一致",
                        "current_state": "两份文档的筹码档位不同。",
                        "evidence": "需求文档 / 表格1；数值文档 / 表格1",
                        "risk": "配置验收无法对齐。",
                        "suggestion": "建立正式配置表。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                ],
                "可测试性与验收标准": [
                    {
                        "title": "重进游戏后的局内恢复规则缺失",
                        "current_state": "文档未说明已扣款未结算时如何恢复。",
                        "evidence": "需求文档 / 全文",
                        "risk": "测试无法覆盖恢复路径。",
                        "suggestion": "补充重进恢复规则。",
                        "severity": "高",
                        "confidence": "中",
                        "blocking": "阻塞测试用例设计",
                    }
                ],
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(stabilized["document_quality_score"], "B")

    def test_fewer_than_three_nonfatal_high_findings_score_b(self) -> None:
        docs = [make_doc("Racing需求文档.docx"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "title": "奖池干预目标选择规则仍缺少一条明确边界",
                        "current_state": "主流程可理解，但奖池充裕分支还少一个明确限制。",
                        "evidence": "Racing需求文档.docx / 段落20",
                        "risk": "实现时可能出现一处条件判断分叉。",
                        "suggestion": "补齐边界条件与示例。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
                "逻辑一致性与数值平衡": [
                    {
                        "title": "W=0 展示赔率默认值未写死",
                        "current_state": "展示口径还有一个默认值待补。",
                        "evidence": "Racing需求文档.docx / 段落28",
                        "risk": "前端展示与验收口径可能暂时不一致。",
                        "suggestion": "补齐默认展示值。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞测试用例设计",
                    }
                ],
                "可测试性与验收标准": [
                    {
                        "title": "组合验收矩阵还缺一组模板数据",
                        "current_state": "验收维度已基本完整，仅少一组组合回放模板。",
                        "evidence": "Racing需求文档.docx / 段落45",
                        "risk": "测试设计需要补一个模板。",
                        "suggestion": "增加一组回放样例。",
                        "severity": "中",
                        "confidence": "中",
                        "blocking": "阻塞测试用例设计",
                    }
                ],
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(stabilized["document_quality_score"], "B")

    def test_fatal_cross_document_formula_conflict_scores_d_with_generic_doc_aliases(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            cross_document_issues=[
                {
                    "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                    "title": "赔率公式在需求与数值文档中存在根本性矛盾",
                    "primary_dimension": "逻辑一致性与数值平衡",
                    "current_state": "需求文档与数值文档给出的赔率公式无法兼容。",
                    "evidence": "需求文档 / 段落28；数值文档 / 段落2",
                    "risk": "服务端和客户端会形成不同结算方案。",
                    "suggestion": "统一唯一赔率公式。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(stabilized["document_quality_score"], "D")
        self.assertEqual(len(stabilized["cross_document_issues"]), 1)

    def test_top_blockers_prioritize_core_gameplay_over_generic_security(self) -> None:
        docs = [make_doc("玩法需求.docx")]
        report = make_report(
            {
                "安全性与反作弊": [
                    {
                        "title": "服务端权威判定与防篡改规则缺失",
                        "current_state": "文档未强调服务端权威。",
                        "evidence": "玩法需求.docx / 全文",
                        "risk": "存在安全风险。",
                        "suggestion": "补充服务端权威说明。",
                        "severity": "高",
                        "confidence": "中",
                        "blocking": "阻塞开发",
                    }
                ],
                "逻辑一致性与数值平衡": [
                    {
                        "title": "筹码、难度、赔率映射缺失",
                        "current_state": "核心配置无法对齐。",
                        "evidence": "玩法需求.docx / 表格1",
                        "risk": "开发无法落配置。",
                        "suggestion": "补充映射表。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(stabilized["top_blockers"][0]["title"], "筹码、难度、赔率映射缺失")

    def test_placeholder_config_gap_is_suppressed(self) -> None:
        docs = [make_doc("玩法需求.docx")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "title": "关键配置字段仍使用占位符[001]，且默认值与可配范围未给出",
                        "current_state": "文档只给了占位符，没有默认值、字段清单和可配范围。",
                        "evidence": "玩法需求.docx / 段落12",
                        "risk": "需要后续补齐配置细节。",
                        "suggestion": "补充配置默认值、范围和字段清单。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        self.assertEqual(stabilized["dimensions"][0]["findings"], [])
        self.assertEqual(stabilized["top_blockers"], [])

    def test_placeholder_payout_extremes_are_not_treated_as_risk(self) -> None:
        docs = [make_doc("未付费用户单机版游戏.md")]
        report = make_report(
            {
                "逻辑一致性与数值平衡": [
                    {
                        "issue_id": "LOGIC_02",
                        "title": "图片配置表存在大量占位符且核心赔付极值未定义",
                        "current_state": "图片1中概率配置均为[001]%等占位符，且最大赔付、最小赔付无具体数值或计算公式。",
                        "evidence": "未付费用户单机版游戏.md / 图片1",
                        "risk": "核心概率与赔付极值缺失，导致后端无法实现开奖逻辑。",
                        "suggestion": "补充占位符具体值与赔付极值。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )
        report["quality_notes"] = [
            "图片1中的概率配置均为[001]%等占位符，无法进行实际数值验收。",
            "文档未提供配置表结构、字段说明及默认值。",
        ]
        report["image_analysis_gaps"] = [
            "图片1为[001]%占位符格式，无法确认具体概率值。"
        ]

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(stabilized["dimensions"][1]["findings"], [])
        self.assertEqual(stabilized["top_blockers"], [])
        self.assertEqual(stabilized["quality_notes"], [])
        self.assertEqual(stabilized["image_analysis_gaps"], [])

    def test_real_formula_conflict_is_kept_when_placeholder_is_mentioned(self) -> None:
        docs = [make_doc("玩法需求.docx")]
        report = make_report(
            {
                "逻辑一致性与数值平衡": [
                    {
                        "title": "占位符公式与固定概率表口径冲突",
                        "current_state": "公式使用[001]%，但同一条件下表格明确写为20%，两处不一致。",
                        "evidence": "玩法需求.docx / 公式1、表格2",
                        "risk": "同一条件存在两套结算口径。",
                        "suggestion": "统一公式与表格口径。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(len(stabilized["dimensions"][1]["findings"]), 1)

    def test_reconnect_hotfix_and_server_authority_are_downgraded_to_low(self) -> None:
        docs = [make_doc("玩法需求.docx")]
        report = make_report(
            {
                "跨系统影响与兼容性": [
                    {
                        "title": "断线重连与热更历史局恢复规则缺失",
                        "current_state": "文档未写断线重连、热更和历史局恢复。",
                        "evidence": "玩法需求.docx / 段落20",
                        "risk": "后续需要补充恢复规则。",
                        "suggestion": "补充弱网、重进和热更说明。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
                "安全性与反作弊": [
                    {
                        "title": "服务端权威判定与防篡改规则缺失",
                        "current_state": "文档未强调服务端权威。",
                        "evidence": "玩法需求.docx / 全文",
                        "risk": "需要补充通用边界说明。",
                        "suggestion": "补充服务端权威说明。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        cross_finding = stabilized["dimensions"][3]["findings"][0]
        sec_finding = stabilized["dimensions"][4]["findings"][0]

        self.assertEqual(cross_finding["severity"], "低")
        self.assertEqual(cross_finding["blocking"], "建议优化")
        self.assertEqual(sec_finding["severity"], "低")
        self.assertEqual(sec_finding["blocking"], "建议优化")

    def test_core_formula_payout_and_actual_settlement_gaps_are_not_downgraded(self) -> None:
        docs = [make_doc("Racing需求文档.docx")]
        report = make_report(
            {
                "逻辑一致性与数值平衡": [
                    {
                        "title": "赔率计算公式多版本冲突且关键变量无定义",
                        "current_state": "同一玩法出现两套赔率公式，且关键变量没有统一定义。",
                        "evidence": "Racing需求文档.docx / 段落28",
                        "risk": "赔率与结算实现会直接分叉。",
                        "suggestion": "统一唯一赔率公式并补齐变量定义。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                    {
                        "title": "奖池状态计算公式存在除零风险且抽水参数x未定义",
                        "current_state": "收入为0或负值时，奖池状态公式没有兜底。",
                        "evidence": "Racing需求文档.docx / 段落36",
                        "risk": "奖池结算链路会直接失效。",
                        "suggestion": "补零值分支并定义抽水参数。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                ],
                "安全性与反作弊": [
                    {
                        "title": "单选项最大赔付无上限且下注接口缺乏幂等与防重设计",
                        "current_state": "下注和赔付上限没有闭环约束。",
                        "evidence": "Racing需求文档.docx / 段落42",
                        "risk": "极端赔率下可能产生资损。",
                        "suggestion": "补充最大赔付上限和幂等防重规则。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                    {
                        "title": "UI展示赔率与实际结算赔率未强制服务端权威对齐",
                        "current_state": "展示赔率与实际结算赔率缺少强制一致规则。",
                        "evidence": "Racing需求文档.docx / 段落45",
                        "risk": "客户端展示与真实结算可能出现双口径。",
                        "suggestion": "明确展示赔率和实际结算赔率的唯一权威关系。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    },
                ],
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        kept_titles = {
            finding["title"]: (finding["severity"], finding["blocking"])
            for dimension in stabilized["dimensions"]
            for finding in dimension["findings"]
        }

        self.assertEqual(kept_titles["赔率计算公式多版本冲突且关键变量无定义"], ("高", "阻塞开发"))
        self.assertEqual(kept_titles["奖池状态计算公式存在除零风险且抽水参数x未定义"], ("高", "阻塞开发"))
        self.assertEqual(kept_titles["单选项最大赔付无上限且下注接口缺乏幂等与防重设计"], ("高", "阻塞开发"))
        self.assertEqual(kept_titles["UI展示赔率与实际结算赔率未强制服务端权威对齐"], ("高", "阻塞开发"))

    def test_guide_conflict_is_capped_at_medium(self) -> None:
        docs = [make_doc("Racing需求.docx")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "issue_id": "GUIDE-ODDS-CONFLICT",
                        "title": "引导演示赔率3.3与1.90两处描述矛盾",
                        "current_state": "新手引导文案写 3.3，玩法正式规则写 1.90。",
                        "evidence": "Racing需求.docx / 段落12、段落76",
                        "risk": "新手阶段对赔率理解可能产生偏差。",
                        "suggestion": "统一引导与正式玩法中的赔率口径。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        finding = stabilized["dimensions"][0]["findings"][0]

        self.assertEqual(finding["severity"], "中")
        self.assertEqual(finding["blocking"], "阻塞测试用例设计")

    def test_restabilize_keeps_formula_conflict_high_when_risk_mentions_new_user(self) -> None:
        docs = [make_doc("Racing spec.docx", kind="requirement"), make_doc("Racing numeric.docx", kind="numeric")]
        report = make_report(
            cross_document_issues=[
                {
                    "issue_id": "formula_conflict",
                    "title": "赔率公式变量冲突与结算口径分裂",
                    "primary_dimension": DIMENSIONS[0],
                    "current_state": "开奖公式中T为完成时间，但赔率公式中T疑似代表总下注额，变量定义与赔付口径冲突。",
                    "evidence": "Racing spec.docx / paragraph 36; Racing numeric.docx / paragraph 2-3",
                    "risk": "开发与测试无法确定实际结算使用的公式。新手易产生预期偏差，若首局实际赔率与展示默认值差异过大，可能引发客诉。",
                    "suggestion": "统一实际赔付公式与展示公式，并补充默认值切换规则。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ]
        )

        first = stabilize_report(normalize_report(report), docs)
        second = stabilize_report(normalize_report(first), docs)

        self.assertEqual(first["cross_document_issues"][0]["severity"], "高")
        self.assertEqual(first["cross_document_issues"][0]["blocking"], "阻塞开发")
        self.assertEqual(second["cross_document_issues"][0]["severity"], "高")
        self.assertEqual(second["cross_document_issues"][0]["blocking"], "阻塞开发")

    def test_generic_guide_gap_is_downgraded_to_low(self) -> None:
        docs = [make_doc("Racing需求.docx")]
        report = make_report(
            {
                "用户体验与游戏性": [
                    {
                        "issue_id": "GUIDE-MISSING-HINT",
                        "title": "新手引导未说明问号按钮作用",
                        "current_state": "教程里没有提到问号入口。",
                        "evidence": "Racing需求.docx / 段落47",
                        "risk": "新手对入口理解成本略高。",
                        "suggestion": "在教程中补一句按钮说明。",
                        "severity": "高",
                        "confidence": "中",
                        "blocking": "阻塞开发",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        finding = stabilized["dimensions"][5]["findings"][0]

        self.assertEqual(finding["severity"], "低")
        self.assertEqual(finding["blocking"], "建议优化")

    def test_cross_document_finding_is_not_duplicated_in_dimension_and_cross_section(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            {
                "逻辑一致性与数值平衡": [
                    {
                        "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                        "title": "赔率公式跨文档冲突",
                        "primary_dimension": "逻辑一致性与数值平衡",
                        "current_state": "需求和数值文档给出了不同赔率公式。",
                        "evidence": "Racing需求文档.docx / 段落2；Racing数值文档.docx / 段落5",
                        "risk": "赔付实现会分叉。",
                        "suggestion": "统一唯一赔率公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                        "evidence_scope": "cross_document",
                    }
                ]
            },
            cross_document_issues=[
                {
                    "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                    "title": "需求文档实时赔率公式与数值文档Odds公式结构冲突",
                    "primary_dimension": "逻辑一致性与数值平衡",
                    "current_state": "需求和数值文档给出了不同赔率公式。",
                    "evidence": "Racing需求文档.docx / 段落2；Racing数值文档.docx / 段落5",
                    "risk": "赔付实现会分叉。",
                    "suggestion": "统一唯一赔率公式。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        self.assertEqual(stabilized["dimensions"][1]["findings"], [])
        self.assertEqual(len(stabilized["cross_document_issues"]), 1)
        self.assertEqual(stabilized["cross_document_issues"][0]["issue_id"], "LOGIC_PAYOUT_FORMULA_CONFLICT")

    def test_similar_issue_across_dimension_and_cross_section_is_deduped(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            {
                "清晰度与完整性": [
                    {
                        "issue_id": "CLAR-006",
                        "canonical_title": "假赔率与实际赔率使用场景未说明",
                        "title": "数值文档区分实际赔率和假赔率，但需求文档未提及假赔率展示逻辑",
                        "primary_dimension": "清晰度与完整性",
                        "current_state": "需求文档没有说明假赔率的展示方式。",
                        "evidence": "Racing数值文档.docx / 段落5；Racing需求文档.docx / 段落28",
                        "risk": "客户端展示和真实赔付可能不一致。",
                        "suggestion": "补充假赔率展示时机。",
                        "severity": "中",
                        "confidence": "中",
                        "blocking": "阻塞测试用例设计",
                    }
                ]
            },
            cross_document_issues=[
                {
                    "issue_id": "CROSS-002",
                    "canonical_title": "实际赔率与假赔率使用场景未对齐",
                    "title": "数值文档提出实际/假赔率之分，需求文档未描述假赔率的展示机制",
                    "primary_dimension": "清晰度与完整性",
                    "current_state": "需求文档没有说明假赔率的展示方式。",
                    "evidence": "Racing数值文档.docx / 段落5；Racing需求文档.docx / 段落28",
                    "risk": "客户端展示和真实赔付可能不一致。",
                    "suggestion": "补充假赔率展示时机。",
                    "severity": "中",
                    "confidence": "中",
                    "blocking": "阻塞测试用例设计",
                }
            ],
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        all_titles = [
            finding["title"]
            for dimension in stabilized["dimensions"]
            for finding in dimension["findings"]
        ] + [finding["title"] for finding in stabilized["cross_document_issues"]]

        self.assertEqual(len([title for title in all_titles if "假赔率" in title and "实际" in title]), 1)

    def test_formula_cluster_merges_fake_odds_and_formula_conflict(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "issue_id": "CLAR-006",
                        "canonical_title": "假赔率与实际赔率使用场景未说明",
                        "title": "数值文档区分实际赔率和假赔率，但需求文档未描述假赔率的展示机制",
                        "primary_dimension": DIMENSIONS[0],
                        "current_state": "需求文档没有说明假赔率何时展示、如何与实际赔付赔率区分。",
                        "evidence": "Racing数值文档.docx / 段落5；Racing需求文档.docx / 段落28",
                        "risk": "客户端展示赔率与真实赔付赔率可能不一致。",
                        "suggestion": "补充展示赔率与实际赔率的使用边界。",
                        "severity": "中",
                        "confidence": "中",
                        "blocking": "阻塞测试用例设计",
                    }
                ]
            },
            cross_document_issues=[
                {
                    "issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT",
                    "title": "需求文档实时赔率公式与数值文档赔率+gamma体系存在根本分歧",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "需求文档和数值文档对赔率公式的定义不一致。",
                    "evidence": "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落2-5",
                    "risk": "开发会形成不同的赔付实现方案。",
                    "suggestion": "统一赔率公式并说明展示赔率与实际赔率关系。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                }
            ],
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        self.assertEqual(len(stabilized["cross_document_issues"]), 1)
        self.assertEqual(len(stabilized["dimensions"][0]["findings"]), 1)
        self.assertIn("假赔率", stabilized["dimensions"][0]["findings"][0]["title"])
        self.assertIn("赔率", stabilized["cross_document_issues"][0]["title"])

    def test_intervention_mapping_and_formula_conflict_do_not_merge(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            cross_document_issues=[
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
                },
                {
                    "issue_id": "CROSS-002",
                    "title": "流程文档的干扰指数与数值文档的Luck随机扰动未建立映射",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "干扰指数和 Luck 都会影响结果，但未说明它们如何对应。",
                    "evidence": "Racing需求文档.docx / 段落43；Racing数值文档.docx / 表格3",
                    "risk": "无法验证干预链路是否按策划意图生效。",
                    "suggestion": "补充干扰指数、Luck、T 公式的映射关系。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                },
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        self.assertEqual(len(stabilized["cross_document_issues"]), 2)

    def test_intervention_mapping_cluster_suppresses_placeholder_and_keeps_terrain_gap(self) -> None:
        docs = [make_doc("Racing需求文档.docx")]
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "issue_id": "CLARITY_01",
                        "title": "核心阈值与概率占位符([001]等)泛滥且无默认值/边界",
                        "primary_dimension": DIMENSIONS[0],
                        "current_state": "下注人数阈值、奖池状态分界线和干扰指数区间都还是占位符。",
                        "evidence": "Racing需求文档.docx / 段落24",
                        "risk": "配置无法初始化，测试无法设计边界用例。",
                        "suggestion": "补齐占位符默认值和范围。",
                        "severity": "中",
                        "confidence": "高",
                        "blocking": "阻塞测试用例设计",
                    },
                    {
                        "issue_id": "CLARITY_02",
                        "title": "地形生成逻辑与隐藏地形对结算的影响未闭环",
                        "primary_dimension": DIMENSIONS[0],
                        "current_state": "只描述了隐藏地形和随机地形，但没有闭环规则。",
                        "evidence": "Racing需求文档.docx / 段落26",
                        "risk": "客户端表现与结算地形可能不一致。",
                        "suggestion": "补充地形抽取与结算关系。",
                        "severity": "中",
                        "confidence": "中",
                        "blocking": "阻塞开发",
                    },
                ],
                DIMENSIONS[1]: [
                    {
                        "issue_id": "LOGIC_01",
                        "title": "干扰指数与开奖时间公式(T)的数学映射缺失",
                        "primary_dimension": DIMENSIONS[1],
                        "current_state": "干扰指数会影响开奖，但没有说明如何作用到 T/Luck。",
                        "evidence": "Racing需求文档.docx / 段落43",
                        "risk": "干预链路无法实现。",
                        "suggestion": "补充干扰指数到 T/Luck 的映射公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                    }
                ],
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        titles = [finding["title"] for dimension in stabilized["dimensions"] for finding in dimension["findings"]]
        blocker_titles = [item["title"] for item in stabilized["top_blockers"]]

        self.assertNotIn("核心阈值与概率占位符([001]等)泛滥且无默认值/边界", titles)
        self.assertIn("地形生成逻辑与隐藏地形对结算的影响未闭环", titles)
        self.assertIn("干扰指数与开奖时间公式(T)的数学映射缺失", titles)
        self.assertIn("干扰指数与开奖时间公式(T)的数学映射缺失", blocker_titles)

    def test_duplicate_formula_symptoms_score_b_when_not_fatal(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            cross_document_issues=[
                {
                    "title": "实时赔率公式中使用占位符[001]%，且未说明展示赔率与实际赔率如何对应",
                    "primary_dimension": DIMENSIONS[1],
                    "current_state": "赔率相关配置存在占位符，且展示赔率与实际赔率边界不清。",
                    "evidence": "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落5",
                    "risk": "实现口径和验收口径可能不一致，但仍可通过补文档解决。",
                    "suggestion": "补充赔率字段定义与展示/实际赔率关系。",
                    "severity": "高",
                    "confidence": "高",
                    "blocking": "阻塞开发",
                },
                {
                    "title": "假赔率展示机制缺失，导致赔率口径无法验证",
                    "primary_dimension": DIMENSIONS[0],
                    "current_state": "需求文档没有说明假赔率何时显示。",
                    "evidence": "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落5",
                    "risk": "测试无法验证展示赔率是否符合规则，但不构成根本不可实现。",
                    "suggestion": "补充假赔率展示规则。",
                    "severity": "高",
                    "confidence": "中",
                    "blocking": "阻塞测试用例设计",
                },
            ]
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        self.assertEqual(stabilized["document_quality_score"], "B")

    def test_noncanonical_model_issue_ids_are_preserved_without_forced_canonical_merge(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "issue_id": "CLARITY-01",
                        "canonical_title": "赔率公式定义冲突",
                        "title": "赔率计算存在两套冲突公式，实际赔付规则未统一",
                        "current_state": "需求文档与数值文档定义了两套赔率公式。",
                        "evidence": "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落2-5",
                        "risk": "结算口径无法统一。",
                        "suggestion": "统一赔率公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                        "primary_dimension": DIMENSIONS[0],
                    },
                    {
                        "issue_id": "CLARITY-02",
                        "canonical_title": "假人数/假金额与真实结算未隔离",
                        "title": "下注人数/金额展示用假数据，但未说明服务端结算、榜单、奖池使用何种数据",
                        "current_state": "展示使用真实值乘系数，但未说明结算与榜单口径。",
                        "evidence": "Racing需求文档.docx / 段落22-23",
                        "risk": "可能出现展示与结算口径不一致。",
                        "suggestion": "明确真实与展示数据边界。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                        "primary_dimension": DIMENSIONS[0],
                    },
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)
        findings = stabilized["dimensions"][0]["findings"]
        cross_findings = stabilized["cross_document_issues"]
        issue_ids = [finding["issue_id"] for finding in findings]
        cross_issue_ids = [finding["issue_id"] for finding in cross_findings]
        titles = [finding["title"] for finding in findings]
        cross_titles = [finding["title"] for finding in cross_findings]

        self.assertIn("CLARITY-01", cross_issue_ids)
        self.assertIn("CLARITY-02", issue_ids)
        self.assertIn("赔率计算存在两套冲突公式，实际赔付规则未统一", cross_titles)
        self.assertIn("下注人数/金额展示用假数据，但未说明服务端结算、榜单、奖池使用何种数据", titles)

    def test_dimension_formula_conflict_with_two_document_evidence_is_promoted_to_cross_section(self) -> None:
        docs = [make_doc("Racing需求文档.docx", kind="requirement"), make_doc("Racing数值文档.docx", kind="numeric")]
        report = make_report(
            {
                DIMENSIONS[0]: [
                    {
                        "title": "赔率计算公式双轨冲突与核心变量未定义",
                        "current_state": "需求文档与数值文档给出两套赔率公式。",
                        "evidence": "Racing需求文档.docx / 段落28；Racing数值文档.docx / 段落2-5",
                        "risk": "结算口径无法统一。",
                        "suggestion": "统一唯一赔率公式。",
                        "severity": "高",
                        "confidence": "高",
                        "blocking": "阻塞开发",
                        "primary_dimension": DIMENSIONS[0],
                    }
                ],
                DIMENSIONS[1]: [
                    {
                        "title": "地形/车型出现概率与速度排序逻辑缺乏配置映射",
                        "current_state": "需求文档提到地形和车型，数值文档提供速度表。",
                        "evidence": "Racing需求文档.docx / 段落27；Racing数值文档.docx / 表格1",
                        "risk": "测试无法验证概率权重。",
                        "suggestion": "补充映射表。",
                        "severity": "中",
                        "confidence": "中",
                        "blocking": "阻塞测试用例设计",
                        "primary_dimension": DIMENSIONS[1],
                    }
                ],
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual([finding["title"] for finding in stabilized["cross_document_issues"]], ["赔率计算公式双轨冲突与核心变量未定义"])
        self.assertEqual(stabilized["cross_document_issues"][0]["evidence_scope"], "cross_document")
        self.assertEqual(stabilized["dimensions"][0]["findings"], [])
        self.assertEqual(
            [finding["title"] for finding in stabilized["dimensions"][1]["findings"]],
            ["地形/车型出现概率与速度排序逻辑缺乏配置映射"],
        )

    def test_render_markdown_uses_clean_note_for_empty_dimension(self) -> None:
        docs = [make_doc("疯狂世界杯.docx")]
        report = make_report()
        report["dimensions"][2]["dimension_note"] = "鏈彂鐜版槑鏄鹃棶棰?"

        markdown = render_markdown(normalize_report(report), docs)

        self.assertIn("### 【可测试性与验收标准】", markdown)
        self.assertIn("未发现明显问题", markdown)
        self.assertNotIn("鏈彂", markdown)


    def test_dimension_note_uses_no_high_risk_when_raw_findings_are_filtered_out(self) -> None:
        docs = [make_doc("Racing spec.docx")]
        report = make_report(
            {
                DIMENSIONS[4]: [
                    {
                        "title": "服务端权威边界待补充",
                        "current_state": "模型提到了一个通用提醒。",
                        "evidence": "稳定基线检查项",
                        "risk": "需要补充边界说明。",
                        "suggestion": "补充说明。",
                        "severity": "中",
                        "confidence": "中",
                        "blocking": "建议优化",
                    }
                ]
            }
        )

        stabilized = stabilize_report(normalize_report(report), docs)

        self.assertEqual(stabilized["dimensions"][4]["findings"], [])
        self.assertEqual(stabilized["dimensions"][4]["dimension_note"], "没有高风险问题")


if __name__ == "__main__":
    unittest.main()
