import { NextRequest, NextResponse } from "next/server";

const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

export async function POST(req: NextRequest) {
  try {
    const tenantId = req.headers.get("x-tenant-id") || "";
    const body = await req.json();
    const res = await fetch(`${BASE_URL}/ingest/git`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Id": tenantId,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Backend unreachable";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
