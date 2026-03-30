# MCP Setup Guide — AI Screening with Any MCP-Compatible Agent

## What is MCP?

MCP (Model Context Protocol) is an open standard (now under the Linux Foundation) that lets AI agents use external tools. Our MCP server exposes your literature review data so any MCP-compatible AI can read papers, make screening decisions, and generate reports.

## Supported Agents

The prisma_tool MCP server works with **any agent that supports the MCP protocol**:

| Agent | Config Location | Status |
|-------|----------------|--------|
| **Claude Code** | `.mcp.json` (project) or `~/.claude/settings.json` | Fully tested |
| **OpenAI Codex CLI** | `~/.codex/config.toml` | Compatible |
| **GitHub Copilot (VS Code)** | `.vscode/mcp.json` | Compatible |
| **Cursor** | `~/.cursor/mcp.json` | Compatible |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | Compatible |
| **Amazon Q Developer** | `~/.aws/amazonq/mcp.json` | Compatible |
| **Google Gemini CLI** | `settings.json` | Compatible |
| **JetBrains AI** | IDE settings UI | Compatible |

Our server uses **stdio transport** (the most universal), so it works everywhere.

## Setup

### 1. MCP Server Configuration

The server config is the same JSON structure for most agents. Copy the example and edit paths:

```bash
cp .mcp.json.example <your-agent-config-location>
```

The config format:

```json
{
  "mcpServers": {
    "prisma-review": {
      "command": "<path-to-prisma_tool>/.venv/bin/python",
      "args": ["run_mcp.py"],
      "cwd": "<path-to-prisma_tool>"
    }
  }
}
```

> **Windows users**: Use `.venv/Scripts/python.exe` instead of `.venv/bin/python`. Use forward slashes in paths.

### Agent-Specific Setup

**Claude Code** — Copy to project root as `.mcp.json` or add to `~/.claude/settings.json`

**OpenAI Codex CLI** — Add to `~/.codex/config.toml`:
```toml
[mcp_servers.prisma-review]
command = "<path-to-prisma_tool>/.venv/bin/python"
args = ["run_mcp.py"]
cwd = "<path-to-prisma_tool>"
```

**GitHub Copilot / VS Code** — Add to `.vscode/mcp.json` in your workspace

**Cursor** — Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project)

**Windsurf** — Add to `~/.codeium/windsurf/mcp_config.json`

**Amazon Q** — Add to `~/.aws/amazonq/mcp.json`

### 2. Restart Your Agent

After adding the config, restart the agent. The MCP server starts automatically when the agent needs it.

### 3. Verify

Ask your AI agent: "Use the prisma-review tools to check screening stats."

The agent should call `get_screening_stats` and show you the current pipeline state.

## Available MCP Tools

### First-Pass Screening (keyword rules + AI review of "maybe" papers)

| Tool | What it does |
|------|--------------|
| `get_screening_stats` | Shows total, included, excluded, maybe counts |
| `get_papers_to_screen` | Returns a batch of "maybe" papers with titles and abstracts |
| `get_paper_details` | Full details of a specific paper |
| `screen_paper` | Save a decision for one paper |
| `batch_screen_papers` | Save decisions for multiple papers at once |
| `search_in_papers` | Search within collected papers by keyword |

### Second-Pass Eligibility Screening (stricter AI-assisted review)

| Tool | What it does |
|------|--------------|
| `get_papers_for_eligibility` | Returns first-pass included papers that need eligibility review |
| `eligibility_screen_paper` | Save an eligibility decision for one paper |
| `batch_eligibility_screen` | Save eligibility decisions for multiple papers at once |

### Reporting

| Tool | What it does |
|------|--------------|
| `generate_report` | Create PRISMA diagram + export .bib/.csv for both passes |
| `download_eligible_papers` | Download open access PDFs (arXiv, Unpaywall, S2) |

### Pipeline Management

| Tool | What it does |
|------|--------------|
| `start_pipeline` | Start full pipeline in background (search → dedup → screen) |
| `get_pipeline_progress` | Check pipeline status, current step, and warnings |
| `stop_pipeline` | Cancel running pipeline (stops after current step) |
| `start_pipeline_step` | Run a single step (search, dedup, or screen) in background |

## Two-Pass Screening Workflow

### Why two passes?

Broad search queries often return hundreds of "included" papers after the first keyword screening — too many for a focused review. The second pass applies stricter, topic-specific criteria using AI.

### How it works

**Pass 1 (keyword rules):** Automated screening based on include/exclude keywords. Produces include/exclude/maybe decisions.

**Pass 1b (AI review of "maybe"):** Claude reviews papers that didn't clearly match keyword rules.

**Pass 2 (eligibility):** Claude applies stricter criteria to all first-pass included papers, narrowing to only the most relevant studies.

### Step-by-step

```
1. Run CLI pipeline:           python -m prisma_review run-all
2. Ask Claude to screen:       "Screen my 'maybe' papers about [topic]"
3. Ask Claude for eligibility:  "Do eligibility screening on included papers.
                                 Only include papers directly about [specific criteria]."
4. Generate final report:       "Generate the PRISMA report"
```

## Troubleshooting

**MCP server not found**: Check that the paths in your `.mcp.json` are correct and use forward slashes.

**Config file not found**: The MCP server looks for `config.yaml` relative to the `prisma_tool` directory. Make sure you've run `cp config.template.yaml config.yaml`.

**No papers to screen**: Make sure you ran `python -m prisma_review screen-rules` first. The MCP server reads from the output files.

**Permission errors**: Make sure the venv Python path is correct and the `.venv` exists.
