#!/usr/bin/env node
/**
 * kf-mcp — Node shim that launches the KnowledgeForge MCP stdio server.
 *
 * Strategy:
 *   1. Try the installed Python console-script `kb-mcp` (preferred).
 *   2. Fallback to `python3 -m kb_mcp_server` if `kb-mcp` is not on PATH.
 *   3. If neither works, print install hint and exit non-zero.
 *
 * Forwards all CLI arguments and the process exit code.
 */
"use strict";

const { spawn, spawnSync } = require("child_process");

const args = process.argv.slice(2);

if (args.includes("--help") || args.includes("-h")) {
  process.stdout.write(
    [
      "kf-mcp — KnowledgeForge MCP stdio server (Node shim)",
      "",
      "Usage:",
      "  kf-mcp serve --backend-url <url> [--tenant <email>]",
      "",
      "All arguments are forwarded to the Python entrypoint `kb-mcp`.",
      "",
      "Prerequisite (until kf-mcp is published to npm with bundled wheels):",
      "  pip install -e <path-to>/kb-mcp-server",
      "",
      "Environment:",
      "  BACKEND_URL   Required. URL of the kb-agent backend (Cloud Run or local).",
      "  KF_TENANT     Optional. Tenant id (email) for multi-tenant deployments.",
      "",
    ].join("\n")
  );
  process.exit(0);
}

function which(cmd) {
  const probe = spawnSync(process.platform === "win32" ? "where" : "which", [cmd], {
    stdio: ["ignore", "pipe", "ignore"],
  });
  return probe.status === 0;
}

let command;
let commandArgs;

if (which("kb-mcp")) {
  command = "kb-mcp";
  commandArgs = args;
} else if (which("python3")) {
  command = "python3";
  commandArgs = ["-m", "kb_mcp_server", ...args];
} else if (which("python")) {
  command = "python";
  commandArgs = ["-m", "kb_mcp_server", ...args];
} else {
  process.stderr.write(
    "kf-mcp: neither `kb-mcp` nor `python3` found on PATH.\n" +
      "Install the Python package first:\n" +
      "  pip install -e <path-to>/kb-mcp-server\n"
  );
  process.exit(127);
}

const child = spawn(command, commandArgs, { stdio: "inherit" });

child.on("error", (err) => {
  process.stderr.write(`kf-mcp: failed to launch ${command}: ${err.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  } else {
    process.exit(code ?? 0);
  }
});
