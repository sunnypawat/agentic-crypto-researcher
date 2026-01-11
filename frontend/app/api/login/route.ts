import { NextRequest } from "next/server";

export const runtime = "nodejs";

const COOKIE = "acr_auth";

export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as {
    token?: string;
    next?: string;
  };
  const token = String(body.token ?? "").trim();
  const next = String(body.next ?? "/").trim() || "/";

  const raw = String(
    process.env.APP_AUTH_TOKENS ?? process.env.APP_AUTH_TOKEN ?? ""
  ).trim();
  if (!raw) {
    // Auth disabled; treat as success.
    return new Response(JSON.stringify({ ok: true, next }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  const allowed = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (!token || !allowed.includes(token)) {
    return new Response(JSON.stringify({ ok: false, error: "Invalid token" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const headers = new Headers({ "Content-Type": "application/json" });
  headers.append(
    "Set-Cookie",
    `${COOKIE}=${encodeURIComponent(
      token
    )}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${60 * 60 * 24 * 7}`
  );

  return new Response(JSON.stringify({ ok: true, next }), {
    status: 200,
    headers,
  });
}
