"""Query translation per source and its transparency (SEARCH#3, 4, 11, 13, 14)."""

from __future__ import annotations

import pytest

from conftest import make_config
from prisma_review.config import Config
from prisma_review.search.filters import SearchFilters
from prisma_review.search.http import SearchStatus
from prisma_review.search.query_plan import (
    arxiv_query, date_range, normalize_date, openalex_search_param, plan_query, query_warnings,
    semantic_bulk_query, text_search_query,
)
from test_search_backends import Resp, fake_http  # noqa: F401  (fixture)

D0, D1 = "2023-01-01", "2024-12-31"
REAL = '("crop yield" OR "yield prediction" OR "harvest forecast") AND ("deep learning" OR CNN) AND (satellite OR "remote sensing")'


# --- SEARCH#4: Crossref plain-text reduction ---------------------------------------

def test_unquoted_and_terms_are_kept():
    assert text_search_query('"deep learning" AND agriculture') == "deep learning agriculture"


def test_not_operands_never_become_search_terms():
    assert text_search_query('"crop yield" NOT "maize"') == "crop yield"
    assert text_search_query('"crop yield" AND NOT ("maize" OR wheat)') == "crop yield"
    plan = plan_query("crossref", "q", '"crop yield" NOT "maize"')
    assert "maize" not in plan.effective_query
    assert any('NOT terms are left out ("maize")' in w for w in plan.warnings)


def test_every_and_group_contributes_terms():
    effective = text_search_query(REAL)
    for term in ("crop yield", "deep learning", "satellite"):
        assert term in effective


def test_crossref_always_reports_what_it_searched():
    plan = plan_query("crossref", "q", '"deep learning" AND agriculture')
    assert plan.effective_query == "deep learning agriculture"
    assert any('"deep learning agriculture"' in w for w in plan.warnings)


def test_crossref_term_cap_is_reported():
    many = " OR ".join(f'"term {i}"' for i in range(14))
    plan = plan_query("crossref", "q", many)
    assert len(plan.effective_query.split(" term")) == 10
    assert any("dropped" in w and "term 13" in w for w in plan.warnings)


# --- Semantic Scholar bulk syntax ----------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ('"crop yield" AND "deep learning"', '"crop yield" + "deep learning"'),
    ('("a b" OR c) AND NOT (x OR y)', '("a b" | c) + -(x | y)'),
    ('"crop yield" NOT maize', '"crop yield" -maize'),
    ('predict* AND wom?n', 'predict* + wom*'),
])
def test_semantic_scholar_bulk_translation(query, expected):
    assert semantic_bulk_query(query) == expected


def test_semantic_scholar_question_mark_is_reported():
    assert plan_query("semantic_scholar", "q", "wom?n").warnings
    assert plan_query("semantic_scholar", "q", '"crop yield"').warnings == []


# --- SEARCH#3 and #13: OpenAlex -------------------------------------------------------

def test_openalex_searches_title_abstract_keywords():
    assert openalex_search_param('"crop yield" AND deep') == (
        "search.title_abstract_keywords", '"crop yield" AND deep')
    plan = plan_query("openalex", "q", '"crop yield"')
    assert "title, abstract and keywords" in plan.field_scope and plan.warnings == []


def test_openalex_wildcards_use_the_exact_search():
    param, _ = openalex_search_param('"crop yield" AND predict*')
    assert param == "search.title_abstract_keywords.exact"
    plan = plan_query("openalex", "q", '"crop yield" AND predict*')
    assert any("exact" in w for w in plan.warnings)
    assert all("ignored" not in w for w in plan.warnings)


def test_openalex_overlong_query_is_reported():
    long_query = " OR ".join(f'"synonym number {i}"' for i in range(200))
    assert any("Split it" in w for w in plan_query("openalex", "q", long_query).warnings)


# --- SEARCH#11: arXiv ----------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ('"crop yield" OR ("crop yield" AND "remote sensing")',
     'all:"crop yield" OR (all:"crop yield" AND all:"remote sensing")'),
    ('ti:"crop yield" AND "remote sensing"', 'ti:"crop yield" AND all:"remote sensing"'),
])
def test_arxiv_phrases_are_prefixed_once(query, expected):
    assert arxiv_query(query) == expected


# --- Scopus date granularity -------------------------------------------------------

def test_scopus_year_only_dates_are_reported():
    f = SearchFilters(document_types=[], require_abstract=False, open_access=False, venues=[])
    plan = plan_query("scopus", "q", '"x"', date_start="2023-03-15", date_end="2024-06-30", filters=f)
    assert plan.effective_query.startswith('TITLE-ABS-KEY("x") AND PUBYEAR > 2022 AND PUBYEAR < 2025')
    assert any("year only" in w for w in plan.warnings)
    assert plan_query("scopus", "q", '"x"', date_start=D0, date_end=D1, filters=f).warnings == []


# --- SEARCH#14: the plan is what is sent -------------------------------------------------

def test_plan_matches_what_every_backend_sends(fake_http, monkeypatch):
    from prisma_review.search import arxiv_search
    from prisma_review.search.crossref_search import search_crossref
    from prisma_review.search.openalex_search import search_openalex
    from prisma_review.search.scopus_search import search_scopus
    from prisma_review.search.semantic_search import search_semantic_scholar

    f = SearchFilters(document_types=["journal-article"], require_abstract=False,
                      open_access=False, venues=[])
    query = REAL + " NOT maize"
    empty = {
        "openalex": Resp(200, {"meta": {"count": 0}, "results": []}),
        "crossref": Resp(200, {"message": {"items": [], "total-results": 0}}),
        "semantic_scholar": Resp(200, {"total": 0, "data": []}),
        "scopus": Resp(200, {"search-results": {"opensearch:totalResults": "0", "entry": []}}),
    }
    runs = {
        "openalex": lambda s: search_openalex(query, D0, D1, filters=f, status=s),
        "crossref": lambda s: search_crossref(query, D0, D1, filters=f, status=s),
        "semantic_scholar": lambda s: search_semantic_scholar(query, D0, D1, filters=f, status=s),
        "scopus": lambda s: search_scopus(query, "FAKE-SCOPUS", D0, D1, filters=f, status=s),
    }
    for source, run in runs.items():
        fake = fake_http(empty[source])
        status = SearchStatus(source)
        run(status)
        plan = plan_query(source, "q", query, date_start=D0, date_end=D1, filters=f)
        assert status.executed == plan.effective_query, source
        assert plan.effective_query in fake.calls[0]["params"].values(), source

    monkeypatch.setattr(arxiv_search._CountingClient, "results", lambda self, search: iter(()))
    status = SearchStatus("arxiv")
    arxiv_search.search_arxiv(query, D0, D1, filters=f, status=status)
    assert status.executed == plan_query("arxiv", "q", query, date_start=D0, date_end=D1).effective_query


# --- Dates ---------------------------------------------------------------------------

def test_dates_are_normalized():
    assert normalize_date("2020") == "2020-01-01"
    assert normalize_date("2020", end=True) == "2020-12-31"
    assert normalize_date("2024-02", end=True) == "2024-02-29"
    assert normalize_date("2023-5-7") == "2023-05-07"
    assert date_range("2020", "2021") == ("2020-01-01", "2021-12-31")
    for bad in ("", "yesterday", "2023-13-01", "2023-02-30"):
        with pytest.raises(ValueError):
            normalize_date(bad)
    with pytest.raises(ValueError):
        date_range("2024-01-01", "2023-01-01")


def test_readiness_flags_an_invalid_date_range():
    cfg = make_config()
    cfg["search"]["date_range"] = {"start": "2024-01-01", "end": "last year"}
    ready = Config(cfg).readiness()
    assert ready["ready"] is False
    assert any("date_range" in p for p in ready["search_problems"])
    assert Config(make_config()).readiness()["ready"] is True


def test_query_warnings_use_the_configured_dates_and_filters():
    cfg = make_config()
    cfg["search"]["sources"] = ["scopus", "crossref"]
    cfg["search"]["date_range"] = {"start": "2023-03-01", "end": "2024-12-31"}
    cfg["search"]["queries"] = [{"name": "q", "terms": '"crop yield" NOT maize'}]
    warns = query_warnings(Config(cfg))
    assert any("year only" in w for w in warns)
    assert any("NOT terms are left out" in w for w in warns)
