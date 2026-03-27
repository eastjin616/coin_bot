import { NextResponse } from "next/server";

export async function GET() {
  const baseUrl = process.env.API_BASE_URL;
  if (!baseUrl) {
    return NextResponse.json({ error: "API_BASE_URL not configured" }, { status: 503 });
  }
  try {
    const res = await fetch(`${baseUrl}/api/trades`, {
      headers: { "X-API-Key": process.env.API_KEY ?? "" },
      cache: "no-store",
    });
    if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Backend unreachable" }, { status: 503 });
  }
}
