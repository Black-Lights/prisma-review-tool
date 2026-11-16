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
- **api_keys.openalex_key**: A free OpenAlex API key (recommended: it raises OpenAlex's daily request budget 10 times; see [CONFIG_GUIDE.md](CONFIG_GUIDE.md#api-keys))

This is the CLI-only path, with one review in the root `config.yaml`. The web app (`python start.py`) moves that review into `projects/<name>/` on its first start and makes it the active project; from then on the CLI, the web app and the MCP server all use `projects/<name>/config.yaml`, so edit that one (or use the Settings page).

## 3. Run

```bash
python -m prisma_review run-all
```

## 4. Check Results

```bash
python -m prisma_review status
```

Your outputs are in `prisma_output/04_export/`:
- `included_papers.bib`: Import into Zotero or use in LaTeX
- `included_papers.csv`: Open in Excel
- `prisma_flow.png`: [PRISMA 2020](https://www.prisma-statement.org/prisma-2020) flow diagram

## 5. (Optional) AI Screening

If you have Claude Code, set up the MCP server for AI-powered screening of uncertain papers. See [MCP_SETUP.md](MCP_SETUP.md).
