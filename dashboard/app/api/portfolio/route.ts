import { NextResponse } from "next/server";

export async function GET() {
  const res = await fetch(`${process.env.API_BASE_URL}/api/portfolio`, {
    headers: { "X-API-Key": process.env.API_KEY ?? "" },
    cache: "no-store",
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  const data = await res.json();
  return NextResponse.json(data);
}
