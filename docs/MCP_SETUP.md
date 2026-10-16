# MCP Setup Guide: AI Screening with Any MCP-Compatible Agent

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

To tie the agent to one review no matter which project the web app has active, add an `env` block with `PRISMA_CONFIG` (see [Which review the server works on](#which-review-the-server-works-on)):

```json
{
  "mcpServers": {
    "prisma-review": {
      "command": "<path-to-prisma_tool>/.venv/bin/python",
      "args": ["run_mcp.py"],
      "cwd": "<path-to-prisma_tool>",
      "env": { "PRISMA_CONFIG": "<path-to-prisma_tool>/projects/<project-name>/config.yaml" }
    }
  }
}
```

### Agent-Specific Setup

**Claude Code**: Copy to project root as `.mcp.json` or add to `~/.claude/settings.json`

**OpenAI Codex CLI**: Add to `~/.codex/config.toml`:
```toml
[mcp_servers.prisma-review]
command = "<path-to-prisma_tool>/.venv/bin/python"
args = ["run_mcp.py"]
cwd = "<path-to-prisma_tool>"
# Optional: pin one review
# env = { PRISMA_CONFIG = "<path-to-prisma_tool>/projects/<project-name>/config.yaml" }
```

**GitHub Copilot / VS Code**: Add to `.vscode/mcp.json` in your workspace

**Cursor**: Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project)

**Windsurf**: Add to `~/.codeium/windsurf/mcp_config.json`

**Amazon Q**: Add to `~/.aws/amazonq/mcp.json`

### 2. Restart Your Agent

After adding the config, restart the agent. The MCP server starts automatically when the agent needs it.

### 3. Verify

Ask your AI agent: "Use the prisma-review tools to show the review config."

The agent should call `get_review_config` and show you which project and config file the server uses, whether the config is ready, and any warnings.

## Which review the server works on

Every tool acts on one review project. The server picks its `config.yaml` in this order:

1. **`PRISMA_CONFIG`** environment variable: a path to a config file (absolute, or relative to the server's working directory). Set it in the agent's MCP config to pin one review.
2. **The active project**: `projects/.active_project` names a folder in `projects/`. This is the same marker the web app's project switcher writes, so without a pin the agent follows the project you select in the web app.
3. **The root `config.yaml`**: only when there is no `projects/.active_project` at all (an install that never created a project).

If `projects/.active_project` names a project that does not exist (or is not a valid project folder name), every tool returns an error saying so instead of quietly using another config. Fix it with `list_projects` and `switch_project`, or in the web app's Projects page.

What the server does to make this visible:

- At startup it writes one line to stderr with the tool version, the project and the config path (plus warnings such as a missing OpenAlex key). Your agent's MCP log shows it.
- Every tool that changes something returns `project`, `project_name` and `config_path`, so you can see which review was touched.
- `switch_project` and `create_project` (with `switch=true`) are refused while a pipeline is running in the server, and while `PRISMA_CONFIG` pins the config.
- `create_project` on an install that only has a root `config.yaml` first copies that review into `projects/` so it stays reachable.

Advanced: `PRISMA_WORKSPACE` points the tool at a different folder holding `config.yaml` and `projects/` (default: the install folder).

## Available MCP Tools

Every tool returns JSON. Failures come back as `{"error": "..."}`, never as a crash.

### Configuration and Projects

| Tool | What it does |
|------|--------------|
| `get_review_config` | Shows the project, config path, how it was chosen, queries, screening rules, filters, `ready`/`problems`, `warnings`, and per-source `query_warnings` and `filter_warnings`. Call this first. |
| `set_review_config` | Changes only the fields you pass (sources, dates, queries, keywords, filters). Validates everything first and writes nothing if a value is invalid. `queries` is a list of `{"name", "terms"}` objects. |
| `list_projects` | Lists projects, the active one, and `pinned_config` if `PRISMA_CONFIG` is set |
| `switch_project` | Makes another project active (same as the web app's switcher) |
| `create_project` | Creates a project from the template (API keys carried over) and, by default, switches to it |

### First-Pass Screening (keyword rules + AI review of "maybe" papers)

| Tool | What it does |
|------|--------------|
| `get_screening_stats` | Shows total, included, excluded, maybe counts |
| `get_papers_to_screen` | Returns a batch of "maybe" papers with titles and abstracts |
| `get_paper_details` | Full details of a specific paper |
| `screen_paper` | Save a decision for one paper |
| `batch_screen_papers` | Save decisions for multiple papers at once (a list of `{"paper_id", "decision", "reason"}`) |
| `search_in_papers` | Search within collected papers by keyword |
| `rescreen` | Re-apply the keyword rules with a different `min_include_hits` (no new search) |

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
| `download_eligible_papers` | Download PDFs (Elsevier, arXiv, Unpaywall, S2) |

### Pipeline Management

| Tool | What it does |
|------|--------------|
| `start_pipeline` | Start full pipeline in background (search, dedup, screen). Replaces the project's earlier results. |
| `get_pipeline_progress` | Check pipeline status, current step, and warnings |
| `stop_pipeline` | Cancel running pipeline (stops after current step) |
| `start_pipeline_step` | Run a single step (search, dedup, or screen) in background |

### Queries and sources

OpenAlex, Scopus, Semantic Scholar and arXiv run your Boolean query (`AND`/`OR`/`NOT` in capitals, quoted phrases, parentheses). OpenAlex and Scopus search title, abstract and keywords; Semantic Scholar title and abstract. Crossref has no Boolean search: it ranks plain terms by relevance and cannot exclude `NOT` terms. `get_review_config` lists what each source loses under `query_warnings`; see the table in [CONFIG_GUIDE.md](CONFIG_GUIDE.md#sources).

Each query and source reports its outcome (`ok`, `partial`, `failed`, `skipped`, `cancelled`); `get_pipeline_progress` shows anything other than `ok` as a warning, so a search that stopped early is never mistaken for a small result. The exact searches run are saved in `01_search/search_log.json` for your methods section (PRISMA 2020 item 7).

A free OpenAlex key (`api_keys.openalex_key`) raises OpenAlex's daily request budget 10 times and is needed to page past 10,000 results per query. `get_review_config` and `start_pipeline` warn when the key is missing. See [CONFIG_GUIDE.md](CONFIG_GUIDE.md#api-keys).

## Two-Pass Screening Workflow

### Why two passes?

Broad search queries often return hundreds of "included" papers after the first keyword screening, which is too many for a focused review. The second pass applies stricter, topic-specific criteria using AI.

### How it works

**Pass 1 (keyword rules):** Automated screening based on include/exclude keywords. Produces include/exclude/maybe decisions.

**Pass 1b (AI review of "maybe"):** Claude reviews papers that didn't clearly match keyword rules.

**Pass 2 (eligibility):** Claude applies stricter criteria to all first-pass included papers, narrowing to only the most relevant studies.

### Step-by-step

```
1. Check the setup:            "Show me the review config"   (get_review_config)
2. Run the pipeline:           "Start the pipeline"          (or: python -m prisma_review run-all)
3. Ask Claude to screen:       "Screen my 'maybe' papers about [topic]"
4. Ask Claude for eligibility:  "Do eligibility screening on included papers.
                                 Only include papers directly about [specific criteria]."
5. Generate final report:       "Generate the PRISMA report"
```

## Troubleshooting

**MCP server not found**: Check that the paths in your `.mcp.json` are correct and use forward slashes.

**"... names 'x', which ..." or "The active project 'x' ... has no config.yaml"**: `projects/.active_project` points to a project that no longer exists. Call `list_projects` and `switch_project`, or pick a project in the web app.

**"No active project and no config.yaml"**: Create a project (`create_project`, or the web app's Projects page) or, for CLI-only use, run `cp config.template.yaml config.yaml`.

**"PRISMA_CONFIG points to ..., which does not exist"**: Fix the path in the agent's MCP config, or remove `PRISMA_CONFIG` to follow the active project.

**An OpenAlex query is reported as `partial`**: OpenAlex stopped answering before all pages were fetched, usually because the daily budget ran out (HTTP 429). Add `api_keys.openalex_key` (see above) and run the search again. The warning names the reason.

**A source is reported as `failed`**: the warning carries the API's error message. Rate limits and server errors were already retried; try again later, or check the key named in the message.

**No papers to screen**: Make sure the pipeline (or `python -m prisma_review screen-rules`) ran first. The MCP server reads from the output files.

**Permission errors**: Make sure the venv Python path is correct and the `.venv` exists.
