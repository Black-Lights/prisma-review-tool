"""Semantic Scholar search backend using REST API."""

from __future__ import annotations

import re
import time
import requests
from ..models import Paper

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,authors,externalIds,year,venue,publicationTypes"


def _clean_query(query: str) -> str:
    """Simplify boolean query for Semantic Scholar."""
    phrases = re.findall(r'"([^"]+)"', query)
    if phrases:
        return " ".join(phrases[:5])
    clean = re.sub(r'\b(AND|OR|NOT)\b', ' ', query)
    clean = re.sub(r'[()"]', '', clean)
    return ' '.join(clean.split())[:200]


def search_semantic_scholar(query: str, date_start: str, date_end: str,
                             max_results: int = 500) -> list[Paper]:
    """Search Semantic Scholar and return normalized Paper objects."""
    search_text = _clean_query(query)
    start_year = int(date_start[:4])
    end_year = int(date_end[:4])

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

    return papers
