"""Project management endpoints: list, create, switch, delete, duplicate, export, import.

Every ``{name}`` is validated as a project folder slug inside projects/ before
it touches the disk: on Windows an encoded backslash (``..%5C..%5CUsers``)
used to reach rmtree and the zip export.
"""

from __future__ import annotations

import io
import re
import shutil
import zipfile
from pathlib import Path

import yaml

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from prisma_review import workspace
from prisma_review.config import Config, ConfigError, load_raw_config, save_raw_config
from prisma_review.pipeline import active_run
from prisma_review.storage import LOCK_FILENAME, atomic_write_json, read_json
from api.deps import (
    get_projects_dir, http_error, pipeline_running, reset_project_caches, switch_project,
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_name(name: str) -> str:
    try:
        return workspace.validate_project_name(name)
    except workspace.WorkspaceError as exc:
        raise http_error(exc) from exc


def _active_project() -> tuple[str | None, str | None]:
    """(active project name, problem with the marker) without raising."""
    try:
        return workspace.read_active_project(), None
    except workspace.WorkspaceError as exc:
        return None, str(exc)


def _require_active_project() -> str:
    try:
        name = workspace.read_active_project()
    except workspace.WorkspaceError as exc:
        raise http_error(exc) from exc
    if not name:
        raise HTTPException(status_code=404, detail="No active project")
    return name


def _state_file(project_dir: Path) -> Path:
    """The project's review_state.json (its config may move output_dir)."""
    try:
        return Config.load(project_dir / "config.yaml").state_file
    except (OSError, ConfigError):
        return project_dir / "prisma_output" / "review_state.json"


def _display_name(project_dir: Path) -> str:
    try:
        name = (load_raw_config(project_dir / "config.yaml").get("project") or {}).get("name")
    except (OSError, ConfigError, AttributeError):
        name = None
    return str(name) if name else project_dir.name


def _read_project_info(project_dir: Path, active_name: str | None) -> dict:
    """Read metadata for a single project directory."""
    name = project_dir.name
    paper_counts = {"search": 0, "dedup": 0, "screened": 0, "eligible": 0}

    state_path = project_dir / "prisma_output" / "review_state.json"
    if state_path.exists():
        try:
            state = read_json(state_path)
            paper_counts["search"] = state.get("search", {}).get("total", 0)
            paper_counts["dedup"] = state.get("dedup", {}).get("remaining", 0)
            paper_counts["screened"] = state.get("screen", {}).get("included", 0)
            paper_counts["eligible"] = state.get("eligibility", {}).get("included", 0)
        except Exception:
            pass

    return {
        "name": name,
        "display_name": _display_name(project_dir),
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
    """List all projects with metadata (``active_error`` explains an invalid marker)."""
    projects_dir = get_projects_dir()
    active, active_error = _active_project()
    result = [_read_project_info(projects_dir / name, active)
              for name in workspace.list_project_names()]
    out: dict = {"projects": result}
    if active_error:
        out["active_error"] = active_error
    return out


@router.post("")
def create_project(body: CreateProjectRequest):
    """Create a new empty project from the config template."""
    try:
        slug = workspace.create_project(body.name)
    except workspace.WorkspaceError as exc:
        raise http_error(exc) from exc
    return {"status": "created", "name": slug, "display_name": body.name.strip()}


@router.post("/{name}/switch")
def switch_active_project(name: str):
    """Switch to a different project."""
    switch_project(name)
    return {"status": "switched", "active": name}


@router.get("/active")
def get_active_project():
    """Return the currently active project name."""
    name, error = _active_project()
    if not name:
        return {"active": None, "error": error} if error else {"active": None}
    return {"active": name, "display_name": _display_name(get_projects_dir() / name)}


@router.delete("/{name}")
def delete_project(name: str):
    """Delete a project directory."""
    name = _valid_name(name)
    projects_dir = get_projects_dir()
    project_dir = projects_dir / name

    if not project_dir.exists() or not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    active, _ = _active_project()
    # A run in this process, or one recorded on disk by another process (the
    # MCP server may work on this project even when it is not the active one).
    if (name == active and pipeline_running()) or active_run(_state_file(project_dir)) is not None:
        raise HTTPException(status_code=409, detail="Cannot delete a project while its pipeline is running")
    shutil.rmtree(project_dir)

    # If we deleted the active project, switch to another or clear
    if name == active:
        remaining = [n for n in workspace.list_project_names()
                     if (projects_dir / n / "config.yaml").is_file()]
        if remaining:
            workspace.set_active_project(remaining[0])
        else:
            workspace.clear_active_project()
        reset_project_caches()

    return {"status": "deleted", "name": name}


@router.post("/{name}/duplicate")
def duplicate_project(name: str, body: DuplicateProjectRequest):
    """Duplicate a project to a new name."""
    name = _valid_name(name)
    projects_dir = get_projects_dir()
    src = projects_dir / name
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    new_slug = _valid_name(workspace.slugify(body.new_name))
    dest = projects_dir / new_slug
    if dest.exists():
        raise HTTPException(status_code=409, detail=f"Project '{new_slug}' already exists")

    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(LOCK_FILENAME))

    # Update project name in the copied config
    dest_config = dest / "config.yaml"
    if dest_config.exists():
        try:
            cfg = load_raw_config(dest_config)
        except ConfigError:
            cfg = None
        if cfg is not None and isinstance(cfg.get("project"), dict):
            cfg["project"]["name"] = body.new_name
            save_raw_config(dest_config, cfg)

    return {"status": "duplicated", "name": new_slug, "display_name": body.new_name}


# config.yaml and its backups or local variants (config.yaml.bak-2026-10-15,
# config.local.yaml): every one of them may hold API keys.
_CONFIG_FILE_RE = re.compile(r"(?i)^config([._-].*)?\.ya?ml(\..*)?$")


def _without_secrets(path: Path) -> bytes | None:
    """A config file with its API keys and contact email blanked, or None to leave it out.

    A file that is not a YAML mapping cannot be cleaned, so it is not exported.
    """
    try:
        data = load_raw_config(path)
    except (OSError, ConfigError):
        return None
    keys = data.get("api_keys")
    if isinstance(keys, dict):
        data["api_keys"] = {field: "" for field in keys}
    return yaml.safe_dump(data, default_flow_style=False, allow_unicode=True,
                          sort_keys=False).encode("utf-8")


@router.get("/export/{name}")
def export_project(name: str):
    """Export a project as a .zip file, without API keys or the contact email.

    config.yaml (and any backup of it) goes into the archive with every
    ``api_keys`` value blanked: an export is meant to be shared or backed up.
    Importing it fills the keys in from the current project.
    """
    name = _valid_name(name)
    project_dir = get_projects_dir() / name

    if not project_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in project_dir.rglob("*"):
            if not file_path.is_file() or file_path.name == LOCK_FILENAME:
                continue
            arcname = file_path.relative_to(project_dir).as_posix()
            if file_path.parent == project_dir and _CONFIG_FILE_RE.match(file_path.name):
                cleaned = _without_secrets(file_path)
                if cleaned is not None:
                    zf.writestr(arcname, cleaned)
                continue
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
            slug = _valid_name(workspace.slugify(zip_name))
            project_dir = projects_dir / slug

            if project_dir.exists():
                raise HTTPException(status_code=409, detail=f"Project '{slug}' already exists")

            project_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(project_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")

    try:
        _adopt_imported_config(project_dir)
    except HTTPException:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise
    return {"status": "imported", "name": slug}


def _adopt_imported_config(project_dir: Path) -> None:
    """Check an imported project's config and give it the current API keys.

    The archive is untrusted: its ``output_dir`` must stay inside the new
    project folder, or a later search would delete result folders wherever it
    points (400, and the import is undone). Exports carry no API keys, so
    empty ones are filled from the config in use, as for a new project.
    """
    cfg_path = project_dir / "config.yaml"
    if not cfg_path.is_file():
        return
    try:
        data = load_raw_config(cfg_path)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=f"The imported config.yaml is not usable: {exc}")
    out = Config(data, base_dir=project_dir, path=cfg_path).output_dir.resolve()
    if not workspace._is_relative_to(out, project_dir.resolve()):
        raise HTTPException(status_code=400, detail=(
            f"The imported config.yaml sets project.output_dir to a folder outside the project "
            f"({out}). Set it to ./prisma_output in the archive and import it again."))
    current = workspace._current_api_keys(None)
    keys = data.get("api_keys") if isinstance(data.get("api_keys"), dict) else {}
    filled = {**keys, **{k: v for k, v in current.items() if v and not keys.get(k)}}
    if filled != keys:
        data["api_keys"] = filled
        save_raw_config(cfg_path, data)


# ---------------------------------------------------------------------------
# UI state persistence (per-project)
# ---------------------------------------------------------------------------

@router.get("/active/ui-state")
def get_ui_state():
    """Return saved UI filter state for the active project."""
    name, _ = _active_project()
    if not name:
        return {}
    state_path = get_projects_dir() / name / "ui_state.json"
    try:
        return read_json(state_path, default={})
    except Exception:
        return {}


@router.put("/active/ui-state")
def save_ui_state(body: dict):
    """Save UI filter state for the active project."""
    name = _require_active_project()
    atomic_write_json(get_projects_dir() / name / "ui_state.json", body, indent=2)
    return {"status": "ok"}
