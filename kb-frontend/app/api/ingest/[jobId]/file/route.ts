import { NextRequest } from "next/server";

const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await params;
  const tenantId = req.headers.get("x-tenant-id") || "";
  const path = req.nextUrl.searchParams.get("path") || "";

  if (!path) {
    return new Response(JSON.stringify({ error: "Missing 'path' query parameter" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  let upstream: Response;
  try {
    const url = `${BASE_URL}/ingest/${encodeURIComponent(jobId)}/file?path=${encodeURIComponent(path)}`;
    upstream = await fetch(url, {
      headers: {
        "X-Tenant-Id": tenantId,
        Accept: "application/json",
      },
      signal: req.signal,
      cache: "no-store",
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Backend unreachable";
    return new Response(JSON.stringify({ error: message }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store",
    },
  });
}
