# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-03-31

### Added
- **Multi-project management**: Save, load, and switch between multiple literature review projects
  - Each project gets its own isolated directory under `projects/` with config.yaml + prisma_output/
  - REST API: 8 new endpoints under `/api/projects` (list, create, switch, delete, duplicate, export, import, active)
  - Web UI: New `/projects` page with glass card grid — create, switch, duplicate, delete, export (.zip), import
  - Sidebar: Active project indicator below logo + Projects nav item
  - Dashboard: Shows active project name in header
- **Auto-migration**: On first run, existing root `config.yaml` + `prisma_output/` are automatically copied into `projects/{slug}/` (originals preserved for CLI backward compatibility)
- **Project export/import**: Export any project as a .zip archive, import from .zip to create a new project

### Changed
- `api/deps.py`: Added `get_projects_dir()` and `switch_project()` for project isolation
- `api/main.py`: Startup now checks for active project, auto-migrates if needed, registers projects router
- `api/routes/config_routes.py`: Config path resolves from active project instead of hardcoded root
- `.gitignore`: Added `projects/` (user data)
- API version bumped to 1.2.0

## [1.2.1] - 2026-03-30

### Added
- **Scopus search implementation**: New `scopus_search.py` module using the Elsevier Scopus Search API
  - Searches via TITLE-ABS-KEY with full Boolean query support
  - Handles pagination (25 results per page), rate limiting (429 retry with backoff)
  - Extracts title, authors, abstract, year, DOI, venue, keywords, Scopus ID
  - Gracefully skips when no API key is configured
  - API key from https://dev.elsevier.com (requires institutional access)
  - Uses raw `requests` — no additional dependencies needed

- **Elsevier/ScienceDirect PDF download**: Papers behind Elsevier paywalls can now be downloaded using the Scopus API key with institutional access
  - Uses the Elsevier Article Retrieval API (`/content/article/doi/{doi}`)
  - Tried first in download strategy (before arXiv, Unpaywall, Semantic Scholar)
  - Covers thousands of subscription journals via institutional access
  - No new dependencies — uses `requests`

### Changed
- `runner.py` now routes to `search_scopus` when "scopus" is in the sources list
- `config.template.yaml` updated with Scopus API key instructions
- Download strategy order: Elsevier → arXiv → Unpaywall → Semantic Scholar
- All download callers (CLI, API, MCP) now pass `config.scopus_key` to `download_papers()`

## [1.2.0] - 2026-03-30

### Added
- **Background pipeline execution**: Pipeline (search → dedup → screen) now runs in a background thread instead of blocking the HTTP request
  - New REST endpoints: `POST /api/pipeline/start`, `GET /api/pipeline/progress`, `POST /api/pipeline/stop`
  - Pipeline state persisted to `review_state.json` under `pipeline` key — survives server restarts
  - Cancellation support: stop after current step, preserving completed results
  - Live progress polling from the web dashboard (2-second interval)
- **4 new MCP tools** for pipeline session management (15 total):
  - `start_pipeline` — start the full pipeline in background
  - `get_pipeline_progress` — check current status, step, warnings
  - `stop_pipeline` — request cancellation
  - `start_pipeline_step` — run a single step (search/dedup/screen)
- **Rate limit handling**: Search step detects zero-result sources (e.g., Semantic Scholar rate limiting) and reports them as warnings instead of failing the pipeline
- **Warnings field**: Pipeline progress includes a `warnings` list for non-fatal issues (rate limits, partial results)
- **Session architecture doc**: `docs/SESSION_SYSTEM.md` explaining background execution, state management, MCP/Web UI sharing

### Added (continued)
- **PRISMA 2020 flow diagram component**: Interactive React-rendered diagram matching the official PRISMA 2020 template (Page et al., BMJ 2021)
  - Proper phases: Identification, Screening, Included with blue phase labels and gold header
  - All required PRISMA boxes: Records identified, Records removed before screening, Records screened, Records excluded, Reports sought for retrieval, Reports not retrieved, Reports assessed for eligibility, Reports excluded, Studies included
  - Auto-populates from live stats, updates when pipeline or screening data changes
  - Download PNG button captures the diagram at 3x resolution using html-to-image
- **PDF browser on Downloads page**: View downloaded papers directly in the web app
  - Inline PDF viewer using browser's native PDF viewer in an iframe
  - Filter pills: All, Downloaded, No OA, Failed with counts
  - Paper table with status, title, DOI links, and View button
  - Same-origin PDF proxy via Next.js API route (avoids cross-origin issues)
- **Eligibility filters on All Papers page**: "Eligible: Included" and "Eligible: Excluded" filters
- **Clickable paper titles**: Paper titles on Screening and Eligibility pages link to paper detail
- **Scroll restoration**: Custom ScrollRestoration component saves/restores scroll position for the main content area across all pages
- **URL-persisted pagination**: Page numbers, filters, and batch sizes are synced to URL params and survive back navigation
- **Source reliability info on Settings page**: Each source shows reliability status and rate-limit warnings

### Changed
- Dashboard "Run All" button now launches background pipeline with live progress bar
- PipelineProgress component shows elapsed time, stop button, and warning indicators
- Modal component now awaits async `onConfirm` before closing (fixes race condition)
- MCP server tools count increased from 11 to 15
- PRISMA flow diagram replaced matplotlib PNG with interactive React component
- Default sources changed to OpenAlex only (arXiv and Semantic Scholar disabled due to rate limits)
- Pipeline stepper shows "--" for pending stats and hides stale counts during pipeline runs
- "AI Eligibility" renamed to "Eligibility" (supports both manual and AI screening)
- Stale eligibility data and download logs cleared automatically when pipeline re-runs
- File locks released during network calls (search no longer blocks API for minutes)
- Load More button preserves scroll position on Screening, Eligibility, and All Papers pages
- "Go Back" button on paper detail uses router.back() to return to the originating page

## [1.1.0] - 2026-03-29

### Added
- **PDF download feature**: New `download` CLI command and `download_eligible_papers` MCP tool
  - Downloads open access papers only (legal: arXiv, Unpaywall API, Semantic Scholar)
  - Descriptive filenames: `AuthorYear_ShortTitle.pdf`
  - Download log saved as `_download_log.json`
  - Papers without open access are skipped and logged as "manual download needed"
- `05_pdfs/` output directory for downloaded papers
- `download.py` module with multi-source OA resolution

### Changed
- Updated README with download feature, new CLI command, new MCP tool
- Updated CHANGELOG format

## [1.0.1] - 2026-03-29

### Added
- Threshold tuning guide in wiki Configuration Guide — simulate different `min_include_hits` values before committing
- Detailed exclude keyword tuning strategy in docs

### Changed
- Wiki Configuration Guide expanded with simulation code example and real-world tuning data
- Presentation template updated with actual PRISMA flow numbers

### Fixed
- Screening strategy documentation now reflects the recommended workflow: start broad, simulate thresholds, then tighten

## [1.0.0] - 2026-03-29

### Added
- **Automated multi-database search**: arXiv, OpenAlex, Semantic Scholar
- **Automatic deduplication**: DOI matching + fuzzy title matching (rapidfuzz)
- **Two-pass screening**:
  - Pass 1: Rule-based keyword screening (automated)
  - Pass 2: AI-assisted eligibility screening via MCP
- **MCP server** with 10 tools for AI-assisted screening — works with Claude Code, OpenAI Codex, GitHub Copilot, Cursor, Windsurf, Amazon Q, Google Gemini CLI, JetBrains AI
- **PRISMA 2020 flow diagram** generation (PNG + Markdown) with automation tool exclusion reporting
- **BibTeX + CSV export** for both first-pass and eligibility-screened papers
- **CLI** with 7 commands: search, dedup, screen-rules, report, export, status, run-all
- **Comprehensive documentation**: README, 5 docs, 9-page wiki
- **MIT license** — all dependencies MIT/BSD/Apache 2.0 compatible
- Removed bibtexparser dependency (was LGPLv3) — replaced with pure Python BibTeX writer
