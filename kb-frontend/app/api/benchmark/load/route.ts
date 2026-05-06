import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

// Shared state — import from parent route would cause circular dependency,
// so we use a simple module-level state that the parent GET can also read.
// In production, this would be Redis/DB.
let loadState = {
  status: "idle" as "idle" | "loading" | "complete" | "error",
  dataset: "" as string,
  progress: 0,
  total: 0,
  message: "",
  startedAt: "",
};

// Export for the parent route to read
export { loadState };

export async function GET() {
  return NextResponse.json(loadState);
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const dataset = body.dataset || "hotpotqa";

  if (loadState.status === "loading") {
    return NextResponse.json(
      { error: "Load already in progress", ...loadState },
      { status: 409 }
    );
  }

  const isArchi = dataset === "archisurance";
  const total = isArchi ? 17 : 1989;
  const label = isArchi ? "ArchiSurance (17 documents)" : "HotpotQA (1989 documents)";

  loadState = {
    status: "loading",
    dataset,
    progress: 0,
    total,
    message: `Starting load of ${label}...`,
    startedAt: new Date().toISOString(),
  };

  // Spawn the Python ingestion script as a background process
  const projectRoot = path.resolve(process.cwd(), "..");
  const evalDir = path.join(projectRoot, "evaluation");
  const envFile = path.join(projectRoot, "kb-agent", ".env");
  const script = isArchi ? "batch_ingest.py" : "benchmark_hotpotqa.py";
  const args = isArchi
    ? [path.join(evalDir, script)]
    : [path.join(evalDir, script), "--n-questions", "200", "--skip-cleanup"];

  // Load env vars from kb-agent/.env
  const envVars: Record<string, string> = { ...process.env as Record<string, string> };
  try {
    const envContent = fs.readFileSync(envFile, "utf-8");
    for (const line of envContent.split("\n")) {
      const match = line.match(/^([A-Z_]+)=(.+)$/);
      if (match) envVars[match[1]] = match[2].trim();
    }
  } catch {
    console.error(`[benchmark-load] Failed to read ${envFile}`);
  }

  try {
    const child = spawn("python", args, {
      cwd: evalDir,
      env: {
        ...envVars,
        PYTHONUNBUFFERED: "1",
        TENANT_ID: dataset === "archisurance" ? "__shared__:archisurance" : "__shared__:hotpotqa",
      } as unknown as NodeJS.ProcessEnv,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    child.unref();

    // Monitor stdout for progress
    let output = "";
    child.stdout?.on("data", (data: Buffer) => {
      const text = data.toString();
      output += text;

      // Count ingested docs from output
      const matches = output.match(/write_to_spanner called/g);
      if (matches) {
        loadState.progress = matches.length;
        loadState.message = `Ingestion in progress: ${matches.length}/${total} documents...`;
      }

      // Check for completion
      if (text.includes("BATCH INGESTION COMPLETE") || text.includes("BENCHMARK COMPLETE")) {
        loadState.status = "complete";
        loadState.progress = total;
        loadState.message = `${label} loaded successfully!`;
      }
    });

    child.stderr?.on("data", (data: Buffer) => {
      // Ignore Spanner metrics warnings
      const text = data.toString();
      if (!text.includes("TimeSeries") && !text.includes("InvalidArgument")) {
        console.error(`[benchmark-load] ${text.slice(0, 200)}`);
      }
    });

    child.on("close", (code: number | null) => {
      if (loadState.status === "loading") {
        if (code === 0) {
          loadState.status = "complete";
          loadState.progress = total;
          loadState.message = `${label} loaded successfully!`;
        } else {
          loadState.status = "error";
          loadState.message = `Process exited with code ${code}. Check the logs.`;
        }
      }
    });

    loadState.message = `Process started for ${label}. Monitoring in progress...`;
    return NextResponse.json(loadState);
  } catch (err: any) {
    loadState.status = "error";
    loadState.message = `Process start error: ${err.message}`;
    return NextResponse.json(loadState, { status: 500 });
  }
}
