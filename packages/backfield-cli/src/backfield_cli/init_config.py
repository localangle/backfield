"""Init configuration models and loaders."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class InitConfig(BaseModel):
    admin_email: str = Field(min_length=1)
    admin_password: str | None = None
    admin_password_file: str | None = None
    admin_display_name: str | None = None
    org_slug: str = "default"
    org_name: str = "Backfield"
    stylebook_name: str = "Default Stylebook"
    skip_stack: bool = False

    @model_validator(mode="after")
    def _validate_password_source(self) -> InitConfig:
        if self.admin_password and self.admin_password_file:
            raise ValueError("Provide only one of admin_password or admin_password_file")
        return self


def load_init_config(path: Path) -> InitConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Init config must be a JSON object")
    return InitConfig.model_validate(payload)
