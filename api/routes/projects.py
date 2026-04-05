"""Project management endpoints — list, create, switch, delete, duplicate, export, import."""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import get_projects_dir, switch_project

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "default-project"


def _active_project_name() -> str | None:
    active_file = get_projects_dir() / ".active_project"
    if active_file.exists():
        return active_file.read_text(encoding="utf-8").strip()
    return None


def _read_project_info(project_dir: Path, active_name: str | None) -> dict:
    """Read metadata for a single project directory."""
    name = project_dir.name
    display_name = name
    paper_counts = {"search": 0, "dedup": 0, "screened": 0, "eligible": 0}

    config_path = project_dir / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            display_name = cfg.get("project", {}).get("name", name)
        except Exception:
            pass

    state_path = project_dir / "prisma_output" / "review_state.json"
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            paper_counts["search"] = state.get("search", {}).get("total", 0)
            paper_counts["dedup"] = state.get("dedup", {}).get("remaining", 0)
            paper_counts["screened"] = state.get("screen", {}).get("included", 0)
            paper_counts["eligible"] = state.get("eligibility", {}).get("included", 0)
        except Exception:
            pass

    return {
        "name": name,
        "display_name": display_name,
        "is_active": name == active_name,
        "paper_counts": paper_counts,
    }


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    name: str

class DuplicateProjectRequest(BaseModel):
    new_name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_projects():
    """List all projects with metadata."""
    projects_dir = get_projects_dir()
    if not projects_dir.exists():
        return {"projects": []}

    active = _active_project_name()
    result = []
    for entry in sorted(projects_dir.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            result.append(_read_project_info(entry, active))
    return {"projects": result}


@router.post("")
def create_project(body: CreateProjectRequest):
    """Create a new empty project from the config template."""
    slug = _slugify(body.name)
    projects_dir = get_projects_dir()
    project_dir = projects_dir / slug

    if project_dir.exists():
        raise HTTPException(status_code=409, detail=f"Project '{slug}' already exists")

    project_dir.mkdir(parents=True, exist_ok=True)

    # Copy template config
    root = Path(__file__).parent.parent.parent
    template = root / "config.template.yaml"
    dest_config = project_dir / "config.yaml"

    # Try to carry over API keys from the currently active project
    active_api_keys = {}
    active_name = _active_project_name()
    if active_name:
        active_config = projects_dir / active_name / "config.yaml"
        if active_config.exists():
            try:
                with open(active_config, "r", encoding="utf-8") as f:
                    active_cfg = yaml.safe_load(f) or {}
                active_api_keys = active_cfg.get("api_keys", {})
            except Exception:
                pass

    if template.exists():
        shutil.copy2(template, dest_config)
        # Set the project name and output_dir in the new config
        with open(dest_config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if "project" not in cfg:
            cfg["project"] = {}
        cfg["project"]["name"] = body.name
        cfg["project"]["output_dir"] = "./prisma_output"
        # Preserve API keys from active project
        if active_api_keys:
            cfg["api_keys"] = active_api_keys
        with open(dest_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        # Minimal fallback config
        cfg = {
            "project": {"name": body.name, "output_dir": "./prisma_output"},
            "api_keys": active_api_keys or {"scopus": "", "openalex_email": ""},
            "search": {"date_range": {"start": "2015-01-01", "end": "2026-12-31"}, "max_results_per_query": 500, "sources": ["openalex"], "queries": []},
            "dedup": {"doi_match": True, "fuzzy_title_threshold": 90},
            "screening": {"rules": {"include_keywords": [], "exclude_keywords": [], "min_include_hits": 2}},
        }
        with open(dest_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Create empty prisma_output dir
    (project_dir / "prisma_output").mkdir(exist_ok=True)

    return {"status": "created", "name": slug, "display_name": body.name}


@router.post("/{name}/switch")
def switch_active_project(name: str):
    """Switch to a different project."""
    switch_project(name)
    return {"status": "switched", "active": name}


@router.get("/active")
def get_active_project():
    """Return the currently active project name."""
    name = _active_project_name()
    if not name:
        return {"active": None}

    projects_dir = get_projects_dir()
    project_dir = projects_dir / name
    display_name = name
    if (project_dir / "config.yaml").exists():
        try:
            with open(project_dir / "config.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            display_name = cfg.get("project", {}).get("name", name)
        except Exception:
            pass

    return {"active": name, "display_name": display_name}


@router.delete("/{name}")
def delete_project(name: str):
    """Delete a project directory."""
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    active = _active_project_name()
    shutil.rmtree(project_dir)

    # If we deleted the active project, switch to another or clear
    if name == active:
        remaining = [d for d in projects_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        active_file = projects_dir / ".active_project"
        if remaining:
            new_active = remaining[0].name
            active_file.write_text(new_active, encoding="utf-8")
            switch_project(new_active)
        elif active_file.exists():
            active_file.unlink()

    return {"status": "deleted", "name": name}


@router.post("/{name}/duplicate")
def duplicate_project(name: str, body: DuplicateProjectRequest):
    """Duplicate a project to a new name."""
    projects_dir = get_projects_dir()
    src = projects_dir / name
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    new_slug = _slugify(body.new_name)
    dest = projects_dir / new_slug
    if dest.exists():
        raise HTTPException(status_code=409, detail=f"Project '{new_slug}' already exists")

    shutil.copytree(src, dest)

    # Update project name in the copied config
    dest_config = dest / "config.yaml"
    if dest_config.exists():
        with open(dest_config, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if "project" in cfg:
            cfg["project"]["name"] = body.new_name
        with open(dest_config, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return {"status": "duplicated", "name": new_slug, "display_name": body.new_name}


@router.get("/export/{name}")
def export_project(name: str):
    """Export a project as a .zip file."""
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                arcname = str(file_path.relative_to(project_dir))
                zf.write(file_path, arcname)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@router.post("/import")
async def import_project(file: UploadFile = File(...)):
    """Import a project from an uploaded .zip file."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    projects_dir = get_projects_dir()
    projects_dir.mkdir(parents=True, exist_ok=True)

    content = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            # Determine project name from zip — use the folder name (stem of zip)
            zip_name = Path(file.filename).stem
            slug = _slugify(zip_name)
            project_dir = projects_dir / slug

            if project_dir.exists():
                raise HTTPException(status_code=409, detail=f"Project '{slug}' already exists")

            project_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(project_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")

    return {"status": "imported", "name": slug}


# ---------------------------------------------------------------------------
# UI state persistence (per-project)
# ---------------------------------------------------------------------------

@router.get("/active/ui-state")
def get_ui_state():
    """Return saved UI filter state for the active project."""
    name = _active_project_name()
    if not name:
        return {}
    state_path = get_projects_dir() / name / "ui_state.json"
    if not state_path.exists():
        return {}
    try:
        return json.load(open(state_path, "r", encoding="utf-8"))
    except Exception:
        return {}


@router.put("/active/ui-state")
def save_ui_state(body: dict):
    """Save UI filter state for the active project."""
    name = _active_project_name()
    if not name:
        raise HTTPException(status_code=404, detail="No active project")
    state_path = get_projects_dir() / name / "ui_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2)
    return {"status": "ok"}
