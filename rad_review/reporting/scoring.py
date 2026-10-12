from __future__ import annotations

from typing import Any

from .base import BLOCKING_RANK, CONFIDENCE_RANK, SEVERITY_RANK, normalize_compare_text, has_any
from .duplicates import collect_distinct_root_findings
from .rules import finding_root_key, finding_signal_text, identify_issue_id_from_text


def is_fatal_core_conflict(finding: dict[str, Any]) -> bool:
    text = " ".join(str(finding.get(field) or "").lower() for field in ("title", "current_state", "evidence"))
    issue_id = str(finding.get("issue_id") or "")
    is_high = str(finding.get("severity") or "") == "高" or str(finding.get("blocking") or "") == "阻塞开发"
    if not is_high:
        return False
    fatal_words = ("根本", "无法兼容", "无法并存", "完全矛盾", "互相矛盾", "重大矛盾", "完全偏离", "无法形成一致方案")
    formula_words = ("赔率", "奖金", "公式", "赔付", "结算", "rtp", "概率", "数值模型", "开奖")
    if has_any(text, *fatal_words) and has_any(text, *formula_words):
        return True
    if str(finding.get("evidence_scope") or "") == "cross_document" and issue_id in {"LOGIC_PAYOUT_FORMULA_CONFLICT", "LOGIC_COLLISION_MODEL_CONFLICT"} and has_any(text, *fatal_words):
        return True
    if has_any(text, "最大赔付", "赔付上限") and has_any(text, "极端倍率", "千万", "百万", "超额", "上限缺失"):
        return True
    if has_any(text, "核心玩法无法理解", "状态机无法形成", "结算链路无法理解"):
        return True
    return False


def is_blocking_high(finding: dict[str, Any]) -> bool:
    return str(finding.get("severity") or "") == "高" or str(finding.get("blocking") or "") == "阻塞开发"


def blocker_priority(finding: dict[str, Any]) -> int:
    text = finding_signal_text(finding)
    issue_id = str(finding.get("issue_id") or "")
    if is_fatal_core_conflict(finding):
        return 5
    if issue_id.startswith(("CORE_", "LOGIC_")) or has_any(text, "核心", "玩法", "数值", "公式", "赔率", "概率", "rtp", "结算", "扣款", "提现", "赔付", "最大赔付", "筹码", "难度", "倍率", "max_mul"):
        return 4
    if has_any(text, "重进", "重连", "断线", "异常", "验收", "重复点击", "幂等", "热更", "历史局", "边界"):
        return 3
    if issue_id.startswith(("SEC_", "COMP_")):
        return 2
    return 1


def stable_score(report: dict[str, Any]) -> tuple[str, str]:
    all_findings = collect_distinct_root_findings(report)
    if not all_findings:
        return "A", "当前文档整体较完整，未发现会阻塞开发与测试设计的明显问题。"
    fatal_findings = [finding for finding in all_findings if is_fatal_core_conflict(finding)]
    if fatal_findings:
        title = fatal_findings[0].get("title") or "核心玩法或结算链路存在根本冲突"
        return "D", f"{title}，当前文档不足以让开发和测试形成一致方案。"
    high_blockers = [finding for finding in all_findings if is_blocking_high(finding)]
    severe_mid_risks = [finding for finding in all_findings if str(finding.get("severity") or "") == "中"]
    if high_blockers:
        if len(high_blockers) < 3:
            return "B", "主流程和关键数值基本可落地，当前仅剩少量高风险问题，补齐后即可推进完整开发与测试。"
        return "C", "主流程可理解，但仍存在高风险缺口或关键边界缺失，需要补充后再完整开工。"
    if severe_mid_risks or any(str(finding.get("blocking") or "") == "阻塞测试用例设计" for finding in all_findings):
        return "B", "主流程基本可落地，但仍有一些中风险问题需要补充澄清。"
    return "A", "当前文档整体较完整，未发现会阻塞开发与测试设计的明显问题。"


def top_blocker_from_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": finding.get("severity", "中"),
        "title": finding.get("title") or finding.get("canonical_title") or "未命名问题",
        "owner": finding.get("planner_role") or finding.get("owner") or "待定",
        "why_now": finding.get("risk") or "该问题会直接影响开发和测试落地。",
        "finding_source": finding.get("finding_source") or "",
        "finding_source_label": finding.get("finding_source_label") or "",
        "source_model": finding.get("source_model") or "",
    }


def top_blocker_candidate_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        [finding for finding in collect_distinct_root_findings(report) if is_blocking_high(finding)],
        key=lambda finding: (
            -blocker_priority(finding),
            -SEVERITY_RANK.get(str(finding.get("severity") or ""), 0),
            -BLOCKING_RANK.get(str(finding.get("blocking") or ""), 0),
            int(finding.get("_order", 999999)),
            str(finding.get("title") or finding.get("canonical_title") or ""),
        ),
    )


def build_top_blockers(report: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in top_blocker_candidate_findings(report):
        dedupe_key = finding_root_key(finding) or str(finding.get("issue_id") or finding.get("title") or "")
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        blockers.append(top_blocker_from_finding(finding))
        if len(blockers) >= 3:
            break
    return blockers


def find_preferred_blocker_match(preferred: dict[str, Any], candidates: list[dict[str, Any]], used_indexes: set[int]) -> int | None:
    preferred_title = str(preferred.get("title") or "").strip()
    preferred_text = " ".join(part for part in (preferred_title, str(preferred.get("why_now") or "").strip()) if part)
    preferred_issue_id = identify_issue_id_from_text(preferred_text)
    preferred_key = normalize_compare_text(preferred_title)
    for index, blocker in enumerate(candidates):
        if index in used_indexes:
            continue
        blocker_title = str(blocker.get("title") or "").strip()
        blocker_key = normalize_compare_text(blocker_title)
        if preferred_key and blocker_key and (preferred_key in blocker_key or blocker_key in preferred_key):
            return index
    if preferred_issue_id:
        for index, blocker in enumerate(candidates):
            if index in used_indexes:
                continue
            blocker_text = " ".join(part for part in (str(blocker.get("title") or "").strip(), str(blocker.get("why_now") or "").strip()) if part)
            blocker_issue_id = identify_issue_id_from_text(blocker_text)
            if blocker_issue_id and blocker_issue_id == preferred_issue_id:
                return index
    return None


def reorder_top_blockers_by_preference(report: dict[str, Any], preferred_blockers: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    candidates = [top_blocker_from_finding(finding) for finding in top_blocker_candidate_findings(report)]
    if not preferred_blockers:
        return candidates[:3]
    ordered: list[dict[str, Any]] = []
    used_indexes: set[int] = set()
    for preferred in preferred_blockers:
        if not isinstance(preferred, dict):
            continue
        match_index = find_preferred_blocker_match(preferred, candidates, used_indexes)
        if match_index is None:
            continue
        ordered.append(dict(candidates[match_index]))
        used_indexes.add(match_index)
    for index, blocker in enumerate(candidates):
        if index in used_indexes:
            continue
        ordered.append(dict(blocker))
    return ordered[:3]
