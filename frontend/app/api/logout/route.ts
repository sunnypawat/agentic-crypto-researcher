export const runtime = "nodejs";

export async function POST() {
  const headers = new Headers({ "Content-Type": "application/json" });
  headers.append(
    "Set-Cookie",
    `acr_auth=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`
  );
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers,
  });
}
