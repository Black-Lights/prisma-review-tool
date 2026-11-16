import { test } from "node:test";
import assert from "node:assert/strict";
import { agentConfigs, type McpSetup } from "../src/lib/mcpSetup.ts";

const setup: McpSetup = {
  transport: "stdio",
  command: "C:/tools/prisma_tool/.venv/Scripts/python.exe",
  script: "C:/tools/prisma_tool/run_mcp.py",
  cwd: "C:/tools/prisma_tool",
  active_config: "C:/tools/prisma_tool/projects/alpha/config.yaml",
  tools: [],
  tools_error: null,
};

test("R-24: every agent config starts the stdio server, none points at an SSE URL", () => {
  const configs = agentConfigs(setup);
  assert.deepEqual(configs.map((c) => c.id), ["claude", "codex", "copilot", "cursor"]);
  for (const c of configs) {
    assert.ok(!c.config.includes("sse") && !c.config.includes("http"), c.id);
    assert.ok(c.config.includes(setup.command) && c.config.includes(setup.script), c.id);
    assert.ok(!c.config.includes("PRISMA_CONFIG"), c.id);
  }
  const claude = JSON.parse(configs[0].config);
  assert.deepEqual(claude.mcpServers["prisma-review"], {
    command: setup.command, args: [setup.script], cwd: setup.cwd,
  });
  const copilot = JSON.parse(configs[2].config);
  assert.equal(copilot.servers["prisma-review"].type, "stdio");
  assert.match(configs[1].config, /^\[mcp_servers\.prisma-review\]\ncommand = "C:\/tools/);
});

test("R-24: pinning adds PRISMA_CONFIG to every agent config", () => {
  for (const c of agentConfigs(setup, setup.active_config)) {
    assert.ok(c.config.includes("PRISMA_CONFIG") && c.config.includes("projects/alpha/config.yaml"), c.id);
  }
  const cursor = JSON.parse(agentConfigs(setup, "x.yaml")[3].config);
  assert.deepEqual(cursor.mcpServers["prisma-review"].env, { PRISMA_CONFIG: "x.yaml" });
});
