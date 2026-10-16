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
