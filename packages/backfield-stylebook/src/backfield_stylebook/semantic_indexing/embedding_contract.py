"""Contracts for semantic document embedding batches."""

from __future__ import annotations

from dataclasses import dataclass, field

from backfield_stylebook.semantic_indexing.contracts import SemanticBuilderEntityType

DEFAULT_SEMANTIC_EMBEDDING_BATCH_SIZE = 64


@dataclass(frozen=True)
class PendingSemanticDocument:
    """One active semantic document row awaiting embedding."""

    entity_type: SemanticBuilderEntityType
    document_id: int
    search_text: str


@dataclass(frozen=True)
class EmbeddingVectorOutcome:
    """Embedding result for one pending semantic document."""

    document: PendingSemanticDocument
    vector: list[float] | None = None
    error_message: str | None = None


@dataclass
class EmbeddingApplySummary:
    """Counts from applying embedding vectors to semantic document rows."""

    indexed: int = 0
    failed: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "indexed": self.indexed,
            "failed": self.failed,
            "skipped": self.skipped,
        }


@dataclass
class EmbeddingRunSummary:
    """Embedding pass outcome for one Backfield Output article scope."""

    status: str
    model_config_id: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    batches: int = 0
    pending: int = 0
    indexed: int = 0
    failed: int = 0
    skipped: int = 0
    error: str | None = None

    def as_dict(self) -> dict[str, int | str | None]:
        return {
            "status": self.status,
            "model_config_id": self.model_config_id,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "batches": self.batches,
            "pending": self.pending,
            "indexed": self.indexed,
            "failed": self.failed,
            "skipped": self.skipped,
            "error": self.error,
        }


@dataclass
class EmbeddingBatchPlan:
    """One provider batch of pending semantic documents."""

    documents: tuple[PendingSemanticDocument, ...] = field(default_factory=tuple)

    def texts(self) -> list[str]:
        return [doc.search_text for doc in self.documents]
