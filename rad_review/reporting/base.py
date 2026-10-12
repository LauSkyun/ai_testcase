from __future__ import annotations

import re
from typing import Any

from rad_review.prompts import DIMENSIONS

NO_FINDINGS_NOTE = "未发现明显问题"
NO_AI_ANALYSIS_NOTE = "未执行 AI 分析"

SEVERITY_RANK = {"低": 1, "中": 2, "高": 3}
CONFIDENCE_RANK = {"低": 1, "中": 2, "高": 3}
BLOCKING_RANK = {"建议优化": 1, "阻塞测试用例设计": 2, "阻塞开发": 3}
PLACEHOLDER_EVIDENCE_MARKERS = ("稳定基线检查项", "结合文档证据复核", "见相关文档章节")
LOW_SEVERITY_BLOCKING = "建议优化"
MEDIUM_SEVERITY_BLOCKING = "阻塞测试用例设计"

CANONICAL_ISSUES: list[dict[str, str]] = [
    {"issue_id": "CORE_TERMINOLOGY_UNIT_COUNT", "dimension": "清晰度与完整性", "title": "核心术语与单位定义不一致", "owner": "系统策划"},
    {"issue_id": "CORE_DIFFICULTY_CONFIG_MISMATCH", "dimension": "清晰度与完整性", "title": "难度、倍率或配置表含义不一致", "owner": "数值策划"},
    {"issue_id": "CORE_BET_CONFIG_MISMATCH", "dimension": "清晰度与完整性", "title": "下注金额或档位配置口径不一致", "owner": "数值策划"},
    {"issue_id": "CORE_JACKPOT_RULE_MISSING", "dimension": "清晰度与完整性", "title": "通关或大奖规则缺失", "owner": "系统策划"},
    {"issue_id": "LOGIC_COLLISION_MODEL_CONFLICT", "dimension": "逻辑一致性与数值平衡", "title": "碰撞判定模型冲突", "owner": "数值策划"},
    {"issue_id": "LOGIC_PAYOUT_FORMULA_CONFLICT", "dimension": "逻辑一致性与数值平衡", "title": "奖金公式与赔率表口径冲突", "owner": "数值策划"},
    {"issue_id": "LOGIC_RTP_PROBABILITY_MAPPING_MISSING", "dimension": "逻辑一致性与数值平衡", "title": "RTP 与概率映射缺失", "owner": "数值策划"},
    {"issue_id": "LOGIC_MAX_PAYOUT_MISSING", "dimension": "逻辑一致性与数值平衡", "title": "最大赔付或风控熔断缺失", "owner": "数值策划"},
    {"issue_id": "TEST_ACCEPTANCE_CRITERIA_MISSING", "dimension": "可测试性与验收标准", "title": "缺少量化验收标准", "owner": "系统策划"},
    {"issue_id": "TEST_CONCURRENT_OPERATION_MISSING", "dimension": "可测试性与验收标准", "title": "重复点击、并发或按钮互斥规则缺失", "owner": "系统策划"},
    {"issue_id": "COMP_RECONNECT_REENTER_MISSING", "dimension": "跨系统影响与兼容性", "title": "断线重连或重进状态恢复规则缺失", "owner": "系统策划"},
    {"issue_id": "COMP_CONFIG_HOT_UPDATE_MISSING", "dimension": "跨系统影响与兼容性", "title": "配置热更与历史局处理规则缺失", "owner": "系统策划"},
    {"issue_id": "SEC_SERVER_AUTHORITY_MISSING", "dimension": "安全性与反作弊", "title": "服务端权威判定与防篡改规则缺失", "owner": "系统策划"},
    {"issue_id": "SEC_CASHOUT_IDEMPOTENCY_MISSING", "dimension": "安全性与反作弊", "title": "提现幂等或重放防护缺失", "owner": "系统策划"},
    {"issue_id": "UX_FAILURE_GUIDANCE_MISSING", "dimension": "用户体验与游戏性", "title": "失败反馈或新手引导不足", "owner": "系统策划"},
]

CANONICAL_BY_ID = {item["issue_id"]: item for item in CANONICAL_ISSUES}

ROOT_CAUSE_CLUSTERS: tuple[dict[str, Any], ...] = (
    {"key": "formula_odds_conflict", "issue_ids": {"LOGIC_PAYOUT_FORMULA_CONFLICT"}, "must": (), "signal": ()},
    {"key": "intervention_mapping", "issue_ids": set(), "must": (), "signal": ()},
    {
        "key": "placeholder_configuration",
        "issue_ids": set(),
        "must": ("占位符", "[001]", "[002]", "[003]"),
        "signal": ("缺失", "未定义", "默认值", "可配范围", "阈值"),
    },
    {
        "key": "display_real_data_isolation",
        "issue_ids": set(),
        "must": ("假人数", "假金额", "显示数据", "展示数据", "真实结算", "真实下注", "奖池计量", "数据源"),
        "signal": ("未明确", "未区分", "隔离", "口径", "未说明", "未定义"),
    },
)


def dedupe_text_list(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def normalize_compare_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[\s`~!@#$%^&*()_\-+=\[\]{}\\|;:'\",.<>/?，。；：！？、】【《》“”‘’—]", "", lowered)
    return lowered


def has_any(text: str, *terms: str) -> bool:
    return any(term.lower() in text for term in terms)


def normalized_max(kind: str, values: list[Any]) -> str:
    ranks = {"severity": SEVERITY_RANK, "confidence": CONFIDENCE_RANK, "blocking": BLOCKING_RANK}[kind]
    fallback = {"severity": "中", "confidence": "中", "blocking": "阻塞测试用例设计"}[kind]
    best = fallback
    for value in values:
        text = str(value or "").strip()
        if ranks.get(text, 0) > ranks.get(best, 0):
            best = text
    return best


def merge_scope(left: str, right: str) -> str:
    if left == right:
        return left
    if "cross_document" in (left, right):
        return "cross_document"
    if not left:
        return right
    return left


def merge_text(left: str, right: str) -> str:
    left = str(left or "").strip()
    right = str(right or "").strip()
    if not left:
        return right
    if not right or right in left:
        return left
    if left in right:
        return right
    return f"{left}；{right}"


def finding_priority(finding: dict[str, Any]) -> tuple[int, int, int]:
    return (
        SEVERITY_RANK.get(str(finding.get("severity") or ""), 0),
        BLOCKING_RANK.get(str(finding.get("blocking") or ""), 0),
        CONFIDENCE_RANK.get(str(finding.get("confidence") or ""), 0),
    )


def sort_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(findings, key=lambda finding: int(finding.get("_order", 999999)))


def public_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in finding.items() if not key.startswith("_")}


def sort_public_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda finding: (
            -SEVERITY_RANK.get(str(finding.get("severity") or ""), 0),
            -BLOCKING_RANK.get(str(finding.get("blocking") or ""), 0),
            -CONFIDENCE_RANK.get(str(finding.get("confidence") or ""), 0),
            str(finding.get("title") or finding.get("canonical_title") or ""),
        ),
    )
