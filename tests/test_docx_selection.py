from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import review
from rad_review.docx_reader import discover_docx_for_game, group_docx_by_game, infer_game_key


class DocxSelectionTests(unittest.TestCase):
    def test_infer_game_key_from_requirement_and_numeric_names(self) -> None:
        self.assertEqual(infer_game_key(Path("小鸡数值文档.docx")), "小鸡")
        self.assertEqual(infer_game_key(Path("musee游戏Racing.docx")), "racing")
        self.assertEqual(infer_game_key(Path("Racing数值文档.docx")), "racing")
        self.assertEqual(infer_game_key(Path("疯狂世界杯.docx")), "疯狂世界杯")

    def test_infer_game_key_prefers_project_folder_when_under_group_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            racing_doc = root / "Racing" / "musee游戏Racing.docx"
            racing_doc.parent.mkdir(parents=True)
            racing_doc.touch()

            self.assertEqual(infer_game_key(racing_doc, root), "Racing")

    def test_discover_docx_for_game_matches_only_requested_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["小鸡.docx", "小鸡数值文档.docx", "musee游戏Racing.docx", "Racing数值文档.docx", "疯狂世界杯.docx"]:
                (root / name).touch()

            chicken = discover_docx_for_game(root, "小鸡")
            racing = discover_docx_for_game(root, "Racing")

        self.assertEqual([path.name for path in chicken], ["小鸡.docx", "小鸡数值文档.docx"])
        self.assertEqual([path.name for path in racing], ["musee游戏Racing.docx", "Racing数值文档.docx"])

    def test_discover_docx_for_game_matches_project_folder_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chicken_dir = root / "小鸡"
            racing_dir = root / "Racing"
            chicken_dir.mkdir()
            racing_dir.mkdir()
            for path in [
                chicken_dir / "小鸡需求.docx",
                chicken_dir / "小鸡数值文档.docx",
                racing_dir / "musee游戏Racing.docx",
                racing_dir / "Racing数值文档.docx",
            ]:
                path.touch()

            chicken = discover_docx_for_game(root, "小鸡")
            racing = discover_docx_for_game(root, "Racing")

        self.assertEqual([path.name for path in chicken], ["小鸡需求.docx", "小鸡数值文档.docx"])
        self.assertEqual([path.name for path in racing], ["musee游戏Racing.docx", "Racing数值文档.docx"])

    def test_group_docx_by_game_splits_current_requirement_style(self) -> None:
        paths = [
            Path("小鸡.docx"),
            Path("小鸡数值文档.docx"),
            Path("musee游戏Racing.docx"),
            Path("Racing数值文档.docx"),
            Path("疯狂世界杯.docx"),
        ]

        groups = group_docx_by_game(paths)

        self.assertEqual(sorted(groups), ["racing", "小鸡", "疯狂世界杯"])
        self.assertEqual([path.name for path in groups["小鸡"]], ["小鸡.docx", "小鸡数值文档.docx"])
        self.assertEqual([path.name for path in groups["racing"]], ["musee游戏Racing.docx", "Racing数值文档.docx"])

    def test_group_docx_by_game_prefers_first_level_project_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [
                root / "小鸡" / "小鸡需求.docx",
                root / "小鸡" / "小鸡数值文档.docx",
                root / "Racing" / "musee游戏Racing.docx",
                root / "Racing" / "Racing数值文档.docx",
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()

            groups = group_docx_by_game(paths, root)

        self.assertEqual(sorted(groups), ["Racing", "小鸡"])
        self.assertEqual([path.name for path in groups["小鸡"]], ["小鸡需求.docx", "小鸡数值文档.docx"])
        self.assertEqual([path.name for path in groups["Racing"]], ["musee游戏Racing.docx", "Racing数值文档.docx"])

    def test_auto_group_reuses_report_root_image_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "requirements"
            output_dir = root / "reports"
            input_dir.mkdir()
            docs = [input_dir / "777" / "需求.docx", input_dir / "racing" / "需求.docx"]
            for path in docs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            options = review.RunOptions(
                timeout=30,
                model_retries=3,
                max_context_chars=1000,
                analyze_images=True,
                image_limit=10,
                log_echo=False,
                require_model=False,
                review_mode="dual_pass",
            )
            calls = []

            def fake_run_single(*args, **kwargs):
                calls.append(kwargs)
                return type(
                    "Result",
                    (),
                    {
                        "warning": "",
                        "log_path": output_dir / "run.log",
                        "json_path": output_dir / "review_report.json",
                    },
                )()

            with (
                patch.object(review, "discover_docx", return_value=docs),
                patch.object(
                    review,
                    "group_docx_by_game",
                    return_value={"777": [docs[0]], "racing": [docs[1]]},
                ),
                patch.object(review, "run_single", side_effect=fake_run_single),
                patch.object(review, "print_result"),
                patch.object(review, "write_group_latest"),
            ):
                exit_code = review.run_auto_group(input_dir, output_dir, False, options)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 2)
        expected_cache = output_dir / ".cache" / "image_analysis"
        self.assertTrue(all(item["image_cache_dir"] == expected_cache for item in calls))

    def test_auto_group_records_failed_game_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "requirements"
            output_dir = root / "reports"
            input_dir.mkdir()
            docs = [input_dir / "777" / "需求.docx", input_dir / "racing" / "需求.docx"]
            for path in docs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            options = review.RunOptions(
                timeout=30,
                model_retries=3,
                max_context_chars=1000,
                analyze_images=False,
                image_limit=10,
                log_echo=False,
                require_model=True,
                review_mode="dual_pass",
            )
            successful_result = type(
                "Result",
                (),
                {
                    "warning": "",
                    "log_path": output_dir / "racing" / "run.log",
                    "json_path": output_dir / "racing" / "review_report.json",
                },
            )()

            with (
                patch.object(review, "discover_docx", return_value=docs),
                patch.object(
                    review,
                    "group_docx_by_game",
                    return_value={"777": [docs[0]], "racing": [docs[1]]},
                ),
                patch.object(
                    review,
                    "run_single",
                    side_effect=[RuntimeError("Model API HTTP 502: upstream request failed"), successful_result],
                ) as mock_run_single,
                patch.object(review, "print_result"),
                patch.object(review, "write_group_latest"),
            ):
                exit_code = review.run_auto_group(input_dir, output_dir, False, options)

            run_dirs = [path for path in output_dir.iterdir() if path.is_dir()]
            self.assertEqual(exit_code, 1)
            self.assertEqual(mock_run_single.call_count, 2)
            self.assertEqual(len(run_dirs), 1)
            summary = json.loads((run_dirs[0] / "group_run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["model_retries"], 3)
            self.assertEqual([item["status"] for item in summary["groups"]], ["failed", "completed"])
            self.assertIn("HTTP 502", summary["groups"][0]["error"])

    def test_auto_group_secondary_warning_records_fallback_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "requirements"
            output_dir = root / "reports"
            input_dir.mkdir()
            docs = [input_dir / "777" / "需求.docx", input_dir / "racing" / "需求.docx"]
            for path in docs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            options = review.RunOptions(
                timeout=30,
                model_retries=3,
                max_context_chars=1000,
                analyze_images=False,
                image_limit=10,
                log_echo=False,
                require_model=True,
                review_mode="dual_pass",
            )
            fallback_result = type(
                "Result",
                (),
                {
                    "warning": "副评审调用失败，本次仅保留 pipeline 版：HTTP 502",
                    "log_path": output_dir / "777" / "run.log",
                    "json_path": output_dir / "777" / "review_report.json",
                },
            )()
            successful_result = type(
                "Result",
                (),
                {
                    "warning": "",
                    "log_path": output_dir / "racing" / "run.log",
                    "json_path": output_dir / "racing" / "review_report.json",
                },
            )()

            with (
                patch.object(review, "discover_docx", return_value=docs),
                patch.object(review, "group_docx_by_game", return_value={"777": [docs[0]], "racing": [docs[1]]}),
                patch.object(review, "run_single", side_effect=[fallback_result, successful_result]) as mock_run_single,
                patch.object(review, "print_result"),
                patch.object(review, "write_group_latest"),
            ):
                exit_code = review.run_auto_group(input_dir, output_dir, False, options)

            run_dirs = [path for path in output_dir.iterdir() if path.is_dir()]
            summary = json.loads((run_dirs[0] / "group_run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 2)
            self.assertEqual(mock_run_single.call_count, 2)
            self.assertEqual([item["status"] for item in summary["groups"]], ["warning", "completed"])
            self.assertIn("仅保留 pipeline", summary["groups"][0]["error"])


if __name__ == "__main__":
    unittest.main()
