"use client";

import { useState } from "react";
import GlassCard from "@/components/GlassCard";
import {
  Cpu,
  Activity,
  Terminal,
  Copy,
  Check,
  Wrench,
} from "lucide-react";

const AGENT_CONFIGS = [
  {
    name: "Claude Code",
    id: "claude",
    language: "json",
    config: `{
  "mcpServers": {
    "prisma-review": {
      "type": "sse",
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}`,
  },
  {
    name: "OpenAI Codex",
    id: "codex",
    language: "toml",
    config: `[mcp.prisma-review]
type = "sse"
url = "http://localhost:8000/mcp/sse"`,
  },
  {
    name: "GitHub Copilot",
    id: "copilot",
    language: "json",
    config: `{
  "mcp": {
    "servers": {
      "prisma-review": {
        "type": "sse",
        "url": "http://localhost:8000/mcp/sse"
      }
    }
  }
}`,
  },
  {
    name: "Cursor",
    id: "cursor",
    language: "json",
    config: `{
  "mcpServers": {
    "prisma-review": {
      "type": "sse",
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}`,
  },
];

const MCP_TOOLS = [
  { name: "get_screening_stats", description: "Get statistics for all pipeline stages (search, dedup, screening, eligibility)" },
  { name: "get_papers_to_screen", description: "Retrieve a batch of papers pending first-pass title/abstract screening" },
  { name: "screen_paper", description: "Submit a screening decision (include/exclude/maybe) for a single paper" },
  { name: "batch_screen_papers", description: "Submit screening decisions for multiple papers in one call" },
  { name: "get_papers_for_eligibility", description: "Retrieve papers that passed first-pass screening for full-text eligibility review" },
  { name: "eligibility_screen_paper", description: "Submit an eligibility decision (include/exclude) for a single paper" },
  { name: "batch_eligibility_screen", description: "Submit eligibility decisions for multiple papers in one call" },
  { name: "get_paper_details", description: "Get full metadata, abstract, and all decisions for a specific paper" },
  { name: "search_in_papers", description: "Full-text search across all paper titles and abstracts" },
  { name: "generate_report", description: "Generate a PRISMA flow diagram and summary statistics report" },
  { name: "download_eligible_papers", description: "Download open access PDFs for all eligible papers" },
];

export default function McpSettingsPage() {
  const [activeAgent, setActiveAgent] = useState("claude");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const activeConfig = AGENT_CONFIGS.find((a) => a.id === activeAgent)!;

  return (
    <div className="space-y-8">
      <div data-tutorial="mcp-header">
        <div className="flex items-center gap-3 mb-2">
          <Cpu className="w-7 h-7 text-primary" />
          <h1 className="text-2xl font-bold text-text-primary">MCP Settings</h1>
        </div>
        <p className="text-text-secondary">
          Connect AI agents to screen papers via the Model Context Protocol.
        </p>
      </div>

      {/* Server Status */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Server Status</h2>
        </div>
        <p className="text-sm text-text-secondary mb-3">
          The MCP server must be running for agents to connect. Start it with:
        </p>
        <div className="relative">
          <pre className="font-mono bg-bg-surface p-4 rounded-lg text-sm text-primary overflow-x-auto">
            uvicorn api.main:app --port 8000
          </pre>
          <button
            onClick={() => copyToClipboard("uvicorn api.main:app --port 8000", "server-cmd")}
            className="absolute top-3 right-3 p-1.5 rounded-md hover:bg-border-glass"
            title="Copy command"
          >
            {copiedId === "server-cmd" ? (
              <Check className="w-4 h-4 text-accent-green" />
            ) : (
              <Copy className="w-4 h-4 text-text-muted" />
            )}
          </button>
        </div>
      </GlassCard>

      {/* Agent Configuration */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <Terminal className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Agent Configuration</h2>
        </div>
        <p className="text-sm text-text-secondary mb-4">
          Add the following configuration to connect your preferred AI agent.
        </p>

        {/* Agent Tabs */}
        <div className="flex gap-1 mb-4 p-1 rounded-lg bg-bg-surface/50 w-fit">
          {AGENT_CONFIGS.map((agent) => (
            <button
              key={agent.id}
              onClick={() => setActiveAgent(agent.id)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                activeAgent === agent.id
                  ? "bg-primary-dim text-primary"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {agent.name}
            </button>
          ))}
        </div>

        {/* Config Block */}
        <div className="relative">
          <pre className="font-mono bg-bg-surface p-4 rounded-lg text-sm text-text-primary overflow-x-auto leading-relaxed">
            {activeConfig.config}
          </pre>
          <button
            onClick={() => copyToClipboard(activeConfig.config, activeConfig.id)}
            className="absolute top-3 right-3 flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm hover:bg-border-glass"
          >
            {copiedId === activeConfig.id ? (
              <>
                <Check className="w-4 h-4 text-accent-green" />
                <span className="text-accent-green">Copied</span>
              </>
            ) : (
              <>
                <Copy className="w-4 h-4 text-text-muted" />
                <span className="text-text-muted">Copy</span>
              </>
            )}
          </button>
        </div>
      </GlassCard>

      {/* Available Tools */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <Wrench className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">Available Tools</h2>
        </div>
        <p className="text-sm text-text-secondary mb-4">
          These {MCP_TOOLS.length} tools are exposed to connected agents via the MCP protocol.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-glass">
                <th className="text-left py-3 px-4 text-text-muted font-medium">Tool</th>
                <th className="text-left py-3 px-4 text-text-muted font-medium">Description</th>
              </tr>
            </thead>
            <tbody>
              {MCP_TOOLS.map((tool) => (
                <tr key={tool.name} className="border-b border-border-glass/50 hover:bg-bg-surface/30">
                  <td className="py-3 px-4 font-mono text-primary whitespace-nowrap">
                    {tool.name}
                  </td>
                  <td className="py-3 px-4 text-text-secondary">
                    {tool.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
