"""Server-Sent Events stream for real-time UI updates.

The API and the MCP server are separate processes that share state only
through disk (``config.yaml``, ``review_state.json``, the result files and
``.active_project``). This endpoint watches those files server-side and tells
connected browsers what changed, so every screen refetches only the data that
changed instead of each one polling independently.

Protocol (one stream per browser tab):

* on connect: ``retry: 1000`` and ``data: {"version", "areas": ["all"], "initial": true}``;
* on change: ``data: {"version", "areas": [...]}``, areas from
  ``project, config, state, pipeline, screen, eligibility, downloads``;
* a ``: keepalive`` comment after 15 s without events;
* the server ends each stream after about 55 s and the browser reconnects
  within a second, so an open tab never blocks shutdown or ``--reload``.

One disk check per tick is shared by every connected client, and runs in a
worker thread so the event loop never waits on the disk.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from prisma_review import workspace
from prisma_review.storage import read_json

from api.deps import get_config

router = APIRouter(tags=["events"])

# How often the server samples the disk for changes.
POLL_SECONDS = 0.5
# A keepalive comment after this long without an event (keeps proxies from closing the stream).
KEEPALIVE_SECONDS = 15.0
# Each stream ends after this long; the browser reconnects after RETRY_MS.
STREAM_SECONDS = 55.0
RETRY_MS = 1000
# A change is sent once the files have been stable for one tick (a decision
# rewrites several files), or after this many ticks of continuous change.
MAX_PENDING_TICKS = 4

AREAS = ("project", "config", "state", "pipeline", "screen", "eligibility", "downloads")

_snapshot_lock = threading.Lock()
_snapshot_cache: dict[str, tuple[float, dict]] = {}
_state_cache: dict[str, tuple[Any, dict]] = {}


def _fingerprint(path: Any) -> tuple[int, int, int] | None:
    try:
        st = os.stat(path)
    except (OSError, TypeError, ValueError):
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _digest(value: Any) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _state_sections(state_file: Any) -> dict[str, str]:
    """A digest per block of review_state.json, re-read only when the file changed."""
    key = str(state_file)
    fp = _fingerprint(state_file)
    cached = _state_cache.get(key)
    if cached is not None and cached[0] == fp:
        return cached[1]
    try:
        state = read_json(state_file, default={}, recover_trailing_data=True) if fp else {}
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    own = ("pipeline", "screen", "eligibility")
    sections = {name: _digest(state.get(name)) for name in own}
    sections["state"] = _digest({k: v for k, v in state.items() if k not in own})
    _state_cache[key] = (fp, sections)
    return sections


def _compute_snapshot() -> dict:
    """Fingerprint of every watched file, grouped by area, and a version over all of them."""
    areas: dict[str, Any] = dict.fromkeys(AREAS)
    try:
        config_path = workspace.resolve_config_path()
        areas["project"] = str(config_path)
    except workspace.WorkspaceError as exc:
        config_path = None
        areas["project"] = f"error: {exc}"

    if config_path is not None:
        areas["config"] = _fingerprint(config_path)
        try:
            config = get_config()
        except Exception:  # noqa: BLE001 - an unusable config only means nothing else to watch
            config = None
        if config is not None:
            sections = _state_sections(config.state_file)
            areas["state"] = sections["state"]
            areas["pipeline"] = sections["pipeline"]
            areas["screen"] = (sections["screen"],
                               _fingerprint(config.screen_dir / "screen_results.json"))
            areas["eligibility"] = (sections["eligibility"],
                                    _fingerprint(config.eligibility_dir / "eligibility_results.json"))
            areas["downloads"] = _fingerprint(config.output_dir / "05_pdfs" / "_download_log.json")
    return {"version": _digest(areas), "areas": areas}


def _shared_snapshot() -> dict:
    """The current snapshot, computed at most once per tick for all clients of a workspace."""
    key = str(workspace.workspace_root())
    with _snapshot_lock:
        now = time.monotonic()
        cached = _snapshot_cache.get(key)
        if cached is not None and now - cached[0] < POLL_SECONDS * 0.8:
            return cached[1]
        snapshot = _compute_snapshot()
        _snapshot_cache[key] = (now, snapshot)
        return snapshot


def _changed_areas(old: dict, new: dict) -> list[str]:
    return [a for a in AREAS if old["areas"].get(a) != new["areas"].get(a)]


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.get("/events")
async def events(request: Request):
    """Stream ``{"version", "areas"}`` events whenever shared disk state changes."""

    async def stream():
        loop = asyncio.get_running_loop()
        started = loop.time()
        sent = await asyncio.to_thread(_shared_snapshot)
        yield f"retry: {RETRY_MS}\n" + _event(
            {"version": sent["version"], "areas": ["all"], "initial": True})

        pending: dict | None = None
        pending_ticks = 0
        last_write = loop.time()
        while loop.time() - started < STREAM_SECONDS:
            await asyncio.sleep(POLL_SECONDS)
            if await request.is_disconnected():
                return
            snapshot = await asyncio.to_thread(_shared_snapshot)
            now = loop.time()

            if snapshot["version"] == sent["version"]:
                pending, pending_ticks = None, 0
            elif pending is not None and (snapshot["version"] == pending["version"]
                                          or pending_ticks >= MAX_PENDING_TICKS):
                yield _event({"version": snapshot["version"],
                              "areas": _changed_areas(sent, snapshot)})
                sent, pending, pending_ticks, last_write = snapshot, None, 0, now
                continue
            else:
                pending, pending_ticks = snapshot, pending_ticks + 1

            if now - last_write >= KEEPALIVE_SECONDS:
                # Comment frame keeps proxies from closing an idle connection.
                yield ": keepalive\n\n"
                last_write = now

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (e.g. nginx)
        },
    )
