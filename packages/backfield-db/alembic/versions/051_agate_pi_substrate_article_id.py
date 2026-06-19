"""Add substrate_article_id on agate_processed_item for article provenance lookups."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "051_pi_substrate_article_id"
down_revision: Union[str, None] = "050_agate_item_timing"
branch_labels: Sequence[str] | None = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agate_processed_item",
        sa.Column("substrate_article_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "agate_processed_item_substrate_article_id_fkey",
        "agate_processed_item",
        "substrate_article",
        ["substrate_article_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agate_processed_item_substrate_article_id",
        "agate_processed_item",
        ["substrate_article_id"],
        postgresql_where=sa.text("substrate_article_id IS NOT NULL"),
        sqlite_where=sa.text("substrate_article_id IS NOT NULL"),
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        UPDATE agate_processed_item pi
        SET substrate_article_id = a.id
        FROM substrate_article a
        WHERE a.source_item_id = pi.id
          AND a.deleted = false
          AND pi.substrate_article_id IS NULL
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            row_rec RECORD;
            article_id_text text;
            sanitized text;
        BEGIN
            FOR row_rec IN
                SELECT id, result_json
                FROM agate_processed_item
                WHERE result_json IS NOT NULL
                  AND result_json <> ''
                  AND substrate_article_id IS NULL
            LOOP
                BEGIN
                    sanitized := replace(row_rec.result_json, '\\u0000', '');
                    sanitized := translate(sanitized, chr(0), '');
                    article_id_text := COALESCE(
                        NULLIF(sanitized::jsonb #>> '{stylebook_output,article_id}', ''),
                        NULLIF(sanitized::jsonb #>> '{geocode_agent,article_id}', ''),
                        NULLIF(sanitized::jsonb #>> '{place_extract,article_id}', '')
                    );
                    IF article_id_text ~ '^[0-9]+$' THEN
                        UPDATE agate_processed_item
                        SET substrate_article_id = article_id_text::integer
                        WHERE id = row_rec.id;
                    END IF;
                EXCEPTION
                    WHEN others THEN
                        NULL;
                END;
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agate_processed_item_substrate_article_id",
        table_name="agate_processed_item",
    )
    op.drop_constraint(
        "agate_processed_item_substrate_article_id_fkey",
        "agate_processed_item",
        type_="foreignkey",
    )
    op.drop_column("agate_processed_item", "substrate_article_id")
