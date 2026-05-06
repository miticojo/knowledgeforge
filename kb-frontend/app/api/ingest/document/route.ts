import { NextRequest } from "next/server";

const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const tenantId = req.headers.get("x-tenant-id") || "";
  const contentType = req.headers.get("content-type") || "";

  const headers: Record<string, string> = {
    "X-Tenant-Id": tenantId,
    Accept: "application/json",
  };

  // Forward body verbatim — multipart/form-data needs its boundary preserved,
  // JSON bodies need Content-Type forwarded too.
  if (contentType) headers["Content-Type"] = contentType;

  let upstream: Response;
  try {
    upstream = await fetch(`${BASE_URL}/ingest/document`, {
      method: "POST",
      headers,
      body: req.body,
      // @ts-expect-error — Node's fetch needs duplex:'half' when streaming a request body.
      duplex: "half",
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
