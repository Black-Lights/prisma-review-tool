"""Screening writers: rescreen, the gate counter, gate matching, and concurrent decisions.

Covers PIPE#2 (lost updates across processes), PIPE#7, PIPE#8, PIPE#11, MCP#3 and the
server side of WEB#4 (screen breakdown computed from screen_results.json).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, make_config, write_config, write_dataset
from prisma_review.diagram import load_state, save_state
from prisma_review.models import Paper, load_papers, save_papers
from prisma_review.screen import NO_REQUIRED_KEYWORD_REASON, screen_by_rules


def j(text: str) -> dict:
    return json.loads(text)


def _screen(out: Path) -> dict[str, Paper]:
    return {p.id: p for p in load_papers(out / "03_screen" / "screen_results.json")}


def _set_decision(out: Path, pid: str, decision: str, method: str, reason: str) -> None:
    path = out / "03_screen" / "screen_results.json"
    papers = load_papers(path)
    for p in papers:
        if p.id == pid:
            p.screen_decision, p.screen_method, p.screen_reason = decision, method, reason
    save_papers(papers, path)


def _gate_config(workspace, **rules) -> None:
    cfg = make_config()
    cfg["screening"]["rules"].update(rules)
    write_config(workspace.project_config("alpha"), cfg)


def _live_run(state_file: Path) -> None:
    state = load_state(state_file)
    state["pipeline"] = {"status": "running", "session_id": "other", "owner_pid": os.getpid(),
                         "owner_host": socket.gethostname(),
                         "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                         "started_at": datetime.now(timezone.utc).isoformat()}
    save_state(state, state_file)


# --------------------------------------------------------------------------- PIPE#7 / MCP#3 rescreen


def test_rest_rescreen_keeps_manual_and_ai_decisions(api_client, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    _gate_config(workspace, required_keywords=["yield"])
    resp = api_client.post("/api/papers/p4/screen", json={"decision": "include", "reason": "manual check"})
    assert resp.status_code == 200 and "error" not in resp.json()
    _set_decision(out, "p6", "exclude", "ai", "off topic")  # recorded by the MCP server

    body = api_client.post("/api/papers/rescreen?min_include_hits=2").json()
    assert body["status"] == "ok"
    papers = _screen(out)
    assert (papers["p4"].screen_decision, papers["p4"].screen_method) == ("include", "manual")
    assert (papers["p6"].screen_decision, papers["p6"].screen_method) == ("exclude", "ai")
    assert papers["p5"].screen_reason == NO_REQUIRED_KEYWORD_REASON
    assert body["kept_manual"] == 1 and body["kept_ai"] == 1


def test_mcp_rescreen_reconciles_eligibility_and_persists_threshold(mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    assert j(mcp_server.screen_paper("p6", "include", "relevant on reading"))["status"] == "ok"
    j(mcp_server.batch_eligibility_screen([
        {"paper_id": "p1", "decision": "include", "reason": "fits"},
        {"paper_id": "p6", "decision": "exclude", "reason": "no data"}]))

    res = j(mcp_server.rescreen(4))
    assert res["status"] == "ok" and res["project"] == "alpha"
    papers = _screen(out)
    assert (papers["p1"].screen_decision, papers["p1"].screen_method) == ("maybe", "rule")
    assert (papers["p6"].screen_decision, papers["p6"].screen_method) == ("include", "ai")

    elig_dir = out / "03b_eligibility"
    assert [p.id for p in load_papers(elig_dir / "eligibility_results.json")] == ["p6"]
    assert load_papers(elig_dir / "eligible_included.json") == []
    assert [p.id for p in load_papers(elig_dir / "eligible_excluded.json")] == ["p6"]
    state = load_state(out / "review_state.json")
    assert state["eligibility"] == {"input_from_screening": 1, "screened": 1, "included": 0,
                                    "excluded": 1, "remaining": 0}
    assert state["screen"]["min_include_hits"] == 4
    saved = yaml.safe_load(workspace.project_config("alpha").read_text(encoding="utf-8"))
    assert saved["screening"]["rules"]["min_include_hits"] == 4


def test_rescreen_keeps_config_comments(mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    path = write_config(workspace.project_config("alpha"), make_config(), header="# my notes\n")
    assert j(mcp_server.rescreen(3))["status"] == "ok"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# my notes\n")
    assert yaml.safe_load(text)["screening"]["rules"]["min_include_hits"] == 3


def test_rescreen_refused_while_a_run_is_active(api_client, mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    _live_run(out / "review_state.json")
    before = (out / "03_screen" / "screen_results.json").read_bytes()
    assert api_client.post("/api/papers/rescreen?min_include_hits=3").status_code == 409
    assert "running" in j(mcp_server.rescreen(3))["error"]
    assert (out / "03_screen" / "screen_results.json").read_bytes() == before


# --------------------------------------------------------------------------- PIPE#8 / WEB#4 gate counter


def test_gate_counter_survives_manual_and_ai_decisions(api_client, mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    _gate_config(workspace, required_keywords=["yield"])
    assert api_client.post("/api/papers/rescreen?min_include_hits=2").json()[
        "excluded_no_required_keyword"] == 3

    api_client.post("/api/papers/p1/screen", json={"decision": "exclude", "reason": "manual"})
    assert load_state(out / "review_state.json")["screen"]["excluded_no_required_keyword"] == 3
    assert j(mcp_server.screen_paper("p4", "include", "fits"))["status"] == "ok"

    expected = {"rule_include": 1, "rule_exclude_keyword": 1, "rule_exclude_required": 2,
                "rule_maybe": 0, "ai_include": 1, "ai_exclude": 0, "ai_maybe": 0,
                "manual_include": 0, "manual_exclude": 1, "manual_maybe": 0, "unscreened": 0}
    screen = api_client.get("/api/stats").json()["screen"]
    assert screen["excluded_no_required_keyword"] == 2
    assert screen["breakdown"] == expected
    assert screen["min_include_hits"] == 2

    # A writer that drops the counter (an older version) cannot change what /api/stats reports.
    state = load_state(out / "review_state.json")
    state["screen"] = {"total_screened": 6, "included": 2, "excluded": 3, "maybe": 1}
    save_state(state, out / "review_state.json")
    screen = api_client.get("/api/stats").json()["screen"]
    assert screen["breakdown"] == expected and screen["excluded_no_required_keyword"] == 2


def test_every_writer_keeps_the_screen_block_complete(api_client, mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    writers = [
        lambda: api_client.post("/api/papers/p4/screen", json={"decision": "include", "reason": "r"}),
        lambda: api_client.post("/api/papers/screen/batch",
                                json=[{"paper_id": "p5", "decision": "exclude", "reason": "r"}]),
        lambda: mcp_server.screen_paper("p6", "exclude", "r"),
        lambda: mcp_server.batch_screen_papers([{"paper_id": "p6", "decision": "include", "reason": "r"}]),
        lambda: api_client.post("/api/pipeline/screen"),
    ]
    for write in writers:
        write()
        screen = load_state(out / "review_state.json")["screen"]
        assert {"breakdown", "excluded_no_required_keyword", "included", "excluded",
                "maybe"} <= set(screen), screen


# --------------------------------------------------------------------------- PIPE#11 gate matching


def _gate(text: str, required: list[str], title: str = "A study") -> Paper:
    paper = Paper(title=title, abstract=text)
    return screen_by_rules([paper], ["study"], [], 1, required)[0]


@pytest.mark.parametrize("text", [
    "We study large language models.",
    "We study large-language models.",
    "We study large  language\nmodels.",
    "We study large\tlanguage models.",
    "We study large\u00a0language models.",
    "We study <i>large language</i> models.",
    "We study Large Language Model agents.",
])
def test_gate_matches_phrase_variants(text):
    assert _gate(text, ["large language model"]).screen_decision == "include"


@pytest.mark.parametrize("text, required, passes", [
    ("Efficient storage on average hardware.", ["RAG"], False),
    ("A RAG pipeline for question answering.", ["RAG"], True),
    ("Two RAGs compared.", ["rag"], True),
    ("Routing among LLMs.", ["LLM"], True),
    ("Air quality and aims.", ["AI"], False),
    ("An AI planner.", ["AI"], True),
])
def test_gate_matches_whole_words(text, required, passes):
    paper = _gate(text, required)
    assert (paper.screen_reason != NO_REQUIRED_KEYWORD_REASON) is passes, paper.screen_reason


def test_gate_miss_without_abstract_needs_review():
    paper = screen_by_rules([Paper(title="A survey", abstract="")], ["survey"], [], 1, ["llm"])[0]
    assert paper.screen_decision == "maybe"
    assert "abstract" in paper.screen_reason


def test_include_and_exclude_matching_is_unchanged():
    # Back-compat: include/exclude keywords still match substrings, so
    # re-running an old review gives the same decisions.
    included = screen_by_rules([Paper(title="Cropland mapping", abstract="")], ["crop", "map"], [], 2)[0]
    assert included.screen_decision == "include"
    excluded = screen_by_rules([Paper(title="Biomedical crops", abstract="")], ["crop"], ["medical"], 1)[0]
    assert excluded.screen_decision == "exclude"


# --------------------------------------------------------------------------- PIPE#2 lost updates


_MCP_WORKER = r"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import mcp_server.server as server
ids = json.loads(sys.argv[2])
go = Path(sys.argv[3])
Path(sys.argv[4]).write_text("ready")
while not go.exists():
    time.sleep(0.01)
for pid in ids:
    out = json.loads(server.screen_paper(pid, "exclude", "mcp"))
    assert "error" not in out, out
"""


def _many_maybe(out: Path, n: int) -> list[str]:
    papers = [Paper(id=f"m{i:03d}", title=f"Paper {i}", abstract="Some text " * 40, source="openalex",
                    screen_decision="maybe", screen_method="rule", screen_reason="rules")
              for i in range(n)]
    save_papers(papers, out / "02_dedup" / "deduplicated.json")
    save_papers(papers, out / "03_screen" / "screen_results.json")
    save_papers(papers, out / "03_screen" / "maybe.json")
    save_state({"search": {"openalex": n, "total": n}, "dedup": {"duplicates_removed": 0, "remaining": n},
                "screen": {"total_screened": n, "included": 0, "excluded": 0, "maybe": n}},
               out / "review_state.json")
    return [p.id for p in papers]


def test_web_and_mcp_decisions_in_parallel_lose_nothing(api_client, workspace, tmp_path):
    out = workspace.output_dir("alpha")
    ids = _many_maybe(out, 60)
    web_ids, mcp_ids = ids[0::2], ids[1::2]
    go, ready = tmp_path / "go", tmp_path / "ready"
    env = {**os.environ, "PRISMA_WORKSPACE": str(workspace.root)}
    proc = subprocess.Popen([sys.executable, "-c", _MCP_WORKER, str(REPO_ROOT), json.dumps(mcp_ids),
                             str(go), str(ready)], env=env, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 60
        while not ready.exists():
            assert proc.poll() is None, proc.stderr.read().decode(errors="replace")
            assert time.monotonic() < deadline
            time.sleep(0.02)
        go.write_text("go")
        for pid in web_ids:
            resp = api_client.post(f"/api/papers/{pid}/screen", json={"decision": "include", "reason": "web"})
            assert "error" not in resp.json()
        assert proc.wait(timeout=120) == 0, proc.stderr.read().decode(errors="replace")
    finally:
        if proc.poll() is None:
            proc.kill()

    papers = _screen(out)
    assert sorted(pid for pid, p in papers.items() if p.screen_decision == "include") == sorted(web_ids)
    assert sorted(pid for pid, p in papers.items() if p.screen_decision == "exclude") == sorted(mcp_ids)
    screen = load_state(out / "review_state.json")["screen"]
    assert (screen["included"], screen["excluded"], screen["maybe"]) == (30, 30, 0)
