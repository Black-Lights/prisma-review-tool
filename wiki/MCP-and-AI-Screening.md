# MCP & AI Screening

## What is MCP?

**Model Context Protocol** (MCP) is an open standard (Linux Foundation) that lets AI agents call external tools. Think of it as "USB for AI" — one standard interface that works with many agents.

Our MCP server exposes your literature review data as tools that any MCP-compatible AI agent can use.

## Supported Agents

| Agent | Config Location | Notes |
|-------|----------------|-------|
| **Claude Code** | `.mcp.json` (project) or `~/.claude/settings.json` | Fully tested, recommended |
| **OpenAI Codex CLI** | `~/.codex/config.toml` | TOML format instead of JSON |
| **GitHub Copilot** | `.vscode/mcp.json` | Agent Mode required |
| **Cursor** | `~/.cursor/mcp.json` | Global or project-level |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | Via Cascade agent |
| **Amazon Q** | `~/.aws/amazonq/mcp.json` | CLI and IDE plugins |
| **Google Gemini CLI** | `settings.json` | Extensible MCP support |
| **JetBrains AI** | IDE settings UI | 2025.1+ |

## Setup

### Step 1: Copy the Example Config

```bash
cp .mcp.json.example <destination>
```

Where `<destination>` depends on your agent (see table above).

### Step 2: Edit Paths

Replace `<path-to-prisma_tool>` with the absolute path to your prisma_tool directory:

**JSON format** (Claude Code, Copilot, Cursor, Windsurf, Amazon Q):
```json
{
  "mcpServers": {
    "prisma-review": {
      "command": "/home/user/prisma_tool/.venv/bin/python",
      "args": ["run_mcp.py"],
      "cwd": "/home/user/prisma_tool"
    }
  }
}
```

**Windows paths** — use forward slashes and `Scripts/python.exe`:
```json
{
  "mcpServers": {
    "prisma-review": {
      "command": "C:/path/to/prisma-review-tool/.venv/Scripts/python.exe",
      "args": ["run_mcp.py"],
      "cwd": "C:/path/to/prisma-review-tool"
    }
  }
}
```

**TOML format** (OpenAI Codex):
```toml
[mcp_servers.prisma-review]
command = "/home/user/prisma_tool/.venv/bin/python"
args = ["run_mcp.py"]
cwd = "/home/user/prisma_tool"
```

### Step 3: Restart Agent

Restart your AI agent (or reload the window in VS Code/Cursor). The MCP server starts automatically when the agent needs it.

### Step 4: Verify

Ask your agent:
> "Use the prisma-review tools to check screening stats."

You should see your current pipeline numbers.

---

## Screening Workflow

### Phase 1: Screen "Maybe" Papers

After running the CLI pipeline (`search` → `dedup` → `screen-rules`), you'll have papers in three categories: included, excluded, and maybe.

Tell your agent:
```
Screen my remaining 'maybe' papers using the prisma-review tools.
My research is about [your topic].
Include papers about: [your inclusion criteria].
Exclude papers about: [your exclusion criteria].
```

**What the agent does:**
1. Calls `get_screening_stats` — sees how many "maybe" papers remain
2. Calls `get_papers_to_screen(batch_size=50)` — gets a batch
3. Reads each paper's title and abstract
4. Decides include/exclude for each paper
5. Calls `batch_screen_papers` — saves all decisions
6. Repeats until all "maybe" papers are processed

### Phase 2: Eligibility Screening (Second Pass)

If too many papers were included (e.g., 500+), do a stricter second pass:

```
Do eligibility screening on my included papers.
Only include papers DIRECTLY about [specific narrow criteria].
Exclude papers that are tangentially related.
```

**What the agent does:**
1. Calls `get_papers_for_eligibility(batch_size=50)` — gets first-pass included papers
2. Reads FULL abstracts (not truncated)
3. Applies stricter criteria
4. Calls `batch_eligibility_screen` — saves decisions
5. Repeats until all papers are screened

### Phase 3: Generate Report

```
Generate the PRISMA report using prisma-review tools.
```

This creates the flow diagram and exports BibTeX/CSV for both passes.

---

## Prompt Tips

The quality of AI screening depends on how clearly you describe your criteria.

**Good prompt:**
```
Screen my 'maybe' papers. My research is about deep learning
for medical image segmentation.

Include papers about:
- CNN and transformer architectures for segmentation
- Medical imaging datasets (CT, MRI, X-ray)
- Clinical validation of DL segmentation models

Exclude papers about:
- Non-medical computer vision
- Traditional methods only (thresholding, region growing without DL)
- Robotics, autonomous driving, remote sensing
```

**Bad prompt:**
```
Screen my papers about machine learning.
```

The more specific your criteria, the better the screening decisions.

---

## Pipeline Management via MCP

You can start, monitor, and stop the entire pipeline directly from your AI agent — no CLI or web dashboard needed.

### Starting the pipeline

Tell your agent:
```
Start the search pipeline using prisma-review tools.
```

The agent calls `start_pipeline`, which launches search → dedup → screen in a background thread. Results are returned immediately with a session ID.

### Monitoring progress

```
Check pipeline progress using prisma-review tools.
```

The agent calls `get_pipeline_progress` to see the current step, completed steps, and any warnings (e.g., rate-limited sources).

### Stopping the pipeline

```
Stop the running pipeline.
```

The agent calls `stop_pipeline`. The pipeline stops after the current step finishes — completed results are preserved.

### Running individual steps

```
Run just the dedup step using prisma-review tools.
```

The agent calls `start_pipeline_step(step="dedup")` to run a single step in background.

### Shared state

The MCP tools and the web dashboard share the same pipeline state. If you start a pipeline from MCP, the web dashboard shows live progress. If you stop from the dashboard, the MCP agent sees the cancellation.

---

## How Decisions Are Stored

Every decision is saved with full transparency:

```json
{
  "id": "a99d0ab0",
  "title": "Paper Title Here",
  "screen_decision": "exclude",
  "screen_reason": "General RS scene classification, not about agriculture or GFMs",
  "screen_method": "ai",
  "eligibility_decision": null,
  "eligibility_reason": null,
  "eligibility_method": null
}
```

Fields:
- `screen_decision` / `eligibility_decision`: "include" or "exclude"
- `screen_reason` / `eligibility_reason`: Why the decision was made
- `screen_method` / `eligibility_method`: "rule" (automated), "ai" (MCP agent), or "manual"

---

## Troubleshooting

**"Config file not found"**: The MCP server looks for `config.yaml` in the prisma_tool directory. Make sure you've created it from the template.

**"No papers to screen"**: Run `python -m prisma_review screen-rules` first. The MCP tools read from the output files.

**Agent doesn't see the tools**: Check that:
1. The config file is in the correct location for your agent
2. Paths use forward slashes (even on Windows)
3. The Python path points to the `.venv` inside prisma_tool
4. You restarted the agent after adding the config

**Agent stops mid-screening**: This can happen if the context window fills up. Just ask it to continue — it will pick up where it left off (already-screened papers are skipped).

**Want to override an AI decision?** Edit the JSON files directly in `prisma_output/03_screen/` or `03b_eligibility/`. Change `screen_decision` and set `screen_method` to `"manual"`.
