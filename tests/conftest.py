"""Shared fixtures: a throw-away workspace, configs, a tiny dataset, the MCP server and the API.

Every fixture points the tool at a temp folder through PRISMA_WORKSPACE, so no
test reads or writes the install folder's config.yaml or projects/.
"""

from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fake secrets: tests assert these never leak into responses.
FAKE_SCOPUS_KEY = "FAKE-SCOPUS-KEY-0000"
FAKE_OPENALEX_KEY = "FAKE-OPENALEX-KEY-1111"


def make_config(name: str = "Alpha review", **sections: Any) -> dict:
    """A minimal config that passes readiness. Keyword arguments replace whole top-level sections."""
    cfg = {
        "project": {"name": name, "output_dir": "./prisma_output"},
        "api_keys": {"scopus": FAKE_SCOPUS_KEY, "openalex_key": FAKE_OPENALEX_KEY,
                     "openalex_email": ""},
        "search": {
            "date_range": {"start": "2020-01-01", "end": "2026-12-31"},
            "max_results_per_query": 25,
            "sources": ["openalex"],
            "queries": [{"name": "main", "terms": '"crop yield" AND prediction'}],
        },
        "dedup": {"doi_match": True, "fuzzy_title_threshold": 90},
        "screening": {"rules": {"include_keywords": ["crop", "yield", "prediction"],
                                "exclude_keywords": ["medical"], "min_include_hits": 2}},
    }
    cfg.update(copy.deepcopy(sections))
    return cfg


def write_config(path: Path, data: dict | None = None, *, header: str = "") -> Path:
    """Write ``data`` (default: make_config()) as YAML to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = make_config() if data is None else data
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
    return path


def write_dataset(output_dir: Path) -> dict:
    """Write a tiny synthetic review into ``output_dir`` (01_search, 02_dedup, 03_screen, state).

    Seven raw records, one duplicate, six unique: p1 and p2 included by rule,
    p3 excluded by rule, p4 to p6 "maybe". Returns {"ids": [...], "by_decision": {...}}.
    """
    from prisma_review.diagram import save_state
    from prisma_review.models import Paper, save_papers

    def paper(pid: str, title: str, abstract: str, **kw: Any) -> Paper:
        return Paper(id=pid, title=title, abstract=abstract, year=2023, source="openalex",
                     authors=["Doe, Jane", "Roe, Rick"], doi=f"10.1234/{pid}",
                     matched_queries=["main"], **kw)

    unique = [
        paper("p1", "Crop yield prediction with deep learning", "Crop yield prediction from imagery."),
        paper("p2", "Yield prediction for maize crops", "We study crop yield prediction."),
        paper("p3", "Medical imaging of crops", "A medical study."),
        paper("p4", "Remote sensing of fields", "Satellite data for agriculture."),
        paper("p5", "Soil moisture estimation", "Soil sensing with radar."),
        paper("p6", "Weather and crops", "Climate effects on harvests."),
    ]
    duplicate = paper("p1dup", unique[0].title, unique[0].abstract, duplicate_of="p1")

    save_papers(unique + [duplicate], output_dir / "01_search" / "all_records.json")
    save_papers(unique, output_dir / "02_dedup" / "deduplicated.json")

    decisions = {"p1": "include", "p2": "include", "p3": "exclude",
                 "p4": "maybe", "p5": "maybe", "p6": "maybe"}
    screened = copy.deepcopy(unique)
    for p in screened:
        p.screen_decision = decisions[p.id]
        p.screen_reason = "keyword rules"
        p.screen_method = "rule"
    screen_dir = output_dir / "03_screen"
    save_papers(screened, screen_dir / "screen_results.json")
    by_decision = {}
    for decision, fname in (("include", "included.json"), ("exclude", "excluded.json"),
                            ("maybe", "maybe.json")):
        subset = [p for p in screened if p.screen_decision == decision]
        save_papers(subset, screen_dir / fname)
        by_decision[decision] = [p.id for p in subset]

    save_state({
        "search": {"openalex": 7, "total": 7},
        "dedup": {"duplicates_removed": 1, "remaining": 6},
        "screen": {"total_screened": 6, "included": 2, "excluded": 1, "maybe": 3},
    }, output_dir / "review_state.json")
    return {"ids": [p.id for p in unique], "by_decision": by_decision}


@dataclass
class Workspace:
    """A temp workspace root: config.yaml (optional) and projects/<name>/."""

    root: Path

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects"

    @property
    def marker(self) -> Path:
        return self.projects_dir / ".active_project"

    def project_config(self, name: str) -> Path:
        return self.projects_dir / name / "config.yaml"

    def output_dir(self, name: str) -> Path:
        return self.projects_dir / name / "prisma_output"

    def add_project(self, name: str = "alpha", config: dict | None = None, *,
                    active: bool = True, dataset: bool = False) -> Path:
        """Create projects/<name>/config.yaml (+ optional dataset); returns the config path."""
        cfg_path = write_config(self.project_config(name),
                                config if config is not None else make_config(name.title()))
        self.output_dir(name).mkdir(parents=True, exist_ok=True)
        if dataset:
            write_dataset(self.output_dir(name))
        if active:
            self.set_marker(name)
        return cfg_path

    def set_marker(self, text: str) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.marker.write_text(text, encoding="utf-8")

    def write_root_config(self, config: dict | None = None, *, dataset: bool = False) -> Path:
        cfg_path = write_config(self.root / "config.yaml", config)
        if dataset:
            write_dataset(self.root / "prisma_output")
        return cfg_path


@pytest.fixture
def bare_workspace(tmp_path, monkeypatch) -> Workspace:
    """An empty workspace root (no config, no projects/) that every resolver points at."""
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("PRISMA_WORKSPACE", str(root))
    monkeypatch.delenv("PRISMA_CONFIG", raising=False)
    monkeypatch.delenv("PRISMA_CORS_ORIGINS", raising=False)
    monkeypatch.chdir(root)
    return Workspace(root)


@pytest.fixture
def workspace(bare_workspace) -> Workspace:
    """A workspace with one ready project, "alpha", marked active (no dataset)."""
    bare_workspace.projects_dir.mkdir()
    bare_workspace.add_project("alpha", make_config("Alpha review"))
    return bare_workspace


@pytest.fixture
def mcp_server(bare_workspace):
    """The MCP server module with its per-process caches reset.

    Tools act on the temp workspace; request ``workspace`` too for the ready
    "alpha" project, or use ``bare_workspace`` to build another layout.
    """
    import mcp_server.server as server

    server._session_manager = None
    yield server
    server._session_manager = None


@pytest.fixture
def api_client(workspace):
    """A FastAPI TestClient (lifespan run) bound to ``workspace``."""
    from fastapi.testclient import TestClient

    import api.deps as deps
    from api.main import app

    deps.reset_project_caches()
    # The API answers to local host names only (TestClient's default is "testserver").
    with TestClient(app, base_url="http://localhost") as client:
        yield client
    deps.reset_project_caches()
