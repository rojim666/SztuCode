"""OpenCode chat models advertised as free; availability is restricted by OpenCode."""

# Verified 2026-10-19 against both the official endpoint table and live model list:
# https://opencode.ai/v2/docs/console/models/
# https://opencode.ai/inference/v1/models
# Jev uses System One rather than chat/completions and is not a chat profile.
# Third-party keyless inference currently returns HTTP 403 FreeTierError:
# "OpenCode's free tier can only be used from within OpenCode."
OPENCODE_BASE_URL = "https://opencode.ai/inference/openai/v1"
OPENCODE_FREE_MODELS = (
    "big-pickle",
    "beam-free",
    "deepseek-v4.1-flash-free",
    "glm-5.3-flash-free",
    "longcat-2.5-preview-free",
    "mimo-v2.6-flash-free",
    "nemotron-3.5-lightning-free",
    "nemotron-3.5-super-vl-free",
    "space-bunny-free",
)

# Keep historical rates for saved runs; these are no longer selectable built-ins.
OPENCODE_RETIRED_FREE_MODELS = (
    "ling-3.0-flash-fin-free",
    "mimo-v2.5-free",
    "nemotron-3-ultra-free",
)
