"""run_all_searches: per-pair status, unique keys, post-filter counts, search_log.json.

Covers SEARCH#5 (a failed or partial query is visible), SEARCH#7 (keys per
source and query index; counts before and after the local post-filter),
SEARCH#14 and #16 (01_search/search_log.json) and the search-runner contract.
"""

from __future__ import annotations

import json

import pytest

from conftest import FAKE_OPENALEX_KEY, FAKE_SCOPUS_KEY, make_config
from prisma_review import __version__
from prisma_review.config import Config
from prisma_review.models import Paper
from prisma_review.search import runner
from prisma_review.search.http import SearchCancelled
from test_search_backends import Resp, fake_http  # noqa: F401  (fixture)

CONTRACT_KEYS = {"source", "query", "query_index", "status", "error", "api_total", "retrieved",
                 "after_post_filter", "executed", "capped_by_max_results", "notes",
                 "removed_by_filter"}


def config(tmp_path, *, sources=("openalex",), queries=None, filters=None, email="") -> Config:
    cfg = make_config()
    cfg["project"]["output_dir"] = str(tmp_path / "out")
    cfg["api_keys"]["openalex_email"] = email
    cfg["search"]["sources"] = list(sources)
    cfg["search"]["queries"] = queries or [{"name": "main", "terms": '"crop yield"'}]
    if filters:
        cfg["search"]["filters"] = filters
    return Config(cfg, base_dir=tmp_path)


class FakeBackend:
    """Stands in for one search_<source> function; records the calls."""

    def __init__(self, source, n=2, *, status="ok", error=None, abstract="An abstract.", raise_exc=None):
        self.source, self.n, self.status, self.error = source, n, status, error
        self.abstract, self.raise_exc = abstract, raise_exc
        self.calls = []

    def __call__(self, query, *args, status=None, should_cancel=None, **kwargs):
        self.calls.append(query)
        if self.raise_exc:
            raise self.raise_exc
        papers = [Paper(title=f"{self.source} {query} {i}", source=self.source,
                        source_id=f"{self.source}-{len(self.calls)}-{i}",
                        abstract=self.abstract if i else "")
                  for i in range(self.n)]
        if status is not None:
            status.status, status.error = self.status, self.error
            status.api_total, status.executed = self.n * 10, f"sent:{query}"
            status.request = {"url": "https://api.example.org", "params": {"q": query}}
        return papers


@pytest.fixture
def backends(monkeypatch):
    fakes = {s: FakeBackend(s) for s in ("arxiv", "crossref", "openalex", "semantic_scholar", "scopus")}
    names = {"arxiv": "search_arxiv", "crossref": "search_crossref", "openalex": "search_openalex",
             "semantic_scholar": "search_semantic_scholar", "scopus": "search_scopus"}
    for source, fn in names.items():
        monkeypatch.setattr(runner, fn, fakes[source])
    return fakes


def test_same_named_and_unnamed_queries_do_not_overwrite(tmp_path, backends):
    cfg = config(tmp_path, sources=["openalex", "semantic_scholar"], queries=[
        {"name": "main", "terms": '"a"'}, {"name": "main", "terms": '"b"'},
        {"terms": '"c"'}, {"terms": '"d"'}])
    results = runner.run_all_searches(cfg)

    assert len(results) == 8
    assert sum(len(v) for v in results.values()) == 16
    assert set(results) == {f"{s}:{i}:{n}" for s in ("openalex", "semantic_scholar")
                            for i, n in enumerate(["main", "main", "unnamed", "unnamed"])}


def test_status_log_follows_the_contract(tmp_path, backends):
    backends["openalex"].status, backends["openalex"].error = "partial", "HTTP 401 on page 2"
    cfg = config(tmp_path, sources=["openalex", "crossref"],
                 queries=[{"name": "q1", "terms": '"a"'}, {"name": "", "terms": "  "},
                          {"name": "q3", "terms": '"c"'}])
    log: list[dict] = []
    runner.run_all_searches(cfg, status_log=log)

    assert len(log) == 4 and all(set(e) == CONTRACT_KEYS for e in log)
    assert [(e["source"], e["query"], e["query_index"]) for e in log] == [
        ("openalex", "q1", 0), ("crossref", "q1", 0), ("openalex", "q3", 2), ("crossref", "q3", 2)]
    oa = [e for e in log if e["source"] == "openalex"]
    assert all(e["status"] == "partial" and e["error"] == "HTTP 401 on page 2" for e in oa)
    assert all(e["status"] == "ok" for e in log if e["source"] == "crossref")
    assert log[0]["api_total"] == 20 and log[0]["executed"] == 'sent:"a"'


def test_one_failed_query_among_several_is_visible(tmp_path, backends, monkeypatch):
    calls = {"n": 0}
    real = backends["openalex"]

    def flaky(query, *args, status=None, **kw):
        calls["n"] += 1
        papers = real(query, *args, status=status, **kw)
        if calls["n"] == 2:
            status.status, status.error = "failed", "HTTP 503 (gave up after 5 attempts)"
            return []
        return papers

    monkeypatch.setattr(runner, "search_openalex", flaky)
    cfg = config(tmp_path, queries=[{"name": f"q{i}", "terms": f'"t{i}"'} for i in range(6)])
    log: list[dict] = []
    results = runner.run_all_searches(cfg, status_log=log)

    assert [e["status"] for e in log] == ["ok", "failed", "ok", "ok", "ok", "ok"]
    assert sum(len(v) for v in results.values()) == 10  # nonzero, yet one query failed


def test_counts_before_and_after_the_post_filter(tmp_path, backends):
    backends["semantic_scholar"].n = 3  # paper 0 has no abstract
    cfg = config(tmp_path, sources=["semantic_scholar"], filters={"require_abstract": True})
    log: list[dict] = []
    results = runner.run_all_searches(cfg, status_log=log)

    assert log[0]["retrieved"] == 3 and log[0]["after_post_filter"] == 2
    assert sum(len(v) for v in results.values()) == 2
    entry = json.loads((cfg.search_dir / "search_log.json").read_text(encoding="utf-8"))["searches"][0]
    assert entry["removed_by_post_filter"] == 1
    assert entry["filter_modes"] == {"require_abstract": "post"}


def test_provenance_is_stamped(tmp_path, backends):
    results = runner.run_all_searches(config(tmp_path, sources=["openalex", "crossref"]))
    for key, papers in results.items():
        source = key.split(":")[0]
        for p in papers:
            assert p.matched_queries == ["main"]
            assert p.found_in_sources == [source]
            assert p.source_ids == {source: p.source_id}


def test_search_log_records_the_executed_search(tmp_path, backends):
    cfg = config(tmp_path, sources=["openalex", "scopus"],
                 queries=[{"name": "main", "terms": '"crop yield" AND predict*'}])
    runner.run_all_searches(cfg)
    log = json.loads((cfg.search_dir / "search_log.json").read_text(encoding="utf-8"))

    assert log["tool_version"] == __version__ and log["complete"] is True
    assert log["date_range"] == {"start": "2020-01-01", "end": "2026-12-31"}
    assert log["queries"][0]["name"] == "main" and len(log["queries"][0]["terms_sha256"]) == 64
    oa, sc = log["searches"]
    assert set(oa) >= CONTRACT_KEYS | {"terms", "field_scope", "syntax", "date_filter", "request",
                                       "filter_modes", "warnings", "started_at", "finished_at"}
    assert "title, abstract and keywords" in oa["field_scope"]
    assert any("exact" in w for w in oa["warnings"])
    assert sc["field_scope"].startswith("TITLE-ABS-KEY")
    assert log["totals"] == {"records": 4, "by_source": {"openalex": 2, "scopus": 2}}


def test_search_log_holds_no_secrets(tmp_path, fake_http):
    fake_http(Resp(200, {"meta": {"count": 1}, "results": [
        {"id": "https://openalex.org/W1", "title": "A paper", "publication_year": 2023}]}))
    cfg = config(tmp_path, email="someone@example.org")
    log: list[dict] = []
    runner.run_all_searches(cfg, status_log=log)
    text = (cfg.search_dir / "search_log.json").read_text(encoding="utf-8")

    assert log[0]["status"] == "ok" and log[0]["retrieved"] == 1
    for secret in (FAKE_OPENALEX_KEY, FAKE_SCOPUS_KEY, "someone@example.org"):
        assert secret not in text and secret not in json.dumps(log)
    assert json.loads(text)["searches"][0]["request"]["api_key"] is True


def test_cancel_stops_the_remaining_pairs(tmp_path, backends, monkeypatch):
    cfg = config(tmp_path, sources=["openalex", "crossref"],
                 queries=[{"name": "q1", "terms": '"a"'}, {"name": "q2", "terms": '"b"'}])
    flag = {"stop": False}

    def stop_after_first(query, *args, status=None, should_cancel=None, **kw):
        flag["stop"] = True
        return FakeBackend("openalex")(query, status=status)

    monkeypatch.setattr(runner, "search_openalex", stop_after_first)
    log: list[dict] = []
    results = runner.run_all_searches(cfg, status_log=log, should_cancel=lambda: flag["stop"])

    assert [e["status"] for e in log] == ["ok", "cancelled", "cancelled", "cancelled"]
    assert backends["crossref"].calls == []
    assert list(results) == ["openalex:0:q1"]
    assert not (cfg.search_dir / "search_log.json").exists()


def test_backend_cancellation_is_reported(tmp_path, backends):
    backends["openalex"].raise_exc = SearchCancelled()
    log: list[dict] = []
    runner.run_all_searches(config(tmp_path, sources=["openalex", "crossref"]), status_log=log)
    assert [e["status"] for e in log] == ["cancelled", "cancelled"]


def test_backend_crash_fails_only_that_pair(tmp_path, backends):
    backends["openalex"].raise_exc = KeyError("title")
    log: list[dict] = []
    results = runner.run_all_searches(config(tmp_path, sources=["openalex", "crossref"]), status_log=log)
    assert [e["status"] for e in log] == ["failed", "ok"]
    assert "KeyError" in log[0]["error"]
    assert results["openalex:0:main"] == [] and len(results["crossref:0:main"]) == 2


def test_unknown_source_is_skipped(tmp_path, backends):
    log: list[dict] = []
    results = runner.run_all_searches(config(tmp_path, sources=["openalex", "pubmed"]), status_log=log)
    assert log[1]["status"] == "skipped" and "pubmed" in log[1]["error"]
    assert log[1]["executed"] is None and list(results) == ["openalex:0:main"]


def test_invalid_date_range_raises(tmp_path, backends):
    cfg = make_config()
    cfg["search"]["date_range"] = {"start": "2024-01-01", "end": "soon"}
    with pytest.raises(ValueError, match="date_range"):
        runner.run_all_searches(Config(cfg, base_dir=tmp_path))


def test_dates_are_normalized_before_the_backends(tmp_path, monkeypatch):
    seen = {}

    def capture(query, start, end, *args, **kwargs):
        seen["range"] = (start, end)
        return []

    monkeypatch.setattr(runner, "search_openalex", capture)
    cfg = make_config()
    cfg["project"]["output_dir"] = str(tmp_path / "out")
    cfg["search"]["date_range"] = {"start": 2020, "end": 2021}
    runner.run_all_searches(Config(cfg, base_dir=tmp_path))
    assert seen["range"] == ("2020-01-01", "2021-12-31")
