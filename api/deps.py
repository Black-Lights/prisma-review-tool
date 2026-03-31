"""Shared dependencies for FastAPI routes."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import HTTPException
from prisma_review.config import Config

_config: Config | None = None
_file_lock = threading.Lock()

# Lazy-initialised session manager (needs _file_lock)
_session_manager = None


def get_projects_dir() -> Path:
    """Return the projects/ directory (sibling of api/)."""
    return Path(__file__).parent.parent / "projects"


def init_config(config_path: Path | None = None) -> None:
    """Initialize the global config. Called once at app startup."""
    global _config
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    _config = Config.load(config_path)


def get_config() -> Config:
    """Get the loaded config. Use as a FastAPI dependency."""
    if _config is None:
        init_config()
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
