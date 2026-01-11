import { NextRequest } from "next/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const body = await req.text();
  const backend =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.BACKEND_URL ||
    "http://localhost:8000";
  const internal = process.env.BACKEND_SHARED_SECRET || "";

  const resp = await fetch(`${backend.replace(/\/$/, "")}/research/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(internal ? { "X-Internal-Auth": internal } : {}),
    },
    body,
    cache: "no-store",
  });

  return new Response(resp.body, {
    status: resp.status,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
