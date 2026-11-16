"""Configuration read/write endpoints.

Contract (the web Settings page relies on it):

* ``GET /api/config`` returns the active config plus ``"_version":
  "<mtime_ns>-<size>"``. API key values are masked as ``"********"`` when set
  (``api_keys.openalex_email`` is not a secret and is returned as-is).
* ``PUT /api/config`` takes the whole config. A masked value keeps the stored
  key; a missing ``api_keys`` section keeps the stored keys. If ``_version``
  is sent and the file changed since, the write is refused with 409.
  ``_version`` is never saved. The write is atomic and the response carries
  the new ``_version``.
"""

from __future__ import annotations

import copy

from fastapi import APIRouter, HTTPException

from prisma_review.config import (
    PUBLIC_API_KEY_FIELDS, Config, ConfigError, config_version, load_raw_config, save_raw_config,
)
from prisma_review import workspace
from prisma_review.storage import project_lock
from api.deps import active_config_path, init_config

router = APIRouter(tags=["config"])

SECRET_MASK = "********"


def _mask_secrets(data: dict) -> dict:
    out = copy.deepcopy(data)
    keys = out.get("api_keys")
    if isinstance(keys, dict):
        for field, value in keys.items():
            if field not in PUBLIC_API_KEY_FIELDS and value not in (None, ""):
                keys[field] = SECRET_MASK
    return out


def _restore_secrets(new: dict, current: dict) -> None:
    """Put stored key values back where the client sent the mask (or no api_keys at all)."""
    stored = current.get("api_keys") if isinstance(current.get("api_keys"), dict) else {}
    if "api_keys" not in new:
        if stored:
            new["api_keys"] = copy.deepcopy(stored)
        return
    keys = new.get("api_keys")
    if isinstance(keys, dict):
        for field, value in keys.items():
            if value == SECRET_MASK:
                keys[field] = stored.get(field, "")


def _read_versioned(path) -> tuple[dict, str | None]:
    """Load the config together with the version of exactly what was read."""
    for _ in range(5):
        before = config_version(path)
        data = load_raw_config(path)
        if config_version(path) == before:
            return data, before
    return data, config_version(path)


@router.get("/config")
def read_config():
    path = active_config_path()
    try:
        data, version = _read_versioned(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Config file not found: {path}")
    except ConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    out = _mask_secrets(data)
    out["_version"] = version
    return out


@router.get("/config/readiness")
def read_config_readiness():
    """Whether the config is ready to run, with problems and non-blocking warnings.

    The warnings include the notice that a root config.yaml with its own
    review is not used (an install upgraded from 1.5).
    """
    path = active_config_path()
    try:
        readiness = Config.load(path).readiness()
    except (ConfigError, FileNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    notice = workspace.root_config_notice()
    if notice:
        readiness["warnings"] = [notice] + list(readiness["warnings"])
    return readiness


@router.put("/config")
def update_config(data: dict):
    path = active_config_path()
    client_version = data.pop("_version", None)
    with project_lock(path.parent):
        try:
            current = load_raw_config(path) if path.exists() else {}
        except ConfigError:
            current = {}  # replacing a broken file is allowed
        current_version = config_version(path)
        if client_version is not None and client_version != current_version:
            raise HTTPException(status_code=409, detail={
                "error": "config_changed",
                "message": "The config changed on disk after it was loaded (another tab, "
                           "the MCP server or an editor). Reload it and apply your edits again.",
                "current_version": current_version,
            })
        _restore_secrets(data, current)
        save_raw_config(path, data)
        new_version = config_version(path)
    # Reload
    init_config(path)
    return {"status": "ok", "_version": new_version}
