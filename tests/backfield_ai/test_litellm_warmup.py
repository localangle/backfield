"""LiteLLM import warmup for worker child processes."""

from __future__ import annotations

from backfield_ai.litellm_warmup import warm_litellm_imports


def test_warm_litellm_imports_loads_provider_modules() -> None:
    warm_litellm_imports()

    import litellm
    import openai.resources.chat
    import openai.resources.embeddings
    from litellm.llms.openai import openai as litellm_openai

    assert litellm is not None
    assert openai.resources.chat is not None
    assert openai.resources.embeddings is not None
    assert litellm_openai is not None
