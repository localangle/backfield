"""Eager LiteLLM / OpenAI SDK imports on the worker main thread.

Parallel graph execution calls LiteLLM from ``asyncio.to_thread`` workers. The OpenAI
Python SDK lazily imports submodules such as ``openai.resources.chat`` on first use;
concurrent first imports across threads can raise importlib ``_DeadlockError``, which
LiteLLM surfaces as ``InternalServerError: OpenAIException - deadlock detected``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def warm_litellm_imports() -> None:
    """Load LiteLLM and common OpenAI SDK modules on the current thread."""
    import litellm  # noqa: F401

    try:
        import openai.resources.chat as _openai_chat  # noqa: F401
        import openai.resources.embeddings as _openai_embeddings  # noqa: F401
    except ImportError:
        logger.debug("OpenAI SDK resource modules unavailable during LiteLLM warmup")
        return

    # Touch LiteLLM's OpenAI provider entrypoint (embedding + completion routing).
    try:
        from litellm.llms.openai import openai as _litellm_openai  # noqa: F401
    except ImportError:
        logger.debug("LiteLLM OpenAI provider module unavailable during warmup")
