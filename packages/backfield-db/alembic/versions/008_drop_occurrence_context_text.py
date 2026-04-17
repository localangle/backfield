"""Drop context_text from backfield_location_mention_occurrence.

Editorial context lives on PlaceExtract `description` and mention `role_in_story` / `nature`;
occurrence rows keep mention_text and offsets only.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_drop_occurrence_context_text"
down_revision: Union[str, None] = "007_starter_flow_add_db_output"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("backfield_location_mention_occurrence", "context_text")


def downgrade() -> None:
    op.add_column(
        "backfield_location_mention_occurrence",
        sa.Column("context_text", sa.Text(), nullable=True),
    )
