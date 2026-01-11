import { NextRequest } from "next/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const body = (await req.json()) as { query?: string };
  const query = (body.query ?? "").toString();

  const backend =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.BACKEND_URL ||
    "http://localhost:8000";
  const internal = process.env.BACKEND_SHARED_SECRET || "";

  const resp = await fetch(`${backend.replace(/\/$/, "")}/research`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(internal ? { "X-Internal-Auth": internal } : {}),
    },
    body: JSON.stringify({ query }),
  });

  const text = await resp.text();
  return new Response(text, {
    status: resp.status,
    headers: {
      "Content-Type": resp.headers.get("content-type") ?? "application/json",
    },
  });
}
