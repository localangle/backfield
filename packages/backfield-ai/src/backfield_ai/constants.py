"""Stable AI model constants shared by API, worker, and future Stylebook code."""

AI_MODEL_KIND_GENERATIVE = "generative"
AI_MODEL_KIND_EMBEDDING = "embedding"

AI_CAPABILITY_TEXT = "text"
AI_CAPABILITY_JSON = "json"
AI_CAPABILITY_VISION = "vision"

DEFAULT_AI_CURRENCY = "USD"

# Organization integration secret keys (encrypted at rest; generic pattern for future vendors).
INTEGRATION_KEY_AI_PROVIDER_OPENAI = "ai.provider.openai"
INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC = "ai.provider.anthropic"

ORG_AI_PROVIDER_INTEGRATION_KEYS: frozenset[str] = frozenset(
    {
        INTEGRATION_KEY_AI_PROVIDER_OPENAI,
        INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC,
    }
)

AI_PROVIDER_SLUG_BY_INTEGRATION_KEY: dict[str, str] = {
    INTEGRATION_KEY_AI_PROVIDER_OPENAI: "openai",
    INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC: "anthropic",
}

# Project-level default model roles (graph nodes resolve these at execution time).
AI_DEFAULT_ROLE_GEOCODE_ROUTER = "geocode.router"
AI_DEFAULT_ROLE_GEOCODE_EVALUATION = "geocode.evaluation"

PROJECT_AI_DEFAULT_ROLES: frozenset[str] = frozenset(
    {
        AI_DEFAULT_ROLE_GEOCODE_ROUTER,
        AI_DEFAULT_ROLE_GEOCODE_EVALUATION,
    }
)
