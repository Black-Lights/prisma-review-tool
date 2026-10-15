"""Semantic Scholar search backend using REST API."""

from __future__ import annotations

import time
import requests
from ..models import Paper
from .query_plan import text_search_query
from .filters import SearchFilters, build_semantic_params, apply_post_filters

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,authors,externalIds,year,venue,publicationTypes,openAccessPdf"


def _clean_query(query: str) -> str:
    """Reduce a Boolean query to Semantic Scholar's plain-text search string.

    Delegates to the shared helper so the transparency warnings reported by
    ``search.query_plan`` match exactly what is sent here.
    """
    return text_search_query(query)


def search_semantic_scholar(query: str, date_start: str, date_end: str,
                             max_results: int = 500,
                             filters: SearchFilters | None = None) -> list[Paper]:
    """Search Semantic Scholar and return normalized Paper objects."""
    search_text = _clean_query(query)
    start_year = int(date_start[:4])
    end_year = int(date_end[:4])

    # Request channel: supported facets as extra query params.
    facet_params = build_semantic_params(filters) if filters else {}

    papers = []
    offset = 0
    batch_size = 100
    retries = 0
    max_retries = 3

    while offset < max_results:
        params = {
            "query": search_text,
            "year": f"{start_year}-{end_year}",
            "limit": min(batch_size, max_results - offset),
            "offset": offset,
            "fields": FIELDS,
            **facet_params,
        }

        try:
            resp = requests.get(API_URL, params=params, timeout=30)

            if resp.status_code == 429:
                retries += 1
                if retries > max_retries:
                    print(f"  [!] Rate limited {max_retries} times, moving on with {len(papers)} papers")
                    break
                wait = 30 * retries
                print(f"  [!] Rate limited, waiting {wait}s (attempt {retries}/{max_retries})...")
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                print(f"  [!] Semantic Scholar API error: {resp.status_code}")
                break

            retries = 0  # Reset on success
            data = resp.json()
            results = data.get("data", [])

            if not results:
                break

            for item in results:
                title = item.get("title", "")
                if not title:
                    continue

                authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
                ext_ids = item.get("externalIds") or {}
                doi = ext_ids.get("DOI")
                pub_types = item.get("publicationTypes") or []

                paper = Paper(
                    title=title.strip(),
                    authors=authors,
                    abstract=(item.get("abstract") or "").strip(),
                    year=item.get("year") or 0,
                    doi=doi,
                    url=f"https://api.semanticscholar.org/CorpusID:{ext_ids.get('CorpusId', '')}",
                    venue=item.get("venue") or "",
                    keywords=[],
                    source="semantic_scholar",
                    source_id=item.get("paperId", ""),
                    type=pub_types[0] if pub_types else None,
                    is_oa=bool(item.get("openAccessPdf")),
                    issn=(ext_ids.get("ISSN") or None),
                )
                papers.append(paper)

            offset += len(results)
            total = data.get("total", 0)
            if offset >= total:
                break

            time.sleep(1)  # Respect rate limits

        except requests.exceptions.RequestException as e:
            print(f"  [!] Semantic Scholar request error: {e}")
            break

    # Post-request safety net (e.g. require_abstract, which has no S2 param).
    if filters:
        papers = apply_post_filters(papers, filters, "semantic_scholar")

    return papers
