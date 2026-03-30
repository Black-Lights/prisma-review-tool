# Session System — Background Pipeline Architecture

## Overview

The pipeline (search → dedup → screen) runs in a **background thread** instead of blocking the HTTP request. This enables:

- Non-blocking execution: the web dashboard remains responsive while the pipeline runs
- Live progress updates via polling (2-second interval)
- Cancellation: stop after current step, preserving completed results
- State persistence: pipeline progress survives server restarts
- Shared control: MCP tools and web UI share the same session

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Web UI      │     │  FastAPI      │     │  MCP Server      │
│  (Next.js)   │────▶│  Routes       │     │  (stdio)         │
│              │     │              │     │                  │
│  Polls every │     │  /start      │     │  start_pipeline  │
│  2 seconds   │     │  /progress   │     │  get_progress    │
│              │     │  /stop       │     │  stop_pipeline   │
└──────────────┘     └──────┬───────┘     └────────┬─────────┘
                            │                      │
                            ▼                      ▼
                     ┌──────────────────────────────────┐
                     │       SessionManager (singleton)  │
                     │                                   │
                     │  - Runs steps in threading.Thread │
                     │  - Thread-safe via _lock           │
                     │  - File I/O via _file_lock         │
                     │  - Persists to review_state.json   │
                     └──────────────────────────────────┘
                            │
                            ▼
                     ┌──────────────────────┐
                     │  prisma_review/       │
                     │  (search, dedup,      │
                     │   screen functions)   │
                     └──────────────────────┘
```

## State Management

### In-Memory State

The `SessionManager` holds all progress state in memory for fast reads:

```python
session_id: str        # Unique ID for this run
status: PipelineStatus # idle | running | completed | failed | cancelled
current_step: str      # search | dedup | screen
progress_message: str  # Human-readable status
started_at: str        # ISO 8601 timestamp
finished_at: str       # ISO 8601 timestamp
completed_steps: list  # ["search", "dedup"]
warnings: list         # Non-fatal issues (rate limits, etc.)
error: str             # Stack trace on failure
result: dict           # Step results on completion
```

### Disk Persistence

Pipeline state is written to `review_state.json` under the `pipeline` key at each step transition:

```json
{
  "search": { "total": 2821, ... },
  "dedup": { "remaining": 2686, ... },
  "screen": { "included": 206, ... },
  "pipeline": {
    "status": "running",
    "current_step": "dedup",
    "progress_message": "Removing duplicates...",
    "started_at": "2026-03-30T12:00:00+00:00",
    "completed_steps": ["search"],
    "warnings": [],
    "error": null
  }
}
```

On server restart, if the persisted status is `"running"`, the SessionManager marks it as `"failed"` with the message "Pipeline was interrupted by server restart".

## Thread Safety

Two locks are used:

1. **`_lock`** (threading.Lock) — protects mutable progress fields. Held briefly during reads (`get_progress`) and writes (`_update`).

2. **`_file_lock`** (threading.Lock, shared with FastAPI routes) — protects JSON file I/O. Held during `load_state`/`save_state` and paper file reads/writes.

These locks are never held simultaneously to avoid deadlocks.

## MCP and Web UI Sharing

Both the FastAPI routes and MCP tools access the same `SessionManager` singleton:

- **FastAPI** (api/deps.py): `get_session_manager()` creates the singleton with the shared `_file_lock`
- **MCP** (mcp_server/server.py): `_get_session_manager()` creates its own singleton (different process, but reads the same `review_state.json`)

When both run in the same process (e.g., the API server), they share the exact same instance. When the MCP server runs as a separate process (stdio transport), they share state via `review_state.json` on disk.

## Rate Limit Handling

The search step calls `run_all_searches()` which catches per-source exceptions and returns empty results for failed sources. After search completes, the session checks for zero-result sources and adds warnings:

```
semantic_scholar: returned 0 results (possible rate limiting or API error)
```

Warnings are included in the progress response and displayed in the web UI. The pipeline does NOT fail — it continues with partial results.

## Cancellation Flow

1. User requests cancel via `POST /api/pipeline/stop` or `stop_pipeline()` MCP tool
2. SessionManager sets `_cancel_requested = True` and updates progress message
3. The cancel flag is checked **between steps** (not mid-step)
4. After the current step finishes, the pipeline transitions to `cancelled` status
5. Results from completed steps are preserved

## API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/pipeline/start` | POST | Start full pipeline in background |
| `/api/pipeline/start/{step}` | POST | Start a single step |
| `/api/pipeline/progress` | GET | Current progress (fast, no I/O) |
| `/api/pipeline/stop` | POST | Request cancellation |
| `/api/pipeline/status` | GET | Pipeline state from disk |

### MCP Tools

| Tool | Description |
|------|-------------|
| `start_pipeline()` | Start full pipeline |
| `get_pipeline_progress()` | Current progress |
| `stop_pipeline()` | Request cancellation |
| `start_pipeline_step(step)` | Start single step |

### Progress Response Schema

```json
{
  "session_id": "string | null",
  "status": "idle | running | completed | failed | cancelled",
  "current_step": "search | dedup | screen | null",
  "progress_message": "string | null",
  "started_at": "ISO 8601 | null",
  "finished_at": "ISO 8601 | null",
  "completed_steps": ["string"],
  "warnings": ["string"],
  "error": "string | null",
  "result": "object | null"
}
```
