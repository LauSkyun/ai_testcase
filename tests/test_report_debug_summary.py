from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import report_debug_summary


def write_report(run_dir: Path, report: dict, documents: list[dict], log_lines: list[str]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "review_report.json").write_text(
        json.dumps({"report": report, "documents": documents}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "run.log").write_text("\n".join(log_lines), encoding="utf-8")


class ReportDebugSummaryTests(unittest.TestCase):
    def test_recovered_model_retry_is_not_counted_as_run_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "run.log"
            log_path.write_text(
                "\n".join(
                    [
                        "[2026-07-30T10:00:00] text model retry scheduled failed_attempt=1 reason='HTTP 502 failed'",
                        "[2026-07-30T10:00:02] EXIT call text model ok elapsed=2.000s",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(report_debug_summary.extract_warning_lines(log_path), [])

    def test_compare_runs_finds_common_and_drift_findings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = [
                {"name": "Racing spec.docx", "kind": "mixed"},
                {"name": "Racing numeric.docx", "kind": "numeric"},
            ]
            report_a = {
                "review_mode": "fusion",
                "primary_model": "gpt-5.4",
                "secondary_model": "deepseek-v4-pro",
                "document_quality_score": "C",
                "top_blockers": [{"title": "赔率公式冲突"}],
                "dimensions": [
                    {"name": "清晰度与完整性", "findings": [{"title": "赔率公式冲突", "severity": "高"}]},
                    {"name": "可测试性与验收标准", "findings": [{"title": "断线恢复规则缺失", "severity": "中"}]},
                ],
                "cross_document_issues": [],
            }
            report_b = {
                "review_mode": "fusion",
                "primary_model": "gpt-5.4",
                "secondary_model": "deepseek-v4-pro",
                "document_quality_score": "C",
                "top_blockers": [{"title": "赔率公式冲突"}],
                "dimensions": [
                    {"name": "清晰度与完整性", "findings": [{"title": "赔率公式冲突", "severity": "高"}]},
                    {"name": "逻辑一致性与数值平衡", "findings": [{"title": "胜负判定规则缺失", "severity": "高"}]},
                ],
                "cross_document_issues": [],
            }
            write_report(root / "run_a", report_a, docs, ["[time] parse primary model json warning=bad json"])
            write_report(root / "run_b", report_b, docs, ["[time] EXIT run ok"])

            summary_a = report_debug_summary.summarize_run(root / "run_a")
            summary_b = report_debug_summary.summarize_run(root / "run_b")
            comparison = report_debug_summary.compare_runs([summary_a, summary_b])

            self.assertTrue(comparison["same_documents"])
            self.assertEqual(comparison["common_root_causes"], ["赔率公式冲突"])
            self.assertCountEqual(comparison["drift_root_causes"], ["断线恢复规则缺失", "胜负判定规则缺失"])
            self.assertEqual(comparison["warning_run_count"], 1)
            self.assertEqual(comparison["only_in_run"]["run_a"], ["断线恢复规则缺失"])
            self.assertEqual(comparison["only_in_run"]["run_b"], ["胜负判定规则缺失"])

    def test_compare_runs_skips_drift_when_documents_differ(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = {
                "review_mode": "fast",
                "document_quality_score": "B",
                "dimensions": [],
                "cross_document_issues": [],
            }
            write_report(root / "run_a", report, [{"name": "A.docx", "kind": "mixed"}], [])
            write_report(root / "run_b", report, [{"name": "B.docx", "kind": "mixed"}], [])

            comparison = report_debug_summary.compare_runs(
                [
                    report_debug_summary.summarize_run(root / "run_a"),
                    report_debug_summary.summarize_run(root / "run_b"),
                ]
            )

            self.assertFalse(comparison["same_documents"])
            self.assertIn("输入文档不一致", comparison["note"])

    def test_dual_pass_summary_exposes_v22_protocol_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir) / "run"
            report = {
                "review_mode": "dual_pass",
                "document_quality_score": "B",
                "dimensions": [],
                "cross_document_issues": [],
            }
            write_report(run_dir, report, [{"name": "game.docx", "kind": "mixed"}], [])
            artifacts = run_dir / "model_artifacts"
            artifacts.mkdir(parents=True)
            packet_id = "a" * 64
            (artifacts / "phase2_control_evidence_packet.json").write_text(
                json.dumps({"protocol_revision": "phase2_v2_2", "evidence_packet_id": packet_id}),
                encoding="utf-8",
            )
            (artifacts / "dual_pass_summary.json").write_text(
                json.dumps(
                    {
                        "secondary_protocol_revision": "phase2_v2_2",
                        "candidate_generation_mode": "deterministic_primary_plus_admitted_delta",
                        "coverage_evidence_packet_id": packet_id,
                        "coverage_evidence_packet_echoed": True,
                        "phase2_delta_only_compliant": True,
                        "phase2_protocol_gate": {"passed": True},
                    }
                ),
                encoding="utf-8",
            )

            summary = report_debug_summary.summarize_run(run_dir)

            self.assertEqual(summary["secondary_protocol_revision"], "phase2_v2_2")
            self.assertEqual(
                summary["candidate_generation_mode"],
                "deterministic_primary_plus_admitted_delta",
            )
            self.assertEqual(summary["coverage_evidence_packet_id"], packet_id)
            self.assertTrue(summary["coverage_evidence_packet_echoed"])
            self.assertTrue(summary["phase2_delta_only_compliant"])
            self.assertTrue(summary["phase2_protocol_gate_passed"])


    def test_resolve_report_dirs_expands_multi_game_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_root = root / "20260706_154044"
            report = {
                "review_mode": "dual_pass",
                "document_quality_score": "B",
                "dimensions": [],
                "cross_document_issues": [],
            }
            docs = [{"name": "777 spec.docx", "kind": "mixed"}]
            write_report(run_root / "777", report, docs, [])
            write_report(run_root / "racing", report, docs, [])

            resolved = report_debug_summary.resolve_report_dirs("20260706_154044", root)

            self.assertEqual(
                [(path.name, run_id) for path, run_id in resolved],
                [("777", "20260706_154044/777"), ("racing", "20260706_154044/racing")],
            )
            summaries = [report_debug_summary.summarize_run(path, run_id=run_id) for path, run_id in resolved]
            self.assertEqual([item["run_id"] for item in summaries], ["20260706_154044/777", "20260706_154044/racing"])

    def test_compare_runs_groups_full_game_batches_by_document_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = {
                "review_mode": "fast",
                "document_quality_score": "B",
                "dimensions": [],
                "cross_document_issues": [],
            }
            rows = []
            for batch in ("run_a", "run_b"):
                for game in ("777", "racing"):
                    run_dir = root / batch / game
                    docs = [{"name": f"{game}.docx", "kind": "mixed"}]
                    write_report(run_dir, report, docs, [])
                    rows.append(
                        report_debug_summary.summarize_run(
                            run_dir,
                            run_id=f"{batch}/{game}",
                        )
                    )

            comparison = report_debug_summary.compare_runs(rows)

        self.assertFalse(comparison["same_documents"])
        self.assertEqual([item["group"] for item in comparison["document_groups"]], ["777", "racing"])
        self.assertTrue(all(item["comparison"]["same_documents"] for item in comparison["document_groups"]))


if __name__ == "__main__":
    unittest.main()
