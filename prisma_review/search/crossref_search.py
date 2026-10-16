"""Crossref search backend using REST API.

Crossref has no Boolean search: the query is reduced to plain terms ranked by
relevance (see :func:`query_plan.text_search_query`), while the structured
``filter`` parameter (dates, type, ISSN, has-abstract) is applied exactly.
"""

from __future__ import annotations

import html
import re
from typing import Callable, Optional

from ..models import Paper
from . import http
from .filters import SearchFilters, build_crossref_filter, normalize_issn
from .http import SearchCancelled, SearchRequestError, SearchStatus
from .query_plan import text_search_query

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

API_URL = "https://api.crossref.org/works"
PAGE_SIZE = 100
SELECT = "DOI,title,author,abstract,issued,published,container-title,ISSN,type,URL"

_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_ABSTRACT_RE = re.compile(r"^\s*<jats:title>\s*abstract\s*</jats:title>", re.IGNORECASE)


def clean_markup(text: str) -> str:
    """Plain text from Crossref's JATS/HTML: tags become spaces, entities are decoded."""
    text = _LEADING_ABSTRACT_RE.sub(" ", text or "")
    text = _TAG_RE.sub(" ", text)
    return " ".join(html.unescape(text).split())


def _year(item: dict) -> int:
    """Publication year: ``issued`` (earliest known date), then ``published``."""
    for key in ("issued", "published", "published-print", "published-online"):
        parts = (item.get(key) or {}).get("date-parts") or []
        first = parts[0] if parts and isinstance(parts[0], list) else parts
        if first and isinstance(first[0], int):
            return first[0]
    return 0


def _parse(item: dict) -> Optional[Paper]:
    titles = item.get("title") or []
    title = clean_markup(titles[0]) if titles else ""
    if not title:
        return None

    authors = []
    for author in item.get("author") or []:
        name = f"{author.get('given', '')} {author.get('family', '')}".strip()
        name = name or (author.get("name") or "").strip()  # organisations
        if name:
            authors.append(name)

    doi = item.get("DOI", "")
    url = item.get("URL", "") or (f"https://doi.org/{doi}" if doi else "")
    venues = item.get("container-title") or []
    issns = item.get("ISSN") or []

    return Paper(
        title=title,
        authors=authors,
        abstract=clean_markup(item.get("abstract", "")),
        year=_year(item),
        doi=doi or None,
        url=url,
        venue=clean_markup(venues[0]) if venues else "",
        # Crossref's "subject" is the journal's subject area, not the paper's
        # keywords, so it is not used (keyword screening would match on it).
        keywords=[],
        source="crossref",
        source_id=doi or "",
        type=item.get("type"),
        issn=normalize_issn(issns[0]) if issns else None,
    )


def search_crossref(query: str, date_start: str, date_end: str,
                    max_results: int = 500, email: str = "",
                    filters: SearchFilters | None = None, *,
                    status: SearchStatus | None = None,
                    should_cancel: Callable[[], bool] | None = None) -> list[Paper]:
    """Search Crossref and return normalized Paper objects (fills ``status``)."""
    status = status if status is not None else SearchStatus("crossref")
    search_text = text_search_query(query)

    # Request channel: date is always filtered; append supported facets to the
    # same structured `filter` string.
    filter_str = f"from-pub-date:{date_start},until-pub-date:{date_end}"
    if filters:
        extra = build_crossref_filter(filters)
        if extra:
            filter_str += "," + extra

    params = {"query": search_text, "filter": filter_str, "select": SELECT}
    status.executed = search_text
    status.request = {"method": "GET", "url": API_URL, "params": dict(params),
                      "paging": "cursor", "mailto": bool(email)}
    if email:
        params["mailto"] = email  # Crossref's polite pool

    papers: list[Paper] = []
    cursor = "*"
    try:
        while len(papers) < max_results and cursor:
            page_params = dict(params, rows=min(PAGE_SIZE, max_results - len(papers)), cursor=cursor)
            resp = http.get(API_URL, params=page_params, timeout=30, should_cancel=should_cancel,
                            secrets=[email], label="Crossref")
            if resp.status_code != 200:
                detail = http.redact(http.api_message(resp), [email])
                msg = f"Crossref HTTP {resp.status_code}: {detail}"
                status.stop(msg, bool(papers))
                print(f"  [!] {msg}")
                break

            message = resp.json().get("message", {})
            if status.api_total is None and message.get("total-results") is not None:
                status.api_total = int(message["total-results"])
            items = message.get("items") or []
            if not items:
                break
            for item in items:
                if len(papers) >= max_results:
                    break
                paper = _parse(item)
                if paper:
                    papers.append(paper)
            status.retrieved = len(papers)
            cursor = message.get("next-cursor")
    except SearchCancelled:
        status.cancel()
    except SearchRequestError as exc:
        status.stop(f"Crossref: {exc}", bool(papers))
        print(f"  [!] Crossref search error: {exc}")
    except ValueError as exc:
        status.stop(f"Crossref returned an unreadable response: {exc}", bool(papers))

    status.retrieved = len(papers)
    return papers
