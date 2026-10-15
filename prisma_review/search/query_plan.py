"""Per-source query planning and transparency.

Different search backends honour different parts of a Boolean query: Scopus
runs the full Boolean expression (``TITLE-ABS-KEY``), arXiv and OpenAlex honour
AND/OR/NOT and quoted phrases natively (OpenAlex's ``search`` parameter has
supported Boolean queries since 2023), while the remaining plain-text APIs
(Crossref, Semantic Scholar) collapse the query to a handful of phrases and
silently drop OR/NOT and ``*`` truncation.

To avoid silent surprises, :func:`query_warnings` reports, per source, which
operators a query loses and what string is actually executed. Those warnings
surface in the pipeline ``warnings`` field (``get_pipeline_progress``). The
plain-text backends import :func:`text_search_query` from here so the reported
"actually searched" string always matches what they really send.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PHRASE_RE = re.compile(r'"([^"]+)"')
_OR_NOT_RE = re.compile(r'\b(OR|NOT)\b')
_BOOL_RE = re.compile(r'\b(AND|OR|NOT)\b')

# Sources whose API is plain-text relevance search, not Boolean.
TEXT_SEARCH_SOURCES = ("crossref", "semantic_scholar")
_MAX_PHRASES = 5


def text_search_query(query: str, max_phrases: int = _MAX_PHRASES) -> str:
    """Reduce a Boolean query to a plain-text search string.

    Shared by the plain-text backends so the transparency warnings always match
    what those backends actually send: keep the first ``max_phrases`` quoted
    phrases joined by spaces; with no quoted phrases, strip Boolean operators
    and punctuation.
    """
    phrases = _PHRASE_RE.findall(query)
    if phrases:
        return " ".join(phrases[:max_phrases])
    clean = _BOOL_RE.sub(" ", query)
    clean = re.sub(r'[()"]', "", clean)
    return " ".join(clean.split())[:200]


@dataclass
class QueryPlan:
    """How a single ``(source, query)`` pair will be executed."""

    source: str
    query_name: str
    raw_query: str
    effective_query: str
    warnings: list[str] = field(default_factory=list)


def plan_query(source: str, query_name: str, query: str) -> QueryPlan:
    """Describe how ``source`` will execute ``query`` and what it drops."""
    label = f"{source} ({query_name})"

    if source in TEXT_SEARCH_SOURCES:
        phrases = _PHRASE_RE.findall(query)
        effective = text_search_query(query)
        warnings: list[str] = []
        if _OR_NOT_RE.search(query):
            warnings.append(
                f"{label}: plain-text API — OR/NOT operators are ignored; terms "
                f"are matched by relevance, not as a Boolean expression."
            )
        if len(phrases) > _MAX_PHRASES:
            warnings.append(
                f"{label}: only the first {_MAX_PHRASES} of {len(phrases)} quoted "
                f"phrases are searched; the remaining {len(phrases) - _MAX_PHRASES} are dropped."
            )
        if "*" in query:
            warnings.append(
                f"{label}: wildcard '*' truncation is not supported and is ignored."
            )
        if warnings:
            warnings.append(f'{label}: actually searched -> "{effective}"')
        return QueryPlan(source, query_name, query, effective, warnings)

    if source in ("arxiv", "openalex"):
        # arXiv and OpenAlex honour AND/OR/NOT and quoted phrases natively;
        # only '*' truncation is unsupported.
        warnings = []
        if "*" in query:
            warnings.append(
                f"{label}: wildcard '*' truncation is not supported and is ignored."
            )
        return QueryPlan(source, query_name, query, query, warnings)

    if source == "scopus":
        # Scopus honours the full Boolean expression — nothing is dropped.
        return QueryPlan(source, query_name, query, query, [])

    # Unknown source — no claims about what it honours.
    return QueryPlan(source, query_name, query, query, [])


def query_warnings(config) -> list[str]:
    """Collect transparency warnings for every ``(query, source)`` pair in config."""
    out: list[str] = []
    for query_def in getattr(config, "queries", []):
        name = query_def.get("name", "unnamed")
        terms = query_def.get("terms", "")
        if not str(terms).strip():
            continue
        for source in getattr(config, "sources", []):
            out.extend(plan_query(source, name, terms).warnings)
    return out
