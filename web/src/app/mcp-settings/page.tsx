"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import GlassCard from "@/components/GlassCard";
import { fetchMcpSetup } from "@/lib/api";
import { agentConfigs } from "@/lib/mcpSetup";
import {
  Cpu,
  Activity,
  Terminal,
  Copy,
  Check,
  Wrench,
} from "lucide-react";

const DOCS_URL = "https://github.com/Black-Lights/prisma-review-tool/blob/main/docs/MCP_SETUP.md";

export default function McpSettingsPage() {
  const [activeAgent, setActiveAgent] = useState("claude");
  const [pin, setPin] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const { data: setup, error, isLoading } = useQuery({
    queryKey: ["mcp-setup"],
    queryFn: fetchMcpSetup,
    staleTime: 60_000,
  });

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const configs = setup ? agentConfigs(setup, pin ? setup.active_config : null) : [];
  const activeConfig = configs.find((a) => a.id === activeAgent) ?? configs[0];
  const testCommand = setup ? `"${setup.command}" "${setup.script}"` : "";

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

      {error && (
        <div role="alert" className="glass p-3 border-l-4 border-l-accent-red text-sm text-accent-red">
          Could not read the MCP setup from the API: {(error as Error).message}. See the{" "}
          <a className="underline" href={DOCS_URL} target="_blank" rel="noreferrer">MCP setup guide</a>.
        </div>
      )}
      {isLoading && <p className="text-text-muted text-sm animate-pulse">Loading...</p>}

      {/* How the server runs */}
      <GlassCard>
        <div className="flex items-center gap-2 mb-4">
          <Activity className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-text-primary">How the server runs</h2>
        </div>
        <p className="text-sm text-text-secondary mb-3">
          The MCP server talks to the agent over stdio: the agent starts it on its own from the
          config below, so there is nothing to keep running. The web app does not need to be open.
          It works on the active project (the one picked on the Projects page) unless the config
          pins a review with <code className="font-mono">PRISMA_CONFIG</code>.
        </p>
        {setup && (
          <>
            <p className="text-sm text-text-secondary mb-2">
              To check that it starts, run this in a terminal (it waits for an agent; stop it with Ctrl+C):
            </p>
            <div className="relative">
              <pre className="font-mono bg-bg-surface p-4 pr-12 rounded-lg text-sm text-primary overflow-x-auto">
                {testCommand}
              </pre>
              <button
                onClick={() => copyToClipboard(testCommand, "server-cmd")}
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
          </>
        )}
      </GlassCard>

      {/* Agent Configuration */}
      {setup && activeConfig && (
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Terminal className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text-primary">Agent Configuration</h2>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            Add this to your agent&apos;s MCP config, then restart the agent. The paths are this install&apos;s.
          </p>

          {/* Agent Tabs */}
          <div className="flex flex-wrap gap-1 mb-4 p-1 rounded-lg bg-bg-surface/50 w-fit">
            {configs.map((agent) => (
              <button
                key={agent.id}
                onClick={() => setActiveAgent(agent.id)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeConfig.id === agent.id
                    ? "bg-primary-dim text-primary"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                {agent.name}
              </button>
            ))}
          </div>

          <p className="text-xs text-text-muted mb-2">File: {activeConfig.where}</p>
          {setup.active_config && (
            <label className="flex items-center gap-2 text-sm text-text-secondary mb-3">
              <input type="checkbox" checked={pin} onChange={(e) => setPin(e.target.checked)} />
              Pin the agent to the active project ({setup.active_config}) instead of following project switches
            </label>
          )}

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
          <p className="text-xs text-text-muted mt-3">
            Other agents (Windsurf, Amazon Q, Gemini CLI, JetBrains AI): see the{" "}
            <a className="underline" href={DOCS_URL} target="_blank" rel="noreferrer">MCP setup guide</a>.
          </p>
        </GlassCard>
      )}

      {/* Available Tools */}
      {setup && (
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Wrench className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold text-text-primary">Available Tools</h2>
          </div>
          {setup.tools.length === 0 ? (
            <p className="text-sm text-text-secondary">
              The tool list is not available ({setup.tools_error ?? "no tools found"}). See the{" "}
              <a className="underline" href={DOCS_URL} target="_blank" rel="noreferrer">MCP setup guide</a>.
            </p>
          ) : (
            <>
              <p className="text-sm text-text-secondary mb-4">
                The server gives connected agents these {setup.tools.length} tools. Every tool returns JSON.
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
                    {setup.tools.map((tool) => (
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
            </>
          )}
        </GlassCard>
      )}
    </div>
  );
}
