"""FastAPI backend for PRISMA Review Tool.

Wraps the prisma_review module as a REST API.
Run with: uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import os
import re
import sys
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse

# Ensure prisma_review is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from prisma_review import __version__, workspace
from api.deps import init_config
from api.routes import papers, pipeline, reports, config_routes, projects, events


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the active config on startup, first moving a root-only install into projects/."""
    try:
        if workspace.pinned_config_path() is None:
            workspace.migrate_root_to_projects()
        init_config()
    except Exception as exc:
        # Keep serving: config-dependent endpoints answer 409 with the reason,
        # and the Projects page can still switch to or create a project.
        print(f"Warning: no usable config at startup: {exc}", file=sys.stderr)
    yield


app = FastAPI(
    title="PRISMA Review Tool API",
    description="REST API for PRISMA 2020 systematic literature reviews",
    version=__version__,
    lifespan=lifespan,
)


# ── Origins allowed to call the API from a browser ─────────────────────
# The API has no authentication and reads/writes local review files, so only
# the local web app may call it from a browser: the Next.js dev default
# (port 3000), the port start.py picks (the first free port in
# [backend + 1000, backend + 2000)), the API's own pages (/docs), plus any
# origins listed in PRISMA_CORS_ORIGINS (comma-separated).

DEFAULT_WEB_PORT = 3000
_LOCAL_ORIGIN_RE = re.compile(r"http://(?:localhost|127\.0\.0\.1|\[::1\]):(\d+)")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_server_port: ContextVar[int | None] = ContextVar("_server_port", default=None)


def _configured_origins() -> set[str]:
    raw = os.environ.get("PRISMA_CORS_ORIGINS", "")
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


def origin_allowed(origin: str, server_port: int | None) -> bool:
    """Whether a browser page at ``origin`` may call this API (served on ``server_port``)."""
    origin = origin.rstrip("/")
    if origin in _configured_origins():
        return True
    match = _LOCAL_ORIGIN_RE.fullmatch(origin)
    if not match:
        return False
    port = int(match.group(1))
    if port == DEFAULT_WEB_PORT:
        return True
    return server_port is not None and (
        port == server_port or server_port + 1000 <= port < server_port + 2000
    )


class LocalOriginMiddleware(CORSMiddleware):
    """CORS for the local web app only, and no state changes from other origins.

    CORS only stops a foreign page from reading responses; a cross-site form
    post or a no-cors fetch still reaches the endpoint. So a request that can
    change state (anything but GET/HEAD/OPTIONS) carrying a foreign Origin is
    refused with 403. Requests without an Origin (curl, scripts) are unaffected.
    """

    def __init__(self, app) -> None:
        super().__init__(app, allow_origins=(), allow_methods=["*"], allow_headers=["*"])

    def is_allowed_origin(self, origin: str) -> bool:
        return origin_allowed(origin, _server_port.get())

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return
        server = scope.get("server")
        token = _server_port.set(server[1] if server else None)
        try:
            origin = Headers(scope=scope).get("origin")
            if origin is not None and scope["method"] not in _SAFE_METHODS \
                    and not self.is_allowed_origin(origin):
                response = PlainTextResponse("Origin not allowed", status_code=403)
                await response(scope, receive, send)
                return
            await super().__call__(scope, receive, send)
        finally:
            _server_port.reset(token)


app.add_middleware(LocalOriginMiddleware)

app.include_router(reports.router, prefix="/api")
app.include_router(papers.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(config_routes.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(events.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
