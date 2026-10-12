# Local RAD environment variables for PowerShell.
# Load with:
#   . .\env.local.ps1
#
# Usage:
# 1. Set ACTIVE_PRIMARY_TEXT_PROVIDER / ACTIVE_SECONDARY_TEXT_PROVIDER.
# 2. Fill the API key and model for the providers you want to use.
# 3. Re-open PowerShell, or run:
#    . .\env.local.ps1
#
# Single-model modes still read AI_BASE_URL / AI_API_KEY / AI_MODEL / AI_WIRE_API.
# Fusion mode reads:
# - AI_PRIMARY_*
# - AI_SECONDARY_*

$ACTIVE_PRIMARY_TEXT_PROVIDER = "qwen"
$ACTIVE_SECONDARY_TEXT_PROVIDER = "qwen"

$TEXT_PROVIDERS = @{
    deepseek = @{
        AI_BASE_URL = "http://47.236.3.167:8080"
        AI_API_KEY  = "sk-0bef3b7c3009e2adc60bd675d6eec76f43f14e1164b420c7ce8a80fc5b7e0055"
        AI_MODEL    = "deepseek-v4-pro"
        AI_WIRE_API = "responses"
    }
    minimax = @{
        AI_BASE_URL = "http://47.236.3.167:8080"
        AI_API_KEY  = "sk-cea4c9c795bfed863934ff79f07788995ed1e72fac1e56ddbf96b0d3568472f5"
        AI_MODEL    = "claude-4.8-opus"
        AI_WIRE_API = "claude"
    }
    qwen = @{
        AI_BASE_URL = "http://47.236.3.167:8080"
        AI_API_KEY  = "sk-2939836b82a522d1fecb55e874588ecd37e89518118d1dae14a055745e00d552"
        AI_MODEL    = "gpt-5.6-sol"
        AI_WIRE_API = "responses"
    }
    glm = @{
        AI_BASE_URL = "http://47.236.3.167:8080"
        AI_API_KEY  = "sk-bdf89415eec12768080d7bdf150b86a9edb49033023bfcf3440bd2b8cd08d90b"
        AI_MODEL    = "claude-fable-5"
        AI_WIRE_API = "claude"
    }
}

# Export every configured provider under a stable name for frozen-Primary
# Secondary benchmarks. This does not change the active primary/secondary pair.
foreach ($providerName in $TEXT_PROVIDERS.Keys) {
    $provider = $TEXT_PROVIDERS[$providerName]
    $providerPrefix = "AI_PROVIDER_$($providerName.ToUpperInvariant())"
    Set-Item -Path "Env:${providerPrefix}_BASE_URL" -Value $provider.AI_BASE_URL
    Set-Item -Path "Env:${providerPrefix}_API_KEY" -Value $provider.AI_API_KEY
    Set-Item -Path "Env:${providerPrefix}_MODEL" -Value $provider.AI_MODEL
    Set-Item -Path "Env:${providerPrefix}_WIRE_API" -Value $provider.AI_WIRE_API
    Set-Item -Path "Env:${providerPrefix}_SEED" -Value ""
}

if (-not $TEXT_PROVIDERS.ContainsKey($ACTIVE_PRIMARY_TEXT_PROVIDER)) {
    throw "Unknown ACTIVE_PRIMARY_TEXT_PROVIDER: $ACTIVE_PRIMARY_TEXT_PROVIDER"
}

if (-not $TEXT_PROVIDERS.ContainsKey($ACTIVE_SECONDARY_TEXT_PROVIDER)) {
    throw "Unknown ACTIVE_SECONDARY_TEXT_PROVIDER: $ACTIVE_SECONDARY_TEXT_PROVIDER"
}

$selectedPrimaryTextProvider = $TEXT_PROVIDERS[$ACTIVE_PRIMARY_TEXT_PROVIDER]
$selectedSecondaryTextProvider = $TEXT_PROVIDERS[$ACTIVE_SECONDARY_TEXT_PROVIDER]

# Keep single-model mode compatible by mapping AI_* to the primary model.
$env:AI_BASE_URL = $selectedPrimaryTextProvider.AI_BASE_URL
$env:AI_API_KEY = $selectedPrimaryTextProvider.AI_API_KEY
$env:AI_MODEL = $selectedPrimaryTextProvider.AI_MODEL
$env:AI_WIRE_API = $selectedPrimaryTextProvider.AI_WIRE_API

# Fusion mode primary model.
$env:AI_PRIMARY_BASE_URL = $selectedPrimaryTextProvider.AI_BASE_URL
$env:AI_PRIMARY_API_KEY = $selectedPrimaryTextProvider.AI_API_KEY
$env:AI_PRIMARY_MODEL = $selectedPrimaryTextProvider.AI_MODEL
$env:AI_PRIMARY_WIRE_API = $selectedPrimaryTextProvider.AI_WIRE_API
$env:AI_PRIMARY_SEED = ""

# Fusion mode secondary model.
$env:AI_SECONDARY_BASE_URL = $selectedSecondaryTextProvider.AI_BASE_URL
$env:AI_SECONDARY_API_KEY = $selectedSecondaryTextProvider.AI_API_KEY
$env:AI_SECONDARY_MODEL = $selectedSecondaryTextProvider.AI_MODEL
$env:AI_SECONDARY_WIRE_API = $selectedSecondaryTextProvider.AI_WIRE_API
$env:AI_SECONDARY_SEED = ""

# Vision model can stay fixed while you compare different text models.
$env:AI_VISION_BASE_URL = "http://47.236.3.167:8080"
$env:AI_VISION_API_KEY = "sk-b7ef86081aa3ad942892a80ef7b951c5a5ed044bdfa0e675b47d8119267a877f"
$env:AI_VISION_MODEL = "kimi-k2.6"
$env:AI_VISION_WIRE_API = "chat_completions"

Write-Host "RAD AI environment variables loaded for this PowerShell session."
Write-Host "Primary text provider: $ACTIVE_PRIMARY_TEXT_PROVIDER"
Write-Host "Primary text model: $env:AI_PRIMARY_MODEL"
Write-Host "Secondary text provider: $ACTIVE_SECONDARY_TEXT_PROVIDER"
Write-Host "Secondary text model: $env:AI_SECONDARY_MODEL"
