"""The CLI search shows the config warnings the web app and the MCP server show.

The missing OpenAlex key warning (SEARCH#6) reached the MCP tools and the web
readiness check, but ``python -m prisma_review search`` ran OpenAlex without a
key and said nothing.
"""

from __future__ import annotations

import pytest

from conftest import FAKE_OPENALEX_KEY, make_config, write_config
from prisma_review.config import Config


@pytest.mark.parametrize("sources, key, expected", [
    (["openalex"], "", True),
    (["openalex", "arxiv"], "", True),
    (["openalex"], FAKE_OPENALEX_KEY, False),
    (["arxiv"], "", False),
])
def test_cli_search_warns_about_a_missing_openalex_key_only_when_relevant(
        workspace, monkeypatch, capsys, sources, key, expected):
    from prisma_review import cli, pipeline

    cfg = make_config("Alpha review")
    cfg["search"]["sources"] = sources
    cfg["api_keys"]["openalex_key"] = key
    config = Config.load(write_config(workspace.project_config("alpha"), cfg))
    monkeypatch.setattr(pipeline, "run_all_searches", lambda config, **_kw: {})

    cli.cmd_search(config)
    out = capsys.readouterr().out
    assert ("api_keys.openalex_key" in out) is expected
    assert FAKE_OPENALEX_KEY not in out
