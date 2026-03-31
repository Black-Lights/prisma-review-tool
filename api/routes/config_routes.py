"""Configuration read/write endpoints."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends

from prisma_review.config import Config
from api.deps import get_config, init_config

router = APIRouter(tags=["config"])


def _config_path() -> Path:
    projects_dir = Path(__file__).parent.parent.parent / "projects"
    active_file = projects_dir / ".active_project"
    if active_file.exists():
        name = active_file.read_text(encoding="utf-8").strip()
        return projects_dir / name / "config.yaml"
    return Path(__file__).parent.parent.parent / "config.yaml"


@router.get("/config")
def read_config():
    path = _config_path()
    if not path.exists():
        return {"error": "config.yaml not found"}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@router.put("/config")
def update_config(data: dict):
    path = _config_path()
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    # Reload config
    init_config(path)
    return {"status": "ok"}
