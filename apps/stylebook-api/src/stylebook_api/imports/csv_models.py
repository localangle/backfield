"""Shared Pydantic models for CSV catalog import."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ImportCsvAnalyzeRequest(BaseModel):
    csv_data: str


class AnalyzeCsvResponse(BaseModel):
    row_count: int
    available_columns: list[str]
    sample_row: dict[str, Any] | None = None


class ImportCsvRequest(BaseModel):
    csv_data: str
    field_mappings: dict[str, str] = Field(default_factory=dict)


class ImportCsvCreatedRow(BaseModel):
    row_index: int
    canonical_id: str
    label: str


class ImportCsvFailedRow(BaseModel):
    row_index: int
    error: str


class ImportCsvResponse(BaseModel):
    total_rows: int
    attempted_rows: int
    created_count: int
    failed_count: int
    created: list[ImportCsvCreatedRow]
    failed: list[ImportCsvFailedRow]
