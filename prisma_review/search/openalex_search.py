"""OpenAlex search backend (REST API).

Credentials travel with each request (``Authorization: Bearer`` header), so
nothing is kept in process-global state: switching projects in a long-running
MCP server or web API can never reuse another project's key or email.

Paging: with an API key the backend uses cursor paging (no depth limit).
Without one it uses basic ``page`` paging, which OpenAlex allows without a key
up to 10,000 results per query; cursor paging past the first page needs a key
(HTTP 401 "API key required for cursor paging").
"""

from __future__ import annotations

from typing import Callable, Optional

from ..models import Paper
from . import http
from .filters import SearchFilters, build_openalex_filters, normalize_issn
from .http import SearchCancelled, SearchRequestError, SearchStatus
from .query_plan import openalex_search_param

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

API_URL = "https://api.openalex.org/works"
PER_PAGE = 100              # OpenAlex maximum
PAGE_PAGING_LIMIT = 10_000  # basic paging stops here (page * per_page)
SELECT = ("id,title,doi,authorships,publication_year,primary_location,"
          "abstract_inverted_index,keywords,type,open_access")
KEY_HINT = ("Add a free OpenAlex API key under api_keys.openalex_key "
            "(https://openalex.org/settings/api).")


def build_params(query: str, date_start: str, date_end: str,
                 filters: SearchFilters | None = None) -> dict:
    """Request parameters (without paging) for one query."""
    param, value = openalex_search_param(query)
    facets = {"from_publication_date": date_start, "to_publication_date": date_end}
    if filters:
        facets.update(build_openalex_filters(filters))
    return {
        param: value,
        "filter": ",".join(f"{k}:{v}" for k, v in facets.items()),
        "select": SELECT,
    }


def _abstract(aii) -> str:
    """Rebuild an abstract from OpenAlex's inverted index."""
    if not aii or not isinstance(aii, dict):
        return ""
    try:
        max_pos = max(max(v) for v in aii.values()) + 1
        words = [""] * max_pos
        for word, positions in aii.items():
            for pos in positions:
                if pos < max_pos:
                    words[pos] = word
        return " ".join(w for w in words if w)
    except (ValueError, TypeError):
        return ""


def _parse(work: dict) -> Optional[Paper]:
    title = work.get("title") or ""
    if not title:
        return None

    authors = []
    for authorship in work.get("authorships") or []:
        name = (authorship.get("author") or {}).get("display_name", "")
        if name:
            authors.append(name)

    venue = ""
    issn = None
    loc = work.get("primary_location")
    if loc and loc.get("source"):
        src = loc["source"]
        venue = src.get("display_name") or ""
        issn = normalize_issn(src.get("issn_l") or (src.get("issn") or [None])[0])

    doi = work.get("doi") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    keywords = [k.get("display_name", "") for k in work.get("keywords") or [] if k.get("display_name")]

    return Paper(
        title=title.strip(),
        authors=authors,
        abstract=_abstract(work.get("abstract_inverted_index")),
        year=work.get("publication_year") or 0,
        doi=doi or None,
        url=work.get("id", ""),
        venue=venue,
        keywords=keywords,
        source="openalex",
        source_id=work.get("id", ""),
        type=work.get("type"),
        is_oa=(work.get("open_access") or {}).get("is_oa"),
        issn=issn,
    )


def search_openalex(query: str, date_start: str, date_end: str,
                    max_results: int = 500, email: str = "",
                    filters: SearchFilters | None = None,
                    api_key: str = "", *,
                    status: SearchStatus | None = None,
                    should_cancel: Callable[[], bool] | None = None) -> list[Paper]:
    """Search OpenAlex and return normalized Paper objects.

    Fills ``status`` (see :class:`~prisma_review.search.http.SearchStatus`):
    a refused page, a rate limit that outlasts the retries or the 10,000
    result limit of keyless paging ends the query as ``partial`` (or
    ``failed`` if nothing came back) with a message saying why.
    """
    status = status if status is not None else SearchStatus("openalex")
    params = build_params(query, date_start, date_end, filters)
    per_page = max(1, min(PER_PAGE, max_results))
    use_cursor = bool(api_key)
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if email:
        headers["User-Agent"] = f"{http.USER_AGENT} (mailto:{email})"
    secrets = [api_key, email]

    search_param = next(k for k in params if k.startswith("search"))
    status.executed = params[search_param]
    status.request = {"method": "GET", "url": API_URL,
                      "params": {**params, "per_page": per_page},
                      "paging": "cursor" if use_cursor else "page",
                      "api_key": bool(api_key)}

    papers: list[Paper] = []
    page, cursor = 1, "*"
    try:
        while len(papers) < max_results:
            if not use_cursor and (page - 1) * per_page >= PAGE_PAGING_LIMIT:
                status.stop(f"OpenAlex pages past {PAGE_PAGING_LIMIT:,} results only with cursor "
                            f"paging, which needs an API key; {len(papers)} of "
                            f"{status.api_total} records retrieved. {KEY_HINT}", bool(papers))
                break
            page_params = dict(params, per_page=per_page)
            if use_cursor:
                page_params["cursor"] = cursor
            else:
                page_params["page"] = page

            resp = http.get(API_URL, params=page_params, headers=headers, timeout=30,
                            should_cancel=should_cancel, secrets=secrets, label="OpenAlex")
            if resp.status_code != 200:
                detail = http.redact(http.api_message(resp), secrets)
                where = f"page {page}" if page > 1 else "the first page"
                msg = f"OpenAlex HTTP {resp.status_code} on {where}: {detail}"
                if resp.status_code in (401, 403) or "api key" in detail.lower():
                    msg += f". {KEY_HINT}"
                status.stop(msg, bool(papers))
                print(f"  [!] {msg}")
                break

            data = resp.json()
            meta = data.get("meta") or {}
            if status.api_total is None and meta.get("count") is not None:
                status.api_total = int(meta["count"])
            results = data.get("results") or []
            if not results:
                break
            for work in results:
                if len(papers) >= max_results:
                    break
                paper = _parse(work)
                if paper:
                    papers.append(paper)
            status.retrieved = len(papers)

            if use_cursor:
                cursor = meta.get("next_cursor")
                if not cursor:
                    break
            else:
                page += 1
                if status.api_total is not None and (page - 1) * per_page >= status.api_total:
                    break
    except SearchCancelled:
        status.cancel()
    except SearchRequestError as exc:
        status.stop(f"OpenAlex: {exc}", bool(papers))
        print(f"  [!] OpenAlex search error: {exc}")
    except ValueError as exc:  # a body that is not JSON
        status.stop(f"OpenAlex returned an unreadable response: {exc}", bool(papers))

    status.retrieved = len(papers)
    return papers
