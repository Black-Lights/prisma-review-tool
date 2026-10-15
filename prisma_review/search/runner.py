"""Orchestrate searches across all configured sources."""

from __future__ import annotations

from ..config import Config
from ..models import Paper
from .arxiv_search import search_arxiv
from .crossref_search import search_crossref
from .openalex_search import search_openalex
from .semantic_search import search_semantic_scholar
from .scopus_search import search_scopus
from .filters import SearchFilters

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)


def run_all_searches(config: Config) -> dict[str, list[Paper]]:
    """Run search queries across all enabled sources. Returns dict keyed by source name."""
    results: dict[str, list[Paper]] = {}
    filters = SearchFilters.from_config(config)

    for query_def in config.queries:
        query_name = query_def.get("name", "unnamed")
        query_terms = query_def.get("terms", "")

        if not query_terms.strip():
            continue

        print(f"\n  Query: {query_name}")

        for source in config.sources:
            key = f"{source}_{query_name}"
            print(f"    Searching {source}...", end=" ", flush=True)

            try:
                if source == "arxiv":
                    papers = search_arxiv(query_terms, config.date_start, config.date_end,
                                          config.max_results, filters)
                elif source == "crossref":
                    papers = search_crossref(query_terms, config.date_start, config.date_end,
                                             config.max_results, config.openalex_email, filters)
                elif source == "openalex":
                    papers = search_openalex(query_terms, config.date_start, config.date_end,
                                             config.max_results, config.openalex_email, filters,
                                             api_key=config.openalex_key)
                elif source == "semantic_scholar":
                    papers = search_semantic_scholar(query_terms, config.date_start, config.date_end,
                                                     config.max_results, filters)
                elif source == "scopus":
                    papers = search_scopus(query_terms, config.scopus_key,
                                           config.date_start, config.date_end,
                                           config.max_results, filters)
                else:
                    print(f"unknown source, skipping")
                    continue

                # Stamp provenance so the report can attribute results per
                # query. Dedup later unions these across merged duplicates.
                for p in papers:
                    p.matched_queries = [query_name]

                results[key] = papers
                print(f"found {len(papers)} papers")

            except Exception as e:
                print(f"error: {e}")
                results[key] = []

    return results
