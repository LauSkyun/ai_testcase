@echo off
rem Copy this file to env.local.cmd, then replace the placeholder values.
rem Run from CMD with: call env.local.cmd

set AI_BASE_URL=http://47.236.3.167:8080
set AI_API_KEY=replace_with_your_api_key
set AI_MODEL=deepseek-v4-pro
set AI_VISION_BASE_URL=https://api.moonshot.ai/v1
set AI_VISION_API_KEY=replace_with_your_kimi_api_key
set AI_VISION_MODEL=kimi-k2.6
rem Use responses when your provider config says wire_api = "responses".
rem Use chat_completions for standard /v1/chat/completions providers.
rem Use claude for Anthropic-compatible /v1/messages providers.
set AI_WIRE_API=responses
rem Kimi vision uses OpenAI-compatible chat completions.
set AI_VISION_WIRE_API=chat_completions
rem Optional: set only when your text model provider supports deterministic seeds.
set AI_SEED=
rem Optional smoke test after loading this file:
rem python review.py --probe-model --timeout 30
rem Formal reviews retry transient text-model failures 3 times by default.
rem Override per run with: --model-retries 5
rem Optional: fusion mode dual-text-model setup
rem Primary review model
set AI_PRIMARY_BASE_URL=https://api.openai.com/v1
set AI_PRIMARY_API_KEY=replace_with_primary_api_key
set AI_PRIMARY_MODEL=gpt-5.4
set AI_PRIMARY_WIRE_API=responses
set AI_PRIMARY_SEED=
rem Secondary review model
set AI_SECONDARY_BASE_URL=http://47.236.3.167:8080
set AI_SECONDARY_API_KEY=replace_with_secondary_api_key
set AI_SECONDARY_MODEL=deepseek-v4-pro
set AI_SECONDARY_WIRE_API=chat_completions
set AI_SECONDARY_SEED=
rem Fusion mode example:
rem python review.py --input requirements --game Racing --output reports --review-mode fusion --require-model

rem Optional: named providers for the frozen-Primary Secondary A/B benchmark.
set AI_PROVIDER_QWEN_BASE_URL=http://47.236.3.167:8080
set AI_PROVIDER_QWEN_API_KEY=replace_with_qwen_api_key
set AI_PROVIDER_QWEN_MODEL=gpt-5.6-sol
set AI_PROVIDER_QWEN_WIRE_API=responses
set AI_PROVIDER_QWEN_SEED=
set AI_PROVIDER_DEEPSEEK_BASE_URL=http://47.236.3.167:8080
set AI_PROVIDER_DEEPSEEK_API_KEY=replace_with_deepseek_api_key
set AI_PROVIDER_DEEPSEEK_MODEL=deepseek-v4-pro
set AI_PROVIDER_DEEPSEEK_WIRE_API=responses
set AI_PROVIDER_DEEPSEEK_SEED=
rem Phase-one example (5 games x 2 providers x 2 repeats = 20 Secondary calls):
rem python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-provider deepseek --secondary-repeats 2 --output reports
rem Phase-two same-Qwen protocol A/B (the only variable is baseline vs phase2 prompt):
rem python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile baseline --secondary-profile phase2 --secondary-repeats 2 --output reports
rem Phase-three V1.1 correction convergence replay (frozen V1 challenge + disposition-gated shadow correct):
rem python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_1 --secondary-repeats 2 --output reports
rem Phase-three V1.2 stability replay (fixed target ledger; score is recalculated only after human-approved corrections):
rem python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_2 --secondary-repeats 2 --output reports
rem Phase-three V1.3 challenge stabilization replay (six fixed checks + deterministic decision/action matrix):
rem python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_3 --secondary-repeats 2 --output reports
rem Pending blind-review outputs expose Variant A/B only. Provider/profile mappings,
rem raw responses, prompts, evidence packets, phase3 before/after previews and full machine metrics stay under _private.

echo RAD AI environment variables loaded for this CMD session.
