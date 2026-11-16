"""Semantic Scholar search backend using the bulk search endpoint.

``/paper/search/bulk`` runs a Boolean query (``+`` AND, ``|`` OR, ``-`` NOT,
quoted phrases, ``*`` prefixes, parentheses) over title and abstract, unlike
the relevance endpoint ``/paper/search`` which supports no query syntax. It
returns up to 1,000 records per call with a continuation token; records are
not relevance-ranked, so a capped query keeps an arbitrary subset of matches.
"""

from __future__ import annotations

from typing import Callable, Optional

from ..models import Paper
from . import http
from .filters import SearchFilters, build_semantic_params
from .http import SearchCancelled, SearchRequestError, SearchStatus
from .query_plan import semantic_bulk_query

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
FIELDS = "title,abstract,authors,externalIds,year,venue,publicationTypes,openAccessPdf"
# The shared keyless pool answers 429 often: back off longer than the default.
RETRIES = 5
BACKOFF = 3.0
_OA_STATUSES = {"GOLD", "GREEN", "HYBRID", "BRONZE", "DIAMOND"}


def _is_oa(pdf) -> Optional[bool]:
    """Open access from ``openAccessPdf``: an object even for closed papers."""
    if not isinstance(pdf, dict):
        return None
    if pdf.get("url") or str(pdf.get("status") or "").upper() in _OA_STATUSES:
        return True
    if str(pdf.get("status") or "").upper() == "CLOSED":
        return False
    return None


def _parse(item: dict) -> Optional[Paper]:
    title = item.get("title") or ""
    if not title:
        return None
    ext_ids = item.get("externalIds") or {}
    pub_types = item.get("publicationTypes") or []
    return Paper(
        title=title.strip(),
        authors=[a.get("name", "") for a in item.get("authors") or [] if a.get("name")],
        abstract=(item.get("abstract") or "").strip(),
        year=item.get("year") or 0,
        doi=ext_ids.get("DOI"),
        url=f"https://api.semanticscholar.org/CorpusID:{ext_ids.get('CorpusId', '')}",
        venue=item.get("venue") or "",
        keywords=[],
        source="semantic_scholar",
        source_id=item.get("paperId", ""),
        # Every type S2 lists (a review is often ["JournalArticle", "Review"]).
        type=",".join(pub_types) or None,
        is_oa=_is_oa(item.get("openAccessPdf")),
        issn=None,  # S2 records carry no ISSN
    )


def search_semantic_scholar(query: str, date_start: str, date_end: str,
                            max_results: int = 500,
                            filters: SearchFilters | None = None, *,
                            status: SearchStatus | None = None,
                            should_cancel: Callable[[], bool] | None = None) -> list[Paper]:
    """Search Semantic Scholar and return normalized Paper objects (fills ``status``)."""
    status = status if status is not None else SearchStatus("semantic_scholar")
    params = {
        "query": semantic_bulk_query(query),
        "publicationDateOrYear": f"{date_start}:{date_end}",
        "fields": FIELDS,
        **(build_semantic_params(filters) if filters else {}),
    }
    status.executed = params["query"]
    status.request = {"method": "GET", "url": API_URL, "params": dict(params), "paging": "token"}

    papers: list[Paper] = []
    token = None
    try:
        while len(papers) < max_results:
            page_params = dict(params, token=token) if token else params
            resp = http.get(API_URL, params=page_params, timeout=30, should_cancel=should_cancel,
                            max_retries=RETRIES, backoff=BACKOFF, label="Semantic Scholar")
            if resp.status_code != 200:
                msg = f"Semantic Scholar HTTP {resp.status_code}: {http.api_message(resp)}"
                status.stop(msg, bool(papers))
                print(f"  [!] {msg}")
                break

            data = resp.json()
            if status.api_total is None and data.get("total") is not None:
                status.api_total = int(data["total"])
            for item in data.get("data") or []:
                if len(papers) >= max_results:
                    break
                paper = _parse(item)
                if paper:
                    papers.append(paper)
            status.retrieved = len(papers)

            token = data.get("token")
            if not token or not data.get("data"):
                break
            http.wait(1.0, should_cancel)  # be polite to the shared pool
    except SearchCancelled:
        status.cancel()
    except SearchRequestError as exc:
        status.stop(f"Semantic Scholar: {exc}", bool(papers))
        print(f"  [!] Semantic Scholar request error: {exc}")
    except ValueError as exc:
        status.stop(f"Semantic Scholar returned an unreadable response: {exc}", bool(papers))

    status.retrieved = len(papers)
    if status.api_total is not None and status.api_total > len(papers) >= max_results:
        status.notes.append(
            f"Semantic Scholar bulk search is not ranked by relevance: the {len(papers)} records "
            f"kept are an arbitrary subset of {status.api_total} matches. Raise "
            f"search.max_results_per_query to retrieve them all."
        )
    return papers
