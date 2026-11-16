# Guide for AI coding agents

PRISMA Review Tool: a Python package for PRISMA 2020 systematic literature reviews, with a CLI, an MCP server (stdio), a FastAPI backend and a Next.js web app. Read `CONTRIBUTING.md` for the general workflow and `docs/` for user-facing behaviour.

## Layout

| Path | What it holds |
|------|---------------|
| `prisma_review/` | The core package. `search/` (one backend per database, `runner.py`, `query_plan.py`, `filters.py`, `http.py`), `dedup.py`, `screen.py` (keyword rules, decisions, rescreen), `pipeline.py` (steps, run ownership), `stats.py` (`compute_flow`, the only source of the PRISMA numbers), `diagram.py`, `workspace.py` (which config is in use), `storage.py` (atomic writes, locks), `config.py`, `cli.py` |
| `mcp_server/server.py`, `run_mcp.py` | The MCP server (FastMCP over stdio, `mcp>=1.30,<2`) |
| `api/` | FastAPI backend: `main.py` (CORS, Host check), `routes/`, `session.py` (background pipeline runs) |
| `web/` | Next.js app; `src/lib/` holds the logic that `web/tests/` covers |
| `tests/` | pytest; `conftest.py` builds a throw-away workspace through `PRISMA_WORKSPACE` |
| `docs/`, `wiki/` | User documentation; keep them in step with behaviour changes |

## Checks before you commit

- Python: create `.venv`, `pip install -r requirements.txt -r api/requirements.txt -r requirements-dev.txt`, then `python -m pytest -q -p no:cacheprovider` from the repo root.
- Web: `cd web && npm ci && npm test && npx next build`.
- MCP smoke: start `run_mcp.py` with the `mcp` stdio client against a temporary workspace (`PRISMA_WORKSPACE`, or `PRISMA_CONFIG` for one config), list the tools and call a few. The stdio client forwards only a few whitelisted environment variables, so pass `env` explicitly. Every tool must return valid JSON and nothing may reach stdout.

## Rules

- **stdout belongs to MCP.** The MCP server speaks JSON-RPC on stdout, so nothing it runs may print there. Progress and diagnostics go to stderr: the search backends and `download.py` rebind `print` to stderr, and only `cli.py` (which the server never calls) prints to stdout. `tests/test_search_stdout.py` and `tests/test_core_mcp_stdio.py` guard this.
- **Atomic writes, one lock.** Write project files through `prisma_review.storage` (`atomic_write_json`, `atomic_write_text`, `atomic_write_yaml`). Every read-modify-write of a project file happens under `project_lock(output_dir)`; change `review_state.json` with `update_state`. The web API, the MCP server and the CLI can run at the same time on the same project.
- **One writer per result.** Screening results go through `screen.write_screen_results` / `apply_screen_decisions` / `apply_eligibility_decisions`, searches through `pipeline.search_step`, dedup through `pipeline.dedup_step`. A pipeline run is claimed on disk (`api.session.SessionManager`, or `pipeline.claimed_run` for the CLI and the synchronous endpoints); anything that would change results refuses while `pipeline.active_run()` reports a live run.
- **One review at a time.** Resolve the config with `workspace.resolve()` / `resolve_config_path()` (`PRISMA_CONFIG`, then `projects/.active_project`, then a root `config.yaml` only when no project exists). Never fall back silently to another project.
- **PRISMA numbers come from `stats.compute_flow`.** The API, the diagrams, the CLI, the MCP tools and the web app show its numbers as they are; do not recompute them elsewhere.
- **Secrets.** Never commit `config.yaml`, `config.*.yaml`, `projects/`, `prisma_output/` or `.mcp.json` (they hold API keys and personal review data; `.gitignore` covers them). API keys and the contact email must never appear in error text, warnings, logs, `search_log.json` or URLs (use `search.http.redact` and `error_text`). `GET /api/config` masks keys as `********`, and project exports blank them.
- **Local only.** The API binds to 127.0.0.1 and answers only to local `Host` headers; keep it that way unless a user opts in (`PRISMA_ALLOWED_HOSTS`, `PRISMA_CORS_ORIGINS`, `start.py --host`).
- **Tests first.** Reproduce a bug in `tests/` before fixing it. Live API calls in tests are not allowed; stub `search.http._send` or the backend functions.
- Docs and commit messages: plain sentences, Conventional Commits (`fix(scope): ...`), no em dash characters.
