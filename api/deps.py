"""Shared dependencies for FastAPI routes."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException

from prisma_review import pipeline, workspace
from prisma_review.config import Config, ConfigError

_config: Config | None = None
# Fingerprint of the config currently loaded into _config: (path, mtime_ns, size).
# Lets get_config() detect when another process (e.g. the MCP server) switched
# the active project or rewrote the config on disk, and reload accordingly. It
# is taken BEFORE loading, so a write landing mid-load causes one more reload.
_config_source: tuple[str, int, int] | None = None

# Lazy-initialised session manager. File writes are serialised with other
# processes through prisma_review.storage.project_lock, not a lock held here.
_session_manager = None


def get_projects_dir() -> Path:
    """Return the projects/ directory of the workspace."""
    return workspace.projects_dir()


def http_error(exc: workspace.WorkspaceError) -> HTTPException:
    """Map a project resolution error to an HTTP error with its message."""
    if isinstance(exc, workspace.InvalidProjectName):
        status = 400
    elif isinstance(exc, workspace.ProjectNotFound):
        status = 404
    else:  # stale marker, missing config, pinned config, project exists
        status = 409
    return HTTPException(status_code=status, detail=str(exc))


def active_config_path() -> Path:
    """The config.yaml in use (PRISMA_CONFIG, else the active project, else root).

    Raises 409 when the active-project marker is invalid or names a missing
    project, instead of silently falling back to another config.
    """
    try:
        return workspace.resolve_config_path()
    except workspace.WorkspaceError as exc:
        raise http_error(exc) from exc


def _source_of(path: Path) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_mtime_ns, st.st_size)


def init_config(config_path: Path | None = None) -> None:
    """Load config into the global cache. Called at app startup and on writes."""
    global _config, _config_source
    if config_path is None:
        config_path = active_config_path()
    source = _source_of(config_path)
    _config = Config.load(config_path)
    _config_source = source


def get_config() -> Config:
    """Get the active config as a FastAPI dependency.

    Re-resolves the active project and the config file's fingerprint on every
    call and reloads if either changed, so screens reflect project switches /
    config edits made out-of-process (notably via the MCP server) without a
    restart. If the file on disk is unreadable or not a mapping (an editor
    saving it non-atomically), the last good config of that file stays in use.
    """
    global _config, _config_source
    path = active_config_path()
    source = _source_of(path)
    if source is None:
        raise HTTPException(status_code=409, detail=f"Config file not found: {path}")
    if _config is not None and _config_source == source:
        return _config
    try:
        config = Config.load(path)
    except (ConfigError, OSError) as exc:
        if _config is not None and _config.config_path == path:
            print(f"Warning: keeping the previous config, {exc}", file=sys.stderr)
            return _config
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _config, _config_source = config, source
    return config


def get_session_manager():
    """Get the singleton SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        from api.session import SessionManager
        config = get_config()
        _session_manager = SessionManager(state_file=config.state_file)
    return _session_manager


def pipeline_running() -> bool:
    """True if this process is running a pipeline (without creating a manager)."""
    return _session_manager is not None and _session_manager.is_running


def project_run_active(state_file: Path | None) -> bool:
    """True if this process runs a pipeline, or ``state_file`` records a live run
    owned by another process (e.g. the MCP server)."""
    if pipeline_running():
        return True
    return state_file is not None and pipeline.active_run(state_file) is not None


def _active_state_file() -> Path | None:
    """The active project's review_state.json, or None when no config is usable."""
    try:
        return get_config().state_file
    except HTTPException:
        return None


def reset_project_caches() -> None:
    """Forget the cached config and session manager (after a project switch or delete)."""
    global _config, _config_source, _session_manager
    _config = None
    _config_source = None
    _session_manager = None


def switch_project(name: str) -> None:
    """Switch the active project. Raises if the name is invalid or a pipeline is running."""
    try:
        workspace.validate_project_name(name)
        workspace.ensure_not_pinned()
    except workspace.WorkspaceError as exc:
        raise http_error(exc) from exc
    if project_run_active(_active_state_file()):
        raise HTTPException(status_code=409, detail="Cannot switch while pipeline is running")
    try:
        workspace.set_active_project(name)
    except workspace.WorkspaceError as exc:
        raise http_error(exc) from exc
    reset_project_caches()
