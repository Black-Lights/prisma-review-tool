"""Shared dependencies for FastAPI routes."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import HTTPException
from prisma_review.config import Config

_config: Config | None = None
# Fingerprint of the config currently loaded into _config: (path, mtime_ns).
# Lets get_config() detect when another process (e.g. the MCP server) switched
# the active project or rewrote the config on disk, and reload accordingly.
_config_source: tuple[str, int] | None = None
_file_lock = threading.Lock()

# Lazy-initialised session manager (needs _file_lock)
_session_manager = None


def get_projects_dir() -> Path:
    """Return the projects/ directory (sibling of api/)."""
    return Path(__file__).parent.parent / "projects"


def _active_config_path() -> Path:
    """Resolve the active project's config.yaml from disk, fresh every call.

    Mirrors how the Projects/Settings routes read `.active_project`, so the API
    follows project switches made by any process (including the MCP server).
    """
    projects_dir = get_projects_dir()
    active_file = projects_dir / ".active_project"
    if active_file.exists():
        name = active_file.read_text(encoding="utf-8").strip()
        candidate = projects_dir / name / "config.yaml"
        if candidate.exists():
            return candidate
    return Path(__file__).parent.parent / "config.yaml"


def _source_of(path: Path) -> tuple[str, int]:
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    return (str(path), mtime)


def init_config(config_path: Path | None = None) -> None:
    """Load config into the global cache. Called at app startup and on writes."""
    global _config, _config_source
    if config_path is None:
        config_path = _active_config_path()
    _config = Config.load(config_path)
    _config_source = _source_of(config_path)


def get_config() -> Config:
    """Get the active config as a FastAPI dependency.

    Re-resolves `.active_project` and the config file's mtime on every call and
    reloads if either changed, so screens reflect project switches / config
    edits made out-of-process (notably via the MCP server) without a restart.
    """
    path = _active_config_path()
    if _config is None or _config_source != _source_of(path):
        init_config(path)
    return _config


def get_file_lock() -> threading.Lock:
    """Get the file lock for thread-safe JSON writes."""
    return _file_lock


def get_session_manager():
    """Get the singleton SessionManager instance."""
    global _session_manager
    if _session_manager is None:
        from api.session import SessionManager
        config = get_config()
        _session_manager = SessionManager(_file_lock, state_file=config.state_file)
    return _session_manager


def switch_project(name: str) -> None:
    """Switch the active project. Raises if pipeline is running."""
    global _session_manager
    sm = get_session_manager()
    if sm.is_running:
        raise HTTPException(status_code=409, detail="Cannot switch while pipeline is running")

    projects_dir = get_projects_dir()
    config_path = projects_dir / name / "config.yaml"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    init_config(config_path)
    _session_manager = None
    (projects_dir / ".active_project").write_text(name, encoding="utf-8")
