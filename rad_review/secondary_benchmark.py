from __future__ import annotations

import copy
import hashlib
import json
import re
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rad_review.docx_reader import ImageBlock, ParagraphBlock, ParsedDocument, TableBlock, sanitize_filename
from rad_review.model_client import ModelConfig, OpenAICompatibleClient
from rad_review.phase3 import (
    PHASE3_PROTOCOL_REVISIONS,
    PHASE3_V12_PROTOCOL_REVISION,
    PHASE3_V13_PROTOCOL_REVISION,
    apply_human_approved_phase3_corrections,
    evaluate_phase3_review,
    parse_phase3_review_json,
    write_phase3_artifacts,
)
from rad_review.prompts import (
    build_dual_pass_secondary_messages,
    build_phase2_control_evidence_packet,
    normalize_secondary_protocol_profile,
)
from rad_review.reporting.base import normalize_compare_text
from rad_review.reporting.ingest import parse_candidate_model_json, parse_dual_pass_review_json, parse_model_json
from rad_review.reporting.modes import (
    build_conservative_dual_pass_candidate_report,
    build_deterministic_phase2_candidate,
    build_dual_pass_comparison_summary,
    build_dual_pass_secondary_finding,
    demote_dual_pass_cross_document_issues,
    evaluate_dual_pass_candidate_selection,
    evaluate_phase2_protocol_gate,
    lock_dual_pass_candidate_score_to_primary,
    lock_dual_pass_candidate_top_blockers_to_primary,
    sanitize_dual_pass_phase2_candidate_review,
    merge_dual_pass_review_report,
    normalize_dual_pass_advice_payload,
)
from rad_review.reporting.render import (
    count_report_findings,
    write_dual_pass_advice_files,
    write_report_files,
)
from rad_review.reporting.rules import identify_root_cause_cluster, inferred_canonical_issue_id
from rad_review.run_logger import RunLogger


REQUIRED_FROZEN_ARTIFACTS = (
    "shared_review_input.json",
    "primary_raw_model_response.txt",
    "primary_review_messages.json",
    "run_metadata.json",
)

ANNOTATION_FIELDS = (
    "valid",
    "duplicate",
    "unsupported",
    "overstated",
    "understated",
    "multiroot",
    "actionable",
)

PHASE3_CHALLENGE_ANNOTATION_FIELDS = (
    "target_correct",
    "valid",
    "evidence_locatable",
    "actionable",
    "should_split",
)

PHASE3_CORRECTION_ANNOTATION_FIELDS = (
    "target_correct",
    "accurate",
    "supported",
    "safe_to_apply",
)

ALL_ANNOTATION_FIELDS = tuple(
    dict.fromkeys(
        ANNOTATION_FIELDS
        + PHASE3_CHALLENGE_ANNOTATION_FIELDS
        + PHASE3_CORRECTION_ANNOTATION_FIELDS
    )
)


def annotation_fields_for_item(item: dict[str, Any]) -> tuple[str, ...]:
    change_type = str(item.get("change_type") or "added").strip().lower()
    if change_type == "challenge":
        return PHASE3_CHALLENGE_ANNOTATION_FIELDS
    if change_type == "correction":
        return PHASE3_CORRECTION_ANNOTATION_FIELDS
    return ANNOTATION_FIELDS

ADDED_REQUIRED_FIELDS = (
    "title",
    "current_state",
    "evidence",
    "risk",
    "suggestion",
    "severity",
    "blocking",
)

PRIVATE_SUMMARY_RELATIVE_PATH = Path("_private") / "secondary_benchmark_internal.json"
PRIVATE_MANIFEST_RELATIVE_PATH = Path("_private") / "benchmark_manifest_internal.json"
PRIVATE_ANNOTATION_RELATIVE_PATH = Path("_private") / "human_annotation_internal.json"
BLIND_SENSITIVE_MARKERS = (
    "protocol_profile",
    "processing_profile",
    "phase2",
    "baseline",
    "evidence_packet_id",
    "coverage_protocol_revision",
    "delta_only",
    "phase3_v1",
    "primary_report_hash",
)


def contains_blind_sensitive_text(value: Any) -> bool:
    text = str(value or "").lower()
    return any(marker in text for marker in BLIND_SENSITIVE_MARKERS)


def redact_blind_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if contains_blind_sensitive_text(key):
                continue
            if isinstance(item, str) and contains_blind_sensitive_text(item):
                continue
            redacted = redact_blind_sensitive_payload(item)
            result[key] = redacted
        return result
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            if isinstance(item, str) and contains_blind_sensitive_text(item):
                continue
            result.append(redact_blind_sensitive_payload(item))
        return result
    return value


def build_pending_public_summary(summary: dict[str, Any]) -> dict[str, Any]:
    design = summary.get("design") if isinstance(summary.get("design"), dict) else {}
    fairness = summary.get("fairness_invariants") if isinstance(summary.get("fairness_invariants"), dict) else {}
    public_calls = [
        {
            "game": item.get("game"),
            "variant_id": item.get("variant_id"),
            "repeat": item.get("repeat"),
            "status": item.get("status"),
            "output_dir": item.get("output_dir"),
            "attempt_count": item.get("attempt_count"),
        }
        for item in summary.get("calls") or []
        if isinstance(item, dict)
    ]
    public_metrics = []
    allowed_metric_keys = {
        "variant_id",
        "completed_calls",
        "expected_calls",
        "candidate_gate_pass_rate",
        "average_claimed_added_count",
        "average_admitted_added_count",
        "minimum_primary_top_blocker_retention",
        "average_field_completeness",
        "average_admitted_field_completeness",
        "phase3_protocol_gate_pass_rate",
        "phase3_baseline_lock_pass_rate",
        "average_phase3_challenge_accepted_count",
        "average_phase3_correction_accepted_count",
        "average_phase3_correction_abstained_count",
        "phase3_target_coverage_ledger_complete_rate",
        "phase3_target_coverage_ledger_valid_rate",
        "phase3_challenge_checks_complete_rate",
        "phase3_challenge_checks_valid_rate",
    }
    for item in summary.get("variant_metrics") or []:
        if isinstance(item, dict):
            public_metrics.append({key: item.get(key) for key in allowed_metric_keys if key in item})
    public_stability = []
    allowed_stability_keys = {
        "variant_id",
        "game",
        "completed_repeats",
        "expected_repeats",
        "added_root_overlap",
        "high_added_root_overlap",
        "severity_consistency",
        "top_blocker_overlap",
        "candidate_adoption_consistent",
        "phase3_challenge_overlap",
        "phase3_correction_overlap",
        "phase3_target_decision_overlap",
        "phase3_challenge_target_overlap",
        "phase3_challenge_check_overlap",
    }
    for item in summary.get("stability_comparison") or []:
        if isinstance(item, dict):
            public_stability.append({key: item.get(key) for key in allowed_stability_keys if key in item})
    return {
        "schema_version": summary.get("schema_version", 1),
        "benchmark_type": summary.get("benchmark_type"),
        "created_at": summary.get("created_at"),
        "source": summary.get("source"),
        "blinding": {
            "public_outputs_use_variant_ids_only": True,
            "provider_mapping_path": "_private/provider_mapping.json",
            "internal_summary_path": PRIVATE_SUMMARY_RELATIVE_PATH.as_posix(),
            "annotation_status": "pending_human_review",
        },
        "design": {
            key: design.get(key)
            for key in (
                "game_count",
                "secondary_variant_count",
                "repeats_per_variant_per_game",
                "expected_secondary_calls",
                "primary_calls",
                "vision_calls",
                "temperature",
            )
        },
        "completion": summary.get("completion") or {},
        "fairness_invariants": {
            "passed": fairness.get("passed"),
            "only_intended_variable_varies": fairness.get("only_intended_variable_varies"),
            "primary_calls_observed": fairness.get("primary_calls_observed", 0),
            "vision_calls_observed": fairness.get("vision_calls_observed", 0),
        },
        "variant_metrics": public_metrics,
        "stability_comparison": public_stability,
        "human_metrics": {"status": "pending_human_annotation"},
        "calls": public_calls,
    }


def build_pending_public_annotation(items: list[dict[str, Any]]) -> dict[str, Any]:
    public_fields = (
        "annotation_id",
        "variant_id",
        "game",
        "repeat",
        "change_type",
        "candidate_issue_id",
        "target_issue_id",
        "challenge_id",
        "correction_id",
        "challenge_type",
        "recommended_action",
        "correction_type",
        "correction_disposition",
        "source_provenance",
        "residual_issue",
        "title",
        "current_state",
        "evidence",
        "risk",
        "suggestion",
        "severity",
        "blocking",
        "confidence",
        "proposed_split",
        "before",
        "after_preview",
        "applied_to_report",
        "reviewer_notes",
        *ALL_ANNOTATION_FIELDS,
    )
    return {
        "schema_version": 2,
        "status": "pending_human_review",
        "instructions": "Annotate Variant A/B only. Internal profile and admission data remain private until finalization.",
        "label_definitions": {
            "valid": "事实和风险成立",
            "duplicate": "与冻结 Primary 的问题重复",
            "unsupported": "证据不足",
            "overstated": "严重度过高",
            "understated": "严重度过低",
            "multiroot": "包含多个独立根因",
            "actionable": "责任人与修改建议可直接执行",
            "target_correct": "challenge/correct 是否指向正确的 Primary finding",
            "evidence_locatable": "证据是否能在冻结输入中准确定位",
            "should_split": "该问题是否确实应该拆成多个独立 finding",
            "accurate": "影子修正是否比原表述更准确",
            "supported": "影子修正是否有冻结输入证据支持",
            "safe_to_apply": "人工确认后是否可安全应用；当前工具仍不会自动应用",
        },
        "items": [
            {key: item.get(key) for key in public_fields if key in item}
            for item in items
            if isinstance(item, dict)
        ],
    }


@dataclass(frozen=True)
class SecondaryProvider:
    requested_name: str
    variant_id: str
    env_prefix: str
    config: ModelConfig
    protocol_profile: str = "baseline"


@dataclass(frozen=True)
class FrozenGame:
    name: str
    source_dir: Path
    documents: list[ParsedDocument]
    shared_input: dict[str, Any]
    primary_messages: list[dict[str, Any]]
    primary_raw: str
    primary_report: dict[str, Any]
    primary_model: str
    hashes: dict[str, str]


@dataclass(frozen=True)
class SecondaryBenchmarkResult:
    run_dir: Path
    summary_json_path: Path
    summary_markdown_path: Path
    annotation_json_path: Path
    expected_calls: int
    completed_calls: int
    failed_calls: int

    @property
    def is_complete(self) -> bool:
        return self.failed_calls == 0 and self.completed_calls == self.expected_calls


@dataclass(frozen=True)
class AnnotationFinalizeResult:
    benchmark_dir: Path
    results_path: Path
    summary_path: Path
    annotated_item_count: int


def run_secondary_benchmark(
    source: Path,
    output_dir: Path,
    provider_names: list[str],
    repeats: int = 2,
    timeout: int = 600,
    model_retries: int = 3,
    protocol_profiles: list[str] | None = None,
) -> SecondaryBenchmarkResult:
    if repeats < 2:
        raise ValueError("--secondary-repeats must be at least 2 for a stability comparison.")
    providers, comparison_axis = resolve_secondary_variants(provider_names, protocol_profiles)

    source = source.resolve()
    output_dir = output_dir.resolve()
    source_games = discover_frozen_game_dirs(source)
    secrets.SystemRandom().shuffle(providers)
    providers = [
        SecondaryProvider(
            requested_name=provider.requested_name,
            variant_id=chr(ord("A") + index),
            env_prefix=provider.env_prefix,
            config=provider.config,
            protocol_profile=provider.protocol_profile,
        )
        for index, provider in enumerate(providers)
    ]
    run_dir = create_benchmark_run_dir(output_dir)
    (run_dir / "_private").mkdir(parents=True, exist_ok=True)
    logger = RunLogger(run_dir / "run.log", echo=None)

    frozen_games: list[FrozenGame] = []
    for source_game in source_games:
        frozen_games.append(freeze_game(source_game, run_dir))

    provider_mapping = {
        "warning": "This file unblinds variants. Keep it separate while human annotation is in progress.",
        "variants": [
            {
                "variant_id": provider.variant_id,
                "requested_provider": provider.requested_name,
                "env_prefix": provider.env_prefix,
                "model": provider.config.text_model,
                "wire_api": provider.config.wire_api,
                "base_url": provider.config.base_url,
                "protocol_profile": provider.protocol_profile,
                "provider_config_hash": provider_config_hash(provider.config),
            }
            for provider in providers
        ],
    }
    write_json(run_dir / "_private" / "provider_mapping.json", provider_mapping)

    expected_calls = len(frozen_games) * len(providers) * repeats
    call_results: list[dict[str, Any]] = []
    annotation_items: list[dict[str, Any]] = []
    for game in frozen_games:
        for provider in providers:
            messages = build_dual_pass_secondary_messages(
                game.shared_input,
                game.primary_report,
                protocol_profile=provider.protocol_profile,
            )
            message_hash = hash_json(messages)
            client = OpenAICompatibleClient(provider.config, timeout=timeout, event_logger=logger.info)
            for repeat_index in range(1, repeats + 1):
                result = run_one_replay(
                    run_dir=run_dir,
                    game=game,
                    provider=provider,
                    repeat_index=repeat_index,
                    messages=messages,
                    message_hash=message_hash,
                    client=client,
                    model_retries=model_retries,
                    logger=logger,
                )
                call_results.append(result)
                annotation_items.extend(result.pop("annotation_items", []))

    completed_calls = sum(item.get("status") == "completed" for item in call_results)
    failed_calls = expected_calls - completed_calls
    paired_comparison_complete = completed_calls == expected_calls
    invariant = build_invariant_summary(frozen_games, call_results, comparison_axis=comparison_axis)
    stability = build_stability_summary(call_results, repeats)
    variant_metrics = build_variant_metrics(call_results, providers)
    summary = {
        "schema_version": 1,
        "benchmark_type": "frozen_primary_secondary_ab",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": str(source),
        "blinding": {
            "public_outputs_use_variant_ids_only": True,
            "provider_mapping_path": "_private/provider_mapping.json",
            "annotation_status": "pending_human_review",
        },
        "design": {
            "game_count": len(frozen_games),
            "secondary_variant_count": len(providers),
            "repeats_per_variant_per_game": repeats,
            "expected_secondary_calls": expected_calls,
            "primary_calls": 0,
            "vision_calls": 0,
            "temperature": 0,
            "comparison_axis": comparison_axis,
        },
        "completion": {
            "completed_secondary_calls": completed_calls,
            "failed_secondary_calls": failed_calls,
            "all_calls_paired": paired_comparison_complete,
        },
        "fairness_invariants": invariant,
        "variant_metrics": variant_metrics,
        "stability_comparison": stability,
        "human_metrics": {
            "status": "pending_human_annotation",
            "valid_added_finding_count": None,
            "added_finding_precision": None,
            "high_value_added_count": None,
            "duplicate_add_rate": None,
        },
        "calls": call_results,
    }
    summary["phase2_acceptance"] = build_phase2_acceptance_summary(summary)
    summary["phase3_acceptance"] = build_phase3_acceptance_summary(summary)
    summary_json_path = run_dir / "secondary_benchmark_summary.json"
    summary_markdown_path = run_dir / "secondary_benchmark_summary.md"
    annotation_json_path = run_dir / "human_annotation_template.json"
    internal_manifest = {
        "schema_version": 2,
        "source": str(source),
        "games": [game.name for game in frozen_games],
        "variants": [provider.variant_id for provider in providers],
        "comparison_axis": comparison_axis,
        "protocol_profiles": sorted({provider.protocol_profile for provider in providers}),
        "provider_config_hashes": sorted({provider_config_hash(provider.config) for provider in providers}),
        "prompt_hashes_by_variant": {
            provider.variant_id: sorted(
                {
                    str(item.get("secondary_message_hash") or "")
                    for item in call_results
                    if item.get("variant_id") == provider.variant_id
                }
            )
            for provider in providers
        },
        "repeats": repeats,
        "expected_secondary_calls": expected_calls,
        "primary_calls": 0,
        "vision_calls": 0,
        "summary": summary_json_path.name,
        "annotation_template": annotation_json_path.name,
        "provider_mapping": "_private/provider_mapping.json",
    }
    public_summary = build_pending_public_summary(summary)
    public_annotation = build_pending_public_annotation(annotation_items)
    write_json(run_dir / PRIVATE_SUMMARY_RELATIVE_PATH, summary)
    write_json(run_dir / PRIVATE_MANIFEST_RELATIVE_PATH, internal_manifest)
    write_json(
        run_dir / PRIVATE_ANNOTATION_RELATIVE_PATH,
        {
            "schema_version": 2,
            "status": "pending_human_review",
            "items": annotation_items,
        },
    )
    write_json(summary_json_path, public_summary)
    summary_markdown_path.write_text(render_blinded_benchmark_markdown(public_summary), encoding="utf-8")
    write_json(annotation_json_path, public_annotation)
    write_json(
        run_dir / "benchmark_manifest.json",
        {
            "schema_version": 2,
            "source": str(source),
            "games": [game.name for game in frozen_games],
            "variants": [provider.variant_id for provider in providers],
            "repeats": repeats,
            "expected_secondary_calls": expected_calls,
            "primary_calls": 0,
            "vision_calls": 0,
            "summary": summary_json_path.name,
            "annotation_template": annotation_json_path.name,
            "internal_manifest": PRIVATE_MANIFEST_RELATIVE_PATH.as_posix(),
            "provider_mapping": "_private/provider_mapping.json",
        },
    )
    return SecondaryBenchmarkResult(
        run_dir=run_dir,
        summary_json_path=summary_json_path,
        summary_markdown_path=summary_markdown_path,
        annotation_json_path=annotation_json_path,
        expected_calls=expected_calls,
        completed_calls=completed_calls,
        failed_calls=failed_calls,
    )


def materialize_phase3_v12_human_approved_reports(
    benchmark_dir: Path,
    summary: dict[str, Any],
    annotation_items: list[dict[str, Any]],
) -> dict[str, Any]:
    calls = [item for item in summary.get("calls") or [] if isinstance(item, dict)]
    call_index = {
        (str(item.get("variant_id") or ""), str(item.get("game") or ""), safe_int(item.get("repeat"))): item
        for item in calls
        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
        in {PHASE3_V12_PROTOCOL_REVISION, PHASE3_V13_PROTOCOL_REVISION}
        and item.get("status") == "completed"
    }
    grouped_items: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for item in annotation_items:
        key = (
            str(item.get("variant_id") or ""),
            str(item.get("game") or ""),
            safe_int(item.get("repeat")),
        )
        if key not in call_index or item.get("change_type") != "correction":
            continue
        if all(item.get(field) is True for field in PHASE3_CORRECTION_ANNOTATION_FIELDS):
            grouped_items.setdefault(key, []).append(item)

    outputs: list[dict[str, Any]] = []
    for key, approved_items in sorted(grouped_items.items()):
        call = call_index[key]
        artifacts = benchmark_dir / str(call.get("private_output_dir") or "") / "model_artifacts"
        public_dir = benchmark_dir / str(call.get("output_dir") or "")
        report_payload = read_json(artifacts / "review_report.json")
        primary_report = report_payload.get("report") if isinstance(report_payload.get("report"), dict) else report_payload
        correction_shadow = read_json(artifacts / "secondary_correction_shadow.json")
        accepted_by_id = {
            str(item.get("correction_id") or ""): item
            for item in correction_shadow.get("accepted_corrections") or []
            if isinstance(item, dict) and str(item.get("correction_id") or "")
        }
        corrections = [
            accepted_by_id[str(item.get("correction_id") or "")]
            for item in approved_items
            if str(item.get("correction_id") or "") in accepted_by_id
        ]
        if not corrections:
            continue
        protocol_revision = str(
            call.get("processing_profile") or call.get("protocol_profile") or PHASE3_V12_PROTOCOL_REVISION
        ).strip().lower()
        revised_report, apply_summary = apply_human_approved_phase3_corrections(
            primary_report,
            corrections,
            protocol_revision=protocol_revision,
        )
        frozen_game = load_frozen_game(benchmark_dir, key[1])
        write_report_files(
            revised_report,
            frozen_game.documents,
            artifacts / "review_report_human_approved.md",
            artifacts / "review_report_human_approved.json",
        )
        write_json(artifacts / "phase3_human_apply_summary.json", apply_summary)
        public_report = redact_blind_sensitive_payload(revised_report)
        write_report_files(
            public_report,
            frozen_game.documents,
            public_dir / "review_report_human_approved.md",
            public_dir / "review_report_human_approved.json",
        )
        write_json(public_dir / "phase3_human_apply_summary.json", redact_blind_sensitive_payload(apply_summary))
        applied_ids = {
            str(item.get("correction_id") or "")
            for item in apply_summary.get("applied_corrections") or []
            if isinstance(item, dict)
        }
        for item in approved_items:
            if str(item.get("correction_id") or "") in applied_ids:
                item["applied_to_report"] = True
                item["applied_report_path"] = (
                    Path(str(call.get("output_dir") or "")) / "review_report_human_approved.json"
                ).as_posix()
        score = apply_summary.get("score_recalculation") or {}
        outputs.append(
            {
                "variant_id": key[0],
                "game": key[1],
                "repeat": key[2],
                "applied_correction_count": apply_summary.get("applied_correction_count", 0),
                "score_before": score.get("score_before"),
                "score_after": score.get("score_after"),
                "score_changed": bool(score.get("score_changed")),
                "high_risk_before": (score.get("risk_counts_before") or {}).get("high_or_block_dev_count"),
                "high_risk_after": (score.get("risk_counts_after") or {}).get("high_or_block_dev_count"),
                "private_report": (
                    Path(str(call.get("private_output_dir") or ""))
                    / "model_artifacts"
                    / "review_report_human_approved.json"
                ).as_posix(),
                "public_report": (
                    Path(str(call.get("output_dir") or "")) / "review_report_human_approved.json"
                ).as_posix(),
            }
        )
    return {
        "applicable": bool(call_index),
        "mode": (
            "human_approved_deterministic_phase3_v1_3"
            if any(
                str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                == PHASE3_V13_PROTOCOL_REVISION
                for item in call_index.values()
            )
            else "human_approved_deterministic_phase3_v1_2"
        ),
        "output_count": len(outputs),
        "applied_correction_count": sum(safe_int(item.get("applied_correction_count")) for item in outputs),
        "score_change_count": sum(bool(item.get("score_changed")) for item in outputs),
        "outputs": outputs,
    }


def finalize_secondary_benchmark_annotations(benchmark_dir: Path) -> AnnotationFinalizeResult:
    benchmark_dir = benchmark_dir.resolve()
    summary_path = benchmark_dir / "secondary_benchmark_summary.json"
    template_path = benchmark_dir / "human_annotation_template.json"
    if not summary_path.is_file() or not template_path.is_file():
        raise FileNotFoundError(
            "Benchmark finalization requires secondary_benchmark_summary.json and human_annotation_template.json."
        )
    internal_summary_path = benchmark_dir / PRIVATE_SUMMARY_RELATIVE_PATH
    internal_annotation_path = benchmark_dir / PRIVATE_ANNOTATION_RELATIVE_PATH
    summary = read_json(internal_summary_path) if internal_summary_path.is_file() else read_json(summary_path)
    template = read_json(template_path)
    completion = summary.get("completion") if isinstance(summary.get("completion"), dict) else {}
    fairness = (
        summary.get("fairness_invariants") if isinstance(summary.get("fairness_invariants"), dict) else {}
    )
    if completion.get("all_calls_paired") is not True:
        completed = safe_int(completion.get("completed_secondary_calls"))
        expected = safe_int((summary.get("design") or {}).get("expected_secondary_calls"))
        raise ValueError(
            f"Cannot finalize human annotation before all Secondary calls are paired: {completed}/{expected}."
        )
    intended_variable_only = fairness.get("only_intended_variable_varies")
    if intended_variable_only is None:
        intended_variable_only = fairness.get("only_secondary_provider_varies")
    if fairness.get("passed") is not True or intended_variable_only is not True:
        raise ValueError("Cannot finalize human annotation because fairness invariants did not pass.")
    public_items = [dict(item) for item in (template.get("items") or []) if isinstance(item, dict)]
    public_items_by_id = {
        str(item.get("annotation_id") or "").strip(): item
        for item in public_items
        if str(item.get("annotation_id") or "").strip()
    }
    internal_template = read_json(internal_annotation_path) if internal_annotation_path.is_file() else template
    items = [dict(item) for item in (internal_template.get("items") or []) if isinstance(item, dict)]
    for item in items:
        public_item = public_items_by_id.get(str(item.get("annotation_id") or "").strip())
        if public_item is None:
            continue
        for field in annotation_fields_for_item(item):
            item[field] = public_item.get(field)
        item["reviewer_notes"] = str(public_item.get("reviewer_notes") or item.get("reviewer_notes") or "")
    decisions_path = benchmark_dir / "human_annotation_decisions.json"
    if decisions_path.is_file():
        decisions_payload = read_json(decisions_path)
        decisions: dict[str, dict[str, Any]] = {}
        duplicate_decision_ids: list[str] = []
        for decision in decisions_payload.get("items") or []:
            if not isinstance(decision, dict):
                continue
            annotation_id = str(decision.get("annotation_id") or "").strip()
            if not annotation_id:
                continue
            if annotation_id in decisions:
                duplicate_decision_ids.append(annotation_id)
            decisions[annotation_id] = decision
        if duplicate_decision_ids:
            raise ValueError(
                "Duplicate annotation decisions: " + ", ".join(sorted(set(duplicate_decision_ids)))
            )
        template_ids = {str(item.get("annotation_id") or "").strip() for item in items}
        unknown_ids = sorted(set(decisions) - template_ids)
        if unknown_ids:
            raise ValueError("Unknown annotation decision ids: " + ", ".join(unknown_ids))
        for item in items:
            annotation_id = str(item.get("annotation_id") or "").strip()
            decision = decisions.get(annotation_id)
            if decision is None:
                continue
            for field in annotation_fields_for_item(item):
                item[field] = decision.get(field)
            item["reviewer_notes"] = str(decision.get("reviewer_notes") or item.get("reviewer_notes") or "")
    incomplete: list[str] = []
    for item in items:
        missing = [
            field
            for field in annotation_fields_for_item(item)
            if not isinstance(item.get(field), bool)
        ]
        if missing:
            incomplete.append(f"{item.get('annotation_id') or '<unknown>'}: {', '.join(missing)}")
    if incomplete:
        preview = "; ".join(incomplete[:10])
        if len(incomplete) > 10:
            preview += f"; ... and {len(incomplete) - 10} more"
        raise ValueError(f"Human annotation is incomplete: {preview}")

    variants = sorted({str(item.get("variant_id") or "") for item in items if str(item.get("variant_id") or "")})
    variant_results: list[dict[str, Any]] = []
    for variant_id in variants:
        variant_items = [item for item in items if item.get("variant_id") == variant_id]
        added_variant_items = [
            item for item in variant_items if str(item.get("change_type") or "added") == "added"
        ]
        challenge_items = [item for item in variant_items if item.get("change_type") == "challenge"]
        correction_items = [item for item in variant_items if item.get("change_type") == "correction"]
        total = len(added_variant_items)
        valid_items = [
            item
            for item in added_variant_items
            if item.get("valid") is True and item.get("duplicate") is False and item.get("unsupported") is False
        ]
        high_value_items = [item for item in valid_items if is_high_finding(item)]
        admitted_items = [item for item in added_variant_items if item.get("added_admission_status") == "admitted"]
        admitted_valid_items = [
            item
            for item in admitted_items
            if item.get("valid") is True and item.get("duplicate") is False and item.get("unsupported") is False
        ]
        admitted_high_value_items = [item for item in admitted_valid_items if is_high_finding(item)]
        variant_results.append(
            {
                "variant_id": variant_id,
                "annotated_added_finding_count": total,
                "valid_added_finding_count": len(valid_items),
                "added_finding_precision": ratio(len(valid_items), total),
                "high_value_added_count": len(high_value_items),
                "duplicate_add_rate": ratio(sum(item.get("duplicate") is True for item in added_variant_items), total),
                "unsupported_count": sum(item.get("unsupported") is True for item in added_variant_items),
                "overstated_count": sum(item.get("overstated") is True for item in added_variant_items),
                "understated_count": sum(item.get("understated") is True for item in added_variant_items),
                "multiroot_count": sum(item.get("multiroot") is True for item in added_variant_items),
                "actionable_rate": ratio(sum(item.get("actionable") is True for item in added_variant_items), total),
                "admitted_added_finding_count": len(admitted_items),
                "admitted_valid_added_finding_count": len(admitted_valid_items),
                "admitted_added_finding_precision": ratio(len(admitted_valid_items), len(admitted_items)),
                "admitted_high_value_added_count": len(admitted_high_value_items),
                "admitted_duplicate_count": sum(item.get("duplicate") is True for item in admitted_items),
                "admitted_duplicate_add_rate": ratio(
                    sum(item.get("duplicate") is True for item in admitted_items), len(admitted_items)
                ),
                "admitted_unsupported_count": sum(item.get("unsupported") is True for item in admitted_items),
                "admitted_overstated_count": sum(item.get("overstated") is True for item in admitted_items),
                "admitted_multiroot_count": sum(item.get("multiroot") is True for item in admitted_items),
                "valid_recall_after_admission": ratio(len(admitted_valid_items), len(valid_items)),
                "high_value_recall_after_admission": ratio(
                    len(admitted_high_value_items), len(high_value_items)
                ),
                "phase3_challenge_count": len(challenge_items),
                "phase3_valid_challenge_count": sum(
                    item.get("target_correct") is True
                    and item.get("valid") is True
                    and item.get("evidence_locatable") is True
                    for item in challenge_items
                ),
                "phase3_challenge_precision": ratio(
                    sum(
                        item.get("target_correct") is True
                        and item.get("valid") is True
                        and item.get("evidence_locatable") is True
                        for item in challenge_items
                    ),
                    len(challenge_items),
                ),
                "phase3_challenge_actionable_rate": ratio(
                    sum(item.get("actionable") is True for item in challenge_items),
                    len(challenge_items),
                ),
                "phase3_should_split_count": sum(
                    item.get("should_split") is True for item in challenge_items
                ),
                "phase3_correction_count": len(correction_items),
                "phase3_safe_correction_count": sum(
                    item.get("target_correct") is True
                    and item.get("accurate") is True
                    and item.get("supported") is True
                    and item.get("safe_to_apply") is True
                    for item in correction_items
                ),
                "phase3_safe_to_apply_rate": ratio(
                    sum(
                        item.get("target_correct") is True
                        and item.get("accurate") is True
                        and item.get("supported") is True
                        and item.get("safe_to_apply") is True
                        for item in correction_items
                    ),
                    len(correction_items),
                ),
            }
        )
    added_items = [item for item in items if str(item.get("change_type") or "added") == "added"]
    challenge_items = [item for item in items if item.get("change_type") == "challenge"]
    correction_items = [item for item in items if item.get("change_type") == "correction"]
    aggregate_total = len(items)
    aggregate_valid = sum(
        item.get("valid") is True and item.get("duplicate") is False and item.get("unsupported") is False
        for item in added_items
    )
    aggregate_admitted_items = [item for item in added_items if item.get("added_admission_status") == "admitted"]
    aggregate_admitted_valid = [
        item
        for item in aggregate_admitted_items
        if item.get("valid") is True and item.get("duplicate") is False and item.get("unsupported") is False
    ]
    human_metrics = {
        "status": "completed",
        "annotated_item_count": aggregate_total,
        "valid_added_finding_count": aggregate_valid,
        "added_finding_precision": ratio(aggregate_valid, len(added_items)),
        "high_value_added_count": sum(
            item.get("valid") is True
            and item.get("duplicate") is False
            and item.get("unsupported") is False
            and is_high_finding(item)
            for item in added_items
        ),
        "duplicate_add_rate": ratio(sum(item.get("duplicate") is True for item in added_items), len(added_items)),
        "admitted_added_finding_count": len(aggregate_admitted_items),
        "admitted_valid_added_finding_count": len(aggregate_admitted_valid),
        "admitted_added_finding_precision": ratio(len(aggregate_admitted_valid), len(aggregate_admitted_items)),
        "admitted_high_value_added_count": sum(is_high_finding(item) for item in aggregate_admitted_valid),
        "admitted_duplicate_count": sum(item.get("duplicate") is True for item in aggregate_admitted_items),
        "admitted_duplicate_add_rate": ratio(
            sum(item.get("duplicate") is True for item in aggregate_admitted_items), len(aggregate_admitted_items)
        ),
        "admitted_unsupported_count": sum(item.get("unsupported") is True for item in aggregate_admitted_items),
        "admitted_overstated_count": sum(item.get("overstated") is True for item in aggregate_admitted_items),
        "admitted_multiroot_count": sum(item.get("multiroot") is True for item in aggregate_admitted_items),
        "valid_recall_after_admission": ratio(len(aggregate_admitted_valid), aggregate_valid),
        "phase3": {
            "challenge_count": len(challenge_items),
            "challenge_target_correct_rate": ratio(
                sum(item.get("target_correct") is True for item in challenge_items),
                len(challenge_items),
            ),
            "challenge_evidence_locatable_rate": ratio(
                sum(item.get("evidence_locatable") is True for item in challenge_items),
                len(challenge_items),
            ),
            "valid_challenge_count": sum(
                item.get("target_correct") is True
                and item.get("valid") is True
                and item.get("evidence_locatable") is True
                for item in challenge_items
            ),
            "challenge_precision": ratio(
                sum(
                    item.get("target_correct") is True
                    and item.get("valid") is True
                    and item.get("evidence_locatable") is True
                    for item in challenge_items
                ),
                len(challenge_items),
            ),
            "challenge_actionable_rate": ratio(
                sum(item.get("actionable") is True for item in challenge_items),
                len(challenge_items),
            ),
            "should_split_count": sum(item.get("should_split") is True for item in challenge_items),
            "correction_count": len(correction_items),
            "correction_target_correct_rate": ratio(
                sum(item.get("target_correct") is True for item in correction_items),
                len(correction_items),
            ),
            "correction_accuracy_rate": ratio(
                sum(item.get("accurate") is True for item in correction_items),
                len(correction_items),
            ),
            "correction_supported_rate": ratio(
                sum(item.get("supported") is True for item in correction_items),
                len(correction_items),
            ),
            "safe_correction_count": sum(
                item.get("target_correct") is True
                and item.get("accurate") is True
                and item.get("supported") is True
                and item.get("safe_to_apply") is True
                for item in correction_items
            ),
            "safe_to_apply_rate": ratio(
                sum(
                    item.get("target_correct") is True
                    and item.get("accurate") is True
                    and item.get("supported") is True
                    and item.get("safe_to_apply") is True
                    for item in correction_items
                ),
                len(correction_items),
            ),
        },
        "variants": variant_results,
    }
    phase3_human_application = materialize_phase3_v12_human_approved_reports(
        benchmark_dir,
        summary,
        items,
    )
    human_metrics["phase3"]["human_applied_correction_count"] = phase3_human_application.get(
        "applied_correction_count", 0
    )
    human_metrics["phase3"]["score_change_count"] = phase3_human_application.get("score_change_count", 0)
    results_payload = {
        "schema_version": 1,
        "status": "completed",
        "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "blinded": True,
        "decision_source": decisions_path.name if decisions_path.is_file() else template_path.name,
        "metrics": human_metrics,
        "phase3_human_application": phase3_human_application,
        "items": items,
    }
    results_path = benchmark_dir / "human_annotation_results.json"
    write_json(results_path, results_payload)
    summary["human_metrics"] = human_metrics
    summary["phase3_human_application"] = phase3_human_application
    summary["phase2_acceptance"] = build_phase2_acceptance_summary(summary)
    summary["phase3_acceptance"] = build_phase3_acceptance_summary(summary)
    if isinstance(summary.get("blinding"), dict):
        summary["blinding"]["annotation_status"] = "completed"
    write_json(internal_summary_path, summary)
    write_json(summary_path, summary)
    (benchmark_dir / "secondary_benchmark_summary.md").write_text(render_benchmark_markdown(summary), encoding="utf-8")
    return AnnotationFinalizeResult(
        benchmark_dir=benchmark_dir,
        results_path=results_path,
        summary_path=summary_path,
        annotated_item_count=aggregate_total,
    )


def reprocess_saved_secondary_responses(
    benchmark_dir: Path,
    processing_profile: str | None = None,
) -> SecondaryBenchmarkResult:
    source_benchmark_dir = benchmark_dir.resolve()
    benchmark_dir = create_reprocessed_benchmark_dir(source_benchmark_dir)
    summary_path = benchmark_dir / "secondary_benchmark_summary.json"
    mapping_path = benchmark_dir / "_private" / "provider_mapping.json"
    if not summary_path.is_file() or not mapping_path.is_file():
        raise FileNotFoundError(
            "Saved-response reprocessing requires secondary_benchmark_summary.json and _private/provider_mapping.json."
        )
    internal_summary_path = benchmark_dir / PRIVATE_SUMMARY_RELATIVE_PATH
    summary = read_json(internal_summary_path) if internal_summary_path.is_file() else read_json(summary_path)
    call_results = [item for item in (summary.get("calls") or []) if isinstance(item, dict)]
    games = {
        game_name: load_frozen_game(benchmark_dir, game_name)
        for game_name in sorted({str(item.get("game") or "") for item in call_results if str(item.get("game") or "")})
    }
    providers = load_blinded_providers(mapping_path)
    logger = RunLogger(benchmark_dir / "run.log", echo=None)
    replacements: dict[tuple[str, str, int], dict[str, Any]] = {}
    replacement_annotations: list[dict[str, Any]] = []
    for saved_call in call_results:
        game_name = str(saved_call.get("game") or "")
        variant_id = str(saved_call.get("variant_id") or "")
        repeat_index = safe_int(saved_call.get("repeat"))
        game = games.get(game_name)
        provider = providers.get(variant_id)
        if game is None or provider is None or repeat_index < 1:
            continue
        private_output_dir = str(saved_call.get("private_output_dir") or "").strip()
        raw_path = (
            benchmark_dir / private_output_dir / "model_artifacts" / "secondary_raw_model_response.txt"
            if private_output_dir
            else benchmark_dir
            / "blinded"
            / variant_id
            / game_name
            / f"repeat_{repeat_index:02d}"
            / "model_artifacts"
            / "secondary_raw_model_response.txt"
        )
        if not raw_path.is_file():
            continue
        messages_path = raw_path.parent / "secondary_review_messages.json"
        saved_messages = read_json(messages_path) if messages_path.is_file() else None
        if not isinstance(saved_messages, list) or not saved_messages:
            raise FileNotFoundError(
                "Saved-response reprocessing requires the original secondary_review_messages.json: "
                f"{messages_path}"
            )
        messages = [item for item in saved_messages if isinstance(item, dict)]
        if len(messages) != len(saved_messages):
            raise ValueError(f"Invalid saved Secondary messages: {messages_path}")
        packet_path = raw_path.parent / "phase2_control_evidence_packet.json"
        saved_evidence_packet = read_json(packet_path) if packet_path.is_file() else None
        client = OpenAICompatibleClient(provider.config, timeout=1, event_logger=logger.info)
        result = run_one_replay(
            run_dir=benchmark_dir,
            game=game,
            provider=provider,
            repeat_index=repeat_index,
            messages=messages,
            message_hash=hash_json(messages),
            client=client,
            model_retries=0,
            logger=logger,
            secondary_raw_override=raw_path.read_text(encoding="utf-8"),
            processing_profile=processing_profile,
            phase2_evidence_packet_override=(
                saved_evidence_packet if isinstance(saved_evidence_packet, dict) else None
            ),
        )
        replacement_annotations.extend(result.pop("annotation_items", []))
        replacements[(game_name, variant_id, repeat_index)] = result

    updated_calls: list[dict[str, Any]] = []
    for item in call_results:
        key = (str(item.get("game") or ""), str(item.get("variant_id") or ""), safe_int(item.get("repeat")))
        updated_calls.append(replacements.get(key, item))
    completed_count = sum(item.get("status") == "completed" for item in updated_calls)
    expected_calls = safe_int((summary.get("design") or {}).get("expected_secondary_calls")) or len(updated_calls)
    failed_count = expected_calls - completed_count
    summary["completion"] = {
        "completed_secondary_calls": completed_count,
        "failed_secondary_calls": failed_count,
        "all_calls_paired": completed_count == expected_calls,
    }
    comparison_axis = str((summary.get("design") or {}).get("comparison_axis") or "provider")
    summary["fairness_invariants"] = build_invariant_summary(
        list(games.values()), updated_calls, comparison_axis=comparison_axis
    )
    if processing_profile:
        summary.setdefault("design", {})["reprocessed_with_profile"] = normalize_secondary_protocol_profile(
            processing_profile
        )
    repeats = safe_int((summary.get("design") or {}).get("repeats_per_variant_per_game")) or 2
    summary["variant_metrics"] = build_variant_metrics(updated_calls, list(providers.values()))
    summary["stability_comparison"] = build_stability_summary(updated_calls, repeats)
    summary["calls"] = updated_calls
    summary["human_metrics"] = {
        "status": "pending_human_annotation",
        "valid_added_finding_count": None,
        "added_finding_precision": None,
        "high_value_added_count": None,
        "duplicate_add_rate": None,
    }
    summary["phase2_acceptance"] = build_phase2_acceptance_summary(summary)
    summary["phase3_acceptance"] = build_phase3_acceptance_summary(summary)
    if isinstance(summary.get("blinding"), dict):
        summary["blinding"]["annotation_status"] = "pending_human_review"
    write_json(internal_summary_path, summary)
    public_summary = build_pending_public_summary(summary)
    write_json(summary_path, public_summary)
    summary_markdown_path = benchmark_dir / "secondary_benchmark_summary.md"
    summary_markdown_path.write_text(render_blinded_benchmark_markdown(public_summary), encoding="utf-8")

    annotation_path = benchmark_dir / "human_annotation_template.json"
    internal_annotation_path = benchmark_dir / PRIVATE_ANNOTATION_RELATIVE_PATH
    annotation_payload = read_json(internal_annotation_path) if internal_annotation_path.is_file() else (
        read_json(annotation_path) if annotation_path.is_file() else {"items": []}
    )
    replaced_keys = set(replacements)
    preserved_annotations = [
        item
        for item in (annotation_payload.get("items") or [])
        if isinstance(item, dict)
        and (str(item.get("game") or ""), str(item.get("variant_id") or ""), safe_int(item.get("repeat")))
        not in replaced_keys
    ]
    annotation_payload["status"] = "pending_human_review"
    annotation_payload["items"] = preserved_annotations + replacement_annotations
    write_json(internal_annotation_path, annotation_payload)
    write_json(annotation_path, build_pending_public_annotation(annotation_payload["items"]))
    internal_reprocess_manifest = {
        "source_benchmark_dir": str(source_benchmark_dir),
        "derived_benchmark_dir": str(benchmark_dir),
        "processing_profile": normalize_secondary_protocol_profile(processing_profile)
        if processing_profile
        else None,
        "model_calls": 0,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    write_json(benchmark_dir / "_private" / "reprocess_manifest_internal.json", internal_reprocess_manifest)
    write_json(
        benchmark_dir / "reprocess_manifest.json",
        {
            "source_benchmark_dir": str(source_benchmark_dir),
            "derived_benchmark_dir": str(benchmark_dir),
            "model_calls": 0,
            "created_at": internal_reprocess_manifest["created_at"],
            "internal_manifest": "_private/reprocess_manifest_internal.json",
        },
    )
    return SecondaryBenchmarkResult(
        run_dir=benchmark_dir,
        summary_json_path=summary_path,
        summary_markdown_path=summary_markdown_path,
        annotation_json_path=annotation_path,
        expected_calls=expected_calls,
        completed_calls=completed_count,
        failed_calls=failed_count,
    )


def create_reprocessed_benchmark_dir(source_dir: Path) -> Path:
    """Copy a saved benchmark before rebuilding derived artifacts."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = source_dir.parent / f"{source_dir.name}_reprocessed_{timestamp}"
    suffix = 1
    while candidate.exists():
        candidate = source_dir.parent / f"{source_dir.name}_reprocessed_{timestamp}_{suffix:02d}"
        suffix += 1
    shutil.copytree(
        source_dir,
        candidate,
        ignore=shutil.ignore_patterns("human_annotation_results.json"),
    )
    return candidate


def discover_frozen_game_dirs(source: Path) -> list[Path]:
    if not source.exists():
        raise FileNotFoundError(f"Secondary replay source does not exist: {source}")
    if has_frozen_artifacts(source):
        return [source]
    candidates = [path for path in sorted(source.iterdir()) if path.is_dir() and has_frozen_artifacts(path)]
    if not candidates:
        raise FileNotFoundError(
            "No replayable dual_pass game directories found. Required model_artifacts: "
            + ", ".join(REQUIRED_FROZEN_ARTIFACTS)
        )
    return candidates


def has_frozen_artifacts(game_dir: Path) -> bool:
    artifacts = game_dir / "model_artifacts"
    return all((artifacts / name).is_file() for name in REQUIRED_FROZEN_ARTIFACTS)


def resolve_secondary_variants(
    provider_names: list[str],
    protocol_profiles: list[str] | None,
) -> tuple[list[SecondaryProvider], str]:
    profiles = [normalize_secondary_protocol_profile(value) for value in (protocol_profiles or [])]
    if profiles:
        normalized_providers = [str(name or "").strip().lower() for name in provider_names]
        if len(provider_names) != 1 or not normalized_providers[0]:
            raise ValueError("Protocol-profile benchmark requires exactly one --secondary-provider value.")
        if len(profiles) not in {1, 2} or len(set(profiles)) != len(profiles):
            raise ValueError(
                "Repeat --secondary-profile once or twice with distinct baseline/phase2/phase3_v1/phase3_v1_1/phase3_v1_2/phase3_v1_3 values."
            )
        variants = [resolve_secondary_provider(provider_names[0], index, profile) for index, profile in enumerate(profiles)]
        return variants, "protocol_profile" if len(profiles) == 2 else "single_profile"

    if len(provider_names) != 2 or len({name.strip().lower() for name in provider_names}) != 2:
        raise ValueError(
            "Provider benchmark requires exactly two distinct --secondary-provider values, or one provider with --secondary-profile."
        )
    return [resolve_secondary_provider(name, index, "baseline") for index, name in enumerate(provider_names)], "provider"


def resolve_secondary_provider(name: str, index: int, protocol_profile: str = "baseline") -> SecondaryProvider:
    requested = name.strip()
    if not requested:
        raise ValueError("--secondary-provider cannot be empty.")
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", requested).strip("_").upper()
    prefix = f"AI_PROVIDER_{normalized}"
    config = ModelConfig.from_prefixed_env(prefix)
    missing: list[str] = []
    if not config.base_url:
        missing.append(f"{prefix}_BASE_URL")
    if not config.api_key:
        missing.append(f"{prefix}_API_KEY")
    if not config.text_model:
        missing.append(f"{prefix}_MODEL")
    if missing:
        raise RuntimeError(
            f"Secondary provider '{requested}' is missing configuration: {', '.join(missing)}. "
            "Load env.local.ps1 or define the named provider variables first."
        )
    return SecondaryProvider(
        requested_name=requested,
        variant_id=chr(ord("A") + index),
        env_prefix=prefix,
        config=config,
        protocol_profile=normalize_secondary_protocol_profile(protocol_profile),
    )


def provider_config_hash(config: ModelConfig) -> str:
    return hash_json(
        {
            "base_url": config.base_url,
            "model": config.text_model,
            "wire_api": config.wire_api,
            "seed": config.seed,
        }
    )


def create_benchmark_run_dir(output_dir: Path) -> Path:
    root = output_dir / "secondary_benchmarks"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = root / timestamp
    suffix = 1
    while candidate.exists():
        candidate = root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def freeze_game(source_game: Path, run_dir: Path) -> FrozenGame:
    artifacts = source_game / "model_artifacts"
    shared_input = read_json(artifacts / "shared_review_input.json")
    primary_messages_raw = read_json(artifacts / "primary_review_messages.json")
    if not isinstance(primary_messages_raw, list):
        raise ValueError(f"Primary messages are not a JSON array: {source_game}")
    primary_messages = [item for item in primary_messages_raw if isinstance(item, dict)]
    primary_raw = (artifacts / "primary_raw_model_response.txt").read_text(encoding="utf-8")
    metadata = read_json(artifacts / "run_metadata.json")
    report_payload = read_source_report_payload(source_game)
    documents = reconstruct_documents(report_payload.get("documents") or [], shared_input)
    primary_report, parse_error = parse_model_json(primary_raw, documents)
    if parse_error:
        raise ValueError(f"Cannot freeze parsed Primary report for {source_game.name}: {parse_error}")
    primary_model = str(metadata.get("primary_text_model") or metadata.get("text_model") or "").strip()
    primary_report["review_mode"] = "dual_pass"
    primary_report["primary_model"] = primary_model
    primary_report["secondary_model"] = ""
    primary_report = demote_dual_pass_cross_document_issues(primary_report)
    hashes = {
        "shared_input_hash": hash_json(shared_input),
        "primary_raw_hash": hash_text(primary_raw),
        "primary_messages_hash": hash_json(primary_messages),
        "primary_report_hash": hash_json(primary_report),
    }

    game_name = sanitize_filename(source_game.name)
    frozen_dir = run_dir / "_private" / "frozen_inputs" / game_name
    frozen_artifacts = frozen_dir / "model_artifacts"
    frozen_artifacts.mkdir(parents=True, exist_ok=True)
    write_json(frozen_artifacts / "shared_review_input.json", shared_input)
    write_json(frozen_artifacts / "primary_review_messages.json", primary_messages)
    (frozen_artifacts / "primary_raw_model_response.txt").write_text(primary_raw, encoding="utf-8")
    write_json(frozen_artifacts / "frozen_primary_report.json", primary_report)
    write_json(
        frozen_dir / "freeze_manifest.json",
        {
            "source_game_dir": str(source_game.resolve()),
            "primary_model": primary_model,
            "document_names": [document.name for document in documents],
            "hashes": hashes,
            "primary_calls_during_freeze": 0,
            "vision_calls_during_freeze": 0,
        },
    )
    return FrozenGame(
        name=game_name,
        source_dir=source_game,
        documents=documents,
        shared_input=shared_input,
        primary_messages=primary_messages,
        primary_raw=primary_raw,
        primary_report=primary_report,
        primary_model=primary_model,
        hashes=hashes,
    )


def load_frozen_game(benchmark_dir: Path, game_name: str) -> FrozenGame:
    frozen_dir = benchmark_dir / "_private" / "frozen_inputs" / game_name
    if not frozen_dir.is_dir():
        frozen_dir = benchmark_dir / "frozen_inputs" / game_name
    artifacts = frozen_dir / "model_artifacts"
    manifest = read_json(frozen_dir / "freeze_manifest.json")
    shared_input = read_json(artifacts / "shared_review_input.json")
    primary_messages = read_json(artifacts / "primary_review_messages.json")
    primary_raw = (artifacts / "primary_raw_model_response.txt").read_text(encoding="utf-8")
    primary_report = read_json(artifacts / "frozen_primary_report.json")
    source_dir = Path(str(manifest.get("source_game_dir") or ""))
    source_payload = read_source_report_payload(source_dir) if source_dir.is_dir() else {}
    documents = reconstruct_documents(source_payload.get("documents") or [], shared_input)
    return FrozenGame(
        name=game_name,
        source_dir=source_dir,
        documents=documents,
        shared_input=shared_input,
        primary_messages=[item for item in primary_messages if isinstance(item, dict)],
        primary_raw=primary_raw,
        primary_report=primary_report,
        primary_model=str(manifest.get("primary_model") or ""),
        hashes={str(key): str(value) for key, value in (manifest.get("hashes") or {}).items()},
    )


def load_blinded_providers(mapping_path: Path) -> dict[str, SecondaryProvider]:
    mapping = read_json(mapping_path)
    providers: dict[str, SecondaryProvider] = {}
    for item in mapping.get("variants") or []:
        if not isinstance(item, dict):
            continue
        variant_id = str(item.get("variant_id") or "").strip()
        env_prefix = str(item.get("env_prefix") or "").strip()
        requested_name = str(item.get("requested_provider") or "").strip()
        if not variant_id or not env_prefix:
            continue
        providers[variant_id] = SecondaryProvider(
            requested_name=requested_name,
            variant_id=variant_id,
            env_prefix=env_prefix,
            config=ModelConfig.from_prefixed_env(env_prefix),
            protocol_profile=normalize_secondary_protocol_profile(item.get("protocol_profile") or "baseline"),
        )
    return providers


def read_source_report_payload(source_game: Path) -> dict[str, Any]:
    for filename in ("review_report_pipeline.json", "review_report.json"):
        path = source_game / filename
        if path.is_file():
            payload = read_json(path)
            if isinstance(payload, dict):
                return payload
    return {}


def reconstruct_documents(raw_documents: list[Any], shared_input: dict[str, Any]) -> list[ParsedDocument]:
    summaries = [item for item in raw_documents if isinstance(item, dict)]
    if not summaries:
        summaries = [
            {"name": str(name), "kind": "requirement"}
            for name in (shared_input.get("document_labels") or [])
            if str(name).strip()
        ]
    documents: list[ParsedDocument] = []
    for index, item in enumerate(summaries, start=1):
        name = str(item.get("name") or f"document_{index}.docx")
        paragraph_count = safe_int(item.get("paragraph_count"))
        table_count = safe_int(item.get("table_count"))
        image_count = safe_int(item.get("image_count"))
        documents.append(
            ParsedDocument(
                path=name,
                name=name,
                kind=str(item.get("kind") or "requirement"),
                paragraphs=[ParagraphBlock(index=value, text="") for value in range(1, paragraph_count + 1)],
                tables=[TableBlock(index=value, rows=[], markdown="") for value in range(1, table_count + 1)],
                images=[
                    ImageBlock(index=value, source_name="", extracted_path="")
                    for value in range(1, image_count + 1)
                ],
                errors=[str(value) for value in (item.get("errors") or [])],
            )
        )
    return documents


def build_phase3_annotation_items(
    *,
    game: FrozenGame,
    variant_id: str,
    repeat_index: int,
    challenge_advice: dict[str, Any],
    correction_shadow: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, challenge in enumerate(challenge_advice.get("accepted_challenges") or [], start=1):
        item = {
            "annotation_id": f"{variant_id}-{game.name}-R{repeat_index:02d}-CH{index:03d}",
            "variant_id": variant_id,
            "game": game.name,
            "repeat": repeat_index,
            "change_type": "challenge",
            "challenge_id": challenge.get("challenge_id") or "",
            "target_issue_id": challenge.get("target_issue_id") or "",
            "candidate_issue_id": challenge.get("target_issue_id") or "",
            "title": challenge.get("target_title") or challenge.get("target_issue_id") or "",
            "challenge_type": challenge.get("challenge_type") or "",
            "recommended_action": challenge.get("recommended_action") or "",
            "current_state": challenge.get("challenged_claim") or "",
            "evidence": challenge.get("evidence") or "",
            "risk": challenge.get("rationale") or "",
            "suggestion": (
                "拆分为："
                + "；".join(
                    str(split.get("title") or "")
                    for split in challenge.get("proposed_split") or []
                    if isinstance(split, dict) and str(split.get("title") or "").strip()
                )
                if challenge.get("recommended_action") == "split"
                else str(challenge.get("recommended_action") or "")
            ),
            "proposed_split": challenge.get("proposed_split") or [],
            "reviewer_notes": "",
        }
        for field in PHASE3_CHALLENGE_ANNOTATION_FIELDS:
            item[field] = None
        items.append(item)
    for index, correction in enumerate(correction_shadow.get("accepted_corrections") or [], start=1):
        item = {
            "annotation_id": f"{variant_id}-{game.name}-R{repeat_index:02d}-CR{index:03d}",
            "variant_id": variant_id,
            "game": game.name,
            "repeat": repeat_index,
            "change_type": "correction",
            "correction_id": correction.get("correction_id") or "",
            "challenge_id": correction.get("challenge_id") or "",
            "target_issue_id": correction.get("target_issue_id") or "",
            "candidate_issue_id": correction.get("target_issue_id") or "",
            "title": (correction.get("before") or {}).get("title") or correction.get("target_issue_id") or "",
            "correction_type": correction.get("correction_type") or "",
            "correction_disposition": correction.get("correction_disposition") or correction.get("correction_type") or "",
            "source_provenance": correction.get("source_provenance") or "",
            "residual_issue": correction.get("residual_issue") or "",
            "current_state": (correction.get("before") or {}).get("current_state") or "",
            "evidence": correction.get("evidence") or "",
            "risk": correction.get("rationale") or "",
            "suggestion": "仅保存影子修正预览，人工确认前不应用。",
            "before": correction.get("before") or {},
            "after_preview": correction.get("after_preview") or {},
            "applied_to_report": False,
            "reviewer_notes": "",
        }
        for field in PHASE3_CORRECTION_ANNOTATION_FIELDS:
            item[field] = None
        items.append(item)
    return items


def process_phase3_replay(
    *,
    game: FrozenGame,
    provider: SecondaryProvider,
    repeat_index: int,
    secondary_raw: str,
    artifacts: Path,
    replay_dir: Path,
    base_result: dict[str, Any],
    attempt_count: int,
    reprocessed_saved_raw: bool,
) -> dict[str, Any]:
    phase3_review, parse_error = parse_phase3_review_json(secondary_raw)
    if parse_error:
        raise ValueError(f"Secondary response is not valid phase3 JSON: {parse_error}")
    challenge_advice, correction_shadow, phase3_summary = evaluate_phase3_review(
        game.primary_report,
        phase3_review,
        document_labels=[document.name for document in game.documents],
        protocol_revision=provider.protocol_profile,
    )
    write_phase3_artifacts(
        challenge_advice,
        correction_shadow,
        artifacts / "secondary_challenge_advice.json",
        artifacts / "secondary_correction_shadow.json",
    )
    write_json(artifacts / "phase3_replay_summary.json", phase3_summary)

    locked_report = copy.deepcopy(game.primary_report)
    write_report_files(
        locked_report,
        game.documents,
        artifacts / "review_report.md",
        artifacts / "review_report.json",
    )
    public_report = redact_blind_sensitive_payload(locked_report)
    write_report_files(
        public_report,
        game.documents,
        replay_dir / "review_report.md",
        replay_dir / "review_report.json",
    )
    annotation_items = build_phase3_annotation_items(
        game=game,
        variant_id=provider.variant_id,
        repeat_index=repeat_index,
        challenge_advice=challenge_advice,
        correction_shadow=correction_shadow,
    )
    result = {
        **base_result,
        "status": "completed",
        "attempt_count": attempt_count,
        "reprocessed_saved_raw": reprocessed_saved_raw,
        "secondary_response_hash": hash_text(secondary_raw),
        "candidate_generation_mode": "phase3_advice_shadow_only",
        "selected_report_owner": "primary_locked",
        "candidate_gate_passed": False,
        "candidate_recommendation_status": "not_applicable_shadow_only",
        "traceability_status": "complete" if phase3_summary.get("protocol_gate_passed") else "rejected",
        "claimed_added_count": 0,
        "admitted_added_count": 0,
        "rejected_added_count": 0,
        "added_rejection_reasons": [],
        "materialized_added_count": 0,
        "added_root_keys": [],
        "high_added_root_keys": [],
        "added_severity_by_root": {},
        "coverage_ledger_completeness": None,
        "coverage_schema_version": 0,
        "coverage_ledger_valid": False,
        "coverage_evidence_packet_echoed": False,
        "phase2_delta_only_compliant": False,
        "phase2_protocol_gate_passed": False,
        "coverage_ledger_errors": [],
        "coverage_confirmed_audit_keys": [],
        "coverage_confirmed_control_keys": [],
        "selected_top_blocker_keys": sorted(report_top_blocker_keys(locked_report)),
        "primary_top_blocker_retention": 1.0,
        "field_completeness": None,
        "admitted_field_completeness": None,
        "phase2_admission_all_passed": False,
        "primary_top3_retention_gate_passed": True,
        "candidate_score_locked_to_primary": True,
        "multiroot_finding_count": 0,
        "preserved_primary_multiroot_finding_count": 0,
        "unsupported_severity_change_count": 0,
        "unsupported_blocking_change_count": 0,
        "lineage_mismatch": False,
        "materialization_mismatch": False,
        "major_judgment_drift": False,
        "selected_finding_count": count_report_findings(locked_report),
        "phase3_protocol_gate_passed": bool(phase3_summary.get("protocol_gate_passed")),
        "phase3_baseline_lock_passed": bool(phase3_summary.get("baseline_lock_passed")),
        "phase3_challenge_claimed_count": safe_int(phase3_summary.get("challenge_claimed_count")),
        "phase3_challenge_accepted_count": safe_int(phase3_summary.get("challenge_accepted_count")),
        "phase3_challenge_rejected_count": safe_int(phase3_summary.get("challenge_rejected_count")),
        "phase3_correction_claimed_count": safe_int(phase3_summary.get("correction_claimed_count")),
        "phase3_correction_accepted_count": safe_int(phase3_summary.get("correction_accepted_count")),
        "phase3_correction_rejected_count": safe_int(phase3_summary.get("correction_rejected_count")),
        "phase3_correction_abstained_count": safe_int(phase3_summary.get("correction_abstained_count")),
        "phase3_correction_disposition_counts": phase3_summary.get("correction_disposition_counts") or {},
        "phase3_challenge_keys": phase3_summary.get("challenge_keys") or [],
        "phase3_correction_keys": phase3_summary.get("correction_keys") or [],
        "phase3_target_coverage_ledger_complete": bool(
            phase3_summary.get("target_coverage_ledger_complete")
        ),
        "phase3_target_coverage_ledger_completeness": phase3_summary.get(
            "target_coverage_ledger_completeness"
        ),
        "phase3_target_coverage_ledger_valid": bool(
            phase3_summary.get("target_coverage_ledger_valid")
        ),
        "phase3_target_coverage_ledger_errors": phase3_summary.get(
            "target_coverage_ledger_errors"
        )
        or [],
        "phase3_target_decision_keys": phase3_summary.get("target_decision_keys") or [],
        "phase3_challenge_target_keys": phase3_summary.get("challenge_target_keys") or [],
        "phase3_challenge_check_keys": phase3_summary.get("challenge_check_keys") or [],
        "phase3_challenge_checks_complete": bool(phase3_summary.get("challenge_checks_complete")),
        "phase3_challenge_checks_completeness": phase3_summary.get("challenge_checks_completeness"),
        "phase3_challenge_checks_valid": phase3_summary.get("challenge_checks_valid"),
        "phase3_challenge_matrix_errors": phase3_summary.get("challenge_matrix_errors") or [],
        "annotation_items": annotation_items,
    }
    write_json(
        artifacts / "replay_metadata.json",
        {key: value for key, value in result.items() if key != "annotation_items"},
    )
    return result


def run_one_replay(
    *,
    run_dir: Path,
    game: FrozenGame,
    provider: SecondaryProvider,
    repeat_index: int,
    messages: list[dict[str, Any]],
    message_hash: str,
    client: OpenAICompatibleClient,
    model_retries: int,
    logger: RunLogger,
    secondary_raw_override: str | None = None,
    processing_profile: str | None = None,
    phase2_evidence_packet_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actual_profile = normalize_secondary_protocol_profile(provider.protocol_profile)
    active_processing_profile = normalize_secondary_protocol_profile(processing_profile or actual_profile)
    message_text = json.dumps(messages, ensure_ascii=False)
    revision_match = re.search(r"protocol_profile=(phase2_v2_\d+)", message_text)
    coverage_protocol_revision = (
        revision_match.group(1)
        if actual_profile == "phase2" and revision_match
        else ("phase2_legacy" if actual_profile == "phase2" else "")
    )
    if coverage_protocol_revision.startswith("phase2_v2_"):
        if secondary_raw_override is not None:
            phase2_evidence_packet = (
                dict(phase2_evidence_packet_override)
                if isinstance(phase2_evidence_packet_override, dict)
                and str(phase2_evidence_packet_override.get("protocol_revision") or "")
                == coverage_protocol_revision
                else {}
            )
        else:
            phase2_evidence_packet = build_phase2_control_evidence_packet(
                game.shared_input,
                game.primary_report,
                protocol_revision=coverage_protocol_revision,
            )
    else:
        phase2_evidence_packet = {}
    expected_evidence_packet_id = str(phase2_evidence_packet.get("evidence_packet_id") or "")
    relative_dir = Path("blinded") / provider.variant_id / game.name / f"repeat_{repeat_index:02d}"
    private_relative_dir = Path("_private") / "calls" / provider.variant_id / game.name / f"repeat_{repeat_index:02d}"
    replay_dir = run_dir / relative_dir
    artifacts = run_dir / private_relative_dir / "model_artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    write_json(artifacts / "secondary_review_messages.json", messages)
    evidence_packet_path = artifacts / "phase2_control_evidence_packet.json"
    if phase2_evidence_packet:
        write_json(evidence_packet_path, phase2_evidence_packet)
    elif evidence_packet_path.exists():
        evidence_packet_path.unlink()
    base_result: dict[str, Any] = {
        "game": game.name,
        "variant_id": provider.variant_id,
        "repeat": repeat_index,
        "status": "failed",
        "output_dir": relative_dir.as_posix(),
        "private_output_dir": private_relative_dir.as_posix(),
        "shared_input_hash": game.hashes["shared_input_hash"],
        "primary_raw_hash": game.hashes["primary_raw_hash"],
        "primary_messages_hash": game.hashes["primary_messages_hash"],
        "primary_report_hash": game.hashes["primary_report_hash"],
        "secondary_message_hash": message_hash,
        "provider_config_hash": provider_config_hash(provider.config),
        "protocol_profile": actual_profile,
        "processing_profile": active_processing_profile,
        "coverage_protocol_revision": coverage_protocol_revision,
        "coverage_evidence_packet_id": expected_evidence_packet_id,
        "temperature": 0,
        "annotation_items": [],
    }
    try:
        if secondary_raw_override is None:
            secondary_raw, attempt_count = call_with_retries(
                client,
                messages,
                provider.config,
                model_retries=model_retries,
                logger=logger,
                stage=f"secondary_benchmark:{provider.variant_id}:{game.name}:repeat_{repeat_index:02d}",
            )
        else:
            secondary_raw = secondary_raw_override
            attempt_count = 0
            logger.info(
                "reprocess saved secondary response",
                game=game.name,
                variant=provider.variant_id,
                repeat=repeat_index,
                response_chars=len(secondary_raw),
            )
        (artifacts / "secondary_raw_model_response.txt").write_text(secondary_raw, encoding="utf-8")
        if active_processing_profile in PHASE3_PROTOCOL_REVISIONS:
            if actual_profile != active_processing_profile:
                raise ValueError(
                    f"{active_processing_profile} processing requires a response generated by the same prompt profile."
                )
            return process_phase3_replay(
                game=game,
                provider=provider,
                repeat_index=repeat_index,
                secondary_raw=secondary_raw,
                artifacts=artifacts,
                replay_dir=replay_dir,
                base_result=base_result,
                attempt_count=attempt_count,
                reprocessed_saved_raw=secondary_raw_override is not None,
            )
        secondary_review, parse_error = parse_dual_pass_review_json(secondary_raw)
        if parse_error:
            raise ValueError(f"Secondary response is not valid dual_pass JSON: {parse_error}")
        phase2_protocol_gate = evaluate_phase2_protocol_gate(
            secondary_review,
            coverage_protocol_revision,
            expected_evidence_packet_id,
        )
        evidence_packet_echoed = bool(phase2_protocol_gate.get("echo_matched"))

        pipeline_report, pipeline_merge_summary = merge_dual_pass_review_report(
            game.primary_report,
            secondary_review,
            game.documents,
            secondary_model=f"variant_{provider.variant_id}",
            shared_input=game.shared_input,
            enforce_phase2_admission=active_processing_profile == "phase2",
            phase2_protocol_gate=phase2_protocol_gate if active_processing_profile == "phase2" else None,
        )
        pipeline_report["review_mode"] = "dual_pass"
        pipeline_report["primary_model"] = game.primary_model
        pipeline_report["secondary_model"] = f"variant_{provider.variant_id}"
        pipeline_report = demote_dual_pass_cross_document_issues(pipeline_report)
        phase2_admission = pipeline_merge_summary.get("phase2_admission") or {}
        candidate_secondary_review = (
            sanitize_dual_pass_phase2_candidate_review(
                game.primary_report,
                secondary_review,
                phase2_admission,
                game.shared_input,
            )
            if active_processing_profile == "phase2"
            else secondary_review
        )
        if active_processing_profile == "phase2":
            phase2_admission["candidate_inputs_sanitized"] = True

        candidate_report: dict[str, Any] | None = None
        candidate_error = ""
        if active_processing_profile == "phase2":
            candidate_report, candidate_secondary_review = build_deterministic_phase2_candidate(
                game.primary_report,
                pipeline_report,
                candidate_secondary_review,
            )
            candidate_report["review_mode"] = "dual_pass_candidate"
            candidate_report["primary_model"] = game.primary_model
            candidate_report["secondary_model"] = f"variant_{provider.variant_id}"
            candidate_report = demote_dual_pass_cross_document_issues(candidate_report)
            candidate_report = lock_dual_pass_candidate_score_to_primary(game.primary_report, candidate_report)
            candidate_report = lock_dual_pass_candidate_top_blockers_to_primary(
                game.primary_report, candidate_report
            )
        else:
            candidate_payload = candidate_secondary_review.get("candidate_report")
            if isinstance(candidate_payload, dict) and candidate_payload:
                candidate_raw = json.dumps(candidate_payload, ensure_ascii=False)
                candidate_report, candidate_error = parse_candidate_model_json(candidate_raw, game.documents)
                if candidate_error:
                    candidate_report, candidate_error = parse_model_json(candidate_raw, game.documents)
                if not candidate_error:
                    candidate_report = build_conservative_dual_pass_candidate_report(
                        game.primary_report,
                        candidate_report,
                        candidate_secondary_review.get("candidate_lineage") or {},
                        candidate_secondary_review.get("missed_findings") or [],
                        f"variant_{provider.variant_id}",
                    )
                    candidate_report["review_mode"] = "dual_pass_candidate"
                    candidate_report["primary_model"] = game.primary_model
                    candidate_report["secondary_model"] = f"variant_{provider.variant_id}"
                    candidate_report = demote_dual_pass_cross_document_issues(candidate_report)

        advice = normalize_dual_pass_advice_payload(
            game.primary_report, candidate_report, candidate_secondary_review
        )
        advice["candidate_generation_mode"] = str(
            candidate_secondary_review.get("candidate_generation_mode") or "model_authored"
        )
        advice["phase2_admission"] = phase2_admission
        lineage_counts = advice.get("lineage_counts_raw") or advice.get("lineage_counts") or {}
        selection = evaluate_dual_pass_candidate_selection(
            game.primary_report,
            candidate_report,
            advice,
            lineage_counts,
            "" if not candidate_error else candidate_error,
            phase2_admission=phase2_admission,
        )
        advice["candidate_block_reasons"] = selection.get("candidate_gate_failure_reasons") or []
        advice["candidate_gate_results"] = selection.get("candidate_gate_results") or {}
        advice["candidate_block_reason_categories"] = selection.get("candidate_gate_failure_categories") or {}

        selected_owner = str(selection.get("selected_report_owner") or "pipeline")
        selected_report = candidate_report if selected_owner == "candidate" and candidate_report else pipeline_report
        write_report_files(
            pipeline_report,
            game.documents,
            artifacts / "review_report_pipeline.md",
            artifacts / "review_report_pipeline.json",
        )
        public_pipeline_report = redact_blind_sensitive_payload(pipeline_report)
        write_report_files(public_pipeline_report, game.documents, replay_dir / "review_report_pipeline.md", replay_dir / "review_report_pipeline.json")
        if candidate_report:
            write_report_files(
                candidate_report,
                game.documents,
                artifacts / "review_report_candidate.md",
                artifacts / "review_report_candidate.json",
            )
            public_candidate_report = redact_blind_sensitive_payload(candidate_report)
            write_report_files(public_candidate_report, game.documents, replay_dir / "review_report_candidate.md", replay_dir / "review_report_candidate.json")
        write_report_files(selected_report, game.documents, artifacts / "review_report.md", artifacts / "review_report.json")
        public_selected_report = redact_blind_sensitive_payload(selected_report)
        write_report_files(public_selected_report, game.documents, replay_dir / "review_report.md", replay_dir / "review_report.json")
        write_dual_pass_advice_files(advice, artifacts / "secondary_review_advice.md", artifacts / "secondary_review_advice.json")
        public_advice = redact_blind_sensitive_payload(advice)
        write_dual_pass_advice_files(public_advice, replay_dir / "secondary_review_advice.md", replay_dir / "secondary_review_advice.json")
        comparison = build_dual_pass_comparison_summary(pipeline_report, candidate_report) if candidate_report else {}
        replay_summary = {
            "status": "completed",
            "game": game.name,
            "variant_id": provider.variant_id,
            "repeat": repeat_index,
            "candidate_generation_mode": advice.get("candidate_generation_mode") or "model_authored",
            "selected_report_owner": selected_owner,
            "candidate_recommendation_status": selection.get("candidate_recommendation_status") or "candidate_unavailable",
            "candidate_gate_results": selection.get("candidate_gate_results") or {},
            "candidate_gate_failure_reasons": selection.get("candidate_gate_failure_reasons") or [],
            "lineage_counts": lineage_counts,
            "traceability_status": advice.get("traceability_status") or "unavailable",
            "candidate_structurally_ready": bool(advice.get("candidate_structurally_ready")),
            "candidate_contains_multiroot_kept_findings": bool(advice.get("candidate_contains_multiroot_kept_findings")),
            "candidate_multiroot_kept_titles": advice.get("candidate_multiroot_kept_titles") or [],
            "candidate_high_signal_demotion_without_support": bool(advice.get("candidate_high_signal_demotion_without_support")),
            "candidate_overcompressed": bool(advice.get("candidate_overcompressed")),
            "candidate_major_judgment_drift": bool(advice.get("candidate_major_judgment_drift")),
            "comparison_summary": comparison,
            "pipeline_merge_summary": pipeline_merge_summary,
            "phase2_admission": phase2_admission,
            "coverage_protocol_revision": base_result["coverage_protocol_revision"],
            "coverage_evidence_packet_id": expected_evidence_packet_id,
            "coverage_evidence_packet_echoed": evidence_packet_echoed,
            "phase2_delta_only_compliant": bool(phase2_protocol_gate.get("delta_only_compliant")),
            "phase2_protocol_gate": phase2_protocol_gate,
        }
        write_json(artifacts / "replay_summary.json", replay_summary)
        added_findings = [item for item in (secondary_review.get("missed_findings") or []) if isinstance(item, dict)]
        admission_results = [item for item in phase2_admission.get("results") or [] if isinstance(item, dict)]
        admitted_findings = [
            finding
            for finding, admission in zip(added_findings, admission_results)
            if admission.get("status") == "admitted"
        ] if active_processing_profile == "phase2" else added_findings
        admitted_multiroot_count = sum(
            1
            for finding in admitted_findings
            if finding.get("multiroot") is True
            or safe_int(finding.get("root_cause_count")) != 1
            or not isinstance(finding.get("root_causes"), list)
            or len(finding.get("root_causes") or []) != 1
        )
        materialized_added = collect_secondary_findings(pipeline_report)
        annotation_items = build_annotation_items(
            game=game,
            variant_id=provider.variant_id,
            repeat_index=repeat_index,
            added_findings=added_findings,
            admission_results=admission_results,
        )
        completeness = field_completeness(added_findings)
        admitted_completeness = field_completeness(admitted_findings)
        rejection_reasons = [
            str(reason)
            for admission in admission_results
            if admission.get("status") == "rejected"
            for reason in admission.get("reasons") or []
            if str(reason)
        ]
        stability_findings = admitted_findings if active_processing_profile == "phase2" else added_findings
        coverage_evaluation = (
            phase2_admission.get("coverage_ledger")
            if isinstance(phase2_admission.get("coverage_ledger"), dict)
            else {}
        )
        coverage_ledger_completeness = coverage_evaluation.get("completeness")
        if coverage_ledger_completeness is None:
            coverage_ledger_completeness = 0.0
        coverage_confirmed_audit_keys = sorted(coverage_evaluation.get("confirmed_audit_keys") or [])
        coverage_confirmed_control_keys = sorted(coverage_evaluation.get("confirmed_control_keys") or [])
        result = {
            **base_result,
            "status": "completed",
            "attempt_count": attempt_count,
            "reprocessed_saved_raw": secondary_raw_override is not None,
            "secondary_response_hash": hash_text(secondary_raw),
            "candidate_generation_mode": advice.get("candidate_generation_mode") or "model_authored",
            "selected_report_owner": selected_owner,
            "candidate_gate_passed": selected_owner == "candidate",
            "candidate_recommendation_status": selection.get("candidate_recommendation_status") or "candidate_unavailable",
            "traceability_status": advice.get("traceability_status") or "unavailable",
            "claimed_added_count": len(added_findings),
            "admitted_added_count": len(admitted_findings),
            "rejected_added_count": len(added_findings) - len(admitted_findings),
            "added_rejection_reasons": rejection_reasons,
            "materialized_added_count": len(materialized_added),
            "added_root_keys": sorted({root_key(item) for item in stability_findings if root_key(item)}),
            "high_added_root_keys": sorted(
                {root_key(item) for item in stability_findings if root_key(item) and is_high_finding(item)}
            ),
            "added_severity_by_root": {
                root_key(item): normalize_severity(item.get("severity"))
                for item in stability_findings
                if root_key(item)
            },
            "coverage_ledger_completeness": coverage_ledger_completeness,
            "coverage_schema_version": safe_int(coverage_evaluation.get("schema_version")),
            "coverage_ledger_valid": coverage_evaluation.get("passed") is True,
            "coverage_evidence_packet_echoed": evidence_packet_echoed,
            "phase2_delta_only_compliant": bool(phase2_protocol_gate.get("delta_only_compliant")),
            "phase2_protocol_gate_passed": bool(phase2_protocol_gate.get("passed")),
            "coverage_ledger_errors": coverage_evaluation.get("errors") or [],
            "coverage_confirmed_audit_keys": coverage_confirmed_audit_keys,
            "coverage_confirmed_control_keys": coverage_confirmed_control_keys,
            "selected_top_blocker_keys": sorted(report_top_blocker_keys(selected_report)),
            "primary_top_blocker_retention": top_blocker_retention(game.primary_report, selected_report),
            "field_completeness": completeness,
            "admitted_field_completeness": admitted_completeness,
            "phase2_admission_all_passed": phase2_admission.get("all_passed") is True,
            "primary_top3_retention_gate_passed": bool(selection.get("primary_top3_retention_gate_passed")),
            "candidate_score_locked_to_primary": bool(selection.get("candidate_score_locked_to_primary")),
            "multiroot_finding_count": admitted_multiroot_count,
            "preserved_primary_multiroot_finding_count": len(
                advice.get("candidate_multiroot_kept_titles") or []
            ),
            "unsupported_severity_change_count": int(bool(advice.get("candidate_high_signal_demotion_without_support"))),
            "unsupported_blocking_change_count": int(bool(advice.get("candidate_blocker_conclusion_mismatch"))),
            "lineage_mismatch": bool(
                advice.get("advice_candidate_structure_mismatch")
                or advice.get("unmapped_primary_issue_ids")
                or advice.get("unmapped_candidate_issue_ids")
            ),
            "materialization_mismatch": str(advice.get("candidate_added_materialization_status") or "none") not in {"none", "complete"}
            or str(advice.get("candidate_merged_materialization_status") or "none") not in {"none", "complete"},
            "major_judgment_drift": bool(advice.get("candidate_major_judgment_drift")),
            "selected_finding_count": count_report_findings(selected_report),
            "annotation_items": annotation_items,
        }
        write_json(artifacts / "replay_metadata.json", {key: value for key, value in result.items() if key != "annotation_items"})
        return result
    except Exception as exc:
        base_result["error"] = str(exc)
        write_json(artifacts / "replay_metadata.json", {key: value for key, value in base_result.items() if key != "annotation_items"})
        logger.info(
            "secondary benchmark replay failed",
            game=game.name,
            variant=provider.variant_id,
            repeat=repeat_index,
            error=str(exc),
        )
        return base_result


def call_with_retries(
    client: OpenAICompatibleClient,
    messages: list[dict[str, Any]],
    config: ModelConfig,
    *,
    model_retries: int,
    logger: RunLogger,
    stage: str,
) -> tuple[str, int]:
    max_attempts = max(0, model_retries) + 1
    for attempt in range(1, max_attempts + 1):
        logger.info("text model request attempt", stage=stage, attempt=attempt, max_attempts=max_attempts)
        try:
            return client.chat(messages, model=config.text_model, temperature=0), attempt
        except Exception as exc:
            if attempt >= max_attempts or not is_retryable_model_error(exc):
                raise RuntimeError(f"{stage} failed after {attempt} attempt(s): {exc}") from exc
            delay_seconds = min(2**attempt, 30)
            logger.info(
                "text model retry scheduled",
                stage=stage,
                failed_attempt=attempt,
                next_attempt=attempt + 1,
                delay_seconds=delay_seconds,
                reason=str(exc),
            )
            time.sleep(delay_seconds)
    raise RuntimeError("Secondary benchmark retry loop exited unexpectedly.")


def is_retryable_model_error(exc: Exception) -> bool:
    message = str(exc or "").strip().lower()
    http_match = re.search(r"\bhttp\s+(\d{3})\b", message)
    if http_match:
        status_code = int(http_match.group(1))
        return status_code >= 500 or status_code in {408, 409, 425, 429}
    return any(
        marker in message
        for marker in (
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
    )


def build_invariant_summary(
    games: list[FrozenGame],
    calls: list[dict[str, Any]],
    comparison_axis: str = "provider",
) -> dict[str, Any]:
    per_game: list[dict[str, Any]] = []
    all_fixed = True
    for game in games:
        game_calls = [item for item in calls if item.get("game") == game.name]
        checks: dict[str, bool] = {}
        for field in (
            "shared_input_hash",
            "primary_raw_hash",
            "primary_messages_hash",
            "primary_report_hash",
        ):
            checks[f"{field}_identical"] = len({str(item.get(field) or "") for item in game_calls}) == 1
        checks["temperature_identical"] = len({item.get("temperature") for item in game_calls}) == 1
        profiles_by_variant = {
            str(item.get("variant_id") or ""): str(item.get("protocol_profile") or "baseline")
            for item in game_calls
        }
        message_hashes_by_variant = {
            variant: {
                str(item.get("secondary_message_hash") or "")
                for item in game_calls
                if str(item.get("variant_id") or "") == variant
            }
            for variant in profiles_by_variant
        }
        provider_hashes = {str(item.get("provider_config_hash") or "") for item in game_calls}
        if comparison_axis == "protocol_profile":
            checks["provider_config_identical"] = len(provider_hashes) == 1
            checks["protocol_profiles_distinct"] = len(set(profiles_by_variant.values())) == len(profiles_by_variant)
            checks["message_hash_stable_within_variant"] = all(
                len(values) == 1 for values in message_hashes_by_variant.values()
            )
            checks["prompt_hashes_distinct_between_variants"] = len(
                {next(iter(values), "") for values in message_hashes_by_variant.values()}
            ) == len(message_hashes_by_variant)
        elif comparison_axis == "single_profile":
            checks["provider_config_identical"] = len(provider_hashes) == 1
            checks["message_hash_stable_within_variant"] = all(
                len(values) == 1 for values in message_hashes_by_variant.values()
            )
        else:
            checks["secondary_message_hash_identical"] = len(
                {str(item.get("secondary_message_hash") or "") for item in game_calls}
            ) == 1
            checks["protocol_profile_identical"] = len(set(profiles_by_variant.values())) == 1
        game_fixed = all(checks.values())
        all_fixed = all_fixed and game_fixed
        per_game.append({"game": game.name, "passed": game_fixed, "checks": checks, "frozen_hashes": game.hashes})
    return {
        "passed": all_fixed,
        "comparison_axis": comparison_axis,
        "only_secondary_provider_varies": all_fixed and comparison_axis == "provider",
        "only_protocol_profile_varies": all_fixed and comparison_axis == "protocol_profile",
        "only_intended_variable_varies": all_fixed,
        "primary_calls_observed": 0,
        "vision_calls_observed": 0,
        "per_game": per_game,
    }


def build_stability_summary(calls: list[dict[str, Any]], repeats: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in calls:
        if item.get("status") == "completed":
            groups.setdefault((str(item.get("variant_id")), str(item.get("game"))), []).append(item)
    result: list[dict[str, Any]] = []
    for (variant_id, game), items in sorted(groups.items()):
        items.sort(key=lambda value: int(value.get("repeat") or 0))
        added_sets = [set(item.get("added_root_keys") or []) for item in items]
        high_sets = [set(item.get("high_added_root_keys") or []) for item in items]
        blocker_sets = [set(item.get("selected_top_blocker_keys") or []) for item in items]
        coverage_sets = [set(item.get("coverage_confirmed_audit_keys") or []) for item in items]
        coverage_control_sets = [set(item.get("coverage_confirmed_control_keys") or []) for item in items]
        phase3_challenge_sets = [set(item.get("phase3_challenge_keys") or []) for item in items]
        phase3_correction_sets = [set(item.get("phase3_correction_keys") or []) for item in items]
        phase3_target_decision_sets = [set(item.get("phase3_target_decision_keys") or []) for item in items]
        phase3_challenge_target_sets = [set(item.get("phase3_challenge_target_keys") or []) for item in items]
        phase3_challenge_check_sets = [set(item.get("phase3_challenge_check_keys") or []) for item in items]
        result.append(
            {
                "variant_id": variant_id,
                "game": game,
                "completed_repeats": len(items),
                "expected_repeats": repeats,
                "added_root_overlap": set_overlap(added_sets),
                "high_added_root_overlap": set_overlap(high_sets),
                "severity_consistency": severity_consistency(items),
                "top_blocker_overlap": set_overlap(blocker_sets),
                "coverage_confirmed_overlap": set_overlap(coverage_sets),
                "coverage_confirmed_control_overlap": set_overlap(coverage_control_sets),
                "candidate_adoption_consistent": len({bool(item.get("candidate_gate_passed")) for item in items}) <= 1,
                "phase3_challenge_overlap": set_overlap(phase3_challenge_sets),
                "phase3_correction_overlap": set_overlap(phase3_correction_sets),
                "phase3_target_decision_overlap": set_overlap(phase3_target_decision_sets),
                "phase3_challenge_target_overlap": set_overlap(phase3_challenge_target_sets),
                "phase3_challenge_check_overlap": set_overlap(phase3_challenge_check_sets),
            }
        )
    return result


def build_variant_metrics(calls: list[dict[str, Any]], providers: list[SecondaryProvider]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for provider in providers:
        items = [item for item in calls if item.get("variant_id") == provider.variant_id]
        completed = [item for item in items if item.get("status") == "completed"]
        count = len(completed)
        rejection_reason_counts: dict[str, int] = {}
        for item in completed:
            for reason in item.get("added_rejection_reasons") or []:
                key = str(reason).split(":", 1)[0]
                rejection_reason_counts[key] = rejection_reason_counts.get(key, 0) + 1
        retention_values = [
            float(item.get("primary_top_blocker_retention"))
            for item in completed
            if item.get("primary_top_blocker_retention") is not None
        ]
        metrics.append(
            {
                "variant_id": provider.variant_id,
                "expected_calls": len(items),
                "completed_calls": count,
                "candidate_gate_pass_rate": ratio(sum(bool(item.get("candidate_gate_passed")) for item in completed), count),
                "candidate_default_adoption_rate": ratio(sum(item.get("selected_report_owner") == "candidate" for item in completed), count),
                "average_claimed_added_count": average(item.get("claimed_added_count") for item in completed),
                "average_admitted_added_count": average(item.get("admitted_added_count") for item in completed),
                "total_rejected_added_count": sum(safe_int(item.get("rejected_added_count")) for item in completed),
                "added_rejection_reason_counts": rejection_reason_counts,
                "average_materialized_added_count": average(item.get("materialized_added_count") for item in completed),
                "average_primary_top_blocker_retention": average(item.get("primary_top_blocker_retention") for item in completed),
                "minimum_primary_top_blocker_retention": min(retention_values) if retention_values else None,
                "primary_top3_gate_pass_rate": ratio(
                    sum(bool(item.get("primary_top3_retention_gate_passed")) for item in completed), count
                ),
                "average_field_completeness": average(item.get("field_completeness") for item in completed),
                "average_admitted_field_completeness": average(
                    item.get("admitted_field_completeness") for item in completed
                ),
                "average_coverage_ledger_completeness": average(
                    item.get("coverage_ledger_completeness") for item in completed
                ),
                "coverage_ledger_valid_rate": ratio(
                    sum(bool(item.get("coverage_ledger_valid")) for item in completed), count
                ),
                "coverage_schema_v2_rate": ratio(
                    sum(safe_int(item.get("coverage_schema_version")) >= 2 for item in completed), count
                ),
                "coverage_evidence_packet_echo_rate": ratio(
                    sum(bool(item.get("coverage_evidence_packet_echoed")) for item in completed), count
                ),
                "phase2_protocol_gate_pass_rate": ratio(
                    sum(bool(item.get("phase2_protocol_gate_passed")) for item in completed), count
                ),
                "phase2_delta_only_compliance_rate": ratio(
                    sum(bool(item.get("phase2_delta_only_compliant")) for item in completed), count
                ),
                "deterministic_candidate_generation_rate": ratio(
                    sum(
                        item.get("candidate_generation_mode")
                        == "deterministic_primary_plus_admitted_delta"
                        for item in completed
                    ),
                    count,
                ),
                "phase2_admission_all_pass_rate": ratio(
                    sum(bool(item.get("phase2_admission_all_passed")) for item in completed), count
                ),
                "candidate_score_lock_rate": ratio(
                    sum(bool(item.get("candidate_score_locked_to_primary")) for item in completed), count
                ),
                "multiroot_finding_count": sum(safe_int(item.get("multiroot_finding_count")) for item in completed),
                "preserved_primary_multiroot_finding_count": sum(
                    safe_int(item.get("preserved_primary_multiroot_finding_count")) for item in completed
                ),
                "unsupported_severity_change_count": sum(
                    safe_int(item.get("unsupported_severity_change_count")) for item in completed
                ),
                "unsupported_blocking_change_count": sum(
                    safe_int(item.get("unsupported_blocking_change_count")) for item in completed
                ),
                "lineage_mismatch_count": sum(bool(item.get("lineage_mismatch")) for item in completed),
                "materialization_mismatch_count": sum(bool(item.get("materialization_mismatch")) for item in completed),
                "major_judgment_drift_count": sum(bool(item.get("major_judgment_drift")) for item in completed),
                "phase3_protocol_gate_pass_rate": ratio(
                    sum(bool(item.get("phase3_protocol_gate_passed")) for item in completed), count
                ),
                "phase3_baseline_lock_pass_rate": ratio(
                    sum(bool(item.get("phase3_baseline_lock_passed")) for item in completed), count
                ),
                "average_phase3_challenge_accepted_count": average(
                    item.get("phase3_challenge_accepted_count") for item in completed
                ),
                "average_phase3_correction_accepted_count": average(
                    item.get("phase3_correction_accepted_count") for item in completed
                ),
                "average_phase3_correction_abstained_count": average(
                    item.get("phase3_correction_abstained_count") for item in completed
                ),
                "phase3_target_coverage_ledger_complete_rate": ratio(
                    sum(
                        bool(item.get("phase3_target_coverage_ledger_complete"))
                        for item in completed
                        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        in {PHASE3_V12_PROTOCOL_REVISION, PHASE3_V13_PROTOCOL_REVISION}
                    ),
                    sum(
                        str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        in {PHASE3_V12_PROTOCOL_REVISION, PHASE3_V13_PROTOCOL_REVISION}
                        for item in completed
                    ),
                ),
                "phase3_target_coverage_ledger_valid_rate": ratio(
                    sum(
                        bool(item.get("phase3_target_coverage_ledger_valid"))
                        for item in completed
                        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        in {PHASE3_V12_PROTOCOL_REVISION, PHASE3_V13_PROTOCOL_REVISION}
                    ),
                    sum(
                        str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        in {PHASE3_V12_PROTOCOL_REVISION, PHASE3_V13_PROTOCOL_REVISION}
                        for item in completed
                    ),
                ),
                "phase3_challenge_checks_complete_rate": ratio(
                    sum(
                        bool(item.get("phase3_challenge_checks_complete"))
                        for item in completed
                        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        == PHASE3_V13_PROTOCOL_REVISION
                    ),
                    sum(
                        str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        == PHASE3_V13_PROTOCOL_REVISION
                        for item in completed
                    ),
                ),
                "phase3_challenge_checks_valid_rate": ratio(
                    sum(
                        bool(item.get("phase3_challenge_checks_valid"))
                        for item in completed
                        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        == PHASE3_V13_PROTOCOL_REVISION
                    ),
                    sum(
                        str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
                        == PHASE3_V13_PROTOCOL_REVISION
                        for item in completed
                    ),
                ),
            }
        )
    return metrics


PHASE2_ACCEPTANCE_THRESHOLDS = {
    "raw_field_completeness_min": 0.9,
    "admitted_field_completeness_min": 1.0,
    "ledger_completeness_min": 1.0,
    "ledger_valid_rate_min": 1.0,
    "coverage_schema_v2_rate_min": 1.0,
    "coverage_evidence_packet_echo_rate_min": 1.0,
    "phase2_protocol_gate_pass_rate_min": 1.0,
    "phase2_delta_only_compliance_rate_min": 1.0,
    "deterministic_candidate_generation_rate_min": 1.0,
    "candidate_gate_pass_rate_min": 0.9,
    "primary_top3_retention_min": round(2 / 3, 4),
    "admitted_precision_min": 0.8,
    "valid_added_count_min": 10,
    "high_value_added_count_min": 5,
    "duplicate_rate_max": 0.15,
    "high_added_root_overlap_min": 0.25,
}


def build_phase2_acceptance_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Build an explicit pass/fail gate for the phase-two directional protocol."""
    calls = [item for item in summary.get("calls") or [] if isinstance(item, dict)]
    phase2_calls = [
        item
        for item in calls
        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower() == "phase2"
    ]
    phase2_variant_ids = sorted(
        {str(item.get("variant_id") or "").strip() for item in phase2_calls if str(item.get("variant_id") or "").strip()}
    )
    if not phase2_calls or not phase2_variant_ids:
        return {
            "applicable": False,
            "status": "not_applicable",
            "eligible_for_next_stage": False,
            "reason": "当前 benchmark 不包含 phase2 processing profile。",
            "thresholds": dict(PHASE2_ACCEPTANCE_THRESHOLDS),
            "checks": {},
            "blocking_reasons": [],
            "pending_reasons": [],
        }

    variant_metrics = [
        item
        for item in summary.get("variant_metrics") or []
        if isinstance(item, dict) and str(item.get("variant_id") or "") in phase2_variant_ids
    ]
    stability_rows = [
        item
        for item in summary.get("stability_comparison") or []
        if isinstance(item, dict) and str(item.get("variant_id") or "") in phase2_variant_ids
    ]
    human = summary.get("human_metrics") if isinstance(summary.get("human_metrics"), dict) else {}
    human_ready = human.get("status") == "completed"
    human_variants = [
        item
        for item in human.get("variants") or []
        if isinstance(item, dict) and str(item.get("variant_id") or "") in phase2_variant_ids
    ]

    def metric_values(field: str) -> list[float]:
        return [float(item[field]) for item in variant_metrics if item.get(field) is not None]

    def minimum_metric(field: str) -> float | None:
        values = metric_values(field)
        return min(values) if values else None

    def sum_metric(field: str) -> int:
        return sum(safe_int(item.get(field)) for item in variant_metrics)

    def check(observed: Any, target: str, passed: bool, *, ready: bool = True) -> dict[str, Any]:
        return {"ready": ready, "passed": bool(passed) if ready else None, "observed": observed, "target": target}

    completed_phase2_calls = sum(item.get("status") == "completed" for item in phase2_calls)
    high_overlap_values = [
        float(item.get("high_added_root_overlap"))
        for item in stability_rows
        if item.get("high_added_root_overlap") is not None
    ]
    high_overlap_average = average(high_overlap_values)
    raw_field_min = minimum_metric("average_field_completeness")
    admitted_field_min = minimum_metric("average_admitted_field_completeness")
    ledger_complete_min = minimum_metric("average_coverage_ledger_completeness")
    ledger_valid_min = minimum_metric("coverage_ledger_valid_rate")
    coverage_schema_v2_min = minimum_metric("coverage_schema_v2_rate")
    v21_required = any(
        str(item.get("coverage_protocol_revision") or "").strip().startswith("phase2_v2_")
        for item in phase2_calls
    )
    v22_required = any(
        str(item.get("coverage_protocol_revision") or "").strip() == "phase2_v2_2"
        for item in phase2_calls
    )
    evidence_packet_echo_min = minimum_metric("coverage_evidence_packet_echo_rate") if v21_required else None
    protocol_gate_min = minimum_metric("phase2_protocol_gate_pass_rate") if v22_required else None
    delta_only_min = minimum_metric("phase2_delta_only_compliance_rate") if v22_required else None
    deterministic_candidate_min = (
        minimum_metric("deterministic_candidate_generation_rate") if v22_required else None
    )
    candidate_gate_min = minimum_metric("candidate_gate_pass_rate")
    top3_min = minimum_metric("minimum_primary_top_blocker_retention")

    human_admitted_count = sum(safe_int(item.get("admitted_added_finding_count")) for item in human_variants)
    human_admitted_valid = sum(safe_int(item.get("admitted_valid_added_finding_count")) for item in human_variants)
    human_admitted_high = sum(safe_int(item.get("admitted_high_value_added_count")) for item in human_variants)
    human_duplicate_count = sum(
        safe_int(item.get("admitted_duplicate_count"))
        if item.get("admitted_duplicate_count") is not None
        else round(float(item.get("admitted_duplicate_add_rate") or 0) * safe_int(item.get("admitted_added_finding_count")))
        for item in human_variants
    )
    human_precision = ratio(human_admitted_valid, human_admitted_count) if human_ready else None
    human_duplicate_rate = ratio(human_duplicate_count, human_admitted_count) if human_ready else None
    human_unsupported = sum(safe_int(item.get("admitted_unsupported_count")) for item in human_variants)
    human_overstated = sum(safe_int(item.get("admitted_overstated_count")) for item in human_variants)
    human_multiroot = sum(safe_int(item.get("admitted_multiroot_count")) for item in human_variants)

    checks = {
        "phase2_calls_complete": check(
            f"{completed_phase2_calls}/{len(phase2_calls)}",
            "100%",
            completed_phase2_calls == len(phase2_calls),
        ),
        "fairness_invariants": check(
            bool((summary.get("fairness_invariants") or {}).get("passed")),
            "true",
            (summary.get("fairness_invariants") or {}).get("passed") is True,
        ),
        "raw_field_completeness": check(
            raw_field_min,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['raw_field_completeness_min']}",
            raw_field_min is not None
            and raw_field_min >= PHASE2_ACCEPTANCE_THRESHOLDS["raw_field_completeness_min"],
        ),
        "admitted_field_completeness": check(
            admitted_field_min,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['admitted_field_completeness_min']}",
            admitted_field_min is not None
            and admitted_field_min >= PHASE2_ACCEPTANCE_THRESHOLDS["admitted_field_completeness_min"],
        ),
        "coverage_ledger_completeness": check(
            ledger_complete_min,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['ledger_completeness_min']}",
            ledger_complete_min is not None
            and ledger_complete_min >= PHASE2_ACCEPTANCE_THRESHOLDS["ledger_completeness_min"],
        ),
        "coverage_ledger_valid_rate": check(
            ledger_valid_min,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['ledger_valid_rate_min']}",
            ledger_valid_min is not None
            and ledger_valid_min >= PHASE2_ACCEPTANCE_THRESHOLDS["ledger_valid_rate_min"],
        ),
        "coverage_schema_v2_rate": check(
            coverage_schema_v2_min,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['coverage_schema_v2_rate_min']}",
            coverage_schema_v2_min is not None
            and coverage_schema_v2_min >= PHASE2_ACCEPTANCE_THRESHOLDS["coverage_schema_v2_rate_min"],
        ),
        "coverage_evidence_packet_echo_rate": check(
            evidence_packet_echo_min if v21_required else "legacy_not_required",
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['coverage_evidence_packet_echo_rate_min']}",
            (not v21_required)
            or (
                evidence_packet_echo_min is not None
                and evidence_packet_echo_min
                >= PHASE2_ACCEPTANCE_THRESHOLDS["coverage_evidence_packet_echo_rate_min"]
            ),
        ),
        "phase2_protocol_gate_pass_rate": check(
            protocol_gate_min if v22_required else "legacy_not_required",
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['phase2_protocol_gate_pass_rate_min']}",
            (not v22_required)
            or (
                protocol_gate_min is not None
                and protocol_gate_min >= PHASE2_ACCEPTANCE_THRESHOLDS["phase2_protocol_gate_pass_rate_min"]
            ),
        ),
        "phase2_delta_only_compliance_rate": check(
            delta_only_min if v22_required else "legacy_not_required",
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['phase2_delta_only_compliance_rate_min']}",
            (not v22_required)
            or (
                delta_only_min is not None
                and delta_only_min >= PHASE2_ACCEPTANCE_THRESHOLDS["phase2_delta_only_compliance_rate_min"]
            ),
        ),
        "deterministic_candidate_generation_rate": check(
            deterministic_candidate_min if v22_required else "legacy_not_required",
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['deterministic_candidate_generation_rate_min']}",
            (not v22_required)
            or (
                deterministic_candidate_min is not None
                and deterministic_candidate_min
                >= PHASE2_ACCEPTANCE_THRESHOLDS["deterministic_candidate_generation_rate_min"]
            ),
        ),
        "candidate_gate_pass_rate": check(
            candidate_gate_min,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['candidate_gate_pass_rate_min']}",
            candidate_gate_min is not None
            and candidate_gate_min >= PHASE2_ACCEPTANCE_THRESHOLDS["candidate_gate_pass_rate_min"],
        ),
        "primary_top3_retention": check(
            top3_min,
            ">=2/3",
            top3_min is not None and top3_min >= (2 / 3),
        ),
        "machine_multiroot": check(sum_metric("multiroot_finding_count"), "0", sum_metric("multiroot_finding_count") == 0),
        "unsupported_severity_change": check(
            sum_metric("unsupported_severity_change_count"),
            "0",
            sum_metric("unsupported_severity_change_count") == 0,
        ),
        "unsupported_blocking_change": check(
            sum_metric("unsupported_blocking_change_count"),
            "0",
            sum_metric("unsupported_blocking_change_count") == 0,
        ),
        "lineage_mismatch": check(sum_metric("lineage_mismatch_count"), "0", sum_metric("lineage_mismatch_count") == 0),
        "materialization_mismatch": check(
            sum_metric("materialization_mismatch_count"),
            "0",
            sum_metric("materialization_mismatch_count") == 0,
        ),
        "major_judgment_drift": check(
            sum_metric("major_judgment_drift_count"),
            "0",
            sum_metric("major_judgment_drift_count") == 0,
        ),
        "high_added_root_overlap": check(
            high_overlap_average,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['high_added_root_overlap_min']}",
            high_overlap_average is not None
            and high_overlap_average >= PHASE2_ACCEPTANCE_THRESHOLDS["high_added_root_overlap_min"],
        ),
        "human_admitted_precision": check(
            human_precision,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['admitted_precision_min']}",
            human_precision is not None
            and human_precision >= PHASE2_ACCEPTANCE_THRESHOLDS["admitted_precision_min"],
            ready=human_ready,
        ),
        "human_valid_added_count": check(
            human_admitted_valid if human_ready else None,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['valid_added_count_min']}",
            human_admitted_valid >= PHASE2_ACCEPTANCE_THRESHOLDS["valid_added_count_min"],
            ready=human_ready,
        ),
        "human_high_value_added_count": check(
            human_admitted_high if human_ready else None,
            f">={PHASE2_ACCEPTANCE_THRESHOLDS['high_value_added_count_min']}",
            human_admitted_high >= PHASE2_ACCEPTANCE_THRESHOLDS["high_value_added_count_min"],
            ready=human_ready,
        ),
        "human_duplicate_rate": check(
            human_duplicate_rate,
            f"<={PHASE2_ACCEPTANCE_THRESHOLDS['duplicate_rate_max']}",
            human_duplicate_rate is not None
            and human_duplicate_rate <= PHASE2_ACCEPTANCE_THRESHOLDS["duplicate_rate_max"],
            ready=human_ready,
        ),
        "human_unsupported": check(human_unsupported if human_ready else None, "0", human_unsupported == 0, ready=human_ready),
        "human_overstated": check(human_overstated if human_ready else None, "0", human_overstated == 0, ready=human_ready),
        "human_multiroot": check(human_multiroot if human_ready else None, "0", human_multiroot == 0, ready=human_ready),
    }
    pending_reasons = [name for name, result in checks.items() if result.get("ready") is not True]
    blocking_reasons = [
        name for name, result in checks.items() if result.get("ready") is True and result.get("passed") is not True
    ]
    status = "failed" if blocking_reasons else "pending_human_annotation" if pending_reasons else "passed"
    return {
        "applicable": True,
        "status": status,
        "eligible_for_next_stage": status == "passed",
        "phase2_variant_ids": phase2_variant_ids,
        "thresholds": dict(PHASE2_ACCEPTANCE_THRESHOLDS),
        "checks": checks,
        "blocking_reasons": blocking_reasons,
        "pending_reasons": pending_reasons,
        "high_added_root_overlap_evaluable_games": len(high_overlap_values),
    }


PHASE3_ACCEPTANCE_THRESHOLDS = {
    "protocol_gate_pass_rate_min": 1.0,
    "baseline_lock_pass_rate_min": 1.0,
    "challenge_target_correct_rate_min": 1.0,
    "challenge_evidence_locatable_rate_min": 1.0,
    "challenge_precision_min": 0.8,
    "correction_target_correct_rate_min": 1.0,
    "correction_supported_rate_min": 1.0,
    "correction_accuracy_rate_min": 0.9,
    "direct_materialization_rate_max": 0.0,
    "target_coverage_ledger_complete_rate_min": 1.0,
    "target_coverage_ledger_valid_rate_min": 1.0,
    "target_decision_overlap_min": 0.8,
    "challenge_overlap_min": 0.5,
    "correction_overlap_min": 0.5,
    "challenge_checks_complete_rate_min": 1.0,
    "challenge_checks_valid_rate_min": 1.0,
    "challenge_target_overlap_min": 0.5,
    "challenge_check_overlap_min": 0.8,
}


def build_phase3_acceptance_summary(summary: dict[str, Any]) -> dict[str, Any]:
    calls = [item for item in summary.get("calls") or [] if isinstance(item, dict)]
    phase3_calls = [
        item
        for item in calls
        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
        in PHASE3_PROTOCOL_REVISIONS
    ]
    variant_ids = sorted(
        {
            str(item.get("variant_id") or "").strip()
            for item in phase3_calls
            if str(item.get("variant_id") or "").strip()
        }
    )
    if not phase3_calls:
        return {
            "applicable": False,
            "status": "not_applicable",
            "eligible_for_next_stage": False,
            "reason": "当前 benchmark 不包含 phase3 profile。",
            "thresholds": dict(PHASE3_ACCEPTANCE_THRESHOLDS),
            "checks": {},
            "blocking_reasons": [],
            "pending_reasons": [],
        }

    completed = [item for item in phase3_calls if item.get("status") == "completed"]
    count = len(completed)
    protocol_rate = ratio(sum(bool(item.get("phase3_protocol_gate_passed")) for item in completed), count)
    lock_rate = ratio(sum(bool(item.get("phase3_baseline_lock_passed")) for item in completed), count)
    v12_calls = [
        item
        for item in completed
        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
        in {PHASE3_V12_PROTOCOL_REVISION, PHASE3_V13_PROTOCOL_REVISION}
    ]
    v12_required = bool(v12_calls)
    v13_calls = [
        item
        for item in completed
        if str(item.get("processing_profile") or item.get("protocol_profile") or "").strip().lower()
        == PHASE3_V13_PROTOCOL_REVISION
    ]
    v13_required = bool(v13_calls)
    v12_variant_ids = {
        str(item.get("variant_id") or "").strip() for item in v12_calls if str(item.get("variant_id") or "").strip()
    }
    v12_stability_rows = [
        item
        for item in summary.get("stability_comparison") or []
        if isinstance(item, dict) and str(item.get("variant_id") or "").strip() in v12_variant_ids
    ]
    ledger_complete_rate = ratio(
        sum(bool(item.get("phase3_target_coverage_ledger_complete")) for item in v12_calls), len(v12_calls)
    )
    ledger_valid_rate = ratio(
        sum(bool(item.get("phase3_target_coverage_ledger_valid")) for item in v12_calls), len(v12_calls)
    )
    challenge_checks_complete_rate = ratio(
        sum(bool(item.get("phase3_challenge_checks_complete")) for item in v13_calls), len(v13_calls)
    )
    challenge_checks_valid_rate = ratio(
        sum(bool(item.get("phase3_challenge_checks_valid")) for item in v13_calls), len(v13_calls)
    )

    def phase3_overlap(field: str) -> float | None:
        values = [float(item[field]) for item in v12_stability_rows if item.get(field) is not None]
        if values:
            return average(values)
        return 1.0 if v12_stability_rows else None

    target_decision_overlap = phase3_overlap("phase3_target_decision_overlap")
    challenge_overlap = phase3_overlap("phase3_challenge_overlap")
    correction_overlap = phase3_overlap("phase3_correction_overlap")
    challenge_target_overlap = phase3_overlap("phase3_challenge_target_overlap")
    challenge_check_overlap = phase3_overlap("phase3_challenge_check_overlap")
    materialized_count = sum(
        item.get("selected_report_owner") != "primary_locked"
        or safe_int(item.get("materialized_added_count")) != 0
        for item in completed
    )
    protected_change_count = sum(
        safe_int(item.get("unsupported_severity_change_count"))
        + safe_int(item.get("unsupported_blocking_change_count"))
        for item in completed
    )
    human = summary.get("human_metrics") if isinstance(summary.get("human_metrics"), dict) else {}
    human_phase3 = human.get("phase3") if isinstance(human.get("phase3"), dict) else {}
    human_ready = human.get("status") == "completed"

    def check(observed: Any, target: str, passed: bool, *, ready: bool = True) -> dict[str, Any]:
        return {
            "ready": ready,
            "passed": bool(passed) if ready else None,
            "observed": observed,
            "target": target,
        }

    challenge_count = safe_int(human_phase3.get("challenge_count"))
    correction_count = safe_int(human_phase3.get("correction_count"))
    challenge_target_rate = human_phase3.get("challenge_target_correct_rate")
    challenge_evidence_rate = human_phase3.get("challenge_evidence_locatable_rate")
    challenge_precision = human_phase3.get("challenge_precision")
    correction_target_rate = human_phase3.get("correction_target_correct_rate")
    correction_supported_rate = human_phase3.get("correction_supported_rate")
    correction_accuracy_rate = human_phase3.get("correction_accuracy_rate")
    challenge_human_ready = human_ready and challenge_count > 0
    correction_human_ready = human_ready and correction_count > 0
    checks = {
        "phase3_calls_complete": check(
            f"{count}/{len(phase3_calls)}",
            "100%",
            count == len(phase3_calls),
        ),
        "fairness_invariants": check(
            bool((summary.get("fairness_invariants") or {}).get("passed")),
            "true",
            (summary.get("fairness_invariants") or {}).get("passed") is True,
        ),
        "protocol_gate_pass_rate": check(
            protocol_rate,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['protocol_gate_pass_rate_min']}",
            protocol_rate is not None
            and protocol_rate >= PHASE3_ACCEPTANCE_THRESHOLDS["protocol_gate_pass_rate_min"],
        ),
        "baseline_lock_pass_rate": check(
            lock_rate,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['baseline_lock_pass_rate_min']}",
            lock_rate is not None
            and lock_rate >= PHASE3_ACCEPTANCE_THRESHOLDS["baseline_lock_pass_rate_min"],
        ),
        "direct_materialization_rate": check(
            ratio(materialized_count, count),
            "0",
            materialized_count == 0,
        ),
        "protected_field_change_count": check(protected_change_count, "0", protected_change_count == 0),
        "target_coverage_ledger_complete_rate": check(
            ledger_complete_rate if v12_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['target_coverage_ledger_complete_rate_min']}",
            (not v12_required)
            or (
                ledger_complete_rate is not None
                and ledger_complete_rate
                >= PHASE3_ACCEPTANCE_THRESHOLDS["target_coverage_ledger_complete_rate_min"]
            ),
        ),
        "target_coverage_ledger_valid_rate": check(
            ledger_valid_rate if v12_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['target_coverage_ledger_valid_rate_min']}",
            (not v12_required)
            or (
                ledger_valid_rate is not None
                and ledger_valid_rate
                >= PHASE3_ACCEPTANCE_THRESHOLDS["target_coverage_ledger_valid_rate_min"]
            ),
        ),
        "target_decision_overlap": check(
            target_decision_overlap if v12_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['target_decision_overlap_min']}",
            (not v12_required)
            or (
                target_decision_overlap is not None
                and target_decision_overlap >= PHASE3_ACCEPTANCE_THRESHOLDS["target_decision_overlap_min"]
            ),
        ),
        "challenge_overlap": check(
            challenge_overlap if v12_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_overlap_min']}",
            (not v12_required)
            or (
                challenge_overlap is not None
                and challenge_overlap >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_overlap_min"]
            ),
        ),
        "correction_overlap": check(
            correction_overlap if v12_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['correction_overlap_min']}",
            (not v12_required)
            or (
                correction_overlap is not None
                and correction_overlap >= PHASE3_ACCEPTANCE_THRESHOLDS["correction_overlap_min"]
            ),
        ),
        "challenge_checks_complete_rate": check(
            challenge_checks_complete_rate if v13_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_checks_complete_rate_min']}",
            (not v13_required)
            or (
                challenge_checks_complete_rate is not None
                and challenge_checks_complete_rate
                >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_checks_complete_rate_min"]
            ),
        ),
        "challenge_checks_valid_rate": check(
            challenge_checks_valid_rate if v13_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_checks_valid_rate_min']}",
            (not v13_required)
            or (
                challenge_checks_valid_rate is not None
                and challenge_checks_valid_rate
                >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_checks_valid_rate_min"]
            ),
        ),
        "challenge_target_overlap": check(
            challenge_target_overlap if v13_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_target_overlap_min']}",
            (not v13_required)
            or (
                challenge_target_overlap is not None
                and challenge_target_overlap >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_target_overlap_min"]
            ),
        ),
        "challenge_check_overlap": check(
            challenge_check_overlap if v13_required else "legacy_not_required",
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_check_overlap_min']}",
            (not v13_required)
            or (
                challenge_check_overlap is not None
                and challenge_check_overlap >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_check_overlap_min"]
            ),
        ),
        "human_challenge_target_correct_rate": check(
            challenge_target_rate,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_target_correct_rate_min']}",
            challenge_target_rate is not None
            and challenge_target_rate >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_target_correct_rate_min"],
            ready=challenge_human_ready,
        ),
        "human_challenge_evidence_locatable_rate": check(
            challenge_evidence_rate,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_evidence_locatable_rate_min']}",
            challenge_evidence_rate is not None
            and challenge_evidence_rate >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_evidence_locatable_rate_min"],
            ready=challenge_human_ready,
        ),
        "human_challenge_precision": check(
            challenge_precision,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['challenge_precision_min']}",
            challenge_precision is not None
            and challenge_precision >= PHASE3_ACCEPTANCE_THRESHOLDS["challenge_precision_min"],
            ready=challenge_human_ready,
        ),
        "human_correction_target_correct_rate": check(
            correction_target_rate,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['correction_target_correct_rate_min']}",
            correction_target_rate is not None
            and correction_target_rate >= PHASE3_ACCEPTANCE_THRESHOLDS["correction_target_correct_rate_min"],
            ready=correction_human_ready,
        ),
        "human_correction_supported_rate": check(
            correction_supported_rate,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['correction_supported_rate_min']}",
            correction_supported_rate is not None
            and correction_supported_rate >= PHASE3_ACCEPTANCE_THRESHOLDS["correction_supported_rate_min"],
            ready=correction_human_ready,
        ),
        "human_correction_accuracy_rate": check(
            correction_accuracy_rate,
            f">={PHASE3_ACCEPTANCE_THRESHOLDS['correction_accuracy_rate_min']}",
            correction_accuracy_rate is not None
            and correction_accuracy_rate >= PHASE3_ACCEPTANCE_THRESHOLDS["correction_accuracy_rate_min"],
            ready=correction_human_ready,
        ),
    }
    pending_reasons = [name for name, result in checks.items() if result.get("ready") is not True]
    blocking_reasons = [
        name
        for name, result in checks.items()
        if result.get("ready") is True and result.get("passed") is not True
    ]
    status = "failed" if blocking_reasons else "pending_human_annotation" if pending_reasons else "passed"
    return {
        "applicable": True,
        "status": status,
        "eligible_for_next_stage": status == "passed",
        "phase3_variant_ids": variant_ids,
        "thresholds": dict(PHASE3_ACCEPTANCE_THRESHOLDS),
        "checks": checks,
        "blocking_reasons": blocking_reasons,
        "pending_reasons": pending_reasons,
        "human_challenge_count": challenge_count if human_ready else None,
        "human_correction_count": correction_count if human_ready else None,
    }


def build_annotation_items(
    *,
    game: FrozenGame,
    variant_id: str,
    repeat_index: int,
    added_findings: list[dict[str, Any]],
    admission_results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, finding in enumerate(added_findings, start=1):
        admission = (
            admission_results[index - 1]
            if isinstance(admission_results, list)
            and index - 1 < len(admission_results)
            and isinstance(admission_results[index - 1], dict)
            else {}
        )
        item = {
            "annotation_id": f"{variant_id}-{game.name}-R{repeat_index:02d}-A{index:03d}",
            "variant_id": variant_id,
            "game": game.name,
            "repeat": repeat_index,
            "change_type": "added",
            "candidate_issue_id": finding.get("candidate_issue_id") or finding.get("issue_id") or "",
            "audit_key": finding.get("audit_key") or admission.get("coverage_audit_key") or "",
            "control_key": finding.get("control_key") or admission.get("coverage_control_key") or "",
            "title": finding.get("title") or finding.get("canonical_title") or "",
            "current_state": finding.get("current_state") or "",
            "evidence": finding.get("evidence") or "",
            "risk": finding.get("risk") or "",
            "suggestion": finding.get("suggestion") or "",
            "severity": finding.get("severity") or "",
            "blocking": finding.get("blocking") or "",
            "confidence": finding.get("confidence") or "",
            "primary_overlap_check": finding.get("primary_overlap_check") or "",
            "independent_root_cause": finding.get("independent_root_cause") or "",
            "root_cause_count": finding.get("root_cause_count"),
            "root_causes": finding.get("root_causes") or [],
            "fact_check": finding.get("fact_check") or {},
            "severity_basis": finding.get("severity_basis") or "",
            "added_admission_status": admission.get("status") or "not_evaluated",
            "added_admission_reasons": admission.get("reasons") or [],
            "primary_duplicate_matches": admission.get("primary_duplicate_matches") or [],
            "broad_primary_duplicate_matches": admission.get("broad_primary_duplicate_matches") or [],
            "reviewer_notes": "",
        }
        for field in ANNOTATION_FIELDS:
            item[field] = None
        items.append(item)
    return items


def field_completeness(findings: list[dict[str, Any]]) -> float | None:
    if not findings:
        return None
    present = 0
    total = len(findings) * len(ADDED_REQUIRED_FIELDS)
    for finding in findings:
        present += sum(bool(str(finding.get(field) or "").strip()) for field in ADDED_REQUIRED_FIELDS)
    return round(present / total, 4) if total else None


def collect_secondary_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for finding in iter_report_findings(report)
        if str(finding.get("finding_source") or "") == "secondary_reviewer"
    ]


def iter_report_findings(report: dict[str, Any]):
    for dimension in report.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        for finding in dimension.get("findings") or []:
            if isinstance(finding, dict):
                yield finding
    for finding in report.get("cross_document_issues") or []:
        if isinstance(finding, dict):
            yield finding


def report_top_blocker_keys(report: dict[str, Any]) -> set[str]:
    return {root_key(item) for item in (report.get("top_blockers") or []) if isinstance(item, dict) and root_key(item)}


def top_blocker_retention(primary: dict[str, Any], selected: dict[str, Any]) -> float | None:
    primary_keys = report_top_blocker_keys(primary)
    if not primary_keys:
        return None
    return round(len(primary_keys & report_top_blocker_keys(selected)) / len(primary_keys), 4)


def root_key(finding: dict[str, Any]) -> str:
    audit_key = str(finding.get("audit_key") or "").strip()
    control_key = str(finding.get("control_key") or "").strip()
    if audit_key and control_key:
        return f"control:{audit_key}:{control_key}"
    normalized = build_dual_pass_secondary_finding(finding, secondary_model="variant")
    cluster = identify_root_cause_cluster(normalized)
    if cluster:
        return f"cluster:{cluster}"
    canonical_issue_id = inferred_canonical_issue_id(normalized)
    if canonical_issue_id:
        return f"issue:{canonical_issue_id}"
    title = normalize_compare_text(str(finding.get("title") or finding.get("canonical_title") or ""))
    return f"title:{title}" if title else ""


def is_high_finding(finding: dict[str, Any]) -> bool:
    severity = normalize_severity(finding.get("severity"))
    blocking = str(finding.get("blocking") or "").strip().lower()
    return severity == "high" or blocking in {"block_dev", "阻塞开发"}


def normalize_severity(value: Any) -> str:
    text = str(value or "").strip().lower()
    return {"高": "high", "中": "medium", "低": "low"}.get(text, text)


def severity_consistency(items: list[dict[str, Any]]) -> float | None:
    if len(items) < 2:
        return None
    maps = [item.get("added_severity_by_root") or {} for item in items]
    common = set(maps[0])
    for mapping in maps[1:]:
        common &= set(mapping)
    if not common:
        return None if all(not mapping for mapping in maps) else 0.0
    consistent = sum(len({str(mapping.get(key)) for mapping in maps}) == 1 for key in common)
    return round(consistent / len(common), 4)


def set_overlap(sets: list[set[str]]) -> float | None:
    if len(sets) < 2:
        return None
    union = set().union(*sets)
    if not union:
        return None
    common = set(sets[0])
    for values in sets[1:]:
        common &= values
    return round(len(common) / len(union), 4)


def render_blinded_benchmark_markdown(summary: dict[str, Any]) -> str:
    completion = summary.get("completion") or {}
    fairness = summary.get("fairness_invariants") or {}
    lines = [
        "# Secondary 盲测待标注摘要",
        "",
        "## 实验完整性",
        "",
        f"- 预期 Secondary 调用：{summary.get('design', {}).get('expected_secondary_calls', 0)}",
        f"- 已完成：{completion.get('completed_secondary_calls', 0)}",
        f"- 失败：{completion.get('failed_secondary_calls', 0)}",
        f"- 全部可配对：{'是' if completion.get('all_calls_paired') else '否'}",
        f"- Primary 调用：{summary.get('design', {}).get('primary_calls', 0)}",
        f"- 视觉调用：{summary.get('design', {}).get('vision_calls', 0)}",
        f"- 公平性不变量：{'通过' if fairness.get('passed') else '未通过'}",
        "",
        "## 盲测说明",
        "",
        "公开产物仅显示 Variant A / B。内部模型、profile、Prompt、协议和自动验收数据均保存在 `_private`，人工标注完成前不要打开。",
        "",
        "## 变体公开汇总",
        "",
        "| 变体 | 完成/预期 | Candidate 通过率 | 声称/准入新增 | 最低 Top3 保留率 | 原始/准入字段完整率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary.get("variant_metrics") or []:
        lines.append(
            "| {variant} | {completed}/{expected} | {gate} | {claimed}/{admitted} | {retention} | {completeness}/{admitted_completeness} |".format(
                variant=item.get("variant_id"),
                completed=item.get("completed_calls"),
                expected=item.get("expected_calls"),
                gate=format_metric(item.get("candidate_gate_pass_rate")),
                claimed=format_metric(item.get("average_claimed_added_count"), percent=False),
                admitted=format_metric(item.get("average_admitted_added_count"), percent=False),
                retention=format_metric(item.get("minimum_primary_top_blocker_retention")),
                completeness=format_metric(item.get("average_field_completeness")),
                admitted_completeness=format_metric(item.get("average_admitted_field_completeness")),
            )
        )
    lines.extend(
        [
            "",
            "## 人工验收状态",
            "",
            "当前为 `pending_human_annotation`。完成公开 `human_annotation_template.json` 后，才能解盲并生成完整机器与人工验收结果。",
            "",
        ]
    )
    return "\n".join(lines)


def render_benchmark_markdown(summary: dict[str, Any]) -> str:
    completion = summary.get("completion") or {}
    fairness = summary.get("fairness_invariants") or {}
    phase3_acceptance = summary.get("phase3_acceptance") or {}
    phase3_only = bool(phase3_acceptance.get("applicable")) and not bool(
        (summary.get("phase2_acceptance") or {}).get("applicable")
    )
    lines = [
        "# Secondary 公平基线对照摘要",
        "",
        "## 实验完整性",
        "",
        f"- 预期 Secondary 调用：{summary.get('design', {}).get('expected_secondary_calls', 0)}",
        f"- 已完成：{completion.get('completed_secondary_calls', 0)}",
        f"- 失败：{completion.get('failed_secondary_calls', 0)}",
        f"- 全部可配对：{'是' if completion.get('all_calls_paired') else '否'}",
        f"- Primary 调用：{summary.get('design', {}).get('primary_calls', 0)}",
        f"- 视觉调用：{summary.get('design', {}).get('vision_calls', 0)}",
        f"- 公平性不变量：{'通过' if fairness.get('passed') else '未通过'}",
        f"- 对照变量：{fairness.get('comparison_axis') or summary.get('design', {}).get('comparison_axis') or 'provider'}",
        f"- 仅预定变量不同：{'是' if fairness.get('only_intended_variable_varies', fairness.get('only_secondary_provider_varies')) else '否'}",
        "",
        "## 盲测说明",
        "",
        "公开产物仅显示 Variant A / B。完成人工标注前不要打开 `_private/provider_mapping.json`。",
    ]
    stability = summary.get("stability_comparison") or []
    if phase3_only:
        lines.extend(
            [
                "",
                "## Phase3 变体汇总",
                "",
                "| 变体 | 完成/预期 | 协议门槛 | 基线锁定 | 目标账本完整/合法 | 平均 Challenge | 平均 Correction | 平均 abstain | Top3 保留 |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in summary.get("variant_metrics") or []:
            lines.append(
                "| {variant} | {completed}/{expected} | {protocol} | {baseline} | {ledger_complete}/{ledger_valid} | {challenge} | {correction} | {abstain} | {retention} |".format(
                    variant=item.get("variant_id"),
                    completed=item.get("completed_calls"),
                    expected=item.get("expected_calls"),
                    protocol=format_metric(item.get("phase3_protocol_gate_pass_rate")),
                    baseline=format_metric(item.get("phase3_baseline_lock_pass_rate")),
                    ledger_complete=format_metric(item.get("phase3_target_coverage_ledger_complete_rate")),
                    ledger_valid=format_metric(item.get("phase3_target_coverage_ledger_valid_rate")),
                    challenge=format_metric(item.get("average_phase3_challenge_accepted_count"), percent=False),
                    correction=format_metric(item.get("average_phase3_correction_accepted_count"), percent=False),
                    abstain=format_metric(item.get("average_phase3_correction_abstained_count"), percent=False),
                    retention=format_metric(item.get("minimum_primary_top_blocker_retention")),
                )
            )
        lines.extend(
            [
                "",
                "## Phase3 复跑稳定性",
                "",
                "| 变体 | 游戏 | 目标决策重合 | Challenge target 重合 | 六类检查重合 | Challenge 语义重合 | Correction 重合 | Top blocker 重合 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in stability:
            lines.append(
                "| {variant} | {game} | {target_decision} | {challenge_target} | {challenge_check} | {challenge} | {correction} | {blocker} |".format(
                    variant=item.get("variant_id"),
                    game=item.get("game"),
                    target_decision=format_metric(item.get("phase3_target_decision_overlap")),
                    challenge_target=format_metric(item.get("phase3_challenge_target_overlap")),
                    challenge_check=format_metric(item.get("phase3_challenge_check_overlap")),
                    challenge=format_metric(item.get("phase3_challenge_overlap")),
                    correction=format_metric(item.get("phase3_correction_overlap")),
                    blocker=format_metric(item.get("top_blocker_overlap")),
                )
            )
    else:
        lines.extend(
            [
                "",
                "## 变体汇总",
                "",
                "| 变体 | 完成/预期 | Candidate 通过率 | 声称/准入新增 | 最低 Top3 保留率 | 原始/准入字段完整率 | Ledger 完整/合法率 | 证据包回显率 | 协议门槛/Delta-only/确定性Candidate |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in summary.get("variant_metrics") or []:
            lines.append(
                "| {variant} | {completed}/{expected} | {gate} | {claimed}/{admitted} | {retention} | {completeness}/{admitted_completeness} | {ledger_completeness}/{ledger_valid} | {packet_echo} | {protocol_gate}/{delta_only}/{deterministic_candidate} |".format(
                    variant=item.get("variant_id"),
                    completed=item.get("completed_calls"),
                    expected=item.get("expected_calls"),
                    gate=format_metric(item.get("candidate_gate_pass_rate")),
                    claimed=format_metric(item.get("average_claimed_added_count"), percent=False),
                    admitted=format_metric(item.get("average_admitted_added_count"), percent=False),
                    retention=format_metric(item.get("minimum_primary_top_blocker_retention")),
                    completeness=format_metric(item.get("average_field_completeness")),
                    admitted_completeness=format_metric(item.get("average_admitted_field_completeness")),
                    ledger_completeness=format_metric(item.get("average_coverage_ledger_completeness")),
                    ledger_valid=format_metric(item.get("coverage_ledger_valid_rate")),
                    packet_echo=format_metric(item.get("coverage_evidence_packet_echo_rate")),
                    protocol_gate=format_metric(item.get("phase2_protocol_gate_pass_rate")),
                    delta_only=format_metric(item.get("phase2_delta_only_compliance_rate")),
                    deterministic_candidate=format_metric(item.get("deterministic_candidate_generation_rate")),
                )
            )
        lines.extend(
            [
                "",
                "## 复跑稳定性",
                "",
                "| 变体 | 游戏 | 高价值新增根因重合 | confirmed audit key 重合 | Candidate 采用一致 |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for item in stability:
            lines.append(
                "| {variant} | {game} | {high_overlap} | {coverage_overlap} | {candidate_consistent} |".format(
                    variant=item.get("variant_id"),
                    game=item.get("game"),
                    high_overlap=format_metric(item.get("high_added_root_overlap")),
                    coverage_overlap=format_metric(item.get("coverage_confirmed_overlap")),
                    candidate_consistent="是" if item.get("candidate_adoption_consistent") else "否",
                )
            )
    acceptance = summary.get("phase2_acceptance") or {}
    if acceptance.get("applicable"):
        lines.extend(
            [
                "",
                "## Phase2 自动验收",
                "",
                f"- 状态：{acceptance.get('status') or 'unknown'}",
                f"- 可进入下一阶段：{'是' if acceptance.get('eligible_for_next_stage') else '否'}",
                f"- 阻断项：{', '.join(str(item) for item in acceptance.get('blocking_reasons') or []) or '无'}",
                f"- 待人工项：{', '.join(str(item) for item in acceptance.get('pending_reasons') or []) or '无'}",
                "",
                "| 检查项 | 当前值 | 门槛 | 结果 |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for name, result in (acceptance.get("checks") or {}).items():
            if not isinstance(result, dict):
                continue
            outcome = "待人工" if result.get("ready") is not True else "通过" if result.get("passed") else "未通过"
            observed = result.get("observed")
            lines.append(f"| {name} | {observed if observed is not None else '-'} | {result.get('target') or '-'} | {outcome} |")
    if phase3_acceptance.get("applicable"):
        lines.extend(
            [
                "",
                "## Phase3 Challenge/Correct 自动验收",
                "",
                f"- 状态：{phase3_acceptance.get('status') or 'unknown'}",
                f"- 可进入下一阶段：{'是' if phase3_acceptance.get('eligible_for_next_stage') else '否'}",
                f"- 阻断项：{', '.join(str(item) for item in phase3_acceptance.get('blocking_reasons') or []) or '无'}",
                f"- 待人工项：{', '.join(str(item) for item in phase3_acceptance.get('pending_reasons') or []) or '无'}",
                "",
                "| 检查项 | 当前值 | 门槛 | 结果 |",
                "| --- | ---: | ---: | --- |",
            ]
        )
        for name, result in (phase3_acceptance.get("checks") or {}).items():
            if not isinstance(result, dict):
                continue
            outcome = "待人工" if result.get("ready") is not True else "通过" if result.get("passed") else "未通过"
            observed = result.get("observed")
            lines.append(
                f"| {name} | {observed if observed is not None else '-'} | {result.get('target') or '-'} | {outcome} |"
            )
    human_metrics = summary.get("human_metrics") or {}
    lines.extend(["", "## 人工验收状态", ""])
    if human_metrics.get("status") == "completed":
        phase3_human = human_metrics.get("phase3") or {}
        phase3_item_count = int(phase3_human.get("challenge_count") or 0) + int(
            phase3_human.get("correction_count") or 0
        )
        added_annotation_count = sum(
            int(item.get("annotated_added_finding_count") or 0)
            for item in human_metrics.get("variants") or []
            if isinstance(item, dict)
        )
        if added_annotation_count or not phase3_item_count:
            lines.extend(
                [
                    f"- 已标注新增问题：{added_annotation_count}",
                    f"- 有效新增：{human_metrics.get('valid_added_finding_count', 0)}",
                    f"- 有效新增率：{format_metric(human_metrics.get('added_finding_precision'))}",
                    f"- 高价值新增：{human_metrics.get('high_value_added_count', 0)}",
                    f"- 重复新增率：{format_metric(human_metrics.get('duplicate_add_rate'))}",
                    "",
                    "| 变体 | 标注数 | 有效新增 | 有效率 | 高价值新增 | 重复率 | 可执行率 |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for item in human_metrics.get("variants") or []:
                lines.append(
                    "| {variant} | {total} | {valid} | {precision} | {high} | {duplicate} | {actionable} |".format(
                        variant=item.get("variant_id"),
                        total=item.get("annotated_added_finding_count"),
                        valid=item.get("valid_added_finding_count"),
                        precision=format_metric(item.get("added_finding_precision")),
                        high=item.get("high_value_added_count"),
                        duplicate=format_metric(item.get("duplicate_add_rate")),
                        actionable=format_metric(item.get("actionable_rate")),
                    )
                )
        if phase3_item_count:
            lines.extend(
                [
                    *([""] if added_annotation_count else []),
                    f"- 已标注 Phase3 审核项：{phase3_item_count}",
                    "",
                    "### Phase3 人工判断",
                    "",
                    f"- Challenge 数：{phase3_human.get('challenge_count', 0)}",
                    f"- Challenge 目标正确率：{format_metric(phase3_human.get('challenge_target_correct_rate'))}",
                    f"- Challenge 证据可定位率：{format_metric(phase3_human.get('challenge_evidence_locatable_rate'))}",
                    f"- Challenge 有效率：{format_metric(phase3_human.get('challenge_precision'))}",
                    f"- Correction 数：{phase3_human.get('correction_count', 0)}",
                    f"- Correction 目标正确率：{format_metric(phase3_human.get('correction_target_correct_rate'))}",
                    f"- Correction 证据支持率：{format_metric(phase3_human.get('correction_supported_rate'))}",
                    f"- Correction 人工准确率：{format_metric(phase3_human.get('correction_accuracy_rate'))}",
                    f"- Correction 可安全应用率：{format_metric(phase3_human.get('safe_to_apply_rate'))}",
                    f"- 已确定性应用 Correction：{phase3_human.get('human_applied_correction_count', 0)}",
                    f"- 评分发生变化的报告：{phase3_human.get('score_change_count', 0)}",
                ]
            )
            application = summary.get("phase3_human_application") or {}
            outputs = [item for item in application.get("outputs") or [] if isinstance(item, dict)]
            if outputs:
                lines.extend(
                    [
                        "",
                        "### V1.2 人工确认后评分重算",
                        "",
                        "| 变体 | 游戏 | 复跑 | 应用修正 | 高风险前/后 | 评分前/后 |",
                        "| --- | --- | ---: | ---: | ---: | ---: |",
                    ]
                )
                for item in outputs:
                    lines.append(
                        "| {variant} | {game} | {repeat} | {applied} | {high_before}/{high_after} | {score_before}/{score_after} |".format(
                            variant=item.get("variant_id"),
                            game=item.get("game"),
                            repeat=item.get("repeat"),
                            applied=item.get("applied_correction_count"),
                            high_before=item.get("high_risk_before"),
                            high_after=item.get("high_risk_after"),
                            score_before=item.get("score_before"),
                            score_after=item.get("score_after"),
                        )
                    )
    else:
        if phase3_acceptance.get("applicable"):
            lines.append(
                "当前为 `pending_human_annotation`。完成 `human_annotation_template.json` 中的 Challenge/Correction 判断后，才能计算 Phase3 人工指标并决定是否进入下一阶段。"
            )
        else:
            lines.append(
                "当前为 `pending_human_annotation`。只有完成 `human_annotation_template.json` 后，才能计算有效新增率、重复率和高价值新增数，并决定是否切换默认 Secondary。"
            )
    lines.append("")
    return "\n".join(lines)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_json(payload: Any) -> str:
    return hash_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def average(values: Any) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return round(sum(numbers) / len(numbers), 4) if numbers else None


def format_metric(value: Any, *, percent: bool = True) -> str:
    if value is None:
        return "-"
    number = float(value)
    return f"{number * 100:.1f}%" if percent else f"{number:.2f}"


__all__ = [
    "AnnotationFinalizeResult",
    "SecondaryBenchmarkResult",
    "build_invariant_summary",
    "discover_frozen_game_dirs",
    "freeze_game",
    "finalize_secondary_benchmark_annotations",
    "reprocess_saved_secondary_responses",
    "resolve_secondary_provider",
    "run_secondary_benchmark",
]
