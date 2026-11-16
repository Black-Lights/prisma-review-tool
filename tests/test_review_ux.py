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
