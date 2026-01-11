import { NextRequest, NextResponse } from "next/server";

const COOKIE = "acr_auth";

function isAuthed(req: NextRequest): boolean {
  const raw = (
    process.env.APP_AUTH_TOKENS ||
    process.env.APP_AUTH_TOKEN ||
    ""
  ).trim();
  if (!raw) return true; // auth disabled
  const allowed = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const got = req.cookies.get(COOKIE)?.value ?? "";
  return allowed.includes(got);
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Allow these routes without auth
  if (
    pathname.startsWith("/api/") ||
    pathname.startsWith("/login") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/robots") ||
    pathname.startsWith("/sitemap")
  ) {
    return NextResponse.next();
  }

  if (isAuthed(req)) return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
