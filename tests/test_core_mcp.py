"""MCP server: project resolution, safety and set_review_config.

Covers MCP#1, 2, 4, 8, 9, 12, 13, 14, 15, 16, 21 and SEARCH#6 (warnings).
No test here starts a real search: pipeline starts use a fake session manager.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, make_config, write_config, write_dataset


def j(text: str) -> dict:
    return json.loads(text)


class FakeSession:
    """Stands in for SessionManager so no test touches the network."""

    def __init__(self, running: bool = False):
        self.is_running = running
        self.started = []

    def start_full_pipeline(self, config):
        self.started.append(config.config_path)
        return "fake-session"

    def request_cancel(self):
        return self.is_running

    def get_progress(self):
        return {"status": "running" if self.is_running else "idle"}


def _same(a, b) -> bool:
    return Path(a).resolve() == Path(b).resolve()


# --------------------------------------------------------------------------- identity


def test_server_reports_tool_version_and_instructions(mcp_server):
    from prisma_review import __version__

    opts = mcp_server.mcp._mcp_server.create_initialization_options()
    assert opts.server_version == __version__
    assert "get_review_config" in opts.instructions
    assert "PRISMA_CONFIG" in opts.instructions


def test_startup_log_names_project_on_stderr_only(mcp_server, workspace, capsys):
    from prisma_review import __version__

    mcp_server.log_startup()
    out, err = capsys.readouterr()
    assert out == ""
    assert __version__ in err and "alpha" in err
    assert str(workspace.project_config("alpha").name) in err


def test_startup_log_reports_invalid_marker(mcp_server, workspace, capsys):
    workspace.set_marker("../../elsewhere")
    mcp_server.log_startup()
    out, err = capsys.readouterr()
    assert out == "" and "no usable config" in err


# --------------------------------------------------------------------------- MCP#2 traversal


@pytest.mark.parametrize("name", ["../../outside_app", "..", "<abs>", "a/b", "C:\\Windows"])
def test_switch_project_rejects_traversal(mcp_server, workspace, name):
    outside = workspace.root.parent / "outside_app"
    write_config(outside / "config.yaml", {"other_app": {"setting": 1}})
    before = (outside / "config.yaml").read_text(encoding="utf-8")
    name = name.replace("<abs>", str(outside))

    out = j(mcp_server.switch_project(name))
    assert "error" in out
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"

    # A follow-up write still lands in the active project, never outside.
    assert j(mcp_server.set_review_config(name="pwned"))["project"] == "alpha"
    assert (outside / "config.yaml").read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------- MCP#9 stale marker


def test_stale_marker_is_an_error_not_a_root_fallback(mcp_server, workspace):
    root_cfg = workspace.write_root_config(make_config("Root review"))
    before = root_cfg.read_text(encoding="utf-8")
    workspace.set_marker("deleted-project")
    mcp_server._session_manager = FakeSession()

    for call in (mcp_server.get_review_config, mcp_server.get_screening_stats,
                 mcp_server.start_pipeline, lambda: mcp_server.set_review_config(name="X")):
        out = j(call())
        assert "deleted-project" in out["error"]
    assert mcp_server._session_manager.started == []
    assert root_cfg.read_text(encoding="utf-8") == before

    listing = j(mcp_server.list_projects())
    assert listing["active"] is None and "deleted-project" in listing["active_error"]
    # Recover by switching to a real project.
    assert j(mcp_server.switch_project("alpha"))["status"] == "switched"


# --------------------------------------------------------------------------- MCP#1 pin and echo


def test_prisma_config_pins_the_server(mcp_server, workspace, monkeypatch):
    beta = workspace.add_project("beta", make_config("Beta review"), active=False)
    monkeypatch.setenv("PRISMA_CONFIG", str(beta))

    out = j(mcp_server.get_review_config())
    assert (out["project"], out["resolved_from"]) == ("beta", "env")
    assert "PRISMA_CONFIG" in j(mcp_server.switch_project("alpha"))["error"]
    assert "PRISMA_CONFIG" in j(mcp_server.create_project("Gamma"))["error"]
    assert j(mcp_server.set_review_config(name="Beta renamed"))["project"] == "beta"
    assert yaml.safe_load(beta.read_text(encoding="utf-8"))["project"]["name"] == "Beta renamed"
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"
    assert j(mcp_server.list_projects())["pinned_config"] == str(beta.resolve())


def test_mutating_tools_echo_project_and_config_path(mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    cfg_path = workspace.project_config("alpha")
    calls = {
        "screen_paper": lambda: mcp_server.screen_paper("p4", "include", "fits"),
        "batch_screen_papers": lambda: mcp_server.batch_screen_papers(
            [{"paper_id": "p5", "decision": "exclude", "reason": "off topic"}]),
        "eligibility_screen_paper": lambda: mcp_server.eligibility_screen_paper("p1", "include", "fits"),
        "batch_eligibility_screen": lambda: mcp_server.batch_eligibility_screen(
            [{"paper_id": "p2", "decision": "exclude", "reason": "no evaluation"}]),
        "rescreen": lambda: mcp_server.rescreen(2),
        "set_review_config": lambda: mcp_server.set_review_config(min_include_hits=2),
        "generate_report": mcp_server.generate_report,
        "get_screening_stats": mcp_server.get_screening_stats,
    }
    for name, call in calls.items():
        out = j(call())
        assert "error" not in out, (name, out)
        assert out["project"] == "alpha", name
        assert _same(out["config_path"], cfg_path), name


def test_pipeline_tools_echo_project(mcp_server, workspace):
    fake = FakeSession()
    mcp_server._session_manager = fake
    out = j(mcp_server.start_pipeline())
    assert out["status"] == "started" and out["project"] == "alpha"
    assert _same(fake.started[0], workspace.project_config("alpha"))
    fake.is_running = True
    out = j(mcp_server.stop_pipeline())
    assert out["status"] == "cancel_requested" and out["project"] == "alpha"


# --------------------------------------------------------------------------- MCP#4 switching while running


def test_switch_and_create_refused_while_pipeline_runs(mcp_server, workspace):
    workspace.add_project("beta", active=False)
    mcp_server._session_manager = FakeSession(running=True)

    assert "pipeline is running" in j(mcp_server.switch_project("beta"))["error"]
    assert "pipeline is running" in j(mcp_server.create_project("Gamma"))["error"]
    assert not (workspace.projects_dir / "gamma").exists()
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"

    out = j(mcp_server.create_project("Gamma", switch=False))
    assert out["status"] == "created" and out["project"] == "gamma"
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"


# --------------------------------------------------------------------------- MCP#8 root-only install


def test_create_project_on_root_only_install_keeps_root_review(mcp_server, bare_workspace):
    bare_workspace.write_root_config(make_config("Root Review"), dataset=True)

    out = j(mcp_server.create_project("Second review"))
    assert out["status"] == "created" and out["migrated_root_project"] == "root-review"
    listing = j(mcp_server.list_projects())
    assert {p["name"] for p in listing["projects"]} == {"root-review", "second-review"}
    assert listing["active"] == "second-review"

    assert j(mcp_server.switch_project("root-review"))["status"] == "switched"
    assert j(mcp_server.get_screening_stats())["screen"]["maybe"] == 3


# --------------------------------------------------------------------------- MCP#12 validation


@pytest.mark.parametrize("kwargs, fragment", [
    ({"sources": ["pubmed", "OpenAlex"]}, "pubmed"),
    ({"sources": []}, "at least one"),
    ({"min_include_hits": 0}, "min_include_hits"),
    ({"min_include_hits": 11}, "min_include_hits"),
    ({"date_start": "last year"}, "date_start"),
    ({"date_end": "2024-02-30"}, "date_end"),
    ({"date_start": "2027-01-01"}, "after"),
    ({"queries": '[{"name": "q", "terms": 123}]'}, "terms"),
    ({"queries": []}, "non-empty"),
    ({"queries": [{"name": "q", "terms": "a"}, {"name": "q", "terms": "b"}]}, "twice"),
    ({"queries": "not json"}, "JSON"),
    ({"include_keywords": ["ok", "  "]}, "include_keywords"),
    ({"required_keywords": [""]}, "required_keywords"),
    ({"document_types": ["article"]}, "article"),
    ({"venues": [" "]}, "venues"),
    ({"name": "  "}, "name"),
])
def test_set_review_config_rejects_invalid_values(mcp_server, workspace, kwargs, fragment):
    path = workspace.project_config("alpha")
    before = path.read_text(encoding="utf-8")
    out = j(mcp_server.set_review_config(**kwargs))
    assert "error" in out, out
    assert fragment in json.dumps(out["problems"])
    assert path.read_text(encoding="utf-8") == before


def test_set_review_config_normalises_and_keeps_other_keys(mcp_server, workspace):
    path = workspace.project_config("alpha")
    cfg = make_config()
    cfg["my_extension"] = {"keep": True}
    write_config(path, cfg)
    out = j(mcp_server.set_review_config(
        sources=["OpenAlex", "arxiv", "openalex"], document_types=["Review"],
        date_start="2021-01-01", include_keywords=[" crop ", "yield"]))
    assert out["status"] == "ok"
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["search"]["sources"] == ["openalex", "arxiv"]
    assert saved["search"]["filters"]["document_types"] == ["review"]
    assert saved["search"]["date_range"]["start"] == "2021-01-01"
    assert saved["screening"]["rules"]["include_keywords"] == ["crop", "yield"]
    assert saved["my_extension"] == {"keep": True}
    assert saved["api_keys"] == make_config()["api_keys"]


# --------------------------------------------------------------------------- MCP#14 null sections


@pytest.mark.parametrize("override", [
    {"search": {"sources": ["openalex"], "queries": [{"name": "q", "terms": "a"}], "filters": None}},
    {"screening": None},
    {"screening": {"rules": None}},
    {"search": None},
    {"project": None},
])
def test_set_review_config_handles_null_sections(mcp_server, workspace, override):
    path = workspace.project_config("alpha")
    write_config(path, make_config(**override))
    out = j(mcp_server.set_review_config(
        name="N", document_types=["journal-article"], include_keywords=["a"], date_start="2021-01-01"))
    assert out["status"] == "ok", out
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["search"]["filters"]["document_types"] == ["journal-article"]
    assert saved["screening"]["rules"]["include_keywords"] == ["a"]
    assert saved["project"]["name"] == "N"


# --------------------------------------------------------------------------- MCP#15 JSON, never exceptions


def test_get_review_config_with_unquoted_yaml_date(mcp_server, workspace):
    path = workspace.project_config("alpha")
    text = yaml.safe_dump(make_config(), sort_keys=False).replace("'2020-01-01'", "2020-01-01")
    path.write_text(text, encoding="utf-8")
    out = j(mcp_server.get_review_config())
    assert out["date_range"]["start"] == "2020-01-01"


def test_start_pipeline_with_null_lists_returns_guard_json(mcp_server, workspace):
    cfg = make_config()
    cfg["search"]["queries"] = None
    cfg["screening"]["rules"]["include_keywords"] = None
    write_config(workspace.project_config("alpha"), cfg)
    mcp_server._session_manager = FakeSession()
    out = j(mcp_server.start_pipeline())
    assert out["error"].startswith("Config not ready") and len(out["problems"]) == 2
    assert mcp_server._session_manager.started == []


def test_broken_config_comes_back_as_json_error(mcp_server, workspace):
    workspace.project_config("alpha").write_text("- not\n- a mapping\n", encoding="utf-8")
    for call in (mcp_server.get_review_config, mcp_server.get_screening_stats,
                 lambda: mcp_server.set_review_config(name="X")):
        assert "mapping" in j(call())["error"]


def test_unexpected_exception_comes_back_as_json_error(mcp_server, workspace, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(mcp_server, "load_state", boom)
    assert j(mcp_server.get_screening_stats()) == {"error": "RuntimeError: disk on fire"}


# --------------------------------------------------------------------------- MCP#16 guard wording


def test_guard_only_blames_the_template_when_it_is_the_template(mcp_server, workspace):
    path = workspace.project_config("alpha")
    mcp_server._session_manager = FakeSession()
    cfg = make_config()
    cfg["search"]["sources"] = []
    write_config(path, cfg)
    out = j(mcp_server.start_pipeline())
    assert "template" not in out["error"]
    assert "set_review_config" in out["hint"]

    write_config(path, yaml.safe_load((REPO_ROOT / "config.template.yaml").read_text(encoding="utf-8")))
    assert "template" in j(mcp_server.start_pipeline())["error"]


def test_rescreen_is_guarded(mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    cfg = make_config()
    cfg["screening"]["rules"]["include_keywords"] = []
    write_config(workspace.project_config("alpha"), cfg)
    out = j(mcp_server.rescreen(2))
    assert out["error"].startswith("Config not ready")


# --------------------------------------------------------------------------- MCP#13, 21, SEARCH#6


def _tools(mcp_server) -> dict:
    return {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_tool_descriptions_are_neutral_and_accurate(mcp_server):
    tools = _tools(mcp_server)
    assert len(tools) >= 21
    text = " ".join((t.description or "") for t in tools.values()).lower()
    for stale in ("gfm", "graph foundation model", "ignores or/not", "first 5 quoted phrases"):
        assert stale not in text
    assert len(tools["set_review_config"].description) < 1500


def test_get_review_config_reports_query_and_key_warnings(mcp_server, workspace):
    cfg = make_config()
    cfg["api_keys"]["openalex_key"] = ""
    cfg["search"]["sources"] = ["openalex", "crossref"]
    cfg["search"]["queries"] = [{"name": "q", "terms": '"crop yield" OR "harvest"'}]
    write_config(workspace.project_config("alpha"), cfg)
    out = j(mcp_server.get_review_config())
    assert any("crossref" in w for w in out["query_warnings"])
    assert any("openalex_key" in w for w in out["warnings"])
    assert out["ready"] is True
    assert "FAKE-SCOPUS" not in json.dumps(out)


def test_queries_accept_a_native_list_or_a_json_string(mcp_server, workspace):
    path = workspace.project_config("alpha")
    q = [{"name": "a", "terms": '"x"  AND y'}]
    assert j(mcp_server.set_review_config(queries=q))["status"] == "ok"
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["search"]["queries"] == [
        {"name": "a", "terms": '"x" AND y'}]
    q2 = [{"name": "b", "terms": "z"}]
    assert j(mcp_server.set_review_config(queries=json.dumps(q2)))["status"] == "ok"
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["search"]["queries"] == q2


def test_batch_decisions_accept_a_native_list_or_a_json_string(mcp_server, workspace):
    write_dataset(workspace.output_dir("alpha"))
    as_list = [{"paper_id": "p4", "decision": "include", "reason": "fits"}]
    assert j(mcp_server.batch_screen_papers(as_list))["results"][0]["status"] == "ok"
    as_json = json.dumps([{"paper_id": "p5", "decision": "exclude", "reason": "no"}])
    assert j(mcp_server.batch_screen_papers(as_json))["results"][0]["status"] == "ok"
    assert "error" in j(mcp_server.batch_screen_papers("not json"))
