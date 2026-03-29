# Quick Start Guide

Get your PRISMA literature review running in 5 minutes.

## 1. Install

```bash
cd prisma_tool
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

## 2. Configure

```bash
cp config.template.yaml config.yaml
```

Open `config.yaml` and change:
- **project.name**: Your review title
- **search.queries**: Your search terms (use Boolean AND/OR)
- **screening.rules**: Your include/exclude keywords

## 3. Run

```bash
python -m prisma_review run-all
```

## 4. Check Results

```bash
python -m prisma_review status
```

Your outputs are in `prisma_output/04_export/`:
- `included_papers.bib` — Import into Zotero or use in LaTeX
- `included_papers.csv` — Open in Excel
- `prisma_flow.png` — [PRISMA 2020](https://www.prisma-statement.org/prisma-2020) flow diagram

## 5. (Optional) AI Screening

If you have Claude Code, set up the MCP server for AI-powered screening of uncertain papers. See [MCP_SETUP.md](MCP_SETUP.md).
