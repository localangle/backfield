"""Abbreviation-aware sentence splitting."""

from __future__ import annotations

from backfield_entities.text.sentences import (
    sentence_containing,
    split_sentences,
)


def test_split_sentences_keeps_common_news_abbreviations() -> None:
    text = (
        "Dr. Smith met Ald. Jessie Fuentes in St. Paul at 10 a.m. "
        "U.S. officials left Monday."
    )
    assert split_sentences(text) == (
        "Dr. Smith met Ald. Jessie Fuentes in St. Paul at 10 a.m.",
        "U.S. officials left Monday.",
    )


def test_split_sentences_keeps_initials() -> None:
    text = "J.B. Pritzker spoke in Springfield. Lawmakers applauded."
    assert split_sentences(text) == (
        "J.B. Pritzker spoke in Springfield.",
        "Lawmakers applauded.",
    )


def test_sentence_containing_does_not_cut_on_st_paul() -> None:
    text = "Police responded in St. Paul after the call came in."
    start = text.index("St. Paul")
    end = start + len("St. Paul")
    assert sentence_containing(text, start, end) == text


def test_sentence_containing_ignores_earlier_title_abbreviation() -> None:
    text = "Dr. Smith spoke in St. Paul yesterday evening."
    start = text.index("St. Paul")
    end = start + len("St. Paul")
    assert sentence_containing(text, start, end) == text
