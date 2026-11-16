"""Export papers to BibTeX and CSV formats."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from .models import Paper
from .storage import atomic_write_text


def _make_unique_keys(papers: list[Paper]) -> list[str]:
    """Generate unique BibTeX keys for a list of papers."""
    key_counts: dict[str, int] = defaultdict(int)
    keys: list[str] = []

    for paper in papers:
        base_key = paper.bibtex_key
        key_counts[base_key] += 1
        if key_counts[base_key] > 1:
            keys.append(f"{base_key}{chr(96 + key_counts[base_key])}")  # a, b, c...
        else:
            keys.append(base_key)

    # Fix first occurrence if there were duplicates
    for i, paper in enumerate(papers):
        base_key = paper.bibtex_key
        if key_counts[base_key] > 1 and keys[i] == base_key:
            keys[i] = f"{base_key}a"

    return keys


def _escape_bibtex(value: str) -> str:
    """Escape special BibTeX characters in a string."""
    return value.replace("{", "\\{").replace("}", "\\}")


def bibtex_text(papers: list[Paper]) -> str:
    """The papers as BibTeX entries."""
    keys = _make_unique_keys(papers)
    lines = []

    for paper, key in zip(papers, keys):
        lines.append(f"@article{{{key},")
        lines.append(f"  title = {{{_escape_bibtex(paper.title)}}},")
        author = " and ".join(paper.authors) if paper.authors else "Unknown"
        lines.append(f"  author = {{{_escape_bibtex(author)}}},")
        if paper.year:
            lines.append(f"  year = {{{paper.year}}},")
        if paper.doi:
            lines.append(f"  doi = {{{paper.doi}}},")
        if paper.url:
            lines.append(f"  url = {{{paper.url}}},")
        if paper.venue:
            lines.append(f"  journal = {{{_escape_bibtex(paper.venue)}}},")
        if paper.abstract:
            lines.append(f"  abstract = {{{_escape_bibtex(paper.abstract)}}},")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def export_bibtex(papers: list[Paper], path: Path) -> None:
    """Export papers to a .bib file."""
    atomic_write_text(path, bibtex_text(papers))


ALL_CSV_FIELDS = [
    "bibtex_key", "title", "authors", "year", "venue", "doi", "url",
    "abstract", "keywords", "source", "source_id",
    "screen_decision", "screen_reason", "screen_method",
    "eligibility_decision", "eligibility_reason", "eligibility_method",
]

DEFAULT_CSV_FIELDS = [
    "bibtex_key", "title", "authors", "year", "venue", "doi", "url",
    "source", "screen_decision",
]


def csv_text(papers: list[Paper], fields: list[str] | None = None) -> str:
    """The papers as CSV text with the given columns (None = the default set)."""
    use_fields = fields if fields else DEFAULT_CSV_FIELDS
    # Always generate bibtex_key if requested
    keys = _make_unique_keys(papers) if "bibtex_key" in use_fields else [None] * len(papers)

    rows = []
    for paper, key in zip(papers, keys):
        row: dict = {}
        for f in use_fields:
            if f == "bibtex_key":
                row[f] = key
            elif f == "authors":
                row[f] = "; ".join(paper.authors)
            elif f == "keywords":
                row[f] = "; ".join(paper.keywords)
            elif hasattr(paper, f):
                row[f] = getattr(paper, f) or ""
        rows.append(row)

    return pd.DataFrame(rows, columns=use_fields).to_csv(index=False)


def export_csv(
    papers: list[Paper],
    path: Path,
    fields: list[str] | None = None,
) -> None:
    """Export papers to a CSV file.

    Args:
        papers: Papers to export.
        path: Output file path.
        fields: Column names to include. None = default set.
    """
    atomic_write_text(path, csv_text(papers, fields))
