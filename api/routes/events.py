"""Server-Sent Events stream for real-time UI updates.

The API and the MCP server are separate processes that share state only
through disk (``review_state.json`` and ``.active_project``). This endpoint
watches those files server-side and pushes a lightweight "changed" event to
connected browsers, so every screen can refetch on change instead of each one
polling independently. One connection per browser drives all screens.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.deps import get_config, get_projects_dir

router = APIRouter(tags=["events"])

# How often the server samples the disk for changes. Cheap stat() calls.
POLL_SECONDS = 1.0


def _state_signature() -> tuple[int, ...]:
    """Cheap fingerprint of the files other processes mutate."""
    paths = []
    try:
        # Active project resolved fresh, so we follow project switches too.
        paths.append(get_config().state_file)
    except Exception:
        pass
    paths.append(get_projects_dir() / ".active_project")

    sig: list[int] = []
    for p in paths:
        try:
            sig.append(p.stat().st_mtime_ns)
        except OSError:
            sig.append(0)
    return tuple(sig)


@router.get("/events")
async def events(request: Request):
    """Stream `data: {"changed": true}` whenever shared disk state changes."""

    async def stream():
        last: tuple[int, ...] | None = None
        while True:
            if await request.is_disconnected():
                break

            sig = _state_signature()
            if sig != last:
                # First iteration (last is None) emits immediately so the
                # client syncs on connect.
                last = sig
                yield f"data: {json.dumps({'changed': True})}\n\n"
            else:
                # Comment frame keeps proxies from closing an idle connection.
                yield ": keepalive\n\n"

            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (e.g. nginx)
        },
    )
