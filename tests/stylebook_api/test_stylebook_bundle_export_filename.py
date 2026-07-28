"""Export ZIP download filenames for Stylebook bundle jobs."""

from __future__ import annotations

from datetime import UTC, datetime

from stylebook_api.routers.stylebook_bundle_jobs import _export_download_filename


def test_export_download_filename_uses_slug_and_utc_date() -> None:
    when = datetime(2026, 7, 16, 18, 30, tzinfo=UTC)
    assert (
        _export_download_filename(
            stylebook_slug="cpm",
            stylebook_name="CPM",
            when=when,
        )
        == "cpm-stylebook-export-2026-07-16.zip"
    )


def test_export_download_filename_avoids_double_stylebook_suffix() -> None:
    when = datetime(2026, 7, 16, tzinfo=UTC)
    assert (
        _export_download_filename(
            stylebook_slug="cpm-stylebook",
            stylebook_name="CPM Stylebook",
            when=when,
        )
        == "cpm-stylebook-export-2026-07-16.zip"
    )


def test_export_download_filename_falls_back_to_name_slug() -> None:
    when = datetime(2026, 1, 2, tzinfo=UTC)
    assert (
        _export_download_filename(
            stylebook_slug=None,
            stylebook_name="North Side Desk",
            when=when,
        )
        == "north-side-desk-stylebook-export-2026-01-02.zip"
    )
