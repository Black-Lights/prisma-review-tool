# Contributing to prisma_tool

Thanks for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/<your-username>/prisma_tool.git
cd prisma_tool
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## Adding a New Search Source

1. Create `prisma_review/search/<source>_search.py` following the pattern in `arxiv_search.py`
2. Implement a function that returns `list[Paper]`
3. Register it in `prisma_review/search/runner.py`

## Adding a New MCP Tool

1. Add your tool function in `mcp_server/server.py` with the `@mcp.tool()` decorator
2. Follow the existing patterns for loading config, papers, and updating state
3. Update `docs/MCP_SETUP.md` with the new tool

## Pull Requests

1. Fork the repo and create a feature branch
2. Make your changes with clear commit messages
3. Test locally with `python -m prisma_review status`
4. Open a PR with a description of what changed and why

## Reporting Issues

Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your Python version and OS
