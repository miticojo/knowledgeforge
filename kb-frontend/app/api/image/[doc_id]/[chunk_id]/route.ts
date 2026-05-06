import { NextRequest, NextResponse } from "next/server";

const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ doc_id: string; chunk_id: string }> }
) {
  const { doc_id, chunk_id } = await params;
  const tenantId = _req.headers.get("x-tenant-id") || "";
  try {
    const res = await fetch(`${BASE_URL}/image/${doc_id}/${chunk_id}`, {
      headers: { "X-Tenant-Id": tenantId },
    });
    if (!res.ok) {
      return NextResponse.json({ error: "Image not found" }, { status: 404 });
    }
    const buffer = await res.arrayBuffer();
    const contentType = res.headers.get("content-type") || "image/png";
    return new NextResponse(buffer, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=86400",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Backend unreachable" },
      { status: 502 }
    );
  }
}
