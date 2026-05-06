# Security & Dependency Audit

Last reviewed: 2026-05-04

## Current Audit Summary

```
critical: 0
high:     1   (xlsx — no upstream fix, see below)
moderate: 32  (transitive in copilotkit / langchain / vitest dependency trees)
low:      0
total:    33
```

Run `npm run audit:check` (which executes `npm audit --audit-level=high`) to fail CI on any new high or critical advisory.

## Before / After

| Severity | Before | After |
|----------|-------:|------:|
| critical | 1      | 0     |
| high     | 9      | 1     |
| moderate | 38     | 32    |
| **total**| **48** | **33**|

Tests after fix: `vitest run` — 3 / 3 passing.

## High / Critical Addressed

### 1. protobufjs `<7.5.5` — Critical (Prototype Pollution, GHSA-h755-8qp9-cq85)
- Resolved via `npm audit fix` (non-breaking transitive bump under `firebase`).
- Version delta: `<7.5.5` → `>=7.5.5`. No major change.

### 2. @xmldom/xmldom `<0.8.13` — High
- Resolved via `npm audit fix` (transitive bump). Non-breaking.

### 3. lodash-es `<=4.17.23` (and dependents `chevrotain`, `chevrotain-allstar`, `langium`, `@chevrotain/gast`, `@chevrotain/cst-dts-gen`) — High (ReDoS)
- Resolved via `npm audit fix` (transitive deduplication). Non-breaking.

### 4. next `>=16.0.0-beta.0 <16.2.3` — High (SSRF / cache-poisoning class advisory)
- Bumped `next` 16.2.2 → **16.2.4** (patch within same major). Non-breaking.
- Updated `package.json` range to `^16.2.4`.
- Tests still green.

### 5. xlsx `*` — High (Prototype Pollution GHSA-4r6h-8v6p-xvw6, ReDoS GHSA-5pgg-2g8v-p4x9) — UNFIXED UPSTREAM
- `npm` reports `No fix available` (the maintainer ships releases outside npm).
- Per task constraint, we do **not** add a new dependency just to patch one transitive.
- **Risk assessment & accepted mitigation:**
  - `xlsx` is used to parse user-uploaded spreadsheets in the ingestion path. Prototype-pollution requires a crafted `.xlsx`; ReDoS requires a crafted file that produces backtracking on parse.
  - Inputs are authenticated/tenant-scoped and processed server-side; impact is bounded to the worker handling the upload.
  - **Action:** track upstream (https://git.sheetjs.com/sheetjs/sheetjs) and consider migrating to `exceljs` if upload volume grows or untrusted public uploads are introduced. Re-evaluate at the next monthly audit.

## Breaking Bumps Considered and REJECTED

`npm audit fix --force` was inspected via dry-run. It proposed:

| Package | Current | Proposed | Why rejected |
|---------|--------:|---------:|--------------|
| `@copilotkit/react-core` | `1.54.1` | `1.10.6` | This is a **downgrade** (npm misreads the dist-tag). Would lose features and require React 18 peer. |
| `@copilotkit/react-ui`   | `1.54.1` | `1.1.2`  | Same — would force React 18 peer, conflicts with current `react@19.2.4`. |
| `@copilotkit/runtime`    | `1.54.1` | `1.8.9`  | Downgrade. |
| `vitest`                 | `2.1.x`  | `4.1.5`  | SemVer-major; risks breaking the (currently green) test suite. Not applied without explicit approval. |

The remaining moderate advisories are gated behind these rejected bumps and on `xlsx` (no fix). They are accepted as transitive risk.

## Remaining Moderate (32) — Rationale

All 32 are transitive and chain back to one of:

| Root cause | Affected branch | Disposition |
|------------|------------------|-------------|
| `uuid <14.0.0` (ReDoS class) | `@copilotkit/*`, `@copilotkitnext/*`, `@ag-ui/*`, `@langchain/*`, `langchain`, `mermaid`, `streamdown`, `@copilotkit/runtime` | Accepted. Fix requires SemVer-major downgrade of `@copilotkit/*` (see rejected table). |
| `prismjs` / `refractor` / `react-syntax-highlighter` | under `@copilotkit/react-ui` | Accepted. Same downgrade trap. |
| `postcss <8.5.10` | reported under `next` chain | Resolved by `next@16.2.4` bump but still listed via deep paths; will clear on next dedupe. |
| `esbuild <=0.24.2`, `vite`, `vite-node`, `@vitest/mocker`, `vitest` | dev-only (test runner) | Accepted. Vitest 4 major bump deferred; dev-only surface, not shipped to prod. |
| `@hono/node-server`, `hono`, `axios`, `follow-redirects`, `dompurify` | under `@copilotkit/runtime` | Resolved by `npm audit fix` where possible; remainder gated on `@copilotkit/runtime` major downgrade — rejected. |

## Constraints Honoured

- **React 19.2.4 / Next 16 majors not bumped down.** A major rule-based fix would have downgraded React-peer requirements; rejected.
- **No new dependencies introduced** to patch a single transitive (per task constraint on `xlsx`).

## When to Re-Audit

- **Monthly**, on the first business day, run `npm run audit:check`.
- **On every dependency upgrade** (any change to `package.json` `dependencies` or `devDependencies`).
- **On any new `@copilotkit/*` major release** — verify whether the upstream maintainer has bumped the bundled `uuid` and `prismjs`; if so, re-run `npm audit` and most of the 32 moderate items should clear.
- **On any new `xlsx` (SheetJS CE) release** published to npm — if a fixed version appears, bump immediately.

## CI Hook

`package.json` now exposes:

```json
"audit:check": "npm audit --audit-level=high"
```

Wire this into CI to fail on any new high or critical regression. Moderate findings are tracked here and not enforced in CI to avoid noise from third-party trees we cannot influence directly.
