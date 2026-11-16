# Roadmap: v1.6 to v2.0

Working plan for the next round of development. Each phase ships as its own release, so users get
something usable at every step.

Status key: `[x]` done, `[~]` in progress, `[ ]` not started.

---

## Phase 1: Integrate the community fork (v1.6.0)

Source: https://github.com/walterdemacedorodrigues/prisma-review-tool, 14 commits by
walterdemacedorodrigues and agoshigagoroba. Branch: `integrate/community-fork`.

- [x] Audit the npm changes before running anything (Next.js 16.2.1 to 16.2.6, registry-only
      lockfile, no new install scripts)
- [x] Scan the Python diff for risky calls (no subprocess, eval, file deletion or unexpected hosts)
- [x] Merge with original authorship kept on every commit
- [x] In-depth review in four areas: MCP and config, search layer, pipeline and API, web UI
- [x] Fix what the review finds, as separate commits on top of the merge, then a second
      adversarial review (security and data integrity, PRISMA and search, UX and back-compat)
      and its fixes
- [x] Smoke tests: MCP stdio handshake, API on a copy of a real review, CLI search on a tiny
      query, `npm ci` and `next build`, fresh installs on Python 3.10 to 3.13
- [x] Credit both authors in CHANGELOG and a README acknowledgements section
- [x] Open a PR on Black-Lights/prisma-review-tool that @mentions walterdemacedorodrigues and
      merges their PR #3 (its commits are part of the branch)
- [x] Tag and release v1.6.0

## Phase 2: Packaging and one version number (v1.7.0)

In 1.6.0 the API reads its version from `prisma_review/__init__.py`, but the web sidebar keeps its
own copy and `web/package.json` says 0.1.0. There is no `pyproject.toml`, and the only install
path is clone + venv + hand-edited absolute paths.

- [ ] `pyproject.toml` with a single version in `prisma_review/__init__.py`; the API and the web
      About modal read it from there (`GET /api/version`)
- [ ] Console scripts: `prisma-review` (CLI), `prisma-review-mcp` (MCP server)
- [ ] Optional extras: `[web]` (fastapi, uvicorn), `[dev]` (pytest)
- [ ] Workspace separate from the install directory: `PRISMA_HOME` env var / `--workspace` flag,
      defaulting to the current directory. Required before uvx or pip installs can work, because
      projects and config cannot live inside site-packages
- [ ] Move `SessionManager` from `api/session.py` into `prisma_review/` so the MCP server no longer
      imports the web backend
- [x] Pytest suite (419 tests in 1.6.0) and web tests (`npm test`)
- [ ] GitHub Actions: tests on push; build on tag
- [ ] Decide: publish to PyPI (enables `uvx prisma-review-mcp` and update-on-restart)

## Phase 3: Update notifications (v1.7.x)

- [ ] `prisma_review/update_check.py`: reads the latest GitHub release, caches the answer for 24h in
      the user cache dir, 2s timeout, never raises, `PRISMA_NO_UPDATE_CHECK=1` turns it off.
      Validates the remote version string strictly (digits and dots) before using it, because it
      ends up in the agent's context
- [ ] MCP server: notice in the server `instructions`, a `get_version` tool, and a one-line
      `update_available` field in `get_screening_stats`
- [ ] CLI: one stderr line on `status` and `run-all`
- [ ] Web: badge in the About modal

## Phase 4: Claude Code plugin and skill (v1.8.0)

- [ ] `.claude-plugin/marketplace.json` at the repo root so the repo is its own marketplace
- [ ] Plugin: `plugin.json`, `.mcp.json`, `skills/prisma-review/SKILL.md`, SessionStart hook that
      prints the update notice
- [ ] Install becomes `/plugin marketplace add Black-Lights/prisma-review-tool` then
      `/plugin install prisma-review`; updates through `/plugin update` or auto-update
- [ ] `SKILL.md` follows the open standard so it also works in Codex, Cursor and Copilot;
      `docs/MCP_SETUP.md` updated for each
- [ ] Optional: list the skill on Agensi

## Phase 5: Agentic layer (v2.0.0)

- [ ] Screening criteria stored per project (pass 1 and pass 2, versioned) instead of living in
      the chat prompt
- [ ] MCP resources: `prisma://config`, `prisma://criteria`, `prisma://flow`
- [ ] MCP prompts: `setup_review`, `screen_batch`, `eligibility_batch`
- [x] Server `instructions` that describe the workflow order (1.6.0)
- [ ] Typed batch tools (a list of objects, not a JSON string); keep the string form for one release
- [ ] Decision audit log (JSONL): paper, pass, decision, reason, reviewer, criteria version, time
- [x] Cross-process file lock for files written by both the web app and the MCP server (1.6.0)
- [ ] Two-reviewer mode: two agents screen independently, conflicts are listed for adjudication,
      Cohen's kappa in the report (PRISMA recommends dual screening)
- [x] Remove thesis-specific examples from tool docstrings (1.6.0)
- [ ] Search-source registry so a new database is one file instead of edits in five places
- [ ] Visual pipeline editor. Prior art: LucasHLoli's prototype in PR #4 (a React Flow graph
      editor in the web app and a LangGraph agent graph), withdrawn by its author in August 2026
      to continue on their fork. Worth revisiting once the agent layer above exists
