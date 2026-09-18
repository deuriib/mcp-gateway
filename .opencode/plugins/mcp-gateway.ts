import type { Plugin } from "@opencode-ai/plugin";

const MARKER = "MCP-GWAY v2.5.0";

const MCP_RULES = `## MCP Rules — Gateway Protocol

All MCP tools run via \`gateway_*\` helpers. **Mandatory order:**

1. \`gateway_listToolFiles\` — discover servers
2. \`gateway_readToolFile\` — read \`servers/<Name>.pyi\` stub for exact tool names + params
3. \`gateway_getToolDocs\` (optional) — full docs when stub is truncated
4. \`gateway_executeToolCode\` — run Starlark: \`Server.tool(param=value)\`

> **Parallel:** Step 1 first. Steps 2-4 can run concurrently across servers/tools.

### Calling Convention (Starlark)

\`\`\`python
result = Servername.tool_name(params....)
value = result["key"]  # brackets, not dot
\`\`\`

- Sync only, keyword args, no \`try/except\`, no classes, no imports.
- Each \`executeToolCode\` scope is fresh — re-fetch or persist via MCP.

### Anti-Patterns

| Anti-Pattern                            | Fix                                       |
| :-------------------------------------- | :---------------------------------------- |
| Guessing tool names                     | Stub from \`readToolFile\` is authoritative |
| Skipping \`listToolFiles\`                | Always discover first when unsure         |
| \`executeToolCode\` before \`readToolFile\` | Confirm signature first                   |
| Assuming cross-call state               | Every call is isolated                    |`;

const COMPACTION_REINJECT = `<!-- ${MARKER} -->\n${MCP_RULES}`;

const SKILL_PATH = "skills";

const GATEWAY_URL_DEFAULT = "http://127.0.0.1:8080/mcp";

function getEnv(name: string): string | undefined {
  try {
    const env = (globalThis as unknown as { process?: { env?: Record<string, string | undefined> } })["process"]?.["env"];
    const value = env?.[name];
    return typeof value === "string" && value.trim() !== "" ? value : undefined;
  } catch {
    return undefined;
  }
}

function resolveGatewayUrl(): string {
  const override = getEnv("MCP_GWAY_URL");
  return override !== undefined ? override.trim() : GATEWAY_URL_DEFAULT;
}

function resolveGatewayHeaders(): Record<string, string> | undefined {
  const token = getEnv("MCP_GWAY_TOKEN");
  return token !== undefined ? { Authorization: `Bearer ${token.trim()}` } : undefined;
}

function ensureSkillPath(config: Record<string, any>): void {
  const skills = (config["skills"] ??= {});
  if (Array.isArray(skills)) {
    if (!skills.includes(SKILL_PATH)) {
      skills.push(SKILL_PATH);
    }
    return;
  }
  const paths = (skills["paths"] ??= []);
  if (Array.isArray(paths) && !paths.includes(SKILL_PATH)) {
    paths.push(SKILL_PATH);
  }
}

function ensureMcpGateway(config: Record<string, any>): void {
  const mcp = (config["mcp"] ??= {});
  if (!mcp["gateway"]) {
    const entry: Record<string, any> = {
      type: "remote",
      url: resolveGatewayUrl(),
      enabled: true,
      timeout: 5000,
      oauth: false,
    };
    const headers = resolveGatewayHeaders();
    if (headers) {
      entry["headers"] = headers;
    }
    mcp["gateway"] = entry;
  }
  ensureSkillPath(config);
}

function appendRules(system: unknown): unknown {
  if (typeof system === "string") {
    return system.includes(MARKER) ||
      system.includes("MCP Rules — Gateway Protocol")
      ? system
      : `${system}\n\n${COMPACTION_REINJECT}`;
  }
  if (Array.isArray(system)) {
    const joined = system.join("\n");
    if (
      joined.includes(MARKER) ||
      joined.includes("MCP Rules — Gateway Protocol")
    ) {
      return system;
    }
    return [...system, COMPACTION_REINJECT];
  }
  return COMPACTION_REINJECT;
}

export const McpGatewayPlugin: Plugin = async (_ctx) => {
  return {
    config: async (config) => {
      try {
        ensureMcpGateway(config as unknown as Record<string, any>);
      } catch {
        // Never break session bootstrap on config merge failure.
      }
    },
    "experimental.chat.system.transform": async (_input, output) => {
      try {
        const out = output as unknown as Record<string, any>;
        out["system"] = appendRules(out["system"]);
      } catch {
        // No-op: system injection must never throw.
      }
    },
    "experimental.session.compacting": async (_input, output) => {
      try {
        const out = output as unknown as Record<string, any>;
        if (Array.isArray(out["context"])) {
          out["context"].push(COMPACTION_REINJECT);
        } else if (typeof out["prompt"] === "string") {
          out["prompt"] = `${out["prompt"]}\n\n${COMPACTION_REINJECT}`;
        }
      } catch {
        // No-op: compaction re-injection must never throw.
      }
    },
  };
};

export default McpGatewayPlugin;
