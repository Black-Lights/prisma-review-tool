# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### Changed
- Dashboard "Run All" button now launches background pipeline with live progress bar
- PipelineProgress component shows elapsed time, stop button, and warning indicators
- Modal component now awaits async `onConfirm` before closing (fixes race condition)
- MCP server tools count increased from 11 to 15

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
