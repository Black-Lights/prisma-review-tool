"""OpenAlex search backend using the pyalex library."""

from __future__ import annotations

import re
from ..models import Paper

try:
    import pyalex
    from pyalex import Works
    HAS_PYALEX = True
except ImportError:
    HAS_PYALEX = False


def _clean_query_for_openalex(query: str) -> str:
    """Simplify boolean query for OpenAlex search.

    OpenAlex search endpoint is a simple text search, not full boolean.
    Extract the key phrases and join them.
    """
    # Extract quoted phrases
    phrases = re.findall(r'"([^"]+)"', query)
    if phrases:
        return " ".join(phrases[:5])  # Use top phrases, keep it focused
    # Fallback: strip boolean operators
    clean = re.sub(r'\b(AND|OR|NOT)\b', ' ', query)
    clean = re.sub(r'[()"]', '', clean)
    return ' '.join(clean.split())[:200]


def search_openalex(query: str, date_start: str, date_end: str,
                     max_results: int = 500, email: str = "") -> list[Paper]:
    """Search OpenAlex and return normalized Paper objects."""
    if not HAS_PYALEX:
        print("  [!] pyalex not installed, skipping OpenAlex")
        return []

    if email:
        pyalex.config.email = email

    search_text = _clean_query_for_openalex(query)
    start_year = int(date_start[:4])
    end_year = int(date_end[:4])

    papers = []
    try:
        results = (
            Works()
            .search(search_text)
            .filter(from_publication_date=date_start, to_publication_date=date_end)
            .select(["id", "title", "doi", "authorships", "publication_year",
                      "primary_location", "abstract_inverted_index", "keywords"])
        )

        count = 0
        for page in results.paginate(per_page=50):
            for work in page:
                if count >= max_results:
                    break

                title = work.get("title", "")
                if not title:
                    continue

                # Reconstruct abstract from inverted index
                abstract = ""
                aii = work.get("abstract_inverted_index")
                if aii and isinstance(aii, dict):
                    try:
                        max_pos = max(max(v) for v in aii.values()) + 1
                        words = [""] * max_pos
                        for word, positions in aii.items():
                            for pos in positions:
                                if pos < max_pos:
                                    words[pos] = word
                        abstract = " ".join(w for w in words if w)
                    except (ValueError, TypeError):
                        abstract = ""

                # Extract authors
                authors = []
                for authorship in work.get("authorships", []):
                    author = authorship.get("author", {})
                    name = author.get("display_name", "")
                    if name:
                        authors.append(name)

                # Extract venue
                venue = ""
                loc = work.get("primary_location")
                if loc and loc.get("source"):
                    venue = loc["source"].get("display_name", "")

                # Extract DOI
                doi = work.get("doi", "")
                if doi and doi.startswith("https://doi.org/"):
                    doi = doi[len("https://doi.org/"):]

                year = work.get("publication_year", 0) or 0

                kw = [k.get("display_name", "") for k in work.get("keywords", []) if k.get("display_name")]

                paper = Paper(
                    title=title.strip(),
                    authors=authors,
                    abstract=abstract,
                    year=year,
                    doi=doi if doi else None,
                    url=work.get("id", ""),
                    venue=venue,
                    keywords=kw,
                    source="openalex",
                    source_id=work.get("id", ""),
                )
                papers.append(paper)
                count += 1

            if count >= max_results:
                break

    except Exception as e:
        print(f"  [!] OpenAlex search error: {e}")

    return papers
