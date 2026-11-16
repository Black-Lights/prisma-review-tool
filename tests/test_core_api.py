"""Web API: project routes, config contract, CORS, config caching.

Covers the pre-existing traversal hole, CORS "*" (WEB#13), MCP#9/10, PIPE#10, PIPE#17.
"""

from __future__ import annotations

import os
import threading
import time
from urllib.parse import quote

import pytest
import yaml

from conftest import FAKE_OPENALEX_KEY, FAKE_SCOPUS_KEY, make_config, write_config
from prisma_review.config import config_version


# --------------------------------------------------------------------------- traversal


@pytest.fixture
def victim(workspace):
    """A directory outside projects/ that the API must never touch."""
    target = workspace.root.parent / "victim"
    write_config(target / "config.yaml", {"other_app": {"setting": 1}})
    (target / "precious.txt").write_text("keep me", encoding="utf-8")
    return target


def _traversal_names(victim):
    return ["..%5C..%5Cvictim", quote(str(victim), safe=""), "..%5Cprojects"]


@pytest.mark.parametrize("idx", [0, 1, 2])
def test_delete_rejects_traversal(api_client, victim, workspace, idx):
    name = _traversal_names(victim)[idx]
    resp = api_client.delete(f"/api/projects/{name}")
    assert resp.status_code == 400, resp.text
    assert (victim / "precious.txt").read_text(encoding="utf-8") == "keep me"
    assert workspace.project_config("alpha").is_file()


@pytest.mark.parametrize("idx", [0, 1])
def test_export_rejects_traversal(api_client, victim, idx):
    resp = api_client.get(f"/api/projects/export/{_traversal_names(victim)[idx]}")
    assert resp.status_code == 400
    assert b"precious" not in resp.content


@pytest.mark.parametrize("idx", [0, 1])
def test_switch_rejects_traversal_and_keeps_marker(api_client, victim, workspace, idx):
    resp = api_client.post(f"/api/projects/{_traversal_names(victim)[idx]}/switch")
    assert resp.status_code == 400
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"


def test_duplicate_rejects_traversal(api_client, victim, workspace):
    resp = api_client.post("/api/projects/..%5C..%5Cvictim/duplicate", json={"new_name": "copy"})
    assert resp.status_code == 400
    assert not (workspace.projects_dir / "copy").exists()


def test_project_routes_still_work(api_client, workspace):
    assert api_client.post("/api/projects", json={"name": "Beta Review"}).json()["name"] == "beta-review"
    assert api_client.post("/api/projects/beta-review/switch").json() == {"status": "switched", "active": "beta-review"}
    assert workspace.marker.read_text(encoding="utf-8") == "beta-review"
    resp = api_client.post("/api/projects/beta-review/duplicate", json={"new_name": "Gamma"})
    assert resp.json()["name"] == "gamma"
    assert api_client.get("/api/projects/export/gamma").status_code == 200
    names = [p["name"] for p in api_client.get("/api/projects").json()["projects"]]
    assert names == ["alpha", "beta-review", "gamma"]
    # Deleting the active project activates another one that has a config.
    assert api_client.delete("/api/projects/beta-review").status_code == 200
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"


# --------------------------------------------------------------------------- stale marker


def test_stale_marker_is_409_not_a_silent_root_fallback(api_client, workspace):
    # MCP#9 / PIPE#17: Settings read nothing while the pipeline used root config.yaml.
    workspace.write_root_config(make_config("Root review"))
    workspace.set_marker("deleted-project")
    for url in ("/api/config", "/api/pipeline/status"):
        resp = api_client.get(url)
        assert resp.status_code == 409, (url, resp.text)
        assert "deleted-project" in resp.json()["detail"]
    listing = api_client.get("/api/projects").json()
    assert "deleted-project" in listing["active_error"]
    assert api_client.get("/api/projects/active").json()["active"] is None
    # The user can recover by switching.
    assert api_client.post("/api/projects/alpha/switch").status_code == 200
    assert api_client.get("/api/config").status_code == 200


def test_startup_migrates_a_root_only_install(bare_workspace):
    from fastapi.testclient import TestClient

    import api.deps as deps
    from api.main import app

    bare_workspace.write_root_config(make_config("Root Review"), dataset=True)
    deps.reset_project_caches()
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/projects/active").json()["active"] == "root-review"
        assert client.get("/api/pipeline/status").json()["project"] == "Root Review"
    deps.reset_project_caches()


def test_api_version_is_the_tool_version(api_client):
    from prisma_review import __version__
    assert api_client.get("/openapi.json").json()["info"]["version"] == __version__


# --------------------------------------------------------------------------- CORS


def test_cors_allows_local_web_origins_only(api_client, monkeypatch):
    def acao(origin):
        return api_client.get("/api/health", headers={"Origin": origin}).headers.get(
            "access-control-allow-origin")

    assert acao("http://localhost:3000") == "http://localhost:3000"
    assert acao("http://127.0.0.1:3000") == "http://127.0.0.1:3000"
    # TestClient's server port is 80: start.py would serve the web app at 1080+.
    assert acao("http://localhost:1080") == "http://localhost:1080"
    assert acao("http://evil.example") is None
    assert acao("http://localhost:5173") is None
    assert acao("null") is None
    monkeypatch.setenv("PRISMA_CORS_ORIGINS", "http://lab-box:4000, https://x.example/")
    assert acao("http://lab-box:4000") == "http://lab-box:4000"
    assert acao("https://x.example") == "https://x.example"


def test_preflight_from_foreign_origin_is_refused(api_client):
    resp = api_client.options("/api/config", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "PUT"})
    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers
    ok = api_client.options("/api/config", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "content-type"})
    assert ok.status_code == 200


def test_state_changes_from_foreign_origin_are_refused(api_client, workspace):
    before = workspace.project_config("alpha").read_text(encoding="utf-8")
    evil = {"Origin": "http://evil.example"}
    assert api_client.put("/api/config", json={"x": 1}, headers=evil).status_code == 403
    assert api_client.delete("/api/projects/alpha", headers=evil).status_code == 403
    assert api_client.post("/api/projects/alpha/switch", headers=evil).status_code == 403
    assert workspace.project_config("alpha").read_text(encoding="utf-8") == before
    # Same request from the web app (or with no Origin at all) goes through.
    local = {"Origin": "http://localhost:3000"}
    assert api_client.post("/api/projects/alpha/switch", headers=local).status_code == 200
    assert api_client.post("/api/projects/alpha/switch").status_code == 200


# --------------------------------------------------------------------------- config contract


def test_get_config_masks_keys_and_has_version(api_client, workspace):
    resp = api_client.get("/api/config", headers={"Origin": "http://localhost:3000"})
    body = resp.json()
    assert FAKE_SCOPUS_KEY not in resp.text and FAKE_OPENALEX_KEY not in resp.text
    assert body["api_keys"] == {"scopus": "********", "openalex_key": "********", "openalex_email": ""}
    assert body["_version"] == config_version(workspace.project_config("alpha"))
    assert body["project"]["name"] == "Alpha review"


def test_put_config_keeps_masked_keys_and_strips_version(api_client, workspace):
    body = api_client.get("/api/config").json()
    body["project"]["name"] = "Renamed"
    resp = api_client.put("/api/config", json=body)
    assert resp.status_code == 200, resp.text
    path = workspace.project_config("alpha")
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["api_keys"]["scopus"] == FAKE_SCOPUS_KEY
    assert saved["api_keys"]["openalex_key"] == FAKE_OPENALEX_KEY
    assert saved["project"]["name"] == "Renamed"
    assert "_version" not in saved
    assert resp.json() == {"status": "ok", "_version": config_version(path)}


def test_put_config_with_new_key_value_replaces_it(api_client, workspace):
    body = api_client.get("/api/config").json()
    body["api_keys"]["openalex_key"] = "NEW-KEY"
    api_client.put("/api/config", json=body)
    saved = yaml.safe_load(workspace.project_config("alpha").read_text(encoding="utf-8"))
    assert saved["api_keys"]["openalex_key"] == "NEW-KEY"
    assert saved["api_keys"]["scopus"] == FAKE_SCOPUS_KEY


def test_put_config_without_api_keys_keeps_stored_keys(api_client, workspace):
    body = api_client.get("/api/config").json()
    del body["api_keys"], body["_version"]
    assert api_client.put("/api/config", json=body).status_code == 200
    saved = yaml.safe_load(workspace.project_config("alpha").read_text(encoding="utf-8"))
    assert saved["api_keys"]["scopus"] == FAKE_SCOPUS_KEY


def test_put_config_with_stale_version_is_409(api_client, workspace):
    body = api_client.get("/api/config").json()
    # Another writer (MCP set_review_config, another tab) changes the file.
    path = workspace.project_config("alpha")
    write_config(path, make_config("Changed by MCP"))
    body["project"]["name"] = "Stale edit"
    resp = api_client.put("/api/config", json=body)
    assert resp.status_code == 409
    assert resp.json()["detail"]["current_version"] == config_version(path)
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["project"]["name"] == "Changed by MCP"


def test_put_config_rejects_non_mapping(api_client, workspace):
    before = workspace.project_config("alpha").read_text(encoding="utf-8")
    assert api_client.put("/api/config", json=["a", "b"]).status_code == 422
    assert workspace.project_config("alpha").read_text(encoding="utf-8") == before


def test_config_readiness_endpoint(api_client, workspace):
    cfg = make_config()
    cfg["api_keys"]["openalex_key"] = ""
    write_config(workspace.project_config("alpha"), cfg)
    body = api_client.get("/api/config/readiness").json()
    assert body["ready"] is True
    assert any("openalex_key" in w for w in body["warnings"])


# --------------------------------------------------------------------------- deps.get_config caching


def test_get_config_keeps_last_good_config_when_file_is_broken(workspace):
    import api.deps as deps

    deps.reset_project_caches()
    assert deps.get_config().project_name == "Alpha review"
    workspace.project_config("alpha").write_text("- not\n- a mapping\n", encoding="utf-8")
    assert deps.get_config().project_name == "Alpha review"
    write_config(workspace.project_config("alpha"), make_config("Fixed"))
    assert deps.get_config().project_name == "Fixed"
    deps.reset_project_caches()


def test_get_config_fingerprint_includes_size(workspace):
    import api.deps as deps

    deps.reset_project_caches()
    path = workspace.project_config("alpha")
    assert deps.get_config().project_name == "Alpha review"
    st = os.stat(path)
    write_config(path, make_config("A longer project name"))
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))  # same mtime, different size
    assert deps.get_config().project_name == "A longer project name"
    deps.reset_project_caches()


def test_config_hot_reload_never_sees_a_half_written_file(workspace):
    # PIPE#10 repro: PUT /api/config truncated config.yaml in place, so a
    # concurrent reader got an empty config and cached it.
    import api.deps as deps
    from api.routes.config_routes import update_config

    deps.reset_project_caches()
    stop = threading.Event()
    bad: list[str] = []
    reads = [0]

    def writer():
        i = 0
        while not stop.is_set():
            data = make_config("x" * (5 + i % 40))
            data["screening"]["rules"]["min_include_hits"] = 2 + i % 3
            update_config(data)
            i += 1

    def reader():
        while not stop.is_set():
            try:
                cfg = deps.get_config()
                if "screening" not in cfg._data:
                    bad.append("missing screening")
                reads[0] += 1
            except Exception as exc:  # noqa: BLE001 - any failure is a bad read
                bad.append(type(exc).__name__)

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(1.5)
    stop.set()
    for t in threads:
        t.join()
    assert reads[0] > 0
    assert bad == []
    on_disk = yaml.safe_load(workspace.project_config("alpha").read_text(encoding="utf-8"))
    assert deps.get_config()._data == on_disk
    deps.reset_project_caches()
