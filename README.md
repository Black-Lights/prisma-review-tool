# PRISMA Review Tool

[![Version: 1.4.2](https://img.shields.io/badge/version-1.4.2-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-green.svg)](https://www.python.org)

Automated systematic literature review following the [PRISMA 2020](https://www.prisma-statement.org/prisma-2020) guidelines ([checklist](https://www.prisma-statement.org/prisma-2020-checklist) | [flow diagram](https://www.prisma-statement.org/prisma-2020-flow-diagram) | [Page et al., 2021](https://doi.org/10.1136/bmj.n71)). Search academic databases, deduplicate results, screen papers with keyword rules, and use AI-assisted screening via any MCP-compatible agent — all from the command line.

## Features

- **Multi-database search**: arXiv, OpenAlex, Semantic Scholar (free, no API keys needed). Optional: Scopus.
- **Automatic deduplication**: DOI matching + fuzzy title matching
- **Two-pass screening**:
  - **Pass 1**: Rule-based keyword screening (automated)
  - **Pass 2**: AI-assisted eligibility screening via MCP (stricter criteria)
- **AI screening via MCP**: Works with Claude Code, OpenAI Codex, GitHub Copilot, Cursor, Windsurf, Amazon Q, Gemini CLI, and any MCP-compatible agent
- **PRISMA 2020 flow diagram**: Interactive diagram matching the official template (Page et al., 2021) with download-as-PNG
- **Flexible export**: CSV with Elsevier-style field picker + BibTeX — exports only filtered papers, choose which columns to include
- **PDF download & viewer**: Download papers via Elsevier (institutional), arXiv, Unpaywall, Semantic Scholar — view inline in web app
- **Background pipeline**: Run search → dedup → screen in background with live progress, cancellation, and rate limit handling
- **Multi-project management**: Save, switch, duplicate, export/import projects — each with isolated config + data
- **Web dashboard**: Real-time pipeline stepper, stat cards, PRISMA flow diagram, PDF browser, eligibility filters

## Quick Start

### One-Command Launch (Web App)

```bash
cd prisma_tool
python start.py
```

That's it. On first run it will:
1. Create a Python virtual environment and install all dependencies
2. Install Node.js packages for the web frontend
3. Create `config.yaml` from the template (if missing)
4. Start the API server and web app on available ports
5. Open the dashboard in your browser

Press **Ctrl+C** to stop — it kills both the backend and frontend automatically.

```bash
# Options
python start.py --install     # Force reinstall all dependencies
python start.py --port 9000   # Custom backend port (frontend = port + 1000)
python start.py --no-browser  # Don't auto-open browser
python start.py --cli         # CLI mode only (no web app)
```

> **Requirements:** Python 3.10+ and Node.js 18+ must be installed.

### Configure

Edit `config.yaml` with your search queries, date range, and screening keywords — or use the **Settings** page in the web app. See [docs/CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md) for details.

### CLI Usage (Without Web App)

If you prefer the command line:

```bash
python start.py --cli     # Sets up venv, shows CLI commands

# Then activate and run:
# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

# Full pipeline
python -m prisma_review run-all

# Or step by step
python -m prisma_review search        # Search databases
python -m prisma_review dedup         # Remove duplicates
python -m prisma_review screen-rules  # Keyword screening
python -m prisma_review report        # Generate PRISMA diagram
python -m prisma_review export        # Export .bib + .csv

# Check progress
python -m prisma_review status
```

### (Optional) AI Screening with Any MCP-Compatible Agent

Set up the MCP server to let AI agents (Claude Code, OpenAI Codex, GitHub Copilot, Cursor, Windsurf, etc.) screen your papers. See [docs/MCP_SETUP.md](docs/MCP_SETUP.md).

### Web App Features

The web dashboard provides:
- **Dashboard** — Real-time pipeline stepper, stat cards, interactive PRISMA 2020 flow diagram
- **Screening** — Review papers with include/exclude/maybe decisions
- **Eligibility** — Second-pass AI-assisted screening for stricter criteria
- **All Papers** — Paginated, filterable, searchable table with field-picker export (CSV, BibTeX) — exports only filtered papers
- **Downloads** — PDF viewer for downloaded papers (Elsevier, arXiv, Unpaywall)
- **Settings** — Edit config, search queries, keywords, API keys from the browser
- **Projects** — Create, switch, duplicate, import/export literature review projects
- **MCP Settings** — View connection instructions for AI agents

## Two-Pass Screening Workflow

Broad search queries in emerging fields often return hundreds of papers. A single keyword screening pass is too coarse — you need a second, stricter pass.

```
Pass 1 (Keyword Rules)          Pass 2 (AI Eligibility)
━━━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━━━━━━━━━━━━━━
1,600 records found             570 first-pass included
  → 57 duplicates removed         → AI reads each abstract
  → 973 excluded by rules         → Applies strict criteria
  → 570 included                  → ~50-80 final papers
```

**Pass 1** uses configurable keyword rules to quickly eliminate obviously irrelevant papers. Papers matching ≥N include keywords (and no exclude keywords) are included; the rest are excluded or flagged as "maybe" for AI review.

**Pass 2** uses Claude (via MCP) to read each first-pass included paper's abstract and apply domain-specific eligibility criteria, narrowing to only the most relevant studies for full-text review.

## CLI Reference

| Command | Description |
|---------|-------------|
| `search` | Search all configured databases with your queries |
| `dedup` | Remove duplicate papers (DOI + fuzzy title) |
| `screen-rules` | Apply keyword-based screening rules |
| `report` | Generate PRISMA flow diagram (PNG + Markdown) |
| `export` | Export included papers to .bib and .csv |
| `download` | Download open access PDFs for eligible papers |
| `status` | Show current pipeline state and counts |
| `run-all` | Run the full pipeline end-to-end |

**Options:**
- `--config PATH` — Path to config.yaml (default: `./config.yaml`)
- `--force` — Re-run a step even if output already exists

## MCP Tools Reference

### First-Pass Screening
| Tool | Description |
|------|-------------|
| `get_screening_stats` | Current pipeline statistics |
| `get_papers_to_screen` | Batch of "maybe" papers for AI review |
| `get_paper_details` | Full details of a specific paper |
| `screen_paper` | Save one screening decision |
| `batch_screen_papers` | Save multiple screening decisions |
| `search_in_papers` | Keyword search across collected papers |

### Second-Pass Eligibility
| Tool | Description |
|------|-------------|
| `get_papers_for_eligibility` | Batch of first-pass included papers for stricter review |
| `eligibility_screen_paper` | Save one eligibility decision |
| `batch_eligibility_screen` | Save multiple eligibility decisions |

### Reporting
| Tool | Description |
|------|-------------|
| `generate_report` | Generate PRISMA diagram + export .bib/.csv |
| `download_eligible_papers` | Download PDFs (Elsevier, arXiv, Unpaywall, S2) |

### Pipeline Management
| Tool | Description |
|------|-------------|
| `start_pipeline` | Start full pipeline in background (search → dedup → screen) |
| `get_pipeline_progress` | Check pipeline status, current step, warnings |
| `stop_pipeline` | Cancel running pipeline (stops after current step) |
| `start_pipeline_step` | Run a single step (search, dedup, or screen) |

## Multi-Project Support

Each literature review is stored as an isolated project with its own config and data:

```
projects/
├── gfm-agriculture/
│   ├── config.yaml
│   └── prisma_output/
├── dl-medical/
│   ├── config.yaml
│   └── prisma_output/
└── .active_project              # tracks which project is loaded
```

- **Switch projects** without losing data — each project has its own pipeline state
- **Auto-migration**: Existing `config.yaml` + `prisma_output/` are automatically copied into `projects/` on first run (originals preserved for CLI)
- **Export/Import**: Share projects as `.zip` files
- **Duplicate**: Clone a project to start a new review from the same config

Manage projects via the web UI (`/projects`) or REST API (`/api/projects`).

## Output Files

```
prisma_output/
├── 01_search/all_records.json           # All papers found (raw)
├── 02_dedup/
│   ├── deduplicated.json                # Unique papers
│   └── duplicates_log.csv               # Which papers were merged
├── 03_screen/
│   ├── screen_results.json              # All papers with decisions
│   ├── included.json                    # First-pass included papers
│   ├── excluded.json                    # Papers excluded
│   └── maybe.json                       # Papers needing manual review
├── 03b_eligibility/
│   ├── eligibility_results.json         # All eligibility decisions
│   ├── eligible_included.json           # Final included papers
│   └── eligible_excluded.json           # Excluded in second pass
├── 04_export/
│   ├── prisma_flow.md                   # PRISMA diagram (Markdown)
│   ├── prisma_flow.png                  # PRISMA diagram (image)
│   ├── included_papers.bib              # First-pass BibTeX
│   ├── included_papers.csv              # First-pass CSV
│   ├── eligible_papers.bib              # Final BibTeX (after eligibility)
│   └── eligible_papers.csv              # Final CSV (after eligibility)
├── 05_pdfs/
│   ├── Author2024_Paper_Title.pdf       # Downloaded open access PDFs
│   └── _download_log.json              # Log of download results
└── review_state.json                    # Pipeline state + counts
```

## Comparison with Existing Tools

Only [2% of systematic review tools](https://doi.org/10.1016/j.jclinepi.2021.10.006) attempt full-process automation. Most focus on one stage.

| Feature | prisma_tool | ASReview | Rayyan | Otto-SR | DistillerSR |
|---------|-------------|----------|--------|---------|-------------|
| Automated search | **Yes** | No | No | No | No |
| Deduplication | Yes | No | Yes | No | Yes |
| Screening | Rule + AI (MCP) | Active learning | Manual + AI | LLM (GPT-4) | AI-assisted |
| Two-pass screening | **Yes** | No | No | No | No |
| PRISMA diagram | Auto-generated | No | Plugin | No | Yes |
| Full pipeline | **Yes** | No | No | Partial | No |
| Open-source | MIT | Apache 2.0 | No | Research | No |
| Cost | Free | Free | Freemium | Research | $$$ |

## Documentation

**Quick start:** See [docs/QUICKSTART.md](docs/QUICKSTART.md)

**Full documentation:** See the [Wiki](https://github.com/Black-Lights/prisma-review-tool/wiki) or browse the [`wiki/`](wiki/) folder:

| Guide | Description |
|-------|-------------|
| [Installation & Setup](wiki/Installation-and-Setup.md) | Python setup, dependencies, first run |
| [Configuration Guide](wiki/Configuration-Guide.md) | How to write config.yaml for any topic |
| [Full Workflow Tutorial](wiki/Full-Workflow-Tutorial.md) | End-to-end walkthrough |
| [MCP & AI Screening](wiki/MCP-and-AI-Screening.md) | Setup with any MCP agent |
| [CLI Reference](wiki/CLI-Reference.md) | All commands and options |
| [MCP Tools API Reference](wiki/MCP-Tools-API-Reference.md) | All 15 MCP tools with params and responses |
| [PRISMA 2020 Compliance](wiki/PRISMA-2020-Compliance.md) | Checklist mapping, flow diagram alignment |
| [Writing Your Methodology](wiki/Writing-Your-Methodology.md) | Template for thesis/paper methods section |
| [Troubleshooting & FAQ](wiki/Troubleshooting-and-FAQ.md) | Common issues and solutions |

Also available in `docs/`:
- [MCP Setup Guide](docs/MCP_SETUP.md) — Quick MCP setup reference
- [Session System](docs/SESSION_SYSTEM.md) — Background pipeline architecture
- [Examples](docs/EXAMPLES.md) — Example configs for different research fields

## Roadmap

- **v1.0**: CLI + MCP server with two-pass screening
- **v1.4** (current): Elsevier-style export with field picker, per-project filter persistence, expanded tutorial
- **v1.3**: One-command launcher, web dashboard, background pipeline, multi-project management, 15 MCP tools
- **v2.0** (planned): Desktop app (Tauri), drag-and-drop config builder, multi-user support

## How to Cite

If you use this tool in your research, please cite:

```
@software{prisma_tool,
  author = {Mughees, Mohammad Ammar},
  title = {PRISMA Review Tool: AI-Assisted Systematic Literature Review},
  year = {2026},
  url = {https://github.com/Black-Lights/prisma-review-tool},
  license = {MIT}
}
```

## Requirements

- Python 3.10+
- Node.js 18+ (for the web app; not needed for CLI-only usage)
- No API keys needed for basic usage (OpenAlex is free and recommended)
- Optional: Scopus API key for broader coverage (get from [dev.elsevier.com](https://dev.elsevier.com), requires institutional access)
- Optional: arXiv and Semantic Scholar (free but have aggressive rate limits)
- Optional: Claude Code subscription for AI-assisted screening via MCP

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
