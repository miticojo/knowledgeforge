import { NextRequest } from "next/server";

const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

// Disable any caching/buffering — this endpoint pipes a live SSE stream.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await params;
  const tenantId = req.headers.get("x-tenant-id") || "";

  let upstream: Response;
  try {
    upstream = await fetch(`${BASE_URL}/ingest/git/${jobId}/events`, {
      headers: {
        "X-Tenant-Id": tenantId,
        Accept: "text/event-stream",
      },
      // Pass through the abort signal so closing the EventSource on the
      // browser tears down the upstream connection too.
      signal: req.signal,
      cache: "no-store",
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Backend unreachable";
    return new Response(`event: failed\ndata: ${JSON.stringify({ error: message })}\n\n`, {
      status: 502,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
      },
    });
  }

  if (!upstream.ok || !upstream.body) {
    const text = upstream.body ? await upstream.text() : "";
    return new Response(
      `event: failed\ndata: ${JSON.stringify({ error: text || `Upstream ${upstream.status}` })}\n\n`,
      {
        status: upstream.status,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
        },
      }
    );
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
