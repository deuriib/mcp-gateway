import { Plugin } from "@opencode/plugin";

const MARKER = "MCP-GWAY v2.8.0";

const MCP_RULES = `## MCP Rules — Gateway Protocol

All MCP tools run via \`gateway_*\` helpers. **Mandatory order:**

1. \`gateway_listToolFiles\` — discover servers
2. \`gateway_readToolFile\` — read \`servers/<Name>.pyi\` stub for exact tool names + params
3. \`gateway_getToolDocs\` (optional) — full docs when stub is truncated
4. \`gateway_executeToolCode\` — run Starlark: \`Server.tool(param=value)\`

> **Parallel:** Step 1 first. Steps 2-4 can run concurrently across servers/tools.

### Calling Convention (Starlark)

\`\`\`python
result = Server.tool(param=value, params....)
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

const GATEWAY_URL_DEFAULT = "http://127.0.0.1:8080/mcp";
const GATEWAY_TIMEOUT_MS = 5000;

const SKILL_URL_DEFAULT =
  "https://raw.githubusercontent.com/deuriib/mcp-gateway/master/skills/mcp-gway/SKILL.md";

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

function systemHasRules(system: unknown): boolean {
  if (!Array.isArray(system)) return false;
  return system.some((entry) => {
    if (typeof entry === "string") {
      return entry.includes(MARKER) || entry.includes("MCP Rules — Gateway Protocol");
    }
    if (entry && typeof entry === "object") {
      const text = (entry as { text?: unknown })["text"];
      return typeof text === "string" && (text.includes(MARKER) || text.includes("MCP Rules — Gateway Protocol"));
    }
    return false;
  });
}

function pushRules(system: unknown): void {
  if (!Array.isArray(system) || systemHasRules(system)) return;
  (system as unknown[]).push({ type: "text", text: COMPACTION_REINJECT });
}

function resolveSkillUrl(): string {
  const override = getEnv("MCP_GWAY_SKILL_URL");
  return override !== undefined ? override.trim() : SKILL_URL_DEFAULT;
}

function stripFrontmatter(body: string): string {
  if (!body.startsWith("---")) return body;
  const end = body.indexOf("\n---", 3);
  if (end === -1) return body;
  return body.slice(end + 4).replace(/^\n+/, "");
}

function parseDescription(body: string): string | undefined {
  const match = body.match(/^---\s*\n([\s\S]*?)\n---/);
  const front = match?.[1];
  const desc = front?.match(/^\s*description:\s*(.+?)\s*$/m)?.[1];
  return desc?.trim() || undefined;
}

export default Plugin.define({
  id: "mcp-gateway",
  async setup(ctx) {
    const gatewayUrl = resolveGatewayUrl();
    const gatewayHeaders = resolveGatewayHeaders();
    const gatewayTimeout = { catalog: GATEWAY_TIMEOUT_MS, execution: GATEWAY_TIMEOUT_MS };

    await ctx.mcp.transform((editor) => {
      try {
        if (!editor.get("gateway")) {
          const config: Record<string, unknown> = {
            type: "remote",
            url: gatewayUrl,
            oauth: false,
            disabled: false,
            timeout: gatewayTimeout,
          };
          if (gatewayHeaders) {
            config["headers"] = gatewayHeaders;
          }
          editor.set("gateway", config as unknown as Parameters<typeof editor.set>[1]);
        }
      } catch {
      }
    });

    try {
      const skillUrl = resolveSkillUrl();
      const res = await fetch(skillUrl);
      if (!res.ok) throw new Error(`skill fetch ${res.status} from ${skillUrl}`);
      const raw = await res.text();
      const content = stripFrontmatter(raw);
      const description = parseDescription(raw) ?? "Manage MCP servers with the mcp-gway CLI plus Code Mode discovery.";
      await ctx.skill.transform((editor) => {
        try {
          if (!editor.get("mcp-gway")) {
            editor.add({
              id: "mcp-gway",
              name: "mcp-gway",
              description,
              location: skillUrl,
              content,
            } as unknown as Parameters<typeof editor.add>[0]);
          }
        } catch {
        }
      });
    } catch {
    }

    await ctx.session.hook("context", (event) => {
      try {
        pushRules((event as unknown as { system?: unknown })["system"]);
      } catch {
      }
    });

    await ctx.session.hook("compaction", (event) => {
      try {
        pushRules((event as unknown as { system?: unknown })["system"]);
      } catch {
      }
    });
  },
});
