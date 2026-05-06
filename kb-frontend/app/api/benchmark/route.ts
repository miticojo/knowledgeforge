import { NextRequest, NextResponse } from "next/server";

const BASE_URL =
  process.env.BACKEND_URL ||
  "http://127.0.0.1:8080";

// Status endpoint — reads state from the /load sub-route
export async function GET(req: NextRequest) {
  // Forward to /load route to get current state
  const url = new URL("/api/benchmark/load", req.url);
  try {
    const res = await fetch(url);
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({
      status: "idle",
      progress: 0,
      total: 0,
      message: "",
    });
  }
}
