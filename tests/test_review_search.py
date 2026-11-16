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
