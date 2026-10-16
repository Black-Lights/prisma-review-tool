"""One shared project resolver for the API and the MCP server (MCP#1, 2, 8, 9, 20, PIPE#17)."""

from __future__ import annotations

import pytest
import yaml

from conftest import make_config, write_config, write_dataset
from prisma_review import workspace as ws


def test_slugify():
    assert ws.slugify("AI in Healthcare: A Review!") == "ai-in-healthcare-a-review"
    assert ws.slugify("  my__review  2 ") == "my-review-2"
    assert ws.slugify("../../evil") == "evil"
    assert ws.slugify("!!!") == "default-project"


@pytest.mark.parametrize("name", [
    "../../outside_app", "..", ".", "C:/abs/dir", "C:\\Windows", "a/b", "a\\b",
    "", "Alpha", "my review", ".active_project", "x:y", None,
])
def test_validate_project_name_rejects(bare_workspace, name):
    with pytest.raises(ws.InvalidProjectName):
        ws.validate_project_name(name)


@pytest.mark.parametrize("name", ["alpha", "my-review-2", "default-project"])
def test_validate_project_name_accepts_slugs(bare_workspace, name):
    assert ws.validate_project_name(name) == name


def test_no_marker_resolves_to_root_config(bare_workspace):
    root_cfg = bare_workspace.write_root_config()
    assert ws.read_active_project() is None
    res = ws.resolve()
    assert (res.config_path, res.project, res.source) == (root_cfg, None, "root")


def test_no_marker_and_no_root_config_is_an_error(bare_workspace):
    with pytest.raises(ws.ConfigNotFound):
        ws.resolve()


def test_valid_marker_resolves_to_project(workspace):
    res = ws.resolve()
    assert res.config_path == workspace.project_config("alpha")
    assert (res.project, res.source) == ("alpha", "marker")


@pytest.mark.parametrize("marker", ["deleted-project", "../../outside", "C:\\abs", "", "  "])
def test_stale_or_invalid_marker_raises_instead_of_falling_back(workspace, marker):
    # MCP#9: a marker naming a deleted project silently retargeted every tool
    # (start_pipeline included) to the root config.yaml.
    workspace.write_root_config(make_config("Root review"))
    workspace.set_marker(marker)
    with pytest.raises(ws.ActiveProjectError):
        ws.read_active_project()
    with pytest.raises(ws.ActiveProjectError):
        ws.resolve_config_path()


def test_prisma_config_env_pins_the_config(workspace, monkeypatch):
    other = workspace.add_project("beta", make_config("Beta"), active=False)
    monkeypatch.setenv("PRISMA_CONFIG", str(other))
    res = ws.resolve()
    assert (res.config_path, res.project, res.source) == (other.resolve(), "beta", "env")


def test_prisma_config_relative_to_cwd_and_outside_projects(workspace, monkeypatch, tmp_path):
    elsewhere = write_config(tmp_path / "elsewhere" / "my.yaml")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRISMA_CONFIG", "elsewhere/my.yaml")
    res = ws.resolve()
    assert res.config_path == elsewhere.resolve() and res.project is None


def test_prisma_config_missing_file_is_an_error(workspace, monkeypatch, tmp_path):
    monkeypatch.setenv("PRISMA_CONFIG", str(tmp_path / "nope.yaml"))
    with pytest.raises(ws.ConfigNotFound):
        ws.resolve()


def test_set_active_project_validates(workspace, tmp_path):
    outside = tmp_path / "outside_app"
    write_config(outside / "config.yaml", {"other_app": 1})
    for bad in ("../../outside_app", str(outside), ".."):
        with pytest.raises(ws.InvalidProjectName):
            ws.set_active_project(bad)
    with pytest.raises(ws.ProjectNotFound):
        ws.set_active_project("missing")
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"
    workspace.add_project("beta", active=False)
    ws.set_active_project("beta")
    assert workspace.marker.read_text(encoding="utf-8") == "beta"


def test_ensure_not_pinned(workspace, monkeypatch):
    ws.ensure_not_pinned()
    monkeypatch.setenv("PRISMA_CONFIG", str(workspace.project_config("alpha")))
    with pytest.raises(ws.ConfigPinned):
        ws.ensure_not_pinned()


def test_create_project_from_template_carries_api_keys(workspace):
    slug = ws.create_project("My New Review")
    assert slug == "my-new-review"
    cfg = yaml.safe_load(workspace.project_config(slug).read_text(encoding="utf-8"))
    assert cfg["project"] == {**cfg["project"], "name": "My New Review", "output_dir": "./prisma_output"}
    assert cfg["api_keys"] == make_config()["api_keys"]
    assert "queries" in cfg["search"]  # came from the template
    assert workspace.output_dir(slug).is_dir()
    assert workspace.marker.read_text(encoding="utf-8") == "alpha"  # not switched
    with pytest.raises(ws.ProjectExists):
        ws.create_project("my new review")


def test_create_project_rejects_empty_name(workspace):
    with pytest.raises(ws.InvalidProjectName):
        ws.create_project("   ")


def test_migrate_root_to_projects(bare_workspace):
    bare_workspace.write_root_config(make_config("Root Review"), dataset=True)
    slug = ws.migrate_root_to_projects()
    assert slug == "root-review"
    assert bare_workspace.marker.read_text(encoding="utf-8") == "root-review"
    cfg = yaml.safe_load(bare_workspace.project_config(slug).read_text(encoding="utf-8"))
    assert cfg["project"]["output_dir"] == "./prisma_output"
    assert (bare_workspace.output_dir(slug) / "03_screen" / "maybe.json").is_file()
    # Root files stay for the CLI; a second call is a no-op.
    assert (bare_workspace.root / "config.yaml").is_file()
    assert ws.migrate_root_to_projects() is None


def test_migrate_never_overwrites_an_existing_project(bare_workspace):
    bare_workspace.write_root_config(make_config("Root Review"))
    existing = write_config(bare_workspace.project_config("root-review"), make_config("Kept"))
    assert ws.migrate_root_to_projects() == "root-review"
    assert yaml.safe_load(existing.read_text(encoding="utf-8"))["project"]["name"] == "Kept"


def test_migrate_uses_configured_output_dir(bare_workspace):
    bare_workspace.write_root_config(make_config(project={"name": "R", "output_dir": "./out"}))
    write_dataset(bare_workspace.root / "out")
    slug = ws.migrate_root_to_projects()
    assert (bare_workspace.output_dir(slug) / "review_state.json").is_file()


def test_project_for_config(workspace, tmp_path):
    assert ws.project_for_config(workspace.project_config("alpha")) == "alpha"
    assert ws.project_for_config(tmp_path / "x" / "config.yaml") is None


def test_list_project_names_skips_hidden(workspace):
    (workspace.projects_dir / ".trash").mkdir()
    workspace.add_project("beta", active=False)
    assert ws.list_project_names() == ["alpha", "beta"]


def test_marker_with_bom_and_newline_is_read(workspace):
    workspace.marker.write_bytes(b"\xef\xbb\xbfalpha\r\n")
    assert ws.read_active_project() == "alpha"
