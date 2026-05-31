"""CSV importer for Stylebook canonical people."""

from __future__ import annotations

import contextlib
from typing import Any

from backfield_stylebook.entities.person.persist import create_standalone_canonical
from fastapi import HTTPException, Request
from sqlmodel import Session

from stylebook_api.imports.csv_models import (
    AnalyzeCsvResponse,
    ImportCsvAnalyzeRequest,
    ImportCsvCreatedRow,
    ImportCsvFailedRow,
    ImportCsvRequest,
    ImportCsvResponse,
)
from stylebook_api.imports.csv_parse import (
    available_columns_from_rows,
    parse_csv_rows,
    parse_public_figure_value,
    read_mapped_cell,
)

MAX_IMPORT_BYTES = 25 * 1024 * 1024


def _enforce_csv_size(csv_data: str) -> None:
    if len(csv_data.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="payload exceeds 25MB")


def _resolve_person_label(
    row: dict[str, str],
    *,
    mappings: dict[str, str],
    row_index: int,
) -> str:
    label = read_mapped_cell(row, mappings, "label")
    if label:
        return label

    full_name = read_mapped_cell(row, mappings, "full_name")
    if full_name:
        return full_name

    first_name = read_mapped_cell(row, mappings, "first_name")
    last_name = read_mapped_cell(row, mappings, "last_name")
    if first_name and last_name:
        return f"{first_name} {last_name}".strip()
    if first_name:
        return first_name
    if last_name:
        return last_name

    for key, value in row.items():
        if value and ("name" in key.lower() or "person" in key.lower()):
            cleaned = str(value).strip()
            if cleaned:
                return cleaned

    return f"Person {row_index + 1}"


class CsvPeopleImporter:
    format = "csv"
    entity = "people"

    def analyze(
        self,
        *,
        payload: ImportCsvAnalyzeRequest,
        request: Request | None = None,
        **kwargs: Any,
    ) -> AnalyzeCsvResponse:
        _ = request
        _enforce_csv_size(payload.csv_data)
        rows = parse_csv_rows(payload.csv_data)
        if not rows:
            return AnalyzeCsvResponse(row_count=0, available_columns=[], sample_row=None)
        return AnalyzeCsvResponse(
            row_count=len(rows),
            available_columns=available_columns_from_rows(rows),
            sample_row=rows[0],
        )

    def run(
        self,
        *,
        stylebook_id: int,
        payload: ImportCsvRequest,
        session: Session,
        request: Request | None = None,
        **kwargs: Any,
    ) -> ImportCsvResponse:
        _ = request
        _enforce_csv_size(payload.csv_data)
        rows = parse_csv_rows(payload.csv_data)
        mappings = payload.field_mappings or {}

        created: list[ImportCsvCreatedRow] = []
        failed: list[ImportCsvFailedRow] = []

        for i, row in enumerate(rows):
            try:
                label = _resolve_person_label(row, mappings=mappings, row_index=i)
                title = read_mapped_cell(row, mappings, "title")
                affiliation = read_mapped_cell(row, mappings, "affiliation")
                person_type = read_mapped_cell(row, mappings, "person_type")
                sort_key = read_mapped_cell(row, mappings, "sort_key")
                public_figure = parse_public_figure_value(
                    read_mapped_cell(row, mappings, "public_figure")
                )

                with session.begin_nested():
                    canon = create_standalone_canonical(
                        session,
                        stylebook_id=stylebook_id,
                        label=label,
                        title=title,
                        affiliation=affiliation,
                        public_figure=public_figure,
                        person_type=person_type,
                        sort_key=sort_key,
                        provenance="stylebook_ui_import_csv",
                    )
                    session.flush()
                    created.append(
                        ImportCsvCreatedRow(
                            row_index=i,
                            canonical_id=str(canon.id),
                            label=str(canon.label),
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - per-row boundary
                failed.append(ImportCsvFailedRow(row_index=i, error=str(exc)))

        if created:
            session.commit()
        else:
            with contextlib.suppress(Exception):
                session.rollback()

        return ImportCsvResponse(
            total_rows=len(rows),
            attempted_rows=len(created) + len(failed),
            created_count=len(created),
            failed_count=len(failed),
            created=created,
            failed=failed,
        )
