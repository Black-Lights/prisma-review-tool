"""Orchestrate searches across all configured sources."""

from __future__ import annotations

from ..config import Config
from ..models import Paper
from .arxiv_search import search_arxiv
from .openalex_search import search_openalex
from .semantic_search import search_semantic_scholar
from .scopus_search import search_scopus


def run_all_searches(config: Config) -> dict[str, list[Paper]]:
    """Run search queries across all enabled sources. Returns dict keyed by source name."""
    results: dict[str, list[Paper]] = {}

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
                    papers = search_arxiv(query_terms, config.date_start, config.date_end, config.max_results)
                elif source == "openalex":
                    papers = search_openalex(query_terms, config.date_start, config.date_end,
                                             config.max_results, config.openalex_email)
                elif source == "semantic_scholar":
                    papers = search_semantic_scholar(query_terms, config.date_start, config.date_end, config.max_results)
                elif source == "scopus":
                    papers = search_scopus(query_terms, config.scopus_key,
                                           config.date_start, config.date_end, config.max_results)
                else:
                    print(f"unknown source, skipping")
                    continue

                results[key] = papers
                print(f"found {len(papers)} papers")

            except Exception as e:
                print(f"error: {e}")
                results[key] = []

    return results
