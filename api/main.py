"""FastAPI backend for PRISMA Review Tool.

Wraps the prisma_review module as a REST API.
Run with: uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure prisma_review is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.deps import init_config, get_projects_dir
from api.routes import papers, pipeline, reports, config_routes, projects


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "default-project"


def _auto_migrate(root: Path, projects_dir: Path) -> Path:
    """Migrate existing root config.yaml + prisma_output/ into projects/.

    Returns the config path of the migrated project.
    """
    root_config = root / "config.yaml"
    with open(root_config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    project_name = cfg.get("project", {}).get("name", "default-project")
    slug = _slugify(project_name)

    project_dir = projects_dir / slug
    project_dir.mkdir(parents=True, exist_ok=True)

    # Copy config.yaml
    dest_config = project_dir / "config.yaml"
    shutil.copy2(root_config, dest_config)

    # Update output_dir in copied config to relative path
    with open(dest_config, "r", encoding="utf-8") as f:
        new_cfg = yaml.safe_load(f)
    if "project" in new_cfg:
        new_cfg["project"]["output_dir"] = "./prisma_output"
    with open(dest_config, "w", encoding="utf-8") as f:
        yaml.safe_dump(new_cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Copy prisma_output/ if it exists
    root_output = root / "prisma_output"
    if root_output.is_dir():
        dest_output = project_dir / "prisma_output"
        if not dest_output.exists():
            shutil.copytree(root_output, dest_output)

    # Write active project marker
    (projects_dir / ".active_project").write_text(slug, encoding="utf-8")

    return dest_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize config on startup, auto-migrating if needed."""
    root = Path(__file__).parent.parent
    projects_dir = get_projects_dir()
    active_file = projects_dir / ".active_project"

    if active_file.exists():
        # Load the active project's config
        name = active_file.read_text(encoding="utf-8").strip()
        config_path = projects_dir / name / "config.yaml"
        if config_path.exists():
            init_config(config_path)
        else:
            init_config()
    elif (root / "config.yaml").exists():
        # Auto-migrate existing root config into projects/
        projects_dir.mkdir(parents=True, exist_ok=True)
        config_path = _auto_migrate(root, projects_dir)
        init_config(config_path)
    else:
        init_config()
    yield


app = FastAPI(
    title="PRISMA Review Tool API",
    description="REST API for PRISMA 2020 systematic literature reviews",
    version="1.4.3",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reports.router, prefix="/api")
app.include_router(papers.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(config_routes.router, prefix="/api")
app.include_router(projects.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
