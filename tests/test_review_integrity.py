"""Data-integrity findings of the v1.6 review.

R-1 (eligibility decisions kept), R-2 (dedup ids stable), R-7 (decisions during a run),
R-8 (CLI and sync endpoints claim the run), R-9 (export temp files), R-12 (failed search).
"""

from __future__ import annotations

import json

import pytest

from conftest import make_config, write_config, write_dataset
from prisma_review.models import load_papers


def j(text: str) -> dict:
    return json.loads(text)


def _elig(out) -> dict:
    return {p.id: p for p in load_papers(out / "03b_eligibility" / "eligibility_results.json")}


# --------------------------------------------------------------------------- R-1


def test_rescreen_round_trip_keeps_eligibility_decisions(api_client, mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    j(mcp_server.batch_eligibility_screen([
        {"paper_id": "p1", "decision": "include", "reason": "fits"},
        {"paper_id": "p2", "decision": "exclude", "reason": "no data"}]))
    stats = api_client.get("/api/stats").json()["flow"]
    assert (stats["included"], stats["eligibility_excluded"]) == (1, 1)

    body = api_client.post("/api/papers/rescreen?min_include_hits=4").json()
    assert body["included"] == 0 and body["eligibility_set_aside"] == 2
    assert set(_elig(out)) == {"p1", "p2"}  # set aside, not deleted
    flow = api_client.get("/api/stats").json()["flow"]
    assert (flow["included"], flow["eligibility_excluded"]) == (0, 0)
    assert load_papers(out / "03b_eligibility" / "eligible_included.json") == []

    body = api_client.post("/api/papers/rescreen?min_include_hits=2").json()
    assert body["eligibility_set_aside"] == 0
    flow = api_client.get("/api/stats").json()["flow"]
    assert (flow["sought_for_retrieval"], flow["included"], flow["eligibility_excluded"],
            flow["awaiting_eligibility"]) == (2, 1, 1, 0)
    assert [p.id for p in load_papers(out / "03b_eligibility" / "eligible_included.json")] == ["p1"]


def test_screen_flip_and_undo_keeps_the_eligibility_decision(api_client, mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    j(mcp_server.eligibility_screen_paper("p1", "include", "fits"))
    assert api_client.post("/api/papers/p1/screen", json={"decision": "exclude", "reason": "oops"}).json()["status"] == "ok"
    assert _elig(out)["p1"].eligibility_decision == "include"
    elig = j(mcp_server.get_papers_for_eligibility(batch_size=5))
    assert elig["already_screened"] == 0 and elig["total_first_pass_included"] == 1

    api_client.post("/api/papers/p1/screen", json={"decision": "include", "reason": "undo"})
    assert (_elig(out)["p1"].eligibility_decision, _elig(out)["p1"].eligibility_method) == ("include", "ai")
    assert api_client.get("/api/stats").json()["flow"]["included"] == 1
    assert api_client.get("/api/papers/eligibility").json()["already_screened"] == 1


def test_new_eligibility_decision_keeps_set_aside_ones(mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    j(mcp_server.eligibility_screen_paper("p1", "include", "fits"))
    j(mcp_server.screen_paper("p1", "exclude", "on reading"))
    j(mcp_server.eligibility_screen_paper("p2", "exclude", "no data"))
    assert set(_elig(out)) == {"p1", "p2"}
    assert [p.id for p in load_papers(out / "03b_eligibility" / "eligible_excluded.json")] == ["p2"]


# --------------------------------------------------------------------------- R-2


def _dedup_fixture(out, *, previous_kept, screen, eligibility):
    """all_records with a DOI pair (a: no abstract, b: abstract) and a title pair (x, y)."""
    from prisma_review.diagram import save_state
    from prisma_review.models import Paper, save_papers

    def paper(pid, title, abstract="", doi=None, **kw):
        kw.setdefault("authors", ["Ada Lovelace"])
        return Paper(id=pid, title=title, abstract=abstract, year=2024, source="openalex",
                     doi=doi, **kw)

    records = [
        paper("a", "Hybrid LLM: cost efficient query routing", doi="10.1/hybrid"),
        paper("b", "Hybrid LLM: cost-efficient query routing", "Routing queries to cheap LLMs. " * 5,
              doi="10.1/HYBRID"),
        paper("x", "Online cascade learning for efficient inference over streams",
              "Cascades of models. " * 5),
        paper("y", "Online cascade learning for efficient inference over data streams",
              "Cascades of models for streams. " * 5, authors=["Grace Hopper"]),
    ]
    save_papers(records, out / "01_search" / "all_records.json")
    save_papers([r for r in records if r.id in previous_kept], out / "02_dedup" / "deduplicated.json")
    screened = [r for r in records if r.id in previous_kept]
    for r in screened:
        r.screen_decision, r.screen_method, r.screen_reason = screen.get(r.id, ("maybe", "rule", "rules"))
    save_papers(screened, out / "03_screen" / "screen_results.json")
    elig = []
    for pid, decision in eligibility.items():
        r = next(r for r in screened if r.id == pid)
        e = Paper.from_dict(r.to_dict())
        e.eligibility_decision, e.eligibility_method = decision, "ai"
        elig.append(e)
    save_papers(elig, out / "03b_eligibility" / "eligibility_results.json")
    save_state({"search": {"openalex": 4, "total": 4}}, out / "review_state.json")


def test_rerunning_dedup_keeps_the_ids_decisions_are_keyed_to(workspace):
    from prisma_review import pipeline
    from prisma_review.config import Config
    from prisma_review.screen import rescreen

    cfg = make_config("Alpha review")
    cfg["dedup"]["fuzzy_title_threshold"] = 99
    config = Config.load(write_config(workspace.project_config("alpha"), cfg))
    out = workspace.output_dir("alpha")
    # v1.5 kept "a" (no abstract) for the DOI pair; the new rule prefers "b".
    _dedup_fixture(out, previous_kept={"a", "x", "y"},
                   screen={"a": ("include", "ai", "fits")}, eligibility={"a": "include"})

    result = pipeline.dedup_step(config)
    kept = {p.id: p for p in load_papers(out / "02_dedup" / "deduplicated.json")}
    assert "a" in kept and "b" not in kept and result["ids_moved"] == 0
    assert kept["a"].abstract.startswith("Routing queries")  # gap filled from "b"
    res = rescreen(config, check_running=False, persist_threshold=False)
    assert res["kept_ai"] == 1 and res["eligibility_set_aside"] == 0
    assert [p.id for p in load_papers(out / "03b_eligibility" / "eligible_included.json")] == ["a"]


def test_decisions_follow_a_record_that_dedup_merges_into_another(workspace):
    from prisma_review import pipeline
    from prisma_review.config import Config
    from prisma_review.screen import rescreen

    cfg = make_config("Alpha review")
    cfg["dedup"]["fuzzy_title_threshold"] = 85  # x and y now merge
    config = Config.load(write_config(workspace.project_config("alpha"), cfg))
    out = workspace.output_dir("alpha")
    _dedup_fixture(out, previous_kept={"b", "x", "y"},
                   screen={"y": ("include", "manual", "read it")}, eligibility={"y": "include"})

    result = pipeline.dedup_step(config)
    kept_ids = {p.id for p in load_papers(out / "02_dedup" / "deduplicated.json")}
    assert result["ids_moved"] == 1 and len(kept_ids & {"x", "y"}) == 1
    survivor = (kept_ids & {"x", "y"}).pop()
    res = rescreen(config, check_running=False, persist_threshold=False)
    screen = {p.id: p for p in load_papers(out / "03_screen" / "screen_results.json")}
    assert (screen[survivor].screen_decision, screen[survivor].screen_method) == ("include", "manual")
    assert res["kept_manual"] == 1 and res["eligibility_set_aside"] == 0
    assert [p.id for p in load_papers(out / "03b_eligibility" / "eligible_included.json")] == [survivor]
    # A second dedup run changes nothing.
    assert pipeline.dedup_step(config)["ids_moved"] == 0
    assert {p.id for p in load_papers(out / "02_dedup" / "deduplicated.json")} == kept_ids


def test_pipeline_screen_step_reports_set_aside_decisions(workspace):
    from api.session import SessionManager
    from prisma_review.config import Config

    out = workspace.output_dir("alpha")
    write_dataset(out)
    from prisma_review.screen import apply_eligibility_decisions
    config = Config.load(workspace.project_config("alpha"))
    apply_eligibility_decisions(config, [{"paper_id": "p1", "decision": "include"}], "ai")
    cfg = make_config("Alpha review")
    cfg["screening"]["rules"]["min_include_hits"] = 4
    config = Config.load(write_config(workspace.project_config("alpha"), cfg))
    session = SessionManager(state_file=config.state_file)
    result = session._run_screen(config)
    assert result["eligibility_set_aside"] == 1 and "kept_ai" in result
    assert any("set aside" in w for w in session.warnings)


# --------------------------------------------------------------------------- R-12


def _offline(monkeypatch):
    import requests

    from prisma_review.search import arxiv_search, http

    def down(*a, **k):
        raise requests.exceptions.ConnectionError("network is down")

    monkeypatch.setattr(http, "_send", down)
    monkeypatch.setattr(http, "_sleep", lambda s: None)
    monkeypatch.setattr(arxiv_search._CountingClient, "results", lambda self, search: down())


def _snapshot(out):
    return {d: sorted(p.name for p in (out / d).iterdir()) if (out / d).is_dir() else None
            for d in ("01_search", "02_dedup", "03_screen", "03b_eligibility")}


def test_a_search_where_every_request_fails_keeps_the_previous_results(workspace, monkeypatch):
    from prisma_review import pipeline
    from prisma_review.config import Config
    from prisma_review.screen import apply_eligibility_decisions

    cfg = make_config("Alpha review")
    cfg["search"]["sources"] = ["openalex", "crossref", "arxiv", "semantic_scholar", "scopus"]
    cfg["api_keys"]["scopus"] = ""  # scopus is skipped
    config = Config.load(write_config(workspace.project_config("alpha"), cfg))
    out = config.output_dir
    write_dataset(out)
    apply_eligibility_decisions(config, [{"paper_id": "p1", "decision": "include"}], "ai")
    (out / "01_search" / "search_log.json").write_text('{"previous": true}', encoding="utf-8")
    records = (out / "01_search" / "all_records.json").read_bytes()
    state = (out / "review_state.json").read_text(encoding="utf-8")
    before = _snapshot(out)
    _offline(monkeypatch)

    outcome = pipeline.search_step(config, replace_downstream=True)
    assert outcome["status"] == "failed" and outcome["total"] == 0
    assert "previous search results" in outcome["error"] and outcome["warnings"]
    assert (out / "01_search" / "all_records.json").read_bytes() == records
    assert (out / "review_state.json").read_text(encoding="utf-8") == state
    assert json.loads((out / "01_search" / "search_log.json").read_text()) == {"previous": True}
    assert (out / "01_search" / "search_log.failed.json").is_file()
    after = _snapshot(out)
    after["01_search"].remove("search_log.failed.json")
    assert after == before


def test_failed_search_fails_the_pipeline_run_with_a_clear_error(workspace, monkeypatch):
    import time

    from api.session import SessionManager
    from prisma_review.config import Config

    config = Config.load(workspace.project_config("alpha"))
    write_dataset(config.output_dir)
    _offline(monkeypatch)
    session = SessionManager(state_file=config.state_file)
    session.start_full_pipeline(config)
    deadline = time.time() + 30
    while session.is_running and time.time() < deadline:
        time.sleep(0.05)
    progress = session.get_progress()
    assert progress["status"] == "failed"
    assert "search" in progress["progress_message"] and "kept" in progress["progress_message"]
    assert progress["completed_steps"] == []
    assert len(load_papers(config.screen_dir / "screen_results.json")) == 6


def test_a_search_that_matches_nothing_is_not_a_failure(workspace, monkeypatch):
    from prisma_review import pipeline
    from prisma_review.config import Config
    from prisma_review.search import runner

    config = Config.load(workspace.project_config("alpha"))
    write_dataset(config.output_dir)

    def nothing(source, terms, start, end, config, filters, status, should_cancel):
        status.api_total = 0
        return []

    monkeypatch.setattr(runner, "_run_backend", nothing)
    outcome = pipeline.search_step(config, replace_downstream=True)
    assert outcome["status"] == "ok" and outcome["total"] == 0
    assert load_papers(config.search_dir / "all_records.json") == []


def test_cli_search_reports_the_failure_and_run_all_stops(workspace, monkeypatch, capsys):
    from prisma_review import cli
    from prisma_review.config import Config

    config = Config.load(workspace.project_config("alpha"))
    write_dataset(config.output_dir)
    _offline(monkeypatch)
    cli.cmd_run_all(config)
    out = capsys.readouterr().out
    assert "[SEARCH] Failed." in out and "Pipeline stopped" in out and "[DEDUP]" not in out
    assert len(load_papers(config.search_dir / "all_records.json")) == 7
