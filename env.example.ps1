# Copy this file to env.local.ps1, then replace the placeholder values.
# Run from PowerShell with: . .\env.local.ps1

$env:AI_BASE_URL = "http://47.236.3.167:8080"
$env:AI_API_KEY = "replace_with_your_api_key"
$env:AI_MODEL = "deepseek-v4-pro"
$env:AI_VISION_BASE_URL = "https://api.moonshot.ai/v1"
$env:AI_VISION_API_KEY = "replace_with_your_kimi_api_key"
$env:AI_VISION_MODEL = "kimi-k2.6"
# Use responses when your provider config says wire_api = "responses".
# Use chat_completions for standard /v1/chat/completions providers.
# Use claude for Anthropic-compatible /v1/messages providers.
$env:AI_WIRE_API = "responses"
# Kimi vision uses OpenAI-compatible chat completions.
$env:AI_VISION_WIRE_API = "chat_completions"
# Optional: set only when your text model provider supports deterministic seeds.
$env:AI_SEED = ""
# Optional smoke test after loading this file:
# python review.py --probe-model --timeout 30
# Formal reviews retry transient text-model failures 3 times by default.
# Override per run with: --model-retries 5

# Optional: fusion mode dual-text-model setup
# Primary review model
$env:AI_PRIMARY_BASE_URL = "https://api.openai.com/v1"
$env:AI_PRIMARY_API_KEY = "replace_with_primary_api_key"
$env:AI_PRIMARY_MODEL = "gpt-5.4"
$env:AI_PRIMARY_WIRE_API = "responses"
$env:AI_PRIMARY_SEED = ""
# Secondary review model
$env:AI_SECONDARY_BASE_URL = "http://47.236.3.167:8080"
$env:AI_SECONDARY_API_KEY = "replace_with_secondary_api_key"
$env:AI_SECONDARY_MODEL = "deepseek-v4-pro"
$env:AI_SECONDARY_WIRE_API = "chat_completions"
$env:AI_SECONDARY_SEED = ""
# Fusion mode example:
# python review.py --input requirements --game Racing --output reports --review-mode fusion --require-model

# Optional: named providers for the frozen-Primary Secondary A/B benchmark.
# Provider names on the CLI are converted to AI_PROVIDER_<UPPER_NAME>_*.
$env:AI_PROVIDER_QWEN_BASE_URL = "http://47.236.3.167:8080"
$env:AI_PROVIDER_QWEN_API_KEY = "replace_with_qwen_api_key"
$env:AI_PROVIDER_QWEN_MODEL = "gpt-5.6-sol"
$env:AI_PROVIDER_QWEN_WIRE_API = "responses"
$env:AI_PROVIDER_QWEN_SEED = ""
$env:AI_PROVIDER_DEEPSEEK_BASE_URL = "http://47.236.3.167:8080"
$env:AI_PROVIDER_DEEPSEEK_API_KEY = "replace_with_deepseek_api_key"
$env:AI_PROVIDER_DEEPSEEK_MODEL = "deepseek-v4-pro"
$env:AI_PROVIDER_DEEPSEEK_WIRE_API = "responses"
$env:AI_PROVIDER_DEEPSEEK_SEED = ""
# Phase-one example (5 games x 2 providers x 2 repeats = 20 Secondary calls):
# python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-provider deepseek --secondary-repeats 2 --output reports
# Phase-two same-Qwen protocol A/B (the only variable is baseline vs phase2 prompt):
# python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile baseline --secondary-profile phase2 --secondary-repeats 2 --output reports
# Phase-three V1.1 correction convergence replay (frozen V1 challenge + disposition-gated shadow correct):
# python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_1 --secondary-repeats 2 --output reports
# Phase-three V1.2 stability replay (fixed target ledger; score is recalculated only after human-approved corrections):
# python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_2 --secondary-repeats 2 --output reports
# Phase-three V1.3 challenge stabilization replay (six fixed checks + deterministic decision/action matrix):
# python review.py --secondary-replay-from reports/20260731_105856 --secondary-provider qwen --secondary-profile phase3_v1_3 --secondary-repeats 2 --output reports
# Pending blind-review outputs expose Variant A/B only. Provider/profile mappings,
# raw responses, prompts, evidence packets, phase3 before/after previews and full machine metrics stay under _private.

Write-Host "RAD AI environment variables loaded for this PowerShell session."
