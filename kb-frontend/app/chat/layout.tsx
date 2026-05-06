"use client";

import { CopilotKit } from "@copilotkit/react-core";
import { useAuth } from "@/components/providers/AuthProvider";
import { SearchScopeProvider, useSearchScope } from "@/components/providers/SearchScopeProvider";
import { useGraphStore } from "@/lib/graph-store";

function CopilotKitWithScope({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const { scope, datasets } = useSearchScope();
  const entityScope = useGraphStore((s) => s.scope);
  const tenantId = user?.email || "";

  const headers: Record<string, string> = {
    "X-Tenant-Id": tenantId,
    "X-Search-Scope": scope,
    "X-Shared-Datasets": datasets.join(","),
  };
  // Always send the header so the backend middleware explicitly clears any
  // stale entity-scope from a previous /graph polling request (the contextvar
  // global is shared across requests in ADK's ThreadPoolExecutor).
  headers["X-Entity-Scope"] = entityScope.join(",");

  return (
    <CopilotKit
      publicApiKey="any-string"
      runtimeUrl="/api/copilotkit"
      agent="kb_agent"
      headers={headers}
    >
      {children}
    </CopilotKit>
  );
}

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SearchScopeProvider>
      <CopilotKitWithScope>{children}</CopilotKitWithScope>
    </SearchScopeProvider>
  );
}
