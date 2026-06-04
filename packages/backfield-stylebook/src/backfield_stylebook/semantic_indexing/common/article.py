"""Article substrate fields shared by all semantic document builders."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db.models import SubstrateArticle
from sqlmodel import Session


@dataclass(frozen=True)
class ArticleSource:
    id: int
    headline: str
    text: str
    deleted: bool

    @classmethod
    def from_row(cls, article: SubstrateArticle) -> ArticleSource:
        assert article.id is not None
        return cls(
            id=int(article.id),
            headline=str(article.headline),
            text=str(article.text),
            deleted=bool(article.deleted),
        )


def load_article_source(session: Session, article_id: int) -> ArticleSource | None:
    article = session.get(SubstrateArticle, article_id)
    if article is None:
        return None
    return ArticleSource.from_row(article)
