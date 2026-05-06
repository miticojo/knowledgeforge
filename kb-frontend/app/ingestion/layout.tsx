"use client";

import { CopilotKit } from "@copilotkit/react-core";
import { useAuth } from "@/components/providers/AuthProvider";
import { SearchScopeProvider, useSearchScope } from "@/components/providers/SearchScopeProvider";

function CopilotKitWithScope({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const { scope, datasets } = useSearchScope();
  const tenantId = user?.email || "";

  return (
    <CopilotKit
      publicApiKey="any-string"
      runtimeUrl="/api/copilotkit"
      agent="kb_ingestion_agent"
      headers={{
        "X-Tenant-Id": tenantId,
        "X-Search-Scope": scope,
        "X-Shared-Datasets": datasets.join(","),
      }}
    >
      {children}
    </CopilotKit>
  );
}

export default function IngestionLayout({
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
