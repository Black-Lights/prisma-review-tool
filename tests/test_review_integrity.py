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
