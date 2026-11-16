"""Pipeline runs: progress after a crash, ownership on disk, cross-process start/stop, search counts.

Covers PIPE#1, 5, 6, 9, 13 and MCP#4 (disk), 5, 6, 7, plus the search runner contract
(status_log, should_cancel). No test here touches the network: the search runner is faked.
"""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from conftest import make_config, write_config, write_dataset
from prisma_review.config import Config
from prisma_review.diagram import load_state, save_state
from prisma_review.models import Paper


def j(text: str) -> dict:
    return json.loads(text)


def _now(offset: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _write_run(state_file: Path, **block) -> None:
    """Put a pipeline block into review_state.json, as another process would."""
    state = load_state(state_file)
    state["pipeline"] = {
        "status": "running", "current_step": "search", "progress_message": "Searching databases...",
        "started_at": _now(-5), "completed_steps": [], "warnings": [], "error": None,
        **block,
    }
    save_state(state, state_file)


def _live_run(state_file: Path, session_id: str = "other-run") -> None:
    """A run owned by a live process (this one) with a fresh heartbeat, but not by the manager under test."""
    _write_run(state_file, session_id=session_id, owner_pid=os.getpid(),
               owner_host=socket.gethostname(), heartbeat_at=_now(), cancel_requested=False)


def _manager(state_file: Path):
    from api.session import SessionManager
    return SessionManager(threading.Lock(), state_file=state_file)


def _wait(manager, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while manager.status == "running":
        assert time.monotonic() < deadline, "pipeline did not finish"
        time.sleep(0.02)
    time.sleep(0.05)


def _patch_search(monkeypatch, fake) -> None:
    """Replace the search runner wherever a module imported it (old and new layouts)."""
    for name in ("prisma_review.search.runner", "prisma_review.pipeline", "api.session",
                 "prisma_review.cli", "api.routes.pipeline"):
        try:
            module = importlib.import_module(name)
        except ImportError:
            continue
        monkeypatch.setattr(module, "run_all_searches", fake, raising=False)


def _no_search(config, **_kwargs):
    return {}


@pytest.fixture
def alpha(workspace) -> Config:
    write_dataset(workspace.output_dir("alpha"))
    return Config.load(workspace.project_config("alpha"))


# --------------------------------------------------------------------------- PIPE#1 stuck "running"


@pytest.mark.parametrize("owner", ["dead", "legacy"])
def test_running_block_of_a_dead_process_is_reported_failed_and_fixed_on_disk(alpha, owner):
    if owner == "dead":
        _write_run(alpha.state_file, session_id="crashed", owner_pid=_dead_pid(),
                   owner_host=socket.gethostname(), heartbeat_at=_now())
    else:  # written by an older version: no owner recorded
        _write_run(alpha.state_file)

    manager = _manager(alpha.state_file)
    progress = manager.get_progress(alpha.state_file)
    assert progress["status"] == "failed"
    assert "interrupted" in progress["progress_message"].lower()
    assert load_state(alpha.state_file)["pipeline"]["status"] == "failed"
    assert manager.request_cancel() is False
    # A second process sees the same, and can start a new run.
    assert _manager(alpha.state_file).get_progress(alpha.state_file)["status"] == "failed"


def test_stale_heartbeat_is_not_running(alpha):
    _write_run(alpha.state_file, session_id="hung", owner_pid=os.getpid(),
               owner_host=socket.gethostname(), heartbeat_at=_now(-3600))
    assert _manager(alpha.state_file).get_progress(alpha.state_file)["status"] == "failed"


def test_api_progress_recovers_after_a_crash(api_client, alpha):
    _write_run(alpha.state_file, session_id="crashed", owner_pid=_dead_pid(),
               owner_host=socket.gethostname(), heartbeat_at=_now())
    assert api_client.get("/api/pipeline/progress").json()["status"] == "failed"
    resp = api_client.post("/api/pipeline/start/dedup")
    assert resp.status_code == 200, resp.text
    deadline = time.monotonic() + 15
    while api_client.get("/api/pipeline/progress").json()["status"] == "running":
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert api_client.get("/api/pipeline/progress").json()["status"] == "completed"


# --------------------------------------------------------------------------- PIPE#5 / MCP#6 completed runs


def test_completed_run_keeps_session_id_result_and_finished_at(alpha):
    manager = _manager(alpha.state_file)
    session_id = manager.start_step("dedup", alpha)
    _wait(manager)
    for progress in (manager.get_progress(alpha.state_file),
                     _manager(alpha.state_file).get_progress(alpha.state_file)):
        assert progress["status"] == "completed"
        assert progress["session_id"] == session_id
        assert progress["finished_at"]
        assert progress["result"]["dedup"]["remaining"] == 6


def test_running_block_records_owner_and_heartbeat(alpha, monkeypatch):
    import prisma_review.pipeline as pipeline

    monkeypatch.setattr(pipeline, "HEARTBEAT_SECONDS", 0.05)
    release = threading.Event()
    manager = _manager(alpha.state_file)

    def slow_step(step, config):
        release.wait(10)
        return {"status": "ok"}

    manager._execute_step = slow_step
    session_id = manager.start_step("dedup", alpha)
    try:
        first = load_state(alpha.state_file)["pipeline"]
        assert first["status"] == "running" and first["session_id"] == session_id
        assert first["owner_pid"] == os.getpid() and first["owner_host"] == socket.gethostname()
        deadline = time.monotonic() + 5
        while load_state(alpha.state_file)["pipeline"]["heartbeat_at"] == first["heartbeat_at"]:
            assert time.monotonic() < deadline, "no heartbeat"
            time.sleep(0.02)
    finally:
        release.set()
        _wait(manager)
    assert load_state(alpha.state_file)["pipeline"]["status"] == "completed"


def test_owner_restores_a_run_another_process_wrongly_marked_interrupted(alpha, monkeypatch):
    import prisma_review.pipeline as pipeline

    monkeypatch.setattr(pipeline, "HEARTBEAT_SECONDS", 0.05)
    release = threading.Event()
    manager = _manager(alpha.state_file)
    manager._execute_step = lambda step, config: (release.wait(10), {"status": "ok"})[1]
    manager.start_step("dedup", alpha)
    try:
        state = load_state(alpha.state_file)
        state["pipeline"] = pipeline.interrupted(state["pipeline"])  # e.g. after a long sleep
        save_state(state, alpha.state_file)
        deadline = time.monotonic() + 5
        while load_state(alpha.state_file)["pipeline"]["status"] != "running":
            assert time.monotonic() < deadline, "the owner did not restore its run"
            time.sleep(0.02)
    finally:
        release.set()
        _wait(manager)
    assert load_state(alpha.state_file)["pipeline"]["status"] == "completed"


# --------------------------------------------------------------------------- PIPE#6 / MCP#7 project switches


def test_progress_does_not_leak_into_another_project(workspace, alpha):
    manager = _manager(alpha.state_file)
    manager.start_step("dedup", alpha)
    _wait(manager)
    workspace.add_project("beta", active=False)
    beta = Config.load(workspace.project_config("beta"))
    progress = manager.get_progress(beta.state_file)
    assert progress["status"] == "idle" and progress["session_id"] is None


def test_mcp_progress_follows_the_active_project(mcp_server, workspace, alpha):
    assert j(mcp_server.start_pipeline_step("dedup"))["status"] == "started"
    _wait(mcp_server._session_manager)
    assert j(mcp_server.get_pipeline_progress())["status"] == "completed"

    workspace.add_project("beta", active=False)
    beta = Config.load(workspace.project_config("beta"))
    _write_run(beta.state_file, status="completed", session_id="beta-run",
               started_at=_now(-60), finished_at=_now(-30))
    workspace.set_marker("beta")  # the web app switched projects
    out = j(mcp_server.get_pipeline_progress())
    assert out["session_id"] == "beta-run"


# --------------------------------------------------------------------------- PIPE#13 / MCP#5 another process


def test_api_start_refused_while_another_process_runs_the_project(api_client, alpha, monkeypatch):
    _patch_search(monkeypatch, _no_search)
    _live_run(alpha.state_file)
    before = (alpha.dedup_dir / "deduplicated.json").read_bytes()
    assert api_client.get("/api/pipeline/progress").json()["status"] == "running"
    assert api_client.post("/api/pipeline/start").status_code == 409
    assert api_client.post("/api/pipeline/start/dedup").status_code == 409
    assert api_client.post("/api/pipeline/screen").status_code == 409
    assert (alpha.dedup_dir / "deduplicated.json").read_bytes() == before
    # Stop reaches the other process's run through the state file.
    resp = api_client.post("/api/pipeline/stop")
    assert resp.status_code == 200, resp.text
    assert load_state(alpha.state_file)["pipeline"]["cancel_requested"] is True


def test_mcp_start_and_switch_refused_while_the_web_app_runs_the_project(
        mcp_server, workspace, alpha, monkeypatch):
    _patch_search(monkeypatch, _no_search)
    workspace.add_project("beta", active=False)
    _live_run(alpha.state_file, session_id="web-run")

    for call in (mcp_server.start_pipeline, lambda: mcp_server.start_pipeline_step("dedup")):
        out = j(call())
        assert "error" in out and out["status"] == "running", out
    assert "pipeline is running" in j(mcp_server.switch_project("beta"))["error"]
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"
    assert j(mcp_server.get_pipeline_progress())["session_id"] == "web-run"

    out = j(mcp_server.stop_pipeline())
    assert out["status"] == "cancel_requested" and out["project"] == "alpha"
    assert load_state(alpha.state_file)["pipeline"]["cancel_requested"] is True


def test_cancel_through_the_state_file_stops_the_owner(alpha):
    release = threading.Event()
    owner = _manager(alpha.state_file)

    def step(name, config):
        if name == "search":
            release.wait(10)
        return {"status": "ok", "step": name}

    owner._execute_step = step
    owner.start_full_pipeline(alpha)
    other = _manager(alpha.state_file)  # e.g. the MCP server
    assert other.request_cancel(alpha.state_file) is True
    release.set()
    _wait(owner)
    assert owner.status == "cancelled"
    assert owner.completed_steps == ["search"]
    assert load_state(alpha.state_file)["pipeline"]["status"] == "cancelled"


# --------------------------------------------------------------------------- PIPE#9 search counts, runner contract


def _search_config(workspace) -> Config:
    cfg = make_config()
    cfg["search"]["sources"] = ["openalex", "semantic_scholar"]
    write_config(workspace.project_config("alpha"), cfg)
    return Config.load(workspace.project_config("alpha"))


def _papers(source: str, n: int) -> list[Paper]:
    return [Paper(title=f"{source} paper {i}", source=source, matched_queries=["main"]) for i in range(n)]


def test_background_search_counts_by_paper_source(workspace, monkeypatch):
    config = _search_config(workspace)
    _patch_search(monkeypatch, lambda config, **_k: {
        "semantic_scholar_main": _papers("semantic_scholar", 2), "openalex_main": _papers("openalex", 1)})
    manager = _manager(config.state_file)
    manager.start_step("search", config)
    _wait(manager)
    assert manager.status == "completed", manager.error
    assert load_state(config.state_file)["search"] == {"semantic_scholar": 2, "openalex": 1, "total": 3}
    assert not any("returned 0 results" in w for w in manager.warnings)


def test_cli_search_counts_by_paper_source(workspace, monkeypatch):
    from prisma_review import cli

    config = _search_config(workspace)
    _patch_search(monkeypatch, lambda config, **_k: {
        "semantic_scholar_main": _papers("semantic_scholar", 2), "openalex_main": _papers("openalex", 1)})
    cli.cmd_search(config)
    assert load_state(config.state_file)["search"] == {"semantic_scholar": 2, "openalex": 1, "total": 3}


def test_search_status_log_becomes_pipeline_warnings(workspace, monkeypatch):
    config = _search_config(workspace)
    seen = {}

    def fake(config, *, status_log=None, should_cancel=None):
        seen["should_cancel"] = should_cancel
        status_log.extend([
            {"source": "openalex", "query": "main", "query_index": 0, "status": "partial",
             "error": "API key required for cursor paging", "api_total": 120, "retrieved": 50,
             "after_post_filter": 50, "executed": "https://api.openalex.org/works?..."},
            {"source": "semantic_scholar", "query": "main", "query_index": 0, "status": "failed",
             "error": "HTTP 429", "api_total": None, "retrieved": 0, "after_post_filter": 0,
             "executed": None},
        ])
        return {"openalex#0": _papers("openalex", 50)}

    _patch_search(monkeypatch, fake)
    manager = _manager(config.state_file)
    manager.start_step("search", config)
    _wait(manager)
    assert manager.status == "completed", manager.error
    assert callable(seen["should_cancel"]) and seen["should_cancel"]() is False
    text = " | ".join(manager.warnings)
    assert "openalex" in text and "partial" in text and "API key required" in text
    assert "semantic_scholar" in text and "failed" in text and "HTTP 429" in text


def test_search_cancelled_mid_run_keeps_previous_results(alpha, monkeypatch):
    before = (alpha.screen_dir / "screen_results.json").read_bytes()
    manager = _manager(alpha.state_file)

    def fake(config, *, status_log=None, should_cancel=None):
        manager.request_cancel()
        assert should_cancel() is True
        status_log.append({"source": "openalex", "query": "main", "query_index": 0,
                           "status": "cancelled", "error": None, "api_total": None,
                           "retrieved": 0, "after_post_filter": 0, "executed": None})
        return {}

    _patch_search(monkeypatch, fake)
    manager.start_full_pipeline(alpha)
    _wait(manager)
    assert manager.status == "cancelled"
    assert (alpha.screen_dir / "screen_results.json").read_bytes() == before
    assert load_state(alpha.state_file)["search"]["total"] == 7
