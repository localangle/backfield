"""Shared text utilities."""

from backfield_entities.text.sentences import (
    SENTENCE_ABBREVIATIONS,
    iter_sentence_break_matches,
    protect_abbreviation_periods,
    restore_abbreviation_periods,
    sentence_bounds_containing,
    sentence_containing,
    split_sentences,
)

__all__ = [
    "SENTENCE_ABBREVIATIONS",
    "iter_sentence_break_matches",
    "protect_abbreviation_periods",
    "restore_abbreviation_periods",
    "sentence_bounds_containing",
    "sentence_containing",
    "split_sentences",
]
