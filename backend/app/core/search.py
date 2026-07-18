"""Shared list-search builder: one implementation of the app's search
semantics — case-insensitive substring, separator-squashed part/ID matching,
pg_trgm typo tolerance, and relevance ranking — so every list endpoint
(inventory, customers, repair orders, suppliers, ...) behaves the same.

Usage:
    where_clause, relevance = build_search(
        term,
        primary=[Model.name, Model.sku],          # substring hit → score 1.0
        squashed=[Model.sku],                     # "10w30" matches "10W-30" → 0.9
        secondary=[Model.description],            # substring hit → 0.8
        similarity=[Model.name],                  # pg_trgm: "gaskit" → "gasket"
    )
    query = query.where(where_clause).order_by(relevance.desc(), Model.name, Model.id)
"""
from __future__ import annotations

from sqlalchemy import case, func, or_
from sqlalchemy.sql import ColumnElement

SIMILARITY_THRESHOLD = 0.3


def squash(col: ColumnElement) -> ColumnElement:
    """Lowercase a column and strip everything but letters/digits, so matches
    ignore dashes, spaces, and punctuation ("ETS-10w30" ≡ "ets 10W30")."""
    return func.regexp_replace(func.lower(col), "[^a-z0-9]", "", "g")


def build_search(
    term: str,
    *,
    primary: list[ColumnElement],
    secondary: list[ColumnElement] | None = None,
    squashed: list[ColumnElement] | None = None,
    similarity: list[ColumnElement] | None = None,
    threshold: float = SIMILARITY_THRESHOLD,
) -> tuple[ColumnElement, ColumnElement]:
    """Build (where_clause, relevance) for a search term.

    Ranking: primary substring 1.0 > squashed 0.9 > secondary 0.8 >
    word_similarity (0..1, realistically < 0.9). Order by relevance.desc()
    with stable tiebreakers so exact hits always beat fuzzy ones.
    """
    term = term.strip()
    squashed_term = "".join(ch for ch in term.lower() if ch.isalnum())

    clauses: list[ColumnElement] = []
    signals: list[ColumnElement] = []

    for col in primary:
        hit = col.ilike(f"%{term}%")
        clauses.append(hit)
        signals.append(case((hit, 1.0), else_=0.0))
    if squashed_term:
        for col in squashed or []:
            hit = squash(col).like(f"%{squashed_term}%")
            clauses.append(hit)
            signals.append(case((hit, 0.9), else_=0.0))
    for col in secondary or []:
        hit = col.ilike(f"%{term}%")
        clauses.append(hit)
        signals.append(case((hit, 0.8), else_=0.0))
    for col in similarity or []:
        clauses.append(func.word_similarity(term, col) > threshold)
        signals.append(func.word_similarity(term, col))

    relevance = func.greatest(*signals) if len(signals) > 1 else signals[0]
    return or_(*clauses), relevance
