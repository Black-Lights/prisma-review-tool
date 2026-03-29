# PRISMA Review Tool — Wiki

Welcome to the prisma_tool documentation. This tool automates PRISMA 2020 systematic literature reviews with AI-assisted screening via the Model Context Protocol (MCP).

## Quick Navigation

| Page | Description |
|------|-------------|
| [Installation & Setup](Installation-&-Setup) | Python setup, dependencies, first run |
| [Configuration Guide](Configuration-Guide) | How to write config.yaml for any research topic |
| [Full Workflow Tutorial](Full-Workflow-Tutorial) | End-to-end walkthrough from search to final papers |
| [MCP & AI Screening](MCP-&-AI-Screening) | Set up AI-assisted screening with any MCP agent |
| [CLI Reference](CLI-Reference) | All commands, options, and output formats |
| [MCP Tools API Reference](MCP-Tools-API-Reference) | All MCP tools with parameters and response formats |
| [PRISMA 2020 Compliance](PRISMA-2020-Compliance) | How the tool aligns with PRISMA 2020, checklist mapping |
| [Writing Your Methodology](Writing-Your-Methodology) | Template for describing the tool in a thesis or paper |
| [Troubleshooting & FAQ](Troubleshooting-&-FAQ) | Common issues and solutions |

## What This Tool Does

```
1. SEARCH      arXiv, OpenAlex, Semantic Scholar    (automated)
       |
2. DEDUP       DOI matching + fuzzy title matching  (automated)
       |
3. SCREEN      Keyword rules (include/exclude)      (automated)
       |
4. AI REVIEW   "Maybe" papers reviewed by AI        (AI-assisted via MCP)
       |
5. ELIGIBILITY Stricter second-pass screening       (AI-assisted via MCP)
       |
6. EXPORT      BibTeX, CSV, PRISMA flow diagram     (automated)
```

## Supported AI Agents

The MCP server works with any agent that supports the protocol:

Claude Code, OpenAI Codex, GitHub Copilot, Cursor, Windsurf, Amazon Q, Google Gemini CLI, JetBrains AI

## License

MIT — free for any use, including commercial and academic.
