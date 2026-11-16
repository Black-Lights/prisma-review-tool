"""Per-source query translation and transparency.

Every search backend imports its query builder from here, and
:func:`plan_query` describes a ``(source, query)`` pair with the same builders,
so the query reported in warnings and in ``01_search/search_log.json`` is
always exactly the query that was sent.

How each source reads a Boolean query (``AND``/``OR``/``NOT`` in capitals,
quoted phrases, parentheses):

* Scopus runs it inside ``TITLE-ABS-KEY(...)`` (title, abstract, keywords).
* OpenAlex runs it with ``search.title_abstract_keywords`` (title, abstract,
  keywords; stemmed). Wildcards (``*``/``?``) need the unstemmed
  ``search.title_abstract_keywords.exact`` form, which is used automatically.
* Semantic Scholar runs it through ``/paper/search/bulk`` (title and abstract;
  stemmed), translated to that endpoint's syntax (``+`` ``|`` ``-``).
* arXiv runs it with quoted phrases scoped to ``all:``.
* Crossref has no Boolean search: the query is reduced to plain search terms
  ranked by relevance, and NOT terms are left out.

:func:`query_warnings` reports, per source, what a query loses. Those warnings
surface in the pipeline ``warnings`` field (``get_pipeline_progress``).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from urllib.parse import urlencode

from .filters import SearchFilters, build_scopus_clause

# Sources whose API is plain-text relevance search, not Boolean.
TEXT_SEARCH_SOURCES = ("crossref",)
_MAX_TERMS = 10
_MAX_TEXT_CHARS = 300

# OpenAlex rejects request URLs over about 4 KB with HTTP 400.
OPENALEX_URL_LIMIT = 4000
_OPENALEX_SCOPE_PARAM = "search.title_abstract_keywords"

_OPERATORS = ("AND", "OR", "NOT")
_WILDCARD_RE = re.compile(r"\w[*?]")
# A quoted phrase that is not already scoped (``ti:"x"``) or part of a word.
_ARXIV_PHRASE_RE = re.compile(r'(?<![\w:])"([^"]+)"')
_SCOPUS_SCOPED_RE = re.compile(r"(?i)(TITLE|ABS|KEY|AUTH|SRCTITLE|TITLE-ABS-KEY)\s*\(")


# --- Dates ---------------------------------------------------------------------

_DATE_RE = re.compile(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?")


def normalize_date(value: object, *, end: bool = False) -> str:
    """``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD`` as a full ISO date.

    A year or month alone means its first day, or its last day when ``end``.
    Raises ValueError for anything else.
    """
    text = str(value if value is not None else "").strip()
    m = _DATE_RE.fullmatch(text)
    if not m:
        raise ValueError(f"'{text}' is not a date (use YYYY-MM-DD)")
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else (12 if end else 1)
    if m.group(3):
        day = int(m.group(3))
    else:
        day = calendar.monthrange(year, month)[1] if end and 1 <= month <= 12 else 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        raise ValueError(f"'{text}' is not a valid date") from None


def date_range(start: object, end: object) -> tuple[str, str]:
    """The configured date range as two ISO dates. Raises ValueError if invalid."""
    s, e = normalize_date(start), normalize_date(end, end=True)
    if s > e:
        raise ValueError(f"the date range starts ({s}) after it ends ({e})")
    return s, e


def _year_only(start: str, end: str) -> bool:
    return start.endswith("-01-01") and end.endswith("-12-31")


# --- Tokenizer -----------------------------------------------------------------

def _tokens(query: str) -> list[tuple[str, str]]:
    """Split a Boolean query into (kind, text) tokens.

    Kinds: ``PHRASE`` (text without quotes), ``WORD``, ``AND``/``OR``/``NOT``
    (capitals only, like OpenAlex and Scopus), ``(`` and ``)``. An unmatched
    quote is ignored.
    """
    out: list[tuple[str, str]] = []
    i, n = 0, len(query)
    while i < n:
        c = query[i]
        if c.isspace():
            i += 1
        elif c in "()":
            out.append((c, c))
            i += 1
        elif c == '"':
            j = query.find('"', i + 1)
            if j == -1:
                i += 1
                continue
            out.append(("PHRASE", " ".join(query[i + 1:j].split())))
            i = j + 1
        else:
            j = i
            while j < n and not query[j].isspace() and query[j] not in '()"':
                j += 1
            word = query[i:j]
            out.append((word, word) if word in _OPERATORS else ("WORD", word))
            i = j
    return out


def _operand_end(tokens: list[tuple[str, str]], i: int) -> int:
    """Index just past the operand starting at ``tokens[i]`` (a term or a group)."""
    if i >= len(tokens):
        return i
    if tokens[i][0] != "(":
        return i + 1
    depth = 0
    for j in range(i, len(tokens)):
        if tokens[j][0] == "(":
            depth += 1
        elif tokens[j][0] == ")":
            depth -= 1
            if depth == 0:
                return j + 1
    return len(tokens)


def _render(tokens: list[tuple[str, str]]) -> str:
    return " ".join(f'"{t}"' if k == "PHRASE" else t for k, t in tokens)


# --- Crossref: plain-text reduction ----------------------------------------------

@dataclass
class _TextReduction:
    effective: str
    negated: list[str]
    dropped: list[str]
    wildcards: bool


def _reduce_to_text(query: str, max_terms: int = _MAX_TERMS) -> _TextReduction:
    tokens = _tokens(query)

    # Leave out NOT operands: a relevance search cannot exclude, and sending
    # them would turn an excluded term into a search term.
    kept: list[tuple[str, str]] = []
    negated: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i][0] == "NOT":
            end = _operand_end(tokens, i + 1)
            if end > i + 1:
                negated.append(_render(tokens[i + 1:end]))
            i = end
            continue
        kept.append(tokens[i])
        i += 1

    # Top-level AND groups, so every concept of (A OR ...) AND (B OR ...)
    # contributes terms, not just the first group.
    groups: list[list[str]] = [[]]
    depth = 0
    wildcards = False
    for kind, text in kept:
        if kind == "(":
            depth += 1
        elif kind == ")":
            depth = max(0, depth - 1)
        elif kind == "AND" and depth == 0:
            groups.append([])
        elif kind in ("PHRASE", "WORD"):
            if _WILDCARD_RE.search(text):
                wildcards = True
            term = re.sub(r"[*?]", "", text)
            term = re.sub(r"~\d*$", "", term).strip()
            if term:
                groups[-1].append(term)
    groups = [g for g in groups if g]

    ordered: list[str] = []
    seen: set[str] = set()
    for rank in range(max((len(g) for g in groups), default=0)):
        for g in groups:
            if rank < len(g) and g[rank].lower() not in seen:
                seen.add(g[rank].lower())
                ordered.append(g[rank])

    chosen = ordered[:max_terms]
    effective = " ".join(chosen)[:_MAX_TEXT_CHARS].strip()
    return _TextReduction(effective, negated, ordered[max_terms:], wildcards)


def text_search_query(query: str, max_terms: int = _MAX_TERMS) -> str:
    """Reduce a Boolean query to a plain-text search string (Crossref).

    Keeps quoted phrases and single words, takes terms from every top-level
    AND group in turn (up to ``max_terms``), leaves out NOT operands and strips
    wildcard characters.
    """
    return _reduce_to_text(query, max_terms).effective


# --- Semantic Scholar bulk search ---------------------------------------------

def semantic_bulk_query(query: str) -> str:
    """Translate a Boolean query to ``/paper/search/bulk`` syntax.

    ``AND`` -> ``+``, ``OR`` -> ``|``, ``NOT x`` -> ``-x``; phrases, parentheses
    and ``*`` prefix wildcards are kept. The endpoint has no single-character
    wildcard, so ``wom?n`` becomes the prefix ``wom*``.
    """
    out: list[str] = []
    negate = False
    for kind, text in _tokens(query):
        if kind == "NOT":
            negate = True
            continue
        if kind == "AND":
            piece = "+"
        elif kind == "OR":
            piece = "|"
        elif kind == "PHRASE":
            piece = f'"{text}"'
        elif kind == "WORD" and "?" in text:
            piece = text.split("?", 1)[0] + "*"
        else:
            piece = text
        if negate and kind not in ("AND", "OR", ")"):
            piece = "-" + piece
            negate = False
        out.append(piece)
    return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", " ".join(out)))


# --- OpenAlex -----------------------------------------------------------------

def openalex_search_param(query: str) -> tuple[str, str]:
    """The OpenAlex search parameter and value for ``query``.

    Title, abstract and keywords (like Scopus TITLE-ABS-KEY), stemmed. A query
    with wildcards uses the ``.exact`` form, because OpenAlex rejects wildcards
    in the stemmed search with HTTP 400.
    """
    value = " ".join(query.split())
    if _WILDCARD_RE.search(value):
        return f"{_OPENALEX_SCOPE_PARAM}.exact", value
    return _OPENALEX_SCOPE_PARAM, value


# --- arXiv --------------------------------------------------------------------

def _arxiv_stamp(iso: str, end: bool) -> str:
    return iso.replace("-", "") + ("2359" if end else "0000")


def arxiv_query(query: str, date_start: Optional[str] = None,
                date_end: Optional[str] = None) -> str:
    """The arXiv ``search_query``: quoted phrases scoped to ``all:``.

    One regex pass, so a repeated phrase or an already scoped phrase
    (``ti:"x"``) is not prefixed twice. With dates, the submission-date range
    is part of the query (filtered by arXiv, not after the fetch).
    """
    q = _ARXIV_PHRASE_RE.sub(r'all:"\1"', " ".join(query.split()))
    if date_start and date_end:
        q = (f"({q}) AND submittedDate:[{_arxiv_stamp(date_start, False)} TO "
             f"{_arxiv_stamp(date_end, True)}]")
    return q


# --- Scopus -------------------------------------------------------------------

def scopus_query(query: str, date_start: str, date_end: str,
                 filters: Optional[SearchFilters] = None) -> str:
    """The Scopus query: ``TITLE-ABS-KEY(...)`` (unless already scoped), a
    ``PUBYEAR`` range and the supported filter clauses."""
    q = " ".join(query.split())
    if not _SCOPUS_SCOPED_RE.match(q):
        q = f"TITLE-ABS-KEY({q})"
    start_year, end_year = int(date_start[:4]), int(date_end[:4])
    q += f" AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1}"
    if filters:
        q += build_scopus_clause(filters)
    return q


# --- Plans --------------------------------------------------------------------

@dataclass
class QueryPlan:
    """How a single ``(source, query)`` pair is executed."""

    source: str
    query_name: str
    raw_query: str
    effective_query: str
    warnings: list[str] = field(default_factory=list)
    syntax: str = ""          # "boolean" or "plain-text relevance"
    field_scope: str = ""     # which fields the query is matched against
    date_filter: str = ""     # how the date range is applied


def plan_query(source: str, query_name: str, query: str, *,
               date_start: Optional[str] = None, date_end: Optional[str] = None,
               filters: Optional[SearchFilters] = None) -> QueryPlan:
    """Describe how ``source`` executes ``query`` and what it loses.

    Uses the same builders as the backends, so ``effective_query`` is the
    string actually sent. Pass the (normalized) date range and filters to get
    the complete Scopus and arXiv query strings.
    """
    label = f"{source} ({query_name})"
    warnings: list[str] = []
    dated = bool(date_start and date_end)

    if source == "crossref":
        red = _reduce_to_text(query)
        warnings.append(
            f'{label}: Crossref has no Boolean search; it ranks records by relevance to '
            f'the plain terms "{red.effective}", so AND/OR/NOT and parentheses are not applied.'
        )
        if red.negated:
            warnings.append(
                f"{label}: NOT terms are left out ({', '.join(red.negated)}); Crossref cannot "
                f"exclude terms, so screening has to remove those records."
            )
        if red.dropped:
            warnings.append(
                f"{label}: only the first {_MAX_TERMS} search terms are sent; dropped: "
                f"{', '.join(red.dropped)}."
            )
        if red.wildcards:
            warnings.append(f"{label}: wildcards are not supported; the word stem is searched instead.")
        return QueryPlan(source, query_name, query, red.effective, warnings,
                         syntax="plain-text relevance",
                         field_scope="all bibliographic metadata (Crossref query)",
                         date_filter="publication date (from-pub-date/until-pub-date)")

    if source == "semantic_scholar":
        effective = semantic_bulk_query(query)
        if re.search(r"\w\?", query):
            warnings.append(
                f"{label}: '?' wildcards are not supported by Semantic Scholar; the term is "
                f"searched as a prefix (e.g. wom?n -> wom*)."
            )
        return QueryPlan(source, query_name, query, effective, warnings,
                         syntax="boolean", field_scope="title and abstract (stemmed)",
                         date_filter="publication date (publicationDateOrYear)")

    if source == "openalex":
        param, value = openalex_search_param(query)
        if param.endswith(".exact"):
            warnings.append(
                f"{label}: the query uses wildcards, which OpenAlex only accepts in its unstemmed "
                f"exact search ({param}); the other terms then match only their exact spelling "
                f"(e.g. 'network' no longer matches 'networks')."
            )
        tokens = _tokens(query)
        if len(tokens) > 1:
            # OpenAlex answers HTTP 400 to a wildcard inside a quoted phrase of
            # several words unless that phrase is the whole search.
            for kind, text in tokens:
                if kind == "PHRASE" and " " in text and _WILDCARD_RE.search(text):
                    warnings.append(
                        f'{label}: OpenAlex refuses a wildcard inside a quoted phrase ("{text}") '
                        f"when the query has other terms (HTTP 400), so this query fails on "
                        f"OpenAlex. Write the words without quotes (e.g. remote AND sens*) or give "
                        f"the phrase a query of its own."
                    )
        size = len(urlencode({param: value}))
        if size > OPENALEX_URL_LIMIT - 500:
            warnings.append(
                f"{label}: the query is {size} characters once URL-encoded; OpenAlex rejects request "
                f"URLs over about {OPENALEX_URL_LIMIT} characters (HTTP 400). Split it into several queries."
            )
        scope = "title, abstract and keywords" + (" (exact, unstemmed)" if param.endswith(".exact") else " (stemmed)")
        return QueryPlan(source, query_name, query, value, warnings, syntax="boolean",
                         field_scope=scope,
                         date_filter="publication date (from/to_publication_date)")

    if source == "arxiv":
        if "*" in query:
            warnings.append(
                f"{label}: arXiv does not document '*' truncation; the term is sent unchanged "
                f"and may match nothing."
            )
        effective = arxiv_query(query, date_start, date_end) if dated else arxiv_query(query)
        return QueryPlan(source, query_name, query, effective, warnings, syntax="boolean",
                         field_scope='all fields (quoted phrases as all:"...")',
                         date_filter="submission date (submittedDate)")

    if source == "scopus":
        effective = (scopus_query(query, date_start, date_end, filters) if dated
                     else " ".join(query.split()))
        if dated and not _year_only(date_start, date_end):
            warnings.append(
                f"{label}: Scopus filters by publication year only, so {date_start} to {date_end} "
                f"runs as {date_start[:4]} to {date_end[:4]}."
            )
        scoped = _SCOPUS_SCOPED_RE.match(" ".join(query.split()))
        return QueryPlan(source, query_name, query, effective, warnings, syntax="boolean",
                         field_scope=("fields as scoped in the query" if scoped
                                      else "TITLE-ABS-KEY (title, abstract, keywords)"),
                         date_filter="publication year (PUBYEAR)")

    # Unknown source: no claims about what it honours.
    return QueryPlan(source, query_name, query, query, [])


def query_warnings(config) -> list[str]:
    """Collect transparency warnings for every ``(query, source)`` pair in config."""
    try:
        start, end = date_range(getattr(config, "date_start", None), getattr(config, "date_end", None))
    except ValueError:
        start = end = None
    filters = SearchFilters.from_config(config)
    out: list[str] = []
    for query_def in getattr(config, "queries", []):
        name = str(query_def.get("name") or "unnamed")
        terms = str(query_def.get("terms") or "")
        if not terms.strip():
            continue
        for source in getattr(config, "sources", []):
            out.extend(plan_query(source, name, terms, date_start=start, date_end=end,
                                  filters=filters).warnings)
    return out
