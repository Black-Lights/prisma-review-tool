"""Scopus search backend using the Elsevier Scopus Search API.

Requires an API key from https://dev.elsevier.com (institutional access).
Usage must comply with the Elsevier API Service Agreement.
"""

from __future__ import annotations

import re
import time
import requests
from ..models import Paper

API_URL = "https://api.elsevier.com/content/search/scopus"
PAGE_SIZE = 25  # Scopus default and max per request


def _build_scopus_query(query: str, date_start: str, date_end: str) -> str:
    """Translate a Boolean query into Scopus search syntax.

    Wraps the user query with TITLE-ABS-KEY() for field-scoped search
    and appends a PUBYEAR range filter.
    """
    # Extract the core query — strip outer whitespace/newlines
    q = " ".join(query.split())

    # Wrap in TITLE-ABS-KEY if not already scoped
    if not re.match(r"(?i)(TITLE|ABS|KEY|AUTH|SRCTITLE|TITLE-ABS-KEY)\s*\(", q):
        q = f"TITLE-ABS-KEY({q})"

    # Add date range
    start_year = int(date_start[:4])
    end_year = int(date_end[:4])
    q += f" AND PUBYEAR > {start_year - 1} AND PUBYEAR < {end_year + 1}"

    return q


def search_scopus(
    query: str,
    api_key: str,
    date_start: str,
    date_end: str,
    max_results: int = 500,
) -> list[Paper]:
    """Search Scopus and return normalized Paper objects.

    Args:
        query: Boolean search query string
        api_key: Elsevier API key (from dev.elsevier.com)
        date_start: Start date (YYYY-MM-DD)
        date_end: End date (YYYY-MM-DD)
        max_results: Maximum number of results to return

    Returns:
        List of Paper objects with source="scopus"
    """
    if not api_key:
        print("  [!] No Scopus API key configured, skipping")
        return []

    scopus_query = _build_scopus_query(query, date_start, date_end)

    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json",
    }

    papers: list[Paper] = []
    start = 0
    retries = 0
    max_retries = 3

    while start < max_results:
        params = {
            "query": scopus_query,
            "count": min(PAGE_SIZE, max_results - start),
            "start": start,
            "view": "COMPLETE",  # Includes abstract
        }

        try:
            resp = requests.get(API_URL, headers=headers, params=params, timeout=30)

            if resp.status_code == 429:
                retries += 1
                if retries > max_retries:
                    print(f"  [!] Rate limited {max_retries} times, moving on with {len(papers)} papers")
                    break
                wait = 30 * retries
                print(f"  [!] Rate limited, waiting {wait}s (attempt {retries}/{max_retries})...")
                time.sleep(wait)
                continue

            if resp.status_code == 401:
                print("  [!] Scopus API key invalid or unauthorized")
                break

            if resp.status_code == 403:
                print("  [!] Scopus API access denied — check institutional access / entitlements")
                break

            if resp.status_code != 200:
                print(f"  [!] Scopus API error: {resp.status_code}")
                break

            retries = 0
            data = resp.json()
            search_results = data.get("search-results", {})
            entries = search_results.get("entry", [])

            # Check for error entries (Scopus returns error as an entry)
            if entries and "error" in entries[0]:
                error_msg = entries[0].get("error", "Unknown error")
                print(f"  [!] Scopus search error: {error_msg}")
                break

            if not entries:
                break

            for item in entries:
                title = item.get("dc:title", "")
                if not title:
                    continue

                # Parse authors
                authors = []
                creator = item.get("dc:creator", "")
                if creator:
                    authors.append(creator)
                # Additional authors from author array
                author_list = item.get("author", [])
                if isinstance(author_list, list):
                    for auth in author_list:
                        name = auth.get("authname", "") or auth.get("given-name", "")
                        if name and name != creator:
                            authors.append(name)

                # Parse year from cover date (format: YYYY-MM-DD)
                cover_date = item.get("prism:coverDate", "")
                year = int(cover_date[:4]) if cover_date and len(cover_date) >= 4 else 0

                # DOI
                doi = item.get("prism:doi")

                # Abstract
                abstract = item.get("dc:description", "") or ""

                # Venue (journal/conference name)
                venue = item.get("prism:publicationName", "") or ""

                # URL
                scopus_id = item.get("dc:identifier", "")  # e.g. "SCOPUS_ID:85012345678"
                eid = item.get("eid", "")
                url = f"https://www.scopus.com/record/display.uri?eid={eid}" if eid else ""

                # Keywords from authkeywords field
                keywords: list[str] = []
                authkeywords = item.get("authkeywords", "")
                if authkeywords and isinstance(authkeywords, str):
                    keywords = [k.strip() for k in authkeywords.split("|") if k.strip()]

                paper = Paper(
                    title=title.strip(),
                    authors=authors,
                    abstract=abstract.strip(),
                    year=year,
                    doi=doi,
                    url=url,
                    venue=venue,
                    keywords=keywords,
                    source="scopus",
                    source_id=scopus_id.replace("SCOPUS_ID:", "") if scopus_id else eid,
                )
                papers.append(paper)

            # Check pagination
            total_results = int(search_results.get("opensearch:totalResults", "0"))
            start += len(entries)

            if start >= total_results or start >= max_results:
                break

            time.sleep(0.5)  # Be polite to the API

        except requests.exceptions.RequestException as e:
            print(f"  [!] Scopus request error: {e}")
            break

    return papers
