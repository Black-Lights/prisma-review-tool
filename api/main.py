"""FastAPI backend for PRISMA Review Tool.

Wraps the prisma_review module as a REST API.
Run with: uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure prisma_review is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.deps import init_config
from api.routes import papers, pipeline, reports, config_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize config on startup."""
    init_config()
    yield


app = FastAPI(
    title="PRISMA Review Tool API",
    description="REST API for PRISMA 2020 systematic literature reviews",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(config_routes.router, prefix="/api")


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
