from __future__ import annotations

"""
调试用途：
这个脚本只读取已经生成好的 `reports/<运行目录>/` 产物，用来在复跑阶段批量对比多份报告。
它会汇总评分、问题数量、严重度分布、Top Blockers、日志 warning，以及同一批文档在多次运行中的共同问题/漂移问题，
帮助判断当前是模型波动，还是报告归一化、去重、融合链路出现了稳定性问题。
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from rad_review.reporting.ingest import extract_json_payload
from rad_review.reporting.normalize import normalize_compare_text
from rad_review.reporting.rules import build_root_cause_key


WARNING_PATTERN = re.compile(r"(parse warning|\bwarning\b|\bfailed\b|error=)", re.IGNORECASE)
PUBLIC_FINDING_FIELDS = (
    "title",
    "severity",
    "current_state",
    "evidence",
    "risk",
    "suggestion",
    "planner_role",
    "confidence",
    "blocking",
)
DUAL_PASS_REQUIRED_ARTIFACTS = (
    "review_report.md",
    "review_report.json",
    "review_report_pipeline.md",
    "review_report_pipeline.json",
    "review_report_candidate.md",
    "review_report_candidate.json",
    "review_report_index.md",
    "review_report_index.json",
    "secondary_review_advice.md",
    "secondary_review_advice.json",
    "model_artifacts/primary_raw_model_response.txt",
    "model_artifacts/secondary_raw_model_response.txt",
    "model_artifacts/shared_review_input.json",
    "model_artifacts/phase2_control_evidence_packet.json",
    "model_artifacts/dual_pass_summary.json",
)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def extract_report_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report = payload.get("report")
    if isinstance(report, dict):
        documents = payload.get("documents") or []
        return report, [item for item in documents if isinstance(item, dict)]
    return payload, []


def iter_public_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for dimension in report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        for finding in dimension.get("findings") or []:
            if isinstance(finding, dict):
                findings.append(finding)
    for finding in report.get("cross_document_issues") or []:
        if isinstance(finding, dict):
            findings.append(finding)
    return findings


def pick_finding_title(finding: dict[str, Any]) -> str:
    for key in ("title", "canonical_title", "issue_title"):
        value = str(finding.get(key) or "").strip()
        if value:
            return value
    return "(未命名问题)"


def severity_bucket(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未标注"
    if "高" in text:
        return "高"
    if "中" in text:
        return "中"
    if "低" in text:
        return "低"
    return text


def extract_warning_lines(log_path: Path) -> list[str]:
    if not log_path.exists():
        return []
    warning_lines: list[str] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "text model retry scheduled" in line.lower():
            continue
        if WARNING_PATTERN.search(line):
            warning_lines.append(line.strip())
    return warning_lines


def load_fusion_summary(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "model_artifacts" / "fusion_merge_summary.json"
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def raw_output_json_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "direct_json": False, "chars": 0}
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = json.loads(extract_json_payload(raw))
        direct_json = isinstance(payload, dict)
    except Exception:
        direct_json = False
    return {"exists": True, "direct_json": direct_json, "chars": len(raw)}


def collect_missing_finding_fields(findings: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for index, finding in enumerate(findings, start=1):
        issue_id = str(finding.get("issue_id") or f"finding_{index}").strip()
        for field in PUBLIC_FINDING_FIELDS:
            if not str(finding.get(field) or "").strip():
                missing.append(f"{issue_id}:{field}")
    return missing


def summarize_image_statuses(run_dir: Path) -> dict[str, int]:
    manifest = load_optional_json(run_dir / "extraction_manifest.json")
    counts: Counter[str] = Counter()
    for document in manifest.get("documents") or []:
        if not isinstance(document, dict):
            continue
        for image in document.get("images") or []:
            if isinstance(image, dict):
                counts[str(image.get("status") or "unknown")] += 1
    return dict(sorted(counts.items()))


def resolve_run_dir(argument: str, reports_root: Path) -> Path:
    candidate = Path(argument)
    if candidate.exists():
        return candidate.resolve()
    return (reports_root / argument).resolve()


def resolve_report_dirs(argument: str, reports_root: Path) -> list[tuple[Path, str | None]]:
    run_dir = resolve_run_dir(argument, reports_root)
    report_path = run_dir / "review_report.json"
    if report_path.exists():
        return [(run_dir, None)]
    nested_run_dirs = sorted(
        child for child in run_dir.iterdir() if child.is_dir() and (child / "review_report.json").exists()
    ) if run_dir.exists() else []
    if nested_run_dirs:
        return [(child, f"{run_dir.name}/{child.name}") for child in nested_run_dirs]
    return [(run_dir, None)]


def summarize_run(run_dir: Path, run_id: str | None = None) -> dict[str, Any]:
    report_path = run_dir / "review_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"未找到报告文件: {report_path}")

    payload = load_json(report_path)
    report, documents = extract_report_payload(payload)
    findings = iter_public_findings(report)
    cross_findings = [item for item in report.get("cross_document_issues") or [] if isinstance(item, dict)]
    severity_counts = Counter(severity_bucket(item.get("severity")) for item in findings)

    title_map: dict[str, str] = {}
    root_key_map: dict[str, str] = {}
    for finding in findings:
        title = pick_finding_title(finding)
        title_map.setdefault(normalize_compare_text(title), title)
        root_key = build_root_cause_key(finding) or normalize_compare_text(title)
        root_key_map.setdefault(root_key, title)

    blockers = []
    for blocker in report.get("top_blockers") or []:
        if not isinstance(blocker, dict):
            continue
        title = str(blocker.get("title") or "").strip()
        if title:
            blockers.append(title)

    index_payload = load_optional_json(run_dir / "review_report_index.json")
    dual_pass_summary = load_optional_json(run_dir / "model_artifacts" / "dual_pass_summary.json")
    metadata = load_optional_json(run_dir / "model_artifacts" / "run_metadata.json")
    required_artifacts = DUAL_PASS_REQUIRED_ARTIFACTS if str(report.get("review_mode") or "").startswith("dual_pass") else (
        "review_report.md",
        "review_report.json",
    )
    missing_artifacts = [relative for relative in required_artifacts if not (run_dir / relative).exists()]
    primary_raw_status = raw_output_json_status(run_dir / "model_artifacts" / "primary_raw_model_response.txt")
    secondary_raw_status = raw_output_json_status(run_dir / "model_artifacts" / "secondary_raw_model_response.txt")
    missing_finding_fields = collect_missing_finding_fields(findings)

    summary = {
        "run_id": run_id or run_dir.name,
        "run_dir": str(run_dir),
        "review_mode": str(report.get("review_mode") or "unknown"),
        "primary_model": str(report.get("primary_model") or ""),
        "secondary_model": str(report.get("secondary_model") or ""),
        "score": str(report.get("document_quality_score") or ""),
        "score_reason": str(report.get("score_reason") or ""),
        "document_names": [str(item.get("name") or "").strip() for item in documents if str(item.get("name") or "").strip()],
        "document_signature": sorted(
            f"{str(item.get('name') or '').strip()}|{str(item.get('kind') or '').strip()}"
            for item in documents
            if str(item.get("name") or "").strip()
        ),
        "total_findings": len(findings),
        "dimension_findings": len(findings) - len(cross_findings),
        "cross_document_findings": len(cross_findings),
        "severity_counts": dict(sorted(severity_counts.items())),
        "top_blockers": blockers,
        "warning_lines": extract_warning_lines(run_dir / "run.log"),
        "artifact_complete": not missing_artifacts,
        "missing_artifacts": missing_artifacts,
        "missing_finding_fields": missing_finding_fields,
        "image_status_counts": summarize_image_statuses(run_dir),
        "document_hash": str(metadata.get("document_hash") or ""),
        "primary_raw_output": primary_raw_status,
        "secondary_raw_output": secondary_raw_status,
        "selected_report_owner": str(index_payload.get("selected_report_owner") or ""),
        "candidate_ready_for_direct_output": bool(index_payload.get("candidate_ready_for_direct_output")),
        "traceability_status": str(index_payload.get("traceability_status") or ""),
        "candidate_structurally_ready": bool(index_payload.get("candidate_structurally_ready")),
        "candidate_gate_failure_reasons": list(index_payload.get("candidate_gate_failure_reasons") or []),
        "secondary_protocol_revision": str(
            index_payload.get("secondary_protocol_revision")
            or dual_pass_summary.get("secondary_protocol_revision")
            or ""
        ),
        "candidate_generation_mode": str(
            index_payload.get("candidate_generation_mode")
            or dual_pass_summary.get("candidate_generation_mode")
            or ""
        ),
        "coverage_evidence_packet_id": str(
            index_payload.get("coverage_evidence_packet_id")
            or dual_pass_summary.get("coverage_evidence_packet_id")
            or ""
        ),
        "coverage_evidence_packet_echoed": bool(
            index_payload.get("coverage_evidence_packet_echoed")
            or dual_pass_summary.get("coverage_evidence_packet_echoed")
        ),
        "phase2_delta_only_compliant": bool(
            index_payload.get("phase2_delta_only_compliant")
            or dual_pass_summary.get("phase2_delta_only_compliant")
        ),
        "phase2_protocol_gate_passed": bool(
            (index_payload.get("phase2_protocol_gate") or dual_pass_summary.get("phase2_protocol_gate") or {}).get(
                "passed"
            )
        ),
        "primary_issue_id_repair_count": int(index_payload.get("primary_issue_id_repair_count") or 0),
        "candidate_issue_id_repair_count": int(index_payload.get("candidate_issue_id_repair_count") or 0),
        "finding_titles": [title_map[key] for key in sorted(title_map)],
        "finding_title_map": title_map,
        "finding_root_map": root_key_map,
        "fusion_summary": load_fusion_summary(run_dir),
    }
    return summary


def compare_same_document_runs(run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    comparison: dict[str, Any] = {
        "same_documents": True,
        "score_distribution": dict(sorted(Counter(item["score"] or "未评分" for item in run_summaries).items())),
        "warning_run_count": sum(1 for item in run_summaries if item["warning_lines"]),
        "document_hash_distribution": sorted({item.get("document_hash") or "" for item in run_summaries}),
    }

    root_sets = [set(item["finding_root_map"].keys()) for item in run_summaries]
    if root_sets:
        common_keys = set.intersection(*root_sets)
        all_keys = set.union(*root_sets)
    else:
        common_keys = set()
        all_keys = set()

    display_lookup: dict[str, str] = {}
    for item in run_summaries:
        display_lookup.update(item["finding_root_map"])

    comparison["common_root_causes"] = [display_lookup[key] for key in sorted(common_keys)]
    comparison["drift_root_causes"] = [display_lookup[key] for key in sorted(all_keys - common_keys)]
    comparison["only_in_run"] = {
        item["run_id"]: [display_lookup[key] for key in sorted(set(item["finding_root_map"]) - common_keys)]
        for item in run_summaries
    }
    comparison["missing_in_run"] = {
        item["run_id"]: [display_lookup[key] for key in sorted(all_keys - set(item["finding_root_map"]))]
        for item in run_summaries
    }
    blocker_sets = []
    blocker_lookup: dict[str, str] = {}
    for item in run_summaries:
        keys = set()
        for title in item["top_blockers"]:
            key = normalize_compare_text(title)
            if not key:
                continue
            keys.add(key)
            blocker_lookup.setdefault(key, title)
        blocker_sets.append(keys)
    if blocker_sets:
        comparison["common_top_blockers"] = [blocker_lookup[key] for key in sorted(set.intersection(*blocker_sets))]
    else:
        comparison["common_top_blockers"] = []
    return comparison


def compare_runs(run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    doc_signatures = {tuple(item["document_signature"]) for item in run_summaries}
    same_documents = len(doc_signatures) <= 1
    if same_documents:
        comparison = compare_same_document_runs(run_summaries)
        comparison["document_groups"] = []
        return comparison

    comparison: dict[str, Any] = {
        "same_documents": False,
        "score_distribution": dict(sorted(Counter(item["score"] or "未评分" for item in run_summaries).items())),
        "warning_run_count": sum(1 for item in run_summaries if item["warning_lines"]),
        "note": "输入文档不一致（汇总中包含多款游戏），整体对比改为按相同输入文档分组。",
        "document_groups": [],
    }
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for item in run_summaries:
        grouped.setdefault(tuple(item["document_signature"]), []).append(item)
    for items in grouped.values():
        if len(items) < 2:
            continue
        game_names = {Path(str(item["run_dir"])).name for item in items}
        group_name = next(iter(game_names)) if len(game_names) == 1 else " / ".join(sorted(game_names))
        comparison["document_groups"].append(
            {
                "group": group_name,
                "run_ids": [item["run_id"] for item in items],
                "comparison": compare_same_document_runs(items),
            }
        )
    comparison["document_groups"].sort(key=lambda item: item["group"])
    return comparison


def format_models(summary: dict[str, Any]) -> str:
    primary = summary["primary_model"]
    secondary = summary["secondary_model"]
    if primary and secondary:
        return f"{primary} + {secondary}"
    return primary or secondary or "unknown"


def format_severity_counts(counts: dict[str, Any]) -> str:
    order = ("高", "中", "低", "未标注")
    seen = set()
    parts = []
    for key in order:
        if key in counts:
            parts.append(f"{key}{counts[key]}")
            seen.add(key)
    for key in sorted(counts):
        if key not in seen:
            parts.append(f"{key}{counts[key]}")
    return " / ".join(parts) if parts else "无"


def render_text(reports_root: Path, run_summaries: list[dict[str, Any]], comparison: dict[str, Any]) -> str:
    lines = [
        "报告调试汇总",
        f"报告根目录：{reports_root.resolve()}",
        f"运行数量：{len(run_summaries)}",
        "",
    ]
    for item in run_summaries:
        lines.append(f"[{item['run_id']}]")
        lines.append(f"  路径：{item['run_dir']}")
        lines.append(f"  文档：{', '.join(item['document_names']) or '未知'}")
        lines.append(f"  模式：{item['review_mode']}")
        lines.append(f"  模型：{format_models(item)}")
        lines.append(f"  评分：{item['score'] or '未评分'}")
        lines.append(
            "  问题："
            f"{item['total_findings']}（单文档 {item['dimension_findings']}，跨文档 {item['cross_document_findings']}；"
            f"严重度 {format_severity_counts(item['severity_counts'])}）"
        )
        if item["top_blockers"]:
            lines.append(f"  Top Blockers：{' | '.join(item['top_blockers'])}")
        lines.append(f"  工件完整：{'是' if item['artifact_complete'] else '否'}")
        if item["missing_artifacts"]:
            lines.append(f"  缺失工件：{', '.join(item['missing_artifacts'])}")
        lines.append(
            "  模型原始输出："
            f"primary JSON={'有效' if item['primary_raw_output']['direct_json'] else '无效/缺失'}，"
            f"secondary JSON={'有效' if item['secondary_raw_output']['direct_json'] else '无效/缺失'}"
        )
        if item["selected_report_owner"]:
            repair_count = item["primary_issue_id_repair_count"] + item["candidate_issue_id_repair_count"]
            lines.append(
                "  Dual Pass："
                f"采用 {item['selected_report_owner']}，"
                f"candidate_ready={item['candidate_ready_for_direct_output']}，"
                f"trace={item['traceability_status'] or 'unknown'}，"
                f"issue_id 修复={repair_count}"
            )
        if item["missing_finding_fields"]:
            lines.append(f"  Finding 必填字段缺失：{', '.join(item['missing_finding_fields'])}")
        if item["image_status_counts"]:
            image_text = " / ".join(f"{key}={value}" for key, value in item["image_status_counts"].items())
            lines.append(f"  图片解析：{image_text}")
        fusion = item["fusion_summary"]
        if fusion:
            lines.append(
                "  Fusion："
                f"+{fusion.get('added_unique_findings', 0)} 唯一问题，"
                f"+{fusion.get('added_unique_high_risk_findings', 0)} 唯一高风险问题"
            )
        if item["warning_lines"]:
            lines.append("  Warnings：")
            lines.extend(f"    - {line}" for line in item["warning_lines"])
        else:
            lines.append("  Warnings：无")
        lines.append("")

    lines.append("稳定性对比")
    lines.append(f"评分分布：{comparison.get('score_distribution', {})}")
    lines.append(f"出现 warning 的运行数：{comparison.get('warning_run_count', 0)}")
    if not comparison.get("same_documents"):
        lines.append(str(comparison.get("note") or "输入文档不一致。"))
        for group in comparison.get("document_groups") or []:
            group_comparison = group["comparison"]
            lines.append("")
            lines.append(f"[{group['group']}] 同输入复跑对比")
            lines.append(f"  运行：{', '.join(group['run_ids'])}")
            lines.append(f"  评分分布：{group_comparison.get('score_distribution', {})}")
            lines.append(
                f"  共享输入 hash 数：{len([item for item in group_comparison.get('document_hash_distribution', []) if item])}"
            )
            lines.append(f"  共同根因数：{len(group_comparison.get('common_root_causes', []))}")
            lines.append(f"  漂移根因数：{len(group_comparison.get('drift_root_causes', []))}")
            lines.append(f"  共同 Top Blockers 数：{len(group_comparison.get('common_top_blockers', []))}")
        return "\n".join(lines)

    lines.append(f"共同根因数：{len(comparison.get('common_root_causes', []))}")
    if comparison.get("common_top_blockers"):
        lines.append(f"共同 Top Blockers：{' | '.join(comparison['common_top_blockers'])}")
    drift_findings = comparison.get("drift_root_causes") or []
    lines.append(f"漂移根因数：{len(drift_findings)}")
    if drift_findings:
        lines.append("漂移根因：")
        lines.extend(f"  - {title}" for title in drift_findings)
    for item in run_summaries:
        only_titles = comparison.get("only_in_run", {}).get(item["run_id"]) or []
        missing_titles = comparison.get("missing_in_run", {}).get(item["run_id"]) or []
        lines.append(f"{item['run_id']} 仅本次出现：{len(only_titles)}")
        lines.extend(f"  - {title}" for title in only_titles)
        lines.append(f"{item['run_id']} 本次缺失：{len(missing_titles)}")
        lines.extend(f"  - {title}" for title in missing_titles)
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量汇总并对比多份已生成报告，帮助排查模型波动与报告链路稳定性。",
    )
    parser.add_argument("runs", nargs="+", help="运行目录名或运行目录路径，例如 20260604_173312")
    parser.add_argument("--reports-root", default="reports", help="报告根目录，默认是 reports")
    parser.add_argument("--json-out", help="可选：把汇总结果额外写成 JSON 文件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    reports_root = Path(args.reports_root)

    run_summaries = []
    for item in args.runs:
        for run_dir, run_id in resolve_report_dirs(item, reports_root):
            run_summaries.append(summarize_run(run_dir, run_id=run_id))

    comparison = compare_runs(run_summaries)
    text = render_text(reports_root, run_summaries, comparison)
    print(text)

    if args.json_out:
        output_path = Path(args.json_out)
        payload = {
            "reports_root": str(reports_root.resolve()),
            "runs": run_summaries,
            "comparison": comparison,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
