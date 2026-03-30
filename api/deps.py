"""Shared dependencies for FastAPI routes."""

from __future__ import annotations

import threading
from pathlib import Path

from prisma_review.config import Config

_config: Config | None = None
_file_lock = threading.Lock()

# Lazy-initialised session manager (needs _file_lock)
_session_manager = None


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
