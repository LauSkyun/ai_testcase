from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rad_review.docx_reader import ParsedDocument, discover_docx, parse_docx, write_manifest
from rad_review.model_client import ModelConfig, OpenAICompatibleClient
from rad_review.prompts import (
    IMAGE_PROMPT,
    PHASE2_PROTOCOL_REVISION,
    build_audit_messages,
    build_document_context,
    build_dual_pass_secondary_messages,
    build_primary_review_messages,
    build_phase2_control_evidence_packet,
    build_review_messages,
    build_shared_review_input,
)
from rad_review.reporting.ingest import parse_audit_json, parse_dual_pass_review_json, parse_model_json
from rad_review.reporting.modes import (
    build_deterministic_phase2_candidate,
    build_dual_pass_comparison_summary,
    build_report_diff_payload,
    demote_dual_pass_cross_document_issues,
    evaluate_dual_pass_candidate_selection,
    evaluate_phase2_protocol_gate,
    lock_dual_pass_candidate_score_to_primary,
    lock_dual_pass_candidate_top_blockers_to_primary,
    sanitize_dual_pass_phase2_candidate_review,
    merge_audit_report,
    merge_dual_pass_review_report,
    merge_secondary_review_report,
    normalize_dual_pass_advice_payload,
)
from rad_review.reporting.normalize import dedupe_text_list, fallback_report
from rad_review.reporting.render import (
    count_report_findings,
    write_dual_pass_advice_files,
    write_dual_pass_index_files,
    write_dual_pass_summary_files,
    write_report_diff_files,
    write_report_files,
)
from rad_review.run_logger import RunLogger


@dataclass
class RunResult:
    document_count: int
    markdown_path: Path
    json_path: Path
    manifest_path: Path | None = None
    log_path: Path | None = None
    warning: str = ""


class ReviewAgent:
    def __init__(
        self,
        input_path: Path,
        output_dir: Path,
        document_paths: list[Path] | None = None,
        run_name: str | None = None,
        timeout: int = 600,
        max_context_chars: int = 120000,
        analyze_images: bool = True,
        image_limit: int = 100,
        log_echo: bool | None = None,
        require_model: bool = False,
        review_mode: str = "fast",
        update_latest: bool = True,
        image_cache_dir: Path | None = None,
        model_retries: int = 3,
    ) -> None:
        self.input_path = input_path
        self.output_dir = output_dir
        self.document_paths = document_paths
        self.run_name = run_name
        self.timeout = timeout
        self.max_context_chars = max_context_chars
        self.analyze_images = analyze_images
        self.image_limit = image_limit
        self.log_echo = log_echo
        self.require_model = require_model
        self.review_mode = review_mode
        self.update_latest = update_latest
        self.image_cache_dir = image_cache_dir or (output_dir / ".cache" / "image_analysis")
        self.model_retries = max(0, int(model_retries))
        if review_mode in {"fusion", "dual_pass"}:
            self.config = ModelConfig.from_prefixed_env("AI_PRIMARY")
            self.secondary_config = ModelConfig.from_prefixed_env("AI_SECONDARY")
        else:
            self.config = ModelConfig.from_env()
            self.secondary_config = None
        self.client = OpenAICompatibleClient(self.config, timeout=timeout)
        self.secondary_client = (
            OpenAICompatibleClient(self.secondary_config, timeout=timeout) if self.secondary_config is not None else None
        )
        self.logger: RunLogger | None = None
        self.current_log_path: Path | None = None

    def run(self, extract_only: bool = False) -> RunResult:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = self.output_dir / (self.run_name or timestamp)
        paths = self._build_run_paths(run_dir)
        self.current_log_path = paths["log_path"]
        logger = RunLogger(paths["log_path"], echo=self.log_echo)
        self.logger = logger
        self.client.set_event_logger(logger.info)
        if self.secondary_client is not None:
            self.secondary_client.set_event_logger(logger.info)

        try:
            with logger.step(
                "run",
                input=self.input_path,
                output=run_dir,
                extract_only=extract_only,
                skip_images=not self.analyze_images,
                timeout_seconds=self.timeout,
                max_context_chars=self.max_context_chars,
                review_mode=self.review_mode,
                model_retries=self.model_retries,
            ):
                self._log_model_config_status()
                docs = self._parse_documents(paths["assets_dir"])
                self._write_extraction_artifacts(docs, paths["manifest_path"], paths["context_path"])

                warning = ""
                if extract_only:
                    report = fallback_report("extract-only 模式，仅完成文档解析，未执行 AI 评审。")
                    with logger.step("write extract-only report", markdown=paths["markdown_path"], json=paths["json_path"]):
                        write_report_files(report, docs, paths["markdown_path"], paths["json_path"])
                    self._write_latest(run_dir)
                    return RunResult(
                        len(docs),
                        paths["markdown_path"],
                        paths["json_path"],
                        paths["manifest_path"],
                        paths["log_path"],
                    )

                if self.analyze_images:
                    self._analyze_images(docs)
                else:
                    self._mark_images_skipped_by_cli(docs)
                self._write_extraction_artifacts(docs, paths["manifest_path"], paths["context_path"])
                self._write_run_metadata(docs, paths["metadata_path"])

                primary_prefix = "AI_PRIMARY" if self.secondary_config is not None else None
                missing_primary = self._missing_text_fields(self.config, prefix=primary_prefix)
                if missing_primary:
                    warning = (
                        "缺少文本评审模型配置："
                        + "、".join(missing_primary)
                        + "。已生成图片/文档解析结果和占位报告。"
                    )
                    if self.require_model:
                        raise RuntimeError(warning)
                    report = fallback_report(warning)
                    report["image_analysis_gaps"] = self._image_gaps(docs)
                    with logger.step("write fallback report", warning=warning):
                        write_report_files(report, docs, paths["markdown_path"], paths["json_path"])
                    self._write_latest(run_dir)
                    return RunResult(
                        len(docs),
                        paths["markdown_path"],
                        paths["json_path"],
                        paths["manifest_path"],
                        paths["log_path"],
                        warning,
                    )

                if self.review_mode == "dual_pass":
                    return self._run_dual_pass(docs, paths, warning)

                report, warning = self._run_standard_review_flow(docs, paths, warning)
                image_gaps = self._image_gaps(docs)
                if image_gaps:
                    report["image_analysis_gaps"] = dedupe_text_list(
                        list(report.get("image_analysis_gaps") or []) + image_gaps
                    )

                if self.review_mode == "strict":
                    report, warning = self._run_strict_audit(docs, paths, report, warning)
                elif self.review_mode == "benchmark":
                    report.setdefault("quality_notes", [])
                    report["quality_notes"].append(
                        "benchmark 模式：本次保留确定性调试工件，用于多次复跑对比；报告仍采用一次主分析结果。"
                    )

                with logger.step("write review report", markdown=paths["markdown_path"], json=paths["json_path"]):
                    write_report_files(report, docs, paths["markdown_path"], paths["json_path"])
                self._write_latest(run_dir)
                return RunResult(
                    len(docs),
                    paths["markdown_path"],
                    paths["json_path"],
                    paths["manifest_path"],
                    paths["log_path"],
                    warning,
                )
        finally:
            self.client.set_event_logger(None)
            if self.secondary_client is not None:
                self.secondary_client.set_event_logger(None)
            self.logger = None

    def _build_run_paths(self, run_dir: Path) -> dict[str, Path]:
        artifacts_dir = run_dir / "model_artifacts"
        return {
            "run_dir": run_dir,
            "assets_dir": run_dir / "assets",
            "manifest_path": run_dir / "extraction_manifest.json",
            "context_path": run_dir / "extraction_context.md",
            "markdown_path": run_dir / "review_report.md",
            "json_path": run_dir / "review_report.json",
            "pre_audit_markdown_path": run_dir / "review_report_pre_audit.md",
            "pre_audit_json_path": run_dir / "review_report_pre_audit.json",
            "diff_markdown_path": run_dir / "review_report_diff.md",
            "diff_json_path": run_dir / "review_report_diff.json",
            "pipeline_markdown_path": run_dir / "review_report_pipeline.md",
            "pipeline_json_path": run_dir / "review_report_pipeline.json",
            "candidate_markdown_path": run_dir / "review_report_candidate.md",
            "candidate_json_path": run_dir / "review_report_candidate.json",
            "index_markdown_path": run_dir / "review_report_index.md",
            "index_json_path": run_dir / "review_report_index.json",
            "advice_markdown_path": run_dir / "secondary_review_advice.md",
            "advice_json_path": run_dir / "secondary_review_advice.json",
            "metadata_path": artifacts_dir / "run_metadata.json",
            "review_messages_path": artifacts_dir / "review_messages.json",
            "raw_response_path": artifacts_dir / "raw_model_response.txt",
            "audit_messages_path": artifacts_dir / "audit_messages.json",
            "raw_audit_response_path": artifacts_dir / "raw_audit_response.txt",
            "shared_review_input_path": artifacts_dir / "shared_review_input.json",
            "primary_review_messages_path": artifacts_dir / "primary_review_messages.json",
            "primary_raw_response_path": artifacts_dir / "primary_raw_model_response.txt",
            "secondary_review_messages_path": artifacts_dir / "secondary_review_messages.json",
            "secondary_raw_response_path": artifacts_dir / "secondary_raw_model_response.txt",
            "fusion_summary_path": artifacts_dir / "fusion_merge_summary.json",
            "dual_pass_summary_path": artifacts_dir / "dual_pass_summary.json",
            "phase2_evidence_packet_path": artifacts_dir / "phase2_control_evidence_packet.json",
            "log_path": run_dir / "run.log",
        }

    def _run_standard_review_flow(
        self,
        docs: list[ParsedDocument],
        paths: dict[str, Path],
        warning: str,
    ) -> tuple[dict[str, Any], str]:
        messages = self._build_review_messages(docs)
        self._write_json_artifact(paths["review_messages_path"], messages)

        if self.review_mode == "fusion":
            missing_secondary = self._missing_text_fields(self.secondary_config, prefix="AI_SECONDARY")
            if missing_secondary:
                raise RuntimeError(
                    "缺少副评审模型配置："
                    + "、".join(missing_secondary)
                    + "。fusion 模式需要同时配置主模型和副模型。"
                )

            self._write_json_artifact(paths["primary_review_messages_path"], messages)
            self._write_json_artifact(paths["secondary_review_messages_path"], messages)

            primary_raw = self._call_text_model(messages, stage="primary")
            self._write_raw_response_artifact(
                paths["raw_response_path"],
                primary_raw,
                model=self.config.text_model,
                wire_api=self.config.wire_api,
                stage="primary",
            )
            self._write_raw_response_artifact(
                paths["primary_raw_response_path"],
                primary_raw,
                model=self.config.text_model,
                wire_api=self.config.wire_api,
                stage="primary",
            )
            with self._require_logger().step("parse primary model json", response_chars=len(primary_raw)):
                primary_report, primary_parse_error = parse_model_json(primary_raw, docs)
            if primary_parse_error:
                warning = append_warning(warning, f"主评审模型返回 JSON 解析失败，已保留原始响应：{primary_parse_error}")
                self._require_logger().info("primary model json parse warning", warning=warning)

            secondary_report: dict[str, Any] | None = None
            try:
                secondary_raw = self._call_text_model(
                    messages,
                    client=self.secondary_client,
                    config=self.secondary_config,
                    stage="secondary",
                )
                self._write_raw_response_artifact(
                    paths["secondary_raw_response_path"],
                    secondary_raw,
                    model=self.secondary_config.text_model if self.secondary_config else "",
                    wire_api=self.secondary_config.wire_api if self.secondary_config else "",
                    stage="secondary",
                )
                with self._require_logger().step("parse secondary model json", response_chars=len(secondary_raw)):
                    secondary_report, secondary_parse_error = parse_model_json(secondary_raw, docs)
                if secondary_parse_error:
                    warning = append_warning(
                        warning,
                        f"副评审模型返回 JSON 解析失败，本次退回主评审结果：{secondary_parse_error}",
                    )
                    self._require_logger().info("secondary model json parse warning", warning=warning)
                    secondary_report = None
            except Exception as exc:
                warning = append_warning(warning, f"副评审模型调用失败，本次退回主评审结果：{exc}")
                self._require_logger().info("secondary model call warning", warning=warning)
                secondary_report = None

            if secondary_report is None:
                report = primary_report
                fusion_summary = {
                    "status": "primary_only",
                    "primary_model": self.config.text_model,
                    "secondary_model": self.secondary_config.text_model if self.secondary_config else "",
                    "reason": "secondary_review_unavailable",
                    "warning": warning,
                }
                report["review_mode"] = "fusion"
                report["primary_model"] = self.config.text_model
                report["secondary_model"] = self.secondary_config.text_model if self.secondary_config else ""
                report["fusion_summary"] = fusion_summary
                report.setdefault("quality_notes", [])
                report["quality_notes"].append("fusion 模式本次仅保留主评审结果，因为副评审结果不可用或不可解析。")
            else:
                with self._require_logger().step("merge secondary review into primary report"):
                    report, fusion_summary = merge_secondary_review_report(
                        primary_report,
                        secondary_report,
                        docs,
                        primary_model=self.config.text_model,
                        secondary_model=self.secondary_config.text_model if self.secondary_config else "",
                    )
            self._write_json_artifact(paths["fusion_summary_path"], fusion_summary)
            return report, warning

        raw = self._call_text_model(messages, stage="review")
        self._write_raw_response_artifact(
            paths["raw_response_path"],
            raw,
            model=self.config.text_model,
            wire_api=self.config.wire_api,
            stage="review",
        )
        self._require_logger().info("ready to parse model json", response_chars=len(raw))
        with self._require_logger().step("parse model json", response_chars=len(raw)):
            report, parse_error = parse_model_json(raw, docs)
        if parse_error:
            warning = f"模型返回 JSON 解析失败，已保留原始响应：{parse_error}"
            self._require_logger().info("model json parse warning", warning=warning)
        return report, warning

    def _run_dual_pass(
        self,
        docs: list[ParsedDocument],
        paths: dict[str, Path],
        warning: str,
    ) -> RunResult:
        missing_secondary = self._missing_text_fields(self.secondary_config, prefix="AI_SECONDARY")
        if missing_secondary:
            raise RuntimeError(
                "缺少副评审模型配置："
                + "、".join(missing_secondary)
                + "。dual_pass 模式需要同时配置主模型和副模型。"
            )

        shared_input = self._build_shared_review_input(docs)
        self._write_json_artifact(paths["shared_review_input_path"], shared_input)
        primary_messages = self._build_primary_review_messages(shared_input)
        self._write_json_artifact(paths["primary_review_messages_path"], primary_messages)

        primary_raw = self._call_text_model(primary_messages, stage="primary")
        self._write_raw_response_artifact(
            paths["raw_response_path"],
            primary_raw,
            model=self.config.text_model,
            wire_api=self.config.wire_api,
            stage="primary",
        )
        self._write_raw_response_artifact(
            paths["primary_raw_response_path"],
            primary_raw,
            model=self.config.text_model,
            wire_api=self.config.wire_api,
            stage="primary",
        )
        with self._require_logger().step("parse primary model json", response_chars=len(primary_raw)):
            primary_report, primary_parse_error = parse_model_json(primary_raw, docs)
        if primary_parse_error:
            warning = append_warning(warning, f"主评审模型返回 JSON 解析失败，已保留原始响应：{primary_parse_error}")
            self._require_logger().info("primary model json parse warning", warning=warning)

        image_gaps = self._image_gaps(docs)
        if image_gaps:
            primary_report["image_analysis_gaps"] = dedupe_text_list(
                list(primary_report.get("image_analysis_gaps") or []) + image_gaps
            )
        primary_report["review_mode"] = "dual_pass"
        primary_report["primary_model"] = self.config.text_model
        primary_report["secondary_model"] = self.secondary_config.text_model if self.secondary_config else ""
        primary_report = demote_dual_pass_cross_document_issues(primary_report)

        phase2_evidence_packet = build_phase2_control_evidence_packet(
            shared_input,
            primary_report,
            protocol_revision=PHASE2_PROTOCOL_REVISION,
        )
        self._write_json_artifact(paths["phase2_evidence_packet_path"], phase2_evidence_packet)
        phase2_protocol_gate: dict[str, Any] = {
            "required": True,
            "protocol_revision": PHASE2_PROTOCOL_REVISION,
            "evidence_packet_id": str(phase2_evidence_packet.get("evidence_packet_id") or ""),
            "echo_required": True,
            "echo_matched": False,
            "delta_only_required": True,
            "delta_only_compliant": False,
            "forbidden_fields_present": [],
            "passed": False,
            "errors": ["secondary_review_unavailable"],
        }

        pipeline_report = primary_report
        candidate_report: dict[str, Any] | None = None
        advice_payload: dict[str, Any] | None = None
        comparison_summary: dict[str, Any] = {}
        selection_result: dict[str, Any] = {
            "selected_report_owner": "pipeline",
            "candidate_recommendation_status": "candidate_unavailable",
            "candidate_gate_results": {},
            "candidate_gate_failure_reasons": ["candidate_report_unavailable"],
            "candidate_gate_failure_categories": {"protocol_blockers": ["candidate_report_unavailable"]},
        }
        lineage_counts = {"kept": 0, "added": 0, "merged": 0, "dropped": 0}
        trace_warning = ""
        dual_pass_summary: dict[str, Any] = {
            "status": "primary_only",
            "secondary_protocol_profile": "phase2",
            "secondary_protocol_revision": PHASE2_PROTOCOL_REVISION,
            "candidate_generation_mode": "unavailable",
            "coverage_evidence_packet_id": phase2_protocol_gate["evidence_packet_id"],
            "coverage_evidence_packet_echoed": False,
            "phase2_protocol_gate": phase2_protocol_gate,
            "primary_model": self.config.text_model,
            "secondary_model": self.secondary_config.text_model if self.secondary_config else "",
            "cross_document_section_disabled": True,
            "traceability_status": "unavailable",
            "readiness_conflict": False,
            "candidate_structure_drift": False,
            "suggestion_level_conflict": False,
            "suggestion_level_override_applied": False,
            "candidate_block_reasons": ["candidate_report_unavailable"],
            "lineage_counts": lineage_counts,
            "comparison_summary": {},
        }
        status = "primary_only"

        try:
            secondary_messages = self._build_dual_pass_secondary_messages(docs, shared_input, primary_report)
            self._write_json_artifact(paths["secondary_review_messages_path"], secondary_messages)
            secondary_raw = self._call_text_model(
                secondary_messages,
                client=self.secondary_client,
                config=self.secondary_config,
                stage="secondary",
            )
            self._write_raw_response_artifact(
                paths["secondary_raw_response_path"],
                secondary_raw,
                model=self.secondary_config.text_model if self.secondary_config else "",
                wire_api=self.secondary_config.wire_api if self.secondary_config else "",
                stage="secondary",
            )
            with self._require_logger().step("parse dual pass secondary json", response_chars=len(secondary_raw)):
                secondary_review, secondary_error = parse_dual_pass_review_json(secondary_raw)
            if secondary_error:
                warning = append_warning(warning, f"副评审组合 JSON 解析失败，本次仅保留 pipeline 版：{secondary_error}")
                self._require_logger().info("dual pass secondary json parse warning", warning=warning)
            else:
                status = "secondary_reviewed"
                phase2_protocol_gate = evaluate_phase2_protocol_gate(
                    secondary_review,
                    PHASE2_PROTOCOL_REVISION,
                    str(phase2_evidence_packet.get("evidence_packet_id") or ""),
                )
                with self._require_logger().step("merge dual pass review into pipeline report"):
                    pipeline_report, pipeline_merge_summary = merge_dual_pass_review_report(
                        primary_report,
                        secondary_review,
                        docs,
                        secondary_model=self.secondary_config.text_model if self.secondary_config else "",
                        shared_input=shared_input,
                        enforce_phase2_admission=True,
                        phase2_protocol_gate=phase2_protocol_gate,
                    )
                pipeline_report["review_mode"] = "dual_pass"
                pipeline_report["primary_model"] = self.config.text_model
                pipeline_report["secondary_model"] = self.secondary_config.text_model if self.secondary_config else ""
                pipeline_report = demote_dual_pass_cross_document_issues(pipeline_report)
                if image_gaps:
                    pipeline_report["image_analysis_gaps"] = dedupe_text_list(
                        list(pipeline_report.get("image_analysis_gaps") or []) + image_gaps
                    )

                phase2_admission = pipeline_merge_summary.get("phase2_admission") or {}
                candidate_secondary_review = sanitize_dual_pass_phase2_candidate_review(
                    primary_report,
                    secondary_review,
                    phase2_admission,
                    shared_input,
                )
                phase2_admission["candidate_inputs_sanitized"] = True
                candidate_report, candidate_secondary_review = build_deterministic_phase2_candidate(
                    primary_report,
                    pipeline_report,
                    candidate_secondary_review,
                )
                if image_gaps:
                    candidate_report["image_analysis_gaps"] = dedupe_text_list(
                        list(candidate_report.get("image_analysis_gaps") or []) + image_gaps
                    )
                candidate_report["review_mode"] = "dual_pass_candidate"
                candidate_report["primary_model"] = self.config.text_model
                candidate_report["secondary_model"] = self.secondary_config.text_model if self.secondary_config else ""
                candidate_report = demote_dual_pass_cross_document_issues(candidate_report)
                candidate_report = lock_dual_pass_candidate_score_to_primary(primary_report, candidate_report)
                candidate_report = lock_dual_pass_candidate_top_blockers_to_primary(
                    primary_report, candidate_report
                )
                write_report_files(
                    candidate_report,
                    docs,
                    paths["candidate_markdown_path"],
                    paths["candidate_json_path"],
                )
                comparison_summary = build_dual_pass_comparison_summary(pipeline_report, candidate_report)
                status = "complete"

                advice_payload = normalize_dual_pass_advice_payload(
                    primary_report, candidate_report, candidate_secondary_review
                )
                advice_payload["candidate_generation_mode"] = str(
                    candidate_secondary_review.get("candidate_generation_mode") or "model_authored"
                )
                advice_payload["phase2_admission"] = phase2_admission
                lineage_counts = advice_payload.get("lineage_counts_raw") or advice_payload.get("lineage_counts") or lineage_counts
                trace_warning = str(advice_payload.get("trace_warning") or "")

                selection_result = evaluate_dual_pass_candidate_selection(
                    primary_report,
                    candidate_report,
                    advice_payload,
                    lineage_counts,
                    warning,
                    phase2_admission=phase2_admission,
                )
                advice_payload["candidate_block_reasons"] = selection_result.get("candidate_gate_failure_reasons") or []
                advice_payload["candidate_gate_results"] = selection_result.get("candidate_gate_results") or {}
                advice_payload["candidate_block_reason_categories"] = (
                    selection_result.get("candidate_gate_failure_categories") or {}
                )
                advice_payload["candidate_blocked_only_by_editorial_judgment"] = bool(
                    selection_result.get("candidate_blocked_only_by_editorial_judgment")
                )
                advice_payload["suggestion_level_conflict"] = bool(
                    selection_result.get("suggestion_level_conflict")
                )
                advice_payload["suggestion_level_override_applied"] = bool(
                    selection_result.get("suggestion_level_override_applied")
                )
                advice_payload["candidate_high_signal_demotion_without_support"] = bool(
                    selection_result.get("candidate_high_signal_demotion_without_support")
                )
                advice_payload["candidate_high_signal_demotion_issue_ids"] = (
                    advice_payload.get("candidate_high_signal_demotion_issue_ids")
                    or selection_result.get("candidate_high_signal_demotion_issue_ids")
                    or []
                )
                advice_payload["candidate_high_signal_demotion_titles"] = (
                    advice_payload.get("candidate_high_signal_demotion_titles")
                    or selection_result.get("candidate_high_signal_demotion_titles")
                    or []
                )
                advice_payload["candidate_overcompressed"] = bool(
                    selection_result.get("candidate_overcompressed")
                )
                advice_payload["candidate_overcompressed_reason"] = str(
                    advice_payload.get("candidate_overcompressed_reason")
                    or selection_result.get("candidate_overcompressed_reason")
                    or ""
                )
                advice_payload["primary_issue_id_repair_count"] = int(
                    advice_payload.get("primary_issue_id_repair_count")
                    or selection_result.get("primary_issue_id_repair_count")
                    or 0
                )
                advice_payload["candidate_issue_id_repair_count"] = int(
                    advice_payload.get("candidate_issue_id_repair_count")
                    or selection_result.get("candidate_issue_id_repair_count")
                    or 0
                )
                advice_payload["lineage_auto_healed"] = bool(
                    advice_payload.get("lineage_auto_healed") or selection_result.get("lineage_auto_healed")
                )
                advice_payload["lineage_auto_mapped_primary_issue_ids"] = (
                    advice_payload.get("lineage_auto_mapped_primary_issue_ids")
                    or selection_result.get("lineage_auto_mapped_primary_issue_ids")
                    or []
                )
                advice_payload["lineage_auto_mapped_candidate_issue_ids"] = (
                    advice_payload.get("lineage_auto_mapped_candidate_issue_ids")
                    or selection_result.get("lineage_auto_mapped_candidate_issue_ids")
                    or []
                )
                write_dual_pass_advice_files(advice_payload, paths["advice_markdown_path"], paths["advice_json_path"])

                dual_pass_summary = {
                    "status": status,
                    "secondary_protocol_profile": "phase2",
                    "secondary_protocol_revision": PHASE2_PROTOCOL_REVISION,
                    "coverage_evidence_packet_id": phase2_protocol_gate.get("evidence_packet_id") or "",
                    "coverage_evidence_packet_echoed": bool(phase2_protocol_gate.get("echo_matched")),
                    "phase2_delta_only_compliant": bool(phase2_protocol_gate.get("delta_only_compliant")),
                    "phase2_protocol_gate": phase2_protocol_gate,
                    "candidate_generation_mode": advice_payload.get("candidate_generation_mode")
                    or "model_authored",
                    "primary_model": self.config.text_model,
                    "secondary_model": self.secondary_config.text_model if self.secondary_config else "",
                    "cross_document_section_disabled": True,
                    "pipeline_merge_summary": pipeline_merge_summary,
                    "phase2_admission": phase2_admission,
                    "selected_report_owner": selection_result.get("selected_report_owner") or "pipeline",
                    "candidate_recommendation_status": selection_result.get("candidate_recommendation_status") or "candidate_unavailable",
                    "candidate_gate_results": selection_result.get("candidate_gate_results") or {},
                    "candidate_gate_failure_reasons": selection_result.get("candidate_gate_failure_reasons") or [],
                    "candidate_gate_failure_categories": selection_result.get("candidate_gate_failure_categories") or {},
                    "candidate_ready_for_direct_output": bool(
                        advice_payload.get("normalized_candidate_ready_for_direct_output")
                    ),
                    "candidate_ready_reason": str(advice_payload.get("normalized_candidate_ready_reason") or ""),
                    "lineage_counts": lineage_counts,
                    "lineage_counts_raw": advice_payload.get("lineage_counts_raw") or lineage_counts,
                    "lineage_counts_materialized": advice_payload.get("lineage_counts_materialized") or {},
                    "traceability_status": str(advice_payload.get("traceability_status") or "unavailable"),
                    "readiness_conflict": bool(advice_payload.get("readiness_conflict")),
                    "candidate_structure_drift": bool(advice_payload.get("candidate_structure_drift")),
                    "suggestion_level_conflict": bool(selection_result.get("suggestion_level_conflict")),
                    "suggestion_level_override_applied": bool(
                        selection_result.get("suggestion_level_override_applied")
                    ),
                    "raw_structure_change": bool(advice_payload.get("raw_structure_change")),
                    "structure_change_explained_by_lineage": bool(
                        advice_payload.get("structure_change_explained_by_lineage")
                    ),
                    "lineage_coverage_complete": bool(advice_payload.get("lineage_coverage_complete")),
                    "unmapped_primary_issue_ids": advice_payload.get("unmapped_primary_issue_ids") or [],
                    "unmapped_candidate_issue_ids": advice_payload.get("unmapped_candidate_issue_ids") or [],
                    "untitled_finding_issue_ids": advice_payload.get("untitled_finding_issue_ids") or [],
                    "missing_issue_id_finding_titles": advice_payload.get("missing_issue_id_finding_titles") or [],
                    "candidate_added_materialization_status": str(
                        advice_payload.get("candidate_added_materialization_status") or "none"
                    ),
                    "candidate_added_materialization_missing_ids": advice_payload.get(
                        "candidate_added_materialization_missing_ids"
                    )
                    or [],
                    "candidate_merged_materialization_status": str(
                        advice_payload.get("candidate_merged_materialization_status") or "none"
                    ),
                    "candidate_merged_materialization_missing_ids": advice_payload.get(
                        "candidate_merged_materialization_missing_ids"
                    )
                    or [],
                    "candidate_issue_id_split_detected": bool(
                        selection_result.get("candidate_issue_id_split_detected")
                        or advice_payload.get("candidate_issue_id_split_detected")
                    ),
                    "candidate_issue_id_split_issue_ids": advice_payload.get("candidate_issue_id_split_issue_ids") or [],
                    "candidate_negated_primary_finding_still_materialized": bool(
                        selection_result.get("candidate_negated_primary_finding_still_materialized")
                        or advice_payload.get("candidate_negated_primary_finding_still_materialized")
                    ),
                    "candidate_negated_primary_issue_ids": advice_payload.get("candidate_negated_primary_issue_ids") or [],
                    "candidate_negated_primary_titles": advice_payload.get("candidate_negated_primary_titles") or [],
                    "candidate_blocker_conclusion_mismatch": bool(
                        selection_result.get("candidate_blocker_conclusion_mismatch")
                        or advice_payload.get("candidate_blocker_conclusion_mismatch")
                    ),
                    "candidate_blocker_conclusion_mismatch_titles": advice_payload.get(
                        "candidate_blocker_conclusion_mismatch_titles"
                    )
                    or [],
                    "candidate_high_signal_demotion_without_support": bool(
                        selection_result.get("candidate_high_signal_demotion_without_support")
                        or advice_payload.get("candidate_high_signal_demotion_without_support")
                    ),
                    "candidate_high_signal_demotion_issue_ids": advice_payload.get(
                        "candidate_high_signal_demotion_issue_ids"
                    )
                    or [],
                    "candidate_high_signal_demotion_titles": advice_payload.get(
                        "candidate_high_signal_demotion_titles"
                    )
                    or [],
                    "candidate_overcompressed": bool(
                        selection_result.get("candidate_overcompressed")
                        or advice_payload.get("candidate_overcompressed")
                    ),
                    "candidate_overcompressed_reason": str(
                        advice_payload.get("candidate_overcompressed_reason")
                        or selection_result.get("candidate_overcompressed_reason")
                        or ""
                    ),
                    "candidate_major_judgment_drift": bool(
                        selection_result.get("candidate_major_judgment_drift")
                        or advice_payload.get("candidate_major_judgment_drift")
                    ),
                    "candidate_structurally_ready": bool(advice_payload.get("candidate_structurally_ready")),
                    "candidate_blocked_only_by_editorial_judgment": bool(
                        selection_result.get("candidate_blocked_only_by_editorial_judgment")
                    ),
                    "primary_issue_id_repair_count": int(advice_payload.get("primary_issue_id_repair_count") or 0),
                    "candidate_issue_id_repair_count": int(advice_payload.get("candidate_issue_id_repair_count") or 0),
                    "lineage_auto_healed": bool(advice_payload.get("lineage_auto_healed")),
                    "lineage_auto_mapped_primary_issue_ids": advice_payload.get(
                        "lineage_auto_mapped_primary_issue_ids"
                    )
                    or [],
                    "lineage_auto_mapped_candidate_issue_ids": advice_payload.get(
                        "lineage_auto_mapped_candidate_issue_ids"
                    )
                    or [],
                    "candidate_contains_multiroot_kept_findings": bool(
                        advice_payload.get("candidate_contains_multiroot_kept_findings")
                    ),
                    "candidate_multiroot_kept_titles": advice_payload.get("candidate_multiroot_kept_titles") or [],
                    "advice_candidate_structure_mismatch": bool(
                        advice_payload.get("advice_candidate_structure_mismatch")
                    ),
                    "advice_claimed_absorbed_but_materialized_separately": advice_payload.get(
                        "advice_claimed_absorbed_but_materialized_separately"
                    )
                    or [],
                    "advice_claimed_added_but_not_materialized": advice_payload.get(
                        "advice_claimed_added_but_not_materialized"
                    )
                    or [],
                    "materialized_missed_without_added": advice_payload.get("materialized_missed_without_added") or [],
                    "candidate_block_reasons": selection_result.get("candidate_gate_failure_reasons") or [],
                    "candidate_block_reason_categories": selection_result.get("candidate_gate_failure_categories") or {},
                    "trace_warning": trace_warning,
                    "comparison_summary": comparison_summary,
                }
        except Exception as exc:
            warning = append_warning(warning, f"副评审调用失败，本次仅保留 pipeline 版：{exc}")
            self._require_logger().info("dual pass secondary warning", warning=warning)

        write_report_files(pipeline_report, docs, paths["pipeline_markdown_path"], paths["pipeline_json_path"])
        final_report = candidate_report if selection_result.get("selected_report_owner") == "candidate" and candidate_report else pipeline_report
        write_report_files(final_report, docs, paths["markdown_path"], paths["json_path"])
        self._write_json_artifact(paths["dual_pass_summary_path"], dual_pass_summary)

        readiness = (advice_payload or {}).get("candidate_readiness") or {}
        summary_payload = {
            "mode": "dual_pass",
            "status": status,
            "secondary_protocol_profile": "phase2",
            "secondary_protocol_revision": PHASE2_PROTOCOL_REVISION,
            "candidate_generation_mode": (advice_payload or {}).get("candidate_generation_mode")
            or ("unavailable" if candidate_report is None else "model_authored"),
            "coverage_evidence_packet_id": phase2_protocol_gate.get("evidence_packet_id") or "",
            "coverage_evidence_packet_echoed": bool(phase2_protocol_gate.get("echo_matched")),
            "phase2_delta_only_compliant": bool(phase2_protocol_gate.get("delta_only_compliant")),
            "phase2_protocol_gate": phase2_protocol_gate,
            "primary_model": self.config.text_model,
            "secondary_model": self.secondary_config.text_model if self.secondary_config else "",
            "selected_report_owner": selection_result.get("selected_report_owner") or "pipeline",
            "selected_report_path": paths["markdown_path"].name,
            "selected_source_report_path": (
                paths["candidate_markdown_path"].name
                if selection_result.get("selected_report_owner") == "candidate" and candidate_report
                else paths["pipeline_markdown_path"].name
            ),
            "candidate_recommendation_status": selection_result.get("candidate_recommendation_status") or "candidate_unavailable",
            "candidate_gate_results": selection_result.get("candidate_gate_results") or {},
            "candidate_gate_failure_reasons": selection_result.get("candidate_gate_failure_reasons") or [],
            "candidate_gate_failure_categories": selection_result.get("candidate_gate_failure_categories") or {},
            "phase2_admission": (advice_payload or {}).get("phase2_admission") or {},
            "primary_top3_retention": selection_result.get("primary_top3_retention"),
            "primary_top3_retention_gate_passed": bool(
                selection_result.get("primary_top3_retention_gate_passed")
            ),
            "candidate_score_locked_to_primary": bool(
                selection_result.get("candidate_score_locked_to_primary")
            ),
            "pipeline_report_path": paths["pipeline_markdown_path"].name,
            "candidate_report_path": paths["candidate_markdown_path"].name if candidate_report else "",
            "advice_path": paths["advice_markdown_path"].name if advice_payload else "",
            "primary_score": str(primary_report.get("document_quality_score") or ""),
            "pipeline_score": str(pipeline_report.get("document_quality_score") or ""),
            "candidate_score": str(candidate_report.get("document_quality_score") or "") if candidate_report else "",
            "selected_score": str(final_report.get("document_quality_score") or ""),
            "pipeline_finding_count": count_report_findings(pipeline_report),
            "candidate_finding_count": count_report_findings(candidate_report or {}),
            "selected_finding_count": count_report_findings(final_report),
            "candidate_ready_for_direct_output": bool((advice_payload or {}).get("normalized_candidate_ready_for_direct_output")),
            "candidate_ready_reason": str((advice_payload or {}).get("normalized_candidate_ready_reason") or ""),
            "lineage_counts": lineage_counts,
            "lineage_counts_raw": (advice_payload or {}).get("lineage_counts_raw") or lineage_counts,
            "lineage_counts_materialized": (advice_payload or {}).get("lineage_counts_materialized") or {},
            "traceability_status": str((advice_payload or {}).get("traceability_status") or "unavailable"),
            "readiness_conflict": bool((advice_payload or {}).get("readiness_conflict")),
            "candidate_structure_drift": bool((advice_payload or {}).get("candidate_structure_drift")),
            "suggestion_level_conflict": bool(selection_result.get("suggestion_level_conflict")),
            "suggestion_level_override_applied": bool(selection_result.get("suggestion_level_override_applied")),
            "raw_structure_change": bool((advice_payload or {}).get("raw_structure_change")),
            "structure_change_explained_by_lineage": bool(
                (advice_payload or {}).get("structure_change_explained_by_lineage")
            ),
            "lineage_coverage_complete": bool((advice_payload or {}).get("lineage_coverage_complete")),
            "unmapped_primary_issue_ids": (advice_payload or {}).get("unmapped_primary_issue_ids") or [],
            "unmapped_candidate_issue_ids": (advice_payload or {}).get("unmapped_candidate_issue_ids") or [],
            "untitled_finding_issue_ids": (advice_payload or {}).get("untitled_finding_issue_ids") or [],
            "missing_issue_id_finding_titles": (advice_payload or {}).get("missing_issue_id_finding_titles") or [],
            "candidate_added_materialization_status": str(
                (advice_payload or {}).get("candidate_added_materialization_status") or "none"
            ),
            "candidate_added_materialization_missing_ids": (advice_payload or {}).get(
                "candidate_added_materialization_missing_ids"
            )
            or [],
            "candidate_merged_materialization_status": str(
                (advice_payload or {}).get("candidate_merged_materialization_status") or "none"
            ),
            "candidate_merged_materialization_missing_ids": (advice_payload or {}).get(
                "candidate_merged_materialization_missing_ids"
            )
            or [],
            "candidate_issue_id_split_detected": bool(
                selection_result.get("candidate_issue_id_split_detected")
                or (advice_payload or {}).get("candidate_issue_id_split_detected")
            ),
            "candidate_issue_id_split_issue_ids": (advice_payload or {}).get("candidate_issue_id_split_issue_ids") or [],
            "candidate_negated_primary_finding_still_materialized": bool(
                selection_result.get("candidate_negated_primary_finding_still_materialized")
                or (advice_payload or {}).get("candidate_negated_primary_finding_still_materialized")
            ),
            "candidate_negated_primary_issue_ids": (advice_payload or {}).get("candidate_negated_primary_issue_ids")
            or [],
            "candidate_negated_primary_titles": (advice_payload or {}).get("candidate_negated_primary_titles") or [],
            "candidate_blocker_conclusion_mismatch": bool(
                selection_result.get("candidate_blocker_conclusion_mismatch")
                or (advice_payload or {}).get("candidate_blocker_conclusion_mismatch")
            ),
            "candidate_blocker_conclusion_mismatch_titles": (
                (advice_payload or {}).get("candidate_blocker_conclusion_mismatch_titles") or []
            ),
            "candidate_high_signal_demotion_without_support": bool(
                selection_result.get("candidate_high_signal_demotion_without_support")
                or (advice_payload or {}).get("candidate_high_signal_demotion_without_support")
            ),
            "candidate_high_signal_demotion_issue_ids": (
                (advice_payload or {}).get("candidate_high_signal_demotion_issue_ids") or []
            ),
            "candidate_high_signal_demotion_titles": (
                (advice_payload or {}).get("candidate_high_signal_demotion_titles") or []
            ),
            "candidate_overcompressed": bool(
                selection_result.get("candidate_overcompressed")
                or (advice_payload or {}).get("candidate_overcompressed")
            ),
            "candidate_overcompressed_reason": str(
                (advice_payload or {}).get("candidate_overcompressed_reason")
                or selection_result.get("candidate_overcompressed_reason")
                or ""
            ),
            "candidate_major_judgment_drift": bool(
                selection_result.get("candidate_major_judgment_drift")
                or (advice_payload or {}).get("candidate_major_judgment_drift")
            ),
            "candidate_structurally_ready": bool((advice_payload or {}).get("candidate_structurally_ready")),
            "candidate_blocked_only_by_editorial_judgment": bool(
                selection_result.get("candidate_blocked_only_by_editorial_judgment")
            ),
            "primary_issue_id_repair_count": int((advice_payload or {}).get("primary_issue_id_repair_count") or 0),
            "candidate_issue_id_repair_count": int((advice_payload or {}).get("candidate_issue_id_repair_count") or 0),
            "lineage_auto_healed": bool((advice_payload or {}).get("lineage_auto_healed")),
            "lineage_auto_mapped_primary_issue_ids": (
                (advice_payload or {}).get("lineage_auto_mapped_primary_issue_ids") or []
            ),
            "lineage_auto_mapped_candidate_issue_ids": (
                (advice_payload or {}).get("lineage_auto_mapped_candidate_issue_ids") or []
            ),
            "candidate_contains_multiroot_kept_findings": bool(
                (advice_payload or {}).get("candidate_contains_multiroot_kept_findings")
            ),
            "candidate_multiroot_kept_titles": (advice_payload or {}).get("candidate_multiroot_kept_titles") or [],
            "advice_candidate_structure_mismatch": bool(
                (advice_payload or {}).get("advice_candidate_structure_mismatch")
            ),
            "advice_claimed_absorbed_but_materialized_separately": (
                (advice_payload or {}).get("advice_claimed_absorbed_but_materialized_separately") or []
            ),
            "advice_claimed_added_but_not_materialized": (
                (advice_payload or {}).get("advice_claimed_added_but_not_materialized") or []
            ),
            "materialized_missed_without_added": (advice_payload or {}).get("materialized_missed_without_added") or [],
            "candidate_block_reasons": selection_result.get("candidate_gate_failure_reasons") or [],
            "candidate_block_reason_categories": selection_result.get("candidate_gate_failure_categories") or {},
            "trace_warning": trace_warning,
            "cross_document_section_disabled": True,
            "comparison_summary": comparison_summary,
            "warning": warning,
        }
        write_dual_pass_index_files(summary_payload, paths["index_markdown_path"], paths["index_json_path"])
        self._write_latest(paths["run_dir"])
        return RunResult(
            len(docs),
            paths["markdown_path"],
            paths["json_path"],
            paths["manifest_path"],
            paths["log_path"],
            warning,
        )

    def _run_strict_audit(
        self,
        docs: list[ParsedDocument],
        paths: dict[str, Path],
        report: dict[str, Any],
        warning: str,
    ) -> tuple[dict[str, Any], str]:
        pre_audit_report = json.loads(json.dumps(report, ensure_ascii=False))
        with self._require_logger().step(
            "write pre-audit review report",
            markdown=paths["pre_audit_markdown_path"],
            json=paths["pre_audit_json_path"],
        ):
            write_report_files(report, docs, paths["pre_audit_markdown_path"], paths["pre_audit_json_path"])

        audit_messages = self._build_audit_messages(docs, report)
        self._write_json_artifact(paths["audit_messages_path"], audit_messages)
        audit_raw = self._call_text_model(audit_messages, stage="audit")
        self._write_raw_response_artifact(
            paths["raw_audit_response_path"],
            audit_raw,
            model=self.config.text_model,
            wire_api=self.config.wire_api,
            stage="audit",
        )
        with self._require_logger().step("parse audit json", response_chars=len(audit_raw)):
            audit, audit_error = parse_audit_json(audit_raw)
        if audit_error:
            warning = append_warning(warning, f"strict 校验 JSON 解析失败：{audit_error}")
            self._require_logger().info("audit json parse warning", warning=warning)
        else:
            with self._require_logger().step("merge audit report"):
                report = merge_audit_report(report, audit, docs)
        report.setdefault("quality_notes", [])
        report["quality_notes"].append(
            "strict 模式已额外保留校验前版本：review_report_pre_audit.md / review_report_pre_audit.json，可直接对比校验前后差异。"
        )
        diff_payload = build_report_diff_payload(pre_audit_report, report)
        with self._require_logger().step(
            "write strict diff summary",
            markdown=paths["diff_markdown_path"],
            json=paths["diff_json_path"],
        ):
            write_report_diff_files(diff_payload, paths["diff_markdown_path"], paths["diff_json_path"])
        return report, warning

    def _parse_documents(self, assets_dir: Path) -> list[ParsedDocument]:
        logger = self._require_logger()
        with logger.step("discover docx", input=self.input_path):
            doc_paths = self.document_paths if self.document_paths is not None else discover_docx(self.input_path)
        logger.info("docx files discovered", count=len(doc_paths), files=", ".join(str(path) for path in doc_paths))
        docs: list[ParsedDocument] = []
        for path in doc_paths:
            with logger.step("parse docx", file=path):
                doc = parse_docx(path, assets_dir)
            logger.info(
                "docx parsed",
                file=path,
                kind=doc.kind,
                paragraphs=len(doc.paragraphs),
                tables=len(doc.tables),
                images=len(doc.images),
            )
            docs.append(doc)
        return docs

    def _analyze_images(self, docs: list[ParsedDocument]) -> None:
        logger = self._require_logger()
        if not self.config.has_vision_model:
            with logger.step("mark images skipped no vision model", image_count=sum(len(doc.images) for doc in docs)):
                for doc in docs:
                    for image in doc.images:
                        image.status = "skipped_no_vision_model"
                        image.error = "缺少 AI_VISION_MODEL 或视觉模型配置。"
            return

        analyzed = 0
        cache_dir = self.image_cache_dir
        with logger.step(
            "analyze images",
            image_limit=self.image_limit,
            vision_model=self.config.vision_model,
            vision_wire_api=self.config.vision_wire_api,
            vision_base_url=self.config.vision_base_url_or_default,
        ):
            for doc in docs:
                for image in doc.images:
                    if analyzed >= self.image_limit:
                        image.status = "skipped_image_limit"
                        image.error = f"超过 image-limit={self.image_limit}，未发送视觉模型。"
                        logger.info("image skipped by limit", doc=doc.name, image=image.index)
                        continue
                    try:
                        with logger.step("analyze image", doc=doc.name, image=image.index, file=image.extracted_path):
                            image_path = Path(image.extracted_path)
                            cache_path = self._image_cache_path(cache_dir, image_path)
                            if cache_path.exists():
                                image.analysis = cache_path.read_text(encoding="utf-8")
                                logger.info("image analysis cache hit", doc=doc.name, image=image.index, cache=cache_path)
                            else:
                                image.analysis = self.client.analyze_image(image_path, IMAGE_PROMPT)
                                cache_path.parent.mkdir(parents=True, exist_ok=True)
                                cache_path.write_text(image.analysis, encoding="utf-8")
                        image.status = "analyzed"
                        analyzed += 1
                    except Exception as exc:
                        image.status = "failed"
                        image.error = str(exc)
                        logger.info("image analysis failed", doc=doc.name, image=image.index, error=exc)

    def _mark_images_skipped_by_cli(self, docs: list[ParsedDocument]) -> None:
        logger = self._require_logger()
        with logger.step("mark images skipped by cli", image_count=sum(len(doc.images) for doc in docs)):
            for doc in docs:
                for image in doc.images:
                    image.status = "skipped_by_cli"
                    image.error = "命令行参数 --skip-images 已跳过视觉模型解析。"

    def _image_gaps(self, docs: list[ParsedDocument]) -> list[str]:
        gaps: list[str] = []
        for doc in docs:
            for image in doc.images:
                if image.status != "analyzed":
                    gaps.append(f"{doc.name} / 图片{image.index}：{image.status}。{image.error}".strip())
        return gaps

    def _write_latest(self, run_dir: Path) -> None:
        if not self.update_latest:
            return
        logger = self._require_logger()
        with logger.step("write latest report", source=run_dir):
            latest = self.output_dir / "latest"
            if latest.exists():
                shutil.rmtree(latest)
            shutil.copytree(run_dir, latest)

    def _write_extraction_artifacts(self, docs: list[ParsedDocument], manifest_path: Path, context_path: Path) -> None:
        logger = self._require_logger()
        with logger.step("write extraction manifest", path=manifest_path):
            write_manifest(docs, manifest_path)
        with logger.step("build document context", document_count=len(docs)):
            context = build_document_context(docs)
        with logger.step("write extraction context", path=context_path, chars=len(context)):
            context_path.write_text(context, encoding="utf-8")

    def _build_review_messages(self, docs: list[ParsedDocument]) -> list[dict[str, Any]]:
        logger = self._require_logger()
        with logger.step("build review messages", document_count=len(docs), max_context_chars=self.max_context_chars):
            messages = build_review_messages(docs, self.max_context_chars)
        logger.info(
            "review messages built",
            message_count=len(messages),
            total_chars=sum(len(str(message.get("content", ""))) for message in messages),
        )
        return messages

    def _build_audit_messages(self, docs: list[ParsedDocument], report: dict[str, Any]) -> list[dict[str, Any]]:
        logger = self._require_logger()
        with logger.step("build audit messages", document_count=len(docs), max_context_chars=self.max_context_chars):
            messages = build_audit_messages(docs, report, self.max_context_chars)
        logger.info(
            "audit messages built",
            message_count=len(messages),
            total_chars=sum(len(str(message.get("content", ""))) for message in messages),
        )
        return messages

    def _build_shared_review_input(self, docs: list[ParsedDocument]) -> dict[str, Any]:
        logger = self._require_logger()
        with logger.step("build shared review input", document_count=len(docs), max_context_chars=self.max_context_chars):
            payload = build_shared_review_input(docs, self.max_context_chars)
        logger.info(
            "shared review input built",
            document_count=len(docs),
            context_chars=len(str(payload.get("document_context") or "")),
        )
        return payload

    def _build_primary_review_messages(self, shared_input: dict[str, Any]) -> list[dict[str, Any]]:
        logger = self._require_logger()
        with logger.step("build primary review messages", max_context_chars=self.max_context_chars):
            messages = build_primary_review_messages(shared_input)
        logger.info(
            "primary review messages built",
            message_count=len(messages),
            total_chars=sum(len(str(message.get("content", ""))) for message in messages),
        )
        return messages

    def _build_dual_pass_secondary_messages(
        self,
        docs: list[ParsedDocument],
        shared_input: dict[str, Any],
        primary_report: dict[str, Any],
    ) -> list[dict[str, Any]]:
        logger = self._require_logger()
        with logger.step("build dual pass secondary messages", document_count=len(docs), max_context_chars=self.max_context_chars):
            messages = build_dual_pass_secondary_messages(shared_input, primary_report)
        logger.info(
            "dual pass secondary messages built",
            message_count=len(messages),
            total_chars=sum(len(str(message.get("content", ""))) for message in messages),
        )
        return messages

    def _call_text_model(
        self,
        messages: list[dict[str, Any]],
        client: OpenAICompatibleClient | None = None,
        config: ModelConfig | None = None,
        stage: str = "primary",
    ) -> str:
        logger = self._require_logger()
        selected_client = client or self.client
        selected_config = config or self.config
        with logger.step(
            "call text model",
            stage=stage,
            model=selected_config.text_model,
            wire_api=selected_config.wire_api,
            temperature=0,
            max_attempts=self.model_retries + 1,
        ):
            max_attempts = self.model_retries + 1
            for attempt in range(1, max_attempts + 1):
                logger.info(
                    "text model request attempt",
                    stage=stage,
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                try:
                    return selected_client.chat(messages, model=selected_config.text_model, temperature=0)
                except Exception as exc:
                    retryable = self._is_retryable_model_error(exc)
                    if not retryable or attempt >= max_attempts:
                        raise RuntimeError(
                            f"{stage} text model failed after {attempt} attempt(s): {exc}"
                        ) from exc
                    delay_seconds = min(2 ** attempt, 30)
                    logger.info(
                        "text model retry scheduled",
                        stage=stage,
                        failed_attempt=attempt,
                        next_attempt=attempt + 1,
                        max_attempts=max_attempts,
                        delay_seconds=delay_seconds,
                        reason=str(exc),
                    )
                    time.sleep(delay_seconds)
        raise RuntimeError("Text model retry loop exited unexpectedly.")

    @staticmethod
    def _is_retryable_model_error(exc: Exception) -> bool:
        message = str(exc or "").strip().lower()
        http_match = re.search(r"\bhttp\s+(\d{3})\b", message)
        if http_match:
            status_code = int(http_match.group(1))
            return status_code >= 500 or status_code in {408, 409, 425, 429}
        retryable_markers = (
            "timed out",
            "timeout",
            "urlopen error",
            "connection reset",
            "connection aborted",
            "connection refused",
            "remote end closed connection",
            "temporarily unavailable",
            "temporary failure",
            "upstream_error",
            "upstream request failed",
            "no text output",
            "did not contain text",
            "unexpected chat-completions response shape",
            "unexpected chat-completions message content",
            "unexpected responses api response shape",
            "unexpected anthropic messages response shape",
        )
        return any(marker in message for marker in retryable_markers)

    def _write_run_metadata(self, docs: list[ParsedDocument], metadata_path: Path) -> None:
        payload = {
            "review_mode": self.review_mode,
            "document_hash": self._document_hash(docs),
            "text_model": self.config.text_model,
            "vision_model": self.config.vision_model,
            "wire_api": self.config.wire_api,
            "vision_wire_api": self.config.vision_wire_api,
            "temperature": 0,
            "seed": self.config.seed,
            "document_count": len(docs),
            "model_retries": self.model_retries,
        }
        if self.secondary_config is not None:
            payload["primary_text_model"] = self.config.text_model
            payload["secondary_text_model"] = self.secondary_config.text_model
            payload["primary_wire_api"] = self.config.wire_api
            payload["secondary_wire_api"] = self.secondary_config.wire_api
            payload["primary_seed"] = self.config.seed
            payload["secondary_seed"] = self.secondary_config.seed
            if self.review_mode == "dual_pass":
                payload["secondary_protocol_profile"] = "phase2"
                payload["secondary_protocol_revision"] = PHASE2_PROTOCOL_REVISION
        self._write_json_artifact(metadata_path, payload)

    def _write_json_artifact(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_text_artifact(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_raw_response_artifact(self, path: Path, text: str, model: str, wire_api: str, stage: str) -> None:
        header = "\n".join(
            [
                f"model: {model or '<unknown>'}",
                f"wire_api: {wire_api or '<unknown>'}",
                f"stage: {stage or '<unknown>'}",
                "",
            ]
        )
        self._write_text_artifact(path, header + text)

    def _document_hash(self, docs: list[ParsedDocument]) -> str:
        payload = []
        for doc in docs:
            payload.append(
                {
                    "name": doc.name,
                    "kind": doc.kind,
                    "paragraphs": [paragraph.__dict__ for paragraph in doc.paragraphs],
                    "tables": [table.__dict__ for table in doc.tables],
                    "images": [
                        {
                            "index": image.index,
                            "source_name": image.source_name,
                            "status": image.status,
                            "analysis": image.analysis,
                            "error": image.error,
                        }
                        for image in doc.images
                    ],
                    "errors": doc.errors,
                }
            )
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _image_cache_path(self, cache_dir: Path, image_path: Path) -> Path:
        prompt_hash = hashlib.sha256(IMAGE_PROMPT.encode("utf-8")).hexdigest()[:12]
        image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
        model_name = (self.config.vision_model or "vision").replace("/", "_").replace("\\", "_")
        return cache_dir / f"{model_name}_{prompt_hash}_{image_hash}.txt"

    def _require_logger(self) -> RunLogger:
        if self.logger is None:
            raise RuntimeError("Run logger is not initialized.")
        return self.logger

    def _missing_text_fields(self, config: ModelConfig | None, prefix: str | None = None) -> list[str]:
        if config is None:
            return []
        if prefix is None:
            return config.missing_text_fields()
        missing: list[str] = []
        if not config.base_url:
            missing.append(f"{prefix}_BASE_URL")
        if not config.api_key:
            missing.append(f"{prefix}_API_KEY")
        if not config.text_model:
            missing.append(f"{prefix}_MODEL")
        return missing

    def _log_model_config_status(self) -> None:
        logger = self._require_logger()
        primary_prefix = "AI_PRIMARY" if self.secondary_config is not None else None
        logger.info(
            "primary model config status",
            text_model_configured=self.config.has_text_model,
            missing_text=",".join(self._missing_text_fields(self.config, prefix=primary_prefix)) or "none",
            vision_model_configured=self.config.has_vision_model,
            missing_vision=",".join(self.config.missing_vision_fields()) or "none",
            text_model=self.config.text_model or "<empty>",
            text_base_url=self.config.base_url or "<empty>",
            vision_model=self.config.vision_model or "<empty>",
            vision_base_url=self.config.vision_base_url_or_default or "<empty>",
            seed=self.config.seed if self.config.seed is not None else "<unset>",
        )
        if self.secondary_config is not None:
            logger.info(
                "secondary model config status",
                text_model_configured=self.secondary_config.has_text_model,
                missing_text=",".join(self._missing_text_fields(self.secondary_config, prefix="AI_SECONDARY")) or "none",
                text_model=self.secondary_config.text_model or "<empty>",
                text_base_url=self.secondary_config.base_url or "<empty>",
                seed=self.secondary_config.seed if self.secondary_config.seed is not None else "<unset>",
            )


def append_warning(existing: str, extra: str) -> str:
    if not existing:
        return extra
    return f"{existing}；{extra}"
