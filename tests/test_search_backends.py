"""Search backends against a stubbed network: status reporting, retries, parsing.

Covers SEARCH#3, 5, 6, 8, 12, 13 and MCP#18. Nothing here touches the network:
``http._send`` (every backend but arXiv) and the arXiv client are replaced.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from prisma_review.search import http
from prisma_review.search.arxiv_search import _CountingClient, search_arxiv
from prisma_review.search.crossref_search import search_crossref
from prisma_review.search.filters import SearchFilters
from prisma_review.search.http import SearchStatus
from prisma_review.search.openalex_search import KEY_HINT, search_openalex
from prisma_review.search.scopus_search import search_scopus
from prisma_review.search.semantic_search import search_semantic_scholar

D0, D1 = "2023-01-01", "2024-12-31"
FAKE_KEY = "FAKE-OA-KEY-123"
FAKE_EMAIL = "someone@example.org"


# --- Offline HTTP ------------------------------------------------------------

class Resp:
    """The bits of requests.Response the backends use."""

    def __init__(self, status: int = 200, payload=None, headers=None, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


class FakeHTTP:
    """Replays responses in order (the last one repeats); records every call.

    A response may be a Resp, an exception to raise, or a callable
    ``(params) -> Resp``.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {})})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        if callable(r) and not isinstance(r, Resp):
            r = r(dict(params or {}))
        return r


@pytest.fixture
def fake_http(monkeypatch):
    """``fake_http(*responses)`` installs a FakeHTTP; waits are recorded, not slept."""
    sleeps: list[float] = []
    monkeypatch.setattr(http, "_sleep", sleeps.append)

    def install(*responses):
        fake = FakeHTTP(responses)
        fake.sleeps = sleeps
        monkeypatch.setattr(http, "_send", fake)
        return fake
    return install


def no_filters() -> SearchFilters:
    return SearchFilters(document_types=[], require_abstract=False, open_access=False, venues=[])


def oa_work(i: int, **kw) -> dict:
    work = {
        "id": f"https://openalex.org/W{i}", "title": f"OpenAlex paper {i}",
        "doi": f"https://doi.org/10.1000/oa{i}", "publication_year": 2023,
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "abstract_inverted_index": {"Crop": [0], "yield": [1]},
        "type": "article", "open_access": {"is_oa": True},
        "primary_location": {"source": {"display_name": "Remote Sensing of Environment",
                                        "issn_l": "0034-4257", "issn": ["0034-4257", "1879-0704"]}},
        "keywords": [{"display_name": "Agronomy"}],
    }
    work.update(kw)
    return work


def oa_page(start: int, n: int, count: int, next_cursor=None) -> Resp:
    return Resp(200, {"meta": {"count": count, "next_cursor": next_cursor},
                      "results": [oa_work(i) for i in range(start, start + n)]})


# --- OpenAlex (SEARCH#6, #3, #13, MCP#18) --------------------------------------

def test_openalex_without_key_pages_past_the_first_page(fake_http):
    fake = fake_http(oa_page(0, 100, 250), oa_page(100, 100, 250), oa_page(200, 50, 250))
    status = SearchStatus("openalex")
    papers = search_openalex('"crop yield"', D0, D1, max_results=250, status=status)

    assert len(papers) == 250
    assert [c["params"].get("page") for c in fake.calls] == [1, 2, 3]
    assert all("cursor" not in c["params"] for c in fake.calls)
    assert all("Authorization" not in c["headers"] for c in fake.calls)
    assert status.status == "ok" and status.api_total == 250 and status.retrieved == 250


def test_openalex_cursor_401_is_partial_and_names_the_key(fake_http):
    refused = Resp(401, {"error": "API key required for cursor paging",
                         "message": "Paging past the first page with cursor= needs a free API key."})
    fake = fake_http(oa_page(0, 100, 900, next_cursor="abc"), refused)
    status = SearchStatus("openalex")
    papers = search_openalex('"crop yield"', D0, D1, max_results=500, api_key=FAKE_KEY, status=status)

    assert len(papers) == 100
    assert status.status == "partial"
    assert "api_keys.openalex_key" in status.error
    assert "API key required for cursor paging" in status.error
    assert FAKE_KEY not in status.error
    assert fake.calls[0]["params"]["cursor"] == "*" and fake.calls[1]["params"]["cursor"] == "abc"


def test_openalex_refused_first_page_is_failed(fake_http):
    fake_http(Resp(403, {"error": "key_not_activated", "message": "Verify your email first."}))
    status = SearchStatus("openalex")
    assert search_openalex('"x"', D0, D1, api_key=FAKE_KEY, status=status) == []
    assert status.status == "failed"
    assert "key_not_activated" in status.error and KEY_HINT in status.error


def test_openalex_keyless_paging_stops_at_10000_with_a_key_hint(fake_http):
    def page(params):
        start = (params["page"] - 1) * 100
        return oa_page(start, 100, 50_000)
    fake = fake_http(page)
    status = SearchStatus("openalex")
    papers = search_openalex('"x"', D0, D1, max_results=20_000, status=status)

    assert len(papers) == 10_000 and len(fake.calls) == 100
    assert status.status == "partial" and "api_keys.openalex_key" in status.error


def test_openalex_retries_429_and_5xx_then_succeeds(fake_http):
    fake = fake_http(Resp(429, headers={"Retry-After": "3"}), Resp(503), oa_page(0, 5, 5))
    status = SearchStatus("openalex")
    papers = search_openalex('"x"', D0, D1, max_results=50, status=status)

    assert len(papers) == 5 and status.status == "ok"
    assert len(fake.calls) == 3
    assert sum(fake.sleeps) >= 3 + http.BACKOFF_SECONDS * 2  # Retry-After honoured, then backoff


def test_openalex_gives_up_after_bounded_retries(fake_http):
    fake = fake_http(Resp(429, {"error": "Too many requests"}))
    status = SearchStatus("openalex")
    assert search_openalex('"x"', D0, D1, status=status) == []

    assert len(fake.calls) == http.MAX_RETRIES + 1
    assert status.status == "failed" and "429" in status.error


def test_openalex_long_retry_after_is_reported_not_waited(fake_http):
    fake = fake_http(Resp(429, headers={"Retry-After": "86400"}))
    status = SearchStatus("openalex")
    search_openalex('"x"', D0, D1, status=status)
    assert len(fake.calls) == 1 and fake.sleeps == []
    assert status.status == "failed" and "86400" in status.error


def test_openalex_scope_and_wildcards(fake_http):
    fake = fake_http(oa_page(0, 1, 1))
    search_openalex('"crop yield" AND deep', D0, D1, status=SearchStatus("openalex"))
    params = fake.calls[-1]["params"]
    assert params["search.title_abstract_keywords"] == '"crop yield" AND deep'
    assert "search" not in params

    fake = fake_http(oa_page(0, 1, 1))
    status = SearchStatus("openalex")
    search_openalex('"crop yield" AND predict*', D0, D1, status=status)
    params = fake.calls[-1]["params"]
    assert params["search.title_abstract_keywords.exact"] == '"crop yield" AND predict*'
    assert status.executed == '"crop yield" AND predict*'


def test_openalex_400_is_reported_with_the_api_message(fake_http):
    fake_http(Resp(400, {"error": "Invalid query parameters error.",
                         "message": "Wildcards (* or ?) require exact (no-stem) search."}))
    status = SearchStatus("openalex")
    search_openalex('"x"', D0, D1, status=status)
    assert status.status == "failed" and "Wildcards" in status.error


def test_openalex_filters_go_in_the_request(fake_http):
    fake = fake_http(oa_page(0, 1, 1))
    f = SearchFilters(document_types=["journal-article", "review"], require_abstract=True,
                      open_access=True, venues=["00344257", "1879-070x"])
    search_openalex('"x"', D0, D1, filters=f, status=SearchStatus("openalex"))
    flt = fake.calls[0]["params"]["filter"]
    assert "from_publication_date:2023-01-01" in flt and "to_publication_date:2024-12-31" in flt
    assert "type:article|review" in flt and "has_abstract:true" in flt and "is_oa:true" in flt
    assert "primary_location.source.issn:0034-4257|1879-070X" in flt


def test_openalex_credentials_do_not_leak_between_projects(fake_http):
    """MCP#18: nothing process-global: a later search without a key sends none."""
    fake = fake_http(oa_page(0, 1, 1))
    search_openalex('"x"', D0, D1, email=FAKE_EMAIL, api_key=FAKE_KEY, status=SearchStatus("openalex"))
    search_openalex('"x"', D0, D1, status=SearchStatus("openalex"))

    first, second = fake.calls
    assert first["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert FAKE_EMAIL in first["headers"]["User-Agent"]
    assert "Authorization" not in second["headers"]
    assert FAKE_EMAIL not in second["headers"]["User-Agent"]
    # Neither the key nor the email ever goes into the URL parameters.
    assert FAKE_KEY not in str(first["params"]) and FAKE_EMAIL not in str(first["params"])


def test_openalex_parses_records(fake_http):
    fake_http(Resp(200, {"meta": {"count": 2}, "results": [
        oa_work(1, primary_location={"source": {"display_name": "J", "issn_l": "0034425x"}}),
        oa_work(2, title=None),
    ]}))
    [p] = search_openalex('"x"', D0, D1, status=SearchStatus("openalex"))
    assert p.abstract == "Crop yield" and p.doi == "10.1000/oa1" and p.issn == "0034-425X"
    assert p.source == "openalex" and p.is_oa is True and p.keywords == ["Agronomy"]


# --- Crossref (SEARCH#5, #12) ------------------------------------------------

def cr_page(items, next_cursor=None, total=None) -> Resp:
    return Resp(200, {"message": {"items": items, "next-cursor": next_cursor,
                                  "total-results": total if total is not None else len(items)}})


def cr_item(i: int, **kw) -> dict:
    item = {"title": [f"Crossref paper {i}"], "DOI": f"10.2000/cr{i}",
            "issued": {"date-parts": [[2023, 5]]}, "type": "journal-article"}
    item.update(kw)
    return item


def test_crossref_persistent_429_is_bounded(fake_http):
    fake = fake_http(Resp(429))
    status = SearchStatus("crossref")
    assert search_crossref('"crop yield"', D0, D1, status=status) == []
    assert len(fake.calls) == http.MAX_RETRIES + 1
    assert status.status == "failed" and "429" in status.error


def test_crossref_timeout_on_page_two_is_partial(fake_http):
    timeout = requests.exceptions.ReadTimeout("read timed out")
    fake = fake_http(cr_page([cr_item(0), cr_item(1)], next_cursor="c2", total=4), timeout)
    status = SearchStatus("crossref")
    papers = search_crossref('"crop yield"', D0, D1, max_results=4, status=status)

    assert len(papers) == 2
    assert status.status == "partial" and "ReadTimeout" in status.error
    assert status.api_total == 4
    assert len(fake.calls) == 1 + http.MAX_RETRIES + 1


def test_crossref_5xx_on_first_page_is_failed_not_empty(fake_http):
    fake_http(Resp(503))
    status = SearchStatus("crossref")
    assert search_crossref('"x"', D0, D1, status=status) == []
    assert status.status == "failed"


def test_crossref_cancel_interrupts_the_backoff(fake_http):
    fake = fake_http(Resp(429))
    status = SearchStatus("crossref")
    calls = iter([False, False, True])
    search_crossref('"x"', D0, D1, status=status, should_cancel=lambda: next(calls, True))
    assert status.status == "cancelled"
    assert len(fake.calls) == 1


def test_crossref_email_is_scrubbed_from_errors(fake_http):
    err = requests.exceptions.ConnectionError(f"Max retries exceeded with url: /works?mailto={FAKE_EMAIL}")
    fake = fake_http(err)
    status = SearchStatus("crossref")
    search_crossref('"x"', D0, D1, email=FAKE_EMAIL, status=status)
    assert fake.calls[0]["params"]["mailto"] == FAKE_EMAIL
    assert FAKE_EMAIL not in status.error and "***" in status.error
    assert FAKE_EMAIL not in str(status.request)


def test_crossref_parsing(fake_http):
    items = [
        {"title": ["Yield of <i>Zea mays</i> under H<sub>2</sub>O &amp; heat"], "DOI": "10.1/a",
         "published": {"date-parts": [[None]]}, "issued": {"date-parts": [[2023, 5]]},
         "abstract": "<jats:title>Abstract</jats:title><jats:p>First para &amp; more.</jats:p>"
                     "<jats:p>Second para.</jats:p>",
         "author": [{"given": "A", "family": "B"}, {"name": "The FOO Consortium"}],
         "subject": ["Agronomy and Crop Science"], "ISSN": ["00344257"],
         "container-title": ["Field &amp; Crops"], "type": "journal-article"},
        {"title": ["Posted content without published"], "DOI": "10.1/b",
         "issued": {"date-parts": [[2024, 2, 1]]}, "type": "posted-content"},
    ]
    fake = fake_http(cr_page(items))
    a, b = search_crossref('"crop yield"', D0, D1, status=SearchStatus("crossref"))

    assert a.title == "Yield of Zea mays under H 2 O & heat"
    assert a.abstract == "First para & more. Second para."
    assert a.year == 2023 and b.year == 2024
    assert a.authors == ["A B", "The FOO Consortium"]
    assert a.keywords == [] and a.issn == "0034-4257" and a.venue == "Field & Crops"
    params = fake.calls[0]["params"]
    assert "select" in params and "User-Agent" in fake.calls[0]["headers"]


# --- Semantic Scholar (SEARCH#4, #8) -------------------------------------------

def s2_item(i: int, **kw) -> dict:
    item = {"paperId": f"p{i}", "title": f"S2 paper {i}", "abstract": "An abstract.",
            "authors": [{"name": "Grace Hopper"}], "year": 2023, "venue": "Some Venue",
            "externalIds": {"DOI": f"10.3000/s2{i}", "CorpusId": i},
            "publicationTypes": ["JournalArticle"], "openAccessPdf": {"url": "", "status": "CLOSED"}}
    item.update(kw)
    return item


def test_semantic_scholar_uses_boolean_bulk_search(fake_http):
    fake = fake_http(Resp(200, {"total": "3", "token": "t2", "data": [s2_item(0), s2_item(1)]}),
                     Resp(200, {"total": "3", "data": [s2_item(2)]}))
    status = SearchStatus("semantic_scholar")
    papers = search_semantic_scholar('("crop yield" OR "yield prediction") AND "deep learning" NOT maize',
                                     D0, D1, max_results=10, status=status)

    first, second = fake.calls
    assert first["url"].endswith("/paper/search/bulk")
    assert first["params"]["query"] == '("crop yield" | "yield prediction") + "deep learning" -maize'
    assert first["params"]["publicationDateOrYear"] == "2023-01-01:2024-12-31"
    assert "token" not in first["params"] and second["params"]["token"] == "t2"
    assert len(papers) == 3 and status.api_total == 3 and status.status == "ok"


def test_semantic_scholar_parsing(fake_http):
    fake_http(Resp(200, {"total": 3, "data": [
        s2_item(0, publicationTypes=["JournalArticle", "Review"]),
        s2_item(1, openAccessPdf={"url": "https://x.org/a.pdf", "status": "GOLD"}),
        s2_item(2, openAccessPdf={"url": "", "status": None}, publicationTypes=None),
    ]}))
    a, b, c = search_semantic_scholar('"x"', D0, D1, status=SearchStatus("semantic_scholar"))
    assert a.type == "JournalArticle,Review" and a.is_oa is False
    assert b.is_oa is True
    assert c.is_oa is None and c.type is None
    assert a.issn is None and a.doi == "10.3000/s20"


def test_semantic_scholar_document_type_mapping(fake_http):
    fake = fake_http(Resp(200, {"total": 0, "data": []}))
    f = SearchFilters(document_types=["review", "book-chapter"], require_abstract=False,
                      open_access=False, venues=[])
    search_semantic_scholar('"x"', D0, D1, filters=f, status=SearchStatus("semantic_scholar"))
    assert fake.calls[0]["params"]["publicationTypes"] == "Review,BookSection"


# --- Scopus ------------------------------------------------------------------

def scopus_page(entries, total) -> Resp:
    return Resp(200, {"search-results": {"opensearch:totalResults": str(total), "entry": entries}})


def test_scopus_empty_result_set_is_ok_not_an_error(fake_http):
    fake_http(scopus_page([{"@_fa": "true", "error": "Result set was empty"}], 0))
    status = SearchStatus("scopus")
    assert search_scopus('"x"', "FAKE-SCOPUS", D0, D1, status=status) == []
    assert status.status == "ok" and status.error is None and status.api_total == 0


def test_scopus_standard_fallback_is_reported(fake_http):
    entry = {"dc:title": "A Scopus paper", "prism:coverDate": "2023-04-01", "prism:issn": "00344257",
             "eid": "2-s2.0-1", "dc:identifier": "SCOPUS_ID:1"}
    fake = fake_http(Resp(401, {"service-error": {"status": {"statusText": "Not on campus"}}}),
                     scopus_page([entry], 1))
    status = SearchStatus("scopus")
    [p] = search_scopus('"x"', "FAKE-SCOPUS", D0, D1, status=status)

    assert fake.calls[1]["params"]["view"] == "STANDARD"
    # Reported (WP-B turns non-ok statuses into pipeline warnings), not only logged.
    assert status.status == "partial" and "no abstracts" in status.error
    assert "STANDARD" in status.notes[0]
    assert "require_abstract" in status.skip_post_filters
    assert p.issn == "0034-4257"


def test_semantic_scholar_capped_search_notes_the_unranked_subset(fake_http):
    fake_http(Resp(200, {"total": 40, "token": "t2", "data": [s2_item(i) for i in range(5)]}))
    status = SearchStatus("semantic_scholar")
    assert len(search_semantic_scholar('"x"', D0, D1, max_results=5, status=status)) == 5
    assert status.status == "ok" and "arbitrary subset of 40" in status.notes[0]


def test_scopus_without_key_is_skipped(fake_http):
    fake = fake_http(Resp(500))
    status = SearchStatus("scopus")
    assert search_scopus('"x"', "", D0, D1, status=status) == []
    assert status.status == "skipped" and fake.calls == []


def test_scopus_bad_key_is_failed_and_redacted(fake_http):
    fake_http(Resp(401, {"service-error": {"status": {"statusText": "Invalid API Key FAKE-SCOPUS"}}}))
    status = SearchStatus("scopus")
    search_scopus('"x"', "FAKE-SCOPUS", D0, D1, status=status)
    assert status.status == "failed" and "FAKE-SCOPUS" not in status.error


# --- arXiv -------------------------------------------------------------------

def _arxiv_result(i: int, year: int = 2023):
    return SimpleNamespace(
        title=f"arXiv paper {i}", authors=[SimpleNamespace(name="Alan Turing")],
        summary="Summary.", doi=None, entry_id=f"http://arxiv.org/abs/2301.0000{i}v1",
        categories=["cs.LG"], published=SimpleNamespace(year=year))


def test_arxiv_error_mid_iteration_keeps_records_and_is_partial(monkeypatch):
    import arxiv

    def results(self, search):
        yield _arxiv_result(1)
        yield _arxiv_result(2)
        raise arxiv.HTTPError("https://export.arxiv.org/api/query", 3, 503)

    monkeypatch.setattr(_CountingClient, "results", results)
    status = SearchStatus("arxiv")
    papers = search_arxiv('"crop yield"', D0, D1, max_results=10, status=status)
    assert len(papers) == 2
    assert status.status == "partial" and "503" in status.error


def test_arxiv_sends_the_date_range_in_the_query(monkeypatch):
    seen = {}

    def results(self, search):
        seen["query"] = search.query
        yield _arxiv_result(1)

    monkeypatch.setattr(_CountingClient, "results", results)
    status = SearchStatus("arxiv")
    search_arxiv('"crop yield" OR ("crop yield" AND "remote sensing")', D0, D1, status=status)
    assert seen["query"] == status.executed
    assert seen["query"] == ('(all:"crop yield" OR (all:"crop yield" AND all:"remote sensing")) '
                             'AND submittedDate:[202301010000 TO 202412312359]')
