import { NextRequest, NextResponse } from "next/server";

const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const url = new URL(req.url);
    const qs = url.searchParams.toString();
    const tenantId = req.headers.get("x-tenant-id") || "";
    const entityScope = req.headers.get("x-entity-scope") || "";

    const headers: Record<string, string> = {};
    if (tenantId) headers["X-Tenant-Id"] = tenantId;
    if (entityScope) headers["X-Entity-Scope"] = entityScope;

    const res = await fetch(
      `${BASE_URL}/graph/neighborhood/${encodeURIComponent(id)}${qs ? `?${qs}` : ""}`,
      { method: "GET", headers }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Backend unreachable";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
