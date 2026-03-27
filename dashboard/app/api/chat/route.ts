import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const res = await fetch(`${process.env.API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": process.env.API_KEY ?? "",
    },
    body: JSON.stringify({ message: body.message }),
  });
  if (!res.ok) return NextResponse.json({ error: "Failed" }, { status: res.status });
  const data = await res.json();
  return NextResponse.json(data);
}
