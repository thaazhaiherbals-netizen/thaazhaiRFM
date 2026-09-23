import { NextRequest, NextResponse } from "next/server";
import { accessStatus, SESSION_COOKIE, sessionRole } from "./lib/session";
export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (path === "/login" || path === "/api/login" || path === "/favicon.ico") return NextResponse.next();
  const role = sessionRole(request.cookies.get(SESSION_COOKIE)?.value);
  if (!role) {
    if (path.startsWith("/api/")) return NextResponse.json({ detail: "Please sign in" }, { status: 401 });
    return NextResponse.redirect(new URL("/login", process.env.APP_URL || request.url));
  }
  if (role === "support" && !path.startsWith("/api/")
    && accessStatus(role, "GET", path) !== 200)
    return NextResponse.redirect(new URL("/customers", process.env.APP_URL || request.url), 303);
  // Server Actions enforce access in the data layer; logout remains available to viewers.
  if (path.startsWith("/api/") && accessStatus(role, request.method, path) === 403)
    return NextResponse.json({ detail: role === "viewer" ? "Viewer access is read-only" : "Customer support access does not permit this action" }, { status: 403 });
  return NextResponse.next();
}
export const config = { matcher: ["/((?!_next/static|_next/image).*)"] };
