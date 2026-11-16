"""Dependency pins that keep a fresh install working."""

from __future__ import annotations

from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent


def _requirements(name: str) -> dict[str, Requirement]:
    reqs: dict[str, Requirement] = {}
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            req = Requirement(line)
            reqs[req.name.lower()] = req
    return reqs


def test_mcp_pinned_below_2():
    # mcp 2.x removed mcp.server.fastmcp, so the server crashed on import.
    mcp = _requirements("requirements.txt")["mcp"]
    assert not mcp.specifier.contains("2.0.0")
    assert not mcp.specifier.contains("2.3.0")
    assert mcp.specifier.contains("1.30.0")


def test_filelock_is_a_runtime_dependency():
    assert "filelock" in _requirements("requirements.txt")


def test_dev_requirements_have_test_tools():
    dev = _requirements("requirements-dev.txt")
    assert {"pytest", "httpx"} <= set(dev)


def test_fastmcp_importable_with_installed_mcp():
    from mcp.server.fastmcp import FastMCP  # noqa: F401


# --------------------------------------------------------------------------- review R-10, OP-3


def test_floors_skip_versions_with_known_advisories():
    core = _requirements("requirements.txt")
    api = _requirements("api/requirements.txt")
    assert not core["filelock"].specifier.contains("4.2.0")
    assert core["filelock"].specifier.contains("4.2.1")
    assert not core["mcp"].specifier.contains("1.29.1") and core["mcp"].specifier.contains("1.30.0")
    assert not core["requests"].specifier.contains("2.32.4")
    assert not core["certifi"].specifier.contains("2026.7.22")
    assert not core["pillow"].specifier.contains("12.3.0")
    assert not api["python-multipart"].specifier.contains("0.0.30")
    assert not api["starlette"].specifier.contains("0.38.6") and api["starlette"].specifier.contains("1.3.1")
    assert not api["fastapi"].specifier.contains("0.115.0")  # pinned starlette below 0.39


def test_numpy_is_a_declared_dependency():
    # prisma_review/dedup.py imports numpy directly (OP-3).
    assert "numpy" in _requirements("requirements.txt")
    assert "import numpy" in (ROOT / "prisma_review" / "dedup.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- review R-21


def _launcher():
    import importlib.util

    spec = importlib.util.spec_from_file_location("prisma_start_r21", ROOT / "start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_start_reinstalls_when_the_requirements_change(tmp_path, monkeypatch):
    launcher = _launcher()
    venv = tmp_path / ".venv"
    venv.mkdir()
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("requests>=2.33\n", encoding="utf-8")
    monkeypatch.setattr(launcher, "VENV_DIR", venv)
    monkeypatch.setattr(launcher, "REQUIREMENT_FILES", (reqs,))
    calls = []
    monkeypatch.setattr(launcher, "run", lambda cmd, **kw: calls.append(cmd) or 0)

    (venv / ".deps_installed").write_text("ok")  # the marker a v1.5 install left behind
    launcher.install_python_deps()
    assert len(calls) == 1 and "-r" in calls[0] and str(reqs) in calls[0]
    launcher.install_python_deps()
    assert len(calls) == 1  # unchanged requirements: nothing to do
    reqs.write_text("requests>=2.33\nfilelock>=4.2.1\n", encoding="utf-8")
    launcher.install_python_deps()
    assert len(calls) == 2


def test_start_installs_the_api_requirements_file():
    launcher = _launcher()
    assert ROOT / "api" / "requirements.txt" in launcher.REQUIREMENT_FILES


def test_entry_points_explain_a_missing_package(monkeypatch, capsys):
    import importlib.util as iu

    import pytest

    from prisma_review import deps

    real = iu.find_spec
    monkeypatch.setattr(iu, "find_spec", lambda name, *a: None if name == "filelock" else real(name, *a))
    assert deps.missing_packages() == ["filelock"]
    with pytest.raises(SystemExit) as info:
        deps.exit_if_missing()
    assert info.value.code == 1
    err = capsys.readouterr().err
    assert "filelock" in err and "start.py --install" in err and "api/requirements.txt" in err


def test_entry_points_call_the_check_before_importing_the_tool():
    for rel, marker in (("run_mcp.py", "from mcp_server.server import main"),
                        ("mcp_server/__main__.py", "from .server import main"),
                        ("prisma_review/__main__.py", "from .cli import main"),
                        ("api/main.py", "from fastapi import FastAPI")):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "exit_if_missing(" in text and text.index("exit_if_missing(") < text.index(marker), rel


def test_start_reinstalls_web_packages_when_the_lockfile_changes(tmp_path, monkeypatch):
    launcher = _launcher()
    web = tmp_path / "web"
    (web / "node_modules").mkdir(parents=True)  # node_modules of the previous version
    (web / "package-lock.json").write_text('{"v": 1}', encoding="utf-8")
    monkeypatch.setattr(launcher, "WEB_DIR", web)
    calls = []
    monkeypatch.setattr(launcher, "run", lambda cmd, **kw: calls.append(cmd) or 0)

    launcher.install_node_deps()
    assert calls and calls[-1][-1] == "ci"
    launcher.install_node_deps()
    assert len(calls) == 1
    (web / "package-lock.json").write_text('{"v": 2}', encoding="utf-8")
    launcher.install_node_deps()
    assert len(calls) == 2
