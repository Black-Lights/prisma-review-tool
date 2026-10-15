"""OpenAlex search backend using the pyalex library."""

from __future__ import annotations

from ..models import Paper
from .filters import SearchFilters, build_openalex_filters, apply_post_filters

try:
    import pyalex
    from pyalex import Works
    HAS_PYALEX = True
except ImportError:
    HAS_PYALEX = False

# Progress output must go to stderr: this module is imported by the stdio MCP
# server, where stdout is the JSON-RPC channel and any stray byte corrupts it.
import sys
import functools
print = functools.partial(print, file=sys.stderr)


def search_openalex(query: str, date_start: str, date_end: str,
                     max_results: int = 500, email: str = "",
                     filters: SearchFilters | None = None,
                     api_key: str = "") -> list[Paper]:
    """Search OpenAlex and return normalized Paper objects."""
    if not HAS_PYALEX:
        print("  [!] pyalex not installed, skipping OpenAlex")
        return []

    if email:
        pyalex.config.email = email
    if api_key:
        pyalex.config.api_key = api_key

    # OpenAlex's `search` parameter honours Boolean operators (AND/OR/NOT),
    # quoted phrases and parentheses natively, so send the raw query through.
    search_text = query
    start_year = int(date_start[:4])
    end_year = int(date_end[:4])

    papers = []
    try:
        results = (
            Works()
            .search(search_text)
            .filter(from_publication_date=date_start, to_publication_date=date_end)
            .select(["id", "title", "doi", "authorships", "publication_year",
                      "primary_location", "abstract_inverted_index", "keywords",
                      "type", "open_access"])
        )

        # Request channel: push supported facets server-side.
        if filters:
            facet_kwargs = build_openalex_filters(filters)
            if facet_kwargs:
                results = results.filter(**facet_kwargs)

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

                # Extract venue + ISSN
                venue = ""
                issn = None
                loc = work.get("primary_location")
                if loc and loc.get("source"):
                    src = loc["source"]
                    venue = src.get("display_name", "")
                    issn = src.get("issn_l") or (src.get("issn") or [None])[0]

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
                    type=work.get("type"),
                    is_oa=(work.get("open_access") or {}).get("is_oa"),
                    issn=issn,
                )
                papers.append(paper)
                count += 1

            if count >= max_results:
                break

    except Exception as e:
        print(f"  [!] OpenAlex search error: {e}")

    # Post-request safety net (no-op for facets already applied server-side).
    if filters:
        papers = apply_post_filters(papers, filters, "openalex")

    return papers
