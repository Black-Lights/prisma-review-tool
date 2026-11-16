"""Unified paper data model for all sources."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

from .storage import atomic_write_json, read_json


@dataclass
class Paper:
    """Unified representation of a research paper from any source."""

    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    year: int = 0
    doi: Optional[str] = None
    url: Optional[str] = None
    venue: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    source: str = ""  # "arxiv", "crossref", "openalex", "semantic_scholar", "scopus"
    source_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Filterable metadata, retained from each source so the post-request
    # fallback in search.filters can evaluate them. The values are the RAW
    # per-source strings (e.g. "article" from OpenAlex, "journal-article" from
    # Crossref); search.filters maps canonical names to these. ``is_oa`` is
    # tri-state: True/False when the source reports it, None when unknown (so
    # the post-filter keeps a paper rather than excluding on missing data).
    type: Optional[str] = None       # raw document type from the source
    is_oa: Optional[bool] = None     # open-access flag (None = unknown)
    issn: Optional[str] = None       # primary ISSN of the venue, if known

    # Names of the configured queries (see config.queries) that returned this
    # paper. A single-element list at search time; on dedup the canonical paper
    # absorbs the query names of its duplicates, so a paper found by more than
    # one query lists them all. Lets the report attribute results per query
    # (with overlap — queries are OR'd, so a paper may belong to several).
    matched_queries: list[str] = field(default_factory=list)

    # Every source that returned this paper, and each source's own record id.
    # A single entry at search time; on dedup the canonical paper absorbs those
    # of its duplicates, so it still knows it was on arXiv (download.py uses the
    # arXiv id) even when another source's record was kept. Empty for records
    # saved before v1.6, which only know ``source``.
    found_in_sources: list[str] = field(default_factory=list)
    source_ids: dict[str, str] = field(default_factory=dict)

    # Other DOIs of the same work, from records dedup merged into this one
    # (e.g. the arXiv DOI of a preprint whose published version is kept).
    alt_dois: list[str] = field(default_factory=list)

    # Screening fields (populated later)
    screen_decision: Optional[str] = None  # "include", "exclude", "maybe"
    screen_reason: Optional[str] = None
    screen_method: Optional[str] = None  # "rule", "ai", "manual"

    # Eligibility screening fields (second pass — stricter criteria)
    eligibility_decision: Optional[str] = None  # "include", "exclude"
    eligibility_reason: Optional[str] = None
    eligibility_method: Optional[str] = None  # "ai", "manual"

    # Dedup fields
    duplicate_of: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Paper:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def normalized_doi(self) -> Optional[str]:
        if not self.doi:
            return None
        doi = self.doi.strip().lower()
        for prefix in ["https://doi.org/", "http://doi.org/", "doi:"]:
            if doi.startswith(prefix):
                doi = doi[len(prefix):]
        return doi

    @property
    def bibtex_key(self) -> str:
        first_author = ""
        if self.authors:
            parts = self.authors[0].replace(",", " ").split()
            first_author = parts[-1] if parts else "Unknown"
        year = str(self.year) if self.year else "XXXX"
        return f"{first_author}{year}"


def save_papers(papers: list[Paper], path: Path) -> None:
    # Atomic: a reader in another process never sees a half-written file.
    atomic_write_json(path, [p.to_dict() for p in papers], indent=2, ensure_ascii=False)


def load_papers(path: Path) -> list[Paper]:
    return [Paper.from_dict(d) for d in read_json(path, default=[])]
