// Playwright walkthrough recorder for KnowledgeForge.
// Output: demo/recording/walkthrough.webm (then encoded to mp4 + gif).
//
// Run:
//   cd demo/recording
//   npm install && npx playwright install chromium
//   node record.mjs
//
// Required: stack on http://localhost:13000, archisurance demo seeded into
// the kb-agent container at /tmp/archisurance-demo, real liteparse on :8090.
import { chromium } from "playwright";

const BASE = process.env.KF_BASE || "http://localhost:13000";
const REPO_URL = process.env.KF_DEMO_REPO || "file:///tmp/archisurance-demo";
// Markdown is preferred over PDF for the recorded walkthrough: chromium headless
// does not render <embed type="application/pdf">, so a PDF source pane shows a
// blank box. Markdown is rendered by the inspector's built-in renderer.
// Default to a path relative to the repo root so the script works for any
// developer / CI runner without hard-coded usernames.
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
const __HERE = dirname(fileURLToPath(import.meta.url));
const DOC_PATH = process.env.KF_DEMO_DOC
  || resolve(__HERE, "../datasets/upload-demo.md");
const OUT_DIR = new URL("./", import.meta.url).pathname;

async function pause(p, ms) { await p.waitForTimeout(ms); }

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    recordVideo: { dir: OUT_DIR, size: { width: 1600, height: 1000 } },
  });
  const page = await ctx.newPage();

  // ──────────────────────────────────────────────────────────────────────
  // 1. Welcome
  // ──────────────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/welcome`, { waitUntil: "domcontentloaded" });
  await pause(page, 3000);

  // 2. Architecture
  await page.goto(`${BASE}/architecture`, { waitUntil: "domcontentloaded" });
  await pause(page, 3500);

  // ──────────────────────────────────────────────────────────────────────
  // 3a. Ingestion — DOC tab: upload a PDF, wait completion, switch tabs
  // ──────────────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/ingestion`, { waitUntil: "domcontentloaded" });
  await pause(page, 1500);

  // Upload tab is active by default
  await page.locator('input[type="file"]').first().setInputFiles(DOC_PATH);
  await pause(page, 1500);
  await page.locator('button', { hasText: /Avvia Processing/i }).first().click();

  // Watch the AgentTimeline fill up (route -> parse_start -> parse_end ...)
  // Generous fixed budget — playwright keeps recording while we wait.
  await pause(page, 75000);

  // Switch the center column to the Documento tab and click the file row
  // so the LiveInspector renders the PDF embed + parsed pane.
  try {
    const docCenterTab = page.locator('button', { hasText: 'Documento' }).first();
    if (await docCenterTab.count()) { await docCenterTab.click({ timeout: 4000 }); await pause(page, 1500); }
  } catch {}
  try {
    const docFileRow = page.locator('li[role="option"]').first();
    if (await docFileRow.count()) { await docFileRow.click({ timeout: 4000 }); await pause(page, 5000); }
  } catch {}

  // Show the auto-extracted Knowledge Graph (entities found in the PDF)
  try {
    const kgTab = page.locator('button', { hasText: /Knowledge Graph/i }).first();
    if (await kgTab.count()) { await kgTab.click({ timeout: 4000 }); await pause(page, 4000); }
  } catch {}

  // ──────────────────────────────────────────────────────────────────────
  // 3b. Ingestion — GIT tab: file:// archisurance, click multiple files
  //     in FileTree (python, markdown, sql), toggle GraphDelta
  // ──────────────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/ingestion`, { waitUntil: "domcontentloaded" });
  await pause(page, 1500);
  await page.locator('button', { hasText: 'Code Repository' }).first().click();
  await pause(page, 600);
  await page.locator('input[placeholder*="github.com"]').first().fill(REPO_URL);
  // Force include globs to cover .md / .sql so the FileTree shows mixed parsers
  const allInputs = page.locator('textarea, input[type="text"], input:not([type])');
  const total = await allInputs.count();
  for (let i = 0; i < total; i++) {
    const v = await allInputs.nth(i).inputValue().catch(() => "");
    if (v.includes("*.py")) {
      await allInputs.nth(i).fill("**/*.py,**/*.md,**/*.sql");
      break;
    }
  }
  await pause(page, 400);
  await page.locator('button', { hasText: /Ingest Repository/i }).first().click();

  // Watch the AgentTimeline populate
  await pause(page, 8000);

  // Wait for FileTree to have several rows
  for (let i = 0; i < 30; i++) {
    if (await page.locator('li[role="option"]').count() >= 4) break;
    await pause(page, 2000);
  }
  await pause(page, 4000);

  // Click a python file
  try {
    const pyRow = page.locator('li[role="option"]').filter({ hasText: 'main.py' }).first();
    if (await pyRow.count()) { await pyRow.click({ timeout: 4000 }); await pause(page, 4500); }
  } catch {}

  // Click a markdown file
  try {
    const mdRow = page.locator('li[role="option"]').filter({ hasText: '01-business' }).first();
    if (await mdRow.count()) { await mdRow.click({ timeout: 4000 }); await pause(page, 4500); }
  } catch {}

  // Click a SQL file
  try {
    const sqlRow = page.locator('li[role="option"]').filter({ hasText: 'schema.sql' }).first();
    if (await sqlRow.count()) { await sqlRow.click({ timeout: 4000 }); await pause(page, 4500); }
  } catch {}

  // Toggle the delta mini-graph
  try {
    const deltaBtn = page.locator('button').filter({ hasText: /delta graph/i }).first();
    if (await deltaBtn.count()) { await deltaBtn.click({ timeout: 4000 }); await pause(page, 3500); }
  } catch {}

  // ──────────────────────────────────────────────────────────────────────
  // 4. Graph explorer
  // ──────────────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/graph`, { waitUntil: "domcontentloaded" });
  await pause(page, 5000);
  for (let i = 0; i < 6; i++) {
    await page.mouse.move(500 + i * 70, 420 + i * 30);
    await pause(page, 220);
  }
  await pause(page, 2500);

  // ──────────────────────────────────────────────────────────────────────
  // 5. Embedding space — fraud query + camera orbit
  // ──────────────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/embeddings`, { waitUntil: "domcontentloaded" });
  await pause(page, 4500);
  const queryInput = page.locator('input[placeholder*="Project a query"]');
  if (await queryInput.count()) {
    await queryInput.click();
    await queryInput.fill("fraud detection scoring");
    await pause(page, 700);
    await page.keyboard.press("Enter");
    await pause(page, 5000);
    // orbit camera by dragging
    await page.mouse.move(720, 500);
    await page.mouse.down();
    await page.mouse.move(900, 380, { steps: 30 });
    await page.mouse.up();
    await pause(page, 2500);
  }

  // ──────────────────────────────────────────────────────────────────────
  // 6. Chat — submit query, wait for streamed answer
  // ──────────────────────────────────────────────────────────────────────
  await page.goto(
    `${BASE}/chat?prompt=${encodeURIComponent("Which business processes does the ClaimsAPI realize?")}`,
    { waitUntil: "domcontentloaded" },
  );
  await pause(page, 2500);
  const sendBtn = page.locator('button[aria-label*="Send" i], button[type="submit"]').first();
  if (await sendBtn.count()) {
    try { await sendBtn.click({ timeout: 2000 }); } catch {}
  } else {
    const ta = page.locator('textarea').first();
    if (await ta.count()) { await ta.click(); await ta.press("Enter"); }
  }
  await pause(page, 30000);

  // ──────────────────────────────────────────────────────────────────────
  // 7. Dashboard
  // ──────────────────────────────────────────────────────────────────────
  await page.goto(`${BASE}/dashboard`, { waitUntil: "domcontentloaded" });
  await pause(page, 4500);

  await ctx.close();
  await browser.close();
  console.log("Recording saved under", OUT_DIR);
}

main().catch((e) => { console.error(e); process.exit(1); });
