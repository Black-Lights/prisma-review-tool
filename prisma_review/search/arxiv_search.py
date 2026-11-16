"""arXiv search backend using the arxiv Python package."""

from __future__ import annotations

from typing import Callable, Optional

import arxiv
from ..models import Paper
from .filters import SearchFilters
from .http import SearchStatus, strip_query
from .query_plan import arxiv_query

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)

PAGE_SIZE = 100
DELAY_SECONDS = 3.0  # arXiv asks for at least 3 s between calls


class _CountingClient(arxiv.Client):
    """arxiv.Client that remembers the total the API reported on the first page."""

    total_results: Optional[int] = None

    def _parse_feed(self, url, first_page=True, _try_index=0):
        feed = super()._parse_feed(url, first_page=first_page, _try_index=_try_index)
        if first_page:
            total = getattr(getattr(feed, "header", None), "total_results", None)
            if isinstance(total, int):
                self.total_results = total
        return feed


def search_arxiv(query: str, date_start: str, date_end: str, max_results: int = 500,
                 filters: SearchFilters | None = None, *,
                 status: SearchStatus | None = None,
                 should_cancel: Callable[[], bool] | None = None) -> list[Paper]:
    """Search arXiv and return normalized Paper objects (fills ``status``).

    arXiv exposes no native facet for document type / open access / venue;
    every record is a preprint and open access. See filters.filter_modes.
    """
    status = status if status is not None else SearchStatus("arxiv")
    translated = arxiv_query(query, date_start, date_end)
    status.executed = translated
    status.request = {"method": "GET", "url": arxiv.Client.query_url_format.split("?")[0],
                      "params": {"search_query": translated, "sortBy": "relevance"},
                      "paging": "start"}

    client = _CountingClient(page_size=max(1, min(PAGE_SIZE, max_results)),
                             delay_seconds=DELAY_SECONDS, num_retries=5)
    search = arxiv.Search(
        query=translated,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    papers: list[Paper] = []
    start_year, end_year = int(date_start[:4]), int(date_end[:4])
    try:
        for result in client.results(search):
            if should_cancel is not None and should_cancel():
                status.cancel()
                break
            year = result.published.year
            if year < start_year or year > end_year:
                continue  # the date range is in the query; this is only a guard

            papers.append(Paper(
                title=result.title.strip().replace("\n", " "),
                authors=[a.name for a in result.authors],
                abstract=result.summary.strip().replace("\n", " "),
                year=year,
                doi=result.doi,
                url=result.entry_id,
                venue="arXiv",
                keywords=list(result.categories) if result.categories else [],
                source="arxiv",
                source_id=result.entry_id,
                type="preprint",
                is_oa=True,
            ))
    except Exception as e:  # arxiv.HTTPError, UnexpectedEmptyPageError, network errors
        status.stop(f"arXiv: {strip_query(str(e))}", bool(papers))
        print(f"\n    [!] arXiv API error: {e}")

    status.api_total = client.total_results
    status.retrieved = len(papers)
    return papers
