"""Scopus search backend using the Elsevier Scopus Search API.

Requires an API key from https://dev.elsevier.com (institutional access).
Usage must comply with the Elsevier API Service Agreement.
"""

from __future__ import annotations

from typing import Callable

from ..models import Paper
from . import http
from .filters import SearchFilters, normalize_issn
from .http import SearchCancelled, SearchRequestError, SearchStatus
from .query_plan import scopus_query

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

API_URL = "https://api.elsevier.com/content/search/scopus"
PAGE_SIZE = 25  # Scopus default and max per request
_EMPTY_RESULT = "Result set was empty"

STANDARD_VIEW_NOTE = (
    "Scopus refused the COMPLETE view (it needs institutional network access), so the "
    "STANDARD view was used: Scopus records have no abstracts and only the first author. "
    "require_abstract was not applied to them, and screening sees their titles only."
)


def _parse(item: dict) -> Paper | None:
    title = item.get("dc:title", "")
    if not title:
        return None

    authors = []
    creator = item.get("dc:creator", "")
    if creator:
        authors.append(creator)
    author_list = item.get("author", [])
    if isinstance(author_list, list):
        for auth in author_list:
            name = auth.get("authname", "") or auth.get("given-name", "")
            if name and name != creator:
                authors.append(name)

    # Year from cover date (format: YYYY-MM-DD)
    cover_date = item.get("prism:coverDate", "")
    year = int(cover_date[:4]) if cover_date and cover_date[:4].isdigit() else 0

    scopus_id = item.get("dc:identifier", "")  # e.g. "SCOPUS_ID:85012345678"
    eid = item.get("eid", "")

    keywords: list[str] = []
    authkeywords = item.get("authkeywords", "")
    if authkeywords and isinstance(authkeywords, str):
        keywords = [k.strip() for k in authkeywords.split("|") if k.strip()]

    oa_flag = item.get("openaccessFlag")
    return Paper(
        title=title.strip(),
        authors=authors,
        abstract=(item.get("dc:description", "") or "").strip(),
        year=year,
        doi=item.get("prism:doi"),
        url=f"https://www.scopus.com/record/display.uri?eid={eid}" if eid else "",
        venue=item.get("prism:publicationName", "") or "",
        keywords=keywords,
        source="scopus",
        source_id=scopus_id.replace("SCOPUS_ID:", "") if scopus_id else eid,
        type=item.get("subtype"),
        is_oa=(bool(oa_flag) if oa_flag is not None else None),
        # Scopus sends ISSNs without the hyphen (00344257).
        issn=normalize_issn(item.get("prism:issn")) or normalize_issn(item.get("prism:eIssn")),
    )


def search_scopus(
    query: str,
    api_key: str,
    date_start: str,
    date_end: str,
    max_results: int = 500,
    filters: SearchFilters | None = None,
    *,
    status: SearchStatus | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[Paper]:
    """Search Scopus and return normalized Paper objects (fills ``status``).

    Args:
        query: Boolean search query string
        api_key: Elsevier API key (from dev.elsevier.com)
        date_start: Start date (YYYY-MM-DD)
        date_end: End date (YYYY-MM-DD)
        max_results: Maximum number of results to return

    Returns:
        List of Paper objects with source="scopus"
    """
    status = status if status is not None else SearchStatus("scopus")
    if not api_key:
        status.status = "skipped"
        status.error = "no Scopus API key configured (api_keys.scopus)"
        print("  [!] No Scopus API key configured, skipping")
        return []

    q = scopus_query(query, date_start, date_end, filters)
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    view = "COMPLETE"  # Try COMPLETE first (includes abstracts, needs institutional IP)
    status.executed = q
    status.request = {"method": "GET", "url": API_URL, "params": {"query": q, "view": view},
                      "paging": "start"}

    papers: list[Paper] = []
    start = 0
    try:
        while start < max_results:
            params = {"query": q, "count": min(PAGE_SIZE, max_results - start),
                      "start": start, "view": view}
            resp = http.get(API_URL, params=params, headers=headers, timeout=30,
                            should_cancel=should_cancel, secrets=[api_key], label="Scopus")

            if resp.status_code == 401 and view == "COMPLETE":
                # COMPLETE view requires institutional IP: fall back to STANDARD
                print("  [!] COMPLETE view unauthorized (not on campus?), falling back to STANDARD view")
                view = "STANDARD"
                status.request["params"]["view"] = view
                status.notes.append(STANDARD_VIEW_NOTE)
                status.skip_post_filters.add("require_abstract")
                # The records are incomplete (no abstracts): report it as a
                # warning-worthy status, not only in the search log.
                status.status, status.error = "partial", STANDARD_VIEW_NOTE
                continue

            if resp.status_code != 200:
                detail = http.redact(http.api_message(resp), [api_key])
                if resp.status_code == 401:
                    msg = f"Scopus API key invalid or unauthorized: {detail}"
                elif resp.status_code == 403:
                    msg = f"Scopus access denied, check institutional access or entitlements: {detail}"
                else:
                    msg = f"Scopus HTTP {resp.status_code}: {detail}"
                status.stop(msg, bool(papers))
                print(f"  [!] {msg}")
                break

            search_results = resp.json().get("search-results", {})
            total = search_results.get("opensearch:totalResults")
            if status.api_total is None and str(total or "").isdigit():
                status.api_total = int(total)
            entries = search_results.get("entry", [])

            # Scopus returns errors (and "no results") as an entry.
            if entries and "error" in entries[0]:
                error_msg = str(entries[0].get("error", "Unknown error"))
                if error_msg != _EMPTY_RESULT:
                    status.stop(f"Scopus search error: {error_msg}", bool(papers))
                    print(f"  [!] Scopus search error: {error_msg}")
                break
            if not entries:
                break

            for item in entries:
                paper = _parse(item)
                if paper:
                    papers.append(paper)
            status.retrieved = len(papers)

            start += len(entries)
            if start >= (status.api_total or 0) or start >= max_results:
                break
            http.wait(0.5, should_cancel)  # Be polite to the API
    except SearchCancelled:
        status.cancel()
    except SearchRequestError as exc:
        status.stop(f"Scopus: {exc}", bool(papers))
        print(f"  [!] Scopus request error: {exc}")
    except ValueError as exc:
        status.stop(f"Scopus returned an unreadable response: {exc}", bool(papers))

    status.retrieved = len(papers)
    return papers
