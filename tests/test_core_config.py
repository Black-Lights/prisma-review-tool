"""Config loading, readiness and the template (MCP#10, 15, 17, PIPE#15, SEARCH#6, SEARCH#15)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from conftest import REPO_ROOT, make_config, write_config
from prisma_review.config import Config


@pytest.mark.parametrize("data", [
    {"project": {"name": "X"}, "search": {"sources": ["openalex"], "queries": [{"name": "a", "terms": "b"}]},
     "screening": {"rules": {"include_keywords": None}}},
    {"project": {"name": "X"}, "search": {"sources": ["openalex"], "queries": None},
     "screening": {"rules": {"include_keywords": ["a"]}}},
    {"project": {"name": "X"}, "search": {"sources": ["openalex"], "queries": ['"a" AND "b"']},
     "screening": {"rules": {"include_keywords": ["a"]}}},
    {"project": None, "search": None, "screening": None, "api_keys": None},
    {"search": {"filters": None, "date_range": None}, "screening": {"rules": None}},
])
def test_readiness_never_raises_on_empty_sections(data):
    # MCP#15: `queries:` or `include_keywords:` left empty (null) made
    # readiness() raise, so start_pipeline threw instead of answering.
    result = Config(data).readiness()
    assert result["ready"] is False and result["problems"]


def test_unquoted_yaml_dates_read_as_strings(tmp_path):
    path = tmp_path / "config.yaml"
    text = yaml.safe_dump(make_config(), sort_keys=False).replace("'2020-01-01'", "2020-01-01")
    path.write_text(text, encoding="utf-8")
    assert isinstance(yaml.safe_load(text)["search"]["date_range"]["start"], dt.date)
    assert Config.load(path).date_start == "2020-01-01"


@pytest.mark.parametrize("raw, expected", [
    (None, []),
    ("llm", ["llm"]),                       # a plain string was iterated per character
    ([2024, None, "", "  rag  "], ["2024", "rag"]),  # numbers and empty items crashed screening
    (["a", "b"], ["a", "b"]),
])
def test_required_keywords_are_coerced(raw, expected):
    cfg = Config({"screening": {"rules": {"required_keywords": raw}}})
    assert cfg.required_keywords == expected


def test_default_sources_unchanged_and_crossref_opt_in():
    # MCP#17 / SEARCH#15: configs without search.sources silently gained Crossref.
    assert Config({}).sources == ["arxiv", "openalex", "semantic_scholar"]
    assert Config({"search": {"sources": None}}).sources == []
    assert Config({"search": {"sources": ["OpenAlex ", "crossref"]}}).sources == ["openalex", "crossref"]


def test_template_enables_only_openalex_and_documents_new_keys():
    text = (REPO_ROOT / "config.template.yaml").read_text(encoding="utf-8")
    tpl = yaml.safe_load(text)
    assert tpl["search"]["sources"] == ["openalex"]
    assert "openalex_key" in tpl["api_keys"]
    assert "required_keywords" in text


def test_openalex_without_key_warns_but_does_not_block():
    cfg = make_config()
    cfg["api_keys"]["openalex_key"] = ""
    readiness = Config(cfg).readiness()
    assert readiness["ready"] is True
    assert any("openalex_key" in w for w in readiness["warnings"])
    assert Config(make_config()).readiness()["warnings"] == []


def test_unknown_source_warns():
    cfg = make_config()
    cfg["search"]["sources"] = ["openalex", "pubmed"]
    assert any("pubmed" in w for w in Config(cfg).readiness()["warnings"])


def test_min_include_hits_zero_is_a_problem():
    cfg = make_config()
    cfg["screening"]["rules"]["min_include_hits"] = 0
    assert not Config(cfg).readiness()["ready"]


@pytest.mark.parametrize("text", ["", "# only a comment\n", "- a\n- b\n", "just a string\n", "a: [b\n"])
def test_non_mapping_or_broken_yaml_is_a_config_error(tmp_path, text):
    from prisma_review.config import ConfigError, load_raw_config

    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_raw_config(path)
    with pytest.raises(ConfigError):
        Config.load(path)


def test_save_raw_config_refuses_non_mapping_and_keeps_file(tmp_path):
    from prisma_review.config import ConfigError, save_raw_config

    path = write_config(tmp_path / "config.yaml")
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ConfigError):
        save_raw_config(path, ["not", "a", "mapping"])
    assert path.read_text(encoding="utf-8") == before


def test_save_raw_config_round_trip_and_version_changes(tmp_path):
    from prisma_review.config import config_version, load_raw_config, save_raw_config

    path = tmp_path / "config.yaml"
    assert config_version(path) is None
    save_raw_config(path, make_config("One"))
    v1 = config_version(path)
    save_raw_config(path, make_config("Two, a longer name"))
    v2 = config_version(path)
    assert v1 and v2 and v1 != v2
    assert load_raw_config(path)["project"]["name"] == "Two, a longer name"
    assert [p.name for p in Path(tmp_path).iterdir()] == ["config.yaml"]
