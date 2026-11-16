"""PRISMA and search findings of the v1.6 review.

R-14 (searches cut at max_results_per_query are reported), R-15 (the version
of record wins over its preprint in dedup), R-16 (venue names match however
they are written), R-26 (quoted wildcard phrases warned about for OpenAlex).
"""

from __future__ import annotations

import json

from conftest import write_dataset
from prisma_review.config import Config
from test_search_runner import backends, config  # noqa: F401  (fixture)


# --------------------------------------------------------------------------- R-14


def test_a_capped_search_is_a_warning_and_the_log_says_truncated(tmp_path, backends):
    from prisma_review import pipeline

    backends["openalex"].n = 30  # api_total 300, cap 25 in make_config
    backends["crossref"].n = 30
    cfg = config(tmp_path, sources=["openalex", "crossref", "arxiv"])
    outcome = pipeline.search_step(cfg)

    assert outcome["status"] == "ok"
    warnings = " | ".join(outcome["warnings"])
    assert "openalex, query 'main': kept 30 of 300 matches (search.max_results_per_query)" in warnings
    assert "crossref, query 'main': kept 30 of 300 matches" in warnings and "relevance" in warnings
    assert "arxiv" not in warnings
    log = json.loads((cfg.search_dir / "search_log.json").read_text(encoding="utf-8"))
    assert log["truncated"] is True and log["complete"] is False


def test_source_notes_become_warnings_once():
    from prisma_review.pipeline import status_warnings

    s2_note = "Semantic Scholar bulk search is not ranked by relevance: arbitrary subset of 23."
    scopus_note = "Scopus refused the COMPLETE view."
    warnings = status_warnings([
        {"source": "semantic_scholar", "query": "q", "status": "ok", "api_total": 23,
         "retrieved": 5, "capped_by_max_results": True, "notes": [s2_note]},
        {"source": "scopus", "query": "q", "status": "partial", "error": scopus_note,
         "api_total": None, "retrieved": 5, "notes": [scopus_note]},
        {"source": "arxiv", "query": "q", "status": "ok", "api_total": 3, "retrieved": 3,
         "capped_by_max_results": False, "notes": []},
    ])
    assert len(warnings) == 2
    assert warnings[0].startswith("semantic_scholar, query 'q': kept 5 of 23 matches") and s2_note in warnings[0]
    assert warnings[1].count(scopus_note) == 1


def test_the_flow_notes_that_identified_counts_are_capped(api_client, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    (out / "01_search" / "search_log.json").write_text(json.dumps({"searches": [
        {"source": "openalex", "query": "main", "api_total": 2311, "retrieved": 25,
         "capped_by_max_results": True},
        {"source": "arxiv", "query": "main", "api_total": 3, "retrieved": 3,
         "capped_by_max_results": False}]}), encoding="utf-8")
    flow = api_client.get("/api/stats").json()["flow"]
    assert flow["identified"]["capped_searches"] == 1
    note = next(n for n in flow["notes"] if "max_results_per_query" in n)
    assert "openalex, query 'main', 25 of 2,311" in note


# --------------------------------------------------------------------------- R-16


def _venue_filters(*venues):
    from prisma_review.search.filters import SearchFilters

    return SearchFilters(document_types=[], require_abstract=False, open_access=False,
                         venues=list(venues))


def test_venue_names_match_however_they_are_written():
    from prisma_review.models import Paper
    from prisma_review.search.filters import apply_post_filters

    cea = [Paper(title=f"t{i}", venue="Computers and Electronics in Agriculture", source="openalex")
           for i in range(5)]
    for name in ("Computers & Electronics in Agriculture", "Comput. Electron. Agric.",
                 "computers and electronics in agriculture", "COMPUTERS AND ELECTRONICS IN AGRICULTURE"):
        assert apply_post_filters(cea, _venue_filters(name), "openalex") == cea, name
    # Still a filter: other journals and words out of order do not pass.
    other = Paper(title="x", venue="Sensing and Remote Control", source="openalex")
    rse = Paper(title="y", venue="Remote Sensing of Environment", source="openalex")
    assert apply_post_filters([other, rse], _venue_filters("Remote Sensing"), "openalex") == [rse]
    removed: dict = {}
    apply_post_filters(cea + [other], _venue_filters("Agriculture Computers"), "openalex",
                       removed=removed)
    assert removed == {"venues (name)": 6}


def test_a_post_filter_that_removes_most_records_is_a_warning(tmp_path, monkeypatch):
    from prisma_review import pipeline
    from prisma_review.models import Paper
    from prisma_review.search import runner

    def openalex(query, *args, status=None, **kwargs):
        status.api_total = 4
        return [Paper(title=f"t{i}", venue="Computers and Electronics in Agriculture",
                      source="openalex", source_id=f"W{i}") for i in range(4)]

    monkeypatch.setattr(runner, "search_openalex", openalex)
    cfg = config(tmp_path, sources=["openalex"], filters={"venues": ["Journal of Agronomy"]})
    outcome = pipeline.search_step(cfg)
    warning = next(w for w in outcome["warnings"] if "removed" in w)
    assert "removed 4 of 4 records (venues (name) 4)" in warning
    log = json.loads((cfg.search_dir / "search_log.json").read_text(encoding="utf-8"))
    assert log["searches"][0]["removed_by_filter"]


# --------------------------------------------------------------------------- R-15


def _versions():
    from prisma_review.models import Paper

    title = "Hybrid LLM routing for cost efficient inference"
    preprint = Paper(id="pre", title=title, year=2023, source="openalex", authors=["Doe, Jane"],
                     doi="10.48550/arxiv.2302.02094", venue="arXiv (Cornell University)",
                     type="preprint", abstract="x" * 1886)
    published = Paper(id="vor", title=title, year=2023, source="openalex", authors=["Doe, Jane"],
                      doi="10.1109/access.2023.3274199", venue="IEEE Access", type="article",
                      issn="2169-3536", abstract="x" * 1882)
    return preprint, published


def test_dedup_keeps_the_version_of_record_over_its_preprint():
    from prisma_review.dedup import deduplicate

    preprint, published = _versions()
    unique, log = deduplicate([preprint, published])
    assert [p.id for p in unique] == ["vor"]
    assert unique[0].venue == "IEEE Access"
    assert unique[0].alt_dois == ["10.48550/arxiv.2302.02094"]
    assert log[0]["duplicate_id"] == "pre"


def test_a_kept_preprint_takes_the_doi_and_venue_of_its_published_version():
    from prisma_review.dedup import deduplicate

    preprint, published = _versions()
    # A previous run kept the preprint, so decisions are keyed to its id.
    unique, _ = deduplicate([preprint, published], prefer_ids={"pre"})
    kept = unique[0]
    assert kept.id == "pre" and kept.abstract == "x" * 1886
    assert (kept.doi, kept.venue, kept.type, kept.issn) == (
        "10.1109/access.2023.3274199", "IEEE Access", "article", "2169-3536")
    assert kept.alt_dois == ["10.48550/arxiv.2302.02094"]


def test_the_arxiv_pdf_is_still_found_through_the_alternative_doi(tmp_path, monkeypatch):
    from prisma_review import download
    from prisma_review.dedup import deduplicate

    preprint, published = _versions()
    kept = deduplicate([preprint, published])[0][0]
    seen = []
    monkeypatch.setattr(download, "_download_pdf", lambda url, path: seen.append(url) or False)
    monkeypatch.setattr(download, "_get_semantic_scholar_pdf_url", lambda doi: None)
    monkeypatch.setattr(download.time, "sleep", lambda s: None)
    download.download_papers([kept], tmp_path)
    assert seen == ["https://arxiv.org/pdf/2302.02094.pdf"]


# --------------------------------------------------------------------------- R-26


def test_a_quoted_wildcard_phrase_in_a_boolean_query_is_flagged_for_openalex():
    from prisma_review.search.query_plan import plan_query

    def flagged(query):
        return any("refuses a wildcard inside a quoted phrase" in w
                   for w in plan_query("openalex", "q", query).warnings)

    assert flagged('("remote sens*" OR "earth observation") AND crop')
    assert not flagged('"remote sens*"')                 # the whole search: accepted
    assert not flagged('remote AND sens* AND crop')      # unquoted: accepted
    assert not flagged('"sens*" AND crop')               # one word
    assert not flagged('"remote sensing" AND crop*')     # wildcard outside the phrase


def test_get_review_config_shows_the_quoted_wildcard_warning(mcp_server, workspace):
    from conftest import make_config, write_config

    cfg = make_config()
    cfg["search"]["queries"] = [{"name": "rs", "terms": '("remote sens*" OR "earth observation") AND crop'}]
    write_config(workspace.project_config("alpha"), cfg)
    out = json.loads(mcp_server.get_review_config())
    assert any("quoted phrase" in w for w in out["query_warnings"])
