export const runtime = "nodejs";

export async function GET() {
  const backend =
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.BACKEND_URL ||
    "http://localhost:8000";
  const internal = process.env.BACKEND_SHARED_SECRET || "";

  try {
    const resp = await fetch(`${backend.replace(/\/$/, "")}/health`, {
      headers: {
        ...(internal ? { "X-Internal-Auth": internal } : {}),
      },
      cache: "no-store",
    });
    return new Response(await resp.text(), {
      status: resp.ok ? 200 : 502,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  } catch (e) {
    return new Response(JSON.stringify({ status: "error", error: String(e) }), {
      status: 502,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }
}
