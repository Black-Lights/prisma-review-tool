"""Agent UX, back-compat and docs findings of the v1.6 review.

R-11 (reserved project names), R-19 (upgrade from 1.5: root config vs active
project), R-23 (unscreened filter), R-24 (in-app MCP setup), R-27 (argument type
errors), R-28 (list_projects when pinned), OP-6 (search log endpoint).
"""

from __future__ import annotations

import json

import pytest

from conftest import write_dataset


def j(text: str) -> dict:
    return json.loads(text)


# --------------------------------------------------------------------------- R-23


def test_unscreened_filter_returns_only_papers_without_a_decision(mcp_server, workspace, api_client):
    write_dataset(workspace.output_dir("alpha"))
    j(mcp_server.screen_paper("p4", "include", "fits"))

    body = j(mcp_server.get_papers_to_screen(batch_size=10, filter_type="unscreened"))
    assert body["total_matching"] == 2
    assert {p["id"] for p in body["papers"]} == {"p5", "p6"}
    assert all(p["current_decision"] == "maybe" for p in body["papers"])

    rest = api_client.get("/api/papers/screen", params={"filter_type": "unscreened"}).json()
    assert {p["id"] for p in rest["papers"]} == {"p5", "p6"}


def test_unscreened_before_keyword_screening_is_every_deduplicated_paper(mcp_server, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    for name in ("screen_results.json", "included.json", "excluded.json", "maybe.json"):
        (out / "03_screen" / name).unlink()
    body = j(mcp_server.get_papers_to_screen(batch_size=10, filter_type="unscreened"))
    assert body["total_matching"] == 6


def test_unknown_filter_type_is_an_error(mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    body = j(mcp_server.get_papers_to_screen(batch_size=1, filter_type="bogus"))
    assert "error" in body
    assert all(option in body["error"] for option in ("maybe", "unscreened", "all"))


# --------------------------------------------------------------------------- R-19


def _upgraded_install(ws, *, root_newer: bool = True):
    """A 1.5.1 install: the real review in the root config, a stale web copy as the active project."""
    import os
    import time

    from conftest import make_config, write_dataset

    ws.add_project("root-review", make_config("Root review"), active=True, dataset=True)
    ws.write_root_config(make_config("Root review"), dataset=True)
    old, new = time.time() - 3600, time.time()
    project_state = ws.output_dir("root-review") / "review_state.json"
    root_state = ws.root / "prisma_output" / "review_state.json"
    os.utime(project_state, (old, old) if root_newer else (new, new))
    os.utime(root_state, (new, new) if root_newer else (old, old))
    return ws.root / "config.yaml"


def test_mcp_says_the_root_config_is_ignored_after_an_upgrade(mcp_server, bare_workspace):
    root_cfg = _upgraded_install(bare_workspace)
    out = j(mcp_server.get_review_config())
    assert out["resolved_from"] == "marker"
    notice = [w for w in out["warnings"] if "root config.yaml" in w]
    assert len(notice) == 1
    assert str(root_cfg) in notice[0] and "PRISMA_CONFIG" in notice[0]
    assert "newer" in notice[0]
    listing = j(mcp_server.list_projects())
    assert any("root config.yaml" in w for w in listing["warnings"])

    from mcp_server.server import log_startup
    import contextlib, io
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        log_startup()
    assert "root config.yaml" in err.getvalue()


def test_web_readiness_shows_the_root_config_notice(bare_workspace):
    from fastapi.testclient import TestClient

    import api.deps as deps
    from api.main import app

    _upgraded_install(bare_workspace, root_newer=False)
    deps.reset_project_caches()
    with TestClient(app, base_url="http://localhost") as client:
        warnings = client.get("/api/config/readiness").json()["warnings"]
    deps.reset_project_caches()
    notice = [w for w in warnings if "root config.yaml" in w]
    assert len(notice) == 1 and "newer" not in notice[0]


def test_an_untouched_template_root_config_is_not_reported(mcp_server, bare_workspace):
    import shutil

    from prisma_review import workspace as ws

    bare_workspace.add_project("alpha")
    shutil.copy(ws.template_path(), bare_workspace.root / "config.yaml")
    out = j(mcp_server.get_review_config())
    assert not any("root config.yaml" in w for w in out["warnings"])


def test_cli_follows_the_same_review_as_the_mcp_server(bare_workspace, capsys):
    from prisma_review import cli

    _upgraded_install(bare_workspace)
    cli.main(["status"])
    out = capsys.readouterr().out
    assert str(bare_workspace.project_config("root-review")) in out
    assert "root config.yaml" in out  # the same notice as the MCP server


def test_cli_explicit_config_and_a_config_in_another_folder_still_win(bare_workspace, tmp_path,
                                                                      monkeypatch, capsys):
    from conftest import make_config, write_config
    from prisma_review import cli

    bare_workspace.add_project("alpha")
    other = write_config(tmp_path / "elsewhere" / "config.yaml", make_config("Elsewhere review"))
    cli.main(["status", "--config", str(other)])
    assert f"Config: {other}" in capsys.readouterr().out
    monkeypatch.chdir(other.parent)
    # PRISMA_WORKSPACE names the workspace explicitly, so it wins over the current folder ...
    assert cli.resolve_cli_config(None) == bare_workspace.project_config("alpha")
    # ... and without it a config.yaml in the current folder is used, as before 1.6.
    from prisma_review import workspace as ws
    monkeypatch.delenv("PRISMA_WORKSPACE")
    monkeypatch.setattr(ws, "INSTALL_DIR", bare_workspace.root)
    assert cli.resolve_cli_config(None) == other.resolve()
    monkeypatch.chdir(bare_workspace.root)
    assert cli.resolve_cli_config(None) == bare_workspace.project_config("alpha")


# --------------------------------------------------------------------------- R-24


def test_mcp_setup_endpoint_gives_the_stdio_command_and_every_tool(api_client, mcp_server):
    import asyncio
    from pathlib import Path

    body = api_client.get("/api/mcp/setup").json()
    assert body["transport"] == "stdio"
    assert body["script"].endswith("/run_mcp.py") and Path(body["script"]).is_file()
    assert Path(body["command"]).is_file() and Path(body["cwd"]).is_dir()
    assert "\\" not in body["command"] + body["script"] + body["cwd"]  # forward slashes for JSON configs
    assert body["active_config"].endswith("projects/alpha/config.yaml")

    registered = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {t["name"] for t in body["tools"]} == registered and len(registered) >= 21
    assert all(t["description"] for t in body["tools"])
    screen = next(t for t in body["tools"] if t["name"] == "screen_paper")
    assert "maybe" not in screen["description"]


def test_the_mcp_settings_page_has_no_sse_endpoint():
    from pathlib import Path

    page = (Path(__file__).resolve().parent.parent / "web" / "src" / "app" / "mcp-settings"
            / "page.tsx").read_text(encoding="utf-8")
    assert "/mcp/sse" not in page and '"sse"' not in page
    assert "fetchMcpSetup" in page


# --------------------------------------------------------------------------- OP-6


def _write_search_log(out, queries):
    log = {"tool_version": "1.6.0", "started_at": "2026-11-01T10:00:00+00:00",
           "finished_at": "2026-11-01T10:05:00+00:00",
           "date_range": {"start": "2021-01-01", "end": "2025-12-31"},
           "max_results_per_query": 500, "sources": ["openalex"],
           "filters": {"document_types": ["journal-article"], "require_abstract": True,
                       "open_access": False, "venues": []},
           "queries": queries, "complete": True, "truncated": False, "searches": []}
    (out / "01_search" / "search_log.json").write_text(json.dumps(log), encoding="utf-8")
    return log


def test_search_log_endpoint_serves_the_log_or_a_clean_404(api_client, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    resp = api_client.get("/api/reports/search-log")
    assert resp.status_code == 404 and "No search log yet" in resp.json()["detail"]
    log = _write_search_log(out, [{"index": 0, "name": "main", "terms": '"crop yield"'}])
    assert api_client.get("/api/reports/search-log").json() == log


def test_by_query_reports_the_queries_of_the_search_that_ran(api_client, workspace):
    out = workspace.output_dir("alpha")
    write_dataset(out)
    # No log: the current settings name the rows.
    body = api_client.get("/api/reports/by-query").json()
    assert body["queries_from"] == "settings"
    assert [q["terms"] for q in body["queries"]] == ['"crop yield" AND prediction']

    # The search ran with other terms than the settings hold now.
    _write_search_log(out, [{"index": 0, "name": "main", "terms": '"crop yield" OR harvest'}])
    body = api_client.get("/api/reports/by-query").json()
    assert body["queries_from"] == "search_log"
    assert body["queries"][0]["name"] == "main"
    assert body["queries"][0]["terms"] == '"crop yield" OR harvest'
    assert body["queries"][0]["found_raw"] == 7
    assert any("changed after this search ran" in n for n in body["notes"])

    _write_search_log(out, [{"index": 0, "name": "main", "terms": '"crop yield" AND prediction'}])
    body = api_client.get("/api/reports/by-query").json()
    assert not any("changed after" in n for n in body["notes"])


# --------------------------------------------------------------------------- R-11


@pytest.mark.parametrize("name", ["nul", "NUL", "con", "aux", "com1", "LPT9", "prn"])
def test_windows_reserved_names_are_not_project_names(api_client, mcp_server, workspace, name):
    resp = api_client.post("/api/projects", json={"name": name})
    assert resp.status_code in (400, 422), resp.text
    assert "reserves" in resp.text and "already exists" not in resp.text
    out = j(mcp_server.create_project(name))
    assert "error" in out and "reserves" in out["error"]
    assert sorted(p.name for p in workspace.projects_dir.iterdir() if p.is_dir()) == ["alpha"]


def test_names_that_only_start_like_a_device_are_fine(api_client, workspace):
    for name in ("con-review", "auxiliary", "com10", "null"):
        assert api_client.post("/api/projects", json={"name": name}).status_code == 200, name


# --------------------------------------------------------------------------- R-28


def test_list_projects_marks_the_pinned_review_as_in_use(mcp_server, bare_workspace, monkeypatch):
    bare_workspace.add_project("alpha", active=True)
    beta = bare_workspace.add_project("beta", active=False)
    listing = j(mcp_server.list_projects())
    assert listing["in_use"] == "alpha" and "pinned_config" not in listing
    assert [p["in_use"] for p in listing["projects"]] == [True, False]

    monkeypatch.setenv("PRISMA_CONFIG", str(beta))
    assert j(mcp_server.get_review_config())["project"] == "beta"
    listing = j(mcp_server.list_projects())
    assert listing["in_use"] == "beta" and listing["active"] == "alpha"
    by_name = {p["name"]: p for p in listing["projects"]}
    assert by_name["beta"]["in_use"] and not by_name["alpha"]["in_use"]
    assert any("PRISMA_CONFIG pins the config" in w and "switch_project is disabled" in w
               for w in listing["warnings"])
