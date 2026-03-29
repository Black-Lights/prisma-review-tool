"""arXiv search backend using the arxiv Python package."""

from __future__ import annotations

import re
import arxiv
from ..models import Paper


def _translate_query(query: str) -> str:
    """Translate boolean query to arXiv API format.

    arXiv uses: all:"term" for full-text search, AND/OR operators.
    Quoted phrases stay as-is, unquoted terms get wrapped in all:"".
    """
    # arXiv API handles AND/OR natively, just need to handle quoted phrases
    # Replace ("term") patterns with all:"term"
    result = query
    # Find quoted phrases and wrap them
    phrases = re.findall(r'"([^"]+)"', result)
    for phrase in phrases:
        result = result.replace(f'"{phrase}"', f'all:"{phrase}"')
    return result


def search_arxiv(query: str, date_start: str, date_end: str, max_results: int = 500) -> list[Paper]:
    """Search arXiv and return normalized Paper objects."""
    translated = _translate_query(query)

    client = arxiv.Client(page_size=50, delay_seconds=5.0, num_retries=5)
    search = arxiv.Search(
        query=translated,
        max_results=min(max_results, 500),
        sort_by=arxiv.SortCriterion.Relevance,
    )

    papers = []
    start_year = int(date_start[:4])
    end_year = int(date_end[:4])

    try:
        results_iter = client.results(search)
    except Exception as e:
        print(f"\n    [!] arXiv API error: {e}")
        return papers

    for result in results_iter:
        year = result.published.year
        if year < start_year or year > end_year:
            continue

        paper = Paper(
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
        )
        papers.append(paper)

    return papers
