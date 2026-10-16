"""Deduplicate papers using DOI matching and fuzzy title matching."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
from rapidfuzz import fuzz, process

from .models import Paper


# Tie-break between equally complete records: prefer sources with cleaner
# bibliographic metadata. Completeness always comes first (see _pick_canonical).
SOURCE_PRIORITY = {
    "crossref": 0,
    "scopus": 1,
    "openalex": 2,
    "semantic_scholar": 3,
    "arxiv": 4,
}

# Titles at or above this score are compared by first author too (borderline).
_BORDERLINE_SCORE = 85
# Rows of the title score matrix computed at once (bounds memory on big years).
_CHUNK_ROWS = 1000


def _pick_canonical(papers: list[Paper]) -> Paper:
    """Pick the record to keep: the most complete one, source priority as tie-break.

    An abstract matters most (keyword rules and AI screening read it), then a
    DOI (dedup, download), then authors.
    """
    def score(p: Paper) -> tuple:
        return (
            1 if (p.abstract or "").strip() else 0,
            1 if p.doi else 0,
            1 if p.authors else 0,
            -SOURCE_PRIORITY.get(p.source, 99),
            len(p.abstract or ""),
            len(p.authors),
        )
    return max(papers, key=score)


def _sources_of(p: Paper) -> list[str]:
    return p.found_in_sources or ([p.source] if p.source else [])


def _absorb(canonical: Paper, group: list[Paper]) -> None:
    """Merge the provenance of ``group`` into ``canonical`` and fill its empty fields.

    Provenance (query names, sources, per-source ids) is the union over the
    group. Bibliographic fields the canonical lacks are taken from the first
    duplicate that has them, so the kept record loses nothing a duplicate knew.
    """
    others = [p for p in group if p is not canonical]
    canonical.matched_queries = sorted({q for g in group for q in g.matched_queries})
    canonical.found_in_sources = sorted({s for g in group for s in _sources_of(g)})
    ids: dict[str, str] = {}
    for g in [canonical] + others:
        if g.source and g.source_id:
            ids.setdefault(g.source, g.source_id)
        for src, sid in (g.source_ids or {}).items():
            ids.setdefault(src, sid)
    canonical.source_ids = ids

    for p in others:
        if not (canonical.abstract or "").strip() and (p.abstract or "").strip():
            canonical.abstract = p.abstract
        if not canonical.doi and p.doi:
            canonical.doi = p.doi
        if not canonical.authors and p.authors:
            canonical.authors = list(p.authors)
        if not canonical.year and p.year:
            canonical.year = p.year
        if not canonical.venue and p.venue:
            canonical.venue = p.venue
        if not canonical.url and p.url:
            canonical.url = p.url
        if not canonical.keywords and p.keywords:
            canonical.keywords = list(p.keywords)
        if not canonical.type and p.type:
            canonical.type = p.type
        if not canonical.issn and p.issn:
            canonical.issn = p.issn
    known_oa = [p.is_oa for p in [canonical] + others if p.is_oa is not None]
    if known_oa:
        canonical.is_oa = any(known_oa)


def _first_author_last(paper: Paper) -> str:
    """Get normalized last name of first author."""
    if not paper.authors:
        return ""
    parts = paper.authors[0].replace(",", " ").split()
    return parts[-1].lower() if parts else ""


def _title_clusters(bucket: list[Paper], fuzzy_threshold: int) -> list[list[int]]:
    """Group indices of ``bucket`` whose titles match, as connected components.

    A pair matches when ``token_sort_ratio`` of the lowercased titles reaches
    ``fuzzy_threshold``, or reaches the borderline score and the first
    authors' last names agree. Union-find makes the result independent of the
    order of the records, and every member of a cluster ends up merged into
    one canonical record.
    """
    n = len(bucket)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    titles = [p.title.lower() for p in bucket]
    cutoff = min(fuzzy_threshold, _BORDERLINE_SCORE)
    for start in range(0, n, _CHUNK_ROWS):
        rows = titles[start:start + _CHUNK_ROWS]
        scores = process.cdist(rows, titles, scorer=fuzz.token_sort_ratio,
                               score_cutoff=cutoff, dtype=np.float32, workers=-1)
        for r, j in zip(*scores.nonzero()):
            i = start + int(r)
            j = int(j)
            if j <= i:
                continue
            score = float(scores[r, j])
            if score >= fuzzy_threshold:
                is_dup = True
            elif score >= _BORDERLINE_SCORE:
                a1 = _first_author_last(bucket[i])
                a2 = _first_author_last(bucket[j])
                is_dup = bool(a1 and a2 and a1 == a2)
            else:
                is_dup = False
            if is_dup:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)
    return [members for members in clusters.values() if len(members) > 1]


def deduplicate(papers: list[Paper], doi_match: bool = True,
                fuzzy_threshold: int = 90) -> tuple[list[Paper], list[dict]]:
    """Remove duplicates. Returns (unique_papers, duplicate_log)."""
    duplicate_log: list[dict] = []
    removed: set[str] = set()
    by_id = {p.id: p for p in papers}

    def log_duplicate(dup: Paper, canonical: Paper, method: str, score: float) -> None:
        duplicate_log.append({
            "duplicate_id": dup.id,
            "duplicate_title": dup.title[:80],
            "duplicate_source": dup.source,
            "canonical_id": canonical.id,
            "canonical_title": canonical.title[:80],
            "match_method": method,
            "score": score,
        })

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
                _absorb(canonical, group)
                for p in group:
                    if p is not canonical:
                        p.duplicate_of = canonical.id
                        removed.add(p.id)
                        log_duplicate(p, canonical, "doi", 100)

    # Pass 2: Fuzzy title matching for remaining papers, bucketed by year to
    # reduce comparisons.
    remaining = [p for p in papers if p.id not in removed]
    year_buckets: dict[int, list[Paper]] = defaultdict(list)
    for p in remaining:
        year_buckets[p.year].append(p)

    for year, bucket in year_buckets.items():
        for members in _title_clusters(bucket, fuzzy_threshold):
            group = [bucket[i] for i in members]
            canonical = _pick_canonical(group)
            _absorb(canonical, group)
            for p in group:
                if p is not canonical:
                    p.duplicate_of = canonical.id
                    removed.add(p.id)
                    score = round(fuzz.token_sort_ratio(p.title.lower(), canonical.title.lower()), 1)
                    log_duplicate(p, canonical, "fuzzy_title", score)

    # A DOI duplicate whose canonical was then merged by title points at a
    # removed record: follow the chain to the record that was kept.
    def final(pid: str) -> str:
        seen = set()
        while pid in by_id and by_id[pid].duplicate_of and pid not in seen:
            seen.add(pid)
            pid = by_id[pid].duplicate_of
        return pid

    for p in papers:
        if p.duplicate_of:
            p.duplicate_of = final(p.duplicate_of)
    for entry in duplicate_log:
        target = final(entry["canonical_id"])
        if target != entry["canonical_id"] and target in by_id:
            entry["canonical_id"] = target
            entry["canonical_title"] = by_id[target].title[:80]

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
