# PRISMA Review Tool

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Automated systematic literature review following the [PRISMA 2020](https://www.prisma-statement.org/prisma-2020) guidelines ([checklist](https://www.prisma-statement.org/prisma-2020-checklist) | [flow diagram](https://www.prisma-statement.org/prisma-2020-flow-diagram) | [Page et al., 2021](https://doi.org/10.1136/bmj.n71)). Search academic databases, deduplicate results, screen papers with keyword rules, and use AI-assisted screening via any MCP-compatible agent — all from the command line.

## Features

- **Multi-database search**: arXiv, OpenAlex, Semantic Scholar (free, no API keys needed). Optional: Scopus.
- **Automatic deduplication**: DOI matching + fuzzy title matching
- **Two-pass screening**:
  - **Pass 1**: Rule-based keyword screening (automated)
  - **Pass 2**: AI-assisted eligibility screening via MCP (stricter criteria)
- **AI screening via MCP**: Works with Claude Code, OpenAI Codex, GitHub Copilot, Cursor, Windsurf, Amazon Q, Gemini CLI, and any MCP-compatible agent
- **PRISMA flow diagram**: Auto-generated PNG + Markdown with all the numbers
- **Export**: BibTeX (.bib) for LaTeX/Zotero + CSV for Excel

## Quick Start

### 1. Setup

```bash
cd prisma_tool
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.template.yaml config.yaml
```

Edit `config.yaml` with your search queries, date range, and screening keywords. See [docs/CONFIG_GUIDE.md](docs/CONFIG_GUIDE.md) for details.

### 3. Run

```bash
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

### 4. (Optional) AI Screening with Any MCP-Compatible Agent

Set up the MCP server to let AI agents (Claude Code, OpenAI Codex, GitHub Copilot, Cursor, Windsurf, etc.) screen your papers. See [docs/MCP_SETUP.md](docs/MCP_SETUP.md).

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
| [Installation & Setup](wiki/Installation-&-Setup) | Python setup, dependencies, first run |
| [Configuration Guide](wiki/Configuration-Guide) | How to write config.yaml for any topic |
| [Full Workflow Tutorial](wiki/Full-Workflow-Tutorial) | End-to-end walkthrough |
| [MCP & AI Screening](wiki/MCP-&-AI-Screening) | Setup with any MCP agent |
| [CLI Reference](wiki/CLI-Reference) | All commands and options |
| [MCP Tools API Reference](wiki/MCP-Tools-API-Reference) | All 10 MCP tools with params and responses |
| [PRISMA 2020 Compliance](wiki/PRISMA-2020-Compliance) | Checklist mapping, flow diagram alignment |
| [Writing Your Methodology](wiki/Writing-Your-Methodology) | Template for thesis/paper methods section |
| [Troubleshooting & FAQ](wiki/Troubleshooting-&-FAQ) | Common issues and solutions |

Also available in `docs/`:
- [MCP Setup Guide](docs/MCP_SETUP.md) — Quick MCP setup reference
- [Examples](docs/EXAMPLES.md) — Example configs for different research fields

## Roadmap

- **v1.0** (current): CLI + MCP server with two-pass screening
- **v2.0** (planned): Web-based UI/UX with visual screening dashboard, drag-and-drop config builder, and interactive PRISMA flow diagrams

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
- No API keys needed for basic usage (arXiv, OpenAlex, Semantic Scholar are free)
- Optional: Scopus API key for broader coverage
- Optional: Claude Code subscription for AI-assisted screening via MCP

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
