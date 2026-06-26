"""Tests for init config loading."""

from __future__ import annotations

import json

import pytest
from backfield_cli.init_config import InitConfig, load_init_config


def test_load_init_config_from_json(tmp_path) -> None:
    path = tmp_path / "init.json"
    path.write_text(
        json.dumps(
            {
                "admin_email": "admin@example.com",
                "admin_password": "pw-test",
                "admin_display_name": "Admin",
                "org_name": "Acme News",
                "stylebook_name": "Acme Stylebook",
                "skip_stack": True,
            }
        ),
        encoding="utf-8",
    )

    config = load_init_config(path)

    assert config.admin_email == "admin@example.com"
    assert config.org_name == "Acme News"
    assert config.stylebook_name == "Acme Stylebook"
    assert config.skip_stack is True


def test_init_config_rejects_dual_password_sources() -> None:
    with pytest.raises(ValueError, match="admin_password"):
        InitConfig.model_validate(
            {
                "admin_email": "admin@example.com",
                "admin_password": "one",
                "admin_password_file": "/tmp/pw",
            }
        )
