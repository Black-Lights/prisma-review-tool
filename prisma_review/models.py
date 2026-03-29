"""Unified paper data model for all sources."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional
import json
from pathlib import Path


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
    source: str = ""  # "arxiv", "openalex", "semantic_scholar", "scopus"
    source_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.to_dict() for p in papers], f, indent=2, ensure_ascii=False)


def load_papers(path: Path) -> list[Paper]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [Paper.from_dict(d) for d in json.load(f)]
