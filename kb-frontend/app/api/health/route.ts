import { NextResponse } from "next/server";

const BASE_URL = process.env.BACKEND_URL || "http://127.0.0.1:8080";

export async function GET() {
  try {
    const res = await fetch(`${BASE_URL}/health`, { method: "GET" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { error: error?.message || "Backend unreachable" },
      { status: 502 }
    );
  }
}
