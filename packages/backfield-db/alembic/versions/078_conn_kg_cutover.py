"""Phase A KG cutover: open-edge uniqueness; drop connection description/evidence_json.

Prereq: run ``backfield migrate-connection-kg --apply`` so duplicates are merged and
evidence children exist. This migration still collapses any remaining open duplicates
and materializes leftover ``evidence_json`` / description into evidence rows before
dropping columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "078_conn_kg_cutover"
down_revision: str | None = "077_conn_kg_phase_a"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "stylebook_connections" not in tables:
        return

    columns = {c["name"] for c in inspector.get_columns("stylebook_connections")}

    # Backfill any remaining null stylebook_id from project.
    if "stylebook_id" in columns:
        op.execute(
            sa.text(
                """
                UPDATE stylebook_connections AS c
                SET stylebook_id = p.stylebook_id
                FROM backfield_project AS p
                WHERE c.project_id = p.id
                  AND c.stylebook_id IS NULL
                  AND p.stylebook_id IS NOT NULL
                """
            )
        )

    if bind.dialect.name == "postgresql" and "stylebook_connection_evidence" in tables:
        # Materialize evidence_json rows that lack a matching evidence child.
        if "evidence_json" in columns:
            op.execute(
                sa.text(
                    """
                    INSERT INTO stylebook_connection_evidence (
                        connection_id,
                        article_id,
                        description,
                        quote,
                        reason,
                        confidence,
                        source,
                        prompt_version,
                        run_id,
                        processed_item_id,
                        match_basis,
                        observed_at,
                        payload_json
                    )
                    SELECT
                        c.id,
                        NULLIF(c.evidence_json->>'article_id', '')::integer,
                        NULLIF(trim(COALESCE(c.description, '')), ''),
                        NULLIF(trim(COALESCE(c.evidence_json->>'quote', '')), ''),
                        NULLIF(
                            trim(
                                COALESCE(
                                    c.evidence_json->>'reason',
                                    c.description,
                                    ''
                                )
                            ),
                            ''
                        ),
                        CASE
                            WHEN c.evidence_json ? 'confidence'
                                 AND NULLIF(c.evidence_json->>'confidence', '') IS NOT NULL
                            THEN (c.evidence_json->>'confidence')::double precision
                            ELSE NULL
                        END,
                        COALESCE(
                            NULLIF(trim(c.evidence_json->>'source'), ''),
                            'dboutput_auto_connections'
                        ),
                        NULLIF(trim(c.evidence_json->>'prompt_version'), ''),
                        NULLIF(trim(c.evidence_json->>'run_id'), ''),
                        NULLIF(c.evidence_json->>'processed_item_id', '')::integer,
                        NULLIF(trim(c.evidence_json->>'match_basis'), ''),
                        c.created_at,
                        NULL
                    FROM stylebook_connections AS c
                    WHERE c.evidence_json IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM stylebook_connection_evidence AS e
                          WHERE e.connection_id = c.id
                            AND (
                                (
                                    NULLIF(c.evidence_json->>'article_id', '')::integer
                                    IS NOT NULL
                                    AND e.article_id =
                                        NULLIF(c.evidence_json->>'article_id', '')::integer
                                )
                                OR (
                                    NULLIF(c.evidence_json->>'article_id', '')::integer
                                    IS NULL
                                    AND e.article_id IS NULL
                                    AND COALESCE(e.quote, '') = COALESCE(
                                        NULLIF(trim(c.evidence_json->>'quote'), ''),
                                        ''
                                    )
                                )
                            )
                      )
                    """
                )
            )

        # Description-only rows with no evidence children → synthetic manual evidence.
        if "description" in columns:
            op.execute(
                sa.text(
                    """
                    INSERT INTO stylebook_connection_evidence (
                        connection_id,
                        article_id,
                        description,
                        quote,
                        reason,
                        source,
                        observed_at
                    )
                    SELECT
                        c.id,
                        NULL,
                        NULLIF(trim(c.description), ''),
                        NULLIF(trim(c.description), ''),
                        NULLIF(trim(c.description), ''),
                        'legacy_manual',
                        c.created_at
                    FROM stylebook_connections AS c
                    WHERE c.description IS NOT NULL
                      AND trim(c.description) <> ''
                      AND NOT EXISTS (
                          SELECT 1
                          FROM stylebook_connection_evidence AS e
                          WHERE e.connection_id = c.id
                      )
                    """
                )
            )

        # Collapse remaining open duplicates on (stylebook_id, ends, nature).
        op.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        FIRST_VALUE(id) OVER (
                            PARTITION BY
                                stylebook_id,
                                from_entity_type,
                                from_entity_id,
                                to_entity_type,
                                to_entity_id,
                                coalesce(nature, '')
                            ORDER BY id ASC
                        ) AS survivor_id
                    FROM stylebook_connections
                    WHERE closed_at IS NULL
                      AND stylebook_id IS NOT NULL
                ),
                dups AS (
                    SELECT id, survivor_id
                    FROM ranked
                    WHERE id <> survivor_id
                )
                UPDATE stylebook_connection_evidence AS e
                SET connection_id = d.survivor_id
                FROM dups AS d
                WHERE e.connection_id = d.id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM stylebook_connection_evidence AS keep
                      WHERE keep.connection_id = d.survivor_id
                        AND keep.article_id IS NOT NULL
                        AND e.article_id IS NOT NULL
                        AND keep.article_id = e.article_id
                  )
                """
            )
        )
        op.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        FIRST_VALUE(id) OVER (
                            PARTITION BY
                                stylebook_id,
                                from_entity_type,
                                from_entity_id,
                                to_entity_type,
                                to_entity_id,
                                coalesce(nature, '')
                            ORDER BY id ASC
                        ) AS survivor_id
                    FROM stylebook_connections
                    WHERE closed_at IS NULL
                      AND stylebook_id IS NOT NULL
                ),
                dups AS (
                    SELECT id, survivor_id
                    FROM ranked
                    WHERE id <> survivor_id
                )
                DELETE FROM stylebook_connection_evidence AS e
                USING dups AS d
                WHERE e.connection_id = d.id
                """
            )
        )
        op.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        FIRST_VALUE(id) OVER (
                            PARTITION BY
                                stylebook_id,
                                from_entity_type,
                                from_entity_id,
                                to_entity_type,
                                to_entity_id,
                                coalesce(nature, '')
                            ORDER BY id ASC
                        ) AS survivor_id
                    FROM stylebook_connections
                    WHERE closed_at IS NULL
                      AND stylebook_id IS NOT NULL
                )
                DELETE FROM stylebook_connections AS c
                USING ranked AS r
                WHERE c.id = r.id
                  AND r.id <> r.survivor_id
                """
            )
        )

        # Evidence FK: cascade deletes with parent connection.
        op.drop_constraint(
            "fk_stylebook_conn_evidence_connection",
            "stylebook_connection_evidence",
            type_="foreignkey",
        )
        op.create_foreign_key(
            "fk_stylebook_conn_evidence_connection",
            "stylebook_connection_evidence",
            "stylebook_connections",
            ["connection_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Drop legacy uniqueness (project + description keyed).
    op.execute("DROP INDEX IF EXISTS uq_stylebook_connection_exact_edge")
    existing_uq = {
        c["name"] for c in inspector.get_unique_constraints("stylebook_connections")
    }
    if "uq_stylebook_connection_exact_edge" in existing_uq:
        op.drop_constraint(
            "uq_stylebook_connection_exact_edge",
            "stylebook_connections",
            type_="unique",
        )

    if "evidence_json" in columns:
        op.drop_column("stylebook_connections", "evidence_json")
    if "description" in columns:
        op.drop_column("stylebook_connections", "description")

    # Refuse null stylebook_id on open edges after backfill.
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM stylebook_connections
                        WHERE stylebook_id IS NULL AND closed_at IS NULL
                    ) THEN
                        RAISE EXCEPTION
                            'stylebook_connections still have null stylebook_id on open edges';
                    END IF;
                END $$;
                """
            )
        )
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_stylebook_connection_open_edge
            ON stylebook_connections (
                stylebook_id,
                from_entity_type,
                from_entity_id,
                to_entity_type,
                to_entity_id,
                coalesce(nature, '')
            )
            WHERE closed_at IS NULL
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_stylebook_connection_open_edge")

    op.add_column(
        "stylebook_connections",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "stylebook_connections",
        sa.Column("evidence_json", sa.JSON(), nullable=True),
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_stylebook_connection_exact_edge
            ON stylebook_connections (
                project_id,
                from_entity_type,
                from_entity_id,
                to_entity_type,
                to_entity_id,
                coalesce(nature, ''),
                coalesce(description, '')
            )
            """
        )
        # Restore non-cascading FK.
        op.drop_constraint(
            "fk_stylebook_conn_evidence_connection",
            "stylebook_connection_evidence",
            type_="foreignkey",
        )
        op.create_foreign_key(
            "fk_stylebook_conn_evidence_connection",
            "stylebook_connection_evidence",
            "stylebook_connections",
            ["connection_id"],
            ["id"],
        )
