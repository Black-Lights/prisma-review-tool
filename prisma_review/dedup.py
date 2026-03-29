"""Deduplicate papers using DOI matching and fuzzy title matching."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz

from .models import Paper


# Prefer sources with more complete metadata
SOURCE_PRIORITY = {
    "scopus": 0,
    "openalex": 1,
    "semantic_scholar": 2,
    "arxiv": 3,
}


def _pick_canonical(papers: list[Paper]) -> Paper:
    """Pick the paper with the most complete metadata as canonical."""
    def score(p: Paper) -> tuple:
        return (
            -SOURCE_PRIORITY.get(p.source, 99),
            len(p.abstract),
            len(p.authors),
            1 if p.doi else 0,
        )
    return max(papers, key=score)


def _first_author_last(paper: Paper) -> str:
    """Get normalized last name of first author."""
    if not paper.authors:
        return ""
    parts = paper.authors[0].replace(",", " ").split()
    return parts[-1].lower() if parts else ""


def deduplicate(papers: list[Paper], doi_match: bool = True,
                fuzzy_threshold: int = 90) -> tuple[list[Paper], list[dict]]:
    """Remove duplicates. Returns (unique_papers, duplicate_log)."""
    duplicate_log: list[dict] = []
    canonical_map: dict[str, Paper] = {}  # id -> canonical paper
    removed: set[str] = set()

    # Pass 1: DOI exact match
    if doi_match:
        doi_groups: dict[str, list[Paper]] = defaultdict(list)
        for p in papers:
            ndoi = p.normalized_doi
            if ndoi:
                doi_groups[ndoi].append(p)

        for doi, group in doi_groups.items():
            if len(group) > 1:
                canonical = _pick_canonical(group)
                for p in group:
                    if p.id != canonical.id:
                        p.duplicate_of = canonical.id
                        removed.add(p.id)
                        duplicate_log.append({
                            "duplicate_id": p.id,
                            "duplicate_title": p.title[:80],
                            "duplicate_source": p.source,
                            "canonical_id": canonical.id,
                            "canonical_title": canonical.title[:80],
                            "match_method": "doi",
                            "score": 100,
                        })

    # Pass 2: Fuzzy title matching for remaining papers
    remaining = [p for p in papers if p.id not in removed]

    # Bucket by year to reduce comparisons
    year_buckets: dict[int, list[Paper]] = defaultdict(list)
    for p in remaining:
        year_buckets[p.year].append(p)

    for year, bucket in year_buckets.items():
        n = len(bucket)
        for i in range(n):
            if bucket[i].id in removed:
                continue
            for j in range(i + 1, n):
                if bucket[j].id in removed:
                    continue

                score = fuzz.token_sort_ratio(
                    bucket[i].title.lower(),
                    bucket[j].title.lower()
                )

                if score >= fuzzy_threshold:
                    is_dup = True
                elif score >= 85:
                    # Borderline: also check first author
                    a1 = _first_author_last(bucket[i])
                    a2 = _first_author_last(bucket[j])
                    is_dup = a1 and a2 and a1 == a2
                else:
                    is_dup = False

                if is_dup:
                    canonical = _pick_canonical([bucket[i], bucket[j]])
                    dup = bucket[j] if canonical.id == bucket[i].id else bucket[i]
                    dup.duplicate_of = canonical.id
                    removed.add(dup.id)
                    duplicate_log.append({
                        "duplicate_id": dup.id,
                        "duplicate_title": dup.title[:80],
                        "duplicate_source": dup.source,
                        "canonical_id": canonical.id,
                        "canonical_title": canonical.title[:80],
                        "match_method": "fuzzy_title",
                        "score": score,
                    })

    unique = [p for p in papers if p.id not in removed]
    return unique, duplicate_log


def save_dedup_log(log: list[dict], path: Path) -> None:
    """Save duplicate log as CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not log:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=log[0].keys())
        writer.writeheader()
        writer.writerows(log)
