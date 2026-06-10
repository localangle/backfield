"""Allow multiple substrate_article_meta rows per meta_type (Subject preset)."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "043_article_meta_multi_subject"
down_revision: Union[str, None] = "042_substrate_article_meta"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_substrate_article_meta_article_id_meta_type",
        "substrate_article_meta",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_substrate_article_meta_article_id_meta_type_category",
        "substrate_article_meta",
        ["article_id", "meta_type", "category"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_substrate_article_meta_article_id_meta_type_category",
        "substrate_article_meta",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_substrate_article_meta_article_id_meta_type",
        "substrate_article_meta",
        ["article_id", "meta_type"],
    )
