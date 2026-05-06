export function tenantHeaders(email: string): HeadersInit {
  return { "X-Tenant-Id": email };
}

/**
 * Build headers for backend agent requests. Includes tenant id and, when
 * an entity scope is active, an `X-Entity-Scope` header listing the entity
 * ids the backend search tool must restrict retrieval to.
 *
 * Pass `scope` explicitly (rather than reading the store here) so this
 * helper stays usable in both client and server contexts.
 */
export function agentHeaders(email: string, scope?: string[]): Record<string, string> {
  const headers: Record<string, string> = { "X-Tenant-Id": email };
  if (scope && scope.length > 0) {
    headers["X-Entity-Scope"] = scope.join(",");
  }
  return headers;
}
