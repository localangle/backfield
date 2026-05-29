"""Worker substrate ingest for person entities."""

from worker.substrate.entities.person.handler import PersonPersistHandler  # noqa: F401

__all__ = ["PersonPersistHandler"]
