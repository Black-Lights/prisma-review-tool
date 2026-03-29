# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
