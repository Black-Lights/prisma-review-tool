"""The web app respects runs owned by another process (integration of PIPE#1 and PIPE#13).

The MCP server records its runs in review_state.json. The web app must not
switch away from the active project, or delete a project, while such a run
is live: the run would keep writing into a project the UI no longer shows,
or into a folder that was just removed.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from prisma_review.diagram import load_state, save_state


@pytest.fixture
def other_process_runs_alpha(workspace):
    """A live pipeline run on "alpha", owned by another (sleeping) process."""
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    state_file = workspace.output_dir("alpha") / "review_state.json"
    state = load_state(state_file)
    now = datetime.now(timezone.utc).isoformat()
    state["pipeline"] = {
        "status": "running", "current_step": "search", "progress_message": "Searching databases...",
        "started_at": now, "completed_steps": [], "warnings": [], "error": None,
        "session_id": "mcp-run", "owner_pid": sleeper.pid, "owner_host": socket.gethostname(),
        "heartbeat_at": now, "cancel_requested": False,
    }
    save_state(state, state_file)
    yield workspace
    sleeper.kill()
    sleeper.wait()


def test_web_switch_refused_while_another_process_runs_the_project(other_process_runs_alpha,
                                                                   api_client):
    workspace = other_process_runs_alpha
    workspace.add_project("beta", active=False)

    r = api_client.post("/api/projects/beta/switch")
    assert r.status_code == 409, r.text
    assert "running" in r.json()["detail"]
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"


def test_web_delete_refused_while_another_process_runs_the_project(other_process_runs_alpha,
                                                                   api_client):
    workspace = other_process_runs_alpha
    workspace.add_project("beta")  # alpha is no longer the active project

    r = api_client.delete("/api/projects/alpha")
    assert r.status_code == 409, r.text
    assert workspace.project_config("alpha").is_file()


def test_web_switch_and_delete_allowed_once_the_owner_is_gone(other_process_runs_alpha, api_client):
    workspace = other_process_runs_alpha
    workspace.add_project("beta", active=False)
    state_file = workspace.output_dir("alpha") / "review_state.json"
    state = load_state(state_file)
    state["pipeline"]["heartbeat_at"] = "2020-01-01T00:00:00+00:00"  # the owner stopped beating
    save_state(state, state_file)

    assert api_client.post("/api/projects/beta/switch").status_code == 200
    assert api_client.delete("/api/projects/alpha").status_code == 200
    assert not workspace.project_config("alpha").exists()
