import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";
import { NextRequest } from "next/server";

// Fallback to localhost 8000 if ENV not provided
const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";
const COPILOTKIT_URL = BASE_URL.endsWith("/copilotkit") ? BASE_URL : `${BASE_URL}/copilotkit`;

const serviceAdapter = new ExperimentalEmptyAdapter();

export const POST = async (req: NextRequest) => {
  const tenantId = req.headers.get("x-tenant-id") || "";
  const searchScope = req.headers.get("x-search-scope") || "all";
  const sharedDatasets = req.headers.get("x-shared-datasets") || "";
  const entityScope = req.headers.get("x-entity-scope") || "";
  const agentHeaders: Record<string, string> = {
    "X-Tenant-Id": tenantId,
    "X-Search-Scope": searchScope,
  };
  if (sharedDatasets) agentHeaders["X-Shared-Datasets"] = sharedDatasets;
  if (entityScope) agentHeaders["X-Entity-Scope"] = entityScope;

  const runtime = new CopilotRuntime({
    agents: {
      kb_agent: new HttpAgent({
        url: COPILOTKIT_URL,
        headers: agentHeaders,
      }) as never,
      kb_ingestion_agent: new HttpAgent({
        url: `${BASE_URL}/copilotkit/ingestion`,
        headers: agentHeaders,
      }) as never,
    },
  });

  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime,
    serviceAdapter,
    endpoint: "/api/copilotkit",
  });

  return handleRequest(req);
};
