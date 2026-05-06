"""Stable AI model constants shared by API, worker, and future Stylebook code."""

AI_MODEL_KIND_GENERATIVE = "generative"
AI_MODEL_KIND_EMBEDDING = "embedding"

AI_CAPABILITY_TEXT = "text"
AI_CAPABILITY_JSON = "json"
AI_CAPABILITY_VISION = "vision"

DEFAULT_AI_CURRENCY = "USD"

# ``BackfieldAiCallRecord.cost_estimate_source`` — how ``estimated_cost`` was produced.
COST_ESTIMATE_SOURCE_LITELLM = "litellm"
COST_ESTIMATE_SOURCE_MANUAL = "manual"
# No completion response to run ``litellm.completion_cost`` on (e.g. transport error).
COST_ESTIMATE_SOURCE_UNAVAILABLE = "unavailable"

# Organization integration secret keys (encrypted at rest; generic pattern for future vendors).
INTEGRATION_KEY_AI_PROVIDER_OPENAI = "ai.provider.openai"
INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC = "ai.provider.anthropic"
INTEGRATION_KEY_AI_PROVIDER_GEMINI = "ai.provider.gemini"
INTEGRATION_KEY_AI_PROVIDER_OPENROUTER = "ai.provider.openrouter"
INTEGRATION_KEY_AI_PROVIDER_AZURE = "ai.provider.azure"

ORG_AI_PROVIDER_INTEGRATION_KEYS: frozenset[str] = frozenset(
    {
        INTEGRATION_KEY_AI_PROVIDER_OPENAI,
        INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC,
        INTEGRATION_KEY_AI_PROVIDER_GEMINI,
        INTEGRATION_KEY_AI_PROVIDER_OPENROUTER,
        INTEGRATION_KEY_AI_PROVIDER_AZURE,
    }
)

# Arbitrary vendor credentials saved like presets (`BackfieldOrganizationIntegrationSecret`).
INTEGRATION_KEY_AI_CREDENTIAL_PREFIX = "ai.credential."

AI_PROVIDER_SLUG_BY_INTEGRATION_KEY: dict[str, str] = {
    INTEGRATION_KEY_AI_PROVIDER_OPENAI: "openai",
    INTEGRATION_KEY_AI_PROVIDER_ANTHROPIC: "anthropic",
    INTEGRATION_KEY_AI_PROVIDER_GEMINI: "gemini",
    INTEGRATION_KEY_AI_PROVIDER_OPENROUTER: "openrouter",
    INTEGRATION_KEY_AI_PROVIDER_AZURE: "azure",
}


def is_built_in_ai_provider_integration_key(integration_key: str) -> bool:
    return integration_key in ORG_AI_PROVIDER_INTEGRATION_KEYS


def is_custom_ai_credential_integration_key(integration_key: str) -> bool:
    """Saved credential rows keyed ``ai.credential.<uuid>`` for custom catalog models."""
    return integration_key.startswith(INTEGRATION_KEY_AI_CREDENTIAL_PREFIX)


# Project-level default model roles (graph nodes resolve these at execution time).
AI_DEFAULT_ROLE_GEOCODE_ROUTER = "geocode.router"
AI_DEFAULT_ROLE_GEOCODE_EVALUATION = "geocode.evaluation"

PROJECT_AI_DEFAULT_ROLES: frozenset[str] = frozenset(
    {
        AI_DEFAULT_ROLE_GEOCODE_ROUTER,
        AI_DEFAULT_ROLE_GEOCODE_EVALUATION,
    }
)
