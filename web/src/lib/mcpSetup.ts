/**
 * The MCP config snippets the MCP Settings page shows.
 *
 * The MCP server speaks stdio only: the agent starts run_mcp.py with the
 * install's Python. GET /api/mcp/setup gives the paths for this install.
 */

export interface McpTool {
  name: string;
  description: string;
}

export interface McpSetup {
  transport: "stdio";
  command: string;
  script: string;
  cwd: string;
  active_config: string | null;
  tools: McpTool[];
  tools_error: string | null;
}

export interface AgentConfig {
  name: string;
  id: string;
  where: string;
  language: "json" | "toml";
  config: string;
}

function json(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function tomlString(value: string): string {
  return JSON.stringify(value); // a TOML basic string has the same escapes for paths
}

/** One config per agent; ``pin`` adds PRISMA_CONFIG so the agent stays on one review. */
export function agentConfigs(setup: McpSetup, pin: string | null = null): AgentConfig[] {
  const server: Record<string, unknown> = {
    command: setup.command,
    args: [setup.script],
    cwd: setup.cwd,
  };
  if (pin) server.env = { PRISMA_CONFIG: pin };
  const toml = [
    "[mcp_servers.prisma-review]",
    `command = ${tomlString(setup.command)}`,
    `args = [${tomlString(setup.script)}]`,
    `cwd = ${tomlString(setup.cwd)}`,
    ...(pin ? [`env = { PRISMA_CONFIG = ${tomlString(pin)} }`] : []),
  ].join("\n");
  return [
    {
      name: "Claude Code",
      id: "claude",
      where: ".mcp.json in your project folder (or ~/.claude.json)",
      language: "json",
      config: json({ mcpServers: { "prisma-review": server } }),
    },
    {
      name: "OpenAI Codex",
      id: "codex",
      where: "~/.codex/config.toml",
      language: "toml",
      config: toml,
    },
    {
      name: "GitHub Copilot",
      id: "copilot",
      where: ".vscode/mcp.json in your workspace",
      language: "json",
      config: json({ servers: { "prisma-review": { type: "stdio", ...server } } }),
    },
    {
      name: "Cursor",
      id: "cursor",
      where: "~/.cursor/mcp.json (or .cursor/mcp.json in a project)",
      language: "json",
      config: json({ mcpServers: { "prisma-review": server } }),
    },
  ];
}
