"""Embedding routing: LiteLLM batch helper and catalog kind guards."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import litellm
import pytest
from backfield_ai.constants import (
    AI_MODEL_KIND_EMBEDDING,
    AI_MODEL_KIND_GENERATIVE,
    COST_ESTIMATE_SOURCE_LITELLM,
)
from backfield_ai.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingModelKindError,
    assert_model_config_is_embedding,
    embed_texts_for_model_config,
    embed_texts_sync,
)


class _Cfg:
    def __init__(self, *, model_kind: str, config_id: str = "cfg-1") -> None:
        self.id = config_id
        self.model_kind = model_kind


def test_assert_model_config_is_embedding_rejects_generative() -> None:
    with pytest.raises(EmbeddingModelKindError):
        assert_model_config_is_embedding(_Cfg(model_kind=AI_MODEL_KIND_GENERATIVE))


def test_embed_texts_sync_requires_non_empty_batch() -> None:
    with pytest.raises(EmbeddingConfigurationError, match="At least one text"):
        embed_texts_sync(
            litellm_model="openai/text-embedding-3-small",
            texts=[],
            api_key="sk-test",
        )


@patch("backfield_ai.embeddings.litellm.embedding")
def test_embed_texts_sync_returns_vectors(mock_embedding: MagicMock) -> None:
    item0 = MagicMock(index=0, embedding=[0.1, 0.2])
    item1 = MagicMock(index=1, embedding=[0.3, 0.4])
    resp = MagicMock(data=[item1, item0], usage=MagicMock(prompt_tokens=4, total_tokens=4))
    mock_embedding.return_value = resp

    result = embed_texts_sync(
        litellm_model="openai/text-embedding-3-small",
        texts=["hello", "world"],
        api_key="sk-test",
        timeout=30.0,
    )

    assert result.batch_error is None
    assert result.dimensions == 2
    assert len(result.items) == 2
    assert result.items[0].vector == [0.1, 0.2]
    assert result.items[1].vector == [0.3, 0.4]
    mock_embedding.assert_called_once()
    call_kwargs = mock_embedding.call_args.kwargs
    assert call_kwargs["model"] == "openai/text-embedding-3-small"
    assert call_kwargs["input"] == ["hello", "world"]
    assert call_kwargs["api_key"] == "sk-test"


@patch("backfield_ai.embeddings.litellm.embedding")
def test_embed_texts_sync_parses_dict_shaped_response_items(mock_embedding: MagicMock) -> None:
    mock_embedding.return_value = {
        "data": [{"index": 0, "embedding": [0.5, 0.6]}],
        "usage": {"prompt_tokens": 2, "total_tokens": 2},
    }

    result = embed_texts_sync(
        litellm_model="text-embedding-3-small",
        texts=["hello"],
        api_key="sk-test",
    )

    assert result.batch_error is None
    assert result.items[0].vector == [0.5, 0.6]
    assert result.dimensions == 2


@patch("backfield_ai.embeddings.litellm.embedding")
def test_embed_texts_sync_surfaces_provider_failure(mock_embedding: MagicMock) -> None:
    mock_embedding.side_effect = RuntimeError("rate limited")

    result = embed_texts_sync(
        litellm_model="openai/text-embedding-3-small",
        texts=["hello"],
        api_key="sk-test",
    )

    assert result.batch_error == "rate limited"
    assert result.items[0].vector is None
    assert result.items[0].error_code == "provider"


def test_assert_model_config_accepts_embedding_kind() -> None:
    assert_model_config_is_embedding(_Cfg(model_kind=AI_MODEL_KIND_EMBEDDING))


@patch("backfield_ai.embeddings.litellm.embedding")
def test_embed_texts_sync_estimates_cost_via_litellm(
    mock_embedding: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item0 = MagicMock(index=0, embedding=[0.1, 0.2])
    resp = MagicMock(data=[item0], usage=MagicMock(prompt_tokens=2, total_tokens=2))
    mock_embedding.return_value = resp
    monkeypatch.setattr(litellm, "completion_cost", lambda **_kw: 0.00002)

    result = embed_texts_sync(
        litellm_model="openai/text-embedding-3-small",
        texts=["hello"],
        api_key="sk-test",
        track_attempt=False,
    )

    assert result.estimated_cost == Decimal("0.00002")
    assert result.cost_estimate_source == COST_ESTIMATE_SOURCE_LITELLM
    assert result.cost_estimate_incomplete is False


@patch("backfield_ai.embeddings.embed_texts_sync")
@patch("backfield_ai.embeddings._resolve_embedding_auth")
def test_embed_texts_for_model_config_does_not_hold_session_during_sync(
    mock_resolve: MagicMock,
    mock_sync: MagicMock,
) -> None:
    from backfield_ai.embeddings import EmbeddingModelAuth

    mock_resolve.return_value = EmbeddingModelAuth(
        litellm_model="openai/text-embedding-3-small",
        api_key="sk-test",
        api_base=None,
        model_config_id="cfg-embed",
    )
    mock_sync.return_value = MagicMock(batch_error=None, items=[])

    embed_texts_for_model_config(
        None,
        project_id=1,
        model_config_id="cfg-embed",
        texts=["hello"],
    )

    mock_resolve.assert_called_once_with(
        None,
        project_id=1,
        model_config_id="cfg-embed",
    )
    mock_sync.assert_called_once_with(
        litellm_model="openai/text-embedding-3-small",
        texts=["hello"],
        api_key="sk-test",
        api_base=None,
        timeout=120.0,
        model_config_id="cfg-embed",
    )
