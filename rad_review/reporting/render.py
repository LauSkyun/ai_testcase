from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rad_review.docx_reader import ParsedDocument, build_collection_summary

from .base import NO_FINDINGS_NOTE
from .schema import assert_report_integrity, iter_public_findings


def render_finding(finding: dict[str, Any]) -> list[str]:
    severity = finding.get("severity", "未标注")
    title = finding.get("title", "未命名问题")
    confidence = finding.get("confidence", "未标注")
    blocking = finding.get("blocking", "未标注")
    planner_role = finding.get("planner_role") or finding.get("owner") or "待定"
    lines = [
        f"- **[严重程度：{severity}] {title}**",
        f"  - 现状描述：{finding.get('current_state', '未提供')}",
        f"  - 证据来源：{finding.get('evidence', '未提供')}",
        f"  - 风险分析：{finding.get('risk', '未提供')}",
        f"  - 修改建议：{finding.get('suggestion', '未提供')}",
        f"  - 关注角色：{planner_role}",
        f"  - 置信度：{confidence}",
        f"  - 阻塞级别：{blocking}",
    ]
    source_label = str(finding.get("finding_source_label") or "").strip()
    source_model = str(finding.get("source_model") or "").strip()
    if source_label or source_model:
        source_text = source_label or "副评审补充"
        if source_model:
            source_text = f"{source_text} ({source_model})"
        lines.append(f"  - 问题来源：{source_text}")
    return lines


def sanitize_dimension_note(note: Any) -> str:
    text = str(note or "").strip()
    if not text:
        return NO_FINDINGS_NOTE
    if any("\ue000" <= char <= "\uf8ff" for char in text):
        return NO_FINDINGS_NOTE
    mojibake_markers = (
        "闂佸搫",
        "闁哄牜",
        "鑴欏",
        "鑼呰",
        "蹇欒",
    )
    if any(marker in text for marker in mojibake_markers):
        return NO_FINDINGS_NOTE
    return text


def sanitize_report_dimension_notes(report: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(report)
    dimensions: list[dict[str, Any]] = []
    for raw_dimension in report.get("dimensions") or []:
        if not isinstance(raw_dimension, dict):
            continue
        dimension = dict(raw_dimension)
        findings = list(dimension.get("findings") or [])
        dimension["findings"] = findings
        dimension["dimension_note"] = "" if findings else sanitize_dimension_note(dimension.get("dimension_note"))
        dimensions.append(dimension)
    sanitized["dimensions"] = dimensions
    return sanitized


def strip_internal_report_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_internal_report_fields(current)
            for key, current in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [strip_internal_report_fields(item) for item in value]
    return value


def _render_block_categories_inline(categories: dict[str, Any] | None) -> str:
    current = categories if isinstance(categories, dict) else {}
    parts: list[str] = []
    for key, values in current.items():
        items = [str(item).strip() for item in (values or []) if str(item).strip()]
        if items:
            parts.append(f"{key}={','.join(items)}")
    return "; ".join(parts)


def _append_phase2_coverage_ledger_lines(lines: list[str], phase2_admission: dict[str, Any]) -> None:
    ledger = phase2_admission.get("coverage_ledger")
    if not isinstance(ledger, dict):
        return
    completeness = ledger.get("completeness")
    completeness_text = f"{float(completeness):.0%}" if isinstance(completeness, (int, float)) else "-"
    lines.append(
        f"- coverage ledger：{'通过' if ledger.get('passed') is True else '未通过'}，完整率 {completeness_text}"
    )
    confirmed_keys = [str(value) for value in ledger.get("confirmed_audit_keys") or [] if str(value).strip()]
    if confirmed_keys:
        lines.append(f"- coverage confirmed_add：{', '.join(confirmed_keys)}")
    confirmed_controls = [
        str(value) for value in ledger.get("confirmed_control_keys") or [] if str(value).strip()
    ]
    if confirmed_controls:
        lines.append(f"- coverage confirmed controls：{', '.join(confirmed_controls)}")
    repairs = [str(value) for value in ledger.get("protocol_repairs") or [] if str(value).strip()]
    if repairs:
        lines.append(f"- coverage 安全归一化：{', '.join(repairs)}")
    errors = [str(value) for value in ledger.get("errors") or [] if str(value).strip()]
    if errors:
        lines.append(f"- coverage ledger 错误：{', '.join(errors)}")


def render_report_diff_markdown(diff: dict[str, Any]) -> str:
    lines: list[str] = []
    counts = diff.get("counts") or {}
    lines.append("# Strict 校验前后差异摘要")
    lines.append("")
    lines.append("## 评分变化")
    lines.append(f"- 校验前：{diff.get('score_before') or '未评级'}")
    lines.append(f"- 校验后：{diff.get('score_after') or '未评级'}")
    if diff.get("score_reason_before"):
        lines.append(f"- 校验前评分原因：{diff.get('score_reason_before')}")
    if diff.get("score_reason_after"):
        lines.append(f"- 校验后评分原因：{diff.get('score_reason_after')}")
    lines.append("")
    lines.append("## 问题数量变化")
    lines.append(f"- 校验前问题数：{counts.get('before', 0)}")
    lines.append(f"- 校验后问题数：{counts.get('after', 0)}")
    lines.append(f"- 新增问题：{counts.get('added', 0)}")
    lines.append(f"- 移除问题：{counts.get('removed', 0)}")
    lines.append(f"- 内容有调整的问题：{counts.get('changed', 0)}")
    lines.append("")
    lines.append("## Top Blockers 变化")
    before_blockers = diff.get("top_blockers_before") or []
    after_blockers = diff.get("top_blockers_after") or []
    lines.append(f"- 校验前：{'；'.join(before_blockers) if before_blockers else '无'}")
    lines.append(f"- 校验后：{'；'.join(after_blockers) if after_blockers else '无'}")
    lines.append("")
    lines.append("## 新增问题")
    added_findings = diff.get("added_findings") or []
    if added_findings:
        for finding in added_findings:
            lines.append(
                f"- [{finding.get('severity', '未标注')}] {finding.get('title', '未命名问题')}：{finding.get('risk', '未提供风险说明')}"
            )
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 移除问题")
    removed_findings = diff.get("removed_findings") or []
    if removed_findings:
        for finding in removed_findings:
            lines.append(f"- [{finding.get('severity', '未标注')}] {finding.get('title', '未命名问题')}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 调整问题")
    changed_findings = diff.get("changed_findings") or []
    if changed_findings:
        for item in changed_findings:
            before_finding = item.get("before") or {}
            after_finding = item.get("after") or {}
            lines.append(
                f"- {after_finding.get('title', before_finding.get('title', '未命名问题'))}：严重度 {before_finding.get('severity', '未标注')} -> {after_finding.get('severity', '未标注')}，阻塞级别 {before_finding.get('blocking', '未标注')} -> {after_finding.get('blocking', '未标注')}"
            )
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 新增备注")
    added_notes = diff.get("added_quality_notes") or []
    if added_notes:
        for note in added_notes:
            lines.append(f"- {note}")
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_markdown(report: dict[str, Any], documents: list[ParsedDocument]) -> str:
    summary = build_collection_summary(documents)
    lines: list[str] = []
    lines.append("# 需求文档分析报告")
    lines.append("")
    lines.append("## 一、总体评价")
    lines.append(report.get("overall_evaluation") or "未提供总体评价。")
    if report.get("document_quality_score"):
        lines.append("")
        lines.append(f"- **文档质量评分：** {report.get('document_quality_score')}")
    if report.get("score_reason"):
        lines.append(f"- **评分原因：** {report.get('score_reason')}")
    blockers = report.get("top_blockers") or []
    if blockers:
        lines.append("")
        lines.append("## 优先处理事项")
        for blocker in blockers:
            lines.append(f"- **[{blocker.get('severity', '未标注')}] {blocker.get('title', '未命名问题')}**")
            lines.append(f"  - 责任建议：{blocker.get('owner', '待定')}")
            lines.append(f"  - 处理原因：{blocker.get('why_now', '未提供')}")
            source_label = str(blocker.get("finding_source_label") or "").strip()
            source_model = str(blocker.get("source_model") or "").strip()
            if source_label or source_model:
                source_text = source_label or "副评审补充"
                if source_model:
                    source_text = f"{source_text} ({source_model})"
                lines.append(f"  - 问题来源：{source_text}")
    lines.append("")
    lines.append("## 文档输入概况")
    lines.append(f"- 文档数量：{summary['document_count']}")
    lines.append(
        f"- 需求文档：{summary['kinds'].get('requirement', 0)}，数值文档：{summary['kinds'].get('numeric', 0)}，混合文档：{summary['kinds'].get('mixed', 0)}，未知类型：{summary['kinds'].get('unknown', 0)}"
    )
    lines.append(f"- 正文段落：{summary['total_paragraphs']}，表格：{summary['total_tables']}，图片：{summary['total_images']}")
    if summary["missing_companion_docs"]:
        lines.append(f"- 缺失配套材料：{'；'.join(summary['missing_companion_docs'])}")
    lines.append("")
    lines.append("## 二、逐维度问题清单")
    for dimension in report.get("dimensions", []):
        lines.append(f"### 【{dimension.get('name', '未知维度')}】")
        findings = dimension.get("findings") or []
        if not findings:
            lines.append(sanitize_dimension_note(dimension.get("dimension_note")))
            lines.append("")
            continue
        for finding in findings:
            lines.extend(render_finding(finding))
        lines.append("")
    lines.append("## 跨文档一致性问题")
    cross_issues = report.get("cross_document_issues") or []
    if cross_issues:
        for finding in cross_issues:
            lines.extend(render_finding(finding))
    else:
        lines.append("未发现明确跨文档一致性问题，或当前输入不足以形成跨文档结论。")
    lines.append("")
    lines.append("## 三、核心测试点建议")
    for category, items in (report.get("test_points") or {}).items():
        lines.append(f"### {category}")
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("- 暂无")
    lines.append("")
    lines.append("## 四、待补充信息")
    missing_information = report.get("missing_information") or []
    if missing_information:
        for item in missing_information:
            lines.append(f"- {item}")
    else:
        lines.append("未发现明显待补充信息。")
    quality_notes = report.get("quality_notes") or []
    if quality_notes:
        lines.append("")
        lines.append("## 五、质量备注")
        for note in quality_notes:
            lines.append(f"- {note}")
    atomicity_queue = report.get("finding_atomicity_review_queue") or []
    if atomicity_queue:
        lines.append("")
        lines.append("## 原子化待人工拆分队列（不计入正式 Finding）")
        lines.append("")
        lines.append("以下原始问题同时包含多个独立决策对象，系统无法在不猜测的前提下安全拆分，因此未进入默认 Finding：")
        for item in atomicity_queue:
            if not isinstance(item, dict):
                continue
            source = item.get("source_finding") if isinstance(item.get("source_finding"), dict) else {}
            title = source.get("title") or source.get("canonical_title") or source.get("issue_id") or "未命名问题"
            objects = ", ".join(str(value) for value in item.get("decision_objects") or []) or "未识别"
            lines.append(f"- **{title}**（决策对象：{objects}）")
            if source.get("current_state"):
                lines.append(f"  - 原始现状：{source.get('current_state')}")
            if source.get("evidence"):
                lines.append(f"  - 原始证据：{source.get('evidence')}")
            if source.get("suggestion"):
                lines.append(f"  - 原始建议：{source.get('suggestion')}")
    image_gaps = report.get("image_analysis_gaps") or []
    if image_gaps:
        lines.append("")
        lines.append("## 六、图片分析缺口")
        for gap in image_gaps:
            lines.append(f"- {gap}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_dual_pass_advice_markdown(advice: dict[str, Any]) -> str:
    assessment = advice.get("quality_assessment") or {}
    lineage_counts = advice.get("lineage_counts") or {}
    lineage_counts_raw = advice.get("lineage_counts_raw") or lineage_counts
    lineage_counts_materialized = advice.get("lineage_counts_materialized") or {}
    block_reasons = advice.get("candidate_block_reasons") or []
    block_categories = advice.get("candidate_block_reason_categories") or {}
    lines: list[str] = []
    lines.append("# Dual Pass 副评审建议")
    lines.append("")
    lines.append("## 总体判断")
    lines.append(str(assessment.get("summary") or "未提供总体判断。"))
    lines.append("")
    lines.append(f"- 建议等级：{assessment.get('suggestion_level') or 'unknown'}")
    lines.append(f"- 是否建议候选稿直出：{'是' if assessment.get('ready_for_direct_output') else '否'}")
    if assessment.get("reason"):
        lines.append(f"- 原因：{assessment.get('reason')}")
    lines.append(f"- 可追踪性：{advice.get('traceability_status') or 'unavailable'}")
    lines.append(f"- readiness 是否冲突：{'是' if advice.get('readiness_conflict') else '否'}")
    lines.append(f"- candidate 是否有结构漂移：{'是' if advice.get('candidate_structure_drift') else '否'}")
    lines.append(f"- primary issue_id 修复数：{int(advice.get('primary_issue_id_repair_count') or 0)}")
    lines.append(f"- candidate issue_id 修复数：{int(advice.get('candidate_issue_id_repair_count') or 0)}")
    lines.append(f"- lineage 是否自动补齐：{'是' if advice.get('lineage_auto_healed') else '否'}")
    lines.append(f"- suggestion_level 是否与 readiness 冲突：{'是' if advice.get('suggestion_level_conflict') else '否'}")
    lines.append(f"- 是否已对 suggestion_level 冲突做 override：{'是' if advice.get('suggestion_level_override_applied') else '否'}")
    lines.append(f"- advice 与 candidate 落盘是否一致：{'否' if advice.get('advice_candidate_structure_mismatch') else '是'}")
    lines.append(
        f"- lineage 原始统计：kept={lineage_counts_raw.get('kept', 0)}, added={lineage_counts_raw.get('added', 0)}, merged={lineage_counts_raw.get('merged', 0)}, dropped={lineage_counts_raw.get('dropped', 0)}"
    )
    lines.append(
        f"- lineage 实际落盘统计：kept={lineage_counts_materialized.get('kept', 0)}, added={lineage_counts_materialized.get('added', 0)}, merged={lineage_counts_materialized.get('merged', 0)}, dropped={lineage_counts_materialized.get('dropped', 0)}"
    )
    if advice.get("lineage_auto_mapped_primary_issue_ids"):
        lines.append(
            f"- 自动补齐的 primary issue_id：{', '.join(str(item) for item in advice.get('lineage_auto_mapped_primary_issue_ids') or [])}"
        )
    if advice.get("lineage_auto_mapped_candidate_issue_ids"):
        lines.append(
            f"- 自动补齐的 candidate issue_id：{', '.join(str(item) for item in advice.get('lineage_auto_mapped_candidate_issue_ids') or [])}"
        )
    lines.append(f"- added 落盘状态：{advice.get('candidate_added_materialization_status') or 'none'}")
    lines.append(f"- merged 落盘状态：{advice.get('candidate_merged_materialization_status') or 'none'}")
    if advice.get("candidate_added_materialization_missing_ids"):
        lines.append(
            f"- 未落盘的 added issue_id：{', '.join(str(item) for item in advice.get('candidate_added_materialization_missing_ids') or [])}"
        )
    if advice.get("candidate_merged_materialization_missing_ids"):
        lines.append(
            f"- 未落盘的 merged issue_id：{', '.join(str(item) for item in advice.get('candidate_merged_materialization_missing_ids') or [])}"
        )
    if advice.get("candidate_issue_id_split_detected"):
        lines.append(
            f"- kept 子编号 issue_id：{', '.join(str(item) for item in advice.get('candidate_issue_id_split_issue_ids') or [])}"
        )
    if advice.get("candidate_negated_primary_finding_still_materialized"):
        lines.append(
            f"- 已被否定但仍落盘的 primary 问题：{', '.join(str(item) for item in advice.get('candidate_negated_primary_titles') or [])}"
        )
    if advice.get("candidate_blocker_conclusion_mismatch"):
        lines.append(
            f"- top_blockers 与 findings 结论不同步：{', '.join(str(item) for item in advice.get('candidate_blocker_conclusion_mismatch_titles') or [])}"
        )
    if advice.get("candidate_high_signal_demotion_without_support"):
        lines.append(
            f"- candidate 下调了高信号核心问题但缺少明确依据：{', '.join(str(item) for item in advice.get('candidate_high_signal_demotion_titles') or [])}"
        )
    if advice.get("candidate_overcompressed"):
        lines.append(
            f"- candidate 存在过度收缩风险：{advice.get('candidate_overcompressed_reason') or '问题数收缩过快且伴随较多共享问题改写。'}"
        )
    if advice.get("candidate_major_judgment_drift"):
        lines.append("- candidate 存在较大结论漂移，当前改判依据不足。")
    phase2_admission = advice.get("phase2_admission") or {}
    if phase2_admission.get("enabled"):
        lines.append(
            f"- phase2 新增准入：声称 {phase2_admission.get('claimed_count', 0)}，"
            f"通过 {phase2_admission.get('admitted_count', 0)}，拒绝 {phase2_admission.get('rejected_count', 0)}"
        )
        _append_phase2_coverage_ledger_lines(lines, phase2_admission)
        for item in phase2_admission.get("results") or []:
            if not isinstance(item, dict) or item.get("status") != "rejected":
                continue
            lines.append(
                f"  - 拒绝《{item.get('title') or item.get('candidate_issue_id') or '未命名问题'}》："
                f"{', '.join(str(reason) for reason in item.get('reasons') or [])}"
            )
    if block_reasons:
        lines.append(f"- 当前不建议默认切 candidate 的原因：{', '.join(str(item) for item in block_reasons)}")
    block_category_text = _render_block_categories_inline(block_categories)
    if block_category_text:
        lines.append(f"- 阻断分类：{block_category_text}")
    lines.append("")
    lines.append("## 优点")
    strengths = assessment.get("strengths") or []
    if strengths:
        for item in strengths:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## 问题")
    issues = assessment.get("issues") or []
    if issues:
        for item in issues:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## 复核备注")
    review_notes = advice.get("review_notes") or []
    if review_notes:
        for item in review_notes:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## 不支持的问题")
    unsupported = advice.get("unsupported_findings") or []
    if unsupported:
        for item in unsupported:
            lines.append(f"- {item.get('title', '未命名问题')}：{item.get('reason', '未说明原因')}")
    else:
        lines.append("- 暂无")
    lines.append("")
    lines.append("## 合并建议")
    merge_recommendations = advice.get("merge_recommendations") or []
    if merge_recommendations:
        for item in merge_recommendations:
            titles = " / ".join(str(title) for title in item.get("titles") or [] if str(title).strip())
            merged_title = str(item.get("merged_title") or "").strip()
            reason = str(item.get("reason") or "").strip()
            if merged_title:
                lines.append(f"- {titles} -> {merged_title}：{reason}".rstrip("："))
            else:
                lines.append(f"- {titles}：{reason}".rstrip("："))
    else:
        lines.append("- 暂无")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_dual_pass_summary_markdown(summary_payload: dict[str, Any]) -> str:
    block_category_text = _render_block_categories_inline(summary_payload.get("candidate_block_reason_categories") or {})
    comparison = summary_payload.get("comparison_summary") or {}
    lineage_counts = summary_payload.get("lineage_counts") or {}
    lineage_counts_raw = summary_payload.get("lineage_counts_raw") or lineage_counts
    lineage_counts_materialized = summary_payload.get("lineage_counts_materialized") or {}
    lines: list[str] = []
    lines.append("# Dual Pass 摘要")
    lines.append("")
    lines.append("## 运行状态")
    lines.append(f"- 状态：{summary_payload.get('status') or 'unknown'}")
    lines.append(f"- 主模型：{summary_payload.get('primary_model') or '<empty>'}")
    lines.append(f"- 副模型：{summary_payload.get('secondary_model') or '<empty>'}")
    lines.append(f"- Secondary 协议：{summary_payload.get('secondary_protocol_profile') or 'baseline'}")
    lines.append(f"- Secondary 协议修订：{summary_payload.get('secondary_protocol_revision') or 'legacy'}")
    lines.append(f"- Candidate 生成方式：{summary_payload.get('candidate_generation_mode') or 'unavailable'}")
    lines.append(f"- 证据包 ID：{summary_payload.get('coverage_evidence_packet_id') or '未生成'}")
    lines.append(f"- 证据包回显：{'通过' if summary_payload.get('coverage_evidence_packet_echoed') else '未通过'}")
    lines.append(f"- Delta-only 输出：{'通过' if summary_payload.get('phase2_delta_only_compliant') else '未通过'}")
    lines.append(f"- Pipeline 报告：{summary_payload.get('pipeline_report_path') or '未生成'}")
    lines.append(f"- Candidate 报告：{summary_payload.get('candidate_report_path') or '未生成'}")
    lines.append(f"- 建议文档：{summary_payload.get('advice_path') or '未生成'}")
    lines.append("")
    lines.append("## 评分与问题数")
    lines.append(f"- Primary 评分：{summary_payload.get('primary_score') or '未提供'}")
    lines.append(f"- Pipeline 评分：{summary_payload.get('pipeline_score') or '未提供'}")
    lines.append(f"- Candidate 评分：{summary_payload.get('candidate_score') or '未提供'}")
    lines.append(f"- Pipeline 问题数：{summary_payload.get('pipeline_finding_count', 0)}")
    lines.append(f"- Candidate 问题数：{summary_payload.get('candidate_finding_count', 0)}")
    lines.append(f"- 是否建议候选稿直出：{'是' if summary_payload.get('candidate_ready_for_direct_output') else '否'}")
    if summary_payload.get("candidate_ready_reason"):
        lines.append(f"- 原因：{summary_payload.get('candidate_ready_reason')}")
    lines.append(f"- 可追踪性：{summary_payload.get('traceability_status') or 'unavailable'}")
    lines.append(f"- readiness 是否冲突：{'是' if summary_payload.get('readiness_conflict') else '否'}")
    lines.append(f"- candidate 是否有结构漂移：{'是' if summary_payload.get('candidate_structure_drift') else '否'}")
    lines.append(f"- candidate 是否达到结构直出门槛：{'是' if summary_payload.get('candidate_structurally_ready') else '否'}")
    lines.append(f"- primary issue_id 修复数：{int(summary_payload.get('primary_issue_id_repair_count') or 0)}")
    lines.append(f"- candidate issue_id 修复数：{int(summary_payload.get('candidate_issue_id_repair_count') or 0)}")
    lines.append(f"- lineage 是否自动补齐：{'是' if summary_payload.get('lineage_auto_healed') else '否'}")
    lines.append(f"- suggestion_level 是否与 readiness 冲突：{'是' if summary_payload.get('suggestion_level_conflict') else '否'}")
    lines.append(f"- 是否已对 suggestion_level 冲突做 override：{'是' if summary_payload.get('suggestion_level_override_applied') else '否'}")
    lines.append(f"- 当前是否仅被编辑性判断阻断：{'是' if summary_payload.get('candidate_blocked_only_by_editorial_judgment') else '否'}")
    phase2_admission = summary_payload.get("phase2_admission") or {}
    if phase2_admission.get("enabled"):
        lines.append(
            f"- phase2 新增准入：通过 {phase2_admission.get('admitted_count', 0)} / "
            f"声称 {phase2_admission.get('claimed_count', 0)}，拒绝 {phase2_admission.get('rejected_count', 0)}"
        )
        _append_phase2_coverage_ledger_lines(lines, phase2_admission)
    lines.append(
        f"- Primary Top 3 保留率：{summary_payload.get('primary_top3_retention') if summary_payload.get('primary_top3_retention') is not None else '-'}"
    )
    lines.append(
        f"- Candidate 评分锁定 Primary：{'是' if summary_payload.get('candidate_score_locked_to_primary') else '否'}"
    )
    lines.append(f"- advice 与 candidate 落盘是否一致：{'否' if summary_payload.get('advice_candidate_structure_mismatch') else '是'}")
    lines.append(
        f"- 是否存在无依据的高信号问题降级：{'是' if summary_payload.get('candidate_high_signal_demotion_without_support') else '否'}"
    )
    if summary_payload.get("candidate_high_signal_demotion_titles"):
        lines.append(
            f"- 涉及问题：{', '.join(str(item) for item in summary_payload.get('candidate_high_signal_demotion_titles') or [])}"
        )
    lines.append(f"- candidate 是否存在过度收缩：{'是' if summary_payload.get('candidate_overcompressed') else '否'}")
    if summary_payload.get("candidate_overcompressed_reason"):
        lines.append(f"- 收缩说明：{summary_payload.get('candidate_overcompressed_reason')}")
    if summary_payload.get("candidate_block_reasons"):
        lines.append(
            f"- 当前不建议默认切 candidate 的原因：{', '.join(str(item) for item in summary_payload.get('candidate_block_reasons') or [])}"
        )
    if block_category_text:
        lines.append(f"- 阻断分类：{block_category_text}")
    lines.append("")
    lines.append("## Trace 摘要")
    lines.append(
        f"- raw：kept={lineage_counts_raw.get('kept', 0)}, added={lineage_counts_raw.get('added', 0)}, merged={lineage_counts_raw.get('merged', 0)}, dropped={lineage_counts_raw.get('dropped', 0)}"
    )
    lines.append(
        f"- materialized：kept={lineage_counts_materialized.get('kept', 0)}, added={lineage_counts_materialized.get('added', 0)}, merged={lineage_counts_materialized.get('merged', 0)}, dropped={lineage_counts_materialized.get('dropped', 0)}"
    )
    if summary_payload.get("lineage_auto_mapped_primary_issue_ids"):
        lines.append(
            f"- 自动补齐的 primary issue_id：{', '.join(str(item) for item in summary_payload.get('lineage_auto_mapped_primary_issue_ids') or [])}"
        )
    if summary_payload.get("lineage_auto_mapped_candidate_issue_ids"):
        lines.append(
            f"- 自动补齐的 candidate issue_id：{', '.join(str(item) for item in summary_payload.get('lineage_auto_mapped_candidate_issue_ids') or [])}"
        )
    lines.append(f"- added 落盘状态：{summary_payload.get('candidate_added_materialization_status') or 'none'}")
    lines.append(f"- merged 落盘状态：{summary_payload.get('candidate_merged_materialization_status') or 'none'}")
    if summary_payload.get("trace_warning"):
        lines.append(f"- trace warning：{summary_payload.get('trace_warning')}")
    lines.append("")
    lines.append("## 对比摘要")
    lines.append(f"- Pipeline 独有问题数：{comparison.get('pipeline_only_count', 0)}")
    lines.append(f"- Candidate 独有问题数：{comparison.get('candidate_only_count', 0)}")
    lines.append(f"- 共享问题中的重大改写数：{comparison.get('materially_changed_count', 0)}")
    if comparison.get("pipeline_only_titles"):
        lines.append(f"- Pipeline 独有示例：{'；'.join(str(title) for title in comparison.get('pipeline_only_titles') or [])}")
    if comparison.get("candidate_only_titles"):
        lines.append(f"- Candidate 独有示例：{'；'.join(str(title) for title in comparison.get('candidate_only_titles') or [])}")
    if comparison.get("materially_changed_titles"):
        lines.append(f"- 重大改写示例：{'；'.join(str(title) for title in comparison.get('materially_changed_titles') or [])}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_dual_pass_index_markdown(summary_payload: dict[str, Any]) -> str:
    block_category_text = _render_block_categories_inline(summary_payload.get("candidate_block_reason_categories") or {})
    comparison = summary_payload.get("comparison_summary") or {}
    gate_failures = summary_payload.get("candidate_gate_failure_reasons") or []
    lineage_counts = summary_payload.get("lineage_counts") or {}
    lineage_counts_raw = summary_payload.get("lineage_counts_raw") or lineage_counts
    lineage_counts_materialized = summary_payload.get("lineage_counts_materialized") or {}
    lines: list[str] = []
    lines.append("# Dual Pass 索引")
    lines.append("")
    lines.append("## 运行结果")
    lines.append(f"- 状态：{summary_payload.get('status') or 'unknown'}")
    lines.append(f"- 主模型：{summary_payload.get('primary_model') or '<empty>'}")
    lines.append(f"- 副模型：{summary_payload.get('secondary_model') or '<empty>'}")
    lines.append(f"- Secondary 协议：{summary_payload.get('secondary_protocol_profile') or 'baseline'}")
    lines.append(f"- Secondary 协议修订：{summary_payload.get('secondary_protocol_revision') or 'legacy'}")
    lines.append(f"- Candidate 生成方式：{summary_payload.get('candidate_generation_mode') or 'unavailable'}")
    lines.append(f"- 证据包回显：{'通过' if summary_payload.get('coverage_evidence_packet_echoed') else '未通过'}")
    lines.append(f"- Delta-only 输出：{'通过' if summary_payload.get('phase2_delta_only_compliant') else '未通过'}")
    lines.append(f"- 默认最终报告来源：{summary_payload.get('selected_report_owner') or 'pipeline'}")
    lines.append(f"- 默认最终报告路径：{summary_payload.get('selected_report_path') or 'review_report.md'}")
    lines.append(f"- 实际来源副本：{summary_payload.get('selected_source_report_path') or '<empty>'}")
    lines.append("")
    lines.append("## 推荐门槛")
    lines.append(f"- 推荐状态：{summary_payload.get('candidate_recommendation_status') or 'candidate_unavailable'}")
    lines.append(f"- 未通过原因：{', '.join(str(item) for item in gate_failures) if gate_failures else '无'}")
    phase2_admission = summary_payload.get("phase2_admission") or {}
    if phase2_admission.get("enabled"):
        lines.append(
            f"- phase2 新增准入：通过 {phase2_admission.get('admitted_count', 0)} / "
            f"声称 {phase2_admission.get('claimed_count', 0)}，拒绝 {phase2_admission.get('rejected_count', 0)}"
        )
        _append_phase2_coverage_ledger_lines(lines, phase2_admission)
    lines.append(
        f"- Primary Top 3 门槛：{'通过' if summary_payload.get('primary_top3_retention_gate_passed') else '未通过'}"
    )
    lines.append(
        f"- Candidate 评分锁定 Primary：{'是' if summary_payload.get('candidate_score_locked_to_primary') else '否'}"
    )
    if block_category_text:
        lines.append(f"- 阻断分类：{block_category_text}")
    lines.append(f"- Candidate 直出建议：{'是' if summary_payload.get('candidate_ready_for_direct_output') else '否'}")
    if summary_payload.get("candidate_ready_reason"):
        lines.append(f"- 原因：{summary_payload.get('candidate_ready_reason')}")
    lines.append(f"- 可追踪性：{summary_payload.get('traceability_status') or 'unavailable'}")
    lines.append(f"- readiness 是否冲突：{'是' if summary_payload.get('readiness_conflict') else '否'}")
    lines.append(f"- candidate 是否有结构漂移：{'是' if summary_payload.get('candidate_structure_drift') else '否'}")
    lines.append(f"- candidate 是否达到结构直出门槛：{'是' if summary_payload.get('candidate_structurally_ready') else '否'}")
    lines.append(f"- primary issue_id 修复数：{int(summary_payload.get('primary_issue_id_repair_count') or 0)}")
    lines.append(f"- candidate issue_id 修复数：{int(summary_payload.get('candidate_issue_id_repair_count') or 0)}")
    lines.append(f"- lineage 是否自动补齐：{'是' if summary_payload.get('lineage_auto_healed') else '否'}")
    lines.append(f"- suggestion_level 是否与 readiness 冲突：{'是' if summary_payload.get('suggestion_level_conflict') else '否'}")
    lines.append(f"- 是否已对 suggestion_level 冲突做 override：{'是' if summary_payload.get('suggestion_level_override_applied') else '否'}")
    lines.append(f"- 当前是否仅被编辑性判断阻断：{'是' if summary_payload.get('candidate_blocked_only_by_editorial_judgment') else '否'}")
    lines.append(f"- advice 与 candidate 落盘是否一致：{'否' if summary_payload.get('advice_candidate_structure_mismatch') else '是'}")
    lines.append(
        f"- 是否存在无依据的高信号问题降级：{'是' if summary_payload.get('candidate_high_signal_demotion_without_support') else '否'}"
    )
    if summary_payload.get("candidate_high_signal_demotion_titles"):
        lines.append(
            f"- 涉及问题：{', '.join(str(item) for item in summary_payload.get('candidate_high_signal_demotion_titles') or [])}"
        )
    lines.append(f"- candidate 是否存在过度收缩：{'是' if summary_payload.get('candidate_overcompressed') else '否'}")
    if summary_payload.get("candidate_overcompressed_reason"):
        lines.append(f"- 收缩说明：{summary_payload.get('candidate_overcompressed_reason')}")
    lines.append("")
    lines.append("## 产物路径")
    lines.append(f"- Pipeline：{summary_payload.get('pipeline_report_path') or '未生成'}")
    lines.append(f"- Candidate：{summary_payload.get('candidate_report_path') or '未生成'}")
    lines.append(f"- Advice：{summary_payload.get('advice_path') or '未生成'}")
    lines.append("")
    lines.append("## 评分与问题数")
    lines.append(f"- Primary：{summary_payload.get('primary_score') or '未提供'}")
    lines.append(f"- Pipeline：{summary_payload.get('pipeline_score') or '未提供'}")
    lines.append(f"- Candidate：{summary_payload.get('candidate_score') or '未提供'}")
    lines.append(f"- Selected：{summary_payload.get('selected_score') or '未提供'}")
    lines.append(f"- Pipeline 问题数：{summary_payload.get('pipeline_finding_count', 0)}")
    lines.append(f"- Candidate 问题数：{summary_payload.get('candidate_finding_count', 0)}")
    lines.append(f"- Selected 问题数：{summary_payload.get('selected_finding_count', 0)}")
    lines.append("")
    lines.append("## Trace 摘要")
    lines.append(
        f"- raw：kept={lineage_counts_raw.get('kept', 0)}, added={lineage_counts_raw.get('added', 0)}, merged={lineage_counts_raw.get('merged', 0)}, dropped={lineage_counts_raw.get('dropped', 0)}"
    )
    lines.append(
        f"- materialized：kept={lineage_counts_materialized.get('kept', 0)}, added={lineage_counts_materialized.get('added', 0)}, merged={lineage_counts_materialized.get('merged', 0)}, dropped={lineage_counts_materialized.get('dropped', 0)}"
    )
    if summary_payload.get("lineage_auto_mapped_primary_issue_ids"):
        lines.append(
            f"- 自动补齐的 primary issue_id：{', '.join(str(item) for item in summary_payload.get('lineage_auto_mapped_primary_issue_ids') or [])}"
        )
    if summary_payload.get("lineage_auto_mapped_candidate_issue_ids"):
        lines.append(
            f"- 自动补齐的 candidate issue_id：{', '.join(str(item) for item in summary_payload.get('lineage_auto_mapped_candidate_issue_ids') or [])}"
        )
    lines.append(f"- added 落盘状态：{summary_payload.get('candidate_added_materialization_status') or 'none'}")
    lines.append(f"- merged 落盘状态：{summary_payload.get('candidate_merged_materialization_status') or 'none'}")
    if summary_payload.get("trace_warning"):
        lines.append(f"- trace warning：{summary_payload.get('trace_warning')}")
    if summary_payload.get("candidate_block_reasons"):
        lines.append(f"- block reasons：{', '.join(str(item) for item in summary_payload.get('candidate_block_reasons') or [])}")
    lines.append("")
    lines.append("## 差异摘要")
    lines.append(f"- Pipeline 独有问题数：{comparison.get('pipeline_only_count', 0)}")
    lines.append(f"- Candidate 独有问题数：{comparison.get('candidate_only_count', 0)}")
    lines.append(f"- 共享问题中的重大改写数：{comparison.get('materially_changed_count', 0)}")
    if comparison.get("pipeline_only_titles"):
        lines.append(f"- Pipeline 独有示例：{'；'.join(str(title) for title in comparison.get('pipeline_only_titles') or [])}")
    if comparison.get("candidate_only_titles"):
        lines.append(f"- Candidate 独有示例：{'；'.join(str(title) for title in comparison.get('candidate_only_titles') or [])}")
    if comparison.get("materially_changed_titles"):
        lines.append(f"- 重大改写示例：{'；'.join(str(title) for title in comparison.get('materially_changed_titles') or [])}")
    if summary_payload.get("warning"):
        lines.append("")
        lines.append("## Warning")
        lines.append(f"- {summary_payload.get('warning')}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_report_diff_files(diff: dict[str, Any], markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_report_diff_markdown(diff), encoding="utf-8")
    json_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report_files(
    report: dict[str, Any],
    documents: list[ParsedDocument],
    markdown_path: Path,
    json_path: Path,
) -> None:
    assert_report_integrity(report)
    sanitized_report = strip_internal_report_fields(sanitize_report_dimension_notes(report))
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(sanitized_report, documents), encoding="utf-8")
    payload = {
        "report": sanitized_report,
        "input_summary": build_collection_summary(documents),
        "documents": [doc.compact_summary() for doc in documents],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_dual_pass_advice_files(advice: dict[str, Any], markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_dual_pass_advice_markdown(advice), encoding="utf-8")
    json_path.write_text(json.dumps(advice, ensure_ascii=False, indent=2), encoding="utf-8")


def write_dual_pass_summary_files(summary_payload: dict[str, Any], markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_dual_pass_summary_markdown(summary_payload), encoding="utf-8")
    json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_dual_pass_index_files(summary_payload: dict[str, Any], markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_dual_pass_index_markdown(summary_payload), encoding="utf-8")
    json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def count_report_findings(report: dict[str, Any]) -> int:
    return len(iter_public_findings(report))


__all__ = [
    "count_report_findings",
    "render_dual_pass_advice_markdown",
    "render_dual_pass_index_markdown",
    "render_dual_pass_summary_markdown",
    "render_finding",
    "render_markdown",
    "render_report_diff_markdown",
    "sanitize_dimension_note",
    "sanitize_report_dimension_notes",
    "strip_internal_report_fields",
    "write_dual_pass_advice_files",
    "write_dual_pass_index_files",
    "write_dual_pass_summary_files",
    "write_report_diff_files",
    "write_report_files",
]
