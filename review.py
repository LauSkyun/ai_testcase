from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rad_review.agent import ReviewAgent, RunResult
from rad_review.docx_reader import discover_docx, discover_docx_for_game, group_docx_by_game, sanitize_filename
from rad_review.model_client import ModelConfig, OpenAICompatibleClient
from rad_review.secondary_benchmark import (
    finalize_secondary_benchmark_annotations,
    reprocess_saved_secondary_responses,
    run_secondary_benchmark,
)


@dataclass
class RunOptions:
    timeout: int
    model_retries: int
    max_context_chars: int
    analyze_images: bool
    image_limit: int
    log_echo: bool | None
    require_model: bool
    review_mode: str


@dataclass
class ProbeCheckResult:
    label: str
    status: str
    model: str
    base_url: str
    wire_api: str
    response: str
    error: str = ""


@dataclass
class ProbeResult:
    review_mode: str
    checks: list[ProbeCheckResult]

    @property
    def is_success(self) -> bool:
        return bool(self.checks) and all(check.status == "ok" for check in self.checks)

    @property
    def model(self) -> str:
        return self.checks[0].model if self.checks else ""

    @property
    def base_url(self) -> str:
        return self.checks[0].base_url if self.checks else ""

    @property
    def wire_api(self) -> str:
        return self.checks[0].wire_api if self.checks else ""

    @property
    def response(self) -> str:
        return self.checks[0].response if self.checks else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze game requirement and numeric design DOCX files before review or test-case design."
    )
    parser.add_argument(
        "--input",
        "-i",
        default="requirements",
        help="A .docx file or a directory containing .docx files, including requirements/<game>/*.docx folder layouts.",
    )
    parser.add_argument("--output", "-o", default="reports", help="Directory for reports, manifests, and extracted images.")
    parser.add_argument(
        "--game",
        help="Only analyze .docx files matching this game, by filename or first-level project folder, for example 小鸡 or Racing.",
    )
    parser.add_argument(
        "--auto-group",
        action="store_true",
        help="Group multiple games in the input directory by first-level project folder or filename, and generate one independent report per game.",
    )
    parser.add_argument("--extract-only", action="store_true", help="Only parse documents and write extraction artifacts.")
    parser.add_argument(
        "--review-mode",
        choices=("fast", "strict", "benchmark", "fusion", "dual_pass"),
        default="fast",
        help="Review workflow: fast runs one analysis, strict adds an audit pass, benchmark stores deterministic debug artifacts, fusion merges primary and secondary model reviews, dual_pass runs a primary draft plus a structured Secondary delta review and a system-built candidate report.",
    )
    parser.add_argument("--skip-images", action="store_true", help="Extract image files but do not send them to a vision model.")
    parser.add_argument("--image-limit", type=int, default=100, help="Maximum images to analyze with the vision model.")
    parser.add_argument("--timeout", type=int, default=600, help="HTTP timeout in seconds for model calls.")
    parser.add_argument(
        "--model-retries",
        type=int,
        default=3,
        help="Retries after the initial text-model request fails with a transient error. Default: 3.",
    )
    parser.add_argument("--max-context-chars", type=int, default=120000, help="Maximum characters sent to the text model.")
    parser.add_argument(
        "--log-echo",
        action="store_true",
        help="Echo run log lines to stderr in addition to writing run.log.",
    )
    parser.add_argument(
        "--require-model",
        action="store_true",
        help="Exit with an error when AI_BASE_URL, AI_API_KEY, or AI_MODEL is missing.",
    )
    parser.add_argument(
        "--probe-model",
        action="store_true",
        help="Send a minimal text request with the current model settings, without parsing any DOCX files. In fusion/dual_pass mode, probe both AI_PRIMARY_* and AI_SECONDARY_*.",
    )
    parser.add_argument(
        "--secondary-replay-from",
        help="Run a frozen-Primary Secondary A/B benchmark from one dual_pass game directory or a grouped batch directory.",
    )
    parser.add_argument(
        "--secondary-provider",
        action="append",
        help="Named Secondary provider via AI_PROVIDER_<NAME>_* variables. Use two distinct providers for provider A/B, or one provider with --secondary-profile.",
    )
    parser.add_argument(
        "--secondary-profile",
        action="append",
        choices=("baseline", "phase2", "phase3_v1", "phase3_v1_1", "phase3_v1_2", "phase3_v1_3"),
        help="Secondary prompt/profile. phase3_v1_3 adds exhaustive challenge checks and a fixed decision/action matrix while preserving human-approved deterministic scoring.",
    )
    parser.add_argument(
        "--secondary-repeats",
        type=int,
        default=2,
        help="Secondary calls per provider per game in replay mode. Minimum and default: 2.",
    )
    parser.add_argument(
        "--secondary-benchmark-finalize",
        help="Validate a completed blind human_annotation_template.json and write annotation metrics back to the benchmark summary.",
    )
    parser.add_argument(
        "--secondary-benchmark-reprocess",
        help="Reprocess saved raw Secondary responses without model calls in a new derived directory; the source benchmark is not overwritten.",
    )
    parser.add_argument(
        "--secondary-reprocess-profile",
        choices=("baseline", "phase2", "phase3_v1", "phase3_v1_1", "phase3_v1_2", "phase3_v1_3"),
        help="Apply this deterministic processing/admission profile while reprocessing saved raw responses; does not call a model.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.secondary_reprocess_profile and not args.secondary_benchmark_reprocess:
        print(
            "[RAD] failed: --secondary-reprocess-profile requires --secondary-benchmark-reprocess.",
            file=sys.stderr,
        )
        return 1
    if args.probe_model:
        try:
            result = probe_text_model(timeout=args.timeout, review_mode=args.review_mode)
        except Exception as exc:  # keep CLI errors readable for DingTalk wrappers
            print(f"[RAD] failed: {exc}", file=sys.stderr)
            return 1
        print_probe_result(result)
        return 0 if result.is_success else 1

    if args.secondary_benchmark_finalize:
        try:
            finalized = finalize_secondary_benchmark_annotations(Path(args.secondary_benchmark_finalize))
        except Exception as exc:
            print(f"[RAD] failed: {exc}", file=sys.stderr)
            return 1
        print(f"[RAD] annotation results: {finalized.results_path}")
        print(f"[RAD] benchmark summary: {finalized.summary_path}")
        print(f"[RAD] annotated items: {finalized.annotated_item_count}")
        return 0

    if args.secondary_benchmark_reprocess:
        try:
            reprocessed = reprocess_saved_secondary_responses(
                Path(args.secondary_benchmark_reprocess),
                processing_profile=args.secondary_reprocess_profile,
            )
        except Exception as exc:
            print(f"[RAD] failed: {exc}", file=sys.stderr)
            return 1
        print(f"[RAD] secondary benchmark: {reprocessed.run_dir}")
        print(f"[RAD] summary: {reprocessed.summary_json_path}")
        print(f"[RAD] calls: {reprocessed.completed_calls}/{reprocessed.expected_calls}")
        return 0 if reprocessed.is_complete else 1

    if args.secondary_replay_from:
        if args.game or args.auto_group or args.extract_only:
            print(
                "[RAD] failed: --secondary-replay-from cannot be combined with --game, --auto-group, or --extract-only.",
                file=sys.stderr,
            )
            return 1
        if args.model_retries < 0:
            print("[RAD] failed: --model-retries must be 0 or greater.", file=sys.stderr)
            return 1
        try:
            benchmark = run_secondary_benchmark(
                Path(args.secondary_replay_from),
                Path(args.output),
                args.secondary_provider or ["qwen", "deepseek"],
                repeats=args.secondary_repeats,
                timeout=args.timeout,
                model_retries=args.model_retries,
                protocol_profiles=args.secondary_profile,
            )
        except Exception as exc:
            print(f"[RAD] failed: {exc}", file=sys.stderr)
            return 1
        print(f"[RAD] secondary benchmark: {benchmark.run_dir}")
        print(f"[RAD] summary: {benchmark.summary_json_path}")
        print(f"[RAD] annotation template: {benchmark.annotation_json_path}")
        print(f"[RAD] calls: {benchmark.completed_calls}/{benchmark.expected_calls}")
        return 0 if benchmark.is_complete else 1

    if args.game and args.auto_group:
        print("[RAD] failed: --game and --auto-group cannot be used together.", file=sys.stderr)
        return 1
    if args.model_retries < 0:
        print("[RAD] failed: --model-retries must be 0 or greater.", file=sys.stderr)
        return 1

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    options = RunOptions(
        timeout=args.timeout,
        model_retries=args.model_retries,
        max_context_chars=args.max_context_chars,
        analyze_images=not args.skip_images,
        image_limit=args.image_limit,
        log_echo=True if args.log_echo else None,
        require_model=args.require_model,
        review_mode=args.review_mode,
    )

    try:
        if args.auto_group:
            return run_auto_group(input_path, output_dir, args.extract_only, options)
        doc_paths = resolve_single_run_documents(input_path, args.game)
        result = run_single(input_path, output_dir, args.extract_only, options, document_paths=doc_paths)
    except Exception as exc:  # keep CLI errors readable for DingTalk wrappers
        print(f"[RAD] failed: {exc}", file=sys.stderr)
        return 1

    print_result(result)
    return 0 if not result.warning else 2 if args.require_model else 0


def probe_text_model(timeout: int, review_mode: str = "fast") -> ProbeResult:
    if review_mode in {"fusion", "dual_pass"}:
        checks = [
            probe_single_text_model("primary", ModelConfig.from_prefixed_env("AI_PRIMARY"), timeout, "AI_PRIMARY"),
            probe_single_text_model("secondary", ModelConfig.from_prefixed_env("AI_SECONDARY"), timeout, "AI_SECONDARY"),
        ]
        return ProbeResult(review_mode=review_mode, checks=checks)

    checks = [probe_single_text_model("default", ModelConfig.from_env(), timeout, "AI")]
    return ProbeResult(review_mode=review_mode, checks=checks)


def probe_single_text_model(label: str, config: ModelConfig, timeout: int, prefix: str) -> ProbeCheckResult:
    missing = missing_probe_text_fields(config, prefix)
    if missing:
        return ProbeCheckResult(
            label=label,
            status="missing_config",
            model=config.text_model,
            base_url=config.base_url,
            wire_api=config.wire_api,
            response="",
            error=build_missing_probe_message(label, prefix, missing),
        )

    client = OpenAICompatibleClient(config, timeout=timeout)
    try:
        response = client.chat(
            [{"role": "user", "content": "Reply with exactly OK."}],
            model=config.text_model,
            temperature=0,
        )
    except Exception as exc:
        return ProbeCheckResult(
            label=label,
            status=classify_probe_failure(exc),
            model=config.text_model,
            base_url=config.base_url,
            wire_api=config.wire_api,
            response="",
            error=str(exc),
        )

    return ProbeCheckResult(
        label=label,
        status="ok",
        model=config.text_model,
        base_url=config.base_url,
        wire_api=config.wire_api,
        response=response,
    )


def missing_probe_text_fields(config: ModelConfig, prefix: str) -> list[str]:
    if prefix == "AI":
        return config.missing_text_fields()

    missing: list[str] = []
    if not config.base_url:
        missing.append(f"{prefix}_BASE_URL")
    if not config.api_key:
        missing.append(f"{prefix}_API_KEY")
    if not config.text_model:
        missing.append(f"{prefix}_MODEL")
    return missing


def build_missing_probe_message(label: str, prefix: str, missing: list[str]) -> str:
    if prefix == "AI":
        return (
            "Missing text model configuration: "
            + ", ".join(missing)
            + ". Load env.local.ps1 or set AI_BASE_URL / AI_API_KEY / AI_MODEL first."
        )
    return (
        f"Missing {label} text model configuration: "
        + ", ".join(missing)
        + f". Load env.local.ps1 or set {prefix}_BASE_URL / {prefix}_API_KEY / {prefix}_MODEL first."
    )


def classify_probe_failure(exc: Exception) -> str:
    message = str(exc).lower()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    return "request_error"


def resolve_single_run_documents(input_path: Path, game_name: str | None) -> list[Path] | None:
    if game_name:
        return discover_docx_for_game(input_path, game_name)
    if input_path.is_file():
        return None

    docs = discover_docx(input_path)
    groups = group_docx_by_game(docs, input_path)
    if len(groups) > 1:
        group_text = "、".join(f"{name}({len(paths)}份)" for name, paths in groups.items())
        raise ValueError(
            "Input directory appears to contain multiple games. "
            f"Use --game <游戏名> or --auto-group. Detected groups: {group_text}"
        )
    return next(iter(groups.values())) if groups else None


def run_single(
    input_path: Path,
    output_dir: Path,
    extract_only: bool,
    options: RunOptions,
    document_paths: list[Path] | None = None,
    run_name: str | None = None,
    update_latest: bool = True,
    image_cache_dir: Path | None = None,
) -> RunResult:
    agent = ReviewAgent(
        input_path=input_path,
        output_dir=output_dir,
        document_paths=document_paths,
        run_name=run_name,
        timeout=options.timeout,
        max_context_chars=options.max_context_chars,
        analyze_images=options.analyze_images,
        image_limit=options.image_limit,
        log_echo=options.log_echo,
        require_model=options.require_model,
        review_mode=options.review_mode,
        update_latest=update_latest,
        image_cache_dir=image_cache_dir,
        model_retries=options.model_retries,
    )
    try:
        return agent.run(extract_only=extract_only)
    except Exception as exc:
        if agent.current_log_path:
            print(f"[RAD] log: {agent.current_log_path}", file=sys.stderr)
        raise


def run_auto_group(input_path: Path, output_dir: Path, extract_only: bool, options: RunOptions) -> int:
    docs = discover_docx(input_path)
    groups = group_docx_by_game(docs, input_path)
    if not groups:
        raise FileNotFoundError(f"No .docx files found under: {input_path}")

    parent_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    parent_dir = output_dir / parent_name
    parent_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 0
    group_results: list[dict[str, object]] = []
    for game_name, paths in groups.items():
        safe_name = sanitize_filename(game_name)
        print(f"[RAD] group: {game_name}")
        try:
            result = run_single(
                input_path,
                parent_dir,
                extract_only,
                options,
                document_paths=paths,
                run_name=safe_name,
                update_latest=False,
                image_cache_dir=output_dir / ".cache" / "image_analysis",
            )
        except Exception as exc:
            log_path = parent_dir / safe_name / "run.log"
            print(f"[RAD] group failed: {game_name}: {exc}", file=sys.stderr)
            if log_path.exists():
                print(f"[RAD] log: {log_path}", file=sys.stderr)
            group_results.append(
                {
                    "game": game_name,
                    "status": "failed",
                    "error": str(exc),
                    "log_path": str(log_path) if log_path.exists() else "",
                    "report_path": "",
                }
            )
            exit_code = 1
            continue

        print_result(result)
        status = "warning" if result.warning else "completed"
        group_results.append(
            {
                "game": game_name,
                "status": status,
                "error": result.warning,
                "log_path": str(result.log_path or ""),
                "report_path": str(result.json_path),
            }
        )
        if result.warning and options.require_model and exit_code == 0:
            exit_code = 2

    summary_path = parent_dir / "group_run_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_dir": str(parent_dir),
                "review_mode": options.review_mode,
                "model_retries": options.model_retries,
                "groups": group_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_group_latest(parent_dir, output_dir)
    print(f"[RAD] grouped output: {parent_dir}")
    print(f"[RAD] grouped summary: {summary_path}")
    return exit_code


def write_group_latest(parent_dir: Path, output_dir: Path) -> None:
    latest = output_dir / "latest"
    if latest.exists():
        shutil.rmtree(latest)
    shutil.copytree(parent_dir, latest)


def print_result(result: RunResult) -> None:
    print(f"[RAD] documents: {result.document_count}")
    print(f"[RAD] markdown: {result.markdown_path}")
    print(f"[RAD] json: {result.json_path}")
    if result.manifest_path:
        print(f"[RAD] manifest: {result.manifest_path}")
    if result.log_path:
        print(f"[RAD] log: {result.log_path}")
    if result.warning:
        print(f"[RAD] warning: {result.warning}", file=sys.stderr)


def print_probe_result(result: ProbeResult) -> None:
    print("[RAD] probe: ok" if result.is_success else "[RAD] probe: failed")
    print(f"[RAD] review_mode: {result.review_mode}")
    for check in result.checks:
        prefix = f"[RAD] {check.label}"
        print(f"{prefix} status: {check.status}")
        print(f"{prefix} model: {check.model}")
        print(f"{prefix} base_url: {check.base_url}")
        print(f"{prefix} wire_api: {check.wire_api}")
        if check.response:
            response_preview = check.response.strip().replace("\r", " ").replace("\n", " ")
            if len(response_preview) > 200:
                response_preview = response_preview[:197] + "..."
            print(f"{prefix} response: {response_preview}")
        if check.error:
            print(f"{prefix} error: {check.error}")


if __name__ == "__main__":
    raise SystemExit(main())
