"""Deduplication: which record is kept, what it absorbs, and provenance (SEARCH#1, 10, 16)."""

from __future__ import annotations

from prisma_review import download
from prisma_review.dedup import deduplicate
from prisma_review.models import Paper, load_papers, save_papers

LONG = "A long abstract about crop yield prediction. " * 10


def test_record_with_an_abstract_beats_a_bare_crossref_record():
    a = Paper(title="Crop yield prediction with deep learning", abstract="", doi="10.1/x",
              source="crossref", source_id="10.1/x", year=2023, matched_queries=["q1"])
    b = Paper(title="Crop yield prediction with deep learning", abstract=LONG, doi="10.1/X",
              source="openalex", source_id="W1", year=2023, matched_queries=["q2"], is_oa=True)
    unique, log = deduplicate([a, b])

    [kept] = unique
    assert kept is b and kept.abstract == LONG and kept.is_oa is True
    assert kept.matched_queries == ["q1", "q2"]
    assert kept.found_in_sources == ["crossref", "openalex"]
    assert kept.source_ids == {"openalex": "W1", "crossref": "10.1/x"}
    assert a.duplicate_of == b.id and log[0]["match_method"] == "doi"


def test_source_priority_only_breaks_ties():
    a = Paper(title="Same", abstract=LONG, doi="10.1/y", authors=["X"], source="crossref", year=2023)
    b = Paper(title="Same", abstract=LONG, doi="10.1/y", authors=["X"], source="openalex", year=2023)
    unique, _ = deduplicate([b, a])
    assert unique == [a]


def test_kept_record_fills_its_gaps_from_duplicates():
    arxiv = Paper(title="Model routing for LLM cost reduction", abstract=LONG, source="arxiv",
                  source_id="http://arxiv.org/abs/2401.00001v1", url="http://arxiv.org/abs/2401.00001v1",
                  year=2024, authors=["Ada Lovelace"])
    crossref = Paper(title="Model Routing for LLM Cost Reduction", abstract="", doi="10.5/routing",
                     source="crossref", source_id="10.5/routing", year=2024, venue="J. Things",
                     issn="1234-5678", type="journal-article", authors=["Ada Lovelace"])
    unique, log = deduplicate([crossref, arxiv])

    [kept] = unique
    assert kept is arxiv
    assert kept.doi == "10.5/routing" and kept.venue == "J. Things" and kept.issn == "1234-5678"
    assert kept.source_ids["arxiv"].endswith("2401.00001v1")
    assert log[0]["match_method"] == "fuzzy_title"


def test_fuzzy_cluster_keeps_every_query_and_points_at_the_kept_record():
    i = Paper(title="A survey of model routing for LLM cost", source="openalex", year=2024,
              matched_queries=["qA"])
    j = Paper(title="A survey of model routing for LLM cost", source="crossref", year=2024,
              matched_queries=["qB"])
    k = Paper(title="A survey of model routing for LLM cost", source="arxiv", year=2024,
              matched_queries=["qC"])
    unique, log = deduplicate([i, j, k], doi_match=False)

    [kept] = unique
    assert kept.matched_queries == ["qA", "qB", "qC"]
    assert sorted(kept.found_in_sources) == ["arxiv", "crossref", "openalex"]
    others = [p for p in (i, j, k) if p is not kept]
    assert all(p.duplicate_of == kept.id for p in others)
    assert len(log) == 2 and all(e["canonical_id"] == kept.id for e in log)


def test_doi_duplicate_chain_resolves_to_the_final_record():
    # a and b share a DOI; b then matches c by title, and c is the most complete.
    a = Paper(title="Deep crop yield models", doi="10.9/a", source="scopus", year=2023,
              matched_queries=["q1"])
    b = Paper(title="Deep crop yield models", doi="10.9/a", source="openalex", year=2023,
              matched_queries=["q2"])
    c = Paper(title="Deep crop yield models", abstract=LONG, doi="10.9/other", authors=["Z"],
              source="semantic_scholar", year=2023, matched_queries=["q3"])
    unique, log = deduplicate([a, b, c])

    assert unique == [c]
    assert a.duplicate_of == c.id and b.duplicate_of == c.id
    assert c.matched_queries == ["q1", "q2", "q3"]
    assert {e["canonical_id"] for e in log} == {c.id}


def test_borderline_titles_need_the_same_first_author():
    # Pairwise title scores: a-b 85.9, b-c 85.0 (borderline), a-c 79.1 (no match).
    base = "Crop yield forecasting from satellite imagery in "
    a = Paper(title=base + "Punjab districts", authors=["Ada Lovelace"], source="openalex", year=2023)
    b = Paper(title=base + "Punjab regions", authors=["Grace Lovelace"], source="scopus", year=2023)
    c = Paper(title=base + "Sindh provinces", authors=["Alan Turing"], source="arxiv", year=2023)
    unique, _ = deduplicate([a, b, c], doi_match=False)
    assert c in unique and len(unique) == 2

    c2 = Paper(title=c.title, authors=["Alan Lovelace"], source="arxiv", year=2023)
    a2 = Paper(title=a.title, authors=a.authors, source="openalex", year=2023)
    b2 = Paper(title=b.title, authors=b.authors, source="scopus", year=2023)
    unique, _ = deduplicate([a2, b2, c2], doi_match=False)
    assert len(unique) == 1  # a-b and b-c both match, so all three are one paper


def test_old_records_without_provenance_fields_still_load_and_merge(tmp_path):
    path = tmp_path / "old.json"
    save_papers([Paper(title="Old paper", source="openalex", doi="10.1/o", year=2020),
                 Paper(title="Old paper", source="scopus", doi="10.1/o", year=2020)], path)
    raw = path.read_text(encoding="utf-8").replace('"found_in_sources": [],', "").replace(
        '"source_ids": {},', "")
    path.write_text(raw, encoding="utf-8")

    papers = load_papers(path)
    assert papers[0].found_in_sources == [] and papers[0].source_ids == {}
    unique, _ = deduplicate(papers)
    assert unique[0].found_in_sources == ["openalex", "scopus"]


def test_download_uses_the_arxiv_id_kept_by_dedup(tmp_path, monkeypatch):
    paper = Paper(title="Model routing", source="openalex", url="https://openalex.org/W1",
                  doi="10.5/routing", source_ids={"openalex": "https://openalex.org/W1",
                                                  "arxiv": "http://arxiv.org/abs/2401.00001v1"})
    fetched = []
    monkeypatch.setattr(download, "_download_pdf", lambda url, path: fetched.append(url) or True)
    monkeypatch.setattr(download, "_get_semantic_scholar_pdf_url",
                        lambda doi: (_ for _ in ()).throw(AssertionError("no lookup needed")))
    stats = download.download_papers([paper], tmp_path, email="", api_key="", delay=0)
    assert fetched == ["https://arxiv.org/pdf/2401.00001v1.pdf"]
    assert stats["downloaded"] == 1
