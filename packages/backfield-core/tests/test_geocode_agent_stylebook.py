"""GeocodeAgent stylebook id handling (multiple catalogs)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from backfield_core.nodes.geocode_agent import run_geocode_agent


def test_geocode_raises_when_cached_catalog_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_PROJECT_ID", "1")
    mock_cm = MagicMock()
    mock_sess = MagicMock()
    mock_sess.get.return_value = None
    mock_cm.__enter__.return_value = mock_sess
    mock_cm.__exit__.return_value = None

    with patch("sqlmodel.Session", return_value=mock_cm):
        with pytest.raises(ValueError, match="catalog"):
            run_geocode_agent({"useCache": True, "stylebook_id": 99999}, {})
